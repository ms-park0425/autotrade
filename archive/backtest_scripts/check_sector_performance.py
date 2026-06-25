#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io
import yfinance as yf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 반도체 대표주
semis = [
    ('005930.KS', '삼성전자'),
    ('000660.KS', 'SK하이닉스'),
    ('006400.KS', '삼성SDI'),
    ('042700.KS', '한미반도체'),
    ('039030.KS', '이오테크닉스'),
]

print('반도체 대표주 오늘 성과')
print('='*60)

total_return = 0
count = 0

for ticker, name in semis:
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period='5d')

        if len(df) >= 2:
            yesterday = df['Close'].iloc[-2]
            today = df['Close'].iloc[-1]
            ret = (today / yesterday - 1) * 100

            total_return += ret
            count += 1

            status = '✅' if ret > 0 else '❌'
            print(f'{name:15} {ret:>7.2f}% {status}')
    except Exception as e:
        print(f'{name:15} 데이터 오류')

if count > 0:
    avg = total_return / count
    print(f'\n평균: {avg:+.2f}%')
