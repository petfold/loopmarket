// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./LoopVerifier.sol";

/// What a clearing contract has recorded as taken from an offer.
interface IFills {
    function filled(bytes32 offer) external view returns (uint256 n, uint256 d);
}

/// `LoopVerifier` deployed once, beside the clearing contracts that use it
/// (2026-09-23). The library is almost all of `BeatClearing`'s code, and the
/// clearing contract had reached EIP-170's size limit; split out, one leg's
/// verification is an external call, and the clearing contract has room for
/// its own bookkeeping (its predecessors' fills, retirement).
///
/// `verify` runs the structural half of one leg against the fills `fills`
/// answers and the potentials given, and returns each give's quantity (the
/// caps the clearing contract checks its committed fills against). It holds
/// no state between calls: the scratch below lives for one verification and
/// anyone may call it — the answer is a computation, not a record.
contract LegVerifier {
    bytes[] private _makers;                       // scratch for one verification
    LoopVerifier.Rat[] private _potentials;
    address private _fills;

    function verify(LoopVerifier.Beat calldata pins, LoopVerifier.Leg calldata leg,
                    bytes[] calldata makers, LoopVerifier.Rat[] calldata potentials, address fills)
        external returns (LoopVerifier.Rat[] memory qtys)
    {
        _makers = makers;
        _potentials = potentials;
        _fills = fills;
        (, LoopVerifier.Facts[] memory gives) = LoopVerifier.verifyLeg(pins, leg, _filledOf, _potentialOf);
        qtys = new LoopVerifier.Rat[](gives.length);
        for (uint256 i = 0; i < gives.length; i++) qtys[i] = gives[i].qty;
    }

    function _potentialOf(bytes memory maker) internal view returns (LoopVerifier.Rat memory) {
        for (uint256 i = 0; i < _makers.length; i++) {
            if (keccak256(_makers[i]) == keccak256(maker)) return _potentials[i];
        }
        revert("maker without a potential");
    }

    function _filledOf(bytes32 offer) internal view returns (LoopVerifier.Rat memory r) {
        (uint256 n, uint256 d) = IFills(_fills).filled(offer);
        r = d == 0 ? LoopVerifier.Rat(0, 1) : LoopVerifier.Rat(n, d);
    }
}
