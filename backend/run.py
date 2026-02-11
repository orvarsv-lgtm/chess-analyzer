"""
Run the Chess Analyzer API server.

Usage:
  cd backend
  uvicorn run:app --reload --port 8000
"""

from app.main import app
