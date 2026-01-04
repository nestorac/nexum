#!/usr/bin/env python3
import os
import re
import time
import unicodedata
from pathlib import Path

from openai import OpenAI

# ----------------------------
# Configuración base
# ----------------------------
MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")

PROMPT_BASE = (
    "Retrato en escala de grises, estilo manga sencillo y elegante, línea limpia, "
    "sombreado suave, fondo blanco. Persona humana corriente, sin alas ni cuernos, "
    "sin rasgos sobrenaturales obvios. Sin texto, sin logos."
)

NEG_BASE = (
    "alas, cuernos, halo literal, demonio monstruoso, texto, tipografía, watermark, logo, "
    "color, gore, terror, hiperrealismo, 3d, render, manos deformes, mala anatomía"
)

# Reintentos simples ante fallos transitorios
MAX_RETRIES = 5
RETRY_SLEEP_SECONDS = 2

client = OpenAI()  # usa OPENAI_API_KEY en el entorno


# ----------------------------
# Utilidades
# ----------------------------
def slugify(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "sin-nombre"


def parse_md_sections(md_text: str):
    """
    Devuelve lista de tuplas (name, section_text) usando encabezados '### Nombre'.
    Ajusta el regex si tus encabezados difieren.
    """
    # Divide por encabezados "### "
    parts = re.split(r"\n(?=###\s+)", md_text)
    out = []
    for part in parts:
        m = re.match(r"###\s+(.+)\n", part)
        if not m:
            continue
        name = m.group(1).strip()
        out.append((name, part.strip()))
    return out


def call_openai_for_prompt(name: str, sheet: str) -> tuple[str, str]:
    """
    Devuelve (prompt, negative_prompt) como texto.
    Mantiene el output muy controlado para que sea fácil guardarlo en plano.
    """
    system = (
        "Transforma fichas de personaje en un prompt de ilustración.\n"
        "Requisitos estrictos:\n"
        f"- Estilo base fijo: {PROMPT_BASE}\n"
        "- El personaje debe parecer humano corriente (sin alas, cuernos, halos literales).\n"
        "- Fondo blanco o casi blanco; composición: plano medio o primer plano.\n"
        "- El prompt debe ser concreto (ropa, edad aprox., gesto, mirada, 1-2 detalles visuales).\n"
        "- Prohibido texto visible en la imagen (carteles, letras, símbolos tipográficos).\n"
        f"- Negative prompt base: {NEG_BASE}\n"
        "Salida estricta en DOS LÍNEAS y nada más:\n"
        "PROMPT: <texto>\n"
        "NEGATIVE: <texto>\n"
    )

    user = f"Nombre: {name}\n\nFicha completa:\n{sheet}"

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.responses.create(
                model=MODEL,
                store=False,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            text = (resp.output_text or "").strip()
            # Parseo robusto de las dos líneas
            prompt = ""
            neg = ""

            for line in text.splitlines():
                if line.startswith("PROMPT:"):
                    prompt = line[len("PROMPT:"):].strip()
                elif line.startswith("NEGATIVE:"):
                    neg = line[len("NEGATIVE:"):].strip()

            if not prompt:
                raise ValueError(f"Respuesta sin PROMPT válido. Respuesta: {text!r}")
            if not neg:
                # Si el modelo no devuelve negative, usamos base
                neg = NEG_BASE

            return prompt, neg

        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_SLEEP_SECONDS * attempt)
            else:
                raise

    raise last_err  # por si acaso


def write_plain_output(path: Path, entries: list[tuple[str, str, str]]):
    """
    entries: lista de (slug, prompt, negative)
    Formato INI-like en texto plano.
    """
    lines = []
    for slug, prompt, neg in entries:
        lines.append(f"[{slug}]")
        # Para evitar saltos de línea dentro del prompt, colapsamos espacios
        p = " ".join(prompt.split())
        n = " ".join(neg.split())
        lines.append(f"prompt={p}")
        lines.append(f"negative={n}")
        lines.append("")  # línea en blanco entre personajes

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


# ----------------------------
# Main
# ----------------------------
def main():
    import argparse

    ap = argparse.ArgumentParser(description="MD de celestiales -> prompts en texto plano")
    ap.add_argument("input_md", help="Fichero markdown con personajes (### Nombre ...)")
    ap.add_argument("-o", "--output", default="celestiales_prompts.txt", help="Salida texto plano")
    ap.add_argument("--limit", type=int, default=0, help="Procesar solo N personajes (0 = todos)")
    ap.add_argument("--sleep", type=float, default=0.0, help="Pausa entre llamadas (segundos)")
    args = ap.parse_args()

    md_path = Path(args.input_md)
    out_path = Path(args.output)

    md_text = md_path.read_text(encoding="utf-8")
    chars = parse_md_sections(md_text)

    if args.limit and args.limit > 0:
        chars = chars[:args.limit]

    results = []
    for idx, (name, section) in enumerate(chars, start=1):
        print(f"[{idx}/{len(chars)}] Generando prompt para: {name}")
        prompt, neg = call_openai_for_prompt(name, section)
        results.append((slugify(name), prompt, neg))
        if args.sleep > 0:
            time.sleep(args.sleep)

    write_plain_output(out_path, results)
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
