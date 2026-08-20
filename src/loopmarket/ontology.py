"""The shared catalogue: an OntoDAG with pinned, content-addressed versions.

Matching needs one primitive from the ontology: *does this offered thing
satisfy that wanted description?* Both sides are conjunctions of category
names; the offered thing satisfies the want iff every wanted category is
covered by some offered concept — equal to it, or an ancestor of it in the
DAG (the offered concept fits within the wanted one).

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

from typing import Iterable

from ontodag import OntoDAG

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

    # -- querying ---------------------------------------------------------------

    def known(self, concept: str) -> bool:
        return concept in self.dag.nodes

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
        """Every wanted category is covered by some offered concept.

        Strict on vocabulary: an unknown category on either side never
        matches — silent vocabulary drift must fail closed, not open.
        """
        offered = list(offered)
        return all(any(self.covers(w, o) for o in offered) for w in wanted)

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

        `ask(..., **ontology.pins)` fills {ontology_root, registry_version,
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
