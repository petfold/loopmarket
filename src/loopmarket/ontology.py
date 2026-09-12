"""The shared catalogue: an OntoDAG with pinned, content-addressed versions.

Matching needs one primitive from the ontology: *does this offered thing
satisfy that wanted description?* Both sides are conjunctions of category
names; the offered thing satisfies the want iff every wanted category is
covered by some offered concept — equal to it, or an ancestor of it in the
DAG (the offered concept fits within the wanted one).

Since 2026-09-12 a conjunction may also carry *service-role* terms —
heads that hang under the marker node `service-role`, such as a route's
`from(...)`/`to(...)` or a transport's `depart(...)`/`arrive(...)`. They
describe where and when the handover happens rather than what the thing
is, and they match by **overlap** (a delivery instant, a handover point
exists) instead of containment. The relation is a property of the head,
declared in the catalogue and so pinned by its root, never of the
dimension: `made_in(greece)` is a `geo` term that matches by containment
like any category, `from(u2e4x)` is a `geo` term that matches by overlap.
**The marker is the only name this module knows** (Peter, 2026-09-12): it
is the maker's job to put the spacetime terms they want into the
conjunction, and the seed catalogue's job to declare which heads are
roles — loopmarket names no head, requires none, and renders none
specially. This is the mechanism that lets the offer's `service` window
and `where` disc leave the record (`docs/plans/P1-spacetime-terms.md`).

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


#: The marker node: a dimension head below it is a *service role*, and its
#: terms match by overlap. A plain node, so it merges, versions and pins
#: like any other vocabulary — a fork of this code cannot change the match
#: relation of a pinned catalogue (U3/U4). The name is provisional until
#: the v3 record freezes it into published roots. It is the one name the
#: core knows: which heads are roles is seed vocabulary (a head has one
#: value space, so `from`/`to` over `geo` and `depart`/`arrive` over `time`
#: are four declarations, not a table here).
SERVICE_ROLE = "service-role"


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

    def declare_service_roles(self, roles: Mapping[str, str]) -> None:
        """Declare role heads whose terms match by overlap: {head: base}.

        Each `head` is put under its base dimension head (inheriting the
        value grammar and the kind ontodag orders it by) *and* under the
        `service-role` marker — the same two edges `odag put from geo
        service-role` writes; this is a convenience for seeds and tests,
        and deliberately has no default: the core names no heads. When a
        base is a prelude head the catalogue has not adopted, ontodag's
        prelude is merged in — idempotent and canonical, the step `odag
        prelude` performs.
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
                    f"{base!r} is not a dimension head or kind: a service "
                    f"role needs a value space to compute overlap in")
        if SERVICE_ROLE not in self.dag.nodes:
            self.dag.put(SERVICE_ROLE, [])
        for head, base in roles.items():
            self.dag.put(head, [base, SERVICE_ROLE])

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

    def is_service_role(self, head: str) -> bool:
        """Does `head` hang under the `service-role` marker?"""
        return (SERVICE_ROLE in self.dag.nodes and head in self.dag.nodes
                and self.dag.is_below(head, SERVICE_ROLE))

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

        Two relations, chosen per term by its head (2026-09-12):

        - **containment** for categories and descriptive terms — every
          wanted one is covered by some offered concept (the offered
          thing is at least as specific as asked: a Corinthian amphora
          for "Greek amphora", `made_in(u2e4x)` for `made_in(u2e)`);
        - **overlap** for service-role terms — for each role head both
          sides name, the meet of the offered terms and the meet of the
          wanted terms intersect (a give from anywhere in `u2e` serves a
          want at `u2e4x`, and the reverse; a delivery instant exists).
          A head only one side names constrains nothing: the other side
          said "anywhere", "anytime".

        Strict on vocabulary (U7): a wanted category nobody knows never
        matches, and a service-role term the catalogue cannot interpret
        fails closed on *either* side — unlike an extra unknown category
        on the offered side, which only narrows the offer and so may be
        ignored, an ignored service term would silently widen it to
        "anywhere". Same-head terms that are provably disjoint make the
        conjunction empty and match nothing.
        """
        offered_roles, offered_plain = self.split_roles(offered)
        wanted_roles, wanted_plain = self.split_roles(wanted)
        if offered_roles is None or wanted_roles is None:
            return False
        if not all(any(self.covers(w, o) for o in offered_plain)
                   for w in wanted_plain):
            return False
        try:
            offered_meets = {h: self.meet(h, ts) for h, ts in offered_roles.items()}
            wanted_meets = {h: self.meet(h, ts) for h, ts in wanted_roles.items()}
        except ValueError:  # a value the head's grammar refuses
            return False
        if None in offered_meets.values() or None in wanted_meets.values():
            return False
        for head, wanted_meet in wanted_meets.items():
            offered_meet = offered_meets.get(head)
            if offered_meet is None:
                continue
            try:
                if _dims.intersect(offered_meet, wanted_meet,
                                   self.head_kind(head)) is None:
                    return False
            except ValueError:
                return False
        return True

    def split_roles(self, concepts: Iterable[str]):
        """Partition a conjunction into ({role head: [terms]}, [the rest]).
        Returns (None, rest) when a service-role term is not interpretable
        vocabulary — the caller fails closed. Public so candidate generators
        (`dimensions.DimensionIndex`) split exactly as the exact check does."""
        roles: dict[str, list[str]] = {}
        plain: list[str] = []
        for c in concepts:
            split = _dims.split_term(c)
            if split is None or not self.is_service_role(split[0]):
                plain.append(c)
                continue
            if self.head_kind(split[0]) is None or not self.known(c):
                return None, plain
            roles.setdefault(split[0], []).append(c)
        return roles, plain

    def meet(self, head: str, terms: list[str]) -> str | None:
        """The intersection of same-head terms as one canonical term, or
        None when it is provably empty (ValueError for a malformed value). Within a dimension meets are exact
        (ontodag DIMENSIONS.md §8); a conjunction *is* the meet of its
        terms, so two `from(...)` on one offer mean their intersection."""
        kind = self.head_kind(head)
        meet = terms[0]
        for term in terms[1:]:
            meet = _dims.intersect(meet, term, kind)
            if meet is None:
                return None
        return _dims.canonicalize(meet, kind)

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
