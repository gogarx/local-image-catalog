#!/usr/bin/env python3
"""Inicializa catalog.db: images, FTS5 images_text, image_tags e triggers."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "catalog.db"

SCHEMA = """BEGIN;

CREATE TABLE IF NOT EXISTS images (
    id         INTEGER PRIMARY KEY,
    file_path  TEXT NOT NULL UNIQUE,
    file_name  TEXT NOT NULL,
    file_size  INTEGER NOT NULL,
    mtime      REAL NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS images_text USING fts5(
    image_id        UNINDEXED,
    prompt_positivo,
    prompt_negativo,
    workflow_json
);

CREATE TRIGGER IF NOT EXISTS images_ai AFTER INSERT ON images BEGIN
    INSERT INTO images_text (rowid, image_id, prompt_positivo, prompt_negativo, workflow_json)
    VALUES (new.id, new.id, '', '', '');
END;

CREATE TRIGGER IF NOT EXISTS images_ad AFTER DELETE ON images BEGIN
    DELETE FROM images_text WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS images_au AFTER UPDATE ON images
WHEN new.id <> old.id
BEGIN
    UPDATE images_text SET rowid = new.id, image_id = new.id
    WHERE rowid = old.id;
END;

CREATE TABLE IF NOT EXISTS image_tags (
    image_id INTEGER NOT NULL,
    tag      TEXT NOT NULL,
    PRIMARY KEY (image_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_image_tags_tag ON image_tags (tag);

CREATE TRIGGER IF NOT EXISTS image_tags_ad AFTER DELETE ON images BEGIN
    DELETE FROM image_tags WHERE image_id = old.id;
END;

COMMIT;
"""

EXPECTED_OBJECTS = {
    "images": "table",
    "images_text": "table",
    "images_ai": "trigger",
    "images_ad": "trigger",
    "images_au": "trigger",
    "image_tags": "table",
    "idx_image_tags_tag": "index",
    "image_tags_ad": "trigger",
}


def _check_fts5() -> None:
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE _fts5_check USING fts5(x)")
    except sqlite3.OperationalError as exc:
        raise SystemExit(
            "ERRO: este SQLite nao foi compilado com suporte a FTS5 "
            f"({exc}). Use um Python/SQLite com FTS5 habilitado."
        ) from exc
    finally:
        con.close()


def _verify_schema(con: sqlite3.Connection) -> None:
    missing = []
    for name, kind in EXPECTED_OBJECTS.items():
        row = con.execute(
            "SELECT type FROM sqlite_master WHERE name = ?", (name,)
        ).fetchone()
        if row is None or row[0] != kind:
            missing.append(name)
    if missing:
        raise RuntimeError(f"objetos ausentes ou invalidos no schema: {missing}")


def init_db(db_path: Path) -> Path:
    db_path = db_path.expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _check_fts5()
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript(SCHEMA)
        con.execute("PRAGMA user_version = 2")
        con.commit()
        _verify_schema(con)
    finally:
        con.close()
    return db_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inicializa o banco catalog.db do local-image-catalog (idempotente)."
    )
    parser.add_argument(
        "db",
        nargs="?",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="caminho do banco SQLite (padrao: %(default)s)",
    )
    args = parser.parse_args(argv)
    try:
        path = init_db(args.db)
    except sqlite3.Error as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    print(f"Banco pronto: {path}")
    print("  - tabela images (metadados dos arquivos)")
    print("  - tabela virtual FTS5 images_text (busca por texto)")
    print("  - tabela image_tags (palavras-chave) + indice idx_image_tags_tag")
    print("  - triggers de sincronia: images_ai, images_ad, images_au, image_tags_ad")
    print("  - journal_mode=WAL, user_version=2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
