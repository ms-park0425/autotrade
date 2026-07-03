#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
프리마켓 → 본장 상관관계 분석

토스 API에서 1분봉 과거 데이터를 수집하여:
- 프리마켓(08:00~09:00) 등락률/거래량
- 정규장 초반(09:00~09:30) 등락률/방향
의 상관관계를 분석합니다.

실행:
  python strategies/intraday/backtest_premarket.py
"""

import sys
import os
import io
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from strategies.intraday.engine.toss_api import TossAPI


def collect_day_candles(api: TossAPI, symbol: str, date_str: str) -> list[dict]:
    """특정 일자의 1분봉 전체 수집 (프리마켓 포함)"""
    # date_str: "2026-07-02" 형태
    # 다음날 00:00 이전까지의 봉을 가져오기 위해 before를 다음날로 설정
    next_day = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    before = f"{next_day}T00:00:00+09:00"

    all_candles = []
    max_pages = 5  # 200봉 * 5 = 1000분봉 (하루 충분)

    for _ in range(max_pages):
        try:
            result = api.get_candles(symbol, interval="1m", count=200)
            if not result:
                break
            candles = result.get("candles", [])
            if not candles:
                break

            # 해당 날짜 봉만 필터
            for c in candles:
                ts = c["timestamp"][:10]  # "2026-07-02"
                if ts == date_str:
                    all_candles.append(c)

            next_before = result.get("nextBefore")
            if not next_before:
                break

            # 다음 페이지 요청을 위해 before 파라미터 사용
            # API에 before를 넘기려면 get_candles를 확장해야 함
            break  # 단일 요청으로 최근 200봉만 사용 (오늘/어제)

        except Exception as e:
            print(f"    [에러] {symbol} 캔들 수집: {e}")
            break

    return sorted(all_candles, key=lambda x: x["timestamp"])


def collect_candles_with_before(api: TossAPI, symbol: str, before: str = None, count: int = 200) -> dict:
    """before 파라미터를 포함한 캔들 조회"""
    import requests
    from dotenv import load_dotenv

    load_dotenv()
    api._ensure_token()

    params = {"symbol": symbol, "interval": "1m", "count": count}
    if before:
        params["before"] = before

    resp = requests.get(
        f"https://openapi.tossinvest.com/api/v1/candles",
        params=params,
        headers=api._headers(),
    )
    resp.raise_for_status()
    return resp.json().get("result", {})


def collect_full_day(api: TossAPI, symbol: str, target_date: str) -> list[dict]:
    """특정 날짜의 1분봉 전체 수집 (페이지네이션 사용)"""
    all_candles = []
    before = None
    next_date = (datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    before = f"{next_date}T00:00:00+09:00"

    for page in range(5):
        try:
            result = collect_candles_with_before(api, symbol, before=before, count=200)
            candles = result.get("candles", [])
            if not candles:
                break

            for c in candles:
                ts_date = c["timestamp"][:10]
                if ts_date == target_date:
                    all_candles.append(c)
                elif ts_date < target_date:
                    # 이전 날짜에 도달, 중단
                    return sorted(all_candles, key=lambda x: x["timestamp"])

            next_before = result.get("nextBefore")
            if not next_before:
                break
            before = next_before

            time.sleep(0.5)  # Rate limit 배려

        except Exception as e:
            print(f"    [에러] {symbol} page {page}: {e}")
            break

    return sorted(all_candles, key=lambda x: x["timestamp"])


def analyze_premarket_pattern(candles: list[dict]) -> dict | None:
    """하루치 1분봉에서 프리마켓/본장 초반 패턴 추출"""
    premarket = []  # 08:00~09:00
    regular_early = []  # 09:00~09:30
    regular_mid = []  # 09:00~10:00

    for c in candles:
        ts = c["timestamp"]
        hour_min = ts[11:16]  # "HH:MM"

        if "08:00" <= hour_min < "09:00":
            premarket.append(c)
        elif "09:00" <= hour_min < "09:30":
            regular_early.append(c)
        elif "09:00" <= hour_min < "10:00":
            regular_mid.append(c)

    if not premarket or not regular_early:
        return None

    # 프리마켓 분석
    pm_open = Decimal(premarket[0]["openPrice"])
    pm_close = Decimal(premarket[-1]["closePrice"])
    pm_high = max(Decimal(c["highPrice"]) for c in premarket)
    pm_low = min(Decimal(c["lowPrice"]) for c in premarket)
    pm_volume = sum(int(c["volume"]) for c in premarket)
    pm_change = float((pm_close - pm_open) / pm_open * 100) if pm_open > 0 else 0

    # 정규장 초반 (09:00~09:30)
    re_open = Decimal(regular_early[0]["openPrice"])
    re_close = Decimal(regular_early[-1]["closePrice"])
    re_high = max(Decimal(c["highPrice"]) for c in regular_early)
    re_low = min(Decimal(c["lowPrice"]) for c in regular_early)
    re_volume = sum(int(c["volume"]) for c in regular_early)
    re_change = float((re_close - re_open) / re_open * 100) if re_open > 0 else 0

    # 갭 (프리마켓 종가 vs 정규장 시가)
    gap = float((re_open - pm_close) / pm_close * 100) if pm_close > 0 else 0

    # 정규장 1시간 (09:00~10:00)
    if regular_mid:
        rm_open = Decimal(regular_mid[0]["openPrice"])
        rm_close = Decimal(regular_mid[-1]["closePrice"])
        rm_change = float((rm_close - rm_open) / rm_open * 100) if rm_open > 0 else 0
    else:
        rm_change = re_change

    return {
        "premarket_change": pm_change,
        "premarket_volume": pm_volume,
        "premarket_candle_count": len(premarket),
        "gap": gap,
        "regular_30m_change": re_change,
        "regular_1h_change": rm_change,
        "regular_early_volume": re_volume,
    }


def run_backtest():
    api = TossAPI()

    # 코스피 거래량 상위 15개
    kospi_symbols = [
        "005930",  # 삼성전자
        "000660",  # SK하이닉스
        "005380",  # 현대차
        "068270",  # 셀트리온
        "000270",  # 기아
        "009150",  # 삼성전기
        "028260",  # 삼성물산
        "012330",  # 현대모비스
        "066570",  # LG전자
        "034020",  # 두산에너빌리티
        "010130",  # 고려아연
        "006400",  # 삼성SDI
        "011200",  # HMM
        "003490",  # 대한항공
        "055550",  # 신한지주
    ]

    # 코스닥 거래량 상위 15개
    kosdaq_symbols = [
        "247540",  # 에코프로비엠
        "086520",  # 에코프로
        "042700",  # 한미반도체
        "003670",  # 포스코퓨처엠
        "035420",  # NAVER
        "035720",  # 카카오
        "259960",  # 크래프톤
        "377300",  # 카카오페이
        "352820",  # 하이브
        "293490",  # 카카오뱅크
        "036570",  # 엔씨소프트
        "328130",  # 루닛
        "403870",  # HPSP
        "058470",  # 리노공업
        "357780",  # 솔브레인
    ]

    all_symbols = kospi_symbols + kosdaq_symbols

    # NXT 프리마켓 거래 가능한 종목만 필터
    print("  NXT 지원 종목 확인 중...")
    symbols = []
    for i in range(0, len(all_symbols), 200):
        batch = all_symbols[i:i+200]
        try:
            stocks_info = api.get_stocks(batch)
            for s in stocks_info:
                detail = s.get("koreanMarketDetail")
                if detail and detail.get("nxtSupported"):
                    symbols.append(s["symbol"])
                else:
                    print(f"    {s['symbol']} ({s['name']}): NXT 미지원 → 제외")
        except Exception as e:
            print(f"    [에러] 종목 정보 조회: {e}")
            symbols = all_symbols
            break

    print(f"  NXT 지원 종목: {len(symbols)}/{len(all_symbols)}개\n")

    # 최근 영업일 계산 (오늘 제외, 최근 5일)
    today = datetime.now()
    dates = []
    d = today - timedelta(days=1)
    while len(dates) < 5:
        if d.weekday() < 5:  # 평일만
            dates.append(d.strftime("%Y-%m-%d"))
        d -= timedelta(days=1)

    print("=" * 70)
    print("  프리마켓 → 본장 상관관계 분석")
    print("=" * 70)
    print(f"  분석 종목: {len(symbols)}개")
    print(f"  분석 기간: {dates[-1]} ~ {dates[0]}")
    print(f"  분석 내용: 프리마켓(08~09) 등락 vs 본장 초반(09~10) 등락")
    print("=" * 70)

    results = []

    for symbol in symbols:
        print(f"\n  [{symbol}] 데이터 수집 중...")

        for date in dates:
            try:
                candles = collect_full_day(api, symbol, date)
                if not candles:
                    print(f"    {date}: 데이터 없음")
                    continue

                pattern = analyze_premarket_pattern(candles)
                if not pattern:
                    print(f"    {date}: 프리마켓 데이터 없음")
                    continue

                pattern["symbol"] = symbol
                pattern["date"] = date
                results.append(pattern)

                pm = pattern["premarket_change"]
                gap = pattern["gap"]
                r30 = pattern["regular_30m_change"]
                r1h = pattern["regular_1h_change"]

                print(f"    {date}: PM {pm:+.2f}% | 갭 {gap:+.2f}% | 30분 {r30:+.2f}% | 1시간 {r1h:+.2f}%")

                time.sleep(1)  # Rate limit

            except Exception as e:
                print(f"    {date}: 에러 - {e}")
                time.sleep(2)

    # ──────────────────────────────────────────────
    # 분석 결과 요약
    # ──────────────────────────────────────────────
    if not results:
        print("\n  수집된 데이터가 없습니다.")
        return

    # 코스피/코스닥 분리
    kospi_set = set(kospi_symbols)
    for r in results:
        r["market"] = "KOSPI" if r["symbol"] in kospi_set else "KOSDAQ"

    print("\n")
    print("=" * 70)
    print("  분석 결과")
    print("=" * 70)

    # 시장별 분리 분석
    for market_name, market_results in [("전체", results), ("KOSPI", [r for r in results if r["market"] == "KOSPI"]), ("KOSDAQ", [r for r in results if r["market"] == "KOSDAQ"])]:
        if not market_results:
            continue

        print(f"\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  【{market_name}】 ({len(market_results)}건)")
        print(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # 1) 프리마켓 상승 vs 본장 방향
        pm_up = [r for r in market_results if r["premarket_change"] > 0.5]
        pm_down = [r for r in market_results if r["premarket_change"] < -0.5]
        pm_flat = [r for r in market_results if -0.5 <= r["premarket_change"] <= 0.5]

        print(f"\n  [1] 프리마켓 등락 → 본장 30분 방향")
        print(f"  {'─' * 50}")

        if pm_up:
            up_then_up = len([r for r in pm_up if r["regular_30m_change"] > 0])
            avg_r30 = sum(r["regular_30m_change"] for r in pm_up) / len(pm_up)
            avg_pm = sum(r["premarket_change"] for r in pm_up) / len(pm_up)
            print(f"  프리마켓 상승 ({len(pm_up)}건): 평균 PM +{avg_pm:.2f}%")
            print(f"    → 본장 30분도 상승: {up_then_up}/{len(pm_up)} ({up_then_up/len(pm_up)*100:.0f}%)")
            print(f"    → 본장 30분 평균: {avg_r30:+.2f}%")

        if pm_down:
            down_then_down = len([r for r in pm_down if r["regular_30m_change"] < 0])
            avg_r30 = sum(r["regular_30m_change"] for r in pm_down) / len(pm_down)
            avg_pm = sum(r["premarket_change"] for r in pm_down) / len(pm_down)
            print(f"\n  프리마켓 하락 ({len(pm_down)}건): 평균 PM {avg_pm:.2f}%")
            print(f"    → 본장 30분도 하락: {down_then_down}/{len(pm_down)} ({down_then_down/len(pm_down)*100:.0f}%)")
            print(f"    → 본장 30분 평균: {avg_r30:+.2f}%")

        if pm_flat:
            avg_r30 = sum(r["regular_30m_change"] for r in pm_flat) / len(pm_flat)
            print(f"\n  프리마켓 보합 ({len(pm_flat)}건):")
            print(f"    → 본장 30분 평균: {avg_r30:+.2f}%")

        # 2) 갭 분석
        print(f"\n  [2] 갭(프리마켓 종가 vs 시초가) → 본장 방향")
        print(f"  {'─' * 50}")

        gap_up = [r for r in market_results if r["gap"] > 0.3]
        gap_down = [r for r in market_results if r["gap"] < -0.3]

        if gap_up:
            gap_up_continue = len([r for r in gap_up if r["regular_30m_change"] > 0])
            avg_gap = sum(r["gap"] for r in gap_up) / len(gap_up)
            avg_r30 = sum(r["regular_30m_change"] for r in gap_up) / len(gap_up)
            print(f"  갭상승 ({len(gap_up)}건): 평균 갭 +{avg_gap:.2f}%")
            print(f"    → 30분 추가 상승: {gap_up_continue}/{len(gap_up)} ({gap_up_continue/len(gap_up)*100:.0f}%)")
            print(f"    → 30분 평균: {avg_r30:+.2f}%")

        if gap_down:
            gap_down_continue = len([r for r in gap_down if r["regular_30m_change"] < 0])
            avg_gap = sum(r["gap"] for r in gap_down) / len(gap_down)
            avg_r30 = sum(r["regular_30m_change"] for r in gap_down) / len(gap_down)
            print(f"\n  갭하락 ({len(gap_down)}건): 평균 갭 {avg_gap:.2f}%")
            print(f"    → 30분 추가 하락: {gap_down_continue}/{len(gap_down)} ({gap_down_continue/len(gap_down)*100:.0f}%)")
            print(f"    → 30분 평균: {avg_r30:+.2f}%")

        # 3) 프리마켓 거래량 → 본장 변동성
        print(f"\n  [3] 프리마켓 거래량 → 본장 변동성")
        print(f"  {'─' * 50}")

        vol_sorted = sorted(market_results, key=lambda x: x["premarket_volume"], reverse=True)
        third = max(len(vol_sorted) // 3, 1)
        high_vol = vol_sorted[:third]
        low_vol = vol_sorted[-third:]

        if high_vol:
            avg_r1h = sum(abs(r["regular_1h_change"]) for r in high_vol) / len(high_vol)
            print(f"  프리마켓 거래량 상위 ({len(high_vol)}건):")
            print(f"    → 본장 1시간 평균 변동폭: {avg_r1h:.2f}%")

        if low_vol:
            avg_r1h = sum(abs(r["regular_1h_change"]) for r in low_vol) / len(low_vol)
            print(f"  프리마켓 거래량 하위 ({len(low_vol)}건):")
            print(f"    → 본장 1시간 평균 변동폭: {avg_r1h:.2f}%")

        # 4) 최적 진입 조건 도출
        print(f"\n  [4] 최적 진입 시그널 후보")
        print(f"  {'─' * 50}")

        strong_signal = [r for r in market_results if r["premarket_change"] > 1.0 and r["gap"] > 0]
        if strong_signal:
            win = len([r for r in strong_signal if r["regular_1h_change"] > 1.0])
            avg_r1h = sum(r["regular_1h_change"] for r in strong_signal) / len(strong_signal)
            print(f"  PM +1%↑ AND 갭상승 ({len(strong_signal)}건):")
            print(f"    → 본장 1시간 +1% 이상: {win}/{len(strong_signal)} ({win/len(strong_signal)*100:.0f}%)")
            print(f"    → 본장 1시간 평균: {avg_r1h:+.2f}%")

        vol_median = sorted(r["premarket_volume"] for r in market_results)[len(market_results)//2]
        vol_up_signal = [r for r in market_results if r["premarket_volume"] > vol_median and r["premarket_change"] > 0.5]
        if vol_up_signal:
            win = len([r for r in vol_up_signal if r["regular_1h_change"] > 0])
            avg_r1h = sum(r["regular_1h_change"] for r in vol_up_signal) / len(vol_up_signal)
            print(f"\n  PM 거래량 중앙값↑ AND PM 상승 ({len(vol_up_signal)}건):")
            print(f"    → 본장 1시간 상승: {win}/{len(vol_up_signal)} ({win/len(vol_up_signal)*100:.0f}%)")
            print(f"    → 본장 1시간 평균: {avg_r1h:+.2f}%")

    # 결과 저장
    output_path = os.path.join(os.path.dirname(__file__), "data", "premarket_analysis.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  결과 저장: {output_path}")

    print(f"\n{'=' * 70}")
    print(f"  총 {len(results)}건 분석 완료")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    run_backtest()
