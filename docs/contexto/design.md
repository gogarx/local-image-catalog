# design.md — Identidade visual e UX

Vale para **toda tela nova**. Tema: **Tokyonight-Dark**, inspirado na
experiência de visualização estilo yandere — escuro, limpo, densa em imagens,
com metadados fora do caminho até serem chamados.

## 1. Cores — tokens em `frontend/src/style.css` (`@theme` do Tailwind 4)

| Token | Hex | Uso típico |
|---|---|---|
| `tokyo-bg` | `#1a1b26` | fundo geral |
| `tokyo-bg-deep` | `#16161e` | fundo profundo (header, rodapés) |
| `tokyo-surface` | `#1f2335` | superfícies: cards, painéis, caixas |
| `tokyo-overlay` | `#292e42` | overlays, chips, elementos flutuantes |
| `tokyo-border` | `#3b4261` | bordas e divisores |
| `tokyo-fg` | `#c0caf5` | texto principal |
| `tokyo-dim` | `#565f89` | texto secundário/apagado, dicas |
| `tokyo-blue` | `#7aa2f7` | acento primário (links, chips de tag, foco) |
| `tokyo-cyan` | `#7dcfff` | acento secundário |
| `tokyo-purple` | `#bb9af7` | acento terciário |
| `tokyo-green` | `#9ece6a` | sucesso / confirmação |
| `tokyo-yellow` | `#e0af68` | aviso |
| `tokyo-red` | `#f7768e` | erro / destrutivo |
| `tokyo-orange` | `#ff9e64` | destaque quente |

Regra de ouro: **sempre as classes utilitárias `*-tokyo-*`; nunca hex solto
nos componentes**. Tela nova que precisar de cor nova define o token no
`@theme` primeiro.

Tipografia: `ui-sans-serif, system-ui, -apple-system, sans-serif` (padrão do
`body` em `style.css`). Fonte do sistema, sem webfonts.

## 2. Layout app-shell — uma barra de rolagem por área

- Raiz `h-screen overflow-hidden`: a página nunca rola.
- `main` da galeria é o **único** scroll da página.
- Painéis sobrepostos (detalhes, viewer) são `h-screen flex-col` com header
  fixo e scroll (`overflow-y-auto` + `overscroll-contain`) **exclusivamente
  no filho de conteúdo** — onde os prompts ultrapassam a altura da tela.
- **Nunca** `overflow-y-scroll` nem rolagem aninhada nas caixas de prompt.

## 3. Grade masonry — colunas independentes, altura natural

- Colunas são pilhas verticais `flex` independentes com imagens em altura
  natural; cada coluna cresce sozinha conforme as imagens chegam —
  carregamento assíncrono nunca quebra nem encavala a grade.
- Distribuição **round-robin** (`index % colunas`): posições determinísticas,
  que não se movem quando as imagens carregam. Nenhuma lib de layout
  (`masonry-layout`/`imagesloaded` são o anti-padrão do projeto legado).
- Colunas responsivas via `ResizeObserver` com debounce de 120ms:
  `<500px→2, <768→3, <1024→4, <1280→5, <1440→6, ≥1440→7` colunas.
- A grade não tem overflow nem altura fixa — o scroll continua sendo só o do
  `main`.

A grade de 7 colunas com distribuição round-robin é herança direta e
declarada do **yandere-masonry** (`~/src/yandere-masonry/`), o userscript
Vue + Vuetify que o desenvolvedor humano adotou como a stack de design ideal
para navegação de imagens: dele vieram o modo waterfall em cascata fluida com
colunas responsivas por breakpoints (`{300:1, 600:2, 900:3, 1200:4, 1600:6,
1920:7, 2400:8, …}` — sete colunas a partir de 1920px no original), o dark
mode persistido como tema e o visualizador que só revela botões e tags
quando a imagem é clicada. O caminho até aqui passou pelo client-modern do
matrix-photo-gallery, que já havia extraído do yandere-masonry — via um save
local da página, o `Masonry.html` — a grade de sete colunas fixas de
14.2857% com distribuição round-robin (`index % columnCount`): a mesma
lógica que o nosso `ImageGrid.vue` preserva, aprimorada para colunas
responsivas de 2 a 7 via `ResizeObserver`.

A diferença decisiva é o que ficou no caminho. O legado carregava
`masonry-layout` 4.2.2 e `imagesloaded` 5.0.0 no `package.json` sem nunca
importá-las — peso morto de instalação — enquanto o TrueMasonry original do
yandere-masonry media a altura de cada item com `getComputedStyle` e
reconstruía o grid inteiro (`grid-row-end: span`) a cada `resize`/`update`,
exatamente o recálculo pesado que travava a CPU no passado. Nossa grade
extraiu a parte que funcionava — colunas verticais independentes em altura
natural, fluxo CSS puro, posições determinísticas — e eliminou as
bibliotecas duplicadas de vez: o `package.json` do frontend não tem um
único pacote de layout, as posições não se movem quando as imagens carregam
e o único cálculo de distribuição é um módulo por coluna. O dark mode do
yandere-masonry era um estado alternável (tema Vuetify trocado no AppBar e
persistido em `localStorage.__darkmode`); aqui ele foi promovido a
identidade fixa do produto — o Tokyonight-Dark da §1 é o modo escuro do
yandere cristalizado como design system, com o viewer limpo, o painel de
detalhes sob demanda e os chips de tags clicáveis herdando o mesmo espírito
de navegação.

## 4. Componentes visuais — forma e comportamento

**ImageCard.** Card do masonry: `media_url` com lazy loading; skeleton
(`min-h-32`) antes do load; fade-in em `@load`; fallback em `@error`
(recarrega o elemento ao trocar de imagem). `media_url` vazia (arquivo fora
da raiz servida) → só o nome do arquivo, sem `<img>`. Cartão com `is_nsfw:
true` ainda não revelado na sessão: miniatura ofuscada com `blur-xl
select-none pointer-events-none` sob um overlay protetor `bg-black/70`
(com aviso "NSFW" em `tokyo-red` e botão discreto "Revelar" em `tokyo-fg`);
o clique no "Revelar" — e qualquer clique no overlay — usa `@click.stop` e
**nunca** propaga ao card pai, para não abrir acidentalmente o `ImageViewer`
com o conteúdo ainda protegido.

**SearchBar.** Busca dinâmica com debounce de 300ms; `Esc` limpa; sincroniza
com `modelValue` (clicar numa tag atualiza o campo). Banner de erro em
`tokyo-red` quando a API responde 400 (sintaxe FTS inválida).

**Header.** Contador de resultados ("N imagens" / "N resultados") em
`tokyo-dim`.

**Estados da grade.** Loading: `opacity-40` na grade. Empty state distinto
para busca sem resultados vs. galeria vazia (a galeria vazia dica:
"Rode scanner.py e depois extractor.py no backend.").

**Paginação.** Anterior/Próximo, 24 por página (semântica `offset` da API).

**ImageViewer.** Visualização expandida estilo yandere: imagem limpa e
centralizada sobre fundo escuro (`z-50`), prompts ocultos por padrão; botões
Detalhes/Fechar; clique na imagem alterna o painel; rodapé de atalhos
("Rolar o scroll: anterior / próxima · Esc fecha · clique na imagem:
detalhes"). Com o viewer aberto e o painel fechado, o scroll do mouse
(`wheel` global com guarda de 200ms contra saltos múltiplos) navega
anterior/próxima; navegação desativada com o painel aberto, para o conteúdo
do painel rolar. `Esc` fecha em camadas: primeiro o painel, depois o viewer;
ao fechar, `blur()` do elemento focado.

**DetailPanel.** Painel deslizante à direita SOBRE o viewer (`z-[60]`):
metadados formatados (`formatSize` B/KB/MB/GB/TB; `formatTime` epoch →
`toLocaleString('pt-BR')`), caixas de prompt positivo/negativo/workflow e
tags como chips clicáveis (`tokyo-blue`) que disparam a busca; só abre pelo
botão Detalhes. Scroll apenas no filho de conteúdo (§2).

**CopyButton.** `navigator.clipboard.writeText` (só se `window.isSecureContext`)
com fallback: textarea oculto → `focus`/`select` → `execCommand('copy')` →
remoção do DOM. Feedback "Copiado!" por 1,5s.

## 5. Interações-padrão

- Busca instantânea: cada tecla (após debounce) chama `/search?q=` (FTS5 do
  SQLite). A grade lista só dados leves (`/images`); metadados pesados
  (`/images/{id}`) só quando a imagem é aberta.
- Clique em chip de tag fecha tudo (viewer + painel) e busca o termo.
- Guarda anti-defasagem: número sequencial por requisição — resposta velha é
  descartada (nada de conteúdo trocado no meio).
- Erros de API mostram o `detail` do FastAPI (nunca engolir).

## 6. Armadilha Tailwind 4 — pointer-events

**Nunca empilhe `pointer-events-none` + `pointer-events-auto` no mesmo
elemento** (ex.: classe estática + condicional juntas): no CSS gerado pelo
Tailwind 4 `.pointer-events-none` vem depois e vence o empate — o overlay
inteiro fica inerte (clique atravessa, botão Fechar morto).

Padrão correto (DetailPanel):
- wrapper `fixed z-50` com `:class="open ? '' : 'pointer-events-none'"`;
- fundo escuro com `pointer-events-auto` quando aberto e `pointer-events-none`
  quando fechado;
- `<aside>` com `pointer-events-auto` permanente (fica fora da tela quando
  fechado).
