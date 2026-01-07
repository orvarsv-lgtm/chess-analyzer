#!/usr/bin/env python
"""
Interactive Chess Analyzer: Fetch Lichess games → Engine analysis → Reporting
"""
import sys
import os
import time
import glob
try:
    import pandas as pd
except ModuleNotFoundError:
    print("\n❌ Missing dependency: pandas")
    print("This usually means you're running outside the project's virtual environment.")
    print("\nRun one of:")
    print("  1) source .venv/bin/activate && python main.py")
    print("  2) ./.venv/bin/python main.py")
    print("\nOr install deps into the venv:")
    print("  ./.venv/bin/pip install -r requirements.txt")
    raise
from datetime import datetime

# Import from src package
from src.lichess_api import fetch_lichess_pgn, parse_pgn
from src.engine_analysis import analyze_game_detailed
from src.performance_metrics import (
    compute_overall_cpl,
    aggregate_cpl_by_phase,
    compute_game_cpl,
    compute_strengths_weaknesses,
    compute_opening_intelligence,
)
from src.phase2 import analyze_phase2

from src.analytics.peer_benchmark import benchmark_from_games_data
from src.analytics.population_store import append_population_record


def _choose_primary_issue(overall: dict, phase_stats: dict) -> str:
    """Deterministic priority for coaching focus to avoid contradictions.

    Priority:
    1) Phase with ≥50% of blunders
    2) Conversion failures (only if severe)
    3) Mate misses
    4) Blunders in equal positions
    5) Raw CPL if unusually high
    """

    def _safe_rate(val):
        try:
            return float(val)
        except Exception:
            return None

    total_blunders = int(overall.get('total_blunders') or 0)
    blunder_dist = overall.get('blunder_distribution', {}) or {}
    if total_blunders > 0 and blunder_dist:
        max_phase = max(blunder_dist.keys(), key=lambda p: blunder_dist[p])
        pct = (blunder_dist[max_phase] / total_blunders * 100.0) if total_blunders else 0.0
        if pct >= 50.0:
            return f"{max_phase.capitalize()} blunders drive losses"

    conv = overall.get('conversion_difficulty', {}) or {}
    win_bucket = (overall.get('endgame_advantage', {}) or {}).get('winning', {}) or {}
    conv_games = int(win_bucket.get('games', 0) or 0)
    conv_rate = _safe_rate(win_bucket.get('conversion_rate'))
    severe_conv = int(conv.get('severe_conversion_errors', 0) or 0)
    avg_loss_ahead = float(conv.get('avg_loss_when_ahead', 0.0) or 0.0)
    endgame_blunders = blunder_dist.get('endgame', 0) if blunder_dist else 0
    endgame_blunder_ratio = (endgame_blunders / total_blunders) if total_blunders else 0.0
    if (
        avg_loss_ahead > 250.0
        and severe_conv >= 3
        and endgame_blunder_ratio > 0.4
    ):
        return "Converting winning endgames"

    if int(overall.get('mate_missed_count', 0) or 0) > 0:
        return "Missed forced mates"

    equal_blunders = int(overall.get('equal_blunders', 0) or 0)
    if equal_blunders >= 2:
        return "Blunders in equal positions"

    overall_cpl = float(overall.get('overall_cpl') or 0.0)
    if overall_cpl >= 150.0:
        return "High centipawn loss overall"

    # Fallback: weakest phase by CPL if available
    if phase_stats:
        weakest_phase = max(phase_stats.keys(), key=lambda p: float(phase_stats[p].get('cpl') or 0.0))
        return f"Weakest phase: {weakest_phase.capitalize()}"
    return "No dominant issue detected"


def load_pgn_file(path: str) -> str:
    """Load PGN text from a local file (no API, no scraping)."""
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _looks_like_pgn(path: str) -> bool:
    return os.path.isfile(path) and path.lower().endswith('.pgn')


def find_pgn_files(search_dirs: list[str]) -> list[str]:
    """Search for .pgn files (non-recursive) in given directories."""
    results: list[str] = []
    for d in search_dirs:
        if not d:
            continue
        d = os.path.expanduser(d)
        if not os.path.isdir(d):
            continue
        # Case-insensitive-ish: look for .pgn and .PGN
        results.extend(glob.glob(os.path.join(d, '*.pgn')))
        results.extend(glob.glob(os.path.join(d, '*.PGN')))

    # De-dupe and sort for stable numbering
    uniq = sorted({os.path.abspath(p) for p in results if _looks_like_pgn(p)})
    return uniq


def prompt_for_pgn_path(project_root: str) -> str | None:
    """Pick a PGN file via discovery + numbered selection, with manual fallback."""
    search_dirs = [
        project_root,
        os.path.join('~', 'Downloads'),
        os.path.join('~', 'Desktop'),
    ]
    candidates = find_pgn_files(search_dirs)

    if candidates:
        print("\n📂 Found PGN files:")
        for i, path in enumerate(candidates, 1):
            # Show relative path when possible (nicer output)
            display = os.path.relpath(path, project_root) if path.startswith(project_root) else path
            print(f"  {i}) {display}")
        print("\nSelect a file by number, or press Enter to type a path.")
        selection = input("PGN selection: ").strip()
        if selection:
            try:
                idx = int(selection)
                if 1 <= idx <= len(candidates):
                    return candidates[idx - 1]
                print("❌ Invalid selection number")
            except ValueError:
                print("❌ Please enter a number")

    # Manual fallback
    manual = input("📄 Enter path to your .pgn file: ").strip()
    if not manual:
        return None

    manual = os.path.expanduser(manual)
    manual = os.path.abspath(manual)
    if not _looks_like_pgn(manual):
        if not os.path.exists(manual):
            print(f"❌ PGN file not found: {manual}")
        else:
            print("❌ Please provide an existing .pgn file")
        return None
    return manual


def import_pgn_games(pgn_path: str, name: str) -> tuple[str | None, int]:
    """Parse a local PGN file and save it to the standard games_{name}.csv."""
    try:
        pgn_path = os.path.abspath(os.path.expanduser(pgn_path))
        if not _looks_like_pgn(pgn_path):
            print(f"❌ PGN file not found (or not a .pgn): {pgn_path}")
            return None, 0

        pgn_text = load_pgn_file(pgn_path)
        if not pgn_text.strip():
            print("❌ PGN file is empty")
            return None, 0

        games_list = parse_pgn(pgn_text, name)
        print(f"✓ Parsed {len(games_list)} games")

        # Add platform field (safe extra column; downstream reads moves_pgn etc.)
        for g in games_list:
            if isinstance(g, dict):
                g['platform'] = 'chess.com'

        csv_filename = f"games_{name}.csv"
        df = pd.DataFrame(games_list)
        df.to_csv(csv_filename, index=False)
        print(f"✓ Saved to {csv_filename}")
        return csv_filename, len(games_list)
    except Exception as e:
        print(f"❌ Error importing PGN: {e}")
        return None, 0


def fetch_user_games(username, max_games=15):
    """Fetch and save games for a Lichess user."""
    print(f"\n📡 Fetching games for '{username}'...")
    
    try:
        pgn_text = fetch_lichess_pgn(username, max_games=max_games)
        print(f"✓ Successfully fetched PGN data")
        
        games_list = parse_pgn(pgn_text, username)
        print(f"✓ Parsed {len(games_list)} games")

        # Add platform field (safe extra column; downstream reads moves_pgn etc.)
        for g in games_list:
            if isinstance(g, dict):
                g['platform'] = 'lichess'
        
        # Save to CSV
        csv_filename = f"games_{username}.csv"
        df = pd.DataFrame(games_list)
        df.to_csv(csv_filename, index=False)
        print(f"✓ Saved to {csv_filename}")
        
        return csv_filename, len(games_list)
        
    except ValueError as e:
        print(f"❌ {e}")
        return None, 0
    except Exception as e:
        print(f"❌ Error fetching games: {e}")
        return None, 0


def run_phase1_for_user(username, csv_file, max_games=15, *, analysis_depth: int = 15):
    # Invariant: max_blunder_phase always defined
    max_blunder_phase = ('none', 0)
    """Execute Phase 1: engine analysis for user's games."""
    print("\n" + "="*70)
    print("🔍 PHASE 1: ENGINE ANALYSIS")
    print("="*70)

    # Runtime guardrail for >20 games
    if max_games > 20:
        print(f"\n⚠️  Engine analysis may take several minutes. Consider reducing game count.")
        print(f"   (Requested: {max_games} games; typical duration: ~5s per game)")

    try:
        df = pd.read_csv(csv_file)
        
        if 'moves_pgn' not in df.columns:
            print(f"❌ No moves_pgn data in {csv_file}")
            return None
        
        print(f"\n{'─'*70}")
        print(f"📂 {username.upper():<15} | {len(df):>3} total games | analyzing up to {max_games}")
        print(f"{'─'*70}")
        
        games_data = []
        failed_games = 0
        skipped_games = 0
        
        for idx, row in df.head(max_games).iterrows():
            moves_pgn = row.get("moves_pgn", "")
            if not moves_pgn or (isinstance(moves_pgn, float) and pd.isna(moves_pgn)):
                skipped_games += 1
                continue
                
            try:
                move_evals = analyze_game_detailed(moves_pgn, depth=analysis_depth)
                games_data.append({
                    "game_info": {
                        "score": row.get("score"),
                        "opening_name": row.get("opening_name"),
                        "time_control": row.get("time_control"),
                        "elo": row.get("elo"),
                        "rating": row.get("elo"),
                        "player_rating": row.get("elo"),
                        "platform": row.get("platform"),
                    },
                    "move_evals": move_evals,
                })
                print(f"  ✓ Game {idx+1}: {len(move_evals):>2} moves analyzed")
            except Exception as e:
                failed_games += 1
                print(f"  ✗ Game {idx+1}: Failed - {str(e)[:35]}")
        
        if not games_data:
            print(f"  ⚠️  No valid games analyzed")
            return None
        
        # Compute metrics
        overall = compute_overall_cpl(games_data)
        phase_stats = aggregate_cpl_by_phase(games_data)

        sw = compute_strengths_weaknesses(games_data)

        # Blunder subtype aggregation (V3 Step 2)
        blunder_subtypes = []
        for g in games_data:
            for m in g.get('move_evals', []):
                if m.get('blunder_type') == 'blunder':
                    blunder_subtypes.append(m.get('blunder_subtype') or 'Unknown')

        # Opening aggregation: compute avg CPL and win rate per opening
        opening_agg = {}
        for i, g in enumerate(games_data):
            opening_name = g['game_info'].get('opening_name') or 'Unknown'
            game_cpl = compute_game_cpl(g.get('move_evals', []))
            score = g['game_info'].get('score')

            rec = opening_agg.setdefault(opening_name, {'cpls': [], 'wins': 0, 'games': 0})
            rec['cpls'].append(game_cpl)
            rec['games'] += 1
            if score == 'win':
                rec['wins'] += 1

        # Compute averages and identify best/worst
        opening_stats = {}
        for name, data in opening_agg.items():
            avg_cpl = round(sum(data['cpls']) / len(data['cpls'])) if data['cpls'] else 0
            win_rate = round((data['wins'] / data['games'] * 100)) if data['games'] > 0 else 0
            opening_stats[name] = {'avg_cpl': avg_cpl, 'win_rate': win_rate, 'games': data['games']}

        # Best opening: lowest CPL (tie-breaker: higher win_rate)
        best_opening = None
        worst_opening = None
        if opening_stats:
            best_opening = min(opening_stats.items(), key=lambda kv: (kv[1]['avg_cpl'], -kv[1]['win_rate']))
            worst_opening = max(opening_stats.items(), key=lambda kv: (kv[1]['avg_cpl'], -kv[1]['win_rate']))
        
        # Display results
        print(f"\n  ✅ Processed: {len(games_data)}/{min(max_games, len(df))} games")
        if skipped_games > 0 or failed_games > 0:
            print(f"     Skipped: {skipped_games} | Failed: {failed_games}")
        print(f"\n  📈 OVERALL PERFORMANCE:")
        print(f"     Avg Centipawn Loss (CPL):  {overall['overall_cpl']:>7.1f} cp/move")
        print(f"     Recent CPL Trend:          {overall['trend']} ({overall['trend_reason']})")
        print(f"     Blunders:                  {overall['total_blunders']:>7} ({overall['blunders_per_100']:.1f} per 100 moves)")
        print(f"     Avg blunder severity:      {overall['avg_blunder_severity']:>7.0f} cp")
        print(f"     Worst blunder:             {overall['max_blunder_severity']:>7} cp")
        print(f"     Mistakes:                  {overall['total_mistakes']:>7}")
        conv = overall.get('conversion_difficulty', {}) or {}
        print(f"     Conversion difficulty:     {conv.get('avg_loss_when_ahead', 0.0):>7} cp avg loss when ahead | severe drops {conv.get('severe_conversion_errors', 0)}/{conv.get('winning_positions', 0)}")
        end_adv = overall.get('endgame_advantage', {}) or {}
        win_bucket = end_adv.get('winning', {}) or {}
        conversion_rate = win_bucket.get('conversion_rate', 'N/A')
        print(f"     Endgames reached with advantage: {win_bucket.get('games', 0):>3} | Successful conversions: {win_bucket.get('conversions', 0)} (rate: {conversion_rate})")
        print(f"     Mate misses / forced mates: missed {overall.get('mate_missed_count', 0)} | forced-loss states {overall.get('forced_loss_count', 0)}")
        # Best/Worst piece usage
        best_piece = overall.get('best_piece', 'N/A')
        worst_piece = overall.get('worst_piece', 'N/A')
        print(f"     Best piece:                {best_piece:>7}")
        print(f"     Worst piece:               {worst_piece:>7}")
        print(f"     ⚠️  Weakest Phase:          {overall['weakest_phase'].upper()}")
        print(f"\n  🎯 BY PHASE (board-state heuristic classification):")
        print(f"     {'Phase':<12} {'CPL':>8} {'Blunders':>9} {'Games':>6} {'Reached +1.0':>12}")
        print(f"     {'-'*55}")
        for phase in ["opening", "middlegame", "endgame"]:
            stats = phase_stats[phase]
            print(f"     {phase.capitalize():<12} {stats['cpl']:>8.1f} {stats['blunders']:>9} {stats['games']:>6} {stats['advantage']:>12}")
        phase_ratio = overall.get('phase_relative_cpl', {}) or {}
        def _fmt_ratio(val):
            if val is None:
                return "N/A"
            return f"{val:.2f}x"
        print(f"     CPL vs overall: Opening {_fmt_ratio(phase_ratio.get('opening'))} | Middlegame {_fmt_ratio(phase_ratio.get('middlegame'))} | Endgame {_fmt_ratio(phase_ratio.get('endgame'))}")

        # Phase interpretation & coach summary (console)
        phase_name = {"opening": "Opening", "middlegame": "Middlegame", "endgame": "Endgame"}
        reached_phases = [
            p for p in ("opening", "middlegame", "endgame")
            if (phase_stats.get(p, {}) or {}).get("total_moves", 0) > 0
        ]
        if not reached_phases:
            reached_phases = ["opening"]

        cpls_with_name = [(p, float(phase_stats[p].get('cpl') or 0.0), phase_name[p]) for p in reached_phases]
        strongest_phase = min(cpls_with_name, key=lambda x: x[1])
        weakest_phase = max(cpls_with_name, key=lambda x: x[1])

        # Blunder distribution
        blunder_dist = overall.get('blunder_distribution', {})
        total_blunders = overall['total_blunders']
        opening_blunders = blunder_dist.get('opening', 0)
        middlegame_blunders = blunder_dist.get('middlegame', 0)
        endgame_blunders = blunder_dist.get('endgame', 0)
        opening_pct = (opening_blunders / total_blunders * 100) if total_blunders > 0 else 0
        middlegame_pct = (middlegame_blunders / total_blunders * 100) if total_blunders > 0 else 0
        endgame_pct = (endgame_blunders / total_blunders * 100) if total_blunders > 0 else 0
        blunder_phases = [
            ('opening', opening_pct),
            ('middlegame', middlegame_pct),
            ('endgame', endgame_pct),
        ]
        if total_blunders > 0:
            max_blunder_phase = max(blunder_phases, key=lambda x: x[1])
        else:
            max_blunder_phase = ('none', 0)  # <-- Ensure always defined

        print(f"\n  💡 PHASE INTERPRETATION\n  " + "-"*62)
        print(f"  • Your {strongest_phase[2].lower()} play is relatively stable (CPL: {strongest_phase[1]:.1f} cp/move).")
        print(f"  • The {weakest_phase[2].lower()} shows the most room for improvement (CPL: {weakest_phase[1]:.1f} cp/move).")
        if total_blunders > 0:
            print(f"  • Pattern: severe accuracy drops in the {max_blunder_phase[0]}, accounting for {max_blunder_phase[1]:.0f}% of all blunders.")
        else:
            print(f"  • Pattern: no significant blunders recorded.")

        print(f"\n  🧠 COACH SUMMARY\n  " + "="*62)
        primary_issue = _choose_primary_issue(overall, phase_stats)
        print(f"  • Primary weakness: {primary_issue}")
        if total_blunders > 0:
            print(f"    (Average blunder: −{int(overall['avg_blunder_severity'])} cp, Worst: −{overall['max_blunder_severity']} cp)")
            if max_blunder_phase[1] > 40:
                print(f"  • Pattern: Blunder concentration in {max_blunder_phase[0]} ({max_blunder_phase[1]:.0f}%)")
        else:
            print(f"    (CPL: {weakest_phase[1]:.1f} cp/move)")

        print(f"  • Strength: Stable {strongest_phase[2].lower()}s with low CPL ({strongest_phase[1]:.1f} cp/move)")
        print(f"  • Training focus:")
        if weakest_phase[2] == 'Endgame':
            print(f"    - Endgame technique and simplification")
            print(f"    - Converting +1.0 positions into wins")
            print(f"    - Calculation accuracy in final phase")
        elif weakest_phase[2] == 'Middlegame':
            print(f"    - Tactical puzzle solving and pattern recognition")
            print(f"    - Position evaluation and planning")
            print(f"    - Double-check calculations before moves")
        else:
            print(f"    - Opening principles and theory")
            print(f"    - Avoid repetitive mistakes in main lines")
            print(f"    - Develop consistent opening preparation")
            print(f"    → ({overall['trend_reason']})")

        return {
            "player": username,
            "games_analyzed": len(games_data),
            "overall_cpl": overall['overall_cpl'],
            "recent_cpl": overall['recent_cpl'],
            "total_blunders": overall['total_blunders'],
            "total_mistakes": overall['total_mistakes'],
            "best_piece": overall.get('best_piece', 'N/A'),
            "worst_piece": overall.get('worst_piece', 'N/A'),
            "phase_stats": phase_stats,
            "games_data": games_data,
        }
        
    except Exception as e:
        print(f"❌ Error in Phase 1: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_phase2_for_user(username, max_games=15, games_data=None, *, analysis_depth: int = 15):
    """Execute Phase 2: aggregation and reporting."""
    print("\n\n" + "="*70)
    print("📊 PHASE 2: AGGREGATION & REPORTING")
    print("="*70)

    def _eval_for_player(val, color: str | None):
        if val is None:
            return None
        if color and color.lower().startswith("b"):
            return -val
        return val

    def _per_game_summaries(games):
        summaries = []
        for idx, g in enumerate(games, start=1):
            info = g.get("game_info", {}) or {}
            color = info.get("color")
            score = info.get("score") or "unknown"
            move_evals = g.get("move_evals", []) or []

            blunders_by_phase = {"opening": 0, "middlegame": 0, "endgame": 0}
            mistakes_by_phase = {"opening": 0, "middlegame": 0, "endgame": 0}
            endgame_final_eval = None

            for mv in move_evals:
                phase = mv.get("phase", "middlegame")
                if mv.get("blunder_type") == "blunder":
                    blunders_by_phase[phase] = blunders_by_phase.get(phase, 0) + 1
                elif mv.get("blunder_type") == "mistake":
                    mistakes_by_phase[phase] = mistakes_by_phase.get(phase, 0) + 1
                if phase == "endgame" and mv.get("eval_after") is not None:
                    endgame_final_eval = _eval_for_player(mv.get("eval_after"), color)

            total_blunders = sum(blunders_by_phase.values())
            total_mistakes = sum(mistakes_by_phase.values())
            worst_phase = None
            if total_blunders > 0:
                worst_phase = max(blunders_by_phase.items(), key=lambda kv: kv[1])[0]
            elif total_mistakes > 0:
                worst_phase = max(mistakes_by_phase.items(), key=lambda kv: kv[1])[0]

            parts = []
            parts.append(f"result {score}")
            if total_blunders > 0:
                parts.append(f"{total_blunders} blunders in {worst_phase}")
            elif total_mistakes > 0:
                parts.append(f"{total_mistakes} mistakes (no blunders)")
            else:
                parts.append("steady (no major errors)")

            if endgame_final_eval is not None and endgame_final_eval >= 100 and score != "win":
                parts.append("reached winning endgame but failed conversion")

            summaries.append(f"Game {idx}: " + "; ".join(parts))
        return summaries
    
    if games_data is None:
        csv_file = f"games_{username}.csv"
        if not os.path.exists(csv_file):
            print(f"❌ {csv_file} not found")
            return 0
        
        try:
            df = pd.read_csv(csv_file)
            
            if 'moves_pgn' not in df.columns:
                print(f"❌ No moves_pgn data")
                return 0
            
            games_data = []
            analyzed_rows = []
            
            for _, row in df.head(max_games).iterrows():
                moves = row.get('moves_pgn')
                if not moves or (isinstance(moves, float) and pd.isna(moves)):
                    continue
                
                move_evals = analyze_game_detailed(moves, depth=analysis_depth)
                if not move_evals:
                    continue
                
                games_data.append({
                    'game_info': {
                        'score': row.get('score'),
                        'opening_name': row.get('opening_name'),
                        'time_control': row.get('time_control'),
                        'elo': row.get('elo'),
                        'rating': row.get('elo'),
                        'player_rating': row.get('elo'),
                        'color': row.get('color'),
                        'platform': row.get('platform'),
                    },
                    'move_evals': move_evals,
                })
                analyzed_rows.append(row.to_dict())
            
            if not games_data:
                print("❌ No valid games")
                return 0
        except Exception as e:
            print(f"❌ Error in Phase 2: {e}")
            return 0
        
    overall = compute_overall_cpl(games_data)
    phase_stats = aggregate_cpl_by_phase(games_data)

    # Peer comparison (uses local population baselines when available)
    peer = benchmark_from_games_data(games_data)

    # Append this run to the local population store to improve future baselines
    try:
        append_population_record(games_data, username=username, source='cli')
    except Exception:
        # Non-critical: analysis output should still succeed even if persistence fails
        pass

    # Strengths & weaknesses (V3 Step 3)
    sw = compute_strengths_weaknesses(games_data)

    # Opening intelligence (V3 Step 4)
    oi = compute_opening_intelligence(games_data)

    # Blunder subtype aggregation (V3 Step 2)
    from collections import Counter
    blunder_subtypes = []
    for g in games_data:
        for m in g.get('move_evals', []):
            if m.get('blunder_type') == 'blunder':
                blunder_subtypes.append(m.get('blunder_subtype') or 'Unknown')
    
    # Save summary
    output_txt = f"{username}_analysis.txt"
    with open(output_txt, 'w') as fh:
        fh.write(f"♟️  CHESS ANALYSIS FOR {username.upper()}\n")
        fh.write("="*70 + "\n\n")
        fh.write(f"Games analyzed: {len(games_data)}\n")
        fh.write(f"Total moves: {overall['total_moves']}\n")
        fh.write(f"Timestamp: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        if len(games_data) < 3:
            fh.write("(Note: limited sample size; signals may be unstable)\n\n")
        
        # Overall metrics
        fh.write("📊 METRICS (Lower CPL = Stronger Play)\n")
        fh.write("-"*70 + "\n")
        fh.write(f"Avg Centipawn Loss (CPL):  {overall['overall_cpl']:>7.1f} cp/move\n")
        
        # Trend with proper logic
        if overall['trend'] == "N/A":
            fh.write(f"Recent CPL Trend:          {overall['trend']} ({overall['trend_reason']})\n")
        else:
            fh.write(f"Recent CPL Trend:          {overall['trend']} ({overall['trend_reason']})\n")
        
        fh.write(f"Blunders:                  {overall['total_blunders']:>7} ({overall['blunders_per_100']:.1f} per 100 moves)\n")
        fh.write(f"Avg blunder severity:      {overall['avg_blunder_severity']:>7.0f} cp\n")
        fh.write(f"Worst blunder:             {overall['max_blunder_severity']:>7} cp\n")
        fh.write(f"Mistakes:                  {overall['total_mistakes']:>7} ({overall['mistakes_per_100']:.1f} per 100 moves)\n")
        fh.write(f"Best piece:                {overall.get('best_piece', 'N/A'):>7}\n")
        fh.write(f"Worst piece:               {overall.get('worst_piece', 'N/A'):>7}\n\n")
        fh.write(f"Mate misses / forced mates: missed {overall.get('mate_missed_count', 0)} | forced-loss states {overall.get('forced_loss_count', 0)}\n\n")

        # Phase ratio feature (endgame relative to opening/middlegame)
        ratio_info = (peer.to_dict().get('phase_ratios', {}) or {}).get('endgame_vs_openmid', {}) or {}
        player_ratio = float(ratio_info.get('player') or 0.0)
        pop_ratio = float(ratio_info.get('population_mean') or 0.0)
        vs_peers = ratio_info.get('vs_peers')
        if player_ratio > 0 and pop_ratio > 0:
            fh.write("CPL PHASE RATIOS (Endgame vs Opening+Middlegame)\n")
            fh.write("-"*70 + "\n")
            fh.write(f"Your endgame CPL ratio: {player_ratio:.2f}x (endgame vs avg(opening,middlegame))\n")
            fh.write(f"Peers average ratio ({peer.rating_bracket}, n={ratio_info.get('population_sample_size', 0)}): {pop_ratio:.2f}x\n")
            fh.write(f"Vs peers: {vs_peers} | Ratio percentile: {ratio_info.get('percentile', 0)}\n")
            if player_ratio < pop_ratio:
                fh.write("Interpretation: Your endgames are less disproportionately error-prone than peers (relative endgame strength).\n\n")
            else:
                fh.write("Interpretation: Your endgames drop off more than peers relative to your earlier phases (relative endgame weakness).\n\n")
        conv = overall.get('conversion_difficulty', {}) or {}
        fh.write("CONVERSION DIFFICULTY\n")
        fh.write("-"*70 + "\n")
        fh.write(f"Winning positions (eval ≥ +1.0): {conv.get('winning_positions', 0)}\n")
        fh.write(f"Avg loss when ahead: {conv.get('avg_loss_when_ahead', 0.0)} cp\n")
        fh.write(f"Severe drops (to < +0.5): {conv.get('severe_conversion_errors', 0)} ({conv.get('severe_error_rate', 0.0)}%)\n\n")

        end_adv = overall.get('endgame_advantage', {}) or {}
        fh.write("ENDGAME ADVANTAGE (bucketed by final eval in endgame)\n")
        fh.write("-"*70 + "\n")
        win_bucket = end_adv.get('winning', {}) or {}
        draw_bucket = end_adv.get('drawing', {}) or {}
        lose_bucket = end_adv.get('losing', {}) or {}
        fh.write(f"Endgames reached with advantage: {win_bucket.get('games', 0)} | Successful conversions: {win_bucket.get('conversions', 0)} | Rate: {win_bucket.get('conversion_rate', 'N/A')} | Avg CPL: {win_bucket.get('avg_cpl', 0.0)}\n")
        fh.write(f"Drawing endgames: {draw_bucket.get('games', 0)} | Avg CPL: {draw_bucket.get('avg_cpl', 0.0)}\n")
        fh.write(f"Losing endgames:  {lose_bucket.get('games', 0)} | Avg CPL: {lose_bucket.get('avg_cpl', 0.0)}\n\n")

        # Strengths & weaknesses (V3 Step 3)
        fh.write("STRENGTHS & WEAKNESSES\n")
        fh.write("-"*70 + "\n")
        strengths = sw.get('strengths', []) or []
        weaknesses = sw.get('weaknesses', []) or []
        if strengths:
            fh.write("Strengths:\n")
            for s in strengths:
                fh.write(f"- {s}\n")
        else:
            fh.write("Strengths: (insufficient signal)\n")

        if weaknesses:
            fh.write("Weaknesses:\n")
            for w in weaknesses:
                fh.write(f"- {w}\n")
        else:
            fh.write("Weaknesses: (none detected)\n")
        fh.write("\n")

        # Opening intelligence (V3 Step 4)
        fh.write("OPENING INTELLIGENCE\n")
        fh.write("-"*70 + "\n")
        best = (oi or {}).get('best_opening')
        worst = (oi or {}).get('worst_opening')
        if best:
            fh.write(f"Best (min 2 games): {best.get('name')} | {best.get('win_rate')}% win | {best.get('avg_player_cpl')} CPL\n")
        if worst:
            fh.write(f"Worst (min 2 games): {worst.get('name')} | {worst.get('win_rate')}% win | {worst.get('avg_player_cpl')} CPL\n")

        rates = (oi or {}).get('pattern_rates', {}) or {}
        if rates:
            fh.write("Patterns (share of games):\n")
            fh.write(f"- Early queen moves: {rates.get('early_queen', 0.0)}%\n")
            fh.write(f"- Premature pawn pushes: {rates.get('pawn_pushes', 0.0)}%\n")
            fh.write(f"- Late/no castling: {rates.get('king_safety_neglect', 0.0)}%\n")
        fh.write("\n")

        # Per-game summaries to surface game-level context
        fh.write("PER-GAME SUMMARY\n")
        fh.write("-"*70 + "\n")
        for line in _per_game_summaries(games_data):
            fh.write(f"- {line}\n")
        fh.write("\n")

        # Blunder types
        fh.write("\nBLUNDER TYPES\n")
        fh.write("-"*70 + "\n")
        if not blunder_subtypes:
            fh.write("No blunders detected.\n\n")
        else:
            counts = Counter(blunder_subtypes)
            total = sum(counts.values())
            for subtype, count in counts.most_common():
                pct = (count / total) * 100.0 if total > 0 else 0.0
                fh.write(f"{subtype}: {pct:.0f}% ({count})\n")
            fh.write("\n")
        
        # Phase table
        fh.write("🎯 BY PHASE (board-state heuristic classification)\n")
        fh.write("-"*70 + "\n")
        fh.write(f"{'Phase':<15} {'CPL':>8} {'Blunders':>9} {'Games':>6} {'Reached +1.0':>12}\n")
        fh.write(f"{'-'*70}\n")
        for p in ['opening', 'middlegame', 'endgame']:
            ps = phase_stats.get(p, {})
            adv_pct = ps.get('advantage', 'N/A')
            total_moves = ps.get('total_moves', 0)
            cpl_val = ps.get('cpl')
            cpl_str = f"{cpl_val:.1f}" if (cpl_val is not None and total_moves > 0) else "N/A"
            fh.write(f"{p.capitalize():<15} {cpl_str:>8} {ps.get('blunders'):>9} {ps.get('games'):>6} {str(adv_pct):>12}\n")
        fh.write("\n  * Reached +1.0 Eval: Represents games where the player reached a winning position\n")
        fh.write("    during that phase, not necessarily converted it.\n\n")
        phase_ratio = overall.get('phase_relative_cpl', {}) or {}
        def _fmt_ratio(val):
            if val is None:
                return "N/A"
            return f"{val:.2f}x"
        fh.write(f"CPL vs overall: Opening {_fmt_ratio(phase_ratio.get('opening'))} | Middlegame {_fmt_ratio(phase_ratio.get('middlegame'))} | Endgame {_fmt_ratio(phase_ratio.get('endgame'))}\n\n")
        
        # Coaching output V3 (deterministic, no duplication)
        reached_phases = [
            p for p in ("opening", "middlegame", "endgame")
            if (phase_stats.get(p, {}) or {}).get("total_moves", 0) > 0
        ]

        phase_name = {"opening": "Opening", "middlegame": "Middlegame", "endgame": "Endgame"}
        strongest_phase = None
        weakest_phase = None
        if reached_phases:
            strongest_phase = min(reached_phases, key=lambda p: float(phase_stats[p].get('cpl') or 0.0))
            weakest_phase = max(reached_phases, key=lambda p: float(phase_stats[p].get('cpl') or 0.0))

        total_blunders = int(overall.get('total_blunders') or 0)
        blunders_per_100 = float(overall.get('blunders_per_100') or 0.0)
        mistakes_per_100 = float(overall.get('mistakes_per_100') or 0.0)
        overall_cpl = float(overall.get('overall_cpl') or 0.0)

        # Top blunder subtype
        subtype_counts = Counter(blunder_subtypes)
        top_subtype = None
        top_subtype_pct = 0.0
        if total_blunders > 0 and subtype_counts:
            top_subtype, top_count = subtype_counts.most_common(1)[0]
            top_subtype_pct = (top_count / total_blunders * 100.0) if total_blunders > 0 else 0.0

        # Blunder concentration by phase
        blunder_dist = overall.get('blunder_distribution', {}) or {}
        max_blunder_phase = None
        max_blunder_phase_pct = 0.0
        if total_blunders > 0:
            by_phase = {p: int(blunder_dist.get(p, 0) or 0) for p in ("opening", "middlegame", "endgame")}
            max_blunder_phase = max(by_phase.keys(), key=lambda p: by_phase[p])
            max_blunder_phase_pct = (by_phase[max_blunder_phase] / total_blunders * 100.0) if total_blunders > 0 else 0.0

        # Profile label (simple, deterministic bands)
        if overall_cpl <= 60:
            profile = "High-accuracy profile"
        elif overall_cpl <= 120:
            profile = "Solid accuracy with room to refine"
        elif overall_cpl <= 250:
            profile = "Inconsistent accuracy"
        else:
            profile = "Volatile accuracy (large swings)"

        fh.write("COACHING SUMMARY (V3)\n")
        fh.write("="*70 + "\n")

        # 1) Overall profile
        fh.write("1) Overall profile\n")
        fh.write(f"- {profile}\n")
        fh.write(f"- Overall CPL: {overall_cpl:.1f} cp/move\n")
        fh.write(f"- Blunders: {total_blunders} ({blunders_per_100:.1f} per 100 moves) | Mistakes: {int(overall.get('total_mistakes') or 0)} ({mistakes_per_100:.1f} per 100 moves)\n")
        fh.write("\n")

        # 2) Primary weakness
        fh.write("2) Primary weakness\n")
        primary_issue = _choose_primary_issue(overall, phase_stats)
        fh.write(f"- {primary_issue}\n")
        fh.write("\n")

        # 3) Error patterns
        fh.write("3) Error patterns\n")
        if total_blunders == 0:
            fh.write("- No blunders detected in the analyzed games.\n")
        else:
            if top_subtype:
                fh.write(f"- Most common blunder type: {top_subtype} ({top_subtype_pct:.0f}%)\n")
            if max_blunder_phase:
                fh.write(f"- Blunders concentrate in: {phase_name.get(max_blunder_phase, max_blunder_phase)} ({max_blunder_phase_pct:.0f}%)\n")
        if overall.get('mate_missed_count', 0) > 0:
            fh.write(f"- Missed forced mates detected: {overall.get('mate_missed_count')} (excluded from CPL)\n")
        rates = (oi or {}).get('pattern_rates', {}) or {}
        if rates.get('early_queen', 0.0) >= 30.0:
            fh.write(f"- Early queen moves appear frequently ({rates.get('early_queen')}%).\n")
        if rates.get('king_safety_neglect', 0.0) >= 30.0:
            fh.write(f"- Late/no castling is common ({rates.get('king_safety_neglect')}%).\n")
        if rates.get('pawn_pushes', 0.0) >= 30.0:
            fh.write(f"- Premature pawn pushing appears often ({rates.get('pawn_pushes')}%).\n")
        fh.write("\n")

        # 4) Strengths
        fh.write("4) Strengths\n")
        strengths_list = sw.get('strengths', []) or []
        if strengths_list:
            for s in strengths_list:
                fh.write(f"- {s}\n")
        else:
            fh.write("- (insufficient signal)\n")
        fh.write("\n")

        # 5) Training priorities
        fh.write("5) Training priorities\n")
        priorities = []
        if primary_issue == "Converting winning endgames":
            priorities.append("Drill winning endgame conversions (simplify when +1.0)")
        if primary_issue == "Blunders in equal positions":
            priorities.append("Slow down in equal positions: blunder-check before tactical operations")
        if primary_issue.endswith("blunders drive losses"):
            priorities.append(f"Reduce {max_blunder_phase or 'phase'} blunders with pre-move checks")
        if top_subtype == "Hanging piece":
            priorities.append("Tactical safety: reduce hanging pieces")
        elif top_subtype == "Missed tactic":
            priorities.append("Calculation: improve tactical awareness")
        elif top_subtype == "King safety":
            priorities.append("King safety: reduce king-exposure moves")
        elif top_subtype == "Endgame technique":
            priorities.append("Endgame technique: convert advantages and simplify safely")

        if rates.get('king_safety_neglect', 0.0) >= 30.0:
            priorities.append("Castle earlier in most games")
        if weakest_phase == "endgame":
            priorities.append("Endgame accuracy and conversion")
        if weakest_phase == "opening":
            priorities.append("Opening fundamentals: develop pieces before operations")

        # Default if nothing triggered
        if not priorities:
            priorities.append("Reduce large evaluation swings with a consistent blunder-check")

        # De-dupe and cap
        seen = set()
        priorities_out = []
        for p in priorities:
            if p not in seen:
                priorities_out.append(p)
                seen.add(p)
        priorities_out = priorities_out[:3]
        for p in priorities_out:
            fh.write(f"- {p}\n")
        fh.write("\n")

        # 6) Concrete next steps
        fh.write("6) Concrete next steps\n")
        next_steps = []
        if rates.get('king_safety_neglect', 0.0) >= 30.0:
            next_steps.append("Set a rule: castle by move 10 unless there is a concrete tactical reason not to")
        if top_subtype in {"Hanging piece", "Missed tactic"}:
            next_steps.append("Daily tactics: 15–20 minutes focused on checks/captures/threats and undefended pieces")
        if top_subtype == "Endgame technique" or weakest_phase == "endgame":
            next_steps.append("Endgame block: 3 sessions/week (king+pawn basics + rook endgames)")
        if not next_steps:
            next_steps.append("Before each move: do a 10-second blunder-check (opponent checks, captures, threats)")
            next_steps.append("Review your top 5 blunders and write the missed idea in one sentence")

        # Cap
        if len(next_steps) < 3:
            next_steps.append("Before each move: do a 10-second blunder-check (opponent checks, captures, threats)")
        if len(next_steps) < 3:
            next_steps.append("Review your 5 biggest blunders and write the missed idea in one sentence")
        if len(next_steps) < 3:
            next_steps.append("Play 2 slower games this week and annotate them with 3 candidate moves per critical position")

        for s in next_steps[:3]:
            fh.write(f"- {s}\n")
        fh.write("\n")
    
    print(f"✓ Analysis saved to {output_txt}")
    return 1
    
    
    
    


def main():
    """Interactive analyzer main."""
    print("\n" + "="*70)
    print("♟️  CHESS ANALYZER")
    print("="*70)

    print("\nChoose input source:")
    print("1) Lichess username")
    print("2) Chess.com PGN file (manual import)")
    source = input("Enter 1 or 2: ").strip()

    username = ""
    pgn_path = ""
    if source == '1':
        username = input("\n📝 Enter your Lichess username: ").strip()
        if not username:
            print("❌ Username cannot be empty")
            return 1
    elif source == '2':
        pgn_path = prompt_for_pgn_path(project_root=os.getcwd())
        if not pgn_path:
            print("❌ No PGN selected")
            return 1
        username = os.path.splitext(os.path.basename(pgn_path))[0]
    else:
        print("❌ Invalid choice")
        return 1
    
    # Get max games
    try:
        max_games_input = input("🎯 How many games to analyze? (default 15): ").strip()
        max_games = int(max_games_input) if max_games_input else 15
    except ValueError:
        max_games = 15
        print(f"ℹ️  Using default: {max_games} games")

    # Guardrail for very large jobs (performance safety)
    if max_games > 20:
        confirm = input(f"⚠️  You requested {max_games} games. This may take a long time. Proceed? [y/N]: ").strip().lower()
        if confirm not in {"y", "yes"}:
            max_games = 20
            print("ℹ️  Limiting to 20 games. Re-run with a smaller number or confirm to analyze more.")

    # Stockfish depth (local analysis). Recommended: 15.
    try:
        depth_in = input("🔧 Stockfish depth (10-20, recommended 15) [15]: ").strip()
        analysis_depth = int(depth_in) if depth_in else 15
    except Exception:
        analysis_depth = 15
    analysis_depth = max(10, min(20, int(analysis_depth)))
    
    print("\n" + "="*70)
    print(f"🚀 FETCHING & ANALYZING: {username}")
    print(f"   Max games: {max_games}")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    try:
        # Fetch/import games
        t0 = time.time()
        if source == '1':
            csv_file, game_count = fetch_user_games(username, max_games=max_games)
        else:
            print(f"\n📥 Importing PGN from '{pgn_path}'...")
            csv_file, game_count = import_pgn_games(pgn_path, username)
        fetch_time = time.time() - t0
        
        if not csv_file or game_count == 0:
            print("\n❌ Failed to fetch games. Exiting.")
            return 1
        
        # Phase 1
        t0 = time.time()
        phase1_result = run_phase1_for_user(username, csv_file, max_games=max_games, analysis_depth=analysis_depth)
        phase1_time = time.time() - t0
        
        if not phase1_result:
            print("\n❌ Phase 1 failed. Exiting.")
            return 1
        
        # Phase 2
        t0 = time.time()
        phase2_count = run_phase2_for_user(
            username,
            max_games=max_games,
            games_data=phase1_result.get("games_data"),
            analysis_depth=analysis_depth,
        )
        phase2_time = time.time() - t0
        
        # Final summary
        print("\n" + "="*70)
        print("✨ ANALYSIS COMPLETE")
        print("="*70)
        print(f"📥 Fetch: {fetch_time:.1f}s")
        print(f"📈 Phase 1: {phase1_time:.1f}s")
        print(f"📊 Phase 2: {phase2_time:.1f}s")
        print(f"   Total: {(fetch_time + phase1_time + phase2_time):.1f}s")
        print(f"\n📋 Results saved to:")
        print(f"   - games_{username}.csv")
        print(f"   - {username}_analysis.txt")
        print("="*70 + "\n")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⏸️  Interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1
if __name__ == '__main__':
    sys.exit(main())
