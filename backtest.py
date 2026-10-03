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
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4))
    for f in filas:
        k = f["variante"]
        g = "fija" if f["gestion"] == "fija" else "ges"
        df = V[k]
        c = df[df[f"{g}_estado"] == "cerrada"].sort_values(f"{g}_salida")
        if c.empty:
            continue
        # R por operación normalizado a "R por año" no tiene sentido visual; se dibuja R acumulado
        ax.plot(pd.to_datetime(c[f"{g}_salida"]), c[f"{g}_R"].cumsum(), lw=2, color=COLORES.get(k, "#000"),
                label=f"{k} · {f['descripcion']}")
    ax.axvline(pd.Timestamp(corte), color="#57606a", ls="--", lw=1)
    ax.text(pd.Timestamp(corte), ax.get_ylim()[1], "  validación →", va="top", fontsize=8, color="#57606a")
    ax.set_title("R acumulado por variante", loc="left", fontsize=11, fontweight="bold", color="#1f2328")
    ax.grid(color="#d8dee4", lw=0.6)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors="#57606a", labelsize=8)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
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

    filas, V, modelo, monot = BT.variantes(ops, cfg, corte=args.corte, max_dia=max_dia, log=log)
    PT.guardar(modelo, carpeta / "puntuacion_aprendida.json")
    desde, hasta = ops.fecha.min(), ops.fecha.max()

    # resumen detallado de la variante activa (la que usa el escáner diario)
    activa = (cfg.get("seleccion") or {}).get("variante_activa", "A")
    va = V.get(activa, V["A"]).copy()
    st = EV.estadisticas(va)
    st.update(version=f"variante {activa}", periodo=f"{desde} → {hasta}", variantes=filas, corte=args.corte)
    (carpeta / "resumen.json").write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    md = [f"# Backtest de variantes ({desde} → {hasta})", "",
          f"Aprendizaje: hasta {args.corte} · Validación: desde {args.corte}. "
          "Las decisiones se toman con el aprendizaje y se confirman en validación.", "",
          tabla_md(filas, args.corte), "",
          "## Puntuación aprendida (variante E)", ""]
    md += [f"- {l}" for l in PT.describir(modelo)]
    if monot:
        md += ["", "¿Ordena bien en validación? (R medio por puntuación; debería crecer hacia la derecha)", "",
               "| Puntuación | " + " | ".join(monot) + " |", "|---|" + "---|" * len(monot),
               "| R medio | " + " | ".join(f"{v['R_medio']:+.2f}" for v in monot.values()) + " |",
               "| Operaciones | " + " | ".join(str(v['n']) for v in monot.values()) + " |"]
    md += ["", f"## Detalle de la variante activa en el escáner ({activa})", "",
           EV.markdown(st, "").replace("# \n", ""),
           "", "> Aviso: sesgo de supervivencia (listas actuales de los índices), solo marco diario, "
           "entrada a la apertura siguiente, sin comisiones. Sirve para comparar variantes, no como promesa de rentabilidad."]
    md = "\n".join(md)
    (carpeta / "resumen.md").write_text(md, encoding="utf-8")
    (carpeta / "variantes.json").write_text(json.dumps({"filas": filas, "puntuacion_validacion": monot},
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
