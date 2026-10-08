# agent.md — Invariantes do banco de dados local (local-image-catalog)

Referência obrigatória para qualquer agente (humano ou IA) que escrever código que
toque em `backend/catalog.db`. Regras marcadas como **INV-xx** são invariantes:
código novo nunca pode violá-las. Se uma invariante precisar mudar, este arquivo
muda junto, no mesmo commit.

## 1. Visão geral

| Item | Valor |
|---|---|
| Arquivo do banco | `backend/catalog.db` (SQLite 3, modo WAL) |
| Criação/manutenção do schema | `backend/init_db.py` (idempotente; pode rodar com o banco populado sem perder dados) |
| Processamento | `backend/scanner.py` (disco → `images`), `backend/extractor.py` (`images` → `images_text`) e `backend/tagger.py` (`images_text` → `image_tags`) — fluxo na seção 7 |
| API HTTP | `backend/main.py` (FastAPI + uvicorn; somente leitura — seção 8) |
| Frontend | `frontend/` (Vue 3 + Vite + Tailwind 4; consome a API — seção 9) |
| Testes | `tests/` (suites de regressão; rodar com `backend/.venv/bin/python tests/test_*.py`) |
| Versão do schema | `PRAGMA user_version = 2` (v2: acrescenta `image_tags`, índice `idx_image_tags_tag` e trigger `image_tags_ad`) |
| Requisito | SQLite compilado com **FTS5** (o script valida e aborta com mensagem clara se faltar) |
| Natureza | 100% local: o app lê/escreve direto no arquivo, sem servidor nem intermediários |

Uso do script: `python3 backend/init_db.py` (aceita um caminho opcional de banco
como argumento, útil para testes). Re-executar é seguro.

Pipeline local padrão (detalhes na seção 7): `init_db.py` → `scanner.py <pasta>`
→ `extractor.py` → busca FTS.

## 2. Objetos do schema

### 2.1 `images` — fonte da verdade sobre os arquivos do disco

| coluna | tipo | regra |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | imutável na prática (INV-07); espelhado no `rowid` de `images_text` |
| `file_path` | TEXT NOT NULL UNIQUE | caminho absoluto do arquivo OU caminho virtual de membro de ZIP (`/backup.zip::pasta/img.png`, INV-12); 1 arquivo = 1 linha (INV-01) |
| `file_name` | TEXT NOT NULL | nome base, para exibição |
| `file_size` | INTEGER NOT NULL | tamanho em bytes |
| `mtime` | REAL NOT NULL | epoch Unix em segundos (float); base para detectar arquivo alterado |
| `indexed_at` | TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP | UTC, formato `YYYY-MM-DD HH:MM:SS` |

### 2.2 `images_text` — tabela virtual FTS5 (busca por texto)

| coluna | papel |
|---|---|
| `image_id` (UNINDEXED) | vínculo com `images.id`; sempre igual ao `rowid` da própria linha (INV-03) |
| `prompt_positivo` | texto buscável (indexado) |
| `prompt_negativo` | texto buscável (indexado) |
| `workflow_json` | texto buscável (indexado; JSON tokenizado como texto comum) |

Notas do FTS5 (comportamento verificado em testes):

- `image_id` é UNINDEXED porque é identificador, não termo de busca.
- O FTS5 **não aceita tipos declarados** nas colunas. Os triggers gravam
  `image_id` com o inteiro `new.id`, e o FTS5 preserva esse valor; comparações
  com inteiros funcionam (`WHERE image_id = 5` casa). Se alguém gravar texto
  ali, a comparação inteira deixa de casar — mais um motivo para nunca escrever
  nessa coluna fora dos triggers.
- Junções e lookups devem usar `rowid` (caminho canônico, sempre inteiro e
  indexado pelo FTS5).

### 2.3 Triggers — manutenção das relações de `images`

| trigger | evento em `images` | ação |
|---|---|---|
| `images_ai` | AFTER INSERT | cria a linha gêmea em `images_text`: `rowid = image_id = new.id`, textos `''` |
| `images_au` | AFTER UPDATE (guarda `WHEN new.id <> old.id`) | re-aponta `rowid`/`image_id`; **texto já indexado é preservado** |
| `images_ad` | AFTER DELETE | remove a linha gêmea (`WHERE rowid = old.id`) |
| `image_tags_ad` | AFTER DELETE | remove os vínculos de tags (`WHERE image_id = old.id`) |

### 2.4 `image_tags` — palavras-chave por imagem (schema v2)

| coluna | tipo | regra |
|---|---|---|
| `image_id` | INTEGER NOT NULL | espelha `images.id` (INV-03) |
| `tag` | TEXT NOT NULL | termo padronizado (ex.: `1girl`, `long_hair`) |

- `PRIMARY KEY (image_id, tag)` já deduplica vínculos; o índice
  `idx_image_tags_tag` acelera busca por tag.
- Preenchida exclusivamente por `backend/tagger.py` com `INSERT OR IGNORE`
  (INV-13) — pode rodar quantas vezes quiser.
- Sem FOREIGN KEY (o projeto padronizou cascata por triggers, já que
  `PRAGMA foreign_keys` é off por padrão no SQLite): `image_tags_ad` limpa os
  vínculos quando a imagem sai de `images`.

## 3. Invariantes

**INV-01 — Um arquivo = uma linha.** `images.file_path` é `UNIQUE NOT NULL`
(caminhos absolutos, sensíveis a maiúsculas no Linux). Renomear/mover arquivo é
`UPDATE images SET file_path = ...` — nunca delete + insert, que trocariam o
`id` e o vínculo com o texto já indexado.

**INV-02 — Bijeção `images` ↔ `images_text`.** Cada linha de `images` tem
exatamente uma linha em `images_text` e vice-versa. Quem garante isso são
somente os triggers — não existe FOREIGN KEY porque tabelas virtuais FTS5 não
podem ser alvo de FK. Código de aplicação não cria nem apaga linhas em
`images_text`.

**INV-03 — `images_text.rowid = images_text.image_id = images.id`.** Use
`rowid` nas junções: `JOIN images_text AS t ON t.rowid = i.id`.

**INV-04 — `images_text` só recebe UPDATE direto** (do indexer, para preencher
os textos extraídos dos metadados da imagem). INSERT e DELETE nela são papel
exclusivo dos triggers. Única exceção: as queries de reparo da seção 5.

**INV-05 — Texto vazio é estado válido.** Imagem recém-catalogada (ou sem
metadados de IA embutidos) fica com `''` nos três campos de texto. Ela não
aparece em buscas FTS (não gera tokens), mas a linha existe para manter a
bijeção. `''` significa "ainda não extraído / sem metadados" — não é erro.

**INV-06 — UPDATE em `images` nunca apaga texto indexado.** O trigger
`images_au` só corrige o vínculo quando o `id` muda. Re-indexar
(`UPDATE images SET file_size, mtime, indexed_at ...`) preserva os prompts; se
o arquivo mudou no disco, o indexer decide se re-extrai e regrava o texto.

**INV-07 — `images.id` é imutável na prática.** Nunca faça UPDATE em massa que
altere `id` (pode criar `rowid` duplicado no FTS e quebrar INV-02/INV-03).
"Substituir" um arquivo = delete + insert.

**INV-08 — Formatos de tempo são fixos.** `indexed_at`: texto UTC ISO-8601
(`CURRENT_TIMESTAMP`). `mtime`: REAL epoch Unix em segundos — comparável direto
com `os.stat().st_mtime`. Nunca gravar datas localizadas nem strings arbitrárias.

**INV-09 — O schema só nasce de `init_db.py`.** Nunca criar/alterar tabela ou
trigger "na mão" em código de aplicação. Migrações futuras: incrementar
`PRAGMA user_version`, atualizar o script e este arquivo.

**INV-10 — DELETE em `images` é cascata lógica e definitiva.** O trigger remove
a linha FTS; não há lixeira nem soft-delete. Precisando de soft-delete, é
mudança de schema deliberada, documentada aqui.

**INV-11 — A API HTTP é somente leitura.** Nenhum endpoint de
`backend/main.py` grava no banco; escritas continuam sendo exclusividade dos
módulos CLI (scanner/extractor). Um endpoint de escrita futuro precisa ser
justificado aqui, respeitando INV-01..INV-10.

**INV-12 — Caminhos virtuais de ZIP (`::`).** Arquivos `.zip` são indexados
SEM descompactar: cada membro interno válido (`.png`, `.webp`) vira uma linha
com caminho virtual `caminho/do.zip::pasta/imagem.png` — o `::` separa o
arquivo físico do membro interno e é o marcador que o extrator usa para ler
da memória. Regras:
- `file_size` = tamanho DESCOMPACTADO do membro (`ZipInfo.file_size`);
  `mtime` = data de modificação do `.zip` FÍSICO — substituir o `.zip`
  atualiza todas as suas linhas virtuais na varredura seguinte
  (idempotência INV-01 por arquivo).
- Pastas internas ocultas (`.*`) e `__MACOSX` são ignoradas; membros com
  nome duplicado resolvem para a ÚLTIMA ocorrência (mesma semântica do
  `zipfile`).
- O separador `::` é exclusivo do namespace virtual: arquivos físicos com
  `::` no nome são pulados pelo scanner.
- ZIP corrompido/ilegível vira "erro" no resumo da varredura, que segue; ZIP
  apagado depois do scan vira "erro" do extrator e a linha permanece
  pendente.
- Membros de ZIP não são servíveis pelo `/media` (StaticFiles): a API
  retorna `media_url` vazio e a UI mostra o placeholder.

**INV-13 — `image_tags` é derivada e aditiva.** Tabela derivada de
`prompt_positivo`: só `backend/tagger.py` escreve nela, sempre com
`INSERT OR IGNORE` — re-rodar só acrescenta vínculos, nunca duplica. Tags
não são removidas automaticamente quando o prompt muda; a única remoção
automática é a cascata da deleção da imagem (`image_tags_ad`). Código de app
busca por tag via índice (`WHERE tag = ?`) e nunca grava em `image_tags`.

## 4. Receitas SQL aprovadas (testadas)

Indexar arquivo novo (indexer):

```sql
INSERT INTO images (file_path, file_name, file_size, mtime)
VALUES (?, ?, ?, ?);
-- images_ai cria a linha FTS automaticamente (textos vazios)
```

Preencher os textos (indexer, após extrair metadados embutidos da imagem):

```sql
UPDATE images_text
SET prompt_positivo = ?, prompt_negativo = ?, workflow_json = ?
WHERE rowid = ?;  -- o images.id correspondente
```

Buscar por texto (UI/API). Com alias, prefira a forma função-de-tabela:

```sql
SELECT i.id, i.file_path, i.file_name, t.prompt_positivo
FROM images_text(?) AS t
JOIN images AS i ON i.id = t.rowid
ORDER BY t.rank;
```

Formas equivalentes de MATCH: sem alias, `WHERE images_text MATCH ?`; com
alias, `WHERE t.images_text MATCH ?`. Restrição a coluna no padrão:
`'prompt_positivo: gato NOT praia'`, `'workflow_json: euler'`.

Re-indexar arquivo alterado no disco:

```sql
UPDATE images
SET file_size = ?, mtime = ?, indexed_at = CURRENT_TIMESTAMP
WHERE file_path = ?;
-- texto FTS permanece intacto (INV-06); re-extração é decisão do indexer
```

Remover arquivo que sumiu do disco:

```sql
DELETE FROM images WHERE file_path = ?;
-- images_ad limpa o FTS e image_tags_ad limpa as tags automaticamente
```

Categorizar com tags (após scanner + extractor):

```bash
python3 backend/tagger.py
```

Buscar por tag (usa o índice `idx_image_tags_tag`):

```sql
SELECT i.id, i.file_path, i.file_name
FROM image_tags AS g
JOIN images AS i ON i.id = g.image_id
WHERE g.tag = ?;
```

Adicionar vínculo manual pontual (exceção de administração; o caminho normal é o tagger):

```sql
INSERT OR IGNORE INTO image_tags (image_id, tag) VALUES (?, ?);
```

## 5. Verificação e reparo da sincronia

Check de sanidade (banco saudável retorna `0, 0, 0`):

```sql
SELECT
  (SELECT count(*) FROM images WHERE id NOT IN (SELECT rowid FROM images_text)) AS fts_faltando,
  (SELECT count(*) FROM images_text WHERE rowid NOT IN (SELECT id FROM images)) AS fts_orfas,
  (SELECT count(*) FROM images_text WHERE CAST(image_id AS INTEGER) <> rowid) AS link_quebrado;
```

Só use os reparos abaixo se o check acusar problema (ex.: alguém escreveu
direto em `images_text`, violando INV-04). Rode uma query por vez:

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

## 6. Notas operacionais

- WAL deixa `catalog.db-wal`/`catalog.db-shm` ao lado do banco durante o uso
  (desaparecem no fechamento limpo da última conexão). Backup consistente com o
  app aberto: `VACUUM INTO 'backup.db'` — não copiar o `.db` "a quente" sem
  checkpoint.
- FTS5 precisa estar habilitado no SQLite; `init_db.py` valida antes de gravar
  qualquer coisa.
- `file_path` é sensível a maiúsculas (Linux): `Foto.PNG` ≠ `foto.png`.
- Busca textual é sempre `MATCH` (índice FTS). Nunca use `LIKE '%...%'` em
  `images_text` — é scan completo e ignora o índice.
- Este arquivo é a fonte da verdade das regras do banco. Código novo que
  contradiga uma INV-xx está errado — ou a INV deve ser revisada aqui, de forma
  explícita.

## 7. Módulos de processamento (scanner.py e extractor.py)

Fluxo de execução local padrão — etapas independentes, sempre nesta ordem:

```
python3 backend/init_db.py            (uma vez; os módulos também auto-garantem o schema)
python3 backend/scanner.py <pasta>    disco -> tabela images
python3 backend/extractor.py          images -> textos em images_text
python3 backend/tagger.py             images_text -> tags em image_tags
consulta FTS (UI/API, seção 8)        images_text MATCH ... JOIN images ...
```

### 7.1 scanner.py — varredura do disco

Uso: `python3 backend/scanner.py <pasta> [--db CAMINHO]`

- Varre `<pasta>` recursivamente com `os.walk` (não segue symlink de pasta,
  pula pastas ocultas `.*`); para cada arquivo de imagem aceito (extensões:
  png, jpg, jpeg, webp, gif, bmp, tif, tiff) lê `os.stat` e grava em `images`:
  `file_path` (caminho absoluto), `file_name`, `file_size` (bytes) e `mtime`.
- Todo SQL usa placeholders `?`: nomes com aspas, acentos e espaços são dados
  como parâmetro, nunca interpolados.
- Encontra um `.zip`: NÃO descompacta. Lê a árvore interna com `zipfile`,
  coleta os membros válidos (`.png`, `.webp`) e grava caminhos virtuais
  `meu.zip::pasta/imagem.png` (INV-12) — `file_size` é o tamanho
  descomprimido do membro e `mtime` é a data do `.zip` físico. ZIP
  corrompido vira "erro" e a varredura segue.
- **Idempotência (INV-01)**: linha existente com o MESMO `file_size` e `mtime`
  é pulada (`continue` — conta como "inalteradas"). Tamanho ou data diferentes
  → `UPDATE` da linha (`id` e texto FTS preservados, INV-06; `indexed_at`
  marca a última passagem do scanner).
- Gravações vão em lotes de 500 (commit incremental; re-rodar retoma de graça).
- Erros de leitura/permissão são avisos no stderr, contam como "erros" e a
  varredura segue — nenhum arquivo ruim aborta o scan.
- **Não remove** linhas de arquivos apagados do disco. Remoção é sempre receita
  explícita (`DELETE FROM images WHERE file_path = ?`), nunca implícita.
- Nunca escreve em `images_text` (quem escreve nela são só os triggers —
  INV-02/INV-04).

Saída: resumo `{adicionadas, atualizadas, inalteradas, erros}`.

### 7.2 extractor.py — extração de prompts/workflow

Uso: `python3 backend/extractor.py [--db CAMINHO] [--limite N]`

- "Pendente" = linha de `images` cuja linha gêmea em `images_text` tem os
  TRÊS campos de texto vazios (`''`, ver INV-05):

```sql
SELECT i.id, i.file_path
FROM images AS i
JOIN images_text AS t ON t.rowid = i.id
WHERE t.prompt_positivo = '' AND t.prompt_negativo = '' AND t.workflow_json = ''
```

- Abre cada pendente com `PIL.Image.open` (read-only: só o cabeçalho e o
  dicionário `img.info`; pixels nunca são decodificados) e grava com
  `UPDATE images_text ... WHERE rowid = ?` — a única escrita direta legítima
  em `images_text` (INV-04).
- Caminho com `::` (membro de ZIP, INV-12): `zipfile.ZipFile.open()` lê apenas
  o cabeçalho de bytes para um `io.BytesIO` (limite de 4 MiB — os chunks de
  metadados ficam antes do IDAT do PNG); `PIL.Image.open` consome o buffer
  direto da memória, nada é extraído para o disco. Se o metadado estourar o
  limite, o membro inteiro é relido como fallback. ZIP
  apagado/corrompido/criptografado vira "erro" e a linha permanece pendente.
- Formatos reconhecidos no `img.info` (convenção deste projeto):
  - **A1111/Forge WebUI** (chunk `parameters`): linhas anteriores a
    `Negative prompt:` → `prompt_positivo`; bloco de `Negative prompt:` até a
    linha `Steps:` → `prompt_negativo`; linha final `Steps: ...` (parâmetros
    de geração) → `workflow_json` (texto plano — o análogo A1111 de "recipe").
  - **ComfyUI** (chunks `prompt` + `workflow`): `workflow_json` recebe o JSON
    de `workflow` (ou de `prompt`, se `workflow` não existir);
    `prompt_positivo`/`prompt_negativo` são resolvidos seguindo as entradas
    `positive`/`negative` do nó `*KSampler*` no JSON `prompt` até o nó
    `*TextEncode*` (um salto). Grafo exótico sem resolução → prompts vazios,
    mas o conteúdo integral continua pesquisável em `workflow_json`.
- **Autocorreção intencional**: imagens sem metadados continuam vazias e,
  portanto, pendentes — são re-tentadas a cada execução (custo baixo: só o
  cabeçalho é lido). Metadados embutidos depois são detectados na próxima
  rodada. Linhas com qualquer campo preenchido não são reprocessadas.
- Limitações do Pedaço 2: lê apenas `img.info` (chunks de texto PNG) — EXIF
  de JPEG (UserComment do A1111) ainda não é lido; arquivo corrompido ou
  sumido vira "erro" no resumo e a linha permanece pendente.

Saída: resumo `{processadas, preenchidas, sem_metadados, erros}`.

### 7.3 Regras de ouro para código futuro

- Os módulos são independentes e idempotentes; rodar scanner → extractor →
  tagger em série, nunca em paralelo (SQLite tem um único escritor; série
  evita SQLITE_BUSY).
- Nenhum módulo cria/altera schema — isso é exclusivo do `init_db.py`
  (INV-09).
- Nenhum módulo escreve em `images_text` além do UPDATE do extractor (INV-04),
  nem em `image_tags` além do tagger (INV-13).
- `--db` existe para apontar bancos de teste; o padrão é sempre
  `backend/catalog.db`.

### 7.4 tagger.py — categorização por tags

Uso: `python3 backend/tagger.py [--db CAMINHO]`

- Baixa o dicionário de `TAGS_URL` (yandere-masonry, `src/data/tags_cn.json`)
  via `urllib` e usa APENAS as **chaves** do objeto JSON — os valores
  (traduções) são ignorados. Sem rede, HTTP de erro ou JSON inválido → erro
  e a execução aborta (nenhuma tag inventada).
- Percorre `SELECT rowid, prompt_positivo FROM images_text WHERE
  prompt_positivo <> ''` e tokeniza o prompt: split por vírgula e quebra de
  linha, strip de `()[]{}` das bordas, sufixo de peso `:1.2` removido,
  lowercase e espaços viram `_` — `(long hair:1.3)` vira `long_hair`.
- Tag só conta como **termo isolado**: o token inteiro precisa ser igual à
  chave (`cat_ears` NÃO casa com "closeup of cat_ears" — tokens diferentes).
- Interseção token∩chave → `INSERT OR IGNORE INTO image_tags VALUES (?, ?)`
  com placeholders blindados (INV-13). Lotes de 500 commits, como os outros
  módulos. Só `prompt_positivo` gera tags (o negativo é ignorado).
- Saída: resumo `{chaves, processadas, inseridos}`.

## 8. API HTTP (main.py) — FastAPI + uvicorn

Servidor **somente leitura** (INV-11): consome `backend/catalog.db` e serve
JSON + os arquivos locais. O frontend Vue 3/Vite (`localhost:5173`) lê a API em
`http://127.0.0.1:8000` sem bloqueios de CORS no navegador.

### 8.1 Subir o servidor

```bash
cd backend
source .venv/bin/activate     # venv do projeto (fastapi, uvicorn, pillow)
uvicorn main:app --host 127.0.0.1 --port 8000
```

- Desenvolvimento com hot-reload: `uvicorn main:app --reload --port 8000`
- Sem ativar o venv: `cd backend && .venv/bin/uvicorn main:app --port 8000`
- Alternativa programática: `.venv/bin/python main.py`
- Docs automáticas (Swagger): `http://127.0.0.1:8000/docs`
- **Sempre `--host 127.0.0.1`** — nunca exponha a API na rede (ver 8.4).

### 8.2 Endpoints

| Rota | O que faz |
|---|---|
| `GET /images?limit=&offset=` | página da galeria; envelope `{total, limit, offset, items}` — cada item traz `id`, `file_name`, `file_size`, `file_path` e `media_url` (derivado, já URL-encoded). Ordenação fixa `ORDER BY id`; `limit` 1..500 (padrão 50), `offset` >= 0. |
| `GET /images/{image_id}` | detalhes completos: JOIN `images` ↔ `images_text` por `rowid` (INV-03) — metadados do arquivo + `prompt_positivo`, `prompt_negativo`, `workflow_json`, `image_id`, `media_url` e `tags` (lista alfabética de `image_tags`, INV-13). 404 se não existir. |
| `GET /search?q=…` | FTS5 pela forma função-de-tabela (`images_text(?)`), ordenado por `rank` (bm25), mesmo envelope paginado de `/images`. Sintaxe FTS inválida → **400** com a mensagem do SQLite. Filtro por coluna: `q=prompt_negativo: borrão`. |
| `/media/<caminho>` | `StaticFiles` montado na raiz (`CATALOG_MEDIA_ROOT`, padrão `/`): `/media/home/usuario/img.png` serve o arquivo físico direto do disco — é a URL que o `<img>` da galeria consome. Membros de ZIP (INV-12) não são servidos: `media_url` retorna vazio e a UI mostra o placeholder (futura melhoria: rota de streaming de membros). |

Envolucro padrão de listagem (galeria e busca):

```json
{"total": 123, "limit": 50, "offset": 0, "items": [{"id": 1, "file_name": "gato.png", "file_size": 1234, "file_path": "/home/u/gato.png", "media_url": "/media/home/u/gato.png"}]}
```

### 8.3 Configuração por variáveis de ambiente

| Variável | Padrão | Efeito |
|---|---|---|
| `CATALOG_DB` | `backend/catalog.db` | banco usado pela API (útil para testes) |
| `CATALOG_MEDIA_ROOT` | `/` | raiz servida pelo `/media` |
| `CATALOG_PORT` | `8000` | porta no modo `python main.py` |

Detalhes de implementação: endpoints síncronos (threadpool do uvicorn) com uma
conexão SQLite por request; o WAL permite a API ler enquanto o scanner grava. A
API garante o schema ao importar (`init_db.init_db`, idempotente e silencioso).

### 8.4 CORS e escopo de segurança (decisões conscientes do projeto)

- `allow_origins=["*"]`: qualquer origem lê a API — é o que faz o dev server do
  Vite funcionar sem configuração extra.
- `/media` com raiz `/` serve **qualquer arquivo legível do disco**, não só os
  catalogados. Com CORS `*`, qualquer site aberto no navegador pode ler esses
  endpoints enquanto o servidor estiver de pé. Aceito por ser app 100% local —
  MITIGAÇÃO OBRIGATÓRIA: bind em `127.0.0.1`, nunca portar para fora. Se um
  dia precisar de mais isolamento: restrinja `CATALOG_MEDIA_ROOT` à pasta das
  imagens ou troque `/media` por rota que só sirva caminhos presentes na
  tabela `images`.
- A API não autentica nada — mesma confiança de um arquivo aberto no disco.

## 9. Frontend (Vue 3 + Vite + Tailwind) — galeria local

Stack: Vue 3 (`<script setup>`), Vite, Tailwind CSS 4 (plugin `@tailwindcss/vite`),
`fetch` nativo (sem axios). Requer Node.js + npm disponíveis no sistema.

### 9.1 Rodar o ambiente

```bash
cd frontend
npm install          # primeira vez
npm run dev          # http://localhost:5173
```

- `npm run build` → gera `dist/` (produção, rotas relativas)
- `npm run preview` → serve o build final para conferência
- Fluxo completo: subir o backend (8.1) e abrir `http://localhost:5173`
  no navegador. O CORS da API já libera o dev server do Vite.

### 9.2 Coerência de URL (regra de ouro do frontend)

- **Nenhuma URL fixa no código.** Toda chamada HTTP (e todo `media_url` de
  `<img>`) sai de `apiUrl()` em `frontend/src/api/client.js`.
- `frontend/.env.development` define `VITE_API_URL=http://127.0.0.1:8000` —
  carregado APENAS pelo dev server do Vite (modo `dev`).
- `npm run build` não lê `.env.development`: sem `VITE_API_URL` definido, o
  client usa rotas relativas (mesma origem) — o sistema continua coerente se
  a porta ou o domínio mudarem. Para apontar outra origem em produção, crie
  `.env.production` com `VITE_API_URL=...`.

### 9.3 Arquitetura dos módulos

| Arquivo | Papel |
|---|---|
| `src/api/client.js` | base URL dinâmica (`import.meta.env.VITE_API_URL` ?? relativa) + `fetch` com tratamento de erro (mostra o `detail` do FastAPI) |
| `src/api/catalog.js` | `fetchImages`, `fetchImage`, `searchImages` — espelham os endpoints da seção 8.2 |
| `src/App.vue` | raiz de composição: estado de busca/página/seleção; guarda anti-defasagem (número sequencial por requisição, resposta velha é descartada) |
| `src/components/SearchBar.vue` | busca dinâmica com debounce de 300ms; `Esc` limpa; emite o termo; sincroniza com `modelValue` (clique em tag atualiza o campo) |
| `src/components/ImageGrid.vue` | grade masonry responsiva (2–7 colunas via `ResizeObserver`; 7 colunas a partir de ~1440px; distribuição round-robin em colunas flex independentes) + paginação Anterior/Próximo |
| `src/components/ImageCard.vue` | card do masonry em altura natural: `media_url` com lazy loading, skeleton `min-h` antes do load, fade-in em `@load`, fallback em `@error` |
| `src/components/ImageViewer.vue` | visualização expandida estilo yandere: imagem limpa e centralizada sobre fundo escuro (`z-50`), prompts ocultos por padrão; botões Detalhes/Fechar; clique na imagem alterna o painel |
| `src/components/DetailPanel.vue` | painel deslizante à direita SOBRE o viewer (`z-[60]`): metadados, caixas de prompt positivo/negativo/workflow e tags como chips clicáveis (`--color-tokyo-blue`) que disparam a busca; só abre pelo botão Detalhes |
| `src/components/CopyButton.vue` | `navigator.clipboard.writeText` com fallback sênior (textarea oculto → `focus`/`select` → `execCommand('copy')` → remoção do DOM) para navegadores que bloqueiam a API moderna |

Comportamentos-chave:

- Busca instantânea: cada tecla (após debounce) chama `/search?q=`, que usa o
  índice FTS5 do SQLite. Erros de sintaxe FTS (HTTP 400) aparecem num banner.
- A grade só lista dados leves (`/images`); os metadados pesados
  (`/images/{id}`) só são puxados quando a imagem é clicada (INV-11: API é
  read-only, o frontend nunca grava).
- Fluxo de visualização (estilo yandere): clique no card abre o
  `ImageViewer` — imagem centralizada, sem prompts por padrão. O painel de
  metadados só aparece ao clicar em "Detalhes" (ou na própria imagem). Com o
  viewer aberto e o painel fechado, o scroll do mouse navega
  anterior/próxima (escuta global `wheel`, guarda de 200ms contra saltos
  múltiplos; navegação desativada com o painel aberto, para o conteúdo do
  painel rolar). `Esc` fecha em camadas: primeiro o painel, depois o viewer.
  Clique num chip de tag fecha tudo e busca o termo via FTS5.
- Paginação é por `offset` (24 por página), mesma semântica da API.
- Layout em "app-shell": raiz `h-screen overflow-hidden` — exatamente uma
  barra de rolagem por área. `main` da galeria é o único scroll da página; o
  painel de detalhes é `h-screen flex-col` com header fixo e scroll
  (`overflow-y-auto` + `overscroll-contain`) EXCLUSIVAMENTE no filho de
  conteúdo, onde os prompts ultrapassam a altura da tela. Nunca use
  `overflow-y-scroll` nem rolagem aninhada nas caixas de prompt.
- Masonry (lógica extraída do projeto antigo matrix-photo-gallery): colunas
  são pilhas verticais independentes com imagens em altura natural — cada
  coluna cresce sozinha conforme as imagens chegam, então o carregamento
  assíncrono nunca quebra nem encavala a grade (no projeto antigo as libs
  `masonry-layout`/`imagesloaded` estavam no package.json sem nunca serem
  importadas — colunas em fluxo normal dispensam relayout). A distribuição é
  round-robin (`index % colunas`): posições determinísticas, que não se
  movem quando as imagens carregam. A grade não tem overflow nem altura
  fixa — o scroll continua sendo só o do `main` (app-shell, sem barra
  fantasma).
- **Nunca empilhe `pointer-events-none` + `pointer-events-auto` no mesmo
  elemento** (ex.: classe estática + condicional juntas): no CSS gerado pelo
  Tailwind 4 `.pointer-events-none` vem depois e vence o empate — o overlay
  inteiro fica inerte (clique atravessa, botão Fechar morto). Padrão correto
  (DetailPanel): wrapper `fixed z-50` com `:class="open ? '' :
  'pointer-events-none'"`; fundo escuro com `pointer-events-auto` quando
  aberto e `pointer-events-none` quando fechado; `<aside>` com
  `pointer-events-auto` permanente (fica fora da tela quando fechado).

### 9.4 Tema visual (Tokyonight-Dark)

Cores centralizadas em `src/style.css` via `@theme` do Tailwind 4
(`--color-tokyo-*`): fundo `#1a1b26`/`#16161e`, texto `#c0caf5`, acentos azul
`#7aa2f7`, ciano `#7dcfff`, verde `#9ece6a`, vermelho `#f7768e`, roxo
`#bb9af7`, bordas `#3b4261`. Usar sempre as classes utilitárias `*-tokyo-*`;
não espalhar hex solto nos componentes.
