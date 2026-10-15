# Pattern Finder (version 2.5)

One package, two ways to use it:

- **Windows desktop app**: a normal program window on your PC.
- **Phone / web app**: runs in a web browser and can be added to your iPhone home screen.

Both use the same engine (the `pattern_core` folder) for prices, indicators, the 21 chart patterns, the textbook confirmation checks, the plain-English explanations, the pattern pictures and the backtest. A change or a test in `pattern_core` therefore covers both apps at once.

> This is a learning and research tool, not financial advice. Chart patterns often fail, and our own backtest found no reliable edge (see `docs/METHODOLOGY_REVIEW.md`).

---

## What's in the folder

| File or folder | What it is |
|---|---|
| `Start_Desktop_App.bat` | Double-click to open the Windows app. Sets itself up the first time. |
| `Start_Web_App_On_My_PC.bat` | Runs the phone/web version on your PC. Your iPhone can open it on the same Wi-Fi. |
| `Run_Backtest.bat` | Downloads 10 years of prices and tests the patterns. Results go in `results`. |
| `Run_Tests.bat` | Runs every self-test. Use it after any change. |
| `Build_EXE.bat` | Optional. Makes a single `PatternFinder.exe`. |
| `desktop_app.py` | The Windows screens only. |
| `streamlit_app.py` | The phone/web screens only. |
| `pattern_core/` | **The shared engine.** All calculations, text and pictures live here. |
| `tests/` and `run_tests.py` | Self-tests for indicators, patterns, the textbook checks and backtest rules. |
| `docs/METHODOLOGY.md` | How every calculation works, with sources. |
| `docs/METHODOLOGY_REVIEW.md` | The review against research and best practice, and what changed. |
| `colab/Kronos_Skill_Test.ipynb` | Optional Google Colab notebook: tests whether Kronos can forecast the thing a pattern claims (target before stop) better than a no-skill simulator, whether it can forecast move size better than the ATR, and, only if it shows skill, whether it picks the better pattern trades. Start here before using Kronos as a filter. |
| `colab/Kronos_Pattern_Filter.ipynb` | Optional Google Colab notebook: uses the Kronos forecasting model as a filter on the backtest trades, and runs two Kronos-only trading strategies (long only, and long and short) against SPY and buy-and-hold. |
| `example_prices.csv` | Made-up practice data for trying the apps without internet. |
| `requirements.txt` | The Python libraries both apps need. |

Inside `pattern_core/`:

| File | What it does |
|---|---|
| `data.py` | Downloads prices from Yahoo Finance, or reads a CSV file. |
| `indicators.py` | Moving averages, RSI, MACD, ATR (Wilder's method), On-Balance Volume and Bollinger Bands. |
| `patterns.py` | Finds the 21 patterns, with their entry, target and stop-loss. |
| `confirm.py` | The 21 textbook confirmation checks (volume, trend, retracement, breakout quality, gaps and key reversal days, room to run) from StockCharts' TA 101 and John Murphy. |
| `pattern_info.py` | Descriptions, glossary, the "how it works" text, and the picture locations. |
| `report.py` | Turns results into plain-English summaries. |
| `examples.py` | Textbook example shapes, used by the tests and the pictures. |
| `pictures.py` | Redraws the Guide pictures (`python -m pattern_core.pictures`). |
| `download.py` | Saves price history as CSV files (`python -m pattern_core.download`). |
| `backtest.py` | The walk-forward backtest (`python -m pattern_core.backtest`). |
| `analyze.py` | Summarises backtest results (`python -m pattern_core.analyze`). |
| `policy.py` | Turns daily forecasts into the long-only and long/short trading tests, and measures them. |
| `images/patterns/` | The 21 Guide pictures. |

---

## Windows desktop app

1. **Install Python once.** Get it from <https://www.python.org/downloads/windows/>. On the installer's first screen, tick **"Add python.exe to PATH"**.
2. **Unzip this folder**, for example into your Documents folder.
3. **Double-click `Start_Desktop_App.bat`.** The first time, it spends a few minutes installing what it needs. After that it opens straight away.

> If Windows shows "Windows protected your PC", click **More info**, then **Run anyway**.

## Phone / web app (iPhone)

### Put it online (free, done once)

1. Make a free account at <https://github.com/signup>.
2. On GitHub, click **+**, then **New repository**. Name it `pattern-finder`, keep it **Public**, and click **Create repository**.
3. Click **uploading an existing file**. Select **everything inside this folder**, including the `pattern_core`, `tests` and `docs` folders, and drag it onto the page. Then click **Commit changes**.
4. Go to <https://share.streamlit.io>, click **Continue with GitHub**, then **Create app**.
5. Fill in the form: Repository `your-name/pattern-finder`, Branch `main`, Main file path `streamlit_app.py`. Click **Deploy**.

### Add it to your iPhone

Open the app's web address in **Safari**, tap **Share**, then **Add to Home Screen**.

### Good to know

- Free Streamlit apps go to sleep when nobody has used them for a while. Tap the wake-up button and wait about a minute.
- Yahoo Finance sometimes limits downloads from cloud servers. If every ticker fails, wait and try again.

To try the web version on your PC first, double-click `Start_Web_App_On_My_PC.bat`.

---

## Making changes safely

1. Make the change in `pattern_core` (or in one app's screen file, if it only affects how that app looks).
2. Double-click `Run_Tests.bat`. Every test should pass.
3. If you changed a pattern rule, redraw the Guide pictures: open a Command Prompt in this folder and run `.venv\Scripts\python.exe -m pattern_core.pictures`.
4. To check the effect on results, double-click `Run_Backtest.bat`.
5. Update the web app by uploading the changed files to GitHub. Update the Windows app by using the new folder (and re-running `Build_EXE.bat` if you use the .exe).

## Backtest

`Run_Backtest.bat` downloads 10 years of daily prices for AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, JPM, XOM, SPY and QQQ (edit the list inside the file to change it). It then tests every pattern the way you could have traded it: using only past prices, entering at the next day's open, and comparing each trade with 200 random-day "twins". It takes 20 to 40 minutes (a little longer than before, because it now also records the textbook checks and replays each trade two extra ways). You can send me `results\trades.csv`, `results\tickers.json` and `results\summary.txt` to update the results.

New in 2.5: `results\summary.txt` ends with a **textbook checks** table. For each check it shows the edge of trades that passed minus trades that failed, and a verdict: **HELPS**, **HURTS**, **no clear effect** or **too few**. Below that are the two trade-management variants (exit on a key reversal day, and a stop beyond a breakaway gap).

## If something goes wrong

- **"Python was not found":** install Python as in step 1, with "Add python.exe to PATH" ticked.
- **"No data found":** check the ticker. Non-US stocks need Yahoo's suffix, for example `SHOP.TO` or `VOD.L`.
- **Setup keeps failing:** delete the `.venv` folder and try again.
- **Anything else:** the desktop app saves error details in `error_log.txt` in this folder.
