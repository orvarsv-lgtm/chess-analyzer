"""Phase 1: Multi-Player Game Analysis with Engine Evaluation"""
import pandas as pd
import os
import glob
from src.engine_analysis import analyze_game_detailed
from src.performance_metrics import compute_overall_cpl, aggregate_cpl_by_phase

def analyze_player(csv_file, max_games=25):
    """Analyze games from a single player file"""
    try:
        df = pd.read_csv(csv_file)
        player_name = os.path.basename(csv_file).replace('games_', '').replace('.csv', '')
        
        # Check if file has moves_pgn column
        if 'moves_pgn' not in df.columns:
            print(f"⏭️  {player_name:<15} → No moves_pgn data (skipped)")
            return None
        
        print(f"\n{'='*70}")
        print(f"📂 {player_name.upper():<15} | {len(df):>3} total games | max {max_games}")
        print(f"{'='*70}")
        
        games_data = []
        failed_games = 0
        skipped_games = 0
        
        for idx, row in df.head(max_games).iterrows():
            moves_pgn = row.get("moves_pgn", "")
            if not moves_pgn or (isinstance(moves_pgn, float) and pd.isna(moves_pgn)):
                skipped_games += 1
                continue
                
            try:
                move_evals = analyze_game_detailed(moves_pgn, depth=20)
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
        
        return {
            "player": player_name,
            "games_analyzed": len(games_data),
            "overall_cpl": overall['overall_cpl'],
            "recent_cpl": overall['recent_cpl'],
            "total_blunders": overall['total_blunders'],
            "total_mistakes": overall['total_mistakes'],
            "phase_stats": phase_stats,
        }
        
    except Exception as e:
        print(f"❌ Error analyzing {csv_file}: {e}")
        return None

if __name__ == "__main__":
    # Main execution (script mode only; avoid running during pytest collection)
    try:
        print("\n" + "="*70)
        print("🔍 PHASE 1: MULTI-PLAYER GAME ANALYSIS WITH ENGINE EVALUATION")
        print("="*70)

        # Find all player game files
        player_files = sorted(glob.glob("games_*.csv"))
        if not player_files:
            print("❌ No player game files found")
            raise SystemExit(1)

        print(f"📁 Found {len(player_files)} player files\n")

        # Analyze each player
        results = []
        for csv_file in player_files:
            result = analyze_player(csv_file, max_games=25)
            if result:
                results.append(result)

        # Summary comparison
        if results:
            print(f"\n\n{'='*70}")
            print("📋 RANKING & COMPARATIVE SUMMARY")
            print(f"{'='*70}")
            print(f"{'Rank':<5} {'Player':<15} {'Games':>7} {'CPL':>8} {'Rec':>7} {'Blund':>6} {'Mist':>6}")
            print("-" * 70)

            sorted_results = sorted(results, key=lambda x: x["overall_cpl"])
            for rank, r in enumerate(sorted_results, 1):
                medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "  "
                print(
                    f"{medal} #{rank:<2} {r['player']:<15} {r['games_analyzed']:>7} {r['overall_cpl']:>8.1f} {r['recent_cpl']:>7.1f} {r['total_blunders']:>6} {r['total_mistakes']:>6}"
                )
        
            # Stats summary
            avg_cpl = sum(r["overall_cpl"] for r in results) / len(results)
            best_cpl = min(r["overall_cpl"] for r in results)
            worst_cpl = max(r["overall_cpl"] for r in results)
            total_games = sum(r["games_analyzed"] for r in results)

            print("\n📊 AGGREGATE STATS:")
            print(f"   Total games analyzed: {total_games}")
            print(f"   Average CPL: {avg_cpl:.1f} cp")
            print(f"   CPL Range: {best_cpl:.1f} - {worst_cpl:.1f} cp")
            print(f"\n✅ Phase 1 analysis complete! Analyzed {len(results)} players")
        else:
            print("❌ No valid results generated")

    except KeyboardInterrupt:
        print("\n⏸️  Analysis interrupted by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
