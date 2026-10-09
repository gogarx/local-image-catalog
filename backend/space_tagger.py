#!/usr/bin/env python3
"""Processa imagens sem tags via o Space WD-Tagger e grava em image_tags com source='space_api'."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from gradio_client import Client, handle_file

import init_db

SPACE_ID = "SmilingWolf/wd-tagger"
MODEL_REPO = "SmilingWolf/wd-swinv2-tagger-v3"
GENERAL_THRESHOLD = 0.35
CHARACTER_THRESHOLD = 0.85
SLEEP_SECONDS = 5
TEMP_DIR = "/tmp"

RATING_KEYS = {"general", "sensitive", "questionable", "explicit"}

TARGETS_SQL = """
SELECT i.id, i.file_path
FROM images AS i
WHERE NOT EXISTS (SELECT 1 FROM image_tags g WHERE g.image_id = i.id)
ORDER BY i.id
LIMIT ?
"""


def normalize_tag(tag: str) -> str:
    return tag.strip().lower().replace(" ", "_")


def label_confidences(node: dict) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for item in node.get("confidences") or []:
        name = item.get("label")
        score = item.get("confidence")
        if isinstance(name, str) and isinstance(score, (int, float)):
            parsed[name] = float(score)
    return parsed


def _finalize(scores: dict[str, float | None]) -> list[str]:
    tags: set[str] = set()
    for name, score in scores.items():
        name = normalize_tag(name)
        if not name:
            continue
        if score is not None and score <= GENERAL_THRESHOLD:
            continue
        tags.add(name)
    return sorted(tags)


def _walk_extract(result: object) -> list[str]:
    scores: dict[str, float | None] = {}

    def add(name: str, score: float | None) -> None:
        scores.setdefault(name, score)

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if "confidences" in node:
                parsed = label_confidences(node)
                if set(parsed) <= RATING_KEYS:
                    return
                for name, score in parsed.items():
                    add(name, score)
                return
            if "general" in node:
                walk(node["general"])
                return
            if node and set(node) <= RATING_KEYS and all(
                isinstance(value, (int, float)) for value in node.values()
            ):
                return
            for key, value in node.items():
                if isinstance(value, (int, float)):
                    add(str(key), float(value))
                else:
                    walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            if "\n" in node:
                return
            for part in node.split(","):
                part = part.strip()
                if not part:
                    continue
                name, _, raw = part.rpartition(":")
                try:
                    add(name or part, float(raw))
                except ValueError:
                    add(part, None)

    walk(result)
    return _finalize(scores)


def extract_general_tags(result: object) -> list[str]:
    if isinstance(result, (list, tuple)):
        label_dicts = [
            item for item in result if isinstance(item, dict) and "confidences" in item
        ]
        if len(label_dicts) == 3:
            parsed = label_confidences(label_dicts[2])
            if not parsed:
                return []
            if not set(parsed) <= RATING_KEYS:
                return _finalize(parsed)
    return _walk_extract(result)


def extract_to_temp(file_path: str) -> str:
    zip_path, _, internal = file_path.partition("::")
    suffix = Path(internal).suffix or ".png"
    fd, temp_path = tempfile.mkstemp(suffix=suffix, dir=TEMP_DIR)
    os.close(fd)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            with zf.open(internal) as member:
                Path(temp_path).write_bytes(member.read())
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return temp_path


def run(db_path: Path, limit: int | None = None, client=None) -> dict[str, int]:
    db_path = init_db.init_db(db_path)
    con = sqlite3.connect(db_path)
    stats = {"alvos": 0, "processadas": 0, "inseridos": 0, "sem_tags": 0, "erros": 0}
    targets = con.execute(TARGETS_SQL, (-1 if limit is None else limit,)).fetchall()
    stats["alvos"] = len(targets)
    if client is None:
        client = Client(SPACE_ID)
    for image_id, file_path in targets:
        stats["processadas"] += 1
        try:
            physical = file_path
            temp_path = ""
            if "::" in file_path:
                temp_path = physical = extract_to_temp(file_path)
            try:
                result = client.predict(
                    image=handle_file(physical),
                    model_repo=MODEL_REPO,
                    general_thresh=GENERAL_THRESHOLD,
                    general_mcut_enabled=False,
                    character_thresh=CHARACTER_THRESHOLD,
                    character_mcut_enabled=False,
                    api_name="/predict",
                )
            finally:
                if temp_path:
                    os.unlink(temp_path)
        except Exception as err:
            stats["erros"] += 1
            print(f"aviso: {file_path}: {err}", file=sys.stderr)
            continue
        tags = extract_general_tags(result)
        if tags:
            before = con.total_changes
            for tag in tags:
                con.execute(
                    "INSERT OR IGNORE INTO image_tags (image_id, tag, source)"
                    " VALUES (?, ?, 'space_api')",
                    (image_id, tag),
                )
            stats["inseridos"] += con.total_changes - before
        else:
            stats["sem_tags"] += 1
        con.commit()
        time.sleep(SLEEP_SECONDS)
    con.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Categoriza imagens sem tags via o Space WD-Tagger (throttle de 5s por imagem)."
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
    print(f"Space: {SPACE_ID}")
    print(f"  modelo: {MODEL_REPO}")
    stats = run(args.db, args.limite)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
