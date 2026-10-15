@echo off
REM Downloads 10 years of daily prices and tests how the patterns would have done.
REM Edit the ticker list below if you like. Results go in the "results" folder.
cd /d "%~dp0"
title Pattern Finder backtest
call windows\_setup.bat || exit /b 1
set TICKERS=AAPL MSFT NVDA AMZN GOOGL META TSLA JPM XOM SPY QQQ
echo Downloading prices for %TICKERS% ...
".venv\Scripts\python.exe" -m pattern_core.download %TICKERS% --period 10y --out prices || goto failed
echo.
echo Running the backtest. This takes 20 to 40 minutes...
".venv\Scripts\python.exe" -m pattern_core.backtest --data-dir prices --out results || goto failed
".venv\Scripts\python.exe" -m pattern_core.analyze --out results > results\summary.txt || goto failed
type results\summary.txt
echo.
echo Done. Your results are in the "results" folder (trades.csv, tickers.json, summary.txt).
pause
exit /b 0
:failed
echo Something went wrong. Scroll up to see the message.
pause
exit /b 1
