"""Runner for Phase 2 analysis."""
from src.phase2 import analyze_phase2

if __name__ == '__main__':
    analyze_phase2(max_games_per_player=10, output_txt='phase2_results.txt', output_openings_csv='phase2_openings.csv')
    print('Phase 2 run complete.')
