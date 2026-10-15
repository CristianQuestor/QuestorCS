# CS Questor — cancelamentos x atendimentos

Cruza a matriz de cancelamentos com o histórico de suporte do Chatwoot (conta 3)
e gera um dashboard local em arquivo único.

Abra **`dashboard/index.html`** com dois cliques. Não precisa de servidor.

---

## Antes de usar o número: o limite da base

A base de atendimentos do Chatwoot **começa em 05/05/2026**. Dos 58 cancelamentos
da matriz de janeiro a agosto, **42 aconteceram antes dessa data** e não têm
histórico possível de atendimento.

Para esses 42, zero chamado significa *não existe o dado*, e não *o cliente não
procurou o suporte*. Tratar os dois casos como a mesma coisa era o erro mais fácil
de cometer aqui, e o dashboard separa os dois explicitamente: a leitura de churn
vale para os **16 clientes** com pelo menos 30 dias de histórico antes da saída.

Esse recorte cresce sozinho a cada mês que passa. Em janeiro de 2027 a coorte
analisável cobre o ano inteiro.

---

## Como rodar

```bash
python src/atualizar.py              # aproveita o cache das chamadas já feitas
python src/atualizar.py --limpar     # descarta o cache e busca tudo de novo
python src/atualizar.py --texto      # também baixa o texto das conversas
python src/atualizar.py --controle   # também remonta o grupo de controle
```

Sem as duas últimas opções, tudo roda em segundos e a aba de atrito usa o texto
que já está em `dados/mensagens.json`.

| Etapa | Primeira vez |
|---|---|
| Casamento e conversas | ~5 min |
| Texto das conversas (`--texto`) | ~14 min |
| Grupo de controle (`--controle`) | ~9 min mais ~6 min de texto |

A extração usa quatro conexões simultâneas contra uma instância de produção, o que
dá menos de três requisições por segundo. Se precisar aliviar mais, baixe
`TRABALHADORES` em `src/mensagens.py`.

### Trocar a lista de empresas

Cole o CSV em **`entrada/`**. O processo escolhe o arquivo mais recente, dando
preferência a quem tem "cancelamento" no nome. O da raiz do projeto continua
valendo como alternativa.

O CSV precisa ter separador `;`, e as colunas `Cliente`, `CNPJ / CPF`,
`Data do cancelamento`, `Motivo (tag)`, `Relato registrado` e `MRR impactado`.

---

## Como as empresas são encontradas

Esta instância do Chatwoot tem um cadastro de empresas que não aparece na
documentação pública da API, em `/api/v1/accounts/3/companies`. Cada empresa traz
o CNPJ em `registration_number`, além do tier e do ambiente.

O casamento é feito **pelo CNPJ**, exato, sem tolerância. Dos 58 registros, 57
casaram. O único que faltou não tem documento preenchido no CSV.

A alternativa seria adivinhar o domínio de e-mail a partir do nome da empresa.
Foi testada e descartada: casava "CASA DO SALPIQUE" com `casagrandecontabil.com.br`
e "MCLARENS DO BRASIL" com `rjsbrasil.com.br`. Se algum dia precisar voltar a esse
caminho, saiba que ele exige revisão manual linha a linha.

Quando um CNPJ não casa, há um segundo caminho pelo nome, que marca o registro
como `casamento_confiavel: false` para revisão. Hoje nenhum registro usa esse
caminho.

---

## Estrutura

```
entrada/              coloque aqui o CSV de entrada
dados/
  empresas.json             resultado do casamento por CNPJ
  conversas.json            metadados das conversas por empresa
  base-conversas.json       varredura da conta inteira
  base-empresas.json        empresas encontradas na varredura
  atencao-alvos.json        conversas que a peneira quer ler
  mensagens.json            texto das conversas, dos dois grupos
  controle-empresas.json    as 114 empresas que não cancelaram
  controle-conversas.json   conversas do grupo de controle
  dashboard.json            agregado que alimenta a página
  cache/                    respostas da API, descartável
dashboard/
  index.html          o dashboard, com os dados embutidos
src/
  chatwoot.py         cliente da API, com retry, cache e limite de requisições
  cancelamentos.py    leitura e normalização do CSV
  extrair.py          casamento e extração
  mensagens.py        texto das conversas, em paralelo e retomável
  varredura.py        varre as 78 mil conversas da conta, agrupadas por empresa
  confronto.py        compara relato com chamados e nomeia o padrão
  risco.py            peneira de metadados e confirmação no texto
  atencao.py          monta a lista de clientes ativos em risco
  controle.py         sorteio do grupo de controle, estratificado por tier
  atrito.py           o léxico de temas e a validação contra o CSAT
  sintese.py          comparação entre grupos e teste de significância
  metricas.py         janelas temporais, cobertura e sinais de risco
  modelo.html         modelo da página
  painel.py           embute os dados no modelo
  atualizar.py        roda tudo
```

---

## O que o dashboard mostra

**Visão geral.** Cancelamentos e MRR por mês, motivo declarado, tier e ambiente.
Quantidade e MRR ficam em gráficos separados de propósito: são escalas diferentes,
e juntá-las em um eixo só sugeriria uma relação que o dado não sustenta.

**Suporte antes da saída.** Só a coorte analisável. A linha do tempo mostra a média
de chamados por cliente em cada bloco de 30 dias antes da saída, dividindo pelo
número de clientes que a base cobre naquele bloco. Onde não há cliente coberto, a
barra aparece hachurada.

**Atrito e sentimento.** O que o cliente escreveu nos chamados, comparado com um
grupo de controle e submetido a teste estatístico. Detalhado mais abaixo.

**Relato x chamados.** Cliente a cliente, o motivo escrito na matriz ao lado dos
temas dos chamados que ele abriu antes de sair, com os fatos do histórico e o que
teria mudado o desfecho.

**Atenção.** Clientes ativos que repetem hoje o padrão de quem cancelou, com o que
fazer em cada caso.

**Clientes.** Todos os 58, com busca, ordenação e filtro por cobertura e tier.
Clicar abre a ficha com o relato do cancelamento, os produtos e assuntos acionados
e a lista de chamados com link direto para a conversa no Chatwoot.

### Sinais de risco

Calculados só para quem tem cobertura suficiente:

| Sinal | Regra |
|---|---|
| Chamados em alta | ritmo dos últimos 90 dias ≥ 1,5x o período anterior |
| CSAT baixo | média abaixo de 3,5 |
| Detratores | duas ou mais notas 1 ou 2 |
| Assunto reincidente | mesmo assunto em 4 ou mais chamados |
| Resposta lenta | primeira resposta acima de 8 horas em média |
| Sem chamado | nenhum chamado, com cobertura suficiente para afirmar isso |
| Fora da janela | cobertura insuficiente, nada a concluir |

---

## Credenciais

Ficam em `.env`, que está no `.gitignore`:

```
CHATWOOT_URL=http://192.168.0.232:3000
CHATWOOT_TOKEN=...
CHATWOOT_ACCOUNT=3
```

O token atual circulou em texto puro durante a montagem do projeto. Vale rotacioná-lo
no Chatwoot quando isso aqui estabilizar.

O dashboard contém CNPJ, MRR e motivo de saída de cliente nomeado. Ele foi feito
para rodar local. Publicar em qualquer endereço acessível de fora é uma decisão
que precisa ser tomada de propósito, não por conveniência.

---

## Análise de atrito e sentimento

A aba **Atrito e sentimento** lê o que o cliente escreveu nos chamados e procura
nove temas de desconforto. São 89.822 mensagens extraídas, 44.135 delas do cliente.

### O método, e por que ele é assim

Cada tema é uma lista de expressões em português, em `src/atrito.py`. É lexical de
propósito: toda contagem aponta para a frase de origem e o link do chamado, e o
time de CS pode conferir e corrigir a lista. Nada depende de um modelo fechado.

Três salvaguardas fazem a diferença entre isso e um número bonito sem lastro.

**Grupo de controle.** 114 empresas que não cancelaram, sorteadas com a mesma
composição de tier de quem saiu e recortadas na mesma faixa de datas. Sem isso,
"63% dos chamados mencionam erro" não significa nada: todo chamado de suporte é,
por definição, alguém que não conseguiu fazer algo.

**Teste estatístico.** Cada tema passa por um teste z de duas proporções. Uma
diferença que caiba no acaso não vira conclusão, por maior que a barra pareça.

**Validação contra o CSAT.** O CSAT é o único sentimento que o próprio cliente
declarou. Os chamados que o léxico marca com atrito alto têm 4,6% de notas 1 ou 2,
contra 2,2% nos de atrito baixo. O léxico acompanha o sentimento declarado.

### O que o dado diz

**Lentidão e travamento é o único tema que separa quem saiu de quem ficou.**
Aparece em 10,8% dos chamados de quem cancelou contra 6,1% de quem ficou, 1,78x
mais, com p = 0,0091.

Nenhum outro tema resiste ao teste. Erro e falha aparece em 63% dos chamados, mas
aparece quase igual nos dois grupos: é a taxa de fundo do suporte, não um sinal de
churn.

**Dificuldade de uso aparece menos em quem saiu** (23,6% contra 24,9%). Isso
importa porque a coluna `Motivo (tag)` do CSV classifica 46 dos 58 cancelamentos
como "Problema de Usabilidade". O dado dos chamados não sustenta essa leitura.

**O relato livre concorda com os chamados, a tag não.** Nos 58 relatos escritos à
mão, lentidão e erro empatam no topo, com 10 menções cada. A tag colapsa tudo em
usabilidade e perde essa informação.

**Ninguém avisa que vai sair.** Menção a cancelar ou trocar o contrato aparece em
0,6% dos chamados, igual nos dois grupos. E o CSAT médio de quem cancelou é 4,9,
com apenas 2,8% de notas 1 ou 2. Os clientes avaliaram bem o atendimento e foram
embora assim mesmo. O desconforto estava no produto, não no suporte.

### Limites que continuam de pé

O recorte significativo se apoia em 34 chamados de um lado e 41 do outro. É
suficiente para o teste, e é pouco para fatiar por produto ou por squad. Com mais
meses de base, instabilidade (1,68x) e urgência (1,3x) podem passar a resistir ao
teste, ou podem sumir.

---

## Relato x chamados, caso a caso

Para cada cancelamento, a tela compara o motivo escrito na matriz com os temas dos
chamados que o cliente abriu antes de sair, e apura o que foi feito do sinal.

As regras estão em `src/confronto.py`, à vista, não escondidas no meio do código.
A mais importante: **o tema dominante nunca é o mais frequente**. "Erro e falha"
aparece em 63% dos chamados de todo mundo, inclusive de quem fica. Só conta como
sinal o tema que passou no teste estatístico, hoje lentidão e travamento.

Os vereditos possíveis:

| Veredito | Quando |
|---|---|
| Sinal ignorado | 3 ou mais chamados do tema de risco em até 90 dias, nenhum escalado |
| Sinal tratado, saiu mesmo assim | mesma repetição, mas com escalonamento registrado |
| Tema de risco, sem repetição | o tema apareceu, de leve |
| Atrito não declarado | os chamados mostram temas que o relato não menciona |
| Volume alto, sem tema de risco | 20 ou mais chamados, nenhum tema que distinga |
| Relato sem lastro nos chamados | o que foi declarado não aparece no histórico |
| Saiu sem falar com o suporte | nenhum chamado, com base suficiente para afirmar |
| Fora da janela de dados | cancelou antes de a base existir |

### O resultado

Dos 16 cancelamentos analisáveis:

- **4 com sinal ignorado.** Repetiram chamados de lentidão e nenhum virou caso.
- **4 com o tema de risco presente, sem repetição** suficiente para alerta.
- **5 com atrito que o relato não menciona.**
- **2 saíram sem nunca falar com o suporte.**
- **1 com relato coerente** com o que os chamados mostram.

O caso mais claro é a Contábil São Paulo: 7 chamados de lentidão em 43 dias, nenhum
escalado, nenhum mal avaliado. Bateu a regra 76 dias antes de cancelar. O relato diz
exatamente "está cancelando por conta da lentidão", e os chamados dizem "mas está
ficando travado no questor".

### O que "como evitar" quer dizer aqui

Não é opinião sobre a causa. É a regra que teria disparado e não disparou, com a data
em que teria disparado. Onde o sinal foi escalado e o cliente saiu mesmo assim, a tela
diz isso também: ali não faltou detecção, faltou prazo ou retorno.

---

## Tela de Atenção

Clientes ativos que repetem hoje o padrão de quem cancelou.

O alerta procura exatamente o que o teste validou: 3 ou mais chamados de lentidão em
até 90 dias, sem ninguém ter assumido o caso. Não é um escore genérico de saúde, é a
reprodução da única regra que a base sustenta.

### Como rodar

```bash
python src/varredura.py           # varre as 78 mil conversas (~90 min, retomável)
python src/atencao.py --preparar  # peneira e lista quem precisa de leitura
python src/mensagens.py           # baixa o texto desses candidatos (~20 min)
python src/atualizar.py           # gera o painel com a tela pronta
```

### Os dois estágios, e por quê

Ler o texto de 78 mil conversas levaria umas quatro horas. Então a peneira usa
metadados, que existem para a base inteira, e ordena quem merece leitura: chamados
classificados como lentidão ou performance, ritmo em alta, notas 1 e 2, mesmo assunto
repetido, ausência de escalonamento.

Só os 250 primeiros passam para a leitura de texto, e de cada um são lidas as 12
conversas mais recentes. **Isso é um recorte, não cobertura total**, e a tela diz
quantos candidatos ficaram sem leitura. Para ampliar, suba `MAX_CANDIDATOS` e
`MAX_CONVERSAS_LIDAS` em `src/risco.py` e rode de novo.

A peneira tem um limite conhecido: ela ordena por metadados para achar um sinal que
só existe no texto. Um cliente com lentidão repetida mas sem nenhum indício de
metadado pode ficar fora dos 250. Ampliar o corte reduz esse risco ao custo de tempo.

### Os três níveis

| Nível | Critério | Ação sugerida |
|---|---|---|
| Ação agora | bate a regra, nenhum escalonamento | abrir caso de produto com dono e prazo, e avisar o cliente |
| Acompanhar de perto | bate a regra, já escalado | confirmar prazo e dar retorno ao cliente |
| Só no radar | tema sem repetição, ou nota baixa, ou só volume | manter no radar |

Clientes que já cancelaram ficam fora, e contas de demonstração e treinamento também.

---

## O que ainda não está aqui

- **Texto das conversas do controle** está amostrado em 800 conversas, não no total
  de 3.737. Basta para a taxa, não para recortes finos.
- **ENOEMI CRODA SFOGGIA** está sem CNPJ no CSV e é o único registro não casado.
- **Relação entre lentidão e ambiente.** 47 dos 58 rodavam em infra do cliente.
  Vale testar se a lentidão relatada se concentra ali, mas a amostra atual não
  sustenta o corte.
