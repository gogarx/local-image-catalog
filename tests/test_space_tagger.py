import io
import os
import shutil
import sqlite3
import sys
import types
import zipfile
from pathlib import Path

from PIL import Image

BACKEND = Path(__file__).resolve().parents[1] / "backend"
ROOT = Path("/tmp/opencode/fixtures_space")
DB = Path("/tmp/opencode/fixtures_space.db")

sys.path.insert(0, str(BACKEND))
import space_tagger  # noqa: E402

SPACE_RESULT = {
    "rating": {"general": 0.9, "sensitive": 0.05, "questionable": 0.03, "explicit": 0.02},
    "character": {"rem_(re:zero)": 0.9},
    "general": {"1girl": 0.95, "long hair": 0.6, "bad hands": 0.2, "horns": 0.85},
}

REAL_SPACE_TUPLE = (
    "Rating: general\n\nCharacters: rem\n\nTags: 1girl, long_hair",
    {
        "label": None,
        "confidences": [
            {"label": "general", "confidence": 0.9},
            {"label": "sensitive", "confidence": 0.05},
        ],
    },
    {
        "label": None,
        "confidences": [{"label": "rem_(re:zero)", "confidence": 0.9}],
    },
    {
        "label": None,
        "confidences": [
            {"label": "1girl", "confidence": 0.95},
            {"label": "long hair", "confidence": 0.6},
            {"label": "bad hands", "confidence": 0.2},
            {"label": "horns", "confidence": 0.85},
        ],
    },
)

EMPTY_GENERAL_TUPLE = (
    "sem tags acima do limite",
    {"label": None, "confidences": [{"label": "general", "confidence": 0.9}]},
    {"label": None, "confidences": []},
    {"label": None, "confidences": []},
)


class FakeClient:
    def __init__(self, results):
        self.results = list(results)
        self.paths = []

    def predict(self, image, **kwargs):
        path = image["path"] if isinstance(image, dict) else str(image)
        assert os.path.exists(path), f"handle_file recebeu caminho inexistente: {path}"
        self.paths.append(path)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        assert kwargs["model_repo"] == space_tagger.MODEL_REPO
        assert kwargs["general_thresh"] == 0.35
        assert kwargs["general_mcut_enabled"] is False
        assert kwargs["character_thresh"] == 0.85
        assert kwargs["character_mcut_enabled"] is False
        assert kwargs["api_name"] == "/predict"
        return result


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


def build_fixtures():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    DB.unlink(missing_ok=True)
    Path(str(DB) + "-wal").unlink(missing_ok=True)
    Path(str(DB) + "-shm").unlink(missing_ok=True)

    member = png_bytes()
    with zipfile.ZipFile(ROOT / "pacote.zip", "w") as zf:
        zf.writestr("dentro.png", member)
    for name in ("solta.png", "flat.png", "vazia.png"):
        (ROOT / name).write_bytes(png_bytes())
    (ROOT / "apagada.png").write_bytes(png_bytes())

    import init_db

    init_db.init_db(DB)
    con = sqlite3.connect(DB)
    names = [
        "pacote.zip::dentro.png",
        "solta.png",
        "flat.png",
        "vazia.png",
        "apagada.png",
        "ja_taggada.png",
    ]
    for name in names:
        con.execute(
            "INSERT INTO images (file_path, file_name, file_size, mtime) VALUES (?, ?, ?, ?)",
            (str(ROOT / name), name, 1, 1.0),
        )
    con.execute(
        "INSERT INTO image_tags (image_id, tag, source) VALUES (6, 'local_tag', 'tagger')"
    )
    con.commit()
    con.close()
    os.remove(ROOT / "apagada.png")
    return member


def rows_of(con, image_id):
    return sorted(
        con.execute("SELECT tag, source FROM image_tags WHERE image_id = ?", (image_id,))
    )


member = build_fixtures()

assert space_tagger.extract_general_tags(SPACE_RESULT) == ["1girl", "horns", "long_hair"]
assert space_tagger.extract_general_tags(REAL_SPACE_TUPLE) == ["1girl", "horns", "long_hair"]
assert space_tagger.extract_general_tags(EMPTY_GENERAL_TUPLE) == []
assert space_tagger.extract_general_tags({"horns": 0.8, "smile": 0.1}) == ["horns"]
assert space_tagger.extract_general_tags("1girl: 0.95, cat_ears: 0.10") == ["1girl"]
assert space_tagger.extract_general_tags("Blue Eyes, horns") == ["blue_eyes", "horns"]
assert space_tagger.extract_general_tags("") == []

sleep_calls = []
space_tagger.time = types.SimpleNamespace(sleep=lambda seconds: sleep_calls.append(seconds))

fake = FakeClient(
    [
        REAL_SPACE_TUPLE,
        "1girl: 0.9, 1girl: 0.8",
        {"horns": 0.8, "smile": 0.1},
        "",
        RuntimeError("simulando falha do Space"),
    ]
)
stats = space_tagger.run(DB, client=fake)
assert stats == {
    "alvos": 5,
    "processadas": 5,
    "inseridos": 5,
    "sem_tags": 1,
    "erros": 1,
}, stats

assert fake.paths[0].startswith("/tmp")
assert not Path(fake.paths[0]).exists(), "temporario do ZIP deveria ter sido removido"
assert fake.paths[1] == str(ROOT / "solta.png")
assert fake.paths[2] == str(ROOT / "flat.png")
assert fake.paths[3] == str(ROOT / "vazia.png")
assert len(fake.paths) == 4

con = sqlite3.connect(DB)
assert rows_of(con, 1) == [
    ("1girl", "space_api"),
    ("horns", "space_api"),
    ("long_hair", "space_api"),
]
assert rows_of(con, 2) == [("1girl", "space_api")]
assert rows_of(con, 3) == [("horns", "space_api")]
assert rows_of(con, 4) == []
assert rows_of(con, 5) == []
assert rows_of(con, 6) == [("local_tag", "tagger")]
con.close()

assert sleep_calls == [5.0, 5.0, 5.0, 5.0], sleep_calls

stats = space_tagger.run(DB, client=FakeClient([SPACE_RESULT]))
assert stats == {
    "alvos": 2,
    "processadas": 2,
    "inseridos": 3,
    "sem_tags": 0,
    "erros": 1,
}, stats

stats = space_tagger.run(DB, client=FakeClient([]))
assert stats == {
    "alvos": 1,
    "processadas": 1,
    "inseridos": 0,
    "sem_tags": 0,
    "erros": 1,
}, stats

assert sleep_calls == [5.0, 5.0, 5.0, 5.0, 5.0]

con = sqlite3.connect(DB)
assert con.execute("SELECT count(*) FROM image_tags").fetchone()[0] == 9
assert con.execute("SELECT count(*) FROM image_tags WHERE source = 'space_api'").fetchone()[0] == 8
assert con.execute("SELECT count(*) FROM image_tags WHERE source = 'tagger'").fetchone()[0] == 1
assert rows_of(con, 4) == [
    ("1girl", "space_api"),
    ("horns", "space_api"),
    ("long_hair", "space_api"),
]
con.execute("DELETE FROM images WHERE id = 1")
con.commit()
assert con.execute("SELECT count(*) FROM image_tags WHERE image_id = 1").fetchone()[0] == 0
assert con.execute("SELECT count(*) FROM image_tags").fetchone()[0] == 6
con.close()

print("TODOS OS TESTES DO SPACE TAGGER PASSARAM")
