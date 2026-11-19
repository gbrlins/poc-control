# POC Control

> **Nota (2026-11-15):** a casa definitiva deste código agora é `https://gitlab.suse.de/sa/poc-control`
> (importado de `gbrlins`; `origin` é `gitlab@gitlab.suse.de:sa/poc-control.git` -- o usuário SSH é `gitlab`, não
> `git`). **Decisão de 2026-11-18: o GitLab é a única casa; as regras da casa antiga -- repositório GitHub `suse-poc-toolkit`
> (e `gbrlins/poc-control`), imagens no Docker Hub `gabriellins/poc-control` e aviso no Slack -- não valem mais** (tudo foi
> incorporado ao GitLab). Os textos abaixo sobre elas ficam só como histórico.
> As mudanças da revisão do Sales Kickoff estão na seção "Revisão do Sales Kickoff (2026-11-13)" mais abaixo.

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

Dono: Gabriel (Solutions Architect, SUSE). Uso mundial: o idioma **padrão é inglês**, com **pt-BR** e **espanhol** como idiomas
completos (seletor PT/EN/ES na casca e no planejador, mais alternância de tema claro/escuro; ver "Tema (claro/escuro) e rodapé de
build" e "O planejador como tela inicial" abaixo). Regras de idioma (decisão de 2026-11-18, que substitui a antiga "tudo em pt-BR"):

- **Quem olha**: sem escolha guardada, o idioma é o do navegador (pt, es ou en; qualquer outro, inglês). Na API, sem `X-UI-Lang`
  nem `?lang=`, o padrão é inglês (`api/app/idioma.py::IDIOMA_PADRAO`). `?lang=orig` / `X-UI-Lang: orig` pede "como está gravado, sem
  traduzir".
- **Texto gravado**: cada campo de texto escrito pela IA ou por uma pessoa guarda o **idioma em que foi escrito** (`idiomas`, JSONB
  por campo; nulo = pt, porque todo texto anterior à marca era pt-BR -- `IDIOMA_LEGADO`). A IA escreve no idioma da tela de quem acionou.
- **Exibição**: quem lê em outro idioma vê a tradução sob demanda, com cache e hash do original (`api/app/traducao_cache.py`); o banco
  nunca recebe a tradução. Vale para telas e para relatórios. Ver "Idioma do texto da IA e dos itens" mais abaixo.
- **Mensagens do sistema**: o backend emite **inglês**; o front as mostra no idioma da tela (`web/src/mensagensServidor.ts`, que também
  reconhece o pt-BR já gravado).
- O **Procedimento** segue o mesmo princípio desde antes: HTML com `idioma_original` e tradução sob demanda (ver "Tradução de exibição").

## Rotas da interface (nomes em inglês, 2026-11-18)

As rotas de página são em inglês, vindas da branch `v2` do Gabriel (item 2.2 da especificação): `/plan`,
`/procedures` (`/new`, `/import-json`, `/:id`), `/pocs/new`, `/rfis/new`, `/tenders`, `/users`, `/my-account`.
Os caminhos antigos em português (`/planejar`, `/procedimentos`, `/pocs/novo`, `/rfis/novo`, `/licitacoes`,
`/usuarios`, `/minha-conta`) continuam funcionando como redirecionamentos (`web/src/App.tsx`), pra links
e favoritos já distribuídos. Só as rotas de página mudaram: os endpoints `/api/...` e os nomes de arquivo/
componente continuam em português. Mais abaixo, onde o texto ainda cita um caminho em português de uma
página, vale o nome em inglês desta seção.

## Repositório e ambiente

- Git: `https://gitlab.suse.de/sa/poc-control` é a única casa deste código (os repositórios do GitHub, `FlavioFGM/suse-poc-toolkit` e `gbrlins/poc-control`, não são mais usados; `docs/sincronizar-gbrlins-poc-control.md` descreve como a `v2` do Gabriel foi trazida e fica como histórico).
- Servidor: Raspberry Pi na rede local, acessado por SSH com o alias `rasp` (chave em `~/.ssh/rasp`, ver `~/.ssh/config`). **Nunca** usar senha nem gravar credenciais em arquivos do repositório.
- Exposição externa: `cloudflared` já instalado na Raspberry. Publicar só o serviço `web`. Recomendado proteger com Cloudflare Access além do login do app.
- Tudo roda com `docker compose`, construído a partir do código (`docker compose up -d --build`). Os `Dockerfile` não têm nada específico de arquitetura e as imagens-base (`python:3.12-slim`, `pgvector/pgvector:pg16`, `node`/`nginx` alpine) são multi-arquitetura: roda em **arm64** (a Raspberry e os Macs com Apple Silicon dos SAs) e em **amd64** (testado em x86 em 2026-11-18; arm64 não foi testado nesta rodada). O "ARM64 apenas" que aparece mais abaixo era só das imagens que se publicavam no Docker Hub, hoje aposentadas.

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
- `docs/diagrams/` — diagramas draw.io do processo de PoC → execução (`poc-to-execution.drawio`) e da análise de RFI
  (`rfi-analysis.drawio`), com uma página de visão geral e uma sequência por fase; o `README.md` de lá diz onde olhar no código
  quando um fluxo mudar.
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

**Rascunho guiado por IA pra item amarelo sem procedimento (2026-11-13):** quando um item de PoC
cai em 🟡 amarelo e nenhum procedimento validado confirma (`Classificacao.procedimento_id is
None`), o usuário pode clicar em "Gerar rascunho guiado com IA" (botão manual, não automático --
pesquisa + geração + chunking/embedding + tradução pode passar de 1 minuto). O Gemini pesquisa com
grounding (documentação da versão estável mais recente + procedimentos/tutoriais já publicados,
`pesquisar_implementacao_item`) e depois redige o HTML estruturado (`gerar_procedimento_guiado`,
mesma convenção de h2/h3 + "Esperado:" por passo + "Se der erro" + "Limpeza" + "Evidências para o
relatório" dos procedimentos validados), moldado ao contexto da PoC (cliente/escopo/parâmetros
técnicos). Cria um `Procedimento` de verdade via `_criar_procedimento` (reaproveita chunking/
embedding/tradução), mas com `status=rascunho` e `gerado_por_ia=True` -- fica **invisível** pra
busca de outros itens (`_buscar_candidatos` só olha `status=validado`) até o próprio usuário
confirmar que executou com sucesso de ponta a ponta e clicar em "Marcar como validado"
(`POST /api/procedimentos/{id}/validar`, genérico -- também serve pra promover um rascunho manual
antigo que nunca tinha como ser validado depois da criação). A IA nunca se autoconfirma; o usuário
julga. `Classificacao.procedimento_rascunho_id` é o vínculo com esse rascunho, distinto de
`procedimento_id` (reservado a match já validado). Escopo desta rodada: só PoC, não RFI (extensão
futura natural, mesmo mecanismo serviria pra `RfiItem`/`avaliar_item_rfi`). Migração `0028`.

**Mesmo rascunho guiado, agora dentro do planejador (2026-11-12):** o planejador (`poc-planner/`)
tem seu próprio catálogo de testes e sua própria biblioteca de procedimentos (local, no navegador),
sem Item nem Classificacao de PoC -- o teste só ganha um Item de verdade se/quando o plano for
"habilitado" como execução (ver "Importar documento do cliente" acima). Na tela de vincular
procedimento a um teste (`procPickerHtml` em `poc-planner/index.html`), um botão "Gerar rascunho
guiado com IA" (só quando `connectorHas('draft')`, ou seja, servido por este backend) chama
`POST /api/planner/procedure-draft` com título/resultado esperado do teste (no idioma da tela, campo `lang` do corpo; antes era sempre em português,
mesma regra de idioma do conteúdo gerado por IA) e cliente/escopo do projeto. O backend reaproveita
o mesmo par de chamadas Gemini de `gerar_rascunho_procedimento` (`app/planner/service.py::gerar_rascunho_planner`)
e cria um `Procedimento` de verdade (`status=rascunho`, `gerado_por_ia=True`,
`origem_conhecimento=planejador` -- valor novo do enum, migração `0029`, já que não existe Item
nem RFI por trás). A resposta tem a mesma forma de uma linha+detalhe de `GET /api/procedimentos`, então
o planejador a importa pra biblioteca local e já vincula ao teste pelos MESMOS conversores que usa
pra importar um procedimento do servidor (`serverProcClean`/`serverProcToLib`), sem parser novo.
Continua `rascunho` (invisível pra `_buscar_candidatos`) até alguém confirmar a execução e validar
pela tela de Procedimentos do lado de cá -- a IA nunca se autoconfirma, mesma regra do lado PoC.

**Exibição no idioma da tela, não no idioma em que foi escrito:** o planejador guarda na biblioteca
local só `html_original` (o que o servidor manda, nunca pré-traduzido) e um `langOriginal` novo
(idioma desse HTML -- o rascunho acima sai no idioma da tela no momento do clique).
Decisão: reaproveitar a tradução sob demanda que `GET /api/procedimentos/{id}?lang=` já faz (ver
"Tradução de exibição" em Procedimentos, com cache permanente por procedimento em
`Procedimento.traducoes`) em vez de gerar as três línguas de uma vez na criação -- mais barato (a
maioria dos procedimentos nunca é aberta nos três idiomas) e sem duplicar o mecanismo de tradução já
existente. `procDisplayHtml` (`poc-planner/index.html`) busca a tradução só quando `state.lang` diverge
de `langOriginal`, guarda o resultado num cache local (`localStorage`, chave
`suse_poc_planner_proc_tr_v1`) e mostra o original enquanto isso -- nunca trava a tela, mesmo
princípio do backend se a tradução falhar. Só vale pra procedimento do servidor (`id` começando com
`srv-`); um procedimento só local (sem UUID de backend) não tem como ser traduzido por aqui.

**Título, só um fallback fixo em inglês, nunca sob demanda (2026-11-12):** diferente do corpo, o
`titulo` de um procedimento nunca passou pelo mecanismo de tradução -- é só uma coluna de texto,
usada como está em todo o resto do app (match por similaridade, listagens do Executar PoC/RFI, que
são pt-BR only e por isso nunca sentiram essa lacuna). Em vez de dar ao título o mesmo tratamento
sob-demanda-com-cache-por-idioma do corpo (3 idiomas, round-trip, cache local), a saída escolhida foi
mais barata: `Procedimento.titulo_en` é preenchido na MESMA chamada que já traduz `html_original` pro
inglês no upload (`traduzir_procedimento_html` ganhou `titulo_traduzido` na resposta, sem chamada
extra ao Gemini) -- um fallback único, não um valor por idioma. O planejador (`dispTitle` em
`poc-planner/index.html`) mostra `titulo_en` sempre que a tela não estiver em português (inglês
**e** espanhol caem no mesmo fallback em inglês -- não existe título em espanhol, por decisão
deliberada: cosmético não justifica tradução pros 3 idiomas), e cai pro título original se a
tradução eager ainda não rodou ou falhou. Migração `0030`.

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
- **Tradução de exibição (o primeiro caso do princípio de idioma do topo deste arquivo)**: o HTML de um
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
  formulários e os resumos de sessão passaram a seguir o princípio do topo (ver "Idioma do texto da IA e dos itens") -- aqui é a exibição do procedimento que
  acompanha o idioma da casca. Migração `0026`.

- **Importar/exportar por JSON** (v2 do Gabriel; esquema em `docs/procedure-schema.md`): `POST /api/procedimentos/importar-json/preview` e
  `/importar-json`, `GET /api/procedimentos/{id}/exportar-json` e `/exportar-json`. Um duplicado (mesmo `id`, ou mesmo título + categorias
  normalizadas) é **pulado**, a não ser que a pessoa peça para sobrescrevê-lo -- e **só o dono** pode (mesma regra de excluir/transferir,
  ADR 4; procedimento sem dono precisa ser assumido antes), porque sobrescrever troca conteúdo, status e metadados. Sobrescrever refaz o idioma
  e o título em inglês como um upload quando o JSON não os traz.

### Carga inicial (pasta `seed/procedimentos/`)

**Como carregar** (não é automático): `docker compose exec api python scripts/import_seed.py --user <e-mail>` (ver `DOCKER.md`, passo 5). O script usa o mesmo
caminho de um upload (`_criar_procedimento`: idioma, título e tradução em inglês, seções com embedding), faz o usuário do `--user` o dono e usa a chave
do Gemini dele; sem `--user` vale a `GEMINI_API_KEY` do ambiente e ficam sem dono. Pula os que já existem (mesmo título). Teste: `tests/test_import_seed_db.py`.

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
| `db` | PostgreSQL + pgvector (imagem `pgvector/pgvector`, multi-arquitetura), volume persistente |
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
RFI, Procedimentos) de cores diferentes (Planejar PoC abre um projeto novo; Analisador de RFI e Procedimentos abrem a lista, que tem o botão de criar), mais uma lista "mais recentes" compacta por área
(PoCs/RFIs/Procedimentos) abaixo, cada uma linkando pra sua tela cheia com filtros (`/pocs`,
`/rfis`, `/procedures`). O planejador em si vive em `/plan` (o botão "Planejar PoC" do hub
leva lá direto pra um projeto novo, `/plan?new=1`). Não existe um botão de atalho pra "Executar PoC"
no hub: a lista "Projetos e PoCs" (Executar por linha) e o link "ver todas" cobrem o caminho até `/pocs` e
`/pocs/:id` (rotas inalteradas).

Embutido na casca, o planejador **não mostra mais a própria tela inicial** (dashboard): "Novo projeto", "Importar
projeto (JSON)", "Importar documento do cliente", a biblioteca de procedimentos e a lista de projetos moram na Home
(`web/src/pages/HomeProjetos.tsx`). A Home abre o planejador já no ponto certo por parâmetros de uso único em
`/plan` (`web/src/features/planejar-poc/pages/PlanPoc.tsx` os repassa ao iframe só no 1º carregamento; o
planejador os retira do endereço, ver `applyUrlAction` em `poc-planner/index.html`): `?open=<id do projeto local>`,
`?new=1` (reaproveita o projeto em branco, se houver), `?import=project` (texto do JSON deixado pela Home em
`sessionStorage`) | `?import=doc`, `?view=library`. Sem parâmetro, retoma a última etapa. "Voltar ao início" de dentro
do planejador é um `postMessage` (`poc-control:navigate`) que a casca converte em navegação para `/`. Standalone
(`/planner/` direto) o dashboard continua existindo.

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
  PoC/RFI, que seguem as regras de idioma do topo.
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

## Revisão do Sales Kickoff (2026-11-13)

Decisões da reunião "Revisão SUSE toolkit" e das anotações do Erico, implementadas na branch
`feature/planejar-poc/revisao-sk-2026-11` (um commit por tema). O que mudou e onde mora:

- **Terminologia**: na interface em inglês, "client" virou "customer" (pt/es continuam "cliente"; nomes internos como
  `clientOrganization`/`cliente` não mudaram, pra não quebrar importações).
- **Exportação do planejador**: três opções -- relatório para o customer, relatório do SA (checklist de instalação +
  roteiro do dia + folha do operador, com credenciais, impressão `print-sa`) e salvar projeto (JSON, já com a seção `eib`).
  O EIB é só informativo: o `run.sh` lê o JSON salvo; não existe mais a pergunta "EIB?" nem a abordagem `eib` (projetos
  antigos com `eib` caem em `manual`).
- **Home**: lista única "Projetos e PoCs" (planejamento local + execução no servidor, ordenável, com Planejar/Executar/
  Excluir). Tudo que a casca sabe do `localStorage` do planejador passa por **`web/src/features/planejar-poc/plannerStore.ts`**
  (chaves, listagem, exclusão, importação pendente, usuário). O planejador carimba quem gravou e a revisão no índice local
  via `ProjectMeta` (revisão = sessão de edição de 5 min, não gravação). Quando os projetos forem pro banco, só esses dois
  pontos mudam (**fora desta PR**: projetos no banco, "modificado por" real e log de alterações).
- **Passo Testes**: uma aba por produto, "Adicionar teste" no topo, ordenação + contagem, testes padrão (catálogo) separados
  dos adicionais.
- **Resumo como ponto único de controle**: as caixas de firewall (portas e hosts/URLs) e o status de cada teste são editados
  no Resumo; a tela de Portas só lista. O checklist de instalação saiu da linha de progressão e virou a aba **Kickoff**
  (`KICKOFF_VIEW`); o progresso das etapas dele fica nessa aba. Os contadores de pendência da faixa de etapas se atualizam
  enquanto se digita (`refreshNavBadges`).
- **Infraestrutura**: campo de nós do Rancher (`infra.rancher.nodeCount`, padrão 1; o EIB perfil 1 gera a ISO de UM nó) e o
  cartão "Arquitetura resultante" (derivado, só leitura).
- **Idioma de relatórios e mensagens**: os relatórios HTML/XLSX do backend aceitam `?lang=pt|en|es`
  (`api/app/relatorio_i18n.py`; o front passa o idioma atual). Mensagens e erros conhecidos do servidor (em inglês; as antigas em pt-BR, algumas
  gravados no banco) são traduzidos só na exibição por `web/src/mensagensServidor.ts` -- manter em sincronia com as strings
  do backend. O prompt sugerido da aba Andamento tem seletor de idioma próprio.
- **Idioma do texto da IA e dos itens** (2026-11-18): o texto escrito pela IA ou digitado por uma pessoa guarda **o idioma em que foi
  escrito, por campo** (`idiomas`, migração `0034`; ver `api/app/idioma.py`). Por campo e não por linha porque os campos nascem em momentos
  e por mãos diferentes (a IA extrai o item num idioma, a pessoa edita só o título em outro; a categoria do RFI nasce na extração e a
  justificativa na avaliação). A IA escreve no idioma da tela de quem acionou (`lang` roteador -> tarefa -> serviço -> `gemini.py`), e
  um texto digitado à mão recebe o idioma da tela de quem digitou; o modal de edição do item só envia os campos que a pessoa mudou.
  Quem lê em outro idioma vê a **tradução sob demanda, com cache** (`api/app/traducao_cache.py`, `X-UI-Lang`): título, descrição,
  critério e categoria do item (`itens.traducoes`, `0033`), justificativa da classificação, justificativa + categoria do item de RFI --
  **nunca** a `descricao` do RFI (cópia literal do edital) nem as mensagens fixas do sistema (já existem nos 3 idiomas). O cache guarda o
  hash do original: editar ou reavaliar invalida sozinho. Só se traduz um campo cujo idioma de origem difere do de quem olha, então
  texto antigo sem marca (pt) não custa nada para quem lê em pt.
  O texto de **uso único** (resumo da sessão por e-mail, resumo executivo, rascunho guiado de procedimento, PoC e planejador) também
  sai no idioma da tela e, quando é guardado (resumo executivo, pontos da sessão, pré-requisitos), com a marca de idioma.
  Não adotamos o `traducao.py`/`campos_no_idioma` e a migração `0031` da `v2` do Gabriel (cache sem hash, marca por linha).
- **Relatórios traduzidos** (PoC: exportar, apresentação, roteiro do dia; RFI: HTML e XLSX): montados a partir de **visões somente de
  leitura** (`api/app/relatorio_visao.py`) com todo o texto escrito em outro idioma já traduzido (itens, justificativas, categorias,
  pré-requisitos, pontos da sessão, resumo executivo, título do procedimento via `titulo_en`, corpo do procedimento pela tradução em
  cache do próprio procedimento). A tradução **nunca é atribuída à linha do ORM** (o próximo commit a gravaria). Os endpoints de
  relatório resolvem a chave do Gemini de quem exporta. Se o Gemini falhar, o relatório sai com o original, como as telas. Limites
  conhecidos: o título da PoC/RFI e o cliente (digitados) não são traduzidos; o erro técnico dentro de uma mensagem de erro de RFI
  segue como foi gravado; as telas de resumo executivo e pontos da sessão ainda mostram o texto gravado (só os relatórios os traduzem);
  o planejador mostra o `detail` de erro da API como veio (inglês).
- **RFI**: botão de download dos documentos enviados (`GET /api/rfis/{id}/documentos/{doc}/download`, só serve arquivo dentro
  da pasta do RFI) e tabela de fontes citadas (ordenável, com Copiar). As fontes novas guardam a URL real (o redirecionamento
  do grounding é resolvido em `api/app/url_real.py`); RFIs avaliados antes continuam com o link de redirecionamento até
  serem reavaliados.
- **Minha conta**: mostra qual chave do Gemini está em uso (últimos 4 caracteres, `UserOut.gemini_key_final`) e confirma
  salvar/remover.
- **Casos de exemplo** em `seed/poc/` (Hospital Santa Aurora pt/en e o ACME Retail), importáveis pelo planejador.

Verificações do front que rodam sem navegador nem banco (saem com código 1 se algo falhar):
`node --experimental-strip-types web/tests/mensagensServidor.check.mts` (tabela de mensagens do servidor, pt/en/es) e
`node --experimental-strip-types web/tests/version.check.mts` (a versão é a mesma em todos os lugares, ver "Versão"),
`node --experimental-strip-types web/tests/apiPaths.check.mts` (todo caminho `/api/...` chamado pelo front existe no backend -- nasceu de uma
renomeação em massa das rotas de página que reescreveu `/api/procedimentos` por engano).

Como rodar/testar localmente (venv, Postgres descartável, stack do compose): ver o passo a passo em
`docs/` quando existir; por ora, `api/.venv` + `pytest` com as variáveis de ambiente de teste, `npm ci && npm run build`
em `web/` e `docker compose --env-file <arquivo> -p <projeto> up -d --build`.

## Versão

O produto tem **uma versão só**: `"version"` em `web/package.json` (MAJOR.MINOR.PATCH). Ela aparece no rodapé do app (`v2.1.0 · data do build`, injetada pelo
`vite build`) e, repetida pelo script, no cabeçalho do planejador e nos relatórios que ele gera (`APP_VERSION` em `poc-planner/index.html`) e no
`package-lock.json`. Para mudar: `scripts/set-version.sh X.Y.Z`, commit, e uma tag anotada `vX.Y.Z` no commit da versão (`git tag -a vX.Y.Z -m ...`,
publicada no GitLab). `node --experimental-strip-types web/tests/version.check.mts` falha se os lugares divergirem. Histórico: `v1.0.0` = a `main`
antes da revisão do Sales Kickoff, `v2.0.0` = a revisão do Sales Kickoff (MR !1), `v2.1.0` = a sincronização com a `v2` do Gabriel + inglês como idioma
padrão, `v2.1.1` = correções do teste local (importação de procedimentos por arquivo, "Executar" na Home, progresso de envio), `v2.1.2` = carga dos procedimentos de exemplo corrigida (`import_seed.py`), diagramas draw.io do processo e "Analisar RFI" abrindo a lista, `v2.1.3` = importar um projeto por JSON descarta o vínculo com a execução (`pocControlId`), que só vale na instância de origem (o "Executar" do exemplo ACME dava "PoC não encontrada").

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

## Publicação no Docker Hub (aposentada em 2026-11-18)

> Não publicamos mais imagens no Docker Hub nem as mantemos atualizadas: o código vive só no GitLab. O que segue descreve o processo
> antigo e vale como referência se alguém voltar a publicar imagens (`DOCKER.md` idem).

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
- Sem avisos no Slack, imagens no Docker Hub nem atualização obrigatória do documento descritivo no Google Docs: essas regras da casa antiga foram aposentadas (ver a nota no topo).

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
planejador), a leitura de `/api/procedimentos` (importar procedimentos pra biblioteca local) e o
`/api/pocs/importar-planejador` (habilitar/abrir a execução, com o plano **sem** credenciais). Os endpoints
`/api/planner/*` não gravam nada no banco (exceto `procedure-draft`, que cria um rascunho de procedimento). A "Sugerir aderência (pesquisa na
web)" e o endpoint `feasibility` foram **removidos** (decisão do Gabriel na `v2`, item 3.6); a aderência por histórico (`history`) continua, e
um projeto salvo antes ainda mostra a etiqueta `web` das sugestões que já tinha. Testes: `cd api && python -m pytest tests`.

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

**Envio de arquivos na interface (PoC e RFI):** escolher um arquivo **não o envia**; ele só sobe quando a pessoa confirma ("Criar RFI",
"Criar PoC", "Enviar N arquivos" numa PoC/RFI existente). A tela diz isso ("Ainda não enviados..."), mostra uma barra de progresso do envio
(`web/src/components/ProgressoEnvio.tsx`, `api.ts::uploadComProgresso`, que manda o mesmo `X-UI-Lang` de `request()`) terminando em "Envio
concluído — colocando a análise na fila…", e mantém a seleção na memória da página ao sair da tela e voltar (`web/src/rascunhoUpload.ts`; some
ao recarregar, e um aviso do navegador pede confirmação ao recarregar/fechar com arquivos escolhidos). Sair da tela NÃO cancela a análise: ela
roda no servidor; o que a interrompe é reiniciar o contêiner da api (ver acima), então não recrie a api enquanto houver `extraindo`.

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
