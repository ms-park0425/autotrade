#!/usr/bin/env python3
"""오늘자 코스닥 NXT 종목 프리마켓 시그널 & 본장 결과 검증"""
import sys, os, io, time, requests
from decimal import Decimal
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from strategies.intraday.engine.toss_api import TossAPI

api = TossAPI()

# 코스닥 거래량 상위 50개
kosdaq_50 = [
    '247540','086520','042700','003670','035420','259960','377300',
    '352820','036570','328130','058470','357780','051910','096770',
    '293490','403870','035720','041510','145020','078340',
    '263750','091990','067160','215600','950140',
    '060310','035900','112040','031510','028300',
    '039030','253450','196170','298380','095340',
    '226330','066910','000250','323410','089030',
    '041190','099190','009520','029480','054620',
    '068760','090460','214150','002230','006730',
]

# NXT 지원 확인
print('NXT 지원 종목 확인...')
nxt_kosdaq = []
for i in range(0, len(kosdaq_50), 200):
    batch = kosdaq_50[i:i+200]
    try:
        info = api.get_stocks(batch)
        for s in info:
            detail = s.get('koreanMarketDetail')
            if detail and detail.get('nxtSupported'):
                nxt_kosdaq.append({'symbol': s['symbol'], 'name': s['name']})
    except Exception as e:
        print(f'  에러: {e}')

print(f'NXT 지원 코스닥: {len(nxt_kosdaq)}/{len(kosdaq_50)}개\n')

today = '2026-07-03'


def get_candles_before(symbol, before, count=200):
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
    next_day = (datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    before = f'{next_day}T00:00:00+09:00'
    all_c = []
    for _ in range(5):
        result = get_candles_before(symbol, before, 200)
        candles = result.get('candles', [])
        if not candles:
            break
        for c in candles:
            td = c['timestamp'][:10]
            if td == target_date:
                all_c.append(c)
            elif td < target_date:
                return sorted(all_c, key=lambda x: x['timestamp'])
        nb = result.get('nextBefore')
        if not nb:
            break
        before = nb
        time.sleep(0.3)
    return sorted(all_c, key=lambda x: x['timestamp'])


def analyze(candles):
    pm = [c for c in candles if '08:00' <= c['timestamp'][11:16] < '08:50']
    reg30 = [c for c in candles if '09:00' <= c['timestamp'][11:16] < '09:30']
    reg1h = [c for c in candles if '09:00' <= c['timestamp'][11:16] < '10:00']

    if len(pm) < 5:
        return None

    mid_idx = len(pm) // 2
    first_half = pm[:mid_idx]

    pm_open = Decimal(pm[0]['openPrice'])
    pm_mid = Decimal(first_half[-1]['closePrice'])
    pm_close = Decimal(pm[-1]['closePrice'])
    pm_high = max(Decimal(c['highPrice']) for c in pm)
    pm_low = min(Decimal(c['lowPrice']) for c in pm)

    first_chg = float((pm_mid - pm_open) / pm_open * 100) if pm_open else 0
    second_chg = float((pm_close - pm_mid) / pm_mid * 100) if pm_mid else 0
    total_chg = float((pm_close - pm_open) / pm_open * 100) if pm_open else 0

    if pm_high != pm_low:
        close_position = float((pm_close - pm_low) / (pm_high - pm_low))
    else:
        close_position = 0.5

    last_10 = pm[-10:] if len(pm) >= 10 else pm[-5:]
    last10_open = Decimal(last_10[0]['openPrice'])
    last10_close = Decimal(last_10[-1]['closePrice'])
    last10_chg = float((last10_close - last10_open) / last10_open * 100) if last10_open else 0

    if first_chg > 0.3 and second_chg > 0.3:
        pattern = 'UP_UP'
    elif first_chg > 0.3 and second_chg < -0.3:
        pattern = 'UP_DOWN'
    elif first_chg < -0.3 and second_chg > 0.3:
        pattern = 'DOWN_UP'
    elif first_chg < -0.3 and second_chg < -0.3:
        pattern = 'DOWN_DOWN'
    else:
        pattern = 'FLAT'

    r30_chg = None
    r1h_chg = None
    if reg30:
        re_open = Decimal(reg30[0]['openPrice'])
        re_close = Decimal(reg30[-1]['closePrice'])
        r30_chg = float((re_close - re_open) / re_open * 100) if re_open else 0
    if reg1h:
        r1h_open = Decimal(reg1h[0]['openPrice'])
        r1h_close = Decimal(reg1h[-1]['closePrice'])
        r1h_chg = float((r1h_close - r1h_open) / r1h_open * 100) if r1h_open else 0

    # 시그널 판정
    signals = []
    if pattern == 'UP_UP' and close_position > 0.7:
        signals.append('BUY: 계속상승+고점마감')
    if pattern == 'DOWN_UP' and close_position > 0.5:
        signals.append('BUY: 빠졌다반등')
    if close_position > 0.7 and last10_chg > 0:
        signals.append('BUY: 고점마감+마지막상승')
    if pattern == 'UP_DOWN':
        signals.append('AVOID: 올랐다꺾임')
    if close_position < 0.3:
        signals.append('AVOID: 저점마감')
    if last10_chg < -0.3:
        signals.append('AVOID: 마지막10분하락')

    return {
        'pattern': pattern,
        'first_chg': first_chg,
        'second_chg': second_chg,
        'total_chg': total_chg,
        'close_position': close_position,
        'last10_chg': last10_chg,
        'r30': r30_chg,
        'r1h': r1h_chg,
        'signals': signals,
    }


# 수집
print(f'오늘({today}) 코스닥 NXT 종목 분석 중...\n')
buy_signals = []
avoid_signals = []
neutral = []

for stock in nxt_kosdaq:
    symbol = stock['symbol']
    name = stock['name']
    try:
        candles = collect_day(symbol, today)
        r = analyze(candles)
        if not r:
            continue
        r['symbol'] = symbol
        r['name'] = name

        has_buy = any('BUY' in s for s in r['signals'])
        has_avoid = any('AVOID' in s for s in r['signals'])

        if has_buy and not has_avoid:
            buy_signals.append(r)
        elif has_avoid:
            avoid_signals.append(r)
        else:
            neutral.append(r)
    except Exception as e:
        pass
    time.sleep(0.5)

# 출력
pattern_kr = {
    'UP_UP': '계속상승',
    'UP_DOWN': '올랐다꺾임',
    'DOWN_UP': '빠졌다반등',
    'DOWN_DOWN': '계속하락',
    'FLAT': '보합',
}

print('=' * 70)
print(f'  오늘({today}) 코스닥 프리마켓 시그널 검증')
print('=' * 70)

print(f'\n  *** BUY 시그널 (매수 후보) ***')
print(f'  {"=" * 60}')
if buy_signals:
    for r in sorted(buy_signals, key=lambda x: x['close_position'], reverse=True):
        pk = pattern_kr.get(r['pattern'], r['pattern'])
        r30s = f"{r['r30']:+.2f}%" if r['r30'] is not None else '장중'
        r1hs = f"{r['r1h']:+.2f}%" if r['r1h'] is not None else '장중'
        print(f"  {r['symbol']} {r['name']:<10}")
        print(f"    PM추이: {pk} | PM등락: {r['total_chg']:+.2f}% | 고점위치: {r['close_position']:.2f} | 마감10분: {r['last10_chg']:+.2f}%")
        print(f"    시그널: {', '.join(r['signals'])}")
        print(f"    본장결과: 30분 {r30s}, 1시간 {r1hs}")
        print()
else:
    print('  없음\n')

print(f'  *** AVOID 시그널 (매수 금지) ***')
print(f'  {"=" * 60}')
if avoid_signals:
    for r in sorted(avoid_signals, key=lambda x: x['r30'] if x['r30'] is not None else 0):
        pk = pattern_kr.get(r['pattern'], r['pattern'])
        r30s = f"{r['r30']:+.2f}%" if r['r30'] is not None else '장중'
        r1hs = f"{r['r1h']:+.2f}%" if r['r1h'] is not None else '장중'
        print(f"  {r['symbol']} {r['name']:<10}")
        print(f"    PM추이: {pk} | PM등락: {r['total_chg']:+.2f}% | 고점위치: {r['close_position']:.2f} | 마감10분: {r['last10_chg']:+.2f}%")
        print(f"    시그널: {', '.join(r['signals'])}")
        print(f"    본장결과: 30분 {r30s}, 1시간 {r1hs}")
        print()

# 요약 검증
print('=' * 70)
print('  검증 요약')
print('=' * 70)

buy_r = [r for r in buy_signals if r['r30'] is not None]
avoid_r = [r for r in avoid_signals if r['r30'] is not None]

if buy_r:
    avg30 = sum(r['r30'] for r in buy_r) / len(buy_r)
    up30 = len([r for r in buy_r if r['r30'] > 0])
    print(f"\n  BUY 시그널 ({len(buy_r)}건):")
    print(f"    30분: 상승 {up30}/{len(buy_r)} ({up30/len(buy_r)*100:.0f}%), 평균 {avg30:+.2f}%")
    r1h_r = [r for r in buy_r if r['r1h'] is not None]
    if r1h_r:
        avg1h = sum(r['r1h'] for r in r1h_r) / len(r1h_r)
        up1h = len([r for r in r1h_r if r['r1h'] > 0])
        print(f"    1시간: 상승 {up1h}/{len(r1h_r)} ({up1h/len(r1h_r)*100:.0f}%), 평균 {avg1h:+.2f}%")

if avoid_r:
    avg30 = sum(r['r30'] for r in avoid_r) / len(avoid_r)
    dn30 = len([r for r in avoid_r if r['r30'] < 0])
    print(f"\n  AVOID 시그널 ({len(avoid_r)}건):")
    print(f"    30분: 하락 {dn30}/{len(avoid_r)} ({dn30/len(avoid_r)*100:.0f}%), 평균 {avg30:+.2f}%")
    r1h_r = [r for r in avoid_r if r['r1h'] is not None]
    if r1h_r:
        avg1h = sum(r['r1h'] for r in r1h_r) / len(r1h_r)
        print(f"    1시간: 평균 {avg1h:+.2f}%")

if buy_r and avoid_r:
    print(f"\n  시그널 따랐을 때 vs 반대:")
    buy_avg = sum(r['r30'] for r in buy_r) / len(buy_r)
    avoid_avg = sum(r['r30'] for r in avoid_r) / len(avoid_r)
    print(f"    BUY 매수 시 30분 수익: {buy_avg:+.2f}%")
    print(f"    AVOID 매수 시 30분 손실: {avoid_avg:+.2f}%")
    print(f"    차이: {buy_avg - avoid_avg:+.2f}%p")
