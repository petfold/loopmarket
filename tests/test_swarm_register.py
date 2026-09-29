"""A register on a LIVE Swarm feed, read by the command line (2026-09-29
night): the attester's register is a book of its own on Swarm — its roots
in the feed, each naming its predecessor (R5) — and a session reading it by
spec (`set registers ID=swarm:TOPIC@OWNER`) opens it at the feed's tip. The
gate passes a licensed dentist over it; after the register revokes the
statement, a proposal still pinning the earlier root is refused for what
the newer root says, and the newer root extends the earlier one.

Skips unless BEE_API, BEE_BATCH and BEE_SIGNER are all set (house
convention: a real purchased batch, so nothing auto-buys; a throwaway key).
Topics are timestamped, so reruns never inherit an old register.
"""

import os
import time
import unittest

BEE_API = os.environ.get("BEE_API")
BEE_BATCH = os.environ.get("BEE_BATCH")
BEE_SIGNER = os.environ.get("BEE_SIGNER")


@unittest.skipUnless(BEE_API and BEE_BATCH and BEE_SIGNER,
                     "set BEE_API, BEE_BATCH and BEE_SIGNER to run the live Swarm register test")
class TestRegisterOnLiveSwarm(unittest.TestCase):
    def test_the_cli_reads_a_register_at_its_feed_tip(self):
        from ontodag import OntoDAG
        from recordstore import MemoryBytesStore, RecordStore

        from loopmarket import Credential, OfferRegistry, Ontology, Requires, Statement, Thing, TimeWindow, give, want
        from loopmarket import cli
        from loopmarket.gate import CounterpartyGate
        from loopmarket.register import Register
        from loopmarket.registry import swarm_offer_book
        from loopmarket.sigs import maker_address

        now = int(time.time())
        owner = maker_address(BEE_SIGNER)
        topic = f"register-{now}"
        reg = Register(swarm_offer_book(topic, api_url=BEE_API, stamp=BEE_BATCH, signer=BEE_SIGNER).store)
        dentist = "0x" + "d0" * 20
        st = Statement(subject=dentist, category="dentist-licensed", issuer=owner, kind="attested",
                       as_of=now - 86_400, until=now + 30 * 86_400, evidence="ee" * 32, path=(owner,),
                       paid_by="subject")
        reg.issue(st.statement_id, now)
        reg.heartbeat(now)
        first = reg.commit()
        self.assertEqual(reg.seq, 0)

        # the reading session: registers by spec, nothing else configured
        cli._OVERRIDES.clear()
        os.environ["LOOP_REGISTERS"] = f"{owner}=swarm:{topic}@{owner}"
        try:
            session = cli.Session()
            regs = cli._registers(session)
            self.assertEqual(regs[owner].root, first)
            self.assertEqual(regs[owner].status(st.statement_id)["state"], "issued")

            cat = Ontology(OntoDAG()).load({"dentistry": [], "dentist-licensed": []})
            book = OfferRegistry(RecordStore(MemoryBytesStore()))
            V = dict(valid=TimeWindow(now - 60, now + 86_400))
            g = give(dentist, Thing(("dentistry",), 1, "visit"), 30, **V, nonce=1)
            w = want("0x" + "a0" * 20, Thing(("dentistry",), 1, "visit"), 40, **V, nonce=2,
                     requires=Requires(counterparty=(Credential("dentist-licensed", ("attested",),
                                                                roots=(owner,), max_root_age=3_600),)))
            book.publish_many([g, w])
            book.present(st)
            book.commit()
            gate = CounterpartyGate.over(book, regs, now=now + 5, latest=regs.get)
            self.assertEqual(gate.faults(w, g, cat, window=(now + 5, now + 5)), [])

            reg.revoke(st.statement_id, now + 10)
            reg.heartbeat(now + 10)
            second = reg.commit()
            self.assertEqual(reg.seq, 1)
            session._registers = None                   # a new command: the registers' heads afresh
            regs = cli._registers(session)
            self.assertEqual(regs[owner].root, second)
            self.assertTrue(regs[owner].extends(first))  # the revocation is an extension (R5)
            pinned = cli._register_at(session)(owner, first)
            stale = CounterpartyGate.over(book, {owner: pinned}, now=now + 20, latest=regs.get)
            faults = stale.faults(w, g, cat, window=(now + 20, now + 20))
            self.assertTrue(faults and "revoked under" in faults[0] and "newest root" in faults[0], faults)
        finally:
            os.environ.pop("LOOP_REGISTERS", None)


if __name__ == "__main__":
    unittest.main()
