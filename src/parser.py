import chess.pgn
import io
from .opening_classifier import classify_opening


def parse_pgn(pgn_text):
    """
    Parse PGN text and return a list of game dictionaries.
    """
    games = []
    pgn_io = io.StringIO(pgn_text)

    while True:
        game = chess.pgn.read_game(pgn_io)
        if game is None:
            break
        
        # Extract moves as space-separated SAN notation
        moves_list = []
        board = game.board()
        for move in game.mainline_moves():
            moves_list.append(board.san(move))
            board.push(move)
        moves_pgn = " ".join(moves_list).strip()

        # Populate opening header or fallback to first 4 SAN moves
        opening = game.headers.get("Opening", "").strip()
        if not opening:
            opening = " ".join(moves_list[:4]) if moves_list else ""

        # Classify opening based on moves
        opening_name = classify_opening(moves_pgn)

        # Parse Elo headers if present
        def _parse_elo(val):
            try:
                return int(val)
            except Exception:
                return ""

        white_elo = _parse_elo(game.headers.get("WhiteElo", ""))
        black_elo = _parse_elo(game.headers.get("BlackElo", ""))

        game_info = {
            "white": game.headers.get("White", ""),
            "black": game.headers.get("Black", ""),
            "result": game.headers.get("Result", ""),
            "opening": opening,
            "opening_name": opening_name,
            "moves": game.end().board().fullmove_number,
            "moves_pgn": moves_pgn,
            "white_elo": white_elo,
            "black_elo": black_elo,
        }
        games.append(game_info)

    return games
