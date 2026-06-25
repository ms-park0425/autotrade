"""
수급 패턴 vs 단기 수익률 분석
실제 데이터로 어떤 수급 패턴이 유효한지 검증
"""

import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 분석 대상 종목 - 반도체 중심
TICKERS = [
    # 반도체 대장주
    ("005930.KS", "삼성전자"),
    ("000660.KS", "SK하이닉스"),
    # 반도체 장비
    ("042700.KS", "한미반도체"),
    ("036540.KS", "SFA반도체"),
    ("094820.KS", "일진파워"),
    ("108320.KS", "LX세미콘"),
    ("039030.KQ", "이오테크닉스"),
    ("058470.KS", "리노공업"),
    ("131970.KS", "주성엔지니어링"),
    ("095610.KS", "테스"),
    ("222080.KS", "씨아이에스"),
    # 반도체 소재/부품
    ("036810.KQ", "에프에스티"),
    ("403870.KS", "HPSP"),
    ("101490.KS", "에스앤에스텍"),
    ("140860.KS", "파크시스템스"),
    ("278280.KS", "천보"),
    ("214430.KS", "아이쓰리시스템"),
    ("035000.KQ", "지투파워"),
    ("122870.KS", "와이지-원"),
]


def get_investor_flow_detail(code: str, days: int = 10):
    """네이버 금융에서 N일 수급 상세 데이터 수집"""
    url = f"https://finance.naver.com/item/frgn.naver?code={code}"

    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")

        daily_data = []

        for table in soup.find_all("table", class_="type2"):
            has_data = any(
                row.find("td") and row.find("td").get_text(strip=True).startswith("20")
                for row in table.find_all("tr")
            )
            if not has_data:
                continue

            for row in table.find_all("tr"):
                tds = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(tds) < 8 or not tds[0].startswith("20"):
                    continue
                if len(daily_data) >= days:
                    break

                try:
                    date = tds[0]
                    close_price = int(tds[1].replace(",", ""))
                    change = tds[2]
                    volume = int(tds[3].replace(",", ""))
                    inst_net = int(tds[5].replace(",", "").replace("+", "") or "0")
                    foreign_net = int(tds[6].replace(",", "").replace("+", "") or "0")
                    foreign_ratio = float(tds[8].replace("%", "").replace(",", "") or "0")

                    # 개인 순매수 = -(외국인 + 기관)
                    individual_net = -(foreign_net + inst_net)

                    daily_data.append({
                        "date": date,
                        "close": close_price,
                        "volume": volume,
                        "foreign_net": foreign_net,
                        "inst_net": inst_net,
                        "individual_net": individual_net,
                        "foreign_ratio": foreign_ratio,
                    })
                except (ValueError, IndexError) as e:
                    continue
            break

        return daily_data

    except Exception as e:
        print(f"  [오류] {code}: {e}")
        return []


def analyze_pattern(ticker: str, name: str):
    """단일 종목 패턴 분석"""
    print(f"\n[분석] {name} ({ticker})")

    code = ticker.replace(".KS", "").replace(".KQ", "")

    # 1. 가격 데이터
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1mo", auto_adjust=True)
        if df.empty or len(df) < 20:
            print("  → 가격 데이터 부족")
            return None
    except Exception as e:
        print(f"  → yfinance 오류: {e}")
        return None

    # 2. 수급 데이터
    supply_data = get_investor_flow_detail(code, days=10)
    if not supply_data or len(supply_data) < 7:
        print("  → 수급 데이터 부족")
        return None

    # 3. 최근 3일 수급 패턴 분석
    recent_3d = supply_data[:3]

    foreign_3d = sum(d["foreign_net"] for d in recent_3d)
    inst_3d = sum(d["inst_net"] for d in recent_3d)
    individual_3d = sum(d["individual_net"] for d in recent_3d)

    # 평균 거래량 vs 최근 거래량
    avg_volume = sum(d["volume"] for d in supply_data[3:]) / len(supply_data[3:])
    recent_volume = recent_3d[0]["volume"]
    volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1

    # 3일 연속 체크
    foreign_consec = all(d["foreign_net"] > 0 for d in recent_3d)
    inst_consec = all(d["inst_net"] > 0 for d in recent_3d)
    individual_consec = all(d["individual_net"] > 0 for d in recent_3d)

    # 4. 이후 수익률 (최근 → 7일전 기준)
    if len(supply_data) >= 10:
        base_price = supply_data[7]["close"]  # 7일 전 종가
        current_price = supply_data[0]["close"]  # 현재 종가

        ret_7d = ((current_price - base_price) / base_price) * 100
    else:
        ret_7d = None

    # 5. 패턴 분류
    pattern = []
    if foreign_3d > 0 and inst_3d > 0:
        pattern.append("외국인+기관 순매수")
    elif foreign_3d > 0:
        pattern.append("외국인 순매수")
    elif inst_3d > 0:
        pattern.append("기관 순매수")

    if individual_3d > 0:
        pattern.append("개인 순매수")

    if volume_ratio >= 2.0:
        pattern.append("거래량 2배+")
    elif volume_ratio >= 1.5:
        pattern.append("거래량 1.5배+")

    if foreign_consec:
        pattern.append("외국인 3일연속")
    if inst_consec:
        pattern.append("기관 3일연속")
    if individual_consec:
        pattern.append("개인 3일연속")

    pattern_str = ", ".join(pattern) if pattern else "무패턴"

    print(f"  패턴: {pattern_str}")
    print(f"  수급: 외국인 {foreign_3d:+,}주, 기관 {inst_3d:+,}주, 개인 {individual_3d:+,}주")
    print(f"  거래량: {volume_ratio:.2f}배")
    if ret_7d is not None:
        print(f"  7일 수익률: {ret_7d:+.2f}%")

    return {
        "ticker": ticker,
        "name": name,
        "foreign_3d": foreign_3d,
        "inst_3d": inst_3d,
        "individual_3d": individual_3d,
        "volume_ratio": volume_ratio,
        "pattern": pattern_str,
        "foreign_consec": foreign_consec,
        "inst_consec": inst_consec,
        "individual_consec": individual_consec,
        "ret_7d": ret_7d,
    }


def main():
    print("=" * 80)
    print("수급 패턴 vs 단기 수익률 분석")
    print("=" * 80)

    results = []

    for ticker, name in TICKERS:
        result = analyze_pattern(ticker, name)
        if result:
            results.append(result)
        time.sleep(1)  # 크롤링 간격

    if not results:
        print("\n분석 가능한 데이터 없음")
        return

    # 결과 분석
    df = pd.DataFrame(results)

    print("\n" + "=" * 80)
    print("📊 패턴별 분석 결과")
    print("=" * 80)

    # 1. 외국인+기관 동반 순매수
    mask1 = (df["foreign_3d"] > 0) & (df["inst_3d"] > 0)
    if mask1.sum() > 0:
        avg_ret = df[mask1]["ret_7d"].mean()
        win_rate = (df[mask1]["ret_7d"] > 0).sum() / mask1.sum() * 100
        print(f"\n[외국인+기관 동반 순매수] ({mask1.sum()}개)")
        print(f"  평균 7일 수익률: {avg_ret:+.2f}%")
        print(f"  승률: {win_rate:.1f}%")

    # 2. 외국인만 순매수
    mask2 = (df["foreign_3d"] > 0) & (df["inst_3d"] <= 0)
    if mask2.sum() > 0:
        avg_ret = df[mask2]["ret_7d"].mean()
        win_rate = (df[mask2]["ret_7d"] > 0).sum() / mask2.sum() * 100
        print(f"\n[외국인만 순매수] ({mask2.sum()}개)")
        print(f"  평균 7일 수익률: {avg_ret:+.2f}%")
        print(f"  승률: {win_rate:.1f}%")

    # 3. 기관만 순매수
    mask3 = (df["foreign_3d"] <= 0) & (df["inst_3d"] > 0)
    if mask3.sum() > 0:
        avg_ret = df[mask3]["ret_7d"].mean()
        win_rate = (df[mask3]["ret_7d"] > 0).sum() / mask3.sum() * 100
        print(f"\n[기관만 순매수] ({mask3.sum()}개)")
        print(f"  평균 7일 수익률: {avg_ret:+.2f}%")
        print(f"  승률: {win_rate:.1f}%")

    # 4. 개인 순매수
    mask4 = df["individual_3d"] > 0
    if mask4.sum() > 0:
        avg_ret = df[mask4]["ret_7d"].mean()
        win_rate = (df[mask4]["ret_7d"] > 0).sum() / mask4.sum() * 100
        print(f"\n[개인 순매수] ({mask4.sum()}개)")
        print(f"  평균 7일 수익률: {avg_ret:+.2f}%")
        print(f"  승률: {win_rate:.1f}%")

    # 5. 거래량 2배+
    mask5 = df["volume_ratio"] >= 2.0
    if mask5.sum() > 0:
        avg_ret = df[mask5]["ret_7d"].mean()
        win_rate = (df[mask5]["ret_7d"] > 0).sum() / mask5.sum() * 100
        print(f"\n[거래량 2배+] ({mask5.sum()}개)")
        print(f"  평균 7일 수익률: {avg_ret:+.2f}%")
        print(f"  승률: {win_rate:.1f}%")

    # 6. 3일 연속 패턴
    mask6 = df["foreign_consec"] & df["inst_consec"]
    if mask6.sum() > 0:
        avg_ret = df[mask6]["ret_7d"].mean()
        win_rate = (df[mask6]["ret_7d"] > 0).sum() / mask6.sum() * 100
        print(f"\n[외국인+기관 3일 연속] ({mask6.sum()}개)")
        print(f"  평균 7일 수익률: {avg_ret:+.2f}%")
        print(f"  승률: {win_rate:.1f}%")

    # 7. 둘 다 순매도
    mask7 = (df["foreign_3d"] < 0) & (df["inst_3d"] < 0)
    if mask7.sum() > 0:
        avg_ret = df[mask7]["ret_7d"].mean()
        win_rate = (df[mask7]["ret_7d"] > 0).sum() / mask7.sum() * 100
        print(f"\n[외국인+기관 둘 다 순매도] ({mask7.sum()}개)")
        print(f"  평균 7일 수익률: {avg_ret:+.2f}%")
        print(f"  승률: {win_rate:.1f}%")

    # 상세 결과
    print("\n" + "=" * 80)
    print("📋 종목별 상세")
    print("=" * 80)

    df_sorted = df.sort_values("ret_7d", ascending=False)
    for idx, row in df_sorted.iterrows():
        print(f"\n{row['name']} ({row['ticker']})")
        print(f"  패턴: {row['pattern']}")
        print(f"  7일 수익률: {row['ret_7d']:+.2f}%")


if __name__ == "__main__":
    main()
