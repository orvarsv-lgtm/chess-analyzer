"""
Opening classifier for chess games.
Matches move sequences to known openings using ECO codes and common names.
"""

# Dictionary of common openings: move sequence → opening name
# Each key is a tuple of SAN moves (in order), value is the opening name
OPENING_PATTERNS = [
    # Italian Game
    (("e4", "e5", "Nf3", "Nc6", "Bc4"), "Italian Game: Two Knights Defence"),
    (("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"), "Italian Game: Giuoco Piano"),
    (("e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6"), "Italian Game: Two Knights Defence"),
    
    # Ruy Lopez (Spanish Opening)
    (("e4", "e5", "Nf3", "Nc6", "Bb5"), "Ruy Lopez"),
    (("e4", "e5", "Nf3", "Nc6", "Bb5", "a6"), "Ruy Lopez: Morphy Defence"),
    (("e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4"), "Ruy Lopez: Morphy Defence"),
    (("e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6"), "Ruy Lopez: Morphy Defence"),
    
    # Sicilian Defence
    (("e4", "c5"), "Sicilian Defence"),
    (("e4", "c5", "Nf3"), "Sicilian Defence"),
    (("e4", "c5", "Nf3", "d6"), "Sicilian: Najdorf Variation"),
    (("e4", "c5", "Nf3", "Nc6"), "Sicilian: Closed Variation"),
    (("e4", "c5", "d4", "cxd4"), "Sicilian: Open Variation"),
    
    # French Defence
    (("e4", "e6"), "French Defence"),
    (("e4", "e6", "d4"), "French Defence"),
    (("e4", "e6", "d4", "d5"), "French Defence: Standard"),
    
    # Caro-Kann Defence
    (("e4", "c6"), "Caro-Kann Defence"),
    (("e4", "c6", "d4"), "Caro-Kann Defence"),
    (("e4", "c6", "d4", "d5"), "Caro-Kann Defence: Main Line"),
    
    # Scandinavian Defence
    (("e4", "d5"), "Scandinavian Defence"),
    (("e4", "d5", "exd5"), "Scandinavian Defence"),
    
    # Queen's Gambit
    (("d4", "d5"), "Queen's Gambit"),
    (("d4", "d5", "c4"), "Queen's Gambit Declined"),
    (("d4", "d5", "c4", "e6"), "Queen's Gambit Declined"),
    (("d4", "d5", "c4", "dxc4"), "Queen's Gambit Accepted"),
    
    # Queen's Indian Defence
    (("d4", "Nf6", "c4", "e6"), "Queen's Indian Defence"),
    (("d4", "Nf6", "c4", "e6", "Nf3"), "Queen's Indian Defence"),
    
    # King's Indian Defence
    (("d4", "Nf6", "c4", "g6"), "King's Indian Defence"),
    (("d4", "Nf6", "c4", "g6", "Nc3"), "King's Indian Defence"),
    (("d4", "Nf6", "c4", "g6", "Nc3", "Bg7"), "King's Indian Defence"),
    
    # Nimzo-Indian Defence
    (("d4", "Nf6", "c4", "e6", "Nc3", "Bb4"), "Nimzo-Indian Defence"),
    
    # Slav Defence
    (("d4", "d5", "c4", "c6"), "Slav Defence"),
    (("d4", "d5", "c4", "c6", "Nf3"), "Slav Defence"),
    
    # English Opening
    (("c4",), "English Opening"),
    (("c4", "e5"), "English Opening"),
    (("c4", "Nf6"), "English Opening"),
    
    # Bird's Opening
    (("f4",), "Bird's Opening"),
    
    # Reti Opening
    (("Nf3",), "Reti Opening"),
    (("Nf3", "d5"), "Reti Opening"),
    (("Nf3", "Nf6"), "Reti Opening"),
    
    # Alekhine's Defence
    (("e4", "Nf6"), "Alekhine's Defence"),
    (("e4", "Nf6", "e5"), "Alekhine's Defence"),
    
    # Modern Defence
    (("e4", "g6"), "Modern Defence"),
    
    # Pirc Defence
    (("d4", "g6"), "Pirc Defence"),
    (("d4", "g6", "e4"), "Pirc Defence"),
    
    # Grob's Attack
    (("g4",), "Grob's Attack"),
]


def classify_opening(moves_pgn_str: str) -> str:
    """
    Classify an opening based on the move sequence.
    
    Args:
        moves_pgn_str: Space-separated SAN moves (e.g., "e4 e5 Nf3 Nc6")
        
    Returns:
        Opening name (str), or "Unknown" if no match found
    """
    if not moves_pgn_str or not isinstance(moves_pgn_str, str):
        return "Unknown"
    
    moves = tuple(moves_pgn_str.strip().split())
    
    # Try to match progressively shorter move sequences
    # Start from longest patterns, work down
    for pattern_len in range(min(len(moves), 8), 0, -1):
        move_prefix = moves[:pattern_len]
        
        # Check all patterns of this length
        for pattern, name in OPENING_PATTERNS:
            if len(pattern) == pattern_len and pattern == move_prefix:
                return name
    
    return "Unknown"
