# Figures are standalone TikZ (figures/fig-*.tex) or Graphviz via dot2tex
# (figures/dot/*.dot); the deck is slides.tex.  `make` builds everything.
FIGS   := $(patsubst figures/%.tex,figures/%.pdf,$(wildcard figures/fig-*.tex))
DOTS   := $(patsubst figures/dot/%.dot,figures/dot-%.pdf,$(wildcard figures/dot/*.dot))
LATEX  := pdflatex -interaction=nonstopmode -halt-on-error

all: slides.pdf
figures: $(FIGS) $(DOTS)

figures/fig-%.pdf: figures/fig-%.tex figures/preamble.tex figstyle.tex
	cd figures && $(LATEX) -output-directory=build fig-$*.tex >/dev/null && cp build/fig-$*.pdf .

figures/dot-%.pdf: figures/dot/%.dot figures/dot/wrap.tex figstyle.tex
	cd figures/dot && dot2tex --figonly -ftikz --styleonly --texmode raw --autosize \
	  --prog $(if $(filter loop3,$*),circo,dot) $*.dot > $*-body.tex && \
	  $(LATEX) -jobname=dot-$* "\def\dotfig{$*-body.tex}\input{wrap.tex}" >/dev/null && mv dot-$*.pdf ..

slides.pdf: slides.tex figstyle.tex $(FIGS) $(DOTS)
	$(LATEX) slides.tex >/dev/null && $(LATEX) slides.tex >/dev/null

png: figures
	mkdir -p figures/png && for f in figures/*.pdf; do pdftoppm -png -r 110 -singlefile $$f figures/png/$$(basename $$f .pdf); done

clean:
	rm -rf figures/build/* figures/png figures/dot/*-body.tex figures/dot/*.aux figures/dot/*.log figures/dot/*.err *.aux *.log *.nav *.out *.snm *.toc *.vrb
