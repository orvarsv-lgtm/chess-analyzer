"""
Coaching Prompt Engine - Sophisticated LLM Coaching Prompts

This module generates the prompts that turn raw chess analytics 
into genuine coaching insights via GPT-4.

The AI Coach is a DIAGNOSTIC REASONING LAYER, not a statistics printer.
"""

from typing import Dict, Any, Optional


def build_career_coaching_prompt(
    stats: Dict[str, Any],
    player_name: str,
    player_rating: Optional[int] = None,
) -> str:
    """
    Build the master prompt for career-level coaching analysis.
    
    This prompt instructs GPT-4 to:
    1. Identify ONE primary cause (not multiple equal-weight issues)
    2. Explain the cognitive failure mechanism (WHY it happens)
    3. Map evidence to the diagnosis
    4. Describe the failure loop
    5. Give ONE behavioral fix + max 2 secondary fixes
    6. Project outcome
    """
    
    # Extract all relevant data
    total_games = stats.get('total_games', 0)
    wins = stats.get('wins', 0)
    losses = stats.get('losses', 0)
    draws = stats.get('draws', 0)
    win_rate = stats.get('win_rate', 0)
    
    # Phase CPL
    opening_cpl = stats.get('opening_cpl', 0)
    middlegame_cpl = stats.get('middlegame_cpl', 0)
    endgame_cpl = stats.get('endgame_cpl', 0)
    
    # Phase Performance Index (PPI) - lower is better, 1.0 = baseline
    ppi = stats.get('ppi', {})
    
    # Blunder data
    total_blunders = stats.get('total_blunders', 0)
    blunder_rate = stats.get('blunder_rate', 0)
    blunder_phases = stats.get('blunder_phases', {})
    blunder_contexts = stats.get('blunder_contexts', {})
    
    # Conversion data
    conversion_stats = stats.get('conversion_stats', {})
    conversion_rate = stats.get('conversion_rate', 0)
    winning_positions = conversion_stats.get('winning_positions', 0)
    converted_wins = conversion_stats.get('converted_wins', 0)
    
    # Rating cost analysis
    rating_cost_factors = stats.get('rating_cost_factors', {})
    biggest_cost = stats.get('biggest_rating_cost', ('unknown', {'count': 0}))
    
    # Opening outcomes
    opening_outcomes = stats.get('opening_outcomes', {})
    avg_eval_after_opening = opening_outcomes.get('avg_eval_after_opening', 0)
    
    # Openings breakdown
    openings = stats.get('openings', {})
    openings_summary = _format_openings_for_prompt(openings)
    
    # Trend
    trend = stats.get('trend_summary', 'No trend data')
    
    # Build the data block
    data_block = f"""
═══════════════════════════════════════════════════════════════
PLAYER DATA: {player_name} ({player_rating or 'Unrated'})
═══════════════════════════════════════════════════════════════

RECORD: {wins}W - {losses}L - {draws}D ({total_games} games, {win_rate:.0%} win rate)

CONVERSION ANALYSIS:
• Winning positions reached (≥+1.5): {winning_positions}
• Successfully converted to wins: {converted_wins}
• Conversion rate: {conversion_rate:.0f}%
• Games thrown away: {winning_positions - converted_wins}

PHASE CPL (Centipawn Loss):
• Opening: {opening_cpl:.0f} CPL
• Middlegame: {middlegame_cpl:.0f} CPL  
• Endgame: {endgame_cpl:.0f} CPL

PHASE PERFORMANCE INDEX (1.0 = baseline, lower = better):
• Opening PPI: {ppi.get('opening', 0):.2f}
• Middlegame PPI: {ppi.get('middlegame', 0):.2f}
• Endgame PPI: {ppi.get('endgame', 0):.2f}

BLUNDER DISTRIBUTION:
• Total blunders: {total_blunders}
• Blunder rate: {blunder_rate:.1f} per 100 moves
• Opening blunders: {blunder_phases.get('opening', 0)}
• Middlegame blunders: {blunder_phases.get('middlegame', 0)}
• Endgame blunders: {blunder_phases.get('endgame', 0)}

BLUNDER CONTEXT (When do blunders happen?):
• After captures (recapture errors): {blunder_contexts.get('after_capture', 0)}
• In winning positions (≥+1.5): {blunder_contexts.get('in_winning_position', 0)}
• In equal positions: {blunder_contexts.get('in_equal_position', 0)}
• After move 35 (time pressure proxy): {blunder_contexts.get('time_trouble_likely', 0)}
• After checks: {blunder_contexts.get('after_check', 0)}

RATING COST FACTORS (estimated):
• Blunders in winning positions: {rating_cost_factors.get('blunders_in_winning_pos', {}).get('count', 0)} occurrences (~{rating_cost_factors.get('blunders_in_winning_pos', {}).get('estimated_points_lost', 0)} rating points lost)
• Endgame collapses: {rating_cost_factors.get('endgame_collapses', {}).get('count', 0)} occurrences (~{rating_cost_factors.get('endgame_collapses', {}).get('estimated_points_lost', 0)} rating points lost)
• Opening disasters: {rating_cost_factors.get('opening_disasters', {}).get('count', 0)} occurrences (~{rating_cost_factors.get('opening_disasters', {}).get('estimated_points_lost', 0)} rating points lost)
• Missed wins (threw away won games): {rating_cost_factors.get('missed_wins', {}).get('count', 0)} occurrences (~{rating_cost_factors.get('missed_wins', {}).get('estimated_points_lost', 0)} rating points lost)

OPENING OUTCOMES:
• Average eval after move 15: {avg_eval_after_opening:+.0f}cp
{openings_summary}

TREND:
{trend}
═══════════════════════════════════════════════════════════════
"""

    # Build the instruction prompt
    instruction_prompt = """
You are an elite chess coach analyzing a player's game data. Your job is DIAGNOSTIC REASONING, not statistics recitation.

══════════════════════════════════════════════════════════════
CRITICAL RULES — VIOLATING THESE MAKES YOUR OUTPUT WORTHLESS
══════════════════════════════════════════════════════════════

1. IDENTIFY EXACTLY ONE PRIMARY CAUSE
   - If you list multiple issues with equal weight, you have failed
   - The primary cause is the cognitive/behavioral failure that explains the most rating loss
   - Everything else is secondary

2. EXPLAIN THE MECHANISM, NOT THE STATISTIC
   - Bad: "Your endgame CPL is 165"
   - Good: "You stop calculating when the position simplifies because you assume fewer pieces = easier"
   
3. NO GENERIC ADVICE
   - If your advice could apply to any 1200-rated player, it is WRONG
   - "Calculate more" = WRONG
   - "Study endgames" = WRONG
   - "Focus on tactics" = WRONG

4. EVERY CLAIM MUST MAP TO DATA
   - Don't say "you struggle in endgames" unless the data shows it
   - Cite specific numbers when making claims

5. BEHAVIORAL FIXES ONLY
   - Not "improve X" but "do Y instead of Z"
   - Must be testable and repeatable

══════════════════════════════════════════════════════════════
REQUIRED OUTPUT STRUCTURE (follow exactly)
══════════════════════════════════════════════════════════════

## Executive Diagnosis

[ONE paragraph. State the SINGLE primary cause of rating loss. Be direct and confident. Start with a strong claim like "Your rating is capped by X" or "You are losing games because of Y".]

## Why This Happens

[Explain the COGNITIVE or BEHAVIORAL mechanism. What does the player misjudge? What false assumption do they make? What triggers the error? Connect multiple data points to ONE explanation.

Use specific cognitive failure patterns like:
- Forced-move blindness (not seeing opponent's best reply)
- Simplification bias (relaxing when pieces trade)
- Passive king bias (keeping king safe when it needs to be active)
- Threat exhaustion (checking threats for 2-3 moves, not 4-5)
- Evaluation inertia (assuming advantage persists without rechecking)]

## Evidence

[Map your diagnosis to SPECIFIC data points. Use bullet points. Every claim must cite a number from the data.]

## The Failure Loop

[Describe the REPEATABLE pattern in one line, formatted as:]

**Failure Loop:** [trigger] → [false assumption] → [behavior] → [result]

[This should make the player say "Yes — that's exactly what happens."]

## Primary Fix

[ONE behavioral rule. Not "improve X" but "When Y happens, do Z instead of W."]

**The Rule:** [State it clearly in bold]

[Explain why this rule addresses the root cause, not just the symptom.]

## Secondary Fixes (if relevant)

[MAX 2. Only include if they clearly support the primary fix. Each must include:
- What to change
- Why it matters (cite data)
- What metric will improve]

## Expected Outcome

[Ground this in data. No hype. Example: "Fixing this pattern would likely convert X additional wins per Y games based on your historical conversion rate."]

══════════════════════════════════════════════════════════════
TONE REQUIREMENTS
══════════════════════════════════════════════════════════════

- Confident and direct
- Coach-like (occasionally blunt)
- Never vague, never generic
- Sound like: "I've analyzed hundreds of players like you. Here's what's actually holding you back."

══════════════════════════════════════════════════════════════
QUALITY CHECK (verify before responding)
══════════════════════════════════════════════════════════════

□ Is there exactly ONE primary issue? If no, rewrite.
□ Does each recommendation map to a specific metric? If no, rewrite.
□ Could this advice apply to a random 1200 player? If yes, rewrite.
□ Did I explain WHY (mechanism), not just WHAT (statistic)? If no, rewrite.

"""

    return instruction_prompt + "\n\nPLAYER DATA TO ANALYZE:\n" + data_block


def build_single_game_coaching_prompt(
    game_data: Dict[str, Any],
    player_color: str,
    player_rating: Optional[int] = None,
) -> str:
    """
    Build prompt for single game analysis.
    
    This provides move-by-move context for deeper analysis.
    """
    
    moves_table = game_data.get('moves_table', [])
    opening = game_data.get('opening_name') or game_data.get('opening', 'Unknown')
    result = game_data.get('result', '*')
    
    # Collect key moments
    blunders = []
    phase_cpl = {'opening': [], 'middlegame': [], 'endgame': []}
    eval_swings = []
    prev_eval = 0
    
    had_winning = False
    had_losing = False
    
    for move in moves_table:
        move_color = move.get('mover') or move.get('color')
        cp_loss = move.get('cp_loss', 0) or move.get('actual_cp_loss', 0) or 0
        phase = move.get('phase', 'middlegame')
        move_num = move.get('move_num') or ((move.get('ply', 0) + 1) // 2)
        san = move.get('san') or move.get('move_san', '?')
        best_move = move.get('best_move_san', '?')
        
        # Track eval
        eval_after = move.get('score_cp') or move.get('eval_after')
        if eval_after is not None:
            try:
                eval_val = int(eval_after)
                if player_color == 'black':
                    eval_val = -eval_val
                
                if eval_val >= 150:
                    had_winning = True
                if eval_val <= -150:
                    had_losing = True
                
                # Track swings on our moves
                if move_color == player_color:
                    swing = prev_eval - eval_val
                    if abs(swing) >= 100:
                        eval_swings.append({
                            'move': move_num,
                            'san': san,
                            'swing': swing,
                            'phase': phase,
                            'best': best_move,
                        })
                
                prev_eval = eval_val
            except (TypeError, ValueError):
                pass
        
        if move_color != player_color:
            continue
        
        # Track phase CPL
        phase_cpl[phase].append(cp_loss)
        
        # Track blunders
        if cp_loss >= 200:
            blunders.append({
                'move': move_num,
                'san': san,
                'cp_loss': cp_loss,
                'phase': phase,
                'best': best_move,
            })
    
    # Calculate averages
    avg_cpl = {
        'opening': sum(phase_cpl['opening']) / len(phase_cpl['opening']) if phase_cpl['opening'] else 0,
        'middlegame': sum(phase_cpl['middlegame']) / len(phase_cpl['middlegame']) if phase_cpl['middlegame'] else 0,
        'endgame': sum(phase_cpl['endgame']) / len(phase_cpl['endgame']) if phase_cpl['endgame'] else 0,
    }
    
    # Determine outcome
    is_win = (player_color == 'white' and result == '1-0') or (player_color == 'black' and result == '0-1')
    is_loss = (player_color == 'white' and result == '0-1') or (player_color == 'black' and result == '1-0')
    
    # Format blunders
    blunders_str = ""
    if blunders:
        for b in blunders:
            blunders_str += f"• Move {b['move']} ({b['phase']}): {b['san']} lost {b['cp_loss']}cp (best: {b['best']})\n"
    else:
        blunders_str = "None"
    
    # Format swings
    swings_str = ""
    if eval_swings:
        for s in sorted(eval_swings, key=lambda x: abs(x['swing']), reverse=True)[:5]:
            direction = "lost" if s['swing'] > 0 else "gained"
            swings_str += f"• Move {s['move']} ({s['phase']}): {s['san']} {direction} {abs(s['swing'])}cp\n"
    else:
        swings_str = "None significant"
    
    # Build prompt
    data_block = f"""
═══════════════════════════════════════════════════════════════
SINGLE GAME ANALYSIS
═══════════════════════════════════════════════════════════════

Opening: {opening}
Player: {player_color.title()} ({player_rating or 'Unrated'})
Result: {result} ({'Win' if is_win else 'Loss' if is_loss else 'Draw'})

Had winning position (≥+1.5): {'Yes' if had_winning else 'No'}
Had losing position (≤-1.5): {'Yes' if had_losing else 'No'}

PHASE CPL:
• Opening: {avg_cpl['opening']:.0f}
• Middlegame: {avg_cpl['middlegame']:.0f}
• Endgame: {avg_cpl['endgame']:.0f}

BLUNDERS (≥200cp loss):
{blunders_str}

BIGGEST EVAL SWINGS:
{swings_str}
═══════════════════════════════════════════════════════════════
"""

    instruction = """
You are a chess coach reviewing a single game. Provide focused, actionable feedback.

RULES:
1. Identify the SINGLE MOVE or DECISION that most determined the outcome
2. Explain WHY that error happened (cognitive mechanism, not just "miscalculation")
3. Give ONE specific lesson to take away from this game
4. Be direct and specific — no generic advice

OUTPUT STRUCTURE:

## What Decided This Game
[One sentence identifying the turning point]

## Why It Happened  
[The cognitive/behavioral error that led to this mistake]

## The Lesson
[One specific, actionable takeaway]
"""

    return instruction + "\n" + data_block


def _format_openings_for_prompt(openings: Dict[str, Dict]) -> str:
    """Format opening stats for the prompt."""
    if not openings:
        return "No opening data"
    
    # Filter and sort
    filtered = {k: v for k, v in openings.items() if k and k != 'Unknown' and v.get('games', 0) >= 2}
    if not filtered:
        return "Insufficient opening data"
    
    sorted_openings = sorted(filtered.items(), key=lambda x: x[1]['games'], reverse=True)[:5]
    
    lines = []
    for name, data in sorted_openings:
        games = data['games']
        wins = data['wins']
        losses = data.get('losses', 0)
        blunders = data.get('blunders', 0)
        total_moves = data.get('total_moves', 1)
        avg_cpl = data.get('total_cpl', 0) / total_moves if total_moves > 0 else 0
        
        # Calculate eval after opening if available
        eval_sum = data.get('eval_after_opening_sum', 0)
        eval_count = data.get('eval_after_opening_count', 0)
        eval_str = f", avg eval@15: {eval_sum/eval_count:+.0f}" if eval_count > 0 else ""
        
        lines.append(f"• {name}: {games}g ({wins}W-{losses}L), CPL: {avg_cpl:.0f}, {blunders} blunders{eval_str}")
    
    return '\n'.join(lines)


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

AI_COACH_SYSTEM_PROMPT = """You are an elite chess coach with 25+ years of experience coaching players from beginner to grandmaster level.

Your role is DIAGNOSTIC REASONING — you identify the root cause of chess problems, not just describe statistics.

Core principles:
1. ONE primary issue, always. Multiple issues with equal weight = failed analysis.
2. Explain the MECHANISM (why errors happen), not just the statistic.
3. Every piece of advice must be SPECIFIC to this player's data.
4. Generic advice ("study tactics", "calculate more") is forbidden.
5. Your tone is confident, direct, occasionally blunt — like a coach who genuinely wants to help.

You speak from data, not platitudes. You identify patterns others miss. You give advice that makes players say "Yes — that's exactly my problem."
"""
