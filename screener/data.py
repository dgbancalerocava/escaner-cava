"""Descarga de datos y mantenimiento de las listas de valores."""
from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


# ------------------------------------------------------------------ universo
def refrescar_universo(carpeta: Path, log=print):
    """Intenta actualizar S&P 500 y Nasdaq 100 desde fuentes públicas.
    Si falla, se mantienen las listas guardadas en el repositorio."""
    import requests
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        d = pd.read_csv(io.StringIO(requests.get(url, headers=UA, timeout=30).text))
        out = pd.DataFrame({"ticker": d.Symbol.str.replace(".", "-", regex=False),
                            "name": d.Security, "sector": d["GICS Sector"]})
        if len(out) > 450:
            out.to_csv(carpeta / "sp500.csv", index=False)
            log(f"S&P 500 actualizado: {len(out)} valores")
    except Exception as e:  # noqa: BLE001
        log(f"No se pudo actualizar S&P 500 ({e}); uso la lista guardada")
    try:
        html = requests.get("https://en.wikipedia.org/wiki/Nasdaq-100", headers=UA, timeout=30).text
        for t in pd.read_html(io.StringIO(html)):
            cols = [str(c).lower() for c in t.columns]
            if "ticker" in cols and len(t) > 90:
                tc = t.columns[cols.index("ticker")]
                nc = t.columns[cols.index("company")] if "company" in cols else tc
                sc = next((t.columns[i] for i, c in enumerate(cols) if "sector" in c), None)
                out = pd.DataFrame({"ticker": t[tc].astype(str).str.replace(".", "-", regex=False),
                                    "name": t[nc], "sector": t[sc] if sc is not None else ""})
                out.to_csv(carpeta / "nasdaq100.csv", index=False)
                log(f"Nasdaq 100 actualizado: {len(out)} valores")
                break
    except Exception as e:  # noqa: BLE001
        log(f"No se pudo actualizar Nasdaq 100 ({e}); uso la lista guardada")


def cargar_universo(carpeta: Path, archivos: list[str]) -> pd.DataFrame:
    filas = []
    for f in archivos:
        d = pd.read_csv(carpeta / f)
        d["grupo"] = f.replace(".csv", "")
        filas.append(d)
    u = pd.concat(filas, ignore_index=True)
    for c in ("name", "sector", "ucits"):
        if c not in u:
            u[c] = ""
    u = u.fillna("")
    # un valor puede estar en varias listas (p.ej. S&P 500 y Nasdaq 100): se analiza una vez
    u = u.groupby("ticker", as_index=False, sort=False).agg(
        {"name": "first", "sector": "first", "ucits": "first", "grupo": lambda s: "/".join(dict.fromkeys(s))})
    return u


# ------------------------------------------------------------------ precios
def _limpiar(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df if len(df) > 60 else None


def descargar(tickers: list[str], anios=5, lote=60, log=print) -> dict[str, pd.DataFrame]:
    import yfinance as yf
    datos: dict[str, pd.DataFrame] = {}
    periodo = f"{anios}y"
    for i in range(0, len(tickers), lote):
        grupo = tickers[i:i + lote]
        for intento in range(3):
            try:
                raw = yf.download(grupo, period=periodo, interval="1d", auto_adjust=True,
                                  group_by="ticker", threads=True, progress=False)
                break
            except Exception as e:  # noqa: BLE001
                log(f"  error descargando lote ({e}); reintento {intento + 1}")
                time.sleep(10 * (intento + 1))
                raw = None
        for t in grupo:
            try:
                sub = raw[t] if raw is not None and len(grupo) > 1 else raw
                df = _limpiar(sub.copy()) if sub is not None else None
                if df is not None:
                    datos[t] = df
            except Exception:  # noqa: BLE001
                pass
        log(f"  descargados {min(i + lote, len(tickers))}/{len(tickers)}")
        time.sleep(2)

    # reintento individual de los que fallaron
    faltan = [t for t in tickers if t not in datos]
    for t in faltan:
        try:
            df = _limpiar(yf.Ticker(t).history(period=periodo, auto_adjust=True))
            if df is not None:
                datos[t] = df
                continue
        except Exception:  # noqa: BLE001
            pass
        df = _stooq(t)
        if df is not None:
            datos[t] = df
        time.sleep(0.5)
    return datos


def _stooq(ticker: str) -> pd.DataFrame | None:
    """Fuente alternativa para valores de EEUU si Yahoo falla."""
    if "." in ticker or ticker.startswith("^"):
        return None
    import requests
    try:
        url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d"
        txt = requests.get(url, headers=UA, timeout=20).text
        df = pd.read_csv(io.StringIO(txt), parse_dates=["Date"], index_col="Date")
        return _limpiar(df.iloc[-1300:])
    except Exception:  # noqa: BLE001
        return None
