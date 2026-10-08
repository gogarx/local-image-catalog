#!/usr/bin/env python3
"""Extrai prompts/workflow das imagens catalogadas (disco ou membro de .zip) para a FTS5."""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

from PIL import Image

import init_db

COMMIT_EVERY = 500
ZIP_HEADER_LIMIT = 4 * 1024 * 1024

ZIP_ERRORS = (zipfile.BadZipFile, RuntimeError, NotImplementedError, KeyError)

PENDING_SQL = """
SELECT i.id, i.file_path
FROM images AS i
JOIN images_text AS t ON t.rowid = i.id
WHERE t.prompt_positivo = '' AND t.prompt_negativo = '' AND t.workflow_json = ''
ORDER BY i.id
LIMIT ?
"""


def _as_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return ""


def _parse_a1111(parameters: str) -> tuple[str, str, str]:
    lines = parameters.splitlines()
    neg_idx = next(
        (i for i, line in enumerate(lines) if line.startswith("Negative prompt:")),
        None,
    )
    steps_idx = next(
        (i for i, line in enumerate(lines) if line.startswith("Steps:")), None
    )
    if neg_idx is not None:
        positive = "\n".join(lines[:neg_idx]).strip()
        neg_end = steps_idx if steps_idx is not None and steps_idx > neg_idx else len(lines)
        negative = "\n".join(
            [lines[neg_idx][len("Negative prompt:"):]] + lines[neg_idx + 1:neg_end]
        ).strip()
    elif steps_idx is not None:
        positive = "\n".join(lines[:steps_idx]).strip()
        negative = ""
    else:
        positive = parameters.strip()
        negative = ""
    workflow = "\n".join(lines[steps_idx:]).strip() if steps_idx is not None else ""
    return positive, negative, workflow


def _text_from_node(graph: dict, ref: object) -> str:
    if not isinstance(ref, (list, tuple)) or not ref:
        return ""
    node = graph.get(str(ref[0]))
    if not isinstance(node, dict):
        return ""
    if "TextEncode" not in str(node.get("class_type", "")):
        return ""
    text = node.get("inputs", {}).get("text")
    if isinstance(text, str):
        return text
    if isinstance(text, list) and all(isinstance(part, str) for part in text):
        return "\n".join(text)
    return ""


def _comfy_texts(prompt_raw: str) -> tuple[str, str]:
    try:
        graph = json.loads(prompt_raw)
    except json.JSONDecodeError:
        return "", ""
    if not isinstance(graph, dict):
        return "", ""
    positive = negative = ""
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        if "KSampler" not in str(node.get("class_type", "")):
            continue
        inputs = node.get("inputs", {})
        positive = _text_from_node(graph, inputs.get("positive")) or positive
        negative = _text_from_node(graph, inputs.get("negative")) or negative
        if positive and negative:
            break
    return positive, negative


def _parse_comfy(info: dict) -> tuple[str, str, str]:
    prompt_raw = _as_text(info.get("prompt"))
    workflow_raw = _as_text(info.get("workflow"))
    positive, negative = _comfy_texts(prompt_raw) if prompt_raw else ("", "")
    return positive, negative, workflow_raw or prompt_raw


def extract_texts(info: dict) -> tuple[str, str, str]:
    parameters = _as_text(info.get("parameters"))
    if parameters:
        return _parse_a1111(parameters)
    if "prompt" in info or "workflow" in info:
        return _parse_comfy(info)
    return "", "", ""


def _info_from_bytes(data: bytes) -> dict:
    with Image.open(io.BytesIO(data)) as img:
        return dict(img.info)


def _read_member(zf: zipfile.ZipFile, internal: str, full: bool) -> bytes:
    with zf.open(internal) as member:
        return member.read() if full else member.read(ZIP_HEADER_LIMIT)


def _read_virtual_info(file_path: str) -> dict:
    zip_path, _, internal = file_path.partition("::")
    with zipfile.ZipFile(zip_path) as zf:
        head = _read_member(zf, internal, full=False)
        try:
            return _info_from_bytes(head)
        except (OSError, ValueError, SyntaxError):
            if len(head) < ZIP_HEADER_LIMIT:
                raise
        return _info_from_bytes(_read_member(zf, internal, full=True))


def _read_info(file_path: str) -> dict:
    if "::" in file_path:
        return _read_virtual_info(file_path)
    with Image.open(file_path) as img:
        return dict(img.info)


def extract_pending(db_path: Path, limit: int | None = None) -> dict[str, int]:
    db_path = init_db.init_db(db_path)
    con = sqlite3.connect(db_path)
    stats = {"processadas": 0, "preenchidas": 0, "sem_metadados": 0, "erros": 0}
    pending = con.execute(PENDING_SQL, (-1 if limit is None else limit,)).fetchall()
    for image_id, file_path in pending:
        stats["processadas"] += 1
        try:
            info = _read_info(file_path)
        except (OSError, ValueError, SyntaxError, *ZIP_ERRORS) as err:
            stats["erros"] += 1
            print(f"aviso: {file_path}: {err}", file=sys.stderr)
            continue
        positive, negative, workflow = extract_texts(info)
        con.execute(
            "UPDATE images_text SET prompt_positivo = ?, prompt_negativo = ?,"
            " workflow_json = ? WHERE rowid = ?",
            (positive, negative, workflow, image_id),
        )
        if positive or negative or workflow:
            stats["preenchidas"] += 1
        else:
            stats["sem_metadados"] += 1
        if stats["processadas"] % COMMIT_EVERY == 0:
            con.commit()
    con.commit()
    con.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preenche os prompts/workflow das imagens pendentes no banco local."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=init_db.DEFAULT_DB_PATH,
        help="caminho do banco (padrao: %(default)s)",
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=None,
        help="maximo de imagens a processar nesta execucao",
    )
    args = parser.parse_args(argv)
    stats = extract_pending(args.db, args.limite)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
