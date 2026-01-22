"""
Opening Repertoire Builder (NEW: #8)

Track which openings you play, identify gaps in preparation,
generate study recommendations, track win% trends.
"""

import streamlit as st
from typing import Dict, List, Any, Optional
from src.database import get_db
import pandas as pd


def analyze_opening_repertoire(username: str, color: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyze user's opening repertoire.
    
    Returns comprehensive opening stats including:
    - Main openings by frequency
    - Win rates by opening
    - Early deviation detection  
    - Gaps in repertoire
    - Trend analysis
    """
    
    db = get_db()
    
    # Get all repertoire data
    repertoire = db.get_opening_repertoire(username, color=color)
    
    if not repertoire:
        return {
            'total_openings': 0,
            'main_openings': [],
            'weak_openings': [],
            'gaps_detected': [],
            'recommendations': []
        }
    
    # Convert to DataFrame for analysis
    df = pd.DataFrame(repertoire)
    
    # Main openings (top 5 by frequency)
    main_openings = df.nlargest(5, 'games_played')[
        ['opening_name', 'games_played', 'win_rate', 'average_cpl', 'deviation_rate']
    ].to_dict('records')
    
    # Weak openings (low win rate OR high CPL)
    weak_threshold_wr = 40  # Win rate < 40%
    weak_threshold_cpl = 50  # CPL > 50
    
    weak_openings = df[
        (df['win_rate'] < weak_threshold_wr) | (df['average_cpl'] > weak_threshold_cpl)
    ][['opening_name', 'games_played', 'win_rate', 'average_cpl', 'deviation_rate']].to_dict('records')
    
    # Gap detection: openings played infrequently
    gap_threshold = 3  # Less than 3 games
    gaps_detected = df[df['games_played'] < gap_threshold]['opening_name'].tolist()
    
    # High deviation rate openings (theory gaps)
    deviation_threshold = 30  # >30% early deviations
    high_deviation = df[df['deviation_rate'] > deviation_threshold][
        ['opening_name', 'deviation_rate', 'games_played']
    ].to_dict('records')
    
    # Generate recommendations
    recommendations = _generate_opening_recommendations(
        main_openings, weak_openings, gaps_detected, high_deviation
    )
    
    return {
        'total_openings': len(df),
        'main_openings': main_openings,
        'weak_openings': weak_openings,
        'gaps_detected': gaps_detected,
        'high_deviation_openings': high_deviation,
        'recommendations': recommendations,
        'repertoire_data': repertoire,
    }


def _generate_opening_recommendations(
    main_openings: List[Dict],
    weak_openings: List[Dict],
    gaps: List[str],
    high_deviation: List[Dict]
) -> List[str]:
    """Generate actionable opening study recommendations."""
    
    recommendations = []
    
    # Weak openings to study
    if weak_openings:
        for opening in weak_openings[:3]:  # Top 3 weakest
            recommendations.append(
                f"📚 Study **{opening['opening_name']}** - "
                f"Win rate: {opening['win_rate']:.0f}%, CPL: {opening['average_cpl']:.0f}"
            )
    
    # Theory gaps (high deviation rate)
    if high_deviation:
        for opening in high_deviation[:2]:
            recommendations.append(
                f"📖 Learn theory for **{opening['opening_name']}** - "
                f"{opening['deviation_rate']:.0f}% deviation rate in {opening['games_played']} games"
            )
    
    # Repertoire gaps (rarely played openings)
    if len(gaps) > 3:
        recommendations.append(
            f"🎯 Consolidate repertoire - {len(gaps)} openings played <3 times. "
            f"Focus on your main lines."
        )
    
    # Build repertoire depth for main openings
    if main_openings:
        top_opening = main_openings[0]
        if top_opening['games_played'] > 10:
            recommendations.append(
                f"⭐ Deepen **{top_opening['opening_name']}** - "
                f"Your most-played opening ({top_opening['games_played']} games). "
                f"Study advanced variations."
            )
    
    # Generate Lichess study links
    recommendations.append(
        f"🔗 **Lichess Opening Explorer**: https://lichess.org/analysis"
    )
    
    return recommendations


def render_opening_repertoire_ui(username: str):
    """Render opening repertoire UI in Streamlit."""
    
    st.subheader("📖 Opening Repertoire")
    
    # Color filter
    color_filter = st.radio(
        "Color",
        options=["Both", "White", "Black"],
        horizontal=True
    )
    
    color = color_filter.lower() if color_filter != "Both" else None
    
    # Analyze repertoire
    repertoire_data = analyze_opening_repertoire(username, color=color)
    
    if repertoire_data['total_openings'] == 0:
        st.info("No opening data yet. Play some games and analyze them to build your repertoire!")
        return
    
    # Overview metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Openings", repertoire_data['total_openings'])
    
    with col2:
        main_count = len(repertoire_data['main_openings'])
        st.metric("Main Openings", f"{main_count}/5")
    
    with col3:
        gaps_count = len(repertoire_data['gaps_detected'])
        st.metric("Gaps (< 3 games)", gaps_count, delta="Consolidate" if gaps_count > 5 else None)
    
    # Main openings table
    st.write("### 🎯 Your Main Openings")
    
    if repertoire_data['main_openings']:
        main_df = pd.DataFrame(repertoire_data['main_openings'])
        main_df = main_df.rename(columns={
            'opening_name': 'Opening',
            'games_played': 'Games',
            'win_rate': 'Win %',
            'average_cpl': 'Avg CPL',
            'deviation_rate': 'Deviation %'
        })
        st.dataframe(main_df, hide_index=True, width='stretch')
    else:
        st.info("Play more games to establish main openings")
    
    # Weak openings (improvement needed)
    if repertoire_data['weak_openings']:
        st.write("### ⚠️ Openings Needing Work")
        
        weak_df = pd.DataFrame(repertoire_data['weak_openings'])
        weak_df = weak_df.rename(columns={
            'opening_name': 'Opening',
            'games_played': 'Games',
            'win_rate': 'Win %',
            'average_cpl': 'Avg CPL',
            'deviation_rate': 'Deviation %'
        })
        st.dataframe(weak_df, hide_index=True, width='stretch')
    
    # Theory gaps (high deviation rate)
    if repertoire_data['high_deviation_openings']:
        st.write("### 📚 Theory Gaps (Early Deviations)")
        
        dev_df = pd.DataFrame(repertoire_data['high_deviation_openings'])
        dev_df = dev_df.rename(columns={
            'opening_name': 'Opening',
            'deviation_rate': 'Deviation %',
            'games_played': 'Games'
        })
        st.dataframe(dev_df, hide_index=True, width='stretch')
    
    # Recommendations
    st.write("### 💡 Study Recommendations")
    
    for rec in repertoire_data['recommendations']:
        if rec.startswith('📚') or rec.startswith('📖'):
            st.warning(rec)
        elif rec.startswith('⭐'):
            st.success(rec)
        else:
            st.info(rec)
    
    # Detailed repertoire table (expandable)
    with st.expander("📊 Full Repertoire Details"):
        full_df = pd.DataFrame(repertoire_data['repertoire_data'])
        
        # Format columns
        display_cols = [
            'opening_name', 'color', 'games_played', 'win_rate',
            'average_cpl', 'deviation_rate', 'last_played_at'
        ]
        
        display_df = full_df[display_cols].rename(columns={
            'opening_name': 'Opening',
            'color': 'Color',
            'games_played': 'Games',
            'win_rate': 'Win %',
            'average_cpl': 'Avg CPL',
            'deviation_rate': 'Deviation %',
            'last_played_at': 'Last Played'
        })
        
        st.dataframe(display_df, hide_index=True, width='stretch')


def generate_lichess_study_link(opening_name: str, color: str) -> str:
    """
    Generate Lichess opening explorer link for an opening.
    
    Example: https://lichess.org/analysis?fen=...&variant=standard
    """
    
    # Simplified - would need proper opening position FENs
    # For now, return generic opening explorer
    base_url = "https://lichess.org/analysis"
    
    # Could enhance with specific ECO codes/positions
    return f"{base_url}#explorer"


def track_opening_trend(username: str, opening_name: str, color: str, last_n_games: int = 20) -> Dict[str, Any]:
    """
    Track win rate trend for a specific opening over time.
    
    Returns:
        {
            'opening': str,
            'total_games': int,
            'recent_win_rate': float,  # Last N games
            'overall_win_rate': float,
            'trend': str,  # 'improving', 'stable', 'declining'
            'games_timeline': List[Dict],  # Per-game data for charting
        }
    """
    
    db = get_db()
    
    # Get games for this opening
    games = db.get_games(
        username,
        filters={'opening_name': opening_name}
    )
    
    if not games:
        return None
    
    # Filter by color if specified
    if color:
        games = [g for g in games if g.get('color') == color]
    
    # Calculate overall stats
    total_games = len(games)
    overall_wins = sum(1 for g in games if g.get('result') == 'win')
    overall_win_rate = (overall_wins / total_games * 100) if total_games > 0 else 0
    
    # Recent games stats
    recent_games = games[:last_n_games]
    recent_wins = sum(1 for g in recent_games if g.get('result') == 'win')
    recent_win_rate = (recent_wins / len(recent_games) * 100) if recent_games else 0
    
    # Determine trend
    if recent_win_rate > overall_win_rate + 10:
        trend = 'improving'
    elif recent_win_rate < overall_win_rate - 10:
        trend = 'declining'
    else:
        trend = 'stable'
    
    # Games timeline for charting
    games_timeline = []
    for i, game in enumerate(games[:50]):  # Last 50 games
        games_timeline.append({
            'game_number': i + 1,
            'date': game.get('date'),
            'result': game.get('result'),
            'elo': game.get('player_elo'),
        })
    
    return {
        'opening': opening_name,
        'total_games': total_games,
        'recent_win_rate': round(recent_win_rate, 1),
        'overall_win_rate': round(overall_win_rate, 1),
        'trend': trend,
        'games_timeline': games_timeline,
    }
