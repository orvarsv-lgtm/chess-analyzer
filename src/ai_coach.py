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
    Generate data-driven coaching review for a single game.
    
    NO generic advice. Every claim backed by move data.
    
    Args:
        game_data: Analyzed game data with moves, evals, phases
        player_color: 'white' or 'black'
        player_rating: Player's current rating (for context)
    
    Returns:
        AICoachResponse with personalized insights
    """
    from src.data_driven_coach import explain_single_game
    
    # Generate data-driven analysis
    analysis = explain_single_game(game_data, player_color, player_rating)
    
    # Extract key moments
    key_moments = []
    for km in analysis.get('key_moments', []):
        key_moments.append({
            'move': km.get('move'),
            'advice': km.get('explanation', ''),
        })
    
    # Build phase-specific advice from data
    phase_cpl = analysis.get('phase_cpl', {})
    opening_advice = ""
    strategic_advice = ""
    tactical_advice = ""
    
    # Opening advice based on actual data
    opening_cpl = phase_cpl.get('opening', 0)
    if opening_cpl > 50:
        opening_advice = (
            f"Opening CPL was {opening_cpl:.0f}, indicating early mistakes. "
            f"Review the first 15 moves for where you deviated."
        )
    elif opening_cpl < 20:
        opening_advice = f"Opening play was solid (CPL: {opening_cpl:.0f}). No major issues."
    else:
        opening_advice = f"Opening was acceptable (CPL: {opening_cpl:.0f})."
    
    # Strategic advice based on conversion
    if analysis.get('had_winning_position') and analysis.get('result') != '1-0' and player_color == 'white':
        strategic_advice = (
            "You had a winning position but failed to convert. "
            "When ahead, look for simplifying trades that preserve your advantage."
        )
    elif analysis.get('had_winning_position') and analysis.get('result') != '0-1' and player_color == 'black':
        strategic_advice = (
            "You had a winning position but failed to convert. "
            "When ahead, look for simplifying trades that preserve your advantage."
        )
    
    # Tactical advice based on blunders
    biggest_swing = analysis.get('biggest_swing', {})
    if biggest_swing.get('swing', 0) >= 200:
        tactical_advice = (
            f"The critical error was move {biggest_swing.get('move')} "
            f"({biggest_swing.get('san')}) which lost {biggest_swing.get('swing')}cp. "
            f"Best was {biggest_swing.get('best')}. Study this position."
        )
    elif analysis.get('blunders', 0) == 0:
        tactical_advice = "No major tactical errors. Good calculation this game."
    
    # Training recommendations tied to data
    training = []
    if opening_cpl > 50:
        training.append(f"Review opening: CPL was {opening_cpl:.0f}")
    if phase_cpl.get('endgame', 0) > 100:
        training.append(f"Endgame study: CPL was {phase_cpl.get('endgame', 0):.0f}")
    if biggest_swing.get('swing', 0) >= 200:
        training.append(f"Analyze move {biggest_swing.get('move')}: {biggest_swing.get('swing')}cp swing")
    if not training:
        training.append("Good game - review for patterns to repeat")
    
    return AICoachResponse(
        game_summary=analysis.get('summary', 'No analysis available.'),
        key_moments=key_moments,
        opening_advice=opening_advice,
        strategic_advice=strategic_advice or "No strategic issues identified from this game.",
        tactical_advice=tactical_advice or "Review blunders for tactical patterns.",
        training_recommendations=training,
        timestamp=datetime.now(),
        cost_cents=0,  # No API call
        tokens_used=0,
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
    # Aggregate statistics across all games
    stats = _aggregate_career_stats(all_games)
    
    # Use the data-driven coaching engine instead of GPT-4
    from src.data_driven_coach import generate_data_driven_analysis, format_analysis_for_display
    
    # Generate analysis from data (no LLM call)
    analysis_result = generate_data_driven_analysis(
        stats=stats,
        games=all_games,
        player_name=player_name,
        player_rating=player_rating,
    )
    
    # Format for display
    analysis_text = format_analysis_for_display(analysis_result)
    
    return {
        'analysis': analysis_text,
        'stats': stats,
        'tokens_used': 0,  # No API call
        'cost_cents': 0,   # Free!
        'timestamp': datetime.now(),
        'primary_issue': analysis_result.get('primary_issue', ''),
        'data_sources': analysis_result.get('data_sources', []),
    }


def generate_career_analysis_with_llm(
    all_games: List[Dict[str, Any]],
    player_name: str,
    player_rating: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate AI analysis using GPT-4 for natural language polish.
    
    This version uses the data-driven analysis as input to GPT-4,
    which just polishes the prose (not generates new content).
    
    Use this for premium users who want more natural-sounding output.
    """
    client = _get_openai_client()
    
    # First generate the data-driven analysis
    stats = _aggregate_career_stats(all_games)
    
    from src.data_driven_coach import generate_data_driven_analysis
    data_analysis = generate_data_driven_analysis(
        stats=stats,
        games=all_games,
        player_name=player_name,
        player_rating=player_rating,
    )
    
    # Now use GPT-4 to polish the prose (NOT generate new content)
    prompt = f"""You are a chess coach. Below is a DATA-DRIVEN analysis of a player's games.

Your job is to REWRITE this analysis in natural, conversational prose.

RULES:
1. DO NOT add any advice that isn't in the data analysis below
2. DO NOT mention Capablanca, Karpov, "chess is a marathon", or generic tips
3. DO NOT recommend external resources like Lichess puzzles
4. EVERY claim must come from the data below
5. Keep it SHORT - max 400 words total

---
DATA ANALYSIS:
{data_analysis['analysis']}

PRIMARY ISSUE: {data_analysis.get('primary_issue', 'Unknown')}

PLAYER: {player_name}
RATING: {player_rating or 'Unknown'}
GAMES: {stats.get('total_games', 0)}
WIN RATE: {stats.get('win_rate', 0):.0%}
CONVERSION: {stats.get('conversion_rate', 0):.0f}%
---

Rewrite the above analysis in a natural coaching voice. Start with the most important finding.
Do NOT add new information. Only rephrase what's there."""

    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[
            {"role": "system", "content": "You are a chess coach who only speaks from data. Never add generic advice."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
        max_tokens=800,
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
        'primary_issue': data_analysis.get('primary_issue', ''),
        'data_sources': data_analysis.get('data_sources', []),
    }


def _aggregate_career_stats(games: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate statistics across all games with advanced analytics."""
    
    # Phase CPL baselines (empirically derived from typical amateur play)
    # These represent "expected" CPL for each phase at amateur level
    PHASE_BASELINES = {
        'opening': 45,      # Fewer critical decisions, more theory
        'middlegame': 95,   # Complex, many candidate moves
        'endgame': 130,     # Fewer pieces but sharper - one mistake = huge CPL
    }
    
    if not games:
        return _empty_career_stats()
    
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
    
    # === NEW: Skill Attribution Tracking ===
    # Track WHERE blunders happen contextually
    blunder_contexts = {
        'after_capture': 0,      # Blunder within 2 moves of a capture
        'after_check': 0,        # Blunder within 2 moves of check
        'in_winning_position': 0,  # Blunder when eval was +150+
        'in_losing_position': 0,   # Blunder when already losing
        'in_equal_position': 0,    # Blunder in roughly equal position
        'time_trouble_likely': 0,  # Blunder after move 35 (proxy for time trouble)
    }
    
    # === NEW: Conversion Tracking ===
    conversion_stats = {
        'winning_positions': 0,     # Games where player had +150 at some point
        'converted_wins': 0,        # Actually won those games
        'losing_positions': 0,      # Games where player was -150 at some point  
        'saved_draws_or_wins': 0,   # Drew or won those "lost" games
    }
    
    # === NEW: Opening Outcome Tracking ===
    opening_outcomes = {
        'games_with_opening_eval': 0,
        'avg_eval_after_opening': 0,  # Eval at move 15
        'left_opening_better': 0,     # % of games leaving opening with advantage
        'left_opening_worse': 0,
        'transition_cpl_sum': 0,      # CPL for moves 10-20 (opening to middlegame)
        'transition_moves': 0,
    }
    
    # Track game quality for best/worst
    game_quality = []
    
    # Track ratings
    ratings = []
    
    # === NEW: Rating Cost Tracking ===
    # Estimate which errors cost the most rating points
    rating_cost_factors = {
        'blunders_in_winning_pos': {'count': 0, 'estimated_points_lost': 0},
        'endgame_collapses': {'count': 0, 'estimated_points_lost': 0},
        'opening_disasters': {'count': 0, 'estimated_points_lost': 0},
        'missed_wins': {'count': 0, 'estimated_points_lost': 0},
    }
    
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
        is_draw = result == '1/2-1/2'
        
        if is_win:
            wins += 1
        elif is_loss:
            losses += 1
        elif is_draw:
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
            openings[opening] = {
                'games': 0, 'wins': 0, 'losses': 0, 
                'total_cpl': 0, 'total_moves': 0, 'blunders': 0,
                'eval_after_opening_sum': 0, 'eval_after_opening_count': 0,
            }
        openings[opening]['games'] += 1
        if is_win:
            openings[opening]['wins'] += 1
        if is_loss:
            openings[opening]['losses'] += 1
        
        game_cpl_sum = 0
        game_moves = 0
        game_blunders = 0
        
        # Track position context through the game
        had_winning_position = False
        had_losing_position = False
        recent_capture = False
        recent_check = False
        last_few_moves_context = []  # Track recent move types
        
        prev_eval = 0
        opening_exit_eval = None
        
        for i, move in enumerate(moves_table):
            move_color = move.get('mover') or move.get('color')
            ply = move.get('ply', i + 1)
            move_num = (ply + 1) // 2
            
            # Track eval for conversion analysis
            eval_after = move.get('score_cp') or move.get('eval_after')
            if eval_after is not None:
                try:
                    eval_val = int(eval_after)
                    # Normalize to player's perspective
                    if focus_color == 'black':
                        eval_val = -eval_val
                    
                    if eval_val >= 150:
                        had_winning_position = True
                    if eval_val <= -150:
                        had_losing_position = True
                    
                    # Capture opening exit eval (around move 15)
                    if 13 <= move_num <= 17 and opening_exit_eval is None:
                        opening_exit_eval = eval_val
                    
                    prev_eval = eval_val
                except (TypeError, ValueError):
                    pass
            
            # Only analyze focus player's moves
            if move_color != focus_color:
                # Track opponent's captures/checks for context
                move_san = move.get('move_san', '')
                if 'x' in move_san:
                    recent_capture = True
                if '+' in move_san or '#' in move_san:
                    recent_check = True
                continue
            
            total_moves += 1
            game_moves += 1
            cp_loss = move.get('cp_loss', 0) or 0
            if cp_loss == 0:
                cp_loss = move.get('actual_cp_loss', 0) or 0
            phase = move.get('phase', 'middlegame')
            move_san = move.get('move_san', '')
            
            game_cpl_sum += cp_loss
            
            # Phase CPL tracking
            if phase == 'opening':
                opening_cpls.append(cp_loss)
            elif phase == 'middlegame':
                middlegame_cpls.append(cp_loss)
            else:
                endgame_cpls.append(cp_loss)
            
            # Transition CPL (moves 10-20)
            if 10 <= move_num <= 20:
                opening_outcomes['transition_cpl_sum'] += cp_loss
                opening_outcomes['transition_moves'] += 1
            
            # Blunder analysis with context
            if cp_loss >= 300:
                blunders += 1
                game_blunders += 1
                blunder_phases[phase] = blunder_phases.get(phase, 0) + 1
                openings[opening]['blunders'] += 1
                
                # === Skill Attribution ===
                if recent_capture:
                    blunder_contexts['after_capture'] += 1
                if recent_check:
                    blunder_contexts['after_check'] += 1
                if move_num >= 35:
                    blunder_contexts['time_trouble_likely'] += 1
                
                # Position context
                if prev_eval >= 150:
                    blunder_contexts['in_winning_position'] += 1
                    rating_cost_factors['blunders_in_winning_pos']['count'] += 1
                    rating_cost_factors['blunders_in_winning_pos']['estimated_points_lost'] += 15
                elif prev_eval <= -150:
                    blunder_contexts['in_losing_position'] += 1
                else:
                    blunder_contexts['in_equal_position'] += 1
                
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
            
            # Reset context flags after player's move
            recent_capture = 'x' in move_san
            recent_check = '+' in move_san or '#' in move_san
        
        # === Opening outcome tracking ===
        if opening_exit_eval is not None:
            opening_outcomes['games_with_opening_eval'] += 1
            opening_outcomes['avg_eval_after_opening'] += opening_exit_eval
            openings[opening]['eval_after_opening_sum'] += opening_exit_eval
            openings[opening]['eval_after_opening_count'] += 1
            
            if opening_exit_eval >= 50:
                opening_outcomes['left_opening_better'] += 1
            elif opening_exit_eval <= -50:
                opening_outcomes['left_opening_worse'] += 1
        
        # === Conversion tracking ===
        if had_winning_position:
            conversion_stats['winning_positions'] += 1
            if is_win:
                conversion_stats['converted_wins'] += 1
            else:
                rating_cost_factors['missed_wins']['count'] += 1
                rating_cost_factors['missed_wins']['estimated_points_lost'] += 20
        
        if had_losing_position:
            conversion_stats['losing_positions'] += 1
            if is_win or is_draw:
                conversion_stats['saved_draws_or_wins'] += 1
        
        # === Endgame collapse detection ===
        if len(endgame_cpls) > 0 and game_blunders >= 2:
            endgame_blunders = sum(1 for i, m in enumerate(moves_table) 
                                   if m.get('phase') == 'endgame' 
                                   and (m.get('cp_loss', 0) or 0) >= 300
                                   and (m.get('mover') or m.get('color')) == focus_color)
            if endgame_blunders >= 2 and is_loss:
                rating_cost_factors['endgame_collapses']['count'] += 1
                rating_cost_factors['endgame_collapses']['estimated_points_lost'] += 18
        
        # === Opening disaster detection ===
        opening_blunders = sum(1 for m in moves_table 
                              if m.get('phase') == 'opening' 
                              and (m.get('cp_loss', 0) or 0) >= 300
                              and (m.get('mover') or m.get('color')) == focus_color)
        if opening_blunders >= 2 and is_loss:
            rating_cost_factors['opening_disasters']['count'] += 1
            rating_cost_factors['opening_disasters']['estimated_points_lost'] += 12
        
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
            'is_loss': is_loss,
            'date': game.get('date', ''),
            'had_winning_pos': had_winning_position,
        })
    
    # Calculate averages
    avg_opening = sum(opening_cpls) / len(opening_cpls) if opening_cpls else 0
    avg_middlegame = sum(middlegame_cpls) / len(middlegame_cpls) if middlegame_cpls else 0
    avg_endgame = sum(endgame_cpls) / len(endgame_cpls) if endgame_cpls else 0
    
    # === PHASE PERFORMANCE INDEX (PPI) ===
    # PPI = player_CPL / baseline_CPL (lower is better, 1.0 = average)
    ppi = {
        'opening': avg_opening / PHASE_BASELINES['opening'] if PHASE_BASELINES['opening'] > 0 else 0,
        'middlegame': avg_middlegame / PHASE_BASELINES['middlegame'] if PHASE_BASELINES['middlegame'] > 0 else 0,
        'endgame': avg_endgame / PHASE_BASELINES['endgame'] if PHASE_BASELINES['endgame'] > 0 else 0,
    }
    
    # Determine best/worst phase BY PPI (not raw CPL!)
    best_phase = min(ppi, key=ppi.get) if ppi else 'unknown'
    worst_phase = max(ppi, key=ppi.get) if ppi else 'unknown'
    
    # Calculate rates per 100 moves
    blunder_rate = (blunders / total_moves * 100) if total_moves > 0 else 0
    mistake_rate = (mistakes / total_moves * 100) if total_moves > 0 else 0
    
    # Find best and worst games
    sorted_by_cpl = sorted(game_quality, key=lambda x: x['avg_cpl'])
    best_games = sorted_by_cpl[:3]
    worst_games = sorted_by_cpl[-3:][::-1]
    
    # Rating range
    rating_range = (min(ratings), max(ratings)) if ratings else (0, 0)
    
    # Trend summary with more detail
    trend = _compute_trend_summary(games, total_games)
    
    # Calculate color-specific stats
    white_win_rate = white_games['wins'] / white_games['games'] if white_games['games'] > 0 else 0
    black_win_rate = black_games['wins'] / black_games['games'] if black_games['games'] > 0 else 0
    white_avg_cpl = white_games['cpl_sum'] / white_games['moves'] if white_games['moves'] > 0 else 0
    black_avg_cpl = black_games['cpl_sum'] / black_games['moves'] if black_games['moves'] > 0 else 0
    
    # === Finalize opening outcomes ===
    if opening_outcomes['games_with_opening_eval'] > 0:
        opening_outcomes['avg_eval_after_opening'] /= opening_outcomes['games_with_opening_eval']
    if opening_outcomes['transition_moves'] > 0:
        opening_outcomes['avg_transition_cpl'] = opening_outcomes['transition_cpl_sum'] / opening_outcomes['transition_moves']
    else:
        opening_outcomes['avg_transition_cpl'] = 0
    
    # === Compute conversion rate ===
    conversion_rate = (conversion_stats['converted_wins'] / conversion_stats['winning_positions'] * 100) if conversion_stats['winning_positions'] > 0 else 0
    
    # === Determine biggest rating cost factor ===
    biggest_rating_cost = max(rating_cost_factors.items(), key=lambda x: x[1]['estimated_points_lost'])
    
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
        # Color stats
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
        # === NEW ANALYTICS ===
        'phase_baselines': PHASE_BASELINES,
        'ppi': ppi,  # Phase Performance Index
        'blunder_contexts': blunder_contexts,  # Skill attribution
        'conversion_stats': conversion_stats,
        'conversion_rate': conversion_rate,
        'opening_outcomes': opening_outcomes,
        'rating_cost_factors': rating_cost_factors,
        'biggest_rating_cost': biggest_rating_cost,
    }


def _empty_career_stats() -> Dict[str, Any]:
    """Return empty stats structure."""
    return {
        'total_games': 0, 'win_rate': 0, 'opening_cpl': 0, 'middlegame_cpl': 0,
        'endgame_cpl': 0, 'blunder_rate': 0, 'mistake_rate': 0, 'openings': {},
        'best_phase': 'unknown', 'worst_phase': 'unknown',
        'trend_summary': 'Not enough games for trend analysis',
        'white_stats': {}, 'black_stats': {}, 'worst_games': [], 'best_games': [],
        'blunder_phases': {}, 'rating_range': (0, 0), 'ppi': {},
        'blunder_contexts': {}, 'conversion_stats': {}, 'conversion_rate': 0,
        'opening_outcomes': {}, 'rating_cost_factors': {}, 'biggest_rating_cost': None,
        'phase_baselines': {'opening': 45, 'middlegame': 95, 'endgame': 130},
    }


def _compute_trend_summary(games: List[Dict], total_games: int) -> str:
    """Compute detailed trend summary."""
    if total_games < 10:
        return "Not enough games for trend analysis."
    
    first_half = games[:len(games)//2]
    second_half = games[len(games)//2:]
    
    first_blunders = 0
    first_moves = 0
    for g in first_half:
        focus_color = g.get('focus_color', 'white')
        for m in g.get('moves_table', []):
            if (m.get('mover') or m.get('color')) == focus_color:
                first_moves += 1
                cp = m.get('cp_loss', 0) or m.get('actual_cp_loss', 0) or 0
                if cp >= 300:
                    first_blunders += 1
    
    second_blunders = 0
    second_moves = 0
    for g in second_half:
        focus_color = g.get('focus_color', 'white')
        for m in g.get('moves_table', []):
            if (m.get('mover') or m.get('color')) == focus_color:
                second_moves += 1
                cp = m.get('cp_loss', 0) or m.get('actual_cp_loss', 0) or 0
                if cp >= 300:
                    second_blunders += 1
    
    first_rate = (first_blunders / first_moves * 100) if first_moves > 0 else 0
    second_rate = (second_blunders / second_moves * 100) if second_moves > 0 else 0
    
    if second_rate < first_rate * 0.8:
        return f"Improving! Blunder rate decreased from {first_rate:.1f} to {second_rate:.1f} per 100 moves."
    elif second_rate > first_rate * 1.2:
        return f"Blunder rate increased from {first_rate:.1f} to {second_rate:.1f} per 100 moves. Consider slowing down."
    else:
        return f"Consistent performance. Blunder rate stable around {(first_rate + second_rate)/2:.1f} per 100 moves."


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


def _format_skill_attribution(blunder_contexts: Dict[str, int], total_blunders: int) -> str:
    """Format skill attribution breakdown for blunders."""
    if not blunder_contexts or total_blunders == 0:
        return "No skill attribution data available."
    
    lines = []
    context_labels = {
        'after_capture': 'After captures (recapture blindness)',
        'after_check': 'After checks (check escape issues)',
        'in_winning_position': 'In winning positions (conversion failures)',
        'in_losing_position': 'In losing positions (desperation errors)',
        'in_equal_position': 'In equal positions (calculation errors)',
        'time_trouble_likely': 'Likely time trouble (late-game errors)',
    }
    
    for ctx, count in sorted(blunder_contexts.items(), key=lambda x: -x[1]):
        if count > 0:
            label = context_labels.get(ctx, ctx.replace('_', ' ').title())
            pct = (count / total_blunders * 100) if total_blunders > 0 else 0
            lines.append(f"- {label}: {count} ({pct:.0f}%)")
    
    return '\n'.join(lines) if lines else "No patterns detected."


def _format_rating_cost(rating_cost_factors: Dict[str, Any]) -> str:
    """Format what's costing the most rating points."""
    if not rating_cost_factors:
        return "No rating cost data available."
    
    cost_labels = {
        'blunders_in_winning_pos': 'Throwing away winning positions',
        'endgame_collapses': 'Endgame collapses (winning → lost)',
        'opening_disasters': 'Opening disasters (lost before move 15)',
        'missed_wins': 'Missed wins (drawing won positions)',
        'time_losses': 'Time management issues',
    }
    
    lines = []
    
    # Helper to get count value from either dict or int
    def get_count(item):
        val = item[1]
        if isinstance(val, dict):
            return val.get('count', 0)
        return val if isinstance(val, (int, float)) else 0
    
    # Handle both dict format and int format
    for factor, data in sorted(rating_cost_factors.items(), key=get_count, reverse=True):
        if isinstance(data, dict):
            count = data.get('count', 0)
            points = data.get('estimated_points_lost', 0)
        elif isinstance(data, (int, float)):
            count = data
            points = 0
        else:
            continue  # Skip invalid data
        
        if count > 0:
            label = cost_labels.get(factor, factor.replace('_', ' ').title())
            impact = '🔴' if count >= 3 else '🟡' if count >= 1 else ''
            points_str = f" (~{points} rating pts)" if points > 0 else ""
            lines.append(f"- {impact} {label}: {count} games{points_str}")
    
    if not lines:
        return "✅ No major rating drains identified."
    
    return '\n'.join(lines)


def _format_opening_outcomes(opening_outcomes: Dict[str, Any], openings: Dict) -> str:
    """Format opening outcome analysis (position quality after opening).

    Supports both per-opening dictionaries and aggregate-only structures.
    """
    if not opening_outcomes:
        return "No opening outcome data available."

    # Detect aggregate-only structure (current aggregator stores global stats)
    if isinstance(opening_outcomes, dict) and 'games_with_opening_eval' in opening_outcomes:
        games = opening_outcomes.get('games_with_opening_eval', 0)
        avg_eval = opening_outcomes.get('avg_eval_after_opening', 0)
        better = opening_outcomes.get('left_opening_better', 0)
        worse = opening_outcomes.get('left_opening_worse', 0)
        avg_transition = opening_outcomes.get('avg_transition_cpl', 0)

        lines = [
            f"Across all openings: {games} games with eval after move 15 (avg {avg_eval:+.0f}cp)",
            f"Left opening better in {better} games; worse in {worse} games",
            f"Transition CPL (moves 10-20): {avg_transition:.0f}",
        ]

        # If per-opening eval data exists inside openings, surface top openings by eval
        opening_eval_lines = []
        for name, data in openings.items():
            eval_count = data.get('eval_after_opening_count', 0)
            if eval_count == 0:
                continue
            avg_eval_opening = data.get('eval_after_opening_sum', 0) / eval_count
            opening_eval_lines.append((name, avg_eval_opening, data.get('games', 0)))

        if opening_eval_lines:
            opening_eval_lines = sorted(opening_eval_lines, key=lambda x: x[1], reverse=True)[:5]
            lines.append("Top openings by position quality after move 15:")
            for name, avg_eval_opening, games_played in opening_eval_lines:
                outcome = '✅ Good positions' if avg_eval_opening > 50 else '⚠️ Difficult positions' if avg_eval_opening < -50 else '➡️ Equal positions'
                lines.append(f"- {name[:35]}: {outcome} (avg {avg_eval_opening:+.0f}cp over {games_played} games)")

        return '\n'.join(lines)

    # Per-opening structure (future-proof)
    lines = []

    for opening_name, data in sorted(opening_outcomes.items(), key=lambda x: x[1].get('games', 0), reverse=True)[:5]:
        games = data.get('games', 0)
        if games == 0:
            continue

        avg_eval = data.get('avg_eval_after_opening', 0)
        transition_cpl = data.get('transition_cpl', 0)  # CPL for moves 10-20

        if avg_eval > 50:
            outcome = '✅ Good positions'
        elif avg_eval < -50:
            outcome = '⚠️ Difficult positions'
        else:
            outcome = '➡️ Equal positions'

        transition_note = f" (but {transition_cpl:.0f} CPL in moves 10-20)" if transition_cpl > 80 else ""

        lines.append(f"- {opening_name[:35]}: {outcome} (avg eval: {avg_eval:+.0f}cp){transition_note}")

    return '\n'.join(lines) if lines else "Not enough opening data."


def _format_ppi_table(ppi: Dict[str, float], phase_cpls: Dict[str, float]) -> str:
    """Format Phase Performance Index table."""
    if not ppi:
        return "No PPI data available."
    
    baselines = {'opening': 45, 'middlegame': 95, 'endgame': 130}
    
    lines = ["Phase Performance Index (1.0 = average, lower = better):"]
    lines.append("| Phase      | Your CPL | Baseline | PPI  | Assessment |")
    lines.append("|------------|----------|----------|------|------------|")
    
    for phase in ['opening', 'middlegame', 'endgame']:
        your_cpl = phase_cpls.get(phase, 0)
        baseline = baselines.get(phase, 100)
        phase_ppi = ppi.get(phase, 1.0)
        
        if phase_ppi <= 0.7:
            assessment = "Excellent"
        elif phase_ppi <= 0.9:
            assessment = "Good"
        elif phase_ppi <= 1.1:
            assessment = "Average"
        elif phase_ppi <= 1.3:
            assessment = "Below avg"
        else:
            assessment = "Needs work"
        
        lines.append(f"| {phase.title():<10} | {your_cpl:>8.0f} | {baseline:>8} | {phase_ppi:.2f} | {assessment:<10} |")
    
    return '\n'.join(lines)


def _format_conversion_stats(conversion_stats: Dict, conversion_rate: float) -> str:
    """Format conversion tracking stats."""
    if not conversion_stats:
        return "No conversion data available."
    
    winning_pos = conversion_stats.get('winning_positions', 0)
    converted = conversion_stats.get('converted_wins', 0)
    losing_pos = conversion_stats.get('losing_positions', 0)
    saved = conversion_stats.get('saved_draws_or_wins', 0)
    
    lines = []
    
    if winning_pos > 0:
        conv_pct = (converted / winning_pos * 100)
        if conv_pct >= 90:
            assessment = "✅ Excellent"
        elif conv_pct >= 75:
            assessment = "Good"
        elif conv_pct >= 60:
            assessment = "⚠️ Needs work"
        else:
            assessment = "🔴 Major issue"
        lines.append(f"Winning position conversion: {converted}/{winning_pos} ({conv_pct:.0f}%) - {assessment}")
    
    if losing_pos > 0:
        save_pct = (saved / losing_pos * 100)
        lines.append(f"Swindles from losing positions: {saved}/{losing_pos} ({save_pct:.0f}%)")
    
    return '\n'.join(lines) if lines else "Not enough position data."


def _format_opening_stats_v2(openings: Dict[str, Dict]) -> str:
    """Format opening statistics with enhanced metrics (v2)."""
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
        
        # Get eval after opening if available
        avg_eval = stats.get('avg_eval_after_opening', None)
        eval_str = f", Pos:{avg_eval:+.0f}cp" if avg_eval is not None else ""
        
        # Warnings
        warnings = []
        if blunders >= 3:
            warnings.append(f"⚠️{blunders} blunders")
        if win_rate < 0.35 and games >= 3:
            warnings.append(f"🔴low WR")
        
        warning_str = f" ({', '.join(warnings)})" if warnings else ""
        
        lines.append(f"- {name[:35]}: {games}g, {wins}W-{losses}L ({win_rate:.0%}), CPL:{avg_cpl:.0f}{eval_str}{warning_str}")
    
    return '\n'.join(lines) if lines else "No opening data"


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
