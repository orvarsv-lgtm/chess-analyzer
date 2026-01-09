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
        confidence_note = "Sample size is robust (50+ games). Estimates are reliable."
    elif total_games >= 20:
        confidence = "MEDIUM"
        confidence_note = f"Sample size is adequate ({total_games} games). Estimates have moderate confidence."
    else:
        confidence = "LOW"
        confidence_note = f"Sample size is limited ({total_games} games). Treat estimates as directional, not precise."
    
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
    
    # Build the data block
    data_block = f"""
══════════════════════════════════════════════════════════════════════════════
PLAYER DATA: {player_name} ({player_rating or 'Unrated'})
══════════════════════════════════════════════════════════════════════════════

⚠️ SEVERITY ASSESSMENT: {severity}
📊 CONFIDENCE LEVEL: {confidence}
   {confidence_note}

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
• TOTAL ESTIMATED RATING LOSS: ~{total_rating_loss} points

📈 TREND
{trend}

📚 OPENING REPERTOIRE
{_format_opening_repertoire(weak_openings, strong_openings)}

⚔️ OPPONENT STRENGTH ANALYSIS
{_format_opponent_analysis(opponent_by_strength)}

🏆 STREAKS & CONSISTENCY
• Max win streak: {max_win_streak} games
• Max loss streak: {max_loss_streak} games
• Longest blunder-free run: {max_blunder_free} games
• Current streak: {current_streak} {current_streak_type or 'N/A'}s

🎯 ENDGAME CONVERSION
• Endgame games (40+ moves): {endgame_games}
• Endgame wins: {endgame_wins}
• Endgame win rate: {endgame_win_rate:.0f}%

🤖 DETERMINISTIC ANALYSIS SUMMARY
(From rule-based system, no LLM — use this as ground truth)
• Primary weakness identified: {deterministic_weakness or 'None flagged'}
• Strengths: {', '.join(deterministic_strengths) if deterministic_strengths else 'None flagged'}

══════════════════════════════════════════════════════════════════════════════
"""

    # Build the instruction prompt
    instruction_prompt = f"""
You are an elite chess coach producing a premium executive performance report. Your output must match the quality of a $500/hour professional coach.

══════════════════════════════════════════════════════════════════════════════
SEVERITY: {severity} | CONFIDENCE: {confidence}
Match your rhetorical intensity to the severity level:
- CRITICAL → Blunt and urgent. "This is costing you rating points."
- SIGNIFICANT → Direct and firm. "This needs immediate attention."
- MODERATE → Calm and corrective. "There's room for improvement here."
══════════════════════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════════════════════
CRITICAL RULES — VIOLATING ANY OF THESE MAKES YOUR OUTPUT WORTHLESS
══════════════════════════════════════════════════════════════════════════════

1. DISTINGUISH ROOT CAUSE vs MANIFESTATIONS
   - ROOT CAUSE = the cognitive/decision-making failure (ONE only)
   - MANIFESTATIONS = where it shows up (endgame, after captures, etc.)
   - Never blame a phase. Blame a mental process.
   - Bad: "Your endgame is weak" (that's a manifestation)
   - Good: "You suffer from Premature Safety Bias — you stop calculating when you think you're 'safe'" (that's a root cause)

2. NAME THE PATTERNS
   - Give cognitive failures specific, memorable names
   - Examples: "Post-Capture Blindness", "Complacency Syndrome", "Evaluation Inertia", "Threat Exhaustion", "Premature Closure"

3. QUANTIFY EVERYTHING + CALIBRATE CONFIDENCE
   - Use specific numbers: "33 games thrown away" not "many games lost"
   - Acknowledge sample size: "{total_games} games analyzed"
   - If confidence is LOW, say: "Based on limited data, this pattern appears to..."
    - Do NOT pad the report by repeating the same stats in multiple sections.
      State the key numbers once (ideally in Evidence), then refer to them implicitly.

4. BEHAVIORAL RULES, NOT VAGUE ADVICE
   - Bad: "Calculate more carefully when winning"
   - Good: "In any position ≥+1.5, identify opponent's best forcing reply before moving. If you cannot name it, you are not allowed to simplify."

5. INCLUDE NEGATIVE CONSTRAINTS
   - What must they STOP doing?
   - "Do NOT trade when ahead without identifying counterplay"
   - "Do NOT push pawns in winning positions without checking tactics"
   - Humans follow negative constraints better than positive advice.

6. IDENTIFY FAILURE TRIGGERS
   - Name the exact moment/situation that triggers collapse:
   - "First simplification", "First passed pawn", "Eval crosses +1.5", "Opponent plays unexpected defense"
    - REQUIRED: write one explicit trigger sentence with a tight time-window.
      Example: "Your collapse reliably begins within 3–5 moves of the first major simplification."

7. PROFILE THE PLAYER'S COGNITIVE STYLE
   - Classify them: Risk-averse? Overconfident when ahead? Reactive under pressure? Pattern-based vs calculation-based?
   - This is gold for self-awareness.

══════════════════════════════════════════════════════════════════════════════
REQUIRED OUTPUT FORMAT (follow EXACTLY)
══════════════════════════════════════════════════════════════════════════════

## 🧠 Executive Diagnosis

[ONE paragraph. Start with a strong claim: "Your rating is capped by..." or "You're consistently losing wins because of..."]

[Second paragraph explaining the SINGLE root cause in cognitive/behavioral terms. End with: "Fixing this one mental habit would yield a larger rating gain than improving every other area combined."]

---

## 🔍 Root Cause vs Manifestations

**🎯 ROOT CAUSE (The Mental Failure):**
[Name it. Example: "Premature Safety Bias" or "Threat Exhaustion Syndrome"]
[Explain what happens in your brain when this occurs. 2-3 sentences on the cognitive mechanism.]

**📍 WHERE IT SHOWS UP (Manifestations):**
- [Manifestation 1]: [Data point]
- [Manifestation 2]: [Data point]
- [Manifestation 3]: [Data point]

[Important: The root cause explains ALL the manifestations. If it doesn't, you picked the wrong root cause.]

---

## 🧬 Your Cognitive Profile

Based on your game patterns, you appear to be:
- **[Profile Type]**: [1-2 sentence description]
- **Collapse Trigger (named + timed)**: [One sentence. Example: "Within 3–5 moves of the first simplification, your accuracy drops."]
- **Inferred assumption (from move selection)**: [Phrase as inference, not mind-reading. Example: "Your move choices suggest you treat simplified positions as lower-risk and stop checking forcing replies."]

---

## 🔁 The Failure Loop

```
[Trigger] → [False assumption] → [Behavior change] → [Opponent action] → [Result]
```

This loop repeats regardless of opening, color, or time control.

---

## 🧪 Evidence Breakdown

**Blunders by Context:**
[Reference specific numbers. Highlight the KEY insight.]

**Phase Performance:**
[Interpret PPI. Remember: the phase isn't the cause, it's where the cause shows up.]

**Opening Outcomes:**
[If openings are NOT the problem, say clearly: "Your openings are not the issue. You exit with an advantage and then throw it away."]

---

## 🎛 Confidence Calibration (Read Before Recommendations)

**Confidence level:** {confidence}
{confidence_note}

[If confidence is LOW: explicitly say which conclusions are strong vs tentative.]

---

## 🚫 What NOT to Work On (Ignore This)

[Explicitly tell them what to SKIP. This is psychologically powerful.]

- **Don't** [Area to ignore] — [Why it doesn't matter for them right now]
- **Don't** [Area to ignore] — [Why it's not their bottleneck]

---

## 🎯 The ONE Rule (If You Remember Nothing Else)

> **[State the behavioral rule in a blockquote. Make it memorable, specific, testable.]**

**Why This Works (Psychologically):**
[Explain WHY this rule changes behavior at the cognitive level. Use concepts like: attention narrowing, threat scanning, loss aversion, premature closure, working memory limits.]

---

## ⏱ Do This During the Game (5 seconds)

Before every move in the error-prone phase/context identified above, ask:
1) **What is my opponent threatening right now (forcing moves first)?**
2) **If I'm wrong, what is the immediate refutation?**

Then apply the ONE Rule.

---

## ❌ Things You Must STOP Doing

1. **STOP** [Negative constraint #1]
   - Why: [Brief explanation tied to data]

2. **STOP** [Negative constraint #2]
   - Why: [Brief explanation tied to data]

---

## 🛠 Secondary Adjustments (Only if they reinforce the ONE Rule)

[IMPORTANT: These are not new domains. Each adjustment must directly support the ONE Rule and the root cause. If it cannot be explained as reinforcement, omit it.]

**1. [Adjustment Name]**
- What to do: [Specific action]
- Why it matters: [Cite the data point]
- Target metric: [Current] → [Target]

**2. [Adjustment Name]** (only if data supports)
- What to do: [Specific action]
- Why it matters: [Cite the data point]
- Target metric: [Current] → [Target]

---

## 📈 Expected Impact

[Do NOT restate the same numbers already stated earlier. Refer back to them implicitly.]

If you:
- [Specific improvement #1]
- [Specific improvement #2]

Then based on your game data:
- **[X] additional wins per 100 games** (confidence: {confidence.lower()})
- **Estimated rating gain: +[low] to +[high] points**

**Conditioning (protect credibility):**
- Phrase impact as conditional on compliance and sample size.
- Example: "If you follow this consistently over the next ~50 games, the expected gain is +[low] to +[high]."

This improvement comes without changing openings, tactics training volume, or time control.

---

## ✅ One-Sentence Summary

[A punchy, memorable summary that captures the essence. This should be something they can repeat to themselves during a game.]

**If you remember only ONE thing, remember this:**
> [Restate the core insight in the most memorable way possible]

══════════════════════════════════════════════════════════════════════════════
TONE REQUIREMENTS (calibrated to severity)
══════════════════════════════════════════════════════════════════════════════

Current severity: {severity}

{"- Be blunt and direct. Use plain language; avoid theatrics." if severity == "CRITICAL" else "- Be firm but constructive. Keep it tight and specific." if severity == "SIGNIFICANT" else "- Be calm and corrective. Keep it concise and evidence-led."}

Style constraints:
- Use metaphors sparingly (max 1 per section). Prefer direct, analytical phrasing.
- Avoid repeating the same stats (counts/percentages) in multiple sections.

Sound like a coach who:
- Has analyzed thousands of players
- Knows exactly what's holding them back
- Genuinely wants them to improve
- Isn't afraid to be direct

══════════════════════════════════════════════════════════════════════════════
QUALITY CHECK (verify before responding)
══════════════════════════════════════════════════════════════════════════════

□ Is there exactly ONE root cause? If no, rewrite.
□ Did I distinguish root cause from manifestations? If no, rewrite.
□ Did I name the cognitive profile and collapse trigger? If no, add them.
□ Did I include "What NOT to work on"? If no, add it.
□ Did I include negative constraints (STOP doing X)? If no, add them.
□ Did I explain WHY the fix works psychologically? If no, add it.
□ Did I calibrate confidence to sample size? If no, adjust.
□ Could this advice apply to a random 1200 player? If yes, rewrite.
□ Did I end with "If you remember only ONE thing"? If no, add it.

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


def _format_opening_repertoire(weak_openings: list, strong_openings: list) -> str:
    """Format opening repertoire stats for the prompt."""
    lines = []
    
    if weak_openings:
        lines.append("❌ Weak openings (<40% win rate, 3+ games):")
        for opening in weak_openings:
            lines.append(f"  • {opening['name']}: {opening['games']} games, {opening['win_rate']:.0f}% win rate")
    else:
        lines.append("✓ No significantly weak openings detected")
    
    lines.append("")
    
    if strong_openings:
        lines.append("✅ Strong openings (≥60% win rate, 3+ games):")
        for opening in strong_openings:
            lines.append(f"  • {opening['name']}: {opening['games']} games, {opening['win_rate']:.0f}% win rate")
    else:
        lines.append("• No standout strong openings detected")
    
    return '\n'.join(lines)


def _format_opponent_analysis(opponent_by_strength: dict) -> str:
    """Format opponent strength analysis for the prompt."""
    if not opponent_by_strength:
        return "No opponent rating data available"
    
    lines = ["┌───────────────────┬───────┬──────────┬──────────┐",
             "│ Opponent Level    │ Games │ Win Rate │ Analysis │",
             "├───────────────────┼───────┼──────────┼──────────┤"]
    
    labels = {
        'lower_rated': 'Lower (-100+)',
        'similar_rated': 'Similar (±100)',
        'higher_rated': 'Higher (+100+)',
    }
    
    for key, label in labels.items():
        data = opponent_by_strength.get(key, {})
        games = data.get('games', 0)
        win_rate = data.get('win_rate', 0)
        
        # Analysis based on expected performance
        if key == 'lower_rated':
            expected = 70  # Should win most vs weaker
            analysis = "🟢 Good" if win_rate >= expected else "🔴 Leaking" if games >= 5 else "—"
        elif key == 'similar_rated':
            expected = 50  # Should be around 50%
            analysis = "🟢 OK" if 40 <= win_rate <= 60 else "🟡 Check" if games >= 5 else "—"
        else:  # higher_rated
            expected = 30  # Lower expected vs stronger
            analysis = "🟢 Punching up" if win_rate >= expected else "🟡 Expected" if games >= 5 else "—"
        
        lines.append(f"│ {label:<17} │ {games:>5} │ {win_rate:>7.0f}% │ {analysis:<8} │")
    
    lines.append("└───────────────────┴───────┴──────────┴──────────┘")
    
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

AI_COACH_SYSTEM_PROMPT = """You are an elite chess performance coach who produces premium diagnostic reports with the depth of a sports psychologist.

Your role is NOT to print statistics. Your role is to:
1. Identify the ONE ROOT CAUSE (cognitive/behavioral failure) — NOT a phase or symptom
2. Distinguish root cause from MANIFESTATIONS (where it shows up)
3. Profile the player's cognitive style (risk-averse, overconfident, etc.)
4. Explain WHY this pattern occurs (attention, working memory, threat scanning failure)
5. Provide BEHAVIORAL rules AND negative constraints ("STOP doing X")
6. Identify the exact TRIGGER that causes collapse
7. Calibrate confidence to sample size — don't overclaim on small data
8. Project expected rating gains with honest uncertainty

Communication constraints:
- Prefer direct, analytical language over drama.
- Avoid padding: do not repeat the same numbers (counts/percentages) across multiple sections.
- When describing "beliefs" or "assumptions", phrase them as inference from behavior (e.g., "Your move choices suggest...") not mind-reading.

You sound like a $500/hour executive coach who:
- Has analyzed thousands of chess players
- Cuts through noise to find the real mental issue
- Is direct, specific, and calibrates intensity to severity
- Explains the psychology behind the fix
- Tells players what NOT to work on (huge psychological value)
- Never says generic things like "study tactics" or "practice more"

FORBIDDEN PHRASES (never use these):
- "Calculate more carefully"
- "Study endgames"  
- "Focus on tactics"
- "Practice more"
- "Be more patient"
- "Think longer"
- "Consider all options"
- "Be more vigilant"

These phrases are worthless. Always provide specific, testable behavioral rules AND negative constraints instead.

REMEMBER: The phase isn't the cause. The mental process is the cause. The phase is just where it shows up.
"""
