"""
Pattern Finder - phone-friendly web version.

It uses exactly the same pattern-finding code as the Windows app
(patterns.py, indicators.py, data.py, report.py, pattern_info.py).
Only the screen layout is different: it runs in a web browser, so it can be
saved to an iPhone home screen and used like an app.

Run it on a computer with:   streamlit run streamlit_app.py
"""

import os
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from pattern_core.data import DataError, fetch_prices, load_csv
from pattern_core.indicators import add_indicators
from pattern_core.pattern_info import DISCLAIMER, GLOSSARY, PATTERN_INFO, STATUS_HELP, picture_path
from pattern_core.patterns import ACTIVE_STATUSES, find_patterns, is_recent
from pattern_core.report import bias_word, checks_short, key_date, money, pattern_text, summary_text

st.set_page_config(page_title="Pattern Finder", page_icon="📈", layout="centered",
                   initial_sidebar_state="collapsed")

PERIODS = ["3mo", "6mo", "1y", "2y", "5y", "10y"]
INTERVALS = {"Daily": "1d", "Weekly": "1wk", "Hourly": "1h"}
UNITS = {"1d": "day", "1wk": "week", "1h": "hour"}
SAMPLE_TICKERS = "AAPL MSFT NVDA AMZN GOOGL META TSLA JPM XOM SPY QQQ"
GREEN, RED, PURPLE, BLUE = "#1a9850", "#d73027", "#7b3294", "#1f5fbf"
CANDLE_UP, CANDLE_DOWN = "#26a69a", "#ef5350"
STATUS_ICON = {"Forming": "🔵", "Confirmed": "🟣", "Target reached": "🟢", "Stopped out": "🔴",
               "Failed": "🔴", "Expired": "⚪"}

# Small style tweaks so it feels more like an app on a phone
st.markdown("""
<style>
  .block-container {padding-top: 1.2rem; padding-left: 0.8rem; padding-right: 0.8rem; max-width: 900px;}
  [data-testid="stMetricValue"] {font-size: 1.25rem;}
  #MainMenu, footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Data and analysis (cached so the same download is reused for 15 minutes)
# ----------------------------------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def get_prices(ticker, period, interval):
    return fetch_prices(ticker, period, interval)


@st.cache_data(ttl=900, show_spinner=False)
def get_market(period, interval):
    """SPY's closing prices for the market checks (None if the download fails)."""
    try:
        return fetch_prices("SPY", period, interval)["Close"]
    except Exception:
        return None


@st.cache_data(ttl=900, show_spinner=False)
def analyse(df, sensitivity, market=None):
    df = add_indicators(df)
    return df, find_patterns(df, sensitivity, checks=True, market=market)


def pattern_color(p):
    return GREEN if p.direction > 0 else RED if p.direction < 0 else PURPLE


def to_markdown(text):
    """Turn the plain report text into tidy markdown for the phone screen."""
    out = []
    for k, line in enumerate(text.split("\n")):
        line = line.replace("$", "\\$")  # stop $ signs being read as maths
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if k == 0:
            out.append(f"#### {stripped}")
        elif not stripped:
            continue
        elif stripped.isupper() and len(stripped) > 3:
            out.append(f"**{stripped.capitalize()}**")
        elif stripped.replace("\\$", "$") == DISCLAIMER:
            continue  # shown separately as small print
        elif indent >= 5 and out and out[-1].startswith("- "):
            out[-1] += f"  \n<small>{stripped}</small>"
        elif indent >= 2:
            out.append(stripped if stripped.startswith("- ") else f"- {stripped}")
        else:
            out.append(stripped)
    return "\n\n".join(out)


# ----------------------------------------------------------------------------
# Chart
# ----------------------------------------------------------------------------
def build_chart(df, ticker, unit, selected=None, last_n=None, show=("vol", "rsi", "macd"), shade=()):
    n = len(df)
    x = np.arange(n)
    o, h, l, c = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    fmt = "%Y-%m-%d %H:%M" if unit == "hour" else "%Y-%m-%d"
    labels = [d.strftime(fmt) for d in df.index]

    panels = ["price"] + [p for p in ("vol", "rsi", "macd") if p in show]
    heights = [0.62] + [0.38 / max(1, len(panels) - 1)] * (len(panels) - 1)
    fig = make_subplots(rows=len(panels), cols=1, shared_xaxes=True, vertical_spacing=0.025,
                        row_heights=heights if len(panels) > 1 else [1.0])
    row = {name: i + 1 for i, name in enumerate(panels)}

    fig.add_trace(go.Candlestick(x=x, open=o, high=h, low=l, close=c, text=labels, name="Price",
                                 increasing_line_color=CANDLE_UP, decreasing_line_color=CANDLE_DOWN,
                                 increasing_fillcolor=CANDLE_UP, decreasing_fillcolor=CANDLE_DOWN,
                                 showlegend=False), row=1, col=1)
    for col, color, name in (("SMA20", "#f2a900", "20 avg"), ("SMA50", "#2962ff", "50 avg"),
                             ("SMA200", "#9c27b0", "200 avg")):
        if df[col].notna().any():
            fig.add_trace(go.Scatter(x=x, y=df[col], mode="lines", line=dict(color=color, width=1.3),
                                     name=name, hoverinfo="skip"), row=1, col=1)

    for p in shade:
        if p is not selected:
            fig.add_vrect(x0=p.start, x1=p.end, fillcolor=pattern_color(p), opacity=0.07, line_width=0,
                          row=1, col=1)

    # Which part of the chart to show
    if selected is not None:
        w = max(10, selected.end - selected.start)
        x0 = max(-1, selected.start - max(10, int(0.4 * w)))
        last = max(selected.last_bar, n - 1 if selected.status in ACTIVE_STATUSES else selected.last_bar)
        x1 = min(n + 15, last + max(10, int(0.3 * w)))
    else:
        span = n if not last_n else min(n, last_n)
        x0, x1 = n - span - 1, n + 6

    ys = []
    if selected is not None:
        ys += _draw_pattern(fig, df, selected, (x0, x1))

    if "vol" in row:
        fig.add_trace(go.Bar(x=x, y=df["Volume"], marker_color=np.where(c >= o, CANDLE_UP, CANDLE_DOWN),
                             opacity=0.6, showlegend=False, hoverinfo="skip"), row=row["vol"], col=1)
        _panel_label(fig, row["vol"], "Volume")
    if "rsi" in row:
        fig.add_trace(go.Scatter(x=x, y=df["RSI"], line=dict(color="#6a1b9a", width=1.2), showlegend=False,
                                 hovertemplate="RSI %{y:.0f}<extra></extra>"), row=row["rsi"], col=1)
        for lvl, colr in ((70, RED), (30, GREEN)):
            fig.add_hline(y=lvl, line=dict(color=colr, width=0.8, dash="dash"), row=row["rsi"], col=1)
        fig.update_yaxes(range=[0, 100], tickvals=[30, 70], row=row["rsi"], col=1)
        _panel_label(fig, row["rsi"], "RSI")
    if "macd" in row:
        hist = df["MACD_hist"].to_numpy()
        fig.add_trace(go.Bar(x=x, y=hist, marker_color=np.where(hist >= 0, CANDLE_UP, CANDLE_DOWN),
                             opacity=0.5, showlegend=False, hoverinfo="skip"), row=row["macd"], col=1)
        fig.add_trace(go.Scatter(x=x, y=df["MACD"], line=dict(color="#2962ff", width=1.1), name="MACD",
                                 showlegend=False, hoverinfo="skip"), row=row["macd"], col=1)
        fig.add_trace(go.Scatter(x=x, y=df["MACD_signal"], line=dict(color="#ff6d00", width=1.1),
                                 name="Signal", showlegend=False, hoverinfo="skip"), row=row["macd"], col=1)
        lo_i, hi_i = max(0, int(x0)), min(n, int(x1) + 1)
        seg = df[["MACD", "MACD_signal", "MACD_hist"]].iloc[lo_i:hi_i].to_numpy()
        m = float(np.nanmax(np.abs(seg))) * 1.15 if np.isfinite(seg).any() else 1
        fig.update_yaxes(range=[-m, m], row=row["macd"], col=1)
        _panel_label(fig, row["macd"], "MACD (blue) and signal (orange)")

    # Price axis range: the visible bars plus any target / stop lines
    lo_i, hi_i = max(0, int(x0)), min(n, int(x1) + 1)
    ys += [float(l[lo_i:hi_i].min()), float(h[lo_i:hi_i].max())]
    pad = (max(ys) - min(ys)) * 0.06
    fig.update_yaxes(range=[min(ys) - pad, max(ys) + 1.5 * pad], row=1, col=1, side="right")

    # Date labels on the x axis
    lo, hi = max(0, int(x0) + 1), min(n - 1, int(x1))
    ticks = np.linspace(lo, hi, 5).round().astype(int) if hi > lo else [lo]
    tick_fmt = "%b %d<br>%H:%M" if unit == "hour" else "%b %d<br>%Y"
    fig.update_xaxes(range=[x0, x1], tickvals=list(ticks),
                     ticktext=[df.index[i].strftime(tick_fmt) for i in ticks],
                     rangeslider_visible=False, showgrid=True, gridcolor="rgba(128,128,128,0.15)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)", side="right", fixedrange=True)
    fig.update_yaxes(fixedrange=False, row=1, col=1)

    fig.update_layout(height=580 if len(panels) > 1 else 440, margin=dict(l=4, r=48, t=28, b=36),
                      dragmode="pan", font=dict(size=11),
                      hovermode="x", legend=dict(orientation="h", y=1.0, x=0.0, yanchor="bottom",
                                                 font=dict(size=10)),
                      xaxis_rangeslider_visible=False)
    return fig


def _panel_label(fig, r, text):
    """Small label in the top-left corner of an indicator panel."""
    fig.add_annotation(text=text, xref="x domain", yref="y domain", x=0.01, y=0.98, showarrow=False,
                       xanchor="left", yanchor="top", font=dict(size=10, color="#777"), row=r, col=1)


def _draw_pattern(fig, df, p, view):
    """Draw one pattern on the price panel. Returns prices that must stay visible."""
    n = len(df)
    c = df["Close"].to_numpy()
    color = pattern_color(p)
    fig.add_vrect(x0=p.start, x1=p.end, fillcolor=color, opacity=0.09, line_width=0, row=1, col=1)

    curve = p.details.get("cup_curve")
    if curve:
        a, b = curve
        xs = np.arange(a, b + 1)
        t = np.linspace(0, 1, len(xs))
        fig.add_trace(go.Scatter(x=xs, y=np.polyval(np.polyfit(t, c[a:b + 1], 2), t), mode="lines",
                                 line=dict(color=color, width=2.5), opacity=0.7, showlegend=False,
                                 hoverinfo="skip"), row=1, col=1)
    for i1, p1, i2, p2 in p.lines:
        fig.add_trace(go.Scatter(x=[i1, i2], y=[p1, p2], mode="lines", line=dict(color=color, width=2.2),
                                 showlegend=False, hoverinfo="skip"), row=1, col=1)
    ext_to = p.breakout_i if p.breakout_i is not None else min(n - 1, p.end + 15)
    if p.status == "Forming":
        ext_to = n + 2
    for sc in p.scenarios:
        i1 = sc.line[0]
        fig.add_trace(go.Scatter(x=[i1, ext_to], y=[sc.level(i1), sc.level(ext_to)], mode="lines",
                                 line=dict(color=color, width=1.3, dash="dash"), showlegend=False,
                                 hoverinfo="skip"), row=1, col=1)

    pts = [(i, pr, lab) for i, pr, lab in p.points]
    fig.add_trace(go.Scatter(
        x=[i for i, _, _ in pts], y=[pr for _, pr, _ in pts], mode="markers+text",
        text=["" if lab == "Touch" else lab for _, _, lab in pts],
        textposition=["top center" if pr >= c[i] else "bottom center" for i, pr, _ in pts],
        textfont=dict(color=color, size=10), marker=dict(color=color, size=7, line=dict(color="white", width=1)),
        showlegend=False, hoverinfo="skip"), row=1, col=1)

    if p.breakout_i is not None:
        fig.add_trace(go.Scatter(x=[p.breakout_i], y=[c[p.breakout_i]], mode="markers+text", text=["Breakout"],
                                 textposition="bottom right" if p.direction > 0 else "top right",
                                 marker=dict(symbol="triangle-up" if p.direction > 0 else "triangle-down",
                                             size=13, color=color, line=dict(color="black", width=1)),
                                 textfont=dict(size=10), showlegend=False, hoverinfo="skip"), row=1, col=1)
    if p.outcome_i is not None:
        hit = p.target if p.status == "Target reached" else p.stop
        fig.add_trace(go.Scatter(x=[p.outcome_i], y=[hit], mode="markers",
                                 marker=dict(symbol="star", size=15, line=dict(color="black", width=1),
                                             color="gold" if p.status == "Target reached" else "black"),
                                 showlegend=False, hoverinfo="skip"), row=1, col=1)

    keep = []
    x0 = p.breakout_i if p.breakout_i is not None else p.end
    x1 = min(max(x0 + 12, (p.outcome_i or n - 1) + 4), view[1] - 0.5)
    x0 = max(x0, view[0] + 0.5)
    if p.direction == 0 and len(p.scenarios) > 1:
        levels = []
        for sc in p.scenarios:
            tgt = sc.target_from(sc.level(n - 1))
            word = "up" if sc.direction > 0 else "down"
            levels.append((tgt, GREEN if sc.direction > 0 else RED, f"Target if {word} {tgt:,.2f}", "dash"))
    else:
        levels = [(p.target, GREEN, f"Target {p.target:,.2f}", "dash"),
                  (p.stop, RED, f"Stop {p.stop:,.2f}", "dash"),
                  (p.entry, BLUE, f"Entry {p.entry:,.2f}", "dot")]
    for val, colr, label, dash in levels:
        if not np.isfinite(val):
            continue
        keep.append(float(val))
        fig.add_trace(go.Scatter(x=[x0, x1], y=[val, val], mode="lines", line=dict(color=colr, width=1.6, dash=dash),
                                 showlegend=False, hoverinfo="skip"), row=1, col=1)
        fig.add_annotation(x=x1, y=val, text=f"<b>{label}</b>", showarrow=False, xanchor="right", yanchor="bottom",
                           font=dict(color=colr, size=11), row=1, col=1)
    return keep


def show_chart(fig):
    st.plotly_chart(fig, width="stretch",
                    config={"displayModeBar": False, "scrollZoom": False, "responsive": True})


def pattern_label(p, df, unit):
    return f"{STATUS_ICON.get(p.status, '')} {p.name} · {p.status} · {key_date(p, df, unit)}"


def patterns_table(pats, df, unit):
    rows = []
    for p in pats:
        two = p.direction == 0
        rows.append({
            "Pattern": p.name, "Bias": bias_word(p), "Status": p.status, "Date": key_date(p, df, unit),
            "Entry": None if two else round(p.entry, 2), "Target": None if two else round(p.target, 2),
            "Stop": None if two else round(p.stop, 2),
            "R:R": None if two or not np.isfinite(p.reward_risk) else round(p.reward_risk, 1),
            "Checks": checks_short(p),
            "Score": p.score,
        })
    return pd.DataFrame(rows)


def filter_patterns(pats, how, n):
    if how == "Active":
        return [p for p in pats if is_recent(p, n)]
    if how == "Bullish":
        return [p for p in pats if p.direction > 0 or PATTERN_INFO[p.name]["bias"] == "Bullish"]
    if how == "Bearish":
        return [p for p in pats if p.direction < 0 or PATTERN_INFO[p.name]["bias"] == "Bearish"]
    return pats


def pattern_explorer(df, pats, ticker, unit, key, show, default_view="6M"):
    """Pattern picker + chart + explanation. Used on both tabs."""
    n = len(df)
    how = st.segmented_control("Show", ["All", "Active", "Bullish", "Bearish"], default="All",
                               key=f"{key}_filter") or "All"
    shown = filter_patterns(pats, how, n)
    options = [None] + list(range(len(shown)))
    pick = st.selectbox(
        f"Pattern ({len(shown)} found)", options, key=f"{key}_pick",
        format_func=lambda i: "Overview - no pattern selected" if i is None else pattern_label(shown[i], df, unit))
    selected = None if pick is None or pick >= len(shown) else shown[pick]

    last_n = None
    if selected is None:
        view = st.segmented_control("Zoom", ["3M", "6M", "1Y", "All"], default=default_view,
                                    key=f"{key}_view") or default_view
        per_month = {"day": 21, "week": 4.3, "hour": 140, "bar": 21}.get(unit, 21)
        last_n = {"3M": int(3 * per_month), "6M": int(6 * per_month), "1Y": int(12 * per_month)}.get(view)
    show_chart(build_chart(df, ticker, unit, selected, last_n, show,
                           shade=[p for p in shown if is_recent(p, n)] if selected is None else ()))
    st.caption("Drag the chart sideways to move around. Tap a pattern in the list above to zoom to it.")

    if selected is None:
        st.markdown(to_markdown(summary_text(ticker, df, pats, unit)), unsafe_allow_html=True)
    else:
        st.markdown(to_markdown(pattern_text(selected, df, unit)), unsafe_allow_html=True)
    if shown:
        with st.expander("All patterns as a table"):
            st.dataframe(patterns_table(shown, df, unit), hide_index=True, width="stretch")
    st.caption(DISCLAIMER)


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------
st.markdown("### 📈 Pattern Finder")
with st.expander("⚙️ Settings", expanded=False):
    c1, c2, c3 = st.columns(3)
    period = c1.selectbox("Period", PERIODS, index=2)
    bar_name = c2.selectbox("Bar size", list(INTERVALS), index=0)
    sens = c3.selectbox("Sensitivity", ["Low", "Medium", "High"], index=1,
                        help="Low = only big, clear swings. High = more patterns, but more false alarms.")
    show = st.multiselect("Indicator panels", ["Volume", "RSI", "MACD"], default=["Volume", "RSI"])
    show_keys = tuple({"Volume": "vol", "RSI": "rsi", "MACD": "macd"}[s] for s in show)
    upload = st.file_uploader("No internet data? Load a CSV price file instead", type=["csv"])
interval = INTERVALS[bar_name]

tab_chart, tab_scan, tab_guide = st.tabs(["Chart", "Scan", "Guide"])


# ----- Chart tab -----
st.session_state.setdefault("ticker", "AAPL")  # show a chart straight away on first open
with tab_chart:
    with st.form("ticker_form", border=False):
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        st.session_state.setdefault("ticker_box", "AAPL")
        typed = c1.text_input("Ticker", key="ticker_box", placeholder="e.g. AAPL, MSFT, SPY").strip().upper()
        go_btn = c2.form_submit_button("Analyze", width="stretch", type="primary")
    if go_btn and typed:
        st.session_state["ticker"] = typed
        st.session_state.pop("chart_pick", None)

    ticker = st.session_state.get("ticker")
    df_raw, unit, source = None, UNITS[interval], None
    if upload is not None:
        try:
            df_raw, unit = load_csv(upload), "bar"
            ticker = upload.name.rsplit(".", 1)[0].upper()
            source = "file"
        except DataError as exc:
            st.error(str(exc))
    elif ticker:
        try:
            with st.spinner(f"Downloading {ticker} from Yahoo Finance..."):
                df_raw = get_prices(ticker, period, interval)
            source = "yahoo"
        except DataError as exc:
            st.error(str(exc))

    if df_raw is None:
        if not ticker and upload is None:
            st.info("Type a ticker symbol and tap **Analyze**.")
    elif len(df_raw) < 40:
        st.warning(f"Only {len(df_raw)} bars of data were found. Choose a longer period in Settings.")
    else:
        df, pats = analyse(df_raw, sens, None if ticker.upper() == "SPY" else get_market(period, interval))
        last, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
        m1, m2, m3 = st.columns(3)
        m1.metric(ticker, money(last), f"{(last - prev) / prev * 100:+.2f}%")
        m2.metric("Patterns", len(pats))
        m3.metric("Active now", sum(is_recent(p, len(df)) for p in pats))
        pattern_explorer(df, pats, ticker, unit, "chart", show_keys)

# ----- Scan tab -----
with tab_scan:
    st.markdown("Check a list of tickers for patterns. It uses the period, bar size and sensitivity in "
                "**Settings**.")
    tick_text = st.text_area("Tickers (separate with spaces or commas)", SAMPLE_TICKERS, height=80)
    active_only = st.checkbox("Only active patterns (forming, or broke out in the last 10 bars)", value=True)
    if st.button("Start scan", type="primary", width="stretch"):
        tickers = list(dict.fromkeys(t.upper() for t in tick_text.replace(",", " ").replace(";", " ").split()))
        rows, problems, store = [], [], {}
        bar = st.progress(0.0, text="Starting...")
        for i, t in enumerate(tickers):
            bar.progress(i / max(1, len(tickers)), text=f"Scanning {t} ({i + 1} of {len(tickers)})")
            try:
                d, ps = analyse(get_prices(t, period, interval), sens,
                                None if t == "SPY" else get_market(period, interval))
                store[t] = (d, ps)
                for p in ps:
                    if active_only and not is_recent(p, len(d)):
                        continue
                    two = p.direction == 0
                    rows.append({"Ticker": t, "Pattern": p.name, "Bias": bias_word(p), "Status": p.status,
                                 "Date": key_date(p, d, UNITS[interval]),
                                 "Last": round(float(d["Close"].iloc[-1]), 2),
                                 "Entry": None if two else round(p.entry, 2),
                                 "Target": None if two else round(p.target, 2),
                                 "Stop": None if two else round(p.stop, 2),
                                 "R:R": None if two or not np.isfinite(p.reward_risk) else round(p.reward_risk, 1),
                                 "Checks": checks_short(p), "Score": p.score})
            except Exception as exc:
                problems.append(f"{t}: {str(exc).splitlines()[0]}")
            time.sleep(0.3)  # be polite to Yahoo Finance
        bar.progress(1.0, text="Done")
        st.session_state["scan"] = (rows, problems, store, UNITS[interval])

    if "scan" in st.session_state:
        rows, problems, store, s_unit = st.session_state["scan"]
        st.success(f"Found {len(rows)} pattern(s).")
        if problems:
            st.warning("Could not load: " + "; ".join(problems))
        if rows:
            res = pd.DataFrame(rows)
            st.dataframe(res, hide_index=True, width="stretch")
            st.download_button("Save results as CSV", res.to_csv(index=False).encode(), "scan_results.csv",
                               "text/csv", width="stretch")
            names = [t for t in store if t in set(res["Ticker"])]
            look = st.selectbox("Look at a ticker's chart", names, key="scan_look")
            if look:
                d, ps = store[look]
                pattern_explorer(d, ps, look, s_unit, f"scan_{look}", show_keys)

# ----- Guide tab -----
with tab_guide:
    st.markdown("#### How to use it")
    st.markdown(
        "1. On **Chart**, type a ticker and tap **Analyze**.\n"
        "2. Pick a pattern from the list. The chart zooms to it and shows three lines: **Entry** (blue dotted), "
        "**Target** (green dashed) and **Stop-loss** (red dashed).\n"
        "3. Under the chart, a plain-English explanation tells you what the pattern means and what the numbers are.\n"
        "4. **Scan** checks a whole list of tickers at once.\n"
        "5. **Settings** (the gear at the top) changes the period, bar size, sensitivity and indicator panels.")
    st.markdown("#### What the status means")
    for s, txt in STATUS_HELP.items():
        st.markdown(f"{STATUS_ICON.get(s, '')} **{s}**: {txt}")
    st.markdown("#### Words used in this app")
    for word, meaning in GLOSSARY:
        st.markdown(f"**{word}**: {meaning}".replace("$", "\\$"))
    for cat in ("Reversal", "Continuation", "Bilateral"):
        st.markdown(f"#### {cat} patterns")
        for name, info in PATTERN_INFO.items():
            if info["category"] == cat:
                with st.expander(f"{name} ({info['bias']})"):
                    pic = picture_path(name)
                    if os.path.exists(pic):
                        st.image(pic, width="stretch")
                    st.markdown(f"**Looks like:** {info['looks']}\n\n**May mean:** {info['means']}\n\n"
                                f"**Target:** {info['target']}\n\n**Stop-loss:** {info['stop']}")
    st.caption(DISCLAIMER)
