# Backtest de variantes (2019-10-09 → 2026-10-01)

Aprendizaje: hasta 2024-01-01 · Validación: desde 2024-01-01. Las decisiones se toman con el aprendizaje y se confirman en validación.

| Var. | Descripción | Periodo | Operaciones/año | Acierto | R medio | R al año | Profit factor | Peor racha | Máx. DD (R) |
|---|---|---|---|---|---|---|---|---|---|
| A | Método actual | hasta 2024 | 923 | 20.7 % | +0.44 | +403.8 | 1.53 | 164 | -443.7 |
| A | Método actual | desde 2024 | 979 | 20.4 % | +0.48 | +469.0 | 1.57 | 89 | -134.3 |
| B | A + stop a la entrada en +1R | hasta 2024 | 1057 | 27.6 % | +0.20 | +207.9 | 1.37 | 45 | -272.2 |
| B | A + stop a la entrada en +1R | desde 2024 | 1148 | 27.9 % | +0.17 | +193.1 | 1.32 | 30 | -107.3 |
| C | B + solo disparo de recuperación con volumen | hasta 2024 | 837 | 27.5 % | +0.22 | +184.8 | 1.41 | 33 | -193.3 |
| C | B + solo disparo de recuperación con volumen | desde 2024 | 889 | 28.7 % | +0.17 | +154.6 | 1.33 | 34 | -121.0 |
| D | C + filtro de tendencia del índice | hasta 2024 | 653 | 28.0 % | +0.25 | +163.0 | 1.46 | 26 | -130.4 |
| D | C + filtro de tendencia del índice | desde 2024 | 832 | 28.0 % | +0.16 | +128.9 | 1.28 | 36 | -161.2 |
| E | D + puntuación aprendida, máx. 2 señales/día | hasta 2024 | 240 | 26.0 % | +0.22 | +53.1 | 1.39 | 14 | -57.7 |
| E | D + puntuación aprendida, máx. 2 señales/día | desde 2024 | 346 | 25.2 % | +0.02 | +6.2 | 1.03 | 24 | -86.5 |

## Puntuación aprendida (variante E)

- relación riesgo/recompensa: más alto es mejor (tramo bajo +0.18 R, tramo alto +0.36 R)
- RSI(14) el día de la señal: más bajo es mejor (tramo bajo +0.43 R, tramo alto +0.24 R)
- estocástico 50: más bajo es mejor (tramo bajo +0.37 R, tramo alto +0.18 R)
- mercado España: resta (R medio +0.09, 153 operaciones)
- mercado Europa tech: resta (R medio +0.01, 136 operaciones)

¿Ordena bien en validación? (R medio por puntuación; debería crecer hacia la derecha)

| Puntuación | -2 | -1 | 0 | 1 | 2 | 3 |
|---|---|---|---|---|---|---|
| R medio | +0.27 | +0.27 | +0.17 | +0.11 | +0.07 | -0.24 |
| Operaciones | 562 | 448 | 439 | 385 | 403 | 203 |

## Detalle de la variante activa en el escáner (A)


Operaciones abiertas: 73 · pendientes de entrar: 0 · anuladas (abren bajo el stop): 0

| Gestión | Cerradas | Acierto | R medio | Profit factor | Máx. drawdown (R) |
|---|---|---|---|---|---|
| Fija (stop / obj. 2) | 6575 | 20.6 % | +0.45 | 1.54 | -443.7 |
| Gestionada (stop a entrada en +1R) | 6604 | 28.0 % | +0.19 | 1.35 | -258.4 |
| Con seguimiento (SAR) | 6602 | 28.0 % | +0.22 | 1.35 | -280.8 |

## Por mercado

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| EEUU | 5623 | 20.5 % | +0.42 | 1.5 | -388.2 |
| ETFs | 313 | 25.6 % | +1.13 | 2.37 | -33.3 |
| España | 372 | 22.0 % | +0.64 | 1.79 | -30.0 |
| Europa tech | 267 | 13.9 % | +0.12 | 1.13 | -93.9 |

## Por marco

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| D | 6575 | 20.6 % | +0.45 | 1.54 | -443.7 |

## Por disparo

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| recuperación del nivel barrido con volumen | 3893 | 19.1 % | +0.57 | 1.66 | -305.6 |
| recuperación del nivel barrido con volumen + ruptura de directriz | 400 | 18.5 % | -0.01 | 0.99 | -55.1 |
| ruptura de directriz | 2282 | 23.5 % | +0.35 | 1.43 | -174.0 |

## Por puntuación

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| 50-69 | 4197 | 18.9 % | +0.51 | 1.59 | -326.4 |
| <50 | 2170 | 23.6 % | +0.36 | 1.45 | -243.9 |
| ≥70 | 208 | 23.6 % | +0.39 | 1.47 | -20.5 |

## Por volumen en la trampa

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| con volumen | 4322 | 19.2 % | +0.51 | 1.6 | -344.5 |
| sin volumen | 2253 | 23.3 % | +0.35 | 1.43 | -174.9 |

## Por año

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| 2019 | 279 | 17.9 % | +0.28 | 1.31 | -108.5 |
| 2020 | 926 | 25.9 % | +0.70 | 1.88 | -442.8 |
| 2021 | 1172 | 23.2 % | +0.51 | 1.64 | -102.9 |
| 2022 | 661 | 11.2 % | -0.20 | 0.78 | -245.2 |
| 2023 | 857 | 19.8 % | +0.60 | 1.72 | -230.4 |
| 2024 | 1148 | 23.3 % | +0.73 | 1.88 | -134.7 |
| 2025 | 875 | 23.1 % | +0.69 | 1.84 | -270.1 |
| 2026 | 657 | 11.9 % | -0.23 | 0.74 | -164.5 |

## Por selección diaria

| Grupo | Cerradas | Acierto | R medio | Profit factor | Máx. DD |
|---|---|---|---|---|---|
| resto | 6575 | 20.6 % | +0.45 | 1.54 | -443.7 |

> Aviso: sesgo de supervivencia (listas actuales de los índices), solo marco diario, entrada a la apertura siguiente, sin comisiones. Sirve para comparar variantes, no como promesa de rentabilidad.