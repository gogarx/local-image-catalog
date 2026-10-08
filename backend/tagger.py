#!/usr/bin/env python3
"""Popula image_tags com palavras-chave padronizadas encontradas nos prompts."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

import init_db

TAGS_URL = (
    "https://raw.githubusercontent.com/gogarx/yandere-masonry/refs/heads/main/src/data/tags_cn.json"
)
COMMIT_EVERY = 500

PROMPTS_SQL = """
SELECT rowid, prompt_positivo
FROM images_text
WHERE prompt_positivo <> ''
"""


def normalize_token(token: str) -> str:
    token = token.strip().strip("()[]{}").strip()
    if ":" in token:
        token = token.split(":", 1)[0].strip()
    return token.lower().replace(" ", "_")


def fetch_tag_keys() -> set[str]:
    try:
        with urllib.request.urlopen(TAGS_URL, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise SystemExit(f"ERRO: nao foi possivel carregar o dicionario de tags: {err}")
    if not isinstance(data, dict):
        raise SystemExit("ERRO: dicionario de tags inesperado (esperado objeto JSON)")
    keys = {normalize_token(key) for key in data}
    keys.discard("")
    if not keys:
        raise SystemExit("ERRO: dicionario de tags vazio")
    return keys


def tag_prompts(db_path: Path, keys: set[str]) -> dict[str, int]:
    db_path = init_db.init_db(db_path)
    con = sqlite3.connect(db_path)
    stats = {"processadas": 0, "inseridos": 0}
    before = con.total_changes
    pending = con.execute(PROMPTS_SQL).fetchall()
    for image_id, prompt in pending:
        stats["processadas"] += 1
        tokens = {normalize_token(part) for part in prompt.replace("\n", ",").split(",")}
        tokens.discard("")
        for tag in tokens & keys:
            con.execute(
                "INSERT OR IGNORE INTO image_tags (image_id, tag) VALUES (?, ?)",
                (image_id, tag),
            )
        if stats["processadas"] % COMMIT_EVERY == 0:
            con.commit()
    con.commit()
    stats["inseridos"] = con.total_changes - before
    con.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Categoriza os prompts com tags padronizadas (idempotente)."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=init_db.DEFAULT_DB_PATH,
        help="caminho do banco (padrao: %(default)s)",
    )
    args = parser.parse_args(argv)
    keys = fetch_tag_keys()
    print(f"Dicionario: {TAGS_URL}")
    print(f"  chaves: {len(keys)}")
    stats = tag_prompts(args.db, keys)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
