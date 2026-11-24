"""Cliente HTTP mínimo da Web API: autenticação, retry e rate limit.

- 401: força um refresh do access token e tenta uma vez.
- 429: espera o `Retry-After` (ou backoff exponencial quando o header não
  vem). Se o Spotify pedir uma espera maior que MAX_WAIT_S, como acontece no
  QUOTA_EXCEEDED, desiste com RateLimitError. Assim o processo não fica
  dormindo por horas, e o enrich retoma depois de onde parou.
- 5xx e erro de rede: backoff exponencial.
"""

import logging
import time

import requests

from auth import get_access_token

API_BASE = "https://api.spotify.com/v1"
MAX_ATTEMPTS = 5
MAX_WAIT_S = 120

log = logging.getLogger(__name__)
_session = requests.Session()


class RateLimitError(RuntimeError):
    """O Spotify pediu para esperar mais do que vale a pena esperar agora."""


def api_get(path: str, params: dict | None = None) -> dict:
    """GET em API_BASE + path; devolve o JSON ou levanta exceção."""
    force_refresh = False
    for attempt in range(MAX_ATTEMPTS):
        backoff = 2 ** attempt
        token = get_access_token(force_refresh=force_refresh)
        try:
            resp = _session.get(
                API_BASE + path,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            log.warning("Erro de rede em %s (%s); nova tentativa em %ss.", path, exc, backoff)
            time.sleep(backoff)
            continue

        if resp.ok:
            return resp.json()

        if resp.status_code == 401 and not force_refresh:
            log.info("401 em %s; renovando o access token.", path)
            force_refresh = True
            continue

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else backoff
            if wait > MAX_WAIT_S:
                raise RateLimitError(
                    f"429 em {path}: Retry-After de {wait}s excede {MAX_WAIT_S}s. {resp.text}"
                )
            log.warning("429 em %s; esperando %ss.", path, wait)
            time.sleep(wait)
            continue

        if resp.status_code >= 500:
            log.warning("%s em %s; nova tentativa em %ss.", resp.status_code, path, backoff)
            time.sleep(backoff)
            continue

        resp.raise_for_status()

    raise RuntimeError(f"GET {path} falhou após {MAX_ATTEMPTS} tentativas.")
