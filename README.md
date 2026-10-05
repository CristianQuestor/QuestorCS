# CS Questor — cancelamentos x atendimentos

Cruza a matriz de cancelamentos com o histórico de suporte do Chatwoot e gera um
dashboard local em arquivo único.

Abra **`dashboard/index.html`** com dois cliques. Não precisa de servidor.

---

## Três coisas para saber antes de usar qualquer número

**1. O Chatwoot entrou em produção em 05/05/2026.** Existe registro desde 25 de
fevereiro, mas era piloto: 3 chamados em fevereiro, 52 em março, 784 em abril. Em
05/05 o volume salta de cerca de 60 para 634 por dia e se estabiliza. A data não
está fixada no código, é calculada pela rampa de volume.

O efeito é duro: **42 dos 58 cancelamentos aconteceram antes disso** e não têm
histórico possível. A leitura de churn vale para 16 clientes.

**2. A extração pela API estava truncada.** O endpoint de conversas por contato
devolve no máximo 20 registros. Todo cliente com mais de 20 chamados vinha
cortado, e são justamente os que mais acionam o suporte. A versão anterior deste
projeto tinha 1.365 conversas onde existem 1.762.

**3. A tela de Atenção não prevê cancelamento.** Foi testada e não separa. Está
explicado mais abaixo.

---

## Origem dos dados

O projeto lê de uma restauração local do banco do Chatwoot, não da API.

| Item | Quantidade |
|---|---|
| Conversas da conta 3 | 78.302 |
| Mensagens | 4.422.250 |
| Respostas de CSAT | 39.281, sendo 14.545 com comentário escrito |
| Empresas | 5.529 |

O dump é de 09/09/2026. Para o intervalo a partir dessa data a API continua sendo
o caminho, e a sincronização incremental ainda não está feita.

### Restaurar o banco

O dump está em `bd_atendimento/`, no formato custom do PostgreSQL, apesar da
extensão `.sql`. Precisa de `pg_restore`.

```bash
B="/c/Program Files/PostgreSQL/17/bin"
D=bd_atendimento/dump09-09-qdesk_suporte-202609091651.sql
"$B/createdb"    -U postgres -h localhost questor_cs
"$B/pg_restore"  -U postgres -h localhost -d questor_cs --schema-only --no-owner --no-privileges "$D"
"$B/pg_restore"  -U postgres -h localhost -d questor_cs --data-only --no-owner --disable-triggers \
   -t conversations -t messages -t contacts -t companies -t group_companies \
   -t services -t csat_survey_responses -t tags -t taggings -t inboxes \
   -t contact_inboxes -t teams -t users -t account_users -t accounts "$D"
```

A restauração do esquema acusa 31 erros da extensão `vector`, usada por recursos
de IA do Chatwoot. Nenhum deles afeta as tabelas usadas aqui.

Credenciais em `.env`, que está no `.gitignore`.

---

## Como rodar

```bash
python src/analisar_base.py   # roda o léxico sobre a base e grava no banco
python src/atualizar.py       # calcula as métricas e gera o dashboard
```

O primeiro só precisa rodar quando o léxico muda. Ele carimba cada conversa com a
versão do léxico e reprocessa apenas o que ficou velho. A base inteira leva pouco
mais de um minuto.

Para trocar a lista de empresas, cole o CSV em `entrada/`. Separador `;`, com as
colunas `Cliente`, `CNPJ / CPF`, `Data do cancelamento`, `Motivo (tag)`,
`Relato registrado` e `MRR impactado`.

---

## Estrutura

```
bd_atendimento/     o dump do PostgreSQL
entrada/            o CSV de cancelamentos
dados/
  dashboard.json    agregado que alimenta a página
dashboard/
  index.html        o dashboard, com os dados embutidos
src/
  banco.py          conexão e consultas ao PostgreSQL
  fonte.py          origem dos dados, nas formas que a análise consome
  analisar_base.py  roda o léxico sobre a base e grava o resultado
  cancelamentos.py  leitura e normalização do CSV
  atrito.py         o léxico de temas e a validação contra o CSAT
  sintese.py        comparação entre grupos e teste de significância
  confronto.py      compara relato com chamados e nomeia o padrão
  atencao.py        a tela de Atenção e sua calibração
  metricas.py       janelas temporais, cobertura e sinais de risco
  modelo.html       modelo da página
  painel.py         embute os dados no modelo
  atualizar.py      roda tudo
  chatwoot.py       cliente da API, para o delta a partir de 09/09
```

Os módulos que falam com a API (`extrair.py`, `varredura.py`, `mensagens.py`,
`controle.py`, `risco.py`) continuam funcionando, mas não são mais o caminho
principal. O `README-api.md` descreve aquele desenho.

---

## O que o dashboard mostra

**Visão geral.** Cancelamentos e MRR por mês, motivo declarado, tier e ambiente.
Quantidade e MRR ficam em gráficos separados: são escalas diferentes, e juntá-las
em um eixo só sugeriria uma relação que o dado não sustenta.

**Suporte antes da saída.** Só a coorte analisável, com a linha do tempo de
chamados por bloco de 30 dias. Onde a base não cobre, a barra aparece hachurada.

**Atrito e sentimento.** O que o cliente escreveu, comparado com um grupo de
controle e submetido a teste estatístico.

**Relato x chamados.** Cliente a cliente, o motivo escrito na matriz ao lado dos
temas dos chamados, com os fatos do histórico e a regra que teria pegado o caso.

**Atenção.** Clientes ativos ordenados por quanto a lentidão pesa no atendimento
deles, com a calibração à vista.

---

## Análise de atrito

O léxico tem onze temas, cada um uma lista de expressões em português, em
`src/atrito.py`. É lexical de propósito: toda contagem aponta para a frase de
origem e o link do chamado, e o time pode conferir e corrigir a lista.

Três salvaguardas separam isso de um número sem lastro.

**Grupo de controle completo.** 1.313 empresas que não cancelaram, 65.178
conversas, na mesma faixa de datas. Não é amostra. Sem isso, "63% dos chamados
mencionam erro" não significa nada: todo chamado de suporte é, por definição,
alguém que não conseguiu fazer algo.

**Teste de duas proporções**, com checagem de validade. Contagem esperada abaixo
de 5 de algum dos lados invalida o teste em vez de produzir um p-valor bonito.

**Validação contra o CSAT.** Os chamados que o léxico marca com atrito alto têm
mais notas 1 e 2 que os de atrito baixo.

### O que o dado diz

**Lentidão e travamento é o único tema que separa quem saiu de quem ficou:**
11,5% contra 7,8%, com p = 0,0054.

Nenhum outro resiste. Erro e falha aparece em 63% dos chamados, quase igual nos
dois grupos: é a taxa de fundo do suporte.

**Dificuldade de uso aparece menos em quem saiu.** Isso importa porque a coluna
`Motivo (tag)` do CSV classifica 46 dos 58 cancelamentos como "Problema de
Usabilidade". Os chamados não sustentam essa leitura, e o relato escrito à mão
também não: nele lentidão e erro empatam no topo.

**Ninguém avisa que vai sair.** Menção a cancelar contrato aparece em 0,6% dos
chamados dos dois grupos, e o CSAT médio de quem cancelou é 4,9.

---

## Relato x chamados

Para cada cancelamento, o motivo escrito na matriz é comparado com os temas dos
chamados anteriores à saída, e o módulo apura o que foi feito do sinal.

A regra mais importante está em `src/confronto.py`: **o tema dominante nunca é o
mais frequente**. Só conta como sinal o tema que passou no teste.

Dos 16 cancelamentos analisáveis, 4 repetiram chamados de lentidão sem que
nenhum virasse caso interno. O mais claro é a Contábil São Paulo, com 7 chamados
em 43 dias, cujo relato diz "está cancelando por conta da lentidão" e cujos
chamados dizem "mas está ficando travado no questor".

Escalonamento é raro em toda a base: cerca de 1,5% dos chamados levam etiqueta de
verificação interna ou transferência.

---

## Tela de Atenção, e por que ela mudou de propósito

Ela nasceu para prever cancelamento. Foi calibrada e não prevê.

| Regra | Cancelaram | Ficaram | Lift |
|---|---|---|---|
| 3 ou mais chamados de lentidão | 36% | 35,7% | 1,02 |
| 5 ou mais | 18% | 24,2% | 0,75 |
| 8 ou mais | 9% | 15,0% | 0,61 |
| lentidão em 20% ou mais dos chamados | 27% | 6,9% | 3,96 |
| lentidão em 30% ou mais | 0% | 2,4% | 0 |

Nenhuma das cinco resiste ao teste. A de lift 3,96 se apoia em 3 clientes entre
11, e foi escolhida depois de olhar cinco regras: é exatamente assim que se
encontra padrão onde não há.

O motivo de fundo é que **lentidão não é marca de cliente em risco, é um problema
da base inteira**. Mais de um terço dos clientes ativos reclama disso. Com 11
cancelamentos analisáveis não há como calibrar um limiar por cliente.

Então a tela ordena os clientes por quanto a lentidão ocupa o atendimento deles,
o que continua sendo trabalho útil de CS e de produto, sem vender uma previsão
que o dado não sustenta. A calibração fica na própria tela para ninguém
reaproveitar a regra achando que ela prediz.

Hoje são 12 clientes com lentidão em 20% ou mais dos chamados, 275 entre 10% e
20%, e 822 com queixa pontual ou ausente, sobre 1.283 clientes ativos.

---

## O que ainda não está aqui

- **Sincronização incremental pela API**, para cobrir de 09/09 até hoje. O cursor
  natural existe: a listagem de conversas vem ordenada por última atividade.
- **Os comentários de CSAT ainda não entraram na análise.** São 14.545 textos em
  que o cliente explica a nota, 906 deles em notas 1 e 2. É a melhor fonte de
  sentimento desta base e está apenas acessível, não usada.
- **ENOEMI CRODA SFOGGIA** está sem CNPJ no CSV e é o único registro não casado.
- **A coorte analisável cresce sozinha.** Cada mês adiciona cancelamentos com
  histórico completo, e a calibração da tela de Atenção pode passar a ser
  possível.

---

## Credenciais e privacidade

`.env` guarda o token do Chatwoot e a senha do PostgreSQL local, e está no
`.gitignore`. O token circulou em texto puro durante a montagem do projeto e vale
rotacioná-lo.

O dump é uma cópia de produção com dados de clientes reais, e o dashboard contém
CNPJ, MRR e motivo de saída de cliente nomeado. Tudo roda local. Publicar em
endereço acessível de fora é uma decisão que precisa ser tomada de propósito.
