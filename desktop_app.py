"""
Pattern Finder - a desktop app that downloads stock prices from Yahoo Finance
and looks for classic chart patterns (double tops, head and shoulders, flags,
triangles and more).

Start it by double-clicking Start_PatternFinder.bat, or run:  python app.py
"""

import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

from pattern_core.data import DataError, fetch_prices, load_csv  # noqa: E402
from pattern_core.indicators import add_indicators  # noqa: E402
from pattern_core.pattern_info import (DISCLAIMER, GLOSSARY, HOW_IT_WORKS, PATTERN_INFO,  # noqa: E402
                                       STATUS_HELP, picture_path)
from pattern_core.patterns import ACTIVE_STATUSES, find_patterns, is_recent  # noqa: E402
from pattern_core.report import bias_word, checks_short, key_date, money, pattern_text, summary_text  # noqa: E402

APP_NAME = "Pattern Finder"
PERIODS = ["3mo", "6mo", "1y", "2y", "5y", "10y"]
INTERVALS = {"Daily": "1d", "Weekly": "1wk", "Hourly": "1h"}
UNITS = {"1d": "day", "1wk": "week", "1h": "hour"}
SAMPLE_TICKERS = "AAPL MSFT NVDA AMZN GOOGL META TSLA JPM XOM SPY QQQ"

GREEN, RED, PURPLE = "#1a9850", "#d73027", "#7b3294"
CANDLE_UP, CANDLE_DOWN = "#26a69a", "#ef5350"
STATUS_COLORS = {
    "Forming": "#1f5fbf", "Confirmed": "#000000", "Target reached": "#1a7f37",
    "Stopped out": "#b42318", "Failed": "#b42318", "Expired": "#8a8a8a",
}


def pattern_color(p):
    if p.direction > 0:
        return GREEN
    if p.direction < 0:
        return RED
    return PURPLE


def market_prices(ticker, period, interval):
    """SPY's closing prices for the market checks (None if the ticker is SPY or the download fails)."""
    if ticker.upper() == "SPY":
        return None
    try:
        return fetch_prices("SPY", period, interval)["Close"]
    except Exception:
        return None


class PatternFinderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} - stock chart pattern scanner")
        self.geometry("1440x900")
        self.minsize(1100, 700)
        self._setup_style()

        self.q = queue.Queue()
        self.df = None
        self.ticker = ""
        self.unit = "day"
        self.patterns = []
        self.visible = []
        self.selected = None
        self.pending_select = None
        self.scan_stop = threading.Event()
        self.scan_rows = []
        self.busy = False

        self.period_var = tk.StringVar(value="1y")
        self.interval_var = tk.StringVar(value="Daily")
        self.sens_var = tk.StringVar(value="Medium")

        self._build_settings_bar()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.chart_tab = ttk.Frame(self.nb)
        self.scan_tab = ttk.Frame(self.nb)
        self.guide_tab = ttk.Frame(self.nb)
        self.nb.add(self.chart_tab, text="  Chart & Patterns  ")
        self.nb.add(self.scan_tab, text="  Scan Many Tickers  ")
        self.nb.add(self.guide_tab, text="  Pattern Guide & Help  ")
        self._build_chart_tab()
        self._build_scan_tab()
        self._build_guide_tab()

        self.status_var = tk.StringVar(value="Type a ticker symbol (for example AAPL) and press Analyze.")
        ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(10, 3)).pack(fill="x", side="bottom")

        self.after(100, self._poll_queue)
        self._draw_empty_chart()

    def report_callback_exception(self, exc, val, tb):
        """Show unexpected errors in a box (and save them) instead of failing silently."""
        import traceback
        text = "".join(traceback.format_exception(exc, val, tb))
        _write_log(text)
        self.busy = False
        self.analyze_btn.configure(state="normal")
        self.configure(cursor="")
        messagebox.showerror(APP_NAME, f"Something went wrong:\n\n{val}\n\n"
                                       "The details were saved to error_log.txt in the app folder.")

    # ------------------------------------------------------------------ setup
    def _setup_style(self):
        style = ttk.Style(self)
        for theme in ("vista", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Treeview", rowheight=24)
        style.configure("Big.TButton", padding=(14, 4))
        style.configure("Head.TLabel", font=("Segoe UI", 11, "bold"))

    def _build_settings_bar(self):
        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="Settings for both tabs:").pack(side="left", padx=(0, 10))
        ttk.Label(bar, text="Period").pack(side="left")
        ttk.Combobox(bar, textvariable=self.period_var, values=PERIODS, width=6, state="readonly").pack(
            side="left", padx=(4, 14))
        ttk.Label(bar, text="Bar size").pack(side="left")
        ttk.Combobox(bar, textvariable=self.interval_var, values=list(INTERVALS), width=8,
                     state="readonly").pack(side="left", padx=(4, 14))
        ttk.Label(bar, text="Sensitivity").pack(side="left")
        ttk.Combobox(bar, textvariable=self.sens_var, values=["Low", "Medium", "High"], width=8,
                     state="readonly").pack(side="left", padx=(4, 14))
        ttk.Label(bar, text="(Low = only big, clear swings.  High = more patterns, more false alarms.)",
                  foreground="#666").pack(side="left")

    # ------------------------------------------------------------- chart tab
    def _build_chart_tab(self):
        top = ttk.Frame(self.chart_tab, padding=(6, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Ticker:", style="Head.TLabel").pack(side="left")
        self.ticker_var = tk.StringVar(value="AAPL")
        entry = ttk.Entry(top, textvariable=self.ticker_var, width=12, font=("Segoe UI", 11))
        entry.pack(side="left", padx=6)
        entry.bind("<Return>", lambda e: self.analyze())
        self.analyze_btn = ttk.Button(top, text="Analyze", style="Big.TButton", command=self.analyze)
        self.analyze_btn.pack(side="left", padx=4)
        ttk.Button(top, text="Open CSV file...", command=self.open_csv).pack(side="left", padx=12)

        self.show_ma = tk.BooleanVar(value=True)
        self.show_vol = tk.BooleanVar(value=True)
        self.show_rsi = tk.BooleanVar(value=True)
        self.show_macd = tk.BooleanVar(value=True)
        self.show_all = tk.BooleanVar(value=False)
        opts = ttk.Frame(top)
        opts.pack(side="right")
        for text, var in (("Moving averages", self.show_ma), ("Volume", self.show_vol), ("RSI", self.show_rsi),
                          ("MACD", self.show_macd), ("Shade all patterns", self.show_all)):
            ttk.Checkbutton(opts, text=text, variable=var, command=self.redraw).pack(side="left", padx=4)
        ttk.Button(opts, text="Whole chart", command=self.show_whole_chart).pack(side="left", padx=(10, 0))

        pane = ttk.PanedWindow(self.chart_tab, orient="horizontal")
        pane.pack(fill="both", expand=True)
        self.pane = pane
        # Give the pattern list enough room once the window has its real size
        self.after(300, lambda: pane.sashpos(0, max(500, pane.winfo_width() - 730)))

        left = ttk.Frame(pane)
        self.fig = Figure(figsize=(9, 7), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=left)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        tb_frame = ttk.Frame(left)
        tb_frame.pack(fill="x")
        NavigationToolbar2Tk(self.canvas, tb_frame).update()
        pane.add(left, weight=3)

        right = ttk.Frame(pane, padding=(6, 0))
        pane.add(right, weight=2)
        head = ttk.Frame(right)
        head.pack(fill="x")
        ttk.Label(head, text="Patterns found", style="Head.TLabel").pack(side="left")
        self.filter_var = tk.StringVar(value="All patterns")
        cb = ttk.Combobox(head, textvariable=self.filter_var, width=34, state="readonly",
                          values=["All patterns", "Active only (forming or recent breakout)",
                                  "Bullish only", "Bearish only"])
        cb.pack(side="right")
        cb.bind("<<ComboboxSelected>>", lambda e: self._fill_table())

        cols = ("pattern", "bias", "status", "date", "entry", "target", "stop", "rr", "checks", "score")
        heads = ("Pattern", "Bias", "Status", "Date", "Entry", "Target", "Stop", "R:R", "Checks", "Score")
        widths = (136, 74, 106, 84, 60, 60, 60, 38, 52, 48)
        tf = ttk.Frame(right)
        tf.pack(fill="both", expand=True, pady=(6, 6))
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=12, selectmode="browse")
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, minwidth=36, anchor="w" if c in ("pattern", "status", "bias") else "e",
                             stretch=c == "pattern")
        for status, color in STATUS_COLORS.items():
            self.tree.tag_configure(status, foreground=color)
        ys = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        self.tree.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        btns = ttk.Frame(right)
        btns.pack(fill="x")
        ttk.Button(btns, text="Show summary", command=self.show_summary).pack(side="left")
        ttk.Button(btns, text="Export patterns to CSV...", command=self.export_patterns).pack(side="right")

        txt_frame = ttk.Frame(right)
        txt_frame.pack(fill="both", expand=True, pady=(6, 4))
        self.info = tk.Text(txt_frame, wrap="word", height=16, font=("Segoe UI", 10), padx=8, pady=6,
                            relief="flat", background="#fbfbfb")
        sy = ttk.Scrollbar(txt_frame, orient="vertical", command=self.info.yview)
        self.info.configure(yscrollcommand=sy.set)
        self.info.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")
        self.info.tag_configure("title", font=("Segoe UI", 12, "bold"))
        self.info.tag_configure("head", font=("Segoe UI", 10, "bold"), spacing1=4)
        self.info.tag_configure("small", foreground="#777", font=("Segoe UI", 9))
        self._set_info("Welcome!\n\nType a ticker symbol at the top left (for example AAPL, MSFT or SPY) "
                       "and press Analyze. The app will download the price history from Yahoo Finance, "
                       "work out common indicators and search for 21 classic chart patterns.\n\n"
                       "No internet? Use 'Open CSV file...' to load prices you saved yourself.\n\n"
                       + DISCLAIMER)

    def _set_info(self, text):
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        lines = text.split("\n")
        for k, line in enumerate(lines):
            if k == 0:
                tag = "title"
            elif line.isupper() and len(line) > 3:
                tag = "head"
            elif line == DISCLAIMER:
                tag = "small"
            else:
                tag = None
            self.info.insert("end", line + "\n", tag)
        self.info.configure(state="disabled")

    # ------------------------------------------------------------ analysing
    def _settings(self):
        return self.period_var.get(), INTERVALS[self.interval_var.get()], self.sens_var.get()

    def analyze(self, ticker=None, select=None):
        if self.busy:
            return
        ticker = (ticker or self.ticker_var.get()).strip().upper()
        if not ticker:
            messagebox.showinfo(APP_NAME, "Please type a ticker symbol first, for example AAPL.")
            return
        self.ticker_var.set(ticker)
        period, interval, sens = self._settings()
        self.pending_select = select
        self._set_busy(True, f"Downloading {ticker} ({period}, {self.interval_var.get().lower()}) "
                             "from Yahoo Finance...")

        def work():
            try:
                df = fetch_prices(ticker, period, interval)
                market = market_prices(ticker, period, interval)
                self.q.put(("analysis", ticker, df, sens, UNITS[interval], market))
            except DataError as exc:
                self.q.put(("error", str(exc)))
            except Exception as exc:  # anything unexpected
                self.q.put(("error", f"Something went wrong: {exc}"))

        threading.Thread(target=work, daemon=True).start()

    def open_csv(self):
        path = filedialog.askopenfilename(title="Open a price file",
                                          filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            df = load_csv(path)
        except DataError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        name = os.path.splitext(os.path.basename(path))[0].upper()
        self.ticker_var.set(name)
        self._finish_analysis(name, df, self.sens_var.get(), "bar")

    def _finish_analysis(self, ticker, df, sens, unit, market=None):
        if len(df) < 40:
            messagebox.showwarning(APP_NAME, f"Only {len(df)} bars of data were found. Patterns need more "
                                             "history - please choose a longer period.")
            self._set_busy(False, "Not enough data.")
            return
        self.status_var.set("Looking for patterns...")
        self.update_idletasks()
        df = add_indicators(df)
        pats = find_patterns(df, sens, checks=True, market=market)
        self.df, self.ticker, self.unit, self.patterns = df, ticker, unit, pats
        self.selected = None
        self._fill_table()
        active = sum(is_recent(p, len(df)) for p in pats)
        self._set_busy(False, f"{ticker}: {len(df)} bars loaded, {len(pats)} patterns found "
                              f"({active} active right now).")
        if self.pending_select:
            name, start_date = self.pending_select
            self.pending_select = None
            for p in self.visible:
                if p.name == name and str(df.index[p.start].date()) == start_date:
                    self.tree.selection_set(str(id(p)))
                    self.tree.see(str(id(p)))
                    return
        self.show_summary()

    def _set_busy(self, busy, msg=""):
        self.busy = busy
        self.analyze_btn.configure(state="disabled" if busy else "normal")
        self.configure(cursor="watch" if busy else "")
        if msg:
            self.status_var.set(msg)

    def _poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "analysis":
                    _, ticker, df, sens, unit, market = msg
                    self._finish_analysis(ticker, df, sens, unit, market)
                elif kind == "error":
                    self._set_busy(False, "Could not load data.")
                    messagebox.showerror(APP_NAME, msg[1])
                elif kind == "scan_progress":
                    _, i, total, tk_ = msg
                    self.scan_prog.configure(maximum=total, value=i)
                    self.scan_status.set(f"Scanning {tk_} ({i + 1} of {total})...")
                elif kind == "scan_rows":
                    for row in msg[1]:
                        self._add_scan_row(row)
                elif kind == "scan_note":
                    self.scan_notes.append(msg[1])
                elif kind == "scan_done":
                    self._scan_finished(msg[1])
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    # ---------------------------------------------------------- pattern list
    def _filtered(self):
        f = self.filter_var.get()
        n = len(self.df) if self.df is not None else 0
        out = []
        for p in self.patterns:
            if f.startswith("Active") and not is_recent(p, n):
                continue
            if f.startswith("Bullish") and p.direction <= 0 and PATTERN_INFO[p.name]["bias"] != "Bullish":
                continue
            if f.startswith("Bearish") and p.direction >= 0 and PATTERN_INFO[p.name]["bias"] != "Bearish":
                continue
            out.append(p)
        return out

    def _fill_table(self):
        self.tree.delete(*self.tree.get_children())
        if self.df is None:
            return
        self.visible = self._filtered()
        for p in self.visible:
            two_sided = p.direction == 0
            rr = p.reward_risk
            self.tree.insert("", "end", iid=str(id(p)), tags=(p.status,), values=(
                p.name, bias_word(p), p.status, key_date(p, self.df, self.unit),
                "both" if two_sided else f"{p.entry:,.2f}",
                "ways" if two_sided else f"{p.target:,.2f}",
                "" if two_sided else f"{p.stop:,.2f}",
                "" if two_sided or not np.isfinite(rr) else f"{rr:.1f}",
                checks_short(p),
                f"{p.score:.0f}",
            ))
        self.redraw()

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        p = next((x for x in self.visible if str(id(x)) == sel[0]), None)
        if p is None:
            return
        self.selected = p
        self._set_info(pattern_text(p, self.df, self.unit))
        self.redraw(focus=True)

    def show_summary(self):
        if self.df is None:
            return
        self.selected = None
        self.tree.selection_remove(self.tree.selection())
        self._set_info(summary_text(self.ticker, self.df, self.patterns, self.unit))
        self.redraw()

    def show_whole_chart(self):
        self.redraw(focus=False)

    def export_patterns(self):
        if not self.patterns:
            messagebox.showinfo(APP_NAME, "There are no patterns to export yet.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"{self.ticker}_patterns.csv",
                                            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        rows = [self._pattern_row(self.ticker, p, self.df, self.unit) for p in self.patterns]
        pd.DataFrame(rows).to_csv(path, index=False)
        self.status_var.set(f"Saved {len(rows)} patterns to {path}")

    @staticmethod
    def _pattern_row(ticker, p, df, unit):
        return {
            "Ticker": ticker, "Pattern": p.name, "Category": PATTERN_INFO[p.name]["category"],
            "Bias": bias_word(p), "Status": p.status,
            "Start": key_date_plain(df, p.start, unit), "End": key_date_plain(df, p.end, unit),
            "Breakout date": key_date_plain(df, p.breakout_i, unit),
            "Entry": round(p.entry, 2), "Target": round(p.target, 2), "Stop": round(p.stop, 2),
            "Reward to risk": round(p.reward_risk, 2) if np.isfinite(p.reward_risk) else "",
            "Checks passed": checks_short(p),
            "Score": p.score, "Last close": round(float(df["Close"].iloc[-1]), 2),
        }

    # --------------------------------------------------------------- drawing
    def _draw_empty_chart(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.axis("off")
        ax.text(0.5, 0.5, "Your chart will appear here.\n\nType a ticker and press Analyze.",
                ha="center", va="center", fontsize=13, color="#888", transform=ax.transAxes)
        self.canvas.draw_idle()

    def redraw(self, focus=None):
        if self.df is None:
            return
        if focus is None:
            focus = self.selected is not None
        df = self.df
        n = len(df)
        x = np.arange(n)
        fig = self.fig
        fig.clear()

        panels = ["price"]
        if self.show_vol.get():
            panels.append("vol")
        if self.show_rsi.get():
            panels.append("rsi")
        if self.show_macd.get():
            panels.append("macd")
        ratios = [4.2] + [1] * (len(panels) - 1)
        gs = fig.add_gridspec(len(panels), 1, height_ratios=ratios, hspace=0.06,
                              left=0.07, right=0.93, top=0.95, bottom=0.07)
        ax = fig.add_subplot(gs[0])
        axes = {"price": ax}
        for k, name in enumerate(panels[1:], start=1):
            axes[name] = fig.add_subplot(gs[k], sharex=ax)

        o, h, l, c = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
        up = c >= o
        colors = np.where(up, CANDLE_UP, CANDLE_DOWN)
        width = 0.65 if n < 400 else 0.8
        ax.vlines(x, l, h, colors=colors, linewidth=0.7 if n < 600 else 0.5)
        ax.bar(x, np.maximum(np.abs(c - o), (h - l) * 0.02 + 1e-9), bottom=np.minimum(o, c), width=width,
               color=colors, edgecolor=colors, linewidth=0.3)

        if self.show_ma.get():
            for col, color, label in (("SMA20", "#f2a900", "20 avg"), ("SMA50", "#2962ff", "50 avg"),
                                      ("SMA200", "#9c27b0", "200 avg")):
                if df[col].notna().any():
                    ax.plot(x, df[col].to_numpy(), color=color, linewidth=1.1, label=label, alpha=0.9)
            ax.legend(loc="best", fontsize=8, framealpha=0.7, ncol=3)

        if self.show_all.get():
            for p in self.visible:
                if p is not self.selected:
                    ax.axvspan(p.start, p.end, color=pattern_color(p), alpha=0.06, linewidth=0)
        # Work out the zoom window first so labels can be placed inside it
        view = (-1, n + 12)
        if focus and self.selected is not None:
            p = self.selected
            w = max(10, p.end - p.start)
            vx0 = max(-1, p.start - max(15, int(0.6 * w)))
            vx1 = min(n + 25, max(p.last_bar, n - 1 if p.status in ACTIVE_STATUSES else p.last_bar)
                      + max(15, int(0.4 * w)))
            view = (vx0, vx1)
        if self.selected is not None:
            self._draw_pattern(ax, self.selected, view)

        price_unit = "" if self.unit == "bar" else f" ({self.interval_var.get().lower()})"
        title = f"{self.ticker}{price_unit}   last close {money(float(c[-1]))}"
        if self.selected is not None:
            title += f"   |   {self.selected.name}: {self.selected.status}"
        ax.set_title(title, fontsize=11, loc="left")
        ax.grid(alpha=0.25)
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")

        if "vol" in axes:
            av = axes["vol"]
            av.bar(x, df["Volume"].to_numpy(), color=colors, width=width, alpha=0.6)
            av.plot(x, df["VolAvg20"].to_numpy(), color="#555", linewidth=0.9)
            av.set_ylabel("Volume", fontsize=8)
            av.yaxis.set_major_formatter(FuncFormatter(_short_number))
        if "rsi" in axes:
            ar = axes["rsi"]
            ar.plot(x, df["RSI"].to_numpy(), color="#6a1b9a", linewidth=1)
            ar.axhline(70, color=RED, linewidth=0.7, linestyle="--")
            ar.axhline(30, color=GREEN, linewidth=0.7, linestyle="--")
            ar.set_ylim(0, 100)
            ar.set_yticks([30, 70])
            ar.set_ylabel("RSI", fontsize=8)
        if "macd" in axes:
            am = axes["macd"]
            hist = df["MACD_hist"].to_numpy()
            am.bar(x, hist, color=np.where(hist >= 0, CANDLE_UP, CANDLE_DOWN), width=width, alpha=0.5)
            am.plot(x, df["MACD"].to_numpy(), color="#2962ff", linewidth=1, label="MACD")
            am.plot(x, df["MACD_signal"].to_numpy(), color="#ff6d00", linewidth=1, label="Signal")
            am.axhline(0, color="#999", linewidth=0.6)
            am.set_ylabel("MACD", fontsize=8)
            am.legend(loc="upper left", fontsize=7, frameon=False, ncol=2)

        dates = df.index
        fmt = "%Y-%m-%d %H:%M" if self.unit == "hour" else "%b %d\n%Y"

        def date_fmt(v, _pos):
            i = int(round(v))
            return dates[i].strftime(fmt) if 0 <= i < n else ""

        bottom = axes[panels[-1]]
        bottom.xaxis.set_major_locator(MaxNLocator(nbins=9, integer=True))
        bottom.xaxis.set_major_formatter(FuncFormatter(date_fmt))
        for name, a in axes.items():
            a.tick_params(labelsize=8)
            if a is not bottom:
                a.tick_params(labelbottom=False)
            if name != "price":
                a.grid(alpha=0.2)
                a.yaxis.tick_right()
            a.format_coord = (lambda xx, yy: f"{date_fmt(xx, 0).replace(chr(10), ' ')}   value {yy:,.2f}")

        # Zoom
        if focus and self.selected is not None:
            p = self.selected
            x0, x1 = view
            ax.set_xlim(x0, x1)
            lo_i, hi_i = max(0, int(x0)), min(n, int(x1) + 1)
            ys = [l[lo_i:hi_i].min(), h[lo_i:hi_i].max()]
            ys += [v for v in (p.target, p.stop, p.entry) if np.isfinite(v)]
            for sc in p.scenarios:
                ys.append(sc.target_from(sc.level(min(n - 1, x1))))
                ys.append(sc.stop)
            pad = (max(ys) - min(ys)) * 0.07
            ax.set_ylim(min(ys) - pad, max(ys) + 1.8 * pad)
            self._autoscale_panels(axes, lo_i, hi_i)
        else:
            ax.set_xlim(*view)
        self.canvas.draw_idle()

    def _autoscale_panels(self, axes, lo, hi):
        df = self.df
        if "vol" in axes:
            axes["vol"].set_ylim(0, df["Volume"].iloc[lo:hi].max() * 1.1 or 1)
        if "macd" in axes:
            seg = df[["MACD", "MACD_signal", "MACD_hist"]].iloc[lo:hi].to_numpy()
            if np.isfinite(seg).any():
                m = np.nanmax(np.abs(seg)) * 1.15 or 1
                axes["macd"].set_ylim(-m, m)

    def _draw_pattern(self, ax, p, view):
        df = self.df
        n = len(df)
        color = pattern_color(p)
        c = df["Close"].to_numpy()
        ax.axvspan(p.start, p.end, color=color, alpha=0.08, linewidth=0)

        # Rounded patterns: draw the fitted curve
        curve = p.details.get("cup_curve")
        if curve:
            a, b_ = curve
            xs = np.arange(a, b_ + 1)
            coef = np.polyfit(np.linspace(0, 1, len(xs)), c[a:b_ + 1], 2)
            ax.plot(xs, np.polyval(coef, np.linspace(0, 1, len(xs))), color=color, linewidth=2, alpha=0.7)

        for i1, p1, i2, p2 in p.lines:
            ax.plot([i1, i2], [p1, p2], color=color, linewidth=1.8)
        ext_to = p.breakout_i if p.breakout_i is not None else min(n - 1, p.end + 15)
        if p.status == "Forming":
            ext_to = n - 1 + 3
        for sc in p.scenarios:
            i1 = sc.line[0]
            ax.plot([i1, ext_to], [sc.level(i1), sc.level(ext_to)], color=color, linewidth=1.1, linestyle="--")

        for i, price, label in p.points:
            above = price >= c[i]
            ax.plot(i, price, "o", color=color, markersize=5, markeredgecolor="white", markeredgewidth=0.8)
            if label != "Touch":
                ax.annotate(label, (i, price), xytext=(0, 9 if above else -12), textcoords="offset points",
                            ha="center", fontsize=8, color=color, fontweight="bold")

        if p.breakout_i is not None:
            marker = "^" if p.direction > 0 else "v"
            ax.plot(p.breakout_i, c[p.breakout_i], marker, color=color, markersize=10, markeredgecolor="black")
            ax.annotate("Breakout", (p.breakout_i, c[p.breakout_i]), xytext=(8, -14 if p.direction > 0 else 10),
                        textcoords="offset points", fontsize=8)
        if p.outcome_i is not None:
            hit = p.target if p.status == "Target reached" else p.stop
            ax.plot(p.outcome_i, hit, "*", color="gold" if p.status == "Target reached" else "black",
                    markersize=13, markeredgecolor="black")

        # Entry / target / stop levels (labels sit just above each line, inside the view)
        x0 = p.breakout_i if p.breakout_i is not None else p.end
        x1 = max(x0 + 12, (p.outcome_i or n - 1) + 4)
        x1 = min(x1, view[1] - 0.5)
        x0 = max(x0, view[0] + 0.5)
        scenarios = p.scenarios if (p.direction == 0 and len(p.scenarios) > 1) else None
        if scenarios:
            for sc in scenarios:
                lvl = sc.level(n - 1)
                tgt = sc.target_from(lvl)
                word = "up" if sc.direction > 0 else "down"
                ax.hlines(tgt, x0, x1, colors=GREEN if sc.direction > 0 else RED, linestyles="--", linewidth=1.2)
                ax.text(x1, tgt, f"Target if it breaks {word}: {tgt:,.2f} ", va="bottom", ha="right",
                        fontsize=8, color=GREEN if sc.direction > 0 else RED, fontweight="bold")
        else:
            for val, col, name, style in ((p.target, GREEN, "Target", "--"), (p.stop, RED, "Stop", "--"),
                                          (p.entry, "#1f5fbf", "Entry", ":")):
                if np.isfinite(val):
                    ax.hlines(val, x0, x1, colors=col, linestyles=style, linewidth=1.3)
                    ax.text(x1, val, f"{name} {val:,.2f} ", va="bottom", ha="right", fontsize=8, color=col,
                            fontweight="bold")

    # ------------------------------------------------------------- scan tab
    def _build_scan_tab(self):
        frm = ttk.Frame(self.scan_tab, padding=10)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Tickers to scan (separate them with spaces, commas or new lines):",
                  style="Head.TLabel").pack(anchor="w")
        self.scan_text = tk.Text(frm, height=4, font=("Segoe UI", 10), wrap="word")
        self.scan_text.pack(fill="x", pady=(4, 6))
        self.scan_text.insert("1.0", SAMPLE_TICKERS)

        row = ttk.Frame(frm)
        row.pack(fill="x")
        self.scan_btn = ttk.Button(row, text="Start scan", style="Big.TButton", command=self.start_scan)
        self.scan_btn.pack(side="left")
        self.stop_btn = ttk.Button(row, text="Stop", command=self.scan_stop.set, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.active_only = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="Only show active patterns (still forming, or broke out in the last 10 bars)",
                        variable=self.active_only).pack(side="left", padx=14)
        ttk.Button(row, text="Export results to CSV...", command=self.export_scan).pack(side="right")

        prog = ttk.Frame(frm)
        prog.pack(fill="x", pady=6)
        self.scan_prog = ttk.Progressbar(prog, mode="determinate", length=260)
        self.scan_prog.pack(side="left")
        self.scan_status = tk.StringVar(value="Uses the Period, Bar size and Sensitivity settings at the top. "
                                              "Double-click a result to open its chart.")
        ttk.Label(prog, textvariable=self.scan_status).pack(side="left", padx=10)

        cols = ("ticker", "pattern", "bias", "status", "date", "last", "entry", "target", "stop", "rr", "checks",
                "score")
        heads = ("Ticker", "Pattern", "Bias", "Status", "Date", "Last close", "Entry", "Target", "Stop",
                 "R:R", "Checks", "Score")
        widths = (70, 190, 80, 110, 100, 85, 80, 80, 80, 50, 60, 55)
        tf = ttk.Frame(frm)
        tf.pack(fill="both", expand=True)
        self.scan_tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="browse")
        for ccol, hh, w in zip(cols, heads, widths):
            self.scan_tree.heading(ccol, text=hh, command=lambda cc=ccol: self._sort_scan(cc))
            self.scan_tree.column(ccol, width=w, anchor="w" if ccol in ("ticker", "pattern", "bias", "status")
                                  else "e", stretch=ccol == "pattern")
        for status, color in STATUS_COLORS.items():
            self.scan_tree.tag_configure(status, foreground=color)
        sy = ttk.Scrollbar(tf, orient="vertical", command=self.scan_tree.yview)
        self.scan_tree.configure(yscrollcommand=sy.set)
        self.scan_tree.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")
        self.scan_tree.bind("<Double-1>", self._open_scan_row)
        self._sort_state = {}
        self.scan_notes = []

    def start_scan(self):
        raw = self.scan_text.get("1.0", "end").replace(",", " ").replace(";", " ").split()
        tickers = list(dict.fromkeys(t.strip().upper() for t in raw if t.strip()))
        if not tickers:
            messagebox.showinfo(APP_NAME, "Please type at least one ticker symbol to scan.")
            return
        period, interval, sens = self._settings()
        active_only = self.active_only.get()
        unit = UNITS[interval]
        self.scan_tree.delete(*self.scan_tree.get_children())
        self.scan_rows = []
        self.scan_notes = []
        self.scan_stop.clear()
        self.scan_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        def work():
            found = 0
            market = market_prices("", period, interval)
            for i, t in enumerate(tickers):
                if self.scan_stop.is_set():
                    break
                self.q.put(("scan_progress", i, len(tickers), t))
                try:
                    df = add_indicators(fetch_prices(t, period, interval))
                    pats = find_patterns(df, sens, checks=True, market=None if t == "SPY" else market)
                    rows = []
                    for p in pats:
                        if active_only and not is_recent(p, len(df)):
                            continue
                        rows.append(self._pattern_row(t, p, df, unit) | {"Date": key_date(p, df, unit)})
                    found += len(rows)
                    self.q.put(("scan_rows", rows))
                except Exception as exc:
                    self.q.put(("scan_note", f"{t}: {str(exc).splitlines()[0]}"))
                time.sleep(0.4)  # be polite to Yahoo Finance
            self.q.put(("scan_done", found))

        threading.Thread(target=work, daemon=True).start()

    def _add_scan_row(self, r):
        self.scan_rows.append(r)
        two = r["Bias"] == "Either way"
        self.scan_tree.insert("", "end", iid=str(len(self.scan_rows) - 1), tags=(r["Status"],), values=(
            r["Ticker"], r["Pattern"], r["Bias"], r["Status"], r["Date"], f"{r['Last close']:,.2f}",
            "both" if two else f"{r['Entry']:,.2f}", "ways" if two else f"{r['Target']:,.2f}",
            "" if two else f"{r['Stop']:,.2f}", "" if two else r["Reward to risk"], r["Checks passed"], r["Score"]))

    def _scan_finished(self, found):
        self.scan_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.scan_prog.configure(value=self.scan_prog["maximum"])
        msg = f"Scan finished: {found} pattern(s) found."
        if self.scan_notes:
            msg += f"  {len(self.scan_notes)} ticker(s) could not be loaded: " + "; ".join(self.scan_notes)[:300]
        self.scan_status.set(msg)

    def _sort_scan(self, col):
        items = [(self.scan_tree.set(k, col), k) for k in self.scan_tree.get_children("")]

        def key(v):
            txt = str(v[0]).replace(",", "")
            try:
                if "/" in txt:   # "7/12" textbook checks: sort by the share passed
                    a, b = txt.split("/")
                    return (0, float(a) / max(float(b), 1.0))
                return (0, float(txt))
            except ValueError:
                return (1, txt)
        rev = not self._sort_state.get(col, False)
        self._sort_state[col] = rev
        for idx, (_, k) in enumerate(sorted(items, key=key, reverse=rev)):
            self.scan_tree.move(k, "", idx)

    def _open_scan_row(self, _event):
        sel = self.scan_tree.selection()
        if not sel:
            return
        r = self.scan_rows[int(sel[0])]
        self.nb.select(self.chart_tab)
        self.analyze(r["Ticker"], select=(r["Pattern"], r["Start"][:10]))

    def export_scan(self):
        if not self.scan_rows:
            messagebox.showinfo(APP_NAME, "There are no scan results to export yet.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="scan_results.csv",
                                            filetypes=[("CSV files", "*.csv")])
        if path:
            pd.DataFrame(self.scan_rows).to_csv(path, index=False)
            self.scan_status.set(f"Saved {len(self.scan_rows)} rows to {path}")

    # ------------------------------------------------------------ guide tab
    def _build_guide_tab(self):
        self._guide_images = []
        frm = ttk.Frame(self.guide_tab, padding=10)
        frm.pack(fill="both", expand=True)
        t = tk.Text(frm, wrap="word", font=("Segoe UI", 10), padx=14, pady=10, relief="flat",
                    background="#fbfbfb")
        sy = ttk.Scrollbar(frm, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sy.set)
        t.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")
        t.tag_configure("h1", font=("Segoe UI", 15, "bold"), spacing1=6, spacing3=6)
        t.tag_configure("h2", font=("Segoe UI", 12, "bold"), spacing1=12, spacing3=4)
        t.tag_configure("h3", font=("Segoe UI", 10, "bold"), spacing1=8)
        t.tag_configure("dim", foreground="#555")

        t.insert("end", "How to use Pattern Finder\n", "h1")
        t.insert("end",
                 "1. Type a ticker symbol (for example AAPL) on the 'Chart & Patterns' tab and press Analyze.\n"
                 "2. The list on the right shows every pattern found, newest first. Click one to zoom the chart "
                 "to it. The chart then shows the pattern's lines, the breakout, and three levels: Entry "
                 "(blue dotted), Target (green dashed) and Stop-loss (red dashed).\n"
                 "3. The text box under the list explains the pattern and its numbers in plain English. "
                 "'Show summary' brings back the overview of the whole chart.\n"
                 "4. The 'Scan Many Tickers' tab checks a whole list of tickers and lists the active patterns. "
                 "Double-click a result to open its chart.\n"
                 "5. Use the magnifying-glass button under the chart to zoom into any area, the house button to "
                 "reset, and the disk button to save the chart as a picture.\n\n")
        t.insert("end", "Words used in this app\n", "h2")
        for word, meaning in GLOSSARY:
            t.insert("end", f"{word}: ", "h3")
            t.insert("end", meaning + "\n")
        t.insert("end", "\nWhat the status means\n", "h2")
        for status, meaning in STATUS_HELP.items():
            t.insert("end", f"{status}: ", "h3")
            t.insert("end", meaning + "\n")
        for cat, blurb in (("Reversal", "These suggest the current trend may turn around."),
                           ("Continuation", "These suggest the current trend may carry on after a pause."),
                           ("Bilateral", "These can break either way; the direction of the breakout decides.")):
            t.insert("end", f"\n{cat} patterns\n", "h2")
            t.insert("end", blurb + "\n", "dim")
            for name, info in PATTERN_INFO.items():
                if info["category"] != cat:
                    continue
                t.insert("end", f"\n{name}  ({info['bias']})\n", "h3")
                pic = picture_path(name)
                if os.path.exists(pic):
                    try:
                        img = tk.PhotoImage(file=pic)
                        self._guide_images.append(img)  # keep a reference so Tk does not discard it
                        t.image_create("end", image=img, pady=4)
                        t.insert("end", "\n")
                    except tk.TclError:
                        pass  # picture could not be loaded: show the text only
                t.insert("end", f"Looks like: {info['looks']}\n")
                t.insert("end", f"May mean: {info['means']}\n")
                t.insert("end", f"Target: {info['target']}\n")
                t.insert("end", f"Stop-loss: {info['stop']}\n")
        t.insert("end", "\nHow the math works (short version)\n", "h2")
        t.insert("end", HOW_IT_WORKS + "\n")
        t.insert("end", "\nImportant\n", "h2")
        t.insert("end", DISCLAIMER + "\n")
        t.configure(state="disabled")


def _short_number(v, _pos=None):
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"{v / div:.0f}{suf}"
    return f"{v:.0f}"


def key_date_plain(df, i, unit):
    if i is None:
        return ""
    d = df.index[int(i)]
    return d.strftime("%Y-%m-%d %H:%M") if unit == "hour" else d.strftime("%Y-%m-%d")


def _write_log(text):
    try:
        folder = os.path.dirname(os.path.abspath(sys.argv[0]))
        with open(os.path.join(folder, "error_log.txt"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + text + "\n")
    except OSError:
        pass


def main():
    if sys.platform.startswith("win"):
        try:  # sharper text on high-resolution Windows screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    try:
        app = PatternFinderApp()
    except Exception:
        import traceback
        _write_log(traceback.format_exc())
        raise
    app.mainloop()


if __name__ == "__main__":
    main()
