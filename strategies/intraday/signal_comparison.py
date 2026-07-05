#!/usr/bin/env python3
"""
진입 신호 비교 백테스트

6가지 완전히 다른 진입 신호를 동일한 청산 조건으로 비교
청산: trail=2% (고점 대비 2% 하락), hard_sl=-1% (진입가 대비 1% 손절)
수수료: 0.6% 왕복
기간: 2026-01 ~ 2026-07
"""
import sys, os, io, json
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

TRAIL_PCT  = 2.0   # 고점 대비 2% 하락 시 trail 청산
HARD_SL    = -1.0  # 진입가 대비 1% 손절
COMMISSION = 0.3   # 왕복 0.3%
CACHE_DIR  = os.path.join(os.path.dirname(__file__), 'data', 'candle_cache')


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────

def load_cache(symbol, date):
    f = os.path.join(CACHE_DIR, f'{symbol}_{date}.json')
    if not os.path.exists(f): return []
    with open(f) as fp: raw = json.load(fp)
    return [c for c in raw if '09:00' <= c['timestamp'][11:16] <= '15:20']


def resample(candles_1m, minutes):
    """1분봉 → N분봉으로 합산"""
    if minutes == 1:
        return candles_1m
    buckets, result = {}, []
    for c in candles_1m:
        ts   = c['timestamp']
        h, m = int(ts[11:13]), int(ts[14:16])
        slot = (h * 60 + m) // minutes * minutes
        key  = f'{h:02d}:{m:02d}'[:2] + f'{slot % 60:02d}'
        bucket_ts = ts[:11] + f'{slot // 60:02d}:{slot % 60:02d}' + ts[16:]
        if bucket_ts not in buckets:
            buckets[bucket_ts] = {
                'timestamp':  bucket_ts,
                'openPrice':  c['openPrice'],
                'highPrice':  c['highPrice'],
                'lowPrice':   c['lowPrice'],
                'closePrice': c['closePrice'],
                'volume':     float(c['volume']),
                'currency':   c.get('currency', 'KRW'),
            }
        else:
            b = buckets[bucket_ts]
            b['highPrice']  = str(max(float(b['highPrice']),  float(c['highPrice'])))
            b['lowPrice']   = str(min(float(b['lowPrice']),   float(c['lowPrice'])))
            b['closePrice'] = c['closePrice']
            b['volume']    += float(c['volume'])
    # timestamp 순 정렬
    for b in buckets.values():
        b['volume'] = str(int(b['volume']))
    return sorted(buckets.values(), key=lambda x: x['timestamp'])


def get_all_dates():
    dates, d = [], datetime(2026, 1, 5)
    today = datetime(2026, 7, 3)
    while d <= today:
        for i in range(5):
            day = d + timedelta(days=i)
            if day <= today:
                dates.append(day.strftime('%Y-%m-%d'))
        d += timedelta(weeks=1)
    return dates


def ema(values, period):
    """지수이동평균"""
    result, k = [], 2 / (period + 1)
    for i, v in enumerate(values):
        if i == 0:
            result.append(v)
        else:
            result.append(v * k + result[-1] * (1 - k))
    return result


def sma(values, period):
    result = []
    for i in range(len(values)):
        w = values[max(0, i-period+1):i+1]
        result.append(sum(w)/len(w))
    return result


def vwap(reg):
    """일중 VWAP"""
    cum_pv, cum_v = 0.0, 0.0
    result = []
    for c in reg:
        tp = (float(c['highPrice']) + float(c['lowPrice']) + float(c['closePrice'])) / 3
        v  = float(c['volume'])
        cum_pv += tp * v
        cum_v  += v
        result.append(cum_pv / cum_v if cum_v > 0 else tp)
    return result


# ─────────────────────────────────────────────
# 청산 공통 로직
# ─────────────────────────────────────────────

def run_exit(reg, entry_idx, entry_price):
    """
    trail=2%, hard_sl=-1%로 청산
    반환: (pnl, reason, hold_bars)
    """
    peak = entry_price
    for j in range(entry_idx, len(reg)):
        hi = float(reg[j]['highPrice'])
        lo = float(reg[j]['lowPrice'])
        if hi > peak: peak = hi

        sl_price    = entry_price * (1 + HARD_SL / 100)
        trail_price = peak * (1 - TRAIL_PCT / 100)

        if lo <= sl_price:
            pnl = (sl_price - entry_price) / entry_price * 100 - COMMISSION
            return pnl, 'SL', j - entry_idx
        elif lo <= trail_price:
            pnl = (trail_price - entry_price) / entry_price * 100 - COMMISSION
            return pnl, 'TRAIL', j - entry_idx

    last = float(reg[-1]['closePrice'])
    pnl  = (last - entry_price) / entry_price * 100 - COMMISSION
    return pnl, 'CLOSE', len(reg) - entry_idx


# ─────────────────────────────────────────────
# 진입 신호 정의
# ─────────────────────────────────────────────

SIGNALS = {}

def signal(name):
    def decorator(fn):
        SIGNALS[name] = fn
        return fn
    return decorator


# ── 신호 1: 기존 기준선 (2봉 연속 양봉) ─────
@signal('S1_기존_2연속양봉')
def s1(reg, i, **_):
    """기존 전략. 비교 기준선."""
    if i < 2: return False
    o1 = float(reg[i-2]['openPrice']); cl1 = float(reg[i-2]['closePrice'])
    o2 = float(reg[i-1]['openPrice']); cl2 = float(reg[i-1]['closePrice'])
    return cl1 > o1 and cl2 > o2 and cl2 > cl1


# ── 신호 2: 거래량 급증 + N봉 신고가 돌파 ────
@signal('S2_거래량급증_신고가')
def s2(reg, i, closes, volumes, **_):
    """
    최근 20봉 거래량 평균의 2배 이상 거래량 + 최근 10봉 고가 돌파
    강한 수급이 터지며 저항을 뚫는 순간
    """
    if i < 20: return False
    vol_avg = sum(volumes[i-20:i]) / 20
    cur_vol = volumes[i-1]
    if cur_vol < vol_avg * 2.0: return False
    recent_high = max(float(reg[j]['highPrice']) for j in range(i-10, i-1))
    return float(reg[i-1]['closePrice']) > recent_high


# ── 신호 3: VWAP 골든크로스 ──────────────────
@signal('S3_VWAP_위로돌파')
def s3(reg, i, vwap_vals, closes, **_):
    """
    전봉이 VWAP 아래에 있다가 현재봉 close가 VWAP 위로 돌파
    + 거래량 평균 이상
    VWAP는 기관/세력의 기준선 → 이를 넘으면 수급 전환 신호
    """
    if i < 2: return False
    prev_cl = float(reg[i-2]['closePrice'])
    curr_cl = float(reg[i-1]['closePrice'])
    prev_vw = vwap_vals[i-2]
    curr_vw = vwap_vals[i-1]
    return prev_cl < prev_vw and curr_cl > curr_vw


# ── 신호 4: 오프닝 레인지 브레이크아웃 (ORB) ─
@signal('S4_ORB_오전고가돌파')
def s4(reg, i, orb_high, **_):
    """
    9:00~9:30 사이 형성된 고가를 처음 돌파하는 순간 진입
    장 초반 30분이 그날의 방향을 결정하는 경우가 많음
    한 번만 발동 (첫 돌파만)
    """
    if orb_high is None: return False
    t = reg[i-1]['timestamp'][11:16]
    if t < '09:30': return False
    cl = float(reg[i-1]['closePrice'])
    prev_cl = float(reg[i-2]['closePrice']) if i >= 2 else 0
    return prev_cl <= orb_high and cl > orb_high


# ── 신호 5: EMA 5/20 골든크로스 + 기울기 ─────
@signal('S5_EMA골든크로스')
def s5(reg, i, ema5, ema20, **_):
    """
    EMA5가 EMA20을 아래서 위로 돌파 (골든크로스)
    + EMA20 자체도 우상향 중 (추세 확인)
    단순 크로스가 아닌 '추세 방향으로의 크로스'
    """
    if i < 3: return False
    cross_up = ema5[i-2] < ema20[i-2] and ema5[i-1] > ema20[i-1]
    trend_up = ema20[i-1] > ema20[i-3]
    return cross_up and trend_up


# ── 신호 6: 볼린저밴드 수축 후 상단 돌파 ──────
@signal('S6_BB스퀴즈_상단돌파')
def s6(reg, i, closes, **_):
    """
    볼린저밴드가 20봉 중 최소폭(squeeze) 구간 이후
    상단을 처음 돌파하는 순간
    변동성 수축 → 폭발 패턴
    """
    if i < 22: return False
    window = closes[i-20:i]
    avg = sum(window) / 20
    std = (sum((x - avg)**2 for x in window) / 20) ** 0.5
    if std == 0: return False
    bb_width = 4 * std / avg  # 밴드폭 (정규화)

    # 최근 20봉 중 현재 밴드폭이 가장 좁은지 (squeeze)
    prev_widths = []
    for k in range(i-20, i-1):
        w = closes[k-20:k]
        if len(w) < 20: continue
        a = sum(w)/20
        s = (sum((x-a)**2 for x in w)/20)**0.5
        prev_widths.append(4*s/a if a > 0 else 0)

    if not prev_widths: return False
    was_narrow = bb_width < min(prev_widths) * 1.3  # 스퀴즈 상태

    upper = avg + 2 * std
    cl = closes[i-1]
    prev_cl = closes[i-2]
    breakout = cl > upper and prev_cl <= upper

    return was_narrow and breakout


# ── 신호 7: 강한 단일 모멘텀 봉 (캔들스틱) ───
@signal('S7_강한_모멘텀봉')
def s7(reg, i, closes, volumes, **_):
    """
    봉 하나의 body가 전체 range의 70% 이상 (강한 방향성)
    + 거래량이 평균 1.5배 이상
    + 직전 5봉이 횡보 (range < 0.5%)  → 돌파 직전 에너지 축적
    """
    if i < 8: return False
    c = reg[i-1]
    op  = float(c['openPrice'])
    cl  = float(c['closePrice'])
    hi  = float(c['highPrice'])
    lo  = float(c['lowPrice'])
    rng = hi - lo
    if rng == 0: return False

    body_ratio = (cl - op) / rng  # 양봉 body 비율
    if body_ratio < 0.70: return False

    vol_avg = sum(volumes[i-6:i-1]) / 5
    if float(c['volume']) < vol_avg * 1.5: return False

    # 직전 5봉 횡보
    prev_highs = max(float(reg[j]['highPrice']) for j in range(i-6, i-1))
    prev_lows  = min(float(reg[j]['lowPrice'])  for j in range(i-6, i-1))
    consolidation = (prev_highs - prev_lows) / prev_lows * 100 < 0.5

    return consolidation


# ─────────────────────────────────────────────
# 시뮬레이션
# ─────────────────────────────────────────────

def simulate_signal(reg_list, signal_fn):
    trades = []

    for reg in reg_list:
        if len(reg) < 25: continue

        closes  = [float(c['closePrice']) for c in reg]
        volumes = [float(c['volume'])     for c in reg]
        vwap_v  = vwap(reg)
        e5      = ema(closes, 5)
        e20     = ema(closes, 20)

        # ORB: 9:00~9:30 고가
        orb_high = None
        orb_triggered = False
        for c in reg:
            if '09:00' <= c['timestamp'][11:16] < '09:30':
                h = float(c['highPrice'])
                if orb_high is None or h > orb_high:
                    orb_high = h

        last_entry_idx = -999

        for i in range(22, len(reg)):
            t = reg[i]['timestamp'][11:16]
            if t < '09:30' or t > '15:10': continue
            if i - last_entry_idx < 5: continue  # cooldown

            # ORB는 하루 1번만
            if signal_fn.__name__ == 's4' and orb_triggered:
                continue

            kwargs = dict(
                closes=closes, volumes=volumes,
                vwap_vals=vwap_v, ema5=e5, ema20=e20,
                orb_high=orb_high,
            )

            if signal_fn(reg, i, **kwargs):
                entry = float(reg[i]['openPrice'])
                if entry <= 0: continue

                pnl, reason, hold = run_exit(reg, i, entry)
                trades.append({'pnl': pnl, 'reason': reason, 'hold': hold})
                last_entry_idx = i

                if signal_fn.__name__ == 's4':
                    orb_triggered = True

    return trades


def summarize(trades):
    if not trades:
        return {'total': 0.0, 'n': 0, 'wr': 0.0, 'avg': 0.0, 'avg_hold': 0.0}
    wins = [t for t in trades if t['pnl'] > 0]
    return {
        'total':    sum(t['pnl'] for t in trades),
        'n':        len(trades),
        'wr':       len(wins) / len(trades) * 100,
        'avg':      sum(t['pnl'] for t in trades) / len(trades),
        'avg_hold': sum(t['hold'] for t in trades) / len(trades),
    }


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
from collections import defaultdict

all_dates = get_all_dates()

print('캔들 캐시 로딩 (1분봉) ...')
all_reg_1m = {}
for symbol in TARGETS:
    all_reg_1m[symbol] = [load_cache(symbol, d) for d in all_dates]
print(f'완료  ({len(TARGETS)}종목 × {len(all_dates)}일)\n')

TIMEFRAMES = [1, 3, 5]

# 타임프레임별 리샘플
all_reg_tf = {}
for tf in TIMEFRAMES:
    all_reg_tf[tf] = {}
    for symbol in TARGETS:
        all_reg_tf[tf][symbol] = [resample(day, tf) for day in all_reg_1m[symbol]]

print(f'진입 신호 비교 시뮬레이션')
print(f'신호: {len(SIGNALS)}개  |  타임프레임: {TIMEFRAMES}분봉  |  종목: {len(TARGETS)}개')
print(f'청산: trail={TRAIL_PCT}%  hard_sl={HARD_SL}%  수수료={COMMISSION}%\n')

# ── 타임프레임 × 신호별 결과 수집 ─────────────
tf_results = {}   # tf_results[tf][sig_name] = {...}

for tf in TIMEFRAMES:
    tf_results[tf] = {}
    for sig_name, sig_fn in SIGNALS.items():
        all_trades, sym_totals = [], []
        for symbol in TARGETS:
            t = simulate_signal(all_reg_tf[tf][symbol], sig_fn)
            all_trades.extend(t)
            sym_totals.append(summarize(t)['total'])
        s = summarize(all_trades)
        tf_results[tf][sig_name] = {
            'port_avg':  sum(sym_totals) / len(sym_totals),
            'sym_totals': sym_totals,
            **s,
        }

# ── 타임프레임별 종합 비교표 ─────────────────
for tf in TIMEFRAMES:
    ranked = sorted(tf_results[tf].items(), key=lambda x: -x[1]['port_avg'])
    print('=' * 88)
    print(f'  [{tf}분봉]  신호별 종합 비교  (전 기간 · 10종목 평균)')
    print('=' * 88)
    print(f'  {"신호":<24} {"포트평균":>9} {"총거래":>7} {"승률":>6} {"거래당":>8} {"평균보유봉":>9}')
    print('  ' + '─' * 72)
    for sig_name, r in ranked:
        mark = ' ◀' if sig_name == ranked[0][0] else ''
        print(f'  {sig_name:<24} {r["port_avg"]:>+8.2f}% {r["n"]:>6}건  {r["wr"]:>5.0f}%'
              f'  {r["avg"]:>+7.3f}%  {r["avg_hold"]:>7.1f}봉{mark}')
    print()

# ── 전체 최고 조합 찾기 ───────────────────────
best_tf, best_sig, best_val = 1, '', -9999
for tf in TIMEFRAMES:
    for sig_name, r in tf_results[tf].items():
        if r['port_avg'] > best_val:
            best_val = r['port_avg']
            best_tf, best_sig = tf, sig_name

print('=' * 70)
print(f'  전체 최고: {best_tf}분봉 + {best_sig}')
print(f'  포트 평균: {best_val:+.2f}%')
print('=' * 70)

# 종목별 상세
best_r = tf_results[best_tf][best_sig]
print(f'  {"종목":<14} {"누적손익":>9} {"거래수":>7} {"승률":>7}')
print('  ' + '─' * 42)
for symbol, name, pnl in zip(TARGETS.keys(), TARGETS.values(), best_r['sym_totals']):
    t = simulate_signal(all_reg_tf[best_tf][symbol], SIGNALS[best_sig])
    s = summarize(t)
    print(f'  {name:<14} {pnl:>+8.2f}% {s["n"]:>6}건  {s["wr"]:>5.0f}%')

# ── 최고 조합 주차별 성과 ─────────────────────
print()
print(f'  [{best_tf}분봉 + {best_sig}] 주차별 성과')
print('  ' + '─' * 48)

weeks_list = []
d = datetime(2026, 1, 5)
today = datetime(2026, 7, 3)
while d <= today:
    week = [(d + timedelta(days=i)).strftime('%Y-%m-%d')
            for i in range(5) if (d + timedelta(days=i)) <= today]
    if week: weeks_list.append(week)
    d += timedelta(weeks=1)

all_data_by_date = {}
for symbol in TARGETS:
    all_data_by_date[symbol] = {}
    for i, date in enumerate(all_dates):
        all_data_by_date[symbol][date] = all_reg_tf[best_tf][symbol][i]

week_pnls = defaultdict(list)
best_fn = SIGNALS[best_sig]
for symbol in TARGETS:
    for week in weeks_list:
        reg_list = [all_data_by_date[symbol][d] for d in week if all_data_by_date[symbol].get(d)]
        t = simulate_signal([r for r in reg_list if r], best_fn)
        s = summarize(t)
        week_pnls[week[0]].append(s['total'])

print(f'  {"주":<12} {"평균손익":>9} {"누적손익":>9} {"참여종목":>8}')
print('  ' + '─' * 45)
cum = 0.0
pos_weeks = 0
for week_start in sorted(week_pnls.keys()):
    pnls = week_pnls[week_start]
    avg = sum(pnls) / len(pnls)
    cum += avg
    if avg > 0: pos_weeks += 1
    mark = ' ▲' if avg > 0 else ''
    print(f'  {week_start:<12} {avg:>+8.2f}% {cum:>+8.2f}%  {len(pnls)}종목{mark}')

total_weeks = len(week_pnls)
print(f'\n  수익 주차: {pos_weeks}/{total_weeks}주')
print('=' * 70)
