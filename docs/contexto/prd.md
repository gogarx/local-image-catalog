# prd.md — Product Requirement Document (local-image-catalog)

## Problema

O acúmulo digital de milhares de mídias geradas por inteligências artísticas
locais — imagens soltas, resultados de experimentos e backups compactados em
`.zip` — sem estourar o armazenamento físico em disco. Hoje essas mídias são
opacas: estão no disco, mas os prompts e workflows que as geraram não são
buscáveis, e abrir um `.zip` "só para ver" exige extração física.

## Usuário alvo

O próprio desenvolvedor e entusiasta de IA que gerencia backups massivos.
App pessoal, uma máquina, um usuário — sem multiusuário, sem autenticação.

## O que o produto entrega

1. **Catalogação sem duplicação.** Imagens soltas (png, jpg, jpeg, webp, gif,
   bmp, tif, tiff) e membros de `.zip` indexados num único ecossistema
   buscável. ZIPs são cidadãos de primeira classe: indexados e exibidos SEM
   descompactar — nada é extraído para o disco, nada é duplicado.
2. **Busca por texto completa e instantânea.** Prompts positivo e negativo +
   nós de grafos do ComfyUI, indexados em FTS5 com ranking bm25, filtros por
   campo e sintaxe de busca (OR, NOT, prefixo). A busca responde enquanto o
   usuário digita.
3. **Metadados extraídos dos formatos conhecidos.** A1111/Forge WebUI (chunk
   `parameters`) e ComfyUI (chunks `prompt`/`workflow`). Imagem sem metadados
   continua catalogada (nome, tamanho, data) e é re-tentada a cada rodada —
   metadados embutidos depois são detectados automaticamente.
4. **Tags limpas e automatizadas.** Dicionário local (yandere) para quem tem
   prompt; Space WD-Tagger via rede para quem não tem. Finalidade:
   categorização visual e base para controle de exibição de conteúdo
   sensível (NSFW). Nenhuma tag é inventada — sem dicionário, não marca.
5. **Galeria local para visualização.** Grade masonry responsiva estilo
   yandere, visualização expandida limpa, painel de detalhes com prompts
   copiáveis em um clique e chips de tags clicáveis que viram buscas.
6. **Operação 100% local, read-only na web.** Nada sai da máquina; a API HTTP
   nunca grava no banco; escritas são exclusividade dos módulos CLI,
   executados manualmente pelo dono da máquina.
7. **Proteção contra dependências externas quebradas.** Rede é opcional:
   sem rede (ou com o Space fora do ar), o sistema local continua 100%
   funcional; o tagger remoto aborta em vez de inventar dados.

## Requisitos não funcionais

- **Idempotência:** re-rodar qualquer módulo é sempre seguro — nada duplica,
  nada perde texto, tudo retoma de onde parou (lotes de 500).
- **Desempenho:** busca sempre por índice (FTS5, nunca varredura); grade sem
  recálculo de layout (colunas independentes, posições determinísticas).
- **Concorrência local:** WAL permite consultar a galeria enquanto a
  indexação roda.
- **Segurança local:** servidor sempre preso a `127.0.0.1`; confiança
  equivalente à de um arquivo aberto no próprio disco.

## Fora de escopo

Multiusuário, autenticação, nuvem ou servidor remoto, escrita/edição via web,
extração física de ZIPs, lixeira/soft-delete.
