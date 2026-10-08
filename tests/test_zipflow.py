import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote

from PIL import Image
from PIL.PngImagePlugin import PngInfo

BACKEND = Path(__file__).resolve().parents[1] / "backend"
ROOT = Path("/tmp/opencode/fixtures_zip")
DB = Path("/tmp/opencode/fixtures_zip.db")

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


def a1111_meta():
    meta = PngInfo()
    meta.add_text("parameters", A1111_TEXT)
    return meta


def comfy_meta():
    meta = PngInfo()
    meta.add_text("prompt", json.dumps(COMFY_PROMPT))
    meta.add_text("workflow", json.dumps(COMFY_WORKFLOW))
    return meta


def png_bytes(meta=None, pad=0):
    if pad:
        meta = PngInfo()
        meta.add_text("parameters", A1111_TEXT + "\n" + "x" * pad)
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(buf, "PNG", pnginfo=meta)
    return buf.getvalue()


def webp_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (0, 255, 0)).save(buf, "WEBP")
    return buf.getvalue()


def build_fixtures():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    DB.unlink(missing_ok=True)
    Path(str(DB) + "-wal").unlink(missing_ok=True)
    Path(str(DB) + "-shm").unlink(missing_ok=True)

    with zipfile.ZipFile(ROOT / "backup.zip", "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a1111.png", png_bytes(a1111_meta()))
        zf.writestr("sub/comfy.png", png_bytes(comfy_meta()))
        zf.writestr("plain.png", png_bytes())
        zf.writestr("foto.webp", webp_bytes())
        zf.writestr("nota.txt", "nao sou imagem")
        zf.writestr(".hidden/x.png", png_bytes())
        zf.writestr("__MACOSX/junk.png", png_bytes())
        zf.writestr("dup.png", png_bytes())
        zf.writestr("dup.png", png_bytes(a1111_meta()))
    with zipfile.ZipFile(ROOT / "big.zip", "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.png", png_bytes(pad=4_600_000))
    with zipfile.ZipFile(ROOT / "perdido.zip", "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("perdido.png", png_bytes())
    (ROOT / "solta.png").write_bytes(png_bytes(a1111_meta()))
    (ROOT / "mau::x.png").write_bytes(png_bytes())
    (ROOT / "corrompido.zip").write_bytes(b"isto nao e um zip")


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
assert s == {"adicionadas": 8, "atualizadas": 0, "inalteradas": 0, "erros": 1}, s

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
by_path = {
    row["file_path"]: row
    for row in con.execute("SELECT * FROM images ORDER BY id").fetchall()
}
assert len(by_path) == 8

backup = str(ROOT / "backup.zip")
virt_a1111 = f"{backup}::a1111.png"
virt_comfy = f"{backup}::sub/comfy.png"
virt_plain = f"{backup}::plain.png"
virt_webp = f"{backup}::foto.webp"
virt_dup = f"{backup}::dup.png"
virt_big = f"{str(ROOT / 'big.zip')}::big.png"
virt_perdido = f"{str(ROOT / 'perdido.zip')}::perdido.png"
solta = str(ROOT / "solta.png")

for p in (virt_a1111, virt_comfy, virt_plain, virt_webp, virt_dup, virt_big, virt_perdido, solta):
    assert p in by_path, p
assert not any(
    ".hidden" in p or "__MACOSX" in p or "nota.txt" in p or "mau::" in p for p in by_path
)

with zipfile.ZipFile(backup) as zf:
    assert by_path[virt_a1111]["file_size"] == zf.getinfo("a1111.png").file_size
    assert by_path[virt_webp]["file_size"] == zf.getinfo("foto.webp").file_size
assert by_path[virt_a1111]["file_name"] == "a1111.png"
assert by_path[virt_comfy]["file_name"] == "comfy.png"
assert by_path[virt_a1111]["mtime"] == os.stat(backup).st_mtime
assert by_path[virt_big]["mtime"] == os.stat(ROOT / "big.zip").st_mtime
assert by_path[solta]["file_size"] == (ROOT / "solta.png").stat().st_size

r = run("scanner.py", str(ROOT), "--db", str(DB))
s = parse_stats(r.stdout)
assert s == {"adicionadas": 0, "atualizadas": 0, "inalteradas": 8, "erros": 1}, s

os.utime(backup, ns=(1600000000 * 10**9,) * 2)
r = run("scanner.py", str(ROOT), "--db", str(DB))
s = parse_stats(r.stdout)
assert s == {"adicionadas": 0, "atualizadas": 5, "inalteradas": 3, "erros": 1}, s
assert (
    con.execute("SELECT mtime FROM images WHERE file_path = ?", (virt_a1111,)).fetchone()[0]
    == 1600000000.0
)

os.remove(ROOT / "perdido.zip")
r = run("extractor.py", "--db", str(DB))
s = parse_stats(r.stdout)
assert s == {"processadas": 8, "preenchidas": 5, "sem_metadados": 2, "erros": 1}, s


def fts(path):
    return con.execute(
        "SELECT t.prompt_positivo, t.prompt_negativo, t.workflow_json "
        "FROM images_text AS t JOIN images AS i ON i.id = t.rowid WHERE i.file_path = ?",
        (path,),
    ).fetchone()


a = fts(virt_a1111)
assert a["prompt_positivo"] == "a majestic gato laranja, on the beach at sunset"
assert a["prompt_negativo"] == "blurry, extra digits"
assert a["workflow_json"].startswith("Steps: 20")

c = fts(virt_comfy)
assert c["prompt_positivo"] == "um gato laranja na praia ao entardecer"
assert c["prompt_negativo"] == "dedos extras, borrão"
assert c["workflow_json"] == json.dumps(COMFY_WORKFLOW)

d = fts(virt_dup)
assert d["prompt_positivo"] == "a majestic gato laranja, on the beach at sunset"

b = fts(virt_big)
assert b["prompt_positivo"] == "a majestic gato laranja, on the beach at sunset"
assert b["workflow_json"].startswith("Steps: 20")
assert len(b["workflow_json"]) > 4_600_000

s_row = fts(solta)
assert s_row["prompt_positivo"] == "a majestic gato laranja, on the beach at sunset"

for p in (virt_plain, virt_webp, virt_perdido):
    t = fts(p)
    assert (t["prompt_positivo"], t["prompt_negativo"], t["workflow_json"]) == ("", "", "")

hits = con.execute(
    "SELECT i.file_path FROM images_text(?) AS t JOIN images AS i ON i.id = t.rowid",
    ("gato",),
).fetchall()
assert sorted(h[0] for h in hits) == sorted(
    [virt_a1111, virt_comfy, virt_dup, virt_big, solta]
)

r = run("extractor.py", "--db", str(DB))
s = parse_stats(r.stdout)
assert s == {"processadas": 3, "preenchidas": 0, "sem_metadados": 2, "erros": 1}, s

os.environ["CATALOG_DB"] = str(DB)
sys.path.insert(0, str(BACKEND))
import main as api_main

assert api_main.media_url(virt_a1111) == "/media/" + quote(virt_a1111.lstrip("/"))
assert api_main.media_url(solta) == "/media/" + quote(solta.lstrip("/"))

con.close()
print("TODOS OS TESTES DE ZIP PASSARAM")
