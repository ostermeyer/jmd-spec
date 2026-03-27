PAPER   := jmd-paper
TEXFILE := $(PAPER).tex
PDF     := $(PAPER).pdf

# Auxiliary files produced by LaTeX / BibTeX
AUX := $(PAPER).aux $(PAPER).bbl $(PAPER).blg \
       $(PAPER).log $(PAPER).out $(PAPER).toc \
       $(PAPER).lof $(PAPER).lot $(PAPER).fls \
       $(PAPER).fdb_latexmk $(PAPER).synctex.gz

.PHONY: all clean

all: $(PDF)

# --- latexmk (handles pdflatex + bibtex reruns automatically) ---------------
$(PDF): $(TEXFILE) $(PAPER).bib acl.sty acl_natbib.bst
	latexmk -f -pdf -bibtex $(TEXFILE); test -f $(PDF)

# --- tectonic (uncomment if installed: self-contained, auto-downloads) ------
# $(PDF): $(TEXFILE) $(PAPER).bib
# 	tectonic $(TEXFILE)

clean:
	rm -f $(AUX) $(PDF)
