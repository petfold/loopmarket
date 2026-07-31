"""P1's headline, as a reproducible test: the triangle demo settling on a
LIVE Swarm book — blobs on a Bee node, the book's head in a signed feed,
the catalogue equally on Swarm with offers pinning its root end-to-end.

Skips unless BEE_API, BEE_BATCH and BEE_SIGNER are all set (house
convention: always pass a real purchased batch so nothing auto-buys):

    BEE_API=http://localhost:1633 BEE_BATCH=<batchID> \
    BEE_SIGNER=<0x-hex-private-key> \
        python3 -m pytest tests/test_swarm_book.py -v

Feed topics are timestamped so reruns with the same key don't inherit an
old book. Costs a handful of feed writes on the batch; use a throwaway key.
"""

import os
import time
import unittest

from loopmarket import (
    GeoDisc, MockSettlement, Ontology, SolverAgent, Thing, TimeWindow,
    ask, bid,
)
from loopmarket.registry import swarm_offer_book

BEE_API = os.environ.get("BEE_API")
BEE_BATCH = os.environ.get("BEE_BATCH")
BEE_SIGNER = os.environ.get("BEE_SIGNER")

CATALOGUE = {
    "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"], "repair": ["service"],
    "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
    "local": [], "weekly": [],
    "vegetable-box": ["produce", "local", "weekly"],
}


@unittest.skipUnless(
    BEE_API and BEE_BATCH and BEE_SIGNER,
    "set BEE_API, BEE_BATCH and BEE_SIGNER to run the live Swarm book test",
)
class TestTriangleOnLiveSwarmBook(unittest.TestCase):
    def test_publish_solve_settle_and_follow(self):
        from recordstore import swarm_store

        topic = f"loopbook-{int(time.time())}"
        swarm = dict(api_url=BEE_API, stamp=BEE_BATCH, signer=BEE_SIGNER)

        # The shared catalogue lives on Swarm too; offers pin its root.
        catalogue = Ontology.persistent(
            swarm_store(f"{topic}-catalogue", **swarm))
        catalogue.load(CATALOGUE)
        ontology_root = catalogue.commit()
        self.assertTrue(ontology_root)

        registry = swarm_offer_book(topic, **swarm)
        now = int(time.time())
        town = dict(service=TimeWindow(now, now + 120 * 86_400),
                    valid=TimeWindow(now - 3_600, now + 30 * 86_400),
                    ontology_root=ontology_root)
        offers = [
            ask("amara", Thing(("piano-lesson",), unit="course"), 100,
                where=GeoDisc(46.05, 14.50, 5_000), **town),
            bid("amara", Thing(("produce", "local", "weekly"),
                               unit="course"), 104,
                where=GeoDisc(46.05, 14.50, 5_000), **town),
            ask("bruno", Thing(("vegetable-box",), unit="course"), 50,
                where=GeoDisc(46.10, 14.55, 15_000), **town),
            bid("bruno", Thing(("bicycle-repair",), unit="course"), 52,
                where=GeoDisc(46.10, 14.55, 15_000), **town),
            ask("chen", Thing(("bicycle-repair",), unit="course"), 80,
                where=GeoDisc(46.06, 14.51, 4_000), **town),
            bid("chen", Thing(("music-lesson",), unit="course"), 83,
                where=GeoDisc(46.06, 14.51, 4_000), **town),
        ]
        registry.publish_many(offers)
        book_root = registry.commit()
        self.assertTrue(book_root)

        agent = SolverAgent(registry=registry, ontology=catalogue,
                            settlement=MockSettlement(registry, catalogue),
                            solver_id="live-solver")
        receipts = agent.step()
        settled = [r for r in receipts if r.accepted]
        self.assertEqual(len(settled), 1, receipts)
        loop_record = registry.store.get(f"loop/{settled[0].loop_id}")
        self.assertEqual(len(loop_record["legs"]), 3)
        self.assertGreater(loop_record["surplus"], 0)

        # Scorched-earth follow: a brand-new registry over the same feed —
        # no shared Python state, the head comes back from the network.
        again = swarm_offer_book(topic, **swarm)
        again_loop = again.store.get(f"loop/{settled[0].loop_id}")
        self.assertEqual(again_loop["legs"], loop_record["legs"])
        fills = list(again.store.keys("fill/"))
        self.assertEqual(len(fills), 6)   # all six offers claimed atomically

        # And the settled book yields nothing on a second pass.
        second = SolverAgent(registry=again, ontology=catalogue,
                             settlement=MockSettlement(again, catalogue),
                             solver_id="second-solver")
        self.assertEqual([r for r in second.step() if r.accepted], [])


if __name__ == "__main__":
    unittest.main()
