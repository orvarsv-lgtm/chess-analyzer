# src/analytics/endgame_analyzer.py
"""Module 2: Endgame Material-Type Breakdown.

Identify which types of endgames cause the most problems.

Endgame Classes:
- King + pawns (no pieces except kings)
- Rook endgames (rooks + pawns only)
- Minor piece endgames (bishops/knights + pawns)
- Queen endgames (queens + pawns)
- Mixed (rook + minor, etc.)

Metrics per type:
- Games count
- Positions/moves count
- Avg CPL
- Blunder rate
- Win rate from equal/winning positions
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import chess

from .schemas import EndgameMaterialBreakdown, EndgameTypeStats

if TYPE_CHECKING:
    from typing import Any

# Thresholds
ENDGAME_MATERIAL_THRESHOLD = 13  # non-pawn material to consider endgame
BLUNDER_CP_THRESHOLD = 300
WINNING_EVAL_THRESHOLD = 200  # consider winning if eval >= +200cp


def _ceil_int(x: float) -> int:
    return int(math.ceil(x))


def _count_pieces(board: chess.Board, color: chess.Color) -> dict[str, int]:
    """Count pieces for a color."""
    return {
        "pawns": len(board.pieces(chess.PAWN, color)),
        "knights": len(board.pieces(chess.KNIGHT, color)),
        "bishops": len(board.pieces(chess.BISHOP, color)),
        "rooks": len(board.pieces(chess.ROOK, color)),
        "queens": len(board.pieces(chess.QUEEN, color)),
    }


def _non_pawn_material(board: chess.Board) -> int:
    """Total non-pawn material on board."""
    values = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    total = 0
    for pt, val in values.items():
        total += val * (len(board.pieces(pt, chess.WHITE)) + len(board.pieces(pt, chess.BLACK)))
    return total


def classify_endgame_type(board: chess.Board) -> str | None:
    """Classify endgame type based on material.

    Returns None if not an endgame (too much material).
    """
    if _non_pawn_material(board) > ENDGAME_MATERIAL_THRESHOLD:
        return None

    white = _count_pieces(board, chess.WHITE)
    black = _count_pieces(board, chess.BLACK)

    total_queens = white["queens"] + black["queens"]
    total_rooks = white["rooks"] + black["rooks"]
    total_minors = white["knights"] + white["bishops"] + black["knights"] + black["bishops"]

    # Pure K+P endgame
    if total_queens == 0 and total_rooks == 0 and total_minors == 0:
        return "king_pawn"

    # Queen endgame (queens, possibly pawns, no other pieces)
    if total_queens > 0 and total_rooks == 0 and total_minors == 0:
        return "queen_endgames"

    # Rook endgame (rooks, possibly pawns, no queens/minors)
    if total_rooks > 0 and total_queens == 0 and total_minors == 0:
        return "rook_endgames"

    # Minor piece endgame (bishops/knights, possibly pawns, no rooks/queens)
    if total_minors > 0 and total_rooks == 0 and total_queens == 0:
        return "minor_piece"

    # Mixed endgame (combination)
    return "mixed"


def analyze_endgames(games_data: list[dict[str, Any]]) -> EndgameMaterialBreakdown:
    """Analyze endgame performance by material type.

    Args:
        games_data: List of game dicts with move_evals.

    Returns:
        EndgameMaterialBreakdown with stats per endgame type.
    """
    result = EndgameMaterialBreakdown()

    # Accumulators per type
    stats: dict[str, dict[str, Any]] = {
        "king_pawn": {"games": set(), "positions": 0, "cp_losses": [], "blunders": 0, "wins_from_winning": 0, "losses_from_winning": 0},
        "rook_endgames": {"games": set(), "positions": 0, "cp_losses": [], "blunders": 0, "wins_from_winning": 0, "losses_from_winning": 0},
        "minor_piece": {"games": set(), "positions": 0, "cp_losses": [], "blunders": 0, "wins_from_winning": 0, "losses_from_winning": 0},
        "queen_endgames": {"games": set(), "positions": 0, "cp_losses": [], "blunders": 0, "wins_from_winning": 0, "losses_from_winning": 0},
        "mixed": {"games": set(), "positions": 0, "cp_losses": [], "blunders": 0, "wins_from_winning": 0, "losses_from_winning": 0},
    }

    for game_idx, game in enumerate(games_data):
        move_evals = game.get("move_evals", []) or []
        game_info = game.get("game_info", {}) or {}
        game_result = game_info.get("score")  # "win", "loss", "draw"
        player_color = game_info.get("color", "").lower()

        # Track if we were winning at endgame entry for this game
        endgame_types_in_game: set[str] = set()
        was_winning_at_entry: dict[str, bool] = {}

        for m in move_evals:
            phase = str(m.get("phase") or "")
            if phase != "endgame":
                continue

            fen = m.get("fen") or m.get("fen_after")
            if not fen:
                continue

            try:
                board = chess.Board(fen)
            except Exception:
                continue

            eg_type = classify_endgame_type(board)
            if eg_type is None:
                continue

            # Track game for this type
            stats[eg_type]["games"].add(game_idx)
            stats[eg_type]["positions"] += 1

            # CPL
            cp_loss = int(m.get("cp_loss") or 0)
            if cp_loss > 0:
                stats[eg_type]["cp_losses"].append(min(cp_loss, 2000))  # cap outliers

            # Blunders
            if cp_loss >= BLUNDER_CP_THRESHOLD:
                stats[eg_type]["blunders"] += 1

            # Track if we were winning when entering this endgame type
            if eg_type not in endgame_types_in_game:
                endgame_types_in_game.add(eg_type)
                eval_val = m.get("eval_before") or m.get("score_cp")
                if eval_val is not None:
                    try:
                        ev = int(eval_val)
                        # Adjust for player color
                        if player_color == "black":
                            ev = -ev
                        was_winning_at_entry[eg_type] = ev >= WINNING_EVAL_THRESHOLD
                    except Exception:
                        pass

        # After processing game, update win/loss from winning
        for eg_type in endgame_types_in_game:
            if was_winning_at_entry.get(eg_type, False):
                if game_result == "win":
                    stats[eg_type]["wins_from_winning"] += 1
                elif game_result == "loss":
                    stats[eg_type]["losses_from_winning"] += 1

    # Build result
    def _build_stats(key: str) -> EndgameTypeStats:
        s = stats[key]
        games = len(s["games"])
        positions = s["positions"]
        cp_losses = s["cp_losses"]
        blunders = s["blunders"]
        wins = s["wins_from_winning"]
        losses = s["losses_from_winning"]

        avg_cpl = _ceil_int(sum(cp_losses) / len(cp_losses)) if cp_losses else 0
        blunder_rate = _ceil_int((blunders / positions) * 100) if positions > 0 else 0
        conversion = _ceil_int((wins / (wins + losses)) * 100) if (wins + losses) > 0 else 0

        return EndgameTypeStats(
            games=games,
            positions=positions,
            avg_cpl=avg_cpl,
            blunder_count=blunders,
            blunder_rate_pct=blunder_rate,
            wins_from_winning=wins,
            losses_from_winning=losses,
            conversion_rate_pct=conversion,
        )

    result.king_pawn = _build_stats("king_pawn")
    result.rook_endgames = _build_stats("rook_endgames")
    result.minor_piece = _build_stats("minor_piece")
    result.queen_endgames = _build_stats("queen_endgames")
    result.mixed = _build_stats("mixed")

    # Determine weakest/strongest by avg CPL (lower is better)
    type_cpls = [
        ("king_pawn", result.king_pawn),
        ("rook_endgames", result.rook_endgames),
        ("minor_piece", result.minor_piece),
        ("queen_endgames", result.queen_endgames),
        ("mixed", result.mixed),
    ]
    # Filter to types with actual data
    type_cpls = [(name, st) for name, st in type_cpls if st.positions > 0]

    if type_cpls:
        sorted_by_cpl = sorted(type_cpls, key=lambda x: x[1].avg_cpl)
        result.strongest_endgame_type = sorted_by_cpl[0][0]
        result.weakest_endgame_type = sorted_by_cpl[-1][0]

    return result
