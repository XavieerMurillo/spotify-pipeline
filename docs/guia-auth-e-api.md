# Guia de estudo: autenticação e Web API do Spotify

> Guia de **estudo** para o projeto `spotify-pipeline`. Ele explica conceitos e aponta a documentação oficial. **Não traz código pronto** de auth, refresh, ingestão ou rate limit: essa parte é sua.
>
> Pesquisa feita em **novembro/2026** em developer.spotify.com. Convenções:
> - "**Doc:**" = afirmação tirada da documentação oficial (com link na seção 7).
> - "**A doc não especifica**" = procurei e a documentação do Spotify não diz.
> - "**Fora da doc do Spotify**" = contexto de outra fonte (RFC, comunidade). Marcado explicitamente.
> - "**⚠ Divergência**" = algo que diverge do que estava assumido no projeto.

Contexto do projeto: app em Development Mode, Redirect URI `http://127.0.0.1:8888/callback`, scopes `user-read-recently-played user-top-read user-library-read playlist-read-private`, Authorization Code feito na mão uma vez e depois só `grant_type=refresh_token`.

---

## ⚠ Resumo das divergências (leia primeiro)

| Crença do projeto | O que a doc diz hoje |
|---|---|
| "Faço o Authorization Code **uma vez** e depois só refresh, para sempre." | **Falso desde 2026.** Refresh tokens agora têm **vida de 6 meses**, contados da autorização original. Refresh **não** renova esse prazo. Depois disso: `400 invalid_grant` e você tem que refazer o fluxo na mão. Anunciado em 18/06/2026; apps novos afetados desde essa data, apps existentes desde **20/07/2026**. (Ver seção 2.) |
| "Fev/2026 cortou endpoints em lote (`GET /tracks`, `/artists`, `/albums`)." | **Correto** para apps em Development Mode. Também caíram `/episodes`, `/shows`, `/audiobooks`, `/chapters` em lote. Novos apps a partir de 11/02/2026; apps existentes a partir de 09/03/2026. Apps em Extended Quota não foram afetados. |
| "Fev/2026 cortou popularity, followers etc." | **Correto.** Track: `available_markets`, `linked_from`, `popularity`. Artist: `followers`, `popularity`. Album: `album_group`, `available_markets`, `label`, `popularity`. |
| "Mar/2026 voltou `external_ids`." | **Correto**: em Track **e** em Album. O changelog de março não dá o dia exato. |
| (implícito) `genres` do artista está disponível. | **Atenção:** o changelog de fev/2026 **não** lista `genres` como removido, mas a página de referência do Get Artist hoje marca `genres` como **Deprecated**. A doc não especifica se ele vem vazio para apps em dev mode. Verifique na resposta real. Em Album, `genres` é deprecated e "sempre vazio". |
| "Duas formas de mandar client credentials (Basic vs body)." | A doc do Spotify **só documenta o header `Authorization: Basic`** para o Authorization Code. Mandar `client_id`/`client_secret` no body não aparece na doc do Spotify (ver seção 1.3). |

Outras mudanças de 2026 que importam: limites de Development Mode (Premium obrigatório, até 5 usuários), quota por "buckets" com `429` + `reason: QUOTA_EXCEEDED`, contada **por conta de desenvolvedor** desde jul/2026 (seção 4).

---

## 1. Authorization Code, passo a passo

Visão geral: o fluxo tem duas etapas. (1) O **navegador** do usuário vai até `accounts.spotify.com/authorize`, o usuário aprova, e o Spotify redireciona de volta para a sua `redirect_uri` com um `code` na query string. (2) O **seu programa** (servidor ou script) troca esse `code` por tokens num `POST` para `accounts.spotify.com/api/token`, autenticando-se com o client secret.

Doc: este fluxo é para apps "long-running" que conseguem guardar o client secret com segurança. Para quem não consegue guardar o secret (mobile, SPA), a doc indica o PKCE.

### 1.1 `GET https://accounts.spotify.com/authorize`

| Parâmetro | Obrigatório? | Para que serve (doc) |
|---|---|---|
| `client_id` | Sim | O Client ID do seu app no Dashboard. |
| `response_type` | Sim | Tem que ser `code`. |
| `redirect_uri` | Sim | Para onde o Spotify manda o usuário depois de aprovar/negar. Tem que bater **exatamente** com uma URI registrada no app. |
| `state` | Opcional, mas **fortemente recomendado** | Proteção contra ataques como CSRF (cross-site request forgery). |
| `scope` | Opcional | Lista de scopes separados por **espaço**. Se omitido, só se autoriza acesso a informação pública. |
| `show_dialog` | Opcional | Padrão `false`: quem já aprovou pode ser redirecionado direto, sem ver a tela de consentimento. `true` força a tela de aprovação de novo. |

**Por que `state` importa.** Você gera um valor aleatório, guarda e manda no `/authorize`. O Spotify devolve o mesmo valor no redirect. Doc: compare os dois; se não baterem, rejeite e pare o fluxo. Sem isso, um atacante poderia fazer seu callback aceitar um `code` que **ele** gerou, e seu app passaria a usar a conta dele. Num fluxo feito à mão uma vez no seu PC o risco é baixo. Mesmo assim, é o hábito certo e custa quase nada.

**Regras de Redirect URI (doc, página "Redirect URIs"):**
- HTTPS é obrigatório, **exceto** para endereço de loopback, onde HTTP é permitido.
- Use o IP literal (`http://127.0.0.1:PORT` ou `http://[::1]:PORT`). **`localhost` não é permitido.** A sua `http://127.0.0.1:8888/callback` está de acordo.
- A URI tem que bater exatamente com a registrada. A única exceção: em loopback dá para registrar sem porta e mandar a porta na requisição.
- Essas validações valem para apps novos desde 09/04/2025, com migração dos antigos até novembro/2025.

**Exemplo de URL (quebrada em linhas só para leitura; os valores precisam de URL-encoding):**

```
GET https://accounts.spotify.com/authorize
    ?client_id=SEU_CLIENT_ID
    &response_type=code
    &redirect_uri=http%3A%2F%2F127.0.0.1%3A8888%2Fcallback
    &state=k3J9xQ2vT8...aleatorio
    &scope=user-read-recently-played%20user-top-read%20user-library-read%20playlist-read-private
```

**Redirect de volta (doc):**
- Sucesso: `http://127.0.0.1:8888/callback?code=AQBx...&state=k3J9xQ2vT8...`
- Negado ou erro: `http://127.0.0.1:8888/callback?error=access_denied&state=k3J9xQ2vT8...`

Nota prática: como nada escuta na porta 8888, o navegador vai mostrar "não foi possível conectar". Isso é esperado num fluxo manual: o `code` está na barra de endereço.

### 1.2 Validade do `code`

- **A doc do Spotify não especifica** quanto tempo o `code` vale nem se pode ser usado mais de uma vez (procurei no tutorial do Authorization Code e na página de Authorization).
- Fora da doc do Spotify: a RFC 6749 (OAuth 2.0), §4.1.2, recomenda que o code expire em pouco tempo (**máximo recomendado de 10 minutos**) e diz que o cliente **não pode usá-lo mais de uma vez**. Na prática: troque o code logo e não reaproveite.

### 1.3 `POST https://accounts.spotify.com/api/token` (trocar code por tokens)

Body `application/x-www-form-urlencoded` (doc):

| Parâmetro | Obrigatório | Valor |
|---|---|---|
| `grant_type` | Sim | `authorization_code` |
| `code` | Sim | O code recebido no redirect |
| `redirect_uri` | Sim | Só para validação: tem que ser **idêntica** à usada no `/authorize`. Não há redirect nesta etapa. |

Headers (doc):

| Header | Valor |
|---|---|
| `Authorization` | `Basic <base64(client_id:client_secret)>` |
| `Content-Type` | `application/x-www-form-urlencoded` |

```http
POST /api/token HTTP/1.1
Host: accounts.spotify.com
Authorization: Basic ZjM4ZjAw...base64 de client_id:client_secret...
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=AQBx...&redirect_uri=http%3A%2F%2F127.0.0.1%3A8888%2Fcallback
```

**As "duas formas" de mandar credenciais:**
- **Header Basic:** é a **única** forma documentada pelo Spotify para o Authorization Code, tanto no tutorial do fluxo quanto no de refresh. O tutorial de Client Credentials também só mostra o header.
- **No body (`client_id` + `client_secret` como campos do form):** **a doc do Spotify não documenta isso.** Fora da doc do Spotify: a RFC 6749 §2.3.1 permite esse formato, mas diz que ele "NÃO É RECOMENDADO" e que o servidor não é obrigado a aceitá-lo. Use o header.
- Não confunda com o **PKCE**: nele vai só o `client_id` no body, sem secret e sem header Basic. É outro fluxo.

**Resposta `200 OK` (doc):**

| Campo | Tipo | Significado |
|---|---|---|
| `access_token` | string | Token para chamar a Web API |
| `token_type` | string | Sempre `"Bearer"` |
| `scope` | string | Scopes concedidos, separados por espaço |
| `expires_in` | int | Validade do access token, em segundos |
| `refresh_token` | string | Usado para obter novos access tokens |

```json
{
  "access_token": "BQBLuPRYBQ...BP8stIv5xr-Iwaf4l8eg",
  "token_type": "Bearer",
  "scope": "user-read-recently-played user-top-read user-library-read playlist-read-private",
  "expires_in": 3600,
  "refresh_token": "AQAQfyEFmJJuCvAFh...cG_m-2KTgNDaDMQqjrOa3"
}
```

Dica de estudo: confira se o `scope` da resposta tem tudo que você pediu. Se faltar algum, as chamadas que dependem dele vão dar 403/401.

### 1.4 Erros comuns

Formato (doc, página "API calls"): erros de **autenticação** (endpoints de token) seguem a RFC 6749 e vêm com duas chaves, `error` e `error_description`. Exemplo dado pela doc:

```json
{ "error": "invalid_client", "error_description": "Invalid client secret" }
```

| Situação | O que se sabe |
|---|---|
| **`redirect_uri` não bate** (no `/authorize` ou no `/api/token`) | Doc: a URI tem que bater exatamente com a registrada, incluindo maiúsculas/minúsculas e barra final. **A doc não especifica** a mensagem de erro exata. Causas típicas: `localhost` em vez de `127.0.0.1`, barra final (`/callback/`), porta diferente, `https` em vez de `http`, ou o `redirect_uri` do POST diferente do usado no `/authorize`. |
| **`invalid_grant`** | Doc (tutorial de refresh e blog de jun/2026): o endpoint de token retorna `invalid_grant` quando o **refresh token** está expirado, revogado ou inválido, com status `400 Bad Request`. Para **code** expirado ou já usado, **a doc do Spotify não especifica**. Fora da doc do Spotify: a RFC 6749 §5.2 define `invalid_grant` justamente para code inválido, expirado, revogado ou que não bate com a `redirect_uri`. Espere esse erro nesses casos. |
| **Code já usado** | A doc não especifica o comportamento. Pela RFC, é erro (`invalid_grant`). Se o seu script tentar trocar duas vezes (rodou duas vezes, deu retry), a segunda falha. Refaça o `/authorize`. |
| **`invalid_client`** | Exemplo da doc: secret errado. Também aparece quando o Basic está montado errado (base64 de `id:secret`, com dois-pontos). |
| **`access_denied`** | Vem no redirect (`?error=access_denied`) quando o usuário nega. |
| **403 depois de autenticado** | Doc (Quota modes): em Development Mode, usuário fora da allowlist do app recebe 403. Adicione sua conta em *User Management* no Dashboard. A doc também diz que o **dono do app precisa ter Premium** para o app em dev mode funcionar. |

---

## 2. Refresh token

### 2.1 Requisição (doc)

```http
POST /api/token HTTP/1.1
Host: accounts.spotify.com
Authorization: Basic <base64(client_id:client_secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=AQAQfyEFmJJuCvAFh...cG_m-2KTgNDaDMQqjrOa3
```

- `grant_type=refresh_token` e `refresh_token` são obrigatórios.
- `client_id` no body: doc diz que é obrigatório **só no PKCE**. No Authorization Code (o seu caso) usa-se o header Basic.

Resposta exemplo da doc:

```json
{
  "access_token": "BQBLuPRYBQ...BP8stIv5xr-Iwaf4l8eg",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "AQAQfyEFmJJuCvAFh...cG_m-2KTgNDaDMQqjrOa3",
  "scope": "user-read-email user-read-private"
}
```

### 2.2 A resposta pode trazer um novo `refresh_token`?

Citação da doc (tutorial "Refreshing tokens"):

> "Depending on the grant used to get the initial refresh token, a refresh token might not be included in each response."
>
> "When a refresh token is not returned, continue using the existing token."

**Consequência prática.** A resposta **pode ou não** trazer `refresh_token`. A doc não detalha quais grants trazem e quais não. Então:
- Se vier um `refresh_token` novo, passe a usar o novo e guarde-o.
- Se **não** vier (ou vier vazio), **mantenha o antigo**. Nunca sobrescreva o valor guardado com `None`/vazio, senão a próxima execução fica sem credencial e você tem que refazer o fluxo manual.
- Pense em onde ele fica guardado (`.env`, arquivo, banco) e se a atualização é atômica: se o script cair no meio da escrita, o token pode ficar corrompido.

### 2.3 Quando um refresh token deixa de valer (⚠ mudança de 2026)

Doc (tutorial de refresh) e blog oficial de 18/06/2026:

- "Refresh tokens issued to apps registered in the Developer Dashboard have a lifetime of **6 months**." O prazo conta a partir da **autorização original do usuário**.
- "Refreshing an access token does not extend the refresh token's lifetime." Renovar o access token todo dia **não** prorroga nada.
- Refazer a autorização gera um token com **novos** 6 meses.
- Datas (blog): apps novos afetados desde o anúncio (18/06/2026); apps existentes desde **20/07/2026**. Para apps existentes, refresh tokens com mais de 6 meses são invalidados no próximo uso.
- Vale só para fluxos com usuário (Authorization Code e PKCE). Client Credentials não tem refresh token.
- Também invalida: token **revogado** (por exemplo, o usuário remove o acesso do app na conta Spotify) ou "otherwise invalid". A doc não lista todos os casos.
- Sintoma: `400 Bad Request` com `invalid_grant` no `/api/token`.
- O que a doc manda fazer: **não tentar de novo**. Descarte o token guardado e refaça o Authorization Code. Retry não resolve `invalid_grant`.
- A doc recomenda **guardar o timestamp da autorização** você mesmo, porque o refresh token não expõe a data de emissão. Assim dá para avisar antes de expirar (por exemplo, a partir de 5 meses e meio).

Implicação para o seu desenho: o "fluxo manual uma vez" passa a ser "fluxo manual **a cada 6 meses**", e o pipeline precisa falhar de forma **clara** quando isso acontecer (mensagem "refaça a autorização", em vez de um traceback genérico ou um loop de retries).

---

## 3. Expiração do access token

### 3.1 O que a doc diz

- Doc (Access token): o access token "is valid for 1 hour (3600 seconds)". O `expires_in` vem em segundos (3600 nos exemplos) e se refere **só ao access token** (doc de refresh).
- Ele é enviado em toda chamada como `Authorization: Bearer <access_token>`.
- A resposta de token **não traz o instante de expiração absoluto**, só a duração. Para saber "até quando vale", você calcula `instante_em_que_recebeu + expires_in`. A doc não especifica se há tolerância de relógio.

### 3.2 Como saber que expirou

- Status **401**. Texto da referência dos endpoints (por exemplo, Get Recently Played) para a resposta 401: *"Bad or expired token. This can happen if the user revoked a token or the access token has expired. You should re-authenticate the user."*
- Corpo: os erros "regulares" da Web API (doc, "API calls") vêm como objeto `error` com `status` (int), `message` (string) e, opcionalmente, `reason`:

```json
{
  "error": {
    "status": 401,
    "message": "..."
  }
}
```

- **A doc não especifica o texto exato de `message`** para token expirado. Não faça a lógica depender de comparar strings de mensagem. Use o status.
- Não confunda com o **400 `invalid_grant`** do `/api/token` (refresh token morto, seção 2.3) nem com **403** (scope faltando ou usuário fora da allowlist).

### 3.3 Estratégias (decisão em aberto: escolha você)

| Estratégia | Como funciona | Prós | Contras |
|---|---|---|---|
| **A. Renovar sempre no início da execução** | Cada execução faz um refresh antes de qualquer chamada. | Simplíssimo. Não precisa guardar access token nem horário. Bom para jobs curtos (bem menos de 1 h). | Um refresh por execução, mesmo sem necessidade. Se a execução passar de 1 h (enrich grande com muitos 429/Retry-After), o token expira no meio, a menos que você combine com B ou C. |
| **B. Renovar on-401** | Usa o token que tem. Ao receber 401, renova e repete a requisição **uma** vez. | Renova só quando precisa. Cobre expiração no meio de jobs longos. | Exige lógica de retry. Cuidado para não entrar em loop: se o 401 persistir depois do refresh, o problema é outro (token revogado, scope). Toda expiração "custa" uma requisição falha, que também conta para o rate limit. Precisa distinguir 401 de 403/429. |
| **C. Checar timestamp** | Guarda `expira_em = recebido_em + expires_in` e renova se faltar menos de uma margem (por exemplo, 60 s) antes de cada chamada ou lote. | Evita a requisição falha. Funciona em jobs longos. | Precisa guardar e atualizar estado (access token + horário). Depende de relógio correto e de escolher a margem. Não cobre revogação antecipada; para isso, o 401 ainda precisa de tratamento. |

Combinações são comuns (por exemplo, A ou C para o caso normal + B como rede de segurança). Perguntas para decidir: quanto tempo dura sua execução mais longa? Você guarda o access token entre execuções ou não?

---

## 4. Rate limit

### 4.1 O que a doc diz

- Doc (Rate limits): o limite é calculado pelo número de chamadas do seu app numa **janela móvel de 30 segundos**.
- **A doc não publica o número** de requisições permitidas.
- Ao exceder: **HTTP 429**. A resposta normalmente traz o header **`Retry-After`** com um valor **em segundos**: espere esse tempo antes de chamar de novo. Repare no "normalmente": a doc não garante o header em todo 429.
- Alguns endpoints têm limites próprios (por exemplo, upload de imagem de playlist).
- Texto da referência para a resposta 429: *"The app has exceeded its rate limits."*

### 4.2 Development mode vs. Extended quota

- **Development mode** (padrão de todo app novo): limite de rate **bem mais baixo**. Doc (Quota modes + migração de fev/2026):
  - O dono do app precisa ter **Spotify Premium** ativo; sem isso o app para de funcionar.
  - Até **5 usuários** autenticados por app, que precisam estar na **allowlist** (fora dela: 403).
  - Client IDs por desenvolvedor: 1 em fev/2026, aumentado para **25** em jul/2026.
  - **Quota buckets** (separado do rate limit): endpoints são agrupados em buckets que dividem um limite. Ao estourar: `429` com corpo:
    ```json
    { "error": { "status": 429, "message": "Too many requests", "reason": "QUOTA_EXCEEDED" } }
    ```
    A doc **não diz** quais endpoints ficam em qual bucket nem os números, e avisa que "groupings and limits are subject to change".
  - Desde jul/2026 a quota de dev mode é contada **por conta de desenvolvedor**, não por Client ID. Vários apps seus dividem os mesmos buckets.
- **Extended quota mode**: limite maior, sem teto de usuários. Mas, doc: desde 15/05/2025 só aceita **organizações** (não indivíduos), com requisitos como **250 mil usuários ativos mensais**. **Para um projeto pessoal, não é opção.** Considere dev mode como permanente.

### 4.3 Implicações para um enrich "1 request por ID"

Como os endpoints em lote (`GET /tracks?ids=...` etc.) **não existem mais em dev mode**, enriquecer N tracks, M artistas e K álbuns custa **N + M + K requisições**.

Atenção a uma contradição na doc: a página de Rate limits ainda recomenda "use batch APIs" (cita Get Multiple Albums), mas esses endpoints foram removidos para dev mode na migração de fev/2026. Para o seu app, vale a migração.

Conceitos para estudar e decidir:

- **Não re-enriquecer o que já tem.** Só peça IDs que ainda não estão na dimensão. Depois da carga inicial, o volume diário cai para poucos IDs novos.
- **Aproveite o que já vem de graça.** O objeto `track` dentro do `recently-played` já traz `album` (simplificado, com `album_type`, `release_date`, `release_date_precision`, `total_tracks`) e `artists` (simplificado, com `id` e `name`). Veja a seção 6: talvez só `/artists/{id}` (por causa de `genres`) seja realmente necessário. A decisão é sua.
- **Backoff:** ao receber 429, espere. Se houver `Retry-After`, respeite esse valor. Se não houver, aplique **backoff exponencial** (espera crescente: 1 s, 2 s, 4 s…, normalmente com um teto e um pouco de aleatoriedade, o "jitter"). Para 5xx, a doc diz que o 503 pode ser repetido "after a delay".
- **Distinga os 429:** `reason: QUOTA_EXCEEDED` (quota de bucket) vs. rate limit da janela de 30 s. Esperar alguns segundos resolve o segundo. A doc não especifica em quanto tempo a quota se recupera.
- **Retomar de onde parou (checkpoint):** se o job cair no meio (429 longo, rede, token), a próxima execução não deveria recomeçar do zero. Ideias: gravar cada resultado assim que chega (em vez de tudo no fim); manter uma fila ou lista de "IDs pendentes" derivada de "IDs referenciados nas fatos − IDs já na dimensão"; tornar a gravação **idempotente** (upsert por ID), para que reprocessar não duplique.
- **Ritmo:** um pequeno intervalo entre requisições reduz a chance de 429, já que a janela é de 30 s.

---

## 5. `GET /me/player/recently-played`

```http
GET /v1/me/player/recently-played?limit=50&after=1484811043508 HTTP/1.1
Host: api.spotify.com
Authorization: Bearer BQBLuPRYBQ...
```

- Scope necessário: `user-read-recently-played`.
- Doc: *"Currently doesn't support podcast episodes."* Só músicas.

### 5.1 Parâmetros (doc)

| Parâmetro | Tipo | Detalhes |
|---|---|---|
| `limit` | integer | Máximo de itens. Padrão **20**, máximo **50**. A própria página se contradiz no mínimo: "Minimum: 1" e "Range: 0 - 50". Use de 1 a 50. |
| `after` | integer | **Unix timestamp em milissegundos.** Retorna itens **depois** (sem incluir) dessa posição. |
| `before` | integer | **Unix timestamp em milissegundos.** Retorna itens **antes** (sem incluir) dessa posição. |

**São mutuamente exclusivos?** **Sim.** Doc: "If `after` is specified, `before` must not be specified" (e vice-versa). Use um ou outro (ou nenhum, para pegar os mais recentes).

### 5.2 Resposta (doc)

| Campo | Significado |
|---|---|
| `href` | Link para o endpoint com o resultado completo |
| `limit` | Máximo de itens da resposta |
| `next` | URL da próxima página, ou `null` |
| `cursors.after` / `cursors.before` | **strings**: "the cursor to use as key to find the next/previous page of items". Repare: no request, `after`/`before` são integers em ms; no response, os cursores vêm como **string**. |
| `total` | "The total number of items available to return" |
| `items[]` | Lista de PlayHistoryObject: `track` (objeto Track completo), `played_at`, `context` |

- **`played_at`**: string `date-time`, "The date and time the track was played." Regra geral da doc ("API calls"): timestamps em **ISO 8601, UTC, com offset zero** (`YYYY-MM-DDTHH:MM:SSZ`). **A doc não especifica** se `played_at` traz frações de segundo. Confira numa resposta real antes de definir o parse e o tipo da coluna. Para usar como cursor `after`, converta para epoch em **ms**.
- **`context`**: de onde a música foi tocada. Campos: `type` (por exemplo, `"artist"`, `"playlist"`, `"album"`, `"show"`), `href`, `external_urls.spotify`, `uri` (por exemplo, `spotify:playlist:...`). **A doc não marca `context` como nullable.** Fora da doc: é comum vir `null` (por exemplo, música tocada fora de playlist/álbum/artista). Trate como opcional e verifique.
- O `track` dentro de cada item é o **objeto Track completo** (com `album`, `artists`, `duration_ms`, `explicit`, `external_ids`, `disc_number`, `track_number`…). Ver seção 6.

Exemplo de resposta **resumido** (valores ilustrativos):

```json
{
  "href": "https://api.spotify.com/v1/me/player/recently-played?limit=50",
  "limit": 50,
  "next": "https://api.spotify.com/v1/me/player/recently-played?before=1763900000000&limit=50",
  "cursors": { "after": "1763912345678", "before": "1763900000000" },
  "total": 50,
  "items": [
    {
      "track": {
        "id": "11dFghVXANMlKmJXsNCbNl",
        "name": "Cut To The Feeling",
        "duration_ms": 207959,
        "explicit": false,
        "disc_number": 1,
        "track_number": 1,
        "external_ids": { "isrc": "USUM71703861" },
        "album": {
          "id": "0tGPJ0bkWOUmH7MEOR77qc",
          "name": "Cut To The Feeling",
          "album_type": "single",
          "release_date": "2017-05-26",
          "release_date_precision": "day",
          "total_tracks": 1,
          "artists": [{ "id": "6sFIWsNpZYqfjUpaCgueju", "name": "Carly Rae Jepsen" }]
        },
        "artists": [{ "id": "6sFIWsNpZYqfjUpaCgueju", "name": "Carly Rae Jepsen", "type": "artist" }],
        "is_local": false,
        "type": "track",
        "uri": "spotify:track:11dFghVXANMlKmJXsNCbNl"
      },
      "played_at": "2026-11-23T14:12:25.678Z",
      "context": {
        "type": "playlist",
        "href": "https://api.spotify.com/v1/playlists/37i9dQZF1DXcBWIGoYBM5M",
        "external_urls": { "spotify": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M" },
        "uri": "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"
      }
    }
  ]
}
```

(O exemplo oficial da página usa valores placeholder e ainda mostra campos deprecated como `popularity`, `available_markets`, `linked_from`. Não conte com eles.)

### 5.3 O limite de 50 e a frequência de execução

- Doc: **no máximo 50 itens por requisição.**
- **A doc não especifica** até onde vai o histórico, isto é, se paginar com `before` traz mais que os 50 mais recentes. Fora da doc: relatos da comunidade dizem que o endpoint só expõe as ~50 últimas reproduções. **Teste você mesmo** seguindo `next`/`before` e veja quando para.
- Implicação: se entre duas execuções você ouvir **mais de 50 músicas**, as mais antigas desse intervalo podem se perder. Estime seu pico (por exemplo, 50 músicas × ~3,5 min ≈ 3 h de escuta contínua) e agende o job com folga abaixo disso.
- Padrão incremental (conceito): guardar o maior `played_at` já carregado e usar `after=<esse instante em ms>` na próxima execução. Como `after` é exclusivo ("not including"), não deveria repetir o último item. Mesmo assim, deduplicar por `(played_at, track_id)` na carga é uma proteção barata.

---

## 6. `GET /tracks/{id}`, `/artists/{id}`, `/albums/{id}`: campos atuais e mapeamento

Doc (changelog de fev/2026): os endpoints **individuais** Get Track, Get Artist e Get Album **continuam disponíveis**. Os em lote, não.

```http
GET /v1/tracks/11dFghVXANMlKmJXsNCbNl HTTP/1.1
Host: api.spotify.com
Authorization: Bearer BQBLuPRYBQ...
```

**Atenção ao parâmetro `market`** (doc, Track Relinking): quando você passa `market`, o Spotify pode aplicar *relinking* e devolver **outra versão** da faixa, com **outro `id`** na raiz. O ID original vinha em `linked_from`, mas `linked_from` foi **removido** em fev/2026. Doc também: com um token de usuário, o país da conta tem prioridade sobre `market`. A doc da página de relinking ainda não menciona a remoção de `linked_from`. Conclusão para estudo: sem `linked_from`, se o ID voltar diferente, você não tem como ligar a resposta ao ID que pediu. Pense se precisa de `market` (provavelmente não).

### 6.1 Campos por objeto (estado atual da referência + changelogs)

**Track** (Get Track):
- Vivos: `album`, `artists`, `disc_number`, `duration_ms`, `explicit`, `external_ids` (`isrc`, `ean`, `upc`; voltou em mar/2026), `external_urls`, `href`, `id`, `is_playable`, `restrictions`, `name`, `track_number`, `type`, `uri`, `is_local`.
- Removidos ou deprecated: `available_markets`, `linked_from`, `popularity` (removidos em fev/2026); `preview_url` (deprecated na referência).

**Artist** (Get Artist):
- Vivos: `external_urls`, `href`, `id`, `images`, `name`, `type`, `uri`.
- Removidos: `followers`, `popularity` (fev/2026).
- **`genres`: marcado como Deprecated na referência, mas NÃO listado como removido em nenhum changelog** (fev, mar, mai, jul/2026). Descrição da doc: lista de gêneros do artista; "If not yet classified, the array is empty." **A doc não especifica** se, em dev mode, ele vem preenchido, vazio ou ausente. Valide com chamadas reais antes de depender dele no modelo.

**Album** (Get Album):
- Vivos: `album_type` (`album`/`single`/`compilation`), `total_tracks`, `external_urls`, `href`, `id`, `images`, `name` (pode vir string vazia após takedown), `release_date`, `release_date_precision` (`year`/`month`/`day`), `restrictions`, `type`, `uri`, `artists`, `tracks` (paginado), `copyrights`, `external_ids` (voltou em mar/2026).
- Removidos ou deprecated: `album_group`, `available_markets`, `label`, `popularity` (removidos em fev/2026); `genres` (deprecated, "always empty").

### 6.2 Mapeamento para o seu modelo

**`dim_track`** (fonte: `GET /tracks/{id}` **ou** o `track` dentro do recently-played, que é o mesmo objeto Track)

| Coluna | Campo da API | Observação |
|---|---|---|
| `track_id` | `id` | |
| `name` | `name` | |
| `album_id` | `album.id` | |
| `duration_ms` | `duration_ms` | integer, ms |
| `explicit` | `explicit` | Doc: `false` também quando "unknown" |
| `isrc` | `external_ids.isrc` | Disponível de novo desde mar/2026. A doc não garante presença em toda faixa: trate como anulável. |
| `track_number` | `track_number` | Número **dentro do disco** |
| `disc_number` | `disc_number` | "usually 1" |

**`dim_artist`** (fonte: `GET /artists/{id}`)

| Coluna | Campo da API | Observação |
|---|---|---|
| `artist_id` | `id` | |
| `name` | `name` | Também vem no artista simplificado do track, sem chamada extra |
| `genres` | `genres` (array de string) | **Deprecated** (ver 6.1). Só existe no artista **completo**: o artista simplificado dentro do track não tem `genres`. É o único motivo forte para chamar `/artists/{id}`. Como modelar um array (coluna array/JSON vs. tabela ponte de gêneros) é decisão sua. |

**`dim_album`** (fonte: `GET /albums/{id}` **ou** o `album` simplificado dentro do track)

| Coluna | Campo da API | Observação |
|---|---|---|
| `album_id` | `id` / `album.id` | |
| `name` | `name` / `album.name` | |
| `album_type` | `album_type` | `album` / `single` / `compilation` |
| `release_date` | `release_date` | String com precisão variável: `"1981"`, `"1981-12"` ou `"1981-12-15"` |
| `release_date_precision` | `release_date_precision` | `year` / `month` / `day`. Doc ("API calls"): datas imprecisas vêm acompanhadas desse campo. Pense em como guardar `release_date`: string crua vs. DATE preenchido + precisão. |
| `total_tracks` | `total_tracks` | |

Todas as colunas de `dim_album` existem no **album simplificado** que vem dentro do Track (doc, schema do Get Track). Se não precisar de `copyrights`, `external_ids` (UPC) ou da lista de faixas, `/albums/{id}` pode ser dispensável. Cada chamada evitada pesa no rate limit (seção 4).

**`bridge_track_artist`** (fonte: `track.artists[]`)

| Coluna | Campo da API | Observação |
|---|---|---|
| `track_id` | `track.id` | |
| `artist_id` | `artists[i].id` | |
| `position` | índice `i` no array `artists` | **A doc não especifica** que a ordem do array tem significado (por exemplo, "primeiro = artista principal"). Ela só diz "The artists who performed the track." Usar o índice como `position` é uma convenção sua: documente-a como tal. |

Lembre também que `track.artists` (quem toca a faixa) e `album.artists` (artistas do álbum) são listas diferentes. A ponte do seu modelo é track→artista.

---

## 7. Links consultados

Autorização e tokens
- Authorization (visão geral dos fluxos): https://developer.spotify.com/documentation/web-api/concepts/authorization
- Authorization Code Flow (tutorial): https://developer.spotify.com/documentation/web-api/tutorials/code-flow
- Refreshing tokens: https://developer.spotify.com/documentation/web-api/tutorials/refreshing-tokens
- Client Credentials Flow (só para comparar o envio de credenciais): https://developer.spotify.com/documentation/web-api/tutorials/client-credentials-flow
- Access token: https://developer.spotify.com/documentation/web-api/concepts/access-token
- Redirect URIs: https://developer.spotify.com/documentation/web-api/concepts/redirect_uri
- Scopes: https://developer.spotify.com/documentation/web-api/concepts/scopes
- Blog, "Introducing refresh token expiration" (18/06/2026): https://developer.spotify.com/blog/2026-06-18-refresh-token-expiration

Limites e modos
- Rate limits: https://developer.spotify.com/documentation/web-api/concepts/rate-limits
- Quota modes: https://developer.spotify.com/documentation/web-api/concepts/quota-modes
- API calls (status codes, formato de erro, timestamps): https://developer.spotify.com/documentation/web-api/concepts/api-calls
- Track Relinking: https://developer.spotify.com/documentation/web-api/concepts/track-relinking

Changelogs e migração 2026
- Changelog fev/2026: https://developer.spotify.com/documentation/web-api/references/changes/february-2026
- Changelog mar/2026: https://developer.spotify.com/documentation/web-api/references/changes/march-2026
- Changelog mai/2026 (novo campo `account_id` no usuário): https://developer.spotify.com/documentation/web-api/references/changes/may-2026
- Changelog jul/2026 (25 Client IDs, quota por conta, corpo do 429 com `QUOTA_EXCEEDED`): https://developer.spotify.com/documentation/web-api/references/changes/july-2026
- Guia de migração fev/2026 (Dev Mode): https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide
- Blog, "Update on Developer Access and Platform Security" (06/02/2026): https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security

Referência de endpoints
- Get Recently Played Tracks: https://developer.spotify.com/documentation/web-api/reference/get-recently-played
- Get Track: https://developer.spotify.com/documentation/web-api/reference/get-track
- Get Artist: https://developer.spotify.com/documentation/web-api/reference/get-an-artist
- Get Album: https://developer.spotify.com/documentation/web-api/reference/get-an-album

Fontes externas (fora da doc do Spotify, citadas só onde a doc é omissa)
- RFC 6749 (OAuth 2.0): §2.3.1 (credenciais no body), §4.1.2 (validade/uso único do code), §5.2 (`invalid_grant`): https://datatracker.ietf.org/doc/html/rfc6749
