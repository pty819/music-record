#!/bin/bash
which camoufox 2>/dev/null || echo "no camoufox in PATH"
pip show camoufox 2>/dev/null | head -3
echo "---"
python3 -c "import camoufox; print(camoufox.__version__)" 2>/dev/null || echo "camoufox not installed"
echo "---"
ls ~/.cache/camoufox/ 2>/dev/null | head -5
echo "---"
ls ~/.hermes/profiles/scraper/home/.cache/camoufox/ 2>/dev/null | head -5