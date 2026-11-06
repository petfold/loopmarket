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
- `30min/`: a 30-minute version of the same talk, with more loops and
  circulations, five slides on OntoDAG and the market page as a dynamic
  website on Swarm; its `notes.md` has the timing and speaker notes.

```
make            # slides.pdf (pdflatex, two passes)
make png        # PNG previews in png/
make clean      # everything but the PDF
```

Needs `pdflatex` with beamer, TikZ, `qrcode`, `tgheros` and booktabs.
The footers carry github.com/petfold/loopmarket and loopmarket.eth.limo
(slide 6: ontodag's; the title slide has no GitHub link there, since its
QR caption gives it). @petfold is beside the name on the title slide and
at the foot of slide 9. The QR codes on slides 1 and 9 point to the
loopmarket and ontodag repositories.
