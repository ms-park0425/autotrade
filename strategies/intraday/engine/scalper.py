"""
1분봉 스캘핑 엔진

전략: 거래량 급증 + 가격 상방돌파 감지 → 시장가 매수 → 2~3% 익절 / 1% 손절 / 3분 시간제한
대상: 코스피 변동성 상위 10종목
"""

import time
import json
import os
from datetime import datetime, time as dt_time, timedelta
from decimal import Decimal
from .toss_api import TossAPI


# 스캘핑 대상 (코스피 거래량+변동성 상위)
SCALP_TARGETS = [
    "005930",  # 삼성전자
    "034020",  # 두산에너빌리티
    "000660",  # SK하이닉스
    "009150",  # 삼성전기
    "028260",  # 삼성물산
    "066570",  # LG전자
    "068270",  # 셀트리온
    "003490",  # 대한항공
    "006400",  # 삼성SDI
    "005380",  # 현대차
]

# 설정
TAKE_PROFIT = 0.025      # +2.5% 익절
STOP_LOSS = -0.01        # -1% 손절
MAX_HOLD_SECONDS = 180   # 3분 시간제한
STRENGTH_THRESHOLD = 200 # 체결강도 200% 이상 (매수가 매도의 2배)
POLL_INTERVAL = 1.0      # 1초마다 폴링


class ScalpPosition:
    def __init__(self, symbol: str, quantity: int, entry_price: float):
        self.symbol = symbol
        self.quantity = quantity
        self.entry_price = entry_price
        self.entry_time = datetime.now()

    @property
    def hold_seconds(self) -> float:
        return (datetime.now() - self.entry_time).total_seconds()


class Scalper:
    def __init__(self, api: TossAPI, max_per_trade: float = 0.10):
        self.api = api
        self.max_per_trade = max_per_trade
        self.position: ScalpPosition | None = None
        self.trade_log: list[dict] = []
        self.daily_pnl = 0.0
        self.daily_trades = 0

        # 종목별 체결강도 히스토리
        self.strength_history: dict[str, list[float]] = {s: [] for s in SCALP_TARGETS}
        # 종목별 최근 가격
        self.price_history: dict[str, list[float]] = {s: [] for s in SCALP_TARGETS}

    def update_market_data(self, symbol: str) -> dict | None:
        """종목 시세 업데이트 (1초마다 호출)"""
        try:
            # 최근 체결 50건
            trades = self.api.get_trades(symbol, count=50)
            if not trades or len(trades) < 3:
                return None

            latest_price = float(trades[0]["price"])

            # 체결강도 계산: 가격 상승 체결 = 매수, 하락 체결 = 매도
            buy_volume = 0
            sell_volume = 0
            for i in range(len(trades) - 1):
                vol = int(trades[i]["volume"])
                curr_price = float(trades[i]["price"])
                prev_price = float(trades[i + 1]["price"])
                if curr_price > prev_price:
                    buy_volume += vol
                elif curr_price < prev_price:
                    sell_volume += vol
                else:
                    # 동일가: 직전 방향 유지 대신 반반
                    buy_volume += vol // 2
                    sell_volume += vol // 2

            strength = (buy_volume / sell_volume * 100) if sell_volume > 0 else 999

            # 히스토리 누적
            self.strength_history[symbol].append(strength)
            if len(self.strength_history[symbol]) > 60:
                self.strength_history[symbol] = self.strength_history[symbol][-60:]

            self.price_history[symbol].append(latest_price)
            if len(self.price_history[symbol]) > 60:
                self.price_history[symbol] = self.price_history[symbol][-60:]

            return {
                "symbol": symbol,
                "price": latest_price,
                "strength": strength,
            }
        except Exception:
            return None

    def check_entry_signal(self, symbol: str) -> bool:
        """진입 시그널: 체결강도 상승 + 가격 상방돌파"""
        str_hist = self.strength_history[symbol]
        price_hist = self.price_history[symbol]

        if len(str_hist) < 2 or len(price_hist) < 3:
            return False

        # 체결강도 상승 중 (직전보다 올라가고 있음)
        if not (str_hist[-1] > str_hist[-2]):
            return False

        # 가격 상방돌파: 현재가 > 직전 2개 고가
        current_price = price_hist[-1]
        recent_high = max(price_hist[-3:-1])

        if current_price <= recent_high:
            return False

        return True

    def check_exit_signal(self) -> str | None:
        """청산 시그널 체크"""
        if not self.position:
            return None

        symbol = self.position.symbol
        price_hist = self.price_history.get(symbol, [])
        if not price_hist:
            return None

        current_price = price_hist[-1]
        entry_price = self.position.entry_price
        pnl_pct = (current_price - entry_price) / entry_price

        # 익절
        if pnl_pct >= TAKE_PROFIT:
            return "TAKE_PROFIT"

        # 손절
        if pnl_pct <= STOP_LOSS:
            return "STOP_LOSS"

        # 시간제한
        if self.position.hold_seconds >= MAX_HOLD_SECONDS:
            return "TIME_STOP"

        return None

    def calc_quantity(self, price: float) -> int:
        """매수 수량 계산"""
        try:
            bp = self.api.get_buying_power("KRW")
            buying_power = float(bp.get("cashBuyingPower", "0"))
            max_amount = buying_power * self.max_per_trade
            return max(int(max_amount / price), 0)
        except Exception:
            return 0

    def enter(self, symbol: str) -> bool:
        """시장가 매수"""
        if self.position:
            return False

        price_hist = self.price_history.get(symbol, [])
        if not price_hist:
            return False

        price = price_hist[-1]
        quantity = self.calc_quantity(price)
        if quantity <= 0:
            return False

        try:
            result = self.api.buy_market(symbol, quantity)
            if result:
                self.position = ScalpPosition(symbol, quantity, price)
                self.daily_trades += 1
                print(f"    >> 매수: {symbol} {quantity}주 @ {price:,.0f}원")
                return True
        except Exception as e:
            print(f"    >> 매수 실패: {e}")

        return False

    def exit(self, reason: str) -> float:
        """시장가 매도, 손익 반환"""
        if not self.position:
            return 0.0

        symbol = self.position.symbol
        quantity = self.position.quantity
        entry_price = self.position.entry_price
        price_hist = self.price_history.get(symbol, [])
        current_price = price_hist[-1] if price_hist else entry_price

        try:
            self.api.sell_market(symbol, quantity)
        except Exception as e:
            print(f"    >> 매도 실패: {e}")
            return 0.0

        pnl_pct = (current_price - entry_price) / entry_price * 100
        pnl_amount = (current_price - entry_price) * quantity
        hold_sec = self.position.hold_seconds

        self.daily_pnl += pnl_pct
        self.trade_log.append({
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": current_price,
            "quantity": quantity,
            "pnl_pct": pnl_pct,
            "pnl_amount": pnl_amount,
            "hold_seconds": hold_sec,
            "reason": reason,
            "time": datetime.now().isoformat(),
        })

        reason_emoji = {"TAKE_PROFIT": "✅", "STOP_LOSS": "⛔", "TIME_STOP": "⏰"}
        print(f"    >> 매도: {symbol} @ {current_price:,.0f}원 "
              f"| {reason_emoji.get(reason, '')} {reason} "
              f"| {pnl_pct:+.2f}% ({pnl_amount:+,.0f}원) "
              f"| {hold_sec:.0f}초 보유")

        self.position = None
        return pnl_pct

    def run(self, duration_minutes: int = None):
        """스캘핑 메인 루프"""
        import sys
        print("=" * 70)
        print("  1분봉 스캘핑 시작")
        print("=" * 70)
        print(f"  대상: {', '.join(SCALP_TARGETS[:5])}...")
        print(f"  익절: +{TAKE_PROFIT*100:.1f}% | 손절: {STOP_LOSS*100:.1f}% | 시간제한: {MAX_HOLD_SECONDS}초")
        print(f"  체결강도 기준: {STRENGTH_THRESHOLD}%")
        print(f"  시작: {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 70)

        start_time = datetime.now()
        scan_count = 0

        try:
            while True:
                now = datetime.now()

                # 장 시간 체크 (09:00~15:20)
                if not (dt_time(9, 0) <= now.time() <= dt_time(15, 20)):
                    if now.time() > dt_time(15, 20):
                        break
                    time.sleep(1)
                    continue

                # 시간 제한
                if duration_minutes:
                    elapsed = (now - start_time).total_seconds() / 60
                    if elapsed >= duration_minutes:
                        break

                # 일일 손실 제한 (-5%)
                if self.daily_pnl <= -5.0:
                    print("\n  [중단] 일일 손실 한도 -5% 도달")
                    break

                scan_count += 1

                # 포지션 보유 중 → 청산 체크
                if self.position:
                    self.update_market_data(self.position.symbol)
                    exit_signal = self.check_exit_signal()
                    if exit_signal:
                        self.exit(exit_signal)
                    time.sleep(POLL_INTERVAL)
                    continue

                # 포지션 없음 → 진입 시그널 탐색
                for symbol in SCALP_TARGETS:
                    data = self.update_market_data(symbol)
                    if not data:
                        continue

                    if self.check_entry_signal(symbol):
                        print(f"\n  [{now.strftime('%H:%M:%S')}] 시그널 감지: {symbol} "
                              f"@ {data['price']:,.0f}원")
                        self.enter(symbol)
                        if self.position:
                            break

                    time.sleep(0.1)  # Rate limit 배려

                # 1분마다 생존 표시
                if scan_count % 60 == 0:
                    ts = now.strftime('%H:%M:%S')
                    print(f"  [{ts}] 감시중... 거래 {self.daily_trades}건 | 손익 {self.daily_pnl:+.2f}%")
                    sys.stdout.flush()

                time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n  [중단] Ctrl+C")

        # 잔여 포지션 청산
        if self.position:
            print("\n  잔여 포지션 청산...")
            self.exit("FORCE_CLOSE")

        # 결과 요약
        self._print_summary()

    def _print_summary(self):
        """거래 결과 요약"""
        print("\n" + "=" * 70)
        print("  스캘핑 결과")
        print("=" * 70)
        print(f"  총 거래: {self.daily_trades}건")
        print(f"  총 손익: {self.daily_pnl:+.2f}%")

        if self.trade_log:
            wins = [t for t in self.trade_log if t["pnl_pct"] > 0]
            losses = [t for t in self.trade_log if t["pnl_pct"] <= 0]
            print(f"  승: {len(wins)}건 | 패: {len(losses)}건 | "
                  f"승률: {len(wins)/len(self.trade_log)*100:.0f}%")

            if wins:
                avg_win = sum(t["pnl_pct"] for t in wins) / len(wins)
                print(f"  평균 수익: +{avg_win:.2f}%")
            if losses:
                avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses)
                print(f"  평균 손실: {avg_loss:.2f}%")

            avg_hold = sum(t["hold_seconds"] for t in self.trade_log) / len(self.trade_log)
            print(f"  평균 보유: {avg_hold:.0f}초")

            total_amount = sum(t["pnl_amount"] for t in self.trade_log)
            print(f"  총 손익금: {total_amount:+,.0f}원")

        # 로그 저장
        log_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"scalp_{datetime.now().strftime('%Y%m%d')}.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.trade_log, f, ensure_ascii=False, indent=2)
        print(f"\n  로그 저장: {log_path}")
        print("=" * 70)
