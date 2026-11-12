# POC Control

> **Nota de sincronização (2026-11-02):** este repositório é a base original de onde
> `FlavioFGM/suse-poc-toolkit` nasceu (pasta `poc-control/` de lá, histórico completo preservado).
> Desde então, todo o desenvolvimento continuou no monorepo; este Pull Request traz o estado atual
> de volta pra cá. Duas diferenças em relação a rodar isto dentro do monorepo: (1) `poc-planner/`
> aqui é só um `index.html` **vendorizado** (cópia de um momento específico, não o projeto irmão
> completo com histórico/testes próprios — ver `poc-planner/README-VENDORED.md`); (2)
> `docker-compose.yml`/`web/Dockerfile`/`scripts/update.sh` foram ajustados para rodar este
> repositório sozinho (sem a pasta-irmã `../poc-planner/` que só existe dentro do monorepo). O
> resto do texto abaixo ainda descreve a arquitetura como "uma pasta do monorepo" porque foi escrito
> lá — mantido como referência de arquitetura, mesmo rodando aqui como repositório único. Ver
> `docs/sincronizar-gbrlins-poc-control.md` para o mecanismo usado nesta sincronização e como repetir
> o processo depois.

> Este projeto passou a ser uma pasta do monorepo `suse-poc-toolkit` (histórico completo
> preservado), ao lado de `../eib-builder/` e `../poc-planner/`. O planejador citado abaixo
> (antes `plannerEngine.js` portado + cópia vendorizada via `scripts/vendor-planner.sh`) agora é
> servido direto a partir de `../poc-planner/index.html` -- ver a seção "Planejador vendorizado e
> conector" mais abaixo, atualizada.

Ferramenta pessoal (depois, do time) pra cobrir o ciclo de PoC de cliente de ponta a ponta:
**planejar** o escopo (tela inicial do app), **executar** com semáforo por item e acompanhamento
de sessão, e fazer uma **triagem automática de TR/edital (RFI)** contra o portfólio SUSE.

Dono: Gabriel (Solutions Architect, SUSE). Idioma da interface e dos textos gerados: **português (pt-BR)**.
A casca do app (menu, navbar, planejador) tem um seletor PT/EN/ES e alternância de tema claro/escuro (ver
"Tema (claro/escuro) e rodapé de build" e "O planejador como tela inicial" abaixo) — isso não muda a regra
acima para o conteúdo gerado pela IA nem para os formulários de domínio do Executar PoC/RFI, que continuam
só em pt-BR. **Única exceção**: a exibição de um Procedimento acompanha esse seletor (tradução
automática do HTML, ver "Tradução de exibição" em "Procedimentos" abaixo) -- os formulários onde ele é
cadastrado/editado continuam em pt-BR, só o conteúdo final mostrado é que muda de idioma.

## Repositório e ambiente

- Git: `https://github.com/FlavioFGM/suse-poc-toolkit.git`, folder `poc-control/` (own history preserved from the former `gbrlins/poc-control.git`). Se `gbrlins/poc-control` ganhar commits novos direto por lá, ver `poc-control/docs/sincronizar-gbrlins-poc-control.md` para o passo a passo de trazê-los pra cá sem perder histórico.
- Servidor: Raspberry Pi na rede local, acessado por SSH com o alias `rasp` (chave em `~/.ssh/rasp`, ver `~/.ssh/config`). **Nunca** usar senha nem gravar credenciais em arquivos do repositório.
- Exposição externa: `cloudflared` já instalado na Raspberry. Publicar só o serviço `web`. Recomendado proteger com Cloudflare Access além do login do app.
- Tudo roda com `docker compose` em imagens **ARM64**.

## Organização do repositório (features separadas para múltiplos times)

O front end é dividido por feature para "Executar PoC", "Planejar PoC" e "RFI" avançarem em
paralelo sem pisar um no outro:

- `web/src/features/executar-poc/` — páginas desta ferramenta (POCs, Procedimentos). Dono: Gabriel.
- `web/src/features/planejar-poc/` — só o wrapper de rota (`pages/PlanPoc.tsx`) que embute o
  planejador num `<iframe>` apontando pra `/planner/` na rota `/` (ver "O planejador como tela
  inicial" abaixo). Nenhuma lógica do planejador mora aqui: ela é o projeto irmão
  `../poc-planner/` (repo/histórico próprio dentro do monorepo), copiado sem alteração pro
  `web/Dockerfile` em build time. Dono: time do planejador (`../poc-planner/`).
- `web/src/features/rfi/` — triagem de TR/edital contra o portfólio SUSE (ver seção "RFI"
  abaixo). Dono: Gabriel.
- `web/src/pages/` (Layout, Home, Login, MinhaConta, Usuarios) e `web/src/i18n.tsx` são a
  casca compartilhada pelas três features — mudança aqui pede revisão de todos os lados.
- `api/` cobre Executar PoC (`api/app/pocs/`, `api/app/classificacao/`, `api/app/procedimentos/`)
  e RFI (`api/app/rfi/`) — o planejador ainda não tem backend próprio além do que empresta de
  Executar PoC pra "Importar documento do cliente" (ver abaixo); guarda o resto só em
  `localStorage`.
- `.github/CODEOWNERS` mapeia esses caminhos para revisão automática; troque o placeholder pelo
  handle real de quem mantém o planejador.
- Convenção de branch: `feature/executar-poc/<nome>`, `feature/planejar-poc/<nome>`,
  `feature/rfi/<nome>` e `feature/shell/<nome>` para mudanças na casca compartilhada.
- Alias de import `@/` → `web/src/` (configurado em `vite.config.ts` e `tsconfig.json`), para os
  imports entre features não dependerem da profundidade relativa de cada pasta.

## Escopo atual

- **Um único usuário** (Gabriel), criado por seed a partir de variáveis do `.env` (`ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH`). O modelo de dados já prevê `user_id` em tudo, para virar multiusuário depois sem migração dolorosa.
- IA: **Gemini** (chave em `GEMINI_API_KEY` no `.env`). Usar chave de plano pago, porque os documentos são de clientes do setor público.

## Conceito central: semáforo por item

Para cada item extraído do PDF da POC:

| Flag | Critério |
|---|---|
| 🟢 Verde | Existe procedimento **validado** na base e o Gemini confirma que ele atende o item. A UI mostra o link "é só seguir". |
| 🟡 Amarelo | Não há procedimento validado, mas a busca na web (Gemini com grounding do Google Search) traz evidência de viabilidade. Mostrar as fontes (links). Sem evidência alguma também cai aqui, como "amarelo — baixa confiança". |
| 🔴 Vermelho | Só com **evidência explícita** de que não é suportado ou não é viável. Mostrar as fontes. |

Regras:
- A flag é **sugestão**. O usuário pode sobrescrever a cor e o procedimento vinculado. Guardar se foi `auto` ou `manual`.
- Guardar a justificativa curta e as fontes de cada classificação.
- Reprocessar um item sob demanda (botão "reavaliar").

## Ciclo de aprendizado

Ao concluir um item, o usuário pode anexar ou escrever o passo a passo que funcionou e clicar em **"Promover a procedimento validado"**. O procedimento entra na base com embedding, e em POCs futuras itens equivalentes saem verdes.

## Procedimentos (base de conhecimento)

- Formato de entrada: **HTML** (upload). Converter para texto/markdown para indexar e guardar o HTML original para exibição.
- Indexar por **seção** (`h2`/`h3`), não o documento inteiro: cada seção é um chunk com embedding, ligado ao procedimento pai. Assim o match aponta para o passo certo.
- Metadados: título, produtos/tecnologias (tags), cliente de origem, data, status (`rascunho` | `validado`), versão.
- Os HTMLs seguem um padrão útil para extração: objetivo e fluxo no topo, "Valores desta sessão", "O que ressaltar", passos numerados com "Esperado:", "Se der erro" (tabela sintoma → causa → ação), "Limpeza" e "Evidências para o relatório".
- **Categorias (taxonomia fixa, `api/app/categorias.py` / `web/src/categorias.ts`)**: 8 códigos (VIRT,
  K8S, STR, SEC, OBS, OS, EDGE, IA) das mesmas áreas do portfólio SUSE usadas na triagem de RFI (ver
  abaixo) -- distinto de `tags` (texto livre). Um procedimento pode ter **várias** categorias
  (`Procedimento.categorias`, `ARRAY(String)` com índice GIN); um item de PoC/RFI tem **uma só**
  (`Item.categoria_codigo`/`RfiItem.categoria_codigo`), extraída pelo Gemini junto com os outros campos
  (sem chamada extra) ou herdada do catálogo do planejador (`app/pocs/planner_import.py`). Usada para
  restringir a busca vetorial de procedimentos (`classificacao/service.py::_buscar_candidatos`) ao
  subconjunto da mesma categoria antes de rankear por similaridade -- mais rápido e mais barato em
  tokens do que varrer a base inteira a cada item; se a categoria ainda não tem nenhum procedimento,
  cai pro fallback sem filtro (nunca perde um match só por lacuna de tagueamento). Mesma lógica vale
  pro seletor manual "Importar procedimento validado" (`sugerir_procedimentos`) e pra busca do RFI (ver
  abaixo). Migração `0018`.
- **Tradução de exibição (única exceção à regra de pt-BR do topo deste arquivo)**: o HTML de um
  procedimento é mostrado no idioma selecionado na casca (`?lang=` em `GET /api/procedimentos/{id}`),
  não necessariamente no idioma em que foi enviado. No upload, `_criar_procedimento`
  (`api/app/procedimentos/router.py` -- caminho compartilhado por upload manual, sync entre
  instâncias e promoção de item de PoC/RFI) detecta o idioma original e já traduz pro inglês de
  forma ansiosa, numa chamada Gemini só (`gemini.py::traduzir_procedimento_html`, HTML -> HTML
  preservando tags/estrutura, sem traduzir comandos/YAML/nomes de recursos/URLs). Os outros dois
  idiomas (pt/es, o que não for o original) ficam preguiçosos: traduzidos na primeira vez que
  alguém abre o procedimento nesse idioma e cacheados em `Procedimento.traducoes` (JSONB) daí em
  diante -- nunca para quem já tem o original no idioma certo. Se a tradução sob demanda falhar,
  cai pro original sem quebrar a página (`idioma_conteudo` no retorno diverge do `lang` pedido, e a
  UI mostra um aviso em vez de fingir que traduziu). As extrações/classificações de PoC e RFI, os
  formulários e os resumos de sessão continuam só em pt-BR -- é só a exibição do procedimento que
  acompanha o idioma da casca. Migração `0026`.

### Carga inicial (pasta `seed/procedimentos/`)

Procedimentos da POC Sefaz-RJ, todos `validado`:
1. **Argo CD do cliente → k3s**: cadastro declarativo de cluster k3s num Argo CD no OpenShift (rede, certificado, ServiceAccount, Secret de cluster, Application, teste GitOps com rollback, limpeza).
2. **HPA em nginx no k3s com Ingress**: Deployment/Service pela UI do Rancher, HPA `autoscaling/v2`, teste de carga, Ingress Traefik com host e TLS opcional.
3. **Integração do k3s com Vault externo**: auth method Kubernetes num mount novo, credencial de revisão (`system:auth-delegator`), política KV v1, papel, pod de teste, diagnóstico de 403, opções de consumo (Agent Injector, CSI, VSO, leitura direta).

Na carga, **remover ou mascarar** dados específicos do cliente que não devem ser reutilizados (IPs, hostnames internos, nomes de repositório). Guardar a versão original separada, sem ir para o índice.

## POCs

- Upload do PDF, de uma planilha (XLSX/CSV), ou texto/JSON colado (inclusive o JSON exportado pelo planejador — ver "O planejador como tela inicial") → o Gemini lê nativamente e devolve JSON estruturado (schema fixo): `itens[] { codigo, titulo, descricao, criterio_aceite, categoria, categoria_codigo }` (`categoria_codigo` é a taxonomia fixa, vazio quando o item não se encaixa claramente numa área do portfólio SUSE — ver "Procedimentos" acima).
- O usuário revisa a lista extraída (editar, juntar, remover) antes de rodar a classificação.
- Cada POC tem **sessões** (data, participantes, agenda).
- Em cada item: status (`pendente` | `em_andamento` | `concluido` | `bloqueado` | `nao_aplicavel`), notas com data e sessão, anexos e procedimento vinculado.

## Resumo de sessão

Botão "Gerar resumo da sessão": a partir das notas e das mudanças de status daquela sessão, o Gemini monta um texto pronto para colar no e-mail ao cliente ("Hoje realizamos…", "Pendências…", "Próximos passos…"). Tom formal e neutro. **Não envia e-mail**: só exibe com botão de copiar. Também exportar o status da POC inteira como HTML imprimível.

## RFI (triagem de edital/TR contra o portfólio SUSE)

Aba separada no menu lateral (`/rfis`), sem relação com uma PoC — é uma primeira triagem
automática, feita antes/independente de qualquer execução.

- Upload de PDF (lido nativamente pelo Gemini), Word (`.docx`, via `python-docx`) ou planilha
  (XLSX/CSV, reaproveitando `app/pocs/planilha_import.py`), ou colar texto.
- Extração (`extrair_itens_rfi` em `api/app/gemini.py`): o Gemini varre o documento inteiro
  (qualquer estilo de numeração/estrutura) e extrai só os itens-folha dentro das áreas do
  portfólio SUSE — lista fixa no prompt (`app/categorias.py`: virtualização, Kubernetes/containers,
  storage, segurança, observabilidade, SO Linux, edge, IA), não configurável na UI — preservando a
  numeração original do edital (`codigo`), usando a seção mais próxima como `categoria` (texto
  livre) e classificando também `categoria_codigo` (o código da taxonomia fixa, na mesma chamada).
  Ignora cláusulas administrativas/jurídicas, penalidades, inventário de hardware e caderno de
  testes.
- Assim que a extração termina, dispara **automaticamente** (mesmo background task, sem clique
  extra — diferente do fluxo "classificar pendentes" do Executar PoC, que é manual) a avaliação
  item a item (`avaliar_item_rfi` em `app/rfi/service.py`). Desde que a categorização passou a
  existir, a ordem mudou: **primeiro busca um procedimento interno validado** (restrito por
  afinidade de `categoria_codigo`, mesma função `_buscar_candidatos` do semáforo de PoC) e só
  pesquisa na web se nenhum procedimento confirmar o atendimento — mesmo espírito de "procurar
  primeiro na base interna" do semáforo de PoC, e mais barato em tokens. Quando um procedimento
  interno confirma, grava `veredito=atende` e `RfiItem.procedimento_id` (exibido na UI como "Ver
  procedimento interno: `<título>`" — `RfiItem.procedimento_titulo`, uma `@property` no modelo que
  lê `procedimento.titulo`, sem precisar de JOIN explícito nem endpoint novo — sem fontes web).
  Senão, cai para a busca web com grounding do Google
  Search, classificando um veredito em **4 estados**: `atende` / `atende_parcial` / `nao_atende` /
  `sem_evidencia`. "Sem evidência" existe pra nunca afirmar atendimento (ou não-atendimento) sem
  achar prova — mesma filosofia do semáforo de PoC acima. Mesmo workaround de 2 chamadas Gemini
  (grounding sem `response_schema` → classificação com `response_schema` sem grounding) pela
  limitação documentada.
- Veredito é sugestão: editável manualmente (`origem: auto|manual`), e cada item tem um botão
  "Reavaliar" individual. Marcar um item como `atende` à mão também alimenta a base de histórico
  compartilhada (`atualizar_embedding_historico_rfi`, mesma usada pela avaliação automática) --
  conhecimento validado pelo usuário conta tanto quanto um confirmado pelo Gemini pra responder
  RFIs/PoCs futuros equivalentes. Deliberadamente **não existe** um "promover a procedimento" do
  lado RFI (diferente do lado PoC, que tem um de verdade a partir de um anexo com passo a passo
  escrito): a resposta de um item de RFI é só texto + veredito, não um procedimento com passo a
  passo de implementação, então catalogar isso em Procedimentos poluiria a base; o histórico
  acima é o canal certo pra essa reutilização.
- Se a extração falhar (`status_extracao=erro` -- inclusive após uma recuperação de reinício do
  servidor, ver ADR 7 abaixo), `POST /api/rfis/{id}/reextrair` tenta de novo só os documentos que
  ainda não geraram nenhum item (evita duplicar itens de um documento que já tinha dado certo
  antes da interrupção). Botão dedicado na UI, só ícone com tooltip, ao lado da mensagem de erro
  -- deliberadamente diferente do "Reavaliar tudo", que reavalia itens já existentes.
- Export em HTML imprimível e XLSX (primeira escrita de planilha do projeto — `openpyxl` só lia
  planilhas de entrada antes).
- Histórico (`/rfis`) com filtro por usuário e por data, resolvido 100% no front (lista inteira
  carregada de uma vez — não há endpoint de filtro, a escala não justifica).
- Tabelas `rfis` (com `criado_por_id` → `users.id` — primeira FK do projeto apontando pra quem
  criou um registro) e `rfi_itens`. Migração `0015`; `rfi_itens.categoria_codigo` e
  `rfi_itens.procedimento_id` (SET NULL) vieram na migração `0018`.

## Stack

| Serviço | Tecnologia |
|---|---|
| `db` | PostgreSQL + pgvector (imagem `pgvector/pgvector`, ARM64), volume persistente |
| `api` | Python + FastAPI, SQLAlchemy + Alembic, SDK `google-genai`, tarefas em background para processar PDFs |
| `web` | React + TypeScript (Vite), servido por nginx, que também faz proxy de `/api` |

- Embeddings: modelo de embedding do Gemini (conferir o nome e a dimensão atuais na documentação antes de criar a coluna `vector`).
- Busca: similaridade de cosseno no pgvector, top-k por item, depois confirmação pelo Gemini (o match tem que fazer sentido, não só ser parecido).
- Login: sessão com cookie httpOnly; senha com hash argon2/bcrypt.

## Modelo de dados

`users`, `pocs`, `poc_documentos` (PDF/planilha original), `itens` (com `categoria_codigo`),
`classificacoes` (flag, origem auto/manual, justificativa, fontes, modelo), `poc_prerequisitos`,
`procedimentos` (com `categorias`, array da taxonomia fixa), `procedimento_chunks` (texto,
embedding), `sessoes`, `notas`, `anexos`, `status_historico`, `rfis` (dono via `criado_por_id`),
`rfi_itens` (veredito de 4 estados, justificativa, fontes, `categoria_codigo`, `procedimento_id`).
Tudo em `api/app/models.py` (arquivo único, não separado por feature); a taxonomia fixa de
categorias vive em `api/app/categorias.py` (não é uma migração, é um dicionário Python).

## Marcos

1. Esqueleto: `docker-compose.yml`, `.env.example`, API com healthcheck, banco com migrações, front vazio, login do usuário único. Subir na Raspberry.
2. Procedimentos: upload de HTML, chunking por seção, embeddings, listagem e visualização. Importar o `seed/`.
3. POC: upload do PDF, extração de itens, revisão da lista.
4. Classificação: busca vetorial → confirmação → grounding web → semáforo com fontes.
5. Execução: sessões, status, notas, anexos, promover a procedimento.
6. Resumo de sessão e exportação HTML.
7. Exposição via cloudflared (+ Cloudflare Access) e backup do volume do Postgres.

## O planejador como tela inicial

Já foi um "modo" trocado no menu hambúrguer (Executar PoC vs. Planejar PoC); depois virou uma
hierarquia única com o planejador na própria raiz (`/`); hoje (`web/src/pages/Home.tsx`) a raiz é
um **hub**, não o planejador em si: hero + um botão de ação por área (Planejar PoC, Analisador de
RFI, Procedimentos) de cores diferentes, mais uma lista "mais recentes" compacta por área
(PoCs/RFIs/Procedimentos) abaixo, cada uma linkando pra sua tela cheia com filtros (`/pocs`,
`/rfis`, `/procedimentos`). O planejador em si vive em `/planejar` (o botão "Planejar PoC" do hub
leva lá direto pra tela inicial DELE — sem pular etapa). Não existe mais um botão de atalho pra
"Executar PoC" no hub: a lista "PoCs recentes" da Home e o link "ver todas" já cobrem o caminho até
`/pocs` e `/pocs/:id` (rotas inalteradas), então o atalho duplicava um caminho que já existia.

Houve um `?start=new`/`?start=import` que pulava a tela inicial do planejador direto pro passo
"Projeto" ou pro formulário de importar documento (pra evitar "clicar em Iniciar duas vezes", uma
no hub e outra lá). Removido (poc-planner/index.html's `applyUrlStart`, `PlanPoc.tsx`): o hub só
tem UM botão "Planejar PoC" que leva pra tela inicial do planejador, e essa tela já lista "Novo
Projeto", "Importar Projeto", "Importar documento do cliente" e "Biblioteca de procedimentos" como
opções igualmente visíveis — eram exatamente os mesmos atalhos que o hub tentava duplicar um nível
acima, só que incompletos (sem "Importar Projeto" nem a biblioteca). Pular essa tela também
escondia essas duas opções por trás de um clique que ninguém pediu.

Não há mais menu lateral (`Sidebar.tsx` foi removido): a navegação entre áreas é só pelo hub da
Home, mais um botão "Início" (ícone de casa) no topbar, visível em toda página
(`web/src/pages/Layout.tsx`), que sempre volta pra `/` -- clicar nele nunca perde nada em
andamento, porque o planejador já salva cada mudança de estado no `localStorage` de forma síncrona
(`saveState()`, chamado a cada tecla/clique, não só ao navegar). "Minha conta" e "Usuários" (só
admin) viraram itens do dropdown de conta no topbar (`account-dropdown`), ao lado do e-mail do
usuário -- não têm mais um lugar próprio na casca.

- Seletor de idioma único (`web/src/i18n.tsx`, pt/en/es) cobre a casca do app e o planejador, que
  já tinha suas próprias traduções nas 3 línguas antes da integração — não muda a regra do topo
  deste arquivo para o conteúdo gerado pela IA nem para os formulários de domínio do Executar
  PoC/RFI, que continuam só em pt-BR.
- **Importar documento do cliente → ligar à execução real**: no painel inicial do planejador,
  além de "Novo Projeto" (preenchimento manual) há "Importar documento do cliente"
  (PDF/XLSX/CSV/JSON). Chama `POST /api/pocs/importar-planejador`, que já cria a `Poc` no
  backend e dispara a extração normal de itens **mais** uma extração adicional
  (`extrair_projeto_planejador` em `api/app/gemini.py`, schema `ExtracaoProjetoPlanejador`)
  tentando pré-popular projeto, produtos e rede do assistente — nunca infra/portas/arquitetura
  (campos que um documento de escopo quase nunca define com precisão) e nunca credenciais. O
  resultado fica em `Poc.parametros_tecnicos["hidratacao_planejador"]` (JSONB, sem migração), e o
  planejador grava o `id` da Poc criada em `state.pocControlId` — campo que **tem que estar
  dentro** de `defaultState()` (não só atribuído em memória), porque `deepMerge()` só preserva
  chaves que já existem no default; qualquer chave fora disso é descartada a cada
  reload/switch/import de projeto.
- No Início do planejador e na etapa Resumo (`executionBlockHtml`, mesma função nos dois
  lugares): se `pocControlId` existe, um botão abre `/pocs/{id}` com `target="_top"` — navega a
  janela de cima (o shell do poc-control), não abre aba nova nem tenta carregar a SPA inteira
  dentro do próprio iframe do planejador — (a tela de execução real — semáforo, vínculo a
  procedimento, Andamento, Apresentação, roteiro do dia — tudo inalterado); se não existe (projeto
  feito do zero), um botão "Habilitar execução desta PoC" cria esse vínculo quando o usuário
  quiser.
- A aba "Testes" própria do assistente (local, status `pending/scheduled/running/pass/
  partial/fail/na`) e a execução real no backend **não são sincronizadas** — são dois mundos
  independentes, decisão deliberada: sincronizar de verdade só funcionaria dentro do mesmo
  navegador, e falsearia o aviso de privacidade do assistente de que "nunca é enviado a nenhum
  servidor".
- **Sem header duplicada quando embutido**: o planejador tem a própria `<header>` (marca+versão,
  "salvo às", seletor PT/EN/ES, exportar, tema), feita pra uso standalone (`/planner/` direto).
  Dentro do iframe do poc-control ela ficava redundante com a topbar do shell (que já tem
  marca+home, idioma e tema) — `renderHeader()` (`poc-planner/index.html`) a suprime quando
  `EMBEDDED_NO_SHELL_THEME` (`window.self !== window.top`, mesma flag que já escondia o botão de
  tema duplicado) é verdadeiro. O que só existia ali (salvo-às, exportar) migrou pra
  `renderEmbeddedToolbar()`, uma faixa fina acima do `renderWizardNav()` -- só nas etapas do
  wizard, mesmo escopo de `renderFooterBar()` (a tela inicial do planejador ainda não tem um
  projeto "aberto" pra exportar). `exportMenuHtml()` ganhou um parâmetro de classe pro botão
  (`btn-outline` ali, em vez do `btn-ghost` branco-sobre-escuro da header, que ficaria ilegível no
  fundo claro do `.container`). Em uso standalone nada muda.

## Tema (claro/escuro) e rodapé de build

- Alternância clara/escura: botão no topbar (`web/src/pages/Layout.tsx`), ao lado do seletor de
  idioma. Escreve o atributo `data-theme` na `<html>` e persiste na mesma chave de localStorage
  que o `poc-planner/index.html` já lê sozinho no carregamento (`suse_poc_planner_theme`). Como o
  planejador agora roda num `<iframe>` (documento separado), a chave compartilhada não basta pra
  sincronizar ao vivo: `Layout.tsx` também dispara um evento `window` (`poc-control:theme-changed`)
  a cada troca, e `PlanPoc.tsx` escuta esse evento pra recarregar o iframe (o planejador persiste
  tudo em localStorage continuamente, então recarregar não perde nada em andamento). CSS escuro:
  bloco `:root[data-theme="dark"]` em `web/src/styles.css`; o CSS escuro do planejador em si mora
  só em `poc-planner/index.html`.
- Rodapé (canto inferior esquerdo, em toda tela): versão (`package.json`) + data/hora exata do
  build, injetadas em build-time via `define` no `vite.config.ts` — não em runtime no navegador
  — pra dar pra confirmar visualmente se um deploy pegou.

## Publicação no Docker Hub

- Imagens públicas em `gabriellins/poc-control`, duas tags (`:api`, `:web`) — um repositório com
  duas tags, não dois repositórios (plano free do Docker Hub costuma limitar repositórios
  privados, não tags; aqui está tudo público, mas a convenção ficou). **ARM64 apenas** — build
  direto na Raspberry, sem manifesto multi-plataforma.
- Tutorial completo (como rodar só com as imagens publicadas, sem clonar/buildar nada — inclui
  como gerar `ADMIN_PASSWORD_HASH` a partir da própria imagem já puxada, e o aviso do `$` do hash
  argon2 sendo corrompido pelo `docker compose`) em `DOCKER.md`, na raiz do repositório. Mantenha
  os dois em sincronia se o processo de setup mudar.
- Scan de vulnerabilidade: pacotes do Alpine (`web/Dockerfile`, bases `node:20-alpine`/
  `nginx:alpine`) podem precisar de pin manual quando o scanner do Docker Hub reporta um CVE já
  corrigido no índice do Alpine — `RUN apk add --no-cache <pacote>=<versão-r*>` na stage final
  (ex.: fix do curl pra `8.23.0-r0`, CVE-2026-92392). `api/Dockerfile` é `python:3.12-slim`
  (Debian/`apt`, não Alpine/`apk`) — mesmo princípio, sintaxe de pin diferente.

## Regras para o agente

- Testar cada marco na Raspberry (`ssh rasp`) antes de seguir para o próximo.
- Nunca commitar `.env`, chaves, PDFs ou HTMLs de cliente com dados reais. Manter `seed/` e `uploads/` no `.gitignore`, salvo os procedimentos já sanitizados.
- Antes de rodar Postgres na Raspberry, confirmar que o volume está em SSD, não em cartão SD.
- Documento de descrição do projeto (público, em inglês, com diagramas Mermaid) no Google Docs:
  https://docs.google.com/document/d/1vR_UaGw8Z1hFAKDKsO_CVcB7iVWkSP2NP0lLHqu52bI/edit — depois
  de uma mudança relevante (feature nova, reestruturação, remoção), checar se ele precisa de
  atualização. Não precisa estar sempre em dia, mas não deixar acumular diferença grande o
  suficiente pra ele parar de refletir a realidade do projeto.
- Imagens no Docker Hub (`gabriellins/poc-control:api`/`:web`, ver "Publicação no Docker Hub"
  acima): mesma lógica — não precisam estar sempre atualizadas, mas quando o código já divergiu
  bastante do que está publicado (feature grande nova, correção de segurança), rebuildar e subir
  pra lá. Na prática, pelo menos 1x por dia em dia de trabalho ativo no projeto; sem rigidez
  nenhuma se não houver mudança real pra publicar.
- Sempre que houver uma atualização relevante no projeto — nova versão publicada, merge na
  `main`, PR concluído/mesclado, deploy na Raspberry — mandar uma mensagem formatada avisando no
  canal do Slack https://suse.slack.com/archives/C06UC7LAFHU, com um resumo das mudanças e o
  status do deploy quando houver um.

## Planejador servido em `/planner/`, e também na rota `/`

O app serve o `index.html` do SUSE PoC Planner (projeto irmão `../poc-planner/` neste mesmo
monorepo) em `/planner/`, copiado **sem alteração** pelo `web/Dockerfile` em build time (não é
mais um script de vendorização separado: como é o mesmo repositório agora, o Dockerfile só faz
`COPY ../poc-planner/index.html ./public/planner/index.html` antes do build do Vite -- sempre
reflete o que estiver na branch). A rota `/` (tela inicial autenticada) é a `Layout` normal do
app com um `<iframe src="/planner/?lang=...">` (`web/src/features/planejar-poc/pages/PlanPoc.tsx`);
`/planner/` sozinho também funciona direto (sem login do app -- usado por `demo/local-stack.sh`
do planejador, por exemplo). As regras do nginx pra `/planner` e `/planner/` ficam em
`web/nginx.conf` (sem elas o fallback da SPA engole essas URLs).

Por estar na mesma origem do `/api`, essa cópia usa o cookie de sessão e liga o **conector** quando
`GET /api/planner/capabilities` responde (rota sem login, em `api/app/planner/`). O conector só envia algo ao
servidor quando a pessoa aciona: `POST /api/planner/hydrate` (importar documento, com tela de revisão no
planejador), `POST /api/planner/feasibility` (aderência por pesquisa na web, sempre marcada como externa e não
confirmada), a leitura de `/api/procedimentos` (importar procedimentos pra biblioteca local) e o
`/api/pocs/importar-planejador` (habilitar/abrir a execução, com o plano **sem** credenciais). Os endpoints
`/api/planner/*` não gravam nada no banco. Testes: `cd api && python -m pytest tests`.

Contexto e contratos: `poc-planner/docs/design-unification.md` e as ADRs em `poc-planner/docs/adr/` (no repo do
planejador). A ADR 2 trata de credenciais.

## Itens vindos do planejador e histórico de resultados (`resultados_catalogo`)

Quando o JSON recebido em `/api/pocs/importar-planejador` traz a lista plana `tests` (o planejador vendorizado em
`/planner/` manda; ver `app/pocs/planner_import.py::itens_do_planejador`), `processar_extracao` cria os itens **direto**,
sem Gemini: título e resultado esperado já vêm resolvidos, e cada item guarda `catalogo_id` (id do teste no catálogo do
planejador), `planner_id`, `resultado` (pending/scheduled/running/pass/partial/fail/na, que é *se o teste passou*; o
`status` continua sendo o estado do fluxo), `prioridade`, `aderencia` e `aderencia_origem`. JSON sem `tests` (o motor
portado, PDFs, planilhas) segue o fluxo de extração com Gemini de sempre.

`resultados_catalogo` é o histórico **anônimo** por teste do catálogo: uma linha por (PoC, teste) com resultado
terminal (pass/partial/fail), sem cliente, título, dono nem texto livre, e **sem cascata** (`poc_id` vira nulo quando a PoC
é excluída). `sucesso` = `resultado = pass` e nenhuma transição do item para `bloqueado`. É mantido por
`app/pocs/resultados.py::sincronizar_resultado_catalogo` (na criação e em `PATCH /itens/{id}` quando `resultado`,
`aderencia` ou `status` mudam) e lido por `GET /api/planner/history?ids=...` (quantas execuções, quantas sem problemas e a
aderência mais nativa entre as com sucesso; só sugestão). Decisões: `poc-planner/docs/adr/ADR-0001-poc-record.md`
(repo do planejador). Migração `0016` só acrescenta e é reversível. Testes: `cd api && python -m pytest tests`
(`tests/test_resultados_db.py` precisa de Postgres e roda dentro do container da api).

## Recuperação de extrações interrompidas (ADR 7)

A extração de itens (PoC) e de requisitos (RFI) roda em `BackgroundTasks`, dentro do processo da api; se o contêiner
reinicia no meio, a tarefa morre e a linha ficava `extraindo` para sempre (e o "Tentar de novo", `reextrair`, só aceita
`erro`). Agora `app/main.py` (lifespan) chama `app/recuperacao.py::recuperar_extracoes_interrompidas` na inicialização:
**toda** linha ainda `extraindo` vira `erro` com a mensagem "interrompida por um reinício do servidor", registrada em log,
e o botão de nova tentativa volta a funcionar. Pressupõe **um worker** do uvicorn (o compose sobe um): com mais de um, a
varredura derrubaria tarefas vivas do outro, então desligue com `EXTRACAO_RECUPERAR_NO_INICIO=false`. Uma falha na
varredura nunca impede a api de subir. `POST /api/rfis/{id}/reextrair` (ver "RFI" acima) é o "tentar de novo" do lado
RFI, equivalente ao `reextrair_poc` que a PoC já tinha. Limite conhecido: uma tarefa travada **sem** reinício (por
exemplo uma chamada ao Gemini que não volta) continua `extraindo` até o próximo reinício (não há data de início da
tarefa para decidir por idade). Testes: `tests/test_recuperacao_db.py` (Postgres, dentro do container da api).

## Propriedade e exclusão permanente (PoC, RFI e Procedimento)

Regras da ADR 4 (`poc-planner/docs/adr/ADR-0004-ownership-deletion.md`, repo do planejador), implementadas em
`app/exclusao.py` e, no front, no componente compartilhado `web/src/components/DangerZone.tsx` (usado em
`PocDetail.tsx`, `RfiDetail.tsx` e `ProcedimentoView.tsx` — é o único lugar da UI que chama esses endpoints; as
listagens (`Pocs.tsx`, `Rfis.tsx`, `Procedimentos.tsx`) só mostram a coluna "Dono"):

- **O dono é `responsavel_id`** (`criado_por_id` é só fato de auditoria), em `pocs`, `procedimentos` e `rfis`. Quem cria vira
  o dono. As PoCs e procedimentos anteriores à migração `0017` ficam **sem dono**; as RFIs começam com o criador como dono.
  Todo usuário logado continua vendo tudo.
- **Só o dono exclui**: `DELETE /api/pocs/{id}`, `DELETE /api/rfis/{id}` e `DELETE /api/procedimentos/{id}` com corpo
  `{"confirmar": "<título>"}`. Nem o administrador exclui a linha de outra pessoa (403); linha sem dono também dá 403
  ("assuma antes"); título errado dá 400. `GET .../{id}/exclusao` mostra o que seria removido e o que permanece/perde o
  vínculo, pra tela de confirmação.
- **Dono**: `PUT .../responsavel` com `{"responsavel_id"}`: o dono atual transfere; qualquer engenheiro assume uma linha
  sem dono (só pra si); o administrador reatribui (mas não exclui). O front resolve o e-mail digitado na transferência via
  `GET /api/auth/usuarios/lookup?email=` (qualquer usuário logado, não só admin — `/api/users` é admin-only).
- **O que a exclusão faz**: uma transação grava a linha de auditoria em `exclusoes` (tipo, quem, quando, **título**,
  contagens; sem cliente nem conteúdo) e remove as linhas (cascata); PoC/RFI só depois removem `uploads/pocs/<id>/` ou
  `uploads/rfis/<id>/` (pasta montada a partir do id, nunca de um caminho do banco) -- Procedimento não tem pasta (o HTML
  mora no banco, `pasta_do("procedimento", ...)` devolve `None`). Falha ao apagar arquivo vai pro log e não desfaz a
  exclusão; `python scripts/limpar_orfaos.py [--apagar]` (no container da api) acha as sobras.
- **Excluir um Procedimento** nunca quebra quem o citava: `Classificacao.procedimento_id`, `Anexo.procedimento_id` e
  `RfiItem.procedimento_id` são `ON DELETE SET NULL` -- a PoC/RFI continua existindo, só perde o vínculo (mostrado na
  prévia como `vinculosQuePerdemProcedimento`).
- **Sobrevivem**: o histórico anônimo `resultados_catalogo` (com `poc_id` nulo) e os procedimentos promovidos a partir dos
  anexos da PoC (ficam para reutilização, a não ser que o próprio procedimento seja excluído depois). Sem lixeira nem
  exclusão lógica; os dumps de backup guardam os dados por até 14 dias, e o que já foi enviado ao Gemini não volta. Testes:
  `tests/test_exclusao_db.py` (Postgres, no container da api).
