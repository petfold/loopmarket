"""The `loop` command line: docs/plans/cli.md's gates G1-G6 and the rules
around them (price memory, the batch-confirm ruling, names in the catalogue,
withdrawal, record streams, settings)."""

import io
import json
import os
import re

import pytest
from ontodag import CONTRACT_VERSION, OntoDAG
from ontodag.dimensions import REGISTRY_VERSION
from ontodag.prelude import DECLARATIONS as PRELUDE_DECLARATIONS
from ontodag.prelude import apply as apply_prelude
from ontodag import surface
from recordstore import MemoryBytesStore, RecordStore

from loopmarket.spacetime import cell_for_coords
from loopmarket import (
    GeoDisc, MockClearing, OfferRegistry, Ontology, SolverAgent, Thing,
    TimeWindow, give, want,
)
from loopmarket import cli

NOW = 1_789_171_200                     # 2026-09-12T00:00:00Z
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRIANGLE_OD = os.path.join(ROOT, "examples", "triangle.od")
TRIANGLE_LOOP = os.path.join(ROOT, "examples", "triangle.loop")

# The catalogue the tests speak: ontodag's prelude (so `geo`/`time` exist),
# `when`/`where` as service roles (the v3 record's spacetime — the CLI knows
# no head, the catalogue declares them), and the triangle's trades.
CATALOGUE = {
    **{name: list(parents) for name, parents in PRELUDE_DECLARATIONS},
    "service-role": [],
    "when": ["time", "service-role"], "where": ["geo", "service-role"],
    "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"], "repair": ["service"],
    "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
    "local": [], "weekly": [], "vegetable-box": ["produce", "local", "weekly"],
    "fruit": ["food"], "apple": ["fruit"], "bicycle": [],
}


def write_od(path, edges):
    with open(path, "w", encoding="utf-8") as fh:
        for name, parents in edges.items():
            fh.write(" ".join([name, *parents]) + "\n")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A scratch home for both tools, an unpinned `.od` catalogue, a fixed
    clock, no confirmation prompts."""
    monkeypatch.setenv("LOOP_HOME", str(tmp_path / "loop"))
    monkeypatch.setenv("ONTODAG_HOME", str(tmp_path / "odag"))
    od = tmp_path / "cat.od"
    write_od(od, CATALOGUE)
    monkeypatch.setenv("LOOP_CATALOGUE", str(od))
    monkeypatch.setenv("LOOP_BOOK", f"rs:{tmp_path / 'book'}")
    monkeypatch.setenv("LOOP_CONFIRM", "off")
    monkeypatch.setenv("LOOP_NOW", str(NOW))
    monkeypatch.setenv("LOOP_MAKER", "amara")
    for var in ("LOOP_WHERE", "LOOP_PEERS", "BEE_SIGNER"):
        monkeypatch.delenv(var, raising=False)
    cli._OVERRIDES.clear()
    return tmp_path


class Runner:
    def __init__(self):
        self.session = cli.Session()

    def __call__(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = cli.dispatch(list(argv), self.session, out, err)
        return code, out.getvalue(), err.getvalue()

    def ok(self, *argv):
        code, out, err = self(*argv)
        assert code == 0, err
        return out

    def batch(self, text):
        out, err = io.StringIO(), io.StringIO()
        tokens = [cli._OUT.set(out), cli._ERR.set(err)]
        try:
            code = cli.run_stream(self.session, io.StringIO(text), False)
        finally:
            for t in reversed(tokens):
                t.var.reset(t)
        return code, out.getvalue(), err.getvalue()


@pytest.fixture
def loop(env):
    run = Runner()
    run.ok("place", "home", "46.05,14.50,5km")
    return run


# ---------------------------------------------------------------- G1: triangle

def _api_triangle(nonces):
    """The same six offers built through the API under the CLI's rules:
    unit `unit`, indivisible, windows from the fixed clock, pins from an
    unpinned catalogue, nonce = now*1000 + the maker's offer count."""
    ont = Ontology().load({k: v for k, v in CATALOGUE.items()})
    pins = dict(ontology_root="", registry_version=REGISTRY_VERSION,
                contract_version=CONTRACT_VERSION)
    W = dict(valid=TimeWindow(NOW, NOW + 30 * 86_400), **pins)
    # v3: the place is a term — the cell containing each radius (all `u24`
    # here, every place sits within its radius of a cell edge); no `when`
    # on the triangle's lines, so the offers are any time
    flat = f"where({cell_for_coords(46.05, 14.50, 5_000)})"
    farm = f"where({cell_for_coords(46.10, 14.55, 15_000)})"
    shop = f"where({cell_for_coords(46.06, 14.51, 4_000)})"
    t = lambda *c: Thing(tuple(c))  # noqa: E731
    offers = [
        give("amara", t("piano-lesson", flat), 100, nonce=nonces[0], **W),
        want("amara", t("produce", "local", "weekly", flat), 104, nonce=nonces[1], **W),
        give("bruno", t("vegetable-box", farm), 50, nonce=nonces[0], **W),
        want("bruno", t("bicycle-repair", farm), 52, nonce=nonces[1], **W),
        give("chen", t("bicycle-repair", shop), 80, nonce=nonces[0], **W),
        want("chen", t("music-lesson", shop), 83, nonce=nonces[1], **W),
    ]
    reg = OfferRegistry(RecordStore(MemoryBytesStore()))
    reg.publish_many(offers)
    reg.commit()
    agent = SolverAgent(reg, ont, MockClearing(reg, ont, clock=lambda: NOW))
    _, loops = agent.find_loops(now=NOW)
    assert len(loops) == 1
    return loops[0].loop_id


def test_g1_triangle_as_text_reproduces_the_python_loop_id(env, monkeypatch):
    monkeypatch.setenv("LOOP_CATALOGUE", TRIANGLE_OD)
    monkeypatch.delenv("LOOP_MAKER")
    monkeypatch.delenv("LOOP_NOW")
    run = Runner()
    with open(TRIANGLE_LOOP, encoding="utf-8") as fh:
        code, out, err = run.batch(fh.read())
    assert code == 0, err
    m = re.search(r"cleared ([0-9a-f]{16})", out)
    assert m, out
    expected = _api_triangle([NOW * 1000, NOW * 1000 + 1])
    assert expected.startswith(m.group(1))
    # the fills landed: the book is empty for a second pass
    code, out, err = run("loops")
    assert code == 1 and out == ""
    # and `set` was durable, as odag's is
    assert cli._read_config()["maker"] == "chen"


# ---------------------------------------------------------------- G2: grammar

CANONICAL_TERMS = [
    "weight(10kg)", "weight(10kg..21/2kg)", "weight(10kg..)", "weight(..11kg)",
    "time(2026-10-01T00:00:00Z..2026-12-31T23:59:59Z)", "count(3)",
    "duration(7200s)", "geo(u2e4)", "length(10/33m)", "temperature(300K)",
]


def test_g2_canonical_terms_pass_the_tokenizer_unchanged():
    dag = OntoDAG()
    apply_prelude(dag)
    for term in CANONICAL_TERMS:
        line = f"give apple {term} 5"
        tokens = cli.PARSER.parse_args(__import__("shlex").split(line)).tokens
        parsed = cli.parse_offer_tokens(tokens)
        assert parsed.concepts == ("apple", term)
        assert parsed.price == 5
        # and the surface law holds across the boundary
        assert surface.elaborate(surface.render(term, dag), dag) == term


def test_g2_two_conventions_and_nothing_else():
    p = cli.parse_offer_tokens(["10kg", "apple", "100"])
    assert (p.qty, p.unit, p.divisible, p.price) == (10, "kg", True, 100)
    assert all(isinstance(v, int) for v in (p.qty, p.price))   # not 10.0 (U2)
    p = cli.parse_offer_tokens(["2.5kg", "apple", "12.5"])
    assert (p.qty, p.price) == (2.5, 12.5)
    p = cli.parse_offer_tokens(["3", "bicycle"])
    assert (p.qty, p.unit, p.divisible, p.price) == (3, "unit", False, None)
    p = cli.parse_offer_tokens(["apple"])
    assert (p.qty, p.price, p.concepts) == (None, None, ("apple",))
    p = cli.parse_offer_tokens(["ride", "where(home)", "when(today..+7d)", "5"])
    assert p.concepts == ("ride", "where(home)", "when(today..+7d)")   # terms, all
    assert p.heads == {}
    p = cli.parse_offer_tokens(["ride", "valid(2h)", "5"])
    assert p.concepts == ("ride",) and p.heads == {"valid": "2h"}     # the one field
    with pytest.raises(ValueError, match="name what is exchanged"):
        cli.parse_offer_tokens(["100"])
    with pytest.raises(ValueError, match="name what is exchanged"):
        cli.parse_offer_tokens(["3", "100"])
    with pytest.raises(ValueError, match="given twice"):
        cli.parse_offer_tokens(["ride", "valid(2h)", "valid(3h)"])


def test_relative_time_elaborates_to_fixed_utc():
    w = cli.window("..+90d", NOW)
    assert (w.start, w.end) == (NOW, NOW + 90 * 86_400)
    w = cli.window("today..+7d", NOW + 3600)
    assert (w.start, w.end) == (NOW, NOW + 3600 + 7 * 86_400)
    w = cli.window("2026-10-01..2026-12-31", NOW)
    assert cli._iso(w.start) == "2026-10-01T00:00:00Z"
    assert cli._iso(w.end) == "2027-01-01T00:00:00Z"
    w = cli.window("2026-10", NOW)
    assert cli._iso(w.end) == "2026-11-01T00:00:00Z"
    assert cli.duration_s("2h") == 7200 and cli.duration_s("30d") == 30 * 86_400
    assert cli.radius_m("5km") == 5000 and cli.radius_m("250") == 250
    assert cli.radius_m("2.5km") == 2500 and cli.radius_m("1/3km") == 1000 / 3
    with pytest.raises(ValueError, match="window"):
        cli.window("+2h", NOW)
    with pytest.raises(ValueError, match="not a time"):
        cli.window("soonish..+2d", NOW)


# ---------------------------------------------------------------- G4: approve = show

def test_g4_approval_block_is_the_show_renderer(loop):
    out = loop.ok("give", "10kg", "apple", "where(home)", "100")
    oid = out.strip().splitlines()[-1]
    block = out.split("\n  note")[0]
    shown = loop.ok("show", oid[:12])
    assert shown.startswith(block)
    assert "state    open" in shown
    assert "up to 10 kg, divisible" in block
    assert "10/kg" in block
    assert "note     where(home) → where(" in out    # a private place: its cell


def test_want_reading_names_the_point(loop):
    out = loop.ok("want", "10kg", "apple", "where(home)", "90")
    assert "10 kg — the point; a floor (`10kg..`) is not encodable yet" in out


# ---------------------------------------------------------------- G5: nothing reserved

def test_g5_setting_and_head_names_are_ordinary_categories(env, tmp_path,
                                                          monkeypatch):
    names = {name: [] for name in list(cli._SETTINGS) + list(cli._INTERPRETED_HEADS)}
    od = tmp_path / "reserved.od"
    write_od(od, names)
    monkeypatch.setenv("LOOP_CATALOGUE", str(od))
    run = Runner()
    run.ok("place", "home", "46.05,14.50,5km")
    monkeypatch.setenv("LOOP_WHERE", "home")
    for name in names:
        oid = run.ok("give", name, "1").strip().splitlines()[-1]
        assert re.fullmatch(r"[0-9a-f]{64}", oid), name
    rows = run.ok("mine", "--raw").splitlines()
    assert len(rows) == len(names)


def test_g5_interpreted_head_declared_as_dimension_fires(env, tmp_path,
                                                        monkeypatch):
    dag = OntoDAG()
    apply_prelude(dag)
    dag.put("valid", ["calendar-dimension"])
    dag.put("apple", [])
    lines = []
    for name, item in dag.nodes.items():
        if name == "*":
            continue
        parents = [p.name for p in item.parents if p.name != "*"]
        lines.append(" ".join([name, *parents]))
    (tmp_path / "shadow.od").write_text("\n".join(lines) + "\n")
    monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "shadow.od"))
    run = Runner()
    code, out, err = run("give", "apple", "1")
    assert code == 1 and "declares `valid` as a dimension" in err


# ---------------------------------------------------------------- G6: bands refuse

@pytest.mark.parametrize("spelling", ["9kg..11kg", "10kg..", "..11kg"])
def test_g6_band_spellings_parse_and_refuse_with_the_point_named(loop, spelling):
    parsed = cli.parse_offer_tokens([spelling, "apple", "5"])
    assert parsed.band == spelling
    code, out, err = loop("give", spelling, "apple", "where(home)", "5")
    assert code == 1
    assert "not encodable" in err and "declare in the direction you know" in err
    assert "`" in err  # the point fallback is named


def test_g6_dimension_terms_refuse_until_quantities_are_terms(env, tmp_path,
                                                             monkeypatch):
    dag = OntoDAG()
    apply_prelude(dag)
    dag.put("apple", [])
    lines = [" ".join([n, *[p.name for p in i.parents if p.name != "*"]])
             for n, i in dag.nodes.items() if n != "*"]
    (tmp_path / "dims.od").write_text("\n".join(lines) + "\n")
    monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "dims.od"))
    run = Runner()
    code, out, err = run("give", "apple", "weight(10kg..10.5kg)", "5")
    assert code == 1 and "quantity term" in err and "ontodag-coupling.md" in err
    # a time term is a catalogue term like any other since the v3 record
    out = run.ok("give", "apple", "time(2026-10)", "5")
    assert "give     apple time(2026-10)" in out


def test_unknown_category_fails_closed(loop):
    code, out, err = loop("give", "durian", "where(home)", "5")
    assert code == 1 and "unknown category: durian" in err and "U7" in err


# ---------------------------------------------------------------- price memory

def test_omitted_price_is_my_last_unit_price_scaled_and_marked(loop):
    loop.ok("give", "10kg", "apple", "where(home)", "100")
    out = loop.ok("give", "5kg", "apple", "where(home)")
    assert "price    50 (10/kg" in out
    assert re.search(r"note     price 50 reused: unit price 10/kg from offer "
                     r"[0-9a-f]{12} \(0m ago\)", out)


def test_price_memory_is_keyed_by_side_and_bare_categories(loop):
    loop.ok("give", "10kg", "apple", "where(home)", "100")
    # a want for the same thing is a different price: no memory to reuse
    code, out, err = loop("want", "5kg", "apple", "where(home)")
    assert code == 1 and "no price, and no earlier want of apple" in err
    # a broader category is never consulted
    code, out, err = loop("give", "5kg", "fruit", "where(home)")
    assert code == 1 and "no earlier give of fruit" in err
    # a parametric term does not change the key
    out = loop.ok("give", "5kg", "apple", "when(today..+3d)", "where(home)")
    assert "price    50" in out


def test_price_memory_never_reads_other_makers(loop, monkeypatch):
    loop.ok("give", "10kg", "apple", "where(home)", "100")
    monkeypatch.setenv("LOOP_MAKER", "bruno")
    code, out, err = loop("give", "5kg", "apple", "where(home)")
    assert code == 1 and "by bruno to reuse" in err


def test_reused_price_refuses_in_a_batch_under_confirm_auto(loop, monkeypatch):
    """Peter's ruling, 2026-09-12: a script that omits a price publishes a
    number nobody saw — refuse the line, name the way out."""
    loop.ok("give", "10kg", "apple", "where(home)", "100")
    monkeypatch.setenv("LOOP_CONFIRM", "auto")
    before = len(loop.ok("mine", "--raw").splitlines())
    code, out, err = loop("give", "5kg", "apple", "where(home)")
    assert code == 1
    assert "refused: the price was reused" in err and "set confirm off" in err
    assert "note     price 50 reused" in out       # the block was still shown
    assert len(loop.ok("mine", "--raw").splitlines()) == before
    # a typed price proceeds in a batch
    assert loop("give", "5kg", "apple", "where(home)", "40")[0] == 0


# ---------------------------------------------------------------- names in the catalogue

def test_places_are_catalogue_nodes_with_coordinates(env, tmp_path):
    run = Runner()
    run.ok("place", "home", "46.05,14.50,5km")
    dag = run.session.personal_session.dag
    cell = cell_for_coords(46.05, 14.50, 5_000)
    assert [p.name for p in dag.nodes["home"].parents] == [f"geo({cell})"]
    assert not dag.nodes["home"].metadata            # no disc anywhere (v3)
    # the node persisted through the store (a fresh session reads it back)
    fresh = Runner()
    out = fresh.ok("give", "apple", "where(home)", "5")
    # the catalogue is a separate store here, so the place is private and
    # publishes as its cell (a catalogue name would stand as spelled, #15)
    assert f"give     apple where({cell})" in out
    assert f"note     where(home) → where({cell})" in out
    # a place is optional: an offer with none is anywhere
    out = fresh.ok("give", "apple", "5")
    assert out.startswith("give     apple\n")


def test_place_under_a_pinned_rs_catalogue_gets_its_cell_edge(env, tmp_path,
                                                             monkeypatch):
    """rs: catalogue with the prelude: the place hangs under its geo cell
    and the metadata survives the commit; offers pin the root."""
    from ontodag import __main__ as odag
    spec = f"rs:{tmp_path / 'cat'}"
    session = odag.Session(odag._normalize_spec(spec))
    apply_prelude(session.dag)
    for name, parents in CATALOGUE.items():
        for p in parents:
            if p not in session.dag.nodes:
                session.dag.put(p, [])
        session.dag.put(name, parents)
    session.save()
    monkeypatch.setenv("LOOP_CATALOGUE", spec)
    # ...and the personal layer is odag's default store, which is separate
    run = Runner()
    run.ok("place", "home", "46.05,14.50,5km")
    personal = run.session.personal_session.dag
    # the personal .od store had no prelude: `place` adopted it (by merge,
    # idempotent) so the place hangs under its cell — that edge is what
    # lets ontodag interpret the name
    assert any(p.name.startswith("geo(") for p in personal.nodes["home"].parents)
    out = run.ok("give", "apple", "where(home)", "5")
    root = run.session.catalogue.root
    assert root and f"catalogue {root[:16]}" in out
    # the pinned catalogue itself is untouched by the private name, and
    # the offer cannot carry a name that root does not hold: a private
    # place publishes as its cell, the name stays private (cli.md §12)
    assert "home" not in run.session.catalogue.dag.nodes
    cell = cell_for_coords(46.05, 14.50, 5_000)
    assert f"give     apple where({cell})" in out
    assert f"note     where(home) → where({cell})" in out
    # a place written INTO the prelude'd rs: store commits (metadata too)
    monkeypatch.setenv("ONTODAG_STORE", spec)
    monkeypatch.delenv("LOOP_CATALOGUE")
    run2 = Runner()
    run2.ok("place", "shop", "46.06,14.51,400m")
    dag = run2.session.personal_session.dag
    assert any(p.name.startswith("geo(") for p in dag.nodes["shop"].parents)
    assert dag.store.root != root                     # a real commit
    shop = Runner().session.personal_session.dag.nodes["shop"]
    assert [p.name for p in shop.parents] == [f"geo({cell_for_coords(46.06, 14.51, 400)})"]


def _od_with_prelude(path, extra_puts):
    """The prelude, the `when`/`where` service roles (the v3 record's
    spacetime — catalogue vocabulary, not the CLI's), then `extra_puts`."""
    dag = OntoDAG()
    apply_prelude(dag)
    dag.put("service-role", [])
    dag.put("when", ["time", "service-role"])
    dag.put("where", ["geo", "service-role"])
    for name, parents in extra_puts:
        dag.put(name, parents)
    lines = [" ".join([n, *[p.name for p in i.parents if p.name != "*"]])
             for n, i in dag.nodes.items() if n != "*"]
    path.write_text("\n".join(lines) + "\n")


def test_role_terms_carry_the_name_and_match_by_the_graph(
        env, tmp_path, monkeypatch):
    """ontodag #15 (2026-09-12): a role head takes the base dimension's
    nodes as parameters, so a catalogue name in a role term stands as
    spelled — `from(my_home)` is the published term, and the graph orders
    it (`my_home ⊑ geo(u2e4x)`), the London→Rome pattern with the name
    kept. Here the personal store is the catalogue, so `place` writes
    vocabulary."""
    # `from`/`to` as roles OF `geo` (a head under a head, #15): only a
    # role head reads a parameter as a node; a bare prefix head would
    # read `my_home` as the literal cell "my_home"
    _od_with_prelude(tmp_path / "roles.od",
                     [("from", ["geo", "service-role"]), ("to", ["geo", "service-role"]),
                      ("ride", [])])
    monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "roles.od"))
    monkeypatch.setenv("ONTODAG_STORE", str(tmp_path / "roles.od"))
    run = Runner()
    run.ok("place", "my_home", "46.05,14.50,500m")
    cell = cell_for_coords(46.05, 14.50, 500)
    out = run.ok("give", "ride", "from(my_home)", "where(my_home)", "5")
    assert "give     from(my_home) ride where(my_home)" in out and "→" not in out
    oid = out.strip().splitlines()[-1]
    rec = run.session.book.store.get(f"offer/{oid}")
    assert rec["gives"]["concepts"] == ["from(my_home)", "ride", "where(my_home)"]
    # a want anywhere in the parent cell matches by the graph's order
    monkeypatch.setenv("LOOP_MAKER", "bruno")
    run.ok("want", "ride", f"from({cell[:2]})", "where(my_home)", "6")
    code, out, err = run("matches")
    assert code == 0 and "amara gives" in out and "bruno" in out
    # a literal value that is not a name passes through unchanged...
    assert f"from({cell[:3]})" in run.ok("want", "ride", f"from({cell[:3]})",
                                         "where(my_home)", "6")
    # ...an undeclared role head is an unknown category (U7)...
    code, out, err = run("want", "ride", "via(my_home)", "where(my_home)", "6")
    assert code == 1 and "unknown category: via(my_home)" in err
    # ...and a name outside the dimension is refused by ontodag, in its
    # own words, never read as a literal cell that spells the same
    code, out, err = run("want", "ride", "from(ride)", "where(my_home)", "6")
    assert code == 1 and "names a category outside the 'geo' dimension" in err
    # `offers` filters through the same order
    assert len(run.ok("offers", f"from({cell[:2]})", "--raw").splitlines()) == 3
    assert run.ok("offers", "from(zzzz)", "--raw") == ""


def test_regions_and_floors_are_names_in_role_terms(env, tmp_path, monkeypatch):
    """A region above cells and a floor under a building (ontodag #15's
    two shapes beyond a place) are catalogue nodes a role term names as
    spelled; matching decides them by the graph (#16): a give to the
    region serves a want on the fourth floor of a building it covers."""
    _od_with_prelude(tmp_path / "city.od",
                     [("delivery", []),
                      ("my_home", ["geo(u2e4x)"]), ("my_home_4th", ["my_home"]),
                      ("ljubljana", ["geo"]), ("geo(u2e4)", ["ljubljana"]),
                      ("geo(u2e5)", ["ljubljana"])])
    monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "city.od"))
    run = Runner()
    out = run.ok("give", "delivery", "where(ljubljana)", "5")
    assert "give     delivery where(ljubljana)" in out
    monkeypatch.setenv("LOOP_MAKER", "bruno")
    out = run.ok("want", "delivery", "where(my_home_4th)", "6")
    assert "want     delivery where(my_home_4th)" in out
    code, out, err = run("matches")
    assert code == 0 and "amara gives delivery where(ljubljana) to bruno" in out
    # a region's covering is a lower bound: a want beyond it does not match
    monkeypatch.setenv("LOOP_MAKER", "chen")
    run.ok("want", "delivery", "where(u2f)", "6")
    assert "chen" not in run.ok("matches")
    assert len(run.ok("offers", "where(u2e4)", "--raw").splitlines()) == 2


def test_time_names_need_nothing_from_loopmarket(env, tmp_path, monkeypatch):
    """`odag put autumn 'time(...)'` then when(autumn): the name's value is
    the time term it hangs under, carried into the role the person typed
    — the same device as a place's cell; containment is ontodag's."""
    _od_with_prelude(tmp_path / "t.od",
                     [("apple", []), ("autumn", ["time(2026-09-22..2026-12-20)"])])
    monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "t.od"))
    run = Runner()
    out = run.ok("give", "apple", "when(autumn)", "5")
    # the name stands as spelled (ontodag #15); the graph orders it
    assert "give     apple when(autumn)" in out and "→" not in out
    assert run.session.catalogue.covers(
        "when(2026-09-01T00:00:00Z..2026-12-31T00:00:00Z)", "when(autumn)")
    # relative spellings are input vocabulary, elaborated to fixed UTC
    out = run.ok("give", "apple", "when(today..+1d)", "5")
    assert "note     when(today..+1d) → when(" in out and "T00:00:00Z.." in out


# ---------------------------------------------------------------- the rest of the surface

def test_withdraw_tombstones_only_my_open_offers(loop, monkeypatch):
    oid = loop.ok("give", "apple", "where(home)", "5").strip().splitlines()[-1]
    monkeypatch.setenv("LOOP_MAKER", "bruno")
    code, out, err = loop("withdraw", oid[:10])
    assert code == 1 and "no such offer of yours" in err
    monkeypatch.setenv("LOOP_MAKER", "amara")
    loop.ok("withdraw", oid[:10])
    assert "withdrawn" in loop.ok("show", oid[:10])
    assert loop("withdraw", oid[:10])[2].strip().endswith("already withdrawn")
    assert loop.ok("offers", "--raw") == ""      # not active any more
    assert oid[:12] in loop.ok("mine", "--raw")  # but still mine, all states


def test_offers_filters_through_satisfies(loop):
    loop.ok("give", "apple", "where(home)", "5")
    loop.ok("give", "piano-lesson", "where(home)", "100")
    rows = loop.ok("offers", "--raw").splitlines()
    assert len(rows) == 2
    assert len(loop.ok("offers", "food", "--raw").splitlines()) == 1
    assert len(loop.ok("offers", "lesson", "--raw").splitlines()) == 1
    assert loop.ok("offers", "bicycle", "--raw") == ""
    assert loop.ok("offers", "unknown-thing", "--raw") == ""   # U7, fails closed
    # a table at a "terminal" (forced render), tab-separated in a pipe
    table = loop.ok("offers", "--render")
    assert table.splitlines()[0].startswith("id")
    assert "\t" in rows[0]


def test_export_import_round_trip_keeps_ids(loop, tmp_path, monkeypatch):
    ids = {loop.ok("give", "apple", "where(home)", "5").strip().splitlines()[-1],
           loop.ok("want", "bicycle", "where(home)", "50").strip().splitlines()[-1]}
    dump = loop.ok("export")
    records = [json.loads(line) for line in dump.splitlines()]
    assert len(records) == 2
    monkeypatch.setenv("LOOP_BOOK", f"rs:{tmp_path / 'other'}")
    other = Runner()
    (tmp_path / "in.jsonl").write_text(dump)
    code, out, err = other("import", str(tmp_path / "in.jsonl"))
    assert code == 0 and err.strip() == "2"
    assert {o.offer_id for o in other.session.book.offers()} == ids


def test_loops_and_clear_are_predicates(loop):
    assert loop("loops")[0] == 1
    assert loop("clear")[0] == 1
    assert loop("matches")[0] == 1


def test_status_reports_roots_and_settings(loop):
    out = loop.ok("status")
    assert "book = rs:" in out and "catalogue root = (unpinned)" in out
    assert "maker = amara" in out and "now = 2026-09-12T00:00:00Z" in out
    assert "categories = " in out


def test_set_is_durable_validated_and_fails_closed(env):
    run = Runner()
    code, out, err = run("set", "alias", "x")
    assert code == 1 and "unknown setting: alias" in err
    assert run("set", "confirm", "maybe")[0] == 1
    assert run("set", "terms", "yesterday-ish")[0] == 1        # not a term
    assert run("set", "book", "/plain/path")[0] == 1
    run.ok("set", "valid", "2h")
    run.ok("set", "terms", "where(home)")
    assert cli._read_config() == {"valid": "2h", "terms": "where(home)"}
    assert oct(os.stat(cli._config_path()).st_mode)[-3:] == "600"
    assert run.ok("set", "valid").strip() == "valid = 2h"
    listing = run.ok("set")
    assert "bee_signer = \n" in listing or "bee_signer = <hidden" in listing
    # precedence: env outranks config
    os.environ["LOOP_VALID"] = "1d"
    try:
        assert run.ok("set", "valid").strip() == "valid = 1d"
    finally:
        del os.environ["LOOP_VALID"]


def test_odag_config_is_inherited_for_shared_settings(env, tmp_path, monkeypatch):
    monkeypatch.delenv("LOOP_CATALOGUE")
    odag_home = tmp_path / "odag"
    odag_home.mkdir(exist_ok=True)
    (odag_home / "config").write_text("bee_api = http://bee.local:1633\n"
                                      "store = rs:" + str(tmp_path / "shared") + "\n")
    assert cli._configured("bee_api") == "http://bee.local:1633"
    assert cli._configured("catalogue") == "rs:" + str(tmp_path / "shared")
    cli._write_config({"bee_api": "http://mine:1633"})
    assert cli._configured("bee_api") == "http://mine:1633"


def test_main_global_flags_and_version(env, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == cli.__version__
    with pytest.raises(SystemExit) as exc:
        cli.main(["--maker", "zed", "--confirm", "off", "set", "maker"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "maker = zed"
    with pytest.raises(SystemExit) as exc:
        cli.main(["--maker"])
    assert exc.value.code == 2


def test_help_lists_every_setting(env):
    run = Runner()
    out = run.ok("help")
    for key in cli._SETTINGS:
        assert f"  {key:<11}" in out


def test_batch_skips_comments_and_reports_shell_errors(env):
    run = Runner()
    code, out, err = run.batch("# a comment\n\ngive 'unbalanced\nset maker amara\n")
    assert code == 0 and "No closing quotation" in err
    assert cli._read_config()["maker"] == "amara"


def test_peers_fold_into_every_answer_and_clear_rebases(env, tmp_path, monkeypatch):
    """`peers`: read-only books folded into offers/matches/loops; `clear`
    first re-bases my book on the fold (P1 §1's clearing pattern)."""
    monkeypatch.setenv("LOOP_CATALOGUE", TRIANGLE_OD)
    amara = Runner()
    amara.ok("place", "home", "46.05,14.50,5km")
    amara.ok("give", "piano-lesson", "where(home)", "100")
    amara.ok("want", "produce", "local", "weekly", "where(home)", "104")
    monkeypatch.setenv("LOOP_BOOK", f"rs:{tmp_path / 'bruno'}")
    monkeypatch.setenv("LOOP_MAKER", "bruno")
    bruno = Runner()
    bruno.ok("give", "vegetable-box", "where(home)", "50")
    bruno.ok("want", "bicycle-repair", "where(home)", "52")
    monkeypatch.setenv("LOOP_BOOK", f"rs:{tmp_path / 'chen'}")
    monkeypatch.setenv("LOOP_MAKER", "chen")
    chen = Runner()
    chen.ok("give", "bicycle-repair", "where(home)", "80")
    chen.ok("want", "music-lesson", "where(home)", "83")
    assert chen("loops")[0] == 1                       # alone, nothing
    monkeypatch.setenv("LOOP_PEERS", f"rs:{tmp_path / 'book'},rs:{tmp_path / 'bruno'}")
    assert len(chen.ok("offers", "--raw").splitlines()) == 6
    assert chen("loops")[0] == 0
    code, out, err = chen("clearing")
    assert code == 0 and "cleared" in out and "re-based on the fold" in err
    assert "filled 6" in chen.ok("status")
    # a bad peer spec is refused at set time
    assert chen("set", "peers", "/no/scheme")[0] == 1


# ---------------------------------------------------------------- composed wants (cli.md §13)

def test_plus_separates_parts_of_a_want_and_nothing_else():
    c = cli.parse_want_line(["ticket", "hamlet", "+", "2", "transport", "from(home)", "60"])
    assert isinstance(c, cli.Composed) and c.price == 60
    assert [p.concepts for p in c.parts] == [("ticket", "hamlet"),
                                             ("transport", "from(home)")]
    assert c.parts[1].qty == 2 and c.parts[1].heads == {}
    assert c.parts[0].price is None and c.parts[1].price is None
    # a line without `+` is an ordinary want
    assert isinstance(cli.parse_want_line(["ticket", "60"]), cli.Parsed)
    with pytest.raises(ValueError, match="parts carry no prices"):
        cli.parse_want_line(["ticket", "5", "+", "transport", "60"])
    with pytest.raises(ValueError, match="no validity of its own"):
        cli.parse_want_line(["ticket", "valid(2h)", "+", "transport", "60"])
    with pytest.raises(ValueError, match="empty part"):
        cli.parse_want_line(["ticket", "+", "+", "transport", "60"])
    with pytest.raises(ValueError, match="want.*only"):
        cli.parse_offer_tokens(["bicycle", "+", "helmet", "900"])


@pytest.fixture
def stage(env, tmp_path, monkeypatch):
    """A catalogue with role heads, two places, and the maker amara."""
    _od_with_prelude(tmp_path / "stage.od",
                     [("from", ["prefix-dimension"]), ("to", ["prefix-dimension"]),
                      ("theatre-ticket", []), ("hamlet", ["theatre-ticket"]),
                      ("transport", []), ("person", [])])
    monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "stage.od"))
    monkeypatch.setenv("LOOP_TERMS", "where(home)")     # the default place
    run = Runner()
    run.ok("place", "home", "46.05,14.50,5km")
    run.ok("place", "venue", "46.051,14.506,100m")
    return run


TICKET = ["theatre-ticket", "hamlet",
          "when(2026-10-05T19:00:00Z..2026-10-05T22:00:00Z)", "where(venue)"]
RIDE = ["transport", "person", "from(home)", "to(venue)",
        "when(2026-10-05T17:00:00Z..2026-10-05T19:00:00Z)"]


def test_drafts_named_numbered_canonical_and_never_in_the_book(stage):
    home = cell_for_coords(46.05, 14.50, 5000)
    venue = cell_for_coords(46.051, 14.506, 100)
    out = stage.ok("draft", "ticket", "want", *TICKET)
    assert out.startswith("ticket  want hamlet theatre-ticket when(2026-10-05T19:00:00Z.."
                          f"2026-10-05T22:00:00Z) where({venue})")
    stage.ok("draft", "ride", "want", *RIDE)
    stage.ok("draft", "want", "hamlet", "5")                # unnamed, priced
    listing = stage.ok("drafts")
    assert f"ride  want from({home}) person to({venue}) transport when(" in listing
    assert "   typed ride want transport person from(home) to(venue)" in listing
    assert f"   note  from(home) → from({home})" in listing   # a private place
    assert re.search(r"^3  want hamlet where\(.*\) 5$", listing, re.M)  # price last
    assert stage.ok("mine", "--raw") == "" and stage.ok("offers", "--raw") == ""
    assert os.path.exists(os.path.join(os.environ["LOOP_HOME"], "drafts"))
    # the canonical line re-parses to the same window and place
    line = listing.splitlines()[0].split(" ", 3)[3].split()
    out = stage.ok("want", *line, "5")
    assert ("want     hamlet theatre-ticket when(2026-10-05T19:00:00Z.."
            f"2026-10-05T22:00:00Z) where({venue})") in out
    # re-drafting a name replaces it and keeps its number
    stage.ok("draft", "ticket", "want", "hamlet", "where(venue)")
    assert stage.ok("drafts").startswith(f"ticket  want hamlet where({venue})")
    # names: not `+`, not numbers (a leading verb starts an unnamed draft)
    for bad in ("+", "7"):
        assert "cannot name a draft" in stage("draft", bad, "want", "hamlet")[2]
    assert "unknown category: want" in stage("draft", "want", "want", "hamlet")[2]
    assert "a draft has no validity" in stage("draft", "want", "hamlet", "valid(2h)")[2]
    stage.ok("draft", "want", "hamlet")
    assert "\n4  want hamlet" in stage.ok("drafts")
    # discard by name and number; discard alone empties
    stage.ok("discard", "ticket", "4")
    names = [l.split()[0] for l in stage.ok("drafts").splitlines() if not l.startswith(" ")]
    assert names == ["ride", "3"]
    code, out, err = stage("discard")
    assert code == 0 and err.strip() == "2 discarded" and stage("drafts")[0] == 1


def test_plus_between_drafts_composes_and_offer_refuses_until_v4(stage, monkeypatch):
    stage.ok("draft", "ticket", "want", *TICKET)
    stage.ok("draft", "ride", "want", *RIDE)
    out = stage.ok("draft", "evening", "ticket", "+", "ride")
    assert out.startswith("evening  want hamlet theatre-ticket when(") and " + from(" in out
    assert "   typed evening ticket + ride" in stage.ok("drafts")
    assert "   note  part 2: from(home) →" in stage.ok("drafts")
    # composition flattens
    stage.ok("draft", "seat", "want", "person", "transport", "where(home)")
    out = stage.ok("draft", "night", "evening", "+", "seat")
    assert out.count(" + ") == 2
    # a copy keeps its parts (and its price, if any)
    stage.ok("draft", "ticket2", "ticket")
    assert stage.ok("drafts").count("ticket2  want hamlet theatre-ticket") == 1
    # offering the composed draft renders every part, then refuses
    code, out, err = stage("offer", "night", "60")
    assert code == 1
    assert "not encodable until the v4 record" in err and "cli.md §13" in err
    assert out.startswith("want     hamlet theatre-ticket + ")
    assert "  part 1   hamlet theatre-ticket" in out and "  part 3   person transport" in out
    assert "price    60 (the lot, on amara's scale; split across the parts" in out
    assert "offer_id (none" in out and "note     part 2: from(home) →" in out
    assert "night  want" in stage.ok("drafts")                     # kept
    assert "needs its price" in stage("offer", "night")[2]
    # parts carry no prices; gives do not compose; one maker
    stage.ok("draft", "priced", "want", "hamlet", "where(venue)", "20")
    assert "carries a price" in stage("draft", "x", "priced", "+", "ride")[2]
    stage.ok("draft", "kit", "give", "hamlet", "where(venue)", "9")
    assert "is a give: composition is want-side only" in stage("draft", "x", "kit", "+", "ride")[2]
    assert "joined as A + B" in stage("draft", "x", "+", "ride")[2]
    assert "no such draft: nope" in stage("draft", "x", "nope", "+", "ride")[2]
    monkeypatch.setenv("LOOP_MAKER", "bruno")
    assert "was drafted as amara" in stage("offer", "priced")[2]
    assert "was drafted as amara" in stage("draft", "y", "ticket", "+", "ride")[2]
    monkeypatch.setenv("LOOP_MAKER", "amara")
    assert stage.ok("mine", "--raw") == ""


def test_offer_publishes_a_simple_draft_and_removes_it(stage):
    stage.ok("draft", "ticket", "want", *TICKET)                  # unpriced
    stage.ok("draft", "seat", "want", "person", "transport", "where(home)", "20")
    # an unpriced draft needs a price at offer (or the price memory)
    assert "no price, and no earlier want" in stage("offer", "ticket")[2]
    out = stage.ok("offer", "ticket", "45")
    oid = out.strip().splitlines()[-1]
    assert re.fullmatch(r"[0-9a-f]{64}", oid) and "price    45" in out
    assert "ticket  want" not in stage.ok("drafts")                  # consumed
    # a priced draft offers as is; a given price shows in the block instead
    out = stage.ok("offer", "seat", "25")
    assert "price    25" in out and stage("drafts")[0] == 1
    rows = stage.ok("mine", "--raw").splitlines()
    assert len(rows) == 2
    # the price memory serves a later unpriced draft of the same thing
    stage.ok("draft", "again", "want", *TICKET)
    out = stage.ok("offer", "again")
    assert "price    45" in out and "reused: unit price 45/unit" in out
    assert "offer NAME [PRICE]" in stage("offer")[2]
    assert "no such draft: zzz" in stage("offer", "zzz", "5")[2]


def test_one_line_composed_want_is_the_same_block(stage):
    code, out, err = stage("want", *TICKET, "+", *RIDE, "60")
    assert code == 1 and "not encodable until the v4 record" in err
    assert out.startswith("want     hamlet theatre-ticket + ")
    assert "  part 2   from(" in out and "price    60" in out
    assert stage("drafts")[0] == 1                       # the line staged nothing
    assert stage.ok("mine", "--raw") == ""
    # a coordinate literal in where(...) is the spelling `place` takes: the
    # cell containing that radius, and nothing else, is what the offer says
    out = stage.ok("want", "hamlet", "where(46.1,14.6,2km)", "5")
    cell = cell_for_coords(46.1, 14.6, 2000)
    assert f"want     hamlet where({cell})" in out
    assert f"note     where(46.1,14.6,2km) → where({cell})" in out


def test_clearing_is_the_verb_and_clear_its_alias(loop):
    assert loop("clearing")[0] == 1 and loop("clear")[0] == 1
    assert "loop clearing" in loop.ok("help") and "loop clear " not in loop.ok("help")


def test_offer_line_is_pythons_offer_literal(loop):
    o = cli.offer_from_line("want 2kg apple where(home) when(2026-10-01..2026-10-03) 9",
                            loop.session)
    assert o.kind == "want" and o.thing.qty == 2 and o.tokens.amount == 9
    line = cli.line_for(o)
    home = cell_for_coords(46.05, 14.50, 5000)
    assert line.startswith(f"want 2kg apple when(2026-10-01..2026-10-03) where({home}) valid(")
    assert line.endswith(" 9")
    again = cli.offer_from_line(line, loop.session)
    assert cli.line_for(again) == line
    assert again.thing == o.thing and again.valid == o.valid and again.v == 3
    assert loop.ok("mine", "--raw") == ""                # a literal publishes nothing
    with pytest.raises(ValueError, match="starts with give or want"):
        cli.offer_from_line("apple 5", loop.session)
    with pytest.raises(ValueError, match="not encodable until the v4"):
        cli.offer_from_line("want apple where(home) + apple where(home) 9", loop.session)
