"""Internationalization (i18n) support for Chess Analyzer.

English is the default language. Icelandic is also supported.
"""
from __future__ import annotations

import streamlit as st
from typing import Dict

# Language codes
ENGLISH = "en"
ICELANDIC = "is"

SUPPORTED_LANGUAGES = {
    ENGLISH: "English",
    ICELANDIC: "Íslenska",
}

# Translation dictionary
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # App title and header
    "app_title": {
        "en": "Chess Analyzer",
        "is": "Skákgreining",
    },
    "contact_us": {
        "en": "Contact us",
        "is": "Hafðu samband",
    },
    
    # Navigation / Tabs
    "tab_analysis": {
        "en": "Analysis",
        "is": "Greining",
    },
    "tab_puzzles": {
        "en": "Puzzles",
        "is": "Þrautir",
    },
    "tab_ai_coach": {
        "en": "AI Coach",
        "is": "Gervigreindarvagna",
    },
    "tab_openings": {
        "en": "Openings",
        "is": "Opnanir",
    },
    "tab_replayer": {
        "en": "Replayer",
        "is": "Endurspilun",
    },
    
    # Inputs section
    "inputs": {
        "en": "Inputs",
        "is": "Inntak",
    },
    "load_previous_analysis": {
        "en": "Load Previous Analysis",
        "is": "Hlaða fyrri greiningu",
    },
    "source": {
        "en": "Source",
        "is": "Heimild",
    },
    "lichess_username": {
        "en": "Lichess username",
        "is": "Lichess notendanafn",
    },
    "chess_com_pgn": {
        "en": "Chess.com PGN file",
        "is": "Chess.com PGN skrá",
    },
    "max_games": {
        "en": "Max games",
        "is": "Hámarksfjöldi leikja",
    },
    "engine_depth": {
        "en": "Engine depth (recommended 15)",
        "is": "Véladýpt (mælt með 15)",
    },
    "run_analysis": {
        "en": "Run analysis",
        "is": "Keyra greiningu",
    },
    "upload_pgn": {
        "en": "Upload PGN file(s)",
        "is": "Hlaða upp PGN skrá(m)",
    },
    
    # Auth
    "sign_in": {
        "en": "Sign In",
        "is": "Skrá inn",
    },
    "sign_out": {
        "en": "Sign Out",
        "is": "Skrá út",
    },
    "sign_up": {
        "en": "Sign Up",
        "is": "Nýskráning",
    },
    "email": {
        "en": "Email",
        "is": "Netfang",
    },
    "password": {
        "en": "Password",
        "is": "Lykilorð",
    },
    "magic_link": {
        "en": "Magic Link",
        "is": "Töfratengill",
    },
    "send_magic_link": {
        "en": "Send Magic Link",
        "is": "Senda töfratengil",
    },
    
    # Analysis results
    "results": {
        "en": "Results",
        "is": "Niðurstöður",
    },
    "games_analyzed": {
        "en": "Games Analyzed",
        "is": "Leikir greindir",
    },
    "total_moves": {
        "en": "Total Moves",
        "is": "Heildarfjöldi leikja",
    },
    "average_cpl": {
        "en": "Average CPL",
        "is": "Meðal CPL",
    },
    "win_rate": {
        "en": "Win Rate",
        "is": "Sigurhlutfall",
    },
    "opening": {
        "en": "Opening",
        "is": "Opnun",
    },
    "middlegame": {
        "en": "Middlegame",
        "is": "Miðleikur",
    },
    "endgame": {
        "en": "Endgame",
        "is": "Lokatafla",
    },
    
    # Puzzles
    "puzzle_trainer": {
        "en": "Puzzle Trainer",
        "is": "Þrautaþjálfun",
    },
    "my_games": {
        "en": "My games",
        "is": "Mínir leikir",
    },
    "other_users": {
        "en": "Other users",
        "is": "Aðrir notendur",
    },
    "generate_puzzles": {
        "en": "Generate Puzzles",
        "is": "Búa til þrautir",
    },
    "your_turn": {
        "en": "Your turn",
        "is": "Þú átt leik",
    },
    "correct": {
        "en": "Correct!",
        "is": "Rétt!",
    },
    "incorrect": {
        "en": "Incorrect",
        "is": "Rangt",
    },
    "hint": {
        "en": "Hint",
        "is": "Vísbending",
    },
    "solution": {
        "en": "Solution",
        "is": "Lausn",
    },
    "next_puzzle": {
        "en": "Next Puzzle",
        "is": "Næsta þraut",
    },
    "difficulty": {
        "en": "Difficulty",
        "is": "Erfiðleikastig",
    },
    "easy": {
        "en": "Easy",
        "is": "Auðvelt",
    },
    "medium": {
        "en": "Medium",
        "is": "Miðlungs",
    },
    "hard": {
        "en": "Hard",
        "is": "Erfitt",
    },
    
    # AI Coach
    "ai_coach_title": {
        "en": "AI Chess Coach",
        "is": "Gervigreindarþjálfari",
    },
    "single_game_review": {
        "en": "Single Game Review",
        "is": "Einstakleikjayfirlit",
    },
    "career_analysis": {
        "en": "Full Career Analysis",
        "is": "Full ferilgreining",
    },
    "generate_review": {
        "en": "Generate AI Coach Review",
        "is": "Búa til þjálfaramat",
    },
    "game_summary": {
        "en": "Game Summary",
        "is": "Leikjayfirlit",
    },
    "key_moments": {
        "en": "Key Moments",
        "is": "Lykilatvik",
    },
    "opening_advice": {
        "en": "Opening Advice",
        "is": "Opnunarráð",
    },
    "strategic_advice": {
        "en": "Strategic Advice",
        "is": "Stefnuráð",
    },
    "tactical_advice": {
        "en": "Tactical Advice",
        "is": "Taktíkráð",
    },
    "training_recommendations": {
        "en": "Training Recommendations",
        "is": "Æfingatillögur",
    },
    "choose_game": {
        "en": "Choose a game",
        "is": "Veldu leik",
    },
    "analyzing_as": {
        "en": "Analyzing your game as",
        "is": "Greini leikinn þinn sem",
    },
    "rating": {
        "en": "Rating",
        "is": "Stigafjöldi",
    },
    
    # Game info
    "white": {
        "en": "White",
        "is": "Hvítur",
    },
    "black": {
        "en": "Black",
        "is": "Svartur",
    },
    "result": {
        "en": "Result",
        "is": "Úrslit",
    },
    "moves": {
        "en": "Moves",
        "is": "Leikir",
    },
    "date": {
        "en": "Date",
        "is": "Dagsetning",
    },
    "game_info": {
        "en": "Game Info",
        "is": "Leikjaupplýsingar",
    },
    
    # Saved analyses
    "saved_analyses": {
        "en": "Your Saved Analyses",
        "is": "Vistaðar greiningar",
    },
    "no_saved_analyses": {
        "en": "No saved analyses yet. Run an analysis to save it.",
        "is": "Engar vistaðar greiningar. Keyrðu greiningu til að vista.",
    },
    "load_analysis": {
        "en": "Load Analysis",
        "is": "Hlaða greiningu",
    },
    "delete": {
        "en": "Delete",
        "is": "Eyða",
    },
    "analysis_saved": {
        "en": "Analysis saved",
        "is": "Greining vistuð",
    },
    "analysis_updated": {
        "en": "Analysis updated",
        "is": "Greining uppfærð",
    },
    
    # Errors and status
    "error": {
        "en": "Error",
        "is": "Villa",
    },
    "loading": {
        "en": "Loading...",
        "is": "Hleður...",
    },
    "please_enter_username": {
        "en": "Please enter a username",
        "is": "Vinsamlegast sláðu inn notendanafn",
    },
    "please_upload_file": {
        "en": "Please upload at least one PGN file",
        "is": "Vinsamlegast hladdu upp að minnsta kosti einni PGN skrá",
    },
    "analysis_complete": {
        "en": "Analysis complete",
        "is": "Greiningu lokið",
    },
    "cache_hit": {
        "en": "Using cached analysis",
        "is": "Nota vistuða greiningu",
    },
    
    # Language selector
    "language": {
        "en": "Language",
        "is": "Tungumál",
    },
    
    # Misc
    "vs": {
        "en": "vs",
        "is": "gegn",
    },
    "game": {
        "en": "Game",
        "is": "Leikur",
    },
    "games": {
        "en": "games",
        "is": "leikir",
    },
    "depth": {
        "en": "depth",
        "is": "dýpt",
    },
}


def get_language() -> str:
    """Get the current language from session state."""
    return st.session_state.get("language", ENGLISH)


def set_language(lang: str) -> None:
    """Set the current language."""
    if lang in SUPPORTED_LANGUAGES:
        st.session_state["language"] = lang


def t(key: str) -> str:
    """Translate a key to the current language.
    
    Args:
        key: Translation key
        
    Returns:
        Translated string, or the key itself if not found
    """
    lang = get_language()
    translation = TRANSLATIONS.get(key, {})
    
    # Try current language, fall back to English, then to key
    return translation.get(lang) or translation.get(ENGLISH) or key


def render_language_selector() -> None:
    """Render the language selector in the sidebar."""
    with st.sidebar:
        current_lang = get_language()
        
        # Use a selectbox with language names
        lang_options = list(SUPPORTED_LANGUAGES.keys())
        lang_names = list(SUPPORTED_LANGUAGES.values())
        
        current_idx = lang_options.index(current_lang) if current_lang in lang_options else 0
        
        selected_name = st.selectbox(
            f"🌐 {t('language')}",
            lang_names,
            index=current_idx,
            key="language_selector",
        )
        
        # Find the language code for the selected name
        selected_lang = lang_options[lang_names.index(selected_name)]
        
        if selected_lang != current_lang:
            set_language(selected_lang)
            st.rerun()
