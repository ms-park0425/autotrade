#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
개선된 시스템 검증
"""

import sys
import io
import yfinance as yf
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 개선된 시스템 추천 (테마 V2)
new_picks = [
    ('330860.KQ', '네패스아크', 81),
    ('457370.KQ', '한켐', 80),
    ('425420.KQ', '티에프이', 79),
    ('170920.KQ', '엘티씨', 78),
    ('007810.KS', '코리아써키트', 77),
    ('451220.KQ', '아이엠티', 76),
    ('083310.KQ', '싸이맥스', 75),
    ('089030.KQ', '테크윙', 73),
    ('046090.KQ', '우리기술', 73),
    ('160550.KQ', '에이팩트', 73),
    ('051600.KS', '한전KPS', 72),
    ('041450.KS', '삼화콘덴서', 72),
    ('196490.KQ', '한솔테크닉스', 72),
    ('203310.KQ', '미래반도체', 70),
    ('010120.KS', 'LS ELECTRIC', 70),
]

# 기존 시스템 추천 (테마 V1)
old_picks = [
    ('092220.KS', 'KEC', 69),
    ('330860.KQ', '네패스아크', 67),
    ('172670.KQ', '에이엘티', 66),
    ('457370.KQ', '한켐', 66),
    ('484590.KQ', '삼양컴텍', 65),
]

print('=' * 100)
print(f'🔥 개선된 시스템 (테마 V2) vs 기존 시스템 (테마 V1)')
print(f'검증 시간: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 100)

def evaluate_picks(picks, system_name):
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

            yesterday_close = df['Close'].iloc[-2]
            today_close = df['Close'].iloc[-1]
            total_return = (today_close / yesterday_close - 1) * 100

            results.append({
                'name': name,
                'score': score,
                'return': total_return
            })

        except Exception as e:
            pass

    if not results:
        print("데이터 없음")
        return None

    # 출력
    print(f'{"순위":<4} {"종목명":<15} {"점수":<5} {"수익률":<10} {"평가":<10}')
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
            f'{r["name"]:<15} '
            f'{r["score"]:<5} '
            f'{r["return"]:>9.2f}% '
            f'{verdict:<10}'
        )

    avg_return = total_return / len(results)
    win_rate = win_count / len(results) * 100

    print()
    print(f'승률: {win_count}/{len(results)} = {win_rate:.1f}%')
    print(f'평균 수익률: {avg_return:+.2f}%')

    return {
        'win_rate': win_rate,
        'avg_return': avg_return,
        'count': len(results)
    }

# 평가
new_result = evaluate_picks(new_picks, '🔥 개선된 시스템 (테마 V2 - 급락반등 전략)')
old_result = evaluate_picks(old_picks, '📊 기존 시스템 (테마 V1 - 지속성 전략)')

# 비교
if new_result and old_result:
    print('\n' + '=' * 100)
    print('📊 시스템 비교')
    print('=' * 100)

    print(f'\n{"지표":<20} {"개선 시스템":<15} {"기존 시스템":<15} {"개선폭":<15}')
    print('-' * 100)

    win_diff = new_result['win_rate'] - old_result['win_rate']
    return_diff = new_result['avg_return'] - old_result['avg_return']

    print(f'{"승률":<20} {new_result["win_rate"]:>13.1f}% {old_result["win_rate"]:>13.1f}% {win_diff:>13.1f}%p')
    print(f'{"평균 수익률":<20} {new_result["avg_return"]:>13.2f}% {old_result["avg_return"]:>13.2f}% {return_diff:>13.2f}%p')
    print(f'{"종목 수":<20} {new_result["count"]:>13} {old_result["count"]:>13}')

    print('\n🎯 결론:')
    if return_diff > 0:
        print(f'✅ 개선된 시스템이 {return_diff:+.2f}%p 더 좋음!')
    else:
        print(f'❌ 기존 시스템이 {-return_diff:+.2f}%p 더 좋음')
