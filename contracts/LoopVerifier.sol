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
///   * each offer is a v4, v5 or v6 record whose pins equal the beat's (U10);
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
///   * (C4, 2026-09-29) an option give — a v6 record naming its underlying —
///     comes with its underlying's record under the same root: a give by the
///     option's writer, in its unit, valid through the exercise window, with
///     the option's quantity free after fills and active holds; the beat's
///     committed hold is exactly the leg's (`checkHolds`), and a taker's
///     remainder counts the holds of others (`filled(offer, taker)`), so a
///     non-holder cannot exercise what is held;
///   * (I3) every item a give — or an option's underlying — names has the
///     beat's committed claim for its maker through that offer
///     (`checkClaims`); a second claim on the item is finalize's race;
///   * (R3b) every credential entry either side requires has a statement
///     about the other side presented under the book root
///     (`cred/<subject>/<id>`), and, unless self-bonded, its issuer's register
///     pinned by the beat, with `revoked/<id>` and `suspended/<id>` absent
///     under that pinned root (`checkStatements`).
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

    /// A register the beat pins (R3b, 2026-09-29; counterparty-gate.md §3.3).
    struct RegisterPin {
        bytes id;                  // the register's id as records spell it (a statement's issuer)
        bytes32 root;              // its pinned root
        uint8 addressing;          // that root's scheme: 0 sha256, 1 Swarm
    }

    /// A presented statement and its standing (R3b).
    struct StatementProof {
        uint32 give;               // the leg's give it concerns
        bool ofGive;               // true: about the give's maker, for the want's entry; false: the reverse
        bytes record;              // the cred/ value: {"rsv":1,"val":{"presentation":..,"statement":<statement>}}
        bytes[] nodes;             // "cred/<subject>/<statement id>" under the book root
        bytes[] revoked;           // "revoked/<statement id>" absent under the issuer's pinned root
        bytes[] suspended;         // "suspended/<statement id>" absent there
    }

    struct Leg {
        OfferProof want;
        OfferProof[] gives;
        Rat[] taken;               // quantity taken from each give
        OfferProof[] underlying;   // C4: give i's underlying when it is an option; else id 0, no bytes
    }

    /// The hold an option leg writes (C4, options-and-cover.md §6.2): `qty` of
    /// `underlying` kept for `holder` (keccak of the wanter's key) from the
    /// exercise window's start to its end; `cap` the underlying's quantity.
    struct Hold {
        bytes32 option;
        bytes32 underlying;
        Rat qty;
        Rat cap;
        bytes32 holder;
        uint64 from;
        uint64 until;
        uint32 leg;
    }

    /// The claim a give naming `item(h)` writes (I3, items-and-ownership.md
    /// §2): its maker's (keccak of the key) one open claim on the item,
    /// through `offer` (an option's: its underlying), until `until`.
    struct ItemClaim {
        bytes32 item;
        bytes32 maker;
        bytes32 offer;
        uint64 until;
        uint32 leg;
    }

    /// What one leg's verification established, for the commitment checks.
    struct Verified {
        Facts want;
        Facts[] gives;
        Facts[] under;             // give i's underlying (empty unless an option)
        bytes32 taker;             // keccak of the want's maker
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
        // v6 (2026-09-29): an option's underlying and window; validity; credential entries
        bytes32 underlying;        // 0 unless an option
        bool hasExercise;
        uint256 exStart;
        uint256 exEnd;
        uint256 validStart;
        uint256 validEnd;
        bool validOpen;            // no end: valid until withdrawn
        uint256 entries;           // `requires.counterparty` entries
        bytes concepts;            // the thing's `"concepts":[...]` array (empty for parts)
    }

    /// Verify one leg. `filled(id, taker)` answers what is no longer
    /// available of an offer to `taker` — recorded fills and the active holds
    /// of others (0/1 for nothing; taker 0: every active hold);
    /// `potential(maker)` the proposed potential of a maker (revert if
    /// unknown). Returns the facts of the want, the gives and the options'
    /// underlyings, for the caller's commitment checks.
    function verifyLeg(
        Beat memory beat,
        Leg memory leg,
        function(bytes32, bytes32) view returns (Rat memory) filled,
        function(bytes memory) view returns (Rat memory) potential
    ) internal view returns (Verified memory v) {
        require(leg.gives.length >= 1 && leg.gives.length == leg.taken.length
                && leg.gives.length == leg.underlying.length, "leg shape");
        Facts memory want = _verifyOffer(beat, leg.want);
        require(!want.isGive, "the head of a leg is a want");
        v.want = want;
        v.taker = keccak256(want.maker);
        bool composed = want.parts.length > 0;
        // a composed want (v4 `Parts`, on chain since 2026-09-18): give i serves
        // part i, whole — the quantity taken is the part's, in the part's unit
        if (composed) require(leg.gives.length == want.parts.length, "one give per part");
        Facts[] memory gives = new Facts[](leg.gives.length);
        v.gives = gives;
        v.under = new Facts[](leg.gives.length);
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
            _requireTakes(g, t, filled(leg.gives[i].id, v.taker));
            v.under[i] = _underlying(beat, leg, i, g, filled);
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

    /// Give `i`'s underlying, when it is an option (C4; `gate.option_fault`
    /// off chain): the writer's own give, in the option's unit, valid through
    /// the exercise window, with the option's quantity free of fills and
    /// active holds. A plain give brings no underlying.
    function _underlying(Beat memory beat, Leg memory leg, uint256 i, Facts memory g,
                         function(bytes32, bytes32) view returns (Rat memory) filled)
        private view returns (Facts memory p)
    {
        OfferProof memory up = leg.underlying[i];
        if (g.underlying == bytes32(0)) {
            require(up.id == bytes32(0) && up.record.length == 0, "an underlying for a plain give");
            return p;
        }
        require(up.id == g.underlying, "not the option's underlying");
        require(g.hasExercise, "an option without an exercise window");
        p = _verifyOffer(beat, up);
        require(p.isGive && p.parts.length == 0, "the underlying is not a give");
        require(_bytesEq(p.maker, g.maker), "option by another maker than its underlying's");
        require(_bytesEq(p.unit, g.unit), "the option's unit is not its underlying's");
        require(p.validStart <= g.exStart && (p.validOpen || g.exEnd <= p.validEnd),
                "the underlying is not valid through the exercise window");
        require(_geq(p.qty, _add(filled(up.id, bytes32(0)), g.qty)),
                "no free capacity on the underlying for the hold");
    }

    /// The beat's committed holds for leg `index` are exactly its option
    /// gives' (C4): one per option, of what the leg took, the underlying's
    /// quantity as its cap, for the wanter, over the exercise window.
    function checkHolds(Verified memory v, Leg memory leg, Hold[] memory holds, uint256 index)
        internal pure
    {
        uint256 options = 0;
        for (uint256 i = 0; i < v.gives.length; i++) {
            Facts memory g = v.gives[i];
            if (g.underlying == bytes32(0)) continue;
            options++;
            bool found = false;
            for (uint256 k = 0; k < holds.length; k++) {
                Hold memory h = holds[k];
                if (h.leg != index || h.option != leg.gives[i].id) continue;
                require(!found, "two holds for one option give");
                found = true;
                require(h.underlying == g.underlying && _eq(h.qty, leg.taken[i]) && _eq(h.cap, v.under[i].qty)
                        && h.holder == v.taker && h.from == g.exStart && h.until == g.exEnd,
                        "a hold is not its option leg's");
            }
            require(found, "an option leg without its hold");
        }
        uint256 count = 0;
        for (uint256 k = 0; k < holds.length; k++) if (holds[k].leg == index) count++;
        require(count == options, "a hold no option give of the leg writes");
    }

    /// The beat's committed item claims for leg `index` are exactly its
    /// gives' (I3): one per item each give names — an option's, its
    /// underlying names — for the give's maker, through that offer; an
    /// option's until its window ends, a fill's past the beat's time (its
    /// exact end, the handover window's, is the semantic half's).
    function checkClaims(Verified memory v, Leg memory leg, ItemClaim[] memory claims, uint256 index,
                         uint256 at) internal pure
    {
        uint256 expected = 0;
        for (uint256 i = 0; i < v.gives.length; i++) {
            Facts memory g = v.gives[i];
            bool option = g.underlying != bytes32(0);
            bytes32 subject = option ? g.underlying : leg.gives[i].id;
            bytes32 maker = keccak256(g.maker);
            bytes32[] memory items = _items(option ? v.under[i].concepts : g.concepts);
            for (uint256 j = 0; j < items.length; j++) {
                expected++;
                bool found = false;
                for (uint256 k = 0; k < claims.length; k++) {
                    ItemClaim memory c = claims[k];
                    if (c.leg != index || c.item != items[j] || c.maker != maker) continue;
                    require(!found, "two claims on one item by one maker in a leg");
                    found = true;
                    require(c.offer == subject, "an item claim through another offer");
                    require(option ? c.until == g.exEnd : c.until > at, "an item claim's end");
                }
                require(found, "a give naming an item without its claim");
            }
        }
        uint256 count = 0;
        for (uint256 k = 0; k < claims.length; k++) if (claims[k].leg == index) count++;
        require(count == expected, "an item claim no give of the leg names");
    }

    /// What a leg's statements are checked against (R3b): the makers of
    /// its sides and the credential entries each requires — the leg
    /// verifier's answer, handed to `checkStatements` (in its own contract,
    /// `StatementVerifier`: EIP-170).
    struct Parties {
        bytes wantMaker;
        bytes[] giveMakers;
        uint256 wantEntries;
        uint256[] giveEntries;
    }

    function parties(Verified memory v) internal pure returns (Parties memory p) {
        p.wantMaker = v.want.maker;
        p.wantEntries = v.want.entries;
        p.giveMakers = new bytes[](v.gives.length);
        p.giveEntries = new uint256[](v.gives.length);
        for (uint256 i = 0; i < v.gives.length; i++) {
            p.giveMakers[i] = v.gives[i].maker;
            p.giveEntries[i] = v.gives[i].entries;
        }
    }

    /// Every credential entry either side of the leg requires has one
    /// statement about the other side, per give, each standing
    /// (`verifyStatement`). Which statement meets which entry (category,
    /// kind, path, validity, the deposit's share) is the semantic half's.
    function checkStatements(Beat memory beat, RegisterPin[] memory regs, StatementProof[] memory statements,
                             Parties memory p) internal pure
    {
        uint256 need = 0;
        for (uint256 i = 0; i < p.giveMakers.length; i++) {
            need += p.wantEntries + p.giveEntries[i];
            uint256 about = 0; uint256 by = 0;
            for (uint256 k = 0; k < statements.length; k++) {
                if (statements[k].give != i) continue;
                if (statements[k].ofGive) about++; else by++;
            }
            require(about == p.wantEntries && by == p.giveEntries[i],
                    "the statements are not one per required entry");
        }
        require(statements.length == need, "a statement for no give of the leg");
        for (uint256 k = 0; k < need; k++) {
            StatementProof memory s = statements[k];
            verifyStatement(beat, regs, s, s.ofGive ? p.giveMakers[s.give] : p.wantMaker);
        }
    }

    /// One statement's standing: presented under the book root as
    /// `cred/<subject>/<id>`, about `subject`, and — unless self-bonded —
    /// its issuer's register pinned, `revoked/<id>` and `suspended/<id>`
    /// absent under that root.
    function verifyStatement(Beat memory beat, RegisterPin[] memory regs, StatementProof memory s,
                             bytes memory subject) internal pure
    {
        bytes memory blob = s.record;
        bytes memory head = bytes('{"rsv":1,"val":{"presentation":');
        require(blob.length > head.length + 2 && blob[blob.length - 1] == '}' && blob[blob.length - 2] == '}',
                "statement envelope");
        for (uint256 i = 0; i < head.length; i++) require(blob[i] == head[i], "statement envelope");
        // the statement is the envelope's last key: its last `,"statement":{`
        // (a presentation before it may hold anything; the statement's own
        // fields hold no such key)
        uint256 at = _lastIndex(blob, bytes(',"statement":{'));
        require(at != type(uint256).max && at >= head.length, "statement envelope");
        bytes memory r = _slice(blob, at + 13, blob.length - 2);
        bytes32 sid = sha256(r);
        require(_hasExact(r, abi.encodePacked('"subject":"', subject, '"')), "the statement is about another key");
        require(_endsWith(r, bytes('"v":1}')), "not a v1 statement");
        require(TrieProofVerifier.verifyInclusion(beat.bookRoot, abi.encodePacked("cred/", subject, "/", _hex(sid)),
                                                  s.nodes, blob, beat.addressing),
                "the statement is not presented under the book root");
        if (_hasExact(r, bytes('"kind":"self-bonded"'))) return;     // its deposit backs it, no register
        uint256 issuerAt = _index(r, '"issuer":"', 0);
        require(issuerAt != type(uint256).max, "statement shape");
        bytes memory issuer = _stringAt(r, issuerAt + 10);
        for (uint256 j = 0; j < regs.length; j++) {
            if (!_bytesEq(regs[j].id, issuer)) continue;
            require(TrieProofVerifier.verifyAbsence(regs[j].root, abi.encodePacked("revoked/", _hex(sid)),
                                                    s.revoked, regs[j].addressing),
                    "the statement is revoked under its register's pinned root");
            require(TrieProofVerifier.verifyAbsence(regs[j].root, abi.encodePacked("suspended/", _hex(sid)),
                                                    s.suspended, regs[j].addressing),
                    "the statement is suspended under its register's pinned root");
            return;
        }
        revert("the statement's register is not pinned");
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
        bytes memory r = _slice(blob, head.length, blob.length - 1);
        require(sha256(r) == p.id, "record does not hash to its id");
        bytes memory key = abi.encodePacked("offer/", _hex(p.id));
        require(TrieProofVerifier.verifyInclusion(beat.bookRoot, key, p.nodes, blob, beat.addressing),
                "offer not under the book root");
        // version and pins
        uint8 ver = _hasExact(r, bytes('"v":6,')) ? 6 : _hasExact(r, bytes('"v":5,')) ? 5
            : _hasExact(r, bytes('"v":4,')) ? 4 : 0;
        require(ver != 0, "not a v4, v5 or v6 record");
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
        _guarantees(r, f, ver, g);
        _validity(r, f, ver);
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
        uint256 c = _index(r, '"concepts":[', thingStart);
        require(c != type(uint256).max && c < thingEnd, "missing concepts");
        f.concepts = _slice(r, c + 11, _arrayEnd(r, c + 11) + 1);
    }

    /// `"valid":[start,end|null]`, and on a v6 record an option's
    /// `"underlying":"<id>"` and `"exercise":[start,end]` (an option's window
    /// always ends: the hold ends with it).
    function _validity(bytes memory r, Facts memory f, uint8 ver) private pure {
        uint256 at = _index(r, '"valid":[', 0);
        require(at != type(uint256).max, "missing valid");
        uint256 next;
        (f.validStart, next) = _intAt(r, at + 9);
        require(r[next] == ',', "valid shape");
        if (r[next + 1] == 'n') f.validOpen = true;
        else (f.validEnd, ) = _intAt(r, next + 1);
        if (ver < 6) return;
        uint256 u = _index(r, '"underlying":"', 0);
        require(u != type(uint256).max, "v6: missing underlying");
        if (r[u + 14] == '"') return;
        f.underlying = _hex32At(r, u + 14);
        uint256 e = _index(r, '"exercise":[', 0);
        require(e != type(uint256).max, "an option without an exercise window");
        f.hasExercise = true;
        (f.exStart, next) = _intAt(r, e + 12);
        require(r[next] == ',' && r[next + 1] != 'n', "an option's window has an end");
        (f.exEnd, ) = _intAt(r, next + 1);
    }

    /// The maker's witness type; on a v5 record its deposit (`"bond":{"asset":
    /// {"concepts":[..],"min":..,"qty":..,"step":..,"unit":".."},"escrow":"..",
    /// "value":".."}` or `"bond":null`) and its requirement (`"requires":{
    /// "accepts":[[[cat..],"unit","price"],..],"escrows":[..]?,"ladder":[..]?,
    /// "oracles":[..],"point":".."}`), read from the sorted-key record bytes.
    function _guarantees(bytes memory r, Facts memory f, uint8 ver, uint256 givesAt) private pure {
        uint256 oracleAt = _index(r, '"oracle":"', 0);
        require(oracleAt != type(uint256).max, "missing oracle");
        f.oracle = _stringAt(r, oracleAt + 10);
        if (ver < 5) return;
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
        // the requirement ends where the next top-level key begins: `"v"` on a
        // v5 record, `"underlying"` on a v6 one (sorted keys)
        uint256 reqEnd = ver == 5 ? _index(r, '"v":5', reqAt) : _index(r, '"underlying":"', reqAt);
        require(reqEnd != type(uint256).max, "requires shape");
        f.requiring = true;
        f.point = _ratField(r, '"point":"', reqAt, reqEnd);
        uint256 accAt = _index(r, '"accepts":[', reqAt);
        require(accAt != type(uint256).max && accAt < reqEnd, "v5: missing accepts");
        // the array itself, bounded by its closing bracket: on a v6 record the
        // keys after it (claim_period, counterparty, ...) are not acceptances
        f.accepts = _slice(r, accAt + 10, _arrayEnd(r, accAt + 10) + 1);
        uint256 cp = _index(r, '"counterparty":[', reqAt);
        if (ver == 6 && cp != type(uint256).max && cp < reqEnd) {
            uint256 end = _arrayEnd(r, cp + 15);
            uint256 k = _index(r, '{"category":"', cp);
            while (k != type(uint256).max && k < end) { f.entries++; k = _index(r, '{"category":"', k + 1); }
        }
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

    /// The index of the `]` closing the array that opens at `start`, reading
    /// strings (and their escapes) as opaque.
    function _arrayEnd(bytes memory r, uint256 start) private pure returns (uint256) {
        require(start < r.length && r[start] == '[', "array shape");
        uint256 depth = 0;
        bool inString = false;
        for (uint256 i = start; i < r.length; i++) {
            bytes1 c = r[i];
            if (inString) {
                if (c == '\\') i++;
                else if (c == '"') inString = false;
                continue;
            }
            if (c == '"') inString = true;
            else if (c == '[') depth++;
            else if (c == ']') {
                depth--;
                if (depth == 0) return i;
            }
        }
        revert("array shape");
    }

    /// The item ids a concepts array names: each element `"item(<64 hex>)"`
    /// (an element starts after `[` or `,`; a quote inside a string is
    /// escaped, so none is mistaken for one). A shortened or malformed id is
    /// refused, as `items.well_formed` refuses it off chain.
    function _items(bytes memory c) private pure returns (bytes32[] memory out) {
        bytes memory head = bytes('"item(');
        uint256 count = 0;
        for (uint256 pass = 0; pass < 2; pass++) {
            uint256 found = 0;
            for (uint256 i = 1; i + head.length <= c.length; i++) {
                if (c[i - 1] != '[' && c[i - 1] != ',') continue;
                bool hit = true;
                for (uint256 j = 0; j < head.length; j++) if (c[i + j] != head[j]) { hit = false; break; }
                if (!hit) continue;
                require(i + head.length + 66 <= c.length && c[i + head.length + 64] == ')'
                        && c[i + head.length + 65] == '"', "an item term that is not a whole id");
                if (pass == 1) out[found] = _hex32At(c, i + head.length);
                found++;
            }
            if (pass == 0) { count = found; out = new bytes32[](count); }
        }
    }

    /// A non-negative integer at `from`, and the index after it.
    function _intAt(bytes memory r, uint256 from) private pure returns (uint256 v, uint256 next) {
        next = from;
        while (next < r.length && r[next] >= '0' && r[next] <= '9') {
            v = v * 10 + (uint8(r[next]) - 48);
            next++;
        }
        require(next > from, "not a number");
    }

    function _hex32At(bytes memory r, uint256 from) private pure returns (bytes32 out) {
        require(from + 64 <= r.length, "hex shape");
        uint256 acc = 0;
        for (uint256 i = 0; i < 64; i++) {
            bytes1 ch = r[from + i];
            uint8 d;
            if (ch >= '0' && ch <= '9') d = uint8(ch) - 48;
            else if (ch >= 'a' && ch <= 'f') d = uint8(ch) - 87;
            else revert("hex shape");
            acc = (acc << 4) | d;
        }
        out = bytes32(acc);
    }

    function _lastIndex(bytes memory hay, bytes memory needle) private pure returns (uint256 found) {
        found = type(uint256).max;
        uint256 at = _indexBytes(hay, needle, 0);
        while (at != type(uint256).max) {
            found = at;
            at = _indexBytes(hay, needle, at + 1);
        }
    }

    function _endsWith(bytes memory hay, bytes memory tail) private pure returns (bool) {
        if (hay.length < tail.length) return false;
        for (uint256 i = 0; i < tail.length; i++) if (hay[hay.length - tail.length + i] != tail[i]) return false;
        return true;
    }

    /// r[from:to], copied a word at a time (2026-09-29: the byte loops were
    /// most of a leg's gas); the last word's tail past `to` is zeroed.
    function _slice(bytes memory r, uint256 from, uint256 to) private pure returns (bytes memory out) {
        require(from <= to && to <= r.length, "slice");
        uint256 len = to - from;
        out = new bytes(len);
        assembly ("memory-safe") {
            let src := add(add(r, 32), from)
            let dst := add(out, 32)
            for { let i := 0 } lt(i, len) { i := add(i, 32) } { mstore(add(dst, i), mload(add(src, i))) }
            mstore(add(dst, len), 0)
        }
    }

    function _stringAt(bytes memory r, uint256 from) private pure returns (bytes memory) {
        uint256 end = from;
        while (end < r.length && r[end] != '"') end++;
        return _slice(r, from, end);
    }

    function _index(bytes memory hay, string memory needle, uint256 from) private pure returns (uint256) {
        return _indexBytes(hay, bytes(needle), from);
    }

    function _hasExact(bytes memory hay, bytes memory needle) private pure returns (bool) {
        return _indexBytes(hay, needle, 0) != type(uint256).max;
    }

    /// The first index at or after `from` where `needle` occurs in `hay`, or
    /// the maximum: each position compared by its first word under a mask
    /// and, for a needle longer than a word, by the keccak of the whole
    /// (2026-09-29, the word-at-a-time form of the byte loop it replaces).
    function _indexBytes(bytes memory hay, bytes memory needle, uint256 from)
        private pure returns (uint256 found)
    {
        found = type(uint256).max;
        uint256 n = needle.length;
        uint256 h = hay.length;
        if (h < n) return found;
        if (n == 0) return from <= h ? from : found;
        assembly ("memory-safe") {
            let len := n
            if gt(len, 32) { len := 32 }
            let mask := not(sub(shl(mul(sub(32, len), 8), 1), 1))
            let word := and(mload(add(needle, 32)), mask)
            let whole := keccak256(add(needle, 32), n)
            let long := gt(n, 32)
            let base := add(hay, 32)
            let last := sub(h, n)
            for { let i := from } iszero(gt(i, last)) { i := add(i, 1) } {
                if eq(and(mload(add(base, i)), mask), word) {
                    if or(iszero(long), eq(keccak256(add(base, i), n), whole)) {
                        found := i
                        break
                    }
                }
            }
        }
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

    function _filledOf(bytes32 id, bytes32) internal view returns (LoopVerifier.Rat memory r) {
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
        LoopVerifier.Verified memory v = LoopVerifier.verifyLeg(beat, leg, _filledOf, _potentialOf);
        wantMaker = v.want.maker;
        giveMakers = new bytes[](v.gives.length);
        for (uint256 i = 0; i < v.gives.length; i++) giveMakers[i] = v.gives[i].maker;
    }
}
