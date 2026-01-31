#!/usr/bin/env python3
"""Test local Stockfish fallback in streamlit_app.py"""

import sys
import os

# Add src to path
sys.path.insert(0, '/Users/orvarsverrisson/chess-analyzer')

# Mock streamlit temporarily to test imports
class MockStreamlit:
    class secrets:
        def __getitem__(self, key):
            raise KeyError(key)
        def get(self, key, default=None):
            return default

sys.modules['streamlit'] = MockStreamlit()

# Now import and test
from streamlit_app import _find_stockfish_path_for_local

print("Testing Stockfish detection...")
path = _find_stockfish_path_for_local()
if path:
    print(f"✓ Found Stockfish at: {path}")
else:
    print("✗ Stockfish not found on this system (expected on VPS)")
