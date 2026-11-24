# Guia de estudo: Spotify Extended Streaming History

Material de apoio para escrever o `src/ingest_history.py`. O guia explica o formato e mapeia o export para a `fact_plays`, mas **não traz implementação**: as funções de parse, normalização e insert ficam por sua conta.

Convenção de confiabilidade usada no texto:

- **[oficial]**: está na documentação do Spotify (support.spotify.com, Spotify for Artists ou developer.spotify.com).
- **[comunidade]**: aparece em posts do fórum do Spotify, blogs ou repositórios de terceiros. É comportamento observado, não contrato.
- **[inferência]**: conclusão minha a partir dos dados ou exemplos. Confira no seu próprio arquivo antes de confiar.

> Aviso importante: a página oficial "Understanding your data" hoje descreve os campos **em prosa** (21 itens) e **não lista os nomes técnicos** (`ts`, `ms_played` etc.). A definição campo a campo fica no PDF `ReadMeFirst_ExtendedStreamingHistory.pdf`, que vem dentro do seu zip. Quando o export chegar, **leia esse PDF primeiro** e compare com este guia. Ele é a fonte oficial mais precisa e pode ter mudado.

---

## 1. Estrutura dos arquivos

### 1.1 Como pedir e o que chega

Em Conta → Privacidade → "Baixar seus dados", existem três pacotes independentes [oficial]:

| Pacote | Cobertura | O que tem de histórico |
|---|---|---|
| **Account data** (básico) | último ano | `StreamingHistory_music_N.json`, `StreamingHistory_podcast_N.json`, `StreamingHistory_audiobook_N.json` (nomes atuais; exports antigos usavam `StreamingHistoryN.json`) [comunidade] |
| **Extended streaming history** | **vida inteira da conta** | `Streaming_History_Audio_*.json`, `Streaming_History_Video_*.json` e o PDF `ReadMeFirst_ExtendedStreamingHistory.pdf` |
| **Technical log information** | logs técnicos | fora do escopo deste projeto |

Todos vêm em JSON [oficial]. O README do projeto já pede o estendido. O básico não serve como fonte principal pelos motivos da tabela da seção 1.3.

### 1.2 Nomes e divisão dos arquivos do estendido

Exemplo real de listagem (export de 2026, publicado por terceiros) [comunidade]:

```
Streaming_History_Audio_2016-2017_0.json
Streaming_History_Audio_2017_1.json
Streaming_History_Audio_2017-2018_2.json
Streaming_History_Audio_2018_3.json
Streaming_History_Audio_2018_4.json
...
Streaming_History_Audio_2024-2025_14.json
Streaming_History_Audio_2025-2026_15.json
Streaming_History_Video_2017-2026.json
ReadMeFirst_ExtendedStreamingHistory.pdf
```

O que dá para tirar disso [inferência, consistente em dois exports diferentes]:

- **A divisão é por tamanho, não por ano.** Os arquivos de áudio têm cerca de 10,5 MB cada (o último é menor). O trecho `2017-2018` no nome é só **o intervalo de anos que caiu naquele arquivo**. Por isso aparecem arquivos como `2018_3` e `2018_4`, ambos de 2018.
- **O sufixo `_N` é sequencial** e dá a ordem dos arquivos. Os anos de arquivos vizinhos se sobrepõem (o fim de um e o começo do próximo caem no mesmo ano).
- **Vídeo vem em um arquivo só** (`Streaming_History_Video_AAAA-AAAA.json`), em geral pequeno.
- Cada arquivo é **um array JSON de objetos**, um objeto por execução (stream).

Consequências para o ingest:

- Use um glob como `Streaming_History_Audio_*.json`. **Não** derive nada do ano no nome.
- Não assuma que os registros estão ordenados por `ts` dentro do arquivo ou entre arquivos [inferência: costumam estar, mas nada oficial garante]. Se precisar de ordem, ordene no banco.
- Decida se o arquivo de vídeo entra (ver seção 3.3).

### 1.3 Básico vs. estendido

| | Básico (`StreamingHistory_music_N.json`) | Estendido (`Streaming_History_Audio_*.json`) |
|---|---|---|
| Cobertura | último ano [oficial] | conta inteira [oficial] |
| Timestamp | `endTime`, `"2022-03-30 20:08"`: **precisão de minuto**, sem fuso explícito (é UTC [oficial]) | `ts`, `"2024-07-22T08:59:28Z"`: precisão de **segundo**, UTC explícito |
| Campos | 4: `endTime`, `artistName`, `trackName`, `msPlayed` | cerca de 23 (seção 2) |
| ID da faixa | **não tem** | `spotify_track_uri` |
| Podcast | arquivo separado | mesmo arquivo, campos `episode_*` |

Exemplo do básico [comunidade]:

```json
{ "endTime": "2022-03-30 20:08", "artistName": "Artista", "trackName": "Faixa", "msPlayed": 183000 }
```

Sem ID e com precisão de minuto, o básico casa muito mal com a API. Mais um motivo para usar só o estendido.

---

## 2. Campos de um registro de áudio

### 2.1 Registro atual (formato 2024+)

Registro de música (exemplo de setembro de 2025, IP trocado) [comunidade]:

```json
{
  "ts": "2025-09-18T13:43:56Z",
  "platform": "windows",
  "ms_played": 270186,
  "conn_country": "US",
  "ip_addr": "203.0.113.10",
  "master_metadata_track_name": "Halo",
  "master_metadata_album_artist_name": "Depeche Mode",
  "master_metadata_album_album_name": "Violator (Deluxe)",
  "spotify_track_uri": "spotify:track:6Rr6wXmEx6w6dsBuqqKJa3",
  "episode_name": null,
  "episode_show_name": null,
  "spotify_episode_uri": null,
  "audiobook_title": null,
  "audiobook_uri": null,
  "audiobook_chapter_uri": null,
  "audiobook_chapter_title": null,
  "reason_start": "trackdone",
  "reason_end": "trackdone",
  "shuffle": true,
  "skipped": false,
  "offline": false,
  "offline_timestamp": 1758202112,
  "incognito_mode": false
}
```

### 2.2 O schema muda entre exports

A lista de chaves **não é estável no tempo** [comunidade, observado em exports de datas diferentes]:

| Formato antigo (até ~2024) | Formato atual (~2024 em diante) |
|---|---|
| `username` | removido |
| `ip_addr_decrypted` | renomeado para `ip_addr` |
| `user_agent_decrypted` (muitas vezes `null`) | removido |
| sem campos de audiobook | `audiobook_title`, `audiobook_uri`, `audiobook_chapter_uri`, `audiobook_chapter_title` |

A página oficial ainda cita username, IP e user agent na lista de 21 itens, sem mencionar audiobooks. Ou seja, a página está desatualizada em relação ao arquivo. Lição para o ingest: **leia campo por campo de forma tolerante** (chave ausente = nulo) e não quebre se aparecer chave nova. Vale registrar no log quais chaves apareceram.

### 2.3 Dicionário de campos

"Pode ser null?" significa que o valor pode vir `null` (ou a chave pode faltar, nos campos que mudaram).

| Campo | Tipo JSON | Significado | Pode ser null? |
|---|---|---|---|
| `ts` | string ISO 8601, `...Z` | Data/hora em que o stream **terminou**, em UTC [oficial]. Precisão de segundo. | Não (nunca vi) |
| `username` | string | Usuário Spotify. Só no formato antigo. | Ausente no formato novo |
| `platform` | string | Plataforma/dispositivo. Formato antigo: texto livre (`"Android OS 9 API 28 (samsung, SM-G960F)"`, `"WebPlayer (websocket RFC6455)"`). Formato novo: valores curtos (`"ios"`, `"windows"`, `"android"`...). [comunidade] | Raro |
| `ms_played` | inteiro | Milissegundos tocados **nesta execução** [oficial]. Pode ser 0. | Não |
| `conn_country` | string (2 letras) | País de onde o stream foi feito, código ISO 3166-1 alpha-2 [oficial: "country code"] | Raro |
| `ip_addr` / `ip_addr_decrypted` | string | IP usado no stream [oficial] | Sim |
| `user_agent_decrypted` | string | User agent (ex.: navegador). Só no formato antigo. | Frequentemente null |
| `master_metadata_track_name` | string | Nome da faixa [oficial] | **Sim**: podcast, audiobook, vídeo e registros "órfãos" (3.3) |
| `master_metadata_album_artist_name` | string | "Artist, band or podcast name" [oficial]. Pelo nome, é o artista **do álbum** (ver 3.8). | **Sim** (mesmos casos) |
| `master_metadata_album_album_name` | string | Nome do álbum [oficial] | **Sim** |
| `spotify_track_uri` | string `spotify:track:<id>` | URI da faixa [oficial] | **Sim** (não-música, órfãos) |
| `episode_name` | string | Nome do episódio de podcast [oficial] | Sim (null em música) |
| `episode_show_name` | string | Nome do programa [oficial] | Sim |
| `spotify_episode_uri` | string `spotify:episode:<id>` | URI do episódio [oficial] | Sim |
| `audiobook_title` | string | Título do audiobook [comunidade: não está na página oficial] | Sim |
| `audiobook_uri` | string | URI do audiobook | Sim |
| `audiobook_chapter_uri` | string | URI do capítulo | Sim |
| `audiobook_chapter_title` | string | Título do capítulo | Sim |
| `reason_start` | string | Por que a execução começou [oficial; valores em 2.4] | Raro |
| `reason_end` | string | Por que a execução terminou [oficial] | Raro (já houve relatos de null) |
| `shuffle` | boolean | Se o modo aleatório estava ligado [oficial] | Raro |
| `skipped` | boolean | "Whether the user skipped to the next song" [oficial] | **Sim** (ver 3.6) |
| `offline` | boolean | Se tocou offline [oficial] | Raro |
| `offline_timestamp` | inteiro (epoch Unix) | "Timestamp of when offline mode was used, if it was used" [oficial]. Nos exemplos de 2024 e 2025 vem **em segundos**, preenchido mesmo com `offline: false`. | Sim (exemplo de 2016 com null) |
| `incognito_mode` | boolean | Se tocou em sessão privada [oficial: "private session"] | Raro |

### 2.4 Valores de `reason_start` / `reason_end`

O Spotify **não publica a lista** fora do PDF do zip. A lista abaixo junta valores observados em exports de terceiros [comunidade]. Os significados são **[inferência]** pelo nome e pelo contexto. Confirme no PDF e com uma contagem simples no seu próprio dado (`GROUP BY reason_start`).

| Valor | Em start | Em end | Significado provável |
|---|---|---|---|
| `trackdone` | ✓ | ✓ | start: a faixa anterior acabou e esta entrou sozinha. end: a faixa tocou até o fim. |
| `fwdbtn` | ✓ | ✓ | botão "próxima" (start: entrou porque a anterior foi pulada; end: esta foi pulada) |
| `backbtn` | ✓ | ✓ | botão "anterior" |
| `clickrow` | ✓ | | clicou na faixa numa lista (playlist, álbum, busca) |
| `playbtn` | ✓ | ✓ | botão play/pause |
| `appload` | ✓ | | retomou ao abrir o app |
| `remote` | ✓ | ✓ | controle por outro dispositivo (Spotify Connect, Chromecast etc.) |
| `trackerror` | ✓ | ✓ | erro de reprodução |
| `endplay` | | ✓ | reprodução encerrada (parou de tocar) |
| `logout` | | ✓ | logout durante a execução |
| `unexpected-exit` | | ✓ | app fechou ou travou tocando |
| `unexpected-exit-while-paused` | | ✓ | app fechou com a faixa pausada |
| `unknown` | ✓ | ✓ | sem informação |
| outros (`popup`, `uriopen`, `persisted`, `clickside`...) | ✓ | | menos frequentes. Trate qualquer valor desconhecido como texto, sem validar contra lista fixa. |

Dica de estudo: na sua tabela, guarde o texto cru. Não converta para enum no ingest, porque um valor novo derrubaria a carga.

---

## 3. Pegadinhas

### 3.1 `ts` é o FIM da execução, e a semântica tem ruído

- **Oficial:** "Date and time of when the stream ended in UTC format". A versão antiga da página dizia que é o momento "when the track stopped playing". Então **`ts` = fim**, e o schema do dono (`played_at` = fim) está alinhado com o export.
- **Início estimado** [inferência]: `início ≈ ts − ms_played`. É estimativa, porque pausas entre começo e fim não entram em `ms_played`.
- **Ruído [comunidade]:** um post no fórum de desenvolvedores relata execuções de vários minutos com `ts` a poucos segundos uma da outra, e registros duplicados com `ts` diferentes. A teoria do autor (sem resposta oficial) é que `ts` seria a hora em que o **servidor recebeu** o evento, e não a hora local. Isso pesa sobretudo em plays **offline**, que só sobem quando o aparelho reconecta.
- **`offline_timestamp` não salva** [inferência, contas feitas com os exemplos públicos]:

  | `ts` (epoch) | `offline_timestamp` | diferença | `ms_played` |
  |---|---|---|---|
  | 1721638768 (2024-07-22T08:59:28Z) | 1721638762 | 6 s | 2,2 s |
  | 1721879539 (2024-07-25T03:52:19Z) | 1721879522 | 17 s | 15,7 s |
  | 1721932586 (2024-07-25T18:36:26Z) | 1721932581 | 5 s | 3,9 s |
  | 1758203036 (2025-09-18T13:43:56Z) | 1758202112 | 924 s | 270 s |

  Nos três primeiros casos, `offline_timestamp` parece o início (diferença ≈ ms_played + alguns segundos). No quarto, não bate. **Não use `offline_timestamp` como início.** Use no máximo como diagnóstico. A unidade vista nesses exemplos é segundo. Se algum registro vier com 13 dígitos, é milissegundo: cheque a magnitude.

### 3.2 Fuso horário

- `ts` vem sempre em UTC com `Z` [oficial]. Guarde em UTC e converta só na consulta ou no Power BI.
- Para análise por hora local (America/Sao_Paulo), lembre que **o Brasil teve horário de verão até 2019**. Um offset fixo de −3 erra parte do histórico antigo. Converta com base de fusos (`zoneinfo`), não com offset fixo.
- `conn_country` mostra onde você estava. Em viagens, a "hora local" real é outra. Decida se isso importa para o dashboard.

### 3.3 Registros sem `master_metadata_track_name`

Quatro origens diferentes, com tratamentos diferentes:

1. **Podcast**: `episode_name`, `episode_show_name` e `spotify_episode_uri` preenchidos, e os campos de faixa null.
2. **Audiobook**: campos `audiobook_*` preenchidos (formato novo). Em exports antigos, audiobook pode aparecer como episódio [inferência].
3. **Vídeo** (`Streaming_History_Video_*.json`): mesmas chaves do áudio [comunidade]. Em geral são videocasts ou clipes, com campos de episódio ou de faixa conforme o caso [inferência: não achei documentação, olhe o seu arquivo].
4. **Registros órfãos**: **tudo** null (faixa, episódio, URI), mas com `ms_played > 0`. Há dois relatos no fórum: um de out/2022 a 2023, que o suporte do Spotify atribuiu a uma mudança de sistema, dizendo que **pedir o export de novo corrige**; e outro com mais de 7 mil registros em 2024, sem explicação. Esses registros não dizem o que tocou.

Exemplo de órfão (2024, formato antigo) [comunidade]:

```json
{
  "ts": "2024-07-22T08:59:28Z", "platform": "ios", "ms_played": 2246, "conn_country": "US",
  "master_metadata_track_name": null, "master_metadata_album_artist_name": null,
  "master_metadata_album_album_name": null, "spotify_track_uri": null,
  "episode_name": null, "episode_show_name": null, "spotify_episode_uri": null,
  "reason_start": "trackdone", "reason_end": "trackdone",
  "shuffle": false, "skipped": false, "offline": false,
  "offline_timestamp": 1721638762, "incognito_mode": false
}
```

Para estudar: conte quantos registros de cada tipo existem no seu export **antes** de decidir o que fazer (ex.: classificar cada registro em music / episode / audiobook / orphan e contar).

### 3.4 Extrair o `track_id` de `spotify_track_uri`

- Formato: `spotify:track:<id>`, em que `<id>` é base62 de 22 caracteres (ex.: `spotify:track:6Rr6wXmEx6w6dsBuqqKJa3` → `6Rr6wXmEx6w6dsBuqqKJa3`). É o mesmo ID que a API devolve em `track.id` [oficial, formato de URI da Web API].
- Pegadinhas:
  - Valide o prefixo `spotify:track:` antes de cortar. Não pegue "a última parte depois de `:`" às cegas: URIs de episódio (`spotify:episode:`) e de arquivos locais (`spotify:local:...`, com vários `:`) existem [inferência quanto a aparecerem no export; não confirmei arquivos locais].
  - O ID do export pode **não ser o mesmo** que a API devolve para "a mesma música". O Spotify tem várias versões da mesma faixa (single, álbum, deluxe, remaster) e faz *track relinking* por mercado. Na prática, casar só por `track_id` pode falhar onde casar por nome+artista funcionaria [inferência].

### 3.5 Duplicatas no mesmo segundo

- Há relatos de registros repetidos [comunidade]. Pode ser duplicata exata (mesmo `ts`, mesma faixa, mesmo `ms_played`) ou a mesma escuta com `ts` levemente diferente.
- Também existem registros **legítimos** com o mesmo `ts`. Exemplo: uma faixa pulada em menos de 1 s e a seguinte terminando no mesmo segundo, ou o mesmo `ts` em dispositivos diferentes [inferência].
- Com a PK `(played_at, track_name)`:
  - duplicata exata → a segunda é rejeitada ou ignorada (provavelmente o que você quer);
  - **a mesma faixa duas vezes no mesmo segundo com `ms_played` diferente** (ex.: um registro de 0 ms e outro real) → colide, e **qual sobrevive depende da ordem de inserção** se você usar "insert or ignore". Pense se isso importa;
  - duas faixas diferentes no mesmo segundo → sem problema;
  - duplicata com `ts` diferente (o ruído de 3.1) → a PK não pega, e entram duas linhas.
- Experimento sugerido: no seu dado, agrupe por (`ts`, `spotify_track_uri`) e conte quantos grupos têm mais de 1 registro, e se eles têm `ms_played` iguais.

### 3.6 `skipped`: null vs. false

- O campo é booleano, mas **aceita null** [comunidade: aparece null em muitos registros, principalmente antigos].
- Semântica sugerida [inferência]: `true` = pulou; `false` = não pulou; `null` = **o cliente não informou** (não quer dizer "não pulou").
- Na coluna `skipped INTEGER`, mapear null → 0 mistura "não sei" com "não". Mapear null → NULL preserva a diferença. Há também um sinal alternativo: `reason_end = 'fwdbtn'` costuma indicar pulo mesmo quando `skipped` vem null/false [inferência]. Vale comparar os dois no seu dado.

### 3.7 `ms_played = 0` e plays curtíssimos

- Existem muitos registros com 0 ms ou poucos ms (faixa carregada e pulada, autoplay interrompido). No fórum, a explicação informal é "pulou ou não tocou" [comunidade].
- Eles não são erro: são eventos reais de "a faixa começou". Se entram na `fact_plays` é a decisão (b) da seção 5.
- Cuidado com somas: `SUM(ms_played)` não muda com eles, mas `COUNT(*)` infla bastante.

### 3.8 `master_metadata_album_artist_name` ≠ lista de artistas

- O export traz **um único artista**, e pelo nome é o artista **do álbum**. A API traz `track.artists[]` (lista, com feats.).
- Em feats. e coletâneas o nome pode divergir do `artists[0].name` da API [inferência: não achei documentação dizendo se é album artist ou primary artist; teste comparando alguns IDs com a API].
- Como você tem `bridge_track_artist`, a lista completa de artistas pode vir do enrich por `track_id`. O `artist_name` da fato fica como rótulo de conveniência.

### 3.9 Formato do texto do timestamp (SQLite compara string)

`played_at` é `TEXT`, e o SQLite compara texto **caractere a caractere**. Estes valores representam o mesmo instante, mas são strings diferentes:

```
2024-07-22T08:59:28Z          <- export
2024-07-22T08:59:28.123Z      <- API (milissegundos)
2024-07-22T08:59:28+00:00     <- outra forma comum de imprimir UTC
2024-07-22 08:59:28           <- outra
```

Defina **um único formato canônico** para a coluna (ex.: sempre com ou sempre sem milissegundos, sempre `Z`) e normalize as **duas** fontes para ele. Sem isso, PK, dedup, `ORDER BY` e `BETWEEN` quebram em silêncio.

---

## 4. Mapeamento para `fact_plays`

Schema de referência (do dono):

```
played_at TEXT NOT NULL (ISO8601 UTC), track_id TEXT, track_name TEXT NOT NULL,
artist_name TEXT NOT NULL, ms_played INTEGER, reason_start, reason_end,
shuffle INTEGER, skipped INTEGER, platform TEXT, context_type, context_uri (só API),
source ('export'), PK (played_at, track_name)
```

### 4.1 Campo do export → coluna

| Coluna | Origem no export | Transformação | Observações |
|---|---|---|---|
| `played_at` | `ts` | normalizar para o formato canônico (3.9) | Semântica = fim, igual à premissa do schema. Precisão de segundo. |
| `track_id` | `spotify_track_uri` | tirar o prefixo `spotify:track:` | null para não-música e órfãos |
| `track_name` | `master_metadata_track_name` | nenhuma (ou trim) | **NOT NULL quebra aqui** (4.3) |
| `artist_name` | `master_metadata_album_artist_name` | nenhuma | **NOT NULL quebra aqui**. Ver 3.8 |
| `ms_played` | `ms_played` | nenhuma | sempre presente no export |
| `reason_start` | `reason_start` | texto cru | |
| `reason_end` | `reason_end` | texto cru | |
| `shuffle` | `shuffle` | bool → 0/1 | null → NULL |
| `skipped` | `skipped` | bool → 0/1 | **null → NULL ou 0? decisão sua** (3.6) |
| `platform` | `platform` | cru, ou normalizado | formatos antigo e novo diferem (2.3). Pense numa coluna derivada `platform_family` |
| `context_type` | — | NULL | o export não tem contexto (playlist/álbum) |
| `context_uri` | — | NULL | idem |
| `source` | — | `'export'` | |

### 4.2 Campos sem coluna: o que fazer

| Campo | Opções |
|---|---|
| `master_metadata_album_album_name` | Descartar e obter via enrich (`dim_album` por `track_id`), **ou** guardar porque é grátis e cobre faixas que saíram do catálogo (o enrich por ID pode falhar nelas). |
| `episode_*`, `audiobook_*` | Dependem da decisão sobre não-música (4.3). |
| `conn_country` | Útil para análise de viagens/fuso. Coluna opcional. |
| `offline`, `offline_timestamp` | Úteis para diagnosticar ruído no `ts`. Coluna opcional ou staging. |
| `incognito_mode` | Interessante: plays em sessão privada **existem no export**. A API provavelmente não os devolve [inferência]. Decida se entram (é o seu próprio histórico, mas você os escondeu de propósito na época). |
| `ip_addr`, `username`, `user_agent_decrypted` | **Dado pessoal sensível** (IP dá localização aproximada). Recomendação de higiene: não persistir. Se o projeto for para o GitHub como portfólio, nem o banco nem amostras devem conter isso. |

Padrão a considerar: uma **tabela de staging** (`raw_export_plays` ou similar) com todas as colunas do export, mais a `fact_plays` limpa derivada dela. O raw permite refazer a limpeza sem reler os JSON e documenta a linhagem. Contra: duplica armazenamento e acrescenta um passo. As duas escolhas são válidas.

### 4.3 Onde o NOT NULL quebra, e as escolhas

`track_name NOT NULL` e `artist_name NOT NULL` vão falhar em:

| Caso | Volume esperado | Opções |
|---|---|---|
| Podcast | depende de quanto você ouve | (a) **filtrar fora**: `fact_plays` vira "plays de música"; (b) preencher `track_name = episode_name`, `artist_name = episode_show_name` e marcar com uma coluna `content_type`; (c) tabela própria `fact_episode_plays` |
| Audiobook | idem | as mesmas três opções, com `audiobook_chapter_title` / `audiobook_title` |
| Vídeo | baixo | idem, ou ignorar o arquivo de vídeo inteiro |
| Órfão (tudo null) | pode ser de milhares | (a) descartar e contar no log; (b) staging, sem ir para a fato; (c) **pedir um export novo** (o suporte disse que corrige o caso 2022–2023) |

Prós e contras rápidos:

- **Filtrar**: schema simples e `track_name` sempre significa "música". Contra: o total de minutos ouvidos fica subestimado, e a API também não traz podcast (o endpoint "doesn't support podcast episodes" [oficial]), então isso fica coerente entre as fontes.
- **Preencher com episódio**: um único lugar para "tudo que eu ouvi". Contra: `track_name` passa a significar duas coisas, e joins com `dim_track` e `track_id` ficam nulos para essas linhas.
- **Tabela separada**: modelagem mais limpa. Contra: mais uma tabela e mais um ingest.

Além do NOT NULL, a PK `(played_at, track_name)` tem pontos fracos:

1. **Não casa com a API** quando a mesma execução vem das duas fontes (ver 5a). É o problema principal.
2. Usa nome, não ID: se o Spotify renomear a faixa ("... - Remastered 2011"), a mesma execução pode chegar com nomes diferentes [inferência].
3. Colisão real de mesma faixa no mesmo segundo (3.5).

Alternativas de chave para estudar: `(played_at, track_id)`; uma surrogate key `play_id` com UNIQUE parcial; ou manter a PK e resolver o cruzamento com a API num passo de dedup separado. Cada uma muda como o "insert or ignore" se comporta.

---

## 5. Impacto nas decisões em aberto

### 5a. A mesma execução vem do export e da API: como casar e quem ganha

**Comparação das duas fontes:**

| | Export (`ts`) | API recently-played (`played_at`) |
|---|---|---|
| Semântica | fim do stream, UTC [oficial] | "The date and time the track was played" [oficial, ambíguo]. Na prática é tratado como fim [comunidade]. |
| Precisão | segundo | milissegundo (os cursores `after`/`before` são epoch em ms [oficial]) |
| `ms_played` | sim | **não** (só `track.duration_ms`, a duração total da faixa) |
| Contexto (playlist/álbum) | não | sim (`context.type`, `context.uri`) |
| Podcast | sim | não |
| Plays parciais/pulados | sim, todos | inconsistente: relatos de que pulados **somem** e de que plays de 1–2 s **aparecem** [comunidade] |
| Janela | vida inteira, mas só até a data do pedido | últimas 50 execuções, coletadas continuamente |

**Por que a PK atual não deduplica** [inferência, mas direta]:

- Mesmo que export e API marquem o mesmo instante, `"…:28Z"` ≠ `"…:28.123Z"` como texto. A PK não colide e entram **duas linhas** da mesma execução.
- Truncar a API para segundos ajuda, mas não resolve: arredondamento (`.999`) e o ruído do `ts` (servidor vs. cliente, offline) podem deixar os dois valores a segundos ou minutos de distância.
- Há ainda um relato [comunidade, 2025] de `played_at` da API com segundos sempre terminando em 4, o que sugere que nem a API registra o instante exato.

**Opções de casamento:**

1. **Igualdade após normalizar** (truncar os dois para segundos e comparar `(played_at, track_id)`).
   Pró: simples e cabe na PK. Contra: perde casos com diferença ≥ 1 s. Quantos são, só medindo.
2. **Janela de tolerância**: considerar a mesma execução quando `track_id` é igual e `|Δt| ≤ N` segundos (N a calibrar: 5 s, 30 s, ou relativo à duração).
   Pró: robusto ao ruído. Contra: não dá para expressar como PK; precisa de um passo de dedup (query ou staging); com N grande, repetições legítimas da mesma faixa podem se fundir.
3. **Corte temporal (cutover)**: o export vale até `T = max(ts)` do export, a API vale depois de `T`, e só na fronteira se aplica a opção 1 ou 2.
   Pró: elimina quase todo o casamento difuso e é fácil de explicar numa entrevista. Contra: perde o contexto que a API tinha coletado antes de `T` (a menos que você "empreste" o contexto, ver abaixo); se a coleta da API ficou parada, o export cobre o buraco, o que é bom.
4. **Manter as duas linhas** (as duas `source`) e deduplicar numa **view**.
   Pró: não perde nada e permite auditar o casamento. Contra: quem consulta a tabela crua conta em dobro; a lógica fica na view.

**Qual fonte deveria ganhar? Critérios para você pesar:**

- **Export ganha** quando o que importa é completude e métricas de escuta (`ms_played`, `skipped`, `reason_*`, `platform`). É a fonte "oficial" do seu histórico e inclui o que a API omite.
- **API ganha** quando o que importa é `context_type`/`context_uri` (de qual playlist veio) e a precisão de ms.
- **Merge** (linha do export + contexto copiado da linha da API casada): é o melhor dos dois, mas é o mais trabalhoso e depende de o casamento ser confiável.
- Note a assimetria: a API só existe a partir do dia em que você começou a coletar. Para todo o passado só existe o export. A disputa acontece apenas na janela de sobreposição (do início da coleta até a data do pedido do export), e mais exports pedidos no futuro voltam a criar sobreposição.

### 5b. O que conta como "play"

**Critérios em uso por aí:**

| Critério | Fonte | Prós | Contras |
|---|---|---|---|
| `ms_played ≥ 30 000` | Regra do Spotify para **contar stream** de música e de vídeo musical: "Counted when a listener plays your song for at least 30 seconds" [oficial, Spotify for Artists]. A página **não fala em royalties**: "regra de royalties" é leitura comum, mas o que está documentado é a contagem de streams. | Padrão da indústria e fácil de defender | Faixas com menos de 30 s nunca contam; não aproveita o reason_end |
| Regra do Last.fm: faixa > 30 s **e** tocada ≥ metade da duração ou ≥ 4 min | [oficial Last.fm] | Considera a duração da faixa | Precisa de `duration_ms` (enrich), mais lógica |
| `ms_played > 0` | — | Não perde nada | Conta autoplays abortados e pulos instantâneos |
| `reason_end = 'trackdone'` | — | "Ouviu até o fim" | Despreza escutas longas interrompidas; o último play antes de fechar o app vira `endplay`/`unexpected-exit` |
| `skipped` ≠ true | — | Simples | `skipped` null em muitos registros (3.6) |

**O problema da API sem `ms_played`:**

Uma linha da API diz que algo foi tocado, mas não por quanto tempo. Opções:

1. **`ms_played = NULL`** para a API e regra de play que trate NULL explicitamente (ex.: "API conta como play").
   Pró: honesto. Contra: o critério fica diferente por fonte, e somas de minutos ignoram a API.
2. **Assumir `ms_played = duration_ms`** (da `dim_track`).
   Pró: as somas funcionam. Contra: é falso para pulos e plays parciais, que a API às vezes inclui [comunidade, 2025]; superestima o tempo.
3. **Estimar pela diferença entre `played_at` consecutivos**: `min(duration_ms, played_at[i] − played_at[i−1])` [inferência].
   Pró: aproxima pulos. Contra: falha em pausas, na primeira faixa da sessão e em buracos de coleta; é heurística e precisa ser documentada.
4. **Deixar a API só como "ponte"** até o próximo export, que substitui essas linhas (combina com o cutover de 5a).
   Pró: no longo prazo tudo tem `ms_played` real. Contra: exige pedir export periodicamente (o export estendido não é instantâneo), e o recente fica sempre aproximado.

Escolha de arquitetura que não depende do critério: **guardar todos os eventos** na fato (inclusive 0 ms) e aplicar a regra de "play" numa **view** ou coluna derivada (`is_play`). Assim o critério pode mudar sem re-ingest. Contra: a fato fica maior e quem esquecer de filtrar conta errado. Em oposição, filtrar já no ingest deixa a fato mais limpa, mas torna a regra irreversível sem recarregar.

---

## 6. Checklist de estudo antes de escrever o ingest

1. Ler o `ReadMeFirst_ExtendedStreamingHistory.pdf` e anotar divergências com este guia (lista de campos, unidade do `offline_timestamp`, valores de reason).
2. Listar as chaves presentes em todos os arquivos (união) e ver se o formato antigo e o novo aparecem misturados.
3. Contar registros por tipo: música / episódio / audiobook / órfão / vídeo.
4. Ver a distribuição de `ms_played` (quantos com 0, < 30 s, ≥ 30 s).
5. Contar grupos duplicados por (`ts`, `spotify_track_uri`).
6. Ver a proporção de `skipped` null por ano.
7. Escolher o formato canônico de `played_at` e aplicá-lo nas duas fontes.
8. Na janela de sobreposição com a API, medir `Δt` entre linhas que você sabe que são a mesma escuta antes de escolher N (5a).

---

## 7. Links consultados

Oficiais (Spotify):

- Understanding your data (descrição em prosa dos 21 itens; `ts` = fim do stream em UTC): https://support.spotify.com/us/article/understanding-your-data/
- Versão "understanding-my-data" da mesma página: https://support.spotify.com/us/article/understanding-my-data/
- Data rights and privacy settings (como baixar os dados): https://support.spotify.com/us/article/data-rights-and-privacy-settings/
- Spotify for Artists, "How your streams are counted" (regra dos 30 s): https://support.spotify.com/us/artists/article/how-we-count-streams/ (também https://artists.spotify.com/help/article/how-we-count-streams)
- Web API, Get Recently Played Tracks (`played_at`, cursores em ms, sem podcasts): https://developer.spotify.com/documentation/web-api/reference/get-recently-played

Não oficiais (comunidade/terceiros):

- Fórum: "Clarification of Spotify data export structure" (definição antiga de `ts` e teoria de hora do servidor): https://community.spotify.com/t5/Spotify-for-Developers/Clarification-of-Spotify-data-export-structure/td-p/5360082
- Fórum: "Extended Streaming History missing track metadata" (registros órfãos, formato antigo com `ip_addr_decrypted`): https://community.spotify.com/t5/Other-Podcasts-Partners-etc/Extended-Streaming-History-missing-track-metadata/td-p/6269152
- Fórum: "Null values in streaming history" (nulls desde out/2022, resposta do suporte): https://community.spotify.com/t5/Spotify-for-Developers/Null-values-in-streaming-history/m-p/5510611/highlight/true
- Fórum: "Help with some tracks with msPlayed 0": https://community.spotify.com/t5/Spotify-for-Developers/Help-with-some-tracks-with-msPlayed-0/td-p/5506167
- Fórum: "Get Recently Played Tracks doesn't return skipped tracks": https://community.spotify.com/t5/Spotify-for-Developers/Get-Recently-Played-Tracks-doesn-t-return-skipped-tracks/td-p/5339618
- Fórum: "Web API Issues with Get Recently Played Tracks endpoint" (2025; plays de 1–2 s, segundos terminando em 4): https://community.spotify.com/t5/Spotify-for-Developers/Web-API-Issues-with-Get-Recently-Played-Tracks-endpoint/td-p/7044755
- Eric Chiang, 2024 (listagem de arquivos e divisão por tamanho, formato antigo): https://ericchiang.github.io/post/spotify
- jrtechs, 2026 (listagem completa de export recente, registro no formato novo): https://jrtechs.net/data-science/the-data-spotify-collected-on-me-over-ten-years
- Raymond Camden, 2025 (registro completo no formato novo): https://www.raymondcamden.com/2025/12/04/make-your-own-spotify-unwrapped
- Last.fm, regras de scrobble: https://www.last.fm/api/scrobbling
