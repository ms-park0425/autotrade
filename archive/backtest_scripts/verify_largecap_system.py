#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
대형주 중심 시스템 검증
"""

import sys
import io
import yfinance as yf
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 대형주 시스템 (최소 1조)
largecap_picks = [
    ('010120.KS', 'LS ELECTRIC', 77),
    ('007810.KS', '코리아써키트', 77),
    ('064350.KS', '현대로템', 74),
    ('010140.KS', '삼성중공업', 74),
    ('089030.KQ', '테크윙', 73),
    ('046090.KQ', '우리기술', 73),
    ('034020.KS', '두산에너빌리티', 73),
    ('051600.KS', '한전KPS', 72),
    ('042660.KS', 'HD현대마린엔진', 72),
    ('041450.KS', '삼화콘덴서', 72),
    ('096770.KS', 'SK이노베이션', 71),
    ('000720.KS', '현대건설', 71),
    ('013030.KS', '성광벤드', 70),
    ('012450.KS', '한화에어로스페이스', 69),
    ('098460.KS', '고영', 69),
]

# 중소형주 시스템 (기존)
smallcap_picks = [
    ('330860.KQ', '네패스아크', 81),
    ('457370.KQ', '한켐', 80),
    ('170920.KQ', '엘티씨', 78),
    ('451220.KQ', '아이엠티', 76),
    ('083310.KQ', '싸이맥스', 75),
]

# 반도체 대형주 (비교용)
semi_largecaps = [
    ('005930.KS', '삼성전자', 0),
    ('000660.KS', 'SK하이닉스', 0),
]

print('=' * 100)
print(f'📊 대형주 vs 중소형주 vs 반도체 대형주')
print(f'검증 시간: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 100)

def evaluate_system(picks, system_name):
    print(f'\n{"="*100}')
    print(f'{system_name}')
    print(f'{"="*100}')

    results = []

    for ticker, name, score in picks:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period='5d')

            if len(df) < 2:
                continue

            info = stock.info or {}
            market_cap = info.get('marketCap', 0) / 1_000_000_000_000  # 조

            yesterday_close = df['Close'].iloc[-2]
            today_close = df['Close'].iloc[-1]
            total_return = (today_close / yesterday_close - 1) * 100

            results.append({
                'name': name,
                'score': score,
                'market_cap': market_cap,
                'return': total_return
            })

        except Exception as e:
            pass

    if not results:
        print("데이터 없음")
        return None

    # 출력
    print(f'{"순위":<4} {"종목명":<20} {"시총(조)":<10} {"점수":<5} {"수익률":<10} {"평가":<10}')
    print('-' * 100)

    win_count = 0
    total_return = 0

    for i, r in enumerate(results, 1):
        verdict = '✅' if r['return'] > 0 else '❌'
        if r['return'] > 0:
            win_count += 1
        total_return += r['return']

        print(
            f'{i:<4} '
            f'{r["name"]:<20} '
            f'{r["market_cap"]:>8.1f}조 '
            f'{r["score"]:<5} '
            f'{r["return"]:>9.2f}% '
            f'{verdict:<10}'
        )

    avg_return = total_return / len(results)
    win_rate = win_count / len(results) * 100

    print()
    print(f'승률: {win_count}/{len(results)} = {win_rate:.1f}%')
    print(f'평균 수익률: {avg_return:+.2f}%')
    print(f'평균 시총: {sum(r["market_cap"] for r in results)/len(results):.1f}조')

    return {
        'win_rate': win_rate,
        'avg_return': avg_return,
        'count': len(results),
        'avg_market_cap': sum(r["market_cap"] for r in results)/len(results)
    }

# 평가
large_result = evaluate_system(largecap_picks, '🔥 대형주 시스템 (1조+)')
small_result = evaluate_system(smallcap_picks, '📊 중소형주 시스템 (1조 미만)')
semi_result = evaluate_system(semi_largecaps, '💎 반도체 대형주 (비교)')

# 비교
if large_result and small_result:
    print('\n' + '=' * 100)
    print('🎯 시스템 비교')
    print('=' * 100)

    print(f'\n{"지표":<20} {"대형주":<15} {"중소형주":<15} {"개선폭":<15}')
    print('-' * 100)

    win_diff = large_result['win_rate'] - small_result['win_rate']
    return_diff = large_result['avg_return'] - small_result['avg_return']

    print(f'{"승률":<20} {large_result["win_rate"]:>13.1f}% {small_result["win_rate"]:>13.1f}% {win_diff:>13.1f}%p')
    print(f'{"평균 수익률":<20} {large_result["avg_return"]:>13.2f}% {small_result["avg_return"]:>13.2f}% {return_diff:>13.2f}%p')
    print(f'{"평균 시총":<20} {large_result["avg_market_cap"]:>12.1f}조 {small_result["avg_market_cap"]:>12.1f}조')

    print('\n🎯 결론:')
    if return_diff > 0:
        print(f'✅ 대형주가 {return_diff:+.2f}%p 더 좋음!')
        print(f'✅ 승률도 {win_diff:+.1f}%p 높음!')
    else:
        print(f'❌ 중소형주가 여전히 나음')

    if semi_result:
        print(f'\n💡 참고: 반도체 대형주 평균 {semi_result["avg_return"]:+.2f}%')
        print('   (우리가 놓친 종목들)')
