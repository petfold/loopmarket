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
///   * each offer is a v4 or v5 record whose pins equal the beat's (U10);
///   * a v5 record's requirement of a counterparty — a bond floor, the
///     witness types it accepts — is met by the other side's declaration
///     (admissibility by declaration, 2026-09-18);
///   * the want is a want, every give a give, makers as the leg claims,
///     no maker on both sides of one leg;
///   * the quantity taken from each give is within its quantity, on its
///     step, at or above its floor, and within what is still unfilled
///     (partial fills are exact: no rounding, ever — U9); the thing's give
///     (or the aggregated gives together) hands over the want's quantity
///     in the want's unit, and for a composed want (v4 `Parts`, since
///     2026-09-18) give i hands over part i's quantity in its unit;
///   * the potentials balance the leg: the lot the buyer pays, times the
///     buyer's potential, covers the sum over gives of unit price times
///     quantity taken times the giver's potential — by cross-multiplication
///     of exact rationals, no division anywhere.
/// What it cannot check is whether each give's thing fits within the want
/// (`Ontology.satisfies` over the pinned catalogue), nor which give among
/// operators is the thing: that half stays optimistic — any reader
/// re-derives it off chain and challenges.
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
        Rat qty;                   // the thing's quantity (a want: what is wanted; 0/1 for parts)
        Rat step;
        Rat min;
        Rat amount;                // the tokens side
        bytes unit;                // the thing's unit (empty for parts)
        Rat[] parts;               // a composed want's part quantities, in the record's order
        bytes[] partUnits;         // and their units
        bytes oracle;              // the witness type the maker settles against
        // v5 (2026-09-19, P3-release-and-reclearing.md §5d): the deposit and the requirement
        bool deposited;            // a `bond` object is present
        bytes depositConcepts;     // the deposit's `"concepts":[...]` array bytes (canonical, sorted)
        bytes depositUnit;
        Rat depositQty;
        bool depositEscrowed;      // a non-empty escrow address
        bool requiring;            // a v5 record with a counterparty requirement
        Rat point;                 // the neutral point, on the requirer's own scale
        bytes accepts;             // the `"accepts":[...]` array bytes
        bytes reqOracles;          // the accepted witness types, as the record's JSON array; "[]" any
        bool reqEscrow;            // `"escrows"` present and non-empty
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
        bool composed = want.parts.length > 0;
        // a composed want (v4 `Parts`, on chain since 2026-09-18): give i serves
        // part i, whole — the quantity taken is the part's, in the part's unit
        if (composed) require(leg.gives.length == want.parts.length, "one give per part");
        gives = new Facts[](leg.gives.length);
        // the buyer's side of the balance: amount * e[head]
        Rat memory eHead = potential(want.maker);
        Rat memory lhs = _mul(want.amount, eHead);
        Rat memory rhs = Rat(0, 1);
        Rat memory total = Rat(0, 1);
        for (uint256 i = 0; i < leg.gives.length; i++) {
            Facts memory g = _verifyOffer(beat, leg.gives[i]);
            require(g.isGive, "a tail of a leg is a give");
            require(!_bytesEq(g.maker, want.maker), "a maker on both sides of a leg");
            Rat memory t = leg.taken[i];
            require(t.n > 0 && t.d > 0, "taken must be positive");
            _requireTakes(g, t, filled(leg.gives[i].id));
            if (composed) {
                require(_eq(t, want.parts[i]), "taken is not the part's quantity");
                require(_bytesEq(g.unit, want.partUnits[i]), "the part's unit");
            }
            // admissibility by declaration (v5, 2026-09-18/19): each side's
            // requirement of a counterparty is met by the other's declaration —
            // the give's deposit reserved per fill, the want taken whole
            _requireMeets(want, g, t, g.qty);
            _requireMeets(g, want, Rat(1, 1), Rat(1, 1));
            total = _add(total, t);
            // value owed to the giver: (amount / qty) * taken * e[giver]
            Rat memory unitPrice = _div(g.amount, g.qty);
            rhs = _add(rhs, _mul(_mul(unitPrice, t), potential(g.maker)));
            gives[i] = g;
        }
        if (!composed) {
            // the want's own quantity is what the thing's give (give 0, or the
            // aggregated gives together) hands over, in the want's unit; which
            // give is the thing among operators is the semantic half's question
            require(_eq(leg.taken[0], want.qty) || _eq(total, want.qty),
                    "taken is not the want's quantity");
            require(_bytesEq(gives[0].unit, want.unit), "the want's unit");
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
        bool v5 = _hasExact(r, bytes('"v":5'));
        require(v5 || _hasExact(r, bytes('"v":4')), "not a v4 or v5 record");
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
        _guarantees(r, f, v5, g);
        bool givesIsThing = _index(r, '"type":"thing"', g) < w && _index(r, '"type":"thing"', g) > g;
        // exactly one side is a thing or the parts of one (U1); parts are want-side only
        bool composed = _index(r, '"type":"parts"', w) != type(uint256).max;
        require(_index(r, '"type":"parts"', 0) >= w, "parts on the give side");
        uint256 thingStart = givesIsThing ? g : w;
        uint256 thingEnd = givesIsThing ? w : r.length;
        uint256 tokensStart = givesIsThing ? w : g;
        uint256 tokensEnd = givesIsThing ? r.length : m;
        f.isGive = givesIsThing;
        f.amount = _ratField(r, '"amount":"', tokensStart, tokensEnd);
        if (composed) {
            require(!givesIsThing, "two things in one offer");
            (f.parts, f.partUnits) = _parts(r, w, r.length);
            f.qty = Rat(0, 1); f.step = Rat(0, 1); f.min = Rat(0, 1);
            return f;
        }
        f.qty = _ratField(r, '"qty":"', thingStart, thingEnd);
        f.step = _ratField(r, '"step":"', thingStart, thingEnd);
        f.min = _ratField(r, '"min":"', thingStart, thingEnd);
        f.unit = _unitField(r, thingStart, thingEnd);
    }

    /// The maker's witness type; on a v5 record its deposit (`"bond":{"asset":
    /// {"concepts":[..],"min":..,"qty":..,"step":..,"unit":".."},"escrow":"..",
    /// "value":".."}` or `"bond":null`) and its requirement (`"requires":{
    /// "accepts":[[[cat..],"unit","price"],..],"escrows":[..]?,"ladder":[..]?,
    /// "oracles":[..],"point":".."}`), read from the sorted-key record bytes.
    function _guarantees(bytes memory r, Facts memory f, bool v5, uint256 givesAt) private pure {
        uint256 oracleAt = _index(r, '"oracle":"', 0);
        require(oracleAt != type(uint256).max, "missing oracle");
        f.oracle = _stringAt(r, oracleAt + 10);
        if (!v5) return;
        uint256 bondAt = _index(r, '"bond":{', 0);
        if (bondAt != type(uint256).max && bondAt < givesAt) {
            f.deposited = true;
            uint256 assetAt = _index(r, '"asset":{', bondAt);
            uint256 conceptsAt = _index(r, '"concepts":[', assetAt);
            uint256 close = conceptsAt + 11;
            while (close < r.length && r[close] != ']') close++;
            f.depositConcepts = _slice(r, conceptsAt + 11, close + 1);
            f.depositQty = _ratField(r, '"qty":"', assetAt, givesAt);
            uint256 unitAt = _index(r, '"unit":"', assetAt);
            f.depositUnit = _stringAt(r, unitAt + 8);
            uint256 escrowAt = _index(r, '"escrow":"', bondAt);
            f.depositEscrowed = escrowAt != type(uint256).max && escrowAt < givesAt && r[escrowAt + 10] != '"';
        }
        uint256 reqAt = _index(r, '"requires":{', 0);
        require(reqAt != type(uint256).max, "v5: missing requires");
        uint256 reqEnd = _index(r, '"v":5', reqAt);
        f.requiring = true;
        f.point = _ratField(r, '"point":"', reqAt, reqEnd);
        uint256 accAt = _index(r, '"accepts":[', reqAt);
        require(accAt != type(uint256).max && accAt < reqEnd, "v5: missing accepts");
        f.accepts = _slice(r, accAt + 10, _index(r, '"oracles":[', accAt));   // up to the next key
        uint256 listAt = _index(r, '"oracles":[', reqAt);
        require(listAt != type(uint256).max && listAt < reqEnd, "v5: missing oracles");
        uint256 lclose = listAt + 10;
        while (lclose < reqEnd && r[lclose] != ']') lclose++;
        f.reqOracles = _slice(r, listAt + 10, lclose + 1);
        uint256 escAt = _index(r, '"escrows":[', reqAt);
        f.reqEscrow = escAt != type(uint256).max && escAt < reqEnd && r[escAt + 11] != ']';
    }

    /// `requirer`'s requirement against `other`'s declaration, `other` taking
    /// `taken` of `whole` (a give reserves its deposit per fill; a want and an
    /// operator's run are whole: 1/1). The structural half: the witness type
    /// accepted; a deposit present, escrowed if one is required; and, for an
    /// acceptance whose category list equals the deposit's *by name* (both
    /// canonical, so equal sets are equal bytes) in the same unit, the
    /// reserved quantity covers point / price by cross-multiplication. An
    /// acceptance that would need subsumption to match is the semantic half's:
    /// no entry equal by name passes here and is re-derived off chain.
    function _requireMeets(Facts memory requirer, Facts memory other, Rat memory taken, Rat memory whole)
        private pure
    {
        if (!requirer.requiring) return;
        _requireOracle(requirer, other);
        if (requirer.point.n == 0) return;
        require(other.deposited, "no deposit against the counterparty's requirement");
        require(!requirer.reqEscrow || other.depositEscrowed, "the deposit is not in an escrow");
        // reserved = qty * taken / whole
        Rat memory reserved = whole.n == 0 ? other.depositQty : _div(_mul(other.depositQty, taken), whole);
        // find an acceptance equal by name and unit: [<concepts>,"<unit>","<price>"]
        bytes memory needle = abi.encodePacked('[', other.depositConcepts, ',"', other.depositUnit, '","');
        uint256 at = _indexBytes(requirer.accepts, needle, 0);
        if (at == type(uint256).max) return;                    // subsumption, if any: the semantic half
        Rat memory price = _ratField(requirer.accepts, '","', at + needle.length - 3, requirer.accepts.length);
        // reserved >= point / price  <=>  reserved * price >= point
        require(_geq(_mul(reserved, price), requirer.point), "deposit share below the counterparty's neutral point");
    }

    function _requireOracle(Facts memory requirer, Facts memory other) private pure {
        if (requirer.reqOracles.length > 2) {                 // not "[]": a list of accepted types
            bytes memory quoted = abi.encodePacked('"', other.oracle, '"');
            require(_indexBytes(requirer.reqOracles, quoted, 0) != type(uint256).max,
                    "witness type not accepted by the counterparty");
        }
    }

    /// The parts of a composed want, `"parts":[{"concepts":[...],"min":..,
    /// "qty":..,"step":..,"unit":..},...]` (sorted keys): each part starts
    /// at its `{"concepts":` and ends at the next one's, or the side's end.
    function _parts(bytes memory r, uint256 from, uint256 to)
        private pure returns (Rat[] memory qtys, bytes[] memory units)
    {
        uint256 count = 0;
        uint256 at = _index(r, '{"concepts":', from);
        while (at != type(uint256).max && at < to) { count++; at = _index(r, '{"concepts":', at + 1); }
        require(count >= 2, "a composed want has at least two parts");
        qtys = new Rat[](count);
        units = new bytes[](count);
        uint256 start = _index(r, '{"concepts":', from);
        for (uint256 i = 0; i < count; i++) {
            uint256 next = _index(r, '{"concepts":', start + 1);
            uint256 end = (next == type(uint256).max || next > to) ? to : next;
            qtys[i] = _ratField(r, '"qty":"', start, end);
            units[i] = _unitField(r, start, end);
            start = next;
        }
    }

    function _unitField(bytes memory r, uint256 from, uint256 to) private pure returns (bytes memory) {
        uint256 at = _index(r, '"unit":"', from);
        require(at != type(uint256).max && at < to, "missing unit");
        return _stringAt(r, at + 8);
    }

    function _eq(Rat memory a, Rat memory b) private pure returns (bool) {
        return a.n * b.d == b.n * a.d;
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

    function _slice(bytes memory r, uint256 from, uint256 to) private pure returns (bytes memory out) {
        out = new bytes(to - from);
        for (uint256 i = 0; i < out.length; i++) out[i] = r[from + i];
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
