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
/// acceptable; one key, or factbond's contract) makes exactly two calls:
/// `hold` (a claim is open, the quiet timeout stops) and `resolve` (the
/// outcome: what the wanter gets, the rest to the giver). A resolver can
/// move a reservation only between that giver and that wanter, so a bad
/// adjudicator's damage is bounded to the legs that chose it.
///
/// **A held reservation is released only by a ruling or by both parties**
/// (plan D3, C1, B2; factbond's rule that only a ruling moves money,
/// 2026-09-28). With a contract resolver the escrow reads the claim inside
/// `hold` (factbond writes it first, USER-GUIDE §6) and refuses one that is
/// not the wanter's, does not name the giver as the key it concerns, claims
/// nothing or more than the reservation, or leaves the giver a shorter
/// dispute window or the procedure a shorter ruling window than the
/// reservation requires; one claim at a time. Why: factbond's `assert_` is
/// permissionless and its `retract` closes a claim with outcome 0, so before
/// this check anyone could assert and retract on a reservation for the fee
/// and the escrow refunded the giver — the claim and the ladder bypassed. A
/// retraction now reopens the reservation (the claimant withdrew, nobody
/// ruled), and a close arriving after the parties settled is acknowledged
/// without moving anything, so the resolver's own case can always end.
///
/// Four acts of the parties, each as small as `cancel` (plan D3, B2, B4,
/// D-4): a reservation marked `claimOnly` at `reserve` — cover — is never
/// countersigned; the wanter may `assign` its claim to any key; the wanter
/// and the giver may `settle` at a split each signs; the giver alone may
/// `extendClaim`, only longer (tail cover).
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

/// A contract resolver as the escrow reads it: factbond's `Assertions`,
/// whose public getter returns these fields in this order (all static, so
/// the getter's flat return decodes as this struct). `status` is its enum:
/// 5 is `Retracted`. The pair is redeployed together, so the layout is
/// pinned by the deployment, not by a version field.
interface IClaims {
    struct Claim {
        address asserter;
        address challenger;
        address consumer;
        bytes32 subject;
        uint256 outcome;
        uint16 confidence;
        uint256 bond;
        uint256 stake;
        uint64 challengeUntil;
        uint64 rulingUntil;
        uint8 status;
        uint64 rulingWindow;
        address about;
    }
    function count() external view returns (uint256);
    function assertions(uint256 id) external view returns (Claim memory);
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
        bool claimOnly;     // cover: never countersigned
        uint64 minChallenge; // the least dispute window a claim must leave the giver
        uint64 minRuling;   // the least ruling window a claim must name
        uint256 claim;      // the open claim's id at a contract resolver (0: none, or a key resolver)
        uint256 deductible; // C5: what a ruled payout leaves with the giver, this fill's share
        uint64[] ladderLead;   // the cancellation ladder: lead seconds, descending to 0 …
        uint256[] ladderAmount; // … and the amount owed at each, in the asset's unit
    }

    /// What `reserve` fixes beside the parties and the amount.
    struct Terms {
        uint64 windowStart;  // the leg's handover window, unix seconds
        uint64 windowEnd;
        uint64 claimSeconds; // how long after the window a claim may be opened
        uint64 minChallenge; // 0: the resolver's own bound suffices
        uint64 minRuling;    // the claim class's evidence period plus its rung's ruling period
        bool claimOnly;      // set by the clearing for a give under `insure`
        uint256 deductible;  // C5 (v7 records): the deposit's deductible, this fill's share
    }

    uint8 private constant RETRACTED = 5;   // IClaims.Claim.status
    uint256 private constant PAYOUT_GAS = 50_000;

    address public owner;
    address public clearing;                            // who reserves: the clearing's key or contract
    uint256 public noticeBlocks;                        // how long a withdrawal is announced
    mapping(bytes32 => Deposit) public deposits;        // offer id -> the deposit backing it
    mapping(bytes32 => bool) public offers;             // this contract's standing offers (signed by state)
    mapping(bytes32 => Reservation) internal reservations; // keccak(offer, loop) -> the reservation
    mapping(bytes32 => uint256) public reservedTotal;   // offer id -> the sum of open reservations
    mapping(bytes32 => uint256) public noticeGiven;     // offer id -> block a withdrawal was announced
    mapping(bytes32 => mapping(address => uint256)) internal splits; // key -> party -> the split it signed, + 1
    mapping(address => mapping(address => uint256)) public owed;     // token -> key -> payouts its address refused

    event Deposited(bytes32 indexed offer, address giver, address token, uint256 amount);
    event Reserved(bytes32 indexed offer, bytes32 indexed loop, address wanter, address resolver, uint256 amount);
    event Held(bytes32 indexed key);
    event Reopened(bytes32 indexed key);                 // the claim was retracted: nobody ruled
    event Closed(bytes32 indexed key);                   // a claim closed after the parties had settled
    event Assigned(bytes32 indexed key, address from, address to);
    event SplitSigned(bytes32 indexed key, address party, uint256 toWanter);
    event ClaimExtended(bytes32 indexed key, uint64 claimUntil);
    event Owed(address indexed token, address indexed to, uint256 amount);
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

    /// The claim terms fixed at `reserve`, the open claim's id, the deductible.
    function terms(bytes32 offer, bytes32 loop) external view returns (
        bool claimOnly, uint64 minChallenge, uint64 minRuling, uint256 claim, uint256 deductible) {
        Reservation storage r = reservations[key(offer, loop)];
        return (r.claimOnly, r.minChallenge, r.minRuling, r.claim, r.deductible);
    }

    /// Reserve `amount` of the deposit for one fill at clearing: the leg's
    /// wanter and window, the resolver both offers declared acceptable, the
    /// claim period after the window, what a claim must leave the giver and
    /// the procedure, whether the reservation is cover (`claimOnly`), and the
    /// wanter's cancellation ladder converted at her acceptance price into
    /// the asset's unit (leads descending to 0, amounts at most `amount`).
    /// Why the clearing passes these rather than the contract reading the
    /// loop record: the record lives in the book, and what the chain needs of
    /// it is these few numbers, which the beat's verifier can hold the
    /// clearing to.
    function reserve(bytes32 offer, bytes32 loop, address wanter, address resolver, uint256 amount,
                     Terms calldata t, uint64[] calldata ladderLead, uint256[] calldata ladderAmount) external {
        require(msg.sender == clearing, "not the clearing");
        bytes32 k = key(offer, loop);
        Reservation storage r = reservations[k];
        require(r.amount == 0 && !r.settled, "already reserved");
        require(amount > 0 && amount <= free(offer), "beyond what is free");
        require(wanter != address(0) && resolver != address(0), "a wanter and a resolver");
        // C4's formality, which no puppet cost defeats: nobody judges a claim
        // on a reservation they are a party to (THREATS T16)
        require(resolver != wanter && resolver != deposits[offer].giver, "the resolver is no party");
        require(t.windowStart <= t.windowEnd, "a window");
        require(t.deductible < amount, "a deductible below the reservation");
        require(ladderLead.length == ladderAmount.length, "a ladder");
        for (uint256 i = 0; i < ladderLead.length; i++) {
            require(ladderAmount[i] <= amount, "ladder above the reservation");
            if (i > 0) require(ladderLead[i] < ladderLead[i - 1], "ladder leads descend");
        }
        r.offer = offer; r.wanter = wanter; r.resolver = resolver; r.amount = amount;
        r.windowStart = t.windowStart; r.windowEnd = t.windowEnd; r.claimUntil = t.windowEnd + t.claimSeconds;
        r.claimOnly = t.claimOnly; r.minChallenge = t.minChallenge; r.minRuling = t.minRuling;
        r.deductible = t.deductible;
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

    /// The wanter countersigns delivery: the reservation returns to the giver
    /// now. Never on cover (`claimOnly`): an insured who countersigned out of
    /// habit would void her cover (plan D3).
    function countersign(bytes32 offer, bytes32 loop) external {
        Reservation storage r = reservations[key(offer, loop)];
        require(msg.sender == r.wanter, "not the wanter");
        require(r.amount > 0 && !r.settled, "not open");
        require(!r.claimOnly, "cover is never countersigned");
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

    /// A negotiated settlement (plan B2): the wanter and the giver each sign
    /// the same split with their own transaction, and the second signature
    /// settles it — `toWanter` to the wanter, the rest to the giver. On any
    /// open reservation, held or cover too: it ends a claim without a ruling
    /// because both parties agreed, and nobody else can trigger it. A
    /// signature of a different split replaces the signer's earlier one.
    function settle(bytes32 offer, bytes32 loop, uint256 toWanter) external {
        bytes32 k = key(offer, loop);
        Reservation storage r = reservations[k];
        address giver = deposits[offer].giver;
        require(msg.sender == r.wanter || msg.sender == giver, "not a party");
        require(r.amount > 0 && !r.settled, "not open");
        require(toWanter <= r.amount, "beyond the reservation");
        splits[k][msg.sender] = toWanter + 1;
        emit SplitSigned(k, msg.sender, toWanter);
        if (splits[k][r.wanter] == toWanter + 1 && splits[k][giver] == toWanter + 1)
            _settle(k, r, toWanter, "split");
    }

    /// The wanter assigns its claim on this reservation to any key (plan B4;
    /// D-2's subrogation, the harmed wanter assigning to the insurer that
    /// paid her): the payout and the wanter's acts are `to`'s from now on,
    /// and splits signed before are void. Not while a claim is open: the
    /// claim stays with its claimant, who sees it through or retracts it
    /// first (a retraction reopens the reservation).
    function assign(bytes32 offer, bytes32 loop, address to) external {
        bytes32 k = key(offer, loop);
        Reservation storage r = reservations[k];
        require(msg.sender == r.wanter, "not the wanter");
        require(to != address(0), "a key");
        require(to != r.resolver, "the resolver is no party");
        require(r.amount > 0 && !r.settled, "not open");
        require(!r.held, "a claim is open");
        delete splits[k][msg.sender];
        delete splits[k][deposits[offer].giver];
        r.wanter = to;
        emit Assigned(k, msg.sender, to);
    }

    /// The giver lengthens the claim period (plan D-4: tail cover, sold as a
    /// give): only the giver, whose exposure it is, and only longer.
    function extendClaim(bytes32 offer, bytes32 loop, uint64 seconds_) external {
        bytes32 k = key(offer, loop);
        Reservation storage r = reservations[k];
        require(msg.sender == deposits[offer].giver, "not the giver");
        require(r.amount > 0 && !r.settled, "not open");
        require(seconds_ > 0, "only longer");
        r.claimUntil += seconds_;
        emit ClaimExtended(k, r.claimUntil);
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
        require(!r.held, "a claim is open");
        require(block.timestamp <= r.claimUntil, "claim period over");
        if (msg.sender.code.length > 0) r.claim = _claimFits(k, r);
        r.held = true;
        emit Held(k);
    }

    /// The claim a contract resolver is opening, read before it opens (a
    /// revert here and the assertion never exists): the wanter's own, naming
    /// the giver it concerns so the giver's watcher is told, a payout within
    /// the reservation, and windows no shorter than the reservation's. A key
    /// resolver is the parties' chosen stand-in and is not read.
    function _claimFits(bytes32 k, Reservation storage r) private view returns (uint256 id) {
        IClaims claims = IClaims(msg.sender);
        id = claims.count();
        IClaims.Claim memory c = claims.assertions(id);
        require(c.consumer == address(this) && c.subject == k, "not this reservation's claim");
        require(c.asserter == r.wanter, "the claim is the wanter's");
        require(c.about == deposits[r.offer].giver, "a claim names the giver it concerns");
        require(c.outcome > 0 && c.outcome <= r.amount, "a payout within the reservation");
        require(c.outcome > r.deductible, "a claim within the deductible pays nothing");
        require(c.challengeUntil >= block.timestamp + r.minChallenge, "challenge window too short");
        require(c.rulingWindow >= r.minRuling, "ruling window too short");
    }

    /// The claim resolved: `toWanter` of the reservation, less the deductible
    /// (C5), to the wanter, the rest to the giver. The resolver's one power,
    /// bounded to this fill. The deductible applies to a ruling only: the
    /// parties' own split and the giver's cancellation are their terms.
    function resolve(bytes32 offer, bytes32 loop, uint256 toWanter) external {
        _resolve(key(offer, loop), reservations[key(offer, loop)], toWanter);
    }

    function _resolve(bytes32 k, Reservation storage r, uint256 toWanter) private {
        require(msg.sender == r.resolver, "not the resolver");
        require(r.amount > 0 && r.held, "no claim held");
        r.held = false;
        if (r.settled) {
            // The parties settled while the claim was open (a split, a
            // countersign): nothing is left to move. Not a revert, which
            // would strand the resolver's case and its stakes.
            emit Closed(k);
            return;
        }
        if (toWanter == 0 && r.claim != 0 && IClaims(msg.sender).assertions(r.claim).status == RETRACTED) {
            // The claimant withdrew and nobody ruled: the reservation reopens,
            // a new claim may open within the claim period, the quiet path after.
            r.claim = 0;
            emit Reopened(k);
            return;
        }
        require(toWanter <= r.amount, "beyond the reservation");
        _settle(k, r, toWanter > r.deductible ? toWanter - r.deductible : 0, "resolved");
    }

    function _settle(bytes32 k, Reservation storage r, uint256 toWanter, string memory how) private {
        r.settled = true;
        Deposit storage d = deposits[r.offer];
        d.released += r.amount;
        reservedTotal[r.offer] -= r.amount;
        uint256 toGiver = r.amount - toWanter;
        if (toWanter > 0) _payOut(d.token, r.wanter, toWanter);
        if (toGiver > 0) _payOut(d.token, d.giver, toGiver);
        emit Settled(k, toWanter, toGiver, how);
    }

    /// A settlement's payout: pushed, and credited to `owed` when the
    /// address refuses it. Why not a plain transfer: a settlement is often
    /// someone else's call — the resolver's close, the quiet settle, the
    /// counterparty's cancel or countersign — and a recipient whose address
    /// reverts (or a contract burning the gas) would otherwise block it, and
    /// with it the resolver's own case. The native push forwards
    /// `PAYOUT_GAS`, enough for a contract wallet's receive; what is refused
    /// waits for `collect`.
    function _payOut(address token, address to, uint256 amount) private {
        bool ok;
        if (token == address(0)) {
            (ok, ) = payable(to).call{value: amount, gas: PAYOUT_GAS}("");
        } else {
            bytes memory ret;
            (ok, ret) = token.call(abi.encodeWithSelector(IERC20.transfer.selector, to, amount));
            ok = ok && ret.length >= 32 && abi.decode(ret, (bool));
        }
        if (!ok) {
            owed[token][to] += amount;
            emit Owed(token, to, amount);
        }
    }

    /// A payout an address refused, collected by that key itself.
    function collect(address token) external {
        uint256 amount = owed[token][msg.sender];
        require(amount > 0, "nothing owed");
        owed[token][msg.sender] = 0;
        _pay(token, payable(msg.sender), amount);
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
