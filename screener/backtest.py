"""
Backtest histórico: recorre cada valor día a día como si el escáner se hubiera ejecutado
cada noche de los últimos años, registra las señales verdes (y las descartadas por R/R
como grupo de control) y simula su resultado con evaluacion.simular.

Notas honestas sobre sus límites:
- Sesgo de supervivencia: se usan las listas ACTUALES del S&P 500 / Nasdaq / IBEX, así que
  no aparecen empresas que cayeron del índice. Esto suele inflar algo los resultados.
- Solo marco diario (el semanal daría muy pocas operaciones para medir).
- El MACD semanal/mensual se toma de la última semana/mes cerrado (sin mirar al futuro).
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from . import indicators as ind
from .engine import evaluar
from .evaluacion import simular

MIN_HIST = 260   # sesiones mínimas antes de empezar a evaluar (media 200 + margen)


def _macd_asof(df: pd.DataFrame, regla: str):
    agg = ind.resample(df, regla)
    line, sig, _ = ind.macd(agg["Close"])
    return line, sig


def backtest_valor(args) -> list[dict]:
    ticker, df, cfg, nombre, grupo = args
    if len(df) < MIN_HIST + 30:
        return []
    d = ind.add_all(df)
    wl, _ = _macd_asof(df, "W-FRI")
    ml, ms = _macd_asof(df, "ME")
    fechas = d.index
    # valor de la última semana / mes CERRADO para cada día (etiqueta <= fecha)
    w_label = wl.index.searchsorted(fechas, side="right") - 1
    w_val = pd.Series(np.where(w_label >= 0, wl.values[np.clip(w_label, 0, None)], np.nan), index=fechas)
    m_label = ml.index.searchsorted(fechas, side="right") - 1
    m_alc = pd.Series(np.where(m_label >= 0, (ml > ms).values[np.clip(m_label, 0, None)], False), index=fechas)

    ctx = cfg["contexto"]
    C, sma = d["Close"].values, d["sma200"].values
    sar = ind.parabolic_sar(df["High"], df["Low"])
    vistos, ocupado_hasta, ops = set(), None, []
    for i in range(MIN_HIST, len(d) - 1):
        # prefiltro barato (mismas condiciones que el contexto del motor)
        if ctx["precio_sobre_media_200"] and not C[i] > sma[i]:
            continue
        if ctx["macd_semanal_sobre_cero"] and not (w_val.iloc[i] > 0):
            continue
        if ocupado_hasta is not None and fechas[i] <= ocupado_hasta:
            continue          # ya hay una operación abierta en este valor
        r = evaluar(d.iloc[: i + 1], ticker, cfg, "D", nombre, grupo, precalculado=True,
                    macd_sup=float(w_val.iloc[i]), macd_men_alc=bool(m_alc.iloc[i]))
        tecnica = r.estado == "SENAL" or (r.estado == "TRAMPA" and "sin R/R" in r.disparo)
        if not tecnica:
            continue
        clave = r.fecha_techo
        if clave in vistos:
            continue
        vistos.add(clave)
        sim = simular(df, r.fecha, r.stop, r.objetivo1, r.objetivo2, sar)
        if sim.get("estado") in ("pendiente", None):
            continue
        ops.append({"fecha": r.fecha, "ticker": ticker, "nombre": nombre, "grupo": grupo, "marco": "D",
                    "disparo": r.disparo, "pasa_filtro": r.estado == "SENAL", "entrada_ref": r.entrada,
                    "stop": r.stop, "objetivo1": r.objetivo1, "objetivo2": r.objetivo2, "rr": r.rr,
                    "puntuacion": r.puntuacion,
                    "vol_trampa": bool(r.volumen_barrida >= cfg["trampa"]["volumen_manos_fuertes"])
                    if not np.isnan(r.volumen_barrida) else False,
                    "n_confirmaciones": len(r.confirmaciones), "fecha_techo": r.fecha_techo, **sim})
        if r.estado == "SENAL" and sim.get("estado") != "anulada":
            fin = sim.get("fija_salida")
            ocupado_hasta = pd.Timestamp(fin) if fin else fechas[-1]
    return ops


def ejecutar(precios: dict, info: pd.DataFrame, cfg: dict, procesos: int = 4, log=print) -> pd.DataFrame:
    tareas = [(t, df, cfg, info.loc[t, "name"], info.loc[t, "grupo"])
              for t, df in precios.items() if not t.startswith("^")]
    filas = []
    with ProcessPoolExecutor(max_workers=procesos) as ex:
        for k, ops in enumerate(ex.map(backtest_valor, tareas, chunksize=4), 1):
            filas.extend(ops)
            if k % 50 == 0:
                log(f"  backtest {k}/{len(tareas)} valores · {len(filas)} operaciones")
    ops = pd.DataFrame(filas)
    if not ops.empty:
        for c in ("fija_estado", "seg_estado", "fija_salida", "seg_salida"):
            if c not in ops:
                ops[c] = None
    return ops
