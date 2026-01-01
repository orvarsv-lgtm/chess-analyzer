def classify_move(cp_loss):
    """
    Classify move quality based on centipawn loss (Chess.com style).
    Args:
        cp_loss: int, centipawn loss for the move (>=0)
    Returns:
        str: Move quality label
    """
    if cp_loss <= 10:
        return "Best"
    elif cp_loss <= 30:
        return "Excellent"
    elif cp_loss <= 60:
        return "Good"
    elif cp_loss <= 150:
        return "Inaccuracy"
    elif cp_loss <= 300:
        return "Mistake"
    else:
        return "Blunder"


def classify_blunder(board_before, board_after, move, eval_before, eval_after, phase: str | None = None):
    """
    Classify a blunder into one of:
    - "Hanging piece"
    - "Missed tactic"
    - "King safety"
    - "Endgame technique"
    - "Unknown"
    Args:
        board_before: chess.Board before the move
        board_after: chess.Board after the move
        move: chess.Move played
        eval_before: evaluation before move (centipawns)
        eval_after: evaluation after move (centipawns)
        phase: optional phase label ("opening"|"middlegame"|"endgame")
    Returns:
        blunder_type (str)
    """
    import chess

    def _total_material_value(b) -> int:
        values = {
            chess.PAWN: 1,
            chess.KNIGHT: 3,
            chess.BISHOP: 3,
            chess.ROOK: 5,
            chess.QUEEN: 9,
        }
        total = 0
        for pt, val in values.items():
            total += val * (len(b.pieces(pt, chess.WHITE)) + len(b.pieces(pt, chess.BLACK)))
        return total

    swing = abs(eval_before - eval_after)

    # Heuristic: Endgame technique (low material / endgame phase + large swing)
    if (phase == "endgame" or _total_material_value(board_after) <= 13) and swing > 200:
        return "Endgame technique"

    # Heuristic: Hanging piece (moved non-pawn piece ends up under-defended)
    try:
        moved_piece = board_after.piece_at(move.to_square)
        if moved_piece and moved_piece.piece_type not in (chess.PAWN, chess.KING):
            opponent = board_after.turn
            attackers = board_after.attackers(opponent, move.to_square)
            defenders = board_after.attackers(not opponent, move.to_square)
            if len(attackers) > 0 and len(attackers) > len(defenders):
                return "Hanging piece"
    except Exception:
        pass

    # Heuristic: King safety (king becomes more attacked after the move)
    try:
        mover = not board_after.turn
        k_after = board_after.king(mover)
        k_before = board_before.king(mover)
        if k_after is not None and k_before is not None:
            attackers_after = len(board_after.attackers(board_after.turn, k_after))
            attackers_before = len(board_before.attackers(not mover, k_before))
            if attackers_after > 0 and attackers_after > attackers_before:
                return "King safety"
    except Exception:
        pass

    # Heuristic: Missed tactic (large swing and there existed a forcing move)
    if swing > 300:
        try:
            for cand in board_before.legal_moves:
                if board_before.gives_check(cand):
                    return "Missed tactic"
                if board_before.is_capture(cand):
                    captured = board_before.piece_at(cand.to_square)
                    if captured and captured.piece_type != chess.PAWN:
                        return "Missed tactic"
        except Exception:
            pass

    return "Unknown"
import chess
import chess.engine
from .performance_metrics import classify_phase_stable

DEBUG_ENGINE = False

# Stockfish configuration
STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"
ANALYSIS_DEPTH = 15


def detect_engine_availability(engine_path: str = STOCKFISH_PATH) -> tuple[bool, str]:
    """Detect whether the configured UCI engine can be launched.

    Returns:
        (available, reason)
    """
    try:
        engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    except FileNotFoundError:
        return False, f"engine binary not found at '{engine_path}'"
    except Exception as e:
        return False, f"engine failed to start: {e}"

    try:
        return True, "ok"
    finally:
        try:
            engine.quit()
        except Exception:
            pass

# Centipawn thresholds
BLUNDER_THRESHOLD = 300
MISTAKE_THRESHOLD = 150
PHASE_THRESHOLDS = {
    "opening": {"blunder": 260, "mistake": 120},
    "middlegame": {"blunder": BLUNDER_THRESHOLD, "mistake": MISTAKE_THRESHOLD},
    "endgame": {"blunder": 220, "mistake": 110},
}


def analyze_game_detailed(moves_pgn_str):
    """
    Analyze a game using Stockfish and return structured move-by-move data.
    
    Args:
        moves_pgn_str: Space-separated SAN moves (e.g., "e4 e5 Nf3 Nc6")
            
    Returns:
        List of move evaluation dicts with keys:
        {
            move_num, color, san, cp_loss, phase, blunder_type, eval_before, eval_after
        }
        Returns empty list if analysis fails or no moves.
    """
    if not moves_pgn_str or not isinstance(moves_pgn_str, str):
        return []
    
    moves = moves_pgn_str.strip().split()
    if not moves:
        return []
    
    # Start Stockfish engine
    try:
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    except FileNotFoundError:
        return []
    except Exception:
        return []
    
    try:
        move_evals = []
        board = chess.Board()
        phase_cache: dict[int, str] = {}
        prev_phase: str | None = None

        def _score_to_cp(info):
            """Return (centipawns, is_mate) from White's POV, capped at 10000."""
            score = info.get("score")
            if score is None:
                return None, False
            try:
                if score.is_mate():
                    mate_val = score.pov(chess.WHITE).mate()
                    if mate_val is None:
                        return None, False
                    cp_val = 10000 if mate_val > 0 else -10000
                    return cp_val, True
                cp = score.pov(chess.WHITE).cp
                if cp is None:
                    return None, False
                if cp > 10000:
                    cp = 10000
                if cp < -10000:
                    cp = -10000
                return cp, False
            except Exception:
                return None, False

        for move_index, move_san in enumerate(moves):
            try:
                # eval before the move
                info_before = engine.analyse(board, chess.engine.Limit(depth=ANALYSIS_DEPTH))
                eval_before, is_mate_before = _score_to_cp(info_before)

                # Keep board snapshot for heuristics (no extra engine calls)
                board_before = board.copy()

                # parse SAN and push move
                try:
                    move_obj = board.parse_san(move_san)
                except Exception:
                    break

                # Determine piece moved (from the current board before the push)
                try:
                    piece_obj = board.piece_at(move_obj.from_square)
                    piece_map = {
                        chess.PAWN: 'Pawn',
                        chess.KNIGHT: 'Knight',
                        chess.BISHOP: 'Bishop',
                        chess.ROOK: 'Rook',
                        chess.QUEEN: 'Queen',
                        chess.KING: 'King',
                    }
                    piece_name = piece_map.get(piece_obj.piece_type, 'Unknown') if piece_obj is not None else 'Unknown'
                except Exception:
                    piece_name = 'Unknown'

                board.push(move_obj)
                board_after = board.copy()

                # eval after the move
                try:
                    info_after = engine.analyse(board, chess.engine.Limit(depth=ANALYSIS_DEPTH))
                except Exception:
                    break

                eval_after, is_mate_after = _score_to_cp(info_after)

                # If we couldn't obtain evals, skip
                if eval_before is None or eval_after is None:
                    continue

                # Determine whose move it was (0-indexed: even = white, odd = black)
                is_white_move = (move_index % 2 == 0)

                # Compute centipawn loss for player who just moved
                if is_white_move:
                    cp_loss = eval_before - eval_after
                else:
                    cp_loss = eval_after - eval_before

                move_number = (move_index // 2) + 1
                move_color = "White" if is_white_move else "Black"

                # Board-state phase classification (stable, cached)
                ply = move_index + 1
                phase = phase_cache.get(ply)
                if phase is None:
                    phase = classify_phase_stable(board_after, move_number, prev_phase)
                    phase_cache[ply] = phase
                prev_phase = phase

                # Mate handling: separate from CPL aggregation
                missed_mate = False
                forced_loss = False
                is_mate_eval = is_mate_before or is_mate_after or abs(eval_before) >= 9000 or abs(eval_after) >= 9000
                if is_mate_eval:
                    if (is_white_move and eval_before is not None and eval_before >= 9000) or (not is_white_move and eval_before is not None and eval_before <= -9000):
                        if not (is_mate_after or (is_white_move and eval_after is not None and eval_after >= 5000) or ((not is_white_move) and eval_after is not None and eval_after <= -5000)):
                            missed_mate = True
                    if (is_white_move and eval_before is not None and eval_before <= -9000) or (not is_white_move and eval_before is not None and eval_before >= 9000):
                        forced_loss = True
                    if DEBUG_ENGINE:
                        print(f"[mate-excluded] move {move_number} {move_color} {move_san} eval_before={eval_before} eval_after={eval_after}")

                cp_loss_capped = 0
                cp_loss_weighted = 0.0
                if not is_mate_eval and cp_loss > 0:
                    cp_loss_capped = min(int(abs(cp_loss)), 10000)
                    eval_before_player = eval_before if is_white_move else -eval_before

                    # Context-aware weighting: losing states count less; winning endgames count more.
                    cpl_weight = 1.0
                    if forced_loss:
                        cpl_weight = 0.25
                    elif eval_before_player <= -600:
                        cpl_weight = 0.5
                    elif eval_before_player < -300:
                        cpl_weight = 0.7
                    elif eval_before_player > 100:
                        cpl_weight = 1.3

                    if phase == "endgame":
                        if eval_before_player >= 150:
                            cpl_weight *= 1.3
                        elif eval_before_player <= -150:
                            cpl_weight *= 0.6

                    cp_loss_weighted = cp_loss_capped * cpl_weight

                blunder_type = None
                blunder_subtype = None
                thresholds = PHASE_THRESHOLDS.get(phase, {"blunder": BLUNDER_THRESHOLD, "mistake": MISTAKE_THRESHOLD})
                loss_for_threshold = cp_loss_capped

                if loss_for_threshold >= thresholds.get("blunder", BLUNDER_THRESHOLD):
                    blunder_type = "blunder"
                    blunder_subtype = classify_blunder(board_before, board_after, move_obj, eval_before, eval_after, phase)
                elif loss_for_threshold >= thresholds.get("mistake", MISTAKE_THRESHOLD):
                    blunder_type = "mistake"
                else:
                    blunder_type = "inaccuracy"

                move_quality = classify_move(cp_loss_capped) if cp_loss_capped > 0 else "Best"
                move_data = {
                    "move_num": move_number,
                    "color": move_color,
                    "san": move_san,
                    "cp_loss": cp_loss_capped,
                    "cp_loss_weighted": cp_loss_weighted,
                    "piece": piece_name,
                    "phase": phase,
                    "blunder_type": blunder_type,
                    "blunder_subtype": blunder_subtype,
                    "move_quality": move_quality,
                    "eval_before": eval_before,
                    "eval_after": eval_after,
                    "is_mate_before": is_mate_before,
                    "is_mate_after": is_mate_after,
                    "missed_mate": missed_mate,
                    "forced_loss": forced_loss,
                }

                move_evals.append(move_data)

            except Exception:
                break

        return move_evals
    
    finally:
        engine.quit()


def analyze_game(moves_pgn_str):
    """
    Analyze a game using Stockfish and print results (backward compatibility).
    
    Args:
        moves_pgn_str: Space-separated SAN moves
            
    Returns:
        None (prints analysis to stdout)
    """
    from collections import Counter
    
    move_evals = analyze_game_detailed(moves_pgn_str)
    
    if not move_evals:
        print("\n⚠️  No moves available for analysis.")
        return

    # Extract blunders and mistakes for printing
    blunders = [m for m in move_evals if m["blunder_type"] == "blunder"]
    mistakes = [m for m in move_evals if m["blunder_type"] == "mistake"]
    cp_losses = [m["cp_loss"] for m in move_evals]

    # Aggregate move quality counts and percentages
    move_qualities = [m.get("move_quality") for m in move_evals if m.get("move_quality")]
    total_moves = len(move_qualities)
    quality_order = ["Best", "Excellent", "Good", "Inaccuracy", "Mistake", "Blunder"]
    quality_counts = Counter(move_qualities)
    quality_stats = []
    if total_moves > 0:
        for q in quality_order:
            count = quality_counts.get(q, 0)
            percent = int(round(100 * count / total_moves))
            quality_stats.append((q, count, percent))

    # Move quality by phase
    phase_quality = {"opening": Counter(), "middlegame": Counter(), "endgame": Counter()}
    for m in move_evals:
        q = m.get("move_quality")
        p = m.get("phase")
        if q and p in phase_quality:
            phase_quality[p][q] += 1

    # Aggregate blunder subtypes
    blunder_subtypes = [m["blunder_subtype"] for m in blunders if m["blunder_subtype"]]
    subtype_counts = Counter(blunder_subtypes)
    total_blunders = len(blunders)
    blunder_type_stats = []
    if total_blunders > 0:
        for subtype, count in subtype_counts.items():
            percent = int(round(100 * count / total_blunders))
            blunder_type_stats.append((subtype, count, percent))
        unknown_count = sum(1 for m in blunders if not m["blunder_subtype"] or m["blunder_subtype"] == "Unknown")
        if unknown_count > 0:
            percent = int(round(100 * unknown_count / total_blunders))
            blunder_type_stats.append(("Unknown", unknown_count, percent))
        blunder_type_stats.sort(key=lambda x: -x[1])

    # Print results
    print("\n" + "=" * 70)
    print("ENGINE ANALYSIS - Most Recent Game")
    print("=" * 70)
    print(f"Moves:   {len(moves_pgn_str.strip().split())}")
    print()

    print("ANALYSIS RESULTS:")
    print("-" * 70)

    # Print move quality breakdown
    if quality_stats:
        print("\nMOVE QUALITY BREAKDOWN:")
        for q, count, percent in quality_stats:
            print(f"{q:<11s} {count:4d} ({percent:2d}%)")

    # Print move quality by phase
    if total_moves > 0:
        print("\nMOVE QUALITY BY PHASE:")
        for phase in ["opening", "middlegame", "endgame"]:
            phase_total = sum(phase_quality[phase].values())
            if phase_total == 0:
                continue
            print(f"  {phase.capitalize():<10s}")
            for q in quality_order:
                count = phase_quality[phase].get(q, 0)
                percent = int(round(100 * count / phase_total)) if phase_total else 0
                print(f"    {q:<11s} {count:4d} ({percent:2d}%)")

    # Blunder type summary
    if blunder_type_stats:
        print("\nBLUNDER TYPES:")
        for subtype, count, percent in blunder_type_stats:
            print(f"- {subtype}: {count} ({percent}%)")

    if blunders:
        print(f"\n🔴 BLUNDERS ({len(blunders)}):")
        for b in blunders:
            subtype = b.get('blunder_subtype')
            subtype_str = f" [{subtype}]" if subtype else ""
            print(f"   {b['move_num']:2d}. {b['color']:5s} {b['san']:6s} (lost {b['cp_loss']:4d} cp){subtype_str}")
    else:
        print("\n🔴 BLUNDERS: None")

    if mistakes:
        print(f"\n🟡 MISTAKES ({len(mistakes)}):")
        for m in mistakes:
            print(f"   {m['move_num']:2d}. {m['color']:5s} {m['san']:6s} (lost {m['cp_loss']:4d} cp)")
    else:
        print("\n🟡 MISTAKES: None")

    if cp_losses:
        avg_loss = sum(cp_losses) / len(cp_losses)
        max_loss = max(cp_losses)
        print(f"\n📊 STATISTICS:")
        print(f"   Average centipawn loss: {avg_loss:6.1f} cp")
        print(f"   Maximum centipawn loss: {max_loss:6d} cp")
        print(f"   Positions analyzed:     {len(cp_losses):6d}")
    else:
        print("\n📊 STATISTICS:")
        print("   No significant centipawn losses found!")

    print("\n" + "=" * 70)
