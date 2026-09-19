// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// The crypto escrow: a smart contract that is a loopmarket maker
/// (P3, docs/plans/P3-release-and-reclearing.md §5a, decided with Peter
/// 2026-09-19). It holds a giver's deposit against its performance — the
/// `bond` of a v5 offer: an asset, a quantity, this contract's address —
/// and releases it on a verdict: to the wanter's key on a ruling of
/// failure (the reserved quantity, or the cancellation ladder's amount
/// when the giver cancelled before the leg's window), back to the giver on
/// the wanter's countersignature of delivery or after the window with no
/// claim. Two rules make a contract a maker (§5a): it **signs by state** —
/// the ids of its standing offers are registered here, and a reader
/// authenticates an offer whose maker is this address against `offers`
/// instead of a signature (U8) — and it **takes no personal tokens**: it
/// charges nothing, so its holding is a condition on the giver's give, not
/// a leg in the loop's value arithmetic (U5 stays). The asset is whatever
/// the wanter accepts and the giver holds — the chain's native coin or any
/// ERC-20 — and the contract never converts anything: the quantity it
/// pays out was fixed at clearing (§5). The verdicts come from `arbiter`
/// (the clearing contract's arbiter hook, factbond's adjudication when it
/// exists); the wanter's countersignature is its key's transaction.
/// Physical custody and agents with fees are the roadmap's end.
interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

contract LoopEscrow {
    struct Deposit {
        address giver;      // the key that deposited, refunds go here
        address token;      // address(0): the native coin
        uint256 amount;     // what is held, in the asset's smallest unit
        uint256 released;   // paid out or refunded so far
    }

    address public arbiter;
    address public owner;
    mapping(bytes32 => Deposit) public deposits;         // offer id -> the deposit backing it
    mapping(bytes32 => bool) public offers;              // this contract's standing offers (signed by state)
    mapping(bytes32 => uint256) public reserved;         // keccak(offer, loop) -> quantity reserved for that fill
    mapping(bytes32 => bool) public settled;             // keccak(offer, loop) -> paid or refunded
    mapping(bytes32 => uint256) public reservedTotal;    // offer id -> the sum of open reservations
    mapping(bytes32 => uint256) public noticeGiven;      // offer id -> block a withdrawal was announced
    uint256 public noticeBlocks;                         // how long a withdrawal is announced before it can happen

    event Deposited(bytes32 indexed offer, address giver, address token, uint256 amount);
    event Reserved(bytes32 indexed offer, bytes32 indexed loop, uint256 amount);
    event Released(bytes32 indexed offer, bytes32 indexed loop, address to, uint256 amount, string reason);
    event Refunded(bytes32 indexed offer, bytes32 indexed loop, uint256 amount, string reason);
    event Withdrawn(bytes32 indexed offer, uint256 amount);
    event OfferRegistered(bytes32 indexed offer);
    event Notice(bytes32 indexed offer, uint256 block_);

    constructor(address arbiter_, uint256 noticeBlocks_) {
        owner = msg.sender;
        arbiter = arbiter_;
        noticeBlocks = noticeBlocks_;
    }

    // ---- a maker by state ----------------------------------------------------

    /// Register a standing offer of this contract (its escrow service): the
    /// contract's signature on the record whose id this is.
    function registerOffer(bytes32 offer) external {
        require(msg.sender == owner, "not the owner");
        offers[offer] = true;
        emit OfferRegistered(offer);
    }

    function setArbiter(address arbiter_) external {
        require(msg.sender == owner, "not the owner");
        arbiter = arbiter_;
    }

    // ---- the deposit ---------------------------------------------------------

    /// Deposit the native coin behind `offer` (the v5 `bond` naming this contract).
    function deposit(bytes32 offer) external payable {
        _deposit(offer, address(0), msg.value);
    }

    /// Deposit `amount` of an ERC-20 behind `offer`; the giver approved this contract first.
    function depositToken(bytes32 offer, address token, uint256 amount) external {
        require(token != address(0), "a token");
        require(IERC20(token).transferFrom(msg.sender, address(this), amount), "transfer failed");
        _deposit(offer, token, amount);
    }

    function _deposit(bytes32 offer, address token, uint256 amount) private {
        require(amount > 0, "nothing deposited");
        Deposit storage d = deposits[offer];
        if (d.giver == address(0)) {
            deposits[offer] = Deposit(msg.sender, token, amount, 0);
        } else {
            require(d.giver == msg.sender && d.token == token, "another deposit backs this offer");
            d.amount += amount;
            noticeGiven[offer] = 0;                      // a top-up withdraws the notice
        }
        emit Deposited(offer, msg.sender, token, amount);
    }

    /// What is held behind an offer, less what has been paid or refunded.
    function held(bytes32 offer) public view returns (uint256) {
        Deposit storage d = deposits[offer];
        return d.amount - d.released;
    }

    // ---- reservation per fill, the verdicts ----------------------------------

    function key(bytes32 offer, bytes32 loop) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(offer, loop));
    }

    /// Reserve `amount` of the deposit for one fill (the arbiter, from the
    /// cleared loop record: bond × taken / quantity, P3 §3a rule 8).
    function reserve(bytes32 offer, bytes32 loop, uint256 amount) external {
        require(msg.sender == arbiter, "not the arbiter");
        bytes32 k = key(offer, loop);
        require(reserved[k] == 0 && !settled[k], "already reserved");
        require(amount > 0 && amount <= free(offer), "beyond what is free");
        reserved[k] = amount;
        reservedTotal[offer] += amount;
        emit Reserved(offer, loop, amount);
    }

    /// A ruling of failure: pay `to` (the wanter's key) up to the reservation.
    function release(bytes32 offer, bytes32 loop, address payable to, uint256 amount, string calldata reason) external {
        require(msg.sender == arbiter, "not the arbiter");
        bytes32 k = key(offer, loop);
        require(!settled[k] && amount > 0 && amount <= reserved[k], "not within the reservation");
        settled[k] = true;
        Deposit storage d = deposits[offer];
        d.released += reserved[k];                       // the rest of the reservation returns below
        reservedTotal[offer] -= reserved[k];
        uint256 back = reserved[k] - amount;
        _pay(d.token, to, amount);
        if (back > 0) _pay(d.token, payable(d.giver), back);
        emit Released(offer, loop, to, amount, reason);
        if (back > 0) emit Refunded(offer, loop, back, "remainder of the reservation");
    }

    /// Delivery countersigned by the wanter (its key), or the arbiter after
    /// the window with no claim: the reservation returns to the giver.
    function refund(bytes32 offer, bytes32 loop, address wanter, string calldata reason) external {
        require(msg.sender == arbiter || msg.sender == wanter, "not the arbiter or the wanter");
        bytes32 k = key(offer, loop);
        require(!settled[k] && reserved[k] > 0, "nothing reserved");
        settled[k] = true;
        Deposit storage d = deposits[offer];
        uint256 amount = reserved[k];
        d.released += amount;
        reservedTotal[offer] -= amount;
        _pay(d.token, payable(d.giver), amount);
        emit Refunded(offer, loop, amount, reason);
    }

    /// What is held and reserved for no fill.
    function free(bytes32 offer) public view returns (uint256) {
        return held(offer) - reservedTotal[offer];
    }

    /// The giver announces a withdrawal; after `noticeBlocks` it may take
    /// what is free. Why the notice: the deposit backs offers that clear off
    /// chain, and a reservation arrives with the ruling, not with the loop —
    /// the notice is the window in which a fill this deposit backs gets its
    /// reservation before the deposit can leave (P3, the verdict hook on the
    /// clearing contract will reserve at finalization and shorten this).
    function notice(bytes32 offer) external {
        require(msg.sender == deposits[offer].giver, "not the giver");
        noticeGiven[offer] = block.number;
        emit Notice(offer, block.number);
    }

    function withdraw(bytes32 offer, uint256 amount) external {
        Deposit storage d = deposits[offer];
        require(msg.sender == d.giver, "not the giver");
        require(noticeGiven[offer] != 0 && block.number >= noticeGiven[offer] + noticeBlocks, "notice not served");
        require(amount > 0 && amount <= free(offer), "beyond what is free");
        d.released += amount;
        _pay(d.token, payable(d.giver), amount);
        emit Withdrawn(offer, amount);
    }

    function _pay(address token, address payable to, uint256 amount) private {
        if (token == address(0)) {
            (bool ok, ) = to.call{value: amount}("");
            require(ok, "payment failed");
        } else {
            require(IERC20(token).transfer(to, amount), "transfer failed");
        }
    }
}
