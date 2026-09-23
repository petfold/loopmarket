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
contract BeatClearing {
    using LoopVerifier for LoopVerifier.Beat;

    /// `n/d` taken from `offer`, which holds `capN/capD` in all (a give's
    /// quantity; 1/1 for a want, taken whole).
    struct Fill { bytes32 offer; uint256 n; uint256 d; uint256 capN; uint256 capD; }

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
    }

    uint256 public immutable bondWei;
    uint256 public immutable windowBlocks;
    address public arbiter;
    LegVerifier public immutable verifier;
    address[] public predecessors;             // earlier clearing contracts: their fills are the floor
    address public successor;                  // set once by `retire`; no new beat after

    uint256 public beatCount;
    mapping(uint256 => BeatRecord) public beats;
    mapping(uint256 => Fill[]) private _pending;                 // fills a beat would record
    mapping(bytes32 => LoopVerifier.Rat) private _recorded;      // this contract's own fills, exact

    event Submitted(uint256 indexed beat, bytes32 bookRoot, bytes32 legsHash, address submitter);
    event Challenged(uint256 indexed beat, uint256 leg, address challenger, string reason);
    event Cancelled(uint256 indexed beat, string reason);
    event Finalized(uint256 indexed beat, bytes32 bookRoot, uint256 fills);
    event Retired(address successor);

    constructor(uint256 bondWei_, uint256 windowBlocks_, address arbiter_, LegVerifier verifier_,
                address[] memory predecessors_) {
        require(predecessors_.length <= 16, "at most 16 predecessors");
        bondWei = bondWei_;
        windowBlocks = windowBlocks_;
        arbiter = arbiter_;
        verifier = verifier_;
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

    // ---- the beat ------------------------------------------------------------

    /// Post one beat's outcome. `legHashes[i]` is keccak256(abi.encode(leg_i))
    /// over the `LoopVerifier.Leg` the submitter would supply to a challenge;
    /// `fills` the quantities every give and want in those legs take (a
    /// want's fill is its whole quantity as 1/1), each with its offer's cap
    /// (the give's quantity; 1/1 for a want); `makers`/`potentials` the
    /// node potentials. The full data is expected beside the chain (the
    /// clearing book on Swarm); the chain holds the commitments.
    function submit(LoopVerifier.Beat calldata pins, bytes32[] calldata legHashes,
                    Fill[] calldata fills, bytes[] calldata makers,
                    LoopVerifier.Rat[] calldata potentials)
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
    function challenge(uint256 beat, uint256 index, bytes32[] calldata legHashes,
                       LoopVerifier.Leg calldata leg, bytes[] calldata makers,
                       LoopVerifier.Rat[] calldata potentials) external
    {
        BeatRecord storage b = beats[beat];
        require(b.submittedAt != 0 && !b.finalized && !b.cancelled, "no open beat");
        require(block.number <= b.submittedAt + windowBlocks, "window closed");
        require(keccak256(abi.encode(legHashes)) == b.legsHash, "not the committed legs");
        require(index < legHashes.length && keccak256(abi.encode(leg)) == legHashes[index],
                "not the committed leg");
        require(keccak256(abi.encode(makers, potentials)) == b.potentialsHash,
                "not the committed potentials");
        // the fills the beat committed must be this leg's: a fault there is the
        // submitter's (the leg is the committed one), so it convicts
        string memory fault = _fillFault(beat, leg);
        if (bytes(fault).length == 0) {
            try verifier.verify(b.pins, leg, makers, potentials, address(this))
                returns (LoopVerifier.Rat[] memory qtys) {
                fault = _capFault(beat, leg, qtys);
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
        Fill[] storage fills = _pending[beat];
        // check every fill before recording any: recorded + this beat's fills
        // of the same offer so far must stay within the cap, exactly
        for (uint256 i = 0; i < fills.length; i++) {
            LoopVerifier.Rat memory total = _filledOf(fills[i].offer);
            if (successor != address(0)) {
                (uint256 sn, uint256 sd) = IRecorded(successor).recorded(fills[i].offer);
                if (sd != 0) total = _plus(total, sn, sd);
            }
            for (uint256 j = 0; j <= i; j++) {
                if (fills[j].offer == fills[i].offer) total = _plus(total, fills[j].n, fills[j].d);
            }
            if (total.n * fills[i].capD > fills[i].capN * total.d) {
                _cancel(beat, "a fill exceeds what is left of its offer");
                payable(b.submitter).transfer(b.bond);
                return;
            }
        }
        for (uint256 i = 0; i < fills.length; i++) {
            _recorded[fills[i].offer] = _plus(_ownOf(fills[i].offer), fills[i].n, fills[i].d);
        }
        b.finalized = true;
        emit Finalized(beat, b.pins.bookRoot, fills.length);
        payable(b.submitter).transfer(b.bond);
    }

    // ---- the verifier, callable so a failure can be caught ------------------

    /// One leg's structural verification against this contract's fills — what
    /// a challenge runs, callable (as `eth_call`) so a submitter or challenger
    /// asks for free first. Returns each give's quantity.
    function verifyLegExternal(LoopVerifier.Beat calldata pins, LoopVerifier.Leg calldata leg,
                               bytes[] calldata makers, LoopVerifier.Rat[] calldata potentials)
        external returns (LoopVerifier.Rat[] memory)
    {
        return verifier.verify(pins, leg, makers, potentials, address(this));
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
