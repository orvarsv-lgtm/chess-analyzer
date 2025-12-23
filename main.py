#!/usr/bin/env python
"""
Interactive Chess Analyzer: Fetch Lichess games → Engine analysis → Reporting
"""
import sys
import os
import time
import glob
import pandas as pd
from datetime import datetime

# Import from src package
from src.lichess_api import fetch_lichess_pgn, parse_pgn
from src.engine_analysis import analyze_game_detailed
from src.performance_metrics import compute_overall_cpl, aggregate_cpl_by_phase, compute_game_cpl
from src.phase2 import analyze_phase2


def fetch_user_games(username, max_games=15):
    """Fetch and save games for a Lichess user."""
    print(f"\n📡 Fetching games for '{username}'...")
    
    try:
        pgn_text = fetch_lichess_pgn(username, max_games=max_games)
        print(f"✓ Successfully fetched PGN data")
        
        games_list = parse_pgn(pgn_text, username)
        print(f"✓ Parsed {len(games_list)} games")
        
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


def run_phase1_for_user(username, csv_file, max_games=15):
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
                move_evals = analyze_game_detailed(moves_pgn)
                games_data.append({
                    "game_info": {
                        "score": row.get("score"),
                        "opening_name": row.get("opening_name"),
                        "time_control": row.get("time_control"),
                        "elo": row.get("elo"),
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

        # Opening aggregation: compute avg CPL and win rate per opening
        opening_agg = {}
        for i, g in enumerate(games_data):
            opening_name = g['game_info'].get('opening_name') or analyzed_rows[i].get('opening_name')
            if opening_name is None:
                opening_name = 'Unknown'
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
        # Best/Worst piece usage
        best_piece = overall.get('best_piece', 'N/A')
        worst_piece = overall.get('worst_piece', 'N/A')
        print(f"     Best piece:                {best_piece:>7}")
        print(f"     Worst piece:               {worst_piece:>7}")
        print(f"     ⚠️  Weakest Phase:          {overall['weakest_phase'].upper()}")
        print(f"\n  🎯 BY PHASE (Opening: moves 1-10, Middlegame: 11-30, Endgame: 31+):")
        print(f"     {'Phase':<12} {'CPL':>8} {'Blunders':>9} {'Games':>6} {'Reached +1.0':>12}")
        print(f"     {'-'*55}")
        for phase in ["opening", "middlegame", "endgame"]:
            stats = phase_stats[phase]
            print(f"     {phase.capitalize():<12} {stats['cpl']:>8.1f} {stats['blunders']:>9} {stats['games']:>6} {stats['advantage']:>12}")

        # Phase interpretation & coach summary (console)
        opening_cpl = phase_stats['opening']['cpl']
        middlegame_cpl = phase_stats['middlegame']['cpl']
        endgame_cpl = phase_stats['endgame']['cpl']

        cpls_with_name = [
            ('opening', opening_cpl, 'Opening'),
            ('middlegame', middlegame_cpl, 'Middlegame'),
            ('endgame', endgame_cpl, 'Endgame'),
        ]
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

        print(f"\n  💡 PHASE INTERPRETATION\n  " + "-"*62)
        print(f"  • Your opening play is relatively stable (CPL: {strongest_phase[1]:.1f} cp/move).")
        print(f"  • The {weakest_phase[2].lower()} shows the most room for improvement (CPL: {weakest_phase[1]:.1f} cp/move).")
        if total_blunders > 0:
            print(f"  • Pattern: severe accuracy drops in the {max_blunder_phase[0]}, accounting for {max_blunder_phase[1]:.0f}% of all blunders.")
        else:
            print(f"  • Pattern: no significant blunders recorded.")

        print(f"\n  🧠 COACH SUMMARY\n  " + "="*62)
        if total_blunders > 0:
            print(f"  • Primary weakness: {weakest_phase[2]} accuracy")
            print(f"    (CPL: {weakest_phase[1]:.1f} cp/move, {max_blunder_phase[1]:.0f}% of blunders)")
            print(f"  • Cause: Large centipawn swings in {weakest_phase[2]} phase")
            print(f"    (Average blunder: −{int(overall['avg_blunder_severity'])} cp, Worst: −{overall['max_blunder_severity']} cp)")
            if max_blunder_phase[1] > 60:
                print(f"  • Pattern: High blunder concentration in {max_blunder_phase[0]} ({max_blunder_phase[1]:.0f}%)")
            elif max_blunder_phase[1] > 40:
                print(f"  • Pattern: Most blunders ({max_blunder_phase[1]:.0f}%) occur in {max_blunder_phase[0]}")
        else:
            print(f"  • Primary weakness: {weakest_phase[2]} play")
            print(f"    (CPL: {weakest_phase[1]:.1f} cp/move)")
            print(f"  • Cause: No major blunders detected. Focus on overall accuracy and centipawn loss.")

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
        }
        
    except Exception as e:
        print(f"❌ Error in Phase 1: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_phase2_for_user(username, max_games=15):
    """Execute Phase 2: aggregation and reporting."""
    print("\n\n" + "="*70)
    print("📊 PHASE 2: AGGREGATION & REPORTING")
    print("="*70)
    
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
            
            move_evals = analyze_game_detailed(moves)
            if not move_evals:
                continue
            
            games_data.append({
                'game_info': {
                    'score': row.get('score'),
                    'opening_name': row.get('opening_name'),
                    'time_control': row.get('time_control'),
                    'elo': row.get('elo'),
                },
                'move_evals': move_evals,
            })
            analyzed_rows.append(row.to_dict())
        
        if not games_data:
            print("❌ No valid games")
            return 0
        
        overall = compute_overall_cpl(games_data)
        phase_stats = aggregate_cpl_by_phase(games_data)
        
        # Save summary
        output_txt = f"{username}_analysis.txt"
        with open(output_txt, 'w') as fh:
            fh.write(f"♟️  CHESS ANALYSIS FOR {username.upper()}\n")
            fh.write("="*70 + "\n\n")
            fh.write(f"Games analyzed: {len(games_data)}\n")
            fh.write(f"Total moves: {overall['total_moves']}\n")
            fh.write(f"Timestamp: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
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
            
            # Phase table
            fh.write("🎯 BY PHASE (Opening: moves 1-10, Middlegame: 11-30, Endgame: 31+)\n")
            fh.write("-"*70 + "\n")
            fh.write(f"{'Phase':<15} {'CPL':>8} {'Blunders':>9} {'Games':>6} {'Reached +1.0':>12}\n")
            fh.write(f"{'-'*70}\n")
            for p in ['opening', 'middlegame', 'endgame']:
                ps = phase_stats.get(p, {})
                adv_pct = ps.get('advantage', 'N/A')
                fh.write(f"{p.capitalize():<15} {ps.get('cpl'):>8.1f} {ps.get('blunders'):>9} {ps.get('games'):>6} {str(adv_pct):>12}\n")
            fh.write("\n  * Reached +1.0 Eval: Represents games where the player reached a winning position\n")
            fh.write("    during that phase, not necessarily converted it.\n\n")
            
            # Phase interpretation
            fh.write("💡 PHASE INTERPRETATION\n")
            fh.write("-"*70 + "\n")
            
            opening_cpl = phase_stats['opening']['cpl']
            middlegame_cpl = phase_stats['middlegame']['cpl']
            endgame_cpl = phase_stats['endgame']['cpl']
            
            cpls_with_name = [
                ('opening', opening_cpl, 'Opening'),
                ('middlegame', middlegame_cpl, 'Middlegame'),
                ('endgame', endgame_cpl, 'Endgame'),
            ]
            strongest_phase = min(cpls_with_name, key=lambda x: x[1])
            weakest_phase = max(cpls_with_name, key=lambda x: x[1])
            
            # Blunder distribution analysis
            blunder_dist = overall.get('blunder_distribution', {})
            total_blunders = overall['total_blunders']
            
            if total_blunders > 0:
                opening_blunders = blunder_dist.get('opening', 0)
                middlegame_blunders = blunder_dist.get('middlegame', 0)
                endgame_blunders = blunder_dist.get('endgame', 0)
                
                opening_pct = (opening_blunders / total_blunders * 100) if total_blunders > 0 else 0
                middlegame_pct = (middlegame_blunders / total_blunders * 100) if total_blunders > 0 else 0
                endgame_pct = (endgame_blunders / total_blunders * 100) if total_blunders > 0 else 0
                
                # Identify phase with highest blunder concentration
                blunder_phases = [
                    ('opening', opening_pct),
                    ('middlegame', middlegame_pct),
                    ('endgame', endgame_pct),
                ]
                max_blunder_phase = max(blunder_phases, key=lambda x: x[1])
                
                # Deterministic interpretation
                if max_blunder_phase[1] > 60:
                    blunder_info = f"severe accuracy drops in the {max_blunder_phase[0]}, accounting for {max_blunder_phase[1]:.0f}% of all blunders"
                elif max_blunder_phase[1] > 40:
                    blunder_info = f"most blunders ({max_blunder_phase[1]:.0f}%) occur in the {max_blunder_phase[0]}"
                else:
                    blunder_info = "blunders are distributed across all phases"
            else:
                blunder_info = "no significant blunders recorded"
            
            # Generate interpretation sentences
            fh.write(f"• Your {strongest_phase[2].lower()} play is relatively stable (CPL: {strongest_phase[1]:.1f} cp/move).\n")
            fh.write(f"• The {weakest_phase[2].lower()} shows the most room for improvement (CPL: {weakest_phase[1]:.1f} cp/move).\n")
            fh.write(f"• Pattern: {blunder_info}.\n\n")
            
            # Coach summary
            fh.write("\n🧠 COACH SUMMARY\n")
            fh.write("="*70 + "\n")
            
            # Primary weakness
            if overall['total_blunders'] > 0:
                fh.write(f"• Primary weakness: {weakest_phase[2]} accuracy\n")
                fh.write(f"  (CPL: {weakest_phase[1]:.1f} cp/move, {max_blunder_phase[1]:.0f}% of blunders)\n")
            else:
                fh.write(f"• Primary weakness: {weakest_phase[2]} play\n")
                fh.write(f"  (CPL: {weakest_phase[1]:.1f} cp/move)\n")
            
            # Cause analysis (blunder severity + concentration)
            avg_blunder_severity = overall['avg_blunder_severity']
            max_blunder_severity = overall['max_blunder_severity']
            fh.write(f"• Cause: Large centipawn swings in {weakest_phase[2]} phase\n")
            fh.write(f"  (Average blunder: −{int(avg_blunder_severity)} cp, Worst: −{max_blunder_severity} cp)\n")
            
            # Pattern
            if max_blunder_phase[1] > 60:
                fh.write(f"• Pattern: High blunder concentration in {max_blunder_phase[0]} ({max_blunder_phase[1]:.0f}%)\n")
            elif max_blunder_phase[1] > 40:
                fh.write(f"• Pattern: Most blunders ({max_blunder_phase[1]:.0f}%) occur in {max_blunder_phase[0]}\n")
            else:
                fh.write(f"• Pattern: Blunders distributed across phases\n")
            
            # Strength
            fh.write(f"• Strength: Stable {strongest_phase[2].lower()}s with low CPL ({strongest_phase[1]:.1f} cp/move)\n")
            
            # Training focus (deterministic)
            fh.write(f"• Training focus:\n")
            if weakest_phase[2] == 'Endgame':
                fh.write(f"  - Endgame technique and simplification\n")
                fh.write(f"  - Converting +1.0 positions into wins\n")
                fh.write(f"  - Calculation accuracy in final phase\n")
            elif weakest_phase[2] == 'Middlegame':
                fh.write(f"  - Tactical puzzle solving and pattern recognition\n")
                fh.write(f"  - Position evaluation and planning\n")
                fh.write(f"  - Double-check calculations before moves\n")
            else:
                fh.write(f"  - Opening principles and theory\n")
                fh.write(f"  - Avoid repetitive mistakes in main lines\n")
                fh.write(f"  - Develop consistent opening preparation\n")
                fh.write(f"  → ({overall['trend_reason']})\n")

            # Legacy-style interpretation and coach summary (preserve old format)
            fh.write("\n💡 PHASE INTERPRETATION (LEGACY)\n")
            fh.write("-"*70 + "\n")
            fh.write(f"• Your opening play is relatively stable (CPL: {opening_cpl:.1f} cp/move).\n")
            fh.write(f"• The endgame shows the most room for improvement (CPL: {endgame_cpl:.1f} cp/move).\n")
            fh.write(f"• Pattern: severe accuracy drops in the {max_blunder_phase[0]}, accounting for {max_blunder_phase[1]:.0f}% of all blunders.\n\n")

            fh.write("\n🧠 COACH SUMMARY (LEGACY)\n")
            fh.write("="*70 + "\n")
            # Primary weakness (legacy phrasing)
            if overall['total_blunders'] > 0:
                fh.write(f"• Primary weakness: {weakest_phase[2]} accuracy\n")
                fh.write(f"  (CPL: {weakest_phase[1]:.1f} cp/move, {max_blunder_phase[1]:.0f}% of blunders)\n")
            else:
                fh.write(f"• Primary weakness: {weakest_phase[2]} play\n")
                fh.write(f"  (CPL: {weakest_phase[1]:.1f} cp/move)\n")

            fh.write(f"• Cause: Large centipawn swings in {weakest_phase[2]} phase\n")
            fh.write(f"  (Average blunder: −{int(avg_blunder_severity)} cp, Worst: −{max_blunder_severity} cp)\n")
            fh.write(f"• Pattern: High blunder concentration in {max_blunder_phase[0]} ({max_blunder_phase[1]:.0f}%)\n")
            fh.write(f"• Strength: Stable openings with low CPL ({strongest_phase[1]:.1f} cp/move)\n")
            fh.write(f"• Training focus:\n")
            if weakest_phase[2] == 'Endgame':
                fh.write(f"  - Endgame technique and simplification\n")
                fh.write(f"  - Converting +1.0 positions into wins\n")
                fh.write(f"  - Calculation accuracy in final phase\n")
            elif weakest_phase[2] == 'Middlegame':
                fh.write(f"  - Tactical puzzle solving and pattern recognition\n")
                fh.write(f"  - Position evaluation and planning\n")
                fh.write(f"  - Double-check calculations before moves\n")
            else:
                fh.write(f"  - Opening principles and theory\n")
                fh.write(f"  - Avoid repetitive mistakes in main lines\n")
                fh.write(f"  - Develop consistent opening preparation\n")
                fh.write(f"  → ({overall['trend_reason']})\n")
        
        print(f"✓ Analysis saved to {output_txt}")
        return 1
        
    except Exception as e:
        print(f"❌ Error in Phase 2: {e}")
        return 0


def main():
    """Interactive analyzer main."""
    print("\n" + "="*70)
    print("♟️  LICHESS CHESS ANALYZER")
    print("="*70)
    
    # Get username
    username = input("\n📝 Enter your Lichess username: ").strip()
    
    if not username:
        print("❌ Username cannot be empty")
        return 1
    
    # Get max games
    try:
        max_games_input = input("🎯 How many games to analyze? (default 15): ").strip()
        max_games = int(max_games_input) if max_games_input else 15
    except ValueError:
        max_games = 15
        print(f"ℹ️  Using default: {max_games} games")
    
    print("\n" + "="*70)
    print(f"🚀 FETCHING & ANALYZING: {username}")
    print(f"   Max games: {max_games}")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    try:
        # Fetch games
        t0 = time.time()
        csv_file, game_count = fetch_user_games(username, max_games=max_games)
        fetch_time = time.time() - t0
        
        if not csv_file or game_count == 0:
            print("\n❌ Failed to fetch games. Exiting.")
            return 1
        
        # Phase 1
        t0 = time.time()
        phase1_result = run_phase1_for_user(username, csv_file, max_games=max_games)
        phase1_time = time.time() - t0
        
        if not phase1_result:
            print("\n❌ Phase 1 failed. Exiting.")
            return 1
        
        # Phase 2
        t0 = time.time()
        phase2_count = run_phase2_for_user(username, max_games=max_games)
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
