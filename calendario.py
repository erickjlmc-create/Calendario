import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# =====================================================================================
# CONFIGURACIÓN (se puede sobreescribir con variables de entorno / secrets)
# =====================================================================================

# Pares a vigilar. "symbol"/"name" son solo para mostrar en la alerta; el dato
# real se descarga con el ticker equivalente en YF_SYMBOLS.
PAIRS = [
    {"symbol": "BTCUSDT",    "name": "BTC/USDT",    "emoji": "🟠"},
    {"symbol": "ETHUSDT",    "name": "ETH/USDT",    "emoji": "🔷"},
    {"symbol": "SOLUSDT",    "name": "SOL/USDT",    "emoji": "🟣"},
    {"symbol": "BNBUSDT",    "name": "BNB/USDT",    "emoji": "🟡"},
    {"symbol": "ADAUSDT",    "name": "ADA/USDT",    "emoji": "🔵"},
    {"symbol": "XRPUSDT",    "name": "XRP/USDT",    "emoji": "⚪"},
    {"symbol": "DOGEUSDT",   "name": "DOGE/USDT",   "emoji": "🐕"},
    {"symbol": "AVAXUSDT",   "name": "AVAX/USDT",   "emoji": "🔺"},
    {"symbol": "LINKUSDT",   "name": "LINK/USDT",   "emoji": "🔗"},
    {"symbol": "DOTUSDT",    "name": "DOT/USDT",    "emoji": "⚫"},
    {"symbol": "NEARUSDT",   "name": "NEAR/USDT",   "emoji": "🌐"},
    {"symbol": "OPUSDT",     "name": "OP/USDT",     "emoji": "🔴"},
    {"symbol": "ATOMUSDT",   "name": "ATOM/USDT",   "emoji": "⚛️"},
    {"symbol": "RENDERUSDT", "name": "RENDER/USDT", "emoji": "🎨"},
    {"symbol": "INJUSDT",    "name": "INJ/USDT",    "emoji": "💉"},
    {"symbol": "WLDUSDT",    "name": "WLD/USDT",    "emoji": "🌍"},
    {"symbol": "TIAUSDT",    "name": "TIA/USDT",    "emoji": "🌌"},
    {"symbol": "ZECUSDT",    "name": "ZEC/USDT",    "emoji": "🛡️"},
    {"symbol": "XMRUSDT",    "name": "XMR/USDT",    "emoji": "🕶️"},
]

YF_SYMBOLS = {
    "BTCUSDT":    "BTC-USD",
    "ETHUSDT":    "ETH-USD",
    "SOLUSDT":    "SOL-USD",
    "BNBUSDT":    "BNB-USD",
    "ADAUSDT":    "ADA-USD",
    "XRPUSDT":    "XRP-USD",
    "DOGEUSDT":   "DOGE-USD",
    "AVAXUSDT":   "AVAX-USD",
    "LINKUSDT":   "LINK-USD",
    "DOTUSDT":    "DOT-USD",
    "NEARUSDT":   "NEAR-USD",
    "OPUSDT":     "OP-USD",
    "ATOMUSDT":   "ATOM-USD",
    "RENDERUSDT": "RENDER-USD",
    "INJUSDT":    "INJ-USD",
    "WLDUSDT":    "WLD-USD",
    "TIAUSDT":    "TIA-USD",
    "ZECUSDT":    "ZEC-USD",
    "XMRUSDT":    "XMR-USD",
}

YF_INTERVAL_LTF = "15m"                                  # Timeframe base (igual al del gráfico)
YF_PERIOD_LTF = os.environ.get("YF_PERIOD_LTF", "60d")   # Yahoo limita 15m a ~60 días
YF_PERIOD_1H = os.environ.get("YF_PERIOD_1H", "730d")    # Yahoo permite más histórico en 1h

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

# ---- Range Filter ----
RF_PER = 24
RF_MULT = 2.7

# ---- Hull Suite ----
HULL_MODE = "Ehma"        # "Hma" | "Thma" | "Ehma"
HULL_LENGTH = 34
HULL_LENGTH_MULT = 2.0

# ---- Triple MA filter (desactivado por defecto, igual que en el indicador) ----
TRIPLE_MA_FILTER = False
MA1_LEN, MA1_TYPE = 144, "EMA"
MA2_LEN, MA2_TYPE = 50, "EMA"
MA3_LEN, MA3_TYPE = 21, "EMA"

# ---- STC ----
STC_FAST = 23
STC_SLOW = 50
STC_LEN = 10
STC_FACTOR = 0.5
STC_OB = 75.0
STC_OS = 25.0
TRIGGER_MODE = "Cruce"      # "Cruce" | "Direccion"
AVOID_EXHAUSTED = True


# =====================================================================================
# INDICADORES BÁSICOS
# =====================================================================================

def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rma(series: pd.Series, length: int) -> pd.Series:
    # Aproximación de ta.rma (Wilder / SMMA) de Pine.
    return series.ewm(alpha=1.0 / length, adjust=False).mean()


def wma(series: pd.Series, length: int) -> pd.Series:
    length = max(int(round(length)), 1)
    weights = np.arange(1, length + 1)

    def _wma(x):
        return np.dot(x, weights) / weights.sum()

    return series.rolling(length).apply(_wma, raw=True)


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def vwma(close: pd.Series, volume: pd.Series, length: int) -> pd.Series:
    pv = (close * volume).rolling(length).sum()
    v = volume.rolling(length).sum()
    return pv / v


def ma(df: pd.DataFrame, length: int, ma_type: str) -> pd.Series:
    close = df["Close"]
    if ma_type == "SMA":
        return sma(close, length)
    if ma_type == "EMA":
        return ema(close, length)
    if ma_type == "SMMA (RMA)":
        return rma(close, length)
    if ma_type == "WMA":
        return wma(close, length)
    if ma_type == "VWMA":
        return vwma(close, df["Volume"], length)
    if ma_type == "HULLMA":
        return wma(2 * wma(close, length / 2) - wma(close, length), np.sqrt(length))
    raise ValueError(f"Tipo de MA desconocido: {ma_type}")


# =====================================================================================
# RANGE FILTER
# =====================================================================================

def range_filter(src: pd.Series, per: int, mult: float):
    diff = src.diff().abs()
    avrng = ema(diff, per)
    wper = per * 2 - 1
    smrng = ema(avrng, wper) * mult

    src_vals = src.to_numpy()
    smrng_vals = smrng.to_numpy()
    n = len(src_vals)

    filt = np.full(n, np.nan)
    upward = np.zeros(n)
    downward = np.zeros(n)

    for i in range(n):
        x = src_vals[i]
        r = smrng_vals[i]
        prev_filt = filt[i - 1] if i > 0 and not np.isnan(filt[i - 1]) else 0.0
        if np.isnan(r):
            filt[i] = x
        else:
            if x > prev_filt:
                filt[i] = prev_filt if (x - r) < prev_filt else (x - r)
            else:
                filt[i] = prev_filt if (x + r) > prev_filt else (x + r)

        if i > 0:
            if filt[i] > filt[i - 1]:
                upward[i] = upward[i - 1] + 1
            elif filt[i] < filt[i - 1]:
                upward[i] = 0
            else:
                upward[i] = upward[i - 1]

            if filt[i] < filt[i - 1]:
                downward[i] = downward[i - 1] + 1
            elif filt[i] > filt[i - 1]:
                downward[i] = 0
            else:
                downward[i] = downward[i - 1]

    filt_s = pd.Series(filt, index=src.index)
    upward_s = pd.Series(upward, index=src.index)
    downward_s = pd.Series(downward, index=src.index)
    return filt_s, smrng, upward_s, downward_s


# =====================================================================================
# HULL SUITE
# =====================================================================================

def hma(src: pd.Series, length: int) -> pd.Series:
    return wma(2 * wma(src, length / 2) - wma(src, length), round(np.sqrt(length)))


def ehma(src: pd.Series, length: int) -> pd.Series:
    return ema(2 * ema(src, length / 2) - ema(src, length), round(np.sqrt(length)))


def thma(src: pd.Series, length: int) -> pd.Series:
    return wma(wma(src, length / 3) * 3 - wma(src, length / 2) - wma(src, length), length)


def hull_suite(src: pd.Series, mode: str, length: int, length_mult: float) -> pd.Series:
    eff_len = int(length * length_mult)
    if mode == "Hma":
        return hma(src, eff_len)
    if mode == "Ehma":
        return ehma(src, eff_len)
    if mode == "Thma":
        return thma(src, eff_len / 2)
    raise ValueError(f"Modo Hull desconocido: {mode}")


# =====================================================================================
# STC — Schaff Trend Cycle
# =====================================================================================

def stc(src: pd.Series, length: int, fast_len: int, slow_len: int, factor: float) -> pd.Series:
    macd = ema(src, fast_len) - ema(src, slow_len)
    macd_vals = macd.to_numpy()
    n = len(macd_vals)

    stc1 = np.full(n, np.nan)
    stc2 = np.full(n, np.nan)

    def rolling_extremes(vals, idx, length):
        lo = max(0, idx - length + 1)
        window = vals[lo: idx + 1]
        window = window[~np.isnan(window)]
        if len(window) == 0:
            return np.nan, np.nan
        return np.min(window), np.max(window)

    for i in range(n):
        lo_m, hi_m = rolling_extremes(macd_vals, i, length)
        range_macd = hi_m - lo_m if not np.isnan(hi_m) else np.nan
        if range_macd is not np.nan and range_macd > 0:
            k = (macd_vals[i] - lo_m) / range_macd * 100
        else:
            k = stc1[i - 1] if i > 0 and not np.isnan(stc1[i - 1]) else np.nan

        if i == 0 or np.isnan(stc1[i - 1]):
            stc1[i] = k
        else:
            stc1[i] = stc1[i - 1] + factor * (k - stc1[i - 1])

        lo_s, hi_s = rolling_extremes(stc1, i, length)
        range_stc1 = hi_s - lo_s if not np.isnan(hi_s) else np.nan
        if range_stc1 is not np.nan and range_stc1 > 0:
            d = (stc1[i] - lo_s) / range_stc1 * 100
        else:
            d = stc2[i - 1] if i > 0 and not np.isnan(stc2[i - 1]) else np.nan

        if i == 0 or np.isnan(stc2[i - 1]):
            stc2[i] = d
        else:
            stc2[i] = stc2[i - 1] + factor * (d - stc2[i - 1])

    stc2 = np.clip(stc2, 0, 100)
    return pd.Series(stc2, index=src.index)


# =====================================================================================
# DESCARGA DE DATOS
# =====================================================================================

def download(symbol: str, interval: str, period: str) -> pd.DataFrame:
    df = yf.download(symbol, interval=interval, period=period, auto_adjust=False, progress=False)
    if df.empty:
        raise RuntimeError(f"Yahoo Finance no devolvió datos para {symbol} ({interval}, {period}).")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Close"])
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    if "Volume" in df.columns:
        agg["Volume"] = "sum"
    out = df.resample(rule, label="right", closed="right").agg(agg)
    return out.dropna(subset=["Close"])


# =====================================================================================
# LÓGICA COMPLETA DEL INDICADOR
# =====================================================================================

def compute_ltf_signals(df15: pd.DataFrame) -> pd.DataFrame:
    src = (df15["High"] + df15["Low"]) / 2  # hl2, igual que "src" del Range Filter en el script

    filt, smrng, upward, downward = range_filter(src, RF_PER, RF_MULT)
    hband = filt + smrng
    lband = filt - smrng

    is_up_color = ((src > filt) & (src > src.shift(1)) & (upward > 0)) | \
                  ((src > filt) & (src < src.shift(1)) & (upward > 0))
    is_down_color = ((src < filt) & (src < src.shift(1)) & (downward > 0)) | \
                    ((src < filt) & (src > src.shift(1)) & (downward > 0))
    is_orange = ~(is_up_color | is_down_color)

    hull = hull_suite(df15["Close"], HULL_MODE, HULL_LENGTH, HULL_LENGTH_MULT)

    if TRIPLE_MA_FILTER:
        ma1 = ma(df15, MA1_LEN, MA1_TYPE)
        ma2 = ma(df15, MA2_LEN, MA2_TYPE)
        ma3 = ma(df15, MA3_LEN, MA3_TYPE)
        bullish_trend = (ma1 < ma2) & (ma2 < ma3)
        bearish_trend = (ma1 > ma2) & (ma2 > ma3)
    else:
        bullish_trend = pd.Series(True, index=df15.index)
        bearish_trend = pd.Series(True, index=df15.index)

    lng = is_orange.shift(1).fillna(False) & (~is_orange) & (hull > hull.shift(2)) & is_up_color & bullish_trend
    srt = is_orange.shift(1).fillna(False) & (~is_orange) & (hull < hull.shift(2)) & is_down_color & bearish_trend

    stc15 = stc(df15["Close"], STC_LEN, STC_FAST, STC_SLOW, STC_FACTOR)

    if TRIGGER_MODE == "Cruce":
        trigger_long = (stc15 > STC_OS) & (stc15.shift(1) <= STC_OS)
        trigger_short = (stc15 < STC_OB) & (stc15.shift(1) >= STC_OB)
    else:
        trigger_long = (stc15 > stc15.shift(1)) & (stc15 > STC_OS) & (stc15 < STC_OB)
        trigger_short = (stc15 < stc15.shift(1)) & (stc15 < STC_OB) & (stc15 > STC_OS)

    out = pd.DataFrame(index=df15.index)
    out["close"] = df15["Close"]
    out["lng"] = lng.fillna(False)
    out["srt"] = srt.fillna(False)
    out["stc15"] = stc15
    out["trigger_long"] = trigger_long.fillna(False)
    out["trigger_short"] = trigger_short.fillna(False)
    return out


def compute_htf_bias(df_htf: pd.DataFrame) -> pd.DataFrame:
    s = stc(df_htf["Close"], STC_LEN, STC_FAST, STC_SLOW, STC_FACTOR)
    bull = s > s.shift(1)
    bear = s < s.shift(1)
    if AVOID_EXHAUSTED:
        bull = bull & (s < STC_OB)
        bear = bear & (s > STC_OS)
    out = pd.DataFrame(index=df_htf.index)
    out["stc"] = s
    out["bias_bull"] = bull.fillna(False)
    out["bias_bear"] = bear.fillna(False)
    return out


def align_htf_to_ltf(ltf_index: pd.DatetimeIndex, htf_df: pd.DataFrame) -> pd.DataFrame:
    # Para cada vela LTF, toma el último valor HTF ya cerrado hasta ese momento
    # (equivalente a request.security con lookahead_off/gaps_off).
    return htf_df.reindex(ltf_index, method="ffill")


# =====================================================================================
# TELEGRAM
# =====================================================================================

def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[AVISO] Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID; no se envía Telegram.")
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=20)
    if resp.status_code != 200:
        print(f"[ERROR] Telegram respondió {resp.status_code}: {resp.text}", file=sys.stderr)


# =====================================================================================
# ESTADO (para no duplicar alertas entre ejecuciones del workflow)
# =====================================================================================

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


# =====================================================================================
# MAIN
# =====================================================================================

def format_price(price: float) -> str:
    # Precios cripto varían mucho en escala (BTC ~100000, DOGE ~0.15), así que
    # se ajustan los decimales según la magnitud para que se lea bien.
    if price >= 100:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:.4f}"
    return f"{price:.6f}"


def build_message(pair: dict, tag: str, direction: str, price: float, bar_id: str) -> str:
    coin_emoji = pair.get("emoji", "🪙")
    name = pair["name"]

    headers = {
        "full": "🔥 SEÑAL FULL",
        "partial": "⚠️ SEÑAL PARCIAL",
        "info": "ℹ️ SEÑAL INFO",
    }
    dir_line = {
        "long": "📈 LONG (compra)",
        "short": "📉 SHORT (venta)",
    }
    details = {
        "full": "✅ 15m + ✅ 1H + ✅ 4H alineados",
        "partial": "✅ 15m + confluencia parcial en 1H o 4H",
        "info": "Señal base (RF + Hull), sin confluencia STC",
    }

    lines = [
        f"{headers[tag]}  {coin_emoji}",
        f"━━━━━━━━━━━━━━━",
        f"🪙 Par: {name}",
        dir_line[direction],
        f"⏱️ Marco: 15m",
        f"💰 Precio: {format_price(price)}",
        f"📊 {details[tag]}",
        f"🕒 Vela: {bar_id}",
    ]
    return "\n".join(lines)


def process_pair(pair: dict, state: dict) -> bool:
    """Procesa un par. Devuelve True si el estado cambió (para saber si hay que guardarlo)."""
    binance_symbol = pair["symbol"]
    yf_symbol = YF_SYMBOLS.get(binance_symbol)
    if not yf_symbol:
        print(f"[AVISO] {binance_symbol} no tiene ticker de Yahoo Finance mapeado, se omite.")
        return False

    print(f"[{datetime.now(timezone.utc).isoformat()}] Procesando {pair['name']} ({yf_symbol})...")

    df15 = download(yf_symbol, YF_INTERVAL_LTF, YF_PERIOD_LTF)
    df1h_raw = download(yf_symbol, "60m", YF_PERIOD_1H)
    df4h = resample_ohlc(df1h_raw, "4h")

    ltf = compute_ltf_signals(df15)
    bias1h = compute_htf_bias(df1h_raw)
    bias4h = compute_htf_bias(df4h)

    bias1h_aligned = align_htf_to_ltf(ltf.index, bias1h)
    bias4h_aligned = align_htf_to_ltf(ltf.index, bias4h)

    df = ltf.join(bias1h_aligned.add_prefix("h1_")).join(bias4h_aligned.add_prefix("h4_"))

    # Se descarta la última fila: puede ser la vela 15m aún en formación
    # (equivalente a exigir barstate.isconfirmed en Pine).
    df_closed = df.iloc[:-1]
    if df_closed.empty:
        print(f"  Sin velas cerradas suficientes todavía para {binance_symbol}.")
        return False

    last = df_closed.iloc[-1]
    last_time = df_closed.index[-1]

    full_long = last["lng"] and last["trigger_long"] and last["h1_bias_bull"] and last["h4_bias_bull"]
    full_short = last["srt"] and last["trigger_short"] and last["h1_bias_bear"] and last["h4_bias_bear"]

    partial_long = last["lng"] and last["trigger_long"] and (last["h1_bias_bull"] or last["h4_bias_bull"]) and not full_long
    partial_short = last["srt"] and last["trigger_short"] and (last["h1_bias_bear"] or last["h4_bias_bear"]) and not full_short

    # Nota: las señales sin confluencia STC (antes "info") ya no se reportan;
    # solo se notifican FULL y PARCIAL.

    last_alerted = state.get(binance_symbol)
    bar_id = last_time.isoformat()

    if last_alerted == bar_id:
        print(f"  Vela {bar_id} ya notificada previamente para {binance_symbol}.")
        return False

    price = float(last["close"])
    msg = None

    if full_long:
        msg = build_message(pair, "full", "long", price, bar_id)
    elif full_short:
        msg = build_message(pair, "full", "short", price, bar_id)
    elif partial_long:
        msg = build_message(pair, "partial", "long", price, bar_id)
    elif partial_short:
        msg = build_message(pair, "partial", "short", price, bar_id)

    if msg:
        print(f"  >> Señal detectada para {binance_symbol}, enviando a Telegram.")
        send_telegram(msg)
        state[binance_symbol] = bar_id
        return True

    print(f"  Sin señal en la última vela cerrada de {binance_symbol} ({bar_id}).")
    return False


def main():
    state = load_state()
    state_changed = False

    for pair in PAIRS:
        try:
            changed = process_pair(pair, state)
            state_changed = state_changed or changed
        except Exception as exc:
            print(f"[ERROR] Fallo procesando {pair['symbol']}: {exc}", file=sys.stderr)

    if state_changed:
        save_state(state)


if __name__ == "__main__":
    main()
