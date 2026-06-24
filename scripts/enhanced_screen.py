"""Thin entry point for enhanced screening.

Delegates to the enhanced_screen package.
Usage:
    cd ~/code/research-workspace/market-data-platform
    uv run --extra dev python ~/code/financial-research/scripts/enhanced_screen.py
"""

from enhanced_screen import main

if __name__ == "__main__":
    main()
