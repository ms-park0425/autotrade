#!/usr/bin/env python3
"""
Walk-Forward 롤링 백테스트

매주 전주 데이터로 최적 파라미터 찾고 → 당주 적용 → 반복
기간: 2026년 1월 ~ 현재
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

CONFIGS = [
    {'name': '기본',          'tp': 2.0, 'sl': -1.5, 'entry': '09:30', 'cool': 5,  'candles': 2},
    {'name': '익절1.5/손절1',  'tp': 1.5, 'sl': -1.0, 'entry': '09:30', 'cool': 5,  'candles': 2},
    {'name': '익절2/손절2',    'tp': 2.0, 'sl': -2.0, 'entry': '09:30', 'cool': 5,  'candles': 2},
    {'name': '익절3/손절1.5',  'tp': 3.0, 'sl': -1.5, 'entry': '09:30', 'cool': 5,  'candles': 2},
    {'name': '10시이후',       'tp': 2.0, 'sl': -1.5, 'entry': '10:00', 'cool': 5,  'candles': 2},
    {'name': '3연속양봉',      'tp': 2.0, 'sl': -1.5, 'entry': '09:30', 'cool': 5,  'candles': 3},
    {'name': '익절1/손절0.5',  'tp': 1.0, 'sl': -0.5, 'entry': '09:30', 'cool': 3,  'candles': 2},
    {'name': '10시+2/2',     'tp': 2.0, 'sl': -2.0, 'entry': '10:00', 'cool': 5,  'candles': 2},
]

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'data', 'candle_cache')
os.makedirs(CACHE_DIR, exist_ok=True)


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
    """하루치 1분봉 수집 (캐시 활용)"""
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
        except Exception as e:
            time.sleep(1)
            break

    data = sorted(all_c, key=lambda x: x['timestamp'])
    if data:
        with open(cache_file, 'w') as f:
            json.dump(data, f)
    return data


def get_reg_candles(candles):
    return [c for c in candles if '09:00' <= c['timestamp'][11:16] <= '15:20']


def is_market_down(all_symbols_day_data, date):
    """시장 하락 감지: 당일 09:01 종가 < 전일 15:19 종가인 종목이 과반수면 하락장"""
    down_count = 0
    valid_count = 0
    for symbol, date_data in all_symbols_day_data.items():
        today_candles = date_data.get(date, [])
        # 전일 찾기
        dates_sorted = sorted(date_data.keys())
        idx = dates_sorted.index(date) if date in dates_sorted else -1
        if idx <= 0:
            continue
        prev_date = dates_sorted[idx - 1]
        prev_candles = date_data.get(prev_date, [])

        # 전일 마지막 종가
        prev_reg = [c for c in prev_candles if '09:00' <= c['timestamp'][11:16] <= '15:20']
        # 당일 첫 봉 (09:01)
        today_reg = [c for c in today_candles if c['timestamp'][11:16] >= '09:01']

        if not prev_reg or not today_reg:
            continue

        prev_close = float(prev_reg[-1]['closePrice'])
        today_open = float(today_reg[0]['closePrice'])

        valid_count += 1
        if today_open < prev_close:
            down_count += 1

    if valid_count == 0:
        return False
    return (down_count / valid_count) >= 0.6  # 60% 이상 하락 시초가면 하락장


def simulate(reg_candles_list, cfg, skip_days=None):
    """여러 날의 캔들로 시뮬레이션 (skip_days: 스킵할 날짜 set)"""
    skip_days = skip_days or set()
    all_trades = []
    for reg in reg_candles_list:
        if not reg:
            continue
        # 하락장 스킵
        date = reg[0]['timestamp'][:10]
        if date in skip_days:
            continue
        position = None
        last_exit_idx = -999
        n = cfg['candles']

        for i in range(n, len(reg)):
            c_curr = reg[i]
            t = c_curr['timestamp'][11:16]
            cl_curr = float(c_curr['closePrice'])

            if position:
                pnl = (cl_curr - position['entry']) / position['entry'] * 100
                if pnl >= cfg['tp']:
                    all_trades.append({'pnl': pnl, 'reason': 'TP'})
                    position = None; last_exit_idx = i
                elif pnl <= cfg['sl']:
                    all_trades.append({'pnl': pnl, 'reason': 'SL'})
                    position = None; last_exit_idx = i
            else:
                if t < cfg['entry']:
                    continue
                if i - last_exit_idx < cfg['cool']:
                    continue
                prev = reg[i-n:i]
                all_bull = all(float(c['closePrice']) > float(c['openPrice']) for c in prev)
                closes = [float(c['closePrice']) for c in prev]
                ladder = all(closes[j] > closes[j-1] for j in range(1, len(closes)))
                if all_bull and ladder:
                    position = {'entry': cl_curr}

        if position:
            last = float(reg[-1]['closePrice'])
            pnl = (last - position['entry']) / position['entry'] * 100
            all_trades.append({'pnl': pnl, 'reason': 'CLOSE'})

    if not all_trades:
        return {'total': 0, 'trades': 0, 'wr': 0}

    wins = [t for t in all_trades if t['pnl'] > 0]
    total = sum(t['pnl'] for t in all_trades)
    return {
        'total': total,
        'trades': len(all_trades),
        'wr': len(wins) / len(all_trades) * 100 if all_trades else 0,
        'tp': len([t for t in all_trades if t['reason'] == 'TP']),
        'sl': len([t for t in all_trades if t['reason'] == 'SL']),
    }


def best_config(reg_candles_list):
    """전주 데이터로 최적 파라미터 선택"""
    best = None
    best_score = -999
    for cfg in CONFIGS:
        result = simulate(reg_candles_list, cfg)
        # 점수: 총손익 * 승률 가중치
        score = result['total']
        if result['trades'] < 3:
            continue
        if score > best_score:
            best_score = score
            best = cfg
    return best if best else CONFIGS[0]


def get_week_dates(year=2026):
    """2026년 월요일~금요일 주 목록"""
    weeks = []
    d = datetime(year, 1, 5)  # 첫 번째 월요일
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


# ═══════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════
weeks = get_week_dates()
print(f'분석 기간: {weeks[0][0]} ~ {weeks[-1][-1]}')
print(f'총 {len(weeks)}주 / {len(TARGETS)}종목')
print()

# 1단계: 전체 데이터 수집
print('데이터 수집 중... (캐시 활용)')
all_dates = [d for w in weeks for d in w]
total_calls = len(TARGETS) * len(all_dates)
done = 0

for symbol, name in TARGETS.items():
    for date in all_dates:
        cache_file = os.path.join(CACHE_DIR, f'{symbol}_{date}.json')
        if not os.path.exists(cache_file):
            collect_day(symbol, date)
            time.sleep(0.4)
        done += 1
        if done % 50 == 0:
            print(f'  {done}/{total_calls} 완료...')

print(f'  데이터 수집 완료!\n')

# 2단계: 전체 데이터 딕셔너리 구성 (하락장 감지용)
all_symbols_day_data = {}
for symbol in TARGETS:
    all_symbols_day_data[symbol] = {}
    for date in all_dates:
        all_symbols_day_data[symbol][date] = collect_day(symbol, date)

# 날짜별 하락장 여부 미리 계산
print('하락장 날짜 계산 중...')
down_days = set()
for date in all_dates:
    if is_market_down(all_symbols_day_data, date):
        down_days.add(date)
print(f'  하락장 감지: {len(down_days)}일 스킵 예정')
print(f'  해당 날짜: {sorted(down_days)[:5]}... (최대 5개 표시)\n')

# 3단계: 종목별 롤링 백테스트 (기존 vs 하락장 필터)
print('=' * 80)
print('  Walk-Forward 롤링 백테스트 결과')
print('  (전주 최적 파라미터 → 당주 적용 / 하락장 스킵 적용)')
print('=' * 80)

all_symbol_results = {}
all_symbol_results_nofilter = {}

for symbol, name in TARGETS.items():
    weekly_results = []
    weekly_results_nf = []

    for week_idx in range(1, len(weeks)):
        prev_week = weeks[week_idx - 1]
        curr_week = weeks[week_idx]

        prev_candles = []
        for date in prev_week:
            reg = get_reg_candles(all_symbols_day_data[symbol][date])
            if reg:
                prev_candles.append(reg)

        curr_candles = []
        for date in curr_week:
            reg = get_reg_candles(all_symbols_day_data[symbol][date])
            if reg:
                curr_candles.append(reg)

        if not prev_candles or not curr_candles:
            continue

        best_cfg = best_config(prev_candles)

        # 필터 없음
        result_nf = simulate(curr_candles, best_cfg)
        result_nf['week'] = curr_week[0]
        result_nf['cfg'] = best_cfg['name']
        weekly_results_nf.append(result_nf)

        # 하락장 스킵 적용
        result = simulate(curr_candles, best_cfg, skip_days=down_days)
        result['week'] = curr_week[0]
        result['cfg'] = best_cfg['name']
        weekly_results.append(result)

    all_symbol_results[symbol] = {'name': name, 'weekly': weekly_results}
    all_symbol_results_nofilter[symbol] = {'name': name, 'weekly': weekly_results_nf}

# 4단계: 결과 출력 (필터 전후 비교)
print()
print(f'  {"종목":<12} {"필터전":>9} {"필터후":>9} {"차이":>7} {"스킵일 효과"}')
print(f'  {"─"*60}')

for symbol, data in all_symbol_results.items():
    name = data['name']
    pnl_filtered = sum(r['total'] for r in data['weekly'])
    pnl_nf = sum(r['total'] for r in all_symbol_results_nofilter[symbol]['weekly'])
    diff = pnl_filtered - pnl_nf
    trades_filtered = sum(r['trades'] for r in data['weekly'])
    trades_nf = sum(r['trades'] for r in all_symbol_results_nofilter[symbol]['weekly'])
    skipped = trades_nf - trades_filtered
    print(f'  {name:<12} {pnl_nf:>+8.2f}% {pnl_filtered:>+8.2f}% {diff:>+6.2f}%  거래 {skipped}건 줄어듦')

# 포트폴리오 합산 비교
print()
print('=' * 80)
print('  포트폴리오 합산 비교 (10종목 평균)')
print('=' * 80)

portfolio_filtered = defaultdict(list)
portfolio_nf = defaultdict(list)
for symbol in all_symbol_results:
    for r in all_symbol_results[symbol]['weekly']:
        portfolio_filtered[r['week']].append(r['total'])
    for r in all_symbol_results_nofilter[symbol]['weekly']:
        portfolio_nf[r['week']].append(r['total'])

cum_f = 0
cum_nf = 0
print(f'  {"주차":<12} {"필터전":>8} {"필터후":>8} {"누적(전)":>9} {"누적(후)":>9} {"스킵?"}')
print(f'  {"─"*60}')
for week in sorted(portfolio_filtered.keys()):
    pnls_f = portfolio_filtered[week]
    pnls_nf_w = portfolio_nf.get(week, pnls_f)
    avg_f = sum(pnls_f) / len(pnls_f)
    avg_nf = sum(pnls_nf_w) / len(pnls_nf_w)
    cum_f += avg_f
    cum_nf += avg_nf

    # 이 주에 스킵된 날 수
    week_dates = [w for w in weeks if w[0] == week]
    skipped_in_week = len([d for d in (week_dates[0] if week_dates else []) if d in down_days])
    skip_str = f'  ({skipped_in_week}일 스킵)' if skipped_in_week else ''

    print(f'  {week:<12} {avg_nf:>+7.2f}% {avg_f:>+7.2f}% {cum_nf:>+8.2f}% {cum_f:>+8.2f}%{skip_str}')

print(f'\n  ── 최종 결과 비교 ──')
print(f'  필터 없음:    누적 {cum_nf:+.2f}% | 평균 {cum_nf/len(portfolio_nf):+.2f}%/주')
print(f'  하락장 스킵:  누적 {cum_f:+.2f}% | 평균 {cum_f/len(portfolio_filtered):+.2f}%/주')
print(f'  개선 효과:    {cum_f - cum_nf:+.2f}%p')

pos_f = len([w for w in portfolio_filtered.values() if sum(w)/len(w) > 0])
pos_nf = len([w for w in portfolio_nf.values() if sum(w)/len(w) > 0])
print(f'  수익 주차:    필터전 {pos_nf}/{len(portfolio_nf)} → 필터후 {pos_f}/{len(portfolio_filtered)}')
print(f'  스킵된 날:    총 {len(down_days)}일')

out_path = os.path.join(os.path.dirname(__file__), 'data', 'rolling_backtest_v2.json')
output = {
    'period': f'{weeks[0][0]} ~ {weeks[-1][-1]}',
    'down_days': sorted(down_days),
    'cumulative_filtered': cum_f,
    'cumulative_nofilter': cum_nf,
}
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'\n  결과 저장: {out_path}')
