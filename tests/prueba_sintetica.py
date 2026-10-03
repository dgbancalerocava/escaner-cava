"""
Prueba del motor con datos simulados (no necesita internet).
    python tests/prueba_sintetica.py
Genera escenarios conocidos y comprueba que el motor los clasifica bien.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from screener import indicators as ind  # noqa: E402
from screener.engine import evaluar  # noqa: E402


def _ohlc(close, vol, seed=0):
    rng = np.random.default_rng(seed)
    close = np.asarray(close, float)
    op = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.002, len(close)))
    rng_hl = np.abs(rng.normal(0.008, 0.003, len(close))) * close
    hi = np.maximum(op, close) + rng_hl * 0.5
    lo = np.minimum(op, close) - rng_hl * 0.5
    idx = pd.bdate_range(end="2026-09-28", periods=len(close))
    return pd.DataFrame({"Open": op, "High": hi, "Low": lo, "Close": close, "Volume": vol}, index=idx)


def escenario(tipo: str, seed=1):
    rng = np.random.default_rng(seed)
    n_base = 1100
    base = 50 * np.exp(np.cumsum(rng.normal(0.0006, 0.009, n_base)))  # tendencia alcista suave
    p0 = base[-1]
    if tipo == "bajista":
        c = np.r_[base, p0 * np.exp(np.cumsum(rng.normal(-0.004, 0.01, 200)))]
        return _ohlc(c, np.full(len(c), 1e6), seed)
    # impulso fuerte +30 % en 30 sesiones
    imp = p0 * np.linspace(1, 1.30, 30)
    top = imp[-1]
    # corrección en zigzag con máximos decrecientes: A baja, B rebota, C baja
    a = np.linspace(top, top * 0.88, 8)
    b = np.linspace(a[-1], top * 0.95, 5)
    c = np.linspace(b[-1], top * 0.90, 5)       # pivote de mínimos en 0.90 aprox. tras A? (0.88 es el mínimo A)
    d = np.linspace(c[-1], top * 0.935, 4)
    tramo = np.r_[imp, a[1:], b[1:], c[1:], d[1:]]
    vol = np.full(n_base + len(tramo), 1e6)
    if tipo == "vigilancia":
        e = np.linspace(d[-1], top * 0.90, 4)[1:]   # se acerca al mínimo A sin perforarlo
        tramo = np.r_[tramo, e]
        closes = np.r_[base, tramo]
        return _ohlc(closes, np.full(len(closes), 1e6), seed)
    # barrida: perfora el mínimo A (0.88) y recupera con volumen
    sweep = np.array([top * 0.895, top * 0.865, top * 0.895, top * 0.905])
    tramo = np.r_[tramo, sweep]
    extra_vol = [1e6, 2.5e6, 2e6, 1.2e6]
    if tipo == "senal":
        tramo = np.r_[tramo, top * 0.918]   # ruptura de la directriz hoy
        extra_vol += [2.2e6]
    if tipo == "trampa":
        tramo = np.r_[tramo, top * 0.91, top * 0.905, top * 0.912, top * 0.908]  # lateral bajo la directriz
        extra_vol += [1e6] * 4
    closes = np.r_[base, tramo]
    vol = np.r_[np.full(len(closes) - len(extra_vol), 1e6), extra_vol]
    df = _ohlc(closes, vol, seed)
    # el mínimo A debe ser un pivote limpio y la barrida debe mostrarse en la mecha
    return df


def main():
    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    ok = True
    for tipo, esperado in [("senal", {"SENAL"}), ("trampa", {"TRAMPA"}),
                           ("vigilancia", {"VIGILANCIA"}), ("bajista", {"NADA"})]:
        df = escenario(tipo)
        r = evaluar(df, tipo.upper(), cfg, "D", tipo, "prueba",
                    df_superior=ind.resample(df, "W-FRI"), df_mensual=ind.resample(df, "ME"))
        estado_ok = r.estado in esperado
        ok &= estado_ok
        print(f"{tipo:11s} -> {r.estado:10s} {'OK ' if estado_ok else 'MAL'} | {r.motivo} | "
              f"entrada {r.entrada:.2f} stop {r.stop:.2f} obj2 {r.objetivo2:.2f} R/R {r.rr:.2f} | "
              f"conf: {r.confirmaciones} avisos: {r.avisos}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
