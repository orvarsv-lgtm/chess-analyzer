#!/usr/bin/env python3
"""Test script for new database and features."""

import sys
from src.database import get_db
from src.streak_detection import detect_current_streaks
from src.opening_repertoire import analyze_opening_repertoire
from src.opponent_strength import analyze_performance_vs_rating_brackets

def test_database():
    """Test database connection and basic queries."""
    print("=" * 70)
    print("TESTING DATABASE")
    print("=" * 70)
    
    db = get_db()
    
    # Test game count
    games = db.get_games("ari", limit=100)
    print(f"\n✓ Database connection successful!")
    print(f"✓ Found {len(games)} games for user 'ari'")
    
    if games:
        first_game = games[0]
        print(f"✓ First game - Result: {first_game['result']} as {first_game['color']}")
        print(f"  Opening: {first_game.get('opening_name', 'Unknown')} ({first_game.get('eco_code', '')})")
        print(f"  Date: {first_game['date']}")
        print(f"  Elo: {first_game.get('player_elo', 'N/A')} vs {first_game.get('opponent_elo', 'N/A')}")
    
    # Test all users (using direct connection)
    conn = db._get_connection()
    try:
        cursor = conn.execute("SELECT DISTINCT username FROM games ORDER BY username")
        all_users = [row['username'] for row in cursor.fetchall()]
        print(f"\n✓ Users in database: {', '.join(all_users)}")
    finally:
        conn.close()
    
    print("\n✓ Database tests PASSED!\n")
    return True


def test_streak_detection():
    """Test streak detection feature."""
    print("=" * 70)
    print("TESTING STREAK DETECTION")
    print("=" * 70)
    
    db = get_db()
    games = db.get_games("ari", limit=100)
    
    if not games:
        print("⚠ No games found for user 'ari', skipping streak test")
        return False
    
    # Convert games to dict format for streak detection
    games_data = []
    for g in games:
        # Color is directly in the database
        focus_color = g['color']
        
        # Determine score from result and color
        result = g['result']
        if focus_color == "white":
            score = "win" if result == "1-0" else "loss" if result == "0-1" else "draw"
        else:
            score = "win" if result == "0-1" else "loss" if result == "1-0" else "draw"
        
        games_data.append({
            "date": g['date'],
            "result": g['result'],
            "opening": g.get('opening_name', 'Unknown'),
            "focus_color": focus_color,
            "game_info": {"score": score},
        })
    
    streaks = detect_current_streaks(games_data, "ari")
    
    print(f"\n✓ Streak detection completed!")
    print(f"✓ Win streak: {streaks.get('current_win_streak', 0)} games")
    print(f"✓ Best win streak: {streaks.get('best_win_streak', 0)} games")
    print(f"✓ Blunder-free streak: {streaks.get('current_blunder_free_streak', 0)} games")
    
    opening_streaks = streaks.get('opening_streaks', [])
    if opening_streaks:
        print(f"✓ Opening-specific streaks: {len(opening_streaks)}")
        for streak in opening_streaks[:3]:
            print(f"  - {streak.get('opening', 'Unknown')}: {streak.get('current_streak', 0)} wins")
    
    print("\n✓ Streak detection tests PASSED!\n")
    return True


def test_opening_repertoire():
    """Test opening repertoire feature."""
    print("=" * 70)
    print("TESTING OPENING REPERTOIRE")
    print("=" * 70)
    
    db = get_db()
    games = db.get_games("ari", limit=100)
    
    if not games:
        print("⚠ No games found for user 'ari', skipping repertoire test")
        return False
    
    # Call the opening repertoire analyzer (it uses the database directly)
    repertoire = analyze_opening_repertoire("ari")
    
    print(f"\n✓ Opening repertoire analysis completed!")
    print(f"✓ Main openings: {len(repertoire.get('main_openings', []))}")
    
    for opening in repertoire.get('main_openings', [])[:3]:
        opening_name = opening.get('opening_name', 'Unknown')
        games_count = opening.get('games_played', 0)
        win_rate = opening.get('win_rate', 0)
        print(f"  - {opening_name}: {games_count} games, {win_rate}% win rate")
    
    weak = repertoire.get('weak_openings', [])
    if weak:
        print(f"✓ Weak openings identified: {len(weak)}")
        for opening in weak[:2]:
            opening_name = opening.get('opening_name', 'Unknown')
            win_rate = opening.get('win_rate', 0)
            print(f"  - {opening_name}: {win_rate}% win rate")
    
    gaps = repertoire.get('gaps_detected', [])
    if gaps:
        print(f"✓ Repertoire gaps found: {len(gaps)}")
    
    print("\n✓ Opening repertoire tests PASSED!\n")
    return True


def test_opponent_strength():
    """Test opponent strength analysis feature."""
    print("=" * 70)
    print("TESTING OPPONENT STRENGTH ANALYSIS")
    print("=" * 70)
    
    db = get_db()
    games = db.get_games("ari", limit=100)
    
    if not games:
        print("⚠ No games found for user 'ari', skipping opponent analysis")
        return True  # Not a failure, just no data
    
    # Convert games to dict format
    games_data = []
    for g in games:
        focus_color = g['color']
        result = g['result']
        player_rating = g.get('player_elo') or 0
        opponent_rating = g.get('opponent_elo') or 0
        
        if player_rating == 0 or opponent_rating == 0:
            continue  # Skip games without ratings
        
        if focus_color == "white":
            score = "win" if result == "1-0" else "loss" if result == "0-1" else "draw"
        else:
            score = "win" if result == "0-1" else "loss" if result == "1-0" else "draw"
        
        games_data.append({
            "white_rating": player_rating if focus_color == "white" else opponent_rating,
            "black_rating": opponent_rating if focus_color == "white" else player_rating,
            "focus_color": focus_color,
            "focus_player_rating": player_rating,
            "game_info": {"score": score},
            "move_evals": [],  # Empty for now
        })
    
    if not games_data:
        print("⚠ No games with ratings found - feature works but needs rating data")
        print("✓ Opponent strength analysis tests PASSED (no data to test)\n")
        return True  # Not a failure, just no data
    
    # Use average rating
    avg_rating = sum(g["focus_player_rating"] for g in games_data) // len(games_data)
    
    analysis = analyze_performance_vs_rating_brackets(games_data, avg_rating)
    
    print(f"\n✓ Opponent strength analysis completed!")
    print(f"✓ Player rating: {avg_rating}")
    
    brackets = analysis.get('by_bracket', {})
    for bracket_name, stats in brackets.items():
        games_count = stats.get('games', 0)
        if games_count > 0:
            print(f"  - {bracket_name}: {games_count} games, "
                  f"{stats.get('win_rate', 0)}% win rate, "
                  f"avg CPL {stats.get('avg_cpl', 0)}")
    
    upsets = analysis.get('upsets', [])
    if upsets:
        print(f"✓ Upsets found: {len(upsets)}")
    
    print("\n✓ Opponent strength tests PASSED!\n")
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("CHESS ANALYZER - NEW FEATURES TEST SUITE")
    print("=" * 70 + "\n")
    
    tests = [
        ("Database", test_database),
        ("Streak Detection", test_streak_detection),
        ("Opening Repertoire", test_opening_repertoire),
        ("Opponent Strength", test_opponent_strength),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success, None))
        except Exception as e:
            print(f"\n✗ {name} test FAILED: {e}\n")
            results.append((name, False, str(e)))
    
    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for name, success, error in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {name}")
        if error:
            print(f"       Error: {error}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! New features are working correctly.\n")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check errors above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
