import json
import shutil
import sqlite3
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
ROOT = Path("/tmp/opencode/fixtures_tags")
DB = Path("/tmp/opencode/fixtures_tags.db")
MOCK = ROOT / "tags_mock.json"

REAL_URL = (
    "https://raw.githubusercontent.com/gogarx/yandere-masonry/refs/heads/main/src/data/tags_cn.json"
)
MOCK_TAGS = {
    "1girl": "女孩",
    "long_hair": "长发",
    "masterpiece": "杰作",
    "cat_ears": "猫耳",
    "upper_body": "上半身",
}

PROMPTS = [
    ("1girl, long hair, (masterpiece:1.2), sunset", "blurry, extra digits"),
    ("a photo of a cat_ears closeup, upper_body", ""),
    ("um gato laranja na praia ao entardecer", "masterpiece"),
    ("", "1girl"),
]

sys.path.insert(0, str(BACKEND))
import tagger  # noqa: E402


def build_fixtures():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    DB.unlink(missing_ok=True)
    Path(str(DB) + "-wal").unlink(missing_ok=True)
    Path(str(DB) + "-shm").unlink(missing_ok=True)
    MOCK.write_text(json.dumps(MOCK_TAGS, ensure_ascii=False), encoding="utf-8")

    import init_db

    init_db.init_db(DB)
    con = sqlite3.connect(DB)
    for index, prompt in enumerate(PROMPTS):
        con.execute(
            "INSERT INTO images (file_path, file_name, file_size, mtime)"
            " VALUES (?, ?, ?, ?)",
            (f"/imgs/img{index}.png", f"img{index}.png", 10 + index, 1760000000.0 + index),
        )
        con.execute(
            "UPDATE images_text SET prompt_positivo = ?, prompt_negativo = ? WHERE rowid = ?",
            (prompt[0], prompt[1], index + 1),
        )
    con.commit()
    con.close()


def tags_of(con, image_id):
    return sorted(
        row[0]
        for row in con.execute(
            "SELECT tag FROM image_tags WHERE image_id = ?", (image_id,)
        )
    )


build_fixtures()

tagger.TAGS_URL = MOCK.as_uri()
keys = tagger.fetch_tag_keys()
assert keys == set(MOCK_TAGS), keys

stats = tagger.tag_prompts(DB, keys)
assert stats == {"processadas": 3, "inseridos": 4}, stats

con = sqlite3.connect(DB)
assert tags_of(con, 1) == ["1girl", "long_hair", "masterpiece"]
assert tags_of(con, 2) == ["upper_body"]
assert tags_of(con, 3) == []
assert tags_of(con, 4) == []

hits = con.execute(
    "SELECT i.file_path FROM image_tags AS g JOIN images AS i ON i.id = g.image_id"
    " WHERE g.tag = ? ORDER BY i.id",
    ("1girl",),
).fetchall()
assert [h[0] for h in hits] == ["/imgs/img0.png"]

stats = tagger.tag_prompts(DB, keys)
assert stats == {"processadas": 3, "inseridos": 0}, stats

try:
    con.execute("INSERT INTO image_tags (image_id, tag) VALUES (1, '1girl')")
    raise AssertionError("PK composta deveria ter falhado")
except sqlite3.IntegrityError:
    pass

con.execute("DELETE FROM images WHERE id = 1")
con.commit()
assert con.execute("SELECT count(*) FROM image_tags WHERE image_id = 1").fetchone()[0] == 0
assert con.execute("SELECT count(*) FROM image_tags").fetchone()[0] == 1
assert con.execute("SELECT count(*) FROM images_text WHERE rowid = 1").fetchone()[0] == 0
con.close()

try:
    with urllib.request.urlopen(REAL_URL, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
    real_keys = {tagger.normalize_token(k) for k in data}
    real_keys.discard("")
    print(f"probe da URL real: {len(data)} chaves carregadas (amostra: {sorted(real_keys)[:3]})")
    assert isinstance(data, dict) and len(real_keys) == len(data)
except Exception as err:
    print(f"aviso: URL real indisponivel agora ({err}) — fluxo local validado com mock")

print("TODOS OS TESTES DE TAGS PASSARAM")
