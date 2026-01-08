"""
Opponent Strength Adjustment (NEW: #9)

Normalize CPL by opponent rating to provide fair performance assessment.
Celebrate good games vs tough opponents, flag unexpected losses to weaker players.
"""

from typing import Dict, List, Any, Optional
import math


def calculate_expected_cpl(player_rating: int, opponent_rating: int, base_cpl: float = 40.0) -> float:
    """
    Calculate expected CPL based on rating difference.
    
    Theory: You're expected to play worse against stronger opponents.
    
    Formula: expected_cpl = base_cpl * rating_adjustment_factor
    
    Args:
        player_rating: Player's Elo rating
        opponent_rating: Opponent's Elo rating
        base_cpl: Baseline CPL for evenly-matched players
    
    Returns:
        Expected CPL for this matchup
    """
    
    rating_diff = opponent_rating - player_rating
    
    # Adjustment factor based on rating difference
    # +200 rating diff → expect ~20% higher CPL
    # -200 rating diff → expect ~15% lower CPL
    
    if rating_diff > 0:
        # Playing up (opponent stronger)
        # Allow higher CPL - it's normal to play worse vs stronger opponents
        adjustment = 1.0 + (rating_diff / 1000)  # +10% per 100 rating points
    else:
        # Playing down (opponent weaker)
        # Expect lower CPL - should play better vs weaker opponents
        adjustment = 1.0 + (rating_diff / 1500)  # Gentler adjustment downward
    
    # Cap adjustment to reasonable range (0.7 to 1.5x)
    adjustment = max(0.7, min(1.5, adjustment))
    
    return base_cpl * adjustment


def adjust_performance_for_opponent_strength(
    actual_cpl: float,
    player_rating: int,
    opponent_rating: int
) -> Dict[str, Any]:
    """
    Adjust performance metrics based on opponent strength.
    
    Returns:
        {
            'actual_cpl': float,
            'expected_cpl': float,
            'adjusted_performance': float,  # -100 to +100 scale
            'rating_diff': int,
            'performance_category': str,  # 'excellent', 'good', 'expected', 'poor', 'terrible'
            'message': str,  # Human-readable assessment
        }
    """
    
    rating_diff = opponent_rating - player_rating
    expected_cpl = calculate_expected_cpl(player_rating, opponent_rating)
    
    # Calculate performance relative to expectation
    # Negative = better than expected, Positive = worse than expected
    cpl_diff = actual_cpl - expected_cpl
    
    # Normalize to -100 to +100 scale
    # -30cp better than expected = +100 (excellent)
    # +30cp worse than expected = -100 (terrible)
    adjusted_performance = -1 * (cpl_diff / 30) * 100
    adjusted_performance = max(-100, min(100, adjusted_performance))
    
    # Categorize performance
    if adjusted_performance >= 50:
        category = 'excellent'
        message = f"🌟 Excellent game! Played {abs(cpl_diff):.0f}cp better than expected vs {opponent_rating}-rated opponent"
    elif adjusted_performance >= 20:
        category = 'good'
        message = f"✅ Good game! Slightly better than expected vs {opponent_rating}-rated opponent"
    elif adjusted_performance >= -20:
        category = 'expected'
        message = f"📊 As expected for this rating matchup ({player_rating} vs {opponent_rating})"
    elif adjusted_performance >= -50:
        category = 'poor'
        message = f"⚠️ Below expectations - {abs(cpl_diff):.0f}cp worse than expected for this matchup"
    else:
        category = 'terrible'
        message = f"❌ Significantly underperformed - {abs(cpl_diff):.0f}cp worse than expected"
    
    return {
        'actual_cpl': actual_cpl,
        'expected_cpl': round(expected_cpl, 1),
        'adjusted_performance': round(adjusted_performance, 1),
        'rating_diff': rating_diff,
        'performance_category': category,
        'message': message,
    }


def analyze_performance_vs_rating_brackets(games_data: List[Dict[str, Any]], player_rating: int) -> Dict[str, Any]:
    """
    Analyze performance across different opponent rating brackets.
    
    Brackets:
    - Much Stronger (+200+)
    - Stronger (+100 to +200)
    - Even (-100 to +100)
    - Weaker (-200 to -100)
    - Much Weaker (-200-)
    
    Returns stats for each bracket.
    """
    
    brackets = {
        'much_stronger': {'range': (200, 9999), 'games': [], 'name': 'Much Stronger (+200+)'},
        'stronger': {'range': (100, 200), 'games': [], 'name': 'Stronger (+100 to +200)'},
        'even': {'range': (-100, 100), 'games': [], 'name': 'Even Match (±100)'},
        'weaker': {'range': (-200, -100), 'games': [], 'name': 'Weaker (-200 to -100)'},
        'much_weaker': {'range': (-9999, -200), 'games': [], 'name': 'Much Weaker (-200-)'},
    }
    
    # Categorize games
    for game in games_data:
        game_info = game.get('game_info', {})
        opponent_elo = game_info.get('opponent_elo') or game_info.get('opponent_rating')
        
        if not opponent_elo:
            continue
        
        rating_diff = opponent_elo - player_rating
        
        # Find bracket
        for bracket_key, bracket_data in brackets.items():
            min_diff, max_diff = bracket_data['range']
            if min_diff <= rating_diff < max_diff:
                bracket_data['games'].append(game)
                break
    
    # Compute stats for each bracket
    bracket_stats = {}
    
    for bracket_key, bracket_data in brackets.items():
        games = bracket_data['games']
        
        if not games:
            bracket_stats[bracket_key] = {
                'name': bracket_data['name'],
                'games_played': 0,
                'avg_cpl': None,
                'win_rate': None,
                'performance_rating': None,
            }
            continue
        
        # Calculate stats
        cpls = []
        wins = 0
        
        for game in games:
            # Extract CPL
            move_evals = game.get('move_evals', [])
            if move_evals:
                game_cpls = [m.get('cp_loss', 0) for m in move_evals if m.get('cp_loss', 0) > 0]
                if game_cpls:
                    cpls.append(sum(game_cpls) / len(game_cpls))
            
            # Count wins
            if game.get('game_info', {}).get('score') == 'win':
                wins += 1
        
        avg_cpl = sum(cpls) / len(cpls) if cpls else None
        win_rate = (wins / len(games) * 100) if games else None
        
        # Calculate performance rating (Elo performance)
        # Simplified: player_rating + (win_rate - 50) * 10
        performance_rating = None
        if win_rate is not None:
            performance_rating = int(player_rating + (win_rate - 50) * 10)
        
        bracket_stats[bracket_key] = {
            'name': bracket_data['name'],
            'games_played': len(games),
            'avg_cpl': round(avg_cpl, 1) if avg_cpl else None,
            'win_rate': round(win_rate, 1) if win_rate else None,
            'performance_rating': performance_rating,
        }
    
    return bracket_stats


def identify_upsets_and_highlights(games_data: List[Dict[str, Any]], player_rating: int) -> Dict[str, List[Dict]]:
    """
    Identify notable games:
    - Upsets: Wins against much stronger opponents
    - Disappointments: Losses to much weaker opponents
    - Best performances: Lowest CPL vs tough opponents
    
    Returns:
        {
            'upsets': List[Dict],  # Wins vs +150+ opponents
            'disappointments': List[Dict],  # Losses vs -150+ opponents
            'best_performances': List[Dict],  # Top 3 games by adjusted performance
        }
    """
    
    upsets = []
    disappointments = []
    all_performances = []
    
    for game in games_data:
        game_info = game.get('game_info', {})
        opponent_elo = game_info.get('opponent_elo') or game_info.get('opponent_rating')
        
        if not opponent_elo:
            continue
        
        rating_diff = opponent_elo - player_rating
        result = game_info.get('score')
        
        # Calculate game CPL
        move_evals = game.get('move_evals', [])
        game_cpls = [m.get('cp_loss', 0) for m in move_evals if m.get('cp_loss', 0) > 0]
        avg_cpl = sum(game_cpls) / len(game_cpls) if game_cpls else 0
        
        # Adjusted performance
        adj_perf = adjust_performance_for_opponent_strength(avg_cpl, player_rating, opponent_elo)
        
        game_summary = {
            'opening': game_info.get('opening_name', 'Unknown'),
            'result': result,
            'opponent_rating': opponent_elo,
            'rating_diff': rating_diff,
            'cpl': round(avg_cpl, 1),
            'adjusted_performance': adj_perf['adjusted_performance'],
            'date': game_info.get('date'),
        }
        
        # Check for upsets
        if result == 'win' and rating_diff >= 150:
            upsets.append(game_summary)
        
        # Check for disappointments
        if result == 'loss' and rating_diff <= -150:
            disappointments.append(game_summary)
        
        # Track all for best performances
        all_performances.append(game_summary)
    
    # Sort by adjusted performance
    all_performances.sort(key=lambda x: x['adjusted_performance'], reverse=True)
    best_performances = all_performances[:3]
    
    # Sort upsets by rating diff
    upsets.sort(key=lambda x: x['rating_diff'], reverse=True)
    
    # Sort disappointments by rating diff (most negative)
    disappointments.sort(key=lambda x: x['rating_diff'])
    
    return {
        'upsets': upsets[:5],  # Top 5 upsets
        'disappointments': disappointments[:5],  # Top 5 disappointments
        'best_performances': best_performances,
    }


def render_opponent_strength_analysis(games_data: List[Dict[str, Any]], player_rating: int):
    """Render opponent strength analysis in Streamlit UI."""
    
    import streamlit as st
    import pandas as pd
    
    st.subheader("🎯 Performance vs Opponent Strength")
    
    # Bracket analysis
    bracket_stats = analyze_performance_vs_rating_brackets(games_data, player_rating)
    
    # Convert to DataFrame
    bracket_rows = []
    for bracket_key, stats in bracket_stats.items():
        if stats['games_played'] > 0:
            bracket_rows.append({
                'Opponent Strength': stats['name'],
                'Games': stats['games_played'],
                'Avg CPL': stats['avg_cpl'],
                'Win %': stats['win_rate'],
                'Performance Rating': stats['performance_rating'],
            })
    
    if bracket_rows:
        df = pd.DataFrame(bracket_rows)
        st.dataframe(df, hide_index=True, use_container_width=True)
        
        # Visualization
        st.bar_chart(df.set_index('Opponent Strength')['Win %'])
    else:
        st.info("No opponent rating data available")
    
    # Highlights
    st.write("---")
    highlights = identify_upsets_and_highlights(games_data, player_rating)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("### 🏆 Best Upset Wins")
        if highlights['upsets']:
            for upset in highlights['upsets']:
                st.success(
                    f"**{upset['opening']}** vs {upset['opponent_rating']} "
                    f"(+{upset['rating_diff']}) - {upset['cpl']}cp CPL"
                )
        else:
            st.info("No upset wins yet - keep playing!")
    
    with col2:
        st.write("### ⚠️ Disappointing Losses")
        if highlights['disappointments']:
            for loss in highlights['disappointments']:
                st.error(
                    f"**{loss['opening']}** vs {loss['opponent_rating']} "
                    f"({loss['rating_diff']}) - {loss['cpl']}cp CPL"
                )
        else:
            st.success("No disappointing losses!")
    
    # Best performances
    st.write("### ⭐ Best Performances (Adjusted)")
    if highlights['best_performances']:
        perf_df = pd.DataFrame(highlights['best_performances'])
        perf_df = perf_df.rename(columns={
            'opening': 'Opening',
            'result': 'Result',
            'opponent_rating': 'Opp Rating',
            'cpl': 'CPL',
            'adjusted_performance': 'Adj Score',
        })
        st.dataframe(perf_df[['Opening', 'Result', 'Opp Rating', 'CPL', 'Adj Score']], hide_index=True)
