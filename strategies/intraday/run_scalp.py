#!/usr/bin/env python3
"""
1분봉 스캘핑 실행

실행:
  python strategies/intraday/run_scalp.py          # 장 종료까지
  python strategies/intraday/run_scalp.py --minutes 30  # 30분만
  python strategies/intraday/run_scalp.py --dry-run     # 시뮬레이션 (주문 안 냄)
"""
import sys
import os
import io
import argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from strategies.intraday.engine.toss_api import TossAPI
from strategies.intraday.engine.scalper import Scalper


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="1분봉 스캘핑")
    parser.add_argument("--minutes", type=int, default=None, help="실행 시간(분). 미지정 시 장 끝까지")
    parser.add_argument("--dry-run", action="store_true", help="시뮬레이션 모드 (주문 안 냄)")
    args = parser.parse_args()

    api = TossAPI()

    if args.dry_run:
        print("*** DRY-RUN 모드: 시그널만 감지, 실제 주문 안 냄 ***\n")

    scalper = Scalper(api)

    if args.dry_run:
        # 매수/매도를 실제로 안 하도록 오버라이드
        original_enter = scalper.enter
        original_exit = scalper.exit

        DRY_BUDGET = 5_000_000  # 500만원

        def fake_enter(symbol):
            price_hist = scalper.price_history.get(symbol, [])
            if price_hist:
                from strategies.intraday.engine.scalper import ScalpPosition
                price = price_hist[-1]
                quantity = int(DRY_BUDGET / price)
                if quantity <= 0:
                    return False
                scalper.position = ScalpPosition(symbol, quantity, price)
                scalper.daily_trades += 1
                print(f"    >> [DRY] 가상 매수: {symbol} {quantity}주 @ {price:,.0f}원 (약 {quantity*price/10000:.0f}만원)")
                return True
            return False

        def fake_exit(reason):
            if not scalper.position:
                return 0.0
            from datetime import datetime
            symbol = scalper.position.symbol
            entry_price = scalper.position.entry_price
            quantity = scalper.position.quantity
            price_hist = scalper.price_history.get(symbol, [])
            current_price = price_hist[-1] if price_hist else entry_price
            pnl_pct = (current_price - entry_price) / entry_price * 100
            hold_sec = scalper.position.hold_seconds
            scalper.daily_pnl += pnl_pct
            scalper.trade_log.append({
                "symbol": symbol,
                "entry_price": entry_price,
                "exit_price": current_price,
                "quantity": quantity,
                "pnl_pct": pnl_pct,
                "pnl_amount": (current_price - entry_price) * quantity,
                "hold_seconds": hold_sec,
                "reason": reason,
                "time": datetime.now().isoformat(),
            })
            pnl_amount = (current_price - entry_price) * quantity
            print(f"    >> [DRY] 가상 매도: {symbol} {quantity}주 @ {current_price:,.0f}원 | {reason} | {pnl_pct:+.2f}% ({pnl_amount:+,.0f}원) | {hold_sec:.0f}초")
            scalper.position = None
            return pnl_pct

        scalper.enter = fake_enter
        scalper.exit = fake_exit

    scalper.run(duration_minutes=args.minutes)
