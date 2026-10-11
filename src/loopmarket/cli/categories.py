"""Looking through the catalogue: `categories` (question 36, decided by
Peter 2026-10-11). Offers are written in the catalogue's words, so finding
one belongs in the tool the offers are made with; `odag` reads the same
catalogue with `-f`, but after the setup its own store is another one."""

from __future__ import annotations

import difflib

from .settings import _err, _want_limit, _want_render

#: How many near words an unknown one is shown.
NEAR = 8


def near_words(dag, word: str, n: int = NEAR) -> list[str]:
    """The catalogue's names nearest to `word`: those spelled like it, most
    alike first, then those containing it, shortest first."""
    names = [name for name in dag.nodes if name != dag.root.name]
    alike = difflib.get_close_matches(word, names, n, 0.7)
    containing = sorted((name for name in names if word in name),
                        key=lambda name: (len(name), name))
    near: list[str] = []
    for name in alike + containing:
        if name not in near and name != word:
            near.append(name)
    return near[:n]


def cmd_categories(args, session, out):
    from ontodag.browse import focus
    dag = session.catalogue.dag
    root = dag.root.name
    word = args.word
    node = focus(dag, word if word is not None else root)
    if node is None:
        near = near_words(dag, word)
        raise ValueError(f"{word} is not in the catalogue; "
                         + (f"near it: {', '.join(near)}" if near else "nothing near it"))
    above = [name for name in node["above"] if name != root]
    below = [(name, dag.nodes[name].descendant_count) for name in node["below"]]
    limit = _want_limit(args, out)
    shown = below[:limit] if limit else below
    if _want_render(args, out):
        if word is None:
            print(f"the top of the catalogue ({len(dag.nodes) - 1} categories in all):",
                  file=out)
        else:
            print(f"{word} is below: {', '.join(above)}" if above
                  else f"{word} is at the top of the catalogue", file=out)
            print(f"below {word}:" if below else f"nothing is below {word}", file=out)
        for name, count in shown:
            print(f"  {name}  ({count} below)" if count else f"  {name}", file=out)
    else:
        for name in above:
            print(f"above\t{name}", file=out)
        for name, count in shown:
            print(f"below\t{name}\t{count}", file=out)
    if limit and len(below) > limit:
        print(f"({len(below) - limit} more; -n 0 shows all)", file=_err())
    return 0
