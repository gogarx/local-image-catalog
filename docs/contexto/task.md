# task.md — Fila de tarefas

Regras: trabalhe **uma por vez, na ordem** de cima para baixo. Ao concluir,
marque `[x]` com a data e mova para "Concluídas". Decisões tomadas durante o
trabalho viram entrada datada em `memory.md`.

## Pendentes

1. [ ] **`backend/requirements.txt`: adicionar `gradio_client`** (e
   dependências necessárias, ex.: `httpx`, `huggingface_hub`). O venv atual tem
   `gradio_client` 2.7.2 instalado, mas o arquivo não o lista — reconstruir o
   venv pelo requirements quebraria o `space_tagger.py`. Descoberta da
   auditoria de contexto de 2026-10-10 (ver `memory.md`).

2. [ ] **`README.md`: sincronizar com o estado atual.** Pontos divergentes:
   `PRAGMA user_version` é **3** (README diz 2); o `agent.md` mora em
   `docs/contexto/` (README diz raiz); comando de testes correto é o loop
   `for t in tests/test_*.py; do python "$t" || break; done` (a forma com glob
   único roda só a primeira suíte); bancos de teste ficam em `/tmp/opencode/`.

## Concluídas

1. [x] 2026-10-10 — Migração do método de contexto: `agent.md` monolítico →
   `prd.md` + `architecture.md` + `rules.md` + `design.md` + `memory.md` +
   fila `task.md`; `agent.md` virou índice. Divergências da auditoria
   (D1–D6) corrigidas na reescrita.

2. [x] 2026-10-10 — **Tarefa 3 — Blacklist NSFW no backend** (`backend/main.py`):
   `NSFW_BLACKLIST` no topo do arquivo; `/images` e `/search` passaram a
   retornar `tags` (minúsculas, lidas de `image_tags` por item) e `is_nsfw`
   (interseção com a blacklist) em cada item do envelope. Leitura pura
   (INV-11/INV-13 intactas), suíte de testes estendida e verde (6/6),
   envelope documentado em `architecture.md` §5.2. Próxima da fila:
   Tarefa 4 (blur no frontend).

3. [x] 2026-10-10 — **Tarefa 4 — Desfoque condicional no frontend**
   (`App.vue` + `ImageGrid`/`ImageCard` existentes): estado de sessão
   `reveladas` (Set reativo no `App.vue`, desce à grade via props, `reveal`
   sobe via emit); `ImageCard` aplica `blur-xl select-none pointer-events-none`
   na miniatura `is_nsfw` não revelada e desenha o overlay protetor com aviso
   "NSFW" e botão "Revelar" (`@click.stop` — o clique nunca vaza ao card pai e
   nunca abre o `ImageViewer` por acidente). Nenhum componente novo criado;
   `npm run build` verde e dev server do Vite ativo com hot-reload.
