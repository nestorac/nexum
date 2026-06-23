# Makefile - Aventura 6: Nexum Tropical

MD      := 06_nexum_tropical.md
PDF     := 06_nexum_tropical.pdf

PANDOC  := pandoc

# Opciones de pandoc (puedes ajustar el margen aquí)
PANDOC_OPTS := --pdf-engine=pdflatex \
               -V papersize=a4 \
               -V geometry:margin=1cm \
               -V fontsize=11pt \
               -V lang=es \
               --syntax-highlighting=tango \
               --metadata title="Aventura 6: Nexum Tropical - Paraíso Eterno"

.PHONY: all pdf clean

all: pdf

pdf: $(PDF)

$(PDF): $(MD)
	@echo "→ Generando PDF..."
	$(PANDOC) $(MD) -o $(PDF) $(PANDOC_OPTS)
	@echo "✓ PDF generado: $(PDF)"

clean:
	rm -f $(PDF)
	@echo "✓ PDF eliminado"
