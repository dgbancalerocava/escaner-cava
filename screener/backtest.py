"""
Backtest histórico y comparación de variantes del método.

1) PASADA BASE (cara): recorre cada valor día a día como si el escáner se hubiera ejecutado
   cada noche, con todos los disparos permitidos y sin filtro de mercado, y apunta cada señal
   técnica (incluidas las descartadas por R/R) junto con sus características y si el índice
   de referencia acompañaba ese día. Cada señal se simula con las tres gestiones.
2) VARIANTES (barato): se construyen filtrando esa lista, sin volver a recorrer el histórico.

Límites honestos:
- Sesgo de supervivencia: listas ACTUALES de los índices.
- Solo marco diario. Sin comisiones. Entrada a la apertura siguiente.
- El MACD semanal/mensual se toma de la última semana/mes cerrado (sin mirar al futuro).
"""
from __future__ import annotations

import copy
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from . import indicators as ind
from . import mercado as MK
from . import puntuacion as PT
from .engine import evaluar
from .evaluacion import region, simular

MIN_HIST = 260   # sesiones mínimas antes de empezar a evaluar (media 200 + margen)


def _macd_cerrado(df: pd.DataFrame, regla: str, fechas):
    agg = ind.resample(df, regla)
    line, sig, _ = ind.macd(agg["Close"])
    pos = line.index.searchsorted(fechas, side="right") - 1   # etiqueta <= fecha => barra cerrada
    ok = pos >= 0
    p = np.clip(pos, 0, None)
    return (np.where(ok, line.values[p], np.nan),
            np.where(ok, (line > sig).values[p], False))


def backtest_valor(args) -> list[dict]:
    ticker, df, cfg, nombre, grupo, reg = args
    if len(df) < MIN_HIST + 30:
        return []
    cfg = copy.deepcopy(cfg)
    cfg.setdefault("disparo", {})["permitidos"] = ["recuperacion", "ruptura"]   # pasada base: todo
    cfg.setdefault("filtro_mercado", {})["activo"] = False
    g = cfg.get("gestion") or {}
    d = ind.add_all(df)
    fechas = d.index
    w_val, _ = _macd_cerrado(df, "W-FRI", fechas)
    _, m_alc = _macd_cerrado(df, "ME", fechas)
    reg = reg.reindex(fechas, method="ffill") if reg is not None else None

    ctx = cfg["contexto"]
    C, sma = d["Close"].values, d["sma200"].values
    sar = ind.parabolic_sar(df["High"], df["Low"])
    vistos, ops = set(), []
    for i in range(MIN_HIST, len(d) - 1):
        if ctx["precio_sobre_media_200"] and not C[i] > sma[i]:
            continue
        if ctx["macd_semanal_sobre_cero"] and not (w_val[i] > 0):
            continue
        r = evaluar(d.iloc[: i + 1], ticker, cfg, "D", nombre, grupo, precalculado=True,
                    macd_sup=float(w_val[i]), macd_men_alc=bool(m_alc[i]))
        tecnica = r.estado == "SENAL" or (r.estado == "TRAMPA" and "sin R/R" in r.disparo)
        if not tecnica:
            continue
        tipo = r.disparo.replace(" (sin R/R)", "")
        clave = (r.fecha_techo, tipo, r.estado == "SENAL")
        if clave in vistos:
            continue
        vistos.add(clave)
        sim = simular(df, r.fecha, r.stop, r.objetivo1, r.objetivo2, sar,
                      be_R=g.get("breakeven_R", 1.0), bloqueo_en_R=g.get("bloqueo_en_R", 2.0),
                      bloqueo_a_R=g.get("bloqueo_a_R", 1.0))
        if sim.get("estado") in ("pendiente", None):
            continue
        ops.append({"fecha": r.fecha, "ticker": ticker, "nombre": nombre, "grupo": grupo, "marco": "D",
                    "disparo": r.disparo, "tipo": tipo, "pasa_filtro": r.estado == "SENAL",
                    "entrada_ref": r.entrada, "stop": r.stop, "objetivo1": r.objetivo1, "objetivo2": r.objetivo2,
                    "rr": r.rr, "riesgo_plan": r.riesgo_pct, "puntuacion": r.puntuacion,
                    "retroceso": r.retroceso, "ratio_tiempo": r.ratio_tiempo,
                    "volumen_barrida": r.volumen_barrida, "rsi14": r.rsi14, "adx": r.adx, "sto50": r.sto50,
                    "dist_sma200": 100 * (C[i] / sma[i] - 1),
                    "macd_mensual_alcista": bool(m_alc[i]),
                    "mercado_ok": bool(reg.iloc[i]) if reg is not None and not pd.isna(reg.iloc[i]) else None,
                    "vol_trampa": bool(r.volumen_barrida >= cfg["trampa"]["volumen_manos_fuertes"])
                    if not np.isnan(r.volumen_barrida) else False,
                    "n_confirmaciones": len(r.confirmaciones), "fecha_techo": r.fecha_techo, **sim})
    return ops


def ejecutar(precios: dict, info: pd.DataFrame, cfg: dict, procesos: int = 4, log=print) -> pd.DataFrame:
    regs = MK.regimenes(precios, cfg)
    tareas = []
    for t, df in precios.items():
        if t.startswith("^"):
            continue
        grupo = info.loc[t, "grupo"]
        tareas.append((t, df, cfg, info.loc[t, "name"], grupo, regs.get(MK.indice_de(grupo, cfg))))
    filas = []
    with ProcessPoolExecutor(max_workers=procesos) as ex:
        for k, ops in enumerate(ex.map(backtest_valor, tareas, chunksize=4), 1):
            filas.extend(ops)
            if k % 50 == 0:
                log(f"  backtest {k}/{len(tareas)} valores · {len(filas)} señales técnicas")
    ops = pd.DataFrame(filas)
    if not ops.empty:
        for c in ("fija_estado", "seg_estado", "ges_estado", "fija_salida", "seg_salida", "ges_salida"):
            if c not in ops:
                ops[c] = None
        ops["region"] = ops.grupo.map(region)
    return ops


# =========================================================================== variantes
def _una_por_estructura(ops: pd.DataFrame) -> pd.DataFrame:
    return ops.sort_values("fecha").drop_duplicates(["ticker", "fecha_techo"], keep="first")


def _sin_solapes(ops: pd.DataFrame, col_salida: str) -> pd.DataFrame:
    """Una sola operación abierta por valor a la vez."""
    keep = []
    for _, g in ops.sort_values("fecha_entrada").groupby("ticker", sort=False):
        fin = None
        for i, row in g.iterrows():
            if row.get("estado") == "anulada":
                continue
            if fin is not None and row.fecha_entrada <= fin:
                continue
            keep.append(i)
            fin = row[col_salida] if isinstance(row[col_salida], str) else "9999-12-31"
    return ops.loc[keep]


def _max_por_dia(ops: pd.DataFrame, n: int, col: str) -> pd.DataFrame:
    return ops.sort_values([col, "rr"], ascending=[False, False]).groupby("fecha", sort=False).head(n)


def _metricas(ops: pd.DataFrame, gestion: str) -> dict:
    col_R, col_e, col_s = f"{gestion}_R", f"{gestion}_estado", f"{gestion}_salida"
    c = ops[ops[col_e] == "cerrada"].sort_values(col_s)
    if c.empty:
        return {"n": 0}
    R = c[col_R]
    anios = max((pd.Timestamp(c.fecha.max()) - pd.Timestamp(c.fecha.min())).days / 365.25, 0.5)
    perd = (R <= 0).astype(int)
    racha = int(perd.groupby((perd != perd.shift()).cumsum()).cumsum().max())
    curva = R.cumsum()
    gan, per = R[R > 0], R[R <= 0]
    return {"n": int(len(R)), "por_anio": round(len(R) / anios, 0), "acierto_pct": round(100 * (R > 0).mean(), 1),
            "R_medio": round(float(R.mean()), 2), "R_anio": round(float(R.sum()) / anios, 1),
            "profit_factor": round(float(gan.sum() / -per.sum()), 2) if per.sum() < 0 else None,
            "racha_perdedora": racha, "max_drawdown_R": round(float((curva - curva.cummax()).min()), 1)}


def variantes(ops: pd.DataFrame, cfg: dict, corte: str = "2024-01-01", max_dia: int = 2, log=print):
    """Construye las variantes A–E y devuelve (tabla, dict de DataFrames, modelo de puntuación)."""
    ops = ops.copy()
    ops["fecha_entrada"] = ops["fecha_entrada"].fillna(ops["fecha"])
    base = ops[ops.pasa_filtro.astype(bool)]
    ops["n_dia"] = ops.fecha.map(base.groupby("fecha").size()).fillna(0)
    base = ops[ops.pasa_filtro.astype(bool)]

    V = {}
    V["A"] = ("Método actual", "fija", _sin_solapes(_una_por_estructura(base), "fija_salida"))
    V["B"] = ("A + stop a la entrada en +1R", "ges", _sin_solapes(_una_por_estructura(base), "ges_salida"))
    rec = base[base.tipo.str.contains("recuperación")]
    V["C"] = ("B + solo disparo de recuperación con volumen", "ges",
              _sin_solapes(_una_por_estructura(rec), "ges_salida"))
    rec_m = rec[rec.mercado_ok.astype("boolean").fillna(True).astype(bool)]
    V["D"] = ("C + filtro de tendencia del índice", "ges", _sin_solapes(_una_por_estructura(rec_m), "ges_salida"))

    # E: puntuación aprendida SOLO con el periodo de aprendizaje de D (sin solapes) y máx. N señales/día
    d_full = _una_por_estructura(rec_m)
    train = d_full[(d_full.fecha < corte) & (d_full.ges_estado == "cerrada")]
    modelo = PT.entrenar(train, "ges_R")
    modelo["corte"] = corte
    d_full = d_full.assign(punt2=PT.puntuar(d_full, modelo))
    V["E"] = (f"D + puntuación aprendida, máx. {max_dia} señales/día", "ges",
              _sin_solapes(_max_por_dia(d_full, max_dia, "punt2"), "ges_salida"))

    filas = []
    for k, (desc, gest, df) in V.items():
        fila = {"variante": k, "descripcion": desc, "gestion": gest}
        for etiqueta, sub in (("aprendizaje", df[df.fecha < corte]), ("validacion", df[df.fecha >= corte])):
            fila[etiqueta] = _metricas(sub, gest)
        fila["total"] = _metricas(df, gest)
        filas.append(fila)

    # ¿la puntuación aprendida ordena bien en validación?
    val = d_full[(d_full.fecha >= corte) & (d_full.ges_estado == "cerrada")]
    monot = {}
    if not val.empty:
        for p_, g in val.groupby(np.clip(val.punt2, -2, 3)):
            monot[str(int(p_))] = {"n": int(len(g)), "R_medio": round(float(g.ges_R.mean()), 2)}
    return filas, {k: v[2] for k, v in V.items()}, modelo, monot
