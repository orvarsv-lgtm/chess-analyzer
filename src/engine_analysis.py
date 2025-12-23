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
def classify_blunder(board, move, eval_before, eval_after):
    """
    Classify a blunder into one of:
    - "Hanging piece"
    - "Missed tactic"
    - "King safety"
    - "Endgame technique"
    - "Unknown"
    Args:
        board: chess.Board before the move
        move: chess.Move played
        eval_before: evaluation before move (centipawns)
        eval_after: evaluation after move (centipawns)
    Returns:
        blunder_type (str)
    """
    import chess
    # Heuristic: Hanging piece
    # If a piece is captured and not recaptured next move, and material drops
    piece_lost = False
    if board.is_capture(move):
        # What piece is being captured?
        captured_piece = board.piece_at(move.to_square)
        if captured_piece and captured_piece.piece_type != chess.PAWN:
            # Check if material drops after the move
            board_copy = board.copy()
            board_copy.push(move)
            material_before = sum([piece.piece_type for piece in board.piece_map().values()])
            material_after = sum([piece.piece_type for piece in board_copy.piece_map().values()])
            if material_after < material_before:
                piece_lost = True
    if piece_lost:
        return "Hanging piece"

    # Heuristic: Endgame technique
    # If few pieces remain and eval swing > 200 cp
    board_copy = board.copy()
    board_copy.push(move)
    non_pawn_pieces = sum(1 for p in board_copy.piece_map().values() if p.piece_type != chess.PAWN)
    if non_pawn_pieces <= 6 and abs(eval_before - eval_after) > 200:
        return "Endgame technique"

    # Heuristic: Missed tactic
    # If eval swing > 300 and best move is tactical (capture, check, threat)
    if abs(eval_before - eval_after) > 300:
        # Try to find if best move is tactical
        # We'll assume best move is a capture or check if available
        for candidate in board.legal_moves:
            if board.is_capture(candidate) or board.gives_check(candidate):
                return "Missed tactic"

    # Heuristic: King safety
    # If king is exposed after move, or new checks/mating threats appear
    board_copy = board.copy()
    board_copy.push(move)
    king_square = board_copy.king(board.turn)
    if king_square is not None:
        attackers = board_copy.attackers(not board.turn, king_square)
        if len(attackers) > 0:
            return "King safety"

    return "Unknown"
import chess
import chess.engine
from .performance_metrics import classify_move_phase

# Stockfish configuration
STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"
ANALYSIS_DEPTH = 15

# Centipawn thresholds
BLUNDER_THRESHOLD = 300
MISTAKE_THRESHOLD = 150


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

        def _score_to_cp(info):
            """Return evaluation in centipawns from White's POV, capped at 10000."""
            score = info.get("score")
            if score is None:
                return None
            try:
                if score.is_mate():
                    mate_val = score.pov(chess.WHITE).mate()
                    if mate_val is None:
                        return None
                    return 10000 if mate_val > 0 else -10000
                cp = score.pov(chess.WHITE).cp
                if cp is None:
                    return None
                if cp > 10000:
                    return 10000
                if cp < -10000:
                    return -10000
                return cp
            except Exception:
                return None

        for move_index, move_san in enumerate(moves):
            try:
                # eval before the move
                info_before = engine.analyse(board, chess.engine.Limit(depth=ANALYSIS_DEPTH))
                eval_before = _score_to_cp(info_before)

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

                # eval after the move
                try:
                    info_after = engine.analyse(board, chess.engine.Limit(depth=ANALYSIS_DEPTH))
                except Exception:
                    break

                eval_after = _score_to_cp(info_after)

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

                # Classify move quality

                blunder_type = None
                blunder_subtype = None
                if cp_loss >= BLUNDER_THRESHOLD:
                    blunder_type = "blunder"
                    # Classify blunder subtype
                    blunder_subtype = classify_blunder(board, move_obj, eval_before, eval_after)
                elif cp_loss >= MISTAKE_THRESHOLD:
                    blunder_type = "mistake"
                elif cp_loss > 0:
                    blunder_type = "inaccuracy"

                # normalize to positive loss when player made worse move
                if cp_loss > 0:
                    # cap cp_loss to avoid skew
                    cp_loss_capped = min(int(abs(cp_loss)), 10000)

                    move_number = (move_index // 2) + 1
                    move_color = "White" if is_white_move else "Black"
                    phase = classify_move_phase(move_index)


                    move_quality = classify_move(cp_loss_capped)
                    move_data = {
                        "move_num": move_number,
                        "color": move_color,
                        "san": move_san,
                        "cp_loss": cp_loss_capped,
                        "piece": piece_name,
                        "phase": phase,
                        "blunder_type": blunder_type,
                        "blunder_subtype": blunder_subtype,
                        "move_quality": move_quality,
                        "eval_before": eval_before,
                        "eval_after": eval_after,
                    }

                    move_evals.append(move_data)

            except Exception:
                break

        return move_evals
    
    finally:
        engine.quit()


def analyze_game(moves_pgn_str):
    # (Optional) Move quality by phase
    phase_quality = {"opening": Counter(), "middlegame": Counter(), "endgame": Counter()}
    for m in move_evals:
        q = m.get("move_quality")
        p = m.get("phase")
        if q and p in phase_quality:
            phase_quality[p][q] += 1
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
    # Print move quality breakdown
    if quality_stats:
        print("\nMOVE QUALITY BREAKDOWN:")
        for q, count, percent in quality_stats:
            print(f"{q:<11s} {count:4d} ({percent:2d}%)")
        # Aggregate move quality counts and percentages
        from collections import Counter
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
    """
    Analyze a game using Stockfish and print results (backward compatibility).
    
    Args:
        moves_pgn_str: Space-separated SAN moves
            
    Returns:
        None (prints analysis to stdout)
    """
    move_evals = analyze_game_detailed(moves_pgn_str)
    
    if not move_evals:
        print("\n⚠️  No moves available for analysis.")
        return
    

    # Extract blunders and mistakes for printing
    blunders = [m for m in move_evals if m["blunder_type"] == "blunder"]
    mistakes = [m for m in move_evals if m["blunder_type"] == "mistake"]
    cp_losses = [m["cp_loss"] for m in move_evals]

    # Aggregate blunder subtypes
    from collections import Counter
    blunder_subtypes = [m["blunder_subtype"] for m in blunders if m["blunder_subtype"]]
    subtype_counts = Counter(blunder_subtypes)
    total_blunders = len(blunders)
    blunder_type_stats = []
    if total_blunders > 0:
        for subtype, count in subtype_counts.items():
            percent = int(round(100 * count / total_blunders))
            blunder_type_stats.append((subtype, count, percent))
        # Add 'Unknown' if any blunders unclassified
        unknown_count = sum(1 for m in blunders if not m["blunder_subtype"] or m["blunder_subtype"] == "Unknown")
        if unknown_count > 0:
            percent = int(round(100 * unknown_count / total_blunders))
            blunder_type_stats.append(("Unknown", unknown_count, percent))
        # Sort by count descending
        blunder_type_stats.sort(key=lambda x: -x[1])
    

    # Print results
    print("\n" + "=" * 70)
    print("ENGINE ANALYSIS - Most Recent Game")
    print("=" * 70)
    print(f"Moves:   {len(moves_pgn_str.strip().split())}")
    print()

    print("ANALYSIS RESULTS:")
    print("-" * 70)

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
