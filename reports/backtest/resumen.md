# Backtest de variantes (2019-10-09 → 2026-10-01)

Aprendizaje: hasta 2024-01-01 · Validación: desde 2024-01-01. Una mejora solo cuenta si se mantiene en validación.

| Var. | Descripción | Periodo | Operaciones/año | Acierto | R medio | R al año | Profit factor | Peor racha | Máx. DD (R) |
|---|---|---|---|---|---|---|---|---|---|
| A | Método actual (gestión fija) | hasta 2024 | 923 | 20.8 % | +0.44 | +409.9 | 1.54 | 167 | -439.7 |
| A | Método actual (gestión fija) | desde 2024 | 981 | 20.4 % | +0.47 | +465.3 | 1.56 | 87 | -135.1 |
| B | A con stop a la entrada en +1R | hasta 2024 | 1057 | 27.7 % | +0.20 | +213.8 | 1.38 | 46 | -276.6 |
| B | A con stop a la entrada en +1R | desde 2024 | 1150 | 27.9 % | +0.16 | +186.5 | 1.30 | 38 | -107.3 |
| C | Calidad ≥ 3 | hasta 2024 | 218 | 15.9 % | +0.88 | +192.1 | 1.99 | 74 | -117.7 |
| C | Calidad ≥ 3 | desde 2024 | 238 | 15.8 % | +1.01 | +240.9 | 2.13 | 47 | -65.3 |
| D | Calidad ≥ 4 (⭐) | hasta 2024 | 30 | 19.2 % | +1.94 | +58.5 | 3.29 | 20 | -23.4 |
| D | Calidad ≥ 4 (⭐) | desde 2024 | 33 | 22.0 % | +2.32 | +77.6 | 3.83 | 18 | -19.8 |
| E | Calidad ≥ 3 + filtro de mercado | hasta 2024 | 183 | 15.5 % | +0.75 | +137.0 | 1.83 | 73 | -105.7 |
| E | Calidad ≥ 3 + filtro de mercado | desde 2024 | 228 | 15.1 % | +0.98 | +223.9 | 2.09 | 47 | -73.8 |

## ¿El índice de calidad sigue ordenando bien?

R medio por operación según la calidad (debería crecer hacia la derecha en los dos periodos).

| Periodo | 0 | 1 | 2 | 3 | ≥4 |
|---|---|---|---|---|---|
| aprendizaje | +0.28 (645) | +0.36 (1811) | +0.48 (1655) | +0.70 (843) | +1.85 (124) |
| validacion | -0.03 (452) | +0.27 (1227) | +0.42 (1109) | +0.81 (609) | +2.26 (94) |

Umbrales de calidad en uso: rr_alto = 9.5, retroceso_bajo = 0.28, ratio_tiempo_alto = 0.23 · Recalculados con el periodo de aprendizaje: rr_alto = 9.5, retroceso_bajo = 0.28, ratio_tiempo_alto = 0.23

## Detalle de la variante activa en el escáner (D)


Operaciones abiertas: 1 · pendientes de entrar: 0 · anuladas (abren bajo el stop): 0

| Gestión | Cerradas | Acierto | R medio | Profit factor | Máx. drawdown (R) |
|---|---|---|---|---|---|
| Fija (stop / obj. 2) | 211 | 20.4 % | +2.10 | 3.52 | -23.4 |
| Gestionada (stop a entrada en +1R) | 211 | 30.8 % | +1.08 | 3.02 | -12.6 |
| Con seguimiento (SAR) | 211 | 32.7 % | +1.09 | 2.75 | -13.8 |

## Por mercado

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| EEUU | 121 | 18.2 % | +1.58 | 2.9 | -15.4 |
| ETFs | 82 | 23.2 % | +1.96 | 3.35 | -12.1 |
| España | 8 | 25.0 % | +11.44 | 13.69 | -4.2 |

## Por marco

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| D | 211 | 20.4 % | +2.10 | 3.52 | -23.4 |

## Por disparo

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| recuperación del nivel barrido con volumen | 208 | 20.7 % | +2.15 | 3.59 | -23.4 |
| ruptura de directriz | 3 | 0.0 % | -1.08 | 0.0 | -2.0 |

## Por puntuación

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| 50-69 | 167 | 19.2 % | +1.78 | 3.09 | -26.9 |
| <50 | 43 | 25.6 % | +3.40 | 5.54 | -9.0 |
| ≥70 | 1 | 0.0 % | -1.00 | 0.0 | 0.0 |

## Por volumen en la trampa

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| con volumen | 208 | 20.7 % | +2.15 | 3.59 | -23.4 |
| sin volumen | 3 | 0.0 % | -1.08 | 0.0 | -2.0 |

## Por año

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| 2019 | 13 | 7.7 % | -0.27 | 0.71 | -11.0 |
| 2020 | 42 | 23.8 % | +2.45 | 3.9 | -22.1 |
| 2021 | 36 | 25.0 % | +2.95 | 4.82 | -12.1 |
| 2022 | 6 | 0.0 % | -1.00 | 0.0 | -5.0 |
| 2023 | 23 | 13.0 % | +1.42 | 2.62 | -13.2 |
| 2024 | 40 | 15.0 % | +1.17 | 2.38 | -10.3 |
| 2025 | 41 | 31.7 % | +4.08 | 6.37 | -18.8 |
| 2026 | 10 | 10.0 % | -0.34 | 0.62 | -4.1 |

## Por selección diaria

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| resto | 211 | 20.4 % | +2.10 | 3.52 | -23.4 |

## Por calidad

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| ≥4 ⭐ | 211 | 20.4 % | +2.10 | 3.52 | -23.4 |

> Aviso: sesgo de supervivencia (listas actuales de los índices), solo marco diario, entrada a la apertura siguiente, sin comisiones. Sirve para comparar variantes, no como promesa de rentabilidad.