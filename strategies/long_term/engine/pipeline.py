"""
src/v2/pipeline.py
중장기 포지션 전략 파이프라인.
구조적 테마 유니버스 → 5팩터 기대수익률 스코어링 → 결과 반환.
"""

import os
import json
import glob
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

_V2_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

CORE_STRUCTURAL_THEMES = [
    "광통신", "HBM(고대역메모리)", "전력반도체", "반도체장비",
    "PCB(FPCB 등)", "SOCAMM", "온디바이스 AI",
    "조선", "방위산업", "원자력발전", "초고압 송전 변압기",
    "2차전지(배터리)", "전기차", "우주항공",
]


def _save_daily(data: dict):
    """파이프라인 결과를 data/v2/YYYY-MM-DD.json 으로 저장. _ prefix 키는 메모리 전용."""
    os.makedirs(_V2_DATA_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(_V2_DATA_DIR, f"{date_str}.json")
    persisted = {k: v for k, v in data.items() if not k.startswith("_")}
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(persisted, f, ensure_ascii=False, indent=2)
    print(f"[v2 일일 리포트 저장] {filepath}")


def load_daily(date_str: str) -> dict:
    """특정 날짜의 v2 저장 리포트 로드."""
    filepath = os.path.join(_V2_DATA_DIR, f"{date_str}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def list_available_dates() -> List[str]:
    """저장된 v2 일일 리포트 날짜 목록 (최신순). YYYY-MM-DD 형식 파일만 포함."""
    import re
    os.makedirs(_V2_DATA_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(_V2_DATA_DIR, "*.json")), reverse=True)
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    return [
        os.path.basename(f).replace(".json", "")
        for f in files
        if date_pattern.match(os.path.basename(f).replace(".json", ""))
    ]


_UNIVERSE_CACHE_FILE = os.path.join(_V2_DATA_DIR, "universe_cache.json")


def _load_universe_cache() -> Optional[tuple]:
    """당일 유니버스 캐시 로드. 오늘 날짜 캐시가 있으면 (kr, us) 반환, 없으면 None."""
    if not os.path.exists(_UNIVERSE_CACHE_FILE):
        return None
    try:
        with open(_UNIVERSE_CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        if cache.get("date") == datetime.now().strftime("%Y-%m-%d"):
            kr = cache.get("kr", [])
            us = cache.get("us", [])
            print(f"[v2 유니버스 캐시] 로드 완료 (한국 {len(kr)}, 미국 {len(us)})")
            return kr, us
    except Exception:
        pass
    return None


def _save_universe_cache(kr: list, us: list):
    """유니버스를 당일 캐시로 저장."""
    os.makedirs(_V2_DATA_DIR, exist_ok=True)
    cache = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "kr": kr,
        "us": us,
    }
    with open(_UNIVERSE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"[v2 유니버스 캐시] 저장 완료 (한국 {len(kr)}, 미국 {len(us)})")


def _row_to_dict(row) -> dict:
    flow = row.get("investor_flow") or {}
    themes = row.get("themes", [])
    themes_str = ", ".join(themes) if isinstance(themes, list) else str(themes)
    return {
        "ticker": row["ticker"],
        "name": row.get("name", ""),
        "price": row.get("price", 0),
        "sector": row.get("sector", ""),
        "themes": themes_str,
        "expected_return_score": row.get("expected_return_score", 0),
        "valuation_score": row.get("valuation_score", 0),
        "earnings_score": row.get("earnings_score", 0),
        "theme_score": row.get("theme_score", 0),
        "entry_score": row.get("entry_score", 0),
        "supply_score": row.get("supply_score", 0),
        "val_detail": row.get("val_detail", ""),
        "earn_detail": row.get("earn_detail", ""),
        "entry_detail": row.get("entry_detail", ""),
        "supply_detail": row.get("supply_detail", ""),
        "fwd_pe": row.get("fwd_pe"),
        "peg": row.get("peg"),
        "rsi": row.get("rsi", 0),
        "ret_1w": row.get("ret_1w", 0),
        "ret_1m": row.get("ret_1m", 0),
        "n_analysts": row.get("n_analysts", 0),
        "foreign_net": flow.get("foreign_net_5d", "") if flow else "",
        "inst_net": flow.get("inst_net_5d", "") if flow else "",
        "foreign_ratio": flow.get("foreign_ratio", "") if flow else "",
    }


def run(min_score: float = 45.0, max_workers: int = 8) -> Optional[Dict]:
    """
    v2 파이프라인 실행.
    반환값: {
        updated_at, version, recommendations, kr_stocks, us_stocks,
        persistence, rotations, structural_analysis
    }
    실패 시 None 반환.
    """
    from universe import build_kr_universe, build_us_universe
    from scorer import score_universe
    from theme_tracker import (
        collect_all_themes, save_theme_history, load_theme_history,
        calc_theme_persistence, detect_rotation, analyze_category_flow,
    )
    from theme_analyst import analyze_all_themes

    try:
        print(f"\n[v2] 파이프라인 실행 중... ({datetime.now():%H:%M})")

        # 1. 테마 히스토리 수집
        print("[v2] 1/4 테마 히스토리 수집 중...")
        all_theme_data = collect_all_themes()
        save_theme_history(all_theme_data)
        history = load_theme_history(days=14)
        persistence = calc_theme_persistence(history)
        rotations = detect_rotation(persistence)
        category_flow = analyze_category_flow(history)
        persistence_by_name = {t["name"]: t["persistence_score"] for t in persistence}
        # 괄호 앞 단어 별칭 추가 — "HBM(고대역메모리)" → "HBM" 으로도 조회 가능
        for name, score in list(persistence_by_name.items()):
            short = name.split("(")[0].replace(" ", "")
            if short not in persistence_by_name:
                persistence_by_name[short] = score

        # 2. 구조적 테마 분석 (Tavily+Gemini, 캐시 사용)
        print("[v2] 2/4 구조적 테마 분석 중...")
        structural = analyze_all_themes(CORE_STRUCTURAL_THEMES)
        structural_map = {s["theme"]: s for s in structural}
        # 괄호 앞 단어 별칭 추가 — "HBM(고대역메모리)" → "HBM" 으로도 조회 가능
        for theme_key in list(structural_map.keys()):
            short = theme_key.split("(")[0].replace(" ", "")
            if short not in structural_map:
                structural_map[short] = structural_map[theme_key]

        # 3. 유니버스 구성 (당일 캐시 우선)
        print("[v2] 3/4 종목 유니버스 구성 중...")
        cached = _load_universe_cache()
        if cached:
            kr_universe, us_universe = cached
        else:
            kr_universe = build_kr_universe()
            us_universe = build_us_universe()
            _save_universe_cache(kr_universe, us_universe)
        for stock in kr_universe + us_universe:
            stock["persistence"] = max(
                (persistence_by_name.get(t, 0) for t in stock["themes"]), default=0
            )
            stock["is_structural"] = any(
                structural_map.get(t, {}).get("is_structural", False) for t in stock["themes"]
            )

        # 4. 스코어링 — V2는 1+2패스(factor)만 받고, 3+4패스는 V2-1 함수로 위임
        # (d218d4f architecture: V2/V2-1 책임 분리 + catchup 중복 제거)
        universe = kr_universe + us_universe
        print("[v2] 4/4 스코어링...")
        factor_df = score_universe(
            universe,
            theme_persistence_map=persistence_by_name,
            structural_map=structural_map,
            min_score=0,
            max_workers=max_workers,
        )

        # factor_df를 그대로 사용 (이미 expected_return_score 계산됨)
        if not factor_df.empty:
            scored_df = factor_df.sort_values(
                "expected_return_score", ascending=False
            ).reset_index(drop=True)
        else:
            scored_df = factor_df

        # V2 base 필터 (기존 동작 유지)
        if not scored_df.empty:
            base_df = scored_df[scored_df["expected_return_score"] >= min_score]
        else:
            base_df = scored_df

        kr_stocks, us_stocks = [], []
        all_kr_stocks, all_us_stocks = [], []
        if not base_df.empty:
            for _, row in base_df.iterrows():
                d = _row_to_dict(row)
                if row["ticker"].endswith((".KS", ".KQ")):
                    kr_stocks.append(d)
                else:
                    us_stocks.append(d)
        # min_score 필터 전 전체 스코어링 결과 (대시보드 테마 상세용)
        if not scored_df.empty:
            for _, row in scored_df.iterrows():
                d = _row_to_dict(row)
                if row["ticker"].endswith((".KS", ".KQ")):
                    all_kr_stocks.append(d)
                else:
                    all_us_stocks.append(d)

        main = {
            "recommendations": kr_stocks[:15] + us_stocks[:15],
            "kr_stocks": kr_stocks[:30],
            "us_stocks": us_stocks[:30],
        }
        # web_app/notifier 호환을 위해 base 1개 유지
        model_results = {"base": main}

        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        result = {
            "updated_at": updated_at,
            "version": "v2",
            "recommendations": main["recommendations"],
            "kr_stocks": main["kr_stocks"],
            "us_stocks": main["us_stocks"],
            # 대시보드 /api/v2/theme_detail 모달용 — min_score 미만 종목 포함 전체
            "all_kr_stocks": all_kr_stocks,
            "all_us_stocks": all_us_stocks,
            "models": model_results,
            "persistence": persistence[:30],
            "rotations": rotations,
            "category_flow": category_flow,
            "structural_analysis": structural,
        }

        _save_daily(result)
        print(f"[v2] 완료! 추천 {len(main['recommendations'])}개 (KR {len(kr_stocks)}, US {len(us_stocks)})")
        return result

    except Exception as e:
        import traceback
        print(f"[v2 파이프라인 오류] {e}")
        traceback.print_exc()
        return None


def refresh_us_only(min_score: float = 45.0, max_workers: int = 8) -> Optional[Dict]:
    """V2 US 부분만 재산출 (06:30 morning refresh용).

    어제 17:00에 산출된 KR 부분은 그대로 두고 US만 fresh yfinance로 다시 점수.
    캐시(themes / structural / universe)를 재활용 — 풀 파이프라인 대비 매우 빠름.

    반환 dict (저장 X, 호출자가 텔레그램/페이퍼 트래커에 사용):
        {us_stocks: [...TOP 30], all_us_stocks: [...전체 점수], updated_at}
    실패 시 None.
    """
    from universe import build_us_universe
    from scorer import score_universe
    from theme_tracker import load_theme_history, calc_theme_persistence
    from theme_analyst import analyze_all_themes

    try:
        print(f"\n[v2/us refresh] 06:30 미국 재산출 중... ({datetime.now():%H:%M})")

        # 1. 테마 지속성 (KR-only 데이터지만 캐시 재사용 — US 점수에 직접 영향 X)
        history = load_theme_history(days=14)
        persistence = calc_theme_persistence(history)
        persistence_by_name = {t["name"]: t["persistence_score"] for t in persistence}
        for name, score in list(persistence_by_name.items()):
            short = name.split("(")[0].replace(" ", "")
            if short not in persistence_by_name:
                persistence_by_name[short] = score

        # 2. 구조적 분석 (캐시 재사용 — 새 LLM 호출 거의 없음)
        structural = analyze_all_themes(CORE_STRUCTURAL_THEMES)
        structural_map = {s["theme"]: s for s in structural}
        for theme_key in list(structural_map.keys()):
            short = theme_key.split("(")[0].replace(" ", "")
            if short not in structural_map:
                structural_map[short] = structural_map[theme_key]

        # 3. US universe만 (캐시 우선)
        cached = _load_universe_cache()
        if cached:
            _, us_universe = cached
        else:
            us_universe = build_us_universe()
        for stock in us_universe:
            stock["persistence"] = max(
                (persistence_by_name.get(t, 0) for t in stock["themes"]), default=0
            )
            stock["is_structural"] = any(
                structural_map.get(t, {}).get("is_structural", False) for t in stock["themes"]
            )

        # 4. 스코어링 (US만)
        print(f"[v2/us refresh] 스코어링 중 ({len(us_universe)}개 종목)...")
        factor_df = score_universe(
            us_universe,
            theme_persistence_map=persistence_by_name,
            structural_map=structural_map,
            min_score=0,
            max_workers=max_workers,
        )

        if not factor_df.empty:
            scored_df = factor_df.sort_values(
                "expected_return_score", ascending=False
            ).reset_index(drop=True)
        else:
            scored_df = factor_df

        if not scored_df.empty:
            base_df = scored_df[scored_df["expected_return_score"] >= min_score]
        else:
            base_df = scored_df

        us_stocks, all_us_stocks = [], []
        if not base_df.empty:
            for _, row in base_df.iterrows():
                d = _row_to_dict(row)
                if not row["ticker"].endswith((".KS", ".KQ")):
                    us_stocks.append(d)
        if not scored_df.empty:
            for _, row in scored_df.iterrows():
                d = _row_to_dict(row)
                if not row["ticker"].endswith((".KS", ".KQ")):
                    all_us_stocks.append(d)

        print(f"[v2/us refresh] 완료 — US TOP 30 {len(us_stocks[:30])}개")
        return {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "us_stocks": us_stocks[:30],
            "all_us_stocks": all_us_stocks,
        }

    except Exception as e:
        import traceback
        print(f"[v2/us refresh 오류] {e}")
        traceback.print_exc()
        return None


def refresh_kr_only(min_score: float = 45.0, max_workers: int = 8) -> Optional[Dict]:
    """V2 KR 부분만 재산출 (15:00 사전 예고용).

    refresh_us_only의 KR 버전. 캐시된 themes/structural/universe 재활용 +
    score_universe(kr_universe)만 다시 돌림. 풀 17:00 파이프라인 대비 매우 빠름
    (테마 수집/구조적 분석 LLM 호출 스킵).

    반환 dict:
        {kr_stocks: [...TOP 30], all_kr_stocks: [...전체 점수], updated_at}
    실패 시 None.
    """
    from universe import build_kr_universe
    from scorer import score_universe
    from theme_tracker import load_theme_history, calc_theme_persistence
    from theme_analyst import analyze_all_themes

    try:
        print(f"\n[v2/kr refresh] 15:00 한국 재산출 중... ({datetime.now():%H:%M})")

        # 1. 테마 지속성 (캐시 재사용)
        history = load_theme_history(days=14)
        persistence = calc_theme_persistence(history)
        persistence_by_name = {t["name"]: t["persistence_score"] for t in persistence}
        for name, score in list(persistence_by_name.items()):
            short = name.split("(")[0].replace(" ", "")
            if short not in persistence_by_name:
                persistence_by_name[short] = score

        # 2. 구조적 분석 (캐시 재사용)
        structural = analyze_all_themes(CORE_STRUCTURAL_THEMES)
        structural_map = {s["theme"]: s for s in structural}
        for theme_key in list(structural_map.keys()):
            short = theme_key.split("(")[0].replace(" ", "")
            if short not in structural_map:
                structural_map[short] = structural_map[theme_key]

        # 3. KR universe만 (캐시 우선)
        cached = _load_universe_cache()
        if cached:
            kr_universe, _ = cached
        else:
            kr_universe = build_kr_universe()
        for stock in kr_universe:
            stock["persistence"] = max(
                (persistence_by_name.get(t, 0) for t in stock["themes"]), default=0
            )
            stock["is_structural"] = any(
                structural_map.get(t, {}).get("is_structural", False) for t in stock["themes"]
            )

        # 4. 스코어링 (KR만)
        print(f"[v2/kr refresh] 스코어링 중 ({len(kr_universe)}개 종목)...")
        factor_df = score_universe(
            kr_universe,
            theme_persistence_map=persistence_by_name,
            structural_map=structural_map,
            min_score=0,
            max_workers=max_workers,
        )

        if not factor_df.empty:
            scored_df = factor_df.sort_values(
                "expected_return_score", ascending=False
            ).reset_index(drop=True)
        else:
            scored_df = factor_df

        if not scored_df.empty:
            base_df = scored_df[scored_df["expected_return_score"] >= min_score]
        else:
            base_df = scored_df

        kr_stocks, all_kr_stocks = [], []
        if not base_df.empty:
            for _, row in base_df.iterrows():
                d = _row_to_dict(row)
                if row["ticker"].endswith((".KS", ".KQ")):
                    kr_stocks.append(d)
        if not scored_df.empty:
            for _, row in scored_df.iterrows():
                d = _row_to_dict(row)
                if row["ticker"].endswith((".KS", ".KQ")):
                    all_kr_stocks.append(d)

        print(f"[v2/kr refresh] 완료 — KR TOP 30 {len(kr_stocks[:30])}개")
        return {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "kr_stocks": kr_stocks[:30],
            "all_kr_stocks": all_kr_stocks,
        }

    except Exception as e:
        import traceback
        print(f"[v2/kr refresh 오류] {e}")
        traceback.print_exc()
        return None
