"""
Backtest histórico + comparación de variantes del método (se lanza a mano desde GitHub Actions).
    python backtest.py                      -> descarga, simula, compara variantes y envía email
    python backtest.py --anios 8 --corte 2024-01-01 --sin-email
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd
import yaml

from screener import backtest as BT
from screener import data as D
from screener import evaluacion as EV
from screener import puntuacion as PT
from screener.emailer import enviar

BASE = Path(__file__).parent
COLORES = {"A": "#57606a", "B": "#0969da", "C": "#8250df", "D": "#bc4c00", "E": "#1a7f37"}


def log(*a):
    print(*a, flush=True)


def _celda(m: dict, k: str, fmt="{:+.2f}"):
    v = m.get(k)
    return "–" if v is None else (fmt.format(v) if isinstance(v, (int, float)) else str(v))


def tabla_md(filas: list[dict], corte: str) -> str:
    out = [f"| Var. | Descripción | Periodo | Operaciones/año | Acierto | R medio | R al año | Profit factor | Peor racha | Máx. DD (R) |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for f in filas:
        for et, nombre in (("aprendizaje", f"hasta {corte[:4]}"), ("validacion", f"desde {corte[:4]}")):
            m = f[et]
            if not m.get("n"):
                out.append(f"| {f['variante']} | {f['descripcion']} | {nombre} | 0 | – | – | – | – | – | – |")
                continue
            out.append(f"| {f['variante']} | {f['descripcion']} | {nombre} | {m['por_anio']:.0f} | {m['acierto_pct']} % | "
                       f"{m['R_medio']:+.2f} | {m['R_anio']:+.1f} | {_celda(m, 'profit_factor', '{:.2f}')} | "
                       f"{m['racha_perdedora']} | {m['max_drawdown_R']} |")
    return "\n".join(out)


def curvas(V: dict, filas: list[dict], ruta: Path, corte: str):
    """Barras: R medio por operación de cada variante en aprendizaje y validación.
    (La curva de R acumulado engaña: la variante con más operaciones siempre "gana", pero nadie
    puede tomar 900 operaciones al año con un capital limitado.)"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import textwrap
    etiquetas = [f"{f['variante']}\n" + textwrap.fill(f["descripcion"].replace(" (⭐)", ""), 20) for f in filas]
    ap = [f["aprendizaje"].get("R_medio") or 0 for f in filas]
    va = [f["validacion"].get("R_medio") or 0 for f in filas]
    x = np.arange(len(filas))
    fig, ax = plt.subplots(figsize=(9, 3.8))
    b1 = ax.bar(x - 0.2, ap, 0.38, color="#0969da", label=f"Aprendizaje (hasta {corte[:4]})")
    b2 = ax.bar(x + 0.2, va, 0.38, color="#bc4c00", label=f"Validación (desde {corte[:4]})")
    for barras in (b1, b2):
        for r in barras:
            ax.annotate(f"{r.get_height():+.2f}", (r.get_x() + r.get_width() / 2, r.get_height()),
                        ha="center", va="bottom", fontsize=8, color="#1f2328")
    ax.axhline(0, color="#57606a", lw=0.8)
    ax.set_xticks(x, etiquetas, fontsize=8)
    ax.set_ylabel("R medio por operación", color="#57606a")
    ax.set_title("¿Cuánto gana cada operación de media? (en R)", loc="left", fontsize=11, fontweight="bold", color="#1f2328")
    ax.grid(axis="y", color="#d8dee4", lw=0.6)
    for s_ in ax.spines.values():
        s_.set_visible(False)
    ax.tick_params(colors="#57606a")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(ruta, dpi=100)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anios", type=int, default=8, help="años de histórico a descargar")
    ap.add_argument("--corte", default="2024-01-01", help="inicio del periodo de validación")
    ap.add_argument("--sin-email", action="store_true")
    ap.add_argument("--desde-csv", help="reutiliza un operaciones.csv ya calculado (solo recalcula variantes)")
    args = ap.parse_args()

    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    carpeta = BASE / "reports" / "backtest"
    carpeta.mkdir(parents=True, exist_ok=True)
    max_dia = int((cfg.get("seleccion") or {}).get("max_senales_dia") or 2)

    if args.desde_csv:
        ops = pd.read_csv(args.desde_csv)
    else:
        universo = D.cargar_universo(BASE / "universe", cfg["universos"])
        log(f"Backtest sobre {len(universo)} valores, {args.anios} años")
        precios = D.descargar(universo.ticker.tolist(), args.anios, log=log)
        info = universo.set_index("ticker")
        precios = {t: df for t, df in precios.items()
                   if t.startswith("^") or (df.Close * df.Volume).iloc[-20:].mean() >= cfg["liquidez_minima"]}
        ops = BT.ejecutar(precios, info, cfg, procesos=os.cpu_count() or 2, log=log)
        if ops.empty:
            log("El backtest no generó operaciones.")
            return
        ops.to_csv(carpeta / "operaciones.csv", index=False)

    filas, V, sugeridos, orden = BT.variantes(ops, cfg, corte=args.corte, max_dia=max_dia, log=log)
    desde, hasta = ops.fecha.min(), ops.fecha.max()

    # resumen detallado de la variante activa (la que usa el escáner diario)
    activa = (cfg.get("seleccion") or {}).get("variante_activa", "A")
    va = V.get(activa, V["A"]).copy()
    st = EV.estadisticas(va)
    st.update(version=f"variante {activa}", periodo=f"{desde} → {hasta}", variantes=filas, corte=args.corte)
    (carpeta / "resumen.json").write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    md = [f"# Backtest de variantes ({desde} → {hasta})", "",
          f"Aprendizaje: hasta {args.corte} · Validación: desde {args.corte}. "
          "Una mejora solo cuenta si se mantiene en validación.", "",
          tabla_md(filas, args.corte), "",
          "## ¿El índice de calidad sigue ordenando bien?", "",
          "R medio por operación según la calidad (debería crecer hacia la derecha en los dos periodos).", ""]
    niveles = sorted({k for o in orden.values() for k in o}, key=int)
    md += ["| Periodo | " + " | ".join(("≥4" if n == "4" else n) for n in niveles) + " |", "|---|" + "---|" * len(niveles)]
    for et, o in orden.items():
        md.append(f"| {et} | " + " | ".join(f"{o[n]['R_medio']:+.2f} ({o[n]['n']})" if n in o else "–" for n in niveles) + " |")
    if sugeridos:
        actuales = {**PT.CALIDAD_DEFECTO, **(cfg.get("calidad") or {})}
        md += ["", "Umbrales de calidad en uso: " + ", ".join(f"{k} = {actuales[k]}" for k in sugeridos)
               + " · Recalculados con el periodo de aprendizaje: " + ", ".join(f"{k} = {v}" for k, v in sugeridos.items())]
    md += ["", f"## Detalle de la variante activa en el escáner ({activa})", "",
           EV.markdown(st, "").replace("# \n", ""),
           "", "> Aviso: sesgo de supervivencia (listas actuales de los índices), solo marco diario, "
           "entrada a la apertura siguiente, sin comisiones. Sirve para comparar variantes, no como promesa de rentabilidad."]
    md = "\n".join(md)
    (carpeta / "resumen.md").write_text(md, encoding="utf-8")
    (carpeta / "variantes.json").write_text(json.dumps({"filas": filas, "calidad_por_periodo": orden,
                                                        "umbrales_sugeridos": sugeridos},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    curvas(V, filas, carpeta / "curva.png", args.corte)
    log(md)

    if not args.sin_email:
        html = ("<div style='font-family:Segoe UI,Helvetica,Arial,sans-serif;max-width:900px'>" + _md_a_html(md)
                + "<p><img src='cid:curva_png' style='max-width:100%'></p></div>")
        enviar(f"Backtest de variantes método Cava · {desde} → {hasta}", html, md,
               {"curva_png": carpeta / "curva.png"}, log)


def _md_a_html(md: str) -> str:
    """Conversión mínima de Markdown (títulos, tablas, listas) a HTML, sin dependencias."""
    out, en_tabla = [], False
    for linea in md.splitlines():
        if linea.startswith("|"):
            celdas = [c.strip() for c in linea.strip("|").split("|")]
            if set("".join(celdas)) <= set("-: "):
                continue
            if not en_tabla:
                out.append("<table cellpadding='5' cellspacing='0' style='border-collapse:collapse;font-size:12px'>")
                out.append("<tr style='background:#f6f8fa'>" + "".join(f"<th align='left'>{c}</th>" for c in celdas) + "</tr>")
                en_tabla = True
            else:
                out.append("<tr style='border-top:1px solid #d8dee4'>" + "".join(f"<td>{c}</td>" for c in celdas) + "</tr>")
            continue
        if en_tabla:
            out.append("</table>")
            en_tabla = False
        if linea.startswith("## "):
            out.append(f"<h3>{linea[3:]}</h3>")
        elif linea.startswith("# "):
            out.append(f"<h2>{linea[2:]}</h2>")
        elif linea.startswith("> "):
            out.append(f"<p style='font-size:12px;color:#57606a'>{linea[2:]}</p>")
        elif linea.startswith("- "):
            out.append(f"<p style='margin:2px 0'>• {linea[2:]}</p>")
        elif linea.strip():
            out.append(f"<p>{linea}</p>")
    if en_tabla:
        out.append("</table>")
    return "\n".join(out)


if __name__ == "__main__":
    main()
