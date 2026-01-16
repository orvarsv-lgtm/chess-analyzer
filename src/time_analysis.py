"""
Time Analysis Module

Analyzes per-move clock data to identify time management patterns:
- Time trouble detection
- Time spent per phase
- Fast moves vs blunders correlation
- Long thinks analysis
- Time management across game progression
"""

from typing import Dict, List, Any, Optional, Tuple


def has_clock_data(games: List[Dict[str, Any]]) -> bool:
    """Check if any games have clock data available."""
    for game in games:
        if game.get('has_clock_data', False):
            return True
    return False


def get_games_with_clock_data(games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter games that have clock data."""
    return [g for g in games if g.get('has_clock_data', False)]


def compute_time_per_move(move_clocks: List[Dict[str, Any]], player_color: str) -> List[Dict[str, Any]]:
    """
    Compute time spent per move for the player.
    
    Args:
        move_clocks: List of move clock data from game
        player_color: 'white' or 'black'
        
    Returns:
        List of dicts with move_number, san, time_spent, clock_remaining
    """
    player_moves = [m for m in move_clocks if m['color'] == player_color]
    
    result = []
    prev_clock = None
    
    for i, move in enumerate(player_moves):
        clock = move.get('clock_seconds')
        if clock is None:
            continue
            
        if prev_clock is not None:
            time_spent = prev_clock - clock
            # Negative time can happen with increment
            time_spent = max(0, time_spent)
        else:
            time_spent = None  # First move, no reference
        
        result.append({
            'move_number': move['move_number'],
            'ply': move['ply'],
            'san': move['san'],
            'time_spent': time_spent,
            'clock_remaining': clock,
        })
        prev_clock = clock
    
    return result


def analyze_time_by_phase(
    time_per_move: List[Dict[str, Any]],
    total_moves: int
) -> Dict[str, Any]:
    """
    Analyze time usage by game phase.
    
    Phase definitions (by player's move number):
    - Opening: moves 1-15
    - Middlegame: moves 16-40
    - Endgame: moves 41+
    
    Returns:
        Dict with phase-wise time stats
    """
    phases = {
        'opening': {'moves': [], 'total_time': 0, 'count': 0},
        'middlegame': {'moves': [], 'total_time': 0, 'count': 0},
        'endgame': {'moves': [], 'total_time': 0, 'count': 0},
    }
    
    for move in time_per_move:
        move_num = move['move_number']
        time_spent = move.get('time_spent')
        
        if time_spent is None:
            continue
        
        if move_num <= 15:
            phase = 'opening'
        elif move_num <= 40:
            phase = 'middlegame'
        else:
            phase = 'endgame'
        
        phases[phase]['moves'].append(move)
        phases[phase]['total_time'] += time_spent
        phases[phase]['count'] += 1
    
    # Calculate averages
    result = {}
    for phase, data in phases.items():
        if data['count'] > 0:
            result[phase] = {
                'avg_time_per_move': round(data['total_time'] / data['count'], 1),
                'total_time': round(data['total_time'], 1),
                'move_count': data['count'],
            }
        else:
            result[phase] = {
                'avg_time_per_move': 0,
                'total_time': 0,
                'move_count': 0,
            }
    
    return result


def detect_time_trouble_moves(
    time_per_move: List[Dict[str, Any]],
    time_control: str
) -> Dict[str, Any]:
    """
    Detect moves made in time trouble.
    
    Time trouble thresholds based on time control:
    - Rapid (10+ min): < 60 seconds remaining
    - Blitz (3-10 min): < 30 seconds remaining
    - Bullet (< 3 min): < 10 seconds remaining
    
    Returns:
        Dict with time trouble analysis
    """
    # Parse time control
    try:
        if '+' in time_control:
            parts = time_control.split('+')
            initial_seconds = int(parts[0])
            increment = int(parts[1]) if len(parts) > 1 else 0
        else:
            initial_seconds = int(time_control)
            increment = 0
        
        estimated_time = initial_seconds + 40 * increment
        
        if estimated_time >= 600:  # Rapid
            threshold = 60
        elif estimated_time >= 180:  # Blitz
            threshold = 30
        else:  # Bullet
            threshold = 10
    except (ValueError, TypeError):
        threshold = 30  # Default
    
    time_trouble_moves = []
    normal_moves = []
    
    for move in time_per_move:
        clock = move.get('clock_remaining')
        time_spent = move.get('time_spent')
        
        if clock is None:
            continue
        
        if clock <= threshold:
            time_trouble_moves.append(move)
        else:
            normal_moves.append(move)
    
    # Calculate average time spent in each zone
    avg_normal = 0
    avg_trouble = 0
    
    if normal_moves:
        normal_times = [m['time_spent'] for m in normal_moves if m['time_spent'] is not None]
        avg_normal = sum(normal_times) / len(normal_times) if normal_times else 0
    
    if time_trouble_moves:
        trouble_times = [m['time_spent'] for m in time_trouble_moves if m['time_spent'] is not None]
        avg_trouble = sum(trouble_times) / len(trouble_times) if trouble_times else 0
    
    return {
        'threshold_seconds': threshold,
        'time_trouble_moves_count': len(time_trouble_moves),
        'normal_moves_count': len(normal_moves),
        'avg_time_normal': round(avg_normal, 1),
        'avg_time_trouble': round(avg_trouble, 1),
        'time_trouble_moves': time_trouble_moves,
        'entered_time_trouble': len(time_trouble_moves) > 0,
        'pct_in_time_trouble': round(len(time_trouble_moves) / (len(time_trouble_moves) + len(normal_moves)) * 100, 1) if (len(time_trouble_moves) + len(normal_moves)) > 0 else 0,
    }


def analyze_long_thinks(
    time_per_move: List[Dict[str, Any]],
    time_control: str
) -> Dict[str, Any]:
    """
    Identify moves where player spent significantly more time than average.
    
    A "long think" is defined as spending > 2x the average time on a move.
    
    Returns:
        Dict with long think analysis
    """
    # Filter moves with valid time data
    valid_moves = [m for m in time_per_move if m.get('time_spent') is not None and m['time_spent'] > 0]
    
    if not valid_moves:
        return {
            'avg_time_per_move': 0,
            'long_think_threshold': 0,
            'long_thinks_count': 0,
            'long_thinks': [],
        }
    
    times = [m['time_spent'] for m in valid_moves]
    avg_time = sum(times) / len(times)
    long_think_threshold = avg_time * 2
    
    long_thinks = [m for m in valid_moves if m['time_spent'] >= long_think_threshold]
    
    return {
        'avg_time_per_move': round(avg_time, 1),
        'long_think_threshold': round(long_think_threshold, 1),
        'long_thinks_count': len(long_thinks),
        'long_thinks': sorted(long_thinks, key=lambda x: x['time_spent'], reverse=True)[:5],  # Top 5
    }


def analyze_fast_moves(
    time_per_move: List[Dict[str, Any]],
    time_control: str
) -> Dict[str, Any]:
    """
    Identify moves made very quickly (potential premoves or impulsive moves).
    
    A "fast move" is defined as < 2 seconds (or < 0.5x average, whichever is smaller).
    
    Returns:
        Dict with fast move analysis
    """
    valid_moves = [m for m in time_per_move if m.get('time_spent') is not None]
    
    if not valid_moves:
        return {
            'fast_move_threshold': 2,
            'fast_moves_count': 0,
            'fast_moves': [],
            'fast_moves_by_phase': {'opening': 0, 'middlegame': 0, 'endgame': 0},
        }
    
    times = [m['time_spent'] for m in valid_moves if m['time_spent'] > 0]
    avg_time = sum(times) / len(times) if times else 0
    
    # Fast move threshold: min of 2 seconds or half the average
    fast_threshold = min(2, avg_time * 0.5) if avg_time > 0 else 2
    
    fast_moves = [m for m in valid_moves if m['time_spent'] is not None and m['time_spent'] <= fast_threshold]
    
    # Count by phase
    by_phase = {'opening': 0, 'middlegame': 0, 'endgame': 0}
    for m in fast_moves:
        move_num = m['move_number']
        if move_num <= 15:
            by_phase['opening'] += 1
        elif move_num <= 40:
            by_phase['middlegame'] += 1
        else:
            by_phase['endgame'] += 1
    
    return {
        'fast_move_threshold': round(fast_threshold, 1),
        'fast_moves_count': len(fast_moves),
        'fast_moves': fast_moves[:10],  # First 10
        'fast_moves_by_phase': by_phase,
    }


def compute_time_management_score(
    phase_analysis: Dict[str, Any],
    time_trouble: Dict[str, Any],
    long_thinks: Dict[str, Any],
    fast_moves: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compute an overall time management score (0-100).
    
    Factors:
    - Not entering time trouble (positive)
    - Consistent time per move across phases (positive)
    - Too many long thinks (negative if excessive)
    - Too many fast moves in critical phases (negative)
    
    Returns:
        Dict with score and breakdown
    """
    score = 100
    breakdown = []
    
    # Time trouble penalty
    if time_trouble.get('entered_time_trouble', False):
        pct_trouble = time_trouble.get('pct_in_time_trouble', 0)
        penalty = min(30, pct_trouble * 0.5)  # Up to -30 for time trouble
        score -= penalty
        breakdown.append(f"-{penalty:.0f}: Time trouble ({pct_trouble:.0f}% of moves)")
    else:
        breakdown.append("+0: No time trouble")
    
    # Phase consistency check
    opening_avg = phase_analysis.get('opening', {}).get('avg_time_per_move', 0)
    middle_avg = phase_analysis.get('middlegame', {}).get('avg_time_per_move', 0)
    endgame_avg = phase_analysis.get('endgame', {}).get('avg_time_per_move', 0)
    
    if opening_avg > 0 and middle_avg > 0:
        # Opening should be faster than middlegame (preparation advantage)
        if opening_avg > middle_avg * 1.5:
            penalty = 10
            score -= penalty
            breakdown.append(f"-{penalty}: Slow opening (avg {opening_avg:.1f}s vs {middle_avg:.1f}s middlegame)")
    
    # Long think penalty (if too concentrated)
    long_think_count = long_thinks.get('long_thinks_count', 0)
    if long_think_count > 5:
        penalty = min(15, (long_think_count - 5) * 2)
        score -= penalty
        breakdown.append(f"-{penalty}: Many long thinks ({long_think_count} moves)")
    
    # Fast moves in middlegame penalty
    fast_middlegame = fast_moves.get('fast_moves_by_phase', {}).get('middlegame', 0)
    if fast_middlegame > 5:
        penalty = min(15, (fast_middlegame - 5) * 2)
        score -= penalty
        breakdown.append(f"-{penalty}: Fast middlegame moves ({fast_middlegame} moves)")
    
    score = max(0, min(100, score))
    
    return {
        'score': round(score),
        'breakdown': breakdown,
        'grade': 'A' if score >= 90 else 'B' if score >= 75 else 'C' if score >= 60 else 'D' if score >= 40 else 'F',
    }


def aggregate_time_analysis(games: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate time analysis across multiple games.
    
    Returns comprehensive time statistics and patterns.
    """
    games_with_clocks = get_games_with_clock_data(games)
    
    if not games_with_clocks:
        return {
            'has_data': False,
            'message': 'No clock data available for these games.',
        }
    
    # Aggregate stats
    all_phase_times = {'opening': [], 'middlegame': [], 'endgame': []}
    time_trouble_count = 0
    total_games = len(games_with_clocks)
    all_time_scores = []
    
    per_game_analysis = []
    
    for game in games_with_clocks:
        player_color = game.get('color', 'white')
        move_clocks = game.get('move_clocks', [])
        time_control = game.get('time_control', '600+0')
        total_moves = game.get('moves', 40)
        
        # Compute per-move time
        time_per_move = compute_time_per_move(move_clocks, player_color)
        
        if not time_per_move:
            continue
        
        # Phase analysis
        phase_analysis = analyze_time_by_phase(time_per_move, total_moves)
        for phase, data in phase_analysis.items():
            if data['avg_time_per_move'] > 0:
                all_phase_times[phase].append(data['avg_time_per_move'])
        
        # Time trouble
        time_trouble = detect_time_trouble_moves(time_per_move, time_control)
        if time_trouble['entered_time_trouble']:
            time_trouble_count += 1
        
        # Long thinks and fast moves
        long_thinks = analyze_long_thinks(time_per_move, time_control)
        fast_moves = analyze_fast_moves(time_per_move, time_control)
        
        # Time management score
        tm_score = compute_time_management_score(phase_analysis, time_trouble, long_thinks, fast_moves)
        all_time_scores.append(tm_score['score'])
        
        per_game_analysis.append({
            'date': game.get('date', ''),
            'result': game.get('score', ''),
            'time_control': time_control,
            'phase_analysis': phase_analysis,
            'time_trouble': time_trouble,
            'long_thinks': long_thinks,
            'fast_moves': fast_moves,
            'time_score': tm_score,
        })
    
    # Compute averages
    avg_phase_times = {}
    for phase, times in all_phase_times.items():
        if times:
            avg_phase_times[phase] = round(sum(times) / len(times), 1)
        else:
            avg_phase_times[phase] = 0
    
    avg_time_score = round(sum(all_time_scores) / len(all_time_scores)) if all_time_scores else 0
    
    # Identify patterns
    patterns = identify_time_patterns(per_game_analysis)
    
    return {
        'has_data': True,
        'games_analyzed': total_games,
        'avg_phase_times': avg_phase_times,
        'time_trouble_games': time_trouble_count,
        'time_trouble_rate': round(time_trouble_count / total_games * 100, 1) if total_games > 0 else 0,
        'avg_time_management_score': avg_time_score,
        'per_game_analysis': per_game_analysis,
        'patterns': patterns,
    }


def identify_time_patterns(per_game_analysis: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Identify recurring time management patterns across games.
    
    Patterns:
    - Consistent time trouble in same phase
    - Long thinks leading to losses
    - Fast moves in critical positions
    - Opening preparation time (fast opening = good prep)
    """
    patterns = []
    
    if not per_game_analysis:
        return patterns
    
    # Pattern 1: Time trouble frequency
    tt_games = [g for g in per_game_analysis if g['time_trouble']['entered_time_trouble']]
    if len(tt_games) >= 2:
        tt_rate = len(tt_games) / len(per_game_analysis) * 100
        if tt_rate >= 50:
            patterns.append({
                'type': 'time_trouble_frequent',
                'severity': 'high' if tt_rate >= 70 else 'medium',
                'description': f"You enter time trouble in {tt_rate:.0f}% of games",
                'recommendation': "Focus on developing faster decision-making. Consider setting move time limits.",
                'stat': f"{len(tt_games)}/{len(per_game_analysis)} games",
            })
    
    # Pattern 2: Slow opening play
    slow_opening_games = []
    for g in per_game_analysis:
        opening_avg = g['phase_analysis'].get('opening', {}).get('avg_time_per_move', 0)
        middle_avg = g['phase_analysis'].get('middlegame', {}).get('avg_time_per_move', 0)
        if opening_avg > 0 and middle_avg > 0 and opening_avg > middle_avg * 1.3:
            slow_opening_games.append(g)
    
    if len(slow_opening_games) >= 2 and len(slow_opening_games) / len(per_game_analysis) >= 0.4:
        patterns.append({
            'type': 'slow_opening',
            'severity': 'medium',
            'description': "You spend more time in the opening than middlegame",
            'recommendation': "Study opening theory to build automatic responses in the first 10-15 moves.",
            'stat': f"{len(slow_opening_games)}/{len(per_game_analysis)} games",
        })
    
    # Pattern 3: Many long thinks
    high_long_think_games = [g for g in per_game_analysis if g['long_thinks']['long_thinks_count'] >= 4]
    if len(high_long_think_games) >= 2:
        patterns.append({
            'type': 'excessive_long_thinks',
            'severity': 'medium',
            'description': "You frequently have deep calculation sessions (4+ long thinks per game)",
            'recommendation': "Practice 'candidate moves' technique - quickly identify 2-3 options before calculating.",
            'stat': f"{len(high_long_think_games)}/{len(per_game_analysis)} games",
        })
    
    # Pattern 4: Fast middlegame moves
    # Only flag if they're making MORE fast moves in middlegame than opening
    # (which would indicate true impulsiveness in complex positions)
    fast_mg_games = []
    for g in per_game_analysis:
        mg_fast = g['fast_moves']['fast_moves_by_phase'].get('middlegame', 0)
        opening_fast = g['fast_moves']['fast_moves_by_phase'].get('opening', 0)
        # Flag if 5+ fast moves in middlegame AND more than in opening
        if mg_fast >= 5 and mg_fast > opening_fast:
            fast_mg_games.append(g)
    
    if len(fast_mg_games) >= 2:
        patterns.append({
            'type': 'impulsive_middlegame',
            'severity': 'high',
            'description': "You make many quick moves in the middlegame (5+ per game)",
            'recommendation': "Force yourself to consider at least one alternative before moving in complex positions.",
            'stat': f"{len(fast_mg_games)}/{len(per_game_analysis)} games",
        })
    
    # Pattern 5: Good time management
    good_tm_games = [g for g in per_game_analysis if g['time_score']['score'] >= 80]
    if len(good_tm_games) >= len(per_game_analysis) * 0.7:
        patterns.append({
            'type': 'good_time_management',
            'severity': 'positive',
            'description': "Your time management is generally good",
            'recommendation': "Keep maintaining consistent time allocation across phases.",
            'stat': f"{len(good_tm_games)}/{len(per_game_analysis)} games with score ≥80",
        })
    
    return patterns
