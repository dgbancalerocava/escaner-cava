"""
Puntuación aprendida de los datos (sustituye a la puntuación "a ojo").

Se entrena SOLO con el periodo de aprendizaje (por defecto 2019-2023) y se valida en el
periodo posterior. El modelo es deliberadamente simple para no sobreajustar:
  - cada variable se divide en tres tramos (terciles) del periodo de aprendizaje;
  - si el tramo alto rinde claramente mejor que el bajo (≥ 0,15 R por operación, con
    suficientes operaciones en cada tramo) la variable suma +1 en el tramo alto y -1 en el bajo;
    si rinde claramente peor, al revés; si no hay diferencia clara, la variable no cuenta;
  - el mercado (EEUU, España, Europa tech, ETFs) suma +1 / -1 si su rendimiento medio se
    separa claramente de la media.
La puntuación final es la suma: un número entero pequeño (p. ej. de -4 a +5).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

VARIABLES = {
    "rr": "relación riesgo/recompensa",
    "riesgo_plan": "distancia al stop (%)",
    "retroceso": "retroceso de la corrección",
    "ratio_tiempo": "duración corrección / tramo",
    "volumen_barrida": "volumen en la barrida",
    "rsi14": "RSI(14) el día de la señal",
    "adx": "ADX el día de la señal",
    "sto50": "estocástico 50",
    "dist_sma200": "distancia a la media de 200 (%)",
    "n_dia": "nº de señales ese día (amplitud)",
}
UMBRAL_R = 0.15
MIN_N = 120


def entrenar(train: pd.DataFrame, col_R: str) -> dict:
    modelo = {"variables": {}, "region": {}, "col_R": col_R, "n_entrenamiento": int(len(train))}
    base = float(train[col_R].mean())
    for v in VARIABLES:
        if v not in train or train[v].notna().sum() < 3 * MIN_N:
            continue
        x = train[[v, col_R]].dropna()
        c1, c2 = np.nanquantile(x[v], [1 / 3, 2 / 3])
        if c1 == c2:
            continue
        bajo, alto = x[x[v] <= c1][col_R], x[x[v] > c2][col_R]
        if len(bajo) < MIN_N or len(alto) < MIN_N:
            continue
        dif = float(alto.mean() - bajo.mean())
        peso = 1 if dif >= UMBRAL_R else (-1 if dif <= -UMBRAL_R else 0)
        modelo["variables"][v] = {"cortes": [float(c1), float(c2)], "peso": peso,
                                  "R_bajo": round(float(bajo.mean()), 2), "R_alto": round(float(alto.mean()), 2)}
    if "region" in train:
        for reg, g in train.groupby("region"):
            if len(g) < MIN_N // 2:
                continue
            dif = float(g[col_R].mean() - base)
            modelo["region"][reg] = {"peso": 1 if dif >= UMBRAL_R else (-1 if dif <= -UMBRAL_R else 0),
                                     "R_medio": round(float(g[col_R].mean()), 2), "n": int(len(g))}
    return modelo


def puntuar(filas: pd.DataFrame, modelo: dict) -> pd.Series:
    p = pd.Series(0.0, index=filas.index)
    for v, m in modelo.get("variables", {}).items():
        if m["peso"] == 0 or v not in filas:
            continue
        x = pd.to_numeric(filas[v], errors="coerce")
        tramo = np.where(x <= m["cortes"][0], -1, np.where(x > m["cortes"][1], 1, 0))
        tramo = np.where(x.isna(), 0, tramo)
        p += m["peso"] * tramo
    if "region" in filas:
        p += filas["region"].map(lambda r: modelo.get("region", {}).get(r, {}).get("peso", 0)).fillna(0)
    return p


def describir(modelo: dict) -> list[str]:
    lineas = []
    for v, m in modelo.get("variables", {}).items():
        if m["peso"]:
            sentido = "más alto es mejor" if m["peso"] > 0 else "más bajo es mejor"
            lineas.append(f"{VARIABLES.get(v, v)}: {sentido} (tramo bajo {m['R_bajo']:+.2f} R, tramo alto {m['R_alto']:+.2f} R)")
    for r, m in modelo.get("region", {}).items():
        if m["peso"]:
            lineas.append(f"mercado {r}: {'suma' if m['peso'] > 0 else 'resta'} (R medio {m['R_medio']:+.2f}, {m['n']} operaciones)")
    return lineas or ["ninguna variable mostró una diferencia clara: la puntuación no discrimina"]


def guardar(modelo: dict, ruta: Path):
    ruta.write_text(json.dumps(modelo, ensure_ascii=False, indent=1), encoding="utf-8")


def cargar(ruta: Path) -> dict | None:
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


# =========================================================================== índice de calidad
# Resultado del backtest de octubre de 2026 (8.600 señales): solo estas características separaron
# bien las operaciones TANTO en 2019-2023 como en 2024-2026. Cada una suma un punto.
CALIDAD_DEFECTO = {"rr_alto": 9.5, "retroceso_bajo": 0.28, "ratio_tiempo_alto": 0.23, "minimo_estrella": 4}


def calidad(rr, retroceso, ratio_tiempo, disparo: str, grupo: str, cfg: dict | None = None) -> tuple[int, list[str]]:
    """Devuelve (puntos, motivos). Escala de -1 a 5."""
    c = {**CALIDAD_DEFECTO, **((cfg or {}).get("calidad") or {})}
    pts, motivos = 0, []
    def ok(x):
        return x is not None and x == x
    if ok(rr) and rr >= c["rr_alto"]:
        pts += 1; motivos.append("R/R alto")
    if ok(retroceso) and retroceso <= c["retroceso_bajo"]:
        pts += 1; motivos.append("corrección poco profunda")
    if ok(ratio_tiempo) and ratio_tiempo >= c["ratio_tiempo_alto"]:
        pts += 1; motivos.append("corrección madura en tiempo")
    tipo = (disparo or "").replace(" (sin R/R)", "")
    if tipo == "recuperación del nivel barrido con volumen":
        pts += 1; motivos.append("escape falso puro")
    g = str(grupo).split("/")[0]
    if g == "etfs":
        pts += 1; motivos.append("ETF")
    elif g == "europe_tech":
        pts -= 1; motivos.append("Europa tech (resta)")
    return pts, motivos
