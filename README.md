# Paper Trader — Flask

Smallest-possible app for a paper trading demo using **Flask + Jinja2 + HTMX**.
- Single codebase; server-rendered pages
- Dummy username-only login stored in SQLite
- Random-walk prices every few seconds; market & limit orders fill instantly if crossed.

## Quick start
```bash
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# Run
python app.py
# Open http://127.0.0.1:5000/login
```
