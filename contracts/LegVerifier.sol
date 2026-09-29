// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./LoopVerifier.sol";

/// What a clearing contract has recorded as taken from an offer.
interface IFills {
    function filled(bytes32 offer) external view returns (uint256 n, uint256 d);
}

/// What active holds keep of an offer from `taker` at `at` (C4, 2026-09-29):
/// every active hold but the taker's own exercisable ones.
interface IHolds {
    function heldAgainst(bytes32 offer, bytes32 taker, uint256 at) external view returns (uint256 n, uint256 d);
}

/// `LoopVerifier` deployed once, beside the clearing contracts that use it
/// (2026-09-23). The library is almost all of `BeatClearing`'s code, and the
/// clearing contract had reached EIP-170's size limit; split out, one leg's
/// verification is an external call, and the clearing contract has room for
/// its own bookkeeping (its predecessors' fills, retirement).
///
/// `verify` runs the structural half of one leg against the fills and holds
/// `fills` answers at the beat's time `at` and the potentials given, checks
/// the beat's committed holds and item claims for leg `index` (2026-09-29:
/// C4, I3), and returns each give's quantity (the caps the clearing
/// contract checks its committed fills against), the taker (keccak of the
/// want's maker, which each give's committed fill names) and the parties a
/// leg's statements are checked against (R3b, `StatementVerifier`). It holds no state between calls: the scratch below lives for one
/// verification and anyone may call it — the answer is a computation, not a
/// record.
contract LegVerifier {
    bytes[] private _makers;                       // scratch for one verification
    LoopVerifier.Rat[] private _potentials;
    address private _fills;
    uint256 private _at;

    function verify(LoopVerifier.Beat calldata pins, LoopVerifier.Leg calldata leg, bytes[] calldata makers,
                    LoopVerifier.Rat[] calldata potentials, LoopVerifier.Hold[] calldata holds,
                    LoopVerifier.ItemClaim[] calldata claims, uint256 index, uint256 at, address fills)
        external returns (LoopVerifier.Rat[] memory qtys, bytes32 taker, LoopVerifier.Parties memory parties)
    {
        _makers = makers;
        _potentials = potentials;
        _fills = fills;
        _at = at;
        LoopVerifier.Verified memory v = LoopVerifier.verifyLeg(pins, leg, _filledOf, _potentialOf);
        LoopVerifier.checkHolds(v, leg, holds, index);
        LoopVerifier.checkClaims(v, leg, claims, index, at);
        parties = LoopVerifier.parties(v);
        qtys = new LoopVerifier.Rat[](v.gives.length);
        for (uint256 i = 0; i < v.gives.length; i++) qtys[i] = v.gives[i].qty;
        taker = v.taker;
    }

    function _potentialOf(bytes memory maker) internal view returns (LoopVerifier.Rat memory) {
        for (uint256 i = 0; i < _makers.length; i++) {
            if (keccak256(_makers[i]) == keccak256(maker)) return _potentials[i];
        }
        revert("maker without a potential");
    }

    /// Recorded fills plus what active holds keep from `taker`.
    function _filledOf(bytes32 offer, bytes32 taker) internal view returns (LoopVerifier.Rat memory r) {
        (uint256 n, uint256 d) = IFills(_fills).filled(offer);
        if (d == 0) { n = 0; d = 1; }
        (uint256 hn, uint256 hd) = IHolds(_fills).heldAgainst(offer, taker, _at);
        if (hd != 0 && hn != 0) { n = n * hd + hn * d; d = d * hd; }
        r = LoopVerifier.Rat(n, d);
    }
}

/// A leg's statements checked against the beat's pins and registers and the
/// parties `LegVerifier` found (R3b, 2026-09-29) — split out when the leg
/// verifier passed EIP-170's size. Pure: anyone may call it.
contract StatementVerifier {
    function verify(LoopVerifier.Beat calldata pins, LoopVerifier.RegisterPin[] calldata registers,
                    LoopVerifier.StatementProof[] calldata statements, LoopVerifier.Parties calldata parties)
        external pure
    {
        LoopVerifier.checkStatements(pins, registers, statements, parties);
    }
}
