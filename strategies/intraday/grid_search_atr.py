#!/usr/bin/env python3
"""
ATR 기반 비대칭 trailing stop 그리드 서치

진입 직후:  hard stop = entry - sl_mult × ATR(10)
수익 발생:  +activate_mult × ATR 도달 시 trail 발동
trail 중:  고점 - trail_mult × ATR(10) 이하로 low 내려오면 청산

캔들 캐시 재사용 (네트워크 호출 없음)
수수료: 0.6% 왕복
"""
import sys, os, io, json, glob
from datetime import datetime, timedelta

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

# 탐색 공간
SL_MULTS       = [0.5, 1.0, 1.5, 2.0]          # 초기 손절 = entry - N×ATR
ACTIVATE_MULTS = [0.0, 0.5, 1.0, 1.5]           # trail 발동 조건 (0 = 즉시 발동)
TRAIL_MULTS    = [1.0, 1.5, 2.0, 3.0]           # trail 폭 = 고점 - N×ATR

ATR_PERIOD = 10
ENTRY_TIME = '09:30'
COOLDOWN   = 5
COMMISSION = 0.6   # 왕복 0.6%

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'data', 'candle_cache')


def get_week_dates():
    weeks = []
    d = datetime(2026, 1, 5)
    today = datetime(2026, 7, 3)
    while d <= today:
        week = [
            (d + timedelta(days=i)).strftime('%Y-%m-%d')
            for i in range(5)
            if (d + timedelta(days=i)) <= today
        ]
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


def calc_atr(reg, period=ATR_PERIOD):
    """각 봉 인덱스의 ATR(period) 반환"""
    trs = [0.0]
    for i in range(1, len(reg)):
        hi = float(reg[i]['highPrice'])
        lo = float(reg[i]['lowPrice'])
        pc = float(reg[i-1]['closePrice'])
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))

    atrs = []
    for i in range(len(reg)):
        start = max(0, i - period + 1)
        window = trs[start:i+1]
        atrs.append(sum(window) / len(window) if window else 0.0)
    return atrs


def simulate(reg_list, sl_mult, activate_mult, trail_mult):
    trades = []

    for reg in reg_list:
        if len(reg) < ATR_PERIOD + 3:
            continue

        atrs = calc_atr(reg)
        position = None
        last_exit_idx = -999

        for i in range(2, len(reg)):
            c_p2  = reg[i - 2]
            c_p1  = reg[i - 1]
            c_cur = reg[i]
            t   = c_cur['timestamp'][11:16]
            hi  = float(c_cur['highPrice'])
            lo  = float(c_cur['lowPrice'])
            op  = float(c_cur['openPrice'])
            atr = atrs[i]

            if atr <= 0:
                continue

            if position:
                entry      = position['entry']
                entry_atr  = position['entry_atr']
                sl_price   = entry - sl_mult * entry_atr

                # 고점 갱신
                if hi > position['peak']:
                    position['peak'] = hi

                # trail 발동 여부 체크
                if not position['trail_on']:
                    if activate_mult == 0.0 or position['peak'] >= entry + activate_mult * entry_atr:
                        position['trail_on'] = True

                if position['trail_on']:
                    trail_price = position['peak'] - trail_mult * atr
                    # trail이 sl보다 위에 있으면 trail 우선
                    exit_price = max(trail_price, sl_price)
                    if lo <= exit_price:
                        pnl = (exit_price - entry) / entry * 100 - COMMISSION
                        trades.append(pnl)
                        position = None
                        last_exit_idx = i
                else:
                    # trail 미발동 → hard stop만
                    if lo <= sl_price:
                        pnl = (sl_price - entry) / entry * 100 - COMMISSION
                        trades.append(pnl)
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
                    position = {
                        'entry':     op,
                        'entry_atr': atrs[i],
                        'peak':      op,
                        'trail_on':  activate_mult == 0.0,
                    }
                    last_exit_idx = -999  # 진입 후 cooldown 리셋 안 함

        if position:
            last = float(reg[-1]['closePrice'])
            pnl  = (last - position['entry']) / position['entry'] * 100 - COMMISSION
            trades.append(pnl)

    return trades


# ── 데이터 로드 ──────────────────────────────
weeks     = get_week_dates()
all_dates = [d for w in weeks for d in w]

print('캔들 캐시 로딩 ...')
all_reg = {}
for symbol in TARGETS:
    all_reg[symbol] = [load_cache(symbol, d) for d in all_dates]
print(f'완료  ({len(TARGETS)}종목 × {len(all_dates)}일)\n')

# ── 그리드 서치 ──────────────────────────────
total = len(SL_MULTS) * len(ACTIVATE_MULTS) * len(TRAIL_MULTS)
print(f'그리드 서치 실행 중 ... ({total}가지 조합 × {len(TARGETS)}종목)')

results = []

for sl in SL_MULTS:
    for act in ACTIVATE_MULTS:
        for tr in TRAIL_MULTS:
            sym_data = {}
            for symbol in TARGETS:
                t = simulate(all_reg[symbol], sl, act, tr)
                sym_data[symbol] = {
                    'total':  sum(t),
                    'trades': len(t),
                    'wr':     (sum(1 for x in t if x > 0) / len(t) * 100) if t else 0.0,
                }
            port_avg = sum(v['total'] for v in sym_data.values()) / len(TARGETS)
            results.append({
                'sl': sl, 'act': act, 'tr': tr,
                'port_avg':     port_avg,
                'total_trades': sum(v['trades'] for v in sym_data.values()),
                'avg_wr':       sum(v['wr'] for v in sym_data.values()) / len(TARGETS),
                'symbols':      sym_data,
            })

results.sort(key=lambda x: -x['port_avg'])
print('완료!\n')

# ── 상위 결과 출력 ───────────────────────────
print('=' * 75)
print('  ATR 기반 비대칭 trailing stop 그리드 서치 결과')
print('  sl_mult: 초기손절  |  act_mult: trail 발동 조건  |  trail_mult: trail 폭')
print('  수수료 0.6% 반영, 전 기간(2026-01~07) 10종목 평균')
print('=' * 75)
print(f'  {"순위":>4}  {"sl×ATR":>7}  {"act×ATR":>8}  {"trail×ATR":>10}  {"포트평균":>9}  {"총거래":>7}  {"평균승률":>7}')
print('  ' + '─' * 62)

for rank, r in enumerate(results[:20], 1):
    print(f'  {rank:>4}  {r["sl"]:>6.1f}x  {r["act"]:>7.1f}x  {r["tr"]:>9.1f}x  '
          f'{r["port_avg"]:>+8.2f}%  {r["total_trades"]:>6}건  {r["avg_wr"]:>5.0f}%')

# ── 최적 조합 종목별 상세 ────────────────────
best = results[0]
print()
print('=' * 55)
print(f'  최적: sl={best["sl"]}x  act={best["act"]}x  trail={best["tr"]}x')
print(f'  → 포트 평균 {best["port_avg"]:+.2f}%  ({best["total_trades"]}건, 승률 {best["avg_wr"]:.0f}%)')
print('=' * 55)
print(f'  {"종목":<14} {"누적손익":>9} {"거래수":>7} {"승률":>7}')
print('  ' + '─' * 42)
for symbol, name in TARGETS.items():
    d = best['symbols'][symbol]
    print(f'  {name:<14} {d["total"]:>+8.2f}% {d["trades"]:>6}건  {d["wr"]:>5.0f}%')

# ── 하위 5개 ─────────────────────────────────
print()
print('  최하위 5 조합:')
for r in results[-5:]:
    print(f'    sl={r["sl"]}x  act={r["act"]}x  trail={r["tr"]}x  → {r["port_avg"]:+.2f}%  ({r["total_trades"]}건)')

# ── 저장 ─────────────────────────────────────
out_path = os.path.join(os.path.dirname(__file__), 'data', 'grid_atr_result.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump([{k: v for k, v in r.items() if k != 'symbols'} for r in results[:20]], f, ensure_ascii=False, indent=2)
print(f'\n  결과 저장: {out_path}')
print('=' * 75)
