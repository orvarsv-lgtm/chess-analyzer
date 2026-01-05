from __future__ import annotations

import streamlit as st
import chess

from ui.chessboard_component import render_chessboard


st.set_page_config(page_title="Chessboard Debug", layout="centered")

st.title("Chessboard Debug")
st.caption("Use this to verify click-to-move emits UCI without refreshing weirdly.")

# A simple, legal position with some obvious moves.
default_fen = chess.STARTING_FEN
fen = st.text_input("FEN", value=default_fen)

try:
    board = chess.Board(fen)
except Exception as e:
    st.error(f"Invalid FEN: {e}")
    st.stop()

orientation = st.selectbox("Orientation", ["white", "black"], index=0)
side_to_move = "w" if board.turn == chess.WHITE else "b"

legal_moves = [m.uci() for m in board.legal_moves]

st.write(f"Side to move: **{side_to_move}**")
st.write(f"Legal moves: **{len(legal_moves)}**")

uci = render_chessboard(
    fen=fen,
    legal_moves=legal_moves,
    orientation=orientation,
    side_to_move=side_to_move,
    highlights={"correct_squares": [], "incorrect_squares": []},
    hint="Click a piece then a destination square.",
    key="debug_board_v1",
)

st.write("---")
st.subheader("Last emitted move")
st.write(uci if uci else "(none)")

if uci:
    try:
        mv = chess.Move.from_uci(uci)
        if mv in board.legal_moves:
            st.success("Move is legal in this position")
        else:
            st.warning("Move is NOT legal in this position")
    except Exception as e:
        st.error(f"Bad UCI emitted: {e}")
