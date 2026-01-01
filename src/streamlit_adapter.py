from __future__ import annotations

import io
import os
from contextlib import redirect_stderr, redirect_stdout


def run_existing_analysis(*, source: str, pgn_path: str, max_games: int) -> dict:
    """Run the existing analyzer pipeline without any interactive I/O.

    This is a Streamlit-safe adapter around the existing CLI functions.

    Notes on parameters (kept intentionally minimal for compatibility):
    - If source == "Lichess username": pgn_path is interpreted as the username.
    - If source == "Chess.com PGN file": pgn_path is interpreted as a filesystem path.

    Returns a structured dict containing (at minimum) the captured CLI output
    and the names of the files written by the analyzer.
    """

    import main as cli_main

    src = (source or "").strip()
    max_games_i = int(max_games)

    # Derive name used for output filenames.
    output_name: str
    if src == "Lichess username":
        output_name = (pgn_path or "").strip()
    else:
        output_name = os.path.splitext(os.path.basename(pgn_path or ""))[0] or "analysis"

    stdout_buf = io.StringIO()
    with redirect_stdout(stdout_buf), redirect_stderr(stdout_buf):
        if src == "Lichess username":
            username = (pgn_path or "").strip()
            csv_file, game_count = cli_main.fetch_user_games(username, max_games=max_games_i)
        else:
            csv_file, game_count = cli_main.import_pgn_games(pgn_path, output_name)

        if not csv_file or int(game_count or 0) == 0:
            return {
                "ok": False,
                "exit_code": 1,
                "source": src,
                "name": output_name,
                "max_games": max_games_i,
                "output_text": stdout_buf.getvalue(),
                "csv_file": None,
                "analysis_file": None,
            }

        phase1_result = cli_main.run_phase1_for_user(output_name, csv_file, max_games=max_games_i)
        if not phase1_result:
            return {
                "ok": False,
                "exit_code": 1,
                "source": src,
                "name": output_name,
                "max_games": max_games_i,
                "output_text": stdout_buf.getvalue(),
                "csv_file": csv_file,
                "analysis_file": None,
            }

        _ = cli_main.run_phase2_for_user(
            output_name,
            max_games=max_games_i,
            games_data=phase1_result.get("games_data"),
        )

    return {
        "ok": True,
        "exit_code": 0,
        "source": src,
        "name": output_name,
        "max_games": max_games_i,
        "output_text": stdout_buf.getvalue(),
        "csv_file": f"games_{output_name}.csv",
        "analysis_file": f"{output_name}_analysis.txt",
    }


def run_analysis_streamlit(source, pgn_path, max_games):
    """Streamlit adapter.

    Must NOT use input() or print().
    Returns structured results.
    """
    results = run_existing_analysis(
        source=source,
        pgn_path=pgn_path,
        max_games=max_games,
    )
    return results
