from .lichess_api import fetch_lichess_pgn, parse_pgn
import pandas as pd
import os
from .engine_analysis import analyze_game, analyze_game_detailed
from .performance_metrics import (
    compute_overall_cpl,
    aggregate_cpl_by_phase,
    compute_opening_stats,
    compute_time_control_stats,
)


def main():
    print("Chess Analyzer - Lichess Games")
    print("=" * 40)
    
    username = input("Enter Lichess username: ").strip()
    
    # Use per-username CSV file
    csv_file = f"games_{username}.csv"
    
    # Check if data already exists for this username
    if os.path.exists(csv_file):
        print(f"\nLoading cached games from {csv_file}...")
        df = pd.read_csv(csv_file)
        print(f"Loaded {len(df)} games from cache\n")
        from_cache = True
    else:
        print(f"\nFetching games for {username}...")
        try:
            pgn_text = fetch_lichess_pgn(username=username, max_games=100)
            print(f"Downloaded {len(pgn_text)} characters of PGN data")
        except ValueError as e:
            print(f"\n{e}")
            return
        except Exception as e:
            print(f"\n❌ {e}")
            return

        print("Parsing games...")
        games = parse_pgn(pgn_text, username)
        print(f"Successfully parsed {len(games)} games\n")

        if len(games) == 0:
            print("No games found!")
            return

        df = pd.DataFrame(games)
        
        # Save to per-username CSV
        df.to_csv(csv_file, index=False)
        print(f"Saved {len(df)} games to {csv_file}\n")
        from_cache = False
    
    # ===== PHASE 1: PERFORMANCE METRICS =====
    
    # Analyze all games with engine (build structured data for metrics)
    print("Computing performance metrics...")
    games_data = []
    for idx, row in df.iterrows():
        moves_pgn = row.get("moves_pgn", "")
        if moves_pgn:
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
    
    # Display engine analysis for most recent game
    if not df.empty and "moves_pgn" in df.columns:
        print("\nAnalyzing the most recent game with Stockfish...")
        recent_game_moves = df.iloc[-1]["moves_pgn"]
        analyze_game(recent_game_moves)
    
    # ===== OVERALL CPL =====
    print("\n" + "=" * 40)
    print("PERFORMANCE METRICS")
    print("=" * 40)
    
    overall_stats = compute_overall_cpl(games_data)
    print(f"Overall Average CPL:  {overall_stats['overall_cpl']:6.1f} cp")
    print(f"Last 10 games CPL:    {overall_stats['recent_cpl']:6.1f} cp ({overall_stats['trend']})")
    print(f"Total blunders:       {overall_stats['total_blunders']}")
    print(f"Total mistakes:       {overall_stats['total_mistakes']}")
    
    # ===== BLUNDERS BY PHASE =====
    print("\n" + "=" * 40)
    print("BLUNDERS BY PHASE")
    print("=" * 40)
    
    phase_stats = aggregate_cpl_by_phase(games_data)
    for phase in ["opening", "middlegame", "endgame"]:
        stats = phase_stats[phase]
        print(f"\n{phase.upper()}:")
        print(f"  CPL:       {stats['cpl']:6.1f} cp")
        print(f"  Blunders:  {stats['blunders']:3d}")
        print(f"  Mistakes:  {stats['mistakes']:3d}")
        print(f"  Games:     {stats['games']:3d}")
        if stats['games'] > 0:
            print(f"  Win rate:  {stats['win_rate']:5.1f}%")
    
    # ===== ELO STATISTICS =====
    if "elo" in df.columns:
        df["elo"] = pd.to_numeric(df["elo"], errors="coerce")
        elo_series = df["elo"].dropna()
        if not elo_series.empty:
            avg_elo = int(elo_series.mean())
            recent_elos = elo_series.tail(10).astype(int).tolist()

            print("\n" + "=" * 40)
            print("ELO STATISTICS")
            print("=" * 40)
            print(f"Average elo: {avg_elo}")
            print("Recent elos (last 10): " + ", ".join(str(e) for e in recent_elos))

            for color in ["white", "black"]:
                color_elos = pd.to_numeric(df[df["color"] == color]["elo"], errors="coerce").dropna()
                if not color_elos.empty:
                    print(f"{color.title()} avg elo: {int(color_elos.mean())}")

    # ===== OPENING PERFORMANCE (by opening_name) =====
    if "opening_name" in df.columns:
        print("\n" + "=" * 40)
        print("TOP OPENINGS (by name)")
        print("=" * 40)
        opening_stats_df = compute_opening_stats(df)
        if not opening_stats_df.empty:
            for idx, (opening_name, row) in enumerate(opening_stats_df.head(10).iterrows(), 1):
                print(f"{idx:2d}. {opening_name:30s} {int(row['games']):3d} games, {row['win_rate']:5.1f}% win")

    # ===== TIME CONTROL ANALYSIS =====
    print("\n" + "=" * 40)
    print("TIME CONTROL PERFORMANCE")
    print("=" * 40)
    tc_stats = compute_time_control_stats(df)
    if not tc_stats.empty:
        for tc, row in tc_stats.iterrows():
            print(f"{tc:15s} {int(row['games']):3d} games, {row['win_rate']:5.1f}% win")
    else:
        print("No time control data available")

    # ===== OVERALL STATISTICS =====
    print("\n" + "=" * 40)
    print("OVERALL STATISTICS")
    print("=" * 40)
    
    total_games = len(df)
    wins = (df["score"] == "win").sum()
    losses = (df["score"] == "loss").sum()
    draws = (df["score"] == "draw").sum()
    win_rate = (wins / total_games) * 100 if total_games > 0 else 0
    
    print(f"Total games: {total_games}")
    print(f"Wins: {wins} ({win_rate:.1f}%)")
    print(f"Losses: {losses}")
    print(f"Draws: {draws}")

    # Statistics by color
    print("\n" + "=" * 40)
    print("STATISTICS BY COLOR")
    print("=" * 40)
    
    for color in ["white", "black"]:
        color_df = df[df["color"] == color]
        if len(color_df) > 0:
            color_wins = (color_df["score"] == "win").sum()
            color_total = len(color_df)
            color_win_rate = (color_wins / color_total) * 100
            print(f"\n{color.upper()}:")
            print(f"  Games: {color_total}")
            print(f"  Wins: {color_wins} ({color_win_rate:.1f}%)")
            print(f"  Draws: {(color_df['score'] == 'draw').sum()}")
            print(f"  Losses: {(color_df['score'] == 'loss').sum()}")
            print(f"  Avg moves: {color_df['moves'].mean():.1f}")

    # Recent performance
    print("\n" + "=" * 40)
    print("RECENT PERFORMANCE (Last 10 games)")
    print("=" * 40)
    
    recent_10 = df.tail(10)[["date", "color", "opening", "score", "moves", "time_control"]]
    print(recent_10.to_string(index=False))


if __name__ == "__main__":
    main()
