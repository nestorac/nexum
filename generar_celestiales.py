#!/usr/bin/env python3
# generar_celestiales.py
#
# Genera ilustraciones para TODOS los "personajes" definidos como encabezados "### ..."
# en un fichero Markdown y crea un nuevo MD insertando la imagen tras cada personaje.
#
# Heurística para evitar categorías (p.ej. "### Patriarcas"):
#   - Si la primera línea NO vacía tras el encabezado empieza por "* " o "- " (lista),
#     se considera categoría y se omite.
#
# Uso:
#   ./generar_celestiales.py plano_celestial.md img/celestiales plano_celestial_conimg.md
#
# Env:
#   OPENAI_API_KEY (obligatoria)
#   OPENAI_ORG_ID  (opcional)
#   OPENAI_IMAGE_MODEL (por defecto gpt-image-1-mini)
#   OPENAI_IMAGE_SIZE  (por defecto 1024x1024)

import base64
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

OPENAI_URL = "https://api.openai.com/v1/images/generations"


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "personaje"


def next_nonempty_line(lines: list[str], start: int) -> tuple[int, str] | tuple[None, None]:
    for i in range(start, len(lines)):
        if lines[i].strip() != "":
            return i, lines[i]
    return None, None


def is_category_heading(lines: list[str], heading_line_idx: int) -> bool:
    """
    Considera "categoría" si lo primero no vacío después del ### es una lista:
      "* " o "- " (ojo: "*Texto*" NO es lista, porque no hay espacio tras '*').
    """
    ni, nl = next_nonempty_line(lines, heading_line_idx + 1)
    if nl is None:
        return True  # nada debajo, no aporta; lo tratamos como no-personaje
    return nl.startswith("* ") or nl.startswith("- ")


def find_current_h1(lines: list[str], idx: int) -> str | None:
    """
    Devuelve el último encabezado '# ...' anterior a idx, para usarlo como "panteón/sección".
    """
    for i in range(idx, -1, -1):
        m = re.match(r"^#\s+(.+)\s*$", lines[i])
        if m:
            return m.group(1).strip()
    return None


def extract_body_excerpt(lines: list[str], start_idx: int, end_idx: int) -> str:
    """
    Extrae texto cercano a la ficha (para prompt). Evita capturar demasiado.
    """
    chunk = []
    for i in range(start_idx, min(end_idx, start_idx + 60)):
        line = lines[i].rstrip("\n")
        if line.startswith("### "):
            break
        if not chunk and not line.strip():
            continue
        chunk.append(line)
        if len(chunk) > 12 and chunk[-1].strip() == "" and chunk[-2].strip() == "":
            break
    return "\n".join(chunk).strip()


def build_prompt(section_h1: str | None, name: str, body_excerpt: str) -> str:
    section = f"Contexto/panteón: {section_h1}. " if section_h1 else ""
    excerpt = body_excerpt.strip()
    if len(excerpt) > 700:
        excerpt = excerpt[:700] + "…"

    return (
        f"{section}"
        f"Ilustración estilo manga en escala de grises (blanco y negro), líneas limpias y elegantes, fondo blanco, "
        f"sin color. Retrato humano realista-estilizado de {name}, sin alas, sin cuernos, sin símbolos sobrenaturales "
        f"obvios; la espiritualidad se sugiere por la expresión y la presencia. Ropa cotidiana sobria. "
        f"Descripción para inspirar rasgos/actitud: {excerpt}"
    )


def generate_image_jpeg(prompt: str, out_path: Path, model: str, size: str, org_id: str | None):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Falta OPENAI_API_KEY en el entorno.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if org_id:
        headers["OpenAI-Organization"] = org_id

    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
        "output_format": "jpeg",
    }

    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=180)
    if not r.ok:
        raise RuntimeError(f"OpenAI HTTP {r.status_code}\n{r.text}")

    data = r.json()
    img_b64 = data["data"][0]["b64_json"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(img_b64))

    # Garantizar gris 100% (por si aparece algún tinte)
    if PIL_AVAILABLE:
        img = Image.open(out_path).convert("L")
        img.save(out_path, format="JPEG", quality=90, optimize=True)


def main():
    if len(sys.argv) != 4:
        print("Uso: ./generar_celestiales.py <in.md> <dir_img_out> <out.md>")
        sys.exit(2)

    in_md = Path(sys.argv[1])
    out_img_dir = Path(sys.argv[2])
    out_md = Path(sys.argv[3])

    model = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1-mini")
    size = os.environ.get("OPENAI_IMAGE_SIZE", "1024x1024")
    org_id = os.environ.get("OPENAI_ORG_ID")

    lines = in_md.read_text(encoding="utf-8").splitlines(True)

    # Localizar todos los "### ..."
    headings = []
    for idx, line in enumerate(lines):
        if line.startswith("### "):
            name = line[4:].strip()
            if not name:
                continue
            # Omitir categorías (### Patriarcas, etc.)
            if is_category_heading(lines, idx):
                continue
            headings.append((idx, name))

    if not headings:
        raise SystemExit("No se encontraron personajes '###' candidatos (no-categoría).")

    # Para delimitar el bloque de cada personaje
    heading_idxs = [h[0] for h in headings] + [len(lines)]

    inserts = []
    for k, (idx, name) in enumerate(headings):
        end_idx = heading_idxs[k + 1]
        section_h1 = find_current_h1(lines, idx)

        body_excerpt = extract_body_excerpt(lines, idx + 1, end_idx)
        slug = slugify(name)
        img_path = out_img_dir / f"{slug}.jpg"

        if not img_path.exists():
            prompt = build_prompt(section_h1, name, body_excerpt)
            
            print("----- PROMPT ENVIADO A LA IA -----")
            print(prompt)
            print("----- FIN PROMPT -----\n")
            print(f"[gen] {name} -> {img_path}")

            generate_image_jpeg(prompt, img_path, model=model, size=size, org_id=org_id)
            time.sleep(0.5)
        else:
            print(f"[skip] {name} (ya existe)")

        rel_img = img_path.as_posix()
        md_img_line = f"\n![]({rel_img})\n\n"
        inserts.append((idx + 1, md_img_line))

    out_lines = lines[:]
    for insert_at, text in sorted(inserts, key=lambda x: x[0], reverse=True):
        out_lines.insert(insert_at, text)

    out_md.write_text("".join(out_lines), encoding="utf-8")
    print(f"OK -> {out_md}  (imágenes en {out_img_dir})")


if __name__ == "__main__":
    main()
