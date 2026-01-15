import io
import re
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
        "clocks": True,  # Request per-move clock times
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

        # Extract moves with clock times
        moves_list = []
        move_clocks = []  # List of (move_number, color, san, clock_seconds)
        board = chess.Board()
        node = game
        move_num = 0
        
        while node.variations:
            next_node = node.variation(0)
            move = next_node.move
            san = board.san(move)
            moves_list.append(san)
            
            # Determine whose move this is
            mover_color = "white" if board.turn == chess.WHITE else "black"
            ply = len(moves_list)
            move_number = (ply + 1) // 2  # 1, 1, 2, 2, 3, 3...
            
            # Extract clock time from comment (format: [%clk H:MM:SS] or [%clk M:SS])
            clock_seconds = None
            comment = next_node.comment or ""
            clock_match = re.search(r'\[%clk\s+(\d+):(\d+):(\d+)\]', comment)
            if clock_match:
                hours, mins, secs = int(clock_match.group(1)), int(clock_match.group(2)), int(clock_match.group(3))
                clock_seconds = hours * 3600 + mins * 60 + secs
            else:
                # Try M:SS format
                clock_match = re.search(r'\[%clk\s+(\d+):(\d+)\]', comment)
                if clock_match:
                    mins, secs = int(clock_match.group(1)), int(clock_match.group(2))
                    clock_seconds = mins * 60 + secs
            
            move_clocks.append({
                'move_number': move_number,
                'ply': ply,
                'color': mover_color,
                'san': san,
                'clock_seconds': clock_seconds,  # None if no clock data
            })
            
            board.push(move)
            node = next_node
        
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

        # Classify opening based on moves; fall back to PGN header when unknown
        opening_name = classify_opening(moves_pgn)
        if not opening_name or opening_name == "Unknown":
            opening_name = opening_hdr or "Unknown"
        
        # Check if we have clock data
        has_clock_data = any(m['clock_seconds'] is not None for m in move_clocks)

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
            "move_clocks": move_clocks,  # Per-move clock data
            "has_clock_data": has_clock_data,
        }

        games.append(game_info)

    return games
