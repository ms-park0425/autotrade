"""
실시간 데이터 수집 및 분석

토스증권 API로부터 시세 데이터를 수집하고
당일 매매에 필요한 지표를 계산합니다.
"""

from decimal import Decimal
from .toss_api import TossAPI


class DataFeed:
    def __init__(self, api: TossAPI):
        self.api = api

    def get_snapshot(self, symbol: str) -> dict:
        """종목의 현재 스냅샷 (현재가 + 호가 + 캔들)"""
        prices = self.api.get_prices([symbol])
        orderbook = self.api.get_orderbook(symbol)
        candles_data = self.api.get_candles(symbol, interval="1m", count=60)

        price_info = prices[0] if prices else {}
        candles = candles_data.get("candles", []) if candles_data else []

        last_price = Decimal(price_info.get("lastPrice", "0"))

        bid_volume = sum(Decimal(b["volume"]) for b in orderbook.get("bids", []))
        ask_volume = sum(Decimal(a["volume"]) for a in orderbook.get("asks", []))
        total_volume = bid_volume + ask_volume
        bid_ratio = float(bid_volume / total_volume * 100) if total_volume > 0 else 50.0

        return {
            "symbol": symbol,
            "last_price": float(last_price),
            "bid_ratio": bid_ratio,
            "bid_volume": float(bid_volume),
            "ask_volume": float(ask_volume),
            "orderbook": orderbook,
            "candles": candles,
        }

    def calc_change_1h(self, candles: list[dict]) -> float:
        """최근 1시간 등락률 (분봉 기준)"""
        if not candles or len(candles) < 2:
            return 0.0
        open_price = Decimal(candles[-1]["openPrice"])
        close_price = Decimal(candles[0]["closePrice"])
        if open_price == 0:
            return 0.0
        return float((close_price - open_price) / open_price * 100)

    def calc_volume_ratio(self, symbol: str) -> float:
        """전일 대비 거래량 배율 (당일 누적 vs 전일 전체)"""
        daily = self.api.get_candles(symbol, interval="1d", count=2)
        candles = daily.get("candles", []) if daily else []
        if len(candles) < 2:
            return 1.0
        today_vol = Decimal(candles[0]["volume"])
        yesterday_vol = Decimal(candles[1]["volume"])
        if yesterday_vol == 0:
            return 1.0
        return float(today_vol / yesterday_vol)

    def calc_consecutive_bullish(self, candles: list[dict], minutes: int = 5) -> int:
        """최근 N분봉 연속 양봉 수 (candles는 최신순 정렬)"""
        count = 0
        for c in candles[:minutes]:
            if Decimal(c["closePrice"]) > Decimal(c["openPrice"]):
                count += 1
            else:
                break
        return count
