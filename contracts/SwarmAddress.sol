// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Swarm's content address of a blob, computed on the EVM — the reference
/// Bee returns for a plain upload (erasure coding off), so a book kept in
/// a Swarm-addressed store (recordstore `addressing: "swarm"`, whose roots
/// are Swarm references) proves under the same root here (P2, 2026-09-18:
/// the live gate posted an honest beat from a Swarm clearing book and the
/// sha256 verifier convicted it — "node hash mismatch"). Mirrors swarmfs's
/// `splitter.py`/`bmt.py`, which mirror bee's `pkg/file/splitter`:
///   * a chunk is span (8 bytes, little-endian) + payload of at most 4096
///     bytes; its address is keccak256(span || BMT root), the BMT root the
///     binary Merkle tree over the payload's 32-byte segments zero-padded
///     to 4096 bytes (128 leaves, 7 levels);
///   * data over 4096 bytes is a tree: leaves of 4096, intermediates of up
///     to 128 child references whose span is the content length beneath,
///     a level of one entry promoted rather than wrapped;
///   * empty data is one chunk of span 0.
/// Segments beyond the payload are zero, so their subtrees are a constant
/// per level: only the segments with content are hashed pairwise and the
/// rest take the constant, which keeps a 400-byte record at ~15 keccaks
/// instead of 127.
library SwarmAddress {
    uint256 private constant CHUNK = 4096;
    uint256 private constant SEGMENT = 32;
    uint256 private constant BRANCHES = CHUNK / SEGMENT;   // 128

    /// The Swarm reference of `data`, any length.
    function addressOf(bytes memory data) internal pure returns (bytes32) {
        if (data.length <= CHUNK) {
            return chunkAddress(data.length, data, 0, data.length);
        }
        uint256 n = (data.length + CHUNK - 1) / CHUNK;
        bytes32[] memory refs = new bytes32[](n);
        uint256[] memory spans = new uint256[](n);
        for (uint256 i = 0; i < n; i++) {
            uint256 start = i * CHUNK;
            uint256 len = data.length - start < CHUNK ? data.length - start : CHUNK;
            refs[i] = chunkAddress(len, data, start, len);
            spans[i] = len;
        }
        while (n > 1) {
            uint256 parents = (n + BRANCHES - 1) / BRANCHES;
            for (uint256 p = 0; p < parents; p++) {
                uint256 from = p * BRANCHES;
                uint256 count = n - from < BRANCHES ? n - from : BRANCHES;
                if (count == 1) {                          // promoted, never wrapped
                    refs[p] = refs[from]; spans[p] = spans[from];
                    continue;
                }
                bytes memory payload = new bytes(count * SEGMENT);
                uint256 span = 0;
                for (uint256 c = 0; c < count; c++) {
                    bytes32 r = refs[from + c];
                    for (uint256 b = 0; b < SEGMENT; b++) payload[c * SEGMENT + b] = r[b];
                    span += spans[from + c];
                }
                refs[p] = chunkAddress(span, payload, 0, payload.length);
                spans[p] = span;
            }
            n = parents;
        }
        return refs[0];
    }

    /// keccak256(span little-endian || BMT root of data[start:start+len]).
    function chunkAddress(uint256 span, bytes memory data, uint256 start, uint256 len)
        internal pure returns (bytes32)
    {
        require(len <= CHUNK, "chunk payload over 4096");
        return keccak256(abi.encodePacked(_spanLE(span), bmtRoot(data, start, len)));
    }

    /// The binary Merkle tree root over data[start:start+len] as 32-byte
    /// segments zero-padded to 4096 bytes.
    function bmtRoot(bytes memory data, uint256 start, uint256 len) internal pure returns (bytes32) {
        uint256 count = (len + SEGMENT - 1) / SEGMENT;        // segments with content
        bytes32[] memory level = new bytes32[](count);
        for (uint256 i = 0; i < count; i++) {
            bytes32 word;
            uint256 at = start + i * SEGMENT;
            assembly { word := mload(add(add(data, 32), at)) }
            uint256 have = len - i * SEGMENT;
            if (have < SEGMENT) {                             // zero-pad the tail segment
                word = word & bytes32(~((uint256(1) << (8 * (SEGMENT - have))) - 1));
            }
            level[i] = word;
        }
        bytes32 zero = bytes32(0);                            // the all-zero subtree at this level
        for (uint256 depth = 0; depth < 7; depth++) {          // 128 leaves -> 1 root
            uint256 next = (count + 1) / 2;
            for (uint256 j = 0; j < next; j++) {
                bytes32 a = level[2 * j];
                bytes32 b = 2 * j + 1 < count ? level[2 * j + 1] : zero;
                level[j] = keccak256(abi.encodePacked(a, b));
            }
            zero = keccak256(abi.encodePacked(zero, zero));
            count = next;
        }
        return count == 0 ? zero : level[0];
    }

    function _spanLE(uint256 span) private pure returns (bytes8 out) {
        uint256 le = 0;
        for (uint256 i = 0; i < 8; i++) {
            le |= ((span >> (8 * i)) & 0xff) << (8 * (7 - i));
        }
        out = bytes8(uint64(le));
    }
}
