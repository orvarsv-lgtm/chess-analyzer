"""
Streak Detection (NEW: #10)

Track win/loss streaks, blunder-free streaks, opening-specific streaks.
Motivational achievements and badges.
"""

import streamlit as st
from typing import Dict, List, Any, Optional
from datetime import datetime
from src.database import get_db


def detect_current_streaks(games_data: List[Dict[str, Any]], username: str) -> Dict[str, Any]:
    """
    Detect all active streaks from recent games.
    
    Streak types:
    - Win streak
    - Loss streak (to warn/motivate)
    - Blunder-free streak
    - Opening-specific win streak
    - Rating climb streak
    
    Returns:
        {
            'win_streak': int,
            'loss_streak': int,
            'blunder_free_streak': int,
            'opening_streaks': List[Dict],  # Opening-specific
            'best_win_streak': int,
            'achievement_unlocked': List[str],  # New milestones
        }
    """
    
    if not games_data:
        return {
            'win_streak': 0,
            'loss_streak': 0,
            'blunder_free_streak': 0,
            'opening_streaks': [],
            'best_win_streak': 0,
            'achievement_unlocked': [],
        }
    
    # Sort games by date (most recent first)
    sorted_games = sorted(
        games_data,
        key=lambda g: g.get('game_info', {}).get('date', ''),
        reverse=True
    )
    
    # Win/Loss streaks
    win_streak = 0
    loss_streak = 0
    
    for game in sorted_games:
        result = game.get('game_info', {}).get('score')
        
        if result == 'win':
            if loss_streak == 0:  # Still on win streak
                win_streak += 1
            else:
                break
        elif result == 'loss':
            if win_streak == 0:  # Still on loss streak
                loss_streak += 1
            else:
                break
        else:  # Draw breaks both streaks
            break
    
    # Blunder-free streak
    blunder_free_streak = 0
    
    for game in sorted_games:
        move_evals = game.get('move_evals', [])
        has_blunder = any(m.get('blunder_type') == 'blunder' for m in move_evals)
        
        if not has_blunder:
            blunder_free_streak += 1
        else:
            break
    
    # Opening-specific streaks
    opening_streaks = _detect_opening_streaks(sorted_games)
    
    # Get historical best from database
    db = get_db()
    all_streaks = db.get_streaks(username)
    
    best_win_streak = 0
    for streak in all_streaks:
        if streak.get('streak_type') == 'win':
            best_win_streak = max(best_win_streak, streak.get('best_count', 0))
    
    # Check for new achievements
    achievements = []
    
    if win_streak >= 5 and win_streak > best_win_streak:
        achievements.append(f"🔥 {win_streak}-game win streak!")
    
    if blunder_free_streak >= 3:
        achievements.append(f"✨ {blunder_free_streak} blunder-free games!")
    
    if blunder_free_streak >= 10:
        achievements.append("🏆 10-game blunder-free streak - Master level!")
    
    return {
        'win_streak': win_streak,
        'loss_streak': loss_streak,
        'blunder_free_streak': blunder_free_streak,
        'opening_streaks': opening_streaks,
        'best_win_streak': best_win_streak,
        'achievement_unlocked': achievements,
    }


def _detect_opening_streaks(sorted_games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect win streaks for specific openings."""
    
    opening_streaks = {}
    
    for game in sorted_games:
        opening = game.get('game_info', {}).get('opening_name', 'Unknown')
        result = game.get('game_info', {}).get('score')
        
        if opening not in opening_streaks:
            opening_streaks[opening] = {'current': 0, 'best': 0}
        
        if result == 'win':
            opening_streaks[opening]['current'] += 1
            opening_streaks[opening]['best'] = max(
                opening_streaks[opening]['best'],
                opening_streaks[opening]['current']
            )
        else:
            # Streak broken, but keep best
            opening_streaks[opening]['current'] = 0
    
    # Convert to list, filter notable streaks
    notable_streaks = []
    for opening, streak_data in opening_streaks.items():
        if streak_data['current'] >= 3:  # At least 3-game streak
            notable_streaks.append({
                'opening': opening,
                'current_streak': streak_data['current'],
                'best_streak': streak_data['best'],
            })
    
    # Sort by current streak
    notable_streaks.sort(key=lambda x: x['current_streak'], reverse=True)
    
    return notable_streaks[:5]  # Top 5


def update_streaks_in_db(username: str, games_data: List[Dict[str, Any]]):
    """Update streak records in database."""
    
    db = get_db()
    streaks = detect_current_streaks(games_data, username)
    
    # Update win streak
    if streaks['win_streak'] > 0:
        db.update_streak(username, 'win', increment=True)
    else:
        db.update_streak(username, 'win', increment=False)
    
    # Update blunder-free streak
    if streaks['blunder_free_streak'] > 0:
        db.update_streak(username, 'blunder_free', increment=True)
    else:
        db.update_streak(username, 'blunder_free', increment=False)
    
    # Update opening-specific streaks
    for opening_streak in streaks['opening_streaks']:
        context = json.dumps({'opening': opening_streak['opening']})
        db.update_streak(username, 'opening_specific', context=context, increment=True)


def render_streak_badges(streaks: Dict[str, Any]):
    """Render streak badges in Streamlit UI."""
    
    st.subheader("🔥 Current Streaks")
    
    # Achievement popups
    if streaks.get('achievement_unlocked'):
        for achievement in streaks['achievement_unlocked']:
            st.success(f"🎉 **Achievement Unlocked!** {achievement}")
    
    # Current streaks display
    col1, col2, col3 = st.columns(3)
    
    with col1:
        win_streak = streaks.get('win_streak', 0)
        best_win = streaks.get('best_win_streak', 0)
        
        if win_streak > 0:
            st.metric(
                "🏆 Win Streak",
                win_streak,
                delta=f"Best: {best_win}" if best_win > win_streak else "New record!",
                delta_color="normal"
            )
        else:
            st.metric("🏆 Win Streak", 0, delta="Start a new streak!")
    
    with col2:
        blunder_free = streaks.get('blunder_free_streak', 0)
        
        if blunder_free > 0:
            st.metric(
                "✨ Blunder-Free",
                f"{blunder_free} games",
                delta="Clean play!" if blunder_free >= 3 else None
            )
        else:
            st.metric("✨ Blunder-Free", 0)
    
    with col3:
        loss_streak = streaks.get('loss_streak', 0)
        
        if loss_streak > 0:
            st.metric(
                "⚠️ Loss Streak",
                loss_streak,
                delta="Time for a break?" if loss_streak >= 3 else "Bounce back!",
                delta_color="inverse"
            )
        else:
            st.metric("⚠️ Loss Streak", 0, delta="No losses!")
    
    # Opening-specific streaks
    opening_streaks = streaks.get('opening_streaks', [])
    
    if opening_streaks:
        st.write("### 🎯 Opening Win Streaks")
        
        for streak in opening_streaks:
            st.info(
                f"**{streak['opening']}**: "
                f"{streak['current_streak']} wins in a row! "
                f"(Best: {streak['best_streak']})"
            )


def get_streak_milestones() -> Dict[int, str]:
    """Define streak milestones for achievements."""
    
    return {
        3: "🥉 Bronze Streak",
        5: "🥈 Silver Streak",
        7: "🥇 Gold Streak",
        10: "💎 Diamond Streak",
        15: "👑 Master Streak",
        20: "🏆 Grandmaster Streak",
    }


def check_milestone_unlocked(streak_value: int, previous_best: int) -> Optional[str]:
    """Check if a milestone was just unlocked."""
    
    milestones = get_streak_milestones()
    
    for threshold, badge in sorted(milestones.items()):
        if streak_value >= threshold > previous_best:
            return badge
    
    return None


import json

def render_achievement_history(username: str):
    """Show historical achievements."""
    
    db = get_db()
    all_streaks = db.get_streaks(username)
    
    if not all_streaks:
        st.info("No achievements yet. Keep playing!")
        return
    
    st.write("### 🏅 Achievement History")
    
    # Group by type
    achievements = {
        'win': [],
        'blunder_free': [],
        'opening_specific': [],
    }
    
    for streak in all_streaks:
        streak_type = streak.get('streak_type')
        if streak_type in achievements:
            achievements[streak_type].append(streak)
    
    # Display
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Win Streaks**")
        for streak in achievements['win'][:5]:
            best = streak.get('best_count', 0)
            if best > 0:
                milestone = check_milestone_unlocked(best, 0)
                badge = milestone or "🔸"
                st.write(f"{badge} Best: {best} games")
    
    with col2:
        st.write("**Blunder-Free Streaks**")
        for streak in achievements['blunder_free'][:5]:
            best = streak.get('best_count', 0)
            if best > 0:
                st.write(f"✨ Best: {best} games")
    
    # Opening-specific
    if achievements['opening_specific']:
        st.write("**Opening Mastery**")
        for streak in achievements['opening_specific'][:10]:
            context = json.loads(streak.get('context', '{}'))
            opening = context.get('opening', 'Unknown')
            best = streak.get('best_count', 0)
            if best >= 3:
                st.write(f"🎯 {opening}: {best}-game win streak")
