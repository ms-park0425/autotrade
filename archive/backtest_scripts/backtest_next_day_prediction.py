#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
"다음날 오를 종목" 예측 팩터 검증

가설 검증:
1. 전날 외국인+기관 동반 순매수 → 다음날 상승률?
2. 전날 장마감 거래량 급증 → 다음날 상승률?
3. 전날 테마 HOT → 다음날 상승률?
4. 전날 RSI 과매도 → 다음날 반등률?

방법:
- 과거 3개월 데이터 수집
- 각 신호별 다음날 수익률 통계
- 승률, 평균 수익률, 샤프비율 계산
"""

import sys
import os
import io
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "symposium"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fetch_investor_flow_historical(code: str, days: int = 60) -> pd.DataFrame:
    """
    네이버 금융에서 과거 외국인/기관 수급 데이터 수집

    반환: DataFrame with columns [date, foreign_net, inst_net, price, volume]
    """
    url = f"https://finance.naver.com/item/frgn.naver?code={code}"

    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")

        data = []

        for table in soup.find_all("table", class_="type2"):
            for row in table.find_all("tr"):
                tds = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(tds) < 8 or not tds[0].startswith("20"):
                    continue

                if len(data) >= days:
                    break

                try:
                    date = tds[0]
                    close_price = int(tds[1].replace(",", ""))
                    volume = int(tds[4].replace(",", ""))
                    inst_net = int(tds[5].replace(",", "").replace("+", "") or "0")
                    foreign_net = int(tds[6].replace(",", "").replace("+", "") or "0")

                    data.append({
                        "date": date,
                        "close": close_price,
                        "volume": volume,
                        "foreign_net": foreign_net,
                        "inst_net": inst_net,
                    })
                except (ValueError, IndexError):
                    continue

            break

        if data:
            df = pd.DataFrame(data)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            return df

        return pd.DataFrame()

    except Exception as e:
        print(f"  [수급 데이터 수집 실패] {code}: {e}")
        return pd.DataFrame()


def calculate_next_day_return(df: pd.DataFrame) -> pd.DataFrame:
    """
    다음날 수익률 계산

    df: [date, close, volume, foreign_net, inst_net]
    반환: 위 컬럼 + next_day_return
    """
    df = df.copy()
    df["next_day_return"] = df["close"].shift(-1) / df["close"] - 1
    df["next_day_return"] = df["next_day_return"] * 100  # %

    return df


def test_signal_performance(df: pd.DataFrame, signal_name: str, condition) -> dict:
    """
    특정 신호의 다음날 수익률 성과 분석

    condition: lambda row: bool (신호 발생 조건)

    반환: {
        "signal": 신호명,
        "count": 신호 발생 횟수,
        "win_rate": 승률 (%),
        "avg_return": 평균 수익률 (%),
        "median_return": 중앙 수익률 (%),
        "max_return": 최대 수익률,
        "min_return": 최소 수익률,
    }
    """
    df_signal = df[df.apply(condition, axis=1)].copy()

    if len(df_signal) == 0:
        return {
            "signal": signal_name,
            "count": 0,
            "win_rate": 0,
            "avg_return": 0,
            "median_return": 0,
            "max_return": 0,
            "min_return": 0,
        }

    # 다음날 수익률 통계
    next_returns = df_signal["next_day_return"].dropna()

    win_count = (next_returns > 0).sum()
    total_count = len(next_returns)

    return {
        "signal": signal_name,
        "count": total_count,
        "win_rate": (win_count / total_count * 100) if total_count > 0 else 0,
        "avg_return": next_returns.mean() if total_count > 0 else 0,
        "median_return": next_returns.median() if total_count > 0 else 0,
        "max_return": next_returns.max() if total_count > 0 else 0,
        "min_return": next_returns.min() if total_count > 0 else 0,
        "std_return": next_returns.std() if total_count > 0 else 0,
    }


def backtest_ticker(ticker: str, name: str) -> pd.DataFrame:
    """
    단일 종목 백테스트

    테스트할 신호들:
    1. 전날 외국인+기관 동반 순매수
    2. 전날 외국인 단독 순매수
    3. 전날 기관 단독 순매수
    4. 전날 거래량 급증 (20일 평균 2배+)
    5. 전날 외국인 매수 급증 (전전날 대비 2배+)
    """
    code = ticker.replace(".KS", "").replace(".KQ", "")

    print(f"\n[{name}] ({ticker}) 백테스트 중...")

    # 1. 수급 데이터 수집
    df = fetch_investor_flow_historical(code, days=90)

    if df.empty or len(df) < 30:
        print(f"  → 데이터 부족 (skip)")
        return pd.DataFrame()

    # 2. 다음날 수익률 계산
    df = calculate_next_day_return(df)

    # 3. 추가 지표 계산
    df["volume_ma20"] = df["volume"].rolling(20).mean()
    df["volume_surge"] = df["volume"] / df["volume_ma20"]

    df["foreign_prev"] = df["foreign_net"].shift(1)
    df["foreign_acceleration"] = df["foreign_net"] / (df["foreign_prev"].abs() + 1)

    # 4. 신호별 성과 테스트
    results = []

    # 신호 1: 전날 동반 순매수
    results.append(test_signal_performance(
        df,
        "전날 동반순매수",
        lambda row: row["foreign_net"] > 0 and row["inst_net"] > 0
    ))

    # 신호 2: 전날 외국인 단독
    results.append(test_signal_performance(
        df,
        "전날 외국인만",
        lambda row: row["foreign_net"] > 0 and row["inst_net"] <= 0
    ))

    # 신호 3: 전날 기관 단독
    results.append(test_signal_performance(
        df,
        "전날 기관만",
        lambda row: row["foreign_net"] <= 0 and row["inst_net"] > 0
    ))

    # 신호 4: 전날 거래량 급증
    results.append(test_signal_performance(
        df,
        "전날 거래량2배+",
        lambda row: row["volume_surge"] >= 2.0 if pd.notna(row["volume_surge"]) else False
    ))

    # 신호 5: 외국인 매수 가속
    results.append(test_signal_performance(
        df,
        "외국인매수가속",
        lambda row: (
            row["foreign_net"] > 0 and
            row["foreign_acceleration"] >= 2.0
            if pd.notna(row["foreign_acceleration"]) else False
        )
    ))

    # 신호 6: 전날 동반 순매수 + 거래량 급증
    results.append(test_signal_performance(
        df,
        "동반매수+거래량",
        lambda row: (
            row["foreign_net"] > 0 and
            row["inst_net"] > 0 and
            row["volume_surge"] >= 2.0
            if pd.notna(row["volume_surge"]) else False
        )
    ))

    # 베이스라인: 무작위 (아무 신호 없음)
    results.append(test_signal_performance(
        df,
        "베이스라인(무작위)",
        lambda row: True  # 모든 날
    ))

    results_df = pd.DataFrame(results)
    results_df["ticker"] = ticker
    results_df["name"] = name

    return results_df


def run_backtest(tickers: list):
    """
    여러 종목 백테스트 실행
    """
    print("=" * 80)
    print("다음날 상승 예측 팩터 백테스트")
    print("=" * 80)
    print(f"테스트 종목: {len(tickers)}개")
    print(f"기간: 최근 90일")
    print("=" * 80)

    all_results = []

    for ticker, name in tickers:
        result = backtest_ticker(ticker, name)
        if not result.empty:
            all_results.append(result)

    if not all_results:
        print("\n[완료] 데이터 없음")
        return

    # 전체 종목 집계
    df_all = pd.concat(all_results, ignore_index=True)

    # 신호별 평균 성과
    summary = df_all.groupby("signal").agg({
        "count": "sum",
        "win_rate": "mean",
        "avg_return": "mean",
        "median_return": "mean",
        "max_return": "mean",
        "min_return": "mean",
        "std_return": "mean",
    }).reset_index()

    # 샤프비율 계산 (단순화: 평균/표준편차)
    summary["sharpe"] = summary["avg_return"] / (summary["std_return"] + 0.01)

    # 정렬 (평균 수익률 기준)
    summary = summary.sort_values("avg_return", ascending=False)

    print("\n" + "=" * 80)
    print("신호별 다음날 수익률 성과 (종합)")
    print("=" * 80)
    print(f"{'신호명':<20} {'발생':<6} {'승률':<8} {'평균':<8} {'중앙':<8} {'샤프':<6}")
    print("-" * 80)

    for _, row in summary.iterrows():
        print(
            f"{row['signal']:<20} "
            f"{int(row['count']):<6} "
            f"{row['win_rate']:>6.1f}% "
            f"{row['avg_return']:>7.2f}% "
            f"{row['median_return']:>7.2f}% "
            f"{row['sharpe']:>6.2f}"
        )

    print("\n" + "=" * 80)
    print("결론")
    print("=" * 80)

    # 베이스라인과 비교
    baseline = summary[summary["signal"] == "베이스라인(무작위)"]
    if not baseline.empty:
        baseline_return = baseline["avg_return"].iloc[0]
        baseline_winrate = baseline["win_rate"].iloc[0]

        print(f"베이스라인 (무작위): 평균 {baseline_return:.2f}%, 승률 {baseline_winrate:.1f}%")
        print()

        for _, row in summary.iterrows():
            if row["signal"] == "베이스라인(무작위)":
                continue

            diff = row["avg_return"] - baseline_return
            is_better = "✅ 유효" if diff > 0.5 else "❌ 무효"

            print(
                f"{row['signal']:<20}: "
                f"평균 {row['avg_return']:+.2f}% (베이스라인 대비 {diff:+.2f}%p) "
                f"{is_better}"
            )

    # CSV 저장
    output_file = "backtest_next_day_signals.csv"
    df_all.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n[저장] {output_file}")

    summary_file = "backtest_summary.csv"
    summary.to_csv(summary_file, index=False, encoding="utf-8-sig")
    print(f"[저장] {summary_file}")


if __name__ == "__main__":
    # 테스트 종목 (대형주 위주)
    test_tickers = [
        ("005930.KS", "삼성전자"),
        ("000660.KS", "SK하이닉스"),
        ("035420.KS", "NAVER"),
        ("005380.KS", "현대차"),
        ("051910.KS", "LG화학"),
        ("006400.KS", "삼성SDI"),
        ("035720.KS", "카카오"),
        ("207940.KS", "삼성바이오로직스"),
        ("068270.KS", "셀트리온"),
        ("105560.KS", "KB금융"),
    ]

    run_backtest(test_tickers)
