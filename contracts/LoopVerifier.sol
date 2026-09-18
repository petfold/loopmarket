// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./TrieProofVerifier.sol";

/// The structural half of clearing, verified on chain (P2, decided with
/// Peter 2026-09-15; docs/plans/proof-fabric.md, P2-loop-selection.md §11).
/// Given a beat — the anchored book root and the catalogue pins — and one
/// leg of a proposed loop with every offer's canonical record bytes and
/// trie proof, this library checks what a contract can check:
///   * each offer's bytes hash to its id (U2) and sit under the book root
///     (a sha256 root, or a Swarm reference for a book on Swarm — the
///     beat says which, `Beat.addressing`, since 2026-09-18);
///   * each offer is a v4 record whose pins equal the beat's (U10);
///   * the want is a want, every give a give, makers as the leg claims,
///     no maker on both sides of one leg;
///   * the quantity taken from each give is within its quantity, on its
///     step, at or above its floor, and within what is still unfilled
///     (partial fills are exact: no rounding, ever — U9);
///   * the potentials balance the leg: the lot the buyer pays, times the
///     buyer's potential, covers the sum over gives of unit price times
///     quantity taken times the giver's potential — by cross-multiplication
///     of exact rationals, no division anywhere.
/// What it cannot check is whether each give's thing fits within the want
/// (`Ontology.satisfies` over the pinned catalogue): that half stays
/// optimistic — any reader re-derives it off chain and challenges.
/// Fields are read from the record bytes by pattern, never by parsing JSON:
/// the record is canonical (sorted keys, no whitespace), so `"gives":{`
/// precedes `"maker":"` precedes `"wants":{`, and inside a side the keys
/// `"amount"`, `"min"`, `"qty"`, `"step"`, `"type"` each occur once.
library LoopVerifier {
    struct Rat { uint256 n; uint256 d; }

    struct Beat {
        bytes32 bookRoot;
        bytes32 ontologyRoot;      // as the offers pin it (32 bytes of the hex root)
        bytes registryVersion;     // e.g. "4.2"
        bytes contractVersion;     // e.g. "0.1"
        uint8 addressing;          // the book root's scheme: 0 sha256, 1 Swarm (BMT) — 2026-09-18
    }

    struct OfferProof {
        bytes32 id;                // sha256 of the canonical record
        bytes record;              // the trie's value blob: {"rsv":1,"val":<canonical v4 record>}
        bytes[] nodes;             // the trie path for "offer/<id>" under bookRoot
    }

    struct Leg {
        OfferProof want;
        OfferProof[] gives;
        Rat[] taken;               // quantity taken from each give
    }

    struct Facts {
        bytes maker;
        bool isGive;               // the thing side is `gives`
        Rat qty;                   // the thing's quantity (a want: what is wanted)
        Rat step;
        Rat min;
        Rat amount;                // the tokens side
    }

    /// Verify one leg. `filled(id)` answers what the contract has already
    /// recorded as taken from an offer (0/1 for nothing); `potential(maker)`
    /// the proposed potential of a maker (revert if unknown). Returns the
    /// facts of the want and the gives, for the caller to record fills from.
    function verifyLeg(
        Beat memory beat,
        Leg memory leg,
        function(bytes32) view returns (Rat memory) filled,
        function(bytes memory) view returns (Rat memory) potential
    ) internal view returns (Facts memory want, Facts[] memory gives) {
        require(leg.gives.length >= 1 && leg.gives.length == leg.taken.length, "leg shape");
        want = _verifyOffer(beat, leg.want);
        require(!want.isGive, "the head of a leg is a want");
        gives = new Facts[](leg.gives.length);
        // the buyer's side of the balance: amount * e[head]
        Rat memory eHead = potential(want.maker);
        Rat memory lhs = _mul(want.amount, eHead);
        Rat memory rhs = Rat(0, 1);
        for (uint256 i = 0; i < leg.gives.length; i++) {
            Facts memory g = _verifyOffer(beat, leg.gives[i]);
            require(g.isGive, "a tail of a leg is a give");
            require(!_bytesEq(g.maker, want.maker), "a maker on both sides of a leg");
            Rat memory t = leg.taken[i];
            require(t.n > 0 && t.d > 0, "taken must be positive");
            _requireTakes(g, t, filled(leg.gives[i].id));
            // value owed to the giver: (amount / qty) * taken * e[giver]
            Rat memory unitPrice = _div(g.amount, g.qty);
            rhs = _add(rhs, _mul(_mul(unitPrice, t), potential(g.maker)));
            gives[i] = g;
        }
        require(_geq(lhs, rhs), "potentials do not balance the leg");
    }

    // ---- one offer -------------------------------------------------------

    /// recordstore stores every value inside a fixed envelope,
    /// `{"rsv":1,"val":<record>}` — the trie hashes the envelope, the offer
    /// id hashes the record. The envelope's bytes are checked exactly and
    /// the record sliced out of it; nothing is re-serialized.
    function _verifyOffer(Beat memory beat, OfferProof memory p) private pure returns (Facts memory f) {
        bytes memory blob = p.record;
        bytes memory head = bytes('{"rsv":1,"val":');
        require(blob.length > head.length + 1 && blob[blob.length - 1] == '}', "value envelope");
        for (uint256 i = 0; i < head.length; i++) require(blob[i] == head[i], "value envelope");
        bytes memory r = new bytes(blob.length - head.length - 1);
        for (uint256 i = 0; i < r.length; i++) r[i] = blob[head.length + i];
        require(sha256(r) == p.id, "record does not hash to its id");
        bytes memory key = abi.encodePacked("offer/", _hex(p.id));
        require(TrieProofVerifier.verifyInclusion(beat.bookRoot, key, p.nodes, blob, beat.addressing),
                "offer not under the book root");
        // version and pins
        require(_hasExact(r, bytes('"v":4')), "not a v4 record");
        require(_hasExact(r, abi.encodePacked('"ontology_root":"', _hex(beat.ontologyRoot), '"')),
                "ontology pin");
        require(_hasExact(r, abi.encodePacked('"registry_version":"', beat.registryVersion, '"')),
                "registry pin");
        require(_hasExact(r, abi.encodePacked('"contract_version":"', beat.contractVersion, '"')),
                "contract pin");
        // the two sides: gives before maker before wants (sorted keys)
        uint256 g = _index(r, '"gives":{', 0);
        uint256 m = _index(r, '"maker":"', g);
        uint256 w = _index(r, '"wants":{', m);
        require(g < m && m < w, "record shape");
        f.maker = _stringAt(r, m + 9);
        bool givesIsThing = _index(r, '"type":"thing"', g) < w && _index(r, '"type":"thing"', g) > g;
        // exactly one side is a thing (U1); a composed want is not verifiable here yet
        require(_index(r, '"type":"parts"', 0) == type(uint256).max, "parts: not yet on chain");
        uint256 thingStart = givesIsThing ? g : w;
        uint256 thingEnd = givesIsThing ? w : r.length;
        uint256 tokensStart = givesIsThing ? w : g;
        uint256 tokensEnd = givesIsThing ? r.length : m;
        f.isGive = givesIsThing;
        f.qty = _ratField(r, '"qty":"', thingStart, thingEnd);
        f.step = _ratField(r, '"step":"', thingStart, thingEnd);
        f.min = _ratField(r, '"min":"', thingStart, thingEnd);
        f.amount = _ratField(r, '"amount":"', tokensStart, tokensEnd);
    }

    /// `Thing.takes(taken, available)`: within what is left, at or above
    /// the floor, a positive multiple of the step (any amount when 0).
    function _requireTakes(Facts memory g, Rat memory t, Rat memory alreadyFilled) private pure {
        Rat memory left = _sub(g.qty, alreadyFilled);
        require(_geq(left, t), "more than is left of the give");
        if (g.min.n > 0) require(_geq(t, g.min), "below the give's floor");
        if (g.step.n > 0) {
            // t / step must be an integer: (t.n * step.d) % (t.d * step.n) == 0
            require((t.n * g.step.d) % (t.d * g.step.n) == 0, "not on the give's step");
        }
    }

    // ---- exact rationals (no division, ever) ---------------------------------

    function _mul(Rat memory a, Rat memory b) private pure returns (Rat memory) {
        return _reduce(Rat(a.n * b.n, a.d * b.d));
    }

    function _div(Rat memory a, Rat memory b) private pure returns (Rat memory) {
        require(b.n > 0, "division by zero");
        return _reduce(Rat(a.n * b.d, a.d * b.n));
    }

    function _add(Rat memory a, Rat memory b) private pure returns (Rat memory) {
        return _reduce(Rat(a.n * b.d + b.n * a.d, a.d * b.d));
    }

    function _sub(Rat memory a, Rat memory b) private pure returns (Rat memory) {
        uint256 x = a.n * b.d; uint256 y = b.n * a.d;
        require(x >= y, "negative");
        return _reduce(Rat(x - y, a.d * b.d));
    }

    function _geq(Rat memory a, Rat memory b) private pure returns (bool) {
        return a.n * b.d >= b.n * a.d;
    }

    function _reduce(Rat memory r) private pure returns (Rat memory) {
        require(r.d > 0, "zero denominator");
        uint256 g = _gcd(r.n, r.d);
        return Rat(r.n / g, r.d / g);
    }

    function _gcd(uint256 a, uint256 b) private pure returns (uint256) {
        if (a == 0) return b;
        while (b != 0) { (a, b) = (b, a % b); }
        return a;
    }

    // ---- reading the canonical record --------------------------------------

    /// A rational field `"key":"n/d"` (or `"n"`) between `from` and `to`.
    function _ratField(bytes memory r, string memory key, uint256 from, uint256 to)
        private pure returns (Rat memory out)
    {
        uint256 at = _index(r, key, from);
        require(at != type(uint256).max && at < to, string(abi.encodePacked("missing ", key)));
        uint256 i = at + bytes(key).length;
        uint256 n = 0; uint256 d = 0; bool inDen = false;
        while (i < r.length && r[i] != '"') {
            bytes1 c = r[i];
            if (c == '/') { require(!inDen, "rational shape"); inDen = true; }
            else {
                require(c >= '0' && c <= '9', "not a number");
                if (inDen) d = d * 10 + (uint8(c) - 48); else n = n * 10 + (uint8(c) - 48);
            }
            i++;
        }
        if (!inDen) d = 1;
        require(d > 0, "zero denominator");
        out = Rat(n, d);
    }

    function _stringAt(bytes memory r, uint256 from) private pure returns (bytes memory) {
        uint256 len = 0;
        while (from + len < r.length && r[from + len] != '"') len++;
        bytes memory out = new bytes(len);
        for (uint256 i = 0; i < len; i++) out[i] = r[from + i];
        return out;
    }

    function _index(bytes memory hay, string memory needle, uint256 from) private pure returns (uint256) {
        return _indexBytes(hay, bytes(needle), from);
    }

    function _hasExact(bytes memory hay, bytes memory needle) private pure returns (bool) {
        return _indexBytes(hay, needle, 0) != type(uint256).max;
    }

    function _indexBytes(bytes memory hay, bytes memory needle, uint256 from) private pure returns (uint256) {
        if (hay.length < needle.length) return type(uint256).max;
        for (uint256 i = from; i + needle.length <= hay.length; i++) {
            bool ok = true;
            for (uint256 j = 0; j < needle.length; j++) {
                if (hay[i + j] != needle[j]) { ok = false; break; }
            }
            if (ok) return i;
        }
        return type(uint256).max;
    }

    function _bytesEq(bytes memory a, bytes memory b) private pure returns (bool) {
        return a.length == b.length && keccak256(a) == keccak256(b);
    }

    function _hex(bytes32 v) private pure returns (bytes memory out) {
        out = new bytes(64);
        bytes memory alphabet = "0123456789abcdef";
        for (uint256 i = 0; i < 32; i++) {
            out[2 * i] = alphabet[uint8(v[i]) >> 4];
            out[2 * i + 1] = alphabet[uint8(v[i]) & 0x0f];
        }
    }
}

/// A test face: potentials and recorded fills supplied as arrays.
contract LoopVerifierFace {
    mapping(bytes32 => LoopVerifier.Rat) private _filled;
    mapping(bytes32 => LoopVerifier.Rat) private _potential;   // keccak(maker) -> e
    mapping(bytes32 => bool) private _known;

    function setFilled(bytes32 id, uint256 n, uint256 d) external { _filled[id] = LoopVerifier.Rat(n, d); }

    function setPotentials(bytes[] calldata makers, uint256[] calldata n, uint256[] calldata d) external {
        for (uint256 i = 0; i < makers.length; i++) {
            _potential[keccak256(makers[i])] = LoopVerifier.Rat(n[i], d[i]);
            _known[keccak256(makers[i])] = true;
        }
    }

    function _filledOf(bytes32 id) internal view returns (LoopVerifier.Rat memory r) {
        r = _filled[id];
        if (r.d == 0) r = LoopVerifier.Rat(0, 1);
    }

    function _potentialOf(bytes memory maker) internal view returns (LoopVerifier.Rat memory) {
        require(_known[keccak256(maker)], "unknown maker in potentials");
        return _potential[keccak256(maker)];
    }

    function verifyLeg(LoopVerifier.Beat memory beat, LoopVerifier.Leg memory leg)
        external view returns (bytes memory wantMaker, bytes[] memory giveMakers)
    {
        (LoopVerifier.Facts memory w, LoopVerifier.Facts[] memory gs) =
            LoopVerifier.verifyLeg(beat, leg, _filledOf, _potentialOf);
        wantMaker = w.maker;
        giveMakers = new bytes[](gs.length);
        for (uint256 i = 0; i < gs.length; i++) giveMakers[i] = gs[i].maker;
    }
}
