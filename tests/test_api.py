import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import quote

from PIL import Image
from PIL.PngImagePlugin import PngInfo

BACKEND = Path(__file__).resolve().parents[1] / "backend"
ROOT = Path("/tmp/opencode/fixtures_api")
DB = Path("/tmp/opencode/fixtures_api.db")
PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"
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
    DB.unlink(missing_ok=True)
    Path(str(DB) + "-wal").unlink(missing_ok=True)
    Path(str(DB) + "-shm").unlink(missing_ok=True)

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

    sub = ROOT / "sub"
    sub.mkdir()
    save_png(sub / WEIRD)

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (0, 0, 255)).save(buf, "PNG")
    with zipfile.ZipFile(ROOT / "pacote.zip", "w") as zf:
        zf.writestr("dentro.png", buf.getvalue())
    return buf.getvalue()


def run_cli(script, *args):
    r = subprocess.run(
        [sys.executable, str(BACKEND / script), *args], capture_output=True, text=True
    )
    print(f"$ {script} {' '.join(args)}")
    print(r.stdout.rstrip())
    assert r.returncode == 0, r.stderr


def fetch(path, method="GET", headers=None):
    req = urllib.request.Request(BASE + path, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read()


def fetch_json(path):
    status, headers, body = fetch(path)
    return status, dict(headers), json.loads(body)


zip_bytes = build_fixtures()
run_cli("scanner.py", str(ROOT), "--db", str(DB))
run_cli("extractor.py", "--db", str(DB))

con = sqlite3.connect(DB)
a1111_id = con.execute(
    "SELECT id FROM images WHERE file_path LIKE '%a1111.png'"
).fetchone()[0]
con.execute("INSERT INTO image_tags (image_id, tag) VALUES (?, '1girl')", (a1111_id,))
comfy_id = con.execute(
    "SELECT id FROM images WHERE file_path LIKE '%comfy.png'"
).fetchone()[0]
con.execute("INSERT INTO image_tags (image_id, tag) VALUES (?, 'explicit')", (comfy_id,))
con.commit()
con.close()

log = open("/tmp/opencode/uvicorn_test.log", "w")
server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)],
    cwd=str(BACKEND),
    env={**os.environ, "CATALOG_DB": str(DB)},
    stdout=log,
    stderr=subprocess.STDOUT,
)

try:
    deadline = time.time() + 20
    while True:
        try:
            status, _, _ = fetch("/images?limit=1")
            if status == 200:
                break
        except Exception:
            pass
        if time.time() > deadline:
            log.flush()
            print(open("/tmp/opencode/uvicorn_test.log").read())
            raise AssertionError("servidor nao subiu")
        time.sleep(0.2)

    status, headers, body = fetch(
        "/images?limit=2&offset=0", headers={"Origin": "http://localhost:5173"}
    )
    data = json.loads(body)
    assert status == 200
    assert headers.get("access-control-allow-origin") == "*", dict(headers)
    assert data["total"] == 5 and data["limit"] == 2 and data["offset"] == 0
    assert len(data["items"]) == 2
    item = data["items"][0]
    assert set(item) == {
        "id", "file_name", "file_size", "file_path", "media_url", "tags", "is_nsfw"
    }
    assert item["media_url"] == "/media/" + quote(item["file_path"].lstrip("/"))
    assert isinstance(item["tags"], list) and isinstance(item["is_nsfw"], bool)

    _, _, data_b = fetch_json("/images?limit=2&offset=2")
    assert len(data_b["items"]) == 2
    _, _, data_c = fetch_json("/images?limit=2&offset=4")
    assert len(data_c["items"]) == 1
    _, _, data_d = fetch_json("/images?limit=2&offset=6")
    assert data_d["items"] == []
    all_ids = (
        [it["id"] for it in data["items"]]
        + [it["id"] for it in data_b["items"]]
        + [it["id"] for it in data_c["items"]]
    )
    assert sorted(all_ids) == [1, 2, 3, 4, 5]

    _, _, full = fetch_json("/images?limit=500")
    items = full["items"]
    assert full["total"] == 5

    status, headers, _ = fetch(
        "/images",
        method="OPTIONS",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert status == 200
    assert headers.get("access-control-allow-origin") == "*"

    a1111 = next(it for it in items if it["file_path"].endswith("a1111.png"))
    comfy = next(it for it in items if it["file_path"].endswith("comfy.png"))
    weird = next(it for it in items if "d'água" in it["file_path"])

    # blacklist NSFW: interseção tags ∩ NSFW_BLACKLIST define a flag
    assert a1111["tags"] == ["1girl"] and a1111["is_nsfw"] is False
    assert comfy["tags"] == ["explicit"] and comfy["is_nsfw"] is True
    assert weird["tags"] == [] and weird["is_nsfw"] is False

    status, _, detail = fetch_json(f"/images/{a1111['id']}")
    assert status == 200
    assert detail["prompt_positivo"] == "a majestic gato laranja, on the beach at sunset"
    assert detail["prompt_negativo"] == "blurry, extra digits"
    assert detail["workflow_json"].startswith("Steps: 20")
    assert detail["image_id"] == detail["id"]
    assert detail["file_path"] == a1111["file_path"]
    assert detail["media_url"] == "/media/" + quote(detail["file_path"].lstrip("/"))
    assert "mtime" in detail and "indexed_at" in detail and "file_size" in detail
    assert detail["tags"] == ["1girl"]

    status, _, weird_detail = fetch_json(f"/images/{weird['id']}")
    assert status == 200
    assert weird_detail["tags"] == []

    status, _, _ = fetch_json("/images/99999")
    assert status == 404

    status, _, data = fetch_json("/search?q=" + quote("gato"))
    assert status == 200 and data["total"] == 2
    assert sorted(it["file_path"] for it in data["items"]) == sorted(
        [a1111["file_path"], comfy["file_path"]]
    )
    assert all("tags" in it and "is_nsfw" in it for it in data["items"])
    search_comfy = next(
        it for it in data["items"] if it["file_path"] == comfy["file_path"]
    )
    assert search_comfy["is_nsfw"] is True and search_comfy["tags"] == ["explicit"]

    _, _, data = fetch_json("/search?q=" + quote("borrão"))
    assert data["total"] == 1 and data["items"][0]["file_path"] == comfy["file_path"]

    _, _, data = fetch_json("/search?q=" + quote("zzz_inexistente"))
    assert data["total"] == 0 and data["items"] == []

    _, _, data = fetch_json("/search?q=" + quote("prompt_negativo: borrão"))
    assert data["total"] == 1 and data["items"][0]["file_path"] == comfy["file_path"]

    status, _, body = fetch("/search?q=%22")
    assert status == 400, (status, body)

    status, headers, body = fetch(a1111["media_url"])
    assert status == 200
    assert headers.get_content_type() == "image/png"
    assert body == (ROOT / "a1111.png").read_bytes()

    status, _, body = fetch(weird["media_url"])
    assert status == 200, weird["media_url"]
    assert body == (ROOT / "sub" / WEIRD).read_bytes()

    # 6) streaming de membro de ZIP (INV-12): 200 + bytes reais, 404 limpo nos erros
    zip_item = next(it for it in items if "::" in it["file_path"])
    assert zip_item["media_url"] == "/media/" + quote(zip_item["file_path"].lstrip("/"))
    status, _, zip_detail = fetch_json(f"/images/{zip_item['id']}")
    assert status == 200
    assert zip_detail["media_url"] == zip_item["media_url"]

    status, headers, body = fetch(zip_item["media_url"])
    assert status == 200
    assert headers.get_content_type() == "image/png"
    assert body == zip_bytes

    status, _, _ = fetch(zip_item["media_url"].replace("dentro.png", "nao_existe.png"))
    assert status == 404

    (ROOT / "pacote.zip").write_bytes(b"isto nao e um zip")
    status, _, _ = fetch(zip_item["media_url"])
    assert status == 404

    os.remove(ROOT / "pacote.zip")
    status, _, _ = fetch(zip_item["media_url"])
    assert status == 404

    print("TODOS OS TESTES DA API PASSARAM")
finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
    log.close()
