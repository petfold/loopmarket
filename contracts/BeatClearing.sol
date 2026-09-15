// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./LoopVerifier.sol";

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
contract BeatClearing {
    using LoopVerifier for LoopVerifier.Beat;

    struct Fill { bytes32 offer; uint256 n; uint256 d; }

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

    uint256 public beatCount;
    mapping(uint256 => BeatRecord) public beats;
    mapping(uint256 => Fill[]) private _pending;                 // fills a beat would record
    mapping(bytes32 => LoopVerifier.Rat) private _filled;        // recorded fills, exact

    event Submitted(uint256 indexed beat, bytes32 bookRoot, bytes32 legsHash, address submitter);
    event Challenged(uint256 indexed beat, uint256 leg, address challenger, string reason);
    event Cancelled(uint256 indexed beat, string reason);
    event Finalized(uint256 indexed beat, bytes32 bookRoot, uint256 fills);

    constructor(uint256 bondWei_, uint256 windowBlocks_, address arbiter_) {
        bondWei = bondWei_;
        windowBlocks = windowBlocks_;
        arbiter = arbiter_;
    }

    // ---- reading -------------------------------------------------------------

    /// What has been recorded as taken from an offer, exact (0/1: nothing).
    function filled(bytes32 offer) public view returns (uint256 n, uint256 d) {
        LoopVerifier.Rat memory r = _filledOf(offer);
        return (r.n, r.d);
    }

    function pendingFills(uint256 beat) external view returns (Fill[] memory) {
        return _pending[beat];
    }

    // ---- the beat ------------------------------------------------------------

    /// Post one beat's outcome. `legHashes[i]` is keccak256(abi.encode(leg_i))
    /// over the `LoopVerifier.Leg` the submitter would supply to a challenge;
    /// `fills` the quantities every give and want in those legs take (a
    /// want's fill is its whole quantity as 1/1); `makers`/`potentials` the
    /// node potentials. The full data is expected beside the chain (the
    /// clearing book on Swarm); the chain holds the commitments.
    function submit(LoopVerifier.Beat calldata pins, bytes32[] calldata legHashes,
                    Fill[] calldata fills, bytes[] calldata makers,
                    LoopVerifier.Rat[] calldata potentials)
        external payable returns (uint256 beat)
    {
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
            // a fill must fit what is already recorded: checked exactly at finalize too
            _pending[beat].push(fills[i]);
        }
        b.fillCount = fills.length;
        emit Submitted(beat, pins.bookRoot, b.legsHash, msg.sender);
    }

    /// Re-verify leg `index` of a beat on chain. Reverts if the supplied data
    /// is not what was committed; cancels the beat and pays the bond to the
    /// challenger if the leg fails `LoopVerifier`; does nothing (the
    /// challenger paid gas for nothing) if the leg verifies.
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
        // the fills the beat committed for this leg's gives must be the quantities taken
        for (uint256 i = 0; i < leg.gives.length; i++) {
            require(_pendingTakes(beat, leg.gives[i].id, leg.taken[i]), "fill differs from leg");
        }
        try this.verifyLegExternal(b.pins, leg, makers, potentials) {
            emit Challenged(beat, index, msg.sender, "leg verifies");
        } catch Error(string memory reason) {
            _cancel(beat, reason);
            emit Challenged(beat, index, msg.sender, reason);
            payable(msg.sender).transfer(b.bond);
        } catch Panic(uint256 code) {
            // arithmetic overflow, an index out of range: a malformed leg
            _cancel(beat, "leg fails: panic");
            emit Challenged(beat, index, msg.sender, "leg fails: panic");
            payable(msg.sender).transfer(b.bond);
            code;
        } catch {
            // out of gas or an unknown error: NOT a conviction — the
            // challenger must bring enough gas for the verification
            revert("verification did not complete: bring more gas");
        }
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

    /// After the window: record the fills exactly, return the bond.
    function finalize(uint256 beat) external {
        BeatRecord storage b = beats[beat];
        require(b.submittedAt != 0 && !b.finalized && !b.cancelled, "no open beat");
        require(block.number > b.submittedAt + windowBlocks, "window open");
        Fill[] storage fills = _pending[beat];
        for (uint256 i = 0; i < fills.length; i++) {
            LoopVerifier.Rat memory before = _filledOf(fills[i].offer);
            // before + fill, exact
            uint256 n = before.n * fills[i].d + fills[i].n * before.d;
            uint256 d = before.d * fills[i].d;
            uint256 g = _gcd(n, d);
            _filled[fills[i].offer] = LoopVerifier.Rat(n / g, d / g);
        }
        b.finalized = true;
        emit Finalized(beat, b.pins.bookRoot, fills.length);
        payable(b.submitter).transfer(b.bond);
    }

    // ---- the verifier, callable so a failure can be caught ------------------

    function verifyLegExternal(LoopVerifier.Beat calldata pins, LoopVerifier.Leg calldata leg,
                               bytes[] calldata makers, LoopVerifier.Rat[] calldata potentials)
        external
    {
        require(msg.sender == address(this), "internal");
        _makers = makers;
        _potentials = potentials;
        LoopVerifier.verifyLeg(pins, leg, _filledOf, _potentialOf);
    }

    bytes[] private _makers;                       // scratch for the lookup during one verification
    LoopVerifier.Rat[] private _potentials;

    function _potentialOf(bytes memory maker) internal view returns (LoopVerifier.Rat memory) {
        for (uint256 i = 0; i < _makers.length; i++) {
            if (keccak256(_makers[i]) == keccak256(maker)) return _potentials[i];
        }
        revert("maker without a potential");
    }

    function _filledOf(bytes32 offer) internal view returns (LoopVerifier.Rat memory r) {
        r = _filled[offer];
        if (r.d == 0) r = LoopVerifier.Rat(0, 1);
    }

    function _pendingTakes(uint256 beat, bytes32 offer, LoopVerifier.Rat calldata taken)
        private view returns (bool)
    {
        Fill[] storage fills = _pending[beat];
        for (uint256 i = 0; i < fills.length; i++) {
            if (fills[i].offer == offer) return fills[i].n * taken.d == taken.n * fills[i].d;
        }
        return false;
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
