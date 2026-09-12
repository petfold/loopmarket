"""The shared catalogue: an OntoDAG with pinned, content-addressed versions.

Matching needs one primitive from the ontology: *does this offered thing
satisfy that wanted description?* Both sides are conjunctions of category
names; the offered thing satisfies the want iff every wanted category is
covered by some offered concept — equal to it, or an ancestor of it in the
DAG (the offered concept fits within the wanted one).

Since 2026-09-12 a conjunction also carries where and when a thing changes
hands — `where(u2e4x)`, `when(2026-10-05T19:00:00Z..)`, a route's
`from(...)`/`to(...)` — as terms of heads the catalogue declares under its
`geo` and `time` dimensions (roles of a dimension, ontodag #15: a role's
parameter may be a value or a node filed in the dimension — a place under
a cell, a region above cells, a floor under a building). They match
exactly like every other term, by **containment**: the want is the wider
cone, the give the narrower (Peter, 2026-09-12 — the toothbrush wanted
within five metres of the reception desk within thirty minutes is a
narrow want, and the give that fits within it is what matches). A head the
want does not name constrains nothing; a head the give does not name puts
it in no cone of that head. There is no second relation: an overlap rule
for "service roles" under a marker node was built on 2026-09-12 and
withdrawn the same night, with ontodag's overlap query mode
(`docs/plans/P1-spacetime-terms.md` §3, superseded). Ontodag is
intersection; so is matching.

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
    #: while they matched by overlap under a marker node; they match by
    #: containment like everything else now, and the marker is gone.
    declare_service_roles = declare_roles

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

        One relation, containment, for every term: each wanted term is
        covered by some offered concept — the offered thing is at least as
        specific as asked. A Corinthian amphora for "Greek amphora";
        `made_in(u2e4x)` for `made_in(u2e)`; a give `where(my_home)` for a
        want `where(u2e4)` (the place is under the cell); a give
        `when(19:00..19:15)` for a want `when(18:00..20:00)`. A head the
        want does not name constrains nothing. A head the give does not
        name is a head it fits within no term of: a give that says nothing
        about where it hands over does not satisfy a want that says where.
        Strict on vocabulary (U7): a wanted category nobody knows never
        matches; an extra unknown category on the offered side only
        narrows the offer and is ignored.

        This is exactly ontodag's `get(wanted)` membership test for the
        give, term by term — `DimensionIndex.candidates` asks that one
        query and this is its pairwise face (Peter, 2026-09-12: ontodag is
        intersection; a want is the wider cone, a give the narrower).
        """
        offered = list(offered)
        if not self._consistent(offered):
            return False
        return all(any(self.covers(w, o) for o in offered) for w in wanted)

    def _consistent(self, concepts) -> bool:
        """Can the conjunction be held at all? Two same-head parametric
        terms with a provably empty meet (`from(u2e4)` and `from(u2e5)`)
        describe nothing — ontodag refuses to file such an item, so the
        index never holds it, and the exact check agrees by matching it
        against nothing (recall-exactness both ways)."""
        by_head: dict[str, list[str]] = {}
        for c in concepts:
            split = _dims.split_term(c)
            if split is not None and self.head_kind(split[0]) is not None:
                by_head.setdefault(split[0], []).append(c)
        for terms in by_head.values():
            for i, a in enumerate(terms):
                for b in terms[i + 1:]:
                    try:
                        if self.dag.meet(a, b) is None:
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
