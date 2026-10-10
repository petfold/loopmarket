"""The federated book: per-maker books folded into one solver-speed view.

The production multi-writer shape (ARCHITECTURE §5 shape 3, ratified
2026-08-21): every book is single-writer at the source — each maker
publishes `offer/`, `sig/` and `withdraw/` keys under their own feed and
signer, clearing publishes `fill/` and `loop/` under its own — and
conflicts exist only at the fold. An **aggregator** folds announced books
with three-way merge under the loop-aware resolver, applies the U8 fold
rules per offer, re-checks every loop a clearing book holds against the
maker books the way clearing checks it (review item 9: anyone may
announce a clearing book, so its fills are not believed on its word),
records its decisions as attributed provenance, and publishes the
**manifest tuple**
`{book_root, provenance_root, announcement_root}`
(docs/plans/P1-federated-book.md §2).

The fold is *pure*: deterministic admission rules plus commutative merge
mean aggregators that saw the same inputs — the catalogue loops are
re-checked under among them — produce byte-identical `book_root`s in any
fold order — divergence between manifests is evidence,
not opinion, and omission is provable against `announcement_root` and the
announcement ground truth (threat register T14). Aggregators charge for
serving, never inclusion; an aggregator that folds selectively is a
censoring aggregator and is caught as one.

Since 2026-09-14 the ground truth has one channel (`announce.py`): the
registry event on chain, latest per owner, readable by anyone. An
aggregator `subscribe`s to it and folds exactly the announced set; a
reader audits any manifest against the same set — a book announced and
never folded is an omission with an absence proof, like a dropped record
— so completeness is a computation one reader runs alone, and comparing
aggregators with each other is no longer how they are trusted. Plurality
stays a deployment property (latency, availability), not a security one.

One assumption rides throughout: all books share one blob space — Swarm's
in deployment, one `MemoryBytesStore` in tests — so a root is enough to
reach any book's bytes. In memory, "feed ownership" is the declared
`owner` of an announced book; on Swarm it becomes the feed's owner
address, which is what makes U8's primary layer real (P1 §1).
"""

from __future__ import annotations

from dataclasses import dataclass

from recordstore import RecordStore

from .registry import (
    CASE, CRED, CURE, EXERCISE, HANDOFF, ITEM, KEY, NOTICE, OPTION,
    FILL, LOOP, OFFER, SIG, WITHDRAW, OfferRegistry, PartialLoopError,
    or_set_resolver,
)
from .schema import Offer, Statement

#: Roles an announced book may carry: makers speak offers, signatures,
#: tombstones and statements about themselves; a clearing instance speaks
#: fills and loops; a register speaks statuses and accreditations in its own
#: separately rooted book, which is announced and never folded (R3a). Every
#: other key class in a book is outside its writer's authority and is refused.
MAKER = "maker"
CLEARING = "clearing"
REGISTER = "register"


@dataclass(frozen=True, slots=True)
class Manifest:
    """What an aggregator publishes: three roots and its name.

    `book_root` is the pure fold (byte-identical across honest aggregators
    with the same inputs); `provenance_root` holds the aggregator's
    attributed speech acts (`origin/`, `reject/`); `announcement_root`
    commits to the exact input set this fold consumed — the completeness
    handle (T14). There is no derived root: the `idx/{c,t,g}` index that
    an `index_root` once named retired 2026-09-12 (Peter: nothing stays
    for a field that names nothing); published cone summaries, if they
    ever come, add a root then (`P1-federated-book.md` §2).
    """

    aggregator: str
    book_root: str
    provenance_root: str
    announcement_root: str


class Aggregator:
    """Folds announced books into one book a solver can read at speed.

    `store_factory` returns a fresh writable RecordStore over the shared
    blob space (in tests: ``lambda: RecordStore(blobs)``; on Swarm, a
    store under the aggregator's own feed). Admission is by reference:
    the aggregator folds the books it was told about and can un-announce
    a flooder — there is no store-side rate limiting to game (P1 §8).
    """

    def __init__(self, store_factory, *, aggregator_id: str = "agg-0", ontology=None,
                 register_at=None, span=None, register_latest=None, resolver_profile=None):
        """`ontology` is the catalogue every clearing book's loops are
        re-checked under (review item 9): without one no loop can be, and
        none is admitted. `register_at`, `span`, `register_latest` and
        `resolver_profile` are the counterparty gate's reads, as
        `BookClearing` takes them, for loops whose legs require credentials
        or accept resolvers by property; without them such a requirement
        fails closed here as it would at clearing (U7)."""
        self._new_store = store_factory
        self.id = aggregator_id
        self._announced: dict[str, tuple[str, object]] = {}
        self.ontology = ontology
        self._gate_reads = dict(register_at=register_at, span=span, register_latest=register_latest,
                                resolver_profile=resolver_profile)

    # -- inputs ----------------------------------------------------------------

    def announce(self, owner: str, store, *, role: str = MAKER) -> None:
        """Register a book: "`owner`'s book is `store`" (one per owner).

        In deployment the announcement is the registry event (`announce.py`)
        naming (owner address, book spec), and `subscribe` resolves the
        channel to these calls; here the store stands in for the resolved
        feed. Re-announcing an owner replaces the entry; un-announcing
        (admission-by-reference's teeth) is `retract`.
        """
        if role not in (MAKER, CLEARING, REGISTER):
            raise ValueError(f"unknown book role: {role!r}")
        self._announced[owner] = (role, store)

    def subscribe(self, announcements, open_book) -> list:
        """Make the announced set exactly the channel's: every standing
        announcement opened with `open_book(spec) -> store` as its owner's
        book, every owner no longer announced retracted. Returns the
        announcements folded. A book the channel names but `open_book`
        cannot reach (an expired feed, a node down) is skipped and recorded
        by the caller's provenance if it wants — it is the maker's
        postage, not the aggregator's omission (P1 §6)."""
        standing = list(announcements.announced())
        for owner in list(self._announced):
            if owner not in {a.owner for a in standing}:
                self.retract(owner)
        folded = []
        for ann in standing:
            try:
                store = open_book(ann.spec())
            except Exception:
                continue
            self.announce(ann.owner, store, role=ann.role)
            folded.append(ann)
        return folded

    def retract(self, owner: str) -> None:
        """Stop folding an owner's book (takes effect at the next fold)."""
        self._announced.pop(owner, None)

    # -- the fold ----------------------------------------------------------------

    def fold(self) -> Manifest:
        """Sanitize every announced book, merge, re-derive, publish.

        Every step is deterministic in the announced (owner, root) set, so
        the whole manifest — not just `book_root` — reproduces across
        aggregators that saw the same inputs.
        """
        provenance = self._new_store()
        announcement = self._new_store()

        staged_roots: list[str] = []
        blobs = None
        store_type = None
        for owner in sorted(self._announced):
            role, store = self._announced[owner]
            root = store.root
            announcement.put(f"announce/{owner}",
                             {"role": role, "root": root or ""})
            if not root or role == REGISTER:
                # a register is separately rooted (R3a): its root is in the
                # announcement set, where a solver finds it to pin, and it
                # never enters the offer book
                continue
            blobs, store_type = store.blobs, type(store)
            source = store_type.at(root, blobs)
            try:
                staged = self._sanitize(owner, role, root, source, provenance)
            except Exception as exc:   # noqa: BLE001 — hostile input fails closed
                # A book the admission rules cannot read is not folded; it
                # used to abort the fold, so one announced book stopped
                # every reader (2026-10-09).
                provenance.put(f"reject/{owner}/*", {
                    "owner": owner,
                    "reason": f"unreadable book ({type(exc).__name__})"})
                continue
            staged_root = staged.commit()
            if staged_root:
                staged_roots.append((role, owner, staged_root))

        def merged(base, staged_root):
            return staged_root if base is None else store_type.merge(
                blobs, None, base, staged_root, resolver=or_set_resolver)

        def merged_all(roots):
            """Merge many staged roots in rounds of pairs, earlier books on
            the left: a merge costs about the size of both sides, so a merge
            tree costs the books' total size times log N, where merging one
            book at a time into the growing union cost N² (400 maker books
            took 10.8 s, 26.9 ms a book and doubling with N). Keeping the
            earlier books on the left gives the root the one-at-a-time fold
            gave: the resolver keeps the first owner's value of a key."""
            roots = list(roots)
            while len(roots) > 1:
                roots = [merged(roots[i], roots[i + 1]) if i + 1 < len(roots)
                         else roots[i] for i in range(0, len(roots), 2)]
            return roots[0] if roots else None

        # The maker books first. Each loop of a clearing book is then
        # re-checked against them the way clearing checks it, and admitted
        # with its fills only if it holds (review item 9): anyone may
        # announce a clearing book, and its fills used to hide offers from
        # every reader on its word alone. What is left of the book is then
        # admitted only if its loops are whole (U11) against the makers
        # alone; one that is not is rejected with its reason, where it used
        # to abort the fold for every reader (an announced "clearing" book
        # with a loop and no fills did, 2026-10-09). Each book is tested on
        # its own, so which other books were announced, and how their owners
        # sort, cannot decide whether it is admitted. Two books that are each
        # whole but claim one offer still fail U11 below, loudly: choosing
        # between them is the loop-granularity resolver's open problem
        # (P1-federated-book.md §3), not a rule for the fold to invent.
        makers_root = merged_all(staged_root for role, _owner, staged_root
                                 in staged_roots if role != CLEARING)
        admitted = []
        for role, owner, staged_root in staged_roots:
            if role != CLEARING:
                continue
            staged_root = self._recheck(owner, staged_root, makers_root, blobs, store_type, provenance)
            if not staged_root:
                continue
            alone = merged(makers_root, staged_root)
            try:
                OfferRegistry(store_type.at(alone, blobs)).verify_loop_atomicity()
            except PartialLoopError as exc:
                provenance.put(f"reject/{owner}/*", {
                    "owner": owner,
                    "reason": f"loops not whole against the makers: {exc}"})
                continue
            admitted.append(staged_root)
        book_root = merged_all([makers_root, *admitted]
                               if makers_root else admitted) or ""

        if book_root:
            folded = OfferRegistry(store_type.at(book_root, blobs))
            folded.verify_loop_atomicity()   # U11, on every fold

        return Manifest(
            aggregator=self.id,
            book_root=book_root,
            provenance_root=provenance.commit() or "",
            announcement_root=announcement.commit() or "",
        )

    # -- admission (the U8 fold rules) -------------------------------------------

    def _recheck(self, owner: str, staged_root: str, makers_root: str | None, blobs, store_type,
                 provenance) -> str:
        """A clearing book's staged speech less every loop that fails the
        re-check, with the loop's fills, holds, exercises and item claims
        (review item 9, decided by Peter 2026-10-10). Each loop is
        re-derived against the maker books folded so far by
        `BookClearing.recheck` — the clearing checklist's own steps, at the
        loop record's time — and its fills and holds must be exactly the
        ones clearing it writes. A failure is an attributed rejection with
        its reason, `reject/<owner>/loop/<loop id>`; a record naming a loop
        the book does not hold is rejected on its own. Returns the root of
        what is left ('' when nothing is)."""
        records = dict(store_type.at(staged_root, blobs).items())
        loops = {key[len(LOOP):]: rec for key, rec in records.items() if key.startswith(LOOP)}
        named = {key: _loops_named(key, rec) for key, rec in records.items() if not key.startswith(LOOP)}
        written: dict[str, dict] = {}       # loop id -> its fills and holds, one pass over the book
        for key, lids in named.items():
            if key.startswith((FILL, OPTION)):
                for lid in lids:
                    written.setdefault(lid, {})[key] = records[key]
        checker = None
        if self.ontology is not None and makers_root:
            from .clearing import BookClearing
            checker = BookClearing(OfferRegistry(store_type.at(makers_root, blobs)), self.ontology,
                                   **self._gate_reads)
        admitted = set()
        for lid in sorted(loops):
            if checker is None:
                reason = ("no catalogue to re-check its loops under" if self.ontology is None
                          else "no maker book is folded: its offers are unknown")
            else:
                try:
                    reason = checker.recheck(loops[lid], written.get(lid, {}), loop_id=lid)
                except Exception as exc:   # noqa: BLE001 — hostile input fails closed
                    reason = f"unreadable loop record ({type(exc).__name__})"
            if reason:
                provenance.put(f"reject/{owner}/loop/{lid}", {"owner": owner, "reason": reason})
            else:
                admitted.add(lid)
        staged = self._new_store()
        for key in sorted(records):
            lids = (key[len(LOOP):],) if key.startswith(LOOP) else named[key]
            if all(lid in admitted for lid in lids):
                staged.put(key, records[key])
            elif not all(lid in loops for lid in lids):
                provenance.put(f"reject/{owner}/{key}",
                               {"owner": owner, "reason": "names a loop this book does not hold"})
        return staged.commit() or ""

    def _sanitize(self, owner: str, role: str, root: str, source,
                  provenance) -> object:
        """One book's admissible speech, copied into a staging store.

        Fail closed in U7's spirit: a record outside its writer's
        authority, an unreadable or mis-keyed offer, a forged maker
        without a valid detached signature — none of it enters the fold,
        and every rejection is an attributed provenance record.
        """
        staged = self._new_store()

        def reject(key: str, reason: str) -> None:
            provenance.put(f"reject/{owner}/{key}",
                           {"owner": owner, "reason": reason})

        offers: dict[str, Offer] = {}
        deferred: list[tuple[str, object]] = []
        records = dict(source.items())
        for key in sorted(records):
            rec = records[key]
            if role == CLEARING and not (key.startswith(FILL) or key.startswith(LOOP) or key.startswith(ITEM)
                                         or key.startswith(OPTION) or key.startswith(EXERCISE)):
                # a clearing book legitimately *contains* the fold it
                # cleared on (it re-based via absorb); only its fills and
                # loops are its own speech — the rest is silently not
                # re-asserted, never "rejected": provenance records are
                # accusations, and carrying your base is not an offense
                continue
            if key.startswith(OFFER):
                if role != MAKER:
                    continue
                oid = key[len(OFFER):]
                try:
                    offer = Offer.from_record(rec)
                except (ValueError, KeyError, TypeError, AttributeError):
                    # AttributeError: a record that is not an object at all;
                    # uncaught, it aborted every reader's fold (2026-10-09)
                    reject(key, "unreadable offer record")
                    continue
                if offer.offer_id != oid:
                    reject(key, "content address mismatch")
                    continue
                if offer.maker != owner:
                    sig = records.get(SIG + oid)
                    if not self._sig_recovers(oid, sig, offer.maker):
                        reject(key, "foreign maker without valid signature")
                        continue
                    staged.put(SIG + oid, sig)
                offers[oid] = offer
                staged.put(key, rec)
                provenance.put(f"origin/{oid}", {"owner": owner, "root": root})
            elif key.startswith(WITHDRAW):
                if role != MAKER:
                    reject(key, "tombstone outside a maker book")
                    continue
                oid = key[len(WITHDRAW):]
                offer = offers.get(oid)   # offer/ sorts before withdraw/
                if offer is None or offer.maker != owner:
                    reject(key, "tombstone for an offer this book cannot close")
                    continue
                staged.put(key, rec)
            elif key.startswith(SIG):
                oid = key[len(SIG):]
                offer = offers.get(oid)   # offer/ sorts before sig/
                if offer is None:
                    reject(key, "signature without an admitted offer")
                elif offer.maker != owner:
                    pass   # verified and staged alongside its foreign offer
                elif self._sig_recovers(oid, rec, owner):
                    staged.put(key, rec)
                # else: an own-maker signature that does not verify here
                # (bad, or no crypto library) is dropped, not folded — feed
                # ownership already authenticates the offer itself.
            elif key.startswith(FILL) or key.startswith(LOOP) or key.startswith(OPTION) \
                    or key.startswith(EXERCISE) or key.startswith(ITEM):
                if role != CLEARING:
                    reject(key, "clearing keys in a maker book")
                    continue
                staged.put(key, rec)
            elif key.startswith(HANDOFF):
                if role != MAKER:
                    reject(key, "handoff outside a maker book")
                    continue
                deferred.append((key, rec))   # handoff/ sorts before offer/
            elif key.startswith(CRED):
                reason = self._cred_fault(owner, role, key, rec)
                if reason:
                    reject(key, reason)
                    continue
                staged.put(key, rec)
            elif key.startswith(CASE):
                # a claim, an answer, a ruling: the writer's sealed speech
                # to one recipient, in its own maker book (case.py)
                from .case import fault as case_fault
                reason = "a case record outside a maker book" if role != MAKER else case_fault(owner, key, rec)
                if reason:
                    reject(key, reason)
                    continue
                staged.put(key, rec)
            elif key.startswith(KEY):
                # a contact card is its owner's speech about its own key, in its
                # own book: the address the key names, the signature its own
                reason = "" if role == MAKER and key[len(KEY):] == owner.lower() else \
                    "a contact card for another key than the book's owner"
                if not reason:
                    try:
                        from .sigs import contact_card_public_key
                        contact_card_public_key(owner, rec)
                    except Exception:            # noqa: BLE001 — unreadable or forged
                        reason = "a contact card that does not recover to the book's owner"
                if reason:
                    reject(key, reason)
                    continue
                staged.put(key, rec)
            elif key.startswith(NOTICE) or key.startswith(CURE):
                # R6: a notice or a cure is its writer's speech between the
                # parties, sealed; admitted in the writer's own maker book
                from .notice import fault
                reason = "notice outside a maker book" if role != MAKER else fault(owner, rec)
                if reason:
                    reject(key, reason)
                    continue
                staged.put(key, rec)
            else:
                reject(key, "unknown keyspace")
        for key, rec in deferred:
            # A sealed handoff is the place-owner's speech about *their own*
            # filled offer (P1-spacetime-terms.md §4): admitted only beside
            # an offer this book's owner made and signed as its sender. The
            # payload is opaque here — aggregators carry it unread; whether
            # the fill exists is the reader's check against the fold.
            loop_id, _, oid = key[len(HANDOFF):].partition("/")
            offer = offers.get(oid)
            if (not loop_id or offer is None or offer.maker != owner
                    or not isinstance(rec, dict) or rec.get("from") != owner):
                reject(key, "handoff for an offer this book does not own")
                continue
            staged.put(key, rec)
        return staged

    @staticmethod
    def _cred_fault(owner: str, role: str, key: str, rec) -> str:
        """Why a `cred/` record is not this book's speech, or "" (R2). A
        statement about a key is its *subject's* presentation
        (counterparty-gate.md §3.2): admitted only in the subject's own
        maker book, under the subject and the statement's own content
        address. Why not `handoff/`'s rule: that one is per offer, and a
        statement about a key has no offer to sit beside. Whether the
        statement is true — its issuer, its path to a root, its status in a
        register — is the gate's to check (R4), not the fold's."""
        if role != MAKER:
            return "statement outside a maker book"
        subject, _, sid = key[len(CRED):].partition("/")
        try:
            statement = Statement.from_record(rec["statement"])
        except (ValueError, KeyError, TypeError, AttributeError):
            # AttributeError: a statement that is not an object at all;
            # uncaught, it rejected the whole book (2026-10-09)
            return "unreadable statement record"
        if statement.statement_id != sid or statement.subject != subject:
            return "content address mismatch"
        if subject != owner:
            return "statement about a key other than the book's owner"
        if rec.get("presentation") is not None and not isinstance(rec["presentation"], dict):
            return "unreadable presentation"
        return ""

    @staticmethod
    def _sig_recovers(offer_id: str, sig, maker: str) -> bool:
        """Fail closed: no signature, no crypto library, no entry."""
        if not isinstance(sig, str):
            return False
        try:
            from .sigs import recover_maker
            return recover_maker(offer_id, sig) == maker
        except Exception:
            return False


def _loops_named(key: str, rec) -> tuple[str, ...]:
    """The loops a clearing record speaks for: a fill's (a part's by its
    key, a whole fill's by its record), a hold's, an item claim's, and
    both of an exercise's (the option's loop and its own)."""
    if key.startswith(FILL):
        _oid, _, lid = key[len(FILL):].partition("/")
        if lid:
            return (lid,)
        loop = rec.get("loop") if isinstance(rec, dict) else None
        return (loop if isinstance(loop, str) else "",)
    if key.startswith(OPTION):
        return (key[len(OPTION):].partition("/")[2],)
    if key.startswith(EXERCISE):
        _oid, _, rest = key[len(EXERCISE):].partition("/")
        option, _, lid = rest.partition("/")
        return (option, lid)
    if key.startswith(ITEM):
        return (key.rsplit("/", 1)[-1],)
    return ("",)


# -- the cross-audit (T14) -----------------------------------------------------

@dataclass(frozen=True, slots=True)
class Omission:
    """One record a manifest claims to have consumed and did not carry.

    `key` sits in `owner`'s book at `announced_root` (the root the
    aggregator's own announcement record names), is absent from
    `book_root`, and has no `reject/` record in `provenance_root`. `proof`
    is recordstore's absence proof for `key` against `book_root`: anyone
    can `verify_proof(proof, book_root)` with no store access, so the
    accusation travels as bytes, not as trust in the auditor.
    """

    owner: str
    key: str
    announced_root: str
    proof: dict | None


def audit_manifest(manifest: Manifest, blobs, *,
                   store_type=RecordStore, expected=()) -> list[Omission]:
    """(announced set) − (speech under `book_root`), as P1 §2 defines it.

    `expected` is the channel's standing announcements (`announce.py`):
    a maker book announced there and absent from the manifest's own
    announcement set is an omitted *book* — the aggregator never folded
    it — reported as an `Omission` of the key `announce/<owner>` with the
    absence proof against `announcement_root`. With the chain as the
    channel this is the whole of T14's completeness check, run by one
    reader with no second aggregator in sight.

    An honest fold is total on the speech it admits: every `offer/` and
    `withdraw/` record in an announced maker book either enters
    `book_root` or earns an attributed `reject/`. Whatever does neither
    was dropped silently — and an aggregator's `announcement_root` is
    its own signed claim about which inputs, at which roots, it folded,
    so the audit needs nothing but the manifest and the blob space.
    Omission (including pay-to-be-indexed, and the nastier form: a
    dropped tombstone resurrecting a withdrawn offer) becomes a proof,
    never a suspicion — the T14 defence, computable by any reader.

    Not audited: `sig/` (an own-maker signature that fails to verify is
    dropped without a rejection by design — feed ownership already
    authenticates the offer) and clearing books (every fold re-checks
    their loops, and U11 checks what it admits).
    """
    announced = store_type.at(manifest.announcement_root, blobs) \
        if manifest.announcement_root else None
    if announced is None:
        return []
    provenance = store_type.at(manifest.provenance_root, blobs) \
        if manifest.provenance_root else None
    book = store_type.at(manifest.book_root, blobs) \
        if manifest.book_root else None

    def in_store(store, key: str) -> bool:
        if store is None:
            return False
        try:
            store.get(key)
        except KeyError:
            return False
        return True

    omissions: list[Omission] = []
    for ann in sorted(expected, key=lambda a: a.owner):
        if ann.role == MAKER and not in_store(announced, f"announce/{ann.owner}"):
            omissions.append(Omission(ann.owner, f"announce/{ann.owner}", "",
                                      announced.prove(f"announce/{ann.owner}")))
    for ann_key in sorted(announced.keys("announce/")):
        rec = announced.get(ann_key)
        owner = ann_key[len("announce/"):]
        if rec.get("role") != MAKER or not rec.get("root"):
            continue
        source = store_type.at(rec["root"], blobs)
        for prefix in (OFFER, WITHDRAW):
            for key in sorted(source.keys(prefix)):
                if in_store(book, key):
                    continue
                if in_store(provenance, f"reject/{owner}/{key}"):
                    continue
                proof = book.prove(key) if book is not None else None
                omissions.append(Omission(owner, key, rec["root"], proof))
    return omissions
