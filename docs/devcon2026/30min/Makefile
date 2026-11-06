# The deck is one file: slides.tex, figures inline as TikZ. `make` builds slides.pdf.
LATEX := pdflatex -interaction=nonstopmode -halt-on-error

all: slides.pdf

slides.pdf: slides.tex
	$(LATEX) slides.tex >/dev/null && $(LATEX) slides.tex >/dev/null

png: slides.pdf
	mkdir -p png && pdftoppm -png -r 110 slides.pdf png/p

clean:
	rm -rf png *.aux *.log *.nav *.out *.snm *.toc *.vrb

.PHONY: all png clean
