"""
Escáner diario "Método Cava".
Uso:  python run.py            (descarga datos, analiza, guarda informe y envía email)
      python run.py --sin-email
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

from screener import data as D
from screener import indicators as ind
from screener.emailer import enviar
from screener import evaluacion as EV
from screener.engine import evaluar
from screener.report import ESTADOS, grafico, guardar, html_email

BASE = Path(__file__).parent


def log(*a):
    print(*a, flush=True)


def analizar(precios: dict, universo, cfg: dict):
    resultados, mercado, analizados = [], [], 0
    info = universo.set_index("ticker")
    for t, df in precios.items():
        row = info.loc[t]
        nombre, grupo = row["name"], row["grupo"]
        es_indice = t.startswith("^")
        # liquidez (no aplica a índices)
        if not es_indice:
            liq = (df.Close * df.Volume).iloc[-20:].mean()
            if liq < cfg["liquidez_minima"]:
                continue
        analizados += 1
        sem, men = ind.resample(df, "W-FRI"), ind.resample(df, "ME")
        try:
            r = evaluar(df, t, cfg, "D", nombre, grupo, df_superior=sem, df_mensual=men)
            # mismo método sobre gráfico semanal (contexto: MACD mensual)
            rw = evaluar(sem, t, cfg, "W", nombre, grupo, df_superior=men, df_mensual=men)
        except Exception as e:  # noqa: BLE001
            log(f"  {t}: error en el análisis ({e})")
            continue
        if es_indice:
            dd = ind.add_all(df)
            ws, ms = ind.add_all(sem), ind.add_all(men)
            mercado.append(dict(ticker=t, nombre=nombre, cierre=float(df.Close.iloc[-1]),
                                macd_sem=float(ws.macd.iloc[-1]),
                                macd_men_alc=bool(ms.macd.iloc[-1] > ms.macd_sig.iloc[-1]),
                                sobre_sma200=bool(dd.Close.iloc[-1] > dd.sma200.iloc[-1]),
                                estado=ESTADOS.get(r.estado, ("", r.motivo))[1] if r.estado != "NADA" else r.motivo))
        resultados.append((r, df))
        rw.fecha = df.index[-1].strftime("%Y-%m-%d")   # la vela semanal en curso lleva fecha del viernes
        if rw.estado in ("SENAL", "TRAMPA"):
            resultados.append((rw, sem))
    return resultados, mercado, analizados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-email", action="store_true")
    ap.add_argument("--sin-refresco", action="store_true", help="no actualizar listas S&P/Nasdaq")
    args = ap.parse_args()

    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    carpeta_u = BASE / "universe"
    if not args.sin_refresco:
        D.refrescar_universo(carpeta_u, log)
    universo = D.cargar_universo(carpeta_u, cfg["universos"])
    log(f"Universo: {len(universo)} valores")

    precios = D.descargar(universo.ticker.tolist(), cfg["anios_historico"], log=log)
    log(f"Datos obtenidos: {len(precios)}/{len(universo)}")
    if len(precios) < 0.5 * len(universo):
        log("ERROR: han fallado demasiadas descargas; no se genera informe.")
        sys.exit(1)

    resultados, mercado, analizados = analizar(precios, universo, cfg)
    fecha = max(df.index[-1] for df in precios.values()).strftime("%Y-%m-%d")

    grupos = {}
    for est in ("SENAL", "TRAMPA", "VIGILANCIA"):
        filas = sorted([r for r, _ in resultados if r.estado == est and not r.ticker.startswith("^")],
                       key=lambda r: -r.puntuacion)
        tope = cfg["informe"]["max_vigilancia"] if est == "VIGILANCIA" else cfg["informe"].get("max_por_estado", 30)
        filas = filas[:tope]
        grupos[est] = filas
    stats = {"analizados": analizados, **{k: len(v) for k, v in grupos.items()}}

    # gráficos para señales y trampas
    carpeta_r = BASE / "reports"
    carpeta_g = carpeta_r / "charts"
    shutil.rmtree(carpeta_g, ignore_errors=True)
    carpeta_g.mkdir(parents=True)
    dfs = {(r.ticker, r.marco): df for r, df in resultados}
    cids, imagenes = {}, {}
    for r in (grupos["SENAL"] + grupos["TRAMPA"])[: cfg["informe"]["max_graficos"]]:
        nombre = f"{r.ticker.replace('^', '')}_{r.marco}.png"
        ruta = carpeta_g / nombre
        grafico(ind.add_all(dfs[(r.ticker, r.marco)]), r, ruta)
        cid = nombre.replace(".", "_")
        cids[f"{r.ticker} ({r.marco})"] = cid
        imagenes[cid] = ruta

    todos = [r for r, _ in resultados]

    # autoevaluación: registra las señales de hoy y recalcula el resultado de todas las anteriores
    carpeta_seg = carpeta_r / "seguimiento"
    nuevas = EV.registrar_senales(carpeta_seg, todos)
    st_vivo = EV.actualizar_seguimiento(carpeta_seg, precios)
    log(f"Seguimiento: {nuevas} señales nuevas registradas")
    ruta_bt = carpeta_r / "backtest" / "resumen.json"
    st_bt = json.loads(ruta_bt.read_text(encoding="utf-8")) if ruta_bt.exists() else None

    guardar(carpeta_r, fecha, mercado, [r for est in grupos.values() for r in est], stats,
            extra={"autoevaluacion_vivo": st_vivo, "autoevaluacion_backtest": (st_bt or {}).get("global")})
    ucits = dict(zip(universo.ticker, universo.ucits))
    html = html_email(fecha, mercado, grupos, {k: v for k, v in ucits.items() if v}, cids, stats,
                      extra_html=EV.html(st_vivo, st_bt))
    (carpeta_r / "latest.html").write_text(html, encoding="utf-8")
    if st_vivo:
        with open(carpeta_r / "latest.md", "a", encoding="utf-8") as f:
            f.write("\n\n" + EV.markdown(st_vivo, "Autoevaluación en vivo").replace("# ", "## ", 1))
    texto = (carpeta_r / "latest.md").read_text(encoding="utf-8")
    log(f"Informe {fecha}: {stats}")
    log(f"Descartados: {sum(1 for r in todos if r.estado == 'NADA')}")

    if not args.sin_email:
        asunto = f"Escáner Cava {fecha} · 🟢 {stats['SENAL']} · 🟠 {stats['TRAMPA']} · 🟡 {stats['VIGILANCIA']}"
        enviar(asunto, html, texto, imagenes, log)


if __name__ == "__main__":
    main()
