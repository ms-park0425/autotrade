"""
scorer_v2.py
1개월 기대수익률 스코어링 (v2).
"지금 얼마나 올랐나"가 아니라 "앞으로 얼마나 오를 여지가 있나"를 평가.

5팩터 (총 100점):
  1. 밸류에이션 괴리 (30점) — Forward PE/PEG 기반 저평가도
  2. 실적 모멘텀 (25점) — 26E 컨센서스 성장률
  3. 테마 구조성 (20점) — 소속 테마 지속성 + 구조적 판정
  4. 진입 타이밍 (15점) — RSI/볼린저/눌림목 (과열 감점)
  5. 수급 추세 (10점) — 외국인/기관 다일 순매수 (한국만)
"""

import warnings
warnings.filterwarnings("ignore")

import os
import json
import pickle
from datetime import datetime
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import ta as ta_lib
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

_V2_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "v2")
_PRICE_CACHE_FILE = os.path.join(_V2_DATA_DIR, "price_cache.pkl")
_BACKLOG_CACHE_FILE = os.path.join(_V2_DATA_DIR, "backlog_cache.json")
# 수주잔고 캐시: {날짜: {ticker: backlog_data}}
# 당일 날짜 키가 있으면 Tavily 호출 없이 재사용
def _load_backlog_cache() -> dict:
    try:
        if os.path.exists(_BACKLOG_CACHE_FILE):
            with open(_BACKLOG_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_backlog_cache(cache: dict):
    os.makedirs(_V2_DATA_DIR, exist_ok=True)
    try:
        with open(_BACKLOG_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [수주잔고 캐시 저장 오류] {e}")


# ─────────────────────────────────────────────────────────────────────────────
# FMP (Financial Modeling Prep) — US 종목 Forward PE / 애널리스트 컨센서스 보완
# FMP_API_KEY 환경변수 있을 때만 활성화. 없으면 yfinance만 사용.
# ─────────────────────────────────────────────────────────────────────────────

_FMP_CACHE_FILE = os.path.join(_V2_DATA_DIR, "fmp_cache.json")
_fmp_daily_cache: dict = {}  # {ticker: {fwd_pe_fmp, eps_g, rev_g, ...}}  read-only during parallel scoring


def _load_fmp_disk_cache() -> dict:
    """당일 FMP 캐시 디스크에서 로드."""
    today = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(_FMP_CACHE_FILE):
        return {}
    try:
        with open(_FMP_CACHE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("date") == today:
            return d.get("cache", {})
    except Exception:
        pass
    return {}


def _save_fmp_disk_cache():
    """_fmp_daily_cache 디스크 저장."""
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(_V2_DATA_DIR, exist_ok=True)
    try:
        with open(_FMP_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"date": today, "cache": _fmp_daily_cache}, f, ensure_ascii=False)
    except Exception as e:
        print(f"  [FMP 캐시 저장 오류] {e}")


def _fmp_parse_estimates(data: list) -> dict:
    """FMP analyst-estimates 응답 파싱 (stable endpoint).
    반환: {eps_g, rev_g, eps_g_1y, rev_g_1y, n_analysts, fwd_eps}

    stable endpoint(2025/9~) 응답 필드:
      epsAvg, revenueAvg, numAnalystsEps
      (옛 estimatedEpsAvg/estimatedRevenueAvg/numberAnalystEstimatedEps 대체)
    과거 actuals(reportedEps/actualRevenue)는 stable 응답에 없음 → 작년 추정치만 prev로 사용.
    """
    if not data or not isinstance(data, list):
        return {}
    current_year = datetime.now().year
    data_sorted = sorted(data, key=lambda x: x.get("date", ""))
    future = [d for d in data_sorted if int((d.get("date") or "0")[:4]) >= current_year]
    past   = [d for d in data_sorted if int((d.get("date") or "0")[:4]) < current_year]

    if not future:
        return {}

    this_y = future[0]
    next_y = future[1] if len(future) > 1 else None

    eps_0y  = this_y.get("epsAvg") or 0
    rev_0y  = this_y.get("revenueAvg") or 0
    n_anal  = this_y.get("numAnalystsEps") or 0

    result: dict = {"n_analysts": n_anal, "fwd_eps": eps_0y}

    # 성장률: 올해 추정 vs 작년 추정
    if past:
        prev = past[-1]
        prev_eps = prev.get("epsAvg") or 0
        prev_rev = prev.get("revenueAvg") or 0
        if prev_eps:
            result["eps_g"] = (eps_0y - prev_eps) / abs(prev_eps)
        if prev_rev:
            result["rev_g"] = (rev_0y - prev_rev) / abs(prev_rev)

    # +1y 성장률
    if next_y:
        eps_1y = next_y.get("epsAvg") or 0
        rev_1y = next_y.get("revenueAvg") or 0
        if eps_0y:
            result["eps_g_1y"] = (eps_1y - eps_0y) / abs(eps_0y)
        if rev_0y:
            result["rev_g_1y"] = (rev_1y - rev_0y) / abs(rev_0y)

    return result


def _prefetch_fmp_us(us_tickers: list):
    """US 종목 전체에 대해 FMP 데이터를 사전 조회 (stable endpoint).
    score_universe() 병렬 스코어링 직전에 단독 실행 → 이후 read-only.

    stable endpoint(2025/9~)는 batch 미지원(Premium 전용)이라 종목별 단일 호출.
    종목당 3 API 호출 (quote → ratios-ttm → analyst-estimates).
    """
    global _fmp_daily_cache
    import time as _t

    api_key = os.environ.get("FMP_API_KEY", "")
    if not api_key or not us_tickers:
        return

    _fmp_daily_cache = _load_fmp_disk_cache()
    to_fetch = [t for t in us_tickers if t not in _fmp_daily_cache]
    if not to_fetch:
        print(f"[FMP] 전체 캐시 히트 ({len(_fmp_daily_cache)}개 종목)")
        return

    print(f"[FMP] {len(to_fetch)}개 US 종목 데이터 조회 중 (종목당 3 API)...")
    base = "https://financialmodelingprep.com/stable"

    for ticker in to_fetch:
        # 1) Quote: 현재가
        try:
            r = requests.get(f"{base}/quote",
                             params={"symbol": ticker, "apikey": api_key}, timeout=10)
            if r.status_code == 200:
                arr = r.json()
                if arr and isinstance(arr, list):
                    item = arr[0]
                    _fmp_daily_cache.setdefault(ticker, {}).update({
                        "price_fmp": item.get("price"),
                    })
        except Exception:
            pass

        # 2) Ratios TTM: PE, PEG (옛 quote의 pe 필드 대체)
        try:
            r = requests.get(f"{base}/ratios-ttm",
                             params={"symbol": ticker, "apikey": api_key}, timeout=10)
            if r.status_code == 200:
                arr = r.json()
                if arr and isinstance(arr, list):
                    item = arr[0]
                    _fmp_daily_cache.setdefault(ticker, {}).update({
                        "pe_ttm":  item.get("priceToEarningsRatioTTM"),
                        "peg_ttm": item.get("priceToEarningsGrowthRatioTTM"),
                    })
        except Exception:
            pass

        # 3) Analyst estimates: EPS/매출 성장률
        if not _fmp_daily_cache.get(ticker, {}).get("_est_done"):
            try:
                r = requests.get(
                    f"{base}/analyst-estimates",
                    params={"symbol": ticker, "period": "annual", "limit": 6, "apikey": api_key},
                    timeout=10,
                )
                parsed = _fmp_parse_estimates(r.json()) if r.status_code == 200 else {}
                _fmp_daily_cache.setdefault(ticker, {}).update(parsed)
                # Forward PE = 현재가 / Forward EPS
                price   = _fmp_daily_cache[ticker].get("price_fmp")
                fwd_eps = parsed.get("fwd_eps", 0)
                if price and fwd_eps and fwd_eps > 0:
                    _fmp_daily_cache[ticker]["fwd_pe_fmp"] = round(price / fwd_eps, 1)
            except Exception:
                pass
            _fmp_daily_cache.setdefault(ticker, {})["_est_done"] = True

        _t.sleep(0.05)  # FMP rate-limit 여유 (분당 ~20 req per ticker × 3 = 60 calls)

    _save_fmp_disk_cache()
    print(f"[FMP] 완료: 신규 {len(to_fetch)}개 조회, 총 {len(_fmp_daily_cache)}개 캐시")


def _apply_fmp_to_result(r: dict, fmp: dict):
    """단일 결과 dict에 FMP 데이터 인플레이스 적용 (earn_detail/val_detail 공란인 경우만)."""
    # ── 실적 모멘텀 보강 ──────────────────────────────────────────────────────
    if not r.get("earn_detail"):
        eps_g    = fmp.get("eps_g")
        rev_g    = fmp.get("rev_g")
        eps_g_1y = fmp.get("eps_g_1y")
        n_anal   = int(fmp.get("n_analysts") or 0)

        if eps_g is not None or rev_g is not None:
            base_earn, earn_detail = 8, ""
            if eps_g is not None and rev_g is not None:
                if   eps_g > 0.50 and rev_g > 0.20: base_earn, earn_detail = 20, f"26E 매출{rev_g*100:.0f}%·EPS{eps_g*100:.0f}% 폭발 (FMP)"
                elif eps_g > 0.25 and rev_g > 0.10: base_earn, earn_detail = 17, f"26E 매출{rev_g*100:.0f}%·EPS{eps_g*100:.0f}% 고성장 (FMP)"
                elif eps_g > 0.10 and rev_g > 0:    base_earn, earn_detail = 13, f"26E 매출{rev_g*100:.0f}%·EPS{eps_g*100:.0f}% 양호 (FMP)"
                elif eps_g > 0:                      base_earn, earn_detail = 10, f"26E EPS{eps_g*100:.0f}% 소폭 (FMP)"
                elif eps_g < -0.10:                  base_earn, earn_detail = 3,  f"26E EPS{eps_g*100:.0f}% 감익 (FMP)"
                else:                                base_earn, earn_detail = 7,  f"26E EPS{eps_g*100:.0f}% 보합 (FMP)"
            elif eps_g is not None:
                base_earn = 16 if eps_g > 0.30 else (12 if eps_g > 0.10 else (4 if eps_g < 0 else 8))
                earn_detail = f"26E EPS{eps_g*100:.0f}% (FMP)"
            if eps_g_1y is not None and earn_detail:
                if   eps_g_1y > 0.20:  base_earn = min(25, base_earn + 5); earn_detail += f" → 27E EPS{eps_g_1y*100:.0f}% 지속"
                elif eps_g_1y > 0.10:  base_earn = min(25, base_earn + 3); earn_detail += f" → 27E {eps_g_1y*100:.0f}%"
                elif eps_g_1y < -0.10: base_earn = max(0,  base_earn - 3); earn_detail += f" → 27E {eps_g_1y*100:.0f}% 꺾임"
            if n_anal >= 10: base_earn = min(25, base_earn + 2)
            elif n_anal >= 5: base_earn = min(25, base_earn + 1)
            base_earn = max(0, min(25, base_earn))
            diff = base_earn - r.get("earnings_score", 10)
            r["earnings_score"] = base_earn
            r["earn_detail"]    = earn_detail
            r["expected_return_score"] = round(r.get("expected_return_score", 0) + diff, 1)
            if n_anal > (r.get("n_analysts") or 0):
                r["n_analysts"] = n_anal

    # ── 밸류에이션 보강 ───────────────────────────────────────────────────────
    if not r.get("val_detail"):
        fwd_pe = float(fmp.get("fwd_pe_fmp") or 0)
        if fwd_pe > 0:
            old_val = r.get("valuation_score", 15)
            if   fwd_pe < 10:  new_val, tag = 28, f"Fwd PE {fwd_pe:.1f} 저평가 (FMP)"
            elif fwd_pe < 20:  new_val, tag = 22, f"Fwd PE {fwd_pe:.1f} 합리적 (FMP)"
            elif fwd_pe < 35:  new_val, tag = 15, f"Fwd PE {fwd_pe:.1f} 적정 (FMP)"
            elif fwd_pe < 60:  new_val, tag = 8,  f"Fwd PE {fwd_pe:.1f} 부담 (FMP)"
            else:              new_val, tag = 3,  f"Fwd PE {fwd_pe:.1f} 고평가 (FMP)"
            diff = new_val - old_val
            r["valuation_score"] = new_val
            r["val_detail"]      = tag
            r["fwd_pe"]          = fwd_pe
            r["expected_return_score"] = round(r.get("expected_return_score", 0) + diff, 1)


def _enrich_with_fmp(results: list) -> list:
    """캐시에서 로드된 결과에 FMP 데이터 사후 적용 (US 종목, 공란 필드만)."""
    if not _fmp_daily_cache:
        return results
    for r in results:
        if not r.get("ticker", "").endswith((".KS", ".KQ")):
            fmp = _fmp_daily_cache.get(r["ticker"], {})
            if fmp:
                _apply_fmp_to_result(r, fmp)
    return results


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# 수주산업 종목 (PEG 대신 수주잔고 기반 밸류에이션 적용)
ORDER_BACKLOG_TICKERS = {
    # 조선
    "009540.KS", "010140.KS", "042660.KS", "097230.KS",  # HD한국조선, 삼성중공업, 한화오션, HJ중공업
    # 방산
    "012450.KS", "047810.KS", "000880.KS",  # 한화에어로, 한국항공우주, 한화
    "079550.KS", "064350.KS",  # LIG넥스원, 현대로템
    "LMT", "RTX", "GD", "NOC", "BA", "HII",  # 미국 방산
    # 원전/플랜트
    "034020.KS", "009830.KS",  # 두산에너빌리티, 한화솔루션
    # 건설/플랜트
    "006360.KS", "000210.KS", "053690.KS",  # GS건설, DL이앤씨, 한미글로벌
}


BACKLOG_QUERY_MAP = {
    "009540.KS": "HD Korea Shipbuilding KSOE order backlog 수주잔고 2026",
    "010140.KS": "Samsung Heavy Industries order backlog 수주잔고 2026",
    "042660.KS": "Hanwha Ocean order backlog 수주잔고 2026",
    "097230.KS": "HJ Shipbuilding order backlog 수주잔고 2026",
    "012450.KS": "Hanwha Aerospace order backlog 수주잔고 2026",
    "047810.KS": "Korea Aerospace Industries KAI order backlog 수주잔고 2026",
    "079550.KS": "LIG Nex1 order backlog defense contract 2026",
    "064350.KS": "Hyundai Rotem order backlog K2 tank defense 2026",
    "000880.KS": "Hanwha Corporation defense order backlog 2026",
    "034020.KS": "Doosan Enerbility nuclear order backlog 수주잔고 2026",
    "006360.KS": "GS Engineering Construction order backlog 수주잔고 2026",
    "053690.KS": "Hanmi Global order backlog 수주잔고 2026",
    "LMT": "Lockheed Martin order backlog 2026",
    "RTX": "RTX Raytheon order backlog 2026",
    "GD": "General Dynamics order backlog 2026",
    "NOC": "Northrop Grumman order backlog 2026",
    "BA": "Boeing order backlog 2026",
}


def _fetch_backlog_ratio(ticker: str, market_cap: float) -> Optional[Dict]:
    """Tavily로 수주잔고를 검색하고 시가총액 대비 비율 산출. 당일 캐시 우선."""
    today = datetime.now().strftime("%Y-%m-%d")
    cache = _load_backlog_cache()
    if today in cache and ticker in cache[today]:
        return cache[today][ticker]

    try:
        from tavily import TavilyClient
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key or market_cap <= 0:
            return None
        client = TavilyClient(api_key=api_key)

        query = BACKLOG_QUERY_MAP.get(ticker, f"{ticker} order backlog 2026")
        r = client.search(query=query, search_depth="basic", max_results=3, include_answer=True)
        answer = r.get("answer", "")
        if not answer:
            return None

        # 답변에서 숫자 추출 시도 (조, 억, billion, trillion)
        import re
        backlog_value = 0

        # 한국식: XX조, XX억
        jo_match = re.search(r'(\d+[\d,.]*)\s*조', answer)
        eok_match = re.search(r'(\d+[\d,.]*)\s*억', answer)
        if jo_match:
            backlog_value = float(jo_match.group(1).replace(",", "")) * 1_000_000_000_000
        elif eok_match:
            backlog_value = float(eok_match.group(1).replace(",", "")) * 100_000_000

        # 영문: $XXB, XX billion
        b_match = re.search(r'\$\s*(\d+[\d,.]*)\s*(?:billion|B\b)', answer, re.IGNORECASE)
        if b_match and backlog_value == 0:
            backlog_value = float(b_match.group(1).replace(",", "")) * 1_000_000_000

        # 수주잔고 연수
        years_match = re.search(r'(\d+[\d.]*)\s*(?:year|년)', answer, re.IGNORECASE)
        years_of_work = float(years_match.group(1)) if years_match else 0

        if backlog_value <= 0 and years_of_work <= 0:
            return None

        backlog_to_cap = backlog_value / market_cap if market_cap > 0 and backlog_value > 0 else 0

        # 읽기 쉬운 포맷
        if backlog_value >= 1_000_000_000_000:
            backlog_str = f"{backlog_value/1_000_000_000_000:.1f}조원"
        elif backlog_value >= 1_000_000_000:
            backlog_str = f"${backlog_value/1_000_000_000:.1f}B"
        else:
            backlog_str = f"{backlog_value/100_000_000:.0f}억"

        result = {
            "backlog_str": backlog_str,
            "backlog_to_cap": round(backlog_to_cap, 2),
            "years_of_work": round(years_of_work, 1),
            "source": answer[:100],
        }
        # 당일 캐시 저장
        if today not in cache:
            cache[today] = {}
        cache[today][ticker] = result
        _save_backlog_cache(cache)
        return result
    except Exception:
        return None


def _safe(value, default=0.0):
    try:
        v = float(value)
        return v if pd.notna(v) else default
    except (TypeError, ValueError):
        return default


def _fetch_kr_investor_flow(code: str, days: int = 5) -> Optional[Dict]:
    """네이버 금융에서 외국인/기관 수급 데이터."""
    url = f"https://finance.naver.com/item/frgn.naver?code={code}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")

        foreign_net, inst_net, foreign_ratio = 0, 0, 0.0
        count = 0
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
                if count >= days:
                    break
                try:
                    inst_net += int(tds[5].replace(",", "").replace("+", "") or "0")
                    foreign_net += int(tds[6].replace(",", "").replace("+", "") or "0")
                    if count == 0 and len(tds) > 8:
                        foreign_ratio = float(tds[8].replace("%", "").replace(",", "") or "0")
                    count += 1
                except (ValueError, IndexError):
                    continue
            break

        return {
            "foreign_net_5d": foreign_net,
            "inst_net_5d": inst_net,
            "foreign_ratio": round(foreign_ratio, 2),
        }
    except Exception:
        return None


def score_stock(
    ticker: str,
    theme_info: Dict = None,
    kr_name: str = "",
    price_df: Optional[pd.DataFrame] = None,
    info_cache: Optional[Dict] = None,
) -> Optional[Dict]:
    """단일 종목의 1개월 기대수익률 스코어를 산출.
    theme_info: {"themes": [...], "persistence": float, "is_structural": bool}
    kr_name: 네이버에서 가져온 한글 종목명 (한국 종목용)
    price_df: 미리 다운로드된 1년 가격 히스토리 (없으면 직접 조회)
    info_cache: 호출자가 공유하는 {ticker: info_dict} 캐시 — 3개 모델 간 .info 중복 호출 방지
    """
    import time as _time

    if theme_info is None:
        theme_info = {"themes": [], "persistence": 0, "is_structural": False}

    try:
        stock = yf.Ticker(ticker)

        if price_df is not None and not price_df.empty:
            df = price_df
            # yfinance 신버전 MultiIndex 컬럼 정규화
            if isinstance(df.columns, pd.MultiIndex):
                try:
                    df = df.xs(ticker, axis=1, level="Ticker", drop_level=True)
                except Exception:
                    df = df.xs(ticker, axis=1, level=1, drop_level=True)
        else:
            for _attempt in range(3):
                try:
                    df = stock.history(period="1y", auto_adjust=True)
                    break
                except Exception as _e:
                    if "Too Many Requests" in str(_e) or "RateLimit" in str(type(_e).__name__):
                        _time.sleep(5 + _attempt * 5)
                    else:
                        raise
            else:
                return None

        if df.empty or len(df) < 60:
            return None

        # 미국 장 미개장 시간(KST 오전)에 Close=NaN 행이 붙는 문제 제거
        # 또한 가격캐시 컬럼 불일치로 인한 NaN 과다 행 감지: 전체 80% 이상 NaN이면 캐시 손상
        close_col = df["Close"] if "Close" in df.columns else None
        if close_col is None:
            return None
        if close_col.isna().mean() > 0.5:
            # 캐시 손상 → yfinance 직접 재조회
            try:
                df = stock.history(period="1y", auto_adjust=True)
            except Exception:
                return None
        df = df[df["Close"].notna()]
        if df.empty or len(df) < 60:
            return None

        # .info 캐시 확인 → 없으면 fetch 후 저장 (401 시 3회 재시도)
        if info_cache is not None and ticker in info_cache:
            info = info_cache[ticker]
        else:
            info = {}
            for _attempt in range(3):
                try:
                    info = stock.info or {}
                    break
                except Exception as _e:
                    err = str(_e)
                    if "401" in err or "Invalid Crumb" in err or "Too Many Requests" in err:
                        _time.sleep(3 + _attempt * 5)
                    else:
                        break
            if info_cache is not None:
                info_cache[ticker] = info
        close = df["Close"]
        volume = df["Volume"]
        high = df["High"]
        low = df["Low"]
        cur_price = _safe(close.iloc[-1])

        if cur_price <= 0:
            return None

        # 시가총액 필터
        market_cap = _safe(info.get("marketCap", 0))
        is_kr = ticker.endswith(".KS") or ticker.endswith(".KQ")
        if is_kr and market_cap > 0 and market_cap < 100_000_000_000:  # 1000억 미만
            return None
        if not is_kr and market_cap > 0 and market_cap < 500_000_000:  # $500M 미만
            return None

        # ─────────────────────────────────────────────────────────────
        # 팩터 1: 밸류에이션 괴리 (30점)
        # ─────────────────────────────────────────────────────────────
        val_score = 15  # 기본점수 (데이터 없으면 중립)
        val_detail = ""

        fwd_pe = _safe(info.get("forwardPE"), 0)
        trailing_pe = _safe(info.get("trailingPE"), 0)
        peg = _safe(info.get("pegRatio"), 0)

        # Forward 컨센서스 (2026E=0y, 2027E=+1y)
        fwd = {}
        try:
            ee = stock.earnings_estimate
            if ee is not None and not ee.empty:
                if "0y" in ee.index:
                    fwd["eps_growth_0y"] = _safe(ee.loc["0y", "growth"], None)
                    fwd["n_analysts"] = int(_safe(ee.loc["0y", "numberOfAnalysts"], 0))
                if "+1y" in ee.index:
                    fwd["eps_growth_1y"] = _safe(ee.loc["+1y", "growth"], None)
                    fwd["n_analysts_1y"] = int(_safe(ee.loc["+1y", "numberOfAnalysts"], 0))
        except Exception:
            pass
        try:
            rev_est = stock.revenue_estimate
            if rev_est is not None and not rev_est.empty:
                if "0y" in rev_est.index:
                    fwd["rev_growth_0y"] = _safe(rev_est.loc["0y", "growth"], None)
                    fwd["n_analysts"] = max(fwd.get("n_analysts", 0),
                                            int(_safe(rev_est.loc["0y", "numberOfAnalysts"], 0)))
                if "+1y" in rev_est.index:
                    fwd["rev_growth_1y"] = _safe(rev_est.loc["+1y", "growth"], None)
        except Exception:
            pass

        # FMP 보완: US 종목 yfinance 누락 데이터 채우기 (FMP_API_KEY 있을 때)
        if not is_kr and _fmp_daily_cache:
            _fmp = _fmp_daily_cache.get(ticker, {})
            if _fmp:
                if fwd_pe <= 0 and (_fmp.get("fwd_pe_fmp") or 0) > 0:
                    fwd_pe = float(_fmp["fwd_pe_fmp"])
                if fwd.get("eps_growth_0y") is None and _fmp.get("eps_g") is not None:
                    fwd["eps_growth_0y"] = _fmp["eps_g"]
                if fwd.get("rev_growth_0y") is None and _fmp.get("rev_g") is not None:
                    fwd["rev_growth_0y"] = _fmp["rev_g"]
                if fwd.get("eps_growth_1y") is None and _fmp.get("eps_g_1y") is not None:
                    fwd["eps_growth_1y"] = _fmp["eps_g_1y"]
                if fwd.get("rev_growth_1y") is None and _fmp.get("rev_g_1y") is not None:
                    fwd["rev_growth_1y"] = _fmp["rev_g_1y"]
                if not fwd.get("n_analysts") and _fmp.get("n_analysts"):
                    fwd["n_analysts"] = int(_fmp["n_analysts"])

        # 수주산업 여부 판별
        is_backlog_industry = ticker in ORDER_BACKLOG_TICKERS
        backlog_data = None

        if is_backlog_industry:
            # 수주산업: 수주잔고 + 매출 대비 소화 기간 기반 밸류에이션
            backlog_data = _fetch_backlog_ratio(ticker, market_cap)
            if backlog_data:
                bstr = backlog_data["backlog_str"]
                b2c = backlog_data["backlog_to_cap"]
                backlog_value = b2c * market_cap if b2c > 0 else 0

                # 연간 매출로 소화 기간 계산
                annual_rev = _safe(info.get("totalRevenue", 0))
                if annual_rev > 0 and backlog_value > 0:
                    digest_years = backlog_value / annual_rev
                else:
                    digest_years = backlog_data.get("years_of_work", 0)

                # 소화 기간별 기본 점수 (빠를수록 매출 전환이 빨라 좋음)
                if digest_years <= 2.0:
                    base = 25
                    speed_tag = f"소화 {digest_years:.1f}년 (빠름)"
                elif digest_years <= 3.5:
                    base = 22
                    speed_tag = f"소화 {digest_years:.1f}년 (적정)"
                elif digest_years <= 5.0:
                    base = 18
                    speed_tag = f"소화 {digest_years:.1f}년 (보통)"
                else:
                    base = 13
                    speed_tag = f"소화 {digest_years:.1f}년 (느림)"

                # 시총 대비 잔고 규모 보정
                if b2c >= 3.0:
                    base = min(30, base + 5)
                elif b2c >= 2.0:
                    base = min(30, base + 3)
                elif b2c >= 1.0:
                    base = min(30, base + 1)

                # PEG 보조
                if peg > 0 and peg < 1.0:
                    base = min(30, base + 2)
                    speed_tag += f", PEG {peg:.2f}"

                val_score = base
                val_detail = f"수주잔고 {bstr} (시총 {b2c:.1f}배, {speed_tag})"

        if not is_backlog_industry or not backlog_data:
            # 일반 기업: PEG / Forward PE 기반
            if peg > 0 and peg < 50:
                if peg < 0.5:
                    val_score = 30
                    val_detail = f"PEG {peg:.2f} 크게 저평가"
                elif peg < 1.0:
                    val_score = 26
                    val_detail = f"PEG {peg:.2f} 저평가"
                elif peg < 1.5:
                    val_score = 20
                    val_detail = f"PEG {peg:.2f} 적정"
                elif peg < 3.0:
                    val_score = 12
                    val_detail = f"PEG {peg:.2f} 다소 고평가"
                else:
                    val_score = 5
                    val_detail = f"PEG {peg:.2f} 고평가"
            elif fwd_pe > 0 and fwd_pe < 200:
                if fwd_pe < 10:
                    val_score = 28
                    val_detail = f"Fwd PE {fwd_pe:.1f} 저평가"
                elif fwd_pe < 20:
                    val_score = 22
                    val_detail = f"Fwd PE {fwd_pe:.1f} 합리적"
                elif fwd_pe < 35:
                    val_score = 15
                    val_detail = f"Fwd PE {fwd_pe:.1f} 적정"
                elif fwd_pe < 60:
                    val_score = 8
                    val_detail = f"Fwd PE {fwd_pe:.1f} 부담"
                else:
                    val_score = 3
                    val_detail = f"Fwd PE {fwd_pe:.1f} 고평가"

        # ─────────────────────────────────────────────────────────────
        # 팩터 2: 실적 모멘텀 (25점)
        # 26E(0y) + 27E(+1y) 컨센서스 종합. 2년 성장 지속성 중시.
        # ─────────────────────────────────────────────────────────────
        earn_score = 10  # 기본
        earn_detail = ""

        eps_g = fwd.get("eps_growth_0y")
        rev_g = fwd.get("rev_growth_0y")
        eps_g_1y = fwd.get("eps_growth_1y")
        rev_g_1y = fwd.get("rev_growth_1y")
        n_analysts = fwd.get("n_analysts", 0)

        # 26E 기본 점수 (최대 20점)
        base_earn = 8
        if eps_g is not None and rev_g is not None:
            if eps_g > 0.50 and rev_g > 0.20:
                base_earn = 20
                earn_detail = f"26E 매출 {rev_g*100:.0f}%+EPS {eps_g*100:.0f}% 폭발"
            elif eps_g > 0.25 and rev_g > 0.10:
                base_earn = 17
                earn_detail = f"26E 매출 {rev_g*100:.0f}%+EPS {eps_g*100:.0f}% 고성장"
            elif eps_g > 0.10 and rev_g > 0:
                base_earn = 13
                earn_detail = f"26E 매출 {rev_g*100:.0f}%+EPS {eps_g*100:.0f}% 양호"
            elif eps_g > 0:
                base_earn = 10
                earn_detail = f"26E EPS {eps_g*100:.0f}% 소폭"
            elif eps_g < -0.10:
                base_earn = 3
                earn_detail = f"26E EPS {eps_g*100:.0f}% 감익"
            else:
                base_earn = 7
                earn_detail = f"26E EPS {eps_g*100:.0f}% 보합"
        elif eps_g is not None:
            if eps_g > 0.30: base_earn = 16
            elif eps_g > 0.10: base_earn = 12
            elif eps_g < 0: base_earn = 4
            earn_detail = f"26E EPS {eps_g*100:.0f}%"

        # 27E 성장 지속성 가감 (최대 +5점 / -3점)
        continuation_bonus = 0
        if eps_g_1y is not None and rev_g_1y is not None:
            # 27E도 성장 지속 → 2년 연속 성장 = 강한 사이클
            if eps_g_1y > 0.20 and rev_g_1y > 0.10:
                continuation_bonus = 5
                earn_detail += f" -> 27E도 매출 {rev_g_1y*100:.0f}%+EPS {eps_g_1y*100:.0f}% 성장 지속"
            elif eps_g_1y > 0.10:
                continuation_bonus = 3
                earn_detail += f" -> 27E EPS {eps_g_1y*100:.0f}% 지속"
            elif eps_g_1y > 0:
                continuation_bonus = 1
                earn_detail += f" -> 27E 소폭 성장"
            elif eps_g_1y < -0.10:
                continuation_bonus = -3
                earn_detail += f" -> 27E EPS {eps_g_1y*100:.0f}% 꺾임 주의"
            elif eps_g_1y < 0:
                continuation_bonus = -1
                earn_detail += f" -> 27E 둔화"
        elif eps_g_1y is not None:
            if eps_g_1y > 0.15:
                continuation_bonus = 3
                earn_detail += f" -> 27E EPS {eps_g_1y*100:.0f}% 지속"
            elif eps_g_1y < -0.10:
                continuation_bonus = -2
                earn_detail += f" -> 27E 꺾임"

        earn_score = max(0, min(25, base_earn + continuation_bonus))

        # 애널리스트 수 가산
        if n_analysts >= 10: earn_score = min(25, earn_score + 2)
        elif n_analysts >= 5: earn_score = min(25, earn_score + 1)

        # ─────────────────────────────────────────────────────────────
        # 팩터 3: 테마 구조성 (20점)
        # ─────────────────────────────────────────────────────────────
        theme_score = 10  # 기본
        theme_detail = ", ".join(theme_info.get("themes", []))

        persistence = theme_info.get("persistence", 0)
        is_structural = theme_info.get("is_structural", False)
        duration_score = theme_info.get("duration_score", 0)
        strength_score = theme_info.get("strength_score", 0)
        driver_stability = theme_info.get("driver_stability", 0)

        if is_structural:
            has_3axis = duration_score > 0 and strength_score > 0 and driver_stability > 0
            if has_3axis:
                # 각 축을 0-1로 정규화 후 평균 → 0-14 변환
                d_norm = (duration_score - 1) / 4        # 1-5 → 0-1
                s_norm = (strength_score - 1) / 9        # 1-10 → 0-1
                ds_norm = (driver_stability - 1) / 4     # 1-5 → 0-1
                avg_norm = (d_norm + s_norm + ds_norm) / 3
                struct_component = round(avg_norm * 14)  # 0-14
            else:
                struct_component = 8  # 3축 데이터 없을 때 중간값
            p_bonus = 6 if persistence >= 60 else (3 if persistence >= 40 else 0)
            theme_score = max(10, min(20, struct_component + p_bonus))
        else:
            if persistence >= 60:
                theme_score = 10
            elif persistence >= 40:
                theme_score = 7
            else:
                theme_score = 4

        # ─────────────────────────────────────────────────────────────
        # 팩터 4: 진입 타이밍 (15점)
        # ─────────────────────────────────────────────────────────────
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        ma5 = close.rolling(5).mean()
        rsi = _safe(ta_lib.momentum.RSIIndicator(close, window=14).rsi().iloc[-1], 50)
        bb_mid = _safe(ma20.iloc[-1])
        bb_std = _safe(close.rolling(20).std().iloc[-1])
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_pct = (cur_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

        def _pct(n):
            raw = close.pct_change(n).iloc[-1]
            return round(float(raw) * 100, 1) if pd.notna(raw) else None

        ret_1w = _pct(5)
        ret_1m = _pct(20)
        ret_3m = _pct(60) if len(close) >= 60 else ret_1m
        ma20_val = _safe(ma20.iloc[-1])
        ma50_val = _safe(ma50.iloc[-1])
        ma5_val = _safe(ma5.iloc[-1])

        entry_score = 8  # 기본
        entry_reasons = []

        # 눌림목: 상승추세인데 단기 조정 중
        if ma20_val > ma50_val and cur_price < ma20_val and cur_price > ma50_val:
            entry_score += 5
            entry_reasons.append("눌림목 (20일선 아래 조정)")
        elif ma20_val > ma50_val and cur_price >= ma20_val:
            entry_score += 2
            entry_reasons.append("상승추세 유지")

        # RSI
        if 35 <= rsi <= 50:
            entry_score += 3
            entry_reasons.append(f"RSI {rsi:.0f} 과매도 근접")
        elif 50 < rsi <= 60:
            entry_score += 2
            entry_reasons.append(f"RSI {rsi:.0f} 적정")
        elif rsi > 70:
            entry_score -= 5
            entry_reasons.append(f"RSI {rsi:.0f} 과열")
        elif rsi > 65:
            entry_score -= 2
            entry_reasons.append(f"RSI {rsi:.0f} 다소 높음")

        # 볼린저
        if bb_pct <= 0.3:
            entry_score += 3
            entry_reasons.append("볼린저 하단 근접")
        elif bb_pct >= 0.9:
            entry_score -= 4
            entry_reasons.append("볼린저 상단 돌파")

        # 1주 급등 감점
        if ret_1w is not None and ret_1w > 15:
            entry_score -= 5
            entry_reasons.append(f"1주 +{ret_1w:.0f}% 급등")

        entry_score = max(0, min(15, entry_score))
        entry_detail = " / ".join(entry_reasons[:3])

        # ─────────────────────────────────────────────────────────────
        # 팩터 5: 수급 추세 (10점, 한국만)
        # ─────────────────────────────────────────────────────────────
        supply_score = 5  # 기본 (미국은 5점 고정)
        supply_detail = ""
        investor_flow = None

        if is_kr:
            code = ticker.split(".")[0]
            investor_flow = _fetch_kr_investor_flow(code, days=5)
            if investor_flow:
                f_net = investor_flow["foreign_net_5d"]
                i_net = investor_flow["inst_net_5d"]
                f_ratio = investor_flow["foreign_ratio"]

                if f_net > 0 and i_net > 0:
                    supply_score = 10
                    supply_detail = f"외국인+기관 동반 순매수"
                elif f_net > 0:
                    supply_score = 7
                    supply_detail = f"외국인 순매수 {f_net:+,}"
                elif i_net > 0:
                    supply_score = 7
                    supply_detail = f"기관 순매수 {i_net:+,}"
                elif f_net < 0 and i_net < 0:
                    supply_score = 1
                    supply_detail = f"외국인+기관 동반 순매도"
                else:
                    supply_score = 4

                if f_ratio > 0:
                    supply_detail += f" (외보유 {f_ratio:.1f}%)"

        # ─────────────────────────────────────────────────────────────
        # 총점
        # ─────────────────────────────────────────────────────────────
        total = val_score + earn_score + theme_score + entry_score + supply_score

        return {
            "ticker": ticker,
            "name": kr_name if kr_name else info.get("shortName", ticker),
            "sector": info.get("sector", ""),
            "price": round(cur_price, 2),
            "market_cap": market_cap,
            "themes": theme_info.get("themes", []),
            # 총점
            "expected_return_score": round(total, 1),
            # 팩터별 점수
            "valuation_score": val_score,
            "earnings_score": earn_score,
            "theme_score": theme_score,
            "entry_score": entry_score,
            "supply_score": supply_score,
            # 상세
            "val_detail": val_detail,
            "earn_detail": earn_detail,
            "theme_detail": theme_detail,
            "entry_detail": entry_detail,
            "supply_detail": supply_detail,
            # 원시 데이터
            "fwd_pe": round(fwd_pe, 1) if fwd_pe > 0 else None,
            "peg": round(peg, 2) if 0 < peg < 50 else None,
            "rsi": round(rsi, 1),
            "bb_pct": round(bb_pct, 2),
            "ret_1w": ret_1w,
            "ret_1m": ret_1m,
            "ret_3m": ret_3m,
            "n_analysts": fwd.get("n_analysts", 0),
            "investor_flow": investor_flow,
        }

    except Exception as e:
        return None


def _recalc_relative_valuation(results: List[Dict]) -> List[Dict]:
    """Peer 대비 상대 밸류에이션으로 val_score를 재계산.

    우선순위:
      1. 같은 테마 내 Fwd PE 중앙값 대비 (가장 세분화)
      2. 같은 섹터 내 Fwd PE 중앙값 대비
      3. 전체 유니버스 Fwd PE 중앙값 대비 (fallback)
    """
    import numpy as np
    from collections import defaultdict

    theme_pe = defaultdict(list)
    sector_pe = defaultdict(list)
    all_pe = []

    for r in results:
        pe = r.get("fwd_pe")
        if pe and 0 < pe < 200:
            themes = r.get("themes", [])
            if isinstance(themes, str):
                themes = [t.strip() for t in themes.split(",") if t.strip()]
            for t in themes:
                if t and t != "(유니버스 외)":
                    theme_pe[t].append(pe)
            sector = r.get("sector", "")
            if sector:
                sector_pe[sector].append(pe)
            all_pe.append(pe)

    theme_median = {t: float(np.median(v)) for t, v in theme_pe.items() if len(v) >= 3}
    sector_median = {s: float(np.median(v)) for s, v in sector_pe.items() if len(v) >= 3}
    universe_median = float(np.median(all_pe)) if len(all_pe) >= 5 else 20.0

    for r in results:
        pe = r.get("fwd_pe")
        peg = r.get("peg")

        if "수주잔고" in r.get("val_detail", ""):
            continue

        if not pe or pe <= 0 or pe >= 200:
            continue

        themes = r.get("themes", [])
        if isinstance(themes, str):
            themes = [t.strip() for t in themes.split(",") if t.strip()]

        peer_median = None
        peer_group = ""

        for t in themes:
            if t in theme_median:
                peer_median = theme_median[t]
                peer_group = t
                break

        if peer_median is None:
            sector = r.get("sector", "")
            if sector in sector_median:
                peer_median = sector_median[sector]
                peer_group = sector

        if peer_median is None:
            peer_median = universe_median
            peer_group = "전체"

        discount = (peer_median - pe) / peer_median if peer_median > 0 else 0

        if discount >= 0.40:
            new_val, tag = 30, "크게 저평가"
        elif discount >= 0.20:
            new_val, tag = 26, "저평가"
        elif discount >= 0.05:
            new_val, tag = 22, "소폭 저평가"
        elif discount >= -0.10:
            new_val, tag = 16, "적정"
        elif discount >= -0.30:
            new_val, tag = 10, "소폭 고평가"
        elif discount >= -0.60:
            new_val, tag = 5, "고평가"
        else:
            new_val, tag = 2, "크게 고평가"

        if peg and 0 < peg < 0.7:
            new_val = min(30, new_val + 3)
        elif peg and 0 < peg < 1.0:
            new_val = min(30, new_val + 1)
        elif peg and peg > 4.0:
            new_val = max(0, new_val - 2)

        # 상대 80% + 절대 20% 블렌딩
        old_val = r["valuation_score"]
        blended_val = max(0, min(30, round(new_val * 0.8 + old_val * 0.2)))

        diff = blended_val - old_val
        r["valuation_score"] = blended_val
        r["expected_return_score"] = round(r["expected_return_score"] + diff, 1)
        r["val_detail"] = (
            f"Fwd PE {pe:.1f} vs {peer_group} 중앙값 {peer_median:.1f} "
            f"({discount*100:+.0f}% {tag})"
        )
        if peg and 0 < peg < 50:
            r["val_detail"] += f" PEG {peg:.2f}"

    return results


# ── catchup/가중치 함수는 V2-1로 이전 (d218d4f architecture) ──────────────────
# 호출자가 1+2패스 결과 받은 후 screener.v2_1.scorer의
# calc_peer_catchup + apply_model_weights를 직접 호출. score_universe는 1+2패스만.


def score_universe(
    universe: List[Dict],
    theme_persistence_map: Dict = None,
    structural_map: Dict = None,
    min_score: float = 0.0,
    max_workers: int = 8,
    info_cache: Optional[Dict] = None,
) -> pd.DataFrame:
    """유니버스 1+2패스 스코어링 (factor 결과만 반환).

    3패스(peer 캐치업)/4패스(모델 가중치)는 호출자가 V2-1의 calc_peer_catchup +
    apply_model_weights로 적용. V2/V2-1 모두 동일 함수 사용 → single source of truth.

    theme_persistence_map: {"테마명": persistence_score}
    structural_map: {"테마명": {"is_structural": bool, ...}}
    info_cache: {ticker: info_dict} — score_stock 병렬 호출 간 .info 공유
    """
    if theme_persistence_map is None:
        theme_persistence_map = {}
    if structural_map is None:
        structural_map = {}

    # ── FMP 사전 조회 (FMP_API_KEY 있을 때만) ─────────────────────────────
    if os.environ.get("FMP_API_KEY"):
        us_syms = [s["ticker"] for s in universe if not s["ticker"].endswith((".KS", ".KQ"))]
        if us_syms:
            _prefetch_fmp_us(us_syms)

    # 종목별 테마 정보 구성
    def build_theme_info(stock):
        themes = stock.get("themes", [])
        max_persistence = max(
            (theme_persistence_map.get(t, 0) for t in themes), default=0
        )
        any_structural = any(
            structural_map.get(t, {}).get("is_structural", False) for t in themes
        )
        # 3축 점수: 소속 테마 중 구조적 테마의 최고값 사용
        best_duration, best_strength, best_driver = 0, 0, 0
        for t in themes:
            s = structural_map.get(t, {})
            if s.get("is_structural", False):
                best_duration = max(best_duration, s.get("duration_score", 0))
                best_strength = max(best_strength, s.get("strength_score", 0))
                best_driver = max(best_driver, s.get("driver_stability", 0))
        return {
            "themes": themes,
            "persistence": max_persistence,
            "is_structural": any_structural,
            "duration_score": best_duration,
            "strength_score": best_strength,
            "driver_stability": best_driver,
        }

    import time as _time

    tickers = [(s["ticker"], build_theme_info(s), s.get("name", "")) for s in universe]
    ticker_symbols = [t for t, _, _ in tickers]
    total = len(tickers)
    print(f"[v2 스코어링] {total}개 종목 분석 중...")

    # ── 가격 히스토리 캐시 로드 ───────────────────────────────────────────────
    price_cache: Dict[str, pd.DataFrame] = {}
    os.makedirs(_V2_DATA_DIR, exist_ok=True)
    if os.path.exists(_PRICE_CACHE_FILE):
        try:
            with open(_PRICE_CACHE_FILE, "rb") as f:
                price_cache = pickle.load(f)
            print(f"[v2 가격캐시] 로드 완료 ({len(price_cache)}개 종목)")
        except Exception:
            price_cache = {}

    # 캐시에 없는 신규 종목 → 1년치 다운로드
    missing = [t for t in ticker_symbols if t not in price_cache]
    # 캐시에 있지만 오늘 데이터가 없는 종목 → 증분 업데이트
    today_str = datetime.now().strftime("%Y-%m-%d")
    stale = [
        t for t in ticker_symbols
        if t in price_cache and not price_cache[t].empty
        and str(price_cache[t].index[-1].date()) < today_str
    ]

    def _normalize_df(df_sym: pd.DataFrame, sym: str) -> pd.DataFrame:
        """yfinance MultiIndex 컬럼을 단순 문자열 컬럼으로 정규화."""
        if df_sym.empty:
            return df_sym
        if isinstance(df_sym.columns, pd.MultiIndex):
            # 단일 티커 다운로드: ('Close','NVDA'),... → 'Close',...
            # get_level_values(0)이 Price 레벨, (1)이 Ticker 레벨
            names = df_sym.columns.names
            if "Ticker" in names:
                price_level = names.index("Ticker") ^ 1  # 0이면 1, 1이면 0
                df_sym = df_sym.xs(sym, axis=1, level="Ticker", drop_level=True)
            else:
                df_sym.columns = df_sym.columns.get_level_values(0)
        # 필요 컬럼만 유지
        keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df_sym.columns]
        return df_sym[keep]

    def _download_chunk(syms: list, period_or_start: str, is_start: bool = False):
        """syms 묶음을 다운로드해서 price_cache에 병합."""
        chunk_size = 100
        for i in range(0, len(syms), chunk_size):
            chunk = syms[i:i + chunk_size]
            try:
                kwargs = dict(auto_adjust=True, progress=False, group_by="ticker", threads=True)
                if is_start:
                    kwargs["start"] = period_or_start
                else:
                    kwargs["period"] = period_or_start
                raw = yf.download(chunk, **kwargs)
                for sym in chunk:
                    try:
                        if len(chunk) == 1:
                            df_sym = _normalize_df(raw, sym)
                        else:
                            lvl0 = raw.columns.get_level_values(0)
                            df_sym = raw[sym] if sym in lvl0 else pd.DataFrame()
                        if df_sym.empty:
                            continue
                        # Close NaN 행 제거 (미장 미개장 시간대 임시 행)
                        df_sym = df_sym[df_sym["Close"].notna()]
                        if df_sym.empty:
                            continue
                        if is_start and sym in price_cache and not price_cache[sym].empty:
                            # 기존 캐시에 새 행만 추가 (중복 제거)
                            existing = price_cache[sym]
                            # 기존 캐시도 정규화 (컬럼 불일치 방지)
                            if isinstance(existing.columns, pd.MultiIndex):
                                existing = _normalize_df(existing, sym)
                            combined = pd.concat([existing, df_sym])
                            price_cache[sym] = combined[~combined.index.duplicated(keep="last")].sort_index()
                            # 1년치만 유지
                            cutoff = price_cache[sym].index[-1] - pd.DateOffset(years=1)
                            price_cache[sym] = price_cache[sym][price_cache[sym].index >= cutoff]
                        else:
                            if len(df_sym) >= 60:
                                price_cache[sym] = df_sym
                    except Exception:
                        pass
            except Exception as e:
                print(f"  [가격 다운로드 오류] {e}")
            if i + chunk_size < len(syms):
                _time.sleep(2)

    if missing:
        print(f"[v2 가격캐시] 신규 {len(missing)}개 종목 다운로드 중...")
        _download_chunk(missing, "1y", is_start=False)

    if stale:
        # 마지막 날짜 다음날부터 오늘까지만 요청
        oldest_last = min(str(price_cache[t].index[-1].date()) for t in stale if t in price_cache and not price_cache[t].empty)
        start_date = (pd.Timestamp(oldest_last) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"[v2 가격캐시] {len(stale)}개 종목 증분 업데이트 ({start_date} 이후)...")
        _download_chunk(stale, start_date, is_start=True)

    if missing or stale:
        try:
            with open(_PRICE_CACHE_FILE, "wb") as f:
                pickle.dump(price_cache, f)
            print(f"[v2 가격캐시] 저장 완료 ({len(price_cache)}개 종목)")
        except Exception as e:
            print(f"  [가격캐시 저장 오류] {e}")

    # ── 1패스: 개별 종목 스코어링 (절대 밸류에이션) ─────────────────────────
    if info_cache is None:
        info_cache = {}
    all_results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(score_stock, t, info, name, price_cache.get(t), info_cache): t
            for t, info, name in tickers
        }
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 100 == 0:
                print(f"  진행: {done}/{total}")
            res = future.result()
            if res:
                all_results.append(res)

    if not all_results:
        return pd.DataFrame()

    # ── 2패스: Peer 대비 상대 밸류에이션 재계산 ─────────────────────────────
    print(f"[v2 상대밸류] {len(all_results)}개 종목 peer 비교 중...")
    all_results = _recalc_relative_valuation(all_results)

    # 3패스(catchup) + 4패스(가중치) + min_score 필터 + 정렬은 호출자(V2 pipeline /
    # V2-1 score_universe_v2_1_factors)가 V2-1의 calc_peer_catchup +
    # apply_model_weights로 처리.

    df = pd.DataFrame(all_results).reset_index(drop=True)
    print(f"[v2 스코어링] 완료: {len(df)}개 종목 (factor only)")
    return df


if __name__ == "__main__":
    # 샘플 테스트
    test_tickers = [
        {"ticker": "009540.KS", "themes": ["조선"]},
        {"ticker": "042660.KS", "themes": ["조선"]},
        {"ticker": "000660.KS", "themes": ["HBM", "반도체대표주"]},
        {"ticker": "006400.KS", "themes": ["2차전지"]},
        {"ticker": "MRVL", "themes": ["AI Semiconductors"]},
        {"ticker": "CRWD", "themes": ["Cloud & Software"]},
    ]

    print("=" * 70)
    print("  v2 스코어링 테스트")
    print("=" * 70)

    for s in test_tickers:
        r = score_stock(s["ticker"], {"themes": s["themes"], "persistence": 65, "is_structural": True})
        if r:
            print(f"\n{r['ticker']} ({r['name']})")
            print(f"  기대수익률: {r['expected_return_score']:.0f}점")
            print(f"  밸류={r['valuation_score']}  실적={r['earnings_score']}  "
                  f"테마={r['theme_score']}  진입={r['entry_score']}  수급={r['supply_score']}")
            print(f"  {r['val_detail']} / {r['earn_detail']}")
            print(f"  {r['entry_detail']}")
            if r.get("supply_detail"):
                print(f"  {r['supply_detail']}")
