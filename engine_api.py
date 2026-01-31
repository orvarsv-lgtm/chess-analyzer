#!/usr/bin/env python3
"""
FastAPI backend for remote Stockfish analysis on VPS.

This backend:
1. Accepts POST /analyze_game with PGN in JSON format
2. Runs Stockfish analysis locally on the VPS
3. Returns structured JSON response with per-move evals
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import chess
import chess.pgn
from io import StringIO
import os

app = FastAPI(title="Chess Analyzer Engine API")

# Path to Stockfish binary
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "/usr/games/stockfish")


class AnalyzeRequest(BaseModel):
    """Request body for /analyze_game"""
    pgn: str
    max_games: int = 1


class MoveAnalysis(BaseModel):
    """Single move analysis"""
    move_san: str
    score_cp: int
    fen: str


class AnalyzeResponse(BaseModel):
    """Response from /analyze_game"""
    success: bool
    games_analyzed: int
    total_moves: int
    analysis: List[Dict[str, Any]]
    headers: Dict[str, str]
    engine_source: str = "remote"


@app.get("/")
def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "chess-analyzer-engine", "version": "1.0"}


@app.post("/analyze_game", response_model=AnalyzeResponse)
def analyze_game(request: AnalyzeRequest, depth: int = Query(15, ge=10, le=20)):
    """
    Analyze a single game via Stockfish.
    
    Parameters:
    - pgn: PGN text of the game
    - max_games: Number of games to analyze (currently always 1 per request)
    - depth: Search depth for Stockfish (10-20, default 15)
    
    Returns:
    - success: True if analysis completed
    - analysis: List of move evaluations
    - headers: Game headers (White, Black, Result, etc.)
    - games_analyzed: Number of games processed
    - total_moves: Total moves analyzed
    """
    
    if not request.pgn or not isinstance(request.pgn, str):
        raise HTTPException(status_code=400, detail="PGN must be non-empty string")
    
    # Parse PGN
    try:
        game = chess.pgn.read_game(StringIO(request.pgn))
        if not game:
            raise HTTPException(status_code=400, detail="No valid PGN game found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PGN parse error: {str(e)}")
    
    # Clamp depth
    depth_clamped = max(10, min(20, depth))
    
    # Open Stockfish engine
    try:
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail=f"Stockfish binary not found at {STOCKFISH_PATH}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Engine startup failed: {str(e)}")
    
    analysis: List[Dict[str, Any]] = []
    total_moves = 0
    
    try:
        board = game.board()
        for move in game.mainline_moves():
            try:
                move_san = board.san(move)
            except Exception:
                move_san = ""
            
            board.push(move)
            total_moves += 1
            
            try:
                info = engine.analyse(board, chess.engine.Limit(depth=depth_clamped))
            except Exception:
                break
            
            # Extract score
            score_cp = 0
            score = info.get("score")
            if score is not None:
                try:
                    if score.is_mate():
                        mate_val = score.pov(chess.WHITE).mate()
                        if mate_val is not None:
                            score_cp = 10000 if mate_val > 0 else -10000
                    else:
                        cp = score.pov(chess.WHITE).cp
                        score_cp = int(cp) if cp is not None else 0
                except Exception:
                    score_cp = 0
            
            analysis.append(
                {
                    "move_san": move_san or "",
                    "score_cp": score_cp,
                    "fen": board.fen(),
                }
            )
    
    finally:
        try:
            engine.quit()
        except Exception:
            pass
    
    return {
        "success": True,
        "games_analyzed": 1,
        "total_moves": total_moves,
        "analysis": analysis,
        "headers": dict(game.headers),
        "engine_source": "remote",
    }


@app.get("/openapi.json", include_in_schema=False)
def get_openapi():
    """Expose OpenAPI schema for debugging"""
    return app.openapi()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
