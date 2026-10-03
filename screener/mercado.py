"""Filtro de mercado: ¿el índice de referencia acompaña?

Un día es "favorable" si el índice tiene el MACD semanal (de la última semana cerrada) por
encima de cero y cierra por encima de su media de 200 sesiones.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind

INDICE_POR_GRUPO = {"sp500": "^GSPC", "nasdaq100": "^GSPC", "etfs": "^GSPC",
                    "ibex35": "^IBEX", "europe_tech": "^STOXX50E"}


def indice_de(grupo: str, cfg: dict) -> str | None:
    mapa = (cfg.get("filtro_mercado") or {}).get("indice_por_grupo") or INDICE_POR_GRUPO
    return mapa.get(str(grupo).split("/")[0])


def regimen(df_indice: pd.DataFrame) -> pd.Series:
    """Serie booleana por fecha: True = mercado favorable para largos."""
    sem = ind.resample(df_indice, "W-FRI")
    macd_w, _, _ = ind.macd(sem["Close"])
    fechas = df_indice.index
    pos = macd_w.index.searchsorted(fechas, side="right") - 1     # última semana cerrada (etiqueta <= fecha)
    w = np.where(pos >= 0, macd_w.values[np.clip(pos, 0, None)], np.nan)
    sma = df_indice["Close"].rolling(200).mean().values
    ok = (w > 0) & (df_indice["Close"].values > sma)
    return pd.Series(ok, index=fechas)


def regimenes(precios: dict, cfg: dict) -> dict[str, pd.Series]:
    out = {}
    mapa = (cfg.get("filtro_mercado") or {}).get("indice_por_grupo") or INDICE_POR_GRUPO
    for t in set(mapa.values()):
        if t in precios and len(precios[t]) > 220:
            out[t] = regimen(precios[t])
    return out


def mercado_ok(regs: dict, grupo: str, fecha, cfg: dict) -> bool | None:
    t = indice_de(grupo, cfg)
    s = regs.get(t)
    if s is None:
        return None
    s = s.loc[:pd.Timestamp(fecha)]
    return bool(s.iloc[-1]) if len(s) else None
