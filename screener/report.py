"""Gráficos, informe HTML para email, JSON y Markdown (este último lo lee Claude)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .engine import Resultado  # noqa: E402

INK, MUTED, GRID = "#1f2328", "#57606a", "#d8dee4"
UP, DOWN = "#1a7f37", "#cf222e"
C_ENTRADA, C_STOP, C_OBJ, C_DIR, C_BARR = "#0969da", "#cf222e", "#1a7f37", "#bc4c00", "#6e7781"

ESTADOS = {
    "SENAL": ("🟢", "Señal activada", "#dafbe1"),
    "TRAMPA": ("🟠", "Trampa hecha · esperando ruptura", "#fff1e5"),
    "VIGILANCIA": ("🟡", "En vigilancia", "#fff8c5"),
}


def _f(x, d=2):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ----------------------------------------------------------------- gráfico
def grafico(df: pd.DataFrame, r: Resultado, ruta: Path, velas=130):
    d = df.iloc[-velas:]
    x = np.arange(len(d))
    fig, (ax, axv) = plt.subplots(2, 1, figsize=(9, 5.2), sharex=True,
                                  gridspec_kw={"height_ratios": [4, 1], "hspace": 0.05})
    col = np.where(d.Close >= d.Open, UP, DOWN)
    ax.vlines(x, d.Low, d.High, color=col, linewidth=0.8)
    body_lo = np.minimum(d.Open, d.Close)
    body_h = np.maximum((d.Close - d.Open).abs(), (d.High - d.Low).max() * 0.002)
    ax.bar(x, body_h, bottom=body_lo, width=0.6, color=col, linewidth=0)
    axv.bar(x, d.Volume, width=0.7, color=col, alpha=0.55, linewidth=0)
    if "vol20" in d:
        axv.plot(x, d["vol20"], color=MUTED, linewidth=1)

    # directriz bajista
    if r._linea:
        fecha_top, h_top, slope, top_pos = r._linea
        i0 = len(df) - len(d)
        xs = np.arange(max(0, top_pos - i0), len(d) + 1)
        ax.plot(xs, h_top + slope * (xs + i0 - top_pos), color=C_DIR, linewidth=1.6, label="Directriz")

    niveles = [(r.entrada, C_ENTRADA, "Entrada", "-"), (r.stop, C_STOP, "Stop", "-"),
               (r.objetivo1, C_OBJ, "Obj. 1", ":"), (r.objetivo2, C_OBJ, "Obj. 2", "-"),
               (r.nivel_barrido, C_BARR, "Nivel barrido", "--")]
    niveles = [n for n in niveles if not (n[0] is None or (isinstance(n[0], float) and math.isnan(n[0])))]
    lo = min([d.Low.min()] + [n[0] for n in niveles])
    hi = max([d.High.max()] + [n[0] for n in niveles])
    pad = (hi - lo) * 0.05
    ax.set_ylim(lo - pad, hi + pad)
    # etiquetas a la derecha sin solaparse (separación mínima del 5 % del rango)
    gap = (hi - lo) * 0.05
    pos = []
    for v, c, lab, ls in sorted(niveles, key=lambda n: n[0]):
        y = v if not pos or v - pos[-1] >= gap else pos[-1] + gap
        pos.append(y)
        ax.axhline(v, color=c, linewidth=1.2, linestyle=ls)
        ax.annotate(f"{lab} {_f(v)}", xy=(len(d) + 0.5, v), xytext=(len(d) + 1.5, y), textcoords="data",
                    fontsize=8, color=INK, va="center", annotation_clip=False,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=c, lw=1))
    ax.set_xlim(-1, len(d) + 1)

    ic, tit, _ = ESTADOS.get(r.estado, ("", r.estado, ""))
    ax.set_title(f"{r.ticker}  {r.nombre}  ·  {tit}  ·  R/R {_f(r.rr, 1)}", loc="left",
                 fontsize=11, color=INK, fontweight="bold")
    for a in (ax, axv):
        a.grid(color=GRID, linewidth=0.6)
        a.tick_params(colors=MUTED, labelsize=8)
        for s in a.spines.values():
            s.set_visible(False)
    ticks = x[:: max(1, len(x) // 7)]
    axv.set_xticks(ticks)
    axv.set_xticklabels([d.index[i].strftime("%d-%b") for i in ticks])
    axv.set_yticks([])
    fig.subplots_adjust(left=0.07, right=0.84, top=0.93, bottom=0.07)
    fig.savefig(ruta, dpi=100)
    plt.close(fig)


# ----------------------------------------------------------------- HTML email
def _tabla(filas: list[Resultado], con_ucits: dict, cids: dict) -> str:
    th = ("<tr style='background:#f6f8fa;color:#57606a;font-size:12px;text-align:left'>"
          "<th>Valor</th><th>Cierre</th><th>Entrada</th><th>Stop</th><th>Riesgo</th>"
          "<th>Obj. 1</th><th>Obj. 2</th><th>R/R</th><th>Punt.</th><th>Notas</th></tr>")
    out = []
    for r in filas:
        notas = "; ".join(r.confirmaciones + [f"⚠ {a}" for a in r.avisos])
        uc = con_ucits.get(r.ticker)
        extra = f"<br><span style='color:#57606a;font-size:11px'>Comprar vía: {uc}</span>" if uc else ""
        marco = " <span style='font-size:10px;background:#ddf4ff;padding:1px 4px;border-radius:3px'>SEMANAL</span>" if r.marco == "W" else ""
        out.append(
            f"<tr style='border-top:1px solid #d8dee4;font-size:13px;vertical-align:top'>"
            f"<td><b>{r.ticker}</b>{marco}<br><span style='color:#57606a;font-size:11px'>{r.nombre} · {r.grupo}</span>{extra}</td>"
            f"<td>{_f(r.cierre)}</td><td><b>{_f(r.entrada)}</b></td><td style='color:#cf222e'>{_f(r.stop)}</td>"
            f"<td>{_f(r.riesgo_pct, 1)} %</td><td>{_f(r.objetivo1)}</td><td>{_f(r.objetivo2)}</td>"
            f"<td><b>{_f(r.rr, 1)}</b></td><td>{_f(r.puntuacion, 0)}</td>"
            f"<td style='font-size:11px;color:#57606a'>{notas}</td></tr>")
    return f"<table cellpadding='6' cellspacing='0' style='border-collapse:collapse;width:100%'>{th}{''.join(out)}</table>"


def html_email(fecha: str, mercado: list[dict], grupos: dict, ucits: dict, cids: dict, stats: dict,
               extra_html: str = "") -> str:
    sem = "".join(
        f"<tr style='font-size:13px;border-top:1px solid #d8dee4'><td><b>{m['nombre']}</b></td><td>{_f(m['cierre'])}</td>"
        f"<td>{'🟢' if m['macd_sem'] > 0 else '🔴'} {'sobre' if m['macd_sem'] > 0 else 'bajo'} cero</td>"
        f"<td>{'🟢 alcista' if m['macd_men_alc'] else '🔴 bajista'}</td>"
        f"<td>{'🟢 encima' if m['sobre_sma200'] else '🔴 debajo'}</td><td>{m['estado']}</td></tr>"
        for m in mercado)
    partes = [f"""
<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1f2328;max-width:860px">
<h2 style="margin:0 0 4px">Escáner método Cava · {fecha}</h2>
<p style="color:#57606a;margin:0 0 16px">{stats['analizados']} valores analizados ·
🟢 {stats['SENAL']} señales · 🟠 {stats['TRAMPA']} trampas · 🟡 {stats['VIGILANCIA']} en vigilancia</p>
<h3 style="margin:16px 0 6px">Semáforo de mercado</h3>
<table cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
<tr style="background:#f6f8fa;color:#57606a;font-size:12px;text-align:left"><th>Índice</th><th>Cierre</th><th>MACD semanal</th><th>MACD mensual</th><th>Media 200</th><th>Estado</th></tr>
{sem}</table>"""]
    for est in ("SENAL", "TRAMPA", "VIGILANCIA"):
        filas = grupos.get(est, [])
        ic, tit, bg = ESTADOS[est]
        partes.append(f"<h3 style='margin:22px 0 6px;background:{bg};padding:6px 8px;border-radius:6px'>{ic} {tit} ({len(filas)})</h3>")
        if not filas:
            partes.append("<p style='color:#57606a'>Ninguno hoy.</p>")
            continue
        if est == "TRAMPA":
            partes.append("<p style='font-size:12px;color:#57606a;margin:0 0 6px'>La entrada indicada es el nivel de la directriz para mañana: la señal salta si el precio cierra por encima.</p>")
        if est == "VIGILANCIA":
            partes.append("<p style='font-size:12px;color:#57606a;margin:0 0 6px'>Aún sin trampa. Stop provisional bajo el mínimo de la corrección; se recalculará cuando haya barrida.</p>")
        partes.append(_tabla(filas, ucits, cids))
    partes.append(extra_html)
    if cids:
        partes.append("<h3 style='margin:24px 0 6px'>Gráficos</h3>")
        for t, cid in cids.items():
            partes.append(f"<p><img src='cid:{cid}' alt='{t}' style='max-width:100%;border:1px solid #d8dee4;border-radius:6px'></p>")
    partes.append("""<p style="font-size:11px;color:#57606a;margin-top:24px">Filtro automático basado en una
reconstrucción pública del método de J. L. Cava. No es una recomendación de inversión: revisa cada gráfico y decide tú.</p></div>""")
    return "".join(partes)


# ----------------------------------------------------------------- JSON / Markdown
def guardar(carpeta: Path, fecha: str, mercado: list[dict], resultados: list[Resultado], stats: dict,
            extra: dict | None = None):
    carpeta.mkdir(parents=True, exist_ok=True)
    datos = {"fecha": fecha, "estadisticas": stats, "mercado": mercado,
             "candidatos": [r.to_dict() for r in resultados if r.estado != "NADA"], **(extra or {})}
    txt = json.dumps(datos, ensure_ascii=False, indent=1, default=str)
    (carpeta / "latest.json").write_text(txt, encoding="utf-8")
    hist = carpeta / "historico"
    hist.mkdir(exist_ok=True)
    (hist / f"{fecha}.json").write_text(txt, encoding="utf-8")

    md = [f"# Escáner método Cava · {fecha}", "",
          f"Analizados: {stats['analizados']} · Señales: {stats['SENAL']} · Trampas: {stats['TRAMPA']} · Vigilancia: {stats['VIGILANCIA']}", "",
          "## Mercado", "| Índice | Cierre | MACD sem. | MACD mens. alcista | Sobre SMA200 | Estado |", "|---|---|---|---|---|---|"]
    md += [f"| {m['nombre']} | {_f(m['cierre'])} | {_f(m['macd_sem'])} | {'sí' if m['macd_men_alc'] else 'no'} | {'sí' if m['sobre_sma200'] else 'no'} | {m['estado']} |" for m in mercado]
    for est in ("SENAL", "TRAMPA", "VIGILANCIA"):
        filas = [r for r in resultados if r.estado == est]
        md += ["", f"## {ESTADOS[est][1]} ({len(filas)})", ""]
        if filas:
            md += ["| Valor | Marco | Cierre | Entrada | Stop | Riesgo % | Obj1 | Obj2 | R/R | Punt. | Notas |", "|---|---|---|---|---|---|---|---|---|---|---|"]
            md += [f"| {r.ticker} ({r.nombre}) | {r.marco} | {_f(r.cierre)} | {_f(r.entrada)} | {_f(r.stop)} | {_f(r.riesgo_pct, 1)} | {_f(r.objetivo1)} | {_f(r.objetivo2)} | {_f(r.rr, 1)} | {_f(r.puntuacion, 0)} | {'; '.join(r.confirmaciones + r.avisos)} |" for r in filas]
    (carpeta / "latest.md").write_text("\n".join(md), encoding="utf-8")
