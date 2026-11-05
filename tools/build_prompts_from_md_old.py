#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
build_prompts_from_md.py

Genera un INI (test_prompts.txt) con:
  [section-id]
  prompt=...
  negative=...

Pero en vez de construir prompt localmente, envía la ficha completa del personaje
a la API de OpenAI para que el modelo genere un prompt preciso y diferente
por personaje.

Requisitos:
  pip install openai
  export OPENAI_API_KEY="..."

Uso:
  python3 build_prompts_from_md.py celestiales.md -o test_prompts.txt --model gpt-5.2
  python3 build_prompts_from_md.py docs/*.md -o test_prompts.txt --cache .cache/prompts.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openai import OpenAI


HEADER_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")  # ## o ###
ITALIC_SUBTITLE_RE = re.compile(r"^\s*\*(.+?)\*\s*$")  # *El mensajero.*
FIELD_RE = re.compile(r"^\s*(prompt|negative)\s*=\s*(.+?)\s*$", re.IGNORECASE)


DEFAULT_NEGATIVE = (
    "alas, cuernos, halo literal, iconografía religiosa explícita, demonio monstruoso, "
    "texto, tipografía, watermark, logo, color, gore, terror, hiperrealismo, 3d, render, "
    "manos deformes, mala anatomía"
)

def eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def truncate(s: str, max_chars: int = 4000) -> str:
    s = s.rstrip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + f"\n...[truncado: {len(s) - max_chars} chars]"


def pretty_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = (
        s.replace("á", "a").replace("é", "e").replace("í", "i")
         .replace("ó", "o").replace("ú", "u").replace("ü", "u")
         .replace("ñ", "n")
    )
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_clean_name(header_line: str) -> str:
    return collapse_spaces(re.sub(r"^\s*#+\s*", "", header_line)).strip()


def split_sections(md_text: str) -> List[Tuple[str, str]]:
    lines = md_text.splitlines()
    indices = [i for i, ln in enumerate(lines) if HEADER_RE.match(ln)]
    if not indices:
        return []
    out: List[Tuple[str, str]] = []
    for idx, start in enumerate(indices):
        end = indices[idx + 1] if idx + 1 < len(indices) else len(lines)
        header = lines[start]
        section = "\n".join(lines[start + 1:end]).strip("\n")
        out.append((header, section))
    return out


def extract_subtitle(section_text: str) -> Tuple[Optional[str], str]:
    lines = section_text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return None, section_text
    m = ITALIC_SUBTITLE_RE.match(lines[i])
    if not m:
        return None, section_text
    subtitle = m.group(1).strip()
    body = "\n".join(lines[:i] + lines[i + 1:]).strip()
    return subtitle, body


def extract_existing_fields(section_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Si tu MD ya tiene prompt=/negative=, los leemos.
    Pero en el modo 'api', normalmente los ignorarás; se dejan por compatibilidad.
    """
    prompt = None
    negative = None
    for ln in section_text.splitlines():
        m = FIELD_RE.match(ln)
        if not m:
            continue
        k = m.group(1).lower()
        v = m.group(2).strip()
        if k == "prompt":
            prompt = v
        elif k == "negative":
            negative = v
    return prompt, negative


@dataclass
class CharacterBlock:
    header: str
    subtitle: Optional[str]
    body: str
    raw_section_text: str
    prompt: Optional[str]
    negative: Optional[str]


def parse_characters_from_md(md_text: str) -> List[CharacterBlock]:
    chars: List[CharacterBlock] = []
    for header_line, section_text in split_sections(md_text):
        header = extract_clean_name(header_line)
        subtitle, body = extract_subtitle(section_text)
        prompt, negative = extract_existing_fields(section_text)
        chars.append(
            CharacterBlock(
                header=header,
                subtitle=subtitle,
                body=body,
                raw_section_text=section_text,
                prompt=prompt,
                negative=negative,
            )
        )
    return chars


def content_fingerprint(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_cache(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(path: Path, cache: Dict[str, Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def build_character_sheet_payload(ch: CharacterBlock) -> str:
    """
    Esto es lo que se manda a la IA: ficha completa “tal cual” (lo más importante),
    más un pequeño encabezado explícito para evitar ambigüedad.
    """
    parts = []
    parts.append(f"Nombre del personaje: {ch.header}")
    if ch.subtitle:
        parts.append(f"Epíteto/rol: {ch.subtitle}")
    parts.append("Ficha completa (Markdown):")
    parts.append(ch.raw_section_text.strip())
    return "\n".join(parts).strip()

def call_model_for_prompt(
    client: OpenAI,
    model: str,
    character_sheet: str,
    default_negative: str,
    temperature: float,
    verbose: bool = False,
    dry_run: bool = False,
    max_retries: int = 4,
    retry_sleep_s: float = 1.5,
) -> Tuple[str, str]:
    """
    Llama a la Responses API pidiendo JSON estricto (Structured Outputs).
    Con verbose=True, imprime payload y respuesta.
    Con dry_run=True, no hace la llamada.
    """

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "prompt": {"type": "string"},
            "negative": {"type": "string"},
        },
        "required": ["prompt", "negative"],
    }

    system_instructions = (
        "Eres un generador de prompts para ilustración. "
        "Convierte una ficha de personaje en un prompt MUY específico y distinto.\n"
        "Reglas obligatorias:\n"
        "1) El prompt DEBE incluir literalmente el nombre del personaje (ej: 'Arcángel Gabriel').\n"
        "2) Debe incluir rasgos concretos basados en la ficha (mínimo 6 detalles observables/coherentes). "
        "Evita vaguedades sin concretar.\n"
        "3) Estética: humano corriente, sin alas/cuernos/halo literal, sin iconografía religiosa explícita.\n"
        "4) Fondo blanco, escala de grises, estilo manga sobrio y elegante, línea limpia, sombreado suave.\n"
        "5) No incluyas texto dentro de la imagen.\n"
        "Devuelve SOLO JSON válido según el schema."
    )

    user_instructions = (
        "A partir de la ficha, genera:\n"
        "- prompt: una sola línea, completa y precisa.\n"
        "- negative: lista separada por comas (puedes reutilizar y ampliar el negativo base).\n\n"
        f"Negativo base (puedes ampliarlo): {default_negative}\n\n"
        f"FICHA:\n{character_sheet}"
    )

    # Payload “real” que va al API
    request_payload = {
        "model": model,
        "input": [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": user_instructions},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "prompt_bundle",
                "strict": True,
                "schema": schema,
            }
        },
        "temperature": temperature,
    }

    if verbose:
        eprint("\n[API] Payload (lo que se envía):")
        # No imprimimos la API key nunca (no está en payload, pero por disciplina)
        eprint(truncate(pretty_json(request_payload), 12000))

    if dry_run:
        # Devuelve algo "placeholder" para no romper el flujo si lo quieres usar
        return ("DRY_RUN: prompt no generado (se omitió llamada API)", default_negative)

    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.responses.create(**request_payload)

            raw_text = resp.output_text or ""
            if verbose:
                eprint("\n[API] Respuesta (output_text bruto):")
                eprint(truncate(raw_text, 12000))

            data = json.loads(raw_text)

            prompt = collapse_spaces(data.get("prompt", ""))
            negative = collapse_spaces(data.get("negative", "")) or default_negative

            # Validaciones anti-genérico (endurece tu requisito)
            # Si quieres ser aún más estricto, sube el mínimo de longitud.
            if len(prompt) < 260:
                raise ValueError(f"Prompt demasiado corto ({len(prompt)} chars): probable genérico.")
            # Anclaje de identidad: el nombre debería aparecer en la ficha; forzamos que aparezca.
            # Extraemos de la ficha la primera línea "Nombre del personaje: X"
            m = re.search(r"^Nombre del personaje:\s*(.+)\s*$", character_sheet, re.MULTILINE)
            expected_name = m.group(1).strip() if m else None
            if expected_name and expected_name.lower() not in prompt.lower():
                raise ValueError(f"Prompt sin nombre del personaje '{expected_name}': identidad no anclada.")

            if verbose:
                eprint("\n[API] Parseado:")
                eprint(f"prompt={prompt}")
                eprint(f"negative={negative}")

            return prompt, negative

        except Exception as e:
            last_err = e
            if attempt < max_retries:
                eprint(f"[API] Error en intento {attempt}/{max_retries}: {e}. Reintentando...")
                time.sleep(retry_sleep_s * attempt)
                continue
            raise RuntimeError(f"Fallo llamando a la API tras {max_retries} intentos: {e}") from e

    assert last_err is not None
    raise RuntimeError(str(last_err))


def to_ini_block(section_id: str, prompt: str, negative: str) -> str:
    return f"[{section_id}]\nprompt={prompt}\nnegative={negative}\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="Ficheros Markdown de entrada")
    ap.add_argument("-o", "--output", required=True, help="Salida INI (test_prompts.txt)")
    ap.add_argument("--model", default="gpt-5.2", help="Modelo (por defecto: gpt-5.2)")
    ap.add_argument("--temperature", type=float, default=0.4, help="Creatividad (0.0-1.0). Recomendado 0.3-0.6")
    ap.add_argument("--cache", default=".cache/prompt_cache.json", help="Cache JSON para evitar pagar dos veces")
    ap.add_argument("--force", action="store_true", help="Ignora cache y regenera todo")
    ap.add_argument("--min-delay", type=float, default=0.2, help="Pausa mínima entre llamadas (segundos)")
    ap.add_argument("-v", "--verbose", action="store_true", help="Muestra payload enviado a la API y respuesta recibida")
    ap.add_argument("--dry-run", action="store_true", help="No llama a la API; solo muestra qué enviaría")

    args = ap.parse_args()

    # OPENAI_API_KEY es necesaria solo si vamos a llamar a la API
    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        eprint("ERROR: falta OPENAI_API_KEY en el entorno (o usa --dry-run).")
        return 2

    client = OpenAI() if not args.dry_run else None

    cache_path = Path(args.cache)
    cache = load_cache(cache_path)

    ini_blocks: List[str] = []

    for inp in args.inputs:
        p = Path(inp)
        if not p.exists():
            eprint(f"ERROR: no existe: {p}")
            return 3

        md_text = p.read_text(encoding="utf-8", errors="replace")
        chars = parse_characters_from_md(md_text)

        total = len(chars)
        if total == 0:
            eprint(f"[{p.name}] No se encontraron secciones de personajes (##/###).")
            continue

        for idx, ch in enumerate(chars, start=1):
            section_id = slugify(ch.header)
            sheet_payload = build_character_sheet_payload(ch)

            eprint(f"[{p.name}] ({idx}/{total}) Generando prompt para: {ch.header}  ->  [{section_id}]")

            fp = content_fingerprint(sheet_payload + f"|model={args.model}|temp={args.temperature}")

            if (not args.force) and fp in cache:
                eprint(f"[{p.name}] ({idx}/{total}) Cache HIT: {ch.header}")
                prompt = cache[fp]["prompt"]
                negative = cache[fp]["negative"]
                if args.verbose:
                    eprint("[CACHE] prompt=" + prompt)
                    eprint("[CACHE] negative=" + negative)
            else:
                eprint(f"[{p.name}] ({idx}/{total}) Cache MISS: {ch.header} -> llamando API")
                prompt, negative = call_model_for_prompt(
                    client=client,  # type: ignore[arg-type]
                    model=args.model,
                    character_sheet=sheet_payload,
                    default_negative=DEFAULT_NEGATIVE,
                    temperature=args.temperature,
                    verbose=args.verbose,
                    dry_run=args.dry_run,
                )

                # En dry-run no tiene sentido cachear (es placeholder), y además evita ensuciar.
                if not args.dry_run:
                    cache[fp] = {"prompt": prompt, "negative": negative}
                    save_cache(cache_path, cache)
                    time.sleep(max(0.0, args.min_delay))

            ini_blocks.append(to_ini_block(section_id, prompt, negative))

    out_path = Path(args.output)
    out_path.write_text("\n".join(ini_blocks).rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
