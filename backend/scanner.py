#!/usr/bin/env python3
"""Varre recursivamente pastas e arquivos .zip catalogando imagens na tabela images."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import zipfile
from pathlib import Path

import init_db

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
ZIP_IMAGE_EXTENSIONS = {".png", ".webp"}
COMMIT_EVERY = 500


def is_image(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS


def is_hidden_internal(internal_name: str) -> bool:
    return any(part == "__MACOSX" or part.startswith(".") for part in internal_name.split("/"))


def scan_folder(folder: Path, db_path: Path) -> dict[str, int]:
    root = os.path.abspath(folder)
    if not os.path.isdir(root):
        raise SystemExit(f"ERRO: pasta inexistente: {root}")
    db_path = init_db.init_db(db_path)
    con = sqlite3.connect(db_path)
    stats = {"adicionadas": 0, "atualizadas": 0, "inalteradas": 0, "erros": 0}
    pending_writes = 0

    def warn(err: BaseException, path: str) -> None:
        stats["erros"] += 1
        print(f"aviso: {path}: {err}", file=sys.stderr)

    def upsert(file_path: str, file_name: str, file_size: int, mtime: float) -> None:
        nonlocal pending_writes
        row = con.execute(
            "SELECT id, file_size, mtime FROM images WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        if row is not None and row[1] == file_size and row[2] == mtime:
            stats["inalteradas"] += 1
            return
        if row is None:
            con.execute(
                "INSERT INTO images (file_path, file_name, file_size, mtime)"
                " VALUES (?, ?, ?, ?)",
                (file_path, file_name, file_size, mtime),
            )
            stats["adicionadas"] += 1
        else:
            con.execute(
                "UPDATE images SET file_size = ?, mtime = ?,"
                " indexed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (file_size, mtime, row[0]),
            )
            stats["atualizadas"] += 1
        pending_writes += 1
        if pending_writes >= COMMIT_EVERY:
            con.commit()
            pending_writes = 0

    def scan_zip(zip_path: str) -> None:
        try:
            st = os.stat(zip_path)
        except OSError as err:
            warn(err, zip_path)
            return
        try:
            with zipfile.ZipFile(zip_path) as zf:
                members = {}
                for info in zf.infolist():
                    if info.is_dir() or is_hidden_internal(info.filename):
                        continue
                    if os.path.splitext(info.filename)[1].lower() not in ZIP_IMAGE_EXTENSIONS:
                        continue
                    members[info.filename] = info
        except (zipfile.BadZipFile, OSError) as err:
            warn(err, zip_path)
            return
        for internal, info in members.items():
            file_name = internal.rsplit("/", 1)[-1]
            upsert(f"{zip_path}::{internal}", file_name, info.file_size, st.st_mtime)

    def on_walk_error(err: OSError) -> None:
        warn(err, getattr(err, "filename", "") or str(err))

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_walk_error):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if "::" in name:
                continue
            file_path = os.path.abspath(os.path.join(dirpath, name))
            if name.lower().endswith(".zip"):
                scan_zip(file_path)
                continue
            if not is_image(name):
                continue
            try:
                st = os.stat(file_path)
            except OSError as err:
                warn(err, file_path)
                continue
            upsert(file_path, name, st.st_size, st.st_mtime)
    con.commit()
    con.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cataloga as imagens de uma pasta (e de arquivos .zip) no banco local (idempotente)."
    )
    parser.add_argument("folder", type=Path, help="pasta raiz da varredura recursiva")
    parser.add_argument(
        "--db",
        type=Path,
        default=init_db.DEFAULT_DB_PATH,
        help="caminho do banco (padrao: %(default)s)",
    )
    args = parser.parse_args(argv)
    stats = scan_folder(args.folder, args.db)
    print(f"Pasta: {os.path.abspath(args.folder)}")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
