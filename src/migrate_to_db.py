"""
Migration utility to convert CSV/JSONL data to SQLite database.

Run once to migrate existing data.
"""

import pandas as pd
import json
from pathlib import Path
from typing import Optional
import glob

from src.database import get_db
from puzzles.puzzle_types import Puzzle
from puzzles.global_puzzle_store import puzzle_key_for_puzzle


def migrate_csv_games():
    """Migrate all games_*.csv files to database."""
    db = get_db()
    csv_files = glob.glob("games_*.csv")
    
    total_games = 0
    for csv_file in csv_files:
        username = csv_file.replace("games_", "").replace(".csv", "")
        print(f"Migrating {csv_file} for user {username}...")
        
        try:
            df = pd.read_csv(csv_file)
            for _, row in df.iterrows():
                game_data = {
                    'username': username,
                    'platform': row.get('platform', 'lichess'),
                    'game_id': None,  # Not stored in CSV
                    'date': row.get('date', ''),
                    'color': row.get('color', ''),
                    'score': row.get('score', ''),
                    'opening': row.get('opening', ''),
                    'opening_name': row.get('opening_name', ''),
                    'eco': row.get('eco'),
                    'time_control': row.get('time_control', ''),
                    'white_elo': row.get('white_elo'),
                    'black_elo': row.get('black_elo'),
                    'elo': row.get('elo'),
                    'opponent_elo': None,  # Calculate from white/black elo
                    'moves': row.get('moves'),
                    'moves_pgn': row.get('moves_pgn', ''),
                }
                
                # Calculate opponent elo
                if game_data['color'] == 'white':
                    game_data['opponent_elo'] = game_data['black_elo']
                else:
                    game_data['opponent_elo'] = game_data['white_elo']
                
                db.insert_game(game_data)
                total_games += 1
        except Exception as e:
            print(f"  Error migrating {csv_file}: {e}")
            continue
    
    print(f"✓ Migrated {total_games} games from {len(csv_files)} CSV files")


def migrate_jsonl_puzzles():
    """Migrate puzzles_global.jsonl to database."""
    db = get_db()
    puzzles_file = Path("data/puzzles_global.jsonl")
    
    if not puzzles_file.exists():
        print("No puzzles_global.jsonl found, skipping")
        return
    
    total_puzzles = 0
    with open(puzzles_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            try:
                record = json.loads(line)
                puzzle_dict = record.get('puzzle', {})
                
                puzzle_data = {
                    'puzzle_key': record.get('puzzle_key', ''),
                    'source_game_id': None,  # Would need to map from original game
                    'source_user': record.get('source_user'),
                    'fen': puzzle_dict.get('fen', ''),
                    'side_to_move': puzzle_dict.get('side_to_move', ''),
                    'best_move_san': puzzle_dict.get('best_move_san', ''),
                    'best_move_uci': puzzle_dict.get('best_move_uci'),
                    'played_move_san': puzzle_dict.get('played_move_san'),
                    'eval_loss_cp': puzzle_dict.get('eval_loss_cp', 0),
                    'phase': puzzle_dict.get('phase', 'middlegame'),
                    'puzzle_type': puzzle_dict.get('puzzle_type', 'missed_tactic'),
                    'difficulty': puzzle_dict.get('difficulty', 'medium'),
                    'move_number': puzzle_dict.get('move_number'),
                    'explanation': puzzle_dict.get('explanation'),
                    'themes': puzzle_dict.get('themes', []),
                }
                
                db.insert_puzzle(puzzle_data)
                total_puzzles += 1
            except Exception as e:
                print(f"  Error migrating puzzle: {e}")
                continue
    
    print(f"✓ Migrated {total_puzzles} puzzles")


def migrate_jsonl_ratings():
    """Migrate puzzle_ratings.jsonl to database."""
    db = get_db()
    ratings_file = Path("data/puzzle_ratings.jsonl")
    
    if not ratings_file.exists():
        print("No puzzle_ratings.jsonl found, skipping")
        return
    
    # This is more complex - need to map puzzle_key to puzzle_id
    # For now, skip or implement later
    print("Ratings migration not yet implemented (requires puzzle_key → puzzle_id mapping)")


def migrate_all():
    """Run all migrations."""
    print("="*70)
    print("MIGRATING DATA TO SQLITE DATABASE")
    print("="*70)
    
    print("\n1. Migrating game data from CSV files...")
    migrate_csv_games()
    
    print("\n2. Migrating puzzles from JSONL...")
    migrate_jsonl_puzzles()
    
    print("\n3. Migrating ratings from JSONL...")
    migrate_jsonl_ratings()
    
    print("\n" + "="*70)
    print("MIGRATION COMPLETE!")
    print("="*70)
    print("\nYou can now use the database instead of CSV/JSONL files.")
    print("Original files have been preserved (not deleted).")


if __name__ == "__main__":
    migrate_all()
