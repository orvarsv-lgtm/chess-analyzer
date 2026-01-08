"""
AI Coach - GPT-4 Powered Chess Coaching Insights

Premium feature that provides natural language coaching using OpenAI's GPT-4.
Analyzes games, positions, and patterns to give personalized improvement advice.

Revenue Model:
- Free tier: 0 AI reviews/month
- Hobbyist ($9.99/mo): 2 AI reviews/month
- Serious ($19.99/mo): 5 AI reviews/month
- Coach ($49.99/mo): Unlimited AI reviews

Cost: ~$0.03-$0.05 per game review (GPT-4 Turbo API)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any

import streamlit as st

# Load environment variables at module import time
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load .env file immediately
except ImportError:
    pass  # python-dotenv not installed, use system env vars only


def _get_api_key():
    """Get OpenAI API key from various sources."""
    # 1. Try environment variable (works locally with .env)
    api_key = os.getenv('OPENAI_API_KEY')
    
    # 2. Try Streamlit secrets (works on Streamlit Cloud)
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get('OPENAI_API_KEY')
        except Exception:
            pass
    
    return api_key


# API client will be initialized lazily
_openai_client = None


def _get_openai_client():
    """Lazy initialization of OpenAI client."""
    global _openai_client
    if _openai_client is None:
        try:
            from openai import OpenAI
            
            # Get API key from environment or Streamlit secrets
            api_key = _get_api_key()
            
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment or Streamlit secrets")
            
            _openai_client = OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")
    return _openai_client


@dataclass
class AICoachResponse:
    """Response from AI coach analysis."""
    game_summary: str  # Overall game summary (2-3 sentences)
    key_moments: List[Dict[str, Any]]  # Critical positions with advice
    opening_advice: str  # Opening-specific feedback
    strategic_advice: str  # Strategic patterns and plans
    tactical_advice: str  # Tactical awareness feedback
    training_recommendations: List[str]  # Specific things to practice
    timestamp: datetime
    cost_cents: int  # API cost in cents
    tokens_used: int  # Total tokens consumed


def generate_game_review(
    game_data: Dict[str, Any],
    player_color: str,
    player_rating: Optional[int] = None,
) -> AICoachResponse:
    """
    Generate comprehensive AI coaching review for a single game.
    
    Args:
        game_data: Analyzed game data with moves, evals, phases
        player_color: 'white' or 'black'
        player_rating: Player's current rating (for context)
    
    Returns:
        AICoachResponse with personalized insights
    """
    client = _get_openai_client()
    
    # Build context prompt from game data
    prompt = _build_game_review_prompt(game_data, player_color, player_rating)
    
    # Call GPT-4 Turbo
    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",  # or "gpt-4o" for faster/cheaper
        messages=[
            {
                "role": "system",
                "content": _get_coach_system_prompt()
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7,  # Slightly creative but not random
        max_tokens=2000,  # Comprehensive review
    )
    
    # Parse response
    content = response.choices[0].message.content
    tokens_used = response.usage.total_tokens
    
    # Estimate cost (GPT-4 Turbo: $0.01/1K input, $0.03/1K output)
    cost_cents = int((tokens_used / 1000) * 2)  # Rough estimate
    
    # Parse structured response
    parsed = _parse_coach_response(content)
    
    return AICoachResponse(
        game_summary=parsed['summary'],
        key_moments=parsed['key_moments'],
        opening_advice=parsed['opening'],
        strategic_advice=parsed['strategy'],
        tactical_advice=parsed['tactics'],
        training_recommendations=parsed['training'],
        timestamp=datetime.now(),
        cost_cents=cost_cents,
        tokens_used=tokens_used,
    )


def generate_position_insight(
    fen: str,
    eval_before: int,
    eval_after: int,
    best_move_san: str,
    played_move_san: str,
    phase: str,
) -> str:
    """
    Generate quick insight for a specific position (for puzzle explanations).
    
    Args:
        fen: Position FEN
        eval_before: Eval before move (centipawns)
        eval_after: Eval after move
        best_move_san: Best move
        played_move_san: Move that was played
        phase: Game phase
    
    Returns:
        Short natural language explanation (2-3 sentences)
    """
    client = _get_openai_client()
    
    prompt = f"""You are a chess coach explaining why a move is wrong and what the player should have done.

Position (FEN): {fen}
Phase: {phase}
Eval before: {eval_before:+}cp
Player played: {played_move_san} (eval after: {eval_after:+}cp)
Best move: {best_move_san}

Explain in 2-3 sentences:
1. Why the played move is wrong
2. What the best move accomplishes
3. Key lesson to learn

Be specific and instructive. Focus on plans/ideas, not just "you lost material"."""
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",  # Cheaper for short responses
        messages=[
            {"role": "system", "content": "You are an expert chess coach."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
        max_tokens=150,
    )
    
    return response.choices[0].message.content.strip()


def generate_training_plan(
    performance_summary: Dict[str, Any],
    player_rating: Optional[int] = None,
    time_commitment: str = "30min/day",
) -> Dict[str, List[str]]:
    """
    Generate personalized weekly training plan based on weaknesses.
    
    Args:
        performance_summary: CPL by phase, blunder rates, opening stats, etc.
        player_rating: Player's rating
        time_commitment: How much time they can dedicate
    
    Returns:
        Dict with daily training tasks
    """
    client = _get_openai_client()
    
    prompt = f"""You are a chess coach creating a personalized training plan.

Player Rating: {player_rating or 'Unknown'}
Time Available: {time_commitment} per day

Performance Data:
{_format_performance_for_prompt(performance_summary)}

Create a 7-day training plan that addresses their weaknesses. For each day, suggest:
- Study topic (opening, tactics, endgames, etc.)
- Specific exercises (puzzle themes, opening lines to review, etc.)
- Approximate time split

Return as JSON:
{{
    "monday": ["Task 1", "Task 2"],
    "tuesday": [...],
    ...
}}"""
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a chess training expert."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.6,
        max_tokens=1000,
        response_format={"type": "json_object"}
    )
    
    import json
    return json.loads(response.choices[0].message.content)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _get_coach_system_prompt() -> str:
    """System prompt for AI coach persona."""
    return """You are an expert chess coach with decades of experience. Your job is to analyze games and provide actionable, personalized feedback.

When reviewing a game:
1. Identify 3-5 critical moments (key decisions, missed tactics, strategic errors)
2. Give specific advice for each phase (opening, middlegame, endgame)
3. Focus on patterns and plans, not just moves
4. Recommend specific training exercises
5. Be encouraging but honest about mistakes

Your tone is professional, supportive, and focused on improvement.
Avoid generic advice like "study more tactics" - be specific."""


def _build_game_review_prompt(
    game_data: Dict[str, Any],
    player_color: str,
    player_rating: Optional[int],
) -> str:
    """Build detailed prompt for game review."""
    
    moves_table = game_data.get('moves_table', [])
    opening_name = game_data.get('opening_name', 'Unknown')
    result = game_data.get('result', 'Unknown')
    
    # Find biggest mistakes (blunders)
    blunders = []
    for move in moves_table:
        if move.get('color') == player_color and move.get('cp_loss', 0) >= 200:
            blunders.append({
                'move_num': move.get('move_num'),
                'san': move.get('san'),
                'cp_loss': move.get('cp_loss'),
                'phase': move.get('phase'),
                'best_move': move.get('best_move_san'),
            })
    
    # Calculate phase performance
    phase_cpl = {}
    for phase in ['opening', 'middlegame', 'endgame']:
        phase_moves = [m for m in moves_table if m.get('phase') == phase and m.get('color') == player_color]
        if phase_moves:
            avg_cpl = sum(m.get('cp_loss', 0) for m in phase_moves) / len(phase_moves)
            phase_cpl[phase] = round(avg_cpl, 1)
    
    prompt = f"""Analyze this chess game and provide coaching feedback.

**Game Info:**
- Opening: {opening_name}
- Player Color: {player_color.title()}
- Player Rating: {player_rating or 'Unknown'}
- Result: {result}

**Performance Summary:**
- Opening CPL: {phase_cpl.get('opening', 'N/A')}
- Middlegame CPL: {phase_cpl.get('middlegame', 'N/A')}
- Endgame CPL: {phase_cpl.get('endgame', 'N/A')}

**Major Blunders (≥200cp loss):**
{_format_blunders(blunders)}

**Instructions:**
Provide a structured review with these sections:

1. **Game Summary** (2-3 sentences): Overall assessment of the game
2. **Key Moments** (3-5 critical positions): For each, explain what happened and what should have been done
3. **Opening Advice**: Specific feedback on the opening played
4. **Strategic Advice**: Plans, piece placement, pawn structure insights
5. **Tactical Advice**: Pattern recognition, calculation accuracy
6. **Training Recommendations**: 3-5 specific things to practice

Be specific, use chess terminology, and focus on improvement."""
    
    return prompt


def _format_blunders(blunders: List[Dict]) -> str:
    """Format blunders for prompt."""
    if not blunders:
        return "None (good job!)"
    
    lines = []
    for b in blunders[:5]:  # Top 5 worst
        lines.append(
            f"- Move {b['move_num']} ({b['phase']}): Played {b['san']} "
            f"(-{b['cp_loss']}cp). Best was {b.get('best_move', '?')}"
        )
    return "\n".join(lines)


def _format_performance_for_prompt(perf: Dict[str, Any]) -> str:
    """Format performance data for training plan prompt."""
    lines = []
    
    if 'opening_cpl' in perf:
        lines.append(f"Opening CPL: {perf['opening_cpl']}")
    if 'middlegame_cpl' in perf:
        lines.append(f"Middlegame CPL: {perf['middlegame_cpl']}")
    if 'endgame_cpl' in perf:
        lines.append(f"Endgame CPL: {perf['endgame_cpl']}")
    
    if 'blunder_rate' in perf:
        lines.append(f"Blunder rate: {perf['blunder_rate']} per 100 moves")
    
    if 'weak_openings' in perf:
        lines.append(f"Weak openings: {', '.join(perf['weak_openings'][:3])}")
    
    return "\n".join(lines)


def _parse_coach_response(content: str) -> Dict[str, Any]:
    """Parse GPT-4 response into structured format."""
    
    parsed = {
        'summary': '',
        'key_moments': [],
        'opening': '',
        'strategy': '',
        'tactics': '',
        'training': [],
    }
    
    # More robust line-by-line parsing
    lines = content.split('\n')
    current_section = None
    current_content = []
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
            
        lower = line_stripped.lower()
        
        # Detect section headers (with or without markdown formatting)
        if any(h in lower for h in ['game summary', 'summary:', '**summary', '1.', 'overall']):
            if current_section and current_content:
                _store_section(parsed, current_section, current_content)
            current_section = 'summary'
            current_content = []
            # If header has content after colon, add it
            if ':' in line_stripped:
                after_colon = line_stripped.split(':', 1)[1].strip()
                if after_colon:
                    current_content.append(after_colon)
        elif any(h in lower for h in ['key moment', 'critical moment', '2.', 'critical position']):
            if current_section and current_content:
                _store_section(parsed, current_section, current_content)
            current_section = 'key_moments'
            current_content = []
        elif any(h in lower for h in ['opening advice', 'opening:', '3.', '**opening']):
            if current_section and current_content:
                _store_section(parsed, current_section, current_content)
            current_section = 'opening'
            current_content = []
        elif any(h in lower for h in ['strategic', 'strategy', '4.', '**strategic']):
            if current_section and current_content:
                _store_section(parsed, current_section, current_content)
            current_section = 'strategy'
            current_content = []
        elif any(h in lower for h in ['tactical', 'tactics', '5.', '**tactical']):
            if current_section and current_content:
                _store_section(parsed, current_section, current_content)
            current_section = 'tactics'
            current_content = []
        elif any(h in lower for h in ['training', 'recommendation', '6.', '**training', 'practice']):
            if current_section and current_content:
                _store_section(parsed, current_section, current_content)
            current_section = 'training'
            current_content = []
        else:
            # Regular content line
            if current_section:
                current_content.append(line_stripped)
    
    # Store the last section
    if current_section and current_content:
        _store_section(parsed, current_section, current_content)
    
    # Fallback if parsing fails - use the whole content
    if not parsed['summary'] and content:
        parsed['summary'] = content[:500] + '...' if len(content) > 500 else content
    
    # Ensure training has items
    if not parsed['training']:
        parsed['training'] = [
            "Review your biggest blunders from this game",
            "Practice similar tactical patterns on Lichess puzzles",
            "Study the opening variation you played"
        ]
    
    # Ensure tactics has content
    if not parsed['tactics']:
        parsed['tactics'] = "Focus on calculation and pattern recognition. Review tactical motifs like pins, forks, and discovered attacks."
    
    return parsed


def _store_section(parsed: Dict, section: str, content: List[str]) -> None:
    """Store parsed content into the appropriate section."""
    text = '\n'.join(content).strip()
    
    if section == 'summary':
        parsed['summary'] = text
    elif section == 'opening':
        parsed['opening'] = text
    elif section == 'strategy':
        parsed['strategy'] = text
    elif section == 'tactics':
        parsed['tactics'] = text
    elif section == 'key_moments':
        # Parse key moments as list
        for line in content:
            if line.strip():
                parsed['key_moments'].append({'move': '?', 'advice': line.strip()})
    elif section == 'training':
        # Extract bullet points
        for line in content:
            clean = line.strip().lstrip('-•*0123456789.) ')
            if clean and len(clean) > 5:
                parsed['training'].append(clean)


# =============================================================================
# CAREER/MULTI-GAME ANALYSIS
# =============================================================================


def generate_career_analysis(
    all_games: List[Dict[str, Any]],
    player_name: str,
    player_rating: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate comprehensive AI analysis of player's entire game history.
    
    This analyzes patterns, trends, and gives career-level coaching advice.
    
    Args:
        all_games: List of all analyzed games
        player_name: Player's username
        player_rating: Current rating (if known)
    
    Returns:
        Dict with career analysis sections
    """
    client = _get_openai_client()
    
    # Aggregate statistics across all games
    stats = _aggregate_career_stats(all_games)
    
    # Format additional context
    worst_games_str = _format_worst_games(stats.get('worst_games', []))
    best_games_str = _format_best_games(stats.get('best_games', []))
    blunder_phase_str = _format_blunder_phases(stats.get('blunder_phases', {}), stats.get('total_blunders', 0))
    
    white_stats = stats.get('white_stats', {})
    black_stats = stats.get('black_stats', {})
    
    prompt = f"""You are an expert chess coach analyzing a player's complete game history. Give SPECIFIC, ACTIONABLE advice based on their actual data.

**Player**: {player_name}
**Rating**: {player_rating or 'Unknown'}
**Rating Range in Dataset**: {stats.get('rating_range', (0,0))[0]} - {stats.get('rating_range', (0,0))[1]}
**Games Analyzed**: {stats['total_games']} (W: {stats.get('wins', 0)}, L: {stats.get('losses', 0)}, D: {stats.get('draws', 0)})

**Performance by Color**:
- As White: {white_stats.get('games', 0)} games, {white_stats.get('win_rate', 0):.0%} win rate, avg CPL: {white_stats.get('avg_cpl', 0):.0f}
- As Black: {black_stats.get('games', 0)} games, {black_stats.get('win_rate', 0):.0%} win rate, avg CPL: {black_stats.get('avg_cpl', 0):.0f}

**Phase Performance (Average CPL - lower is better)**:
- Opening (moves 1-15): {stats['opening_cpl']:.0f} CPL
- Middlegame (moves 16-40): {stats['middlegame_cpl']:.0f} CPL  
- Endgame (moves 41+): {stats['endgame_cpl']:.0f} CPL
- Best Phase: {stats['best_phase']} | Worst Phase: {stats['worst_phase']}

**Error Analysis**:
- Blunders (≥300 CPL): {stats.get('total_blunders', 0)} total ({stats['blunder_rate']:.1f} per 100 moves)
- Mistakes (100-299 CPL): {stats.get('total_mistakes', 0)} total ({stats['mistake_rate']:.1f} per 100 moves)
{blunder_phase_str}

**Opening Repertoire**:
{_format_opening_stats(stats['openings'])}

**Best Performed Games** (lowest average CPL):
{best_games_str}

**Worst Performed Games** (highest average CPL - focus areas):
{worst_games_str}

**Recent Trend**: {stats['trend_summary']}

---

**Provide a SPECIFIC career analysis with these sections**:

1. **Career Overview** (3-4 sentences): Assessment based on their actual stats. Mention their rating, win rate by color difference if significant, and phase strengths.

2. **Biggest Strengths** (3 items): Be specific! Reference their actual openings, win rates, and best games. Example: "Your Scotch Game shows mastery with 75% win rate and only 73 CPL"

3. **Critical Weaknesses** (3 items): Reference specific numbers. Example: "Endgame CPL of 171 vs Opening CPL of 46 shows a 3.7x decline - this is where games are being lost"

4. **Opening Repertoire Analysis**: 
   - Recommend specific openings based on their data
   - Identify which openings have high blunder counts
   - If they play better as White or Black, suggest appropriate repertoire

5. **Phase-by-Phase Breakdown**:
   - Opening: What's working? What needs attention?
   - Middlegame: Specific tactical/strategic issues based on their CPL jump
   - Endgame: Concrete endgame types to study based on their weaknesses

6. **Personalized Training Plan** (weekly schedule):
   - Be specific: "Tuesday: Practice rook endgames (your endgame CPL is 171)"
   - Reference their openings: "Study games in the Vienna Game (your 50% win rate suggests you're not fully understanding the plans)"

7. **Rating Improvement Estimate**: 
   - Current estimated strength based on CPL
   - Realistic 3-month and 6-month targets
   - Specific milestones: "Reduce blunder rate from 8.5 to 5.0 per 100 moves"

Be brutally honest but encouraging. Use their actual numbers throughout."""

    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[
            {"role": "system", "content": "You are an expert chess coach with decades of experience helping players improve."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=3000,
    )
    
    content = response.choices[0].message.content
    tokens_used = response.usage.total_tokens
    cost_cents = int((tokens_used / 1000) * 3)
    
    return {
        'analysis': content,
        'stats': stats,
        'tokens_used': tokens_used,
        'cost_cents': cost_cents,
        'timestamp': datetime.now(),
    }


def _aggregate_career_stats(games: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate statistics across all games."""
    
    if not games:
        return {
            'total_games': 0,
            'win_rate': 0,
            'opening_cpl': 0,
            'middlegame_cpl': 0,
            'endgame_cpl': 0,
            'blunder_rate': 0,
            'mistake_rate': 0,
            'openings': {},
            'best_phase': 'unknown',
            'worst_phase': 'unknown',
            'trend_summary': 'Not enough games for trend analysis',
            'white_stats': {},
            'black_stats': {},
            'worst_games': [],
            'best_games': [],
            'blunder_phases': {},
            'rating_range': (0, 0),
        }
    
    total_games = len(games)
    wins = 0
    losses = 0
    draws = 0
    
    # Track by color
    white_games = {'games': 0, 'wins': 0, 'cpl_sum': 0, 'moves': 0}
    black_games = {'games': 0, 'wins': 0, 'cpl_sum': 0, 'moves': 0}
    
    # Collect CPL by phase
    opening_cpls = []
    middlegame_cpls = []
    endgame_cpls = []
    blunders = 0
    mistakes = 0
    total_moves = 0
    openings = {}
    
    # Track blunders by phase
    blunder_phases = {'opening': 0, 'middlegame': 0, 'endgame': 0}
    
    # Track game quality for best/worst
    game_quality = []
    
    # Track ratings
    ratings = []
    
    for game in games:
        moves_table = game.get('moves_table', [])
        focus_color = game.get('focus_color', 'white')
        opening = game.get('opening') or game.get('opening_name') or 'Unknown'
        result = game.get('result', '*')
        
        # Get rating
        rating = game.get('focus_player_rating') or game.get('white_rating' if focus_color == 'white' else 'black_rating')
        if rating and rating > 0:
            ratings.append(rating)
        
        # Track wins/losses/draws
        is_win = (focus_color == 'white' and result == '1-0') or (focus_color == 'black' and result == '0-1')
        is_loss = (focus_color == 'white' and result == '0-1') or (focus_color == 'black' and result == '1-0')
        
        if is_win:
            wins += 1
        elif is_loss:
            losses += 1
        elif result == '1/2-1/2':
            draws += 1
        
        # Track by color
        if focus_color == 'white':
            white_games['games'] += 1
            if is_win:
                white_games['wins'] += 1
        else:
            black_games['games'] += 1
            if is_win:
                black_games['wins'] += 1
        
        # Track opening stats
        if opening not in openings:
            openings[opening] = {'games': 0, 'wins': 0, 'losses': 0, 'total_cpl': 0, 'total_moves': 0, 'blunders': 0}
        openings[opening]['games'] += 1
        if is_win:
            openings[opening]['wins'] += 1
        if is_loss:
            openings[opening]['losses'] += 1
        
        game_cpl_sum = 0
        game_moves = 0
        game_blunders = 0
        
        for move in moves_table:
            move_color = move.get('mover') or move.get('color')
            if move_color != focus_color:
                continue
            
            total_moves += 1
            game_moves += 1
            cp_loss = move.get('cp_loss', 0) or 0
            if cp_loss == 0:
                cp_loss = move.get('actual_cp_loss', 0) or 0
            phase = move.get('phase', 'middlegame')
            
            game_cpl_sum += cp_loss
            
            if phase == 'opening':
                opening_cpls.append(cp_loss)
            elif phase == 'middlegame':
                middlegame_cpls.append(cp_loss)
            else:
                endgame_cpls.append(cp_loss)
            
            if cp_loss >= 300:
                blunders += 1
                game_blunders += 1
                blunder_phases[phase] = blunder_phases.get(phase, 0) + 1
                openings[opening]['blunders'] += 1
            elif cp_loss >= 100:
                mistakes += 1
            
            openings[opening]['total_cpl'] += cp_loss
            openings[opening]['total_moves'] += 1
            
            # Track by color
            if focus_color == 'white':
                white_games['cpl_sum'] += cp_loss
                white_games['moves'] += 1
            else:
                black_games['cpl_sum'] += cp_loss
                black_games['moves'] += 1
        
        # Track game quality
        avg_cpl = game_cpl_sum / game_moves if game_moves > 0 else 0
        game_quality.append({
            'index': game.get('index', 0),
            'white': game.get('white', '?'),
            'black': game.get('black', '?'),
            'opening': opening,
            'result': result,
            'avg_cpl': avg_cpl,
            'blunders': game_blunders,
            'is_win': is_win,
            'date': game.get('date', ''),
        })
    
    # Calculate averages
    avg_opening = sum(opening_cpls) / len(opening_cpls) if opening_cpls else 0
    avg_middlegame = sum(middlegame_cpls) / len(middlegame_cpls) if middlegame_cpls else 0
    avg_endgame = sum(endgame_cpls) / len(endgame_cpls) if endgame_cpls else 0
    
    # Determine best/worst phase
    phases = {'opening': avg_opening, 'middlegame': avg_middlegame, 'endgame': avg_endgame}
    best_phase = min(phases, key=phases.get) if phases else 'unknown'
    worst_phase = max(phases, key=phases.get) if phases else 'unknown'
    
    # Calculate rates per 100 moves
    blunder_rate = (blunders / total_moves * 100) if total_moves > 0 else 0
    mistake_rate = (mistakes / total_moves * 100) if total_moves > 0 else 0
    
    # Find best and worst games
    sorted_by_cpl = sorted(game_quality, key=lambda x: x['avg_cpl'])
    best_games = sorted_by_cpl[:3]
    worst_games = sorted_by_cpl[-3:][::-1]
    
    # Rating range
    rating_range = (min(ratings), max(ratings)) if ratings else (0, 0)
    
    # Trend summary
    if total_games >= 10:
        first_half = games[:len(games)//2]
        second_half = games[len(games)//2:]
        
        # Count blunders using correct keys
        first_blunders = 0
        for g in first_half:
            focus_color = g.get('focus_color', 'white')
            for m in g.get('moves_table', []):
                move_color = m.get('mover') or m.get('color')
                if move_color == focus_color:
                    cp = m.get('cp_loss', 0) or m.get('actual_cp_loss', 0) or 0
                    if cp >= 300:
                        first_blunders += 1
        
        second_blunders = 0
        for g in second_half:
            focus_color = g.get('focus_color', 'white')
            for m in g.get('moves_table', []):
                move_color = m.get('mover') or m.get('color')
                if move_color == focus_color:
                    cp = m.get('cp_loss', 0) or m.get('actual_cp_loss', 0) or 0
                    if cp >= 300:
                        second_blunders += 1
        
        if second_blunders < first_blunders * 0.8:
            trend = "Improving! Blunder rate has decreased over recent games."
        elif second_blunders > first_blunders * 1.2:
            trend = "Blunder rate has increased recently. Time to slow down and focus."
        else:
            trend = "Performance is consistent across games."
    else:
        trend = "Not enough games for trend analysis."
    
    # Calculate color-specific stats
    white_win_rate = white_games['wins'] / white_games['games'] if white_games['games'] > 0 else 0
    black_win_rate = black_games['wins'] / black_games['games'] if black_games['games'] > 0 else 0
    white_avg_cpl = white_games['cpl_sum'] / white_games['moves'] if white_games['moves'] > 0 else 0
    black_avg_cpl = black_games['cpl_sum'] / black_games['moves'] if black_games['moves'] > 0 else 0
    
    return {
        'total_games': total_games,
        'wins': wins,
        'losses': losses,
        'draws': draws,
        'win_rate': wins / total_games if total_games > 0 else 0,
        'opening_cpl': avg_opening,
        'middlegame_cpl': avg_middlegame,
        'endgame_cpl': avg_endgame,
        'blunder_rate': blunder_rate,
        'mistake_rate': mistake_rate,
        'total_blunders': blunders,
        'total_mistakes': mistakes,
        'total_moves': total_moves,
        'openings': openings,
        'best_phase': best_phase,
        'worst_phase': worst_phase,
        'trend_summary': trend,
        # New detailed stats
        'white_stats': {
            'games': white_games['games'],
            'wins': white_games['wins'],
            'win_rate': white_win_rate,
            'avg_cpl': white_avg_cpl,
        },
        'black_stats': {
            'games': black_games['games'],
            'wins': black_games['wins'],
            'win_rate': black_win_rate,
            'avg_cpl': black_avg_cpl,
        },
        'blunder_phases': blunder_phases,
        'best_games': best_games,
        'worst_games': worst_games,
        'rating_range': rating_range,
    }


def _format_opening_stats(openings: Dict[str, Dict]) -> str:
    """Format opening statistics for the prompt."""
    if not openings:
        return "No opening data available"
    
    # Filter out 'Unknown' if there are other openings
    filtered = {k: v for k, v in openings.items() if k and k != 'Unknown'}
    if not filtered:
        filtered = openings  # Fall back to including Unknown
    
    # Sort by games played
    sorted_openings = sorted(filtered.items(), key=lambda x: x[1]['games'], reverse=True)[:7]
    
    lines = []
    for name, stats in sorted_openings:
        games = stats['games']
        wins = stats['wins']
        losses = stats.get('losses', 0)
        blunders = stats.get('blunders', 0)
        total_moves = stats.get('total_moves', games * 30)
        win_rate = wins / games if games > 0 else 0
        avg_cpl = stats['total_cpl'] / total_moves if total_moves > 0 else 0
        blunder_note = f" ⚠️{blunders} blunders" if blunders >= 3 else ""
        lines.append(f"- {name}: {games}g, {wins}W-{losses}L ({win_rate:.0%}), CPL:{avg_cpl:.0f}{blunder_note}")
    
    return '\n'.join(lines) if lines else "No opening data"


def _format_worst_games(worst_games: List[Dict]) -> str:
    """Format worst performed games for the prompt."""
    if not worst_games:
        return "No data"
    
    lines = []
    for g in worst_games[:3]:
        result_emoji = "❌" if not g.get('is_win') else "✅"
        lines.append(f"- Game {g.get('index', '?')}: {g.get('opening', 'Unknown')[:30]} - {result_emoji} {g.get('result', '?')} - CPL: {g.get('avg_cpl', 0):.0f}, {g.get('blunders', 0)} blunders")
    
    return '\n'.join(lines) if lines else "No data"


def _format_best_games(best_games: List[Dict]) -> str:
    """Format best performed games for the prompt."""
    if not best_games:
        return "No data"
    
    lines = []
    for g in best_games[:3]:
        result_emoji = "✅" if g.get('is_win') else "❌"
        lines.append(f"- Game {g.get('index', '?')}: {g.get('opening', 'Unknown')[:30]} - {result_emoji} {g.get('result', '?')} - CPL: {g.get('avg_cpl', 0):.0f}")
    
    return '\n'.join(lines) if lines else "No data"


def _format_blunder_phases(blunder_phases: Dict[str, int], total_blunders: int) -> str:
    """Format blunder distribution by phase."""
    if not blunder_phases or total_blunders == 0:
        return "- Blunder distribution: No data"
    
    parts = []
    for phase in ['opening', 'middlegame', 'endgame']:
        count = blunder_phases.get(phase, 0)
        pct = (count / total_blunders * 100) if total_blunders > 0 else 0
        parts.append(f"{phase.title()}: {count} ({pct:.0f}%)")
    
    return f"- Blunder distribution: {', '.join(parts)}"
    return parsed


# =============================================================================
# USAGE TRACKING (for premium limits)
# =============================================================================


def check_ai_coach_quota(user_tier: str, user_id: str) -> tuple[bool, int]:
    """
    Check if user has remaining AI coach quota.
    
    Args:
        user_tier: 'free', 'hobbyist', 'serious', 'coach'
        user_id: User identifier
    
    Returns:
        (has_quota, remaining_reviews)
    """
    # Monthly limits by tier
    limits = {
        'free': 0,       # No AI coach for free users
        'hobbyist': 2,   # 2 reviews/month
        'serious': 5,    # 5 reviews/month
        'coach': 999999  # Unlimited
    }
    
    limit = limits.get(user_tier, 0)
    
    if limit == 999999:
        return (True, 999999)
    
    # Count this month's usage
    # In real implementation, query database
    # For now, use session state
    usage_key = f'ai_reviews_{user_id}_202601'  # Month-specific key
    current_usage = st.session_state.get(usage_key, 0)
    
    remaining = limit - current_usage
    
    return (remaining > 0, max(0, remaining))


def increment_ai_coach_usage(user_id: str):
    """Increment AI coach usage counter."""
    usage_key = f'ai_reviews_{user_id}_202601'
    current = st.session_state.get(usage_key, 0)
    st.session_state[usage_key] = current + 1


# =============================================================================
# DEMO MODE (for testing without API key)
# =============================================================================


def generate_demo_review(game_data: Dict[str, Any]) -> AICoachResponse:
    """Generate fake review for demo purposes (no API call)."""
    return AICoachResponse(
        game_summary="This was a sharp Sicilian Defense game where you struggled in the middlegame. Your opening was solid but you missed a tactical shot on move 18 that cost you the game.",
        key_moments=[
            {
                'move': 18,
                'advice': 'After ...Nf6, you should have played Bxf6 to eliminate their strong knight. Instead, you played Qd2 which allowed ...Ng4 with a devastating attack.'
            },
            {
                'move': 23,
                'advice': 'In this endgame position, trading rooks with Rxd8 would have simplified to a drawable position. Your move Re1 allowed your opponent to activate their king.'
            }
        ],
        opening_advice="Your Sicilian Najdorf move order was correct. Consider studying the English Attack variation more deeply, as you seemed uncomfortable with White's setup.",
        strategic_advice="You need to work on recognizing when to trade pieces. In worse positions, simplification is often your best friend. Also, pay attention to pawn structure - the backward pawn on d6 was a long-term weakness.",
        tactical_advice="You missed several tactical opportunities. On move 15, there was a simple knight fork available with Nxe5. Practice tactics puzzles focusing on knight forks and pins.",
        training_recommendations=[
            "Study English Attack vs Najdorf (focus on plans after 6.Be3)",
            "Practice knight fork tactics (30 puzzles)",
            "Review endgame principle: when to trade pieces",
            "Analyze 3 GM games in this opening line"
        ],
        timestamp=datetime.now(),
        cost_cents=4,
        tokens_used=1234,
    )
