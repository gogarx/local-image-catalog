# rules.md — Restrições que não podem ser violadas

Regras marcadas como **INV-xx** são invariantes do banco `backend/catalog.db`:
código novo nunca as viola. Se uma invariante precisar mudar, este arquivo muda
junto, no mesmo commit. Detalhes de schema, pipeline, endpoints e receitas SQL
estão em `architecture.md`; o visual está em `design.md`.

## 1. Invariantes do banco

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

**INV-04 — `images_text` só recebe UPDATE direto** (do extractor, para preencher
os textos extraídos dos metadados da imagem). INSERT e DELETE nela são papel
exclusivo dos triggers. Única exceção: as queries de reparo documentadas em
`architecture.md` §7.

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
`PRAGMA user_version`, atualizar o script e a seção de schema de
`architecture.md`.

**INV-10 — DELETE em `images` é cascata lógica e definitiva.** O trigger remove
a linha FTS e os vínculos de tags; não há lixeira nem soft-delete. Precisando
de soft-delete, é mudança de schema deliberada, documentada.

**INV-11 — A API HTTP é somente leitura.** Nenhum endpoint de `backend/main.py`
grava no banco; escritas continuam sendo exclusividade dos módulos CLI
(scanner/extractor). Um endpoint de escrita futuro precisa ser justificado
aqui, respeitando INV-01..INV-10. O frontend nunca grava.

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
- Membros de ZIP são servidos por streaming em RAM (nunca extraídos para o
  disco; única exceção documentada: o temporário de uma requisição do
  space_tagger).

**INV-13 — `image_tags` é derivada e aditiva.** Tabela derivada dos prompts
(tagger local) e da visão do Space WD-Tagger: só `backend/tagger.py` e
`backend/space_tagger.py` escrevem nela, sempre com `INSERT OR IGNORE`
(colunas explícitas!) — re-rodar só acrescenta vínculos, nunca duplica. A
coluna `source` marca a origem (`'tagger'` ou `'space_api'`) e o primeiro
que grava vence (OR IGNORE preserva o marcador original). Tags não são
removidas automaticamente quando o prompt muda; a única remoção automática
é a cascata da deleção da imagem (`image_tags_ad`). Código de app busca por
tag via índice (`WHERE tag = ?`) e nunca grava em `image_tags`.

## 2. Regras de ouro para código futuro

- Os módulos CLI são independentes e idempotentes; rodar scanner → extractor →
  tagger → space_tagger em série, **nunca em paralelo** (SQLite tem um único
  escritor; série evita SQLITE_BUSY).
- Nenhum módulo cria/altera schema — isso é exclusivo do `init_db.py` (INV-09).
- Escrita em `images_text`: só o UPDATE do extractor (INV-04). Escrita em
  `image_tags`: só tagger e space_tagger, sempre `INSERT OR IGNORE` com colunas
  explícitas (INV-13).
- `--db` existe para apontar bancos de teste; o padrão é sempre
  `backend/catalog.db`.
- Nunca escreva na coluna `image_id` de `images_text` fora dos triggers: o FTS5
  preserva o inteiro gravado pelo trigger e as comparações inteiras dependem
  disso.

## 3. Regras de SQL e banco

- Busca textual é sempre `MATCH` (índice FTS). **Nunca use `LIKE '%...%'` em
  `images_text`** — é scan completo e ignora o índice.
- Junções com FTS sempre por `rowid` (INV-03): `JOIN images_text AS t ON
  t.rowid = i.id`.
- Todo SQL usa placeholders `?`: nomes com aspas, acentos e espaços são
  parâmetro, nunca interpolados.
- `file_path` é sensível a maiúsculas (Linux): `Foto.PNG` ≠ `foto.png`.
- Backup consistente com o app aberto: `VACUUM INTO 'backup.db'` — nunca
  copiar o `.db` "a quente" sem checkpoint.
- FTS5 é requisito obrigatório do SQLite; `init_db.py` valida antes de gravar
  qualquer coisa.

## 4. Regras da API (backend/main.py)

- Nenhum endpoint grava no banco (INV-11).
- **Sempre bind em `127.0.0.1` — nunca exponha a API na rede.** CORS é `*` e
  `/media` serve qualquer arquivo legível da raiz; o bind local é a mitigação
  consciente e obrigatória (detalhes em `architecture.md` §5).
- Endpoints síncronos, uma conexão SQLite por request (WAL permite ler
  enquanto o scanner grava).

## 5. Regras do frontend (frontend/)

- **Nenhuma URL fixa no código.** Toda chamada HTTP e todo `media_url` saem de
  `apiUrl()` em `src/api/client.js`.
- **Nunca empilhe `pointer-events-none` + `pointer-events-auto` no mesmo
  elemento** (ex.: classe estática + condicional juntas): no CSS gerado pelo
  Tailwind 4 `.pointer-events-none` vem depois e vence o empate — o overlay
  inteiro fica inerte. Padrão correto em `design.md` §6.
- **Exatamente uma barra de rolagem por área** (app-shell): nunca
  `overflow-y-scroll` nem rolagem aninhada nas caixas de prompt; o scroll do
  painel de detalhes é exclusivo do filho de conteúdo.
- **Cores sempre pelas classes utilitárias `*-tokyo-*`** (tokens de
  `src/style.css`); não espalhar hex solto nos componentes.
- O frontend nunca grava nada — só consome a API read-only (INV-11).
