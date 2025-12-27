"""Phase 2 analyzer: per-player and per-opening aggregates from engine-evaluated games."""

import glob
import os
import pandas as pd
from .engine_analysis import analyze_game_detailed
from .performance_metrics import (
    compute_game_cpl,
    compute_overall_cpl,
    aggregate_cpl_by_phase,
    compute_opening_stats,
    compute_time_control_stats,
)


def analyze_phase2(max_games_per_player=10, output_txt='phase2_results.txt', output_openings_csv='phase2_openings.csv'):
    """Run Phase 2 analysis across player files and save summary outputs.

    Args:
        max_games_per_player: int, number of games to analyze per player (default 10)
        output_txt: path to text summary
        output_openings_csv: path to openings CSV report

    Returns:
        results: list of per-player summary dicts
    """
    player_files = sorted(glob.glob('games_*.csv'))
    results = []
    combined_df_rows = []

    for csv_file in player_files:
        df = pd.read_csv(csv_file)
        player = os.path.basename(csv_file).replace('games_', '').replace('.csv', '')

        if 'moves_pgn' not in df.columns:
            # nothing to analyze for this file
            continue

        games_data = []
        analyzed_rows = []

        for _, row in df.head(max_games_per_player).iterrows():
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
            continue

        overall = compute_overall_cpl(games_data)
        phase_stats = aggregate_cpl_by_phase(games_data)

        summary = {
            'player': player,
            'games_analyzed': len(games_data),
            'overall_cpl': overall['overall_cpl'],
            'recent_cpl': overall['recent_cpl'],
            'trend': overall['trend'],
            'total_blunders': overall['total_blunders'],
            'total_mistakes': overall['total_mistakes'],
            'phase_stats': phase_stats,
            'weakest_phase': overall.get('weakest_phase', 'N/A'),
            'max_blunder_severity': overall.get('max_blunder_severity', 0),
            'avg_blunder_severity': overall.get('avg_blunder_severity', 0),
        }

        results.append(summary)

        # keep rows analyzed for opening/time-control aggregation
        for r in analyzed_rows:
            r['_player'] = player
            combined_df_rows.append(r)

    # Save textual summary
    with open(output_txt, 'w') as fh:
        fh.write('Phase 2 Analysis Summary\n')
        fh.write('='*60 + '\n')
        if not results:
            fh.write('No players analyzed.\n')
        else:
            for s in sorted(results, key=lambda x: x['overall_cpl']):
                fh.write(f"Player: {s['player']}\n")
                fh.write(f"  Games analyzed: {s['games_analyzed']}\n")
                fh.write(f"  CPL: {s['overall_cpl']} cp | Recent: {s['recent_cpl']} cp | Trend: {s['trend']}\n")
                fh.write(f"  Blunders: {s['total_blunders']} | Mistakes: {s['total_mistakes']}\n")
                fh.write('  By Phase:\n')
                for p in ['opening', 'middlegame', 'endgame']:
                    ps = s['phase_stats'].get(p, {})
                    fh.write(f"    {p}: CPL={ps.get('cpl')} cp, Blunders={ps.get('blunders')}\n")
                # Coach summary logic
                fh.write('  Coach Summary:\n')
                # Safety guard: ensure all keys exist and are safe to access
                total_blunders = s.get('total_blunders', 0)
                weakest_phase = s.get('weakest_phase', 'N/A')
                max_blunder_severity = s.get('max_blunder_severity', 0)
                avg_blunder_severity = s.get('avg_blunder_severity', 0)
                if total_blunders == 0:
                    fh.write('    Weakest Phase: Accuracy (no major blunders detected)\n')
                    fh.write('    Focus: Improve overall accuracy and reduce centipawn loss.\n')
                else:
                    fh.write(f"    Weakest Phase: {weakest_phase}\n")
                    fh.write(f"    Blunder Severity: max {max_blunder_severity} cp, avg {avg_blunder_severity} cp\n")
                fh.write('\n')
        fh.flush()

    # If we have combined rows, compute opening & time-control stats
    if combined_df_rows:
        combined_df = pd.DataFrame(combined_df_rows)
        try:
            openings = compute_opening_stats(combined_df)
            openings.to_csv(output_openings_csv)
        except Exception:
            # fallback: write combined rows
            combined_df.to_csv(output_openings_csv, index=False)

    return results


if __name__ == '__main__':
    res = analyze_phase2(max_games_per_player=10)
    print(f"Phase 2: analyzed {len(res)} players. Summary saved to 'phase2_results.txt' and openings report to 'phase2_openings.csv'.")
