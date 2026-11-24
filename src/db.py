"""Conexão com o SQLite e inicialização do schema.

Uso:
    python src/db.py   # cria o banco (se não existir) e aplica sql/schema.sql
"""

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "sql" / "schema.sql"
DEFAULT_DB_PATH = "data/spotify.db"

load_dotenv(REPO_ROOT / ".env")


def get_db_path() -> Path:
    """Caminho do banco a partir de DB_PATH (.env); relativo = relativo à raiz do repo."""
    path = Path(os.getenv("DB_PATH") or DEFAULT_DB_PATH)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def get_connection() -> sqlite3.Connection:
    """Abre uma conexão com foreign keys ligadas e linhas acessíveis por nome."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Executa sql/schema.sql (idempotente: usa CREATE ... IF NOT EXISTS)."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


if __name__ == "__main__":
    with get_connection() as conn:
        init_schema(conn)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
    conn.close()
    print(f"Banco: {get_db_path()}")
    print("Tabelas:")
    for row in tables:
        print(f"  - {row['name']}")
