#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
기술적 신호 → 다음날 수익률 백테스트

검증할 가설:
1. RSI 30~40 (과매도) → 다음날 반등?
2. 볼린저밴드 하단 → 다음날 반등?
3. 5일선 골든크로스 → 다음날 상승?
4. 거래량 급증 → 다음날 상승?
5. 눌림목 패턴 → 다음날 반등?

vs 베이스라인 (무작위)
"""

import sys
import os
import io
import pandas as pd
import yfinance as yf
import ta as ta_lib
import warnings
warnings.filterwarnings("ignore")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def fetch_price_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """주가 데이터 수집"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, auto_adjust=True)

        if df.empty:
            return pd.DataFrame()

        df = df[df["Close"].notna()].copy()
        return df

    except Exception as e:
        print(f"  [데이터 수집 실패] {ticker}: {e}")
        return pd.DataFrame()


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """기술적 지표 계산"""
    df = df.copy()

    close = df["Close"]
    volume = df["Volume"]

    # RSI (9일)
    try:
        rsi = ta_lib.momentum.RSIIndicator(close=close, window=9).rsi()
        df["rsi"] = rsi
    except:
        df["rsi"] = 50

    # 볼린저밴드
    try:
        bb = ta_lib.volatility.BollingerBands(close=close, window=20, window_dev=2)
        df["bb_low"] = bb.bollinger_lband()
        df["bb_high"] = bb.bollinger_hband()
        df["bb_position"] = (close - df["bb_low"]) / (df["bb_high"] - df["bb_low"])
    except:
        df["bb_position"] = 0.5

    # 이평선
    df["ma5"] = close.rolling(5).mean()
    df["ma20"] = close.rolling(20).mean()

    # 거래량
    df["volume_ma20"] = volume.rolling(20).mean()
    df["volume_ratio"] = volume / df["volume_ma20"]

    # 수익률
    df["ret_1d"] = close.pct_change(1)
    df["ret_5d"] = close.pct_change(5)

    # 다음날 수익률 (목표 변수)
    df["next_day_return"] = close.shift(-1) / close - 1
    df["next_day_return_pct"] = df["next_day_return"] * 100

    return df


def test_signal(df: pd.DataFrame, signal_name: str, condition) -> dict:
    """
    신호별 다음날 수익률 분석

    condition: lambda row: bool
    """
    df_signal = df[df.apply(condition, axis=1)].copy()

    if len(df_signal) == 0:
        return {
            "signal": signal_name,
            "count": 0,
            "win_rate": 0,
            "avg_return": 0,
            "median_return": 0,
        }

    next_returns = df_signal["next_day_return_pct"].dropna()

    if len(next_returns) == 0:
        return {
            "signal": signal_name,
            "count": 0,
            "win_rate": 0,
            "avg_return": 0,
            "median_return": 0,
        }

    win_count = (next_returns > 0).sum()

    return {
        "signal": signal_name,
        "count": len(next_returns),
        "win_rate": (win_count / len(next_returns) * 100),
        "avg_return": next_returns.mean(),
        "median_return": next_returns.median(),
        "max_return": next_returns.max(),
        "min_return": next_returns.min(),
        "std_return": next_returns.std(),
    }


def backtest_ticker(ticker: str, name: str) -> pd.DataFrame:
    """단일 종목 백테스트"""
    print(f"\n[{name}] ({ticker}) 분석 중...")

    df = fetch_price_data(ticker, period="6mo")

    if df.empty or len(df) < 60:
        print(f"  → 데이터 부족")
        return pd.DataFrame()

    df = calculate_indicators(df)

    # 최소 60일 이후 데이터만 사용 (지표 안정화)
    df = df.iloc[60:].copy()

    if len(df) < 30:
        print(f"  → 유효 데이터 부족")
        return pd.DataFrame()

    print(f"  → {len(df)}일 데이터 분석")

    results = []

    # 신호 1: RSI 30~40 (과매도 반등)
    results.append(test_signal(
        df,
        "RSI 30-40 과매도",
        lambda row: 30 <= row["rsi"] <= 40 if pd.notna(row["rsi"]) else False
    ))

    # 신호 2: RSI 40~50 (양호)
    results.append(test_signal(
        df,
        "RSI 40-50 양호",
        lambda row: 40 < row["rsi"] <= 50 if pd.notna(row["rsi"]) else False
    ))

    # 신호 3: RSI > 65 (과열)
    results.append(test_signal(
        df,
        "RSI > 65 과열",
        lambda row: row["rsi"] > 65 if pd.notna(row["rsi"]) else False
    ))

    # 신호 4: 볼린저 하단 (하위 20%)
    results.append(test_signal(
        df,
        "볼린저 하단",
        lambda row: row["bb_position"] < 0.2 if pd.notna(row["bb_position"]) else False
    ))

    # 신호 5: 볼린저 상단 (상위 80%+)
    results.append(test_signal(
        df,
        "볼린저 상단",
        lambda row: row["bb_position"] > 0.8 if pd.notna(row["bb_position"]) else False
    ))

    # 신호 6: 5일선 > 20일선 (상승 추세)
    results.append(test_signal(
        df,
        "5일선 > 20일선",
        lambda row: (
            row["ma5"] > row["ma20"]
            if pd.notna(row["ma5"]) and pd.notna(row["ma20"]) else False
        )
    ))

    # 신호 7: 거래량 2배+ 급증
    results.append(test_signal(
        df,
        "거래량 2배+",
        lambda row: row["volume_ratio"] >= 2.0 if pd.notna(row["volume_ratio"]) else False
    ))

    # 신호 8: 눌림목 (5일 -3~-10% + 당일 반등)
    results.append(test_signal(
        df,
        "눌림목 패턴",
        lambda row: (
            -10 <= (row["ret_5d"] * 100) <= -3 and
            (row["ret_1d"] * 100) > 1
            if pd.notna(row["ret_5d"]) and pd.notna(row["ret_1d"]) else False
        )
    ))

    # 신호 9: 조합 - RSI 과매도 + 거래량 급증
    results.append(test_signal(
        df,
        "RSI과매도 + 거래량",
        lambda row: (
            30 <= row["rsi"] <= 40 and
            row["volume_ratio"] >= 2.0
            if pd.notna(row["rsi"]) and pd.notna(row["volume_ratio"]) else False
        )
    ))

    # 베이스라인
    results.append(test_signal(
        df,
        "베이스라인(무작위)",
        lambda row: True
    ))

    results_df = pd.DataFrame(results)
    results_df["ticker"] = ticker
    results_df["name"] = name

    return results_df


def run_backtest(tickers: list):
    """메인 백테스트"""
    print("=" * 80)
    print("기술적 신호 → 다음날 수익률 백테스트")
    print("=" * 80)
    print(f"종목 수: {len(tickers)}")
    print(f"기간: 6개월")
    print("=" * 80)

    all_results = []

    for ticker, name in tickers:
        result = backtest_ticker(ticker, name)
        if not result.empty:
            all_results.append(result)

    if not all_results:
        print("\n❌ 데이터 수집 실패")
        return

    df_all = pd.concat(all_results, ignore_index=True)

    # 신호별 집계
    summary = df_all.groupby("signal").agg({
        "count": "sum",
        "win_rate": "mean",
        "avg_return": "mean",
        "median_return": "mean",
        "std_return": "mean",
    }).reset_index()

    summary["sharpe"] = summary["avg_return"] / (summary["std_return"] + 0.01)
    summary = summary.sort_values("avg_return", ascending=False)

    print("\n" + "=" * 100)
    print("📊 신호별 다음날 수익률 분석 결과")
    print("=" * 100)
    print(f"{'신호명':<25} {'발생횟수':<10} {'승률':<10} {'평균수익률':<12} {'중앙수익률':<12} {'샤프비율':<10}")
    print("-" * 100)

    for _, row in summary.iterrows():
        print(
            f"{row['signal']:<25} "
            f"{int(row['count']):<10} "
            f"{row['win_rate']:>8.1f}% "
            f"{row['avg_return']:>10.3f}% "
            f"{row['median_return']:>10.3f}% "
            f"{row['sharpe']:>10.2f}"
        )

    print("\n" + "=" * 100)
    print("🎯 결론 (베이스라인 대비)")
    print("=" * 100)

    baseline = summary[summary["signal"] == "베이스라인(무작위)"]
    if not baseline.empty:
        baseline_return = baseline["avg_return"].iloc[0]
        baseline_winrate = baseline["win_rate"].iloc[0]

        print(f"\n📍 베이스라인: 평균 {baseline_return:+.3f}%, 승률 {baseline_winrate:.1f}%")
        print(f"   (= 아무 전략 없이 무작위로 매수했을 때)\n")

        for _, row in summary.iterrows():
            if row["signal"] == "베이스라인(무작위)":
                continue

            diff_return = row["avg_return"] - baseline_return
            diff_winrate = row["win_rate"] - baseline_winrate

            # 유효성 판단
            if diff_return > 0.3 and diff_winrate > 3:
                verdict = "✅ 강력 유효"
            elif diff_return > 0.1 and diff_winrate > 1:
                verdict = "✅ 유효"
            elif diff_return > -0.1:
                verdict = "⚠️  미약"
            else:
                verdict = "❌ 역효과"

            print(
                f"{verdict} {row['signal']:<25}: "
                f"수익률 {row['avg_return']:+.3f}% ({diff_return:+.3f}%p), "
                f"승률 {row['win_rate']:.1f}% ({diff_winrate:+.1f}%p)"
            )

    # CSV 저장
    output_file = "backtest_technical_results.csv"
    df_all.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n[저장] {output_file}")

    summary_file = "backtest_technical_summary.csv"
    summary.to_csv(summary_file, index=False, encoding="utf-8-sig")
    print(f"[저장] {summary_file}")


if __name__ == "__main__":
    test_tickers = [
        ("005930.KS", "삼성전자"),
        ("000660.KS", "SK하이닉스"),
        ("035420.KS", "NAVER"),
        ("005380.KS", "현대차"),
        ("051910.KS", "LG화학"),
        ("006400.KS", "삼성SDI"),
        ("035720.KS", "카카오"),
        ("068270.KS", "셀트리온"),
        ("105560.KS", "KB금융"),
        ("055550.KS", "신한지주"),
    ]

    run_backtest(test_tickers)
