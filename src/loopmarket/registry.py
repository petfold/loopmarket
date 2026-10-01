"""The distributed offer book: a RecordStore keyspace.

Layout (one book = one RecordStore, one root reference per version):

    offer/<offer_id>                 -> the offer record (immutable value)
    sig/<offer_id>                   -> detached maker signature (U8, off-feed)
    handoff/<loop_id>/<offer_id>     -> sealed settlement text (handoff.py)
    notice/<loop_id>/<offer_id>      -> a claimant's notice to the giver, sealed (R6, notice.py)
    cure/<loop_id>/<offer_id>        -> the giver's answer to it, sealed (R6)
    cred/<subject>/<statement_id>    -> {"statement": ..., "presentation": ...} — a statement about
                                        the book owner's key, presented for the counterparty gate
                                        (v6, R2, 2026-09-29; counterparty-gate.md §3.2)
    key/<address>                    -> a key card: a signature over a fixed message naming the
                                        address, so anyone may seal to the key (sigs.py, 2026-10-01)
    withdraw/<offer_id>              -> 1  (monotone tombstone: offer closed)
    fill/<offer_id>                  -> {"loop": <loop_id>, "qty": <taken>} for a give taken whole,
                                        {"loop": <loop_id>, "gives": [{"offer", "qty"}]} for a want
                                        (v4, 2026-09-14; the 2026-08 fill was {"loop"} alone)
    fill/<offer_id>/<loop_id>        -> {"loop": <loop_id>, "qty": <taken>} — a PARTIAL fill of a
                                        divisible give (2026-09-14): the remainder stays open, and
                                        the fills of one give sum to at most its quantity (U11)
    loop/<loop_id>                   -> the cleared loop record
    option/<offer_id>/<loop_id>      -> a hold on a plain offer, written with an option's fill (C2,
                                        2026-09-29): {"option", "holder", "until", "qty"}; active while
                                        now < until, the offer admissible only to the holder meanwhile
    exercise/<offer_id>/<option loop>/<loop_id> -> {"qty"}: what an exercise took of that hold
    item/<h>/<maker>/<loop_id>       -> {"offer", "until"}: a maker's claim on one unique item, written
                                        with the fill or hold that makes it (I2, 2026-09-29; per maker,
                                        plan D5); active while now < until

There is no index in the book. The `idx/{c,t,g}` prefixes (per concept,
per touched day bucket, per geohash prefix) were written by maker books
until 2026-08-21, then only by aggregators as derived state, and read by
nothing throughout; they retired 2026-09-12 when ontodag #14 made the
`DimensionIndex` one query — ontodag is the one intersection engine, and
a second index of the same three dimensions never gets a query path
(`docs/plans/ontodag-coupling.md` §5). Derived query structures, if they
are ever published, get a manifest root of their own then (cone
summaries, `P1-federated-book.md` §2) — never book keys.

Everything the marketplace knows at a moment is one root reference:
`snapshot()` returns `(root, frozen_reader)`, and solvers work against that
frozen state — recordstore's snapshot isolation is what makes "solve against
a pinned book" free. Offers are immutable and content-addressed, so
publication is naturally an OR-set: concurrent publishers writing the same
offer write byte-identical records (canonical encoding), concurrent distinct
publications touch distinct keys, and `commit(reconcile=True)` three-way
merges the rest. The only genuinely racy key class is `fill/` — clearing
claims — resolved first-writer-wins by `or_set_resolver`.

Deployment shapes (see ARCHITECTURE.md §5):
- local/dev: RecordStore over MemoryBytesStore/DirBytesStore.
- shared book on Swarm: `swarm_offer_book(topic, signer=...)` — blobs via
  BeeBytesStore, the mutable head via a signed SwarmFeedPointer.
- fully peer-to-peer: one book *per maker* (each maker signs their own feed);
  an aggregator folds maker roots with `RecordStore.merge`, which the
  canonical trie makes O(divergence). The key layout is identical either way.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Iterable, Iterator

from .schema import q, rat, Offer, Statement

OFFER = "offer/"
SIG = "sig/"
WITHDRAW = "withdraw/"
FILL = "fill/"
LOOP = "loop/"
HANDOFF = "handoff/"   # handoff/<loop_id>/<offer_id> -> sealed text (see handoff.py)
CRED = "cred/"         # cred/<subject>/<statement_id> -> a presented statement (R2)
NOTICE = "notice/"     # notice/<loop_id>/<offer_id> -> a sealed notice (R6)
OPTION = "option/"     # option/<offer_id>/<loop_id> -> a hold (C2)
EXERCISE = "exercise/"  # exercise/<offer_id>/<option loop>/<loop_id> -> what an exercise took (C2)
ITEM = "item/"         # item/<h>/<maker>/<loop_id> -> a maker's claim on an item (I2)
CURE = "cure/"         # cure/<loop_id>/<offer_id> -> a sealed cure (R6)
KEY = "key/"           # key/<address> -> the key's card: its public key, recoverable (2026-10-01)


class PartialLoopError(RuntimeError):
    """A book holds a loop missing some of its fills (planned invariant U11).

    Clearing is atomic per writer, so this can only arise from a merge in
    which two loops claimed one offer. There is no safe repair — evicting a
    cleared loop is a finality rollback — so the checker raises instead of
    resolving, by design (docs/plans/P1-federated-book.md §3).
    """


def or_set_resolver(key: str, base, ours, theirs):
    """Merge policy for concurrent book writers.

    Offers and indexes are add-only values of identical content — either
    side's copy is the value. A doubly-claimed offer keeps the
    lexicographically smaller loop id, deterministically on every replica
    (commutative, so 3+ writers stay order-independent).

    The per-key fill rule is convergence mechanics, not clearing policy:
    when two loops claim one offer, resolving fill-by-fill can strand the
    losing loop with its `loop/` record and its *other* fills — a cleared
    loop missing a leg, which nothing repairs. Until the deterministic
    loop-granularity resolver exists (registered open problem,
    docs/plans/P1-federated-book.md §3), `verify_loop_atomicity` checks the
    merged book and fails loudly (planned invariant U11).
    """
    if ours == theirs:
        return ours
    if key.startswith(FILL):
        candidates = [v for v in (ours, theirs) if isinstance(v, dict)]
        return min(candidates, key=lambda v: v.get("loop", "")) if candidates else ours
    # add-only keyspace: prefer presence over absence
    return ours if ours is not None else theirs


class OfferRegistry:
    """Publish, enumerate and clear offers over a duck-typed RecordStore."""

    def __init__(self, store):
        self.store = store

    # -- writing ---------------------------------------------------------------

    def publish(self, offer: Offer) -> str:
        oid = offer.offer_id
        self.store.put(OFFER + oid, offer.to_record())
        return oid

    def publish_many(self, offers: Iterable[Offer]) -> list[str]:
        return [self.publish(o) for o in offers]

    def absorb(self, other: "OfferRegistry") -> None:
        """Re-assert another book's entire content as this writer's base.

        The clearing pattern (P1 §1): a clearing instance bases its
        *own feed* on an aggregator's fold by re-asserting the folded
        records and committing. Canonical encoding makes the re-commit
        reproduce the source root byte-for-byte — equal content, equal
        root — so anyone can verify the claimed base is exactly the fold
        (ontodag's clone-verification pattern). O(book); incremental
        re-basing via `diff` is the production upgrade.
        """
        for key, rec in other.store.items(""):
            self.store.put(key, rec)

    def withdraw(self, offer_id: str) -> None:
        """Close an offer forever: a monotone tombstone (lands with P1, §5).

        An *add*, never a delete — a removal is lossy and does not commute
        with a concurrent addition, so it cannot survive a grow-only merge;
        the tombstone merges as ordinary OR-set presence and fails closed
        the moment it is visible at fold time. Re-publishing the identical
        offer does not un-withdraw it (same content, same id, same
        tombstone): a fresh intention is a fresh offer, fresh nonce,
        fresh id.
        """
        if not self.store.contains(OFFER + offer_id):
            raise KeyError(offer_id)
        self.store.put(WITHDRAW + offer_id, 1)

    def is_withdrawn(self, offer_id: str) -> bool:
        return self.store.contains(WITHDRAW + offer_id)

    def attach_signature(self, offer_id: str, sig_hex: str) -> None:
        """Store a detached maker signature beside its offer (planned U8).

        The secondary authenticity layer, for offers circulating outside
        their home feed; feed ownership stays primary. Fail closed: a
        signature that does not recover to the offer's maker is refused,
        so the book never holds a sidecar that lies about who is speaking.
        Needs the `sig` extra (eth-keys).
        """
        from .sigs import recover_maker

        offer = self.get(offer_id)
        if recover_maker(offer_id, sig_hex) != offer.maker:
            raise ValueError("signature does not recover to the offer's maker")
        self.store.put(SIG + offer_id, sig_hex)

    def signature(self, offer_id: str) -> str | None:
        """The offer's detached signature, if one has been attached."""
        key = SIG + offer_id
        return self.store.get(key) if self.store.contains(key) else None

    def publish_key_card(self, address: str, sig_hex: str) -> None:
        """Store a key card (`sigs.sign_key_card`) under `key/<address>`: the
        key's public key, recoverable by anyone who wants to seal to it — an
        adjudicator's, a register's, a maker's with no signed offer yet. Fail
        closed: a card that does not recover to its address is refused."""
        from .sigs import key_card_public_key
        key_card_public_key(address, sig_hex)
        self.store.put(KEY + address.lower(), sig_hex)

    def key_card(self, address: str) -> str | None:
        key = KEY + address.lower()
        return self.store.get(key) if self.store.contains(key) else None

    def loop_of(self, offer_id: str) -> str | None:
        """The loop that filled `offer_id` whole, if any; for a partially
        filled give, the first of its loops in sorted order (`loops_of` has
        them all)."""
        key = FILL + offer_id
        rec = self.store.get(key) if self.store.contains(key) else None
        if isinstance(rec, dict):
            return rec.get("loop")
        loops = self.loops_of(offer_id)
        return loops[0] if loops else None

    def loops_of(self, offer_id: str) -> list[str]:
        """Every loop that took from `offer_id`: the whole fill's, or the
        partial fills', sorted."""
        key = FILL + offer_id
        if self.store.contains(key):
            rec = self.store.get(key)
            return [rec["loop"]] if isinstance(rec, dict) and rec.get("loop") else []
        return sorted(k[len(key) + 1:] for k in self.store.keys(key + "/"))

    def taken(self, offer_id: str) -> Fraction:
        """How much of the offer's thing fills have taken: the whole
        quantity under a whole fill (a want's always), the sum of the partial
        fills otherwise."""
        key = FILL + offer_id
        if self.store.contains(key):
            return q(self.get(offer_id).parts[0].qty) if not self.get(offer_id).composed \
                else Fraction(1)
        total = Fraction(0)
        for k in self.store.keys(key + "/"):
            rec = self.store.get(k)
            total += q(rec["qty"]) if isinstance(rec, dict) and "qty" in rec else 0
        return total

    def available(self, offer_id: str, now: int | None = None) -> Fraction:
        """What a fill may still take from a give: its quantity less what
        fills took (0 for a want or a composed want once filled) and, given
        `now`, less what active holds keep for their holders (C2)."""
        offer = self.get(offer_id)
        if offer.composed:
            return Fraction(0) if self.store.contains(FILL + offer_id) else Fraction(1)
        left = q(offer.thing.qty) - self.taken(offer_id)
        if now is not None:
            left -= self.held(offer_id, now)
        return left

    def availability(self, offers, now: int | None = None) -> dict[str, Fraction]:
        """{offer_id: available} for the offers given — what the solver and
        clearing pass to the matching checks."""
        return {o.offer_id: self.available(o.offer_id, now) for o in offers}

    # -- holds (options on plain offers, C2, options-and-cover.md §3) ------------

    def holds(self, offer_id: str) -> list[tuple[str, dict]]:
        """Every (option loop, hold record) on an offer, in key order."""
        prefix = f"{OPTION}{offer_id}/"
        return [(k[len(prefix):], rec) for k, rec in self.store.items(prefix)]

    def hold_left(self, offer_id: str, option_loop: str) -> Fraction:
        """What of one hold its exercises have not taken yet."""
        rec = self.store.get(f"{OPTION}{offer_id}/{option_loop}")
        taken = sum((q(r["qty"]) for _, r in self.store.items(f"{EXERCISE}{offer_id}/{option_loop}/")),
                    Fraction(0))
        return q(rec["qty"]) - taken

    def held(self, offer_id: str, now: int) -> Fraction:
        """What active holds keep of an offer at `now`: a function of time,
        so expiry needs no write (§3.6)."""
        return sum((self.hold_left(offer_id, lid) for lid, rec in self.holds(offer_id)
                    if now < int(rec["until"])), Fraction(0))

    def held_by(self, offer_id: str, holder: str, now: int) -> Fraction:
        """What `holder` may take of the offer by exercising at `now`: its
        holds whose option's exercise window is open (§3.5)."""
        total = Fraction(0)
        for lid, rec in self.holds(offer_id):
            if rec["holder"] == holder and self._exercisable(rec, now):
                total += self.hold_left(offer_id, lid)
        return total

    def exercisable(self, offer_id: str, now: int) -> Fraction:
        """What all holders together may exercise of the offer at `now`."""
        return sum((self.hold_left(offer_id, lid) for lid, rec in self.holds(offer_id)
                    if self._exercisable(rec, now)), Fraction(0))

    def _exercisable(self, rec: dict, now: int) -> bool:
        if not now < int(rec["until"]):
            return False
        try:
            option = self.get(rec["option"])
        except KeyError:
            return False
        return option.exercise is not None and option.exercise.start <= now

    def item_claims(self, h: str, maker: str) -> list[tuple[str, dict]]:
        """Every (loop, claim) `maker` has made on item h."""
        prefix = f"{ITEM}{h}/{maker}/"
        return [(k[len(prefix):], rec) for k, rec in self.store.items(prefix)]

    def item_claimed(self, h: str, maker: str, now: int, *, offer_id: str = "") -> bool:
        """Does `maker` hold an active claim on item h through an offer
        other than `offer_id`? The per-item rule (plan D5): one active hold
        or open fill per (maker, item) — it stops a seller double-selling by
        accident, and says nothing across makers."""
        return any(now < int(rec["until"]) and rec["offer"] != offer_id
                   for _, rec in self.item_claims(h, maker))

    def exercise_records(self, offer_id: str, holder: str, taken, now: int, loop_id: str) -> dict:
        """The `exercise/` records an exercise leg taking `taken` of the
        offer writes: the holder's open holds consumed in key order, the
        rest from the free remainder. Deterministic in the book and the
        decision (U2's discipline for fills)."""
        out, need = {}, q(taken)
        for lid, rec in self.holds(offer_id):
            if need <= 0:
                break
            if rec["holder"] != holder or not self._exercisable(rec, now):
                continue
            use = min(need, self.hold_left(offer_id, lid))
            if use > 0:
                out[f"{EXERCISE}{offer_id}/{lid}/{loop_id}"] = {"qty": rat(use)}
                need -= use
        return out

    def attach_handoff(self, loop_id: str, offer_id: str, record: dict, *,
                       fold=None) -> None:
        """Store a sealed handoff beside a *filled* offer of this book's
        maker: `handoff/<loop_id>/<offer_id>` (docs/plans/P1-spacetime-terms.md
        §4; `handoff.seal` makes the record). A sidecar like `sig/` — never
        in identity, OR-set presence in merges, unread by aggregators. The
        fill is checked against `fold` when given (fills live in the
        clearing book, which a maker's own book need not contain), else
        against this book. Fail closed: no fill, no handoff."""
        book = fold if fold is not None else self
        if book.loop_of(offer_id) != loop_id:
            raise ValueError("handoff for an offer this loop did not fill")
        if not isinstance(record, dict) or "ct" not in record:
            raise ValueError("a handoff record is a sealed payload")
        self.store.put(f"{HANDOFF}{loop_id}/{offer_id}", record)

    def handoff(self, loop_id: str, offer_id: str) -> dict | None:
        key = f"{HANDOFF}{loop_id}/{offer_id}"
        return self.store.get(key) if self.store.contains(key) else None

    def handoffs(self) -> Iterator[tuple[str, str, dict]]:
        """Every (loop_id, offer_id, sealed record) in the book."""
        for key, rec in self.store.items(HANDOFF):
            loop_id, _, offer_id = key[len(HANDOFF):].partition("/")
            yield loop_id, offer_id, rec

    def present(self, statement: Statement, presentation: dict | None = None) -> str:
        """Present a statement about a key in this book: `cred/<subject>/
        <statement id>` → the statement and the presentation it was derived
        from (`counterparty-gate.md` §3.2, R2). A sidecar like `sig/` and
        `handoff/`: never in any offer's identity, so a credential renews or
        is revoked without re-signing an offer; public, because the gate is
        a matching gate and the solver must see it before proposing. The
        fold admits it only in the subject's own book; `presentation` is
        the adapter's (an issuer's signature, a selective disclosure) and
        opaque here — never the documents themselves (§7)."""
        if presentation is not None and not isinstance(presentation, dict):
            raise ValueError("a presentation is a record")
        sid = statement.statement_id
        self.store.put(f"{CRED}{statement.subject}/{sid}",
                       {"statement": statement.to_record(), "presentation": presentation})
        return sid

    def send_notice(self, loop_id: str, offer_id: str, side: dict) -> None:
        """Write a sealed notice (`notice.sealed`) about the fill of
        `offer_id` in `loop_id` into this, the claimant's, book (R6)."""
        self._sidecar(NOTICE, loop_id, offer_id, side)

    def send_cure(self, loop_id: str, offer_id: str, side: dict) -> None:
        """Write the giver's sealed answer to a notice into its own book."""
        self._sidecar(CURE, loop_id, offer_id, side)

    def _sidecar(self, prefix: str, loop_id: str, offer_id: str, side: dict) -> None:
        from .notice import fault
        why = fault(side.get("from", "") if isinstance(side, dict) else "", side)
        if why:
            raise ValueError(why)
        self.store.put(f"{prefix}{loop_id}/{offer_id}", side)

    def notice(self, loop_id: str, offer_id: str) -> dict | None:
        key = f"{NOTICE}{loop_id}/{offer_id}"
        return self.store.get(key) if self.store.contains(key) else None

    def cure(self, loop_id: str, offer_id: str) -> dict | None:
        key = f"{CURE}{loop_id}/{offer_id}"
        return self.store.get(key) if self.store.contains(key) else None

    def statements(self, subject: str | None = None) -> Iterator[tuple[Statement, dict | None]]:
        """Every presented (statement, presentation), or those about `subject`."""
        prefix = CRED if subject is None else f"{CRED}{subject}/"
        for _key, rec in self.store.items(prefix):
            yield Statement.from_record(rec["statement"]), rec.get("presentation")

    def mark_filled(self, fills, loop_id: str, loop_record: dict, extra: dict | None = None) -> None:
        """Claim every offer for the loop; a pure function of the decision.

        No wall clock: the same logical clearing must produce
        byte-identical records on every replica ("equal content ⇒ equal
        root"). Timestamps that matter are attributed provenance, and
        trustworthy time is *anchored* time — a feed index or an on-chain
        anchor — which is factbond's to build, never a field smuggled into
        the fill (docs/plans/P1-federated-book.md §3).
        """
        if isinstance(fills, dict):         # v4: {offer_id: fill record}
            for oid, rec in fills.items():
                self.store.put(FILL + oid, rec)
        else:                                # ids alone: the 2026-08 fill
            for oid in fills:
                self.store.put(FILL + oid, {"loop": loop_id})
        for key, rec in sorted((extra or {}).items()):   # holds and exercises, in the same commit (C2)
            self.store.put(key, rec)
        self.store.put(LOOP + loop_id, loop_record)

    def commit(self, *, reconcile: bool = True) -> str:
        """Land staged changes; with reconcile, converge with other writers.

        Every reconciled commit re-checks loop atomicity (U11): a scan of
        `loop/` and `fill/`, the stopgap price of per-key fill resolution.
        """
        try:
            root = self.store.commit(reconcile=reconcile, resolver=or_set_resolver)
        except TypeError:  # store without multi-writer support (plain mock)
            return self.store.commit()
        if reconcile:
            self.verify_loop_atomicity()
        return root

    def verify_loop_atomicity(self) -> None:
        """Raise PartialLoopError unless every loop in the book is whole.

        The U11 invariant, checked rather than resolved: every present
        `loop/` record holds the fill of every leg it names, and every
        `fill/` points at a present loop. Run after every fold (reconciled
        commits do it automatically; aggregators folding with
        `RecordStore.merge` must call it themselves).
        """
        for key, rec in self.store.items(LOOP):
            lid = key[len(LOOP):]
            for leg in rec.get("legs", []):
                for oid in (*leg.get("gives", [leg["give"]]), leg["want"]):
                    claim = (self.store.get(FILL + oid)
                             if self.store.contains(FILL + oid) else None)
                    winner = claim.get("loop") if isinstance(claim, dict) else None
                    if winner != lid and not self.store.contains(f"{FILL}{oid}/{lid}"):
                        raise PartialLoopError(
                            f"loop {lid[:12]} lost offer {oid[:12]} to "
                            f"{winner[:12] if winner else 'nothing'}"
                        )
        partial: dict[str, Fraction] = {}
        for key, rec in self.store.items(FILL):
            lid = rec.get("loop", "") if isinstance(rec, dict) else ""
            if not self.store.contains(LOOP + lid):
                raise PartialLoopError(
                    f"fill on {key[len(FILL):][:12]} points at absent loop"
                )
            oid, _, part = key[len(FILL):].partition("/")
            if part:
                partial[oid] = partial.get(oid, Fraction(0)) + q(rec.get("qty", 0))
                if self.store.contains(FILL + oid):
                    raise PartialLoopError(
                        f"offer {oid[:12]} is filled whole and in part")
        for oid, total in partial.items():
            if self.store.contains(OFFER + oid) and total > q(self.get(oid).thing.qty):
                raise PartialLoopError(
                    f"offer {oid[:12]} oversold: fills take {total} of "
                    f"{q(self.get(oid).thing.qty)}")
        # U11 extended (C2): a hold, and every exercise of it, names a present loop
        for key, _rec in self.store.items(OPTION):
            lid = key[len(OPTION):].partition("/")[2]
            if not self.store.contains(LOOP + lid):
                raise PartialLoopError(f"hold {key[len(OPTION):][:12]} points at absent loop")
        for key, _rec in self.store.items(EXERCISE):
            _oid, _, rest = key[len(EXERCISE):].partition("/")
            opt, _, lid = rest.partition("/")
            if not (self.store.contains(LOOP + opt) and self.store.contains(LOOP + lid)):
                raise PartialLoopError(f"exercise {key[len(EXERCISE):][:12]} points at absent loop")
        for key, _rec in self.store.items(ITEM):
            lid = key.rsplit("/", 1)[-1]
            if not self.store.contains(LOOP + lid):
                raise PartialLoopError(f"item claim {key[len(ITEM):][:12]} points at absent loop")

    # -- reading ---------------------------------------------------------------

    def snapshot(self):
        """(root, frozen registry) — the unit a solver works against."""
        root = self.store.root
        frozen = type(self.store).at(root, self.store.blobs)
        return root, OfferRegistry(frozen)

    def get(self, offer_id: str) -> Offer:
        return Offer.from_record(self.store.get(OFFER + offer_id))

    def is_filled(self, offer_id: str) -> bool:
        """Filled whole, or a give whose remainder is too little for any
        further fill (below its floor or its step: dust, left unfilled)."""
        if self.store.contains(FILL + offer_id):
            return True
        if next(iter(self.store.keys(FILL + offer_id + "/")), None) is None:
            return False                       # no partial fill either
        offer = self.get(offer_id)
        return offer.thing.exhausted(self.available(offer_id))

    def offers(self, *, now: int | None = None,
               include_filled: bool = False) -> Iterator[Offer]:
        """Active offers: fills, tombstones and (given `now`) expiry filtered.

        `include_filled=True` disables all liveness filtering — the
        full-book scan a follower or auditor wants.
        """
        for key, rec in self.store.items(OFFER):
            oid = key[len(OFFER):]
            if not include_filled and (self.is_filled(oid)
                                       or self.is_withdrawn(oid)):
                continue
            offer = Offer.from_record(rec)
            if now is not None and not offer.valid.is_open_at(now):
                continue
            yield offer


# ------------------------------------------------------------------ Swarm wiring

def swarm_offer_book(topic: str, *, signer=None, owner=None, **kw) -> OfferRegistry:
    """A shared offer book on Swarm: BeeBytesStore blobs + signed feed head.

    Exactly recordstore's `swarm_store` — pass `signer` to publish (your
    book / a shared book you hold the key for) or `owner` to follow someone
    else's. Requires `recordstore[bee,feeds]` and a Bee node with a usable
    postage batch (see the swarm extra in pyproject.toml).
    """
    from recordstore import swarm_store

    return OfferRegistry(swarm_store(topic, signer=signer, owner=owner, **kw))
