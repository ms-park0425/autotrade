"""
당일 매매 스코어링 엔진

config.json의 점수 체계에 따라 종목 점수를 산출합니다.
- 차트 패턴: 40점
- 거래량: 30점
- 호가창: 20점
- 테마/재료: 10점 (현재 미구현, 추후 확장)
"""

import json
import os


def load_config():
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "config.json"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def score_chart(change_1h: float, consecutive_bullish: int) -> float:
    """차트 패턴 점수 (최대 40점)"""
    score = 0.0

    if change_1h >= 5.0:
        score += 20
    elif change_1h >= 3.0:
        score += 12
    elif change_1h >= 2.0:
        score += 8

    if consecutive_bullish >= 5:
        score += 10
    elif consecutive_bullish >= 3:
        score += 7
    elif consecutive_bullish >= 2:
        score += 4

    # 지속 상승 보너스
    if change_1h >= 5.0 and consecutive_bullish >= 3:
        score += 10

    return min(score, 40.0)


def score_volume(volume_ratio: float) -> float:
    """거래량 점수 (최대 30점)"""
    if volume_ratio >= 5.0:
        return 25.0
    elif volume_ratio >= 3.0:
        return 18.0
    elif volume_ratio >= 2.0:
        return 12.0
    elif volume_ratio >= 1.5:
        return 5.0
    return 0.0


def score_orderbook(bid_ratio: float) -> float:
    """호가창 점수 (최대 20점)"""
    if bid_ratio >= 70:
        return 15.0
    elif bid_ratio >= 60:
        return 10.0
    elif bid_ratio >= 55:
        return 5.0
    return 0.0


def score_candidate(
    change_1h: float,
    consecutive_bullish: int,
    volume_ratio: float,
    bid_ratio: float,
) -> dict:
    """종목 종합 점수 산출"""
    chart = score_chart(change_1h, consecutive_bullish)
    volume = score_volume(volume_ratio)
    orderbook = score_orderbook(bid_ratio)
    theme = 0.0  # 추후 뉴스/테마 분석 연동

    total = chart + volume + orderbook + theme

    return {
        "total": total,
        "chart_score": chart,
        "volume_score": volume,
        "order_score": orderbook,
        "theme_score": theme,
    }
