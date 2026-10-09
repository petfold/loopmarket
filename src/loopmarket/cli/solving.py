"""Finding and clearing loops: `loops` (found on a pinned snapshot, never
cleared), `clearing` (the clearing house over the fold, its fills
committed to my book), `propose` (the same, each loop posted as a beat),
and the sealed-proposal beat: `commit`, `reveal`, `sealed`, `outcome`."""

from __future__ import annotations

import os

from ..clearing import MockClearing
from ..reads import Reads
from ..registry import LegRecord
from ..schema import q
from ..solver.agent import SolverAgent
from . import clients
from .clients import _chain_fills, _clearing_reads, _escrow_held, _gate_reads, _reads, _sealed_client
from .render import _leg_line, _print_loop
from .settings import _configured, _err, _home_dir, _peer_specs, _read_json, _write_json
from .spellings import _calendar_span


def cmd_loops(args, session, out):
    """Find on a pinned snapshot, print, never clear. Exit 1 when nothing
    is profitable, so `loop loops && loop clear` reads naturally."""
    fold = session.fold()
    agent = SolverAgent(fold, session.catalogue, clearing=None, solver_id="loop-cli", min_surplus=0.0,
                        reads=_reads(session), span=_calendar_span, **_gate_reads(session))
    root, loops = agent.find_loops(now=session.now)
    for loop in loops:
        _print_loop(loop, fold, out)
    return 0 if loops else 1


def cmd_propose(args, session, out):
    """Clear locally as `clearing` does and post every accepted loop as one
    beat on the clearing contract (P2, 2026-09-15): the book keeps the data,
    the chain the commitments and — after `finalize` — the fills. The
    bee_signer key pays the bond and is the submitter."""
    from ..clearing import ChainClearing
    now = session.now
    if _peer_specs() or _configured("registry"):
        session.book.absorb(session.fold())
        session.book.commit()
    book, ontology = session.book, session.catalogue
    client = clients._beat_client(session)
    reads = Reads(chain_fills=client.filled, escrow_held=_escrow_held(session))
    agent = SolverAgent(book, ontology,
                        ChainClearing(book, ontology, beat_client=client, clock=lambda: now,
                                      reads=reads, **_clearing_reads(session)),
                        solver_id="loop-cli", min_surplus=0.0, reads=reads, span=_calendar_span,
                        **_gate_reads(session))
    receipts = agent.step(now=now)
    posted = 0
    for r in receipts:
        if r.accepted:
            posted += 1
            print(f"posted {r.reason}: loop {r.loop_id[:16]}…", file=out)
        else:
            print(f"rejected {r.loop_id[:16]}…: {r.reason}", file=_err())
    if posted:
        print(f"book root {book.store.root}", file=out)
    return 0 if posted else 1


def _sealed_path(beat: int) -> str:
    return os.path.join(_home_dir(), "sealed", f"{beat}.json")


def cmd_commit(args, session, out):
    """Solve on the fold and seal the loops for the current beat (P2, the
    sealed-proposal beat, 2026-09-18): the bundle's bytes and salt stay in
    this home (`sealed/BEAT.json`, mine to reveal), the commitment goes to
    the sealed beat. One commitment per solver per beat. Exit 1: nothing to
    propose."""
    from ..auction import COMMIT, PHASES, bundle_bytes, seal
    from ..clearing import LoopProposal
    sealed = _sealed_client(session)
    beat = sealed.current()
    if sealed.phase(beat) != COMMIT:
        raise ValueError(f"beat {beat} is in its {PHASES[sealed.phase(beat)]} phase; commits open "
                         f"at block {sealed.window(beat + 1)[0]}")
    fold = session.fold()
    agent = SolverAgent(fold, session.catalogue, clearing=None, solver_id="loop-cli", min_surplus=0.0,
                        reads=Reads(chain_fills=_chain_fills(session)))
    root, loops = agent.find_loops(now=session.now)
    if not loops:
        print(f"beat {beat}: nothing to propose on root {root[:16]}…", file=_err())
        return 1
    proposals = [LoopProposal(loop, root, session.catalogue.root, "loop-cli", session.now)
                 for loop in loops]
    data = bundle_bytes(proposals)
    commitment, salt = seal(data)
    os.makedirs(os.path.dirname(_sealed_path(beat)), exist_ok=True)
    _write_json(_sealed_path(beat), {"beat": beat, "root": root, "proposal": data.hex(),
                                     "salt": salt.hex(), "loops": [p.circulation.loop_id for p in proposals]})
    sealed.commit(commitment)
    for loop in loops:
        _print_loop(loop, fold, out)
    print(f"committed beat {beat}: {len(loops)} loop(s) on root {root[:16]}…, "
          f"reveal from block {sealed.window(beat)[1]}", file=out)
    return 0


def cmd_reveal(args, session, out):
    """Open this session's sealed bundle for a beat in its reveal phase (the
    latest committed one unless BEAT is given)."""
    from ..auction import PHASES, REVEAL
    sealed = _sealed_client(session)
    if args.beat is not None:
        beat = int(args.beat)
    else:
        home = os.path.join(_home_dir(), "sealed")
        mine = sorted(int(f[:-5]) for f in os.listdir(home) if f.endswith(".json")) \
            if os.path.isdir(home) else []
        if not mine:
            raise ValueError("nothing committed from this home")
        beat = mine[-1]
    kept = _read_json(_sealed_path(beat), None)
    if not kept:
        raise ValueError(f"no sealed bundle for beat {beat} in this home")
    if sealed.phase(beat) != REVEAL:
        raise ValueError(f"beat {beat} is {PHASES[sealed.phase(beat)]}; reveals run from block "
                         f"{sealed.window(beat)[1]} to {sealed.window(beat)[2]}")
    sealed.reveal(beat, bytes.fromhex(kept["proposal"]), bytes.fromhex(kept["salt"]))
    print(f"revealed beat {beat}: {len(kept['loops'])} loop(s)", file=out)
    return 0


def cmd_sealed(args, session, out):
    """Where the sealed beat stands: the current beat, its phase and window,
    who committed and who revealed."""
    from ..auction import PHASES
    sealed = _sealed_client(session)
    beat = int(args.beat) if args.beat is not None else sealed.current()
    start, commit_end, end = sealed.window(beat)
    print(f"beat {beat}: {PHASES[sealed.phase(beat)]} (block {sealed.block()}; commits "
          f"{start}..{commit_end - 1}, reveals {commit_end}..{end - 1})", file=out)
    revealed = {s.lower() for s, _ in sealed.revealed(beat)} if sealed.phase(beat) >= 1 else set()
    for solver in sealed.committers(beat):
        print(f"  {solver} {'revealed' if solver.lower() in revealed else 'committed'}", file=out)
    o = sealed.outcome(beat)
    if o:
        print(f"  outcome recorded by {o['submitter']}: winners {o['winners'].hex()[:16]}…", file=out)
    return 0


def cmd_outcome(args, session, out):
    """Derive a closed beat's outcome and, unless `--check`, post the winners
    to the clearing contract and record it on the sealed beat: every
    revealed loop re-derived (U3), the baseline's loops as the reserve bid,
    the fairness filter, deterministic selection. The beat's snapshot is
    this session's fold. Exit 0 with winners, 1 with none, 2 when the beat
    is still open."""
    from ..auction import CLOSED, PHASES, baseline_proposals, outcome
    from ..clearing import ChainClearing
    sealed = _sealed_client(session)
    beat = int(args.beat) if args.beat is not None else max(sealed.current() - 1, 0)
    if sealed.phase(beat) != CLOSED:
        print(f"beat {beat} is {PHASES[sealed.phase(beat)]}: closes at block {sealed.window(beat)[2]}",
              file=_err())
        return 2
    now = session.now
    if _peer_specs() or _configured("registry"):
        session.book.absorb(session.fold())
        session.book.commit()
    book, ontology = session.book, session.catalogue
    root, snapshot = book.snapshot()
    revealed = sealed.revealed(beat)
    reads = Reads(chain_fills=_chain_fills(session))
    result = outcome(beat, revealed, snapshot, ontology, now=now, reads=reads,
                     baseline=baseline_proposals(snapshot, ontology, now=now, reads=reads))
    print(f"beat {beat}: {len(revealed)} revealed, {result.candidates} candidate loop(s), "
          f"{len(result.winners)} winner(s), score {float(result.score):.4f}", file=out)
    for lid, why in sorted(result.rejected.items()):
        print(f"  rejected {lid[:16]}…: {why}", file=out)
    for lid, why in sorted(result.dropped.items()):
        print(f"  dropped  {lid[:16]}…: {why}", file=out)
    for c in result.winners:
        _print_loop(c.proposal.loop, snapshot, out, prefix=f"  wins ({c.solver}) ")
    if args.check or not result.winners:
        return 0 if result.winners else 1
    clearing = ChainClearing(book, ontology, beat_client=clients._beat_client(session), clock=lambda: now)
    posted = []
    for c in result.winners:
        receipt = clearing.submit(c.proposal)
        if receipt.accepted:
            posted.append((c.loop_id, receipt.reason))
            print(f"  posted {receipt.reason}: loop {c.loop_id[:16]}…", file=out)
        else:
            print(f"  refused {c.loop_id[:16]}…: {receipt.reason}", file=_err())
    sealed.record(beat, result.revealed_set, result.winners_hash)
    book.store.put(f"auction/{beat}", {"v": 1, "beat": beat, "book_root": root,
                                       "revealed_set": result.revealed_set.hex(),
                                       "winners": [{"loop": lid, "beat": r} for lid, r in posted],
                                       "solver": "loop-cli"})
    book.commit()
    print(f"recorded beat {beat}: {len(posted)} loop(s) posted, book root {book.store.root}", file=out)
    return 0 if posted else 1


def cmd_clearing(args, session, out):
    """Run the clearing house locally: MockClearing over the fold, fills
    committed to my book. Named for what it does; `clear` means delete on
    every terminal, and publishing is not clearing (Peter, 2026-09-12);
    `clear` is still accepted, silently. With peers, my book first absorbs
    the fold — a clearing book legitimately contains what it cleared on
    (P1 §1)."""
    now = session.now
    if _peer_specs():
        session.book.absorb(session.fold())
        session.book.commit()
        print("book re-based on the fold", file=_err())
    book = session.book
    ontology = session.catalogue
    agent = SolverAgent(book, ontology,
                        MockClearing(book, ontology, clock=lambda: now, **_clearing_reads(session)),
                        solver_id="loop-cli", min_surplus=0.0, span=_calendar_span, **_gate_reads(session))
    receipts = agent.step(now=now)
    cleared = 0
    for r in receipts:
        if r.accepted:
            cleared += 1
            rec = book.store.get(f"loop/{r.loop_id}")
            print(f"cleared {r.loop_id[:16]}… surplus "
                  f"{100 * float(q(rec['surplus'])):.2f}%", file=out)
            for leg in LegRecord.of_loop(rec):
                gives = [book.get(g) for g in leg.gives]
                print("  " + _leg_line(gives, book.get(leg.want)), file=out)
        else:
            print(f"rejected {r.loop_id[:16]}…: {r.reason}", file=_err())
    if cleared:
        print(f"book root {book.store.root}", file=out)
    return 0 if cleared else 1
