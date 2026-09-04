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
