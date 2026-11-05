# Devcon 8 lightning talk

*The Loop Economy: A Universal Combinatorial Marketplace Without a
Platform*, Devcon 8, Mumbai, Lightning Stage, 6 November 2026, 11:00.

- `slides.pdf`: the deck, 16:9. Nine slides for five minutes, then four
  backup slides.
- `slides.tex`: its source. The figures are TikZ inside it, in the style
  of the September Swarm talk (`../talk/slides/figstyle.tex`).
- `talk.md`: the script with timings, where the deck departs from the
  brief, the facts it relies on, and the Devcon 8 guideline notes.
- `devcon.txt`: the brief.

```
make            # slides.pdf (pdflatex, two passes)
make png        # PNG previews in png/
make clean      # everything but the PDF
```

Needs `pdflatex` with beamer, TikZ, `qrcode`, `tgheros` and booktabs.
Every slide's footer carries https://github.com/petfold/loopmarket and
@petfold. The QR codes on slides 1 and 9 point to the loopmarket and
ontodag repositories.
