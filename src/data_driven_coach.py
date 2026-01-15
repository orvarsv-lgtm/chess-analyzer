"""
Data-Driven Chess Coaching Engine

Generates player-specific coaching text ONLY from analyzed data.
No generic advice. Every sentence is backed by stats.

Rules:
- If a section cannot be justified by data, it returns None
- No external resource recommendations unless data-justified
- All explanations reference specific numbers from the analysis
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class CoachingSection:
    """A coaching section with its data justification."""
    title: str
    content: str
    data_sources: List[str]  # What data justified this section
    confidence: float  # 0-1, how strong is the data support


# =============================================================================
# GAME SUMMARY - What actually decided the game(s)
# =============================================================================


def explain_game_summary(stats: Dict[str, Any]) -> Optional[CoachingSection]:
    """
    Generate data-driven game summary.
    
    Only includes claims backed by actual numbers.
    """
    total_games = stats.get('total_games', 0)
    if total_games == 0:
        return None
    
    wins = stats.get('wins', 0)
    losses = stats.get('losses', 0)
    draws = stats.get('draws', 0)
    conversion_rate = stats.get('conversion_rate', 0)
    conversion_stats = stats.get('conversion_stats', {})
    total_blunders = stats.get('total_blunders', 0)
    blunder_rate = stats.get('blunder_rate', 0)
    blunder_phases = stats.get('blunder_phases', {})
    rating_cost = stats.get('rating_cost_factors', {})
    
    # Get dynamic threshold info
    winning_threshold_cp = stats.get('winning_threshold_cp', 150)
    winning_threshold_pawns = winning_threshold_cp / 100
    
    lines = []
    data_sources = []
    
    # What's the primary story?
    winning_positions = conversion_stats.get('winning_positions', 0)
    converted = conversion_stats.get('converted_wins', 0)
    
    # Story 1: Conversion failure is the main issue
    if winning_positions >= 3 and conversion_rate < 70:
        unconverted = winning_positions - converted
        lines.append(
            f"You reached winning positions (≥+{winning_threshold_pawns:.1f}) in {winning_positions} games "
            f"but only converted {converted} to wins ({conversion_rate:.0f}%). "
            f"You let {unconverted} winning games slip away."
        )
        data_sources.append(f"conversion_rate={conversion_rate:.0f}%")
    
    # Story 2: Blunders concentrated in specific phase
    if total_blunders >= 3:
        max_phase = max(blunder_phases, key=blunder_phases.get) if blunder_phases else None
        if max_phase:
            phase_blunders = blunder_phases[max_phase]
            phase_pct = (phase_blunders / total_blunders * 100) if total_blunders > 0 else 0
            if phase_pct >= 50:
                lines.append(
                    f"{phase_pct:.0f}% of your blunders ({phase_blunders}/{total_blunders}) "
                    f"occurred in the {max_phase}. This is where your games break down."
                )
                data_sources.append(f"blunder_phases[{max_phase}]={phase_blunders}")
    
    # Story 3: Specific rating cost factor
    if rating_cost:
        top_factor = max(rating_cost.items(), key=lambda x: _get_count(x[1]))
        factor_name, factor_data = top_factor
        count = _get_count(factor_data)
        if count >= 2:
            factor_labels = {
                'blunders_in_winning_pos': 'throwing away winning positions',
                'endgame_collapses': 'collapsing in won endgames',
                'opening_disasters': 'opening disasters before move 15',
                'missed_wins': 'drawing games you had won',
            }
            label = factor_labels.get(factor_name, factor_name.replace('_', ' '))
            lines.append(f"Your biggest leak: {label} ({count} games).")
            data_sources.append(f"rating_cost[{factor_name}]={count}")
    
    # Add win/loss context
    if losses > wins:
        lines.append(f"Record: {wins}W-{losses}L-{draws}D across {total_games} games.")
    
    if not lines:
        # Fallback: just state the facts
        lines.append(
            f"Analyzed {total_games} games ({wins}W-{losses}L-{draws}D). "
            f"Blunder rate: {blunder_rate:.1f} per 100 moves."
        )
        data_sources.append(f"blunder_rate={blunder_rate:.1f}")
    
    return CoachingSection(
        title="What's Happening",
        content=' '.join(lines),
        data_sources=data_sources,
        confidence=0.9 if len(data_sources) >= 2 else 0.6
    )


# =============================================================================
# OPENING OUTCOMES - Position quality, not "study this"
# =============================================================================


def explain_opening_outcomes(stats: Dict[str, Any]) -> Optional[CoachingSection]:
    """
    Explain opening performance based on position quality after move 15.
    
    Never says "study this opening". Instead:
    - Reports average eval after opening
    - Identifies if losses happen despite good positions
    """
    openings = stats.get('openings', {})
    opening_outcomes = stats.get('opening_outcomes', {})
    
    if not openings:
        return None
    
    lines = []
    data_sources = []
    
    # Filter meaningful openings (at least 2 games)
    meaningful_openings = {
        k: v for k, v in openings.items() 
        if k and k != 'Unknown' and v.get('games', 0) >= 2
    }
    
    if not meaningful_openings:
        return None
    
    # Find openings with position data
    openings_with_eval = []
    for name, data in meaningful_openings.items():
        eval_count = data.get('eval_after_opening_count', 0)
        if eval_count > 0:
            avg_eval = data.get('eval_after_opening_sum', 0) / eval_count
            games = data.get('games', 0)
            wins = data.get('wins', 0)
            losses = data.get('losses', 0)
            win_rate = wins / games if games > 0 else 0
            openings_with_eval.append({
                'name': name,
                'avg_eval': avg_eval,
                'games': games,
                'win_rate': win_rate,
                'wins': wins,
                'losses': losses,
            })
    
    if openings_with_eval:
        # Sort by games played
        openings_with_eval.sort(key=lambda x: -x['games'])
        
        # Find the story: good positions but bad results?
        for op in openings_with_eval[:3]:
            if op['avg_eval'] >= 30 and op['win_rate'] < 0.5 and op['games'] >= 3:
                # Good positions, bad results = conversion issue
                lines.append(
                    f"**{op['name']}**: You average +{op['avg_eval']:.0f}cp after move 15, "
                    f"but your win rate is only {op['win_rate']:.0%} ({op['wins']}W-{op['losses']}L). "
                    f"The opening isn't the problem — you're losing these games later."
                )
                data_sources.append(f"{op['name']}: eval={op['avg_eval']:+.0f}, WR={op['win_rate']:.0%}")
            
            elif op['avg_eval'] <= -30 and op['games'] >= 3:
                # Bad positions from the opening
                lines.append(
                    f"**{op['name']}**: You average {op['avg_eval']:.0f}cp after move 15. "
                    f"You're consistently getting worse positions out of this opening."
                )
                data_sources.append(f"{op['name']}: eval={op['avg_eval']:+.0f}")
            
            elif op['win_rate'] >= 0.6 and op['avg_eval'] >= 20 and op['games'] >= 3:
                # This one works
                lines.append(
                    f"**{op['name']}** is working: +{op['avg_eval']:.0f}cp average, "
                    f"{op['win_rate']:.0%} win rate over {op['games']} games."
                )
                data_sources.append(f"{op['name']}: WR={op['win_rate']:.0%}")
    
    # Global opening outcome
    if opening_outcomes:
        avg_eval = opening_outcomes.get('avg_eval_after_opening', 0)
        better = opening_outcomes.get('left_opening_better', 0)
        worse = opening_outcomes.get('left_opening_worse', 0)
        total_eval_games = opening_outcomes.get('games_with_opening_eval', 0)
        
        if total_eval_games >= 5:
            if avg_eval >= 30:
                lines.append(
                    f"Overall: You leave the opening with +{avg_eval:.0f}cp on average "
                    f"({better} games better, {worse} worse). Your openings are solid."
                )
            elif avg_eval <= -30:
                lines.append(
                    f"Overall: You leave the opening with {avg_eval:.0f}cp on average. "
                    f"You're starting the middlegame at a disadvantage in most games."
                )
    
    if not lines:
        return None
    
    return CoachingSection(
        title="Opening Position Quality",
        content='\n'.join(lines),
        data_sources=data_sources,
        confidence=0.8 if len(data_sources) >= 2 else 0.5
    )


# =============================================================================
# FAILURE PATTERN ANALYSIS - What's actually breaking
# =============================================================================


def explain_failure_patterns(stats: Dict[str, Any]) -> Optional[CoachingSection]:
    """
    Identify specific failure patterns with frequency, phase, and eval context.
    
    Patterns detected:
    - Blunders after captures (recapture calculation)
    - Over-pushing in winning positions
    - Defensive collapse when worse
    - Endgame technique breakdown
    """
    blunder_contexts = stats.get('blunder_contexts', {})
    total_blunders = stats.get('total_blunders', 0)
    blunder_phases = stats.get('blunder_phases', {})
    conversion_rate = stats.get('conversion_rate', 0)
    
    # Get dynamic threshold
    winning_threshold_cp = stats.get('winning_threshold_cp', 150)
    winning_threshold_pawns = winning_threshold_cp / 100
    
    if total_blunders < 3:
        return None
    
    lines = []
    data_sources = []
    
    # Pattern 1: Post-capture blunders (recapture calculation)
    after_capture = blunder_contexts.get('after_capture', 0)
    if after_capture >= 2:
        pct = (after_capture / total_blunders * 100)
        if pct >= 25:
            lines.append(
                f"**Recapture calculation errors**: {pct:.0f}% of your blunders "
                f"({after_capture}/{total_blunders}) occur immediately after captures. "
                f"When you take a piece, you're not fully calculating your opponent's best reply."
            )
            data_sources.append(f"after_capture={after_capture} ({pct:.0f}%)")
    
    # Pattern 2: Winning position blunders (conversion failure)
    in_winning = blunder_contexts.get('in_winning_position', 0)
    if in_winning >= 2:
        pct = (in_winning / total_blunders * 100)
        if pct >= 20:
            lines.append(
                f"**Conversion failures**: {pct:.0f}% of your blunders ({in_winning}/{total_blunders}) "
                f"happen when you're already winning (≥+{winning_threshold_pawns:.1f}). You relax when ahead and stop calculating."
            )
            data_sources.append(f"in_winning_position={in_winning} ({pct:.0f}%)")
    
    # Pattern 3: Time pressure proxy (late-game blunders)
    time_trouble = blunder_contexts.get('time_trouble_likely', 0)
    if time_trouble >= 2:
        pct = (time_trouble / total_blunders * 100)
        if pct >= 30:
            lines.append(
                f"**Late-game errors (possible time pressure)**: {pct:.0f}% of your blunders "
                f"({time_trouble}/{total_blunders}) occur after move 35. "
                f"If you're playing timed games, you may be running low on time."
            )
            data_sources.append(f"time_trouble_likely={time_trouble} ({pct:.0f}%)")
    
    # Pattern 4: Endgame-specific breakdown
    endgame_blunders = blunder_phases.get('endgame', 0)
    if endgame_blunders >= 3:
        endgame_pct = (endgame_blunders / total_blunders * 100)
        if endgame_pct >= 40:
            endgame_cpl = stats.get('endgame_cpl', 0)
            lines.append(
                f"**Endgame breakdown**: {endgame_pct:.0f}% of your blunders "
                f"({endgame_blunders}/{total_blunders}) occur in the endgame. "
                f"Your endgame CPL is {endgame_cpl:.0f}."
            )
            data_sources.append(f"endgame_blunders={endgame_blunders} ({endgame_pct:.0f}%)")
    
    # Pattern 5: Defensive collapse
    in_losing = blunder_contexts.get('in_losing_position', 0)
    in_equal = blunder_contexts.get('in_equal_position', 0)
    if in_losing >= 2 and in_losing > in_equal:
        pct = (in_losing / total_blunders * 100)
        lines.append(
            f"**Defensive collapse**: {pct:.0f}% of your blunders ({in_losing}/{total_blunders}) "
            f"happen when you're already worse. When behind, you compound mistakes."
        )
        data_sources.append(f"in_losing_position={in_losing} ({pct:.0f}%)")
    
    if not lines:
        # No clear patterns - state that
        return CoachingSection(
            title="Failure Patterns",
            content=f"No dominant failure pattern detected across {total_blunders} blunders. "
                    f"Errors are distributed across different contexts.",
            data_sources=["no_dominant_pattern"],
            confidence=0.4
        )
    
    return CoachingSection(
        title="Failure Patterns",
        content='\n\n'.join(lines),
        data_sources=data_sources,
        confidence=0.85 if len(lines) >= 2 else 0.6
    )


# =============================================================================
# TACTICAL WEAKNESS ANALYSIS - Only if data supports it
# =============================================================================


def explain_tactical_weaknesses(
    stats: Dict[str, Any],
    games: List[Dict[str, Any]]
) -> Optional[CoachingSection]:
    """
    Identify concrete tactical weaknesses from move data.
    
    Only reports patterns that actually appear in the data:
    - Missed forks/pins (requires move analysis)
    - Hanging pieces after exchanges
    - Failure to spot threats
    
    Returns None if no tactical patterns are detectable.
    """
    # We need to analyze actual move sequences for tactical patterns
    # For now, we'll look at what we can infer from blunder contexts
    
    blunder_contexts = stats.get('blunder_contexts', {})
    total_blunders = stats.get('total_blunders', 0)
    
    if total_blunders < 3:
        return None
    
    lines = []
    data_sources = []
    
    # After-check blunders suggest threat blindness
    after_check = blunder_contexts.get('after_check', 0)
    if after_check >= 2:
        pct = (after_check / total_blunders * 100)
        if pct >= 15:
            lines.append(
                f"**Threat blindness after checks**: {after_check} blunders ({pct:.0f}%) "
                f"occur within 2 moves of being checked. When your king is attacked, "
                f"you're not fully scanning for follow-up threats."
            )
            data_sources.append(f"after_check={after_check}")
    
    # After-capture blunders often indicate hanging piece blindness
    after_capture = blunder_contexts.get('after_capture', 0)
    if after_capture >= 3:
        pct = (after_capture / total_blunders * 100)
        if pct >= 30:
            lines.append(
                f"**Exchange blindness**: {after_capture} blunders ({pct:.0f}%) happen after captures. "
                f"After an exchange, you're leaving pieces undefended or missing recapture tactics."
            )
            data_sources.append(f"after_capture_tactical={after_capture}")
    
    # If we have game-level data, look for specific tactical misses
    tactical_miss_count = 0
    fork_misses = 0
    
    for game in games:
        moves_table = game.get('moves_table', [])
        focus_color = game.get('focus_color', 'white')
        
        for move in moves_table:
            if (move.get('mover') or move.get('color')) != focus_color:
                continue
            
            cp_loss = move.get('cp_loss', 0) or 0
            best_move = move.get('best_move_san', '')
            
            # Detect if best move was a tactical shot (simplistic heuristic)
            if cp_loss >= 200:
                tactical_miss_count += 1
                # Check for fork patterns (N captures with multiple threats)
                if best_move and best_move.startswith('N') and 'x' in best_move:
                    fork_misses += 1
    
    if fork_misses >= 2:
        lines.append(
            f"**Missed knight tactics**: At least {fork_misses} missed knight tactics "
            f"(captures/forks) were identified as best moves when you blundered."
        )
        data_sources.append(f"fork_misses={fork_misses}")
    
    if not lines:
        return None
    
    return CoachingSection(
        title="Tactical Weaknesses",
        content='\n\n'.join(lines),
        data_sources=data_sources,
        confidence=0.7
    )


# =============================================================================
# TRAINING RECOMMENDATIONS - Measurable, tied to data
# =============================================================================


def generate_training_recommendations(
    stats: Dict[str, Any],
    failure_patterns: Optional[CoachingSection],
    opening_analysis: Optional[CoachingSection],
    tactical_analysis: Optional[CoachingSection],
) -> Optional[CoachingSection]:
    """
    Generate training recommendations tied directly to identified weaknesses.
    
    Each recommendation includes:
    - What to fix (tied to data)
    - Numeric goal
    - How to verify improvement
    """
    recommendations = []
    data_sources = []
    
    conversion_rate = stats.get('conversion_rate', 0)
    blunder_rate = stats.get('blunder_rate', 0)
    endgame_cpl = stats.get('endgame_cpl', 0)
    blunder_contexts = stats.get('blunder_contexts', {})
    total_blunders = stats.get('total_blunders', 0)
    
    # Get dynamic threshold
    winning_threshold_cp = stats.get('winning_threshold_cp', 150)
    winning_threshold_pawns = winning_threshold_cp / 100
    
    # Recommendation 1: Conversion (if below 70%)
    if conversion_rate > 0 and conversion_rate < 70:
        target = min(75, conversion_rate + 15)
        recommendations.append({
            'fix': "Improve conversion from winning positions",
            'because': f"Your conversion rate is {conversion_rate:.0f}%",
            'goal': f"Conversion rate: {conversion_rate:.0f}% → {target:.0f}%",
            'verify': f"Track % of games where you had ≥+{winning_threshold_pawns:.1f} and won",
        })
        data_sources.append(f"conversion_rate={conversion_rate:.0f}%")
    
    # Recommendation 2: Endgame (if CPL > 150)
    if endgame_cpl > 150:
        target_cpl = max(120, endgame_cpl - 40)
        recommendations.append({
            'fix': "Reduce endgame errors",
            'because': f"Your endgame CPL is {endgame_cpl:.0f} (baseline: 130)",
            'goal': f"Endgame CPL: {endgame_cpl:.0f} → {target_cpl:.0f}",
            'verify': "Measure endgame CPL in your next 10 games",
        })
        data_sources.append(f"endgame_cpl={endgame_cpl:.0f}")
    
    # Recommendation 3: Post-capture calculation
    after_capture = blunder_contexts.get('after_capture', 0)
    if total_blunders > 0:
        after_capture_pct = (after_capture / total_blunders * 100)
        if after_capture >= 3 and after_capture_pct >= 25:
            target_pct = max(10, after_capture_pct - 15)
            recommendations.append({
                'fix': "Improve recapture calculation",
                'because': f"{after_capture_pct:.0f}% of blunders occur after captures",
                'goal': f"Post-capture blunder %: {after_capture_pct:.0f}% → {target_pct:.0f}%",
                'verify': "Before recapturing, always ask: what's their best reply?",
            })
            data_sources.append(f"after_capture={after_capture_pct:.0f}%")
    
    # Recommendation 4: Blunder rate reduction
    if blunder_rate > 5:
        target_rate = max(3, blunder_rate - 2)
        recommendations.append({
            'fix': "Reduce overall blunder rate",
            'because': f"Current blunder rate: {blunder_rate:.1f} per 100 moves",
            'goal': f"Blunder rate: {blunder_rate:.1f} → {target_rate:.1f} per 100 moves",
            'verify': "Track blunders per game over next 10 games",
        })
        data_sources.append(f"blunder_rate={blunder_rate:.1f}")
    
    # Recommendation 5: Winning position discipline
    in_winning = blunder_contexts.get('in_winning_position', 0)
    if total_blunders > 0:
        in_winning_pct = (in_winning / total_blunders * 100)
        if in_winning >= 2 and in_winning_pct >= 20:
            recommendations.append({
                'fix': "Maintain focus when winning",
                'because': f"{in_winning_pct:.0f}% of blunders happen when already ahead",
                'goal': f"Blunders in winning positions: {in_winning} → {max(0, in_winning - 2)}",
                'verify': f"When ahead by +{winning_threshold_pawns:.1f}, spend 30 extra seconds on each move",
            })
            data_sources.append(f"in_winning_position={in_winning}")
    
    if not recommendations:
        return None
    
    # Format output
    lines = []
    for i, rec in enumerate(recommendations[:4], 1):  # Max 4 recommendations
        lines.append(f"**{i}. {rec['fix']}**")
        lines.append(f"   _Because_: {rec['because']}")
        lines.append(f"   _Goal_: {rec['goal']}")
        lines.append(f"   _Verify_: {rec['verify']}")
        lines.append("")
    
    return CoachingSection(
        title="Training Recommendations",
        content='\n'.join(lines).strip(),
        data_sources=data_sources,
        confidence=0.9
    )


# =============================================================================
# MAIN COACHING ENGINE
# =============================================================================


def generate_data_driven_analysis(
    stats: Dict[str, Any],
    games: List[Dict[str, Any]],
    player_name: str,
    player_rating: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate complete data-driven coaching analysis.
    
    Returns a structured analysis where every section is backed by data.
    Sections with insufficient data are omitted entirely.
    """
    
    # Generate each section
    summary = explain_game_summary(stats)
    opening = explain_opening_outcomes(stats)
    failures = explain_failure_patterns(stats)
    tactics = explain_tactical_weaknesses(stats, games)
    training = generate_training_recommendations(stats, failures, opening, tactics)
    
    # Build final analysis
    sections = []
    
    if summary:
        sections.append(f"## {summary.title}\n\n{summary.content}")
    
    if failures:
        sections.append(f"## {failures.title}\n\n{failures.content}")
    
    if opening:
        sections.append(f"## {opening.title}\n\n{opening.content}")
    
    if tactics:
        sections.append(f"## {tactics.title}\n\n{tactics.content}")
    
    if training:
        sections.append(f"## {training.title}\n\n{training.content}")
    
    # Create primary finding
    primary_issue = _determine_primary_issue(stats)
    
    analysis_text = '\n\n---\n\n'.join(sections) if sections else "Insufficient data for analysis."
    
    # Collect all data sources used
    all_data_sources = []
    for section in [summary, opening, failures, tactics, training]:
        if section:
            all_data_sources.extend(section.data_sources)
    
    return {
        'analysis': analysis_text,
        'primary_issue': primary_issue,
        'sections': {
            'summary': summary,
            'opening': opening,
            'failures': failures,
            'tactics': tactics,
            'training': training,
        },
        'data_sources': all_data_sources,
        'stats': stats,
    }


def _determine_primary_issue(stats: Dict[str, Any]) -> str:
    """Determine the single most important issue to fix."""
    conversion_rate = stats.get('conversion_rate', 100)
    blunder_rate = stats.get('blunder_rate', 0)
    blunder_contexts = stats.get('blunder_contexts', {})
    total_blunders = stats.get('total_blunders', 0)
    
    # Priority 1: Conversion (if below 70%)
    if conversion_rate < 70 and stats.get('conversion_stats', {}).get('winning_positions', 0) >= 3:
        return f"Conversion failure ({conversion_rate:.0f}% conversion rate)"
    
    # Priority 2: Winning position blunders
    in_winning = blunder_contexts.get('in_winning_position', 0)
    if total_blunders > 0:
        in_winning_pct = (in_winning / total_blunders * 100)
        if in_winning_pct >= 30:
            return f"Blunders when winning ({in_winning_pct:.0f}% of blunders)"
    
    # Priority 3: Post-capture blunders
    after_capture = blunder_contexts.get('after_capture', 0)
    if total_blunders > 0:
        after_capture_pct = (after_capture / total_blunders * 100)
        if after_capture_pct >= 35:
            return f"Recapture calculation ({after_capture_pct:.0f}% of blunders)"
    
    # Priority 4: Endgame issues
    endgame_cpl = stats.get('endgame_cpl', 0)
    if endgame_cpl > 160:
        return f"Endgame technique (CPL: {endgame_cpl:.0f})"
    
    # Priority 5: High blunder rate overall
    if blunder_rate > 6:
        return f"High blunder rate ({blunder_rate:.1f} per 100 moves)"
    
    return "No dominant weakness identified"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _get_count(data) -> int:
    """Extract count from rating cost factor data."""
    if isinstance(data, dict):
        return data.get('count', 0)
    return data if isinstance(data, (int, float)) else 0


def format_analysis_for_display(analysis: Dict[str, Any]) -> str:
    """Format the analysis for display in the UI."""
    output = []
    
    # Add primary issue banner
    primary = analysis.get('primary_issue', '')
    if primary and primary != "No dominant weakness identified":
        output.append(f"**🎯 Primary Issue**: {primary}\n")
    
    # Add main analysis
    output.append(analysis.get('analysis', ''))
    
    # Add data sources (collapsed)
    data_sources = analysis.get('data_sources', [])
    if data_sources:
        output.append("\n\n---\n_Data sources: " + ', '.join(data_sources[:5]) + "_")
    
    return '\n'.join(output)


# =============================================================================
# SINGLE GAME ANALYSIS - Data-driven
# =============================================================================


def explain_single_game(
    game_data: Dict[str, Any],
    player_color: str,
    player_rating: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate data-driven analysis for a single game.
    
    Returns sections only if data supports them.
    """
    moves_table = game_data.get('moves_table', [])
    opening_name = game_data.get('opening_name') or game_data.get('opening') or 'Unknown'
    result = game_data.get('result', '*')
    
    # Determine outcome
    is_win = (player_color == 'white' and result == '1-0') or (player_color == 'black' and result == '0-1')
    is_loss = (player_color == 'white' and result == '0-1') or (player_color == 'black' and result == '1-0')
    is_draw = result == '1/2-1/2'
    
    # Analyze moves
    blunders = []
    mistakes = []
    phase_cpl = {'opening': [], 'middlegame': [], 'endgame': []}
    eval_history = []
    critical_moments = []
    
    had_winning_position = False
    had_losing_position = False
    biggest_swing = {'move': None, 'swing': 0, 'phase': None}
    
    prev_eval = 0
    
    for move in moves_table:
        move_color = move.get('mover') or move.get('color')
        cp_loss = move.get('cp_loss', 0) or move.get('actual_cp_loss', 0) or 0
        phase = move.get('phase', 'middlegame')
        move_num = move.get('move_num') or ((move.get('ply', 0) + 1) // 2)
        san = move.get('san') or move.get('move_san', '?')
        best_move = move.get('best_move_san', '?')
        
        # Get eval
        eval_after = move.get('score_cp') or move.get('eval_after')
        if eval_after is not None:
            try:
                eval_val = int(eval_after)
                if player_color == 'black':
                    eval_val = -eval_val
                eval_history.append(eval_val)
                
                if eval_val >= 150:
                    had_winning_position = True
                if eval_val <= -150:
                    had_losing_position = True
                
                # Track swings on our moves
                if move_color == player_color:
                    swing = prev_eval - eval_val  # Positive = we lost eval
                    if swing > biggest_swing['swing']:
                        biggest_swing = {
                            'move': move_num,
                            'swing': swing,
                            'phase': phase,
                            'san': san,
                            'best': best_move,
                            'eval_before': prev_eval,
                            'eval_after': eval_val,
                        }
                
                prev_eval = eval_val
            except (TypeError, ValueError):
                pass
        
        if move_color != player_color:
            continue
        
        # Track phase CPL
        if phase in phase_cpl:
            phase_cpl[phase].append(cp_loss)
        
        # Track errors
        if cp_loss >= 300:
            blunders.append({
                'move_num': move_num,
                'san': san,
                'cp_loss': cp_loss,
                'phase': phase,
                'best_move': best_move,
            })
        elif cp_loss >= 100:
            mistakes.append({
                'move_num': move_num,
                'san': san,
                'cp_loss': cp_loss,
                'phase': phase,
            })
    
    # Calculate phase averages
    phase_avg = {}
    for phase, cpls in phase_cpl.items():
        if cpls:
            phase_avg[phase] = sum(cpls) / len(cpls)
    
    # Determine what decided the game
    sections = []
    data_sources = []
    
    # === GAME SUMMARY ===
    summary_lines = []
    
    if is_loss and had_winning_position:
        summary_lines.append(
            f"You had a winning position but lost the game. "
            f"This was a conversion failure."
        )
        data_sources.append("had_winning_position=True, result=loss")
    elif is_win and had_losing_position:
        summary_lines.append(
            f"You were in a losing position but turned it around. "
            f"Your opponent failed to convert their advantage."
        )
        data_sources.append("had_losing_position=True, result=win")
    
    if biggest_swing['swing'] >= 200:
        summary_lines.append(
            f"The game turned on move {biggest_swing['move']} ({biggest_swing['san']}) "
            f"in the {biggest_swing['phase']}, where the eval swung from "
            f"{biggest_swing['eval_before']:+}cp to {biggest_swing['eval_after']:+}cp "
            f"({biggest_swing['swing']}cp loss). Best was {biggest_swing['best']}."
        )
        data_sources.append(f"biggest_swing={biggest_swing['swing']}cp")
    
    if len(blunders) >= 2:
        blunder_phases = [b['phase'] for b in blunders]
        most_common_phase = max(set(blunder_phases), key=blunder_phases.count)
        summary_lines.append(
            f"{len(blunders)} blunders in this game, mostly in the {most_common_phase}."
        )
        data_sources.append(f"blunders={len(blunders)}")
    elif len(blunders) == 1:
        b = blunders[0]
        summary_lines.append(
            f"One blunder: move {b['move_num']} ({b['san']}) lost {b['cp_loss']}cp. "
            f"Best was {b['best_move']}."
        )
        data_sources.append(f"blunder_move={b['move_num']}")
    elif len(blunders) == 0 and is_loss:
        summary_lines.append(
            "No major blunders detected. You were likely outplayed gradually "
            "through small inaccuracies rather than one decisive mistake."
        )
        data_sources.append("no_blunders_but_loss")
    
    if summary_lines:
        sections.append(CoachingSection(
            title="What Decided This Game",
            content=' '.join(summary_lines),
            data_sources=data_sources.copy(),
            confidence=0.9
        ))
    
    # === KEY MOMENTS ===
    key_moments = []
    for b in blunders[:3]:
        key_moments.append({
            'move': b['move_num'],
            'played': b['san'],
            'best': b['best_move'],
            'cp_loss': b['cp_loss'],
            'phase': b['phase'],
            'explanation': f"Move {b['move_num']} ({b['san']}) lost {b['cp_loss']}cp. Best was {b['best_move']}.",
        })
    
    # === PHASE ANALYSIS ===
    phase_lines = []
    worst_phase = None
    worst_cpl = 0
    for phase, avg in phase_avg.items():
        if avg > worst_cpl:
            worst_cpl = avg
            worst_phase = phase
        if avg > 80:
            phase_lines.append(f"- **{phase.title()}** CPL: {avg:.0f} (struggled here)")
        else:
            phase_lines.append(f"- **{phase.title()}** CPL: {avg:.0f}")
    
    if phase_lines:
        if worst_phase and worst_cpl > 80:
            phase_lines.append(f"\nYour weakest phase this game: **{worst_phase}** ({worst_cpl:.0f} CPL)")
        sections.append(CoachingSection(
            title="Phase Performance",
            content='\n'.join(phase_lines),
            data_sources=[f"phase_cpl_{p}={v:.0f}" for p, v in phase_avg.items()],
            confidence=0.8
        ))
    
    # === TRAINING TAKEAWAY ===
    if blunders:
        takeaway = []
        if worst_phase:
            takeaway.append(f"Review your {worst_phase} play in this game.")
        if biggest_swing['swing'] >= 200:
            takeaway.append(
                f"Analyze why {biggest_swing['san']} was wrong on move {biggest_swing['move']}. "
                f"What did {biggest_swing['best']} accomplish that you missed?"
            )
        if takeaway:
            sections.append(CoachingSection(
                title="Takeaway",
                content=' '.join(takeaway),
                data_sources=["game_specific"],
                confidence=0.7
            ))
    
    # Build output
    analysis_text = '\n\n'.join(
        f"## {s.title}\n\n{s.content}" for s in sections
    ) if sections else "Clean game - no major errors detected."
    
    return {
        'analysis': analysis_text,
        'summary': sections[0].content if sections else "No analysis available.",
        'key_moments': key_moments,
        'phase_cpl': phase_avg,
        'blunders': len(blunders),
        'mistakes': len(mistakes),
        'had_winning_position': had_winning_position,
        'had_losing_position': had_losing_position,
        'biggest_swing': biggest_swing,
        'opening': opening_name,
        'result': result,
        'data_sources': data_sources,
    }
