#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
당일 매매 실시간 모니터링

실행:
  python strategies/intraday/run_monitor.py

동작:
  - 9:00 장 시작과 동시에 실시간 모니터링
  - 1분마다 급등 종목 스캔
  - 조건 충족 시 즉시 텔레그램 알림
  - 보유 포지션 익절/손절 자동 처리
"""

import sys
import os
import io
import time
import json
from datetime import datetime, time as dt_time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from strategies.intraday.engine.toss_api import TossAPI
from strategies.intraday.engine.data_feed import DataFeed
from strategies.intraday.engine.scorer import score_candidate, load_config
from strategies.intraday.engine.executor import Executor


def is_market_time():
    now = datetime.now()
    current_time = now.time()
    return dt_time(9, 0) <= current_time <= dt_time(15, 30)


def load_scan_universe() -> list[str]:
    """스캔 대상 종목 로드 (시가총액 상위 + 거래대금 상위)"""
    # TODO: 실제로는 KRX에서 당일 거래대금 상위 종목을 가져와야 함
    # 우선 수동 리스트로 시작, 추후 동적으로 교체
    universe_path = os.path.join(
        os.path.dirname(__file__), "config", "universe.json"
    )
    if os.path.exists(universe_path):
        with open(universe_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def send_alert(candidate: dict):
    """급등 알림 텔레그램 전송"""
    try:
        from strategies.common import telegram_notifier

        msg = f"🚨 <b>급등 알림!</b>\n\n"
        msg += f"<b>{candidate.get('name', candidate['symbol'])}</b> ({candidate['symbol']})\n"
        msg += f"📊 현재가: {candidate['last_price']:,.0f}원 ({candidate['change_1h']:+.1f}%)\n"
        msg += f"🕐 시간: {datetime.now().strftime('%H:%M')}\n\n"
        msg += f"📈 거래량: 전일 대비 {candidate['volume_ratio']:.1f}배\n"
        msg += f"💰 호가창: 매수 {candidate['bid_ratio']:.0f}% 우위\n"
        msg += f"📊 연속 양봉: {candidate['consecutive_bullish']}개\n\n"
        msg += f"⚡ 점수: {candidate['score']:.0f}점\n"
        msg += f"  ├─ 차트: {candidate['chart_score']:.0f}점\n"
        msg += f"  ├─ 거래량: {candidate['volume_score']:.0f}점\n"
        msg += f"  └─ 호가창: {candidate['order_score']:.0f}점"

        telegram_notifier.send_telegram_message(msg, parse_mode="HTML")
        print(f"  [알림] 텔레그램 전송: {candidate['symbol']}")
    except Exception as e:
        print(f"  [알림] 전송 실패: {e}")


def send_exit_alert(symbol: str, reason: str):
    """청산 알림"""
    try:
        from strategies.common import telegram_notifier

        reason_map = {
            "TAKE_PROFIT_HALF": "✅ 익절 50% (+5%)",
            "TAKE_PROFIT_FULL": "✅ 익절 100% (+7%)",
            "STOP_LOSS_HALF": "⛔ 손절 50% (-2%)",
            "STOP_LOSS_FULL": "⛔ 손절 100% (-3%)",
            "TIME_STOP_WARNING": "⏰ 시간손절 (14시, 수익없음)",
            "TIME_STOP_FINAL": "⏰ 장마감 청산 (15시)",
        }
        msg = f"📤 <b>포지션 청산</b>\n\n"
        msg += f"종목: {symbol}\n"
        msg += f"사유: {reason_map.get(reason, reason)}\n"
        msg += f"시각: {datetime.now().strftime('%H:%M:%S')}"

        telegram_notifier.send_telegram_message(msg, parse_mode="HTML")
    except Exception:
        pass


def run_monitor(auto_trade: bool = False):
    """실시간 모니터링 메인 루프"""
    api = TossAPI()
    feed = DataFeed(api)
    executor = Executor(api)
    config = load_config()

    scan_interval = config.get("monitoring", {}).get("scan_interval_seconds", 60)
    min_score = config.get("filters", {}).get("min_score", 60.0)
    min_change = config.get("filters", {}).get("min_change_1h", 3.0)
    min_volume = config.get("filters", {}).get("min_volume_ratio", 2.0)
    min_bid = config.get("filters", {}).get("min_bid_ratio", 0.55)

    print("=" * 70)
    print("  당일 매매 실시간 모니터링")
    print("=" * 70)
    print(f"  시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  스캔 간격: {scan_interval}초")
    print(f"  자동매매: {'ON' if auto_trade else 'OFF (알림만)'}")
    print(f"  필터: 등락 {min_change}%+, 거래량 {min_volume}배+, 매수비율 {min_bid*100}%+")
    print(f"  최소점수: {min_score}점")
    print("=" * 70)

    # 장 시작 대기
    while not is_market_time():
        now = datetime.now()
        if now.time() < dt_time(9, 0):
            wait = (datetime.combine(now.date(), dt_time(9, 0)) - now).total_seconds()
            print(f"  [대기] 09:00까지 {int(wait)}초...")
            time.sleep(min(60, wait))
        else:
            print("  [종료] 장 마감 시간")
            return

    print(f"\n  [시작] 모니터링 개시 - {datetime.now().strftime('%H:%M:%S')}")

    universe = load_scan_universe()
    if not universe:
        print("  [경고] universe.json이 없습니다. config/universe.json에 종목코드 리스트를 넣어주세요.")
        return

    alerted = set()

    try:
        while is_market_time():
            now_str = datetime.now().strftime('%H:%M:%S')
            print(f"\n  [{now_str}] 스캔 중... ({len(universe)}종목)")

            # 1) 보유 포지션 체크 (익절/손절)
            for symbol in list(executor.positions.keys()):
                try:
                    prices = api.get_prices([symbol])
                    if not prices:
                        continue
                    current = float(prices[0]["lastPrice"])
                    reason = executor.check_exit_conditions(symbol, current)
                    if reason:
                        print(f"    [{symbol}] 청산: {reason}")
                        executor.close_position(symbol, reason)
                        send_exit_alert(symbol, reason)
                except Exception as e:
                    print(f"    [{symbol}] 포지션 체크 실패: {e}")

            # 2) 신규 종목 스캔
            # 현재가를 배치로 조회 (최대 200개씩)
            for i in range(0, len(universe), 200):
                batch = universe[i:i+200]
                try:
                    prices = api.get_prices(batch)
                except Exception as e:
                    print(f"    [에러] 현재가 조회 실패: {e}")
                    continue

                for price_info in (prices or []):
                    symbol = price_info["symbol"]
                    if symbol in alerted:
                        continue

                    try:
                        snapshot = feed.get_snapshot(symbol)
                        candles = snapshot["candles"]
                        change_1h = feed.calc_change_1h(candles)

                        # 빠른 필터
                        if change_1h < min_change:
                            continue

                        volume_ratio = feed.calc_volume_ratio(symbol)
                        if volume_ratio < min_volume:
                            continue

                        bid_ratio = snapshot["bid_ratio"]
                        if bid_ratio < min_bid * 100:
                            continue

                        consecutive = feed.calc_consecutive_bullish(candles)

                        scores = score_candidate(
                            change_1h=change_1h,
                            consecutive_bullish=consecutive,
                            volume_ratio=volume_ratio,
                            bid_ratio=bid_ratio,
                        )

                        if scores["total"] >= min_score:
                            candidate = {
                                "symbol": symbol,
                                "last_price": snapshot["last_price"],
                                "change_1h": change_1h,
                                "volume_ratio": volume_ratio,
                                "bid_ratio": bid_ratio,
                                "consecutive_bullish": consecutive,
                                "score": scores["total"],
                                "chart_score": scores["chart_score"],
                                "volume_score": scores["volume_score"],
                                "order_score": scores["order_score"],
                            }

                            print(f"    >> {symbol} | {change_1h:+.1f}% | 거래량 {volume_ratio:.1f}x | 점수 {scores['total']:.0f}")
                            alerted.add(symbol)
                            send_alert(candidate)

                            # 자동매매 모드
                            if auto_trade and executor.can_open_position():
                                price = int(snapshot["last_price"])
                                result = executor.open_position(symbol, price)
                                if result:
                                    print(f"    >> 매수 실행: {symbol} @ {price:,}원")

                    except Exception as e:
                        continue

            time.sleep(scan_interval)

    except KeyboardInterrupt:
        print("\n\n  [중단] Ctrl+C")

    # 장 마감 전 전량 청산
    if auto_trade and executor.positions:
        print("\n  [마감] 전체 포지션 청산...")
        executor.close_all()

    print("\n  [종료] 모니터링 종료")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="당일 매매 실시간 모니터링")
    parser.add_argument("--auto-trade", action="store_true", help="자동매매 활성화 (기본: 알림만)")
    parser.add_argument("--test", action="store_true", help="API 연결 테스트만 실행")
    args = parser.parse_args()

    if args.test:
        print("토스증권 API 연결 테스트...")
        try:
            api = TossAPI()
            accounts = api.get_accounts()
            print(f"  계좌 조회 성공: {accounts}")
            bp = api.get_buying_power("KRW")
            print(f"  매수가능금액: {bp}")
            prices = api.get_prices(["005930"])
            print(f"  삼성전자 현재가: {prices}")
            print("\nAPI 연결 정상!")
        except Exception as e:
            print(f"\n  연결 실패: {e}")
            print("  .env의 TOSS_CLIENT_ID, TOSS_CLIENT_SECRET을 확인하세요.")
    else:
        run_monitor(auto_trade=args.auto_trade)
