#!/usr/bin/env python3
"""
트레일링 스탑 백테스트

진입: 분봉 2연속 양봉 + 계단상승 (09:30 이후)
청산: 보유 중 고점 대비 X% 하락 시 청산 (트레일링 스탑)
"""
import sys, os, io, time, json, requests
from datetime import datetime, timedelta
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from strategies.intraday.engine.toss_api import TossAPI
api = TossAPI()

TARGETS = {
    '005930': '삼성전자',
    '034020': '두산에너빌리티',
    '000660': 'SK하이닉스',
    '009150': '삼성전기',
    '028260': '삼성물산',
    '066570': 'LG전자',
    '068270': '셀트리온',
    '003490': '대한항공',
    '006400': '삼성SDI',
    '005380': '현대차',
}

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'data', 'candle_cache')


def collect_day(symbol, target_date):
    cache_file = os.path.join(CACHE_DIR, f'{symbol}_{target_date}.json')
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return json.load(f)
    return []


def get_reg_candles(candles):
    return [c for c in candles if '09:00' <= c['timestamp'][11:16] <= '15:20']


def simulate_trailing(reg_list, trail_pct, hard_sl=-3.0, entry_time='09:30', cooldown=5):
    """
    트레일링 스탑 시뮬레이션
    trail_pct: 고점 대비 X% 하락 시 청산 (예: 1.0 = 고점 대비 -1%)
    hard_sl: 진입가 대비 절대 손절선 (예: -3.0 = -3%)
    """
    all_trades = []

    for reg in reg_list:
        if not reg:
            continue

        position = None
        peak_price = 0
        last_exit_idx = -999

        for i in range(2, len(reg)):
            c_prev2 = reg[i-2]
            c_prev  = reg[i-1]
            c_curr  = reg[i]
            t = c_curr['timestamp'][11:16]
            cl_curr = float(c_curr['closePrice'])

            if position:
                entry = position['entry']
                # 고점 갱신
                if cl_curr > peak_price:
                    peak_price = cl_curr

                pnl_from_entry = (cl_curr - entry) / entry * 100
                pnl_from_peak = (cl_curr - peak_price) / peak_price * 100

                # 하드 손절 (진입가 대비)
                if pnl_from_entry <= hard_sl:
                    all_trades.append({
                        'pnl': pnl_from_entry,
                        'peak_pnl': (peak_price - entry) / entry * 100,
                        'reason': 'HARD_SL',
                        'hold': i - position['idx'],
                        'entry_time': position['time'],
                        'exit_time': t,
                    })
                    position = None
                    last_exit_idx = i

                # 트레일링 스탑 (고점 대비)
                elif pnl_from_peak <= -trail_pct:
                    all_trades.append({
                        'pnl': pnl_from_entry,
                        'peak_pnl': (peak_price - entry) / entry * 100,
                        'reason': 'TRAIL',
                        'hold': i - position['idx'],
                        'entry_time': position['time'],
                        'exit_time': t,
                    })
                    position = None
                    last_exit_idx = i

            else:
                if t < entry_time:
                    continue
                if i - last_exit_idx < cooldown:
                    continue

                # 진입: 2연속 양봉 + 계단상승
                o1 = float(c_prev2['openPrice']); cl1 = float(c_prev2['closePrice'])
                o2 = float(c_prev['openPrice']);  cl2 = float(c_prev['closePrice'])

                if cl1 > o1 and cl2 > o2 and cl2 > cl1:
                    position = {'entry': cl_curr, 'idx': i, 'time': t}
                    peak_price = cl_curr

        # 미청산 → 장 마감
        if position:
            last = float(reg[-1]['closePrice'])
            pnl = (last - position['entry']) / position['entry'] * 100
            peak_pnl = (peak_price - position['entry']) / position['entry'] * 100
            all_trades.append({
                'pnl': pnl,
                'peak_pnl': peak_pnl,
                'reason': 'CLOSE',
                'hold': len(reg) - position['idx'],
                'entry_time': position['time'],
                'exit_time': '15:20',
            })

    return all_trades


# 데이터 로드
dates = []
d = datetime(2026, 7, 3)
while len(dates) < 25:
    if d.weekday() < 5:
        dates.append(d.strftime('%Y-%m-%d'))
    d -= timedelta(days=1)

print('트레일링 스탑 최적화 백테스트')
print(f'기간: {dates[-1]} ~ {dates[0]} ({len(dates)}영업일)')
print()

# 종목별 캔들 로드
data_cache = {}
for symbol in TARGETS:
    data_cache[symbol] = []
    for date in dates:
        candles = collect_day(symbol, date)
        reg = get_reg_candles(candles)
        if reg:
            data_cache[symbol].append(reg)

# 트레일링 스탑 % 조합 테스트
trail_options = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
hard_sl_options = [-2.0, -3.0, -5.0]  # 절대 손절선

print('=' * 85)
print('  종목별 트레일링 스탑 최적화')
print('  (진입: 2연속 양봉 09:30이후 / 청산: 고점 대비 X% 하락)')
print('=' * 85)

best_overall = {}

for symbol, name in TARGETS.items():
    reg_list = data_cache[symbol]
    print(f'\n  [{name}]')
    print(f'  {"트레일":>6} {"하드SL":>7} {"거래":>5} {"승률":>6} {"총손익":>8} {"평균수익":>8} {"평균손실":>8} {"평균고점":>8}')
    print(f'  {"─"*70}')

    best_pnl = -999
    best_cfg = None

    for trail in trail_options:
        for hard_sl in hard_sl_options:
            trades = simulate_trailing(reg_list, trail, hard_sl)
            if not trades:
                continue

            wins = [t for t in trades if t['pnl'] > 0]
            losses = [t for t in trades if t['pnl'] <= 0]
            total = sum(t['pnl'] for t in trades)
            wr = len(wins) / len(trades) * 100
            avg_win = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t['pnl'] for t in losses) / len(losses) if losses else 0
            avg_peak = sum(t['peak_pnl'] for t in trades) / len(trades)

            mark = ''
            if total > best_pnl:
                best_pnl = total
                best_cfg = {'trail': trail, 'hard_sl': hard_sl}
                mark = ' ◀'

            print(f'  {trail:>5.1f}% {hard_sl:>6.1f}% {len(trades):>5} {wr:>5.0f}% {total:>+7.2f}% {avg_win:>+7.2f}% {avg_loss:>+7.2f}% {avg_peak:>+7.2f}%{mark}')

    best_overall[symbol] = {'name': name, 'cfg': best_cfg, 'pnl': best_pnl}

# 종목별 최적 요약
print()
print('=' * 85)
print('  종목별 최적 트레일링 스탑 요약')
print('=' * 85)
print(f'  {"종목":<12} {"트레일":>7} {"하드SL":>7} {"5일손익":>9}')
print(f'  {"─"*40}')

for symbol, result in best_overall.items():
    cfg = result['cfg']
    if cfg:
        print(f'  {result["name"]:<12} {cfg["trail"]:>6.1f}% {cfg["hard_sl"]:>6.1f}% {result["pnl"]:>+8.2f}%')

# 고정 익절 vs 트레일링 비교 (최적 설정으로)
print()
print('=' * 85)
print('  [비교] 고정익절(2%/1.5%) vs 트레일링 스탑 — 전체 종목 합산')
print('=' * 85)

def simulate_fixed(reg_list, tp=2.0, sl=-1.5, entry_time='09:30', cool=5):
    all_trades = []
    for reg in reg_list:
        if not reg:
            continue
        position = None
        last_exit_idx = -999
        for i in range(2, len(reg)):
            c_prev2 = reg[i-2]; c_prev = reg[i-1]; c_curr = reg[i]
            t = c_curr['timestamp'][11:16]
            cl_curr = float(c_curr['closePrice'])
            if position:
                pnl = (cl_curr - position['entry']) / position['entry'] * 100
                if pnl >= tp:
                    all_trades.append({'pnl': pnl, 'reason': 'TP'})
                    position = None; last_exit_idx = i
                elif pnl <= sl:
                    all_trades.append({'pnl': pnl, 'reason': 'SL'})
                    position = None; last_exit_idx = i
            else:
                if t < entry_time or i - last_exit_idx < cool:
                    continue
                o1 = float(c_prev2['openPrice']); cl1 = float(c_prev2['closePrice'])
                o2 = float(c_prev['openPrice']);  cl2 = float(c_prev['closePrice'])
                if cl1 > o1 and cl2 > o2 and cl2 > cl1:
                    position = {'entry': cl_curr}
        if position:
            last = float(reg[-1]['closePrice'])
            pnl = (last - position['entry']) / position['entry'] * 100
            all_trades.append({'pnl': pnl, 'reason': 'CLOSE'})
    return sum(t['pnl'] for t in all_trades)


total_fixed = 0
total_trail = 0

print(f'  {"종목":<12} {"고정익절":>9} {"트레일링":>9} {"차이":>7}')
print(f'  {"─"*45}')

for symbol, name in TARGETS.items():
    reg_list = data_cache[symbol]

    fixed_pnl = simulate_fixed(reg_list)

    best = best_overall[symbol]['cfg']
    if best:
        trail_trades = simulate_trailing(reg_list, best['trail'], best['hard_sl'])
        trail_pnl = sum(t['pnl'] for t in trail_trades)
    else:
        trail_pnl = 0

    diff = trail_pnl - fixed_pnl
    total_fixed += fixed_pnl
    total_trail += trail_pnl
    print(f'  {name:<12} {fixed_pnl:>+8.2f}% {trail_pnl:>+8.2f}% {diff:>+6.2f}%')

print(f'  {"─"*45}')
print(f'  {"합산":<12} {total_fixed:>+8.2f}% {total_trail:>+8.2f}% {total_trail-total_fixed:>+6.2f}%')
