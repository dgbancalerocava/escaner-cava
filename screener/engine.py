"""
Motor de reglas: traduce el método de José Luis Cava a condiciones medibles.

Secuencia para cada valor (largos):
  1. CONTEXTO  -> MACD del marco superior > 0, precio sobre su media larga,
                  tramo previo fuerte (RSI >= 60, ADX >= 20).
  2. ALERTA    -> estocásticos lentos (50/89) en sobreventa o retroceso >= 38,2 %.
  3. ESTRUCTURA-> techo del tramo, inicio del tramo, mínimo de la corrección,
                  directriz bajista (recta que une el techo con los máximos decrecientes).
  4. TRAMPA    -> barrida: perfora un mínimo relevante y recupera en pocas sesiones.
  5. DISPARO   -> cierre por encima de la directriz, con R/R >= 3.

Estados resultantes:
  SENAL      (verde)   trampa + ruptura de directriz + R/R suficiente
  TRAMPA     (naranja) trampa hecha, falta la ruptura; se da el nivel de disparo
  VIGILANCIA (amarillo) contexto + alerta, sin trampa todavía
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from . import indicators as ind


@dataclass
class Resultado:
    ticker: str
    nombre: str = ""
    grupo: str = ""
    marco: str = "D"           # D = diario, W = semanal
    estado: str = "NADA"       # SENAL / TRAMPA / VIGILANCIA / NADA
    motivo: str = ""
    fecha: str = ""
    cierre: float = math.nan
    puntuacion: float = 0.0
    # estructura
    techo: float = math.nan
    fecha_techo: str = ""
    inicio_tramo: float = math.nan
    minimo_correccion: float = math.nan
    retroceso: float = math.nan
    ratio_tiempo: float = math.nan
    directriz_hoy: float = math.nan
    directriz_manana: float = math.nan
    # trampa
    nivel_barrido: float = math.nan
    fecha_barrida: str = ""
    minimo_barrida: float = math.nan
    volumen_barrida: float = math.nan
    # plan
    entrada: float = math.nan
    stop: float = math.nan
    objetivo1: float = math.nan
    objetivo2: float = math.nan
    rr: float = math.nan
    rr_obj1: float = math.nan
    riesgo_pct: float = math.nan
    acciones: int = 0
    # indicadores
    macd_superior: float = math.nan
    macd_mensual_alcista: bool = False
    rsi14: float = math.nan
    rsi2: float = math.nan
    sto50: float = math.nan
    sto89: float = math.nan
    adx: float = math.nan
    sar: float = math.nan
    disparo: str = ""          # recuperación / ruptura / degradada (sin R/R)
    dist_sma200: float = math.nan
    puntuacion2: float = math.nan   # puntuación aprendida del backtest (si existe)
    seleccionada: bool = False      # ⭐ prioritaria (calidad alta)
    calidad: int = 0                # índice de calidad -1..5 (ver puntuacion.calidad)
    motivos_calidad: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    confirmaciones: list = field(default_factory=list)
    # interno para los gráficos (no se exporta)
    _linea: tuple | None = None

    def to_dict(self):
        d = asdict(self)
        d.pop("_linea", None)
        for k, v in d.items():
            if isinstance(v, float):
                d[k] = None if (v is None or math.isnan(v)) else round(v, 4)
        return d


# ----------------------------------------------------------------- utilidades
def _pivots_low(low: np.ndarray, w: int, last_confirmed: int):
    out = []
    for i in range(w, last_confirmed + 1):
        win = low[i - w: i + w + 1]
        if low[i] == win.min() and np.argmin(win) == w:
            out.append(i)
    return out


def _directriz(high: np.ndarray, top: int, upto: int):
    """Recta desde el techo que deja por debajo todos los máximos (top, upto].
    Devuelve (pendiente, índice del punto de apoyo) o (None, None)."""
    if upto <= top:
        return None, None
    js = np.arange(top + 1, upto + 1)
    slopes = (high[js] - high[top]) / (js - top)
    k = int(np.argmax(slopes))
    slope = float(slopes[k])
    return min(slope, 0.0), int(js[k])


def _fmt(idx, i):
    return idx[i].strftime("%Y-%m-%d")


# ------------------------------------------------------------ análisis de estructura
def _estructura(df: pd.DataFrame, top: int, cfg: dict):
    """Evalúa la corrección que empieza en `top`. Devuelve dict o None."""
    est, tr, dp = cfg["estructura"], cfg["trampa"], cfg["disparo"]
    H, L, C, V = (df[c].values for c in ("High", "Low", "Close", "Volume"))
    vol20 = df["vol20"].values
    n = len(df)
    today = n - 1

    start_lo = max(0, top - 90)
    if top - start_lo < 5:
        return None
    start = start_lo + int(np.argmin(L[start_lo:top]))
    impulso = H[top] - L[start]
    if impulso <= 0:
        return None
    corr_idx = top + 1 + int(np.argmin(L[top + 1: today + 1]))
    corr_low = L[corr_idx]
    retro = (H[top] - corr_low) / impulso
    ratio_t = (today - top) / max(1, top - start)

    # --- trampa / barrida
    w = est["ventana_pivote"]
    piv = [p for p in _pivots_low(L, w, today - w) if p >= start]
    trampa = None
    s_from = max(top + 1, today - tr["ventana"])
    for s in range(today, s_from - 1, -1):          # barrida más reciente primero
        for p in sorted(piv, reverse=True):
            if p + w >= s:
                continue
            nivel = L[p]
            if L[s] >= nivel:
                continue
            # antes de la barrida el nivel aguantó en cierre
            if (C[p + 1: s] < nivel).any():
                continue
            # recupera en pocas sesiones y sigue por encima hoy
            rec = [r for r in range(s, min(today, s + tr["sesiones_recuperacion"]) + 1) if C[r] > nivel]
            if not rec or C[today] <= nivel:
                continue
            r = rec[0]
            if (C[r:today + 1] < nivel).any():
                continue
            vmax = np.nanmax(V[s:r + 1])
            vrel = vmax / vol20[s] if vol20[s] and not np.isnan(vol20[s]) and vol20[s] > 0 else np.nan
            trampa = dict(p=p, s=s, r=r, nivel=nivel, min_barrida=float(L[s:today + 1].min()), vrel=vrel)
            break
        if trampa:
            break
    if trampa and tr.get("exigir_volumen") and not (trampa["vrel"] >= tr["volumen_manos_fuertes"]):
        trampa = None

    # --- ruptura de directriz (después de la trampa si la hay)
    ruptura = None
    t_from = (trampa["r"] if trampa else top + 2)
    for t in range(max(t_from, top + 2), today + 1):
        slope, _ = _directriz(H, top, t - 1)
        if slope is None:
            continue
        linea_t = H[top] + slope * (t - top)
        if C[t] > linea_t and C[t - 1] <= H[top] + slope * (t - 1 - top) + 1e-12:
            ruptura = dict(t=t, linea=linea_t, slope=slope)
    slope_now, apoyo = _directriz(H, top, today - 1 if today - 1 > top else today)
    if slope_now is None:
        slope_now = 0.0
    linea_hoy = H[top] + slope_now * (today - top)
    slope_tm, _ = _directriz(H, top, today)
    linea_man = H[top] + (slope_tm or 0.0) * (today + 1 - top)

    return dict(top=top, start=start, impulso=impulso, corr_idx=corr_idx, corr_low=corr_low,
                retro=retro, ratio_t=ratio_t, trampa=trampa, ruptura=ruptura,
                linea_hoy=linea_hoy, linea_man=linea_man, slope=slope_tm or 0.0)


# --------------------------------------------------------------------- evaluación
def evaluar(df_raw: pd.DataFrame, ticker: str, cfg: dict, marco="D", nombre="", grupo="",
            df_superior: pd.DataFrame | None = None, df_mensual: pd.DataFrame | None = None,
            precalculado: bool = False, macd_sup: float | None = None,
            macd_men_alc: bool | None = None, mercado_ok: bool | None = None) -> Resultado:
    """Evalúa el último día de `df_raw`.
    Para el backtest se pasa `precalculado=True` (df ya con indicadores) y los valores
    del MACD semanal/mensual ya calculados, así no se recalcula todo cada día."""
    ctx, al, est, tr, dp = cfg["contexto"], cfg["alerta"], cfg["estructura"], cfg["trampa"], cfg["disparo"]
    res = Resultado(ticker=ticker, nombre=nombre, grupo=grupo, marco=marco)
    df = df_raw if precalculado else ind.add_all(df_raw)
    n = len(df)
    if n < 120:
        res.motivo = "histórico insuficiente"
        return res
    today = n - 1
    last = df.iloc[-1]
    idx = df.index
    res.fecha = _fmt(idx, today)
    res.cierre = float(last.Close)
    for k in ("rsi14", "rsi2", "sto50", "sto89", "adx", "sar"):
        setattr(res, k, float(last[k]))
    media_larga = last["sma200"] if marco == "D" else last["sma40"]
    if media_larga and not np.isnan(media_larga):
        res.dist_sma200 = float(100 * (last.Close / media_larga - 1))

    # ---------- 1. CONTEXTO
    if macd_sup is not None:
        res.macd_superior = float(macd_sup)
    elif df_superior is not None and len(df_superior) > 35:
        res.macd_superior = float(ind.add_all(df_superior)["macd"].iloc[-1])
    if macd_men_alc is not None:
        res.macd_mensual_alcista = bool(macd_men_alc)
    elif df_mensual is not None and len(df_mensual) > 35:
        m = ind.add_all(df_mensual)
        res.macd_mensual_alcista = bool(m["macd"].iloc[-1] > m["macd_sig"].iloc[-1])

    fallos = []
    if ctx["macd_semanal_sobre_cero"] and not (res.macd_superior > 0):
        fallos.append("MACD del marco superior bajo cero")
    if ctx.get("exigir_macd_mensual_alcista") and not res.macd_mensual_alcista:
        fallos.append("MACD mensual bajista")
    fm = cfg.get("filtro_mercado") or {}
    if fm.get("activo") and mercado_ok is False:
        fallos.append("índice de referencia en contra (filtro de mercado)")
    media = "sma200" if marco == "D" else "sma40"
    if ctx["precio_sobre_media_200"] and not (last.Close > last[media]):
        fallos.append("precio bajo la media larga")

    # ---------- 3. ESTRUCTURA (techo del tramo)
    win = est["ventana_maximo"]
    H = df["High"].values
    lo = max(0, today - win)
    top = lo + int(np.argmax(H[lo:today + 1]))
    e = None
    if today - top >= est["min_sesiones_correccion"]:
        e = _estructura(df, top, cfg)
    else:
        # quizá la ruptura reciente ya superó el techo: evaluamos la estructura anterior
        hi = today - dp["sesiones_ruptura_reciente"] - 1
        if hi - lo > 10:
            top2 = lo + int(np.argmax(H[lo:hi + 1]))
            e2 = _estructura(df, top2, cfg) if today - top2 >= est["min_sesiones_correccion"] else None
            if e2 and e2["trampa"] and e2["ruptura"] and today - e2["ruptura"]["t"] < dp["sesiones_ruptura_reciente"]:
                e = e2
        if e is None:
            res.motivo = "en máximos / tramo en marcha (esperar corrección)"
            return res

    if e is None:
        res.motivo = "sin estructura"
        return res

    top, start = e["top"], e["start"]
    rsi_max = float(df["rsi14"].iloc[start:top + 1].max())
    adx_max = float(df["adx"].iloc[max(0, today - 30):].max())
    if rsi_max < ctx["rsi_impulso_minimo"]:
        fallos.append(f"tramo previo débil (RSI máx {rsi_max:.0f})")
    if adx_max < ctx["adx_minimo"]:
        fallos.append(f"sin fuerza de tendencia (ADX máx {adx_max:.0f})")

    res.techo = float(H[top]); res.fecha_techo = _fmt(idx, top)
    res.inicio_tramo = float(df["Low"].iloc[start])
    res.minimo_correccion = float(e["corr_low"])
    res.retroceso = float(e["retro"]); res.ratio_tiempo = float(e["ratio_t"])
    res.directriz_hoy = float(e["linea_hoy"]); res.directriz_manana = float(e["linea_man"])
    res._linea = (idx[top], float(H[top]), e["slope"], top)

    if fallos:
        res.motivo = "; ".join(fallos)
        return res
    if e["retro"] > al["retroceso_max"]:
        res.motivo = f"retroceso excesivo ({e['retro']:.0%}): tendencia dañada"
        return res
    if e["ratio_t"] > est["ratio_tiempo_max"]:
        res.motivo = f"corrección demasiado larga ({e['ratio_t']:.1f}x el tramo): posible agotamiento"
        return res

    # ---------- 2. ALERTA
    wv = al["ventana_estocastico"]
    sto_min = float(np.nanmin(df[["sto50", "sto89"]].iloc[-wv:].values))
    alerta = sto_min <= al["estocastico_lento_max"] or e["retro"] >= al["retroceso_min"]

    # ---------- plan de operación
    atr_now = float(last.atr)
    margen = dp["margen_stop_atr"] * atr_now
    obj1 = float(H[top])
    obj2 = float(e["corr_low"] + e["impulso"])          # igualdad: nuevo tramo = tramo anterior

    def plan(entrada, base_stop):
        stop = base_stop - margen
        riesgo = entrada - stop
        if riesgo <= 0:
            return None
        return dict(entrada=entrada, stop=stop, rr=(obj2 - entrada) / riesgo,
                    rr1=(obj1 - entrada) / riesgo, riesgo_pct=100 * riesgo / entrada)

    t = e["trampa"]
    rup = e["ruptura"]
    V, vol20 = df["Volume"].values, df["vol20"].values

    # confirmaciones de osciladores rápidos
    conf = []
    rsi2 = df["rsi2"].values
    if np.nanmin(rsi2[-7:]) < 15 and rsi2[-1] > 50:
        conf.append("RSI(2) gira desde sobreventa")
    k, d = df["sto_k"].values, df["sto_d"].values
    if np.nanmin(k[-7:]) < 30 and k[-1] > d[-1]:
        conf.append("estocástico rápido cruza al alza")
    if res.macd_mensual_alcista:
        conf.append("MACD mensual alcista")
    if t and not np.isnan(t["vrel"]) and t["vrel"] >= tr["volumen_manos_fuertes"]:
        conf.append(f"barrida con volumen {t['vrel']:.1f}x (manos fuertes)")
    res.confirmaciones = conf

    if t:
        res.nivel_barrido = float(t["nivel"]); res.fecha_barrida = _fmt(idx, t["s"])
        res.minimo_barrida = float(t["min_barrida"]); res.volumen_barrida = float(t["vrel"]) if not np.isnan(t["vrel"]) else math.nan

    estado = "NADA"
    p = None
    Cn = df["Close"].values
    if rup:
        linea_rup_hoy = H[top] + rup["slope"] * (today - top)
        if Cn[today] <= linea_rup_hoy:
            rup = None                       # volvió por debajo de la directriz: ruptura fallida
        elif today - rup["t"] >= dp["sesiones_ruptura_reciente"]:
            res.motivo = f"ruptura ya producida el {_fmt(idx, rup['t'])}: tramo en marcha, esperar otra corrección"
            return res
    # Dos disparos posibles tras la trampa (como en los ejemplos de Cava):
    #  a) recuperación del nivel barrido con volumen de manos fuertes (escape falso a la baja)
    #  b) ruptura de la directriz bajista / recta superior del triángulo
    permitidos = dp.get("permitidos") or ["recuperacion", "ruptura"]
    recup = ("recuperacion" in permitidos and t is not None and today - t["r"] < dp["sesiones_ruptura_reciente"]
             and not np.isnan(t["vrel"]) and t["vrel"] >= tr["volumen_manos_fuertes"])
    rup_ok = ("ruptura" in permitidos and t is not None and rup is not None
              and today - rup["t"] < dp["sesiones_ruptura_reciente"])
    tipo_disparo = ""
    degradada = False
    if rup_ok or recup:
        p = plan(float(last.Close), t["min_barrida"])
        estado = "SENAL"
        partes = []
        if recup:
            partes.append("recuperación del nivel barrido con volumen")
            if t["r"] != today:
                res.avisos.append(f"recuperó el nivel el {_fmt(idx, t['r'])}")
        if rup_ok:
            partes.append("ruptura de directriz")
            vr = V[rup["t"]] / vol20[rup["t"]] if vol20[rup["t"]] else np.nan
            if vr >= dp["volumen_ruptura"]:
                conf.append(f"ruptura con volumen {vr:.1f}x")
            if rup["t"] != today:
                res.avisos.append(f"la ruptura fue el {_fmt(idx, rup['t'])}")
        tipo_disparo = " + ".join(partes)
    elif t:
        p = plan(max(float(e["linea_man"]), float(last.Close)), t["min_barrida"])
        estado = "TRAMPA"
    elif alerta:
        p = plan(max(float(e["linea_man"]), float(last.Close)), float(e["corr_low"]))
        estado = "VIGILANCIA"
    else:
        res.motivo = "en corrección sin alerta todavía"
        return res

    if p is None:
        res.motivo = "plan inválido"
        return res
    res.entrada, res.stop, res.rr, res.rr_obj1, res.riesgo_pct = p["entrada"], p["stop"], p["rr"], p["rr1"], p["riesgo_pct"]
    res.objetivo1, res.objetivo2 = obj1, obj2
    cap = cfg.get("capital") or 0
    if cap > 0:
        res.acciones = int((cap * cfg.get("riesgo_por_operacion_pct", 1) / 100) // (p["entrada"] - p["stop"]))

    if res.rr < dp["rr_minimo"]:
        res.avisos.append(f"R/R {res.rr:.1f} < {dp['rr_minimo']:.0f}: no cumple, esperar mejor precio")
        if estado == "SENAL":
            estado, degradada = "TRAMPA", True   # señal técnica sin R/R: no se compra
    if res.riesgo_pct > dp["riesgo_max_pct"]:
        res.avisos.append(f"stop muy lejano ({res.riesgo_pct:.1f} %)")
        if estado == "SENAL":
            estado, degradada = "TRAMPA", True
    if 1.618 <= e["ratio_t"] <= 2.618:
        conf.append(f"duración de la corrección en zona Fibonacci ({e['ratio_t']:.2f}x)")
    if e["ratio_t"] > 2.0:
        res.avisos.append("corrección ya larga: vigilar agotamiento")

    res.estado = estado
    res.disparo = tipo_disparo + (" (sin R/R)" if degradada else "")
    res.motivo = {"SENAL": f"trampa + {tipo_disparo}",
                  "TRAMPA": ("disparo técnico producido pero sin R/R o stop válido: esperar retroceso"
                             if degradada else "trampa hecha, falta ruptura de directriz"),
                  "VIGILANCIA": "contexto alcista y corrección madura, sin trampa aún"}[estado]
    res.puntuacion = _puntuar(res, e, adx_max)
    from .puntuacion import calidad as _calidad
    res.calidad, res.motivos_calidad = _calidad(res.rr, res.retroceso, res.ratio_tiempo, res.disparo, grupo, cfg)
    return res


def _puntuar(res: Resultado, e: dict, adx_max: float) -> float:
    pts = min(max(res.rr, 0), 6) / 6 * 30
    pts += 8 * len(res.confirmaciones)
    if 0.382 <= e["retro"] <= 0.618:
        pts += 10
    if adx_max >= 25:
        pts += 5
    pts -= 5 * len(res.avisos)
    return round(max(0.0, min(100.0, pts)), 1)
