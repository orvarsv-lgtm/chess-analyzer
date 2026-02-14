#!/usr/bin/env python3
"""
Backfill existing puzzles with tactic tags and update blunder subtypes.

This script:
1. Re-tags all existing puzzles with the new tactic detection engine
2. Updates difficulty to 'standard' for all puzzles
3. Re-classifies blunder subtypes on existing move evaluations

Usage:
    DATABASE_URL=... python backfill_tactics.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import chess

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.analysis_core import detect_puzzle_tactics, classify_blunder_subtype

DATABASE_URL = os.getenv("DATABASE_URL", "")


async def backfill_puzzle_tactics():
    if not DATABASE_URL:
        print("❌ DATABASE_URL not set")
        sys.exit(1)

    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # 1. Fetch all puzzles
        result = await db.execute(
            text("SELECT id, fen, best_move_uci, solution_line, themes FROM puzzles")
        )
        puzzles = result.fetchall()
        print(f"📊 Found {len(puzzles)} puzzles to backfill")

        updated = 0
        for p in puzzles:
            pid, fen, best_move_uci, solution_line, old_themes = p

            if not fen or not best_move_uci:
                continue

            # Parse solution_line
            sol = []
            if solution_line:
                if isinstance(solution_line, str):
                    try:
                        sol = json.loads(solution_line)
                    except Exception:
                        sol = []
                elif isinstance(solution_line, list):
                    sol = solution_line

            # Detect new tactic tags
            new_tags = detect_puzzle_tactics(fen, best_move_uci, sol)

            if new_tags != old_themes:
                await db.execute(
                    text("UPDATE puzzles SET themes = :themes, difficulty = 'standard' WHERE id = :id"),
                    {"themes": json.dumps(new_tags), "id": pid}
                )
                updated += 1

        await db.commit()
        print(f"✅ Updated {updated} puzzles with new tactic tags")

        # 2. Re-classify blunder subtypes
        result2 = await db.execute(
            text("""
                SELECT me.id, me.fen_before, me.san, me.best_move_uci, me.phase
                FROM move_evaluations me
                WHERE me.move_quality = 'Blunder'
                  AND me.fen_before IS NOT NULL
                  AND me.san IS NOT NULL
            """)
        )
        blunders = result2.fetchall()
        print(f"\n📊 Found {len(blunders)} blunders to re-classify")

        reclassified = 0
        for b in blunders:
            bid, fen_before, san, best_move_uci, phase = b

            if not fen_before:
                continue

            try:
                board = chess.Board(fen_before)
                move = board.parse_san(san)
                best_move = chess.Move.from_uci(best_move_uci) if best_move_uci else None

                new_subtype = classify_blunder_subtype(board, move, best_move, phase or "middlegame")

                await db.execute(
                    text("UPDATE move_evaluations SET blunder_subtype = :subtype WHERE id = :id"),
                    {"subtype": new_subtype, "id": bid}
                )
                reclassified += 1
            except Exception:
                continue

        await db.commit()
        print(f"✅ Re-classified {reclassified} blunder subtypes")

    await engine.dispose()
    print("\n🎉 Backfill complete!")


if __name__ == "__main__":
    asyncio.run(backfill_puzzle_tactics())
