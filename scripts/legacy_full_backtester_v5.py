#!/usr/bin/env python3
"""
Bybit public archive full backtester v5: weak intraday short / pump-fade research.

This script is designed to run on your own machine/VPS with internet access.
It uses only public Bybit historical trade archives, no API key.

Data source pattern:
  https://public.bybit.com/trading/{SYMBOL}/{SYMBOL}{YYYY-MM-DD}.csv.gz

Example quick test:
  python bybit_public_archive_full_backtester_v5.py \
    --start 2026-03-18 --end 2026-03-27 \
    --symbols EIGENUSDT,GRASSUSDT,RVNUSDT,ENJUSDT,JTOUSDT,STGUSDT,ENAUSDT \
    --cache-dir ./bybit_cache \
    --out-metrics metrics.csv --out-trades trades.csv

Example full universe, 30 days:
  python bybit_public_archive_full_backtester_v5.py \
    --start 2026-03-01 --end 2026-03-31 \
    --full-universe \
    --cache-dir ./bybit_cache \
    --out-metrics bybit_metrics_2026_03.csv \
    --out-trades bybit_trades_2026_03.csv

Notes:
  - Full-universe tick-level scans are large. Start with --max-symbols or a symbol list.
  - This is research code, not live trading code.
  - Fees, slippage, funding and order-book depth are not included in PnL here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import requests

BASE_ARCHIVE = "https://public.bybit.com/trading/"
MAJORS = {
    "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","BNBUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT",
    "LINKUSDT","TRXUSDT","TONUSDT","DOTUSDT","LTCUSDT","BCHUSDT","POLUSDT","MATICUSDT",
    "ETCUSDT","UNIUSDT","NEARUSDT","APTUSDT","ARBUSDT","OPUSDT","FILUSDT","ATOMUSDT",
}


def parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def date_range(start: dt.date, end: dt.date) -> list[dt.date]:
    out=[]; cur=start
    while cur <= end:
        out.append(cur); cur += dt.timedelta(days=1)
    return out


def session() -> requests.Session:
    s=requests.Session()
    s.headers.update({"User-Agent":"bybit-weak-intraday-research-v5/1.0"})
    return s


def get_universe(sess: requests.Session, exclude_majors=True) -> list[str]:
    r=sess.get(BASE_ARCHIVE, timeout=30)
    r.raise_for_status()
    syms=[]
    for m in re.finditer(r'href="([^"]+/)"', r.text):
        sym=m.group(1).strip('/').upper()
        if not sym.endswith('USDT'):
            continue
        if '-' in sym or sym.endswith('PERP'):
            continue
        if exclude_majors and sym in MAJORS:
            continue
        syms.append(sym)
    return sorted(set(syms))


def archive_url(symbol: str, day: dt.date) -> str:
    return f"{BASE_ARCHIVE}{symbol}/{symbol}{day:%Y-%m-%d}.csv.gz"


def cache_path(cache_dir: Path, symbol: str, day: dt.date) -> Path:
    return cache_dir / symbol / f"{symbol}{day:%Y-%m-%d}.csv.gz"


def download_file(sess: requests.Session, url: str, out: Path, retries=3, sleep=0.25) -> bool:
    if out.exists() and out.stat().st_size > 0:
        return True
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp=out.with_suffix(out.suffix+'.tmp')
    for attempt in range(retries):
        try:
            r=sess.get(url, stream=True, timeout=45)
            if r.status_code == 404:
                return False
            r.raise_for_status()
            with open(tmp,'wb') as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
            tmp.replace(out)
            time.sleep(sleep)
            return True
        except Exception as e:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            if attempt == retries-1:
                print(f"WARN download failed {url}: {e}", file=sys.stderr)
                return False
            time.sleep(1.0+attempt)
    return False


def load_ticks(path: Path) -> pd.DataFrame:
    usecols=['timestamp','symbol','side','size','price','foreignNotional']
    df=pd.read_csv(path, usecols=usecols)
    ts_ms=(df['timestamp'].astype(float).to_numpy()*1000).astype('int64')
    df['dt']=pd.to_datetime(ts_ms, unit='ms', utc=True)
    df['ts_ns']=df['dt'].astype('int64')
    df['size']=pd.to_numeric(df['size'], errors='coerce')
    df['price']=pd.to_numeric(df['price'], errors='coerce')
    df['quote']=pd.to_numeric(df['foreignNotional'], errors='coerce').abs()
    df=df.dropna(subset=['dt','ts_ns','size','price','quote']).sort_values('ts_ns')
    return df


def make_bars(df: pd.DataFrame, interval='5min') -> pd.DataFrame:
    g=df.set_index('dt').resample(interval, label='left', closed='left')
    bars=pd.DataFrame({
        'open':g['price'].first(), 'high':g['price'].max(), 'low':g['price'].min(), 'close':g['price'].last(),
        'volume':g['size'].sum(), 'turnover':g['quote'].sum(), 'trades':g['price'].count(),
    }).dropna(subset=['open','high','low','close'])
    bars['cum_turnover']=bars['turnover'].cumsum()
    bars['cum_volume']=bars['volume'].cumsum()
    bars['vwap']=bars['cum_turnover']/bars['cum_volume'].replace(0, np.nan)
    return bars.reset_index()


def path_max_short(bars: pd.DataFrame):
    highs=bars['high'].to_numpy(float); lows=bars['low'].to_numpy(float)
    running=np.maximum.accumulate(highs); dd=lows/running-1
    trough=int(np.nanargmin(dd)); peak=int(np.nanargmax(highs[:trough+1]))
    return -float(dd[trough]), peak, trough


def path_runup(bars: pd.DataFrame):
    lows=bars['low'].to_numpy(float); highs=bars['high'].to_numpy(float)
    running=np.minimum.accumulate(lows); ru=highs/running-1
    peak=int(np.nanargmax(ru)); trough=int(np.nanargmin(lows[:peak+1]))
    return float(ru[peak]), trough, peak


def first_vwap_loss_after_peak(bars: pd.DataFrame, peak_idx: int):
    peak_time=bars.iloc[peak_idx]['dt']
    after=bars[bars['dt'] > peak_time]
    below=after[after['close'] < after['vwap']]
    if below.empty:
        return None
    row=below.iloc[0]
    return dict(time=row['dt'], ts_ns=int(row['dt'].value), price=float(row['close']))


def midpoint_loss_after_runup(bars: pd.DataFrame, trough_idx: int, peak_idx: int):
    low=float(bars.iloc[trough_idx]['low']); high=float(bars.iloc[peak_idx]['high'])
    midpoint=low+0.5*(high-low)
    after=bars[bars['dt'] > bars.iloc[peak_idx]['dt']]
    below=after[after['close'] < midpoint]
    return None if below.empty else below.iloc[0]['dt']


def sell_share_after(ticks: pd.DataFrame, ts_ns: int) -> float:
    ap=ticks[ticks['ts_ns'] > ts_ns]
    if ap.empty:
        return np.nan
    total=ap['quote'].sum()
    sell=ap.loc[ap['side'].str.lower()=='sell','quote'].sum()
    return float(sell/total*100) if total else np.nan


def first_barrier(prices: np.ndarray, ts_ns: np.ndarray, entry_price: float, entry_ns: int, tp: float, sl: float, max_hold_min: float | None = None):
    if prices.size == 0:
        return dict(outcome='no_data', exit_time_utc=None, exit_price=np.nan, pnl_underlying_pct=np.nan, minutes_to_exit=np.nan)
    if max_hold_min is not None:
        max_ns=entry_ns+int(max_hold_min*60*1e9)
        keep=ts_ns <= max_ns
        prices=prices[keep]; ts_ns=ts_ns[keep]
        if prices.size == 0:
            return dict(outcome='time_stop', exit_time_utc=None, exit_price=np.nan, pnl_underlying_pct=0.0, minutes_to_exit=max_hold_min)
    target=entry_price*(1-tp); stop=entry_price*(1+sl)
    hit_tp=prices <= target; hit_sl=prices >= stop; hit=hit_tp | hit_sl
    if hit.any():
        i=int(np.argmax(hit)); outcome='tp' if hit_tp[i] else 'sl'
        exit_price=target if outcome=='tp' else stop
        pnl=(entry_price-exit_price)/entry_price*100
        minutes=(ts_ns[i]-entry_ns)/1e9/60
        return dict(outcome=outcome, exit_time_utc=pd.to_datetime(ts_ns[i], unit='ns', utc=True).isoformat(), exit_price=exit_price, pnl_underlying_pct=pnl, minutes_to_exit=minutes)
    exit_price=float(prices[-1])
    pnl=(entry_price-exit_price)/entry_price*100
    minutes=(ts_ns[-1]-entry_ns)/1e9/60
    return dict(outcome='time_stop' if max_hold_min is not None else 'eod', exit_time_utc=pd.to_datetime(ts_ns[-1], unit='ns', utc=True).isoformat(), exit_price=exit_price, pnl_underlying_pct=pnl, minutes_to_exit=minutes)


def analyze_symbol_day(symbol: str, day: dt.date, cur_path: Path, prev_path: Path, cfg) -> tuple[dict | None, dict | None]:
    cur_ticks=load_ticks(cur_path)
    prev_ticks=load_ticks(prev_path)
    if cur_ticks.empty or prev_ticks.empty:
        return None, None
    cur_bars=make_bars(cur_ticks); prev_bars=make_bars(prev_ticks)
    if cur_bars.empty or prev_bars.empty:
        return None, None
    turnover=float(cur_ticks['quote'].sum())
    prev_turnover=float(prev_ticks['quote'].sum())
    turnover_ratio=turnover/prev_turnover if prev_turnover else np.nan
    prev_ret=(float(prev_ticks['price'].iloc[-1])/float(prev_ticks['price'].iloc[0])-1)*100
    prev_short, _, _ = path_max_short(prev_bars)
    prev_max_dd=-prev_short*100
    max_short, weak_peak, weak_trough = path_max_short(cur_bars)
    max_runup, run_trough, run_peak = path_runup(cur_bars)
    weak_peak_time=cur_bars.iloc[weak_peak]['dt']; pump_peak_time=cur_bars.iloc[run_peak]['dt']
    weak_peak_hour=weak_peak_time.hour + weak_peak_time.minute/60
    pump_peak_hour=pump_peak_time.hour + pump_peak_time.minute/60
    weak_entry=first_vwap_loss_after_peak(cur_bars, weak_peak)
    pump_entry=first_vwap_loss_after_peak(cur_bars, run_peak)
    midpoint_loss=midpoint_loss_after_runup(cur_bars, run_trough, run_peak)
    weak_sell=sell_share_after(cur_ticks, int(weak_peak_time.value))
    pump_sell=sell_share_after(cur_ticks, int(pump_peak_time.value))

    weak=0
    if prev_ret <= -4: weak += 2
    if prev_max_dd <= -9: weak += 2
    if turnover_ratio <= 0.8: weak += 2
    if 3 <= max_runup*100 <= 12: weak += 1
    if weak_peak_hour <= 11: weak += 1
    if weak_entry is not None: weak += 2
    if weak_sell >= 52: weak += 1

    pump=0
    if turnover_ratio >= 8: pump += 2
    if turnover_ratio >= 15: pump += 1
    if max_runup*100 >= 25: pump += 2
    if 7 <= pump_peak_hour <= 11.5: pump += 1
    if pump_entry is not None: pump += 2
    if midpoint_loss is not None: pump += 1
    if pump_sell >= 52: pump += 1

    main_candidate = turnover >= cfg.min_turnover and (weak >= cfg.weak_threshold or pump >= cfg.pump_threshold)
    mode=None; entry=None; tp=None; sl=None
    if main_candidate:
        if pump >= cfg.pump_threshold and pump >= weak:
            mode='pump'; entry=pump_entry; tp=cfg.tp_pump; sl=cfg.sl_pump
        else:
            mode='weak'; entry=weak_entry; tp=cfg.tp_weak; sl=cfg.sl_weak
    metrics={
        'date':str(day), 'symbol':symbol, 'turnover_usdt':turnover, 'prev_turnover_usdt':prev_turnover,
        'turnover_ratio_vs_prev':turnover_ratio, 'prev_day_ret_pct':prev_ret, 'prev_day_max_dd_pct':prev_max_dd,
        'max_short_move_pct':max_short*100, 'max_runup_pct':max_runup*100,
        'weak_peak_time_utc':weak_peak_time.isoformat(), 'pump_peak_time_utc':pump_peak_time.isoformat(),
        'weak_peak_hour_utc':weak_peak_hour, 'pump_peak_hour_utc':pump_peak_hour,
        'weak_vwap_loss_time_utc':None if weak_entry is None else weak_entry['time'].isoformat(),
        'pump_vwap_loss_time_utc':None if pump_entry is None else pump_entry['time'].isoformat(),
        'weak_sell_share_after_peak_pct':weak_sell, 'pump_sell_share_after_peak_pct':pump_sell,
        'weak_score':weak, 'pump_score':pump, 'candidate_score':max(weak,pump),
        'main_candidate_v5':main_candidate, 'selected_mode':mode,
    }
    trade=None
    if main_candidate and entry is not None:
        mask=cur_ticks['ts_ns'].to_numpy() > entry['ts_ns']
        prices=cur_ticks.loc[mask,'price'].to_numpy(float)
        ns=cur_ticks.loc[mask,'ts_ns'].to_numpy('int64')
        mfe=(entry['price']-np.min(prices))/entry['price']*100 if prices.size else np.nan
        mae=(np.max(prices)-entry['price'])/entry['price']*100 if prices.size else np.nan
        res=first_barrier(prices, ns, entry['price'], entry['ts_ns'], tp, sl, cfg.max_hold_min)
        trade={
            'date':str(day), 'symbol':symbol, 'mode':mode, 'entry_time_utc':entry['time'].isoformat(),
            'entry_price':entry['price'], 'tp_pct':tp*100, 'sl_pct':sl*100,
            'mfe_after_entry_pct':mfe, 'mae_after_entry_pct':mae,
            **res,
        }
    return metrics, trade


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--start', required=True)
    ap.add_argument('--end', required=True)
    ap.add_argument('--symbols', default='', help='comma-separated symbols; ignored if --full-universe')
    ap.add_argument('--symbol-file', default='')
    ap.add_argument('--full-universe', action='store_true')
    ap.add_argument('--include-majors', action='store_true')
    ap.add_argument('--max-symbols', type=int, default=0)
    ap.add_argument('--cache-dir', default='./bybit_archive_cache')
    ap.add_argument('--out-metrics', default='bybit_metrics_v5.csv')
    ap.add_argument('--out-trades', default='bybit_trades_v5.csv')
    ap.add_argument('--min-turnover', type=float, default=1_000_000)
    ap.add_argument('--weak-threshold', type=int, default=9)
    ap.add_argument('--pump-threshold', type=int, default=9)
    ap.add_argument('--tp-weak', type=float, default=0.06, help='underlying TP decimal, e.g. 0.06')
    ap.add_argument('--sl-weak', type=float, default=0.07)
    ap.add_argument('--tp-pump', type=float, default=0.08)
    ap.add_argument('--sl-pump', type=float, default=0.07)
    ap.add_argument('--max-hold-min', type=float, default=720, help='default 12h; use 1440 for EOD-like')
    ap.add_argument('--sleep', type=float, default=0.15)
    args=ap.parse_args()
    start=parse_date(args.start); end=parse_date(args.end); days=date_range(start,end)
    sess=session(); cache=Path(args.cache_dir)
    if args.full_universe:
        symbols=get_universe(sess, exclude_majors=not args.include_majors)
    elif args.symbol_file:
        symbols=[x.strip().upper() for x in Path(args.symbol_file).read_text().splitlines() if x.strip()]
    else:
        symbols=[x.strip().upper() for x in args.symbols.split(',') if x.strip()]
    if args.max_symbols and len(symbols)>args.max_symbols:
        symbols=symbols[:args.max_symbols]
    print(f"symbols={len(symbols)} days={len(days)}", file=sys.stderr)
    metrics=[]; trades=[]
    for i,sym in enumerate(symbols,1):
        for day in days:
            prev=day-dt.timedelta(days=1)
            cur_path=cache_path(cache,sym,day); prev_path=cache_path(cache,sym,prev)
            ok1=download_file(sess, archive_url(sym,day), cur_path, sleep=args.sleep)
            ok0=download_file(sess, archive_url(sym,prev), prev_path, sleep=args.sleep)
            if not (ok1 and ok0):
                continue
            try:
                m,t=analyze_symbol_day(sym, day, cur_path, prev_path, args)
                if m: metrics.append(m)
                if t: trades.append({**m, **t})
            except Exception as e:
                print(f"WARN analyze failed {sym} {day}: {e}", file=sys.stderr)
        if i % 25 == 0:
            print(f"processed {i}/{len(symbols)} metrics={len(metrics)} trades={len(trades)}", file=sys.stderr)
    dfm=pd.DataFrame(metrics)
    dft=pd.DataFrame(trades)
    if not dfm.empty:
        dfm=dfm.sort_values(['date','candidate_score','turnover_usdt'], ascending=[True,False,False])
    if not dft.empty:
        dft=dft.sort_values(['date','candidate_score','turnover_usdt'], ascending=[True,False,False])
    dfm.to_csv(args.out_metrics, index=False)
    dft.to_csv(args.out_trades, index=False)
    print(f"wrote {args.out_metrics}: {len(dfm)} rows")
    print(f"wrote {args.out_trades}: {len(dft)} candidate trades")
    if not dft.empty:
        cols=['date','symbol','mode','turnover_usdt','weak_score','pump_score','entry_time_utc','tp_pct','sl_pct','outcome','pnl_underlying_pct','minutes_to_exit','mfe_after_entry_pct','mae_after_entry_pct']
        print(dft[cols].head(50).to_string(index=False))

if __name__ == '__main__':
    main()
