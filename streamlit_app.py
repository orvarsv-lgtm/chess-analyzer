from __future__ import annotations

import os
import re
import tempfile

import streamlit as st

from src.streamlit_adapter import run_analysis_streamlit


def main() -> None:
    st.title("Chess Analyzer")

    source = st.radio("Source", ["Lichess username", "Chess.com PGN file"])
    max_games = st.number_input("Max games", min_value=1, max_value=50, value=10, step=1)

    if source == "Lichess username":
        username = st.text_input("Lichess username")
        if st.button("Run analysis"):
            results = run_analysis_streamlit(source=source, pgn_path=username, max_games=max_games)
            st.json(results)

    else:
        uploaded = st.file_uploader("Upload PGN", type=["pgn"])
        if st.button("Run analysis"):
            if not uploaded:
                st.error("Please upload a PGN file.")
                return

            original_stem = os.path.splitext(uploaded.name or "uploaded")[0]
            safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", original_stem).strip("_") or "uploaded"

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pgn", prefix=f"{safe_stem}_") as tmp:
                tmp.write(uploaded.getvalue())
                tmp_path = tmp.name

            try:
                results = run_analysis_streamlit(source=source, pgn_path=tmp_path, max_games=max_games)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

            st.json(results)


if __name__ == "__main__":
    main()

