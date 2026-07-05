#!/usr/bin/env python3
"""
Walk-Forward 롤링 백테스트 — 트레일링 스탑

매주, 종목별로:
  1. 전주 데이터 → (trail_pct, hard_sl) 최적 파라미터 탐색
  2. 당주 데이터에 그 파라미터 적용
  3. 반복

파라미터 탐색 공간:
  trail_pct  : 고점 대비 X% 하락 시 청산 (0.5 ~ 3.0)
  hard_sl    : 진입가 대비 절대 손절 (-0.5 ~ -5.0)

기간: 2026-01-05 ~ 현재 (2026-07-03)
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

# 탐색 공간
TRAIL_OPTIONS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
ENTRY_TIME = '09:30'
COOLDOWN   = 5   # 봉 수 기준 (1분봉 5개 = 5분)

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'data', 'candle_cache')
COMMISSION = 0.3 * 2  # 왕복 0.6%


# ─────────────────────────────────────────────
# 데이터 수집
# ─────────────────────────────────────────────

def get_candles_before(symbol, before=None, count=200):
    api._ensure_token()
    params = {'symbol': symbol, 'interval': '1m', 'count': count}
    if before:
        params['before'] = before
    resp = requests.get(
        'https://openapi.tossinvest.com/api/v1/candles',
        params=params, headers=api._headers()
    )
    resp.raise_for_status()
    return resp.json().get('result', {})


def collect_day(symbol, target_date):
    """하루치 1분봉 (캐시 우선)"""
    cache_file = os.path.join(CACHE_DIR, f'{symbol}_{target_date}.json')
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return json.load(f)

    next_day = (datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    before = f'{next_day}T00:00:00+09:00'
    all_c = []
    for _ in range(5):
        try:
            result = get_candles_before(symbol, before, 200)
            candles = result.get('candles', [])
            if not candles:
                break
            for c in candles:
                if c['timestamp'][:10] == target_date:
                    all_c.append(c)
                elif c['timestamp'][:10] < target_date:
                    data = sorted(all_c, key=lambda x: x['timestamp'])
                    with open(cache_file, 'w') as f:
                        json.dump(data, f)
                    return data
            nb = result.get('nextBefore')
            if not nb:
                break
            before = nb
            time.sleep(0.2)
        except Exception:
            time.sleep(1)
            break

    data = sorted(all_c, key=lambda x: x['timestamp'])
    if data:
        with open(cache_file, 'w') as f:
            json.dump(data, f)
    return data


def get_reg_candles(candles):
    return [c for c in candles if '09:00' <= c['timestamp'][11:16] <= '15:20']


# ─────────────────────────────────────────────
# 시뮬레이션 (트레일링 스탑)
# ─────────────────────────────────────────────

def simulate_trailing(reg_list, trail_pct):
    """
    trail_pct : 고점(high 기준) 대비 X% 하락 시 청산
    - 진입 직후 peak = entry(open)이므로 바로 떨어지면 진입가 대비 trail_pct% 손절
    - 올라가면 peak가 끌려 올라가고, 고점 대비 trail_pct% 하락 시 청산
    → hard_sl 별도 불필요, trail 하나로 익절·손절 모두 커버
    """
    all_trades = []

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
            t     = c_cur['timestamp'][11:16]
            hi    = float(c_cur['highPrice'])
            lo    = float(c_cur['lowPrice'])
            op    = float(c_cur['openPrice'])

            if position:
                entry = position['entry']

                if hi > peak_price:
                    peak_price = hi

                trail_price = peak_price * (1 - trail_pct / 100)

                if lo <= trail_price:
                    pnl = (trail_price - entry) / entry * 100 - COMMISSION
                    all_trades.append({
                        'pnl': pnl,
                        'peak_pnl': (peak_price - entry) / entry * 100,
                        'reason': 'TRAIL',
                    })
                    position = None
                    last_exit_idx = i
            else:
                if t < ENTRY_TIME:
                    continue
                if i - last_exit_idx < COOLDOWN:
                    continue
                o1  = float(c_p2['openPrice']);  cl1 = float(c_p2['closePrice'])
                o2  = float(c_p1['openPrice']);  cl2 = float(c_p1['closePrice'])
                if cl1 > o1 and cl2 > o2 and cl2 > cl1:
                    position = {'entry': op, 'idx': i}
                    peak_price = op

        if position:
            last = float(reg[-1]['closePrice'])
            pnl  = (last - position['entry']) / position['entry'] * 100 - COMMISSION
            all_trades.append({
                'pnl': pnl,
                'peak_pnl': (peak_price - position['entry']) / position['entry'] * 100,
                'reason': 'CLOSE',
            })

    return all_trades


def score_trades(trades):
    """최적화 스코어: 총손익 (거래 0건이면 -9999)"""
    if not trades:
        return -9999.0
    return sum(t['pnl'] for t in trades)


def best_params(reg_list):
    """전주 데이터로 최적 trail_pct 탐색"""
    best_trail  = 2.0
    best_score  = -9999.0

    for trail in TRAIL_OPTIONS:
        trades = simulate_trailing(reg_list, trail)
        sc = score_trades(trades)
        if sc > best_score:
            best_score  = sc
            best_trail  = trail

    return best_trail


def summarize(trades):
    if not trades:
        return {'total': 0.0, 'trades': 0, 'wr': 0.0, 'trail': 0, 'close': 0}
    wins = [t for t in trades if t['pnl'] > 0]
    return {
        'total':  sum(t['pnl'] for t in trades),
        'trades': len(trades),
        'wr':     len(wins) / len(trades) * 100,
        'trail':  sum(1 for t in trades if t['reason'] == 'TRAIL'),
        'close':  sum(1 for t in trades if t['reason'] == 'CLOSE'),
    }


# ─────────────────────────────────────────────
# 주차 생성
# ─────────────────────────────────────────────

def get_week_dates(year=2026):
    weeks = []
    d = datetime(year, 1, 5)   # 2026년 첫 월요일
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


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

weeks = get_week_dates()
all_dates = [d for w in weeks for d in w]

print('=' * 80)
print('  Walk-Forward 롤링 백테스트 — 트레일링 스탑')
print('  전주 종목별 최적 (trail%, hard_sl%) → 당주 적용')
print('=' * 80)
print(f'  기간: {weeks[0][0]} ~ {weeks[-1][-1]}  ({len(weeks)}주)')
print(f'  종목: {len(TARGETS)}개')
print(f'  탐색: trail {TRAIL_OPTIONS}')
print()

# ── 1. 데이터 수집 ──────────────────────────
print('[1/3] 캔들 데이터 수집 중 ...')
total_calls = len(TARGETS) * len(all_dates)
done = 0
for symbol in TARGETS:
    for date in all_dates:
        cache_file = os.path.join(CACHE_DIR, f'{symbol}_{date}.json')
        if not os.path.exists(cache_file):
            collect_day(symbol, date)
            time.sleep(0.4)
        done += 1
        if done % 50 == 0:
            print(f'    {done}/{total_calls} 완료...')
print(f'    완료!\n')

# ── 2. 전체 캔들 메모리에 로드 ───────────────
print('[2/3] 데이터 로딩 ...')
all_data = {}    # all_data[symbol][date] = reg_candles (list)
for symbol in TARGETS:
    all_data[symbol] = {}
    for date in all_dates:
        raw = collect_day(symbol, date)
        reg = get_reg_candles(raw)
        all_data[symbol][date] = reg
print(f'    완료!\n')

# ── 3. 롤링 백테스트 ─────────────────────────
print('[3/3] Walk-Forward 시뮬레이션 ...')

# 결과 저장
rolling_results = {}   # [symbol][week_idx] = {...}

for symbol, name in TARGETS.items():
    rolling_results[symbol] = []

    for week_idx in range(1, len(weeks)):
        prev_week = weeks[week_idx - 1]
        curr_week = weeks[week_idx]

        # 전주 캔들 목록
        prev_reg_list = [all_data[symbol][d] for d in prev_week if all_data[symbol].get(d)]
        prev_reg_list = [r for r in prev_reg_list if r]

        # 당주 캔들 목록
        curr_reg_list = [all_data[symbol][d] for d in curr_week if all_data[symbol].get(d)]
        curr_reg_list = [r for r in curr_reg_list if r]

        if not prev_reg_list or not curr_reg_list:
            continue

        # 전주로 최적 trail 탐색
        opt_trail = best_params(prev_reg_list)

        # 당주 시뮬
        trades = simulate_trailing(curr_reg_list, opt_trail)
        s = summarize(trades)

        rolling_results[symbol].append({
            'week':      curr_week[0],
            'opt_trail': opt_trail,
            **s,
        })

print('    완료!\n')

# ─────────────────────────────────────────────
# 출력 — 종목별 주차 상세
# ─────────────────────────────────────────────
print('=' * 95)
print('  종목별 Walk-Forward 결과  (전주 최적 파라미터 → 당주 적용)')
print('=' * 95)

for symbol, name in TARGETS.items():
    results = rolling_results[symbol]
    if not results:
        continue

    total_pnl    = sum(r['total'] for r in results)
    total_trades = sum(r['trades'] for r in results)
    pos_weeks    = sum(1 for r in results if r['total'] > 0)

    print(f'\n  [{name}]  누적손익 {total_pnl:+.2f}%  |  {total_trades}건  |  수익주 {pos_weeks}/{len(results)}')
    print(f'  {"주":<12} {"trail":>6} {"거래":>5} {"승률":>6} {"주손익":>8} {"trail청산":>8}')
    print(f'  {"─"*60}')
    for r in results:
        print(f'  {r["week"]:<12} {r["opt_trail"]:>5.1f}% '
              f'{r["trades"]:>5} {r["wr"]:>5.0f}% {r["total"]:>+7.2f}% '
              f'{r["trail"]:>6}건')

# ─────────────────────────────────────────────
# 출력 — 포트폴리오 주차별 합산
# ─────────────────────────────────────────────
print()
print('=' * 80)
print('  포트폴리오 주차별 합산 (10종목 평균)')
print('=' * 80)

portfolio_by_week = defaultdict(list)
for symbol in TARGETS:
    for r in rolling_results[symbol]:
        portfolio_by_week[r['week']].append(r['total'])

cum = 0.0
print(f'  {"주":<12} {"평균손익":>9} {"누적손익":>9} {"참여종목":>8}')
print(f'  {"─"*50}')
for week in sorted(portfolio_by_week.keys()):
    pnls = portfolio_by_week[week]
    avg  = sum(pnls) / len(pnls)
    cum += avg
    print(f'  {week:<12} {avg:>+8.2f}% {cum:>+8.2f}%  {len(pnls)}종목')

# ─────────────────────────────────────────────
# 출력 — 종목별 최종 요약
# ─────────────────────────────────────────────
print()
print('=' * 80)
print('  종목별 최종 요약')
print('=' * 80)
print(f'  {"종목":<12} {"누적손익":>9} {"총거래":>7} {"평균승률":>8} {"수익주/전체주"}')
print(f'  {"─"*60}')

for symbol, name in TARGETS.items():
    results = rolling_results[symbol]
    if not results:
        continue
    total_pnl = sum(r['total'] for r in results)
    total_tr  = sum(r['trades'] for r in results)
    avg_wr    = sum(r['wr'] for r in results if r['trades'] > 0) / max(1, sum(1 for r in results if r['trades'] > 0))
    pos_weeks = sum(1 for r in results if r['total'] > 0)
    print(f'  {name:<12} {total_pnl:>+8.2f}% {total_tr:>7}건  {avg_wr:>6.0f}%  {pos_weeks}/{len(results)}주')

# 포트폴리오 최종
port_total = sum(sum(r['total'] for r in rolling_results[s]) / max(1, len(rolling_results[s]))
                 for s in TARGETS)
print(f'\n  포트폴리오 (종목 평균 합산): {port_total:+.2f}%')
print(f'  분석 주수: {len(portfolio_by_week)}주')
pos_port_weeks = sum(1 for pnls in portfolio_by_week.values() if sum(pnls) / len(pnls) > 0)
print(f'  수익 주차: {pos_port_weeks}/{len(portfolio_by_week)}주')

# ─────────────────────────────────────────────
# 파라미터 선택 빈도 분석
# ─────────────────────────────────────────────
print()
print('=' * 80)
print('  최적 파라미터 선택 빈도 (전 종목 합산)')
print('=' * 80)

trail_freq = defaultdict(int)

for symbol in TARGETS:
    for r in rolling_results[symbol]:
        trail_freq[r['opt_trail']] += 1

print('  트레일링 %  선택 빈도:')
for k in sorted(trail_freq):
    bar = '█' * trail_freq[k]
    print(f'    {k:>4.1f}%  {trail_freq[k]:>4}회  {bar}')

# ─────────────────────────────────────────────
# 결과 저장
# ─────────────────────────────────────────────
out_path = os.path.join(os.path.dirname(__file__), 'data', 'rolling_trailing_result.json')
output = {
    'period': f'{weeks[0][0]} ~ {weeks[-1][-1]}',
    'weeks': len(portfolio_by_week),
    'portfolio_cum_pnl': port_total,
    'weekly_portfolio': {
        w: {'avg': sum(pnls)/len(pnls), 'symbols': len(pnls)}
        for w, pnls in sorted(portfolio_by_week.items())
    },
    'symbol_detail': {
        symbol: rolling_results[symbol]
        for symbol in TARGETS
    },
}
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'\n  결과 저장: {out_path}')
print('=' * 80)
