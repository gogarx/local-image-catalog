# local-image-catalog

Catálogo local, ultraleve e inteligente para indexar e pesquisar milhares de
imagens de IA (Stable Diffusion / ComfyUI) e backups pessoais de fotos. Tudo
roda de forma síncrona e direta no seu disco: sem intermediários, sem
servidores externos, sem nuvem. Validado na prática com mais de 7 mil
imagens catalogadas, a maioria delas dentro de arquivos .zip.

O pipeline é read-only por natureza: a API HTTP nunca grava no banco; as
escritas ficam exclusivas dos módulos de linha de comando. Backups em .zip
são suportados nativamente — as imagens internas são catalogadas, pesquisadas
e exibidas sem nunca serem descompactadas, sem gastar um byte extra de disco.

## Arquitetura desacoplada

O projeto é dividido em pedaços lógicos independentes, unidos por um banco
SQLite e por um contrato técnico explícito (o arquivo agent.md na raiz).

### Banco de dados — SQLite WAL + FTS5 (backend/catalog.db)

- images: metadados dos arquivos (caminho absoluto, nome, tamanho em bytes,
  mtime). Suporta caminhos virtuais de membros de ZIP no formato
  /backup.zip::pasta/imagem.png.
- images_text: tabela virtual FTS5 com prompt positivo, prompt negativo e
  workflow, mantida em sincronia automática com images por triggers.
- image_tags: palavras-chave padronizadas por imagem, com chave primária
  composta (image_id, tag) e índice de busca por tag.
- Modo WAL (a API lê enquanto o scanner escreve) e versão de schema
  rastreada em PRAGMA user_version (atualmente 2).

### Backend — FastAPI + Uvicorn (backend/)

API HTTP somente leitura:

- GET /images — grade da galeria com paginação (limit e offset).
- GET /images/{id} — detalhes técnicos completos: prompts, workflow e tags.
- GET /search?q= — busca por texto completo instantânea, direto no índice
  FTS5 do SQLite, ordenada por relevância.
- /media — arquivos servidos direto do disco via StaticFiles; membros de
  ZIP são lidos do .zip direto para a RAM (io.BytesIO) e respondidos como
  StreamingResponse com o media_type correto.

Pipeline CLI (os únicos escritores do banco): init_db.py, scanner.py,
extractor.py e tagger.py — todos idempotentes, podem rodar quantas vezes
quiser.

### Frontend — Vue 3 + Vite + Tailwind CSS 4 (frontend/)

Tema escuro Tokyonight-Dark. Grade masonry responsiva de até 7 colunas,
visualizador expandido com navegação por scroll do mouse, painel de
metadados sob demanda (prompts, workflow e tags clicáveis) e busca dinâmica
com debounce. Nenhuma URL fixa no código: o dev server lê a VITE_API_URL do
arquivo .env.development e o build de produção usa rotas relativas.

## Requisitos

- Python 3.10+ com SQLite compilado com FTS5 (o init_db.py valida antes de
  qualquer gravação).
- Node.js + npm (apenas para o frontend).
- Navegador moderno (desenvolvido e testado no Brave).

## Primeira instalação

```
cd backend
python3 -m venv .venv
.venv/bin/pip install fastapi uvicorn pillow

cd ../frontend
npm install
```

## Manual de execução passo a passo

Os comandos do backend partem da pasta backend/ com o ambiente virtual
ativado:

```
cd backend
source .venv/bin/activate
```

1. Inicializar o banco (idempotente; cria catalog.db com o schema v2):

```
python init_db.py
```

2. Varrer as pastas de imagens (incremental e idempotente; arquivos .zip
são varridos por dentro, sem descompactar):

```
python scanner.py /caminho/para/as/imagens
```

3. Extrair os metadados (prompts e workflow dos chunks PNG do A1111 e do
ComfyUI; membros de ZIP são lidos direto para a memória):

```
python extractor.py
```

4. Categorizar com tags padronizadas (opcional; baixa o dicionário de
chaves do yandere-masonry e cruza com os prompts):

```
python tagger.py
```

5. Subir a API HTTP (docs automáticas em http://127.0.0.1:8000/docs):

```
uvicorn main:app --host 127.0.0.1 --port 8000
```

6. Iniciar o painel do frontend e abrir http://localhost:5173 no Brave (o
.env.development já aponta a API em http://127.0.0.1:8000):

```
cd ../frontend
npm run dev
```

## Garantia de qualidade

A suíte de testes de regressão roda contra bancos temporários em /tmp — o
banco real nunca é tocado. Com o ambiente virtual ativado, na raiz do
projeto:

```
source backend/.venv/bin/activate
for t in tests/test_*.py; do python "$t" || break; done
```

Cada suíte termina com um "TODOS OS TESTES ... PASSARAM":

- tests/test_init_db.py — schema, triggers, cascata e queries de reparo
- tests/test_processing.py — scanner incremental e extração de metadados
- tests/test_api.py — endpoints, CORS, /media e streaming de ZIP
- tests/test_zipflow.py — varredura e extração de membros de ZIP
- tests/test_tagger.py — dicionário externo e mapeamento de tags

O sistema só deve ser considerado estável com as cinco suítes verdes; se
qualquer uma falhar, nada foi quebrado por acidente — corrija antes de
continuar. O contrato completo das regras do banco, dos módulos e da API
(invariantes INV-01 a INV-13) está no agent.md, que é a fonte da verdade
deste projeto.
