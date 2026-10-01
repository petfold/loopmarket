"""A personal view of arbitrators (2026-10-01, `counterparty-gate.md` §7a):
from the escrow's log alone, the arbitrators named on reservations where I
or a maker I trust was a party, their rulings, and who among us lost under
one and chose it again — nothing outside the circle counted, so a puppet
that loses and returns flatters nobody."""

pytest = __import__("pytest")
pytest.importorskip("eth_hash", reason="reservation keys need eth-hash")

from loopmarket.escrow import reservation_key  # noqa: E402
from loopmarket.reputation import view  # noqa: E402

W, G, T, P, Q = "0xW", "0xG", "0xT", "0xP", "0xQ"     # me, a giver, a trusted maker, a puppet pair
J, K = "0xJudge", "0xKadi"
o = {n: f"{n:02x}" * 32 for n in range(1, 7)}
lp = {n: f"{n + 16:02x}" * 32 for n in range(1, 7)}


def _res(n, wanter, resolver, t):
    return {"offer": o[n], "loop": lp[n], "wanter": wanter, "resolver": resolver, "amount": 10, "time": t, "block": t}


def _end(n, to_wanter, t):
    return {"key": reservation_key(o[n], lp[n]), "toWanter": to_wanter, "toGiver": 10 - to_wanter, "how": "resolved",
            "time": t}


def test_a_loser_who_chooses_the_same_arbitrator_again_is_seen_and_a_puppet_is_not():
    deposited = [{"offer": o[1], "giver": G}, {"offer": o[2], "giver": G}, {"offer": o[3], "giver": T},
                 {"offer": o[4], "giver": Q}, {"offer": o[5], "giver": Q}, {"offer": o[6], "giver": G}]
    reserved = [_res(1, W, J, 10), _res(2, W, J, 30),       # I lose under J, then name J again
                _res(3, W, K, 12),                           # under K the giver T (trusted) loses
                _res(4, P, J, 14), _res(5, P, J, 40),        # a puppet loses under J and returns: not my circle
                _res(6, W, K, 5)]                            # before any loss: not "again"
    settled = [_end(1, 0, 20), _end(3, 10, 25), _end(4, 0, 22)]
    # when each party's offer on each leg was posted: my want on leg 2 after my loss at 20
    when = {(W, 1): 1, (W, 2): 25, (W, 3): 2, (W, 6): 1, (P, 4): 1, (P, 5): 30, (T, 3): 2, (G, 1): 1,
            (G, 2): 1, (G, 6): 1, (Q, 4): 1, (Q, 5): 1}
    nums = {o[n]: n for n in o}
    posted = lambda maker, offer, loop: when.get((maker, nums[offer]))
    rows = {a.key: a for a in view(reserved, settled, deposited, me=W, trusted=[T], posted=posted)}
    assert set(rows) == {J, K}
    assert rows[J].chosen_again == [W] and len(rows[J].legs) == 2           # the puppet's legs are not mine
    assert [(w, t) for w, _g, t, _m, _ in rows[J].rulings] == [(W, 0)]
    assert rows[K].chosen_again == [] and [t for *_, t, _m, _x in rows[K].rulings] == [10]
    # a later fill of an offer posted before the loss is no new choice
    early = {**when, (W, 2): 15}
    assert view(reserved, settled, deposited, me=W, posted=lambda m, off, lp_: early.get((m, nums[off])))[0] \
        .chosen_again == []
    # with no reader of postings, nothing counts as a return (an unknown posting counts nothing)
    assert all(a.chosen_again == [] for a in view(reserved, settled, deposited, me=W, trusted=[T]))
    # T's own view: the arbitrator it lost a ruling under, with no return
    (only,) = view(reserved, settled, deposited, me=T, posted=posted)
    assert only.key == K and only.chosen_again == []
