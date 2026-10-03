"""Indicadores técnicos usados por el método (implementación propia, sin dependencias extra)."""
import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def wilder(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1 / n, adjust=False).mean()


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def rsi(close: pd.Series, n=14) -> pd.Series:
    d = close.diff()
    up = wilder(d.clip(lower=0), n)
    down = wilder((-d).clip(lower=0), n)
    rs = up / down.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(100.0).where(down.notna())


def stochastic(high, low, close, n=14, k_smooth=3, d_smooth=3):
    ll = low.rolling(n).min()
    hh = high.rolling(n).max()
    raw = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    k = raw.rolling(k_smooth).mean()
    d = k.rolling(d_smooth).mean()
    return k, d


def atr(high, low, close, n=14) -> pd.Series:
    pc = close.shift()
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return wilder(tr, n)


def adx(high, low, close, n=14) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr_n = atr(high, low, close, n)
    plus_di = 100 * wilder(pd.Series(plus_dm, index=high.index), n) / tr_n
    minus_di = 100 * wilder(pd.Series(minus_dm, index=high.index), n) / tr_n
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return wilder(dx.fillna(0), n)


def parabolic_sar(high: pd.Series, low: pd.Series, step=0.02, max_step=0.2) -> pd.Series:
    h, l = high.values, low.values
    n = len(h)
    sar = np.full(n, np.nan)
    if n < 3:
        return pd.Series(sar, index=high.index)
    bull = True
    af = step
    ep = h[0]
    sar[0] = l[0]
    for i in range(1, n):
        prev = sar[i - 1]
        cur = prev + af * (ep - prev)
        if bull:
            cur = min(cur, l[i - 1], l[i - 2] if i >= 2 else l[i - 1])
            if l[i] < cur:
                bull, cur, ep, af = False, ep, l[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, max_step)
        else:
            cur = max(cur, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > cur:
                bull, cur, ep, af = True, ep, h[i], step
            elif l[i] < ep:
                ep, af = l[i], min(af + step, max_step)
        sar[i] = cur
    return pd.Series(sar, index=high.index)


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Convierte velas diarias a semanales ('W-FRI') o mensuales ('ME')."""
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return df.resample(rule).agg(agg).dropna(subset=["Close"])


def add_all(df: pd.DataFrame) -> pd.DataFrame:
    """Añade al DataFrame OHLCV todas las columnas de indicadores."""
    out = df.copy()
    h, l, c = out["High"], out["Low"], out["Close"]
    out["macd"], out["macd_sig"], out["macd_hist"] = macd(c)
    out["rsi14"] = rsi(c, 14)
    out["rsi2"] = rsi(c, 2)
    out["sto50"], _ = stochastic(h, l, c, 50)
    out["sto89"], _ = stochastic(h, l, c, 89)
    out["sto_k"], out["sto_d"] = stochastic(h, l, c, 14)
    out["atr"] = atr(h, l, c)
    out["adx"] = adx(h, l, c)
    out["sma200"] = c.rolling(200).mean()
    out["sma40"] = c.rolling(40).mean()
    out["vol20"] = out["Volume"].rolling(20).mean()
    out["sar"] = parabolic_sar(h, l)
    return out
