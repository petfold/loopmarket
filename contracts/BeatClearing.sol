// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./LegVerifier.sol";

/// A successor's own fills, without its predecessors' (one hop forward).
interface IRecorded {
    function recorded(bytes32 offer) external view returns (uint256 n, uint256 d);
}

/// The optimistic beat (P2, decided with Peter 2026-09-15; docs/plans/
/// P2-batch-auction.md §2/§6, proof-fabric.md). One outcome per beat: a
/// submitter posts the beat's pins, the hash of every leg, the fills the
/// legs imply and the potentials, with a bond. During the challenge window
/// anyone may re-verify one leg on chain by supplying its full data — the
/// contract checks the data against the committed hash and runs
/// `LoopVerifier`; a leg that fails cancels the beat and pays the bond to
/// the challenger. After the window anyone finalizes: the fills are
/// recorded (the chain becomes the authority on what is filled) and the
/// bond returns. What the contract cannot verify — whether each give's
/// thing fits within the want, a graph question over the pinned catalogue
/// — is the arbiter's: an address (factbond's adjudication, P3) that may
/// cancel a beat within the window on a semantic challenge decided off
/// chain. Until an arbiter is set, semantic faults are what the bond and
/// the readers' re-derivation deter, not what the contract catches.
///
/// Each committed fill carries its offer's *cap* — the give's quantity, a
/// want's 1/1 (a want is filled whole) — so `finalize` can check that the
/// beat's fills fit what the chain has recorded since (2026-09-23). Two beats
/// submitted against the same book may each be sound at their pinned root
/// and together overfill an offer; before, only a challenge on the second
/// caught that, and `finalize` summed the fills blindly. Now the later
/// finalize cancels its beat and refunds the bond — a race, not a fraud. A
/// cap is a commitment like any other: one that is not the record's quantity,
/// a want fill that is not whole, or a give fill that is not the leg's
/// quantity convicts the beat on challenge.
///
/// The fill authority across a redeploy (2026-09-23; proof-fabric.md's open
/// problem of 2026-09-18). Fills live in the contract that recorded them, so
/// a redeployed contract knew none of them and offers cleared under the old
/// one cleared again. Now a contract is built with its `predecessors`: its
/// `filled` is what it recorded plus what each of them answers — the old
/// contracts' fills are the new one's floor, and an offer they filled is as
/// filled here. `recorded` is this contract's own. And the arbiter may
/// `retire` a contract to its successor: it takes no new beat after that,
/// and a beat still open when it retired checks, at finalize, what the
/// successor has recorded as well — so fills never race across the two in
/// either direction. (Contracts deployed before this one have no `retire`:
/// they stay open, and are read as predecessors only.) Leg verification is
/// the `LegVerifier` deployed beside it — the library outgrew EIP-170's
/// room for both.
///
/// Holds, item claims and registers (2026-09-29: C4, I3, R3b). A beat also
/// commits the holds its option legs write and the item claims its gives
/// write, each naming its leg, and the register roots it pins; a challenge
/// checks them against the leg (`LegVerifier`), and `finalize` records them
/// beside the fills. The chain is then the authority on holds as on fills:
/// a leg's remainder for its taker is the give's quantity less the fills
/// and every active hold but the taker's own exercisable ones
/// (`heldAgainst`), so an exercise by a non-holder of held capacity is
/// convicted, and a holder's fill consumes its holds first, in the order
/// they were recorded (off chain: in loop-id order — the two differ only
/// for one holder with several holds on one offer). Every time question —
/// is a hold active, is its window open, has a claim run out — is asked at
/// the beat's own clock, the block time it was submitted at. A second claim
/// by one maker on one item through another offer, like a fill beyond what
/// is left, is a race `finalize` cancels, not a fraud. Holds and claims
/// live in the contract that recorded them: a successor does not read its
/// predecessors' (none recorded any before this one), so retire a contract
/// with holds only after their windows have closed.
contract BeatClearing {
    using LoopVerifier for LoopVerifier.Beat;

    /// `n/d` taken from `offer`, which holds `capN/capD` in all (a give's
    /// quantity; 1/1 for a want, taken whole), by `taker` (keccak of the
    /// leg's wanter; 0 for the want's own fill) — whose holds on the offer
    /// the fill consumes first.
    struct Fill { bytes32 offer; uint256 n; uint256 d; uint256 capN; uint256 capD; bytes32 taker; }

    /// A hold as recorded: what of it exercises have `used`.
    struct StoredHold {
        bytes32 option;
        bytes32 holder;
        LoopVerifier.Rat qty;
        LoopVerifier.Rat used;
        uint64 from;
        uint64 until;
    }

    /// A maker's claim on an item, as recorded: through which offer, until when.
    struct StoredClaim { bytes32 offer; uint64 until; }

    struct BeatRecord {
        LoopVerifier.Beat pins;
        address submitter;
        uint256 bond;
        uint256 submittedAt;       // block number
        bytes32 legsHash;          // keccak of the leg hashes
        bytes32 potentialsHash;    // keccak of (makers, potentials)
        uint256 fillCount;
        bool finalized;
        bool cancelled;
        uint64 time;               // block time at submission: the beat's clock (C4)
        bytes32 registersHash;     // keccak of the register pins (R3b)
    }

    uint256 public immutable bondWei;
    uint256 public immutable windowBlocks;
    address public arbiter;
    LegVerifier public immutable verifier;
    StatementVerifier public immutable statements;      // R3b: a leg's statements, deployed beside it
    address[] public predecessors;             // earlier clearing contracts: their fills are the floor
    address public successor;                  // set once by `retire`; no new beat after

    uint256 public beatCount;
    mapping(uint256 => BeatRecord) public beats;
    mapping(uint256 => Fill[]) private _pending;                 // fills a beat would record
    mapping(bytes32 => LoopVerifier.Rat) private _recorded;      // this contract's own fills, exact
    mapping(uint256 => LoopVerifier.Hold[]) private _pendingHolds;          // holds a beat would record
    mapping(uint256 => LoopVerifier.ItemClaim[]) private _pendingClaims;    // item claims a beat would record
    mapping(bytes32 => StoredHold[]) private _holds;                        // underlying -> its holds
    mapping(bytes32 => mapping(bytes32 => StoredClaim)) private _claims;    // item -> maker -> claim

    event Submitted(uint256 indexed beat, bytes32 bookRoot, bytes32 legsHash, address submitter);
    event Challenged(uint256 indexed beat, uint256 leg, address challenger, string reason);
    event Cancelled(uint256 indexed beat, string reason);
    event Finalized(uint256 indexed beat, bytes32 bookRoot, uint256 fills);
    event Retired(address successor);

    constructor(uint256 bondWei_, uint256 windowBlocks_, address arbiter_, LegVerifier verifier_,
                StatementVerifier statements_, address[] memory predecessors_) {
        require(predecessors_.length <= 16, "at most 16 predecessors");
        bondWei = bondWei_;
        windowBlocks = windowBlocks_;
        arbiter = arbiter_;
        verifier = verifier_;
        statements = statements_;
        predecessors = predecessors_;
    }

    // ---- reading -------------------------------------------------------------

    /// What has been taken from an offer, exact (0/1: nothing): what this
    /// contract recorded plus what every predecessor answers.
    function filled(bytes32 offer) public view returns (uint256 n, uint256 d) {
        LoopVerifier.Rat memory r = _filledOf(offer);
        return (r.n, r.d);
    }

    /// What this contract itself recorded as taken from an offer.
    function recorded(bytes32 offer) external view returns (uint256 n, uint256 d) {
        LoopVerifier.Rat memory r = _ownOf(offer);
        return (r.n, r.d);
    }

    function predecessorCount() external view returns (uint256) {
        return predecessors.length;
    }

    function pendingFills(uint256 beat) external view returns (Fill[] memory) {
        return _pending[beat];
    }

    function pendingHolds(uint256 beat) external view returns (LoopVerifier.Hold[] memory) {
        return _pendingHolds[beat];
    }

    function pendingClaims(uint256 beat) external view returns (LoopVerifier.ItemClaim[] memory) {
        return _pendingClaims[beat];
    }

    /// The holds recorded on an offer, with what exercises used of each.
    function holdsOf(bytes32 offer) external view returns (StoredHold[] memory) {
        return _holds[offer];
    }

    /// A maker's recorded claim on an item (offer 0: none).
    function itemClaim(bytes32 item, bytes32 maker) external view returns (bytes32 offer, uint64 until) {
        StoredClaim storage c = _claims[item][maker];
        return (c.offer, c.until);
    }

    /// What active holds keep of `offer` from `taker` at `at`: every hold
    /// still running (at < until) less its used part, but the taker's own
    /// whose exercise window has opened (from <= at) — those it may take.
    function heldAgainst(bytes32 offer, bytes32 taker, uint256 at) public view returns (uint256 n, uint256 d) {
        LoopVerifier.Rat memory r = _heldAgainst(offer, taker, at);
        return (r.n, r.d);
    }

    // ---- the beat ------------------------------------------------------------

    /// Post one beat's outcome. `legHashes[i]` is keccak256(abi.encode(leg_i,
    /// statements_i)) over the `LoopVerifier.Leg` and the statements the
    /// submitter would supply to a challenge;
    /// `fills` the quantities every give and want in those legs take (a
    /// want's fill is its whole quantity as 1/1), each with its offer's cap
    /// (the give's quantity; 1/1 for a want) and its taker; `holds` and
    /// `claims` what the option legs and the gives naming items write, each
    /// naming its leg; `registers` the register roots the beat pins;
    /// `makers`/`potentials` the node potentials. The full data is expected
    /// beside the chain (the clearing book on Swarm); the chain holds the
    /// commitments.
    function submit(LoopVerifier.Beat calldata pins, LoopVerifier.RegisterPin[] calldata registers,
                    bytes32[] calldata legHashes, Fill[] calldata fills,
                    LoopVerifier.Hold[] calldata holds, LoopVerifier.ItemClaim[] calldata claims,
                    bytes[] calldata makers, LoopVerifier.Rat[] calldata potentials)
        external payable returns (uint256 beat)
    {
        require(successor == address(0), "retired: submit to the successor");
        require(msg.value == bondWei, "bond");
        require(legHashes.length >= 1 && fills.length >= 2, "an empty beat");
        require(makers.length == potentials.length, "potentials shape");
        beat = ++beatCount;
        BeatRecord storage b = beats[beat];
        b.pins = pins;
        b.submitter = msg.sender;
        b.bond = msg.value;
        b.submittedAt = block.number;
        b.legsHash = keccak256(abi.encode(legHashes));
        b.potentialsHash = keccak256(abi.encode(makers, potentials));
        b.time = uint64(block.timestamp);
        b.registersHash = keccak256(abi.encode(registers));
        for (uint256 i = 0; i < holds.length; i++) {
            LoopVerifier.Hold calldata h = holds[i];
            require(h.leg < legHashes.length && h.qty.n > 0 && h.qty.d > 0 && h.cap.d > 0
                    && h.from <= h.until, "a hold's shape");
            _pendingHolds[beat].push(h);
        }
        for (uint256 i = 0; i < claims.length; i++) {
            require(claims[i].leg < legHashes.length, "a claim's shape");
            _pendingClaims[beat].push(claims[i]);
        }
        for (uint256 i = 0; i < fills.length; i++) {
            require(fills[i].n > 0 && fills[i].d > 0, "a fill takes something");
            require(fills[i].capN > 0 && fills[i].capD > 0, "a fill names its offer's cap");
            require(fills[i].n * fills[i].capD <= fills[i].capN * fills[i].d, "a fill beyond its cap");
            // what the chain records meanwhile is checked against the caps at finalize
            _pending[beat].push(fills[i]);
        }
        b.fillCount = fills.length;
        emit Submitted(beat, pins.bookRoot, b.legsHash, msg.sender);
    }

    /// Re-verify leg `index` of a beat on chain. Reverts if the supplied data
    /// is not what was committed; cancels the beat and pays the bond to the
    /// challenger if the leg fails `LoopVerifier` or the beat's committed
    /// fills are not the leg's (the want whole, each give's quantity taken,
    /// each cap the offer's quantity); does nothing (the challenger paid gas
    /// for nothing) if the leg verifies.
    function challenge(uint256 beat, uint256 index, LoopVerifier.RegisterPin[] calldata registers,
                       bytes32[] calldata legHashes, LoopVerifier.Leg calldata leg,
                       LoopVerifier.StatementProof[] calldata proofs, bytes[] calldata makers,
                       LoopVerifier.Rat[] calldata potentials) external
    {
        BeatRecord storage b = beats[beat];
        require(b.submittedAt != 0 && !b.finalized && !b.cancelled, "no open beat");
        require(block.number <= b.submittedAt + windowBlocks, "window closed");
        require(keccak256(abi.encode(registers)) == b.registersHash, "not the committed registers");
        require(keccak256(abi.encode(legHashes)) == b.legsHash, "not the committed legs");
        require(index < legHashes.length && keccak256(abi.encode(leg, proofs)) == legHashes[index],
                "not the committed leg");
        require(keccak256(abi.encode(makers, potentials)) == b.potentialsHash,
                "not the committed potentials");
        // the fills the beat committed must be this leg's: a fault there is the
        // submitter's (the leg is the committed one), so it convicts
        string memory fault = _fillFault(beat, leg);
        if (bytes(fault).length == 0) {
            try verifier.verify(b.pins, leg, makers, potentials, _pendingHolds[beat], _pendingClaims[beat],
                                index, b.time, address(this))
                returns (LoopVerifier.Rat[] memory qtys, bytes32 taker, LoopVerifier.Parties memory parties) {
                fault = _capFault(beat, leg, qtys);
                if (bytes(fault).length == 0) fault = _takerFault(beat, leg, taker);
                if (bytes(fault).length == 0) fault = _statementFault(b.pins, registers, proofs, parties);
                if (bytes(fault).length == 0) {
                    emit Challenged(beat, index, msg.sender, "leg verifies");
                    return;
                }
            } catch Error(string memory reason) {
                fault = reason;
            } catch Panic(uint256 code) {
                // arithmetic overflow, an index out of range: a malformed leg
                fault = "leg fails: panic";
                code;
            } catch {
                // out of gas or an unknown error: NOT a conviction — the
                // challenger must bring enough gas for the verification
                revert("verification did not complete: bring more gas");
            }
        }
        _cancel(beat, fault);
        emit Challenged(beat, index, msg.sender, fault);
        payable(msg.sender).transfer(b.bond);
    }

    /// Hand the fill authority to `to`, once: no new beat here after this;
    /// beats already open still finalize, counting what `to` has recorded.
    function retire(address to) external {
        require(msg.sender == arbiter && arbiter != address(0), "not the arbiter");
        require(successor == address(0), "already retired");
        require(to != address(0) && to != address(this), "no successor");
        successor = to;
        emit Retired(to);
    }

    /// The arbiter's word on what the contract cannot compute.
    function cancelByArbiter(uint256 beat, string calldata reason) external {
        require(msg.sender == arbiter && arbiter != address(0), "not the arbiter");
        BeatRecord storage b = beats[beat];
        require(b.submittedAt != 0 && !b.finalized && !b.cancelled, "no open beat");
        require(block.number <= b.submittedAt + windowBlocks, "window closed");
        _cancel(beat, reason);
        payable(arbiter).transfer(b.bond);
    }

    /// After the window: record the fills exactly, return the bond — or, when
    /// what the chain has recorded since the beat was submitted leaves too
    /// little of an offer for its fill, cancel the beat whole (a loop clears
    /// all its legs or none) and return the bond: a race between beats
    /// sound at their own roots, not a fault of this one.
    function finalize(uint256 beat) external {
        BeatRecord storage b = beats[beat];
        require(b.submittedAt != 0 && !b.finalized && !b.cancelled, "no open beat");
        require(block.number > b.submittedAt + windowBlocks, "window open");
        // check everything before recording anything
        string memory race = _raceFault(beat, b.time);
        if (bytes(race).length != 0) {
            _cancel(beat, race);
            payable(b.submitter).transfer(b.bond);
            return;
        }
        Fill[] storage fills = _pending[beat];
        for (uint256 i = 0; i < fills.length; i++) {
            _recorded[fills[i].offer] = _plus(_ownOf(fills[i].offer), fills[i].n, fills[i].d);
            if (fills[i].taker != bytes32(0)) _consume(fills[i], b.time);
        }
        LoopVerifier.Hold[] storage holds = _pendingHolds[beat];
        for (uint256 k = 0; k < holds.length; k++) {
            LoopVerifier.Hold storage h = holds[k];
            _holds[h.underlying].push(StoredHold(h.option, h.holder, h.qty, LoopVerifier.Rat(0, 1), h.from, h.until));
        }
        LoopVerifier.ItemClaim[] storage claims = _pendingClaims[beat];
        for (uint256 k = 0; k < claims.length; k++) {
            StoredClaim storage c = _claims[claims[k].item][claims[k].maker];
            if (c.offer != claims[k].offer) c.offer = claims[k].offer;
            else if (c.until >= claims[k].until) continue;
            c.until = claims[k].until;
        }
        b.finalized = true;
        emit Finalized(beat, b.pins.bookRoot, fills.length);
        payable(b.submitter).transfer(b.bond);
    }

    // ---- the verifier, callable so a failure can be caught ------------------

    /// One leg's structural verification against this contract's fills and
    /// holds at time `at` (0: now) — what a challenge runs, callable (as
    /// `eth_call`) so a submitter or challenger asks for free first, the
    /// challenger at the beat's own clock. Returns each give's quantity.
    function verifyLegExternal(LoopVerifier.Beat calldata pins, LoopVerifier.RegisterPin[] calldata registers,
                               LoopVerifier.Leg calldata leg, LoopVerifier.StatementProof[] calldata proofs,
                               bytes[] calldata makers, LoopVerifier.Rat[] calldata potentials,
                               LoopVerifier.Hold[] calldata holds, LoopVerifier.ItemClaim[] calldata claims,
                               uint256 index, uint256 at)
        external returns (LoopVerifier.Rat[] memory qtys)
    {
        LoopVerifier.Parties memory parties;
        (qtys, , parties) = verifier.verify(pins, leg, makers, potentials, holds, claims, index,
                                            at == 0 ? block.timestamp : at, address(this));
        statements.verify(pins, registers, proofs, parties);
    }

    /// Why a leg's statements do not stand, or "" (R3b): the statement
    /// verifier's reason, as a conviction.
    function _statementFault(LoopVerifier.Beat memory pins, LoopVerifier.RegisterPin[] calldata registers,
                             LoopVerifier.StatementProof[] calldata proofs, LoopVerifier.Parties memory parties)
        private view returns (string memory)
    {
        try statements.verify(pins, registers, proofs, parties) {
            return "";
        } catch Error(string memory reason) {
            return reason;
        } catch Panic(uint256) {
            return "statement fails: panic";
        } catch {
            revert("verification did not complete: bring more gas");
        }
    }

    /// Why the beat cannot be recorded as it stands, or "": a fill beyond
    /// what fills, active holds and this beat leave of its offer; a hold
    /// beyond what they leave of its underlying; an item its maker already
    /// claims through another offer. A race between beats, not a fraud.
    function _raceFault(uint256 beat, uint256 at) private view returns (string memory) {
        Fill[] storage fills = _pending[beat];
        LoopVerifier.Hold[] storage holds = _pendingHolds[beat];
        for (uint256 i = 0; i < fills.length; i++) {
            LoopVerifier.Rat memory total = _takenOf(fills[i].offer, fills[i].taker, at);
            for (uint256 j = 0; j <= i; j++) {
                if (fills[j].offer == fills[i].offer) total = _plus(total, fills[j].n, fills[j].d);
            }
            for (uint256 k = 0; k < holds.length; k++) {
                if (holds[k].underlying == fills[i].offer) total = _plus(total, holds[k].qty.n, holds[k].qty.d);
            }
            if (total.n * fills[i].capD > fills[i].capN * total.d) return "a fill exceeds what is left of its offer";
        }
        for (uint256 k = 0; k < holds.length; k++) {
            bytes32 u = holds[k].underlying;
            LoopVerifier.Rat memory total = _takenOf(u, bytes32(0), at);
            for (uint256 i = 0; i < fills.length; i++) {
                if (fills[i].offer == u) total = _plus(total, fills[i].n, fills[i].d);
            }
            for (uint256 j = 0; j <= k; j++) {
                if (holds[j].underlying == u) total = _plus(total, holds[j].qty.n, holds[j].qty.d);
            }
            if (total.n * holds[k].cap.d > holds[k].cap.n * total.d) return "a hold exceeds what is left of its underlying";
        }
        LoopVerifier.ItemClaim[] storage claims = _pendingClaims[beat];
        for (uint256 k = 0; k < claims.length; k++) {
            StoredClaim storage c = _claims[claims[k].item][claims[k].maker];
            if (c.until > at && c.offer != claims[k].offer) return "an item its maker already claims through another offer";
            for (uint256 j = 0; j < k; j++) {
                if (claims[j].item == claims[k].item && claims[j].maker == claims[k].maker
                    && claims[j].offer != claims[k].offer) return "an item its maker already claims through another offer";
            }
        }
        return "";
    }

    /// Recorded here, by the predecessors and (once retired) the successor,
    /// plus what active holds keep from `taker` at `at`.
    function _takenOf(bytes32 offer, bytes32 taker, uint256 at) private view returns (LoopVerifier.Rat memory total) {
        total = _filledOf(offer);
        if (successor != address(0)) {
            (uint256 sn, uint256 sd) = IRecorded(successor).recorded(offer);
            if (sd != 0) total = _plus(total, sn, sd);
        }
        LoopVerifier.Rat memory held = _heldAgainst(offer, taker, at);
        if (held.n != 0) total = _plus(total, held.n, held.d);
    }

    function _heldAgainst(bytes32 offer, bytes32 taker, uint256 at) private view returns (LoopVerifier.Rat memory r) {
        r = LoopVerifier.Rat(0, 1);
        StoredHold[] storage hs = _holds[offer];
        for (uint256 k = 0; k < hs.length; k++) {
            StoredHold storage h = hs[k];
            if (at >= h.until) continue;                                  // run out: expiry needs no write
            if (taker != bytes32(0) && h.holder == taker && h.from <= at) continue;   // the taker's own
            r = _plus(r, h.qty.n * h.used.d - h.used.n * h.qty.d, h.qty.d * h.used.d);
        }
    }

    /// A holder's fill takes its exercisable holds on the offer first, in the
    /// order they were recorded; the rest came from the free remainder.
    function _consume(Fill storage f, uint256 at) private {
        StoredHold[] storage hs = _holds[f.offer];
        LoopVerifier.Rat memory need = LoopVerifier.Rat(f.n, f.d);
        for (uint256 k = 0; k < hs.length && need.n != 0; k++) {
            StoredHold storage h = hs[k];
            if (h.holder != f.taker || at < h.from || at >= h.until) continue;
            // left = qty - used; use = min(need, left)
            uint256 ln = h.qty.n * h.used.d - h.used.n * h.qty.d;
            uint256 ld = h.qty.d * h.used.d;
            if (ln == 0) continue;
            bool all = need.n * ld <= ln * need.d;                        // need <= left
            (uint256 un, uint256 ud) = all ? (need.n, need.d) : (ln, ld);
            h.used = _plus(h.used, un, ud);
            need = all ? LoopVerifier.Rat(0, 1) : _minus(need, ln, ld);
        }
    }

    /// Recorded here plus every predecessor's answer.
    function _filledOf(bytes32 offer) internal view returns (LoopVerifier.Rat memory r) {
        r = _ownOf(offer);
        for (uint256 i = 0; i < predecessors.length; i++) {
            (uint256 n, uint256 d) = IFills(predecessors[i]).filled(offer);
            if (d != 0 && n != 0) r = _plus(r, n, d);
        }
    }

    function _ownOf(bytes32 offer) internal view returns (LoopVerifier.Rat memory r) {
        r = _recorded[offer];
        if (r.d == 0) r = LoopVerifier.Rat(0, 1);
    }

    /// The beat's committed fill of `offer` (the first), and whether it exists.
    function _pendingOf(uint256 beat, bytes32 offer) private view returns (bool, Fill memory f) {
        Fill[] storage fills = _pending[beat];
        for (uint256 i = 0; i < fills.length; i++) {
            if (fills[i].offer == offer) return (true, fills[i]);
        }
        return (false, f);
    }

    /// Why the beat's committed fills are not `leg`'s, or "": the want filled
    /// whole against a cap of 1/1, every give by the quantity the leg takes.
    function _fillFault(uint256 beat, LoopVerifier.Leg calldata leg) private view returns (string memory) {
        (bool found, Fill memory w) = _pendingOf(beat, leg.want.id);
        if (!found || w.n != w.d || w.capN != w.capD) return "the want's fill is not whole";
        for (uint256 i = 0; i < leg.gives.length; i++) {
            (bool has, Fill memory g) = _pendingOf(beat, leg.gives[i].id);
            if (!has || g.n * leg.taken[i].d != leg.taken[i].n * g.d) return "fill differs from leg";
        }
        return "";
    }

    /// Why a give's committed fill does not name the leg's wanter as its
    /// taker, or "" (a taker is whose holds the fill consumes).
    function _takerFault(uint256 beat, LoopVerifier.Leg calldata leg, bytes32 taker)
        private view returns (string memory)
    {
        for (uint256 i = 0; i < leg.gives.length; i++) {
            (, Fill memory g) = _pendingOf(beat, leg.gives[i].id);
            if (g.taker != taker) return "a fill's taker is not the leg's wanter";
        }
        return "";
    }

    /// Why a give's committed cap is not its record's quantity, or "".
    function _capFault(uint256 beat, LoopVerifier.Leg calldata leg, LoopVerifier.Rat[] memory qtys)
        private view returns (string memory)
    {
        for (uint256 i = 0; i < leg.gives.length; i++) {
            (, Fill memory g) = _pendingOf(beat, leg.gives[i].id);
            if (g.capN * qtys[i].d != qtys[i].n * g.capD) return "a cap is not its give's quantity";
        }
        return "";
    }

    /// a + n/d, exact and reduced.
    function _plus(LoopVerifier.Rat memory a, uint256 n, uint256 d)
        private pure returns (LoopVerifier.Rat memory)
    {
        uint256 num = a.n * d + n * a.d;
        uint256 den = a.d * d;
        uint256 g = _gcd(num, den);
        return LoopVerifier.Rat(num / g, den / g);
    }

    /// a - n/d, exact and reduced (the caller knows a >= n/d).
    function _minus(LoopVerifier.Rat memory a, uint256 n, uint256 d)
        private pure returns (LoopVerifier.Rat memory)
    {
        uint256 num = a.n * d - n * a.d;
        uint256 den = a.d * d;
        uint256 g = _gcd(num, den);
        return LoopVerifier.Rat(num / g, den / g);
    }

    function _cancel(uint256 beat, string memory reason) private {
        beats[beat].cancelled = true;
        emit Cancelled(beat, reason);
    }

    function _gcd(uint256 a, uint256 b) private pure returns (uint256) {
        if (a == 0) return b;
        while (b != 0) { (a, b) = (b, a % b); }
        return a;
    }
}
