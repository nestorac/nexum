# Bestiario: fichas a media página A4
# Uso: make -f Makefile bestiario   (desde oneshots/)

MD          := bestiario.md
METADATA    := metadata_bestiario.yaml
FILTER      := filtros/bestiario.lua
OUT_DIR     := tmp
PDF         := $(OUT_DIR)/bestiario.pdf

PANDOC      := pandoc
PDF_ENGINE  := xelatex

.PHONY: bestiario clean-bestiario

bestiario: $(PDF)

$(OUT_DIR):
	mkdir -p $(OUT_DIR)

$(PDF): $(MD) $(METADATA) $(FILTER) | $(OUT_DIR)
	$(PANDOC) "$(MD)" -o "$(PDF)" \
	  --from=markdown+smart \
	  --standalone \
	  --pdf-engine=$(PDF_ENGINE) \
	  --metadata-file=$(METADATA) \
	  --lua-filter=$(FILTER) \
	  --resource-path=.:img:img/monstruos

clean-bestiario:
	rm -f "$(PDF)"
