#!/usr/bin/env python
"""
Unified chess analyzer runner: Phase 1 (engine analysis) → Phase 2 (aggregation & reporting)
"""
import sys
import os
import time
import glob
import pandas as pd
from datetime import datetime

# Import from src package
from src.engine_analysis import analyze_game_detailed
from src.performance_metrics import compute_overall_cpl, aggregate_cpl_by_phase
from src.phase2 import analyze_phase2


def run_phase1(max_games=10):
    """Execute Phase 1: engine analysis of player games."""
    print("\n" + "="*70)
    print("🔍 PHASE 1: ENGINE ANALYSIS")
    print("="*70)
    
    player_files = sorted(glob.glob('games_*.csv'))
    print(f"📁 Found {len(player_files)} player files\n")
    
    phase1_results = []
    
    for csv_file in player_files:
        df = pd.read_csv(csv_file)
        player_name = os.path.basename(csv_file).replace('games_', '').replace('.csv', '')
        
        # Check if file has moves_pgn column
        if 'moves_pgn' not in df.columns:
            print(f"⏭️  {player_name:<15} → No moves_pgn data (skipped)")
            continue
        
        print(f"\n{'─'*70}")
        print(f"📂 {player_name.upper():<15} | {len(df):>3} total games | max {max_games}")
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
            continue
        
        # Compute metrics
        overall = compute_overall_cpl(games_data)
        phase_stats = aggregate_cpl_by_phase(games_data)
        
        # Display results
        print(f"\n  ✅ Processed: {len(games_data)}/{min(max_games, len(df))} games")
        if skipped_games > 0 or failed_games > 0:
            print(f"     Skipped: {skipped_games} | Failed: {failed_games}")
        print(f"\n  📈 OVERALL:")
        print(f"     CPL:            {overall['overall_cpl']:>7.1f} cp")
        print(f"     Recent CPL:     {overall['recent_cpl']:>7.1f} cp ({overall['trend']})")
        print(f"     Blunders:       {overall['total_blunders']:>7}")
        print(f"     Mistakes:       {overall['total_mistakes']:>7}")
        print(f"\n  🎯 BY PHASE:")
        for phase in ["opening", "middlegame", "endgame"]:
            stats = phase_stats[phase]
            print(f"     {phase.capitalize():11} | CPL: {stats['cpl']:7.1f} cp | Blunders: {stats['blunders']:2} | Win%: {stats['win_rate']:>6.1%}")
        
        phase1_results.append({
            "player": player_name,
            "games_analyzed": len(games_data),
            "overall_cpl": overall['overall_cpl'],
            "recent_cpl": overall['recent_cpl'],
            "total_blunders": overall['total_blunders'],
            "total_mistakes": overall['total_mistakes'],
            "phase_stats": phase_stats,
        })
    
    # Phase 1 summary
    if phase1_results:
        print(f"\n\n{'='*70}")
        print("📋 PHASE 1 RANKING")
        print(f"{'='*70}")
        print(f"{'Rank':<5} {'Player':<15} {'Games':>7} {'CPL':>8} {'Rec':>7} {'Blund':>6} {'Mist':>6}")
        print("-" * 70)
        
        sorted_results = sorted(phase1_results, key=lambda x: x['overall_cpl'])
        for rank, r in enumerate(sorted_results, 1):
            medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "  "
            print(f"{medal} #{rank:<2} {r['player']:<15} {r['games_analyzed']:>7} {r['overall_cpl']:>8.1f} {r['recent_cpl']:>7.1f} {r['total_blunders']:>6} {r['total_mistakes']:>6}")
        
        avg_cpl = sum(r['overall_cpl'] for r in phase1_results) / len(phase1_results)
        best_cpl = min(r['overall_cpl'] for r in phase1_results)
        worst_cpl = max(r['overall_cpl'] for r in phase1_results)
        total_games = sum(r['games_analyzed'] for r in phase1_results)
        
        print(f"\n📊 AGGREGATE STATS:")
        print(f"   Total games analyzed: {total_games}")
        print(f"   Average CPL: {avg_cpl:.1f} cp")
        print(f"   CPL Range: {best_cpl:.1f} - {worst_cpl:.1f} cp")
        print(f"\n✅ Phase 1 complete! Analyzed {len(phase1_results)} players")
    else:
        print("\n❌ Phase 1: No valid results generated")
    
    return len(phase1_results)


def run_phase2(max_games=10):
    """Execute Phase 2: aggregation and reporting."""
    print("\n\n" + "="*70)
    print("📊 PHASE 2: AGGREGATION & REPORTING")
    print("="*70)
    
    results = analyze_phase2(
        max_games_per_player=max_games,
        output_txt='phase2_results.txt',
        output_openings_csv='phase2_openings.csv'
    )
    
    print(f"\n✅ Phase 2 complete! Saved:")
    print(f"   - phase2_results.txt (summary by player)")
    print(f"   - phase2_openings.csv (opening statistics)")
    
    return len(results)


def main():
    """Run complete analysis pipeline."""
    print("\n" + "="*70)
    print("🚀 CHESS ANALYZER - COMPLETE PIPELINE")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    max_games = 10  # Can be made configurable
    
    try:
        # Phase 1
        t0 = time.time()
        phase1_count = run_phase1(max_games=max_games)
        phase1_time = time.time() - t0
        
        if phase1_count == 0:
            print("\n❌ Phase 1 yielded no results. Aborting pipeline.")
            return 1
        
        # Phase 2
        t0 = time.time()
        phase2_count = run_phase2(max_games=max_games)
        phase2_time = time.time() - t0
        
        # Final summary
        print("\n" + "="*70)
        print("✨ PIPELINE COMPLETE")
        print("="*70)
        print(f"📈 Phase 1: {phase1_count} players analyzed in {phase1_time:.1f}s")
        print(f"📊 Phase 2: {phase2_count} players aggregated in {phase2_time:.1f}s")
        print(f"   Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Total time: {(phase1_time + phase2_time):.1f}s")
        print("="*70 + "\n")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⏸️  Pipeline interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
