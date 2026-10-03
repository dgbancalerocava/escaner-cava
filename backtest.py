"""
Backtest histórico del método (se lanza a mano desde GitHub Actions o en local).
    python backtest.py               -> descarga datos, simula y envía el resumen por email
    python backtest.py --anios 8 --sin-email
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml

from screener import backtest as BT
from screener import data as D
from screener import evaluacion as EV
from screener.emailer import enviar

BASE = Path(__file__).parent


def log(*a):
    print(*a, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anios", type=int, default=8, help="años de histórico a descargar")
    ap.add_argument("--sin-email", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    universo = D.cargar_universo(BASE / "universe", cfg["universos"])
    log(f"Backtest sobre {len(universo)} valores, {args.anios} años")
    precios = D.descargar(universo.ticker.tolist(), args.anios, log=log)
    info = universo.set_index("ticker")
    # filtro de liquidez actual (igual que el escáner diario)
    precios = {t: df for t, df in precios.items()
               if t.startswith("^") or (df.Close * df.Volume).iloc[-20:].mean() >= cfg["liquidez_minima"]}

    ops = BT.ejecutar(precios, info, cfg, procesos=os.cpu_count() or 2, log=log)
    carpeta = BASE / "reports" / "backtest"
    carpeta.mkdir(parents=True, exist_ok=True)
    if ops.empty:
        log("El backtest no generó operaciones.")
        return
    ops.to_csv(carpeta / "operaciones.csv", index=False)
    st = EV.estadisticas(ops)
    desde, hasta = ops.fecha.min(), ops.fecha.max()
    st["periodo"] = f"{desde} → {hasta}"
    st["parametros"] = {k: cfg[k] for k in ("contexto", "alerta", "estructura", "trampa", "disparo")}
    (carpeta / "resumen.json").write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    md = EV.markdown(st, f"Backtest histórico ({desde} → {hasta})")
    md += ("\n\n> Aviso: sesgo de supervivencia (listas actuales de los índices), solo marco diario, "
           "entrada a la apertura siguiente, sin comisiones. Úsalo para comparar variantes del método, no como promesa de rentabilidad.")
    (carpeta / "resumen.md").write_text(md, encoding="utf-8")
    hay_curva = EV.curva_R(ops, carpeta / "curva.png", f"Curva acumulada en R · {desde} → {hasta}")
    log(md)

    if not args.sin_email:
        html = "<div style='font-family:Segoe UI,Helvetica,Arial,sans-serif;max-width:860px'>" + _md_a_html(md)
        imgs = {}
        if hay_curva:
            html += "<p><img src='cid:curva_png' style='max-width:100%'></p>"
            imgs["curva_png"] = carpeta / "curva.png"
        html += "</div>"
        enviar(f"Backtest método Cava · {desde} → {hasta}", html, md, imgs, log)


def _md_a_html(md: str) -> str:
    """Conversión mínima de las tablas Markdown del resumen a HTML (sin dependencias)."""
    out, en_tabla = [], False
    for linea in md.splitlines():
        if linea.startswith("|"):
            celdas = [c.strip() for c in linea.strip("|").split("|")]
            if set("".join(celdas)) <= set("-: "):
                continue
            if not en_tabla:
                out.append("<table cellpadding='5' cellspacing='0' style='border-collapse:collapse;font-size:13px'>")
                en_tabla = True
                out.append("<tr style='background:#f6f8fa'>" + "".join(f"<th align='left'>{c}</th>" for c in celdas) + "</tr>")
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
        elif linea.strip():
            out.append(f"<p>{linea}</p>")
    if en_tabla:
        out.append("</table>")
    return "\n".join(out)


if __name__ == "__main__":
    main()
