# Bybit Intraday Weakness Research v5

Дата подготовки: 2026-05-20

## Scope

Проверка сделана на публичных tick-level файлах Bybit `/trading/` для:

- 6 reported winners: EIGEN, GRASS, RVN, ENJ, JTO, STG
- 1 дополнительный candidate, найденный фильтром: ENA
- near-miss controls: AERO, ARKM, BOME, APE, CHZ, DRIFT, CETUS

Это не полный 30–60 day full-universe backtest. Это tick-level validation текущей гипотезы v4/v5 на сильных кандидатах и near-miss controls.

## Методика

Для каждого symbol/date:

1. Загрузить Bybit public trade archive CSV.GZ.
2. Собрать 5m OHLCV из тиков.
3. Посчитать cumulative intraday VWAP.
4. Для weak-mode найти path high, от которого был максимальный последующий short move.
5. Для pump-mode найти peak после максимального intraday runup.
6. Entry proxy: первый 5m close ниже cumulative VWAP после peak.
7. После entry проверить tick-by-tick, что срабатывает первым: TP или SL.
8. Отдельно проверить max holding windows: 2h, 3h, 4h, 6h, 8h, 12h, EOD.

## Entry summary: 7 сильных кандидатов

| Symbol | Date | Mode | Entry UTC | MFE after entry | MAE after entry | Max short move | Notes |
|---|---:|---|---:|---:|---:|---:|---|
| EIGENUSDT | 2026-03-18 | weak | 05:40 | 9.16% | 0.26% | 10.41% | clean weak-continuation |
| GRASSUSDT | 2026-03-18 | weak | 12:30 | 12.99% | 2.78% | 15.77% | clean, but entry later |
| RVNUSDT | 2026-03-18 | weak | 04:05 | 6.17% | 2.53% | 9.85% | liquidity dry-up style |
| ENJUSDT | 2026-03-18 | pump | 10:10 | 13.72% | 5.63% | 23.97% | pump-fade, requires wider stop |
| JTOUSDT | 2026-03-27 | weak | 10:40 | 4.06% | 0.70% | 6.75% | weaker target; 4% works, 5–6% may not |
| STGUSDT | 2026-03-27 | pump | 14:30 | 9.33% | 1.25% | 20.39% | good pump-fade after later confirmation |
| ENAUSDT | 2026-03-27 | weak | 07:00 | 9.82% | 0.67% | 11.27% | extra candidate; looks like true winner |

## TP/SL grid: key results on 7 candidates

Underlying TP/SL, not leveraged PnL.

| TP | SL | TP hits | SL hits | EOD/time exits | Avg underlying PnL | Notes |
|---:|---:|---:|---:|---:|---:|---|
| 4% | 7% | 7/7 | 0/7 | 0/7 | 4.00% | safest confirmation target |
| 5% | 7% | 6/7 | 0/7 | 1/7 | 4.69% | JTO exits EOD around +2.86% |
| 6% | 7% | 6/7 | 0/7 | 1/7 | 5.55% | good balance; JTO misses |
| 8% | 7% | 5/7 | 0/7 | 2/7 | 6.85% | stronger but slower; RVN/JTO miss |
| 8% | 3% | 4/7 | 1/7 | 2/7 | 5.28% | too tight for ENJ pump-fade |
| 12% | 7% | 2/7 | 0/7 | 5/7 | 8.12% | high average but many EOD holds; not clean TP strategy |

## Holding window insight

The move is not immediate. Many winners need 4–12 hours after VWAP-loss.

For TP 6% / SL 7%:

| Max holding | TP hits | SL hits | Avg underlying PnL |
|---:|---:|---:|---:|
| 2h | 0/7 | 0/7 | 0.87% |
| 4h | 2/7 | 0/7 | 3.58% |
| 8h | 4/7 | 0/7 | 5.02% |
| 12h | 6/7 | 0/7 | 5.61% |
| EOD | 6/7 | 0/7 | 5.55% |

Implication: this is intraday, but not necessarily scalp. A 2–3 hour time stop is probably too aggressive.

## Weak vs pump-fade

### Weak continuation

Weak candidates: EIGEN, GRASS, RVN, JTO, ENA.

- 4% TP hit: 5/5
- 5–6% TP hit: 4/5; JTO missed but still ended positive
- 8% TP hit: 3/5; RVN and JTO missed
- MAE was modest: roughly 0.26%–2.78%

Suggested weak-mode exit logic:

- TP1: 4% underlying
- TP2: 6% underlying
- optional runner to 8% only when MFE momentum remains strong
- SL: technical reclaim of VWAP/high is better than fixed tight 2–3%; hard disaster stop can be around 5–7% underlying

### Pump-and-fade

Pump candidates: ENJ, STG.

- 8% TP / 7% SL: 2/2 TP
- 3% SL would stop ENJ before the eventual fade
- Pump-fade needs wider stop or a later/cleaner retest entry

Suggested pump-mode exit logic:

- TP1: 6%–8% underlying
- TP2: 10%–12% underlying only for extreme pumps
- SL: 7% underlying or technical reclaim of failed high; fixed 3% is too tight for pump-fade

## Near-miss controls

Some controls below the v4/v5 threshold also had tradeable movement:

- AERO score 7: MFE 7.21%, 6% TP hit
- ARKM score 6: MFE 6.64%, 6% TP hit late
- DRIFT score 10 but turnover below $1M: MFE 7.24%, 6% TP hit late
- CHZ score 5: MFE 4.14%, only 4% TP hit
- BOME score 6: MFE 3.82%, no 4% TP

Interpretation: the conservative rule `turnover >= $1M AND score >= 9` is good for narrowing the funnel, but it is not the whole opportunity set. A broader strategy could include score 6–8 as a lower-confidence tier with smaller size and lower target.

## Proposed v5 rules

### Tier A: high-confidence weak continuation

```text
turnover_usdt >= 1,000,000
AND weak_score >= 9
AND entry = first 5m close below cumulative VWAP after peak
```

Exit:

```text
TP1 = 4% underlying
TP2 = 6% underlying
runner = 8% only if trend remains clean
SL = VWAP reclaim / failed-high reclaim / hard 5–7% underlying
max hold = 8–12h or EOD
```

### Tier B: high-confidence pump-and-fade

```text
turnover_usdt >= 1,000,000
AND pump_score >= 9
AND turnover_ratio >= 8x
AND intraday_runup >= 25%
AND entry = VWAP loss or failed VWAP reclaim after pump peak
```

Exit:

```text
TP1 = 6% underlying
TP2 = 8% underlying
runner = 10–12% only for extreme pump
SL = hard 7% underlying or reclaim of failed high
avoid fixed 3% SL after first VWAP-loss; it is too tight for pump-fade
```

### Tier C: lower-confidence expansion bucket

```text
turnover_usdt >= 1,000,000
AND candidate_score 6–8
AND MFE/MAE proxy looks clean
```

Exit:

```text
TP = 4% underlying
smaller size
no runner
```

This bucket is not part of the current main strategy, but may become useful after full-universe testing.

## Current conclusion

The strongest practical rule is no longer simply `+50% PnL target`. The tick-level test suggests:

```text
Underlying target 4–6% is robust for weak-continuation.
Underlying target 6–8% is realistic for pump-fade.
A 3% stop is too tight for pump-fade.
A 2–3h time stop is too short; 8–12h/EOD works better in this sample.
```

At 5x leverage:

```text
4% underlying = about +20% position PnL
6% underlying = about +30% position PnL
8% underlying = about +40% position PnL
10% underlying = about +50% position PnL
```

The reported +50% results likely require either:

1. better entry than our VWAP-loss proxy,
2. higher leverage,
3. runner exits beyond TP1/TP2,
4. multiple partial trades,
5. or a combination of these.

## Next full backtest requirement

To validate profitability, run full-universe test over 30–60 days:

- all Bybit linear USDT perps
- exclude majors
- compute weak_score and pump_score daily
- simulate TP/SL order tick-by-tick
- include fees, slippage, funding, and realistic order type
- evaluate by score tier, turnover tier, time of peak, and mode

