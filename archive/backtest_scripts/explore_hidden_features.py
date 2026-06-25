#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
숨겨진 예측 특징 탐색

다음날 상승과 관련있는 특징 찾기:
1. 캔들 패턴 (망치형, 도지, 장악형 등)
2. 연속 상승/하락일
3. 전일 등락률 구간별
4. 변동성 (ATR)
5. 고가/저가 위치
6. 요일 효과
7. 월초/월말 효과
8. 52주 고점/저점 대비 위치
9. MACD, 스토캐스틱
10. 갭 패턴
"""

import sys
import os
import io
import pandas as pd
import numpy as np
import yfinance as yf
import ta as ta_lib
import warnings
warnings.filterwarnings("ignore")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def fetch_data(ticker: str, period: str = "1y") -> pd.DataFrame:
    """주가 데이터 수집 (1년)"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, auto_adjust=False)

        if df.empty:
            return pd.DataFrame()

        df = df[df["Close"].notna()].copy()
        return df

    except Exception as e:
        return pd.DataFrame()


def calculate_features(df: pd.DataFrame) -> pd.DataFrame:
    """다양한 특징 계산"""
    df = df.copy()

    open_price = df["Open"]
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    volume = df["Volume"]

    # ─── 기본 지표 ───
    df["ret_1d"] = close.pct_change(1) * 100
    df["next_day_return"] = close.shift(-1) / close - 1
    df["next_day_return_pct"] = df["next_day_return"] * 100

    # ─── 1. 캔들 패턴 ───
    # 몸통 크기
    df["body"] = abs(close - open_price)
    df["body_pct"] = df["body"] / open_price * 100

    # 위/아래 꼬리
    df["upper_shadow"] = high - df[["Open", "Close"]].max(axis=1)
    df["lower_shadow"] = df[["Open", "Close"]].min(axis=1) - low

    # 망치형 (아래 꼬리 긴 양봉)
    df["is_hammer"] = (
        (close > open_price) &  # 양봉
        (df["lower_shadow"] > df["body"] * 2) &  # 아래 꼬리가 몸통의 2배+
        (df["upper_shadow"] < df["body"] * 0.3)  # 위 꼬리 짧음
    )

    # 도지 (몸통 거의 없음)
    df["is_doji"] = df["body_pct"] < 0.1

    # 장대양봉/음봉
    df["is_big_green"] = (close > open_price) & (df["body_pct"] > 3)
    df["is_big_red"] = (close < open_price) & (df["body_pct"] > 3)

    # ─── 2. 연속일 ───
    # 연속 상승일
    up_days = (df["ret_1d"] > 0).astype(int)
    df["consecutive_up"] = up_days.groupby((up_days != up_days.shift()).cumsum()).cumsum()

    # 연속 하락일
    down_days = (df["ret_1d"] < 0).astype(int)
    df["consecutive_down"] = down_days.groupby((down_days != down_days.shift()).cumsum()).cumsum()

    # ─── 3. 변동성 (ATR) ───
    try:
        atr = ta_lib.volatility.AverageTrueRange(high=high, low=low, close=close, window=14)
        df["atr"] = atr.average_true_range()
        df["atr_pct"] = df["atr"] / close * 100
    except:
        df["atr_pct"] = 0

    # ─── 4. 고가/저가 위치 ───
    # 종가가 당일 레인지 어디에 위치?
    df["close_position"] = (close - low) / (high - low + 0.01)

    # ─── 5. MACD ───
    try:
        macd = ta_lib.trend.MACD(close=close)
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_diff"] = macd.macd_diff()
        df["macd_cross_up"] = (df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1))
    except:
        df["macd_cross_up"] = False

    # ─── 6. 52주 고저점 대비 ───
    df["high_52w"] = high.rolling(252).max()
    df["low_52w"] = low.rolling(252).min()
    df["from_52w_high"] = (df["high_52w"] - close) / df["high_52w"] * 100
    df["from_52w_low"] = (close - df["low_52w"]) / df["low_52w"] * 100

    # ─── 7. 요일 ───
    df["weekday"] = df.index.dayofweek  # 0=월, 4=금

    # ─── 8. 월초/월말 ───
    df["day_of_month"] = df.index.day

    # ─── 9. 갭 ───
    prev_close = close.shift(1)
    df["gap_pct"] = (open_price - prev_close) / prev_close * 100
    df["is_gap_up"] = df["gap_pct"] > 1
    df["is_gap_down"] = df["gap_pct"] < -1

    # ─── 10. 전일 등락률 구간 ───
    df["ret_1d_prev"] = df["ret_1d"].shift(1)

    return df


def test_feature(df: pd.DataFrame, feature_name: str, condition, baseline_return: float) -> dict:
    """특징별 다음날 수익률 분석"""
    df_feature = df[df.apply(condition, axis=1)].copy()

    if len(df_feature) == 0:
        return {
            "feature": feature_name,
            "count": 0,
            "win_rate": 0,
            "avg_return": 0,
            "vs_baseline": 0,
        }

    next_returns = df_feature["next_day_return_pct"].dropna()

    if len(next_returns) == 0:
        return {
            "feature": feature_name,
            "count": 0,
            "win_rate": 0,
            "avg_return": 0,
            "vs_baseline": 0,
        }

    win_count = (next_returns > 0).sum()
    avg_return = next_returns.mean()

    return {
        "feature": feature_name,
        "count": len(next_returns),
        "win_rate": (win_count / len(next_returns) * 100),
        "avg_return": avg_return,
        "median_return": next_returns.median(),
        "vs_baseline": avg_return - baseline_return,
        "std": next_returns.std(),
    }


def explore_ticker(ticker: str, name: str) -> pd.DataFrame:
    """단일 종목 특징 탐색"""
    print(f"\n[{name}] ({ticker}) 탐색 중...")

    df = fetch_data(ticker, period="1y")

    if df.empty or len(df) < 100:
        print(f"  → 데이터 부족")
        return pd.DataFrame()

    df = calculate_features(df)

    # 최소 60일 이후
    df = df.iloc[60:].copy()

    if len(df) < 50:
        print(f"  → 유효 데이터 부족")
        return pd.DataFrame()

    print(f"  → {len(df)}일 분석")

    # 베이스라인
    baseline_return = df["next_day_return_pct"].dropna().mean()

    results = []

    # ═══ 캔들 패턴 ═══
    results.append(test_feature(df, "망치형 캔들", lambda r: r["is_hammer"], baseline_return))
    results.append(test_feature(df, "도지 캔들", lambda r: r["is_doji"], baseline_return))
    results.append(test_feature(df, "장대양봉", lambda r: r["is_big_green"], baseline_return))
    results.append(test_feature(df, "장대음봉", lambda r: r["is_big_red"], baseline_return))

    # ═══ 연속일 ═══
    results.append(test_feature(df, "2일 연속 상승", lambda r: r["consecutive_up"] >= 2, baseline_return))
    results.append(test_feature(df, "3일 연속 상승", lambda r: r["consecutive_up"] >= 3, baseline_return))
    results.append(test_feature(df, "2일 연속 하락", lambda r: r["consecutive_down"] >= 2, baseline_return))
    results.append(test_feature(df, "3일 연속 하락", lambda r: r["consecutive_down"] >= 3, baseline_return))

    # ═══ 변동성 ═══
    results.append(test_feature(df, "ATR 높음 (3%+)", lambda r: r["atr_pct"] > 3, baseline_return))
    results.append(test_feature(df, "ATR 낮음 (<1%)", lambda r: r["atr_pct"] < 1, baseline_return))

    # ═══ 고가/저가 위치 ═══
    results.append(test_feature(df, "당일 고가 근접 (상위 80%+)", lambda r: r["close_position"] > 0.8, baseline_return))
    results.append(test_feature(df, "당일 저가 근접 (하위 20%)", lambda r: r["close_position"] < 0.2, baseline_return))

    # ═══ MACD ═══
    results.append(test_feature(df, "MACD 골든크로스", lambda r: r["macd_cross_up"], baseline_return))

    # ═══ 52주 고저점 ═══
    results.append(test_feature(df, "52주 고점 근접 (-5%)", lambda r: r["from_52w_high"] < 5, baseline_return))
    results.append(test_feature(df, "52주 저점 근접 (+20%)", lambda r: r["from_52w_low"] < 20, baseline_return))

    # ═══ 요일 효과 ═══
    results.append(test_feature(df, "월요일", lambda r: r["weekday"] == 0, baseline_return))
    results.append(test_feature(df, "화요일", lambda r: r["weekday"] == 1, baseline_return))
    results.append(test_feature(df, "수요일", lambda r: r["weekday"] == 2, baseline_return))
    results.append(test_feature(df, "목요일", lambda r: r["weekday"] == 3, baseline_return))
    results.append(test_feature(df, "금요일", lambda r: r["weekday"] == 4, baseline_return))

    # ═══ 월초/월말 ═══
    results.append(test_feature(df, "월초 (1~5일)", lambda r: r["day_of_month"] <= 5, baseline_return))
    results.append(test_feature(df, "월말 (25~31일)", lambda r: r["day_of_month"] >= 25, baseline_return))

    # ═══ 갭 패턴 ═══
    results.append(test_feature(df, "갭상승 시초가", lambda r: r["is_gap_up"], baseline_return))
    results.append(test_feature(df, "갭하락 시초가", lambda r: r["is_gap_down"], baseline_return))

    # ═══ 전일 등락률 구간 ═══
    results.append(test_feature(df, "전일 +2% 이상", lambda r: r["ret_1d_prev"] > 2, baseline_return))
    results.append(test_feature(df, "전일 -2% 이하", lambda r: r["ret_1d_prev"] < -2, baseline_return))
    results.append(test_feature(df, "전일 보합 (±0.5%)", lambda r: abs(r["ret_1d_prev"]) < 0.5, baseline_return))

    results_df = pd.DataFrame(results)
    results_df["ticker"] = ticker
    results_df["name"] = name
    results_df["baseline"] = baseline_return

    return results_df


def run_exploration(tickers: list):
    """메인 탐색"""
    print("=" * 100)
    print("숨겨진 예측 특징 탐색")
    print("=" * 100)
    print(f"종목 수: {len(tickers)}")
    print(f"기간: 1년")
    print("=" * 100)

    all_results = []

    for ticker, name in tickers:
        result = explore_ticker(ticker, name)
        if not result.empty:
            all_results.append(result)

    if not all_results:
        print("\n❌ 데이터 수집 실패")
        return

    df_all = pd.concat(all_results, ignore_index=True)

    # 특징별 집계
    summary = df_all.groupby("feature").agg({
        "count": "sum",
        "win_rate": "mean",
        "avg_return": "mean",
        "vs_baseline": "mean",
        "std": "mean",
    }).reset_index()

    # 필터: 최소 30회 이상 발생
    summary = summary[summary["count"] >= 30]

    # 베이스라인 대비 정렬
    summary = summary.sort_values("vs_baseline", ascending=False)

    print("\n" + "=" * 110)
    print("🔍 특징별 다음날 수익률 분석 (베이스라인 대비 정렬)")
    print("=" * 110)
    print(f"{'특징':<30} {'발생':<8} {'승률':<10} {'평균수익률':<12} {'베이스라인 대비':<15} {'효과':<10}")
    print("-" * 110)

    for _, row in summary.iterrows():
        diff = row["vs_baseline"]

        if diff > 0.5:
            effect = "✅ 강력"
        elif diff > 0.2:
            effect = "✅ 유효"
        elif diff > -0.2:
            effect = "⚠️  미약"
        else:
            effect = "❌ 역효과"

        print(
            f"{row['feature']:<30} "
            f"{int(row['count']):<8} "
            f"{row['win_rate']:>8.1f}% "
            f"{row['avg_return']:>10.3f}% "
            f"{row['vs_baseline']:>13.3f}%p "
            f"{effect:<10}"
        )

    print("\n" + "=" * 110)
    print("🎯 발견된 유효 특징 (베이스라인 대비 +0.2%p 이상)")
    print("=" * 110)

    valid_features = summary[summary["vs_baseline"] > 0.2]

    if not valid_features.empty:
        for _, row in valid_features.iterrows():
            print(
                f"✅ {row['feature']:<30}: "
                f"+{row['vs_baseline']:.3f}%p (승률 {row['win_rate']:.1f}%, {int(row['count'])}회 발생)"
            )
    else:
        print("발견된 유효 특징 없음")

    print("\n" + "=" * 110)
    print("⚠️ 역효과 특징 (베이스라인 대비 -0.2%p 이하)")
    print("=" * 110)

    negative_features = summary[summary["vs_baseline"] < -0.2]

    if not negative_features.empty:
        for _, row in negative_features.iterrows():
            print(
                f"❌ {row['feature']:<30}: "
                f"{row['vs_baseline']:.3f}%p (승률 {row['win_rate']:.1f}%, {int(row['count'])}회 발생)"
            )
    else:
        print("발견된 역효과 특징 없음")

    # CSV 저장
    output_file = "feature_exploration_results.csv"
    df_all.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n[저장] {output_file}")

    summary_file = "feature_exploration_summary.csv"
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

    run_exploration(test_tickers)
