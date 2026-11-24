"""Carga inicial: export JSON do Spotify (Extended Streaming History) -> fact_plays.

Responsabilidade: ler os arquivos JSON do export em data/raw/ e gravar em
fact_plays com source='export'. É a carga histórica; o ingest_recent.py
cuida do incremental daí em diante.

Este arquivo é um esqueleto. A lógica é sua.
"""

# TODO: descobrir o formato do export quando ele chegar: quais arquivos,
#       quais campos (ts, ms_played, spotify_track_uri, reason_start, ...).
# TODO: listar e ler os JSON de data/raw/.
# TODO: mapear cada registro para as colunas de fact_plays.
#       Pergunta: como extrair o track_id da URI? E quando não há URI
#       (podcast, faixa local, registro antigo)?
# TODO: normalizar played_at para ISO8601 UTC no mesmo formato da API,
#       senão a PK (played_at, track_name) não casa entre as fontes.
# TODO: dedup — registros no mesmo segundo existem; a PK composta resolve?
# TODO: quando a mesma execução também veio da API, qual fonte ganha?
#       — ver Decisões de projeto no README.
# TODO: definir o critério de "play" (ms_played mínimo?) ANTES de olhar
#       números — ver Decisões de projeto no README. Filtrar aqui na carga
#       ou só na análise?
# TODO: enfileirar na enrich_queue os track IDs sem metadata.
# TODO: performance — inserir linha a linha ou em lote (executemany) numa
#       transação? O export pode ter centenas de milhares de linhas.


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
