#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
테마 효과 백테스트

검증 내용:
1. "약세" vs "강세" 테마 - 실제 다음날 수익률
2. 테마 지속성별 수익률
3. 테마 순환 효과
4. 당일 HOT 테마 효과
5. 섹터별 상관관계
"""

import sys
import io
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def fetch_theme_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """주가 + 테마 데이터"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, auto_adjust=True)

        if df.empty or len(df) < 60:
            return pd.DataFrame()

        df = df[df["Close"].notna()].copy()

        # 다음날 수익률
        df["next_day_return"] = df["Close"].shift(-1) / df["Close"] - 1
        df["next_day_return_pct"] = df["next_day_return"] * 100

        # 최근 추세 (테마 강세/약세 판단)
        df["ma5"] = df["Close"].rolling(5).mean()
        df["ma20"] = df["Close"].rolling(20).mean()

        # 5일 수익률 (테마 지속성)
        df["ret_5d"] = df["Close"].pct_change(5) * 100
        df["ret_10d"] = df["Close"].pct_change(10) * 100
        df["ret_20d"] = df["Close"].pct_change(20) * 100

        # 테마 상태 판단
        df["is_uptrend"] = df["ma5"] > df["ma20"]
        df["is_strong_uptrend"] = (df["ma5"] > df["ma20"]) & (df["ret_5d"] > 5)
        df["is_downtrend"] = df["ma5"] < df["ma20"]
        df["is_strong_downtrend"] = (df["ma5"] < df["ma20"]) & (df["ret_5d"] < -5)

        return df

    except Exception as e:
        return pd.DataFrame()


def test_theme_condition(df: pd.DataFrame, condition_name: str, condition_func) -> dict:
    """테마 조건별 다음날 수익률"""
    df_filtered = df[df.apply(condition_func, axis=1)].copy()

    if len(df_filtered) == 0:
        return {
            "condition": condition_name,
            "count": 0,
            "win_rate": 0,
            "avg_return": 0,
        }

    next_returns = df_filtered["next_day_return_pct"].dropna()

    if len(next_returns) == 0:
        return {
            "condition": condition_name,
            "count": 0,
            "win_rate": 0,
            "avg_return": 0,
        }

    win_count = (next_returns > 0).sum()

    return {
        "condition": condition_name,
        "count": len(next_returns),
        "win_rate": (win_count / len(next_returns) * 100),
        "avg_return": next_returns.mean(),
        "median_return": next_returns.median(),
        "std": next_returns.std(),
    }


def analyze_ticker(ticker: str, name: str) -> pd.DataFrame:
    """단일 종목 테마 분석"""
    print(f"[{name}] ({ticker}) 분석 중...")

    df = fetch_theme_data(ticker, period="1y")

    if df.empty or len(df) < 100:
        print(f"  → 데이터 부족")
        return pd.DataFrame()

    # 최소 60일 이후
    df = df.iloc[60:].copy()

    if len(df) < 50:
        return pd.DataFrame()

    print(f"  → {len(df)}일 분석")

    results = []

    # ═══ 테마 추세별 ═══

    # 1. 강세 추세 (5일선 > 20일선)
    results.append(test_theme_condition(
        df,
        "강세 추세 (5일선>20일선)",
        lambda r: r["is_uptrend"]
    ))

    # 2. 약세 추세 (5일선 < 20일선)
    results.append(test_theme_condition(
        df,
        "약세 추세 (5일선<20일선)",
        lambda r: r["is_downtrend"]
    ))

    # 3. 강력 상승 추세 (5일선>20일선 + 5일 +5%)
    results.append(test_theme_condition(
        df,
        "강력 상승 (5일선>20일선 + 5일+5%)",
        lambda r: r["is_strong_uptrend"]
    ))

    # 4. 강력 하락 추세 (5일선<20일선 + 5일 -5%)
    results.append(test_theme_condition(
        df,
        "강력 하락 (5일선<20일선 + 5일-5%)",
        lambda r: r["is_strong_downtrend"]
    ))

    # ═══ 최근 수익률 구간별 ═══

    # 5. 5일 +10% 이상 (급등)
    results.append(test_theme_condition(
        df,
        "5일 +10% 이상 급등",
        lambda r: r["ret_5d"] > 10 if pd.notna(r["ret_5d"]) else False
    ))

    # 6. 5일 +5~10% (상승)
    results.append(test_theme_condition(
        df,
        "5일 +5~10% 상승",
        lambda r: 5 < r["ret_5d"] <= 10 if pd.notna(r["ret_5d"]) else False
    ))

    # 7. 5일 0~5% (약상승)
    results.append(test_theme_condition(
        df,
        "5일 0~5% 약상승",
        lambda r: 0 < r["ret_5d"] <= 5 if pd.notna(r["ret_5d"]) else False
    ))

    # 8. 5일 -5~0% (약하락)
    results.append(test_theme_condition(
        df,
        "5일 -5~0% 약하락",
        lambda r: -5 <= r["ret_5d"] < 0 if pd.notna(r["ret_5d"]) else False
    ))

    # 9. 5일 -10~-5% (하락)
    results.append(test_theme_condition(
        df,
        "5일 -10~-5% 하락",
        lambda r: -10 <= r["ret_5d"] < -5 if pd.notna(r["ret_5d"]) else False
    ))

    # 10. 5일 -10% 이하 (급락)
    results.append(test_theme_condition(
        df,
        "5일 -10% 이하 급락",
        lambda r: r["ret_5d"] < -10 if pd.notna(r["ret_5d"]) else False
    ))

    # ═══ 20일 추세 + 5일 조정 ═══

    # 11. 20일 상승 + 5일 조정 (눌림목)
    results.append(test_theme_condition(
        df,
        "눌림목 (20일+10% + 5일-5%)",
        lambda r: (
            r["ret_20d"] > 10 and -5 <= r["ret_5d"] < 0
            if pd.notna(r["ret_20d"]) and pd.notna(r["ret_5d"]) else False
        )
    ))

    # 12. 20일 하락 + 5일 반등
    results.append(test_theme_condition(
        df,
        "반등 (20일-10% + 5일+5%)",
        lambda r: (
            r["ret_20d"] < -10 and r["ret_5d"] > 5
            if pd.notna(r["ret_20d"]) and pd.notna(r["ret_5d"]) else False
        )
    ))

    results_df = pd.DataFrame(results)
    results_df["ticker"] = ticker
    results_df["name"] = name

    return results_df


def run_theme_backtest(tickers: list):
    """테마 백테스트 실행"""
    print("=" * 100)
    print("테마 효과 백테스트")
    print("=" * 100)
    print(f"종목 수: {len(tickers)}")
    print(f"기간: 1년")
    print("=" * 100)

    all_results = []

    for ticker, name in tickers:
        result = analyze_ticker(ticker, name)
        if not result.empty:
            all_results.append(result)

    if not all_results:
        print("\n❌ 데이터 수집 실패")
        return

    df_all = pd.concat(all_results, ignore_index=True)

    # 조건별 집계
    summary = df_all.groupby("condition").agg({
        "count": "sum",
        "win_rate": "mean",
        "avg_return": "mean",
        "median_return": "mean",
        "std": "mean",
    }).reset_index()

    # 최소 30회 발생
    summary = summary[summary["count"] >= 30]

    # 평균 수익률 기준 정렬
    summary = summary.sort_values("avg_return", ascending=False)

    print("\n" + "=" * 110)
    print("🔍 테마 조건별 다음날 수익률")
    print("=" * 110)
    print(f"{'조건':<35} {'발생':<8} {'승률':<10} {'평균':<10} {'중앙':<10} {'효과':<10}")
    print("-" * 110)

    for _, row in summary.iterrows():
        avg = row["avg_return"]

        if avg > 0.5:
            effect = "✅ 강력"
        elif avg > 0.2:
            effect = "✅ 유효"
        elif avg > -0.2:
            effect = "⚠️  미약"
        else:
            effect = "❌ 역효과"

        print(
            f"{row['condition']:<35} "
            f"{int(row['count']):<8} "
            f"{row['win_rate']:>8.1f}% "
            f"{row['avg_return']:>9.3f}% "
            f"{row['median_return']:>9.3f}% "
            f"{effect:<10}"
        )

    print("\n" + "=" * 110)
    print("🎯 핵심 발견")
    print("=" * 110)

    # 강세 vs 약세
    uptrend = summary[summary["condition"] == "강세 추세 (5일선>20일선)"]
    downtrend = summary[summary["condition"] == "약세 추세 (5일선<20일선)"]

    if not uptrend.empty and not downtrend.empty:
        up_return = uptrend["avg_return"].iloc[0]
        down_return = downtrend["avg_return"].iloc[0]
        diff = up_return - down_return

        print(f"\n1️⃣ 강세 vs 약세 테마")
        print(f"   강세 추세: {up_return:+.3f}%")
        print(f"   약세 추세: {down_return:+.3f}%")
        print(f"   차이: {diff:+.3f}%p")

        if diff > 0:
            print(f"   ✅ 강세 테마가 {diff:.3f}%p 더 좋음")
        else:
            print(f"   ⚠️  약세 테마가 오히려 나음 (역발상?)")

    # 급등 vs 급락
    surge = summary[summary["condition"] == "5일 +10% 이상 급등"]
    crash = summary[summary["condition"] == "5일 -10% 이하 급락"]

    print(f"\n2️⃣ 급등 vs 급락 후")
    if not surge.empty:
        print(f"   5일 +10% 급등 후: {surge['avg_return'].iloc[0]:+.3f}%")
    if not crash.empty:
        print(f"   5일 -10% 급락 후: {crash['avg_return'].iloc[0]:+.3f}%")

    # 유효한 전략
    valid = summary[summary["avg_return"] > 0.2]

    print(f"\n3️⃣ 유효한 테마 전략 (평균 +0.2%p 이상)")
    if not valid.empty:
        for _, row in valid.iterrows():
            print(f"   ✅ {row['condition']}: {row['avg_return']:+.3f}%")
    else:
        print("   없음")

    # 역효과 전략
    negative = summary[summary["avg_return"] < -0.2]

    print(f"\n4️⃣ 피해야 할 테마 전략 (평균 -0.2%p 이하)")
    if not negative.empty:
        for _, row in negative.iterrows():
            print(f"   ❌ {row['condition']}: {row['avg_return']:+.3f}%")
    else:
        print("   없음")

    # CSV 저장
    output_file = "theme_backtest_results.csv"
    df_all.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n[저장] {output_file}")

    summary_file = "theme_backtest_summary.csv"
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

    run_theme_backtest(test_tickers)
