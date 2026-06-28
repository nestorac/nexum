# Makefile: un único MD -> un único PDF

MD          := personajes_jugadores.md
METADATA    := metadata.yaml
OUT_DIR     := tmp
PDF         := $(OUT_DIR)/personajes_jugadores.pdf

CELESTIALES_MD_IN   := test.md
CELESTIALES_MD_OUT  := test_out.md
CELESTIALES_IMG_DIR := img/celestiales
CELESTIALES_SCRIPT  := generar_celestiales.py

PANDOC      := pandoc
PDF_ENGINE  := xelatex

PANDOC_OPTS := \
  --from=markdown+smart \
  --standalone \
  --pdf-engine=$(PDF_ENGINE) \
  --metadata-file=$(METADATA) \
  --lua-filter=filtros/pj.lua

.PHONY: all clean

all: $(PDF)

celestiales_img:
	@echo ">> Generando ilustraciones de personajes celestiales"
	mkdir -p $(CELESTIALES_IMG_DIR)
	./$(CELESTIALES_SCRIPT) \
		$(CELESTIALES_MD_IN) \
		$(CELESTIALES_IMG_DIR) \
		$(CELESTIALES_MD_OUT)
	@echo ">> OK: $(CELESTIALES_MD_OUT)"

$(OUT_DIR):
	mkdir -p $(OUT_DIR)

$(PDF): $(MD) | $(OUT_DIR)
	$(PANDOC) "$(MD)" -o "$(PDF)" $(PANDOC_OPTS)

clean:
	rm -f "$(PDF)"
