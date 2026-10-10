"""`watch` end to end on composed and aggregated legs (the 2026-10 review,
§7 suggestion 9): offers typed at the command line, cleared by `loop
clearing`, and every party's `watch` — the daemon itself, polling while
clearing happens elsewhere, and single passes — reporting its own fills
with its counterparties and carrying the sealed handoffs. A composed or
aggregated leg has several gives, and until 2026-10-09 `watch` matched
only the first, so the second giver never heard it was filled
(`test_cli.py::test_every_give_of_a_composed_leg_finds_its_leg` covers
finding the leg; these cover the daemon).

Each maker signs with a throwaway key made here, so the handoffs are
sealed for real. A handoff goes to the leg's first give only: sealing to
several givers is an open protocol question (the review's §4), and the
tests pin today's behaviour so that deciding it changes them."""

import io
import os
import secrets
from types import SimpleNamespace

import pytest

pytest.importorskip("coincurve", reason="sealed handoffs need the sig extra")

from loopmarket import cli  # noqa: E402
from loopmarket.sigs import maker_address  # noqa: E402
from loopmarket.spacetime import cell_for_coords  # noqa: E402
from test_cli import Runner, _od_with_prelude  # noqa: E402

DELIVERY = [("operator", []), ("graph-dimension", ["dimension"]),
            ("transport", ["graph-dimension", "operator"]),
            ("operator-input", []), ("operator-output", []),
            ("from", ["geo", "operator-input"]), ("to", ["geo", "operator-output"]),
            ("small-item", []), ("food", []), ("vegetable-box", ["food", "small-item"]),
            ("repair", []), ("bicycle-repair", ["repair"]), ("lesson", []), ("piano-lesson", ["lesson"])]


class Town:
    """One book everyone writes (the dev shape, `docs/plans/cli.md` §8) and
    one catalogue; each maker signs with its own key and runs its own client,
    with its own home: what it has seen, the handoff texts it keeps until
    they can be sealed, its names."""

    def __init__(self, tmp_path, monkeypatch, catalogue, names):
        _od_with_prelude(tmp_path / "town.od", catalogue)
        monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "town.od"))
        monkeypatch.delenv("LOOP_MAKER")               # identity = the signer's address
        self.tmp, self.monkeypatch = tmp_path, monkeypatch
        self.key = {n: "0x" + secrets.token_hex(32) for n in names}
        self.who = {n: maker_address(k) for n, k in self.key.items()}

    def as_(self, name):
        """Become `name`: its key, its home, and a client started afresh, as
        a command line is, so it reads the book as the others left it."""
        home = self.tmp / "homes" / name
        self.monkeypatch.setenv("BEE_SIGNER", self.key[name])
        self.monkeypatch.setenv("LOOP_HOME", str(home / "loop"))
        self.monkeypatch.setenv("ONTODAG_HOME", str(home / "odag"))
        return Runner()

    def book(self):
        """The shared book as it stands now."""
        return cli.stores._open_book(os.environ["LOOP_BOOK"])

    def daemon(self, name, between):
        """`watch` without `--once`, as `name`, for two passes: `between()`
        runs where the daemon sleeps after the first (another writer at
        work), and the second sleep stops it. Returns (first pass, second
        pass) as printed."""
        out, err, passes = io.StringIO(), io.StringIO(), []

        def sleep(_seconds):
            passes.append(out.getvalue())
            if len(passes) == 1:
                between()
                self.as_(name)
                return
            raise KeyboardInterrupt

        self.monkeypatch.setattr(cli.watch, "_time", SimpleNamespace(sleep=sleep))
        run = self.as_(name)
        with pytest.raises(KeyboardInterrupt):
            cli.dispatch(["watch"], run.session, out, err)
        first = passes[0]
        return first, passes[1][len(first):]


def test_the_courier_of_a_composed_leg_hears_of_its_fill_from_the_daemon(env, tmp_path, monkeypatch):
    """Peter's vegetable box (`examples/delivery.loop`) with keys: the
    buyer's want is met by the grocer's box and the courier's run together,
    one composed leg. The courier's daemon is polling when clearing happens
    in another session; its next pass reports both its fills, the run to
    the buyer among them. The buyer hears it receives the box from both
    givers; its door's handoff is sealed to the grocer, the leg's first
    give, who opens it, and the courier gets none (the open question)."""
    town = Town(tmp_path, monkeypatch, DELIVERY, ("grocer", "buyer", "courier", "mechanic"))
    run = town.as_("grocer")
    run.ok("place", "shop", "41.3874,2.1686,20m")
    run.ok("give", "vegetable-box", "shop", "5")
    run.ok("want", "bicycle-repair", "shop", "6")
    run = town.as_("buyer")
    run.ok("place", "door", "41.4036,2.1744,20m", "Carrer", "de", "Verdi", "12")
    box = run.ok("want", "vegetable-box", "door", "8").strip().splitlines()[-1]
    at_door = f"geo({cell_for_coords(41.4036, 2.1744, 20)})"         # the door's cell, without its address
    run.ok("give", "piano-lesson", at_door, "4")
    run.ok("give", "piano-lesson", at_door, "4")
    run = town.as_("courier")
    ride = run.ok("give", "transport(small-item)", "from(geo(sp3))", "to(geo(sp3))", "2").strip().splitlines()[-1]
    run.ok("want", "piano-lesson", "geo(sp3)", "5")
    run = town.as_("mechanic")
    run.ok("give", "bicycle-repair", "geo(sp3)", "5")
    run.ok("want", "piano-lesson", "geo(sp3)", "5")

    def clearing_elsewhere():
        out = town.as_("mechanic").ok("clearing")
        assert "cleared " in out and "(composed)" in out

    first, second = town.daemon("courier", clearing_elsewhere)
    C, B, G = town.who["courier"], town.who["buyer"], town.who["grocer"]
    assert first == ""                                                  # nothing cleared yet
    assert second.count("filled   ") == 2
    assert f"filled   {ride[:12]} in loop" in second
    assert f"{C} gives from(geo(sp3)) to(geo(sp3)) transport(small-item) to {B}" in second
    assert f"{C} receives piano-lesson from {B}" in second
    book = town.book()
    leg = next(l for l in book.loop_legs(book.loop_of(box)) if l.want == box)
    assert leg.gives[1] == ride and book.get(leg.gives[0]).maker == G   # the box first, the courier second
    # the buyer: the box from both givers; its door sealed to the leg's first give
    out = town.as_("buyer").ok("watch", "--once")
    assert f"{B} receives vegetable-box from {', '.join(sorted([C, G]))}" in out
    assert out.count("sealed to ") == 1 and f"handoff  {box[:12]} sealed to {G}" in out
    out = town.as_("grocer").ok("watch", "--once")
    assert f"handoff  from {B}" in out and "door: Carrer de Verdi 12" in out
    code, out, _ = town.as_("courier")("watch", "--once")
    assert code == 1 and "handoff" not in out                          # nothing new; no door for the courier


def test_every_lifter_of_an_aggregated_leg_hears_of_its_share(env, tmp_path, monkeypatch):
    """The six lifters (`P2-loop-selection.md` §10), typed: the mover wants
    six, three lifters give two each (the third by the person), and each
    wants a lesson the mover gives, so one leg takes from all three. The
    third lifter's daemon reports its share; every lifter's pass reports its
    own fill; the mover hears it receives lifting from all three, and its
    handoff is sealed to the leg's first give alone."""
    town = Town(tmp_path, monkeypatch, [("lifting", []), ("lesson", [])], ("mover", "ana", "ben", "cai"))
    M = town.who["mover"]
    run = town.as_("mover")
    piano = run.ok("want", "6", "lifting", "160").strip().splitlines()[-1]
    run.ok("handoff", piano[:12], "the", "yard", "gate")
    for _ in range(3):
        run.ok("give", "lesson", "50")
    lifts = {}
    for name, qty in (("ana", "2"), ("ben", "2"), ("cai", "2:1")):
        run = town.as_(name)
        lifts[name] = run.ok("give", qty, "lifting", "30").strip().splitlines()[-1]
        run.ok("want", "lesson", "31")
    first, second = town.daemon("cai", lambda: town.as_("mover").ok("clearing"))
    assert first == ""
    book = town.book()
    leg = next(l for l in book.loop_legs(book.loop_of(piano)) if l.want == piano)
    assert sorted(leg.gives) == sorted(lifts.values()) and len(leg.gives) == 3
    assert f"filled   {lifts['cai'][:12]}" in second and f"{town.who['cai']} gives lifting to {M}" in second
    for name in ("ana", "ben"):
        out = town.as_(name).ok("watch", "--once")
        assert f"filled   {lifts[name][:12]}" in out and f"{town.who[name]} gives lifting to {M}" in out
    out = town.as_("mover").ok("watch", "--once")
    lifters = ", ".join(sorted(town.who[n] for n in ("ana", "ben", "cai")))
    assert f"{M} receives lifting from {lifters}" in out
    first_give = book.get(leg.gives[0]).maker
    assert out.count("sealed to ") == 1 and f"sealed to {first_give}" in out
    for name in ("ana", "ben", "cai"):
        code, out, _ = town.as_(name)("watch", "--once")
        if town.who[name] == first_give:
            assert code == 0 and f"handoff  from {M}" in out and "the yard gate" in out
        else:
            assert code == 1 and "handoff" not in out                  # no gate code for the others
