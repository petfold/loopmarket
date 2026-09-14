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

Three relations, and the catalogue says which applies (the marker nodes
`handover`, `descriptive` and `operator`, the names this module knows
besides the dimensions'):

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
  coordinate of that dimension;
- **want within give**, for the argument of an operator — `transport(...)`,
  the category under the marker `operator`. The courier who moves small
  items writes `give transport(small-item weight(..8kg))`; the wanter with
  a bicycle writes `want transport(bicycle weight(12kg))`. The argument is
  the operator's own want — what it accepts, an implicit want the give
  carries (Peter, 2026-09-13) — so it is matched like one, with the sides
  swapped: every constraint of the give's argument must contain a term of
  the want's (`bicycle ⊑ small-item`; the 12 kg bicycle fails the 8 kg
  limit), while the operator itself goes the usual way (`bicycle-courier ⊑
  transport`). A conjunction in the argument is several constraints, and
  `transport(A B)` is the same term as `transport(A) transport(B)`, and
  ontodag spells it one way (sorted, deduplicated). A give
  constraint the want does not answer refuses — a vague want ("move some
  goods") against a bicycle-only courier is the mirror of `give fruit`
  against `want apples`.

The one rule under all three: whoever fixes a value states a fact, whoever
leaves it open states an acceptance, and the fact must lie within the
acceptance. The giver fixes what the thing is; the wanter fixes what the
courier carries; either may fix where and when it changes hands.

A head the want does not name constrains nothing; a coordinate the give
does not state puts it in no cone of that head (an internet service has no
place, and does not serve a want at a door). Ontodag is intersection; all
three relations are `is_below`, and the seed decides the direction. The
operator term itself is ontodag's: a head of the *graph kind*
(`graph-dimension`, ontodag #19, 0.26.0) takes a conjunction of
constraints on the graph as its parameter, canonicalises it (sorted,
deduplicated, a redundant constraint refused, an unknown one failing
closed) and orders two such terms by the graph; this module only reads
the head and the constraints off it.

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


#: Marker nodes, the only names this module knows besides the dimensions'.
#: `handover`: the base heads under it (`geo`, `time`) are the
#: dimensions whose terms say where or when the thing changes hands and
#: match when one side contains the other — a bare cell, place or window,
#: and every role head under them (`from`/`to`, `depart`/`arrive`), since a
#: head under a head inherits the marker by transitive reduction anyway.
#: `descriptive`: a geo or time head whose terms describe the thing instead
#: (`made_in(corinth)`, `made(1850)`) opts out here and matches by
#: containment like a category.
HANDOVER = "handover"
DESCRIPTIVE = "descriptive"
#: Operator markers (composition, `docs/plans/P2-loop-selection.md` §10).
#: `operator`: a category under it (`transport`, `storage`) is an operator —
#: its parenthesised argument is what it accepts, matched want-within-give
#: (module docstring), and a give naming it MOVES a thing along the
#: dimension whose two ends it also names: a role under `operator-input`
#: (`from`, `depart`) is where it picks the thing up, one under
#: `operator-output` (`to`, `arrive`) where it puts it down. The solver
#: composes such a give with the give of the thing to satisfy a want at the
#: output coordinate; clearing re-derives.
OPERATOR = "operator"
OPERATOR_INPUT = "operator-input"
OPERATOR_OUTPUT = "operator-output"


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

    def declare_operator(self, operators: Mapping[str, tuple[str, str]]) -> None:
        """Declare operators: {category: (input head, output head)} —
        `{"transport": ("from", "to"), "storage": ("depart", "arrive")}`.
        The category goes under `operator` and under ontodag's
        `graph-dimension` kind (so `transport(small-item weight(..8kg))`
        is a term the graph orders, ontodag #19; the kind is declared under
        `dimension` if the catalogue lacks it), the two heads — roles of
        one dimension — under `operator-input` and `operator-output`:
        `odag put graph-dimension dimension`, `odag put transport
        graph-dimension operator`, `odag put from geo operator-input`,
        `odag put to geo operator-output`. Which dimension
        a give moves along is read off the give itself (the ends it names),
        so the category is not tied to a dimension here. Seed vocabulary;
        the core names no head. (0.5.0 took `{base: (in, out)}`: a give was
        an operator by naming two ends; since 2026-09-13 the operator is a
        category, because its argument is what it accepts.)"""
        for category, (inp, out) in operators.items():
            kind = self.head_kind(category)
            if kind not in (None, _dims.KIND_GRAPH) or category in _dims.KINDS:
                raise ValueError(
                    f"{category!r} is a {kind} head: an operator is a "
                    f"category whose argument is what it accepts")
            base = self.base_head(inp)
            if base is None or base == inp or self.base_head(out) != base \
                    or base == out:
                raise ValueError(
                    f"{inp!r}/{out!r}: an operator's ends are two roles of one "
                    f"dimension, the one it moves a thing along")
            if kind is None:            # `transport(...)` is a term of the graph kind
                if _dims.KIND_GRAPH not in self.dag.nodes:
                    if _dims.DIMENSION_ROOT not in self.dag.nodes:
                        from ontodag.prelude import apply as apply_prelude
                        apply_prelude(self.dag)
                    self.dag.put(_dims.KIND_GRAPH, [_dims.DIMENSION_ROOT])
                self.dag.put(category, [_dims.KIND_GRAPH])
            if OPERATOR not in self.dag.nodes:
                self.dag.put(OPERATOR, [])
            if not self.dag.is_below(category, OPERATOR):
                self.dag.add_edge(self.dag.nodes[OPERATOR], self.dag.nodes[category])
            self._mark(OPERATOR_INPUT, [inp])
            self._mark(OPERATOR_OUTPUT, [out])

    def operator_of(self, term: str) -> str | None:
        """The operator category `term` names — `transport(bicycle)` and
        bare `transport` both name `transport` — or None."""
        split = _dims.split_term(term)
        head = term if split is None else split[0]
        if head not in self.dag.nodes or head in _dims.KINDS \
                or OPERATOR not in self.dag.nodes \
                or not self.dag.is_below(head, OPERATOR):
            return None
        return head

    def argument(self, term: str) -> tuple[str, ...]:
        """The constraints an operator term's argument states, in
        ontodag's canonical spelling: `transport(weight(..8000g)
        small-item)` → `("small-item", "weight(..8kg)")`; a bare operator
        accepts anything: `()`. A term the catalogue refuses (an unknown or
        redundant constraint) has no argument here — `known` is where it
        fails closed."""
        split = _dims.split_term(term)
        if split is None:
            return ()
        try:
            canonical = self.dag._canonical_name(term)
        except ValueError:
            return ()
        return _dims.constraints(_dims.split_term(canonical)[1])

    def ends(self, concepts: Iterable[str]) -> list[tuple[str, str, str]]:
        """The moves an operator give states: `[(base, input term, output
        term)]` — one per dimension whose two ends it names (`from(a)` and
        `to(b)` → `("geo", "from(a)", "to(b)")`). Sorted by base."""
        by_base: dict[str, list] = {}
        for c in concepts:
            head = self.handover_class(c)
            if head is None or _dims.split_term(c) is None:
                continue
            for marker, slot in ((OPERATOR_INPUT, 0), (OPERATOR_OUTPUT, 1)):
                if marker in self.dag.nodes and self.dag.is_below(head, marker):
                    by_base.setdefault(self.base_head(head), [None, None])[slot] = c
        return [(b, i, o) for b, (i, o) in sorted(by_base.items()) if i and o]

    def base_head(self, head: str) -> str | None:
        """The base head of a role — the head directly under a kind node on
        the way up (`from` → `geo`); a base head is its own base."""
        if head not in self.dag.nodes or self.head_kind(head) is None:
            return None
        node = self.dag.nodes[head]
        for item in [node, *self.dag.get_ancestors(node)]:
            if any(p.name in _dims.KINDS for p in item.parents):
                return item.name
        return None

    def coordinate(self, concepts: Iterable[str], base: str) -> str | None:
        """The bare coordinate of dimension `base` a conjunction states
        (its place, its time), or None."""
        for c in concepts:
            if self.handover_class(c) == base:
                return c
        return None

    def bare(self, term: str) -> str:
        """A role term respelled as the bare coordinate it denotes:
        `from(my_home)` → `my_home` (a node), `to(u2e4)` → `geo(u2e4)`."""
        split = _dims.split_term(term)
        if split is None:
            return term
        head, param = split
        base = self.base_head(head)
        if base is None or base == head or param in self.dag.nodes:
            return param if param in self.dag.nodes else term
        return f"{base}({param})"

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
        narrows the offer and is ignored — except an operator term the
        catalogue refuses (an unknown or redundant constraint), which
        would widen the give to "accepts anything" and so refuses; a give
        whose same-head terms are provably disjoint describes nothing and
        satisfies nothing.

        An operator term (`transport(bicycle)`, a category under
        `operator`) is answered by an offered operator term whose category
        fits within it — and the offered term's argument, the operator's own
        want, must be answered in turn: every constraint it states contains
        some constituent the wanted operator terms state (`bicycle ⊑
        small-item`), so an offered constraint the want is silent on
        refuses. Both sides may spread one argument over several terms.

        All three relations are ontodag's `is_below`; the seed decides the
        direction by marking the handover heads and the operator categories
        (Peter, 2026-09-12/13: ontodag is intersection; a want is the wider
        cone for what a thing is, the give's argument the wider cone for
        what an operator accepts, and either side may be the wider one for
        where and when it changes hands).
        """
        offered, wanted = list(offered), list(wanted)
        if not self._consistent(offered) or not self._consistent(wanted):
            return False                # a conjunction that describes nothing
        classes = {o: self.handover_class(o) for o in offered}
        ops_o = {o: h for o in offered if (h := self.operator_of(o))}
        ops_w = {w: h for w in wanted if (h := self.operator_of(w))}
        for w in wanted:
            wc = self.handover_class(w)
            if w in ops_w:
                if not any(self.covers(ops_w[w], ho) for ho in ops_o.values()):
                    return False
            elif wc is None:
                if not any(self.covers(w, o) for o in offered):
                    return False
            else:
                same = [o for o in offered if classes[o] == wc]
                if not any(self.covers(w, o) or self.covers(o, w) for o in same):
                    return False
        for o, ho in ops_o.items():     # the operator's own want, answered
            if not self.known(o):
                return False            # an argument the catalogue refuses is not "accepts anything"
            pool = [d for w, hw in ops_w.items() if self.covers(hw, ho)
                    for d in self.argument(w)]
            if not any(self.covers(hw, ho) for hw in ops_w.values()):
                return False
            if not all(any(self.covers(c, d) for d in pool) for c in self.argument(o)):
                return False
        return True

    def accepts(self, concepts: Iterable[str], operator_terms: Iterable[str]) -> bool:
        """Does a thing described by `concepts` fit what the operator terms
        accept — every constraint of every argument contains some concept?
        The payload check of a composed leg (`matching.check_composition`):
        the box goes with the small-item courier, the piano does not."""
        concepts = list(concepts)
        return all(any(self.covers(c, d) for d in concepts)
                   for t in operator_terms for c in self.argument(t))

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
                        or self.head_kind(split[0]) == _dims.KIND_GRAPH \
                        or not self.known(c):
                    continue            # (graph-kind terms are never disjoint)
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
