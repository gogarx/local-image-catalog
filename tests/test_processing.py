import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

BACKEND = Path(__file__).resolve().parents[1] / "backend"
ROOT = Path("/tmp/opencode/fixtures_catalog")
DB = Path("/tmp/opencode/fixtures_catalog.db")
DB_LIMIT = Path("/tmp/opencode/fixtures_limit.db")
WEIRD = "estranho 'd'água \"x\".png"

A1111_TEXT = (
    "a majestic gato laranja, on the beach at sunset\n"
    "Negative prompt: blurry, extra digits\n"
    "Steps: 20, Sampler: DPM++ 2M, CFG scale: 7, Seed: 12345, Size: 512x512"
)
COMFY_PROMPT = {
    "3": {
        "class_type": "KSampler",
        "inputs": {"seed": 1, "steps": 20, "positive": ["6", 0], "negative": ["7", 0]},
    },
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "um gato laranja na praia ao entardecer"}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "dedos extras, borrão"}},
}
COMFY_WORKFLOW = {"nodes": [{"id": 1, "type": "KSampler"}], "links": [[1, 6, 0, 3, 0]]}


def build_fixtures():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    for p in (DB, DB_LIMIT):
        p.unlink(missing_ok=True)
        Path(str(p) + "-wal").unlink(missing_ok=True)
        Path(str(p) + "-shm").unlink(missing_ok=True)

    def save_png(path, meta=None):
        Image.new("RGB", (8, 8), (255, 0, 0)).save(path, pnginfo=meta)

    meta = PngInfo()
    meta.add_text("parameters", A1111_TEXT)
    save_png(ROOT / "a1111.png", meta)

    meta = PngInfo()
    meta.add_text("prompt", json.dumps(COMFY_PROMPT))
    meta.add_text("workflow", json.dumps(COMFY_WORKFLOW))
    save_png(ROOT / "comfy.png", meta)

    save_png(ROOT / "plain.png")
    Image.new("RGB", (8, 8), (0, 0, 255)).save(ROOT / "foto.jpg")

    sub = ROOT / "sub"
    sub.mkdir()
    save_png(sub / WEIRD)

    hidden = ROOT / ".cache"
    hidden.mkdir()
    save_png(hidden / "ignored.png")

    (ROOT / "nota.txt").write_text("nao sou imagem")
    (ROOT / "broken.png").write_text("isto nao e um png de verdade")


def run(script, *args):
    r = subprocess.run(
        [sys.executable, str(BACKEND / script), *args], capture_output=True, text=True
    )
    print(f"$ python3 {script} {' '.join(args)}")
    print(r.stdout.rstrip())
    if r.stderr.strip():
        print("stderr:", r.stderr.strip())
    assert r.returncode == 0, f"{script} falhou com {r.returncode}"
    return r


def parse_stats(out):
    stats = {}
    for line in out.splitlines():
        if line.startswith("  ") and ": " in line:
            k, v = line.strip().split(": ")
            stats[k] = int(v)
    return stats


build_fixtures()

r = run("scanner.py", str(ROOT), "--db", str(DB))
s = parse_stats(r.stdout)
assert s == {"adicionadas": 6, "atualizadas": 0, "inalteradas": 0, "erros": 0}, s

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute("SELECT * FROM images ORDER BY id").fetchall()
assert len(rows) == 6
by_path = {row["file_path"]: row for row in rows}
assert not any(".cache" in p or "nota.txt" in p for p in by_path)
weird_path = os.path.abspath(str(ROOT / "sub" / WEIRD))
assert weird_path in by_path
for path, row in by_path.items():
    assert os.path.isabs(path) and path == os.path.abspath(path)
    assert row["file_name"] == os.path.basename(path)
    st = os.stat(path)
    assert row["file_size"] == st.st_size
    assert row["mtime"] == st.st_mtime
    assert len(row["indexed_at"]) == 19

r = run("scanner.py", str(ROOT), "--db", str(DB))
s = parse_stats(r.stdout)
assert s == {"adicionadas": 0, "atualizadas": 0, "inalteradas": 6, "erros": 0}, s

r = run("extractor.py", "--db", str(DB))
s = parse_stats(r.stdout)
assert s == {"processadas": 6, "preenchidas": 2, "sem_metadados": 3, "erros": 1}, s


def fts(path):
    return con.execute(
        "SELECT t.prompt_positivo, t.prompt_negativo, t.workflow_json "
        "FROM images_text AS t JOIN images AS i ON i.id = t.rowid WHERE i.file_path = ?",
        (path,),
    ).fetchone()


a = fts(str(ROOT / "a1111.png"))
assert a["prompt_positivo"] == "a majestic gato laranja, on the beach at sunset"
assert a["prompt_negativo"] == "blurry, extra digits"
assert a["workflow_json"].startswith("Steps: 20")

c = fts(str(ROOT / "comfy.png"))
assert c["prompt_positivo"] == "um gato laranja na praia ao entardecer"
assert c["prompt_negativo"] == "dedos extras, borrão"
assert c["workflow_json"] == json.dumps(COMFY_WORKFLOW)

for p in (str(ROOT / "plain.png"), str(ROOT / "foto.jpg"), weird_path, str(ROOT / "broken.png")):
    t = fts(p)
    assert (t["prompt_positivo"], t["prompt_negativo"], t["workflow_json"]) == ("", "", "")

hits = con.execute(
    "SELECT i.file_path FROM images_text(?) AS t JOIN images AS i ON i.id = t.rowid",
    ("gato",),
).fetchall()
assert sorted(h[0] for h in hits) == sorted([str(ROOT / "a1111.png"), str(ROOT / "comfy.png")])
hits = con.execute(
    "SELECT i.file_path FROM images_text(?) AS t JOIN images AS i ON i.id = t.rowid",
    ("borrão",),
).fetchall()
assert [h[0] for h in hits] == [str(ROOT / "comfy.png")]

a1111_path = ROOT / "a1111.png"
os.utime(a1111_path, ns=(1600000000 * 10**9,) * 2)
r = run("scanner.py", str(ROOT), "--db", str(DB))
s = parse_stats(r.stdout)
assert s == {"adicionadas": 0, "atualizadas": 1, "inalteradas": 5, "erros": 0}, s
assert con.execute("SELECT mtime FROM images WHERE file_path = ?", (str(a1111_path),)).fetchone()[0] == 1600000000.0
assert fts(str(a1111_path))["prompt_positivo"] == "a majestic gato laranja, on the beach at sunset"

os.remove(ROOT / "comfy.png")
r = run("scanner.py", str(ROOT), "--db", str(DB))
s = parse_stats(r.stdout)
assert s == {"adicionadas": 0, "atualizadas": 0, "inalteradas": 5, "erros": 0}, s
assert con.execute("SELECT count(*) FROM images").fetchone()[0] == 6

r = run("extractor.py", "--db", str(DB))
s = parse_stats(r.stdout)
assert s == {"processadas": 4, "preenchidas": 0, "sem_metadados": 3, "erros": 1}, s
con.close()

run("init_db.py", str(DB_LIMIT))
con = sqlite3.connect(DB_LIMIT)
for name in ("a1111.png", "plain.png"):
    p = str(ROOT / name)
    st = os.stat(p)
    con.execute(
        "INSERT INTO images (file_path, file_name, file_size, mtime) VALUES (?, ?, ?, ?)",
        (p, name, st.st_size, st.st_mtime),
    )
con.commit()
con.close()

r = run("extractor.py", "--db", str(DB_LIMIT), "--limite", "1")
s = parse_stats(r.stdout)
assert s == {"processadas": 1, "preenchidas": 1, "sem_metadados": 0, "erros": 0}, s
con = sqlite3.connect(DB_LIMIT)
con.row_factory = sqlite3.Row
first = con.execute(
    "SELECT t.prompt_positivo FROM images_text AS t JOIN images AS i ON i.id = t.rowid WHERE i.file_path = ?",
    (str(ROOT / "a1111.png"),),
).fetchone()
assert first["prompt_positivo"] == "a majestic gato laranja, on the beach at sunset"
second = con.execute(
    "SELECT t.prompt_positivo, t.prompt_negativo, t.workflow_json FROM images_text AS t "
    "JOIN images AS i ON i.id = t.rowid WHERE i.file_path = ?",
    (str(ROOT / "plain.png"),),
).fetchone()
assert (second["prompt_positivo"], second["prompt_negativo"], second["workflow_json"]) == ("", "", "")
con.close()

print("TODOS OS TESTES DE PROCESSAMENTO PASSARAM")
