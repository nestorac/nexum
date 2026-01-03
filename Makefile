# Makefile: un único MD -> un único PDF

MD          := personajes_jugadores.md
METADATA    := metadata.yaml
OUT_DIR     := tmp
PDF         := $(OUT_DIR)/personajes_jugadores.pdf

PANDOC      := pandoc
PDF_ENGINE  := xelatex

PANDOC_OPTS := \
  --from=markdown+smart \
  --standalone \
  --pdf-engine=$(PDF_ENGINE) \
  --metadata-file=$(METADATA)

.PHONY: all clean

all: $(PDF)

$(OUT_DIR):
	mkdir -p $(OUT_DIR)

$(PDF): $(MD) | $(OUT_DIR)
	$(PANDOC) "$(MD)" -o "$(PDF)" $(PANDOC_OPTS)

clean:
	rm -f "$(PDF)"
