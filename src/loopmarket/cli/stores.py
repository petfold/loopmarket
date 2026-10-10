"""The session: the book, the catalogue, the personal names layer, the
clock and the identity a command works with.

`Session` opens everything lazily (odag's rule: `help` and `set` must work
with the node down). `_open_book` is the one place a book spec becomes a
book; a test replaces it here (`cli.stores._open_book`), and the other
modules call it through this module."""

from __future__ import annotations

import os
import time as _time

from ontodag import OntoDAG

from ..ontology import Ontology
from ..registry import OfferRegistry
from .settings import _OVERRIDES, _book_spec, _configured, _err, _peer_specs
from .spellings import _INTERPRETED_HEADS, parse_now


def _open_catalogue(spec: str | None):
    """An odag `Session` for a store spec (`.od` file, `rs:PATH`,
    `swarm:NAME`); `None` opens odag's active store.

    Private use of ontodag's CLI, isolated here on purpose (cli.md §11.3;
    `Session._open` also normalizes a spec through it): opening a catalogue
    from an odag store spec
    should be a public ontodag call, and this function is deleted the day it
    is. Copying `_load_native` and the backends would drift; importing them
    keeps the two tools on one store layout. Bee settings loopmarket got as
    flags are pushed into odag's flag layer so the same node is used."""
    from ontodag import __main__ as odag

    for key in ("bee_api", "bee_batch", "bee_signer"):
        if _OVERRIDES.get(key):
            odag._OVERRIDES[key] = _OVERRIDES[key]
    if spec is None:
        return odag.Session(odag._resolve_store())
    return odag.Session(odag._normalize_spec(spec))


def _open_book(spec: str) -> OfferRegistry:
    """`rs:PATH` (odag's on-disk layout: blobs/ + root) or `swarm:TOPIC`
    (mine, signed with bee_signer) / `swarm:TOPIC@OWNER` (someone else's,
    read-only). Swarm imports stay inside this path (boundary B2)."""
    if spec.startswith("rs:"):
        from recordstore import DirBytesStore, FilePointer, RecordStore

        path = os.path.abspath(os.path.expanduser(spec[3:]))
        os.makedirs(path, exist_ok=True)
        return OfferRegistry(RecordStore(
            DirBytesStore(os.path.join(path, "blobs")),
            pointer=FilePointer(os.path.join(path, "root"))))
    if spec.startswith("swarm:"):
        from ..registry import swarm_offer_book

        topic, _, owner = spec[6:].partition("@")
        kw = dict(api_url=_configured("bee_api"))
        if _configured("bee_batch"):
            kw["stamp"] = _configured("bee_batch")
        if owner:
            return swarm_offer_book(topic, owner=owner, **kw)
        signer = _configured("bee_signer")
        if not signer:
            raise ValueError(
                f"{spec}: a swarm: book needs bee_signer to publish, or "
                f"swarm:TOPIC@OWNER to follow someone else's")
        return swarm_offer_book(topic, signer=signer, **kw)
    raise ValueError(f"{spec}: a book is rs:PATH or swarm:TOPIC[@OWNER]")


def _addressing_of(registry: OfferRegistry) -> str:
    """The scheme the book's roots are in — `sha256` for a directory or
    memory store, `swarm` for a book on Swarm or a Swarm-addressed mirror.
    recordstore names it privately for proof envelopes; the same answer is
    what a fold must be built under (a public accessor is asked upstream)."""
    try:
        from recordstore.recordstore import _addressing_name
        return _addressing_name(registry.store.blobs)
    except Exception:                       # noqa: BLE001 — an unknown store: sha256, the default
        return "sha256"


def _fold_blobs(book: OfferRegistry):
    """The bytes store a fold is computed in: the *book's* addressing, so the
    fold's root is the root the book has once it absorbs the fold — equal
    content, equal reference — and a proposal solved on the fold pins a
    root the clearing book and the chain resolve. A memory store is sha256
    only, so a Swarm-addressed book folds in a scratch directory under
    Swarm addressing (found live 2026-09-18: a sealed proposal pinning the
    memory fold's sha256 root was "solved against another root" beside the
    Swarm clearing book's BMT root of the same content)."""
    from recordstore import DirBytesStore, MemoryBytesStore
    if _addressing_of(book) == "swarm":
        import tempfile
        return DirBytesStore(tempfile.mkdtemp(prefix="loop-fold-"), addressing="swarm")
    return MemoryBytesStore()


class Session:
    """Everything a command may need, opened lazily (odag's rule: `help`
    and `set` must work with the node down)."""

    def __init__(self):
        self._book = None
        self._personal = None
        self._catalogue = None
        #: (owner, key, reason) for everything the last fold rejected
        self.rejections: list[tuple[str, str, str]] = []

    # -- the book ---------------------------------------------------------------

    @property
    def book(self) -> OfferRegistry:
        if self._book is None:
            self._book = _open_book(_book_spec())
        return self._book

    def fold(self) -> OfferRegistry:
        """My book plus every announced book plus every peer, as one
        read-only registry — the read path (P1 §2, T14).

        The announced books come from the `registry` channel with their
        owners, so they fold through `Aggregator` under the U8 admission
        rules: each book is read as *its announced owner's*, and speech the
        owner may not make is refused with an attributed rejection. This
        is the solver-self-fold: no aggregator's manifest is trusted, the
        fold is recomputed from the announced set and the makers' own
        books. Every loop of an announced clearing book is re-checked
        against the maker books under this session's catalogue and gate,
        as clearing checks it, and admitted only if it holds (review item
        9); what the fold rejected, and why, is kept in `rejections`
        (`loop fold` prints it). `peers` are books you trust by spec,
        without an owner: a plain OR-set union (`absorb`) — the shared
        dev/demo shape. Then the U11 check.

        Where a clearing contract is set (`beat`), the registry returned
        counts an offer filled only by what its finalized beats recorded
        (`OfferRegistry(chain_fills=...)`, review item 9): book fills hide
        nothing there."""
        specs, registry = _peer_specs(), _configured("registry")
        self.rejections = []
        if not specs and not registry:
            return self._read_by_chain(self.book)
        from recordstore import MemoryBytesStore, RecordStore

        folded = OfferRegistry(RecordStore(_fold_blobs(self.book)))
        folded.absorb(self.book)
        if registry:
            from ..federation import CLEARING, Aggregator
            blobs = MemoryBytesStore()
            announced = list(self.announcements.announced())
            # the catalogue is opened only when there are loops to re-check
            clearing = any(ann.role == CLEARING for ann in announced)
            agg = Aggregator(lambda: RecordStore(blobs), aggregator_id="loop-cli",
                             ontology=self.catalogue if clearing else None,
                             **(self._gate_reads() if clearing else {}))
            for ann in announced:
                try:
                    peer = _open_book(ann.spec())
                except Exception as exc:                # the maker's postage, not our omission
                    print(f"loop: {ann.owner}: {exc}", file=_err())
                    continue
                if ann.spec() == _book_spec() or ann.spec() == \
                        f"{_book_spec()}@{ann.owner}":
                    continue                            # my own book is already in
                staged = OfferRegistry(RecordStore(blobs))
                staged.absorb(peer)
                staged.commit()
                agg.announce(ann.owner, staged.store, role=ann.role)
            manifest = agg.fold()
            if manifest.book_root:
                folded.absorb(OfferRegistry(RecordStore.at(manifest.book_root, blobs)))
            if manifest.provenance_root:
                self.rejections = [(rec.get("owner", ""), key[len("reject/"):].partition("/")[2],
                                    rec.get("reason", ""))
                                   for key, rec in RecordStore.at(manifest.provenance_root, blobs).items("reject/")]
        for spec in specs:
            folded.absorb(_open_book(spec))
        folded.commit()
        folded.verify_loop_atomicity()
        return self._read_by_chain(folded)

    def _read_by_chain(self, registry: OfferRegistry) -> OfferRegistry:
        """`registry` read with the clearing contract's fills as the fill
        authority when one is set (review item 9), else as it is. A view to
        read: writes go to `book`, whose clearing must keep refusing what
        it has filled itself."""
        from . import clients
        fills = clients._chain_fills(self)
        return registry if fills is None else OfferRegistry(registry.store, chain_fills=fills)

    def _gate_reads(self) -> dict:
        """The counterparty gate's reads for the fold's re-check, as a
        clearing takes them (`clients._clearing_reads`), each opened only
        when a loop asks for it: most folds re-check no credential."""
        from . import clients
        from .spellings import _calendar_span
        return {"register_at": lambda rid, root: clients._register_at(self)(rid, root),
                "register_latest": lambda rid: clients._registers(self).get(rid),
                "resolver_profile": clients._resolver_profiles(self), "span": _calendar_span}

    @property
    def announcements(self):
        """The announcement channel named by `registry` (announce.py)."""
        from ..announce import open_announcements
        spec = _configured("registry")
        if not spec:
            raise ValueError(
                "no registry: `loop set registry chain:RPC_URL@CONTRACT` (or "
                "file:PATH for sessions on one machine)")
        return open_announcements(spec, key=_configured("bee_signer") or None)

    # -- the catalogue and the names layer ---------------------------------------

    def _open(self) -> None:
        self._personal = _open_catalogue(None)
        spec = _configured("catalogue")
        if spec:
            from ontodag import __main__ as odag
            if odag._normalize_spec(spec) != self._personal.spec:
                self._catalogue = _open_catalogue(spec)
                return
        self._catalogue = self._personal

    @property
    def catalogue_session(self):
        if self._catalogue is None:
            self._open()
        return self._catalogue

    @property
    def personal_session(self):
        if self._personal is None:
            self._open()
        return self._personal

    @property
    def catalogue(self) -> Ontology:
        """The pinned ground offers match under (the primary store, never
        the composed view: matching must see exactly what the root names)."""
        ontology = Ontology(self.catalogue_session.dag)
        self._check_heads(ontology.dag)
        return ontology

    def view(self) -> OntoDAG:
        """The resolution view: catalogue + personal layer + odag overlays.
        Read-only, in memory; nothing ever writes the union."""
        if self.catalogue_session is self.personal_session:
            return self.personal_session.view()
        composed = OntoDAG()
        composed.merge(self.catalogue_session.dag)
        composed.merge(self.personal_session.view())
        return composed

    @staticmethod
    def _check_heads(dag: OntoDAG) -> None:
        """Gate G5's tripwire: the head this CLI interprets onto a field
        (`valid`) must not be a dimension head the loaded catalogue
        declares — it would silently be shadowed."""
        if "dimension" not in dag.nodes:
            return
        for head in _INTERPRETED_HEADS:
            if head in dag.nodes and dag.is_below(head, "dimension"):
                raise ValueError(
                    f"the catalogue declares `{head}` as a dimension, but "
                    f"`loop` interprets {head}(...) onto the offer's validity "
                    f"field (docs/plans/P1-spacetime-terms.md §2); refusing "
                    f"rather than shadowing it")

    # -- clock and identity --------------------------------------------------------

    @property
    def now(self) -> int:
        value = _configured("now")
        return parse_now(value) if value else int(_time.time())

    @property
    def maker(self) -> str:
        maker = _configured("maker")
        if maker:
            return maker
        signer = _configured("bee_signer")
        if signer:
            try:
                from ..sigs import maker_address
                return maker_address(signer)
            except Exception:  # noqa: BLE001 — the sig extra is optional
                pass
        raise ValueError(
            "no maker identity: `loop set maker NAME` (or set bee_signer with "
            "the sig extra installed, and the key's address is your name)")


def _resolve_id(session: Session, prefix: str, *, mine_only: bool) -> str:
    """The whole id of the one offer `prefix` names: one of mine in my book
    (`mine_only`), else any in the fold."""
    book = session.book if mine_only else session.fold()
    matches = sorted({o.offer_id for o in book.offers(include_filled=True)
                      if o.offer_id.startswith(prefix)
                      and (not mine_only or o.maker == session.maker)})
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"{prefix}: no such offer"
                         + (" of yours" if mine_only else ""))
    raise ValueError(f"{prefix}: ambiguous — "
                     + ", ".join(m[:16] for m in matches))
