"""
universe.py
구조적 테마 내 전체 종목 유니버스를 구성한다.
"오늘 급등 여부"와 무관하게, 테마에 속한 모든 종목이 대상.
"""

import os
import json
import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from collections import defaultdict

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ── 한국: 구조적 테마 ID (네이버 금융) ────────────────────────────────────────
KR_STRUCTURAL_THEMES = {
    # AI 하드웨어
    "광통신": 586,
    "HBM": 536,
    "시스템반도체": 307,
    "전력반도체": 533,
    "반도체장비": 144,
    "PCB": 287,
    "SOCAMM": 599,
    "온디바이스AI": 545,
    "MLCC": 405,
    "반도체대표주": 155,
    # 에너지/전력
    "원자력발전": 205,
    "초고압변압기": 123,
    "SOFC": 559,
    "LNG": 381,
    # 방산/조선
    "조선": 30,
    "방위산업": 94,
    "우주항공": 200,
    "드론": 349,
    # 2차전지/모빌리티
    "2차전지": 64,
    "전기차": 227,
    # 기타 구조적
    "로봇": 505,
}

# ── 미국: Finviz 산업 필터 ────────────────────────────────────────────────────
US_STRUCTURAL_INDUSTRIES = {
    "AI Semiconductors": "ind_semiconductors,cap_largeover",
    "Semiconductor Equipment": "ind_semiconductorequipment,cap_midover",
    "Defense & Aerospace": "ind_aerospacedefense,cap_midover",
    "Nuclear & Utilities": "ind_utilitiesregulated,cap_largeover",
    "Electrical Equipment": "ind_electricalequipment,cap_midover",
    "Communication Equipment": "ind_communicationequipment,cap_midover",
    "EV & Auto Parts": "ind_autoparts,cap_midover",
    "Solar & Renewable": "ind_solar,cap_midover",
    "Biotech": "ind_biotechnology,cap_largeover",
    "Cloud & Software": "ind_softwareinfrastructure,cap_largeover",
}


def _code_to_ticker(code: str) -> str:
    """6자리 종목코드 → yfinance 티커."""
    code = code.strip()
    if code[0] in ("1", "2", "3", "4"):
        return f"{code}.KQ"
    return f"{code}.KS"


def _fetch_theme_stocks(theme_no: int) -> List[Dict]:
    """네이버 테마 상세에서 전체 종목 추출."""
    url = f"https://finance.naver.com/sise/sise_group_detail.naver?type=theme&no={theme_no}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")

        stocks = []
        for row in soup.find_all("tr"):
            for link in row.find_all("a", href=True):
                href = link.get("href", "")
                if "code=" in href:
                    code = href.split("code=")[-1].split("&")[0]
                    if len(code) == 6 and code.isdigit():
                        name = link.get_text(strip=True)
                        stocks.append({
                            "code": code,
                            "ticker": _code_to_ticker(code),
                            "name": name,
                        })
                    break
        return stocks
    except Exception as e:
        print(f"  [오류] theme_no={theme_no}: {e}")
        return []


def build_kr_universe() -> List[Dict]:
    """한국 구조적 테마 내 전체 종목 유니버스 구성.
    반환: [{"ticker": "009540.KS", "name": "HD한국조선해양", "code": "009540",
            "themes": ["조선"]}]
    """
    print(f"[KR 유니버스] {len(KR_STRUCTURAL_THEMES)}개 구조적 테마 종목 수집 중...")
    ticker_map = {}  # ticker -> {name, code, themes: set}

    for theme_name, theme_no in KR_STRUCTURAL_THEMES.items():
        stocks = _fetch_theme_stocks(theme_no)
        for s in stocks:
            t = s["ticker"]
            if t not in ticker_map:
                ticker_map[t] = {
                    "ticker": t,
                    "name": s["name"],
                    "code": s["code"],
                    "themes": set(),
                }
            ticker_map[t]["themes"].add(theme_name)

    # 네이버 테마에 빠진 핵심 방산 종목 수동 추가
    MANUAL_ADDITIONS = {
        "012450.KS": {"name": "한화에어로스페이스", "code": "012450", "themes": ["방위산업"]},
        "079550.KS": {"name": "LIG넥스원", "code": "079550", "themes": ["방위산업"]},
        "064350.KS": {"name": "현대로템", "code": "064350", "themes": ["방위산업"]},
    }
    for ticker, info in MANUAL_ADDITIONS.items():
        if ticker not in ticker_map:
            ticker_map[ticker] = {
                "ticker": ticker,
                "name": info["name"],
                "code": info["code"],
                "themes": set(info["themes"]),
            }
        else:
            for t in info["themes"]:
                ticker_map[ticker]["themes"].add(t)

    # set → list 변환
    universe = []
    for v in ticker_map.values():
        v["themes"] = sorted(v["themes"])
        universe.append(v)

    print(f"[KR 유니버스] {len(universe)}개 종목 (중복 제거 완료)")
    return universe


def _parse_finviz_industry(industry_filter: str, max_items: int = 30) -> List[Dict]:
    """Finviz 산업 필터로 종목 추출."""
    url = f"https://finviz.com/screener.ashx?v=111&f={industry_filter}&o=-perf4w"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        items = []
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                tds = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(tds) >= 10 and tds[0].isdigit():
                    items.append({
                        "ticker": tds[1],
                        "name": tds[2],
                        "sector": tds[3],
                        "industry": tds[4],
                        "market_cap": tds[6],
                    })
                    if len(items) >= max_items:
                        break
            if items:
                break
        return items
    except Exception as e:
        print(f"  [오류] {industry_filter}: {e}")
        return []


def build_us_universe() -> List[Dict]:
    """미국 유니버스: us_themes.json(세분화 테마) + Finviz(산업 보완) 병합."""
    ticker_map = {}

    # 1. us_themes.json에서 세분화된 테마별 종목 로드
    themes_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "us_themes.json")
    if os.path.exists(themes_file):
        with open(themes_file, "r", encoding="utf-8") as f:
            us_themes = json.load(f)
        for theme_name, tickers in us_themes.items():
            for t in tickers:
                if t not in ticker_map:
                    ticker_map[t] = {
                        "ticker": t,
                        "name": "",
                        "sector": "",
                        "themes": set(),
                    }
                ticker_map[t]["themes"].add(theme_name)
        print(f"[US 유니버스] us_themes.json: {len(ticker_map)}개 종목, {len(us_themes)}개 테마")

    # 2. Finviz 산업 필터로 보완 (themes.json에 없는 종목 추가)
    print(f"[US 유니버스] Finviz {len(US_STRUCTURAL_INDUSTRIES)}개 산업 보완 중...")
    for theme_name, industry_filter in US_STRUCTURAL_INDUSTRIES.items():
        stocks = _parse_finviz_industry(industry_filter, max_items=20)
        for s in stocks:
            t = s["ticker"]
            if t not in ticker_map:
                ticker_map[t] = {
                    "ticker": t,
                    "name": s["name"],
                    "sector": s.get("sector", ""),
                    "themes": set(),
                }
            ticker_map[t]["themes"].add(theme_name)

    universe = []
    for v in ticker_map.values():
        v["themes"] = sorted(v["themes"])
        universe.append(v)

    print(f"[US 유니버스] 총 {len(universe)}개 종목 (중복 제거 완료)")
    return universe


if __name__ == "__main__":
    print("=" * 60)
    print("  구조적 테마 유니버스 구성")
    print("=" * 60)

    kr = build_kr_universe()
    print(f"\n한국 유니버스 샘플:")
    for s in kr[:10]:
        print(f"  {s['ticker']:<12} {s['name']:<20} [{', '.join(s['themes'])}]")

    print()
    us = build_us_universe()
    print(f"\n미국 유니버스 샘플:")
    for s in us[:10]:
        print(f"  {s['ticker']:<8} {s['name'][:25]:<27} [{', '.join(s['themes'])}]")

    # 테마별 종목 수 통계
    print(f"\n{'='*60}")
    kr_theme_counts = defaultdict(int)
    for s in kr:
        for t in s["themes"]:
            kr_theme_counts[t] += 1
    for t, c in sorted(kr_theme_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:<20} {c}개")
