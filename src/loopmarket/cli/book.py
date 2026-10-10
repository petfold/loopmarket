"""Reading the book and the fold, and the announcement channel: `offers`,
`show`, `matches`, `mine`, `status`, `announce`, `announced`, `fold`, and
the record streams `export` and `import`."""

from __future__ import annotations

import json
import sys

from ..matching import candidate_matches
from ..schema import Offer
from .options import _option_demand, _options_on
from .render import _concepts, _num, _print_table, _row, _state, render_offer
from .settings import _book_spec, _configured, _err, _peer_specs
from .spellings import _iso
from .stores import Session, _resolve_id


def cmd_mine(args, session, out):
    now = session.now
    book = session._read_by_chain(session.book)       # where a chain is set, its fills decide
    rows = [_row(o, now, book)
            for o in book.offers(include_filled=True)
            if o.maker == session.maker]
    rows.sort(key=lambda r: r[0])
    _print_table(rows, args, out)
    return 0


def cmd_offers(args, session, out):
    now = session.now
    fold = session.fold()
    rows = []
    ontology = session.catalogue if args.categories else None
    for o in fold.offers(now=now):
        if ontology is not None and \
                not any(ontology.satisfies(p.concepts, args.categories) for p in o.parts):
            continue
        rows.append(_row(o, now, fold))
    rows.sort(key=lambda r: r[0])
    _print_table(rows, args, out)
    return 0


def cmd_show(args, session, out):
    oid = _resolve_id(session, args.id, mine_only=False)
    fold = session.fold()
    offer = fold.get(oid)
    now = session.now
    print(render_offer(offer), file=out)
    print(f"  state    {_state(fold, offer, now)}", file=out)
    # options (2026-09-29): what may be held of it, and who would pay to hold it
    for o in _options_on(fold, offer, now):
        print(f"  option   {o.offer_id[:12]}: holdable until {_iso(o.exercise.end)} "
              f"for {_num(o.tokens.amount)} (on {o.maker}'s scale)", file=out)
    if offer.maker == session.maker:
        for w in _option_demand(session, fold, offer, now):
            print(f"  demand   {w.maker} wants to hold a thing like this ({_concepts(w)}, bids "
                  f"{_num(w.tokens.amount)} on their scale): loop option {oid[:12]} --for {w.offer_id[:12]}",
                  file=out)
    return 0


def _matches(session: Session):
    now = session.now
    fold = session.fold()
    return list(candidate_matches(list(fold.offers(now=now)),
                                  session.catalogue, now=now))


def cmd_matches(args, session, out):
    rows = [f"{m.giver} gives {' '.join(m.give.thing.concepts)} to "
            f"{m.receiver} (wants {' '.join(m.want.thing.concepts)}) "
            f"rate {float(m.rate):.4g}  {m.give.offer_id[:12]}>{m.want.offer_id[:12]}"
            for m in _matches(session)]
    rows.sort()
    for r in rows:
        print(r, file=out)
    return 0 if rows else 1


def _owner_for_announcing(session) -> str:
    """Who announces: on chain the transaction's sender, i.e. bee_signer's
    address; on the file and memory channels the configured maker."""
    key = _configured("bee_signer")
    if key:
        try:
            from ..sigs import maker_address
            return maker_address(key)
        except Exception:
            pass
    maker = _configured("maker")
    if not maker:
        raise ValueError("announcing needs an identity: set bee_signer (or maker)")
    return maker


def cmd_announce(args, session, out):
    """Say "my book is here" on the announcement channel: the book spec
    without its owner (`swarm:TOPIC`, or `rs:PATH` on a file channel), so
    every reader of the channel folds it as mine."""
    spec = _book_spec()
    if spec.startswith("swarm:") and "@" in spec:
        raise ValueError(f"{spec}: announce a book you write, not one you follow")
    role = args.role or "maker"
    ann = session.announcements.announce(spec, role, owner=_owner_for_announcing(session))
    print(f"announced {ann.owner} {ann.book} ({ann.role})", file=out)
    return 0


def cmd_announced(args, session, out):
    """The standing announcements: owner, book, role."""
    for ann in session.announcements.announced():
        print(f"{ann.owner} {ann.book} {ann.role}", file=out)
    return 0


def cmd_fold(args, session, out):
    """Fold the announced books and my peers myself and print the root —
    the number any aggregator's manifest must agree with (T14) — and, on
    stderr, what the fold rejected and why: a record outside its writer's
    authority, a loop of a clearing book that fails the re-check (review
    item 9), a book it could not read."""
    fold = session.fold()
    every = list(fold.offers(include_filled=True))
    print(f"book root {fold.store.root or '(empty)'}", file=out)
    print(f"offers {len(every)}", file=_err())
    for owner, key, reason in session.rejections:
        print(f"rejected {owner} {key}: {reason}", file=_err())
    return 0


def cmd_status(args, session, out):
    print(f"book = {_book_spec()}", file=out)
    book = session.book
    print(f"book root = {book.store.root or '(empty)'}", file=out)
    every = list(book.offers(include_filled=True))
    print(f"offers = {len(every)} "
          f"(filled {sum(book.is_filled(o.offer_id) for o in every)}, "
          f"withdrawn {sum(book.is_withdrawn(o.offer_id) for o in every)})",
          file=out)
    print(f"catalogue = {session.catalogue_session.describe()}", file=out)
    ontology = session.catalogue
    print(f"catalogue root = {ontology.root or '(unpinned)'}", file=out)
    print(f"categories = {len(ontology.dag.nodes)}", file=out)
    print(f"registry = {_configured('registry') or '(none)'}", file=out)
    print(f"peers = {', '.join(_peer_specs()) or '(none)'}", file=out)
    for key in ("maker", "terms", "valid", "confirm"):
        print(f"{key} = {_configured(key) or '(unset)'}", file=out)
    print(f"now = {_iso(session.now)}"
          + ("" if _configured("now") else " (wall clock)"), file=out)
    return 0


def cmd_export(args, session, out):
    for o in session.book.offers(include_filled=True):
        print(json.dumps(o.to_record(), sort_keys=True,
                         separators=(",", ":")), file=out)
    return 0


def cmd_import(args, session, out):
    stream = open(args.file, encoding="utf-8") if args.file else sys.stdin
    try:
        n = 0
        for line in stream:
            line = line.strip()
            if not line:
                continue
            session.book.publish(Offer.from_record(json.loads(line)))
            n += 1
    finally:
        if args.file:
            stream.close()
    if n:
        session.book.commit()
    print(n, file=_err())
    return 0
