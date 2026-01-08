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


# API client will be initialized lazily
_openai_client = None


def _get_openaGet API key from environment (already loaded by load_dotenv at module import)
            api_key = os.getenv('OPENAI_API_KEY')
                # Try loading from .env file using python-dotenv
                try:
                    from dotenv import load_dotenv
                    load_dotenv()
                    api_key = os.getenv('OPENAI_API_KEY')
                except ImportError:
                    pass  # dotenv not installed, continue with env var only
            
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment or .env file")
            
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
    
    # Simple parsing - could be made more robust with regex or structured outputs
    sections = content.split('\n\n')
    
    parsed = {
        'summary': '',
        'key_moments': [],
        'opening': '',
        'strategy': '',
        'tactics': '',
        'training': [],
    }
    
    current_section = None
    for section in sections:
        section = section.strip()
        if not section:
            continue
        
        # Detect sections by headers
        lower = section.lower()
        if 'game summary' in lower or 'overall' in lower:
            current_section = 'summary'
        elif 'key moment' in lower or 'critical' in lower:
            current_section = 'key_moments'
        elif 'opening' in lower:
            current_section = 'opening'
        elif 'strategic' in lower or 'strategy' in lower:
            current_section = 'strategy'
        elif 'tactical' in lower or 'tactics' in lower:
            current_section = 'tactics'
        elif 'training' in lower or 'recommendation' in lower:
            current_section = 'training'
        
        # Store content
        if current_section == 'summary' and not parsed['summary']:
            parsed['summary'] = section
        elif current_section == 'opening' and not parsed['opening']:
            parsed['opening'] = section
        elif current_section == 'strategy' and not parsed['strategy']:
            parsed['strategy'] = section
        elif current_section == 'tactics' and not parsed['tactics']:
            parsed['tactics'] = section
        elif current_section == 'training':
            # Extract bullet points
            lines = section.split('\n')
            for line in lines:
                if line.strip().startswith(('-', '•', '*', '1.', '2.', '3.')):
                    parsed['training'].append(line.strip().lstrip('-•* 123456789.'))
    
    # Fallback if parsing fails
    if not parsed['summary']:
        parsed['summary'] = content[:200] + '...'
    
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
