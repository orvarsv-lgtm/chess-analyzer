"""
Coaching Prompt Engine - Elite Chess Coaching Prompts

This module generates the prompts that turn raw chess analytics 
into premium diagnostic coaching insights via GPT.

The AI Coach produces executive-level performance reports that:
- Distinguish ROOT CAUSE from MANIFESTATIONS
- Identify player's meta-cognitive profile
- Provide behavioral rules with psychological grounding
- Include negative constraints ("Do NOT do this")
- Calibrate confidence based on sample size
- Project expected rating gains with confidence bounds
"""

from typing import Dict, Any, Optional


def build_career_coaching_prompt(
    stats: Dict[str, Any],
    player_name: str,
    player_rating: Optional[int] = None,
) -> str:
    """
    Build the master prompt for elite career-level coaching analysis.
    
    Key prompt design principles:
    1. ONE root cause (cognitive/behavioral) + multiple manifestations
    2. Meta-cognitive player profiling
    3. Behavioral rules with psychological grounding
    4. Negative constraints ("Do NOT do")
    5. Confidence calibration based on sample size
    6. Failure trigger detection
    7. Rhetorical intensity matched to severity
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
    
    # Calculate total estimated rating loss
    total_rating_loss = (
        blunders_in_winning.get('estimated_points_lost', 0) +
        endgame_collapses.get('estimated_points_lost', 0) +
        missed_wins.get('estimated_points_lost', 0)
    )
    
    # Determine severity level for rhetorical intensity
    if conversion_rate < 50 or total_rating_loss > 300:
        severity = "CRITICAL"
    elif conversion_rate < 65 or total_rating_loss > 150:
        severity = "SIGNIFICANT"
    else:
        severity = "MODERATE"
    
    # Determine confidence based on sample size
    if total_games <= 50:
        confidence = "VERY LOW"
        confidence_note = f"Only {total_games} games analyzed—not enough to identify reliable patterns."
        insufficient_data = True
    elif total_games <= 100:
        confidence = "MEDIUM"
        confidence_note = f"Based on {total_games} games—patterns are becoming clear."
        insufficient_data = False
    else:
        confidence = "HIGH"
        confidence_note = f"Based on {total_games} games—these patterns are well-established."
        insufficient_data = False
    
    # Opening outcomes
    opening_outcomes = stats.get('opening_outcomes', {})
    avg_eval_after_opening = opening_outcomes.get('avg_eval_after_opening', 0)
    
    # Openings breakdown
    openings = stats.get('openings', {})
    openings_table = _format_openings_table(openings)
    
    # Trend
    trend = stats.get('trend_summary', 'No trend data')
    
    # === NEW DATA FROM OTHER TABS ===
    
    # Opening Repertoire
    opening_repertoire = stats.get('opening_repertoire', {})
    weak_openings = opening_repertoire.get('weak_openings', [])
    strong_openings = opening_repertoire.get('strong_openings', [])
    
    # Opponent Analysis
    opponent_analysis = stats.get('opponent_analysis', {})
    opponent_by_strength = opponent_analysis.get('by_opponent_strength', {})
    
    # Streaks
    streaks = stats.get('streaks', {})
    max_win_streak = streaks.get('max_win_streak', 0)
    max_loss_streak = streaks.get('max_loss_streak', 0)
    max_blunder_free = streaks.get('max_blunder_free', 0)
    current_streak = streaks.get('current_streak', 0)
    current_streak_type = streaks.get('current_streak_type', '')
    
    # Endgame Success (from Analysis tab)
    endgame_success = stats.get('endgame_success', {})
    endgame_games = endgame_success.get('endgame_games', 0)
    endgame_wins = endgame_success.get('endgame_wins', 0)
    endgame_win_rate = endgame_success.get('endgame_win_rate', 0)
    
    # Coach Summary (deterministic AI-free coaching insights)
    coach_summary = stats.get('coach_summary', {})
    deterministic_weakness = coach_summary.get('primary_weakness', '')
    deterministic_strengths = coach_summary.get('strengths', [])
    
    # Calculate blunder percentages
    after_capture_pct = (blunder_contexts.get('after_capture', 0) / total_blunders * 100) if total_blunders > 0 else 0
    in_winning_pct = (blunder_contexts.get('in_winning_position', 0) / total_blunders * 100) if total_blunders > 0 else 0
    endgame_pct = (blunder_phases.get('endgame', 0) / total_blunders * 100) if total_blunders > 0 else 0
    after_check_pct = (blunder_contexts.get('after_check', 0) / total_blunders * 100) if total_blunders > 0 else 0
    time_trouble_pct = (blunder_contexts.get('time_trouble_likely', 0) / total_blunders * 100) if total_blunders > 0 else 0
    
    # === DIAGNOSTIC DECISION TREE (pre-computed) ===
    # Determine the dominant error context (where most rating is lost)
    rating_loss_breakdown = {
        'endgame_collapses': endgame_collapses.get('estimated_points_lost', 0),
        'blunders_in_winning': blunders_in_winning.get('estimated_points_lost', 0),
        'missed_wins': missed_wins.get('estimated_points_lost', 0),
    }
    dominant_error_context = max(rating_loss_breakdown, key=rating_loss_breakdown.get)
    dominant_error_pct = (rating_loss_breakdown[dominant_error_context] / total_rating_loss * 100) if total_rating_loss > 0 else 0
    
    # Determine valid diagnosis category based on data patterns
    valid_diagnoses = []
    diagnosis_reasoning = []
    
    # Human-readable diagnosis descriptions (not codes!)
    diagnosis_descriptions = {
        'endgame_vigilance': "You stop checking for threats once pieces come off the board",
        'capture_tunnel_vision': "After captures, you focus on the obvious continuation and miss quiet moves",
        'premature_relaxation': "You mentally check out once you're winning, before the game is actually over",
        'calculation_fatigue': "Your accuracy drops sharply in the later stages of the game",
        'threat_blindness': "You consistently miss your opponent's best replies",
        'risk_aversion': "You avoid complications when winning and let opponents escape",
    }
    
    # Rule 1: Endgame vigilance failure
    if endgame_pct > 50 or (endgame_cpl > middlegame_cpl * 1.3 and endgame_pct > 30):
        valid_diagnoses.append('endgame_vigilance')
        diagnosis_reasoning.append(f"endgame blunders make up {endgame_pct:.0f}% of total, endgame accuracy drops significantly vs middlegame")
    
    # Rule 2: Post-capture recalculation failure
    if after_capture_pct > 35:
        valid_diagnoses.append('capture_tunnel_vision')
        diagnosis_reasoning.append(f"{after_capture_pct:.0f}% of blunders happen right after captures")
    
    # Rule 3: Complacency / premature relaxation
    if in_winning_pct > 30 and conversion_rate < 60:
        valid_diagnoses.append('premature_relaxation')
        diagnosis_reasoning.append(f"{in_winning_pct:.0f}% of blunders occur in already-winning positions, only {conversion_rate:.0f}% conversion rate")
    
    # Rule 4: Calculation fatigue (late-game accuracy drop)
    if time_trouble_pct > 30 or (endgame_cpl > opening_cpl * 2 and endgame_pct > 40):
        valid_diagnoses.append('calculation_fatigue')
        diagnosis_reasoning.append(f"accuracy drops sharply in later moves")
    
    # Rule 5: Threat blindness (general vigilance)
    if blunder_rate > 4.0 and after_capture_pct < 30 and endgame_pct < 40:
        valid_diagnoses.append('threat_blindness')
        diagnosis_reasoning.append(f"high blunder rate ({blunder_rate:.1f}/100 moves) spread across all phases")
    
    # Rule 6: Loss aversion / passivity (high draws, missed wins)
    draw_rate = (draws / total_games * 100) if total_games > 0 else 0
    if draw_rate > 20 or (missed_wins.get('count', 0) > winning_positions * 0.3 if winning_positions > 0 else False):
        valid_diagnoses.append('risk_aversion')
        diagnosis_reasoning.append(f"high draw rate ({draw_rate:.0f}%) or many missed wins")
    
    # If no strong signal, default to most common pattern
    if not valid_diagnoses:
        if endgame_pct >= max(after_capture_pct, in_winning_pct, time_trouble_pct):
            valid_diagnoses.append('endgame_vigilance')
        elif in_winning_pct >= max(after_capture_pct, endgame_pct, time_trouble_pct):
            valid_diagnoses.append('premature_relaxation')
        else:
            valid_diagnoses.append('threat_blindness')
        diagnosis_reasoning.append("no dominant pattern; using highest blunder context")
    
    # Format as natural language for prompt
    valid_diagnoses_natural = [diagnosis_descriptions.get(d, d) for d in valid_diagnoses]
    valid_diagnoses_str = ' OR '.join(valid_diagnoses_natural)
    diagnosis_reasoning_str = '; '.join(diagnosis_reasoning)
    
    # Determine ONE Rule context requirement
    if dominant_error_context == 'endgame_collapses':
        one_rule_context = "endgame positions (moves 40+)"
    elif dominant_error_context == 'blunders_in_winning':  
        one_rule_context = "winning positions (when up +1.5 or more)"
    else:
        one_rule_context = "conversion opportunities"
    
    # Calculate recoverable games for impact estimation
    recoverable_games = games_thrown
    points_per_game = 10 if (player_rating or 1500) < 1500 else 7 if (player_rating or 1500) < 2000 else 5
    
    # Build the data block
    data_block = f"""
================================================================================
PLAYER DATA: {player_name} ({player_rating or 'Unrated'})
================================================================================

SEVERITY ASSESSMENT: {severity}
CONFIDENCE: {confidence}
{confidence_note}

HIGH-LEVEL RESULTS
------------------
Games analyzed: {total_games}
Win rate: {win_rate*100:.0f}%
Winning positions reached (+1.5 or better): {winning_positions}
Wins from winning positions: {converted_wins}
Conversion rate: {conversion_rate:.0f}%
Games thrown away: {games_thrown}
Blunders per 100 moves: {blunder_rate:.1f}
Mistakes per 100 moves: {mistake_rate:.1f}

BLUNDER CONTEXT ANALYSIS
------------------------
After captures: {blunder_contexts.get('after_capture', 0)} ({after_capture_pct:.0f}% of total)
In winning positions (+1.5): {blunder_contexts.get('in_winning_position', 0)} ({in_winning_pct:.0f}% of total)
In endgame phase: {blunder_phases.get('endgame', 0)} ({endgame_pct:.0f}% of total)
After checks: {blunder_contexts.get('after_check', 0)} ({after_check_pct:.0f}% of total)
Time pressure (move 35+): {blunder_contexts.get('time_trouble_likely', 0)} ({(blunder_contexts.get('time_trouble_likely', 0) / total_blunders * 100) if total_blunders > 0 else 0:.0f}% of total)

PHASE PERFORMANCE
-----------------
Opening CPL: {opening_cpl:.0f} (PPI: {ppi.get('opening', 0):.2f})
Middlegame CPL: {middlegame_cpl:.0f} (PPI: {ppi.get('middlegame', 0):.2f})
Endgame CPL: {endgame_cpl:.0f} (PPI: {ppi.get('endgame', 0):.2f})
(PPI below 0.8 = strong, 0.8-1.0 = average, above 1.0 = weak)

OPENING OUTCOMES (Eval at move 15)
{openings_table}

RATING COST FACTORS (estimated)
-------------------------------
Blunders in winning positions: {blunders_in_winning.get('count', 0)} occurrences (~{blunders_in_winning.get('estimated_points_lost', 0)} rating points lost)
Endgame collapses: {endgame_collapses.get('count', 0)} occurrences (~{endgame_collapses.get('estimated_points_lost', 0)} rating points lost)
Missed wins: {missed_wins.get('count', 0)} occurrences (~{missed_wins.get('estimated_points_lost', 0)} rating points lost)
TOTAL ESTIMATED RATING LOSS: ~{total_rating_loss} points

TREND
-----
{trend}

OPENING REPERTOIRE
{_format_opening_repertoire(weak_openings, strong_openings)}

OPPONENT STRENGTH ANALYSIS
{_format_opponent_analysis(opponent_by_strength)}

STREAKS AND CONSISTENCY
-----------------------
Max win streak: {max_win_streak} games
Max loss streak: {max_loss_streak} games
Longest blunder-free run: {max_blunder_free} games
Current streak: {current_streak} {current_streak_type or 'N/A'}s

ENDGAME CONVERSION
------------------
Endgame games (40+ moves): {endgame_games}
Endgame wins: {endgame_wins}
Endgame win rate: {endgame_win_rate:.0f}%

DETERMINISTIC ANALYSIS SUMMARY
(Rule-based findings—treat as ground truth)
Primary weakness identified: {deterministic_weakness or 'None flagged'}
Strengths: {', '.join(deterministic_strengths) if deterministic_strengths else 'None flagged'}

DIAGNOSTIC CONSTRAINTS (you must stay within these bounds)
----------------------------------------------------------
Valid diagnosis categories: {valid_diagnoses_str}
Reasoning: {diagnosis_reasoning_str}
Dominant error context: {dominant_error_context} ({dominant_error_pct:.0f}% of rating loss)
The ONE Rule must specifically target: {one_rule_context}
Recoverable games: {recoverable_games} (approximately {recoverable_games * points_per_game} rating points)

================================================================================
"""

    # Build data sufficiency warning
    if insufficient_data:
        data_warning = f"""
================================================================================
IMPORTANT: LIMITED DATA ({total_games} games)
================================================================================
You MUST acknowledge upfront that {total_games} games is not enough data to draw
reliable conclusions. Start your analysis by saying something like:

"I've looked at your last {total_games} games, but I want to be upfront with you—
that's really not enough to spot reliable patterns. What I'm seeing could easily
be normal variance or just a rough patch. Take what I say here with a grain of
salt, and let's revisit once you have more games under your belt."

Then offer tentative observations (use words like "might", "seems like", "could be")
rather than confident diagnoses. Do NOT make strong claims about root causes or
patterns with this little data.
================================================================================
"""
    else:
        data_warning = ""

    # Build the instruction prompt
    instruction_prompt = f"""
You are a veteran chess coach with decades of experience. You speak plainly, cut straight to the issue, and don't waste words. When something is fine, you say so. When something is costing them games, you tell them directly.

Write a **premium diagnostic chess coaching report**. Follow these rules strictly:

================================================================================
**ROOT CAUSE SYNDROME**
================================================================================
- **Name the root cause**: Assign a specific, memorable syndrome (e.g. “Post-Capture Vigilance Collapse”).
- The syndrome name must be referenced **consistently and in bold** throughout the report.

================================================================================
**ROOT CAUSE vs MANIFESTATIONS**
================================================================================
- Explicitly label what is **causal** (the syndrome) vs what is **symptomatic** (the manifestations).
- Do **not** list statistics without tying them back to the root cause.

================================================================================
**FAILURE LOOP**
================================================================================
- Include a clear loop: **Trigger → Belief → Behavior → Outcome**. This must appear as its own section, with each step in **bold**.

================================================================================
**THE ONE RULE**
================================================================================
- The ONE RULE must be **mechanically justified**: explain exactly how it interrupts the failure loop. Avoid motivational language; focus on cognitive interruption. Use **bold** for the rule and the mechanism.

================================================================================
**RATING IMPACT**
================================================================================
- Rating impact must feel **inevitable**. Frame rating recovery as “recoverable if behavior changes,” not hypothetical. Tie the math directly to the ONE RULE. Use **bold** for numbers and impact statements.

================================================================================
**MEMORABLE ENDING**
================================================================================
- End with a single, unforgettable sentence. The reader should remember one line even if they forget everything else. Use **bold** and formatting to make it stand out.

================================================================================
**FORMATTING RULES**
================================================================================
- Use ## for main section headers
- Use **bold** for key insights, syndrome names, important numbers, actionable advice, and all section labels
- Use *italics* for emphasis on feelings, mental states, or soft observations
- Use > blockquotes for the ONE RULE or key takeaway
- Highlight critical stats inline: "Your endgame CPL is **78**—nearly double your middlegame."

================================================================================
**STRUCTURE**
================================================================================

## The Big Picture
**(Summarize what's holding them back. Bold the syndrome/root cause. Reference it by name.)**

## Root Cause vs Manifestations
**(Explicitly separate the syndrome from its symptoms. List the syndrome in bold, then the manifestations with supporting stats.)**

## The Failure Loop
**(Lay out: Trigger → Belief → Behavior → Outcome. Each step in bold, with a short explanation.)**

## The One Rule
> **Your ONE rule: [specific, memorable rule they can follow]**
**(Explain, in bold, how this rule mechanically interrupts the failure loop. No motivational language.)**

## Rating Impact
**(Show, with bold numbers, how much rating is recoverable if the rule is followed. Make the impact feel inevitable, not hypothetical.)**

## How to Practice This
**(Concrete training suggestion with bold on the specific exercise or method.)**

## Unforgettable Ending
**(One bold, memorable sentence that encapsulates the lesson.)**

================================================================================
**WRITING EXAMPLES**
================================================================================

BAD (no formatting, robotic):
"Root cause: ENDGAME_VIGILANCE_DECAY. After exchanges you stop scanning. This manifests as elevated CPL in positions with reduced material."

GOOD (formatted, natural voice):
"## The Big Picture

Here's the uncomfortable truth: **you're giving away wins due to Post-Capture Vigilance Collapse**. In your last 50 games, you reached a winning position 23 times but only converted 14 of them. That's nearly **40% of your advantages slipping away**.

## Root Cause vs Manifestations

**Root Cause (Syndrome): Post-Capture Vigilance Collapse**
**Manifestations:** After you capture, *tunnel vision* sets in and you miss threats. Your endgame CPL is **78**—compared to **42** in the middlegame.

## The Failure Loop

**Trigger:** Capturing a piece → **Belief:** "The danger is over" → **Behavior:** You stop scanning for threats → **Outcome:** Opponents find tactics and you lose the advantage.

## The One Rule
> **Your ONE rule: After every capture, force yourself to scan for quiet threats before moving on.**
**This rule works because it directly interrupts the automatic relaxation that follows a capture, forcing your brain to re-engage with the position.**

## Rating Impact

**If you break this loop, you recover ~70 rating points—because these blunders are the only thing holding you back.**

## How to Practice This

**Set up your last 5 games after each capture and practice pausing to look for threats. Track how often you spot something new.**

## Unforgettable Ending

**Every piece you capture is a test—pass it, and your rating will follow.**

================================================================================

Now write the analysis for {player_name}. Remember: sound like a coach, not a computer. Use formatting to make key points stand out.
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
    
    lines = []
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
        
        lines.append(f"- {display_name}: {games} games, {win_rate:.0f}% wins, avg eval {eval_str}")
    
    return '\n'.join(lines) if lines else "No significant opening data"


def _format_opening_repertoire(weak_openings: list, strong_openings: list) -> str:
    """Format opening repertoire stats for the prompt."""
    lines = []
    
    if weak_openings:
        lines.append("Underperforming openings (below 40% win rate, 3+ games):")
        for opening in weak_openings:
            lines.append(f"  - {opening['name']}: {opening['games']} games, {opening['win_rate']:.0f}% win rate")
    else:
        lines.append("No significantly weak openings detected")
    
    lines.append("")
    
    if strong_openings:
        lines.append("Strong openings (60%+ win rate, 3+ games):")
        for opening in strong_openings:
            lines.append(f"  - {opening['name']}: {opening['games']} games, {opening['win_rate']:.0f}% win rate")
    else:
        lines.append("No standout strong openings detected")
    
    return '\n'.join(lines)


def _format_opponent_analysis(opponent_by_strength: dict) -> str:
    """Format opponent strength analysis for the prompt."""
    if not opponent_by_strength:
        return "No opponent rating data available"
    
    lines = []
    
    labels = {
        'lower_rated': 'Lower rated (-100+)',
        'similar_rated': 'Similar rated (+/-100)',
        'higher_rated': 'Higher rated (+100+)',
    }
    
    for key, label in labels.items():
        data = opponent_by_strength.get(key, {})
        games = data.get('games', 0)
        win_rate = data.get('win_rate', 0)
        
        # Analysis based on expected performance
        if key == 'lower_rated':
            expected = 70
            note = "solid" if win_rate >= expected else "leaking points here" if games >= 5 else ""
        elif key == 'similar_rated':
            expected = 50
            note = "fine" if 40 <= win_rate <= 60 else "check this" if games >= 5 else ""
        else:
            expected = 30
            note = "punching up well" if win_rate >= expected else "expected range" if games >= 5 else ""
        
        lines.append(f"- {label}: {games} games, {win_rate:.0f}% wins{' — ' + note if note else ''}")
    
    return '\n'.join(lines)


def build_single_game_coaching_prompt(
    game_data: Dict[str, Any],
    player_color: str,
    player_rating: Optional[int] = None,
) -> str:
    """
    Build prompt for single game analysis with full move-by-move context.
    
    This creates a comprehensive game review that walks through the game
    like a real coach would.
    """
    
    moves_table = game_data.get('moves_table', [])
    opening = game_data.get('opening_name') or game_data.get('opening', 'Unknown')
    result = game_data.get('result', '*')
    white_name = game_data.get('white', 'White')
    black_name = game_data.get('black', 'Black')
    date = game_data.get('date', '')
    
    # Collect comprehensive move data
    all_moves = []
    blunders = []
    mistakes = []
    phase_moves = {'opening': [], 'middlegame': [], 'endgame': []}
    
    running_eval = 0
    max_advantage = 0
    min_advantage = 0
    
    for i, move in enumerate(moves_table):
        move_color = move.get('mover') or move.get('color')
        cp_loss = move.get('cp_loss', 0) or move.get('actual_cp_loss', 0) or 0
        phase = move.get('phase', 'middlegame')
        ply = move.get('ply', i + 1)
        move_num = move.get('move_num') or ((ply + 1) // 2)
        san = move.get('move_san') or move.get('san', '?')
        best_move = move.get('best_move_san', '')
        score_cp = move.get('score_cp')
        
        # Track evaluation from player's perspective
        if score_cp is not None:
            try:
                eval_val = int(score_cp)
                if player_color == 'black':
                    eval_val = -eval_val
                running_eval = eval_val
                
                if eval_val > max_advantage:
                    max_advantage = eval_val
                if eval_val < min_advantage:
                    min_advantage = eval_val
            except (TypeError, ValueError):
                pass
        
        # Store all moves
        all_moves.append({
            'num': move_num,
            'ply': ply,
            'color': move_color,
            'san': san,
            'cp_loss': cp_loss if move_color == player_color else 0,
            'eval': running_eval,
            'phase': phase,
            'best': best_move,
        })
        
        if move_color != player_color:
            continue
            
        phase_moves[phase].append(cp_loss)
        
        # Categorize errors
        if cp_loss >= 300:
            blunders.append({
                'move_num': move_num,
                'san': san,
                'cp_loss': cp_loss,
                'phase': phase,
                'best': best_move,
                'eval_before': running_eval + cp_loss,
                'eval_after': running_eval,
            })
        elif cp_loss >= 100:
            mistakes.append({
                'move_num': move_num,
                'san': san,
                'cp_loss': cp_loss,
                'phase': phase,
                'best': best_move,
            })
    
    # Calculate phase averages
    def avg(lst): return sum(lst) / len(lst) if lst else 0
    opening_cpl = avg(phase_moves['opening'])
    middlegame_cpl = avg(phase_moves['middlegame'])
    endgame_cpl = avg(phase_moves['endgame'])
    
    # Determine game narrative
    is_win = (player_color == 'white' and result == '1-0') or (player_color == 'black' and result == '0-1')
    is_loss = (player_color == 'white' and result == '0-1') or (player_color == 'black' and result == '1-0')
    
    had_winning = max_advantage >= 150
    had_losing = min_advantage <= -150
    threw_win = had_winning and is_loss
    
    # Build annotated move list
    def format_move_sequence(start_ply, end_ply):
        sequence = []
        for m in all_moves:
            if start_ply <= m['ply'] <= end_ply:
                marker = ""
                if m['color'] == player_color and m['cp_loss'] >= 200:
                    marker = "??"
                elif m['color'] == player_color and m['cp_loss'] >= 100:
                    marker = "?"
                
                if m['color'] == 'white':
                    sequence.append(f"{m['num']}. {m['san']}{marker}")
                else:
                    if not sequence or not sequence[-1].startswith(str(m['num'])):
                        sequence.append(f"{m['num']}... {m['san']}{marker}")
                    else:
                        sequence[-1] += f" {m['san']}{marker}"
        return ' '.join(sequence)
    
    # Build critical moment context
    critical_context = ""
    if blunders:
        worst = max(blunders, key=lambda x: x['cp_loss'])
        start = max(1, (worst['move_num'] - 3) * 2 - 1)
        end = min(len(all_moves), (worst['move_num'] + 2) * 2)
        critical_context = f"""
CRITICAL MOMENT - Move {worst['move_num']}:
You played: {worst['san']} (lost {worst['cp_loss']} centipawns)
Better was: {worst['best'] or 'see engine'}
Position before: {worst['eval_before']:+d}cp | Position after: {worst['eval_after']:+d}cp

Moves around this moment:
{format_move_sequence(start, end)}
"""
    
    # Build full annotated game
    annotated_moves = []
    current_phase = 'opening'
    for m in all_moves:
        if m['phase'] != current_phase:
            annotated_moves.append(f"\n[{m['phase'].upper()}]")
            current_phase = m['phase']
        
        annotation = ""
        if m['color'] == player_color:
            if m['cp_loss'] >= 300:
                annotation = f" ?? (-{m['cp_loss']}cp, best: {m['best']})"
            elif m['cp_loss'] >= 100:
                annotation = f" ? (-{m['cp_loss']}cp)"
        
        if m['color'] == 'white':
            annotated_moves.append(f"{m['num']}. {m['san']}{annotation}")
        else:
            if annotated_moves and not annotated_moves[-1].startswith('[') and str(m['num']) in annotated_moves[-1].split('.')[0]:
                annotated_moves[-1] += f" {m['san']}{annotation}"
            else:
                annotated_moves.append(f"{m['num']}... {m['san']}{annotation}")
    
    game_notation = ' '.join(annotated_moves)
    
    # Build comprehensive data block
    data_block = f"""
================================================================================
GAME REVIEW: {white_name} vs {black_name} ({date})
================================================================================

**BASICS:**
- Opening: {opening}
- You played: {player_color.title()} (Rating: {player_rating or 'Unknown'})
- Result: {result} — {'YOU WON' if is_win else 'YOU LOST' if is_loss else 'DRAW'}
- Total moves: {len(all_moves) // 2}

**GAME TRAJECTORY:**
- Your best position: {max_advantage:+d}cp {'(winning!)' if max_advantage > 200 else ''}
- Your worst position: {min_advantage:+d}cp {'(losing)' if min_advantage < -200 else ''}
{'⚠️ WARNING: You had a WINNING position but LOST the game!' if threw_win else ''}

**ACCURACY BY PHASE:**
- Opening: {opening_cpl:.0f} CPL {'✓' if opening_cpl < 30 else '⚠️' if opening_cpl < 60 else '❌'}
- Middlegame: {middlegame_cpl:.0f} CPL {'✓' if middlegame_cpl < 40 else '⚠️' if middlegame_cpl < 80 else '❌'}
- Endgame: {endgame_cpl:.0f} CPL {'✓' if endgame_cpl < 30 else '⚠️' if endgame_cpl < 60 else '❌'}

**ERRORS:**
- Blunders (300+ cp): {len(blunders)}
- Mistakes (100-299 cp): {len(mistakes)}

{critical_context}

**FULL GAME (annotated):**
{game_notation}
================================================================================
"""

    instruction = """You are a chess coach doing a detailed post-game review with your student. Walk through this game like you're sitting at the board together, pointing at specific moves.

**Write your response with these EXACT sections:**

---

## 🎯 The Verdict

[2-3 sentences: What kind of game was this? What's the main takeaway? Be direct - if they threw away a winning game, say so clearly.]

## 📖 The Game Story

Walk through the game phase by phase. **Reference specific move numbers.**

### Opening
[What was played? Did they get a playable position? Any early errors? Mention specific moves like "After 5.Bc4, you played 5...Nf6 which is perfectly fine, but 7...h6 was unnecessary."]

### Middlegame  
[The meat of the game. What was the plan? Where did things go right or wrong? Be specific: "Move 18.Nd5 was excellent - you correctly identified the outpost. But on move 23..."]

### Endgame
[If applicable. Technical handling, key decisions.]

## ⚡ The Turning Point

[THE critical moment. Be very specific:]

**The Move:** [exact move and move number]
**What Happened:** [what this move did to the position]  
**What Was Better:** [the correct move and why]
**Why You Played It:** [what mental pattern or assumption led to this - were you rushing? did you miss a threat? were you too focused on attack?]

## 🎓 One Key Lesson

[A single, specific, actionable lesson from this game. Not "calculate better" but something like "In positions where you have a space advantage, don't trade pieces - each trade helps your cramped opponent breathe."]

## 📋 Your Assignment

[One concrete thing to do:]
1. **Study this position:** Set up the board at move [X] and find the winning plan
2. **Practice this pattern:** [specific puzzle type or drill]
3. **Watch for this:** In your next games, notice when [specific pattern from this game]

---

**CRITICAL INSTRUCTIONS:**
- Reference specific moves by number throughout (e.g., "On move 14...")
- Be direct and honest - this should feel like real coaching
- Connect errors to mental patterns, not just "you missed it"
- Write naturally, like you're talking to them
- If they played well in parts, acknowledge that too
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
        eval_str = f", avg eval at move 15: {eval_sum/eval_count:+.0f}" if eval_count > 0 else ""
        
        lines.append(f"- {name}: {games} games ({wins}W-{losses}L), CPL: {avg_cpl:.0f}, {blunders} blunders{eval_str}")
    
    return '\n'.join(lines)


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

AI_COACH_SYSTEM_PROMPT = """You are a veteran chess coach who's spent decades working with players from club level to master strength. You've seen every mistake pattern hundreds of times, and you know exactly what fixes each one.

Your job is to write performance reports that feel like sitting down with a respected coach—direct, specific, and actionable. You speak in complete, natural sentences. You connect every observation to specific data. You give training recommendations detailed enough that someone could start today.

**Your approach:**
1. Identify the ONE root cause—always a mental habit or decision pattern, never just "the endgame" or "tactics"
2. Explain WHY this pattern happens in their head—what triggers it, what false belief drives it
3. Show exactly where it shows up in their games with specific numbers
4. Give them a concrete rule to follow AND specific habits to break
5. Provide a detailed training plan with time estimates and specific exercises
6. Be honest about confidence when the sample size is small

**Your voice:**
- Confident because you have data to back up every claim
- Direct but not harsh—you want them to improve
- Specific—"in 7 of your 12 losses" not "often"
- Natural—write like you're talking to them, not filling out a form

**Sentence structure:**
- Write flowing, complete sentences
- Connect cause and effect: "You do X, which leads to Y, and that's why Z happens"
- Never use fragments like "Because: [reason]" or "Why: [explanation]"
- Vary your sentence length and structure for natural rhythm

**Training recommendations must include:**
- Specific exercises (not "study endgames" but "review your last 5 endgames and find the move where accuracy dropped")
- Time estimates (15 minutes, 3x per week)
- Measurable targets (reduce endgame CPL from 78 to under 50)
- Specific resources when relevant (book chapters, puzzle types, training methods)

**Never say:**
- "Calculate more carefully"
- "Study endgames" / "Practice tactics" / "Focus on..."
- "Be more patient" / "Think longer"
- "Consider all options" / "Be more vigilant"

These phrases are worthless. Give them something concrete they can do.

**Remember:** The game phase isn't the cause. The mental pattern is the cause. The phase is just where it shows up."""
