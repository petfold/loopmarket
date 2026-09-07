# Slides

Beamer deck for the September 2026 Swarm talk; speaker notes and timing
live in `../swarm-talk-2026-09.md`.

```
make            # figures (standalone TikZ + Graphviz via dot2tex), then slides.pdf
make figures    # only the figures: figures/fig-*.pdf, figures/dot-*.pdf
make png        # PNG previews of every figure in figures/png/
make clean
```

Needs `pdflatex` with beamer, tikz, pgfplots, standalone, booktabs;
`dot` (Graphviz) and `dot2tex` for the three `figures/dot/*.dot` sources.
Style lives in one place, `figstyle.tex` (colours, node and arrow
styles), shared by every figure and the deck. More figures are drawn
than the deck uses; pick from `figures/png/`.

v2 (2026-09-07) revised the deck after `../issues.txt`: barter-first loop,
private-scale star (`fig-scale`), OntoDAG multi-parent examples
(`fig-ontodag-features`, edges taken from ontodag's `core` pack), vertical
catalogue figures, the toothbrush (`fig-toothbrush`, `fig-loop-delivery`),
multi-hop chains (`fig-chain`), solvers (`fig-solvers`), factbond
(`fig-factbond`), and a who-pays-for-what table. `fig-liquidity` moved to
backup.
