# CLAUDE.md — Pattern Finder

Guidance for Claude when working in this repository.

## What this is

Pattern Finder downloads stock prices from Yahoo Finance and detects **21 classic chart patterns**. For each pattern it works out an entry, a target and a stop-loss, plus **21 "textbook confirmation checks"**. It also backtests whether the patterns actually work.

- **Windows desktop app:** `desktop_app.py` (Tkinter).
- **Phone/web app:** `streamlit_app.py`. It runs on the user's PC and is opened from an iPhone.
- **Shared engine:** `pattern_core/`, used by both apps and the backtest.
- **Version:** `pattern_core.__version__` (currently 2.5.0).

This is a learning and research tool, not financial advice. **The honest current finding is that the patterns show no reliable edge** over random entries: v2.1 edge −0.18% per trade, 95% range −1.17% to +0.81%. Don't overstate results anywhere.

## The user

- **Not an expert in coding.** Has a basic understanding of statistics.
- **Explain things simply:** full, grammatical sentences, and define jargon before using it, in replies, code comments, docs and in-app text alike.
- **Uses Windows.** Runs everything through the `.bat` files. Has no Mac.
- **Sends results back** (`results/summary.txt`, `results/trades.csv`, `results/tickers.json`) for interpretation.
- **Google Drive folder** for the Colab notebooks: `DRIVE_FOLDER = "/content/drive/MyDrive/Colab Notebooks/PatternFinder"`.

## Commands

All commands run from the repo root. On Windows, the `.bat` files create `.venv` via `windows\_setup.bat`.

| Task | Command | Windows |
|---|---|---|
| All self-tests | `python run_tests.py` | `Run_Tests.bat` |
| Desktop app | `python desktop_app.py` | `Start_Desktop_App.bat` |
| Web app | `streamlit run streamlit_app.py` | `Start_Web_App_On_My_PC.bat` |
| Download prices | `python -m pattern_core.download AAPL MSFT ... --period 10y --out prices` | (inside `Run_Backtest.bat`) |
| Backtest (20–40 min) | `python -m pattern_core.backtest --data-dir prices --out results` | `Run_Backtest.bat` |
| Summarise backtest | `python -m pattern_core.analyze --out results > results/summary.txt` | (inside `Run_Backtest.bat`) |
| Redraw Guide pictures | `python -m pattern_core.pictures` | — |
| Single-file .exe | — | `Build_EXE.bat` |

The backtest's ticker list is AAPL MSFT NVDA AMZN GOOGL META TSLA JPM XOM SPY QQQ. **SPY.csv must be in the prices folder** for the market and relative-strength checks; without it they are left blank.

**Run `python run_tests.py` after every change. It must end with `ALL TESTS PASSED`.**

## Layout

```
pattern_core/
  data.py          Yahoo download (yfinance, auto_adjust=True) and CSV loading
  indicators.py    SMA, EMA, RSI and ATR (Wilder's smoothing), MACD, OBV, Bollinger Bands
  patterns.py      Swing points (ATR zigzag), the 21 pattern detectors, evaluate(), dedupe(), find_patterns()
  confirm.py       The 21 textbook checks, key reversal days, Context, attach_checks(), flat_columns(), PROVEN
  backtest.py      Walk-forward backtest, simulate(), random twins, the two trade-management variants
  analyze.py       Summary statistics: clustered SEs, Holm/BH, split halves, check_report(), variant_report()
  report.py        Plain-English text shown in both apps (pattern_text, summary_text, checks_lines)
  pattern_info.py  Pattern descriptions, glossary, HOW_IT_WORKS, DISCLAIMER, picture paths
  examples.py      Textbook example shapes (CASES, GAP_CASES), used by the tests and the pictures
  pictures.py      Draws images/patterns/*.png from examples.py using the real finder
  policy.py        Forecast-driven long-only and long/short trading tests (used by the Kronos notebooks)
tests/             test_indicators, test_patterns, test_backtest, test_confirm, test_statistics, test_policy
docs/METHODOLOGY.md         Every rule and its source. Keep it in sync with the code.
docs/METHODOLOGY_REVIEW.md  The earlier academic review (historical record; don't rewrite it)
colab/             Kronos notebooks (archived experiments, see below)
```

## Architecture and rules that must not break

1. **One engine.** All calculations and user-facing text live in `pattern_core/`. The two app files only draw screens. A change to logic or wording goes in the engine, so both apps get it.
2. **No peeking at the future.**
   - The backtest gives the finder only the last 500 bars up to day *t*. A breakout is judged on day *t*'s close, and the trade enters at the **next day's open**.
   - Every check in `confirm.py` uses only data up to the day it is judged on.
   - `tests/test_confirm.py` verifies this by comparing results on full and truncated data. Keep that test passing, and extend it to cover any new check.
3. **Bearish = flipped bullish.**
   - Bearish patterns are found by flipping the chart (`Bars.mirror()`, price → K − price) and running the bullish rules, then flipping back with `mirror_pattern`. Keep rules symmetrical this way rather than writing separate bearish logic.
   - Point labels written for the flipped chart are fixed at the end of `find_patterns`.
4. **Thresholds are fixed in advance from cited sources**: Lo, Mamaysky & Wang (2000), Edwards & Magee, Bulkowski, O'Neil, StockCharts *TA 101*, and Murphy's *Charting Made Easy*.
   - **Never tune a threshold on backtest results.** Doing so finds "winners" by luck.
   - Each constant carries a comment naming its source. Mark our own choices as "our choice".
5. **Fair comparison.**
   - Each real trade is compared with 200 **random twins**: same stock, direction, stop and target distances (%) and time limit, but random start days within ±250 bars.
   - **Edge** = trade return − average twin return.
   - Trade-management variants are compared on the **same** twin days (`twin_days` / `twin_results`).
6. **Statistics standards** (`analyze.py`):
   - Standard errors are clustered by calendar month.
   - P-values use Student's t.
   - Holm and Benjamini–Hochberg corrections apply across patterns and across checks.
   - Groups with fewer than 20 trades are labelled "too few".
   - A check counts as **HELPS** only if Holm p < 0.05, the difference is above 0 in **both** halves of the period, and at least 20 trades passed and 20 failed.
7. **Trade rules** (`simulate`):
   - Costs: 0.05% per side.
   - An overnight gap through a level exits at the open.
   - If the stop and target are hit on the same day, the stop counts.
   - Time limit: the pattern's width, kept between 10 and 100 bars.
   - Skip the trade if the next open is already past the stop or target.
8. **Performance.** `find_patterns(df, sens)` runs once per day per ticker in the backtest, so it must stay fast.
   - Checks are **off by default**. The apps call `find_patterns(df, sens, checks=True, market=spy_close)`.
   - The backtest works out checks only on signal days, via `Context` + `run_checks`.

## Common tasks

**Adding or changing a pattern:**
1. Write the detector in `patterns.py`, and register it in `find_patterns` (plus a flipped version if needed).
2. Add an entry to `PATTERN_INFO` (category, bias, looks, means, target, stop).
3. Add a textbook shape to `examples.py`: `CASES` for close-only shapes, `GAP_CASES` for full OHLC tables, which gap patterns need.
4. Classify the pattern in `confirm.py` (`REVERSAL` / `CONTINUATION` / `TOPS_BOTTOMS` / `TRIANGLES`).
5. Run `python -m pattern_core.pictures`, then the tests.
6. Update the pattern count everywhere it appears: README, METHODOLOGY, `desktop_app.py` about text, and the `analyze.py` docstring.

**Adding a textbook check:**
1. Add a `CheckDef` (key, group, label, plain-English question, source) to `CHECKS` in `confirm.py`.
2. Add its logic in `run_checks`, using `put(key, applies, passed, value, text)`.
   - Return `passed=None` when it can't be judged; that is different from failing.
   - If it only makes sense at a breakout, add it to `NEEDS_BREAKOUT`.
3. Document it in METHODOLOGY section 4b, and add a test.
4. The backtest columns (`chk_<key>`, `val_<key>`) and the analysis table pick it up automatically.

**After the user's backtest:** only checks marked **HELPS** in `results/summary.txt` go into `PROVEN` in `confirm.py`. The apps then label them "(helped in the backtest)". `PROVEN` is currently empty because the v2.5 backtest results haven't come back yet.

**Releasing:**
1. Bump `__version__`.
2. Update README and METHODOLOGY.
3. Run all tests.
4. Zip the folder as `PatternFinder_vX.Y.zip`, without `__pycache__` or `.venv`.

## Environment notes

- **Python 3.10+.** Required libraries are in `requirements.txt`; scipy is *not* required, so don't add it.
- **In Claude's cloud workspace,** Yahoo Finance and Hugging Face are blocked by network policy. Don't try to work around this.
  - Test with `example_prices.csv` or synthetic data, or ask the user to attach their `prices` folder.
  - Fake `fetch_prices` when testing the apps offline.
- **Desktop app:** can be smoke-tested headlessly with `xvfb-run`.
- **Web app:** use `streamlit.testing.v1.AppTest`.
- **Notebooks** are built by scripts and run with `nbclient`, using a tiny untrained Kronos stand-in for offline tests.

## Research history (context for future suggestions)

- **v2.0–v2.1 backtests:** no reliable pattern edge. The quality score did not predict results.
- **Breakout-day volume alone** (v2.1 trades) did not help. Heavy-volume breakouts hit their targets more often, but only because their targets were closer; edge vs twins was flat.
- **Kronos / TimesFM time-series forecasting:** tested in the `colab/` notebooks and **abandoned by the user**.
  - Kronos-base leaned strongly downward and showed no rank skill after its training cutoff.
  - Don't propose time-series forecasting models again unless the user asks.
- **v2.5 added** the textbook checks (from TA 101 parts 4–16 and Murphy), island reversals, and two variants: an exit after a strong key reversal day, and a gap-based stop.
  - **Waiting on:** the user's v2.5 backtest results.
  - **Deferred:** log-scale trend lines (TA 101 part 6), because they would change every pattern's shape and mix that effect with the checks.
