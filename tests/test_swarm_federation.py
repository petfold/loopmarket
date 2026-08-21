"""The federated book on a live Swarm: per-maker feeds, one fold, followers.

The live variant of the P1 federation gates (docs/plans/P1-federated-book.md
§9's rule: every multi-writer path ships a scorched-earth follower test).
Three makers publish their books under their *own* feeds and signers — the
maker IS the feed-owner address, so U8's primary layer is real here, not
declared — an aggregator folds them over the network, a solver settles the
triangle against the fold, the aggregator re-folds the settlement book in
and publishes its manifest under its own feed, and a follower armed with
nothing but (aggregator address, topic) reads the whole settled world back.

Conventions follow test_swarm_book.py: skipped unless BEE_API, BEE_BATCH
and BEE_SIGNER are set; a real purchased batch id so nothing auto-buys;
timestamped topics so reruns inherit nothing; throwaway per-maker signers
generated per run (feeds need no funds). Staging, provenance, index and
settlement stores ride Bee blobs with local pointers — no feed updates, so
the run is gentle on batch slots; settlement under its *own feed* is a
later refinement (the blobs and root are already network-borne).
"""

import os
import secrets
import time
import unittest

BEE_API = os.environ.get("BEE_API")
BEE_BATCH = os.environ.get("BEE_BATCH")
BEE_SIGNER = os.environ.get("BEE_SIGNER")

CATALOGUE = {
    "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"], "repair": ["service"],
    "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
    "local": [], "weekly": [], "vegetable-box": ["produce", "local", "weekly"],
}


@unittest.skipUnless(
    BEE_API and BEE_BATCH and BEE_SIGNER,
    "set BEE_API, BEE_BATCH and BEE_SIGNER to run the live federation test",
)
class TestFederatedBookOnLiveSwarm(unittest.TestCase):
    def test_publish_fold_settle_refold_and_follow(self):
        from recordstore import BeeBytesStore, RecordStore, swarm_store

        from loopmarket import (
            Aggregator, GeoDisc, MockSettlement, OfferRegistry, Ontology,
            SolverAgent, Thing, TimeWindow, ask, bid, maker_address,
        )
        from loopmarket.federation import SETTLEMENT

        topic = f"loopfed-{int(time.time())}"
        swarm = dict(api_url=BEE_API, stamp=BEE_BATCH)

        def blobstore():
            return RecordStore(BeeBytesStore(BEE_API, BEE_BATCH))

        catalogue = Ontology.persistent(
            swarm_store(f"{topic}-catalogue", signer=BEE_SIGNER, **swarm))
        catalogue.load(CATALOGUE)
        self.assertTrue(catalogue.commit())
        pins = catalogue.pins

        now = int(time.time())
        town = dict(service=TimeWindow(now, now + 120 * 86_400),
                    valid=TimeWindow(now - 3_600, now + 30 * 86_400), **pins)
        places = [GeoDisc(46.05, 14.50, 5_000), GeoDisc(46.10, 14.55, 15_000),
                  GeoDisc(46.06, 14.51, 4_000)]
        gives_wants = [("piano-lesson", ("produce", "local", "weekly")),
                       ("vegetable-box", ("bicycle-repair",)),
                       ("bicycle-repair", ("music-lesson",))]
        prices = [(100, 104), (50, 52), (80, 83)]

        # one feed per maker; the maker identity IS the feed-owner address
        books = {}
        for i in range(3):
            key = secrets.token_hex(32)
            addr = maker_address(key)
            reg = OfferRegistry(
                swarm_store(f"{topic}-book-{i}", signer=key, **swarm))
            gives, wants = gives_wants[i]
            p_ask, p_bid = prices[i]
            reg.publish_many([
                ask(addr, Thing((gives,), unit="course"), p_ask,
                    where=places[i], **town),
                bid(addr, Thing(wants, unit="course"), p_bid,
                    where=places[i], **town),
            ])
            self.assertTrue(reg.commit())
            books[addr] = (i, reg)

        # the aggregator folds over the network
        agg = Aggregator(blobstore, aggregator_id="agg-live")
        for addr, (_, reg) in books.items():
            agg.announce(addr, reg.store)
        m1 = agg.fold()
        self.assertTrue(m1.book_root)
        folded = OfferRegistry(
            RecordStore(BeeBytesStore(BEE_API, BEE_BATCH), root=m1.book_root))
        self.assertEqual(len(list(folded.offers(now=now))), 6)

        # settlement is its own writer over the fold (blobs on Swarm; the
        # root travels by hand until the settlement feed lands)
        settle = OfferRegistry(
            RecordStore(BeeBytesStore(BEE_API, BEE_BATCH), root=m1.book_root))
        agent = SolverAgent(settle, catalogue,
                            MockSettlement(settle, catalogue),
                            solver_id="fed-live-solver")
        settled = [r for r in agent.step() if r.accepted]
        self.assertEqual(len(settled), 1, settled)

        # re-fold with the settlement book; publish the manifest on the
        # aggregator's own feed
        agg.announce("settlement-0", settle.store, role=SETTLEMENT)
        m2 = agg.fold()
        self.assertNotEqual(m2.book_root, m1.book_root)
        agg_key = secrets.token_hex(32)
        agg_addr = maker_address(agg_key)
        manifest_feed = swarm_store(f"{topic}-manifest", signer=agg_key, **swarm)
        manifest_feed.put("manifest", {
            "aggregator": m2.aggregator, "book_root": m2.book_root,
            "provenance_root": m2.provenance_root, "index_root": m2.index_root,
            "announcement_root": m2.announcement_root,
        })
        self.assertTrue(manifest_feed.commit())

        # scorched-earth follower: (aggregator address, topic) and a Bee
        # node are the only inputs — no shared Python state
        feed = swarm_store(f"{topic}-manifest", owner=agg_addr, **swarm)
        manifest = feed.get("manifest")
        follower = OfferRegistry(RecordStore(
            BeeBytesStore(BEE_API, BEE_BATCH), root=manifest["book_root"]))
        loop_rec = follower.store.get(f"loop/{settled[0].loop_id}")
        self.assertEqual(len(loop_rec["legs"]), 3)
        self.assertEqual(len(list(follower.store.keys("fill/"))), 6)
        self.assertEqual(list(follower.offers(now=now)), [])
        follower.verify_loop_atomicity()

        # the fold's provenance attributes every offer to its maker's feed
        prov = RecordStore(BeeBytesStore(BEE_API, BEE_BATCH),
                           root=manifest["provenance_root"])
        for addr, (_, reg) in books.items():
            for offer in reg.offers(include_filled=True):
                self.assertEqual(prov.get(f"origin/{offer.offer_id}")["owner"],
                                 addr)

        # a per-maker book is independently followable by (owner, topic)
        some_addr, (i, _) = next(iter(books.items()))
        maker_view = OfferRegistry(
            swarm_store(f"{topic}-book-{i}", owner=some_addr, **swarm))
        self.assertEqual(len(list(maker_view.offers(include_filled=True))), 2)

        # and a second solver pass over the followed fold settles nothing
        second = SolverAgent(follower, catalogue,
                             MockSettlement(follower, catalogue),
                             solver_id="second")
        self.assertEqual([r for r in second.step() if r.accepted], [])


if __name__ == "__main__":
    unittest.main()
