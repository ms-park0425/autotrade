#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
오늘 예측 종목 실제 성과 검증
"""

import sys
import io
import yfinance as yf
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

tickers = [
    ('092220.KS', 'KEC', 69),
    ('330860.KQ', '네패스아크', 67),
    ('172670.KQ', '에이엘티', 66),
    ('457370.KQ', '한켐', 66),
    ('484590.KQ', '삼양컴텍', 65),
    ('126730.KQ', '코칩', 64),
    ('170920.KQ', '엘티씨', 64),
    ('000720.KS', '현대건설', 63),
    ('051600.KS', '한전KPS', 63),
    ('043260.KS', '성호전자', 63),
    ('033160.KS', '엠케이전자', 63),
    ('355150.KQ', '코스텍시스', 63),
    ('007810.KS', '코리아써키트', 63),
    ('278280.KQ', '천보', 62),
    ('451220.KQ', '아이엠티', 62),
]

print('=' * 100)
print(f'📊 오늘(2026-06-25) 실제 수익률 검증')
print(f'분석 시간: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 100)
print()

results = []

for ticker, name, score in tickers:
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period='5d')

        if len(df) < 2:
            print(f'{name:15} - 데이터 없음')
            continue

        # 어제 종가 (6/24)
        yesterday_close = df['Close'].iloc[-2]

        # 오늘 데이터 (6/25)
        today_open = df['Open'].iloc[-1]
        today_high = df['High'].iloc[-1]
        today_low = df['Low'].iloc[-1]
        today_close = df['Close'].iloc[-1]
        today_volume = df['Volume'].iloc[-1]

        # 수익률 계산
        gap = (today_open / yesterday_close - 1) * 100
        intraday = (today_close / today_open - 1) * 100
        total_return = (today_close / yesterday_close - 1) * 100

        results.append({
            'name': name,
            'score': score,
            'yesterday': yesterday_close,
            'today_open': today_open,
            'today_high': today_high,
            'today_low': today_low,
            'today_close': today_close,
            'gap': gap,
            'intraday': intraday,
            'total': total_return,
            'volume': today_volume
        })

    except Exception as e:
        print(f'{name:15} - 에러: {e}')

# 결과 출력
print(f'{"순위":<4} {"종목명":<15} {"점수":<5} {"갭":<8} {"장중":<8} {"총수익률":<10} {"평가":<10}')
print('-' * 100)

win_count = 0
total_return_sum = 0

for i, r in enumerate(results, 1):
    verdict = '✅ 성공' if r['total'] > 0 else '❌ 실패'
    if r['total'] > 0:
        win_count += 1

    total_return_sum += r['total']

    print(
        f'{i:<4} '
        f'{r["name"]:<15} '
        f'{r["score"]:<5} '
        f'{r["gap"]:>7.2f}% '
        f'{r["intraday"]:>7.2f}% '
        f'{r["total"]:>9.2f}% '
        f'{verdict:<10}'
    )

print()
print('=' * 100)
print('📈 종합 결과')
print('=' * 100)
print(f'승률: {win_count}/{len(results)} = {win_count/len(results)*100:.1f}%')
print(f'평균 수익률: {total_return_sum/len(results):.2f}%')
print(f'상승 종목 수: {win_count}개')
print(f'하락 종목 수: {len(results) - win_count}개')
print()

# 베이스라인 비교
print('🎯 백테스트 예상 vs 실제')
print(f'예상 승률: 55~68%')
print(f'실제 승률: {win_count/len(results)*100:.1f}%')
print(f'예상 평균 수익률: +0.9~1.2%')
print(f'실제 평균 수익률: {total_return_sum/len(results):+.2f}%')
print()

# 상세 분석
if results:
    best = max(results, key=lambda x: x['total'])
    worst = min(results, key=lambda x: x['total'])

    print('🥇 최고 수익')
    print(f'   {best["name"]}: {best["total"]:+.2f}% (점수 {best["score"]}점)')
    print()
    print('💀 최악 손실')
    print(f'   {worst["name"]}: {worst["total"]:+.2f}% (점수 {worst["score"]}점)')
    print()

    # 점수별 수익률 상관관계
    high_score = [r for r in results if r['score'] >= 65]
    low_score = [r for r in results if r['score'] < 65]

    if high_score:
        high_avg = sum(r['total'] for r in high_score) / len(high_score)
        print(f'📊 고점수(65점+) 평균: {high_avg:+.2f}% ({len(high_score)}개)')

    if low_score:
        low_avg = sum(r['total'] for r in low_score) / len(low_score)
        print(f'📊 저점수(65점 미만) 평균: {low_avg:+.2f}% ({len(low_score)}개)')
