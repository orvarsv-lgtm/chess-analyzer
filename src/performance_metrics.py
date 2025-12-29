"""src.performance_metrics

Performance metrics computation for chess games.
Computes CPL, game phases, blunder frequency, and performance trends.

Phase classifier (hybrid, deterministic, non-overlapping):
- Opening if move_number ≤ 10 OR either side has 2+ undeveloped minor pieces
- Endgame if total non-pawn material ≤ ENDGAME_THRESHOLD
- Otherwise Middlegame

Every move must fall into exactly one phase; we assert this to avoid silent bugs.
"""

import pandas as pd

ENDGAME_THRESHOLD = 13  # roughly R+minor vs R+minor (non-pawn material)
DEBUG_PHASES = False


def compute_strengths_weaknesses(games_data: list) -> dict:
    """Derive deterministic strengths/weaknesses from existing engine output.

    This is purely heuristic and uses only already-computed per-move data:
    - phase CPL
    - blunder/mistake rates
    - piece-associated error concentration
    - blunder subtype concentration

    Returns:
        {
          "strengths": [str, ...],
          "weaknesses": [str, ...],
          "signals": { ... }  # small numeric facts used to justify output
        }
    """
    from collections import Counter

    strengths: list[str] = []
    weaknesses: list[str] = []

    overall = compute_overall_cpl(games_data)
    phase_stats = aggregate_cpl_by_phase(games_data)

    baseline_cpl = float(overall.get("overall_cpl") or 0.0)
    blunders_per_100 = float(overall.get("blunders_per_100") or 0.0)
    mistakes_per_100 = float(overall.get("mistakes_per_100") or 0.0)
    total_blunders = int(overall.get("total_blunders") or 0)

    # Phase relative performance (relative-to-self baseline; deterministic)
    if baseline_cpl > 0:
        strong_ratio = 0.85
        weak_ratio = 1.15
        for phase in ("opening", "middlegame", "endgame"):
            ps = phase_stats.get(phase, {})
            cpl = float(ps.get("cpl") or 0.0)
            if cpl <= baseline_cpl * strong_ratio and ps.get("total_moves", 0) > 0:
                if phase == "opening":
                    strengths.append("Strong opening preparation")
                elif phase == "middlegame":
                    strengths.append("Stable middlegame decision-making")
                else:
                    strengths.append("Solid endgame technique (relative accuracy)")
            if cpl >= baseline_cpl * weak_ratio and ps.get("total_moves", 0) > 0:
                if phase == "opening":
                    weaknesses.append("Opening accuracy drops early")
                elif phase == "middlegame":
                    weaknesses.append("Middlegame accuracy drops under complexity")
                else:
                    weaknesses.append("Endgame accuracy drops in simplified positions")

    # Blunder / mistake rate signals
    if blunders_per_100 <= 1.0 and total_blunders > 0:
        strengths.append("Low blunder rate")
    if blunders_per_100 >= 3.0:
        weaknesses.append("High blunder rate (frequent large eval swings)")
    if mistakes_per_100 >= 6.0:
        weaknesses.append("Many medium-strength mistakes (evaluation drift)")

    # Concentrated blunder phase
    blunder_dist = overall.get("blunder_distribution", {}) or {}
    if total_blunders > 0:
        by_phase = {p: int(blunder_dist.get(p, 0) or 0) for p in ("opening", "middlegame", "endgame")}
        phase_top, phase_top_count = max(by_phase.items(), key=lambda kv: kv[1])
        if phase_top_count / total_blunders >= 0.60:
            if phase_top == "opening":
                weaknesses.append("Blunders cluster in the opening")
            elif phase_top == "middlegame":
                weaknesses.append("Blunders cluster in the middlegame")
            else:
                weaknesses.append("Blunders cluster in the endgame")

    # Piece-related error concentration (uses existing "piece" field)
    blunder_piece_counts: Counter[str] = Counter()
    piece_cp_losses: dict[str, list[int]] = {}
    blunder_subtypes: Counter[str] = Counter()

    for g in games_data:
        for m in g.get("move_evals", []) or []:
            piece = m.get("piece") or "Unknown"
            cp_loss = int(m.get("cp_loss") or 0)
            if cp_loss > 0:
                piece_cp_losses.setdefault(piece, []).append(cp_loss)

            if m.get("blunder_type") == "blunder":
                blunder_piece_counts[piece] += 1
                blunder_subtypes[m.get("blunder_subtype") or "Unknown"] += 1

    if total_blunders > 0 and blunder_piece_counts:
        top_piece, top_piece_count = blunder_piece_counts.most_common(1)[0]
        if top_piece_count / total_blunders >= 0.45 and top_piece in {"Queen", "King", "Rook", "Bishop", "Knight"}:
            if top_piece == "Queen":
                weaknesses.append("Frequent queen-related errors")
            elif top_piece == "King":
                weaknesses.append("King safety errors appear repeatedly")
            else:
                weaknesses.append(f"Errors often involve the {top_piece.lower()}")

    # Blunder subtype concentration
    if total_blunders > 0 and blunder_subtypes:
        top_subtype, top_subtype_count = blunder_subtypes.most_common(1)[0]
        if top_subtype_count / total_blunders >= 0.45 and top_subtype != "Unknown":
            if top_subtype == "Hanging piece":
                weaknesses.append("Piece-hanging blunders (tactical oversight)")
            elif top_subtype == "Missed tactic":
                weaknesses.append("Missed tactics in sharp positions")
            elif top_subtype == "King safety":
                weaknesses.append("King safety collapses under pressure")
            elif top_subtype == "Endgame technique":
                weaknesses.append("Endgame technique issues")

    # Best/worst piece signal (existing compute_overall_cpl output)
    best_piece = overall.get("best_piece")
    worst_piece = overall.get("worst_piece")
    if best_piece and best_piece != "N/A":
        strengths.append(f"Reliable {str(best_piece).lower()} play")
    if worst_piece and worst_piece != "N/A" and worst_piece != best_piece:
        weaknesses.append(f"Unreliable {str(worst_piece).lower()} play")

    # De-duplicate while preserving order
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for it in items:
            if it and it not in seen:
                out.append(it)
                seen.add(it)
        return out

    strengths = _dedupe(strengths)
    weaknesses = _dedupe(weaknesses)

    # Keep output bounded and readable
    strengths = strengths[:4]
    weaknesses = weaknesses[:4]

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "signals": {
            "baseline_cpl": baseline_cpl,
            "blunders_per_100": blunders_per_100,
            "mistakes_per_100": mistakes_per_100,
            "total_blunders": total_blunders,
        },
    }


def _normalize_player_color(value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip().lower()
    if v in {"white", "w"}:
        return "white"
    if v in {"black", "b"}:
        return "black"
    return None


def compute_player_cpl(move_evals: list, player_color: str | None) -> float:
    """Average CPL for the player's own moves only (not opponent moves)."""
    pc = _normalize_player_color(player_color)
    if not move_evals or pc is None:
        return 0.0

    want = "White" if pc == "white" else "Black"
    cp_losses = [m.get("cp_loss", 0) for m in move_evals if m.get("color") == want and m.get("cp_loss", 0) > 0]
    if not cp_losses:
        return 0.0
    return float(sum(cp_losses) / len(cp_losses))


def compute_opening_intelligence(games_data: list) -> dict:
    """Compute per-opening performance and simple opening-phase pattern flags.

    Uses only existing game_info + move_evals (no engine calls).

    Patterns (per game, player-focused):
    - early_queen: player moved queen by their move <= 6
    - pawn_pushes: player played >=4 pawn moves by their move <= 6
    - king_safety_neglect: no castling, or castled after move >= 11 (only if game is long enough)
    """
    from collections import Counter

    opening_stats: dict[str, dict] = {}
    pattern_counts = Counter({"early_queen": 0, "pawn_pushes": 0, "king_safety_neglect": 0})
    games_count = 0

    for g in games_data or []:
        info = g.get("game_info", {}) or {}
        opening_name = info.get("opening_name") or "Unknown"
        score = info.get("score")
        player_color = _normalize_player_color(info.get("color"))
        move_evals = g.get("move_evals", []) or []
        if not move_evals:
            continue

        games_count += 1
        player_cpl = compute_player_cpl(move_evals, player_color)

        rec = opening_stats.setdefault(
            opening_name,
            {
                "games": 0,
                "wins": 0,
                "cpls": [],
                "patterns": Counter({"early_queen": 0, "pawn_pushes": 0, "king_safety_neglect": 0}),
            },
        )
        rec["games"] += 1
        if score == "win":
            rec["wins"] += 1
        rec["cpls"].append(player_cpl)

        # Player move filter
        want = None
        if player_color == "white":
            want = "White"
        elif player_color == "black":
            want = "Black"

        player_moves = [m for m in move_evals if (want is None or m.get("color") == want)]

        # Pattern: early queen
        early_queen = any((m.get("piece") == "Queen" and int(m.get("move_num") or 999) <= 6) for m in player_moves)

        # Pattern: premature pawn pushes
        pawn_pushes_count = sum(1 for m in player_moves if m.get("piece") == "Pawn" and int(m.get("move_num") or 999) <= 6)
        pawn_pushes = pawn_pushes_count >= 4

        # Pattern: king safety neglect (late/no castling)
        castle_moves = [m for m in player_moves if str(m.get("san") or "") in {"O-O", "O-O-O"}]
        castle_move_num = min((int(m.get("move_num") or 999) for m in castle_moves), default=None)
        game_len = len(move_evals)
        king_safety_neglect = False
        if game_len >= 20:  # only meaningful in non-miniature games
            if castle_move_num is None:
                king_safety_neglect = True
            elif castle_move_num >= 11:
                king_safety_neglect = True

        for key, flag in (
            ("early_queen", early_queen),
            ("pawn_pushes", pawn_pushes),
            ("king_safety_neglect", king_safety_neglect),
        ):
            if flag:
                rec["patterns"][key] += 1
                pattern_counts[key] += 1

    # Finalize per-opening aggregates
    openings_out: dict[str, dict] = {}
    for name, rec in opening_stats.items():
        games = int(rec.get("games") or 0)
        wins = int(rec.get("wins") or 0)
        cpls = rec.get("cpls") or []
        avg_cpl = float(sum(cpls) / len(cpls)) if cpls else 0.0
        win_rate = float((wins / games) * 100.0) if games > 0 else 0.0
        patterns = rec.get("patterns") or Counter()
        openings_out[name] = {
            "games": games,
            "wins": wins,
            "win_rate": round(win_rate, 1),
            "avg_player_cpl": round(avg_cpl, 1),
            "patterns": {k: int(patterns.get(k, 0)) for k in ("early_queen", "pawn_pushes", "king_safety_neglect")},
        }

    # Identify best/worst openings with a small stability threshold
    eligible = [(name, data) for name, data in openings_out.items() if data.get("games", 0) >= 2]
    best = None
    worst = None
    if eligible:
        best = min(eligible, key=lambda kv: (kv[1].get("avg_player_cpl", 0.0), -kv[1].get("win_rate", 0.0)))
        worst = max(eligible, key=lambda kv: (kv[1].get("avg_player_cpl", 0.0), -kv[1].get("win_rate", 0.0)))

    pattern_rates = {}
    for k in ("early_queen", "pawn_pushes", "king_safety_neglect"):
        pattern_rates[k] = round((pattern_counts.get(k, 0) / games_count * 100.0), 1) if games_count > 0 else 0.0

    return {
        "openings": openings_out,
        "best_opening": {"name": best[0], **best[1]} if best else None,
        "worst_opening": {"name": worst[0], **worst[1]} if worst else None,
        "pattern_rates": pattern_rates,
        "games_count": games_count,
    }


def _undeveloped_minors(board) -> tuple[int, int]:
    """Return (white, black) undeveloped minor counts (still on home squares).

    Home squares for knights: b1/g1, b8/g8
    Home squares for bishops: c1/f1, c8/f8
    """
    import chess

    white_squares = {chess.B1, chess.G1, chess.C1, chess.F1}
    black_squares = {chess.B8, chess.G8, chess.C8, chess.F8}
    white = sum(1 for sq in white_squares if (p := board.piece_at(sq)) and p.color == chess.WHITE and p.piece_type in (chess.KNIGHT, chess.BISHOP))
    black = sum(1 for sq in black_squares if (p := board.piece_at(sq)) and p.color == chess.BLACK and p.piece_type in (chess.KNIGHT, chess.BISHOP))
    return white, black


def _total_non_pawn_material(board) -> int:
    """Total material (both sides) excluding pawns and kings."""
    import chess

    values = {
        chess.KNIGHT: 3,
        chess.BISHOP: 3,
        chess.ROOK: 5,
        chess.QUEEN: 9,
    }
    total = 0
    for piece_type, val in values.items():
        total += val * (len(board.pieces(piece_type, chess.WHITE)) + len(board.pieces(piece_type, chess.BLACK)))
    return total


def _king_is_active(board, color) -> bool:
    """Heuristic king activity: king steps into central four ranks/files."""
    import chess

    center_squares = {
        chess.D4, chess.E4, chess.D5, chess.E5,
        chess.C4, chess.F4, chess.C5, chess.F5,
    }
    king_sq = board.king(color)
    return king_sq is not None and king_sq in center_squares


def classify_phase(board, move_number: int) -> str:
    """Classify game phase from board state and move number (non-overlapping).

    Opening: move_number ≤ 10 OR either side has 2+ undeveloped minor pieces
    Endgame: total non-pawn material ≤ ENDGAME_THRESHOLD
    Otherwise: Middlegame
    """
    import chess

    white_undev, black_undev = _undeveloped_minors(board)
    total_non_pawn = _total_non_pawn_material(board)
    pawns_total = len(board.pieces(chess.PAWN, chess.WHITE)) + len(board.pieces(chess.PAWN, chess.BLACK))
    queens_total = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))

    if move_number <= 12 or white_undev >= 2 or black_undev >= 2:
        return "opening"

    # Endgame heuristics: material thinning, queen trade, low pawn count, king activity
    if total_non_pawn <= ENDGAME_THRESHOLD:
        return "endgame"
    if queens_total == 0 and total_non_pawn <= ENDGAME_THRESHOLD + 3:
        return "endgame"
    if pawns_total <= 6 and total_non_pawn <= ENDGAME_THRESHOLD + 9:
        return "endgame"
    if queens_total == 0 and (_king_is_active(board, chess.WHITE) or _king_is_active(board, chess.BLACK)):
        return "endgame"

    return "middlegame"


def classify_phase_stable(board, move_number: int, previous_phase: str | None) -> str:
    """Stable (non-oscillating) phase classification with sanity logging."""
    order = {"opening": 0, "middlegame": 1, "endgame": 2}
    candidate = classify_phase(board, move_number)

    if previous_phase and order.get(candidate, 1) < order.get(previous_phase, 1):
        # Prevent regression but log only when debugging to avoid noise
        if DEBUG_PHASES:
            print(f"[phase-change] prevented regression {previous_phase} -> {candidate} at move {move_number}")
        return previous_phase

    if previous_phase and candidate != previous_phase and DEBUG_PHASES:
        print(f"[phase-change] {previous_phase} -> {candidate} at move {move_number}")

    if candidate not in order:
        raise ValueError(f"Unclassified phase at move {move_number}")
    return candidate


def compute_game_cpl(move_evals: list) -> float:
    """
    Compute average Centipawn Loss (CPL) for a game.
    
    CPL = average of cp_loss across all moves where cp_loss > 0
    
    Args:
        move_evals: List of dicts with keys: cp_loss
        
    Returns:
        Average CPL for the game (float), or 0.0 if no losses
    """
    if not move_evals:
        return 0.0
    
    cp_losses = []
    for m in move_evals:
        # Skip mate evaluations to avoid polluting CPL
        if m.get("is_mate_before") or m.get("is_mate_after"):
            continue
        loss_weighted = m.get("cp_loss_weighted")
        loss_raw = m.get("cp_loss", 0)
        loss = loss_weighted if loss_weighted is not None else loss_raw
        if loss and loss > 0:
            cp_losses.append(loss)
    
    if not cp_losses:
        return 0.0
    
    return sum(cp_losses) / len(cp_losses)


def aggregate_cpl_by_phase(games_data: list) -> dict:
    """
    Aggregate CPL and statistics by game phase.
    
    For each phase:
      - CPL: average centipawn loss per move (lower is better)
      - Blunders/Mistakes: total count
      - Games: number of games where this phase occurred
      - Advantage: % of games with evaluation ≥ +1.0 (winning) at phase end
      - Total Moves: total moves in this phase across all games
    
    Args:
        games_data: List of game dicts from engine analysis
                   
    Returns:
        Dict with phase stats
    """
    phases = {
        "opening": {"cp_losses": [], "blunders": 0, "mistakes": 0, "game_count": 0, "games_with_advantage": 0, "total_moves": 0},
        "middlegame": {"cp_losses": [], "blunders": 0, "mistakes": 0, "game_count": 0, "games_with_advantage": 0, "total_moves": 0},
        "endgame": {"cp_losses": [], "blunders": 0, "mistakes": 0, "game_count": 0, "games_with_advantage": 0, "total_moves": 0},
    }
    
    for game_data in games_data:
        move_evals = game_data.get("move_evals", [])
        
        # Track which phases occurred and their final evals
        phase_seen = {"opening": False, "middlegame": False, "endgame": False}
        phase_final_eval = {"opening": None, "middlegame": None, "endgame": None}
        
        for move_eval in move_evals:
            phase = move_eval.get("phase", "opening")
            cp_loss = move_eval.get("cp_loss_weighted")
            cp_loss_raw = move_eval.get("cp_loss", 0)
            blunder_type = move_eval.get("blunder_type", None)
            eval_after = move_eval.get("eval_after", None)
            is_mate = move_eval.get("is_mate_before") or move_eval.get("is_mate_after")
            
            # Collect CP losses
            if cp_loss is None:
                cp_loss = cp_loss_raw

            if not is_mate and cp_loss and cp_loss > 0:
                phases[phase]["cp_losses"].append(cp_loss)
            
            # Count blunders/mistakes
            if blunder_type == "blunder":
                phases[phase]["blunders"] += 1
            elif blunder_type == "mistake":
                phases[phase]["mistakes"] += 1
            
            # Track total moves (each move must belong to exactly one phase)
            phases[phase]["total_moves"] += 1
            
            # Update final eval (keep last)
            if eval_after is not None:
                phase_final_eval[phase] = eval_after
            
            phase_seen[phase] = True
        
        # Count games and check for advantage
        for phase, seen in phase_seen.items():
            if seen:
                phases[phase]["game_count"] += 1
                if phase_final_eval[phase] is not None and phase_final_eval[phase] >= 100:
                    phases[phase]["games_with_advantage"] += 1
    
    # Sanity: ensure we accounted for moves and no phase with zero moves if seen
    total_moves_accounted = sum(data["total_moves"] for data in phases.values())
    assert total_moves_accounted >= 0

    # Compute final metrics
    result = {}
    for phase, data in phases.items():
        # CPL
        avg_cpl = sum(data["cp_losses"]) / len(data["cp_losses"]) if data["cp_losses"] else 0.0
        
        # Advantage percentage (eval ≥ +1.0 at phase end)
        if data["game_count"] >= 2:
            adv_pct = (data["games_with_advantage"] / data["game_count"]) * 100.0
            advantage_str = f"{adv_pct:.1f}%"
        else:
            advantage_str = "N/A"
        
        result[phase] = {
            "cpl": round(avg_cpl, 1),
            "blunders": data["blunders"],
            "mistakes": data["mistakes"],
            "games": data["game_count"],
            "advantage": advantage_str,
            "total_moves": data["total_moves"],
        }

        # No phase should have zero moves if its game_count > 0
        if data["game_count"] > 0:
            assert data["total_moves"] > 0, f"Phase {phase} has games but zero moves"

    # Ensure move coverage across phases
    if total_moves_accounted == 0:
        raise AssertionError("No moves were aggregated into phases")
    
    return result


def compute_overall_cpl(games_data: list) -> dict:
    """
    Compute overall CPL metrics across all games.
    
    Args:
        games_data: List of game dicts from engine analysis
        
    Returns:
        Dict with overall metrics including real trend comparison and blunder severity
    """
    if not games_data:
        return {
            "overall_cpl": 0.0,
            "recent_cpl": 0.0,
            "trend": "N/A",
            "trend_reason": "insufficient history",
            "total_blunders": 0,
            "total_mistakes": 0,
            "total_moves": 0,
            "blunders_per_100": 0.0,
            "mistakes_per_100": 0.0,
            "weakest_phase": "N/A",
            "blunder_distribution": {},
            "avg_blunder_severity": 0.0,
            "max_blunder_severity": 0,
            "phase_relative_cpl": {},
            "endgame_advantage": {},
            "conversion_difficulty": {},
            "mate_missed_count": 0,
            "forced_loss_count": 0,
            "equal_blunders": 0,
        }
    
    all_game_cpls = []
    recent_game_cpls = []
    total_blunders = 0
    total_mistakes = 0
    total_moves = 0
    blunder_by_phase = {"opening": 0, "middlegame": 0, "endgame": 0}
    blunder_losses = []  # Track all blunder CP losses for severity analysis
    piece_losses = {}  # map piece name -> list of cp_loss values
    conversion_swings = []  # cp_loss when already ahead (conversion difficulty)
    winning_conversion_chances = 0
    severe_conversion_errors = 0
    mate_missed_count = 0
    forced_loss_count = 0
    equal_blunders = 0
    endgame_advantage_buckets = {
        "winning": {"games": 0, "cp_losses": [], "conversions": 0},
        "drawing": {"games": 0, "cp_losses": []},
        "losing": {"games": 0, "cp_losses": []},
    }
    
    for idx, game_data in enumerate(games_data):
        move_evals = game_data.get("move_evals", [])
        game_info = game_data.get("game_info", {}) or {}
        
        game_cpl = compute_game_cpl(move_evals)
        all_game_cpls.append(game_cpl)
        
        # Last 3 games for "recent" trend
        if idx >= len(games_data) - 3:
            recent_game_cpls.append(game_cpl)
        
        # Count blunders/mistakes and moves
        endgame_cp_losses = []
        endgame_final_eval = None
        for move_eval in move_evals:
            blunder_type = move_eval.get("blunder_type")
            phase = move_eval.get("phase", "opening")
            cp_loss_weighted = move_eval.get("cp_loss_weighted")
            cp_loss_raw = move_eval.get("cp_loss", 0)
            piece_name = move_eval.get("piece", "Unknown")
            eval_before = move_eval.get("eval_before")
            eval_after = move_eval.get("eval_after")
            move_color = move_eval.get("color")
            eval_before_player = None
            if eval_before is not None:
                if move_color == "White":
                    eval_before_player = eval_before
                elif move_color == "Black":
                    eval_before_player = -eval_before
                else:
                    eval_before_player = eval_before
            is_mate = move_eval.get("is_mate_before") or move_eval.get("is_mate_after")
            mate_missed = move_eval.get("missed_mate")
            forced_loss = move_eval.get("forced_loss")

            if mate_missed:
                mate_missed_count += 1
            if forced_loss:
                forced_loss_count += 1

            if blunder_type == "blunder":
                total_blunders += 1
                if not is_mate:
                    blunder_losses.append(cp_loss_raw)  # severity uses raw
                blunder_by_phase[phase] += 1
                # Equal-position blunders: eval around 0.0 before the move (player POV)
                if eval_before_player is not None and -100 <= eval_before_player <= 100:
                    equal_blunders += 1
            elif blunder_type == "mistake":
                total_mistakes += 1
            total_moves += 1
            # Track piece cp losses for any inaccuracy/mistake/blunder
            if cp_loss_raw > 0 and not is_mate:
                piece_losses.setdefault(piece_name, []).append(cp_loss_raw)

            # Conversion difficulty: when already ahead from mover POV (eval_before_player >= +1.0)
            if eval_before_player is not None and eval_before_player >= 100 and cp_loss_raw > 0 and not is_mate:
                winning_conversion_chances += 1
                conversion_swings.append(cp_loss_weighted or cp_loss_raw)
                eval_after_player = None
                if eval_after is not None:
                    eval_after_player = eval_after if move_color == "White" else -eval_after
                if eval_after_player is not None and eval_after_player < 50:
                    severe_conversion_errors += 1

            # Endgame advantage-aware stats
            if phase == "endgame":
                if cp_loss_weighted and cp_loss_weighted > 0 and not is_mate:
                    endgame_cp_losses.append(cp_loss_weighted)
                if eval_after is not None:
                    endgame_final_eval = eval_after

        if endgame_final_eval is not None:
            bucket = "drawing"
            if endgame_final_eval >= 100:
                bucket = "winning"
            elif endgame_final_eval <= -100:
                bucket = "losing"

            bucket_data = endgame_advantage_buckets.get(bucket)
            if bucket_data is not None:
                bucket_data["games"] += 1
                bucket_data["cp_losses"].extend(endgame_cp_losses)
                if bucket == "winning":
                    bucket_data["conversions"] += 1 if game_info.get("score") == "win" else 0
    
    overall = sum(all_game_cpls) / len(all_game_cpls) if all_game_cpls else 0.0
    recent = sum(recent_game_cpls) / len(recent_game_cpls) if recent_game_cpls else overall
    
    # Trend: compare recent N games vs previous N games (real comparison)
    n = min(3, len(all_game_cpls) // 2)  # Use 3 games or half if fewer
    trend = "N/A"
    trend_reason = "insufficient history"
    
    if len(all_game_cpls) >= 6 and n >= 2:
        recent_games = all_game_cpls[-n:]
        previous_games = all_game_cpls[-2*n:-n]
        
        recent_avg = sum(recent_games) / len(recent_games)
        prev_avg = sum(previous_games) / len(previous_games)
        
        diff = prev_avg - recent_avg  # positive = improving
        
        if diff > 10:  # Improvement threshold
            trend = "↑ improving"
            trend_reason = f"recent {n} games avg {recent_avg:.1f} vs prior {n} games avg {prev_avg:.1f}"
        elif diff < -10:  # Decline threshold
            trend = "↓ declining"
            trend_reason = f"recent {n} games avg {recent_avg:.1f} vs prior {n} games avg {prev_avg:.1f}"
        else:
            trend = "→ stable"
            trend_reason = f"minimal change ({abs(diff):.1f} cp difference)"
    elif len(all_game_cpls) >= 4:
        trend = "N/A"
        trend_reason = "insufficient game history"
    
    # Blunders/mistakes per 100 moves
    blunders_per_100 = (total_blunders / total_moves * 100) if total_moves > 0 else 0.0
    mistakes_per_100 = (total_mistakes / total_moves * 100) if total_moves > 0 else 0.0
    
    # Blunder severity (average and max)
    avg_blunder_severity = sum(blunder_losses) / len(blunder_losses) if blunder_losses else 0.0
    max_blunder_severity = max(blunder_losses) if blunder_losses else 0
    
    # Determine weakest phase
    phase_stats = aggregate_cpl_by_phase(games_data)
    total_moves_phase = sum((phase_stats[p].get("total_moves", 0) for p in phase_stats))
    assert total_moves_phase == total_moves, "Phase move totals must match analyzed moves"
    weakest_phase = max(phase_stats.keys(), key=lambda p: phase_stats[p]["cpl"])
    if total_blunders == 0:
        weakest_phase = "Accuracy (no major blunders detected)"

    # Phase-relative CPL ratios (phase CPL vs overall CPL)
    phase_relative_cpl = {}
    for phase_name, stats in phase_stats.items():
        phase_cpl = float(stats.get("cpl") or 0.0)
        phase_relative_cpl[phase_name] = round(phase_cpl / overall, 2) if overall > 0 else None

    # Endgame advantage buckets summary
    endgame_advantage_stats = {}
    for bucket, data in endgame_advantage_buckets.items():
        games = int(data.get("games") or 0)
        cp_losses = data.get("cp_losses", [])
        avg_cpl = sum(cp_losses) / len(cp_losses) if cp_losses else 0.0
        summary = {"games": games, "avg_cpl": round(avg_cpl, 1)}
        if bucket == "winning":
            conversions = int(data.get("conversions") or 0)
            summary["conversions"] = conversions
            summary["conversion_rate"] = round((conversions / games) * 100.0, 1) if games > 0 else "N/A"
        endgame_advantage_stats[bucket] = summary

    # Conversion difficulty summary
    conversion_difficulty = {
        "winning_positions": winning_conversion_chances,
        "avg_loss_when_ahead": round(sum(conversion_swings) / len(conversion_swings), 1) if conversion_swings else 0.0,
        "severe_conversion_errors": severe_conversion_errors,
        "severe_error_rate": round((severe_conversion_errors / winning_conversion_chances) * 100.0, 1) if winning_conversion_chances > 0 else 0.0,
    }

    # Compute best and worst piece usage by average cp_loss (lower = better)
    best_piece = "N/A"
    worst_piece = "N/A"
    if piece_losses:
        piece_avg = {p: (sum(v) / len(v)) for p, v in piece_losses.items() if v}
        if piece_avg:
            # best -> min avg loss, worst -> max avg loss
            best_piece = min(piece_avg.keys(), key=lambda k: piece_avg[k])
            worst_piece = max(piece_avg.keys(), key=lambda k: piece_avg[k])
    
    return {
        "overall_cpl": round(overall, 1),
        "recent_cpl": round(recent, 1),
        "trend": trend,
        "trend_reason": trend_reason,
        "total_blunders": total_blunders,
        "total_mistakes": total_mistakes,
        "total_moves": total_moves,
        "blunders_per_100": round(blunders_per_100, 1),
        "mistakes_per_100": round(mistakes_per_100, 1),
        "weakest_phase": weakest_phase,
        "blunder_distribution": blunder_by_phase,
        "avg_blunder_severity": round(avg_blunder_severity, 0),
        "max_blunder_severity": int(max_blunder_severity),
        "best_piece": best_piece,
        "worst_piece": worst_piece,
        "phase_relative_cpl": phase_relative_cpl,
        "endgame_advantage": endgame_advantage_stats,
        "conversion_difficulty": conversion_difficulty,
        "mate_missed_count": mate_missed_count,
        "forced_loss_count": forced_loss_count,
        "equal_blunders": equal_blunders,
    }


def compute_opening_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute performance stats per opening."""
    if "opening_name" not in df.columns:
        return pd.DataFrame()
    
    stats = df.groupby("opening_name").agg({
        "score": [lambda x: (x == "win").sum(), len],
        "elo": "mean",
    }).round(1)
    
    stats.columns = ["wins", "games", "avg_elo"]
    stats["win_rate"] = (stats["wins"] / stats["games"] * 100).round(1)
    stats = stats.sort_values(["games", "win_rate"], ascending=[False, False])
    
    return stats


def compute_time_control_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute performance stats per time control."""
    if "time_control" not in df.columns:
        return pd.DataFrame()
    
    df_tc = df[df["time_control"].notna() & (df["time_control"] != "")]
    
    if df_tc.empty:
        return pd.DataFrame()
    
    stats = df_tc.groupby("time_control").agg({
        "score": [lambda x: (x == "win").sum(), len],
    }).round(1)
    
    stats.columns = ["wins", "games"]
    stats["win_rate"] = (stats["wins"] / stats["games"] * 100).round(1)
    stats = stats.sort_values("games", ascending=False)
    
    return stats
