# memory.md — Histórico de decisões

Como usar: **leia antes de propor mudança de rumo**. Toda decisão importante
vira uma entrada datada aqui — o "porquê", não só o "o quê", incluindo
alternativas descartadas quando relevante. Novas entram no final.

---

## 2026-10-08 — Fundação do banco (commit 7999b84)

**Decisão.** SQLite 3 em modo WAL com FTS5 como barramento único entre os
blocos; bijeção `images` ↔ `images_text` mantida exclusivamente por triggers
(não FK — tabelas virtuais FTS5 não podem ser alvo de FK e `PRAGMA
foreign_keys` é off por padrão no SQLite); `rowid` como chave de junção
canônica.
**Motivo.** WAL permite a API ler enquanto o scanner grava; triggers
centralizam a integridade fora do código de aplicação. As invariantes INV-xx
nasceram junto, antes de qualquer módulo.

## 2026-10-08 — Scanner incremental e ZIPs sem descompactar (commit 6910af3)

**Decisão.** Idempotência por par (`file_size`, `mtime`); ZIPs indexados como
cidadãos de primeira classe via caminhos virtuais `caminho.zip::membro`
(INV-12): `file_size` descomprimido, `mtime` do `.zip` físico; pastas ocultas
e `__MACOSX` ignoradas; gravações em lotes de 500; remoção de linha nunca
implícita.
**Motivo.** Indexar backup compactado sem tocar no disco; substituir o `.zip`
atualiza todas as suas linhas virtuais na varredura seguinte.

## 2026-10-08 — Extractor read-only e pendentes re-tentados (commit 84c28ea)

**Decisão.** Extração lê apenas cabeçalho + `img.info` (pixels nunca
decodificados); convenções A1111 (`parameters`) e ComfyUI (`*KSampler*` →
`*TextEncode*`, um salto); imagens sem metadados permanecem vazias e são
re-tentadas a cada execução (autocorreção intencional, custo baixo).
**Observação.** A mensagem do commit menciona "arquivos .txt gêmeos", mas o
código **nunca** leu `.txt` — "gêmeo" neste projeto é a linha espelhada em
`images_text`. Registrado aqui para ninguém procurar uma feature que não
existe.

## 2026-10-08 — API somente leitura com CORS conscientemente aberto (commit ad5db88)

**Decisão.** FastAPI read-only (INV-11); `allow_origins=["*"]`; `/media` serve
qualquer arquivo legível da raiz (padrão `/`). MITIGAÇÃO OBRIGATÓRIA: bind
sempre em `127.0.0.1`.
**Motivo.** App 100% local, mesma confiança de arquivo aberto no disco; CORS
livre elimina configuração no dev server do Vite. Alternativa descartada por
enquanto: restringir `CATALOG_MEDIA_ROOT` — pressupõe estrutura de pastas que
o produto não exige.

## 2026-10-08 — Interface Tokyonight + app-shell + navegação por scroll (commit fd9cc89)

**Decisão.** Tema Tokyonight-Dark com tokens centralizados no `@theme`;
raiz `h-screen overflow-hidden` (exatamente uma barra de rolagem por área);
`wheel` navega anterior/próxima com guarda de 200ms; `Esc` fecha em camadas
(painel → viewer).

## 2026-10-08 — Testes de regressão standalone (commit b2f2684)

**Decisão.** Suítes com `assert` puro, sem pytest; rodam com o venv do
backend; bancos temporários em `/tmp/opencode/`; a suíte da API sobe um
uvicorn real (porta 8123) em vez de mockar HTTP.

## 2026-10-08 — Streaming de ZIP em RAM (commit 317e0b4)

**Decisão.** `/media` atende membros de ZIP por `StreamingResponse` de
`io.BytesIO` (chunks de 64 KiB + `Content-Length`); 404 limpo para zip
corrompido/apagado/membro inexistente; guarda de path traversal via
`realpath`. Nada é extraído para o disco.

## 2026-10-08 — Requirements pinado, com lacuna conhecida (commits 0b33e80, 5388af6)

**Decisão.** `node_modules` e `.venv` saem do rastreamento do git;
`backend/requirements.txt` com dependências pinadas.
**Lacuna.** `gradio_client` (presente no venv atual) NÃO está no requirements —
reconstruir o venv só pelo arquivo quebraria o space_tagger. Tarefa pendente
na fila (`task.md`).

## 2026-10-08 — Space WD-Tagger como complemento opcional (commit 9e3adc4)

**Decisão.** Alvos = imagens SEM nenhuma tag (`NOT EXISTS`) — complementa o
tagger local, que só marca quem tem prompt; gravação `INSERT OR IGNORE` com
`source='space_api'` (primeiro que grava vence); throttle de 5s por sucesso;
exceção documentada à regra "nada em disco": membro de ZIP vira temporário
físico em `/tmp` por uma requisição, removido no `finally`; parser descarta
rating e characters e filtra score > 0.35.
**Motivo.** Rede é opcional: erro por imagem não aborta nada e o sistema
local segue 100% funcional.
**Nota.** O PRD cita controle de exibição de conteúdo sensível (NSFW) como
finalidade das tags via rede; hoje o parser **descarta** o rating — o
controle de NSFW ainda não está implementado no frontend.

## 2026-10-08 — Masonry round-robin (herança do projeto matrix-photo-gallery)

**Decisão.** Colunas verticais `flex` independentes em altura natural com
distribuição round-robin (`index % colunas`); posições determinísticas;
nenhuma lib de layout.
**Motivo.** No projeto legado, `masonry-layout`/`imagesloaded` estavam no
`package.json` sem nunca serem importadas, e o recálculo de layout travava a
CPU. Colunas em fluxo normal dispensam relayout e o carregamento assíncrono
nunca encavala a grade.

## 2026-10-08 — Armadilha de pointer-events no Tailwind 4

**Descoberta/decisão.** Nunca empilhar `pointer-events-none` +
`pointer-events-auto` no mesmo elemento: no CSS gerado pelo Tailwind 4,
`.pointer-events-none` vem depois e vence o empate — o overlay inteiro fica
inerte. Padrão correto (DetailPanel): wrapper com `:class` condicional, overlay
alternando auto/none, `<aside>` com `pointer-events-auto` permanente.

## 2026-10-10 — Migração do método de contexto (agent.md monolítico → multi-arquivo)

**Decisão.** O `agent.md` de 589 linhas foi distribuído no novo método de
contexto: `prd.md` (o quê), `architecture.md` (como), `rules.md`
(restrições/invariantes), `design.md` (visual), `task.md` (fila), `memory.md`
(este arquivo). `agent.md` vira índice de entrada com o protocolo de leitura.
**Auditoria prévia.** O agent.md estava ~95% em sync com o código; divergências
corrigidas na reescrita: escrita de `image_tags` também pelo space_tagger
(D1), snippet do tagger com colunas explícitas (D2), envelope do `/search`
documentado com `q` + `prompt_positivo` (D3), 14 tokens do tema completos
(D4), comando de testes em loop (D6). Pendências identificadas foram para a
fila: `gradio_client` no requirements.txt e sincronização do README
(task.md).

## 2026-10-10 — Consolidação histórica: leitura profunda do Matrix legado e do yandere-masonry

**Decisão.** Registrar a linhagem dos dois projetos ancestrais em prosa nos
arquivos de contexto, após leitura profunda dos fontes. Foram examinados o
repositório antigo
`/home/gogarx/Backup_HD_antigo/gogarx/Downloads/program/matrix-photo-gallery/`
(`AGENTS.md`, `server/` completo, `client-modern/`) e o `~/src/yandere-masonry/`
(`src/` completo, `package.json`, READMEs).

**Descobertas (verificadas em código, não em memória):**

- **Cadeia de linhagem da grade.** yandere-masonry (userscript Vue 2.7.16 +
  Vuetify 2.7.2, waterfall com breakpoints `{300:1, 600:2, 900:3, 1200:4,
  1600:6, 1920:7, 2400:8, 2700:9, 3000:10}`) → save local da página em
  `client/novolayout/Masonry.html` → `MasonryGrid.vue` do client-modern
  ("7 colunas baseadas no Masonry.html", fixas a 14.2857%, round-robin
  `index % columnCount`) → nosso `ImageGrid.vue` (mesmo round-robin,
  responsivo 2–7 colunas via `ResizeObserver`).
- **Bibliotecas duplicadas confirmadas.** `client-modern/package.json`
  declara `masonry-layout ^4.2.2` + `imagesloaded ^5.0.0` que o
  `MasonryGrid.vue` **nunca importa**; o TrueMasonry do yandere-masonry
  (CSS Grid com `grid-row-end: span` recalculado via `getComputedStyle` a
  cada `resize`/`update`) era o relayout pesado que travava a CPU. Nosso
  frontend não tem nenhum pacote de layout.
- **Dark mode do yandere-masonry.** `vuetify.theme.dark` alternado no
  AppBar, persistido em `localStorage.__darkmode`, estilos via
  `.theme--dark` e `html:has(#app.theme--dark)`; aqui promovido a tema fixo
  Tokyonight (sem toggle) como identidade do produto.
- **Dores do Matrix legado.** A API só persistia apontadores no MongoDB
  (mongoengine) — as `image_url`/`thumbnail_url` eram downloads remotos do
  homeserver via `api.get_download_url()`; miniaturas nativas grandes
  demais exigiam pipeline S3 (`make-small-thumbnails`); login por token
  quebrado na `matrix_client` 0.3.2 (`login_with_token` inexistente →
  `AttributeError`); Python 3.6.5 pinado; e a API caída virava
  silenciosamente um mock de 100 imagens do `picsum.photos` no frontend.

**Ação.** `architecture.md` ganhou a §5.5 (prosa: o streaming síncrono
local em RAM via `io.BytesIO` aposenta o modelo "metadados aqui, bytes lá"
do Matrix, saltando de três saltos remotos para um salto local em
`127.0.0.1`); `design.md` §3 ganhou a prosa da linhagem yandere-masonry
(round-robin extraído da lógica bem-sucedida, bibliotecas duplicadas
eliminadas, dark mode cristalizado como design system Tokyonight-Dark).

## 2026-10-10 — Controle NSFW, etapa backend: lista negra de termos na API (Tarefa 3)

**Decisão.** `NSFW_BLACKLIST` — conjunto imutável `{"nsfw", "nudity",
"explicit", "breasts", "cleavage", "hentai"}` — definido no topo do
`backend/main.py`; os endpoints de listagem e busca passaram a montar cada
item via `build_item()`, que lê as tags da imagem
(`SELECT tag FROM image_tags WHERE image_id = ?`, coletadas em minúsculas)
e injeta `"tags"` e `"is_nsfw": bool(set(tags) & NSFW_BLACKLIST)` no
envelope JSON, preservando todos os campos anteriores do contrato.

**Motivo.** Fornecer à galeria a informação de que o desfoque condicional
(Tarefa 4, pendente) precisa, sem violar INV-11 (nenhuma escrita; a API
continua 100% read-only) nem INV-13 (leitura por `image_id` usa a chave
primária `(image_id, tag)`; `image_tags` segue derivada e aditiva, escrita
exclusiva de tagger/space_tagger). O cálculo é derivado na leitura, por item
— uma consulta indexada por imagem, até `limit=500` por página, custo
irrisório no app local — e nada é persistido, então a lista negra pode
evoluir sem migração de schema.

**Nota.** O parser do space_tagger descarta o rating do WD-Tagger (ver
2026-10-08), logo a blacklist opera sobre as tags gerais normalizadas; o
termo `explicit` da lista cobre o caso de alguém gravar ratings como tags no
futuro.

**Testes.** `test_api.py` estendido: o fixture ganhou a tag `explicit` na
imagem comfy (caso positivo), o assert do conjunto exato de campos do item
recebeu `tags` e `is_nsfw`, há casos positivo/negativo/vazio na listagem e
na busca, e o caso "imagem sem tags" migrou de comfy para weird. Suíte
completa verde (6/6). Envelope atualizado no `architecture.md` §5.2.

## 2026-10-10 — Controle NSFW, etapa frontend: desfoque condicional nos cartões (Tarefa 4)

**Decisão.** Estado de sessão `reveladas = reactive(new Set())` no `App.vue`
(IDs revelados manualmente pelo usuário); `ImageCard` computa
`ofuscada = is_nsfw && !reveladas.has(id)` e, quando verdadeira, aplica
`blur-xl select-none pointer-events-none` na miniatura (o fade de load passou
de `transition-opacity` para `transition-all`, cobrindo também a transição do
desfoque) e desenha o overlay protetor `absolute inset-0 ... bg-black/70
z-10` com o aviso "NSFW" em `tokyo-red` e o botão discreto "Revelar". O
clique do Revelar usa `@click.stop` — regra de ouro de UX: o evento nunca
vaza ao card pai, que abriria acidentalmente o `ImageViewer` em tela cheia —
e o overlay inteiro também intercepta cliques (`@click.stop` sem handler),
para um toque na área do aviso não abrir o viewer com a imagem sem desfoque.

**Motivo.** A cadeia estado→props→emit foi a forma de cumprir "estado no
`App.vue`, sem criar subcomponentes" dentro da arquitetura real: `App.vue`
detém o Set reativo e o passa via props; `ImageGrid` apenas reemite o
`reveal`; `ImageCard` (dono da tag `<img>`) aplica as classes e o overlay.
O "botão" Revelar é um `<span role="button" tabindex="0">`: o card já é um
`<button>`, e aninhar botão dentro de botão é HTML inválido (conteúdo
interativo) — o `.stop` e o emit funcionam identicamente no span.

**Nota.** A revelação é por sessão (não persistida em `localStorage`) e
pontual por imagem; a proteção cobre apenas a miniatura na grade — o
`ImageViewer` segue sem bloqueio, pois o controle é de exibição discreta
(PRD), não de acesso. Build de produção verde (vite, 18 módulos); o dev
server do Vite permaneceu ativo e recebeu as mudanças por hot-reload.
