#!/usr/bin/env python3
"""
고정 파라미터 그리드 서치 — 트레일링 스탑
전체 기간 · 전체 종목에 모든 (trail_pct, hard_sl) 조합 적용
캔들 캐시 재사용
"""
import sys, os, io, json
from datetime import datetime, timedelta
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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

TRAIL_OPTIONS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
ENTRY_TIME = '09:30'
COOLDOWN   = 5
COMMISSION = 0.3 * 2  # 왕복 0.6%

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'data', 'candle_cache')


def get_week_dates(year=2026):
    weeks = []
    d = datetime(year, 1, 5)
    today = datetime(2026, 7, 3)
    while d <= today:
        week = []
        for i in range(5):
            day = d + timedelta(days=i)
            if day <= today:
                week.append(day.strftime('%Y-%m-%d'))
        if week:
            weeks.append(week)
        d += timedelta(weeks=1)
    return weeks


def load_cache(symbol, date):
    f = os.path.join(CACHE_DIR, f'{symbol}_{date}.json')
    if not os.path.exists(f):
        return []
    with open(f) as fp:
        raw = json.load(fp)
    return [c for c in raw if '09:00' <= c['timestamp'][11:16] <= '15:20']


def simulate(reg_list, trail_pct):
    trades = []
    for reg in reg_list:
        if not reg:
            continue
        position = None
        peak_price = 0.0
        last_exit_idx = -999

        for i in range(2, len(reg)):
            c_p2  = reg[i - 2]
            c_p1  = reg[i - 1]
            c_cur = reg[i]
            t   = c_cur['timestamp'][11:16]
            hi  = float(c_cur['highPrice'])
            lo  = float(c_cur['lowPrice'])
            op  = float(c_cur['openPrice'])

            if position:
                entry = position['entry']
                if hi > peak_price:
                    peak_price = hi

                trail_price = peak_price * (1 - trail_pct / 100)

                if lo <= trail_price:
                    trades.append((trail_price - entry) / entry * 100 - COMMISSION)
                    position = None
                    last_exit_idx = i
            else:
                if t < ENTRY_TIME:
                    continue
                if i - last_exit_idx < COOLDOWN:
                    continue
                o1  = float(c_p2['openPrice']); cl1 = float(c_p2['closePrice'])
                o2  = float(c_p1['openPrice']); cl2 = float(c_p1['closePrice'])
                if cl1 > o1 and cl2 > o2 and cl2 > cl1:
                    position = {'entry': op}
                    peak_price = op

        if position:
            last = float(reg[-1]['closePrice'])
            trades.append((last - position['entry']) / position['entry'] * 100 - COMMISSION)

    return trades


# ── 데이터 로드 ──────────────────────────────
weeks    = get_week_dates()
all_dates = [d for w in weeks for d in w]

print('캔들 캐시 로딩 ...')
all_reg = {}   # all_reg[symbol] = [reg_candles_per_day, ...]
for symbol in TARGETS:
    all_reg[symbol] = [load_cache(symbol, d) for d in all_dates]
print(f'완료  ({len(TARGETS)}종목 × {len(all_dates)}일)\n')

# ── 그리드 서치 ──────────────────────────────
print('그리드 서치 실행 중 ...')
grid = {}

for trail in TRAIL_OPTIONS:
    sym_pnls = {}
    for symbol in TARGETS:
        t = simulate(all_reg[symbol], trail)
        sym_pnls[symbol] = {
            'total':  sum(t),
            'trades': len(t),
            'wr':     (sum(1 for x in t if x > 0) / len(t) * 100) if t else 0.0,
        }
    port_avg = sum(v['total'] for v in sym_pnls.values()) / len(TARGETS)
    grid[trail] = {
        'port_avg':     port_avg,
        'total_trades': sum(v['trades'] for v in sym_pnls.values()),
        'avg_wr':       sum(v['wr'] for v in sym_pnls.values()) / len(TARGETS),
        'symbols':      sym_pnls,
    }

print('완료!\n')

# ── 출력 — trail별 성과표 ────────────────────
best_trail = max(TRAIL_OPTIONS, key=lambda t: grid[t]['port_avg'])
best_pnl   = grid[best_trail]['port_avg']

print('=' * 65)
print('  trail% 별 성과  (10종목 평균, 전 기간, 수수료 0.6% 반영)')
print('=' * 65)
print(f'  {"trail%":>8}  {"포트평균":>9}  {"총거래":>7}  {"평균승률":>7}')
print('  ' + '─' * 45)
for trail in TRAIL_OPTIONS:
    d = grid[trail]
    marker = ' ◀ 최적' if trail == best_trail else ''
    print(f'  {trail:>7.1f}%  {d["port_avg"]:>+8.2f}%  {d["total_trades"]:>6}건  {d["avg_wr"]:>5.0f}%{marker}')

# ── 최적 trail 종목별 상세 ───────────────────
print()
print('=' * 55)
print(f'  최적 trail={best_trail:.1f}%  → 포트 평균 {best_pnl:+.2f}%')
print('=' * 55)
best_data = grid[best_trail]
print(f'  {"종목":<14} {"누적손익":>9} {"거래수":>7} {"승률":>7}')
print('  ' + '─' * 42)
for symbol, name in TARGETS.items():
    d = best_data['symbols'][symbol]
    print(f'  {name:<14} {d["total"]:>+8.2f}% {d["trades"]:>6}건  {d["wr"]:>5.0f}%')
print(f'\n  포트 평균: {best_data["port_avg"]:+.2f}%  |  총거래: {best_data["total_trades"]}건  |  평균승률: {best_data["avg_wr"]:.0f}%')

# ── 저장 ────────────────────────────────────
out = {
    'best_trail': best_trail,
    'best_port_avg': best_pnl,
    'grid': {
        f'trail={t}': {
            'port_avg':     grid[t]['port_avg'],
            'total_trades': grid[t]['total_trades'],
            'avg_wr':       grid[t]['avg_wr'],
        }
        for t in TRAIL_OPTIONS
    }
}
out_path = os.path.join(os.path.dirname(__file__), 'data', 'grid_search_result.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f'  결과 저장: {out_path}')
print('=' * 72)
