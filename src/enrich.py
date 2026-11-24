"""Enrich: IDs sem metadata -> dim_track, dim_artist, dim_album, bridge_track_artist.

Responsabilidade: consumir a enrich_queue e buscar metadata de cada ID na
Web API. Sem endpoints em lote (fev/2026), é 1 request por ID
(GET /tracks/{id}, /artists/{id}, /albums/{id}), então o processo precisa
ser incremental e retomável: se morrer no meio (ex.: 429), roda de novo e
continua de onde parou.

Este arquivo é um esqueleto. A lógica é sua.
"""

# TODO: obter um access token via auth.py (e se ele expirar no meio de uma
#       rodada longa? — ver "quando renovar" nas Decisões de projeto).
# TODO: ler os itens pendentes da enrich_queue. Em que ordem processar
#       (tracks primeiro, porque revelam artist_id e album_id)?
# TODO: para cada track: buscar, gravar em dim_track e bridge_track_artist
#       (position 0 = artista principal) e enfileirar artistas/álbum novos.
# TODO: para cada artist/album: buscar e gravar na dimensão correspondente.
#       Pergunta: genres é lista — como guardar no TEXT (JSON array)?
# TODO: em sucesso, remover o item da fila; em erro, incrementar attempts e
#       gravar last_error. Depois de quantas tentativas desistir?
# TODO: rate limit — respeitar o 429 / Retry-After. Esperar e tentar de novo,
#       ou parar a rodada e deixar para a próxima?
# TODO: commit a cada item ou a cada lote? O que acontece com o progresso se
#       o processo cair entre um commit e outro?
# TODO: política de refresh das dimensões (nunca, a cada 90 dias, só artista?)
#       — ver Decisões de projeto no README.


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
