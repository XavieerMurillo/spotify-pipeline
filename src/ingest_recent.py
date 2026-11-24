"""Carga incremental: GET /me/player/recently-played -> fact_plays.

A API devolve só as últimas 50 execuções. Cada rodada busca essas 50 e grava
com INSERT OR IGNORE, então a PK (played_at, track_name) descarta o que já foi
carregado e rodar de novo é seguro. Para não perder execuções, o script precisa
rodar antes que você ouça 50 faixas novas. Se a execução mais antiga do lote for
mais nova que a última já gravada, sobrou um buraco, e o script avisa.

Regras (ver README):
- `played_at` é gravado como 'YYYY-MM-DDTHH:MM:SSZ' (UTC, sem ms), o mesmo
  formato do export.
- Corte temporal: linhas com played_at <= max(played_at) do export são
  ignoradas, porque naquele período o export é a fonte de verdade.
- Arquivos locais (sem ID do Spotify) ficam de fora, como no export.
- O objeto `track` já traz tudo de dim_track, dim_album, do nome do artista e
  da ponte, então as dimensões são preenchidas aqui mesmo, sem gastar request
  de enrich. A política para dimensões já existentes ainda está em aberto; por
  ora vale a primeira versão vista (ON CONFLICT DO NOTHING).

Uso:
    python src/ingest_recent.py
"""

import logging
import sqlite3
import sys
from datetime import datetime, timezone

from auth import AuthError
from db import get_connection, init_schema
from spotify_api import api_get

log = logging.getLogger("ingest_recent")


def normalize_played_at(raw: str) -> str:
    """'2026-11-24T00:16:25.143Z' -> '2026-11-24T00:16:25Z'."""
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def max_played_at(conn: sqlite3.Connection, source: str) -> str | None:
    row = conn.execute(
        "SELECT max(played_at) FROM fact_plays WHERE source = ?", (source,)
    ).fetchone()
    return row[0]


def upsert_dimensions(conn: sqlite3.Connection, track: dict) -> None:
    album = track["album"]
    conn.execute(
        """INSERT INTO dim_album
               (album_id, name, album_type, release_date, release_date_precision, total_tracks)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(album_id) DO NOTHING""",
        (
            album["id"],
            album["name"],
            album.get("album_type"),
            album.get("release_date"),
            album.get("release_date_precision"),
            album.get("total_tracks"),
        ),
    )
    conn.execute(
        """INSERT INTO dim_track
               (track_id, name, album_id, duration_ms, explicit, isrc, track_number, disc_number)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(track_id) DO NOTHING""",
        (
            track["id"],
            track["name"],
            album["id"],
            track.get("duration_ms"),
            int(bool(track.get("explicit"))),
            (track.get("external_ids") or {}).get("isrc"),
            track.get("track_number"),
            track.get("disc_number"),
        ),
    )
    # genres fica NULL: o GET /artists/{id} não devolve mais o campo.
    for position, artist in enumerate(track["artists"]):
        if not artist.get("id"):
            continue
        conn.execute(
            "INSERT INTO dim_artist (artist_id, name) VALUES (?, ?) "
            "ON CONFLICT(artist_id) DO NOTHING",
            (artist["id"], artist["name"]),
        )
        conn.execute(
            "INSERT OR IGNORE INTO bridge_track_artist (track_id, artist_id, position) "
            "VALUES (?, ?, ?)",
            (track["id"], artist["id"], position),
        )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        data = api_get("/me/player/recently-played", params={"limit": 50})
    except AuthError as exc:
        log.error("%s", exc)
        return 1
    items = data.get("items", [])
    log.info("API devolveu %d execuções.", len(items))

    conn = get_connection()
    try:
        init_schema(conn)
        export_cutoff = max_played_at(conn, "export")
        last_api = max_played_at(conn, "api")

        rows, skipped_local, skipped_cutoff = [], 0, 0
        for item in items:
            track = item["track"]
            played_at = normalize_played_at(item["played_at"])
            if track.get("is_local") or not track.get("id"):
                skipped_local += 1
                continue
            if export_cutoff and played_at <= export_cutoff:
                skipped_cutoff += 1
                continue
            context = item.get("context") or {}
            rows.append((
                played_at,
                track["id"],
                track["name"],
                track["artists"][0]["name"],
                context.get("type"),
                context.get("uri"),
            ))
            upsert_dimensions(conn, track)

        before = conn.total_changes
        conn.executemany(
            """INSERT OR IGNORE INTO fact_plays
                   (played_at, track_id, track_name, artist_name, context_type, context_uri, source)
               VALUES (?, ?, ?, ?, ?, ?, 'api')""",
            rows,
        )
        inserted = conn.total_changes - before
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    log.info(
        "fact_plays: %d novas, %d já existiam, %d arquivos locais, %d antes do corte do export.",
        inserted, len(rows) - inserted, skipped_local, skipped_cutoff,
    )

    if last_api and len(items) == 50:
        oldest = min(normalize_played_at(i["played_at"]) for i in items)
        if oldest > last_api:
            log.warning(
                "Possível buraco: última execução gravada %s, mais antiga do lote %s. "
                "Rode o script com mais frequência.",
                last_api, oldest,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
