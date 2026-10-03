"""
Autoevaluación: ¿qué habría pasado si se hubieran tomado las señales?

Cada señal se simula con dos gestiones:
  FIJA        entrada a la apertura siguiente, stop inicial y salida en el Objetivo 2
              (o por tiempo tras `max_sesiones`).
  SEGUIMIENTO entrada igual; al tocar el Objetivo 1 el stop sube a la entrada y desde
              ahí sigue al Parabolic SAR (gestión tendencial al estilo Cava). Sin objetivo fijo.

El resultado se mide en R (múltiplos del riesgo inicial): +3R = ganó 3 veces lo que arriesgaba,
-1R = saltó el stop. Así se comparan operaciones de distinto tamaño.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import indicators as ind

COLS_SENAL = ["fecha", "ticker", "nombre", "grupo", "marco", "disparo", "pasa_filtro", "entrada_ref",
              "stop", "objetivo1", "objetivo2", "rr", "puntuacion", "vol_trampa", "n_confirmaciones",
              "fecha_techo"]


def region(grupo: str) -> str:
    g = str(grupo).split("/")[0]
    return {"sp500": "EEUU", "nasdaq100": "EEUU", "ibex35": "España", "europe_tech": "Europa tech",
            "etfs": "ETFs", "indices": "Índices"}.get(g, g)


def tramo_puntuacion(p: float) -> str:
    return "≥70" if p >= 70 else ("50-69" if p >= 50 else "<50")


# ----------------------------------------------------------------- simulación
def simular(df: pd.DataFrame, fecha: str, stop: float, obj1: float, obj2: float,
            sar: pd.Series | None = None, max_sesiones: int = 120, max_seguimiento: int = 250) -> dict:
    """Simula una señal emitida al cierre de `fecha` sobre velas diarias `df`."""
    idx = df.index
    pos = idx.searchsorted(pd.Timestamp(fecha), side="right")   # primera sesión posterior
    if pos >= len(df):
        return {"estado": "pendiente"}
    O, H, L, C = (df[c].values for c in ("Open", "High", "Low", "Close"))
    entrada = float(O[pos])
    if entrada <= stop:
        return {"estado": "anulada", "nota": "abre por debajo del stop"}
    riesgo = entrada - stop
    if sar is None:
        sar = ind.parabolic_sar(df["High"], df["Low"])
    S = sar.values
    out = {"fecha_entrada": idx[pos].strftime("%Y-%m-%d"), "entrada": entrada, "riesgo_pct": 100 * riesgo / entrada}

    # --- gestión FIJA
    salida, j_out, motivo = None, None, None
    for j in range(pos, min(len(df), pos + max_sesiones)):
        if L[j] <= stop:
            salida, motivo = (min(O[j], stop) if j > pos else stop), "stop"
        elif H[j] >= obj2:
            salida, motivo = (max(O[j], obj2) if j > pos else obj2), "objetivo"
        if salida is not None:
            j_out = j
            break
    if salida is None and pos + max_sesiones <= len(df) - 1:
        j_out = pos + max_sesiones - 1
        salida, motivo = C[j_out], "tiempo"
    hasta = (j_out if j_out is not None else len(df) - 1) + 1
    out["mfe_R"] = (H[pos:hasta].max() - entrada) / riesgo
    out["mae_R"] = (L[pos:hasta].min() - entrada) / riesgo
    out["toco_obj1"] = bool(H[pos:hasta].max() >= obj1)
    if salida is None:
        out.update(fija_estado="abierta", fija_R=(C[-1] - entrada) / riesgo, fija_sesiones=len(df) - pos)
    else:
        out.update(fija_estado="cerrada", fija_R=(salida - entrada) / riesgo, fija_motivo=motivo,
                   fija_salida=idx[j_out].strftime("%Y-%m-%d"), fija_sesiones=j_out - pos + 1)

    # --- gestión con SEGUIMIENTO
    st, alcanzo1, salida2, j2 = stop, False, None, None
    for j in range(pos, min(len(df), pos + max_seguimiento)):
        if L[j] <= st:
            salida2, j2 = (min(O[j], st) if j > pos else st), j
            break
        if H[j] >= obj1:
            alcanzo1 = True
        if alcanzo1:
            st = max(st, entrada)
            if not np.isnan(S[j]) and S[j] < C[j]:
                st = max(st, S[j])
    if salida2 is None and pos + max_seguimiento <= len(df) - 1:
        j2 = pos + max_seguimiento - 1
        salida2 = C[j2]
    if salida2 is None:
        out.update(seg_estado="abierta", seg_R=(C[-1] - entrada) / riesgo, seg_stop_actual=st)
    else:
        out.update(seg_estado="cerrada", seg_R=(salida2 - entrada) / riesgo,
                   seg_salida=idx[j2].strftime("%Y-%m-%d"), seg_sesiones=j2 - pos + 1)
    out["estado"] = "abierta" if out["fija_estado"] == "abierta" else "cerrada"
    return out


# ----------------------------------------------------------------- estadísticas
def _stats(R: pd.Series) -> dict:
    R = R.dropna()
    if R.empty:
        return {"n": 0}
    gan, per = R[R > 0], R[R <= 0]
    curva = R.cumsum()
    dd = float((curva - curva.cummax()).min())
    return {"n": int(len(R)), "acierto_pct": round(100 * len(gan) / len(R), 1),
            "R_medio": round(float(R.mean()), 2), "R_total": round(float(R.sum()), 1),
            "ganancia_media_R": round(float(gan.mean()), 2) if len(gan) else 0.0,
            "perdida_media_R": round(float(per.mean()), 2) if len(per) else 0.0,
            "profit_factor": round(float(gan.sum() / -per.sum()), 2) if per.sum() < 0 else None,
            "max_drawdown_R": round(dd, 1)}


def estadisticas(ops: pd.DataFrame, solo_filtradas=True) -> dict:
    """ops: una fila por operación simulada. Devuelve tablas globales y por grupos."""
    if ops.empty:
        return {"global": {}, "grupos": {}}
    base = ops[ops.pasa_filtro.astype(bool)] if solo_filtradas else ops
    cerr = base[base.fija_estado == "cerrada"].sort_values("fija_salida")
    cerr_s = base[base.seg_estado == "cerrada"].sort_values("seg_salida")
    out = {"global": {"fija": _stats(cerr.fija_R), "seguimiento": _stats(cerr_s.seg_R),
                      "abiertas": int((base.estado == "abierta").sum()),
                      "anuladas": int((base.estado == "anulada").sum()),
                      "pendientes": int((base.estado == "pendiente").sum())},
           "grupos": {}}
    cerr = cerr.assign(region=cerr.grupo.map(region), tramo=cerr.puntuacion.map(tramo_puntuacion),
                       anio=cerr.fecha.str[:4],
                       vol=np.where(cerr.vol_trampa.astype(bool), "con volumen", "sin volumen"),
                       tipo=cerr.disparo.str.replace(" (sin R/R)", "", regex=False))
    for col, nombre in [("region", "Mercado"), ("marco", "Marco"), ("tipo", "Disparo"),
                        ("tramo", "Puntuación"), ("vol", "Volumen en la trampa"), ("anio", "Año")]:
        out["grupos"][nombre] = {str(k): _stats(g.fija_R) | {"R_medio_seg": _stats(g.seg_R).get("R_medio")}
                                 for k, g in cerr.groupby(col)}
    # efecto del filtro R/R (señales técnicas que se descartaron por R/R < mínimo)
    if not solo_filtradas or (~ops.pasa_filtro.astype(bool)).any():
        c_all = ops[ops.fija_estado == "cerrada"]
        out["grupos"]["Filtro R/R"] = {
            ("pasa (R/R ≥ mínimo)" if k else "descartada (R/R bajo)"): _stats(g.fija_R)
            for k, g in c_all.groupby(c_all.pasa_filtro.astype(bool))}
    return out


def curva_R(ops: pd.DataFrame, ruta: Path, titulo: str):
    """Gráfico de la curva acumulada en R (gestión fija y seguimiento)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    base = ops[ops.pasa_filtro.astype(bool)]
    f = base[base.fija_estado == "cerrada"].sort_values("fija_salida")
    s = base[base.seg_estado == "cerrada"].sort_values("seg_salida")
    if f.empty:
        return False
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(pd.to_datetime(f.fija_salida), f.fija_R.cumsum(), color="#0969da", lw=2, label="Gestión fija (stop / obj. 2)")
    if not s.empty:
        ax.plot(pd.to_datetime(s.seg_salida), s.seg_R.cumsum(), color="#bc4c00", lw=2, label="Con seguimiento (SAR)")
    ax.axhline(0, color="#57606a", lw=0.8)
    ax.set_title(titulo, loc="left", fontsize=11, fontweight="bold", color="#1f2328")
    ax.set_ylabel("R acumulado", color="#57606a")
    ax.grid(color="#d8dee4", lw=0.6)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(colors="#57606a", labelsize=8)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(ruta, dpi=100)
    plt.close(fig)
    return True


# ----------------------------------------------------------------- seguimiento en vivo
def registrar_senales(carpeta: Path, resultados) -> int:
    """Añade al registro las señales del día (y las descartadas por R/R como grupo de control)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / "senales.csv"
    previas = pd.read_csv(ruta, dtype=str) if ruta.exists() else pd.DataFrame(columns=COLS_SENAL)
    claves = set(zip(previas.ticker, previas.marco, previas.fecha_techo))
    nuevas = []
    for r in resultados:
        tecnica = r.estado == "SENAL" or (r.estado == "TRAMPA" and "sin R/R" in (r.disparo or ""))
        if not tecnica or r.ticker.startswith("^"):
            continue
        k = (r.ticker, r.marco, r.fecha_techo)
        if k in claves:
            continue
        claves.add(k)
        nuevas.append({"fecha": r.fecha, "ticker": r.ticker, "nombre": r.nombre, "grupo": r.grupo,
                       "marco": r.marco, "disparo": r.disparo, "pasa_filtro": r.estado == "SENAL",
                       "entrada_ref": round(r.entrada, 4), "stop": round(r.stop, 4),
                       "objetivo1": round(r.objetivo1, 4), "objetivo2": round(r.objetivo2, 4),
                       "rr": round(r.rr, 2), "puntuacion": r.puntuacion,
                       "vol_trampa": bool(r.volumen_barrida >= 1.3) if not math.isnan(r.volumen_barrida) else False,
                       "n_confirmaciones": len(r.confirmaciones), "fecha_techo": r.fecha_techo})
    if nuevas:
        pd.concat([previas, pd.DataFrame(nuevas)], ignore_index=True).to_csv(ruta, index=False)
    return len(nuevas)


def evaluar_registro(senales: pd.DataFrame, precios: dict) -> pd.DataFrame:
    filas = []
    sars = {}
    for _, s in senales.iterrows():
        df = precios.get(s.ticker)
        if df is None:
            continue
        if s.ticker not in sars:
            sars[s.ticker] = ind.parabolic_sar(df["High"], df["Low"])
        r = simular(df, s.fecha, float(s.stop), float(s.objetivo1), float(s.objetivo2), sars[s.ticker])
        filas.append({**s.to_dict(), **r})
    ops = pd.DataFrame(filas)
    if ops.empty:
        return ops
    for c in ("fija_R", "seg_R", "puntuacion", "rr", "mfe_R", "mae_R", "entrada"):
        ops[c] = pd.to_numeric(ops[c], errors="coerce") if c in ops else np.nan
    for c in ("fija_estado", "seg_estado", "fija_salida", "seg_salida"):
        if c not in ops:
            ops[c] = None
    ops["pasa_filtro"] = ops.pasa_filtro.astype(str).str.lower().isin(["true", "1"])
    ops["vol_trampa"] = ops.vol_trampa.astype(str).str.lower().isin(["true", "1"])
    return ops


def actualizar_seguimiento(carpeta: Path, precios: dict) -> dict:
    """Recalcula desde cero el resultado de todas las señales registradas."""
    ruta = carpeta / "senales.csv"
    if not ruta.exists():
        return {}
    ops = evaluar_registro(pd.read_csv(ruta, dtype=str), precios)
    if ops.empty:
        return {}
    ops.to_csv(carpeta / "operaciones.csv", index=False)
    st = estadisticas(ops)
    abiertas = ops[(ops.estado == "abierta") & ops.pasa_filtro]
    st["abiertas_detalle"] = abiertas[["fecha", "ticker", "marco", "entrada", "stop", "objetivo2", "fija_R", "seg_R"]] \
        .round(2).to_dict("records") if not abiertas.empty else []
    (carpeta / "resumen.json").write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (carpeta / "resumen.md").write_text(markdown(st, "Seguimiento en vivo de las señales"), encoding="utf-8")
    return st


# ----------------------------------------------------------------- presentación
def _fila(nombre, s):
    if not s or not s.get("n"):
        return f"| {nombre} | 0 | – | – | – | – |"
    return (f"| {nombre} | {s['n']} | {s['acierto_pct']} % | {s['R_medio']:+.2f} | "
            f"{s['profit_factor'] if s['profit_factor'] is not None else '–'} | {s['max_drawdown_R']} |")


def markdown(st: dict, titulo: str) -> str:
    g = st.get("global", {})
    md = [f"# {titulo}", "",
          f"Operaciones abiertas: {g.get('abiertas', 0)} · pendientes de entrar: {g.get('pendientes', 0)} · anuladas (abren bajo el stop): {g.get('anuladas', 0)}", "",
          "| Gestión | Cerradas | Acierto | R medio | Profit factor | Máx. drawdown (R) |", "|---|---|---|---|---|---|",
          _fila("Fija (stop / obj. 2)", g.get("fija")), _fila("Con seguimiento (SAR)", g.get("seguimiento"))]
    for nombre, tabla in st.get("grupos", {}).items():
        md += ["", f"## Por {nombre[0].lower() + nombre[1:]}", "", "| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |",
               "|---|---|---|---|---|---|"]
        md += [_fila(k, v) for k, v in tabla.items()]
    if st.get("abiertas_detalle"):
        md += ["", "## Operaciones abiertas", "", "| Fecha | Valor | Marco | Entrada | Stop | Obj. 2 | R actual |", "|---|---|---|---|---|---|---|"]
        md += [f"| {a['fecha']} | {a['ticker']} | {a['marco']} | {a['entrada']} | {a['stop']} | {a['objetivo2']} | {a['fija_R']:+.2f} |"
               for a in st["abiertas_detalle"]]
    return "\n".join(md)


def html(st_vivo: dict, st_backtest: dict | None) -> str:
    def fila(nombre, s):
        if not s or not s.get("n"):
            return f"<tr><td>{nombre}</td><td colspan='5' style='color:#57606a'>sin operaciones cerradas todavía</td></tr>"
        pf = s["profit_factor"] if s["profit_factor"] is not None else "–"
        color = "#1a7f37" if s["R_medio"] > 0 else "#cf222e"
        return (f"<tr style='border-top:1px solid #d8dee4'><td>{nombre}</td><td>{s['n']}</td><td>{s['acierto_pct']} %</td>"
                f"<td style='color:{color}'><b>{s['R_medio']:+.2f} R</b></td><td>{pf}</td><td>{s['max_drawdown_R']} R</td></tr>")
    th = ("<tr style='background:#f6f8fa;color:#57606a;font-size:12px;text-align:left'><th></th><th>Cerradas</th>"
          "<th>Acierto</th><th>R medio</th><th>Profit factor</th><th>Máx. drawdown</th></tr>")
    g = (st_vivo or {}).get("global", {})
    filas = [fila("En vivo · gestión fija", g.get("fija")), fila("En vivo · con seguimiento", g.get("seguimiento"))]
    if st_backtest and st_backtest.get("global"):
        b = st_backtest["global"]
        filas += [fila("Histórico 5 años · fija", b.get("fija")), fila("Histórico 5 años · seguimiento", b.get("seguimiento"))]
    abiertas = (st_vivo or {}).get("abiertas_detalle", [])
    txt_ab = ""
    if abiertas:
        orden = sorted(abiertas, key=lambda a: -(a["fija_R"] if a["fija_R"] == a["fija_R"] else -99))
        resto = f" y {len(orden) - 20} más" if len(orden) > 20 else ""
        txt_ab = f"<p style='font-size:12px;color:#57606a'>Abiertas ({len(orden)}): " + ", ".join(
            f"{a['ticker']} ({a['fija_R']:+.1f} R)" for a in orden[:20]) + resto + "</p>"
    return (f"<h3 style='margin:22px 0 6px'>📊 Autoevaluación del método</h3>"
            f"<p style='font-size:12px;color:#57606a;margin:0 0 6px'>Resultado si se hubieran tomado todas las señales verdes "
            f"(entrada a la apertura siguiente). R = múltiplos del riesgo: +1 R gana lo arriesgado, −1 R salta el stop.</p>"
            f"<table cellpadding='6' cellspacing='0' style='border-collapse:collapse;width:100%;font-size:13px'>{th}{''.join(filas)}</table>{txt_ab}")
