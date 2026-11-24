# spotify-pipeline

Pipeline pessoal que junta o histórico completo de execuções do Spotify (Extended Streaming History) com coleta incremental pela Web API, modela os dados em fato + dimensões no SQLite e termina num dashboard Power BI. Treina OAuth com refresh token, ingestão incremental com dedup, modelagem dimensional e rate limit estrutural (a API não tem mais endpoints em lote).

## Setup

- [x] **Pedir o Extended Streaming History.** Conta → Privacidade → download de dados, opção estendida (não a básica, que só cobre 1 ano). Chega por e-mail em alguns dias.
- [x] **Criar o app no Spotify Developer Dashboard.** Redirect URI: `http://127.0.0.1:8888/callback` (`localhost` não é aceito). Nome do app não pode começar com "Spot".
- [x] Copiar `.env.example` para `.env` e preencher Client ID e Client Secret.
- [x] `python -m venv .venv` e `.venv\Scripts\pip install -r requirements.txt`.
- [x] **Pegar o refresh token:** `.venv\Scripts\python src\get_refresh_token.py`. Abre o navegador, recebe o callback em `127.0.0.1:8888`, grava o token e a data de emissão no `.env` e valida com `GET /me`.
- [x] `python src/db.py` para criar o banco e as tabelas (o `ingest_recent.py` também aplica o schema).

## Uso

```powershell
.venv\Scripts\python src\ingest_recent.py   # últimas 50 execuções -> fact_plays + dimensões
```

A API só guarda as últimas 50 execuções: rodar com frequência suficiente para não passar disso entre uma coleta e outra. O script avisa quando detecta um buraco.

### Agendamento (Windows)

Uma tarefa do Agendador de Tarefas, `spotify-pipeline ingest_recent`, roda o script de hora em hora e no logon, com `pythonw.exe` (sem janela). Se o PC estava desligado no horário, ela roda assim que der. O log fica em `logs/ingest_recent.log`, com rotação de 1 MB.

```powershell
$repo = "C:\caminho\para\spotify-pipeline"
$action = New-ScheduledTaskAction -Execute "$repo\.venv\Scripts\pythonw.exe" -Argument "src\ingest_recent.py" -WorkingDirectory $repo
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
$logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "spotify-pipeline ingest_recent" -Action $action -Trigger $hourly,$logon -Settings $settings
```

Limitação: com o PC desligado, o que for ouvido em outro dispositivo só é capturado se ainda estiver entre as últimas 50 execuções quando a tarefa rodar.

> **O refresh token vence 180 dias após a autorização** (o refresh não estende o prazo). Quando vencer, o `/api/token` responde `400 invalid_grant`: rodar `get_refresh_token.py` de novo.

### Limitações da API observadas (nov/2026)

- `GET /artists/{id}` não devolve mais `genres` (veio nulo no teste; a doc marca o campo como deprecated). Análises por gênero dependem de outra fonte.
- O refresh não devolveu `refresh_token` novo; o token original continua valendo.
- O objeto `track` do `recently-played` já traz todas as colunas de `dim_track` e `dim_album`, então o enrich por ID é quase desnecessário para música vinda da API.

## Decisões de projeto

**Autenticação**

- **Onde guardar Client ID, secret e refresh token sem que entrem no Git**
  - Escolha: `.env` na raiz, listado no `.gitignore` desde antes do primeiro commit; `.env.example` sem valores vai pro Git.
  - Motivo: projeto local de um usuário só; um cofre de segredos seria complexidade sem ganho. Segredo commitado uma vez fica no histórico, por isso o `.gitignore` veio primeiro.
- **Quando renovar o access token** (sempre no início, só ao tomar 401, ou outra regra)
  - Escolha: na primeira chamada de cada execução e quando faltar menos de 5 min para expirar; se ainda assim vier 401, força um refresh e tenta uma vez.
  - Motivo: cada coleta leva segundos, então renovar no início é barato e evita 401 previsível. A margem cobre o enrich longo; o retry no 401 cobre token revogado ou relógio errado.
- **Onde gravar o refresh token renovado** (o refresh pode devolver um token novo ou nenhum)
  - Escolha: no próprio `.env`, só quando a resposta trouxer um `refresh_token` diferente do atual. A data de emissão fica em `SPOTIFY_REFRESH_TOKEN_ISSUED_AT` e o script avisa quando faltarem 15 dias para os 180.
  - Motivo: a doc diz que o token pode não vir na resposta e, nesse caso, o atual continua valendo; sobrescrever com vazio derrubaria o acesso. O token não informa a própria idade, então a data precisa ser guardada.

**Modelagem e dados**

- **Qual fonte ganha quando a mesma execução vem do export e da API**
  - Escolha: corte temporal. O export é a fonte de verdade até o `max(ts)` dele; linhas da API só entram com `played_at` posterior a esse corte. `played_at` é gravado nas duas fontes no formato canônico `YYYY-MM-DDTHH:MM:SSZ` (UTC, precisão de segundo).
  - Motivo: o export tem precisão de segundo e a API de milissegundo, e o `ts` do export tem ruído de ±1 s ou mais. Casar execução por execução exigiria janela de tolerância e ainda erraria nas bordas. O corte é simples, determinístico e fácil de explicar, e privilegia o export porque ele tem `ms_played`, `skipped` e `reason_*`.
- **Execuções sem faixa de música (podcast, audiobook, vídeo, registros órfãos)**
  - Escolha: ficam fora de `fact_plays`; o `ingest_history.py` só carrega linhas com `spotify_track_uri` e registra no log quantas descartou por tipo.
  - Motivo: o projeto analisa música; essas linhas quebram o `NOT NULL` de `track_name`/`artist_name` e não têm dimensão correspondente. A contagem no log mantém a perda visível.
- **Gênero mais ouvido: view SQL ou cálculo no Power BI via ponte**
  - Escolha: _a definir_
  - Motivo: _a definir_
- **Política de refresh das dimensões** (nunca, a cada 90 dias, ou só artista)
  - Escolha: _a definir_
  - Motivo: _a definir_
- **O que conta como "play"**
  - Escolha: no export, `ms_played >= 30000`. Linhas da API contam como play (não têm `ms_played`). As linhas abaixo de 30 s continuam no fato; o filtro é aplicado na análise, não na carga.
  - Motivo: 30 s é a regra oficial de contagem de streams do Spotify for Artists, então é defensável. Manter as linhas curtas preserva a análise de pulos. Limitação documentada: a API não permite aplicar o mesmo critério, e pelos relatos ela já omite boa parte dos pulos, mas não todos.

## Estrutura

```
spotify-pipeline/
├── .gitignore
├── .env.example
├── README.md
├── requirements.txt
├── sql/
│   └── schema.sql        # fato, dimensões, ponte e fila de enrich
├── src/
│   ├── get_refresh_token.py # handshake OAuth (1x a cada 180 dias)
│   ├── auth.py           # refresh token -> access token
│   ├── spotify_api.py    # GET com retry, 401 e rate limit (429)
│   ├── ingest_recent.py  # /me/player/recently-played -> fact_plays + dim_*
│   ├── ingest_history.py # export JSON -> fact_plays
│   ├── enrich.py         # IDs sem metadata -> dim_*
│   └── db.py             # conexão + init do schema
└── data/
    ├── raw/              # export do Spotify (ignorado no Git)
    └── spotify.db        # banco SQLite (ignorado no Git)
```
