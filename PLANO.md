# Plano — Dashboard de CS (Questor Sistemas)

> **Status: executado.** O dashboard está em `dashboard/index.html` e as instruções
> de uso ficam no `README.md`. Este documento é o plano original, mantido como
> registro. Uma coisa mudou depois da execução: a base do Chatwoot só tem conversas
> desde 05/05/2026, então a janela de 12 meses proposta aqui não existe para a
> maior parte dos cancelamentos. O README explica o recorte que passou a valer.

Cruzar a matriz de cancelamentos (Jan–Ago/2026) com o histórico de atendimentos do
Chatwoot (conta 3) para responder: **o suporte dá sinal antecipado de churn?**

---

## 1. O que foi validado na API (feito, não é suposição)

Token `MQ3hZ...` autentica como **Jean Carlos**, perfil `administrator`, conta 3.

| Verificação | Resultado |
|---|---|
| Conversas na conta 3 | 78.361 |
| Contatos | 8.828 |
| Empresas cadastradas | 5.529 |
| Empresas do CSV encontradas por CNPJ | **57 de 58** |
| Conversas da empresa-piloto (MLC) | 43, em 10s |
| Conversas com nota CSAT | ~60% |

### A descoberta que define a arquitetura

O Chatwoot desta instância tem um cadastro de **empresas** (`/api/v1/accounts/3/companies`)
que não aparece na documentação pública. Cada empresa traz:

- `registration_number` — o CNPJ, sem máscara, que casa exatamente com a coluna do CSV
- `group_company` — o tier do cliente (bronze, prata, ouro, esmeralda, diamante)
- `custom_attributes.ambiente` — Infra do Cliente / Infra Questor Dedicado / Compartilhado
- `contacts` — todas as pessoas daquela empresa

Isso importa porque a alternativa era adivinhar o domínio de e-mail a partir do nome
da empresa. Testei: gera falso positivo grosseiro. "CASA DO SALPIQUE" casava com
`casagrandecontabil.com.br`, "MCLARENS DO BRASIL" com `rjsbrasil.com.br`. O casamento
por CNPJ é determinístico e dispensa revisão manual.

Distribuição dos 57 cancelamentos já cruzados: 26 bronze, 14 prata, 10 diamante,
6 ouro, 1 esmeralda. E 47 dos 57 rodavam em infra do próprio cliente.

---

## 2. Pipeline de extração

Quatro etapas, cada uma gravando seu resultado em disco para não repetir chamada.

**Etapa 1 — Ler o CSV.** Separador `;`, UTF-8 com BOM, 58 linhas. Normalizar o CNPJ
removendo pontuação. Converter datas `DD/MM/AAAA` e valores de MRR do formato brasileiro.

**Etapa 2 — Resolver empresa.** Para cada CNPJ, chamar `/companies/search?q=<cnpj>` e
confirmar a igualdade do `registration_number`. Só aceitar casamento exato.

**Etapa 3 — Puxar conversas.** Para cada empresa, `/companies/{id}` devolve os contatos.
Para cada contato, `/contacts/{id}/conversations`. Deduplicar por id de conversa.

**Etapa 4 — Consolidar.** Gravar um JSON por empresa mais um agregado.

Campos aproveitáveis por conversa, todos já confirmados na resposta da API:
`created_at`, `status`, `labels`, `first_reply_created_at`, `csat_rating`,
`priority`, `service` (o assunto do chamado) e os atributos `Status` e `produto`.

Custo estimado: cerca de 10 a 20 minutos para as 57 empresas. Cabe em uma execução.

### Ponto de atenção sobre volume

Baixar o texto das mensagens é opcional e multiplica o tempo por dez. A Etapa 4
grava só os metadados. Se a leitura dos relatos for necessária, ela vira uma etapa
sob demanda, disparada por empresa, e não no lote inicial.

---

## 3. O que o dashboard mostra

### Visão geral
Cancelamentos por mês, MRR perdido acumulado, motivo em tag, tipo total contra parcial.
Recorte por tier e por ambiente, que são dados que o CSV não tem e a API traz.

### A tela que justifica o projeto: linha do tempo pré-cancelamento
Para cada cliente, os atendimentos nos 12 meses anteriores à data de cancelamento,
em barras por mês. É aqui que se vê se houve escalada de chamados antes da saída.

### Sinais de risco
Quatro indicadores por cliente, nos 90 dias que antecedem o cancelamento:

- volume de chamados contra a média do próprio cliente no período anterior
- média de CSAT e quantidade de notas 1 e 2
- reincidência do mesmo `service` ou `produto`
- tempo até a primeira resposta

### Confronto relato contra atendimento
Lado a lado, o motivo declarado no cancelamento e os produtos e serviços que o cliente
mais acionou. Serve para checar se o motivo registrado bate com o que o suporte viu.

### Ficha do cliente
Uma empresa por vez, com todos os chamados, e link direto para a conversa no Chatwoot
em `http://192.168.0.232:3000/app/accounts/3/conversations/{id}`.

---

## 4. Como fica no projeto

```
QuestorCS/
  cancelamentos-matriz-Janeiro-Agosto-2026.csv   (entrada, já está aqui)
  src/
    chatwoot.py        cliente da API, com retry e limite de requisições
    extrair.py         etapas 1 a 4
    metricas.py        janelas temporais e indicadores de risco
  dados/
    empresas.json      resultado do casamento por CNPJ
    conversas.json     metadados das conversas
    dashboard.json     agregado que alimenta a tela
  dashboard/
    index.html         página única, lê o dashboard.json
  .env                 token, fora do versionamento
```

Python para extrair, HTML de arquivo único para exibir. Sem servidor, sem banco.
Reprocessar é rodar `python src/extrair.py` de novo.

**O token sai do código.** Hoje ele está em texto puro nesta conversa. Vai para um
`.env` com `.gitignore`, e vale rotacioná-lo no Chatwoot quando o projeto estabilizar.

**O dashboard fica local.** O conteúdo tem CNPJ, MRR e motivo de cancelamento de
cliente nomeado. Não publico isso como página hospedada sem você mandar.

---

## 5. Ordem de execução

1. Cliente da API e casamento por CNPJ das 58 linhas
2. Extração das conversas das 57 empresas, com cache em disco
3. Cálculo das métricas e janelas temporais
4. Dashboard, começando pela visão geral e pela linha do tempo
5. Telas de risco e de confronto relato contra atendimento

---

## 6. Perguntas em aberto

**1. Janela de comparação.** Proponho 12 meses antes do cancelamento, com recorte
de 90 dias para os sinais de risco. Confirma?

**2. Grupo de controle.** O número de chamados de quem cancelou só significa algo
comparado a quem ficou. Posso extrair uma amostra de clientes ativos do mesmo tier
para servir de linha de base. Isso soma tempo de extração. Quer?

**3. ENOEMI CRODA SFOGGIA** está sem CNPJ no CSV e é a única linha que não casou.
Você me passa o documento ou eu busco pelo nome no cadastro de empresas?

**4. Texto das conversas.** Os metadados respondem quase tudo. Ler o conteúdo das
mensagens permitiria comparar o relato de cancelamento com o que o cliente escreveu
no suporte, mas encarece bastante a extração. Entra agora ou fica para depois?

**5. Mais CSVs.** Você mencionou colar uma lista de empresas numa pasta. O arquivo
de cancelamentos já serve como essa lista. Vem outro arquivo, com escopo diferente?
