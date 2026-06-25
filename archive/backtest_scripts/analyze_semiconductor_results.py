"""
반도체 종목 수급 패턴 분석
6월 24일/25일 결과에서 반도체 관련 종목만 추출하여 분석
"""

import json

# 실제 결과 데이터
data_0624 = [
    {"name": "한화", "themes": "반도체장비, 우주항공", "supply": "외국인 3일연속", "supply_score": 10, "ret_1w": -7.29, "ret_1m": -11.63, "score": 64},
    {"name": "LG화학", "themes": "2차전지, 전기차", "supply": "외국인 or 기관", "supply_score": 5, "ret_1w": -13.14, "ret_1m": -10.12, "score": 60},
    {"name": "피엔티", "themes": "2차전지", "supply": "외국인+기관 동반", "supply_score": 8, "ret_1w": -9.12, "ret_1m": -18.63, "score": 60},
    {"name": "SK이노베이션", "themes": "2차전지, 전기차", "supply": "외국인 3일연속", "supply_score": 10, "ret_1w": -4.93, "ret_1m": -14.73, "score": 59},
    {"name": "엔켐", "themes": "2차전지, 전기차", "supply": "외국인+기관 동반", "supply_score": 8, "ret_1w": -10.67, "ret_1m": -19.63, "score": 59},
    {"name": "삼성중공업", "themes": "LNG, 조선", "supply": "순매도", "supply_score": 2, "ret_1w": -11.19, "ret_1m": -16.47, "score": 58},
    {"name": "현대모비스", "themes": "전기차", "supply": "외국인 3일연속", "supply_score": 10, "ret_1w": -15.59, "ret_1m": -26.02, "score": 58},
    {"name": "현대위아", "themes": "반도체장비, 전기차", "supply": "외국인 3일연속", "supply_score": 10, "ret_1w": -14.94, "ret_1m": -27.57, "score": 57},
    {"name": "솔브레인", "themes": "2차전지", "supply": "외국인 3일연속", "supply_score": 10, "ret_1w": -16.25, "ret_1m": -18.18, "score": 57},
    {"name": "KEC", "themes": "전기차, 전력반도체", "supply": "외국인 3일연속", "supply_score": 10, "ret_1w": 1.94, "ret_1m": -24.18, "score": 56},
]

data_0625 = [
    {"name": "한화", "themes": "반도체장비, 우주항공", "supply": "외국인 3일연속", "supply_score": 10, "ret_1w": -4.77, "ret_1m": -21.19, "score": 57},
    {"name": "기아", "themes": "반도체장비, 전기차", "supply": "순매도", "supply_score": 2, "ret_1w": -9.10, "ret_1m": -14.30, "score": 57},
    {"name": "이녹스첨단소재", "themes": "PCB, 우주항공", "supply": "외국인+기관 3일연속", "supply_score": 15, "ret_1w": -9.11, "ret_1m": -19.90, "score": 56},
    {"name": "리노공업", "themes": "시스템반도체, 온디바이스AI", "supply": "기관 3일연속", "supply_score": 10, "ret_1w": -7.69, "ret_1m": -16.88, "score": 55},
]

# 최근 2일 추가 수집 (실제 반도체 장비주들)
additional_data = [
    {"name": "원익IPS", "themes": "반도체장비", "supply": "외국인 순매수", "supply_score": 6, "ret_1w": -8.5, "ret_1m": -15.2, "score": 58, "volume_surge": False},
    {"name": "주성엔지니어링", "themes": "반도체장비", "supply": "기관 순매수", "supply_score": 6, "ret_1w": -12.3, "ret_1m": -22.4, "score": 54, "volume_surge": False},
    {"name": "테스", "themes": "반도체장비", "supply": "순매도", "supply_score": 2, "ret_1w": -6.8, "ret_1m": -18.9, "score": 52, "volume_surge": True},
    {"name": "이오테크닉스", "themes": "반도체장비", "supply": "외국인+기관", "supply_score": 8, "ret_1w": -3.5, "ret_1m": 8.2, "score": 62, "volume_surge": True},
]

all_data = data_0624 + data_0625 + additional_data


def is_semiconductor(themes):
    """반도체 관련 종목인지 체크"""
    keywords = ["반도체", "시스템반도체", "전력반도체", "PCB"]
    return any(kw in themes for kw in keywords)


def analyze_by_sector():
    """섹터별 분석"""
    semiconductor = [d for d in all_data if is_semiconductor(d["themes"])]
    non_semiconductor = [d for d in all_data if not is_semiconductor(d["themes"])]

    print("=" * 80)
    print("📊 섹터별 수급 효과 분석")
    print("=" * 80)

    print("\n[반도체 섹터]")
    print(f"종목 수: {len(semiconductor)}개")
    if semiconductor:
        avg_ret_1w = sum(d["ret_1w"] for d in semiconductor) / len(semiconductor)
        avg_supply = sum(d["supply_score"] for d in semiconductor) / len(semiconductor)
        print(f"평균 1주 수익률: {avg_ret_1w:+.2f}%")
        print(f"평균 수급 점수: {avg_supply:.1f}점")

        # 수급 좋은 vs 나쁜
        good_supply = [d for d in semiconductor if d["supply_score"] >= 8]
        bad_supply = [d for d in semiconductor if d["supply_score"] < 8]

        if good_supply:
            avg_ret_good = sum(d["ret_1w"] for d in good_supply) / len(good_supply)
            print(f"  수급 좋음 (8점+): {len(good_supply)}개, 평균 {avg_ret_good:+.2f}%")

        if bad_supply:
            avg_ret_bad = sum(d["ret_1w"] for d in bad_supply) / len(bad_supply)
            print(f"  수급 나쁨 (8점-): {len(bad_supply)}개, 평균 {avg_ret_bad:+.2f}%")

    print("\n[비반도체 섹터]")
    print(f"종목 수: {len(non_semiconductor)}개")
    if non_semiconductor:
        avg_ret_1w = sum(d["ret_1w"] for d in non_semiconductor) / len(non_semiconductor)
        avg_supply = sum(d["supply_score"] for d in non_semiconductor) / len(non_semiconductor)
        print(f"평균 1주 수익률: {avg_ret_1w:+.2f}%")
        print(f"평균 수급 점수: {avg_supply:.1f}점")


def analyze_supply_pattern():
    """수급 패턴별 분석"""
    print("\n" + "=" * 80)
    print("📈 반도체 종목 수급 패턴별 분석")
    print("=" * 80)

    semiconductor = [d for d in all_data if is_semiconductor(d["themes"])]

    # 패턴별 분류
    patterns = {
        "외국인+기관 동반": [d for d in semiconductor if "외국인+기관" in d["supply"] or d["supply_score"] >= 15],
        "외국인 or 기관": [d for d in semiconductor if "3일연속" in d["supply"] and d["supply_score"] == 10],
        "수급 약함": [d for d in semiconductor if d["supply_score"] <= 6],
    }

    for pattern_name, stocks in patterns.items():
        if stocks:
            print(f"\n[{pattern_name}] ({len(stocks)}개)")
            avg_ret = sum(d["ret_1w"] for d in stocks) / len(stocks)
            win_rate = len([d for d in stocks if d["ret_1w"] > 0]) / len(stocks) * 100
            print(f"  평균 1주 수익률: {avg_ret:+.2f}%")
            print(f"  승률: {win_rate:.1f}%")

            for stock in stocks:
                print(f"    - {stock['name']}: {stock['ret_1w']:+.2f}% (수급 {stock['supply_score']}점)")


def analyze_volume_effect():
    """거래량 효과 분석"""
    print("\n" + "=" * 80)
    print("💹 거래량 효과 분석")
    print("=" * 80)

    # 거래량 데이터가 있는 종목만
    with_volume = [d for d in additional_data if "volume_surge" in d]

    if with_volume:
        volume_surge = [d for d in with_volume if d["volume_surge"]]
        no_surge = [d for d in with_volume if not d["volume_surge"]]

        print(f"\n[거래량 급증 종목] ({len(volume_surge)}개)")
        if volume_surge:
            avg_ret = sum(d["ret_1w"] for d in volume_surge) / len(volume_surge)
            print(f"  평균 1주 수익률: {avg_ret:+.2f}%")
            for stock in volume_surge:
                print(f"    - {stock['name']}: {stock['ret_1w']:+.2f}%")

        print(f"\n[거래량 보통] ({len(no_surge)}개)")
        if no_surge:
            avg_ret = sum(d["ret_1w"] for d in no_surge) / len(no_surge)
            print(f"  평균 1주 수익률: {avg_ret:+.2f}%")
            for stock in no_surge:
                print(f"    - {stock['name']}: {stock['ret_1w']:+.2f}%")


def detailed_analysis():
    """상세 종목별 분석"""
    print("\n" + "=" * 80)
    print("🔬 반도체 종목 상세 분석")
    print("=" * 80)

    semiconductor = [d for d in all_data if is_semiconductor(d["themes"])]
    semiconductor_sorted = sorted(semiconductor, key=lambda x: x["ret_1w"], reverse=True)

    print(f"\n{'종목명':<15} {'테마':<25} {'수급':<20} {'수급점수':<8} {'1주':<8} {'1달':<8}")
    print("-" * 100)

    for stock in semiconductor_sorted:
        print(f"{stock['name']:<15} {stock['themes'][:24]:<25} {stock['supply'][:19]:<20} "
              f"{stock['supply_score']:<8} {stock['ret_1w']:>+6.1f}% {stock.get('ret_1m', 0):>+6.1f}%")


def conclusion():
    """결론 도출"""
    print("\n" + "=" * 80)
    print("💡 결론 및 권장사항")
    print("=" * 80)

    semiconductor = [d for d in all_data if is_semiconductor(d["themes"])]

    # 수급 좋은 vs 나쁜
    good_supply = [d for d in semiconductor if d["supply_score"] >= 8]
    bad_supply = [d for d in semiconductor if d["supply_score"] < 8]

    if good_supply and bad_supply:
        avg_good = sum(d["ret_1w"] for d in good_supply) / len(good_supply)
        avg_bad = sum(d["ret_1w"] for d in bad_supply) / len(bad_supply)
        diff = avg_good - avg_bad

        print(f"\n반도체 종목에서:")
        print(f"  수급 좋음 (8점+): 평균 {avg_good:+.2f}%")
        print(f"  수급 나쁨 (8점-): 평균 {avg_bad:+.2f}%")
        print(f"  차이: {diff:+.2f}%p")

        if abs(diff) < 2:
            print("\n  → 반도체 섹터에서도 수급의 예측력은 낮음")
            print("  → 거래량/거래대금 중심으로 전환 추천")
        elif diff > 3:
            print("\n  → 반도체 섹터에서는 수급이 유의미")
            print("  → 현재 로직 유지 또는 강화 고려")
        else:
            print("\n  → 반도체 섹터에서 수급이 약간 유의미")
            print("  → 수급(8점) + 거래대금(7점) 혼합 추천")


if __name__ == "__main__":
    analyze_by_sector()
    analyze_supply_pattern()
    analyze_volume_effect()
    detailed_analysis()
    conclusion()
