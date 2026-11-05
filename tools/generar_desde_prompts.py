#!/usr/bin/env python3
import base64
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests

API_URL = "https://api.openai.com/v1/images/generations"

# Opciones "baratas"
DEFAULT_MODEL = "gpt-image-1-mini"
DEFAULT_QUALITY = "low"          # low|medium|high|auto (GPT image models)  :contentReference[oaicite:4]{index=4}
DEFAULT_SIZE = "1024x1024"       # GPT image models: 1024x1024, 1024x1536, 1536x1024, auto :contentReference[oaicite:5]{index=5}
DEFAULT_OUT_FORMAT = "jpeg"      # png|jpeg|webp :contentReference[oaicite:6]{index=6}
DEFAULT_OUT_COMPRESSION = 70     # 0-100 (jpeg/webp) :contentReference[oaicite:7]{index=7}

# Comportamiento
SLEEP_BETWEEN_CALLS_SEC = 0.4
RETRIES = 3


@dataclass
class PromptEntry:
    name: str
    prompt: str
    negative: str


def parse_prompts_file(path: Path) -> List[PromptEntry]:
    """
    Parse simple INI-like file:
      [section-name]
      prompt=...
      negative=...

    - prompt y negative pueden contener cualquier cosa en la misma línea.
    - no soporta multilinea; si la quieres, se puede ampliar.
    """
    text = path.read_text(encoding="utf-8")
    lines = [ln.rstrip("\n") for ln in text.splitlines()]

    entries: List[PromptEntry] = []
    current: Optional[Dict[str, str]] = None

    section_re = re.compile(r"^\[([^\]]+)\]\s*$")
    kv_re = re.compile(r"^(prompt|negative)\s*=\s*(.*)\s*$", re.IGNORECASE)

    for ln in lines:
        ln_stripped = ln.strip()
        if not ln_stripped or ln_stripped.startswith(";") or ln_stripped.startswith("#"):
            continue

        m_sec = section_re.match(ln_stripped)
        if m_sec:
            # flush previous
            if current:
                name = current.get("name", "").strip()
                prompt = current.get("prompt", "").strip()
                negative = current.get("negative", "").strip()
                if name and prompt:
                    entries.append(PromptEntry(name=name, prompt=prompt, negative=negative))
            current = {"name": m_sec.group(1).strip(), "prompt": "", "negative": ""}
            continue

        m_kv = kv_re.match(ln)
        if m_kv and current is not None:
            key = m_kv.group(1).lower()
            val = m_kv.group(2).strip()
            current[key] = val
            continue

    # flush last
    if current:
        name = current.get("name", "").strip()
        prompt = current.get("prompt", "").strip()
        negative = current.get("negative", "").strip()
        if name and prompt:
            entries.append(PromptEntry(name=name, prompt=prompt, negative=negative))

    if not entries:
        raise ValueError("No se encontraron entradas válidas en el fichero de prompts.")
    return entries


def build_final_prompt(entry: PromptEntry) -> str:
    """
    El usuario pide: "negative los añades al prompt".
    Lo hacemos de forma explícita para que el modelo lo respete mejor.
    """
    if entry.negative:
        return (
            f"{entry.prompt}\n\n"
            f"IMPORTANT: Avoid / do NOT include any of the following: {entry.negative}"
        )
    return entry.prompt


def request_image_b64(final_prompt: str, model: str, quality: str, size: str,
                      output_format: str, output_compression: int,
                      org_id: Optional[str] = None) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en el entorno.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if org_id:
        headers["OpenAI-Organization"] = org_id

    payload = {
        "model": model,
        "prompt": final_prompt,
        "n": 1,
        "quality": quality,                   # :contentReference[oaicite:8]{index=8}
        "size": size,                         # :contentReference[oaicite:9]{index=9}
        "output_format": output_format,       # :contentReference[oaicite:10]{index=10}
        "output_compression": output_compression,  # :contentReference[oaicite:11]{index=11}
    }

    r = requests.post(API_URL, headers=headers, json=payload, timeout=180)
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}\n{r.text}")

    data = r.json()
    return data["data"][0]["b64_json"]


def sanitize_filename(name: str) -> str:
    # Si el nombre ya es tipo slug, se respeta; si no, lo normalizamos mínimo.
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9._-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "sin_nombre"


def main():
    if len(sys.argv) not in (1, 2):
        print("Uso: ./generar_desde_prompts.py [test_prompts.txt]", file=sys.stderr)
        sys.exit(2)

    prompts_path = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("test_prompts.txt")
    out_dir = Path("img/celestiales")
    out_dir.mkdir(parents=True, exist_ok=True)

    model = os.environ.get("OPENAI_IMAGE_MODEL", DEFAULT_MODEL)
    quality = os.environ.get("OPENAI_IMAGE_QUALITY", DEFAULT_QUALITY)
    size = os.environ.get("OPENAI_IMAGE_SIZE", DEFAULT_SIZE)
    output_format = os.environ.get("OPENAI_IMAGE_FORMAT", DEFAULT_OUT_FORMAT)
    output_compression = int(os.environ.get("OPENAI_IMAGE_COMPRESSION", str(DEFAULT_OUT_COMPRESSION)))
    org_id = os.environ.get("OPENAI_ORG_ID")

    entries = parse_prompts_file(prompts_path)

    for idx, entry in enumerate(entries, start=1):
        fname = sanitize_filename(entry.name) + ".jpg"
        out_path = out_dir / fname

        if out_path.exists():
            print(f"[{idx}/{len(entries)}] skip {entry.name} -> {out_path} (ya existe)")
            continue

        final_prompt = build_final_prompt(entry)

        print(f"[{idx}/{len(entries)}] gen  {entry.name} -> {out_path}")
        print("----- PROMPT ENVIADO A LA IA -----")
        print(final_prompt)
        print("----- FIN PROMPT -----\n")

        # Si quieres ver exactamente lo enviado:
        # print("----- PROMPT -----\n" + final_prompt + "\n----- END PROMPT -----")

        last_err = None
        for attempt in range(1, RETRIES + 1):
            try:
                b64 = request_image_b64(
                    final_prompt=final_prompt,
                    model=model,
                    quality=quality,
                    size=size,
                    output_format=output_format,
                    output_compression=output_compression,
                    org_id=org_id,
                )
                out_path.write_bytes(base64.b64decode(b64))
                print(f"         OK")
                last_err = None
                break
            except Exception as e:
                last_err = e
                print(f"         intento {attempt}/{RETRIES} falló: {e}", file=sys.stderr)
                time.sleep(1.5 * attempt)

        if last_err:
            raise SystemExit(f"Error generando {entry.name}: {last_err}")

        time.sleep(SLEEP_BETWEEN_CALLS_SEC)


if __name__ == "__main__":
    main()
