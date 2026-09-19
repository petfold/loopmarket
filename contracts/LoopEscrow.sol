// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// The crypto escrow: a smart contract that is a loopmarket maker
/// (P3, docs/plans/P3-release-and-reclearing.md §5a and §5e, decided with
/// Peter 2026-09-19). It holds a giver's deposit — the `bond` of a v5
/// offer: an asset, a quantity, this contract's address — behind the
/// offer id, reserves a share of it per fill at clearing, and settles
/// each reservation **by timeout or by the giver's and wanter's own
/// acts** wherever nothing is disputed:
///
///   - quiet after the window: a claim period passes with no claim held
///     and anyone settles — the reservation returns to the giver;
///   - countersigned delivery: the wanter's own transaction returns it now;
///   - the giver's cancellation: the giver's own transaction pays the
///     wanter the ladder's amount at that lead and returns the rest.
///
/// Only a **contested claim** needs a ruling, and the claim mechanism —
/// stakes, contest, escalation, the adjudicator at the top, the fee — is
/// factbond's, not a second copy here. The `resolver` fixed for the
/// reservation at clearing (the adjudicator both offers declared
/// acceptable; today one key, later factbond's contract) makes exactly
/// two calls: `hold` (a claim is open, the quiet timeout stops) and
/// `resolve` (the outcome: what the wanter gets, the rest to the giver).
/// A resolver can move a reservation only between that giver and that
/// wanter, so a bad adjudicator's damage is bounded to the legs that
/// chose it.
///
/// Two rules make a contract a maker (§5a): it **signs by state** — the
/// ids of its standing offers are registered here, and a reader
/// authenticates an offer whose maker is this address against `offers`
/// instead of a signature (U8) — and it **takes no personal tokens**: it
/// charges nothing, so its holding is a condition on the giver's give,
/// not a leg in the loop's value arithmetic (U5 stays). The asset is
/// whatever the wanter accepts and the giver holds — the chain's native
/// coin or any ERC-20 — and the contract never converts anything: every
/// quantity here was fixed at clearing in the asset's own unit (§5).
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

    struct Reservation {
        bytes32 offer;      // the deposit this reservation draws on
        address wanter;     // the leg's counterparty: payouts go here
        address resolver;   // who may hold and resolve a contested claim
        uint256 amount;     // the share reserved for this fill (bond × taken / quantity)
        uint64 windowStart; // the leg's handover window, unix seconds
        uint64 windowEnd;
        uint64 claimUntil;  // a claim may be opened until here; after, anyone settles
        bool held;          // a claim is open: the quiet timeout does not settle
        bool settled;
        uint64[] ladderLead;   // the cancellation ladder: lead seconds, descending to 0 …
        uint256[] ladderAmount; // … and the amount owed at each, in the asset's unit
    }

    address public owner;
    address public clearing;                            // who reserves: the clearing's key or contract
    uint256 public noticeBlocks;                        // how long a withdrawal is announced
    mapping(bytes32 => Deposit) public deposits;        // offer id -> the deposit backing it
    mapping(bytes32 => bool) public offers;             // this contract's standing offers (signed by state)
    mapping(bytes32 => Reservation) internal reservations; // keccak(offer, loop) -> the reservation
    mapping(bytes32 => uint256) public reservedTotal;   // offer id -> the sum of open reservations
    mapping(bytes32 => uint256) public noticeGiven;     // offer id -> block a withdrawal was announced

    event Deposited(bytes32 indexed offer, address giver, address token, uint256 amount);
    event Reserved(bytes32 indexed offer, bytes32 indexed loop, address wanter, address resolver, uint256 amount);
    event Held(bytes32 indexed key);
    event Settled(bytes32 indexed key, uint256 toWanter, uint256 toGiver, string how);
    event Withdrawn(bytes32 indexed offer, uint256 amount);
    event Notice(bytes32 indexed offer, uint256 block_);
    event OfferRegistered(bytes32 indexed offer);

    constructor(address clearing_, uint256 noticeBlocks_) {
        owner = msg.sender;
        clearing = clearing_;
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

    function setClearing(address clearing_) external {
        require(msg.sender == owner, "not the owner");
        clearing = clearing_;
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

    /// What is held and reserved for no fill.
    function free(bytes32 offer) public view returns (uint256) {
        return held(offer) - reservedTotal[offer];
    }

    // ---- the reservation per fill --------------------------------------------

    function key(bytes32 offer, bytes32 loop) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(offer, loop));
    }

    function reservation(bytes32 offer, bytes32 loop) external view returns (
        address wanter, address resolver, uint256 amount, uint64 windowStart, uint64 windowEnd,
        uint64 claimUntil, bool isHeld, bool settled, uint64[] memory ladderLead, uint256[] memory ladderAmount) {
        Reservation storage r = reservations[key(offer, loop)];
        return (r.wanter, r.resolver, r.amount, r.windowStart, r.windowEnd, r.claimUntil, r.held, r.settled,
                r.ladderLead, r.ladderAmount);
    }

    /// Reserve `amount` of the deposit for one fill at clearing: the leg's
    /// wanter and window, the resolver both offers declared acceptable, the
    /// claim period after the window, and the wanter's cancellation ladder
    /// converted at her acceptance price into the asset's unit (leads
    /// descending to 0, amounts at most `amount`). Why the clearing passes
    /// these rather than the contract reading the loop record: the record
    /// lives in the book, and what the chain needs of it is these few
    /// numbers, which the beat's verifier can hold the clearing to.
    function reserve(bytes32 offer, bytes32 loop, address wanter, address resolver, uint256 amount,
                     uint64 windowStart, uint64 windowEnd, uint64 claimSeconds,
                     uint64[] calldata ladderLead, uint256[] calldata ladderAmount) external {
        require(msg.sender == clearing, "not the clearing");
        bytes32 k = key(offer, loop);
        Reservation storage r = reservations[k];
        require(r.amount == 0 && !r.settled, "already reserved");
        require(amount > 0 && amount <= free(offer), "beyond what is free");
        require(wanter != address(0) && resolver != address(0), "a wanter and a resolver");
        require(windowStart <= windowEnd, "a window");
        require(ladderLead.length == ladderAmount.length, "a ladder");
        for (uint256 i = 0; i < ladderLead.length; i++) {
            require(ladderAmount[i] <= amount, "ladder above the reservation");
            if (i > 0) require(ladderLead[i] < ladderLead[i - 1], "ladder leads descend");
        }
        r.offer = offer; r.wanter = wanter; r.resolver = resolver; r.amount = amount;
        r.windowStart = windowStart; r.windowEnd = windowEnd; r.claimUntil = windowEnd + claimSeconds;
        r.ladderLead = ladderLead; r.ladderAmount = ladderAmount;
        reservedTotal[offer] += amount;
        emit Reserved(offer, loop, wanter, resolver, amount);
    }

    /// The ladder read at `lead` seconds before the window: the amount at the
    /// nearest point at or below, linear between points, the last point past
    /// the far end, the whole reservation at lead 0 with no ladder.
    function ladderAt(bytes32 offer, bytes32 loop, uint64 lead) public view returns (uint256) {
        Reservation storage r = reservations[key(offer, loop)];
        uint256 n = r.ladderLead.length;
        if (n == 0) return r.amount;
        if (lead >= r.ladderLead[0]) return r.ladderAmount[0];
        for (uint256 i = 1; i < n; i++) {
            if (lead >= r.ladderLead[i]) {
                uint256 span = r.ladderLead[i - 1] - r.ladderLead[i];
                uint256 into = r.ladderLead[i - 1] - lead;   // from the farther point toward the nearer
                // linear: amount[i-1] + (amount[i] - amount[i-1]) * into / span, either direction
                if (r.ladderAmount[i] >= r.ladderAmount[i - 1])
                    return r.ladderAmount[i - 1] + (r.ladderAmount[i] - r.ladderAmount[i - 1]) * into / span;
                return r.ladderAmount[i - 1] - (r.ladderAmount[i - 1] - r.ladderAmount[i]) * into / span;
            }
        }
        return r.ladderAmount[n - 1];
    }

    // ---- the undisputed paths ------------------------------------------------

    /// The giver cancels the leg: the wanter is owed the ladder's amount at
    /// this lead (the whole reservation once the window has begun), the rest
    /// returns. The giver's own act; nobody can dispute it.
    function cancel(bytes32 offer, bytes32 loop) external {
        Reservation storage r = reservations[key(offer, loop)];
        require(msg.sender == deposits[offer].giver, "not the giver");
        require(r.amount > 0 && !r.settled && !r.held, "not open");
        uint64 lead = block.timestamp < r.windowStart ? r.windowStart - uint64(block.timestamp) : 0;
        _settle(key(offer, loop), r, lead == 0 ? r.amount : ladderAt(offer, loop, lead), "cancelled");
    }

    /// The wanter countersigns delivery: the reservation returns to the giver now.
    function countersign(bytes32 offer, bytes32 loop) external {
        Reservation storage r = reservations[key(offer, loop)];
        require(msg.sender == r.wanter, "not the wanter");
        require(r.amount > 0 && !r.settled, "not open");
        _settle(key(offer, loop), r, 0, "countersigned");
    }

    /// Quiet after the window: the claim period passed with no claim held,
    /// and anyone returns the reservation to the giver.
    function settle(bytes32 offer, bytes32 loop) external {
        Reservation storage r = reservations[key(offer, loop)];
        require(r.amount > 0 && !r.settled, "not open");
        require(!r.held, "a claim is open");
        require(block.timestamp > r.claimUntil, "claim period open");
        _settle(key(offer, loop), r, 0, "quiet");
    }

    // ---- the resolver's two calls --------------------------------------------
    // Two spellings of each: by (offer, loop) for people and the CLI, and by
    // the reservation's key alone — the `subject` a generic resolver such as
    // factbond's `Assertions` knows (its IConsumer: `hold(bytes32)`,
    // `resolve(bytes32, uint256)`); the key is keccak(offer, loop), so the
    // subject of a claim on a fill is derivable by anyone from the record.

    function hold(bytes32 k) external {
        _hold(k, reservations[k]);
    }

    function resolve(bytes32 k, uint256 toWanter) external {
        _resolve(k, reservations[k], toWanter);
    }

    /// A claim about this fill is open (factbond: a bonded assertion whose
    /// subject is this key): the quiet timeout stops.
    function hold(bytes32 offer, bytes32 loop) external {
        _hold(key(offer, loop), reservations[key(offer, loop)]);
    }

    function _hold(bytes32 k, Reservation storage r) private {
        require(msg.sender == r.resolver, "not the resolver");
        require(r.amount > 0 && !r.settled, "not open");
        require(block.timestamp <= r.claimUntil, "claim period over");
        r.held = true;
        emit Held(k);
    }

    /// The claim resolved: `toWanter` of the reservation to the wanter, the
    /// rest to the giver. The resolver's one power, bounded to this fill.
    function resolve(bytes32 offer, bytes32 loop, uint256 toWanter) external {
        _resolve(key(offer, loop), reservations[key(offer, loop)], toWanter);
    }

    function _resolve(bytes32 k, Reservation storage r, uint256 toWanter) private {
        require(msg.sender == r.resolver, "not the resolver");
        require(r.amount > 0 && !r.settled && r.held, "no claim held");
        require(toWanter <= r.amount, "beyond the reservation");
        _settle(k, r, toWanter, "resolved");
    }

    function _settle(bytes32 k, Reservation storage r, uint256 toWanter, string memory how) private {
        r.settled = true;
        Deposit storage d = deposits[r.offer];
        d.released += r.amount;
        reservedTotal[r.offer] -= r.amount;
        uint256 toGiver = r.amount - toWanter;
        if (toWanter > 0) _pay(d.token, payable(r.wanter), toWanter);
        if (toGiver > 0) _pay(d.token, payable(d.giver), toGiver);
        emit Settled(k, toWanter, toGiver, how);
    }

    // ---- the giver leaves ----------------------------------------------------

    /// The giver announces a withdrawal; after `noticeBlocks` it may take
    /// what is free. Why the notice: the deposit backs offers that clear off
    /// chain, and a reservation arrives with the clearing's call, not with
    /// the loop — the notice is the window in which a fill this deposit
    /// backs gets its reservation before the deposit can leave.
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
