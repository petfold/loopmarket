// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./SwarmAddress.sol";

/// On-chain verification of recordstore's trie proofs
/// (`format: "recordstore-trie-proof", version: 1`; sha256 addressing, or
/// since 2026-09-18 Swarm's BMT addressing for a book whose roots are Swarm
/// references — `SwarmAddress.sol`, chosen by the `addressing` argument the
/// proof envelope names: 0 sha256, 1 swarm) —
/// the P2 clearing contract's evidence layer (docs/plans/proof-fabric.md
/// §1, §5). A proof is the raw node blobs along a key's one possible path
/// in the canonical radix trie; each node is canonical JSON,
///   {"c":{"35":"<ref>",...},"p":"<hex prefix>","tn":1,"v":<ref>|null}
/// with keys as UTF-8 bytes and children indexed by the next byte's two
/// hex digits. The walk needs no JSON parser: the child for byte XX is the
/// 64 hex characters after the pattern `"XX":"`, which can occur nowhere
/// else in a node (the other keys are "p", "tn", "v"; values are hex).
/// Verification is the hash chain over the exact bytes — sha256 per node
/// (the EVM precompile) or Swarm's chunk address, never a re-serialization — mirroring
/// recordstore's `verify_proof` step for step. Absence is provable because
/// the encoding is canonical: the walk ends where the key would live.
library TrieProofVerifier {
    uint8 internal constant SHA256 = 0;
    uint8 internal constant SWARM = 1;

    /// The reference of `blob` under an addressing scheme: sha256 of the
    /// bytes, or Swarm's chunk-tree address of them.
    function refOf(bytes memory blob, uint8 addressing) internal pure returns (bytes32) {
        if (addressing == SHA256) return sha256(blob);
        if (addressing == SWARM) return SwarmAddress.addressOf(blob);
        revert("unknown addressing");
    }

    /// Walk `nodes` from `root` along `key`. Returns whether the key is
    /// present and, if so, the reference of its value blob under the same
    /// addressing. Reverts on any node that does not hash to where the walk
    /// expects it, on a malformed node, or on a walk that ends before it
    /// concludes.
    function verifyPath(bytes32 root, bytes memory key, bytes[] memory nodes, uint8 addressing)
        internal pure returns (bool present, bytes32 valueRef)
    {
        bytes32 expected = root;
        uint256 pos = 0;                       // how much of `key` is consumed
        bool concluded = false;
        for (uint256 i = 0; i < nodes.length; i++) {
            require(!concluded, "node past conclusion");
            bytes memory node = nodes[i];
            require(refOf(node, addressing) == expected, "node hash mismatch");
            // the prefix
            (uint256 pStart, uint256 pLen) = _find(node, '"p":"', 0);
            require(pStart != type(uint256).max, "no prefix");
            uint256 hexLen = _spanUntilQuote(node, pStart + pLen);
            require(hexLen % 2 == 0, "odd prefix");
            uint256 prefixLen = hexLen / 2;
            if (!_prefixMatches(node, pStart + pLen, prefixLen, key, pos)) {
                present = false; concluded = true; continue;   // diverges inside the prefix
            }
            pos += prefixLen;
            if (pos == key.length) {
                (uint256 vStart, uint256 vLen) = _find(node, '"v":', 0);
                require(vStart != type(uint256).max, "no value field");
                uint256 at = vStart + vLen;
                if (node[at] == '"') {
                    valueRef = _readHex32(node, at + 1);
                    present = true;
                } else {
                    present = false;           // "v":null
                }
                concluded = true;
                continue;
            }
            // descend by the next key byte
            bytes memory pattern = new bytes(6);
            pattern[0] = '"';
            pattern[1] = _hexChar(uint8(key[pos]) >> 4);
            pattern[2] = _hexChar(uint8(key[pos]) & 0x0f);
            pattern[3] = '"'; pattern[4] = ':'; pattern[5] = '"';
            (uint256 cStart, uint256 cLen) = _find(node, string(pattern), 0);
            if (cStart == type(uint256).max) {
                present = false; concluded = true; continue;   // nowhere to descend
            }
            expected = _readHex32(node, cStart + cLen);
            pos += 1;
        }
        require(concluded, "proof ends before the walk");
    }

    /// Inclusion: the key is present and `value` hashes to its reference.
    function verifyInclusion(bytes32 root, bytes memory key, bytes[] memory nodes, bytes memory value,
                             uint8 addressing)
        internal pure returns (bool)
    {
        (bool present, bytes32 ref) = verifyPath(root, key, nodes, addressing);
        return present && refOf(value, addressing) == ref;
    }

    /// Absence: the walk concludes without the key.
    function verifyAbsence(bytes32 root, bytes memory key, bytes[] memory nodes, uint8 addressing)
        internal pure returns (bool)
    {
        (bool present, ) = verifyPath(root, key, nodes, addressing);
        return !present;
    }

    // ---- byte helpers ----------------------------------------------------

    function _find(bytes memory hay, string memory needleStr, uint256 from)
        private pure returns (uint256 start, uint256 len)
    {
        bytes memory needle = bytes(needleStr);
        len = needle.length;
        if (hay.length < len) return (type(uint256).max, len);
        for (uint256 i = from; i + len <= hay.length; i++) {
            bool ok = true;
            for (uint256 j = 0; j < len; j++) {
                if (hay[i + j] != needle[j]) { ok = false; break; }
            }
            if (ok) return (i, len);
        }
        return (type(uint256).max, len);
    }

    function _spanUntilQuote(bytes memory s, uint256 from) private pure returns (uint256 n) {
        while (from + n < s.length && s[from + n] != '"') n++;
        require(from + n < s.length, "unterminated string");
    }

    function _prefixMatches(bytes memory node, uint256 hexAt, uint256 prefixLen,
                            bytes memory key, uint256 pos) private pure returns (bool) {
        if (pos + prefixLen > key.length) return false;
        for (uint256 i = 0; i < prefixLen; i++) {
            uint8 b = _hexVal(node[hexAt + 2 * i]) * 16 + _hexVal(node[hexAt + 2 * i + 1]);
            if (bytes1(b) != key[pos + i]) return false;
        }
        return true;
    }

    function _readHex32(bytes memory s, uint256 from) private pure returns (bytes32 out) {
        require(from + 64 <= s.length, "short reference");
        uint256 acc = 0;
        for (uint256 i = 0; i < 64; i++) {
            acc = (acc << 4) | _hexVal(s[from + i]);
        }
        return bytes32(acc);
    }

    function _hexVal(bytes1 c) private pure returns (uint8) {
        uint8 u = uint8(c);
        if (u >= 48 && u <= 57) return u - 48;          // 0-9
        if (u >= 97 && u <= 102) return u - 87;         // a-f
        if (u >= 65 && u <= 70) return u - 55;          // A-F
        revert("not hex");
    }

    function _hexChar(uint8 v) private pure returns (bytes1) {
        return v < 10 ? bytes1(v + 48) : bytes1(v + 87);
    }
}

/// A thin external face over the library, for tests and for callers that
/// verify off-contract; the clearing contract inlines the library.
contract TrieProofVerifierFace {
    function verifyPath(bytes32 root, bytes memory key, bytes[] memory nodes, uint8 addressing)
        external pure returns (bool, bytes32)
    { return TrieProofVerifier.verifyPath(root, key, nodes, addressing); }

    function verifyInclusion(bytes32 root, bytes memory key, bytes[] memory nodes, bytes memory value,
                             uint8 addressing)
        external pure returns (bool)
    { return TrieProofVerifier.verifyInclusion(root, key, nodes, value, addressing); }

    function verifyAbsence(bytes32 root, bytes memory key, bytes[] memory nodes, uint8 addressing)
        external pure returns (bool)
    { return TrieProofVerifier.verifyAbsence(root, key, nodes, addressing); }

    function swarmReference(bytes memory data) external pure returns (bytes32)
    { return SwarmAddress.addressOf(data); }
}
