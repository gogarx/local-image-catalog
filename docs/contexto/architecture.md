# architecture.md — Como o sistema é construído

O ecossistema é desacoplado em três blocos independentes que conversam por
meio de uma base de dados comum: **SQLite em modo WAL** — que permite leituras
simultâneas (API/frontend) durante a indexação (scanner/extractor/tagger).
Cada bloco roda sozinho; nenhum conhece os outros além do banco (e, no caso do
frontend, da API HTTP).

## 1. Blocos e diretórios

| Bloco | Pasta | Papel |
|---|---|---|
| Núcleo de dados | `backend/` | `catalog.db` (SQLite WAL + FTS5), schema criado por `init_db.py` |
| Processamento (CLI) | `backend/*.py` | Módulos escritores: scanner, extractor, tagger, space_tagger |
| API HTTP | `backend/main.py` | FastAPI somente leitura + streaming de mídia |
| Interface | `frontend/` | Vue 3 + Vite + Tailwind CSS 4, galeria local |
| Testes | `tests/` | Suítes de regressão standalone (§9) |
| Contexto | `docs/contexto/` | prd, architecture, rules, design, task, memory, agent |

```
backend/catalog.db       banco (WAL; -wal/-shm ao lado durante o uso)
backend/init_db.py       schema idempotente (única fonte de schema, INV-09)
backend/scanner.py       disco -> images
backend/extractor.py     images -> texts em images_text
backend/tagger.py        prompts -> tags em image_tags (dicionário local)
backend/space_tagger.py  images sem tags -> tags via Space WD-Tagger (rede)
backend/main.py          API FastAPI read-only + /media
backend/requirements.txt deps pinadas (falta gradio_client — ver task.md)
backend/.venv/           venv do projeto (não rastreado no git)
frontend/src/            App.vue, api/{client,catalog}.js, components/
tests/test_*.py          regressão standalone
```

## 2. Núcleo de dados — schema (v3, `PRAGMA user_version = 3`)

Requisito: SQLite compilado com **FTS5** (`init_db.py` valida e aborta com
mensagem clara se faltar). Histórico de versões: v1 base; v2 tabela + índice
`image_tags` e trigger `image_tags_ad`; v3 coluna `source` em `image_tags`
(migração v2→v3 roda automática no `init_db.py`).

### 2.1 `images` — fonte da verdade sobre os arquivos do disco

| coluna | tipo | regra |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | imutável na prática (INV-07); espelhado no `rowid` de `images_text` |
| `file_path` | TEXT NOT NULL UNIQUE | caminho absoluto OU caminho virtual de ZIP (`/backup.zip::pasta/img.png`, INV-12); 1 arquivo = 1 linha (INV-01) |
| `file_name` | TEXT NOT NULL | nome base, para exibição |
| `file_size` | INTEGER NOT NULL | bytes (membro de ZIP: tamanho descomprimido) |
| `mtime` | REAL NOT NULL | epoch Unix em segundos; base para detectar arquivo alterado |
| `indexed_at` | TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP | UTC `YYYY-MM-DD HH:MM:SS` |

### 2.2 `images_text` — tabela virtual FTS5 (busca por texto)

| coluna | papel |
|---|---|
| `image_id` (UNINDEXED) | vínculo com `images.id`; sempre igual ao `rowid` da própria linha (INV-03) |
| `prompt_positivo` | texto buscável (indexado) |
| `prompt_negativo` | texto buscável (indexado) |
| `workflow_json` | texto buscável (indexado; JSON tokenizado como texto comum) |

Notas FTS5 (comportamento verificado em testes): `image_id` é UNINDEXED porque
é identificador, não termo de busca; o FTS5 **não aceita tipos declarados**
nas colunas e preserva o inteiro gravado pelos triggers (comparações
`WHERE image_id = 5` casam). Junções e lookups usam `rowid` (canônico, sempre
inteiro e indexado). `''` nos três campos = "ainda não extraído / sem
metadados" (INV-05), e a imagem não aparece em buscas FTS (não gera tokens).

### 2.3 Triggers — manutenção das relações

| trigger | evento em `images` | ação |
|---|---|---|
| `images_ai` | AFTER INSERT | cria a linha gêmea em `images_text`: `rowid = image_id = new.id`, textos `''` |
| `images_au` | AFTER UPDATE (guarda `WHEN new.id <> old.id`) | re-aponta `rowid`/`image_id`; **texto já indexado é preservado** |
| `images_ad` | AFTER DELETE | remove a linha gêmea (`WHERE rowid = old.id`) |
| `image_tags_ad` | AFTER DELETE | remove os vínculos de tags (`WHERE image_id = old.id`) |

### 2.4 `image_tags` — palavras-chave por imagem

| coluna | tipo | regra |
|---|---|---|
| `image_id` | INTEGER NOT NULL | espelha `images.id` (INV-03) |
| `tag` | TEXT NOT NULL | termo padronizado (ex.: `1girl`, `long_hair`) |
| `source` | TEXT NOT NULL DEFAULT 'tagger' | `'tagger'` (dicionário local) ou `'space_api'` (Space WD-Tagger) |

`PRIMARY KEY (image_id, tag)` deduplica vínculos; índice `idx_image_tags_tag`
acelera busca por tag. Escrita exclusiva de `tagger.py` e `space_tagger.py`
com `INSERT OR IGNORE` (INV-13) — pode rodar quantas vezes quiser. Sem FOREIGN
KEY (cascata por triggers, já que `PRAGMA foreign_keys` é off por padrão no
SQLite).

## 3. Pipeline de processamento (módulos CLI)

Fluxo padrão — etapas independentes, sempre nesta ordem, **nunca em paralelo**:

```
python3 backend/init_db.py            (uma vez; os módulos também auto-garantem o schema)
python3 backend/scanner.py <pasta>    disco -> images
python3 backend/extractor.py          images -> textos em images_text
python3 backend/tagger.py             images_text -> tags em image_tags
python3 backend/space_tagger.py       images sem tags -> Space WD-Tagger (opcional, requer rede)
consulta FTS (UI/API)                  images_text MATCH ... JOIN images ...
```

Todos os módulos: `--db CAMINHO` para bancos de teste (padrão
`backend/catalog.db`), SQL 100% com placeholders `?`, gravações em lotes de
500 (commit incremental; execução interrompida retoma de graça), erros
individuais nunca abortam a execução.

### 3.1 scanner.py — varredura do disco

Uso: `python3 backend/scanner.py <pasta> [--db CAMINHO]`

- `os.walk` recursivo (não segue symlink de pasta, pula pastas ocultas
  `.*`); aceita png, jpg, jpeg, webp, gif, bmp, tif, tiff; grava `file_path`
  absoluto, `file_name`, `file_size`, `mtime`.
- Encontra `.zip`: NÃO descompacta — lê a árvore interna com `zipfile`,
  coleta membros `.png`/`.webp` e grava caminhos virtuais `zip::membro`
  (INV-12). ZIP corrompido vira "erro" e a varredura segue.
- **Idempotência (INV-01)**: linha existente com o MESMO `file_size` e `mtime`
  é pulada ("inalteradas"); diferente → `UPDATE` por `id` preservando texto
  FTS (INV-06) e `indexed_at`.
- **Não remove** linhas de arquivos apagados do disco (remoção é sempre
  receita explícita). Nunca escreve em `images_text`.
- Saída: `{adicionadas, atualizadas, inalteradas, erros}`.

### 3.2 extractor.py — extração de prompts/workflow

Uso: `python3 backend/extractor.py [--db CAMINHO] [--limite N]`

- "Pendente" = três campos de texto vazios (INV-05); processa os `id`s mais
  antigos primeiro (`ORDER BY i.id LIMIT ?`).
- Abre cada pendente com `PIL.Image.open` (read-only: só cabeçalho e
  `img.info`; pixels nunca decodificados) e grava com `UPDATE images_text ...
  WHERE rowid = ?` — a única escrita direta legítima em `images_text` (INV-04).
- Caminho com `::` (INV-12): `zipfile.ZipFile.open()` lê cabeçalho de bytes
  para `io.BytesIO` (limite de 4 MiB — os chunks de metadados ficam antes do
  IDAT do PNG); metadado que estourar o limite → membro relido inteiro como
  fallback. ZIP apagado/corrompido/criptografado → "erro", linha permanece
  pendente.
- Formatos reconhecidos no `img.info`:
  - **A1111/Forge WebUI** (chunk `parameters`): linhas antes de
    `Negative prompt:` → `prompt_positivo`; de `Negative prompt:` até `Steps:`
    → `prompt_negativo`; linha `Steps: ...` → `workflow_json` (texto plano).
  - **ComfyUI** (chunks `prompt` + `workflow`): `workflow_json` recebe o JSON
    de `workflow` (ou de `prompt`, se `workflow` não existir); prompts
    resolvidos seguindo as entradas `positive`/`negative` do nó `*KSampler*`
    até o nó `*TextEncode*` (um salto). Grafo exótico sem resolução → prompts
    vazios, conteúdo integral pesquisável em `workflow_json`.
- **Autocorreção intencional**: imagens sem metadados continuam vazias e
  re-tentadas a cada execução (custo baixo: só o cabeçalho); metadados
  embutidos depois são detectados na próxima rodada.
- Limitação conhecida: lê apenas chunks de texto PNG — EXIF de JPEG
  (UserComment do A1111) ainda não é lido.
- Saída: `{processadas, preenchidas, sem_metadados, erros}`.

### 3.3 tagger.py — categorização por dicionário

Uso: `python3 backend/tagger.py [--db CAMINHO]`

- Baixa o dicionário de `TAGS_URL` (yandere-masonry, `src/data/tags_cn.json`)
  via `urllib` e usa APENAS as **chaves** do JSON (valores ignorados). Sem
  rede, HTTP de erro ou JSON inválido → aborta (nenhuma tag inventada).
- Percorre `prompt_positivo <> ''` e tokeniza: split por vírgula/quebra de
  linha, strip de `()[]{}` das bordas, sufixo de peso `:1.2` removido,
  lowercase, espaços viram `_` — `(long hair:1.3)` → `long_hair`.
- Tag só conta como **termo isolado** (o token inteiro igual à chave;
  `cat_ears` NÃO casa com "closeup of cat_ears"). Interseção token∩chave →
  `INSERT OR IGNORE INTO image_tags (image_id, tag) VALUES (?, ?)` (INV-13).
  Só `prompt_positivo` gera tags.
- Saída: `{chaves, processadas, inseridos}`.

### 3.4 space_tagger.py — tags via Hugging Face Space (opcional, rede)

Uso: `python3 backend/space_tagger.py [--db CAMINHO] [--limite N]`

- Alvos: imagens SEM nenhum registro em `image_tags` (`NOT EXISTS`) —
  complementa o tagger local, que só marca quem tem prompt.
- Chamada: `client.predict(image=handle_file(...), model_repo=
  "SmilingWolf/wd-swinv2-tagger-v3", general_thresh=0.35,
  general_mcut_enabled=False, character_thresh=0.85,
  character_mcut_enabled=False, api_name="/predict")` no Space
  `SmilingWolf/wd-tagger` (gradio_client). Os nomes dos parâmetros mudam sem
  aviso — `client.view_api()` é a fonte oficial; erro de parâmetro → a imagem
  vira "erro" e continua alvo. `run(db_path, limit, client=None)` aceita
  cliente injetado (usado pelos testes).
- Parser: do retorno (tupla de Labels do Gradio) pega o bloco de tags gerais
  (terceiro Label quando há 3 blocos de confianças), descarta rating
  (`RATING_KEYS`: general/sensitive/questionable/explicit) e characters,
  filtra score > 0.35 e normaliza (lowercase, espaços → `_`). Formatos
  alternativos suportados: dict com seção `general`, dict plano, string
  "tag: score".
- Caminhos virtuais (INV-12): membro extraído para temporário FÍSICO em `/tmp`
  (`tempfile.mkstemp`, sufixo original), passado ao `handle_file()` e REMOVIDO
  no `finally` — exceção documentada à regra "nada em disco", vida útil de
  uma requisição.
- Throttling: `time.sleep(5)` após cada sucesso (rate limit do HF); erro não
  pausa, só conta, e a imagem permanece alvo.
- Gravação: `INSERT OR IGNORE INTO image_tags (image_id, tag, source)
  VALUES (?, ?, 'space_api')` (INV-13); commit por imagem preserva o
  progresso. Sem rede/Space fora do ar: erros por imagem e o sistema local
  segue 100% funcional.
- Saída: `{alvos, processadas, inseridos, sem_tags, erros}`.

## 4. Receitas SQL aprovadas (testadas)

Indexar arquivo novo (indexer):

```sql
INSERT INTO images (file_path, file_name, file_size, mtime)
VALUES (?, ?, ?, ?);
-- images_ai cria a linha FTS automaticamente (textos vazios)
```

Preencher os textos (extractor, após extrair metadados embutidos):

```sql
UPDATE images_text
SET prompt_positivo = ?, prompt_negativo = ?, workflow_json = ?
WHERE rowid = ?;  -- o images.id correspondente
```

Buscar por texto (UI/API), forma função-de-tabela (junção por rowid, INV-03):

```sql
SELECT i.id, i.file_path, i.file_name, t.prompt_positivo
FROM images_text(?) AS t
JOIN images AS i ON i.id = t.rowid
ORDER BY t.rank;
```

Formas equivalentes de MATCH: sem alias, `WHERE images_text MATCH ?`; com
alias, `WHERE t.images_text MATCH ?`. Restrição a coluna no padrão:
`'prompt_positivo: gato NOT praia'`, `'workflow_json: euler'`.

Re-indexar arquivo alterado no disco (o scanner atualiza por `id`, preservando
texto FTS — INV-06):

```sql
UPDATE images
SET file_size = ?, mtime = ?, indexed_at = CURRENT_TIMESTAMP
WHERE id = ?;
```

Remover arquivo que sumiu do disco:

```sql
DELETE FROM images WHERE file_path = ?;
-- images_ad limpa o FTS e image_tags_ad limpa as tags automaticamente
```

Buscar por tag (índice `idx_image_tags_tag`):

```sql
SELECT i.id, i.file_path, i.file_name
FROM image_tags AS g
JOIN images AS i ON i.id = g.image_id
WHERE g.tag = ?;
```

Vínculo manual pontual (exceção de administração; caminho normal é o tagger):

```sql
INSERT OR IGNORE INTO image_tags (image_id, tag) VALUES (?, ?);
```

## 5. API HTTP (backend/main.py) — FastAPI + uvicorn, somente leitura

Consome `backend/catalog.db` e serve JSON + arquivos locais. Endpoints
síncronos (threadpool do uvicorn), uma conexão SQLite por request
(`timeout=5.0`); o WAL permite a API ler enquanto o scanner grava. A API
garante o schema ao importar (`init_db.init_db`, idempotente e silencioso).

### 5.1 Subir o servidor

```bash
cd backend
source .venv/bin/activate        # fastapi, uvicorn, pillow, gradio_client
uvicorn main:app --host 127.0.0.1 --port 8000
```

- Hot-reload: `uvicorn main:app --reload --port 8000`
- Sem ativar o venv: `cd backend && .venv/bin/uvicorn main:app --port 8000`
- Alternativa programática: `.venv/bin/python main.py`
- Swagger: `http://127.0.0.1:8000/docs`
- **Sempre `--host 127.0.0.1`** (ver 5.4)

### 5.2 Endpoints

| Rota | O que faz |
|---|---|
| `GET /images?limit=&offset=` | página da galeria; envelope `{total, limit, offset, items}` — items: `id`, `file_name`, `file_size`, `file_path`, `media_url` (derivado, URL-encoded), `tags` (lista minúscula lida de `image_tags` por item) e `is_nsfw` (true quando a interseção entre as tags da imagem e `NSFW_BLACKLIST` — conjunto imutável definido no topo do `main.py` — é não vazia). `ORDER BY id`; `limit` 1..500 (padrão 50), `offset` >= 0. |
| `GET /images/{image_id}` | detalhes: JOIN por `rowid` (INV-03) — metadados + `prompt_positivo`, `prompt_negativo`, `workflow_json`, `image_id`, `media_url` e `tags` (lista alfabética de `image_tags`). 404 "imagem não encontrada" se não existir. |
| `GET /search?q=…` | FTS5 (`images_text(?)`), `ORDER BY t.rank` (bm25); envelope `{q, total, limit, offset, items}` — cada item traz os campos de `/images` (incluindo `tags` e `is_nsfw`) **+ `prompt_positivo`**. Filtro por coluna: `q=prompt_negativo: borrão`. Sintaxe FTS inválida → **400** com a mensagem do SQLite (heurística: só mensagens com "fts5", "unterminated string" ou "unknown special query"; demais `OperationalError` viram 500). |
| `/media/<caminho>` | mídia direto da máquina: arquivos físicos via `CatalogFiles` (subclasse de `StaticFiles`) montado na raiz (`CATALOG_MEDIA_ROOT`, padrão `/`); caminhos com `::` (INV-12) são lidos do `.zip` para `io.BytesIO` e respondidos como `StreamingResponse` (chunks de 64 KiB + `Content-Length`) com `media_type` correto. ZIP corrompido/apagado/membro inexistente → **404 limpo**. É a URL (encodeada: `::` → `%3A%3A`) que o `<img>` da galeria consome. |

- `media_url`: derivado de `file_path` com `quote()`; **vazio quando o arquivo
  não está sob `CATALOG_MEDIA_ROOT`** — o frontend, nesse caso, mostra apenas
  o nome do arquivo (sem `<img>`).
- `media_type` de ZIP: `image/png`, `image/webp`, `image/jpeg` (jpg/jpeg),
  `image/gif`; fallback `mimetypes.guess_type`, default
  `application/octet-stream`.
- Guarda de path traversal: o carregador de membro resolve `realpath` e
  recusa (404) `.zip` físico fora de `CATALOG_MEDIA_ROOT`.

### 5.3 Variáveis de ambiente

| Variável | Padrão | Efeito |
|---|---|---|
| `CATALOG_DB` | `backend/catalog.db` | banco usado pela API (útil para testes) |
| `CATALOG_MEDIA_ROOT` | `/` | raiz servida pelo `/media` |
| `CATALOG_PORT` | `8000` | porta no modo `python main.py` |

### 5.4 CORS e escopo de segurança (decisões conscientes)

- `allow_origins=["*"]`: qualquer origem lê a API — é o que faz o dev server
  do Vite funcionar sem configuração extra.
- `/media` com raiz `/` serve **qualquer arquivo legível do disco**, não só
  os catalogados. Com CORS `*`, qualquer site aberto no navegador pode ler
  esses endpoints enquanto o servidor estiver de pé. Aceito por ser app 100%
  local — MITIGAÇÃO OBRIGATÓRIA: bind em `127.0.0.1`, nunca portar para fora.
  Se um dia precisar de mais isolamento: restrinja `CATALOG_MEDIA_ROOT` à
  pasta das imagens ou troque `/media` por rota que só sirva caminhos
  presentes na tabela `images`.
- A API não autentica nada — mesma confiança de um arquivo aberto no disco.

### 5.5 Linhagem — como esta API aposentou o pipeline do Matrix legado

Este serviço existe para resolver, no plano local, o gargalo que condenava o
projeto antigo `matrix-photo-gallery`
(`/home/gogarx/Backup_HD_antigo/gogarx/Downloads/program/matrix-photo-gallery/`).
Lá, a galeria era uma sombra de dados remotos: `matrix_client` 0.3.2 mantinha
uma conexão autenticada ao homeserver (o login por token sequer funcionava —
`login_with_token` é método inexistente nessa versão da lib e quebrava com
`AttributeError`), o importador percorria os eventos `m.image` das salas em
lotes de mil mensagens por chamada `get_room_messages`, e o MongoDB via
mongoengine persistia apenas apontadores — `room_id`, `event_id`, `sender`,
`timestamp` e as URLs de download geradas por `api.get_download_url()`. Cada
foto exibida era, portanto, um download remoto no meio da navegação; as
miniaturas nativas do Matrix eram grandes demais a ponto de exigir um
pipeline paralelo (`make-small-thumbnails`) que as reprocessava e empurrava
para um bucket S3. E quando qualquer elo dessa corrente caía — rede,
credencial, o Python 3.6.5 pinado, o Flask <2.0 — o frontend nem reclamava:
substituía silenciosamente a galeria por 100 imagens falsas do
`picsum.photos`, sem erro visível ao usuário.

A nova API inverte o modelo: o arquivo já está na máquina. O scanner indexa o
disco uma única vez (idempotente, INV-01), o SQLite local em modo WAL é a
fonte da verdade, e o FastAPI atende em `127.0.0.1` com endpoints síncronos
e uma conexão por request. No lugar dos três saltos do legado (navegador →
Flask → homeserver Matrix, mais a dependência opcional do S3 para
miniaturas), a mídia percorre um único salto local: `/media` serve o arquivo
físico direto do disco via `StaticFiles` e, quando o caminho aponta para
dentro de um `.zip` (INV-12), o `zipfile` lê apenas o membro pedido para um
`io.BytesIO` — streaming síncrono inteiramente em RAM, em chunks de 64 KiB
com `Content-Length` — respondendo com o `media_type` correto, sem
descompactar nada, sem arquivo extra no disco, sem rede, sem credenciais e
sem serviço intermediário. A lentidão do sistema antigo nunca foi só o
banco: era o modelo inteiro de "metadados aqui, bytes lá". Ao trazer os
bytes para a mesma máquina dos metadados — e ao trocar a conexão viva às
salas e a sessão mongoengine por um arquivo SQLite garantido por triggers
(INV-02/INV-03) — a API eliminou a latência de rede, os pontos de falha
externos e o estado de sessão: a coerência agora nasce do próprio banco, e o
WAL permite consultar a galeria enquanto o scanner grava.

## 6. Frontend (Vue 3 + Vite + Tailwind CSS 4)

Stack: Vue 3 (`<script setup>`), Vite, Tailwind 4 (plugin
`@tailwindcss/vite`), `fetch` nativo (sem axios). Requer Node.js + npm.

```bash
cd frontend
npm install          # primeira vez
npm run dev          # http://localhost:5173
npm run build        # dist/ (rotas relativas)
npm run preview      # serve o build final
```

### 6.1 Módulos

| Arquivo | Papel |
|---|---|
| `src/api/client.js` | base URL dinâmica (`import.meta.env.VITE_API_URL` ?? relativa; `/` finais removidos) + `request(path, { signal })` com tratamento de erro (mostra o `detail` do FastAPI) |
| `src/api/catalog.js` | `fetchImages`, `fetchImage`, `searchImages` — espelham os endpoints da §5.2; aceitam `{limit, offset, signal}` |
| `src/App.vue` | raiz: estado de busca/página/seleção; PAGE_SIZE 24; guardas anti-defasagem (sequencial por requisição, resposta velha descartada); `Esc` em camadas (painel → viewer); `wheel` global com guarda de 200ms; clique em tag fecha tudo e busca; `reveladas` — Set reativo de sessão com os IDs NSFW revelados manualmente (desce à grade via props, `reveal` sobe via emit) |
| `src/components/SearchBar.vue` | busca com debounce 300ms; `Esc` limpa; sincroniza com `modelValue` |
| `src/components/ImageGrid.vue` | masonry 2–7 colunas (ResizeObserver, debounce 120ms; ≥1440px → 7) + paginação Anterior/Próximo; empty states distintos; loading `opacity-40` |
| `src/components/ImageCard.vue` | card em altura natural: lazy loading, skeleton, fade-in, fallback; `media_url` vazia → só nome; `is_nsfw` não revelada → `blur-xl` + overlay "NSFW" com botão "Revelar" (`@click.stop`, clique nunca vaza ao card) |
| `src/components/ImageViewer.vue` | viewer estilo yandere (`z-50`), prompts ocultos, Detalhes/Fechar, clique alterna painel, rodapé de atalhos |
| `src/components/DetailPanel.vue` | painel deslizante `z-[60]`, scroll só no conteúdo, chips de tag clicáveis (`tokyo-blue`), formatSize/formatTime pt-BR |
| `src/components/CopyButton.vue` | clipboard com fallback (design.md §4) |

### 6.2 Coerência de URL (regra de ouro do frontend)

- **Nenhuma URL fixa no código.** Toda chamada HTTP (e todo `media_url` de
  `<img>`) sai de `apiUrl()` em `src/api/client.js`.
- `frontend/.env.development` define `VITE_API_URL=http://127.0.0.1:8000` —
  carregado APENAS pelo dev server do Vite (modo `dev`).
- `npm run build` não lê `.env.development`: sem `VITE_API_URL`, o client usa
  rotas relativas (mesma origem) — o sistema continua coerente se a porta ou
  o domínio mudarem. Para apontar outra origem em produção, crie
  `.env.production` com `VITE_API_URL=...`.

Comportamentos de visual e UX estão especificados em `design.md`.

## 7. Verificação e reparo da sincronia

Check de sanidade (banco saudável retorna `0, 0, 0`):

```sql
SELECT
  (SELECT count(*) FROM images WHERE id NOT IN (SELECT rowid FROM images_text)) AS fts_faltando,
  (SELECT count(*) FROM images_text WHERE rowid NOT IN (SELECT id FROM images)) AS fts_orfas,
  (SELECT count(*) FROM images_text WHERE CAST(image_id AS INTEGER) <> rowid) AS link_quebrado;
```

Só use os reparos abaixo se o check acusar problema (ex.: alguém escreveu
direto em `images_text`, violando INV-04 — esta é a única exceção legítima).
Rode uma query por vez:

```sql
INSERT INTO images_text (rowid, image_id, prompt_positivo, prompt_negativo, workflow_json)
SELECT id, id, '', '', ''
FROM images WHERE id NOT IN (SELECT rowid FROM images_text);

DELETE FROM images_text
WHERE rowid NOT IN (SELECT id FROM images);

UPDATE images_text SET image_id = rowid
WHERE CAST(image_id AS INTEGER) <> rowid;
```

Tags órfãs (só se alguém mexeu direto nas tabelas; fluxo normal não gera):

```sql
SELECT count(*) FROM image_tags WHERE image_id NOT IN (SELECT id FROM images);  -- saudável: 0
DELETE FROM image_tags WHERE image_id NOT IN (SELECT id FROM images);
```

## 8. Testes de regressão

Suítes standalone com `assert` puro (sem pytest), bancos e fixtures
temporários em `/tmp/opencode/`. Cada uma termina com "TODOS OS TESTES …
PASSARAM". Rodar com o venv do backend, **em loop** (o glob numa chamada única
executa só a primeira suíte — os demais arquivos viram `sys.argv`):

```bash
source backend/.venv/bin/activate
for t in tests/test_*.py; do python "$t" || break; done
```

| Suíte | Cobre |
|---|---|
| `test_init_db.py` | schema via subprocess, bijeção triggers↔FTS, MATCH (com/sem alias, filtros por coluna), preservação de texto no UPDATE (INV-06), remapeio de id, cascata de delete, UNIQUE de `file_path`, idempotência, `user_version=3`, WAL, queries de reparo, PK de `image_tags`, `source` default e "primeiro que grava vence" |
| `test_processing.py` | scanner end-to-end com fixtures reais (PNG A1111, PNG Comfy, PNG sem metadados, JPEG, nome com acentos/aspas, pasta oculta ignorada), re-scan inalterado, mtime alterado → UPDATE preservando FTS, arquivo apagado permanece, `--limite` do extractor, buscas FTS |
| `test_api.py` | uvicorn real (porta 8123): CORS (origem + preflight), envelope/paginação, detalhe (campos + tags + 404), busca (ranking, filtro por coluna, 400), `/media` físico e streaming de ZIP + 404 limpo (membro inexistente, zip corrompido, zip apagado) |
| `test_zipflow.py` | caminhos virtuais `::`, `__MACOSX`/`.*`/não-imagem ignorados, duplicado → última ocorrência, `file_size` descomprimido, mtime do zip físico, zip corrompido → erro, metadado > 4 MiB → fallback, zip apagado → erro com linha pendente, `media_url` encodeada |
| `test_tagger.py` | dicionário mock via `file://`: só chaves, normalização (pesos/parênteses), termo isolado, idempotência, PK deduplica, cascata; probe opcional (15s, não fatal) da URL real do dicionário |
| `test_space_tagger.py` | parser de todos os formatos de retorno, `FakeClient` (asserts de kwargs e caminhos), temporário em `/tmp` criado/removido, `sleep(5)` por sucesso, gravação `source='space_api'`, só imagens sem tags são alvo, erro mantém alvo, cascata |

## 9. Notas operacionais

- WAL deixa `catalog.db-wal`/`catalog.db-shm` ao lado do banco durante o uso
  (desaparecem no fechamento limpo da última conexão). Backup consistente com
  o app aberto: `VACUUM INTO 'backup.db'` — não copiar o `.db` "a quente".
- `file_path` é sensível a maiúsculas (Linux).
- Busca textual é sempre `MATCH` (nunca `LIKE` — ver rules.md §3).
- `backend/requirements.txt` está pinado mas **não inclui `gradio_client`**
  (presente no venv atual) — reconstrução do venv só pelo arquivo quebraria o
  space_tagger (tarefa pendente em `task.md`).
