"""
주문 실행 엔진

매수/매도 로직, 포지션 관리, 익절/손절/시간손절 처리
"""

import json
import os
import time
from datetime import datetime, time as dt_time
from .toss_api import TossAPI


def load_config():
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "config.json"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


class Position:
    def __init__(self, symbol: str, quantity: int, entry_price: float, entry_time: datetime):
        self.symbol = symbol
        self.quantity = quantity
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.half_sold = False


class Executor:
    def __init__(self, api: TossAPI):
        self.api = api
        self.config = load_config()
        self.positions: dict[str, Position] = {}
        self.daily_pnl = 0.0

    @property
    def max_positions(self) -> int:
        return self.config["risk"]["max_positions"]

    @property
    def max_per_trade(self) -> float:
        return self.config["risk"]["max_per_trade"]

    @property
    def daily_loss_limit(self) -> float:
        return self.config["risk"]["daily_loss_limit"]

    def can_open_position(self) -> bool:
        if len(self.positions) >= self.max_positions:
            return False
        if self.daily_pnl <= self.daily_loss_limit:
            return False
        return True

    def calc_quantity(self, price: float) -> int:
        """매수 가능 금액 기준 수량 계산"""
        bp = self.api.get_buying_power("KRW")
        buying_power = float(bp.get("cashBuyingPower", "0"))
        max_amount = buying_power * self.max_per_trade
        qty = int(max_amount / price)
        return max(qty, 0)

    def open_position(self, symbol: str, price: int) -> dict | None:
        """시장가 매수로 포지션 진입"""
        if not self.can_open_position():
            return None

        quantity = self.calc_quantity(price)
        if quantity <= 0:
            return None

        result = self.api.buy_market(symbol, quantity)
        if result:
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=price,
                entry_time=datetime.now(),
            )
        return result

    def check_exit_conditions(self, symbol: str, current_price: float) -> str | None:
        """익절/손절/시간손절 조건 확인"""
        pos = self.positions.get(symbol)
        if not pos:
            return None

        pnl_pct = (current_price - pos.entry_price) / pos.entry_price
        now = datetime.now().time()

        tp1 = self.config["trading"]["take_profit_1"]
        tp2 = self.config["trading"]["take_profit_2"]
        sl1 = self.config["trading"]["stop_loss_1"]
        sl2 = self.config["trading"]["stop_loss_2"]

        # 시간 손절
        time_stop_final = dt_time(15, 0)
        time_stop_warning = dt_time(14, 0)

        if now >= time_stop_final:
            return "TIME_STOP_FINAL"

        # 손절
        if pnl_pct <= sl2:
            return "STOP_LOSS_FULL"
        if pnl_pct <= sl1 and not pos.half_sold:
            return "STOP_LOSS_HALF"

        # 익절
        if pnl_pct >= tp2:
            return "TAKE_PROFIT_FULL"
        if pnl_pct >= tp1 and not pos.half_sold:
            return "TAKE_PROFIT_HALF"

        # 시간 경고 (수익 없으면 청산)
        if now >= time_stop_warning and pnl_pct <= 0:
            return "TIME_STOP_WARNING"

        return None

    def close_position(self, symbol: str, reason: str) -> dict | None:
        """포지션 청산"""
        pos = self.positions.get(symbol)
        if not pos:
            return None

        if reason in ("TAKE_PROFIT_HALF", "STOP_LOSS_HALF"):
            sell_qty = pos.quantity // 2
            pos.quantity -= sell_qty
            pos.half_sold = True
        else:
            sell_qty = pos.quantity
            del self.positions[symbol]

        if sell_qty <= 0:
            return None

        return self.api.sell_market(symbol, sell_qty)

    def close_all(self) -> list[dict]:
        """전체 포지션 청산 (장 마감용)"""
        results = []
        for symbol in list(self.positions.keys()):
            result = self.close_position(symbol, "TIME_STOP_FINAL")
            if result:
                results.append(result)
        return results
