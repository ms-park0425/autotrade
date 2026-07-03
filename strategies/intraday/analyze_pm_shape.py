#!/usr/bin/env python3
"""프리마켓 추이 패턴(모양) 분석 - 전반/후반/마지막10분 추세별 본장 결과"""
import sys, os, io, time, json, requests
from decimal import Decimal
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from strategies.intraday.engine.toss_api import TossAPI

api = TossAPI()

kospi = ['005930','000660','005380','068270','000270','009150','028260',
         '012330','066570','034020','010130','006400','011200','055550']
kosdaq = ['247540','086520','042700','003670','035420','259960','377300',
          '352820','036570','328130','058470','357780','051910','096770']

# NXT 지원 종목만
all_sym = kospi + kosdaq
stocks_info = api.get_stocks(all_sym)
nxt_symbols = [s['symbol'] for s in stocks_info if s.get('koreanMarketDetail',{}).get('nxtSupported')]
print(f"NXT 지원: {len(nxt_symbols)}/{len(all_sym)}개")

# 최근 5영업일
dates = []
d = datetime(2026, 7, 2)
while len(dates) < 5:
    if d.weekday() < 5:
        dates.append(d.strftime('%Y-%m-%d'))
    d -= timedelta(days=1)
print(f"분석 기간: {dates[-1]} ~ {dates[0]}")


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


def analyze_pm_shape(candles):
    pm = [c for c in candles if '08:00' <= c['timestamp'][11:16] < '08:50']
    reg30 = [c for c in candles if '09:00' <= c['timestamp'][11:16] < '09:30']
    reg1h = [c for c in candles if '09:00' <= c['timestamp'][11:16] < '10:00']

    if len(pm) < 5 or not reg30:
        return None

    mid_idx = len(pm) // 2
    first_half = pm[:mid_idx]
    second_half = pm[mid_idx:]

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

    # 패턴 분류
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

    re_open = Decimal(reg30[0]['openPrice'])
    re_close = Decimal(reg30[-1]['closePrice'])
    r30_chg = float((re_close - re_open) / re_open * 100) if re_open else 0

    if reg1h:
        r1h_open = Decimal(reg1h[0]['openPrice'])
        r1h_close = Decimal(reg1h[-1]['closePrice'])
        r1h_chg = float((r1h_close - r1h_open) / r1h_open * 100) if r1h_open else 0
    else:
        r1h_chg = r30_chg

    return {
        'pattern': pattern,
        'first_chg': first_chg,
        'second_chg': second_chg,
        'total_chg': total_chg,
        'close_position': close_position,
        'last10_chg': last10_chg,
        'r30': r30_chg,
        'r1h': r1h_chg,
    }


# 수집
results = []
for symbol in nxt_symbols:
    market = 'KOSPI' if symbol in kospi else 'KOSDAQ'
    for date in dates:
        try:
            candles = collect_day(symbol, date)
            r = analyze_pm_shape(candles)
            if r:
                r['symbol'] = symbol
                r['market'] = market
                r['date'] = date
                results.append(r)
        except Exception as e:
            pass
        time.sleep(0.5)
    print(f"  {symbol} done ({len([r for r in results if r['symbol']==symbol])}건)")

print(f"\n총 {len(results)}건 분석")

# ═══════════════════════════════════════════
# 결과 출력
# ═══════════════════════════════════════════
print("\n" + "=" * 70)
print("  [1] 프리마켓 추이 패턴별 본장 결과")
print("=" * 70)

patterns_desc = {
    'UP_UP': '전반 상승 + 후반 상승 (계속 올라감)',
    'UP_DOWN': '전반 상승 + 후반 하락 (올랐다 꺾임)',
    'DOWN_UP': '전반 하락 + 후반 반등 (빠졌다 반등)',
    'DOWN_DOWN': '전반 하락 + 후반 하락 (계속 내려감)',
    'FLAT': '보합 (큰 변화 없음)',
}

for p, desc in patterns_desc.items():
    subset = [r for r in results if r['pattern'] == p]
    if not subset:
        continue
    up30 = len([r for r in subset if r['r30'] > 0])
    up1h = len([r for r in subset if r['r1h'] > 0])
    avg30 = sum(r['r30'] for r in subset) / len(subset)
    avg1h = sum(r['r1h'] for r in subset) / len(subset)
    print(f"\n  {desc} ({len(subset)}건)")
    print(f"    본장 30분 상승: {up30}/{len(subset)} ({up30/len(subset)*100:.0f}%) 평균 {avg30:+.2f}%")
    print(f"    본장 1시간 상승: {up1h}/{len(subset)} ({up1h/len(subset)*100:.0f}%) 평균 {avg1h:+.2f}%")

# 코스피/코스닥 분리
for mkt in ['KOSPI', 'KOSDAQ']:
    mdata = [r for r in results if r['market'] == mkt]
    if not mdata:
        continue
    print(f"\n  {'━' * 60}")
    print(f"  [{mkt}] ({len(mdata)}건)")
    print(f"  {'━' * 60}")
    for p, desc in patterns_desc.items():
        subset = [r for r in mdata if r['pattern'] == p]
        if not subset:
            continue
        up30 = len([r for r in subset if r['r30'] > 0])
        avg30 = sum(r['r30'] for r in subset) / len(subset)
        avg1h = sum(r['r1h'] for r in subset) / len(subset)
        print(f"    {desc}")
        print(f"      ({len(subset)}건) 30분상승 {up30}/{len(subset)}({up30/len(subset)*100:.0f}%) 평균30분 {avg30:+.2f}% 1시간 {avg1h:+.2f}%")

# ═══════════════════════════════════════════
print("\n" + "=" * 70)
print("  [2] 프리마켓 마지막 10분 추세 → 본장 결과")
print("=" * 70)

last10_up = [r for r in results if r['last10_chg'] > 0.3]
last10_down = [r for r in results if r['last10_chg'] < -0.3]
last10_flat = [r for r in results if -0.3 <= r['last10_chg'] <= 0.3]

if last10_up:
    up30 = len([r for r in last10_up if r['r30'] > 0])
    avg30 = sum(r['r30'] for r in last10_up) / len(last10_up)
    avg1h = sum(r['r1h'] for r in last10_up) / len(last10_up)
    print(f"\n  마지막10분 상승 ({len(last10_up)}건):")
    print(f"    본장 30분 상승: {up30}/{len(last10_up)} ({up30/len(last10_up)*100:.0f}%) 평균 {avg30:+.2f}%")
    print(f"    본장 1시간 평균: {avg1h:+.2f}%")

if last10_down:
    dn30 = len([r for r in last10_down if r['r30'] < 0])
    avg30 = sum(r['r30'] for r in last10_down) / len(last10_down)
    avg1h = sum(r['r1h'] for r in last10_down) / len(last10_down)
    print(f"\n  마지막10분 하락 ({len(last10_down)}건):")
    print(f"    본장 30분 하락: {dn30}/{len(last10_down)} ({dn30/len(last10_down)*100:.0f}%) 평균 {avg30:+.2f}%")
    print(f"    본장 1시간 평균: {avg1h:+.2f}%")

if last10_flat:
    avg30 = sum(r['r30'] for r in last10_flat) / len(last10_flat)
    print(f"\n  마지막10분 보합 ({len(last10_flat)}건): 본장 30분 평균 {avg30:+.2f}%")

# 코스피/코스닥 분리
for mkt in ['KOSPI', 'KOSDAQ']:
    mdata = [r for r in results if r['market'] == mkt]
    print(f"\n  [{mkt}]")
    l10u = [r for r in mdata if r['last10_chg'] > 0.3]
    l10d = [r for r in mdata if r['last10_chg'] < -0.3]
    if l10u:
        up30 = len([r for r in l10u if r['r30'] > 0])
        avg30 = sum(r['r30'] for r in l10u) / len(l10u)
        print(f"    마지막10분 상승 ({len(l10u)}건): 30분상승 {up30}/{len(l10u)}({up30/len(l10u)*100:.0f}%) 평균 {avg30:+.2f}%")
    if l10d:
        dn30 = len([r for r in l10d if r['r30'] < 0])
        avg30 = sum(r['r30'] for r in l10d) / len(l10d)
        print(f"    마지막10분 하락 ({len(l10d)}건): 30분하락 {dn30}/{len(l10d)}({dn30/len(l10d)*100:.0f}%) 평균 {avg30:+.2f}%")

# ═══════════════════════════════════════════
print("\n" + "=" * 70)
print("  [3] 상승 후 꺾임(UP_DOWN) 상세")
print("=" * 70)

up_down = [r for r in results if r['pattern'] == 'UP_DOWN']
for r in sorted(up_down, key=lambda x: x['r30']):
    print(f"  {r['symbol']}({r['market']}) {r['date']}: "
          f"전반{r['first_chg']:+.1f}% 후반{r['second_chg']:+.1f}% "
          f"마감10분{r['last10_chg']:+.1f}% | "
          f"본장30분 {r['r30']:+.1f}% 1시간 {r['r1h']:+.1f}%")

# ═══════════════════════════════════════════
print("\n" + "=" * 70)
print("  [4] 고점 대비 프리마켓 마감 위치 → 본장")
print("=" * 70)

high_close = [r for r in results if r['close_position'] > 0.7]
low_close = [r for r in results if r['close_position'] < 0.3]
mid_close = [r for r in results if 0.3 <= r['close_position'] <= 0.7]

if high_close:
    up30 = len([r for r in high_close if r['r30'] > 0])
    avg30 = sum(r['r30'] for r in high_close) / len(high_close)
    avg1h = sum(r['r1h'] for r in high_close) / len(high_close)
    print(f"\n  고점 근처 마감 (0.7~1.0) ({len(high_close)}건):")
    print(f"    30분 상승: {up30}/{len(high_close)} ({up30/len(high_close)*100:.0f}%) 평균 {avg30:+.2f}%, 1시간 {avg1h:+.2f}%")

if mid_close:
    up30 = len([r for r in mid_close if r['r30'] > 0])
    avg30 = sum(r['r30'] for r in mid_close) / len(mid_close)
    avg1h = sum(r['r1h'] for r in mid_close) / len(mid_close)
    print(f"\n  중간 마감 (0.3~0.7) ({len(mid_close)}건):")
    print(f"    30분 상승: {up30}/{len(mid_close)} ({up30/len(mid_close)*100:.0f}%) 평균 {avg30:+.2f}%, 1시간 {avg1h:+.2f}%")

if low_close:
    dn30 = len([r for r in low_close if r['r30'] < 0])
    avg30 = sum(r['r30'] for r in low_close) / len(low_close)
    avg1h = sum(r['r1h'] for r in low_close) / len(low_close)
    print(f"\n  저점 근처 마감 (0.0~0.3) ({len(low_close)}건):")
    print(f"    30분 하락: {dn30}/{len(low_close)} ({dn30/len(low_close)*100:.0f}%) 평균 {avg30:+.2f}%, 1시간 {avg1h:+.2f}%")

# 코스피/코스닥 분리
for mkt in ['KOSPI', 'KOSDAQ']:
    mdata = [r for r in results if r['market'] == mkt]
    print(f"\n  [{mkt}]")
    hc = [r for r in mdata if r['close_position'] > 0.7]
    lc = [r for r in mdata if r['close_position'] < 0.3]
    if hc:
        up30 = len([r for r in hc if r['r30'] > 0])
        avg30 = sum(r['r30'] for r in hc) / len(hc)
        print(f"    고점마감({len(hc)}건): 30분상승 {up30}/{len(hc)}({up30/len(hc)*100:.0f}%) 평균 {avg30:+.2f}%")
    if lc:
        dn30 = len([r for r in lc if r['r30'] < 0])
        avg30 = sum(r['r30'] for r in lc) / len(lc)
        print(f"    저점마감({len(lc)}건): 30분하락 {dn30}/{len(lc)}({dn30/len(lc)*100:.0f}%) 평균 {avg30:+.2f}%")
