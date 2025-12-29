def save_results(name, analyzed_games):
    """Save analysis results to CSV and TXT files."""
    df = pd.DataFrame(analyzed_games)
    df.to_csv(f"games_{name}.csv", index=False)
    with open(f"{name}_analysis.txt", "w", encoding="utf-8") as f:
        for game in analyzed_games:
            f.write(game.get("summary", "") + "\n\n")
def load_pgn_file(path):
    """Load PGN file from disk and return as string."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
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
    print("Welcome to Chess Analyzer!")
    print("Choose input source:")
    print("1. Lichess username")
    print("2. Chess.com PGN file")
    choice = input("Enter 1 or 2: ").strip()

    def main():
        print("Welcome to Chess Analyzer!")
        print("Choose input source:")
        print("1. Lichess username")
        print("2. Chess.com PGN file")
        choice = input("Enter 1 or 2: ").strip()

        if choice == "1":
            username = input("Enter Lichess username: ").strip()
            print(f"Fetching games for {username}...")
            games = fetch_and_parse_lichess_games(username)
            platform = "lichess"
            name = username
        elif choice == "2":
            pgn_path = input("Enter path to Chess.com PGN file: ").strip()
            print(f"Loading PGN from {pgn_path}...")
            pgn_str = load_pgn_file(pgn_path)
            games = parse_pgn(pgn_str)
            platform = "chess.com"
            import os
            name = os.path.splitext(os.path.basename(pgn_path))[0]
        else:
            print("Invalid choice. Exiting.")
            return

        # Add platform field to each game object
        for game in games:
            game["platform"] = platform

        print(f"Fetched {len(games)} games. Running analysis...")
        analyzed_games = analyze_games(games)
        save_results(name, analyzed_games)
        print(f"Analysis complete. Results saved to games_{name}.csv and {name}_analysis.txt.")
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
