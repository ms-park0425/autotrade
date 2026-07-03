"""
토스증권 Open API 클라이언트

OAuth2 Client Credentials 인증 + 시세/주문/계좌 API 래퍼
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://openapi.tossinvest.com"


class TossAPI:
    def __init__(self):
        self.client_id = os.getenv("TOSS_CLIENT_ID")
        self.client_secret = os.getenv("TOSS_CLIENT_SECRET")
        self.account_seq = int(os.getenv("TOSS_ACCOUNT_SEQ", "1"))
        self._access_token = None
        self._token_expires_at = 0

    def _ensure_token(self):
        if self._access_token and time.time() < self._token_expires_at - 60:
            return
        resp = requests.post(
            f"{BASE_URL}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data["expires_in"]

    def _headers(self, with_account=False):
        self._ensure_token()
        h = {"Authorization": f"Bearer {self._access_token}"}
        if with_account:
            h["X-Tossinvest-Account"] = str(self.account_seq)
        return h

    def _get(self, path, params=None, with_account=False):
        resp = requests.get(
            f"{BASE_URL}{path}",
            params=params,
            headers=self._headers(with_account),
        )
        resp.raise_for_status()
        return resp.json().get("result")

    def _post(self, path, json_data=None, with_account=False):
        resp = requests.post(
            f"{BASE_URL}{path}",
            json=json_data,
            headers=self._headers(with_account),
        )
        resp.raise_for_status()
        return resp.json().get("result")

    # ──────────────────────────────────────────────
    # Market Data
    # ──────────────────────────────────────────────

    def get_prices(self, symbols: list[str]) -> list[dict]:
        return self._get("/api/v1/prices", {"symbols": ",".join(symbols)})

    def get_orderbook(self, symbol: str) -> dict:
        return self._get("/api/v1/orderbook", {"symbol": symbol})

    def get_trades(self, symbol: str, count: int = 50) -> list[dict]:
        return self._get("/api/v1/trades", {"symbol": symbol, "count": count})

    def get_candles(self, symbol: str, interval: str = "1m", count: int = 60) -> dict:
        return self._get(
            "/api/v1/candles",
            {"symbol": symbol, "interval": interval, "count": count},
        )

    # ──────────────────────────────────────────────
    # Stock Info
    # ──────────────────────────────────────────────

    def get_stocks(self, symbols: list[str]) -> list[dict]:
        return self._get("/api/v1/stocks", {"symbols": ",".join(symbols)})

    def get_warnings(self, symbol: str) -> list[dict]:
        return self._get(f"/api/v1/stocks/{symbol}/warnings")

    # ──────────────────────────────────────────────
    # Market Info
    # ──────────────────────────────────────────────

    def get_market_calendar_kr(self, date: str = None) -> dict:
        params = {"date": date} if date else {}
        return self._get("/api/v1/market-calendar/KR", params)

    # ──────────────────────────────────────────────
    # Account / Asset
    # ──────────────────────────────────────────────

    def get_accounts(self) -> list[dict]:
        return self._get("/api/v1/accounts")

    def get_holdings(self, symbol: str = None) -> dict:
        params = {"symbol": symbol} if symbol else {}
        return self._get("/api/v1/holdings", params, with_account=True)

    def get_buying_power(self, currency: str = "KRW") -> dict:
        return self._get(
            "/api/v1/buying-power", {"currency": currency}, with_account=True
        )

    def get_sellable_quantity(self, symbol: str) -> dict:
        return self._get(
            "/api/v1/sellable-quantity", {"symbol": symbol}, with_account=True
        )

    # ──────────────────────────────────────────────
    # Order
    # ──────────────────────────────────────────────

    def buy_limit(self, symbol: str, quantity: int, price: int) -> dict:
        return self._post(
            "/api/v1/orders",
            {
                "symbol": symbol,
                "side": "BUY",
                "orderType": "LIMIT",
                "quantity": str(quantity),
                "price": str(price),
            },
            with_account=True,
        )

    def buy_market(self, symbol: str, quantity: int) -> dict:
        return self._post(
            "/api/v1/orders",
            {
                "symbol": symbol,
                "side": "BUY",
                "orderType": "MARKET",
                "quantity": str(quantity),
            },
            with_account=True,
        )

    def sell_limit(self, symbol: str, quantity: int, price: int) -> dict:
        return self._post(
            "/api/v1/orders",
            {
                "symbol": symbol,
                "side": "SELL",
                "orderType": "LIMIT",
                "quantity": str(quantity),
                "price": str(price),
            },
            with_account=True,
        )

    def sell_market(self, symbol: str, quantity: int) -> dict:
        return self._post(
            "/api/v1/orders",
            {
                "symbol": symbol,
                "side": "SELL",
                "orderType": "MARKET",
                "quantity": str(quantity),
            },
            with_account=True,
        )

    def cancel_order(self, order_id: str) -> dict:
        return self._post(
            f"/api/v1/orders/{order_id}/cancel", {}, with_account=True
        )

    def get_open_orders(self, symbol: str = None) -> list[dict]:
        params = {"status": "OPEN"}
        if symbol:
            params["symbol"] = symbol
        result = self._get("/api/v1/orders", params, with_account=True)
        return result.get("orders", [])
