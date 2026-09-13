"""The shared catalogue: an OntoDAG with pinned, content-addressed versions.

Matching needs one primitive from the ontology: *does this offered thing
satisfy that wanted description?* Both sides are conjunctions of category
names; the offered thing satisfies the want iff every wanted category is
covered by some offered concept — equal to it, or an ancestor of it in the
DAG (the offered concept fits within the wanted one).

Since 2026-09-12 a conjunction also carries where and when a thing changes
hands, as **bare terms of the geo and time dimensions**: a cell
(`geo(u2e4x)`), a place node under a cell (`my_shop`), a region above cells
(`barcelona`), a window (`time(2026-10-05T19:00:00Z..)`), a named time. No
head: "at this place" is what a geo term in a conjunction already means
(Peter, 2026-09-13 — the `where`/`when` heads of the day before were
unnecessary and are gone). A head is kept only where something has two
coordinates of one kind — a route's `from(...)`/`to(...)`, a transport's
`depart`/`arrive` — or where a geo/time term *describes* the thing rather
than saying where it changes hands (`made_in(corinth)`, `made(1850)`).

Two relations, and the catalogue says which applies (the marker node
`handover`, the one name this module knows besides the dimensions'):

- **containment, give within want**, for categories and descriptive
  terms — the offered thing is at least as specific as asked (a Corinthian
  amphora for "Greek amphora", `made_in(u2e4x)` for `made_in(u2e)`), never
  the reverse (a thing made somewhere in Greece is not known to be
  Corinthian);
- **one contains the other**, for handover coordinates — a seller who
  delivers anywhere in Barcelona (`barcelona`) serves a want at a door
  inside it (`my_door`), and a seller at a fixed shop (`my_shop`) serves a
  buyer who will collect anywhere in the city; whichever side is the
  flexible one. Partial overlap (a box straddling the edge of the
  courier's area) is not a match: one set contains the other, or nothing.
  Which dimensions are handover coordinates is seed vocabulary: `geo` and
  `time` hang under the marker `handover` (`declare_handover`), every role
  under them inherits it (`from`/`to`, `depart`/`arrive`), a descriptive
  head opts out under `descriptive` (`declare_descriptive`), and a bare
  node in a marked dimension — a place, a region, a named time — is a
  coordinate of that dimension.

A head the want does not name constrains nothing; a coordinate the give
does not state puts it in no cone of that head (an internet service has no
place, and does not serve a want at a door). Ontodag is intersection; both
relations are `is_below`, and the seed decides the direction.

Offers pin the catalogue version they were written against
(`Offer.ontology_root`): persistence through `EagerOntoDAG` over a
`RecordStore` gives every committed catalogue state a canonical root
reference, so "the semantic ground cannot move under a committed loop" is a
string comparison. `Ontology.root` exposes it.

Bonded catalogue assertions (staking money on "X fits within Y") are roadmap
P3 — the `assert_edge` signature carries the bond argument already so call
sites don't churn.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from ontodag import OntoDAG
from ontodag import dimensions as _dims

try:  # persistence is optional: the core must work in memory (boundary B1)
    from ontodag import EagerOntoDAG
except Exception:  # pragma: no cover
    EagerOntoDAG = None  # type: ignore[assignment]


#: Two marker nodes, the only names this module knows besides the
#: dimensions'. `handover`: the base heads under it (`geo`, `time`) are the
#: dimensions whose terms say where or when the thing changes hands and
#: match when one side contains the other — a bare cell, place or window,
#: and every role head under them (`from`/`to`, `depart`/`arrive`), since a
#: head under a head inherits the marker by transitive reduction anyway.
#: `descriptive`: a geo or time head whose terms describe the thing instead
#: (`made_in(corinth)`, `made(1850)`) opts out here and matches by
#: containment like a category.
HANDOVER = "handover"
DESCRIPTIVE = "descriptive"


class Ontology:
    """A thin, matching-oriented facade over an OntoDAG."""

    def __init__(self, dag: OntoDAG | None = None):
        self.dag = dag if dag is not None else OntoDAG()

    # -- building -------------------------------------------------------------

    def assert_edge(self, sub: str, supers: Iterable[str], *, bond: float = 0.0) -> None:
        """Assert `sub` fits within every category in `supers`.

        Missing supercategories are created under the root first, so
        ontologies can be declared top-down in one pass. `bond` is recorded
        intent (P3): assertions will carry stakes scaled to their centrality.
        """
        del bond  # carried for API stability; not yet enforced (roadmap P3)
        for s in supers:
            if s not in self.dag.nodes:
                self.dag.put(s, [])
        self.dag.put(sub, list(supers))

    def load(self, edges: dict[str, list[str]]) -> "Ontology":
        """Bulk declaration: {sub: [supers...]}, order-independent."""
        pending = dict(edges)
        while pending:
            progressed = False
            for sub, supers in list(pending.items()):
                if all(s in self.dag.nodes or s in edges for s in supers):
                    for s in supers:
                        if s not in self.dag.nodes:
                            self.dag.put(s, [])
                    self.dag.put(sub, supers)
                    del pending[sub]
                    progressed = True
            if not progressed:  # pragma: no cover - malformed input guard
                raise ValueError(f"unresolvable supercategories in {sorted(pending)}")
        return self

    def declare_roles(self, roles: Mapping[str, str]) -> None:
        """Declare role heads of a dimension: {head: base}.

        Each `head` is put under its base dimension head, inheriting the
        value grammar and the kind ontodag orders it by — the one edge
        `odag put from geo` writes. A role's parameter may then name the
        base dimension's nodes (`from(my_home)`, ontodag #15). This is a
        convenience for seeds and tests and deliberately has no default:
        the core names no heads. When a base is a prelude head the
        catalogue has not adopted, ontodag's prelude is merged in —
        idempotent and canonical, the step `odag prelude` performs.
        Declaring this vocabulary is a catalogue write: on a persistent
        catalogue it moves the root, so it belongs with the other seed
        declarations, before offers pin the root.
        """
        if any(base not in self.dag.nodes for base in roles.values()):
            from ontodag.prelude import apply as apply_prelude
            apply_prelude(self.dag)
        for head, base in roles.items():
            if self._kind_of(base) is None:
                raise ValueError(
                    f"{base!r} is not a dimension head or kind: a role "
                    f"needs a value space to be ordered in")
        for head, base in roles.items():
            self.dag.put(head, [base])

    #: The 2026-09-12 name, kept one release: roles were "service roles"
    #: while they matched by overlap under a marker node.
    declare_service_roles = declare_roles

    def declare_handover(self, heads: Iterable[str]) -> None:
        """Mark base dimension heads as handover coordinates: their terms —
        and the terms of every role under them — say where or when the
        thing changes hands and match when one side contains the other
        (module docstring). Seed vocabulary, no default: the core names no
        head. One edge each, `handover → geo`; a role `from` under `geo`
        needs no edge of its own (it would be redundant and reduced away).
        Prelude heads are adopted on demand. A catalogue write, before
        offers pin the root."""
        self._mark(HANDOVER, heads)

    def declare_descriptive(self, heads: Iterable[str]) -> None:
        """Opt a geo or time head out of the handover reading: its terms
        describe the thing (`made_in(corinth)`, `made(1850)`) and match by
        containment like a category — the offered thing at least as
        specific as asked, never the reverse."""
        self._mark(DESCRIPTIVE, heads)

    def _mark(self, marker: str, heads: Iterable[str]) -> None:
        heads = list(heads)
        if any(head not in self.dag.nodes for head in heads):
            from ontodag.prelude import apply as apply_prelude
            apply_prelude(self.dag)             # `geo`/`time` are prelude heads
        if marker not in self.dag.nodes:
            self.dag.put(marker, [])
        node = self.dag.nodes[marker]
        for head in heads:
            if self.head_kind(head) is None:
                raise ValueError(
                    f"{head!r} is not a dimension head: a {marker} "
                    f"declaration needs a value space to be ordered in")
            if not self.dag.is_below(head, marker):
                self.dag.add_edge(node, self.dag.nodes[head])

    def handover_heads(self) -> set[str]:
        """The base heads directly under the `handover` marker."""
        if HANDOVER not in self.dag.nodes:
            return set()
        return {n.name for n in self.dag.nodes[HANDOVER].neighbors}

    def handover_class(self, concept: str) -> str | None:
        """The head whose handover coordinate `concept` states, or None
        when `concept` is a category or a descriptive term. A term
        `head(param)` states a coordinate iff its head is under `handover`
        (a marked base head, or a role under one) and not under
        `descriptive`; a bare node — a place under a cell, a region above
        cells, a named time — states the coordinate of the marked base head
        it is filed in."""
        marked = self.handover_heads()
        if not marked:
            return None
        split = _dims.split_term(concept)
        if split is not None:
            head = split[0]
            if head not in self.dag.nodes or self.head_kind(head) is None:
                return None
            if not self.dag.is_below(head, HANDOVER):
                return None
            if DESCRIPTIVE in self.dag.nodes and self.dag.is_below(head, DESCRIPTIVE):
                return None
            return head
        if concept not in self.dag.nodes or concept in marked:
            return None
        for head in sorted(marked):
            if self.dag.is_below(concept, head):
                return head
        return None

    # -- querying ---------------------------------------------------------------

    def known(self, concept: str) -> bool:
        """Is `concept` vocabulary of this catalogue?

        A node is. So is a *parametric term of a declared dimension head*
        — `from(u2e4x)`, `weight(..11kg)` — although no such node exists:
        the head is pinned by the catalogue root, the value grammar by the
        registry version, and ontodag orders these terms by computation
        (prefix containment, interval arithmetic). Asking the DAG to order
        the term against itself is the public test that it can interpret
        it: an undeclared head answers False, a malformed value raises —
        both fail closed (U7). Entered 2026-09-12 so role terms in offers
        (`from(...)`, `to(...)`) match the way ontodag's own worked example
        does; `docs/plans/ontodag-coupling.md` §2 anticipated the step.
        """
        if concept in self.dag.nodes:
            return True
        if "(" not in concept:
            return False
        try:
            return bool(self.dag.is_below(concept, concept))
        except ValueError:
            return False

    def head_kind(self, head: str) -> str | None:
        """The registry kind a declared dimension head orders its values by
        (`linear-dimension`, `prefix-dimension`, ...), else None. Kind
        nodes themselves and plain categories are not heads."""
        if head in _dims.KINDS or head not in self.dag.nodes:
            return None
        return self._kind_of(head)

    def _kind_of(self, name: str) -> str | None:
        """`name`'s kind: itself if it is a kind node, else the kind it
        inherits. Used where a role's *base* may be either."""
        if name in _dims.KINDS:
            return name if name in self.dag.nodes else None
        if name not in self.dag.nodes:
            return None
        for kind in sorted(_dims.KINDS):
            if kind in self.dag.nodes and self.dag.is_below(name, kind):
                return kind
        return None

    def covers(self, wanted: str, offered: str) -> bool:
        """True iff `offered` fits within `wanted` (equal, or a descendant).

        Vocabulary strictness stays explicit here (invariant U7: unknown
        never matches), then ontodag's `is_below` (>= 0.7.0) answers the
        subsumption: an upward walk from `offered` with early exit,
        bounded by its shallow ancestor cone — never by enumerating
        `wanted`'s descendant cone, which for a broad category is most of
        the catalogue (and, on a lazy catalogue, most of the fetches).
        """
        if not self.known(wanted) or not self.known(offered):
            return False
        return self.dag.is_below(offered, wanted)

    def satisfies(self, offered: Iterable[str], wanted: Iterable[str]) -> bool:
        """Does the offered conjunction satisfy the wanted one?

        Every wanted term must be answered by an offered one. A category or
        descriptive term is answered by an offered concept that fits within
        it (the offered thing is at least as specific as asked). A handover
        coordinate — a bare geo or time term, or a term of a head marked
        under `handover` — is answered by an offered coordinate *of the
        same head* that fits within it or contains it: the seller who
        delivers anywhere in the city serves the want at the door, and the
        seller at the shop serves the buyer who collects anywhere in the
        city. A head the want does not name constrains nothing; a
        coordinate the give does not state answers nothing.

        Strict on vocabulary (U7): a wanted category nobody knows never
        matches; an extra unknown category on the offered side only
        narrows the offer and is ignored; a give whose same-head terms are
        provably disjoint describes nothing and satisfies nothing.

        Both relations are ontodag's `is_below`; the seed decides the
        direction by marking the handover heads (Peter, 2026-09-12/13:
        ontodag is intersection; a want is the wider cone for what a thing
        is, and either side may be the wider one for where and when it
        changes hands).
        """
        offered, wanted = list(offered), list(wanted)
        if not self._consistent(offered) or not self._consistent(wanted):
            return False                # a conjunction that describes nothing
        classes = {o: self.handover_class(o) for o in offered}
        for w in wanted:
            wc = self.handover_class(w)
            if wc is None:
                if not any(self.covers(w, o) for o in offered):
                    return False
                continue
            same = [o for o in offered if classes[o] == wc]
            if not any(self.covers(w, o) or self.covers(o, w) for o in same):
                return False
        return True

    def _consistent(self, concepts) -> bool:
        """Can the conjunction be held at all? Two coordinates of one head
        that provably share no point — `from(u2e4)` and `from(u2e5)`, a
        place under `u2e4x` and the cell `u2f` — describe nothing: ontodag
        refuses to file such an item, so the index never holds it, and the
        exact check agrees by matching it against nothing (recall-exactness
        both ways). Same-head descriptive terms likewise. Decided by
        ontodag's pairwise `overlaps` (terms or nodes either side); a pair
        it cannot compare fails closed."""
        by_class: dict[str, list[str]] = {}
        for c in concepts:
            cls = self.handover_class(c)
            if cls is None:
                split = _dims.split_term(c)
                if split is None or self.head_kind(split[0]) is None \
                        or not self.known(c):
                    continue
                cls = split[0]
            by_class.setdefault(cls, []).append(c)
        for terms in by_class.values():
            for i, a in enumerate(terms):
                for b in terms[i + 1:]:
                    try:
                        if not self.dag.overlaps(a, b):
                            return False
                    except ValueError:
                        return False
        return True

    # -- persistence -----------------------------------------------------------

    @property
    def root(self) -> str:
        """Canonical root of the last committed catalogue state ('' if none).

        The store rides on the DAG as `.store` (EagerOntoDAG); `.record_store`
        is kept as a fallback for older spellings. Not `dag.root` — that is
        the DAG's top *Item*, not a version reference.
        """
        store = getattr(self.dag, "store", None) \
            or getattr(self.dag, "record_store", None)
        return getattr(store, "root", "") or ""

    @property
    def pins(self) -> dict[str, str]:
        """Constructor kwargs pinning this catalogue as an offer's ground.

        `give(..., **ontology.pins)` fills {ontology_root, registry_version,
        contract_version} in one move (planned invariant U10). The root
        alone under-specifies the pinned semantics — ontodag's dimension
        registry participates in canonical reduction, and the contract
        version names the guarantee set the writer assumed — so all three
        travel together (docs/plans/proof-fabric.md §3).
        """
        from ontodag import CONTRACT_VERSION
        from ontodag.dimensions import REGISTRY_VERSION

        return {
            "ontology_root": self.root,
            "registry_version": REGISTRY_VERSION,
            "contract_version": CONTRACT_VERSION,
        }

    @classmethod
    def persistent(cls, record_store) -> "Ontology":
        """An Ontology whose DAG persists through a RecordStore.

        `record_store` is duck-typed (anything with the RecordStore surface);
        pass one made by `recordstore.swarm_store(topic, ...)` for a shared,
        Swarm-published catalogue, or over `MemoryBytesStore` for tests.
        """
        if EagerOntoDAG is None:  # pragma: no cover
            raise RuntimeError("ontodag.EagerOntoDAG unavailable")
        return cls(EagerOntoDAG(record_store))

    def commit(self) -> str:
        """Commit the catalogue, returning its canonical root reference."""
        commit = getattr(self.dag, "commit", None)
        if commit is None:
            raise TypeError("this Ontology is in-memory; build it via .persistent()")
        return commit()
