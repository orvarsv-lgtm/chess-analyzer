"""
Performance metrics computation for chess games.
Computes CPL, game phases, blunder frequency, and performance trends.

Phase definitions (by move number, 1-indexed):
  - Opening: moves 1–10
  - Middlegame: moves 11–30
  - Endgame: move 31+

CPL (Centipawn Loss): average loss per move, not per game.
Lower CPL indicates stronger, more accurate play.
"""

import pandas as pd


def classify_move_phase(move_index: int) -> str:
    """
    Classify a move's game phase based on move number (1-indexed).
    
    Args:
        move_index: 0-indexed move number (0 = move 1, 1 = move 2, etc.)
        
    Returns:
        "opening" | "middlegame" | "endgame"
        
    Definitions:
      - Opening: moves 1–10 (indices 0–9)
      - Middlegame: moves 11–30 (indices 10–29)
      - Endgame: move 31+ (indices 30+)
    """
    move_num = move_index + 1  # Convert to 1-indexed
    
    if move_num <= 10:
        return "opening"
    elif move_num <= 30:
        return "middlegame"
    else:
        return "endgame"


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
    
    cp_losses = [m.get("cp_loss", 0) for m in move_evals if m.get("cp_loss", 0) > 0]
    
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
            cp_loss = move_eval.get("cp_loss", 0)
            blunder_type = move_eval.get("blunder_type", None)
            eval_after = move_eval.get("eval_after", None)
            
            # Collect CP losses
            if cp_loss > 0:
                phases[phase]["cp_losses"].append(cp_loss)
            
            # Count blunders/mistakes
            if blunder_type == "blunder":
                phases[phase]["blunders"] += 1
            elif blunder_type == "mistake":
                phases[phase]["mistakes"] += 1
            
            # Track total moves
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
        }
    
    all_game_cpls = []
    recent_game_cpls = []
    total_blunders = 0
    total_mistakes = 0
    total_moves = 0
    blunder_by_phase = {"opening": 0, "middlegame": 0, "endgame": 0}
    blunder_losses = []  # Track all blunder CP losses for severity analysis
    piece_losses = {}  # map piece name -> list of cp_loss values
    
    for idx, game_data in enumerate(games_data):
        move_evals = game_data.get("move_evals", [])
        
        game_cpl = compute_game_cpl(move_evals)
        all_game_cpls.append(game_cpl)
        
        # Last 3 games for "recent" trend
        if idx >= len(games_data) - 3:
            recent_game_cpls.append(game_cpl)
        
        # Count blunders/mistakes and moves
        for move_eval in move_evals:
            blunder_type = move_eval.get("blunder_type")
            phase = move_eval.get("phase", "opening")
            cp_loss = move_eval.get("cp_loss", 0)
            piece_name = move_eval.get("piece", "Unknown")
            
            if blunder_type == "blunder":
                total_blunders += 1
                blunder_losses.append(cp_loss)  # Track for severity
                blunder_by_phase[phase] += 1
            elif blunder_type == "mistake":
                total_mistakes += 1
            total_moves += 1
            # Track piece cp losses for any inaccuracy/mistake/blunder
            if cp_loss > 0:
                piece_losses.setdefault(piece_name, []).append(cp_loss)
    
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
    if total_blunders == 0:
        weakest_phase = "Accuracy (no major blunders detected)"
    else:
        weakest_phase = max(phase_stats.keys(), key=lambda p: phase_stats[p]["cpl"])

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
