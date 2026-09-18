// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// The sealed-proposal beat in front of `BeatClearing` (P2,
/// docs/plans/P2-batch-auction.md §2–§6; built 2026-09-18). Beats have a
/// fixed cadence from deployment: `period` blocks each, the first
/// `commitBlocks` of which are the commit phase and the rest the reveal
/// phase. A solver commits keccak256(proposal || salt) — one commitment
/// per solver per beat, never replaced, so a commitment is not a free
/// option — and reveals the proposal bytes and salt in the reveal phase;
/// the bytes are emitted, so every replica reads the same revealed set
/// from the chain and the outcome is a deterministic function of (the
/// beat's pinned book root, the revealed set, the baseline's reserve
/// bid). What a proposal is worth, which survive the fairness filter and
/// which win is computed off chain (`loopmarket.auction`) and posted to
/// `BeatClearing` loop by loop; `record` pins the outcome a submitter
/// derived — the hash of the revealed set it saw and of the winners — so
/// a second submitter deriving something else is a visible dispute, not
/// a silent fork. This is the commit-reveal fallback of §3; Shutter
/// threshold encryption (the primary) replaces the commit with an
/// encrypt-to-epoch and the reveal with the epoch's key, behind the same
/// phases. No bond here yet: solver bonds route through factbond (§8).
contract SealedBeat {
    uint256 public immutable genesis;       // block the cadence starts at
    uint256 public immutable period;        // blocks per beat
    uint256 public immutable commitBlocks;  // the commit phase, from a beat's start
    address public immutable clearing;      // the BeatClearing outcomes go to

    struct Outcome { address submitter; bytes32 revealedSet; bytes32 winners; }

    mapping(uint256 => mapping(address => bytes32)) public commitments;   // beat -> solver -> keccak(proposal||salt)
    mapping(uint256 => mapping(address => bytes32)) public revealed;      // beat -> solver -> keccak(proposal)
    mapping(uint256 => address[]) private _committers;
    mapping(uint256 => Outcome) public outcomes;

    event Committed(uint256 indexed beat, address indexed solver, bytes32 commitment);
    event Revealed(uint256 indexed beat, address indexed solver, bytes proposal);
    event Recorded(uint256 indexed beat, address submitter, bytes32 revealedSet, bytes32 winners);
    event Disputed(uint256 indexed beat, address submitter, bytes32 revealedSet, bytes32 winners);

    constructor(uint256 period_, uint256 commitBlocks_, address clearing_) {
        require(period_ > 1 && commitBlocks_ > 0 && commitBlocks_ < period_, "phases");
        genesis = block.number;
        period = period_;
        commitBlocks = commitBlocks_;
        clearing = clearing_;
    }

    // ---- the calendar ----------------------------------------------------------

    /// The beat the current block belongs to (beat 0 starts at `genesis`).
    function current() public view returns (uint256) {
        return (block.number - genesis) / period;
    }

    /// A beat's blocks: [start, commitEnd) commits, [commitEnd, end) reveals.
    function window(uint256 beat) public view returns (uint256 start, uint256 commitEnd, uint256 end) {
        start = genesis + beat * period;
        commitEnd = start + commitBlocks;
        end = start + period;
    }

    /// 0 while committing, 1 while revealing, 2 once closed, 3 not yet begun.
    function phase(uint256 beat) public view returns (uint8) {
        (uint256 start, uint256 commitEnd, uint256 end) = window(beat);
        if (block.number < start) return 3;
        if (block.number < commitEnd) return 0;
        if (block.number < end) return 1;
        return 2;
    }

    function committers(uint256 beat) external view returns (address[] memory) {
        return _committers[beat];
    }

    // ---- commit, reveal, record -------------------------------------------------

    /// Seal a proposal for the current beat: keccak256(abi.encodePacked(proposal, salt)).
    function commit(bytes32 commitment) external {
        uint256 beat = current();
        require(phase(beat) == 0, "not the commit phase");
        require(commitment != bytes32(0), "empty commitment");
        require(commitments[beat][msg.sender] == bytes32(0), "already committed this beat");
        commitments[beat][msg.sender] = commitment;
        _committers[beat].push(msg.sender);
        emit Committed(beat, msg.sender, commitment);
    }

    /// Open the seal: the bytes and salt behind the commitment, once, in
    /// the beat's reveal phase. The bytes are emitted for every reader.
    function reveal(uint256 beat, bytes calldata proposal, bytes32 salt) external {
        require(phase(beat) == 1, "not the reveal phase");
        bytes32 sealed_ = commitments[beat][msg.sender];
        require(sealed_ != bytes32(0), "nothing committed");
        require(revealed[beat][msg.sender] == bytes32(0), "already revealed");
        require(keccak256(abi.encodePacked(proposal, salt)) == sealed_, "not the committed proposal");
        revealed[beat][msg.sender] = keccak256(proposal);
        emit Revealed(beat, msg.sender, proposal);
    }

    /// Pin the outcome derived for a closed beat: the hash of the revealed
    /// set the submitter read and of the winners it posted to `clearing`.
    /// The first record stands; a later one that differs is a dispute.
    function record(uint256 beat, bytes32 revealedSet, bytes32 winners) external {
        require(phase(beat) == 2, "beat not closed");
        Outcome storage o = outcomes[beat];
        if (o.submitter == address(0)) {
            outcomes[beat] = Outcome(msg.sender, revealedSet, winners);
            emit Recorded(beat, msg.sender, revealedSet, winners);
        } else if (o.revealedSet != revealedSet || o.winners != winners) {
            emit Disputed(beat, msg.sender, revealedSet, winners);
        }
    }
}
