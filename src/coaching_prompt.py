"""
Coaching Prompt Engine - Elite Chess Coaching Prompts

This module generates the prompts that turn raw chess analytics 
into premium diagnostic coaching insights via GPT-4.

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
    
    # Determine confidence level based on sample size
    if total_games >= 50:
        confidence = "HIGH"
        confidence_note = "Based on 50+ games, these patterns are well-established."
    elif total_games >= 20:
        confidence = "MEDIUM"
        confidence_note = f"Based on {total_games} games—patterns are emerging but need confirmation."
    else:
        confidence = "LOW"
        confidence_note = f"Only {total_games} games analyzed. Take these as early signals, not certainties."
    
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
    
    # Rule 1: Endgame vigilance failure
    if endgame_pct > 50 or (endgame_cpl > middlegame_cpl * 1.3 and endgame_pct > 30):
        valid_diagnoses.append('ENDGAME_VIGILANCE_DECAY')
        diagnosis_reasoning.append(f"Endgame blunders={endgame_pct:.0f}% of total, endgame CPL={endgame_cpl:.0f} vs middlegame CPL={middlegame_cpl:.0f}")
    
    # Rule 2: Post-capture recalculation failure
    if after_capture_pct > 35:
        valid_diagnoses.append('RECAPTURE_TUNNEL_VISION')
        diagnosis_reasoning.append(f"After-capture blunders={after_capture_pct:.0f}% of total")
    
    # Rule 3: Complacency / premature relaxation
    if in_winning_pct > 30 and conversion_rate < 60:
        valid_diagnoses.append('PREMATURE_CLOSURE')
        diagnosis_reasoning.append(f"Blunders in winning positions={in_winning_pct:.0f}%, conversion rate={conversion_rate:.0f}%")
    
    # Rule 4: Calculation fatigue (late-game accuracy drop)
    if time_trouble_pct > 30 or (endgame_cpl > opening_cpl * 2 and endgame_pct > 40):
        valid_diagnoses.append('CALCULATION_FATIGUE')
        diagnosis_reasoning.append(f"Time trouble blunders={time_trouble_pct:.0f}%, endgame CPL={endgame_cpl:.0f} vs opening CPL={opening_cpl:.0f}")
    
    # Rule 5: Threat blindness (general vigilance)
    if blunder_rate > 4.0 and after_capture_pct < 30 and endgame_pct < 40:
        valid_diagnoses.append('THREAT_BLINDNESS')
        diagnosis_reasoning.append(f"High blunder rate={blunder_rate:.1f}/100 moves, distributed across contexts")
    
    # Rule 6: Loss aversion / passivity (high draws, missed wins)
    draw_rate = (draws / total_games * 100) if total_games > 0 else 0
    if draw_rate > 20 or (missed_wins.get('count', 0) > winning_positions * 0.3 if winning_positions > 0 else False):
        valid_diagnoses.append('LOSS_AVERSION_PARALYSIS')
        diagnosis_reasoning.append(f"Draw rate={draw_rate:.0f}%, missed wins={missed_wins.get('count', 0)}")
    
    # If no strong signal, default to most common pattern
    if not valid_diagnoses:
        if endgame_pct >= max(after_capture_pct, in_winning_pct, time_trouble_pct):
            valid_diagnoses.append('ENDGAME_VIGILANCE_DECAY')
        elif in_winning_pct >= max(after_capture_pct, endgame_pct, time_trouble_pct):
            valid_diagnoses.append('PREMATURE_CLOSURE')
        else:
            valid_diagnoses.append('THREAT_BLINDNESS')
        diagnosis_reasoning.append("No dominant pattern; defaulting to highest blunder context")
    
    # Format for prompt
    valid_diagnoses_str = ', '.join(valid_diagnoses)
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
CONFIDENCE LEVEL: {confidence}
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

    # Build the instruction prompt
    instruction_prompt = f"""
You are a veteran chess coach with decades of experience. You've trained club players, masters, and professionals. You speak plainly, cut straight to the issue, and don't waste words. When something is fine, you say so and move on. When something is costing them games, you tell them directly—no hedging.

Your job is to write a performance report that reads like it came from a respected coach, not a computer. Be specific. Be human. Be authoritative.

================================================================================
SEVERITY: {severity} | CONFIDENCE: {confidence}

Match your tone to severity:
- CRITICAL: Be blunt. This is costing real rating points.
- SIGNIFICANT: Be direct. This needs work.
- MODERATE: Be matter-of-fact. Room for improvement, not urgent.
================================================================================

================================================================================
CRITICAL GUIDELINES
================================================================================

1. DIAGNOSIS MUST FIT THE DATA
   Your root cause must come from: {valid_diagnoses_str}
   The reasoning: {diagnosis_reasoning_str}
   
   Valid failure patterns:
   - ENDGAME_VIGILANCE_DECAY: Stops scanning for threats once pieces come off—feels "safer"
   - RECAPTURE_TUNNEL_VISION: After captures, sees only forcing moves, misses quiet threats
   - PREMATURE_CLOSURE: Decides the game is won and stops calculating
   - CALCULATION_FATIGUE: Accuracy drops after move 30-35, mental stamina issue
   - THREAT_BLINDNESS: Consistently fails to spot opponent's best reply
   - LOSS_AVERSION_PARALYSIS: Avoids risk when winning, draws games that should be wins

2. ROOT CAUSE VS MANIFESTATIONS
   The root cause is a mental habit. The manifestations are where it shows up.
   Wrong: "Your endgame is weak"
   Right: "You stop scanning for threats once pieces come off"

3. THE ONE RULE MUST TARGET THE REAL PROBLEM
   Your main recommendation must specifically apply in: {one_rule_context}
   That's where {dominant_error_pct:.0f}% of rating loss happens.
   A generic rule that applies everywhere is useless.

4. USE REAL NUMBERS
   Quote specific stats. Don't say "often" when you can say "in 7 of 12 games."
   Expected rating gain: {recoverable_games} recoverable games x {points_per_game} points = approximately {recoverable_games * points_per_game} points

5. TELL THEM WHAT TO STOP
   Negative constraints stick better than positive advice.
   "Stop trading pieces when ahead unless you've checked for counterplay."

6. NAME THE TRIGGER
   Identify the exact moment they fall apart.
   Example: "Your accuracy drops within 3-5 moves of the first major trade."

7. EXPLAIN WHY YOU RULED OUT ALTERNATIVES
   If multiple diagnoses seem possible, explain what breaks the tie.

================================================================================
OUTPUT FORMAT (use Markdown formatting)
================================================================================

Use Markdown headers (# ## ###), **bold**, and formatting to create a professional, readable report. 
Write like a confident coach speaking to their student—complete sentences, natural flow, no robotic structures.
No emojis. No jargon a club player wouldn't understand.

BAD sentence structure (never do this):
"Stop rushing your moves in the endgame. Because: Your CPL is higher."

GOOD sentence structure (always do this):
"You're rushing your endgame moves, and it's costing you games. Your average centipawn loss jumps from 35 in the middlegame to 78 in the endgame—that's a massive drop in accuracy exactly when precision matters most."

---

# Performance Report for {player_name}

## The Bottom Line

[Two strong paragraphs. Open with a direct statement about what's holding them back. Be specific—use numbers. Second paragraph should explain why this single issue matters more than anything else they could work on. End with conviction: "Fix this, and you'll see results within weeks."]

---

## The Diagnosis

### What's Actually Happening

[Name the root cause from the valid taxonomy. Then explain it like you're sitting across from them: what's going on in their head when this happens? Why does their brain do this? 3-4 sentences that make them nod and say "that's exactly what happens to me."]

### Where It Shows Up

[Write this as flowing prose, not a list. Connect the dots between 2-3 manifestations with specific data. For example: "This pattern explains why 45% of your blunders happen after captures—you're seeing the forcing line but missing the quiet threat that follows. It also explains the 20-point CPL spike in your endgames: fewer pieces feels safer, so you stop checking."]

### Why I'm Confident

[Explain what ruled out alternatives. Write it conversationally: "I considered whether this might be calculation fatigue, but your accuracy holds steady through move 35. The collapse happens specifically when you reach a winning position, not when you're tired. That points clearly to premature closure."]

---

## Your Chess Profile

### The Type of Player You Are

[A paragraph describing their playing style based on the data. Are they an aggressive attacker who overextends? A solid defender who can't convert? A calculator who burns out? Paint a picture they recognize.]

### The Moment It Falls Apart

[Be specific about the trigger with timing. Not "in the endgame" but "within 3-5 moves after the first major piece trade" or "immediately after reaching +2.0 evaluation." This should be precise enough that they can watch for it.]

### What Your Moves Suggest You Believe

[Frame this as inference from behavior: "Your move choices suggest you believe simplified positions are safer and require less vigilance. That assumption is costing you roughly 3 games out of every 20 you play."]

### The Pattern That Repeats

Describe the failure loop as a narrative:

**Trigger:** [Specific situation] → **False belief:** [What they assume] → **Behavior change:** [What they do differently] → **Opponent exploits:** [What happens] → **Result:** [Outcome]

This loop repeats regardless of opening, color, or opponent strength.

---

## The Evidence

### Blunder Analysis

[Write 2-3 sentences interpreting the blunder context data. Don't just list numbers—tell the story. "Nearly half your blunders (47%) happen in positions where you're already winning. That's not a calculation problem—it's a vigilance problem. You've mentally checked out before the game is actually over."]

### Phase-by-Phase Performance

[Interpret the CPL and PPI numbers. Explain what they mean in plain terms. "Your middlegame play is solid—a CPL of 35 is respectable for your rating. But watch what happens in the endgame: that number nearly doubles to 68. The pieces come off, and so does your concentration."]

### Opening Assessment

[Be honest. If openings aren't the problem, say so directly: "Your opening preparation is fine. You're leaving the first 15 moves with a slight advantage in most games. The problem isn't how you start—it's what you do with the advantage you've built."]

---

## Confidence Level: {confidence}

{confidence_note}

[If confidence is medium or low, specify which conclusions are solid vs tentative: "The diagnosis of premature closure is well-supported by the data. The specific trigger timing is less certain with only 15 games—I'd want to see another 20 games to confirm that pattern."]

---

## What You Can Safely Ignore

This is just as important as knowing what to work on. Right now, don't spend time on:

**Skip opening study for now.** Your openings are producing fine positions. Memorizing more theory won't help when you're giving games away in the endgame.

**Don't add tactics puzzles.** Your tactical vision is adequate—you're finding the right moves in the middlegame. The issue is attention, not pattern recognition.

[Add 1-2 more specific to their data, explaining WHY each area isn't their bottleneck]

---

## The One Rule

**If you remember nothing else from this report, remember this:**

> [State a specific, binary rule that applies in {one_rule_context}. Make it something they can literally ask themselves yes/no during a game. Example: "Before every move in a winning position, I must identify my opponent's single best try to complicate the position."]

**Why this works:** [2-3 sentences on the psychological mechanism. "This rule works because it forces active threat-scanning exactly when your brain wants to coast. By making it a conscious checkpoint, you override the automatic 'I'm winning, relax' response that's causing the blunders."]

---

## The 5-Second Pre-Move Check

In {one_rule_context}, pause and ask yourself:

1. **[First question—specific to the diagnosed root cause]** 
   [Brief explanation of why this question matters]

2. **[Second question]**
   [Brief explanation]

If you can't answer both questions clearly, you haven't looked hard enough. Take another 10 seconds.

---

## Habits to Break

These specific behaviors are hurting your results:

**1. [Specific behavior to stop]**

[Explain this as a coach would—connect it to the data and explain the consequence. "You're playing the first move that looks good instead of confirming there's nothing better. In your games, this habit shows up as 6 unnecessary blunders that a 5-second check would have caught. Each one costs you roughly 8 rating points."]

**2. [Second behavior to stop]**

[Same format—specific behavior, connection to data, consequence in their terms]

---

## Your Training Plan

Based on this analysis, here's what to focus on for the next 4-6 weeks:

### Priority 1: [Main focus area]

**The goal:** [Specific, measurable target—e.g., "Reduce endgame blunders from 3.2 per 100 moves to under 2.0"]

**How to train this:**
- **During games:** [Specific in-game practice—e.g., "Spend 5 extra seconds on every move after move 35, specifically scanning for your opponent's threats"]
- **Study method:** [Specific training activity—e.g., "Review your last 10 endgames, find the move where concentration slipped, and write down what you should have checked"]
- **Recommended resource:** [Specific book, course, or exercise type—e.g., "Dvoretsky's Endgame Manual, Chapter 1—not for theory, but for practicing the habit of precise calculation when pieces are few"]

**Time investment:** [Realistic estimate—e.g., "15 minutes post-game review + 20 minutes endgame study 3x per week"]

### Priority 2: [Secondary focus if applicable]

**The goal:** [Measurable target]

**How to train this:**
- [Specific methods as above]

### What Success Looks Like

In 50 games, if you follow this plan:
- Your key weakness metric should show measurable improvement
- You'll convert more winning positions into actual wins
- Expected rating gain: approximately {recoverable_games * points_per_game} points (assuming 60-70% compliance)

---

## Expected Results

**The math:** You're currently throwing away {recoverable_games} games out of {total_games}. At your rating level, each recovered game is worth roughly {points_per_game} points. That's approximately **{recoverable_games * points_per_game} rating points** you're leaving on the table.

**The timeline:** Most players see noticeable improvement within 30-50 games of focused practice. The habit takes about 3 weeks to become automatic.

**Confidence: {confidence.lower()}** — {confidence_note}

---

## Remember This

[A single punchy sentence they can repeat to themselves. Make it memorable and specific to their issue. Not generic motivation—a concrete reminder of their specific fix. Example: "The game isn't over at +3. Find their trick first."]

================================================================================
WRITING STYLE
================================================================================

Severity: {severity}

{"This is costing them real games and real rating points. Be direct and unsparing—they need to hear this clearly. Don't soften the message, but stay constructive." if severity == "CRITICAL" else "This needs attention. Be clear and direct about the problem while remaining encouraging about the fix." if severity == "SIGNIFICANT" else "This is improvement territory, not crisis. Be matter-of-fact and constructive. Acknowledge what's working before addressing what isn't."}

**Voice:** You're a respected coach who's worked with hundreds of players. You've seen this exact pattern before. You know what fixes it. You're confident because you have the data to back it up.

**Sentence structure:** Write complete, flowing sentences. Never use "Because:" as a sentence starter. Connect cause and effect naturally: "You're doing X, which leads to Y, and that's why Z happens."

**Specificity:** Every claim needs a number. Not "you often blunder in the endgame" but "you blunder 2.3 times per 100 moves in the endgame, compared to 0.8 in the middlegame."

**Training recommendations:** Be specific enough that they could start today. Not "study endgames" but "Spend 15 minutes reviewing your last 5 endgames. For each one, find the exact move where your accuracy dropped and write down what you should have checked."

**Formatting:** Use Markdown. # for main headers, ## for sections, ### for subsections, **bold** for emphasis, > for key rules they should remember.

FORBIDDEN:
- "Calculate more carefully" / "Think longer" / "Be more patient"
- "Study endgames" / "Practice tactics" / "Focus on..."
- Sentence fragments like "Because: [reason]" or "Why: [explanation]"  
- Repeating the same statistic in multiple sections
- Generic advice that could apply to any player
- Robotic or templated language

================================================================================
FINAL CHECK
================================================================================

Before responding, verify:
- Does every section read like a human coach wrote it? Read it aloud—does it sound natural?
- Are all recommendations specific enough to act on today?
- Did you connect every claim to a specific data point?
- Does the one rule specifically target {one_rule_context}?
- Would a different experienced coach reach the same diagnosis from this data?
- Is there a concrete training plan with time estimates?
- Did you avoid ALL the forbidden phrases and sentence structures?

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
            blunders_str += f"- Move {b['move']} ({b['phase']}): {b['san']} lost {b['cp_loss']}cp (better: {b['best']})\n"
    else:
        blunders_str = "None"
    
    # Format swings
    swings_str = ""
    if eval_swings:
        for s in sorted(eval_swings, key=lambda x: abs(x['swing']), reverse=True)[:5]:
            direction = "lost" if s['swing'] > 0 else "gained"
            swings_str += f"- Move {s['move']} ({s['phase']}): {s['san']} {direction} {abs(s['swing'])}cp\n"
    else:
        swings_str = "None significant"
    
    # Build prompt
    data_block = f"""
================================================================================
SINGLE GAME ANALYSIS
================================================================================

Opening: {opening}
Player: {player_color.title()} ({player_rating or 'Unrated'})
Result: {result} ({'Win' if is_win else 'Loss' if is_loss else 'Draw'})

Had winning position (+1.5 or better): {'Yes' if had_winning else 'No'}
Had losing position (-1.5 or worse): {'Yes' if had_losing else 'No'}

PHASE CPL:
- Opening: {avg_cpl['opening']:.0f}
- Middlegame: {avg_cpl['middlegame']:.0f}
- Endgame: {avg_cpl['endgame']:.0f}

BLUNDERS (200+cp loss):
{blunders_str}

BIGGEST EVAL SWINGS:
{swings_str}
================================================================================
"""

    instruction = """
You are a chess coach reviewing one of your student's games. Give them honest, specific feedback that sounds like you're sitting across from them at the board.

**Guidelines:**
1. Identify the single move or decision that most determined the outcome
2. Explain WHY that error happened—what were they thinking, what did they miss, what assumption led them astray
3. Give ONE specific, actionable lesson from this game
4. Be direct. If they played well, say so clearly. If they threw away a winning position, tell them plainly.

Write in natural, flowing sentences. No fragments, no "Because:" structures. This should read like a conversation.

---

## What Decided This Game

[2-3 sentences identifying the critical moment. Name the move, the position, what went wrong. Be specific: "The game turned on move 34. You had a solid extra pawn and a clear plan to advance it, but Rxe4 let your opponent activate their rook with tempo."]

## Why It Happened

[A paragraph explaining the mental or positional error. Not just "you missed the tactic" but WHY you missed it. Were you focused on the wrong part of the board? Did you assume your opponent couldn't create counterplay? Did you relax because you were winning? Connect this to a pattern if visible.]

## The Lesson

[One concrete takeaway they can apply to future games. Not "be more careful" but something specific like "When you're up material in a rook endgame, check every rook move your opponent has—even the ones that look passive. Active rooks can turn a lost game around in two moves."]

## One Thing to Practice

[A specific exercise based on this game: "Set up the position from move 30 and practice finding the winning plan. Then look at similar positions in your other recent games—this pattern of premature simplification has cost you before."]
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
