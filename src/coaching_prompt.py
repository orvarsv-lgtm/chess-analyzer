"""
Coaching Prompt Engine - Elite Chess Coaching Prompts

This module generates the prompts that turn raw chess analytics 
into premium diagnostic coaching insights via GPT-4.

The AI Coach produces executive-level performance reports that:
- Identify ONE primary cause with quantified impact
- Explain the cognitive mechanism (not just statistics)
- Provide behavioral rules with measurable targets
- Project expected rating gains based on data
"""

from typing import Dict, Any, Optional


def build_career_coaching_prompt(
    stats: Dict[str, Any],
    player_name: str,
    player_rating: Optional[int] = None,
) -> str:
    """
    Build the master prompt for elite career-level coaching analysis.
    
    This prompt instructs GPT-4 to produce a premium coaching report with:
    1. Executive diagnosis (ONE primary cause, quantified)
    2. Cognitive mechanism explanation
    3. Evidence tables with specific numbers
    4. The failure loop pattern
    5. Primary fix with behavioral rule
    6. Secondary fixes with target metrics
    7. Expected rating impact projection
    8. One-sentence summary
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
    mistake_rate = stats.get('mistake_rate', 0)
    blunder_phases = stats.get('blunder_phases', {})
    blunder_contexts = stats.get('blunder_contexts', {})
    
    # Conversion data
    conversion_stats = stats.get('conversion_stats', {})
    conversion_rate = stats.get('conversion_rate', 0)
    winning_positions = conversion_stats.get('winning_positions', 0)
    converted_wins = conversion_stats.get('converted_wins', 0)
    games_thrown = winning_positions - converted_wins
    
    # Rating cost analysis
    rating_cost_factors = stats.get('rating_cost_factors', {})
    
    # Calculate estimated rating points lost
    blunders_in_winning = rating_cost_factors.get('blunders_in_winning_pos', {})
    endgame_collapses = rating_cost_factors.get('endgame_collapses', {})
    missed_wins = rating_cost_factors.get('missed_wins', {})
    
    # Opening outcomes
    opening_outcomes = stats.get('opening_outcomes', {})
    avg_eval_after_opening = opening_outcomes.get('avg_eval_after_opening', 0)
    
    # Openings breakdown
    openings = stats.get('openings', {})
    openings_table = _format_openings_table(openings)
    
    # Trend
    trend = stats.get('trend_summary', 'No trend data')
    
    # Calculate blunder percentages
    after_capture_pct = (blunder_contexts.get('after_capture', 0) / total_blunders * 100) if total_blunders > 0 else 0
    in_winning_pct = (blunder_contexts.get('in_winning_position', 0) / total_blunders * 100) if total_blunders > 0 else 0
    endgame_pct = (blunder_phases.get('endgame', 0) / total_blunders * 100) if total_blunders > 0 else 0
    after_check_pct = (blunder_contexts.get('after_check', 0) / total_blunders * 100) if total_blunders > 0 else 0
    
    # Build the data block
    data_block = f"""
══════════════════════════════════════════════════════════════════════════════
PLAYER DATA: {player_name} ({player_rating or 'Unrated'})
══════════════════════════════════════════════════════════════════════════════

📊 HIGH-LEVEL RESULTS
┌─────────────────────────────────┬────────────┐
│ Metric                          │ Value      │
├─────────────────────────────────┼────────────┤
│ Games analyzed                  │ {total_games:>10} │
│ Win rate                        │ {win_rate*100:>9.0f}% │
│ Winning positions reached (≥+1.5) │ {winning_positions:>10} │
│ Wins from winning positions     │ {converted_wins:>10} │
│ Conversion rate                 │ {conversion_rate:>9.0f}% │
│ Games thrown away               │ {games_thrown:>10} │
│ Blunders / 100 moves            │ {blunder_rate:>10.1f} │
│ Mistakes / 100 moves            │ {mistake_rate:>10.1f} │
└─────────────────────────────────┴────────────┘

🎯 BLUNDER CONTEXT ANALYSIS
┌────────────────────────────────┬──────────┬─────────────┐
│ Situation                      │ Blunders │ % of total  │
├────────────────────────────────┼──────────┼─────────────┤
│ After captures                 │ {blunder_contexts.get('after_capture', 0):>8} │ {after_capture_pct:>10.0f}% │
│ In winning positions (≥+1.5)   │ {blunder_contexts.get('in_winning_position', 0):>8} │ {in_winning_pct:>10.0f}% │
│ In endgame phase               │ {blunder_phases.get('endgame', 0):>8} │ {endgame_pct:>10.0f}% │
│ After checks                   │ {blunder_contexts.get('after_check', 0):>8} │ {after_check_pct:>10.0f}% │
│ Time pressure (move 35+)       │ {blunder_contexts.get('time_trouble_likely', 0):>8} │ {(blunder_contexts.get('time_trouble_likely', 0) / total_blunders * 100) if total_blunders > 0 else 0:>10.0f}% │
└────────────────────────────────┴──────────┴─────────────┘

♟️ PHASE PERFORMANCE
┌─────────────┬─────────┬───────────────────────────────┐
│ Phase       │ Avg CPL │ Phase Performance Index (PPI) │
├─────────────┼─────────┼───────────────────────────────┤
│ Opening     │ {opening_cpl:>7.0f} │ {ppi.get('opening', 0):>29.2f} │
│ Middlegame  │ {middlegame_cpl:>7.0f} │ {ppi.get('middlegame', 0):>29.2f} │
│ Endgame     │ {endgame_cpl:>7.0f} │ {ppi.get('endgame', 0):>29.2f} │
└─────────────┴─────────┴───────────────────────────────┘
(PPI: < 0.8 = strong, 0.8-1.0 = average, > 1.0 = weak)

🎲 OPENING OUTCOMES (Eval @ move 15)
{openings_table}

💰 RATING COST FACTORS (estimated)
• Blunders in winning positions: {blunders_in_winning.get('count', 0)} occurrences (~{blunders_in_winning.get('estimated_points_lost', 0)} rating points lost)
• Endgame collapses: {endgame_collapses.get('count', 0)} occurrences (~{endgame_collapses.get('estimated_points_lost', 0)} rating points lost)
• Missed wins: {missed_wins.get('count', 0)} occurrences (~{missed_wins.get('estimated_points_lost', 0)} rating points lost)

📈 TREND
{trend}

══════════════════════════════════════════════════════════════════════════════
"""

    # Build the instruction prompt
    instruction_prompt = """
You are an elite chess coach producing a premium executive performance report. Your output must match the quality of a $500/hour professional coach.

══════════════════════════════════════════════════════════════════════════════
CRITICAL RULES — VIOLATING ANY OF THESE MAKES YOUR OUTPUT WORTHLESS
══════════════════════════════════════════════════════════════════════════════

1. ONE PRIMARY CAUSE ONLY
   - If you identify multiple issues with equal weight, you have FAILED
   - Everything traces back to ONE cognitive/behavioral failure
   - Use specific numbers: "33 games thrown away" not "many games lost"

2. NAME THE PATTERNS
   - Give cognitive failures specific names: "Post-Capture Blindness", "Complacency Syndrome"
   - These names should be memorable and precise

3. QUANTIFY EVERYTHING
   - Bad: "You blunder frequently after captures"
   - Good: "46 blunders (38%) occur immediately after captures"

4. BEHAVIORAL RULES, NOT VAGUE ADVICE
   - Bad: "Calculate more carefully when winning"
   - Good: "In any position ≥+1.5, identify opponent's best forcing reply before moving. If you cannot name it, you are not allowed to simplify."

5. TARGET METRICS FOR EVERY FIX
   - Every recommendation needs: Current value → Target value
   - Example: "Post-capture blunder rate: 38% → under 22%"

6. EXPECTED IMPACT MUST BE CALCULATED
   - Show the math: "Improving conversion from 51% → 65% = ~14 additional wins per 100 games"
   - Estimate rating gain based on the data

══════════════════════════════════════════════════════════════════════════════
REQUIRED OUTPUT FORMAT (follow EXACTLY)
══════════════════════════════════════════════════════════════════════════════

## 🧠 Executive Diagnosis (Read This First)

[ONE paragraph. Start with a strong claim: "Your rating is capped by..." or "Your rating is severely limited by..."]

[Second paragraph explaining the SINGLE pattern in concrete terms. Use specific numbers. End with: "Fixing this one behavior would yield a larger rating gain than improving every other area combined."]

---

## 🔴 Primary Leak: [Name It]

**What's happening:**
[Use exact numbers from the data. Example: "You reached winning positions in 68 games but converted only 35 into wins. That means: 33 winning games were thrown away."]

**🔁 The Failure Loop**

```
[Trigger] → [False assumption] → [Behavior change] → [Opponent action] → [Result]
```

Example: `Gain advantage → assume reduced complexity → stop scanning for forcing replies → opponent finds resource → evaluation collapses`

[Add: "This loop repeats regardless of opening, color, or time control."]

---

## 🧪 Evidence Breakdown

**Blunders by Context:**
[Reference the context table data. Highlight the key insight: where vigilance drops]

**Phase Performance:**
[Interpret the PPI numbers. Identify which phase is weakest and WHY (not just the number)]

**Opening Outcomes:**
[If openings are NOT the problem, say so clearly: "Your openings are not the problem. You routinely exit with an advantage and lose it later."]

---

## ⚠️ Tactical Blind Spots

**1️⃣ [Named Pattern #1]** (e.g., "Post-Capture Blindness")
[X blunders (Y%) occur in this situation. Explain the cognitive failure.]

**2️⃣ [Named Pattern #2]** (if data supports it)
[Same format]

---

## 🎯 Primary Fix (Non-Negotiable)

**The [Name] Rule:**

> [State the behavioral rule in a blockquote. It must be specific, testable, and repeatable.]

**If you cannot name:**
1. [First thing to check]
2. [Second thing to check]

**→ You are not allowed to [specific action].**

[Explain why this rule directly attacks the root cause.]

---

## 🛠 Secondary Fixes

**1. [Fix Name]**
- What to do: [Specific action]
- Why it matters: [Cite the data point]
- Target metric: [Current] → [Target]

**2. [Fix Name]** (only if data supports)
- What to do: [Specific action]  
- Why it matters: [Cite the data point]
- Target metric: [Current] → [Target]

---

## 📈 Expected Impact

If you:
- [Specific improvement #1]
- [Specific improvement #2]

Then based on your game data:
- **[X] additional wins per 100 games**
- **Estimated rating gain: +[low] to +[high] points**

This improvement comes without changing openings, tactics training volume, or time control.

---

## ✅ One-Sentence Summary

[A punchy, memorable summary. Example: "You don't lose because you don't know what to do — you lose because you stop calculating precisely at the moment precision matters most."]

══════════════════════════════════════════════════════════════════════════════
TONE REQUIREMENTS
══════════════════════════════════════════════════════════════════════════════

- Confident, direct, occasionally blunt
- Like a $500/hour coach who genuinely wants to help
- Never vague, never generic, never soft
- Sound like: "I've analyzed thousands of players. This is what's actually holding you back."

══════════════════════════════════════════════════════════════════════════════
QUALITY CHECK (verify before responding)
══════════════════════════════════════════════════════════════════════════════

□ Is there exactly ONE primary issue? If no, rewrite.
□ Did I use specific numbers throughout? If no, rewrite.
□ Does each fix have a target metric (X → Y)? If no, rewrite.
□ Did I calculate expected rating gain? If no, rewrite.
□ Could this advice apply to a random 1200 player? If yes, rewrite.
□ Did I end with a memorable one-sentence summary? If no, add it.

"""

    return instruction_prompt + "\n\nPLAYER DATA TO ANALYZE:\n" + data_block


def _format_openings_table(openings: Dict[str, Dict]) -> str:
    """Format opening stats as a table for the prompt."""
    if not openings:
        return "No opening data available"
    
    # Filter and sort
    filtered = {k: v for k, v in openings.items() if k and k != 'Unknown' and v.get('games', 0) >= 2}
    if not filtered:
        return "Insufficient opening data"
    
    sorted_openings = sorted(filtered.items(), key=lambda x: x[1]['games'], reverse=True)[:5]
    
    lines = ["┌────────────────────────────────┬───────┬──────────────┬──────────┐",
             "│ Opening                        │ Games │ Avg Eval @15 │ Win Rate │",
             "├────────────────────────────────┼───────┼──────────────┼──────────┤"]
    
    for name, data in sorted_openings:
        games = data['games']
        wins = data['wins']
        win_rate = (wins / games * 100) if games > 0 else 0
        
        # Calculate eval after opening if available
        eval_sum = data.get('eval_after_opening_sum', 0)
        eval_count = data.get('eval_after_opening_count', 0)
        eval_str = f"{eval_sum/eval_count:+.0f} cp" if eval_count > 0 else "N/A"
        
        # Truncate opening name if too long
        display_name = name[:30] if len(name) > 30 else name
        
        lines.append(f"│ {display_name:<30} │ {games:>5} │ {eval_str:>12} │ {win_rate:>7.0f}% │")
    
    lines.append("└────────────────────────────────┴───────┴──────────────┴──────────┘")
    
    return '\n'.join(lines)


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

AI_COACH_SYSTEM_PROMPT = """You are an elite chess coach producing executive-level performance reports. Your analysis is worth $500/hour.

Your role is DIAGNOSTIC REASONING — identifying the single root cause that explains the majority of rating loss.

Core principles:
1. ONE primary issue, always. Multiple issues with equal weight = failed analysis.
2. NAME your patterns: "Post-Capture Blindness", "Complacency Syndrome", "Evaluation Inertia"
3. QUANTIFY everything: "33 games thrown away" not "many games lost"
4. BEHAVIORAL RULES, not vague advice: "When ≥+1.5, identify opponent's best forcing reply before moving"
5. TARGET METRICS: Every fix needs "Current → Target" numbers
6. Calculate EXPECTED RATING GAIN based on the data

Forbidden phrases:
- "Calculate more carefully"
- "Study endgames"  
- "Focus on tactics"
- "Be more vigilant"
- Any advice that could apply to any 1200-rated player

You speak with the confidence of someone who has analyzed thousands of games and knows exactly what's holding this player back.
"""
