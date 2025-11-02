# Repository Guidelines

## Project Structure & Module Organization
The trading toolkit lives in `grid_strategy_tk/`. Runtime modules sit under `grid_strategy_tk/src/`, split by responsibility: UI windows (`*window.py`, `components/`), analytics engines (`backtest_engine.py`, `stock_analysis_engine.py`), and integrations (`akshare_wrapper.py`, `services/`). Configuration templates and cached inputs are stored in `grid_strategy_tk/config/` and `grid_strategy_tk/data/`; keep large CSVs or generated cache files in `grid_strategy_tk/data/cache`. Automated tests reside in `grid_strategy_tk/tests/`, while packaging artefacts land in `grid_strategy_tk/dist/` after builds.

## Build, Test, and Development Commands
Set up the environment with `pip install -r grid_strategy_tk/requirements.txt` (Python 3.9+). Start the desktop app via `python grid_strategy_tk/src/app.py`. Run the headless API monitor for quick data checks with `python grid_strategy_tk/src/etf_data_fetcher_standalone.py`. Execute the test suite using `pytest -c grid_strategy_tk/pytest.ini`; add `-k <pattern>` for focused runs. Produce a Windows bundle through `python grid_strategy_tk/build.py`, then copy the `data/cache`, `data/results`, and `src/assets` folders beside the executable.

## Coding Style & Naming Conventions
Follow PEP 8 with four-space indentation and snake_case module/function names (`stock_analysis_engine.py`). Keep class names in PascalCase and align docstrings with existing bilingual comments. Where practical, type annotate public functions and favour pandas/numpy vectorised operations over manual loops. Centralised services and reusable widgets should live under `grid_strategy_tk/src/services/` or `grid_strategy_tk/src/components/` to keep imports predictable.

## Testing Guidelines
Pytest discovers files matching `test_*.py` under `grid_strategy_tk/tests/`; mirror this pattern for new suites. Prefer fixture-driven data and patch AkShare/network calls with local CSV samples from `grid_strategy_tk/data/` to keep tests deterministic. When adding analytics logic, include regression tests that validate both numeric output and key DataFrame columns.

## Commit & Pull Request Guidelines
Recent history uses concise, action-first Chinese commit titles (e.g., `优化雷达图更新逻辑`); continue that tense and keep subject lines under 50 characters. Reference related issues in the body when necessary and group changes by feature. Pull requests should outline motivation, highlight user-facing impacts, note testing performed, and attach screenshots for UI updates or new charts. Label breaking behavioural changes explicitly to prompt targeted review.

## Packaging & Assets
Localized strings live in `grid_strategy_tk/src/locales/`, and UI assets in `grid_strategy_tk/src/assets/`; ensure new resources follow the existing naming scheme (`zh_CN.json`, `icon_<feature>.png`). Versioned configuration samples belong in `grid_strategy_tk/config/`, while per-user overrides should stay out of version control but be documented in PR discussion.
