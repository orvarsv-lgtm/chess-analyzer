import io
import chess.pgn
import requests
from .opening_classifier import classify_opening


def fetch_lichess_pgn(username, max_games=50):
    """
    Fetch PGN games for a user from Lichess API.
    
    Args:
        username: Lichess username
        max_games: Maximum number of games to fetch (default 50)
        
    Returns:
        Raw PGN text string
        
    Raises:
        ValueError: If username doesn't exist
        Exception: If other API errors occur
    """
    url = f"https://lichess.org/api/games/user/{username}"
    params = {
        "max": max_games,
        "moves": True,
    }
    headers = {
        "Accept": "application/x-chess-pgn",
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 404:
            raise ValueError(f"❌ Username '{username}' not found on Lichess. Please check the username.")
        
        if response.status_code != 200:
            raise Exception(f"❌ Lichess API error: {response.status_code} {response.reason}")
        
        return response.text
    
    except requests.exceptions.Timeout:
        raise Exception("❌ Request timed out. Lichess API took too long to respond.")
    except requests.exceptions.ConnectionError:
        raise Exception("❌ Connection error. Unable to reach Lichess API.")
    except ValueError:
        raise  # Re-raise ValueError (invalid username)
    except Exception:
        raise  # Re-raise other exceptions


def parse_pgn(pgn_text, username):
    games = []
    pgn_io = io.StringIO(pgn_text)

    while True:
        game = chess.pgn.read_game(pgn_io)
        if game is None:
            break

        white = game.headers.get("White", "")
        black = game.headers.get("Black", "")
        result = game.headers.get("Result", "")

        if username == white:
            color = "white"
            score = "win" if result == "1-0" else "loss" if result == "0-1" else "draw"
        else:
            color = "black"
            score = "win" if result == "0-1" else "loss" if result == "1-0" else "draw"

        # Extract moves as space-separated SAN notation
        moves_list = []
        board = chess.Board()
        for move in game.mainline_moves():
            moves_list.append(board.san(move))
            board.push(move)
        moves_pgn = " ".join(moves_list).strip()

        # Parse elo headers if present
        def _parse_elo(val):
            try:
                return int(val)
            except Exception:
                return ""

        white_elo = _parse_elo(game.headers.get("WhiteElo", ""))
        black_elo = _parse_elo(game.headers.get("BlackElo", ""))

        # Determine user's elo for this game
        elo = white_elo if username == white else black_elo

        opening_hdr = game.headers.get("Opening", "").strip()
        if not opening_hdr:
            opening_hdr = " ".join(moves_list[:4]) if moves_list else ""

        # Classify opening based on moves
        opening_name = classify_opening(moves_pgn)

        game_info = {
            "color": color,
            "score": score,
            "opening": opening_hdr,
            "opening_name": opening_name,
            "moves": game.end().board().fullmove_number,
            "date": game.headers.get("Date", ""),
            "time_control": game.headers.get("TimeControl", ""),
            "moves_pgn": moves_pgn,
            "white_elo": white_elo,
            "black_elo": black_elo,
            "elo": elo,
        }

        games.append(game_info)

    return games
