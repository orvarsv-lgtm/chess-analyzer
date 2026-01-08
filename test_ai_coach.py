"""
Test script for AI Coach functionality
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test 1: Check API key is loaded
print("Test 1: Checking API key...")
api_key = os.getenv('OPENAI_API_KEY')
if api_key:
    print(f"✅ API key loaded: {api_key[:20]}...{api_key[-10:]}")
else:
    print("❌ API key not found!")
    exit(1)

# Test 2: Import AI Coach modules
print("\nTest 2: Importing AI Coach modules...")
try:
    from src.ai_coach import (
        generate_game_review,
        generate_demo_review,
        check_ai_coach_quota,
        _get_openai_client
    )
    print("✅ AI Coach modules imported successfully")
except Exception as e:
    print(f"❌ Failed to import: {e}")
    exit(1)

# Test 3: Test OpenAI client initialization
print("\nTest 3: Testing OpenAI client initialization...")
try:
    client = _get_openai_client()
    print(f"✅ OpenAI client initialized: {type(client)}")
except Exception as e:
    print(f"❌ Failed to initialize client: {e}")
    exit(1)

# Test 4: Test demo review (no API call)
print("\nTest 4: Testing demo review generation...")
try:
    demo_game = {
        'opening_name': 'Sicilian Defense: Najdorf Variation',
        'result': '0-1'
    }
    review = generate_demo_review(demo_game)
    print(f"✅ Demo review generated")
    print(f"   Summary: {review.game_summary[:100]}...")
    print(f"   Training recommendations: {len(review.training_recommendations)}")
except Exception as e:
    print(f"❌ Failed to generate demo review: {e}")
    exit(1)

# Test 5: Test quota checking
print("\nTest 5: Testing quota system...")
try:
    has_quota_free, remaining_free = check_ai_coach_quota('free', 'test_user')
    has_quota_serious, remaining_serious = check_ai_coach_quota('serious', 'test_user')
    print(f"✅ Quota check working")
    print(f"   Free tier: {has_quota_free}, remaining: {remaining_free}")
    print(f"   Serious tier: {has_quota_serious}, remaining: {remaining_serious}")
except Exception as e:
    print(f"❌ Failed quota check: {e}")
    exit(1)

# Test 6: Test real API call (simple position insight)
print("\nTest 6: Testing real OpenAI API call...")
print("   (This will use a small amount of credits, ~$0.001)")

try:
    from src.ai_coach import generate_position_insight
    
    insight = generate_position_insight(
        fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
        eval_before=20,
        eval_after=-50,
        best_move_san="d5",
        played_move_san="e5",
        phase="opening"
    )
    
    print(f"✅ Real API call successful!")
    print(f"   Response: {insight[:150]}...")
    
except Exception as e:
    print(f"❌ API call failed: {e}")
    print("   This might be due to:")
    print("   - Invalid API key")
    print("   - Network issues")
    print("   - OpenAI service down")
    exit(1)

print("\n" + "="*60)
print("🎉 ALL TESTS PASSED!")
print("="*60)
print("\n✅ AI Coach is ready to use!")
print("   - Navigate to http://localhost:8501")
print("   - Click '🤖 AI Coach' tab")
print("   - Analyze some games and generate AI reviews")
print("\n💡 Tip: Start with 'Demo Mode' to see sample output")
print("   Then switch to a paid tier (use sidebar selector)")
print("   to test real AI reviews with your analyzed games")
