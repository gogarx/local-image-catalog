#!/usr/bin/env python3
"""API FastAPI do local-image-catalog: galeria, detalhes, busca FTS e mídia local."""

from __future__ import annotations

import io
import mimetypes
import os
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

import init_db

DB_PATH = Path(os.environ.get("CATALOG_DB", init_db.DEFAULT_DB_PATH))
MEDIA_ROOT = Path(os.environ.get("CATALOG_MEDIA_ROOT", "/"))
NSFW_BLACKLIST = {"nsfw", "nudity", "explicit", "breasts", "cleavage", "hentai"}

init_db.init_db(DB_PATH)

app = FastAPI(title="local-image-catalog", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=5.0)
    con.row_factory = sqlite3.Row
    return con


def media_url(file_path: str) -> str:
    try:
        rel = Path(file_path).relative_to(MEDIA_ROOT)
    except ValueError:
        return ""
    return "/media/" + quote(rel.as_posix())


def build_item(con: sqlite3.Connection, row: sqlite3.Row) -> dict:
    tags = [
        r[0].lower()
        for r in con.execute(
            "SELECT tag FROM image_tags WHERE image_id = ?", (row["id"],)
        )
    ]
    return {
        **dict(row),
        "media_url": media_url(row["file_path"]),
        "tags": tags,
        "is_nsfw": bool(set(tags) & NSFW_BLACKLIST),
    }


@app.get("/images")
def list_images(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    with closing(db()) as con:
        total = con.execute("SELECT count(*) FROM images").fetchone()[0]
        rows = con.execute(
            "SELECT id, file_name, file_size, file_path FROM images"
            " ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        items = [build_item(con, row) for row in rows]
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.get("/images/{image_id}")
def image_detail(image_id: int):
    with closing(db()) as con:
        row = con.execute(
            "SELECT i.id, i.file_path, i.file_name, i.file_size, i.mtime, i.indexed_at,"
            " t.image_id, t.prompt_positivo, t.prompt_negativo, t.workflow_json"
            " FROM images AS i"
            " JOIN images_text AS t ON t.rowid = i.id"
            " WHERE i.id = ?",
            (image_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="imagem não encontrada")
        tags = [
            r[0]
            for r in con.execute(
                "SELECT tag FROM image_tags WHERE image_id = ? ORDER BY tag",
                (image_id,),
            )
        ]
    data = dict(row)
    data["media_url"] = media_url(data["file_path"])
    data["tags"] = tags
    return data


@app.get("/search")
def search(
    q: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    with closing(db()) as con:
        try:
            total = con.execute(
                "SELECT count(*) FROM images_text(?) AS t", (q,)
            ).fetchone()[0]
            rows = con.execute(
                "SELECT i.id, i.file_name, i.file_size, i.file_path, t.prompt_positivo"
                " FROM images_text(?) AS t"
                " JOIN images AS i ON i.id = t.rowid"
                " ORDER BY t.rank"
                " LIMIT ? OFFSET ?",
                (q, limit, offset),
            ).fetchall()
        except sqlite3.OperationalError as err:
            msg = str(err).lower()
            if "fts5" in msg or "unterminated string" in msg or "unknown special query" in msg:
                raise HTTPException(
                    status_code=400, detail=f"consulta FTS inválida: {err}"
                ) from err
            raise
        items = [build_item(con, row) for row in rows]
    return {"q": q, "total": total, "limit": limit, "offset": offset, "items": items}


MEDIA_TYPES = {
    ".png": "image/png",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
}
CHUNK_SIZE = 64 * 1024


def iter_chunks(buffer: io.BytesIO):
    while True:
        chunk = buffer.read(CHUNK_SIZE)
        if not chunk:
            return
        yield chunk


class CatalogFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        if "::" not in path:
            return await super().get_response(path, scope)
        try:
            buffer, media_type = await run_in_threadpool(self.load_member, path)
        except (OSError, zipfile.BadZipFile, RuntimeError, KeyError, ValueError):
            return Response(status_code=404)
        size = buffer.getbuffer().nbytes
        buffer.seek(0)
        return StreamingResponse(
            iter_chunks(buffer),
            media_type=media_type,
            headers={"Content-Length": str(size)},
        )

    def load_member(self, path: str) -> tuple[io.BytesIO, str]:
        zip_rel, _, internal = path.partition("::")
        base = str(MEDIA_ROOT.resolve())
        full_zip = os.path.realpath(os.path.join(base, zip_rel.lstrip("/")))
        if not full_zip.startswith(base.rstrip("/") + "/"):
            raise ValueError("caminho fora da raiz")
        with zipfile.ZipFile(full_zip) as zf:
            with zf.open(internal) as member:
                buffer = io.BytesIO(member.read())
        suffix = Path(internal).suffix.lower()
        media_type = MEDIA_TYPES.get(suffix) or mimetypes.guess_type(internal)[0]
        return buffer, media_type or "application/octet-stream"


app.mount("/media", CatalogFiles(directory=str(MEDIA_ROOT)), name="media")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("CATALOG_PORT", "8000")))
