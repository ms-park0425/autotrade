#!/usr/bin/env python3
"""코스피 10개 종목 스캘핑 파라미터 최적화"""
import sys, os, io, time, requests
from datetime import datetime, timedelta

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

# 파라미터 조합
CONFIGS = [
    {'name': '기본(2%/1.5%)',        'tp': 2.0, 'sl': -1.5, 'entry': '09:30', 'cool': 5,  'candles': 2},
    {'name': '익절1.5%/손절1%',       'tp': 1.5, 'sl': -1.0, 'entry': '09:30', 'cool': 5,  'candles': 2},
    {'name': '익절2%/손절2%',         'tp': 2.0, 'sl': -2.0, 'entry': '09:30', 'cool': 5,  'candles': 2},
    {'name': '익절3%/손절1.5%',       'tp': 3.0, 'sl': -1.5, 'entry': '09:30', 'cool': 5,  'candles': 2},
    {'name': '익절2%/손절1.5%/쿨10', 'tp': 2.0, 'sl': -1.5, 'entry': '09:30', 'cool': 10, 'candles': 2},
    {'name': '3연속양봉',             'tp': 2.0, 'sl': -1.5, 'entry': '09:30', 'cool': 5,  'candles': 3},
    {'name': '10시이후진입',          'tp': 2.0, 'sl': -1.5, 'entry': '10:00', 'cool': 5,  'candles': 2},
    {'name': '익절1%/손절0.5%',       'tp': 1.0, 'sl': -0.5, 'entry': '09:30', 'cool': 3,  'candles': 2},
]


def get_candles_before(symbol, before=None, count=200):
    api._ensure_token()
    params = {'symbol': symbol, 'interval': '1m', 'count': count}
    if before:
        params['before'] = before
    resp = requests.get('https://openapi.tossinvest.com/api/v1/candles', params=params, headers=api._headers())
    resp.raise_for_status()
    return resp.json().get('result', {})


def collect_day(symbol, target_date):
    next_day = (datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    before = f'{next_day}T00:00:00+09:00'
    all_c = []
    for _ in range(5):
        result = get_candles_before(symbol, before, 200)
        candles = result.get('candles', [])
        if not candles:
            break
        for c in candles:
            if c['timestamp'][:10] == target_date:
                all_c.append(c)
            elif c['timestamp'][:10] < target_date:
                return sorted(all_c, key=lambda x: x['timestamp'])
        nb = result.get('nextBefore')
        if not nb:
            break
        before = nb
        time.sleep(0.2)
    return sorted(all_c, key=lambda x: x['timestamp'])


def simulate(candles_by_date, cfg):
    """파라미터 조합으로 시뮬레이션"""
    all_trades = []
    for date, reg in candles_by_date.items():
        if not reg:
            continue
        position = None
        last_exit_idx = -999
        n_candles = cfg['candles']

        for i in range(n_candles, len(reg)):
            c_curr = reg[i]
            t = c_curr['timestamp'][11:16]
            cl_curr = float(c_curr['closePrice'])

            if position:
                entry = position['entry_price']
                pnl = (cl_curr - entry) / entry * 100
                if pnl >= cfg['tp']:
                    all_trades.append({'pnl': pnl, 'reason': 'TP', 'hold': i - position['entry_idx']})
                    position = None
                    last_exit_idx = i
                elif pnl <= cfg['sl']:
                    all_trades.append({'pnl': pnl, 'reason': 'SL', 'hold': i - position['entry_idx']})
                    position = None
                    last_exit_idx = i
            else:
                if t < cfg['entry']:
                    continue
                if i - last_exit_idx < cfg['cool']:
                    continue

                # 연속 양봉 + 계단상승 체크
                prev_candles = reg[i-n_candles:i]
                all_bull = all(float(c['closePrice']) > float(c['openPrice']) for c in prev_candles)
                closes = [float(c['closePrice']) for c in prev_candles]
                ladder = all(closes[j] > closes[j-1] for j in range(1, len(closes)))

                if all_bull and ladder:
                    position = {'entry_price': cl_curr, 'entry_time': t, 'entry_idx': i}

        if position:
            last_price = float(reg[-1]['closePrice'])
            pnl = (last_price - position['entry_price']) / position['entry_price'] * 100
            all_trades.append({'pnl': pnl, 'reason': 'CLOSE', 'hold': len(reg) - position['entry_idx']})

    return all_trades


# 데이터 수집
dates = []
d = datetime(2026, 7, 3)
while len(dates) < 5:
    if d.weekday() < 5:
        dates.append(d.strftime('%Y-%m-%d'))
    d -= timedelta(days=1)

print(f'분석 기간: {dates[-1]} ~ {dates[0]}')
print(f'대상: {len(TARGETS)}종목 × {len(CONFIGS)}설정 = {len(TARGETS)*len(CONFIGS)}조합')
print()

# 종목별 데이터 캐시
data_cache = {}
for symbol, name in TARGETS.items():
    print(f'  [{name}] 데이터 수집 중...')
    data_cache[symbol] = {}
    for date in dates:
        candles = collect_day(symbol, date)
        reg = [c for c in candles if '09:00' <= c['timestamp'][11:16] <= '15:20']
        data_cache[symbol][date] = reg
        time.sleep(0.3)
    time.sleep(0.5)

print()
print('=' * 90)
print('  최적화 결과')
print('=' * 90)

# 종목별 최적 설정 찾기
best_per_symbol = {}

for symbol, name in TARGETS.items():
    print(f'\n  [{name} ({symbol})]')
    print(f'  {"설정":<22} {"거래":>5} {"승률":>6} {"총손익":>8} {"익절":>5} {"손절":>5} {"평균수익":>8} {"평균손실":>8}')
    print(f'  {"─"*75}')

    best_cfg = None
    best_pnl = -999

    for cfg in CONFIGS:
        trades = simulate(data_cache[symbol], cfg)
        if not trades:
            continue

        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] <= 0]
        total = sum(t['pnl'] for t in trades)
        wr = len(wins) / len(trades) * 100
        tp_cnt = len([t for t in trades if t['reason'] == 'TP'])
        sl_cnt = len([t for t in trades if t['reason'] == 'SL'])
        avg_win = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t['pnl'] for t in losses) / len(losses) if losses else 0

        mark = ''
        if total > best_pnl:
            best_pnl = total
            best_cfg = cfg
            mark = ' ◀'

        print(f'  {cfg["name"]:<22} {len(trades):>5} {wr:>5.0f}% {total:>+7.2f}% {tp_cnt:>5} {sl_cnt:>5} {avg_win:>+7.2f}% {avg_loss:>+7.2f}%{mark}')

    best_per_symbol[symbol] = {'name': name, 'cfg': best_cfg, 'pnl': best_pnl}

# 전체 요약
print()
print('=' * 90)
print('  종목별 최적 설정 요약')
print('=' * 90)
print(f'  {"종목":<12} {"최적설정":<22} {"5일총손익":>10}')
print(f'  {"─"*50}')

for symbol, result in best_per_symbol.items():
    cfg_name = result['cfg']['name'] if result['cfg'] else 'N/A'
    print(f'  {result["name"]:<12} {cfg_name:<22} {result["pnl"]:>+9.2f}%')

# 공통 최적 설정 찾기
from collections import Counter
cfg_counter = Counter(r['cfg']['name'] for r in best_per_symbol.values() if r['cfg'])
print(f'\n  가장 많은 종목에서 최적인 설정: {cfg_counter.most_common(1)[0]}')
