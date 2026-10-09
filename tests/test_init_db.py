import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
INIT = BACKEND / "init_db.py"
DB = Path("/tmp/opencode/test_catalog.db")

for p in (DB, Path(str(DB) + "-wal"), Path(str(DB) + "-shm")):
    if p.exists():
        p.unlink()

r = subprocess.run([sys.executable, str(INIT), str(DB)], capture_output=True, text=True)
print(r.stdout.strip())
assert r.returncode == 0, r.stderr

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

con.execute(
    "INSERT INTO images (file_path, file_name, file_size, mtime) VALUES (?,?,?,?)",
    ("/imgs/gato.png", "gato.png", 1234, 1760000000.5),
)
con.execute(
    "INSERT INTO images (file_path, file_name, file_size, mtime) VALUES (?,?,?,?)",
    ("/imgs/praia.png", "praia.png", 2048, 1760000100.0),
)
con.commit()
rows = con.execute(
    "SELECT rowid, image_id, typeof(image_id) AS t, prompt_positivo, prompt_negativo, workflow_json "
    "FROM images_text ORDER BY rowid"
).fetchall()
assert len(rows) == 2
print("placeholders:", [tuple(r) for r in rows])
assert [r["rowid"] for r in rows] == [1, 2]
assert all(r["image_id"] == r["rowid"] for r in rows)
assert all(r["prompt_positivo"] == "" and r["prompt_negativo"] == "" and r["workflow_json"] == "" for r in rows)

con.execute(
    "UPDATE images_text SET prompt_positivo=?, prompt_negativo=?, workflow_json=? WHERE rowid=?",
    (
        "um gato laranja na praia ao entardecer",
        "dedos extras, borrão",
        '{"sampler": "euler", "steps": 20}',
        1,
    ),
)
con.commit()

assert [h[0] for h in con.execute("SELECT rowid FROM images_text WHERE images_text MATCH 'gato'")] == [1]
assert [h[0] for h in con.execute("SELECT rowid FROM images_text WHERE images_text MATCH 'praia' ORDER BY rank")] == [1]
assert [h[0] for h in con.execute("SELECT rowid FROM images_text WHERE images_text MATCH 'workflow_json: euler'")] == [1]
assert [h[0] for h in con.execute("SELECT rowid FROM images_text WHERE images_text MATCH 'prompt_negativo: dedos'")] == [1]
assert con.execute("SELECT count(*) FROM images_text WHERE images_text MATCH 'inexistente'").fetchone()[0] == 0

joined = con.execute(
    "SELECT i.file_path, t.prompt_positivo FROM images_text(?) AS t "
    "JOIN images AS i ON i.id = t.rowid ORDER BY t.rank",
    ("gato",),
).fetchall()
assert len(joined) == 1 and joined[0]["file_path"] == "/imgs/gato.png"

con.execute("UPDATE images SET file_size=999, mtime=1760000999.0, indexed_at=CURRENT_TIMESTAMP WHERE id=1")
con.commit()
assert con.execute("SELECT prompt_positivo FROM images_text WHERE rowid=1").fetchone()[0] == "um gato laranja na praia ao entardecer"

con.execute("UPDATE images SET id=100 WHERE id=2")
con.commit()
assert con.execute("SELECT count(*) FROM images_text WHERE rowid=2").fetchone()[0] == 0
moved = con.execute("SELECT rowid, image_id FROM images_text WHERE rowid=100").fetchone()
assert moved is not None and moved["image_id"] == 100
assert con.execute("SELECT count(*) FROM images_text").fetchone()[0] == 2

con.execute("DELETE FROM images WHERE id=100")
con.commit()
assert con.execute("SELECT count(*) FROM images_text").fetchone()[0] == 1
assert con.execute("SELECT count(*) FROM images_text WHERE rowid=100").fetchone()[0] == 0

try:
    con.execute(
        "INSERT INTO images (file_path, file_name, file_size, mtime) VALUES (?,?,?,?)",
        ("/imgs/gato.png", "gato.png", 1, 1.0),
    )
    raise AssertionError("UNIQUE de file_path deveria ter falhado")
except sqlite3.IntegrityError:
    pass

con.close()
r2 = subprocess.run([sys.executable, str(INIT), str(DB)], capture_output=True, text=True)
assert r2.returncode == 0, r2.stderr
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
assert con.execute("SELECT count(*) FROM images").fetchone()[0] == 1
assert con.execute("SELECT prompt_positivo FROM images_text WHERE rowid=1").fetchone()[0] == "um gato laranja na praia ao entardecer"
assert con.execute("PRAGMA user_version").fetchone()[0] == 3
assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

CHECK = """
SELECT
  (SELECT count(*) FROM images WHERE id NOT IN (SELECT rowid FROM images_text)) AS fts_faltando,
  (SELECT count(*) FROM images_text WHERE rowid NOT IN (SELECT id FROM images)) AS fts_orfas,
  (SELECT count(*) FROM images_text WHERE CAST(image_id AS INTEGER) <> rowid) AS link_quebrado
"""

con.execute("DELETE FROM images_text WHERE rowid=1")
con.execute(
    "INSERT INTO images_text (rowid, image_id, prompt_positivo, prompt_negativo, workflow_json) "
    "VALUES (999, 999, 'orfã', '', '')"
)
con.commit()
chk = con.execute(CHECK).fetchone()
print("check pós-corrupção:", tuple(chk))
assert tuple(chk) == (1, 1, 0)

con.execute(
    "INSERT INTO images_text (rowid, image_id, prompt_positivo, prompt_negativo, workflow_json) "
    "SELECT id, id, '', '', '' FROM images WHERE id NOT IN (SELECT rowid FROM images_text)"
)
con.execute("DELETE FROM images_text WHERE rowid NOT IN (SELECT id FROM images)")
con.execute("UPDATE images_text SET image_id = rowid WHERE CAST(image_id AS INTEGER) <> rowid")
con.commit()
chk = con.execute(CHECK).fetchone()
print("check pós-reparo:", tuple(chk))
assert tuple(chk) == (0, 0, 0)
assert con.execute("SELECT count(*) FROM images_text").fetchone()[0] == 1

con.execute("INSERT INTO image_tags (image_id, tag) VALUES (1, '1girl')")
try:
    con.execute("INSERT INTO image_tags (image_id, tag) VALUES (1, '1girl')")
    raise AssertionError("PK composta de image_tags deveria ter falhado")
except sqlite3.IntegrityError:
    pass
assert (
    con.execute("SELECT source FROM image_tags WHERE image_id = 1 AND tag = '1girl'").fetchone()[0]
    == "tagger"
)
con.execute(
    "INSERT OR IGNORE INTO image_tags (image_id, tag, source) VALUES (1, 'horns', 'space_api')"
)
con.execute(
    "INSERT OR IGNORE INTO image_tags (image_id, tag, source) VALUES (1, 'horns', 'tagger')"
)
assert (
    con.execute("SELECT source FROM image_tags WHERE image_id = 1 AND tag = 'horns'").fetchone()[0]
    == "space_api"
)
con.execute("DELETE FROM images WHERE id = 1")
con.commit()
assert con.execute("SELECT count(*) FROM image_tags").fetchone()[0] == 0
assert con.execute("SELECT count(*) FROM images_text WHERE rowid = 1").fetchone()[0] == 0

con.close()
print("TODOS OS TESTES PASSARAM")
