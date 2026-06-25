"""
theme_analyst.py
Tavily 웹검색으로 최신 자료를 수집한 뒤, Gemini LLM에게 넘겨
테마가 글로벌 투자사이클에서 구조적 수혜인지 분석/판단한다.

2단계:
  1. Tavily → 테마별 최신 검색 결과 수집
  2. Gemini → 검색 결과를 기반으로 구조적 수혜 여부 판단 + 근거 작성
"""

import os
import json
import time
import requests
from datetime import datetime
from typing import Dict, List, Optional

_V2_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "v2")
ANALYSIS_FILE = os.path.join(_V2_DATA_DIR, "theme_analysis.json")

# 테마 → 영문 검색 키워드 매핑
THEME_SEARCH_MAP = {
    # 한국 핵심 테마
    "광통신": "AI optical transceiver 800G 1.6T Lumentum Coherent Ciena AAOI market demand 2026",
    "HBM(고대역메모리)": "HBM high bandwidth memory SK hynix Micron demand supply AI GPU 2026",
    "시스템반도체": "system semiconductor foundry AI chip advanced packaging 2026",
    "전력반도체": "power semiconductor SiC GaN AI data center power demand ON Semi Wolfspeed 2026",
    "반도체장비": "semiconductor equipment ASML AMAT LRCX capex spending outlook 2026",
    "PCB(FPCB 등)": "PCB FC-BGA AI server substrate demand Korea 2026",
    "SOCAMM": "SOCAMM CAMM LPDDR5X memory module AI server 2026",
    "온디바이스 AI": "on-device AI edge NPU smartphone PC semiconductor 2026",
    "조선": "Korea shipbuilding LNG carrier order backlog supercycle defense 2026",
    "방위산업": "defense export global arms spending NATO LMT RTX NOC 2026",
    "우주항공": "space industry SpaceX Rocket Lab satellite launch commercial 2026",
    "원자력발전": "nuclear power SMR small modular reactor data center electricity 2026",
    "초고압 송전 변압기": "power transformer grid infrastructure shortage AI data center GE Vernova 2026",
    "2차전지(배터리)": "EV battery LFP solid state CATL Samsung SDI demand 2026",
    "전기차": "EV sales global recovery China Europe subsidy Tesla Rivian 2026",
    # 미국 추가 테마
    "CPU/프로세서": "CPU processor AMD Intel QCOM ARM AI edge inference computing demand 2026",
    "수소연료전지": "hydrogen fuel cell market Plug Power Bloom Energy FCEL growth outlook 2026",
    "AI 인프라 (데이터센터)": "AI data center hyperscaler capex construction power demand REIT 2026",
    "AI 인프라 (네트워킹)": "AI networking Cisco Arista switch bandwidth demand data center 2026",
    "클린에너지/태양광": "solar energy Enphase FSLR US IRA incentive demand installation 2026",
    "사이버보안": "cybersecurity AI-driven threats CRWD PANW market growth enterprise 2026",
    "로봇/자동화": "robotics automation AI humanoid robot industrial Intuitive Surgical Rockwell Korea 2026",
    "AI 반도체 (설계)": "AI chip design NVDA AMD AVGO Broadcom fabless GPU inference training revenue 2026",
    "방위기술/드론": "defense technology drone UAV AeroVironment KTOS Palantir PLTR defense AI contract 2026",
    "양자컴퓨팅": "quantum computing IonQ Rigetti D-Wave IBM Google Willow commercial milestone revenue 2026",
    "크리티컬 메탈/구리": "critical minerals copper FCX Freeport MP Materials rare earth EV AI data center demand 2026",
    "LNG/에너지인프라": "LNG liquefied natural gas Cheniere US export Europe energy security infrastructure demand 2026",
    "반도체 EDA/설계툴": "semiconductor EDA design tools Synopsys Cadence AI chip custom ASIC design growth 2026",
}

GEMINI_SYSTEM_PROMPT = """당신은 글로벌 매크로 전략 애널리스트입니다.
주어진 웹 검색 자료를 기반으로, 특정 투자 테마가 현재 글로벌 투자사이클에서
"구조적 수혜(structural beneficiary)"인지 판단합니다.

구조적 수혜란:
- 단기 모멘텀이 아닌, 최소 1-3년 이상 지속되는 Capex/수요 사이클의 수혜
- 글로벌 하이퍼스케일러 AI 투자, 방위비 증가, 에너지 전환 등 메가 트렌드에 연동
- 수주잔고, 공급 부족, 설비투자 확대 등 객관적 데이터로 뒷받침 가능

반드시 아래 JSON 형식으로만 응답하세요:
{
  "is_structural": true/false,
  "confidence": "높음" | "보통" | "낮음",
  "verdict": "구조적 수혜 판단을 1줄로 요약",
  "bull_case": "구조적이라고 보는 근거 2-3줄",
  "bear_case": "구조적이 아닐 수 있는 리스크 1-2줄",
  "investment_horizon": "수혜 지속 예상 기간 (예: 2026-2028)",
  "key_drivers": ["드라이버1", "드라이버2", "드라이버3"],
  "key_data": "핵심 숫자/데이터 1-2개 (예: 시장 규모, 성장률, 수주잔고)",
  "duration_score": "1~5 정수. 1=1년 미만, 2=1-2년, 3=2-4년, 4=4-7년, 5=7년 이상 지속 예상",
  "strength_score": "1~10 정수. 관련 기업 매출/영업이익에 기여하는 강도. 1=미미한 수혜, 5=핵심 성장동력, 10=기업 존재 자체가 이 테마에 연동",
  "driver_stability": "1~5 정수. 드라이버 안정성. 1=투기성 단기수요, 2=정책 의존, 3=글로벌 수요 주도, 4=수요+기술 복합, 5=정책+기술+수요 삼박자 구조적 확정"
}"""


def _get_tavily_client():
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None
    try:
        from tavily import TavilyClient
        return TavilyClient(api_key=api_key)
    except ImportError:
        return None


def _get_gemini_api_key():
    return os.environ.get("GEMINI_API_KEY")


def _get_openai_api_key():
    return os.environ.get("OPENAI_API_KEY")


def _openai_judge(theme_name: str, search_text: str) -> Dict:
    """OpenAI Chat Completions로 구조적 수혜 판단 (Gemini fallback).
    openai SDK 사용. 키 없으면 None.
    """
    api_key = _get_openai_api_key()
    if not api_key:
        return None
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": GEMINI_SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"투자 테마: {theme_name}\n\n"
                    f"아래는 이 테마에 대한 최신 웹 검색 자료입니다. "
                    f"이 자료를 기반으로 이 테마가 글로벌 투자사이클에서 "
                    f"구조적 수혜인지 판단해주세요.\n\n"
                    f"=== 검색 자료 ===\n{search_text[:3000]}"
                )},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1024,
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return json.loads(raw)
    except ImportError:
        print("  [OpenAI] openai 패키지 없음 (pip install openai)")
        return None
    except Exception as e:
        print(f"  [OpenAI 판단 실패] {theme_name}: {type(e).__name__}: {e}")
        return None


def _tavily_search(theme_name: str, client) -> str:
    """Tavily로 테마 관련 최신 자료를 검색해 텍스트로 반환."""
    query = THEME_SEARCH_MAP.get(theme_name,
        f"{theme_name} investment cycle structural growth outlook 2026")

    try:
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=5,
            include_answer=True,
        )

        parts = []
        answer = response.get("answer", "")
        if answer:
            parts.append(f"[요약] {answer}")

        for r in response.get("results", [])[:5]:
            title = r.get("title", "")
            content = r.get("content", "")[:300]
            url = r.get("url", "")
            parts.append(f"[{title}] {content} (출처: {url})")

        sources = [{"title": r.get("title", ""), "url": r.get("url", "")}
                   for r in response.get("results", [])[:5]]

        return "\n\n".join(parts), sources

    except Exception as e:
        print(f"  [Tavily 검색 실패] {theme_name}: {e}")
        return "", []


def _gemini_judge(theme_name: str, search_text: str) -> Dict:
    """Gemini에 검색 결과를 전달해 구조적 수혜 여부를 판단."""
    api_key = _get_gemini_api_key()
    if not api_key:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={api_key}"

    payload = {
        "system_instruction": {
            "parts": [{"text": GEMINI_SYSTEM_PROMPT}]
        },
        "contents": [{
            "parts": [{
                "text": (
                    f"투자 테마: {theme_name}\n\n"
                    f"아래는 이 테마에 대한 최신 웹 검색 자료입니다. "
                    f"이 자료를 기반으로 이 테마가 글로벌 투자사이클에서 "
                    f"구조적 수혜인지 판단해주세요.\n\n"
                    f"=== 검색 자료 ===\n{search_text[:3000]}"
                )
            }]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        },
    }

    max_retries = 4
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"  [Rate Limit] {wait}초 대기... ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            response.raise_for_status()

            data = response.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            return json.loads(raw)

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                print(f"  [Gemini 판단 실패] {theme_name}: {e}")
                return None

    return None


def analyze_theme_structural(theme_name: str, tavily_client=None) -> Dict:
    """단일 테마: Tavily 검색 → Gemini 판단."""

    # Step 1: Tavily 검색
    search_text = ""
    sources = []
    if tavily_client:
        search_text, sources = _tavily_search(theme_name, tavily_client)

    # Step 2: LLM 판단 (Gemini 우선, 실패 시 OpenAI fallback)
    judgment = None
    method = ""
    if search_text and _get_gemini_api_key():
        judgment = _gemini_judge(theme_name, search_text)
        if judgment:
            method = "tavily+gemini"
    if judgment is None and search_text and _get_openai_api_key():
        print(f"  [{theme_name}] Gemini 실패 → OpenAI fallback 시도")
        judgment = _openai_judge(theme_name, search_text)
        if judgment:
            method = "tavily+openai"

    # Step 3: 결과 조립
    if judgment:
        return {
            "theme": theme_name,
            "is_structural": judgment.get("is_structural", False),
            "confidence": judgment.get("confidence", "낮음"),
            "verdict": judgment.get("verdict", ""),
            "bull_case": judgment.get("bull_case", ""),
            "bear_case": judgment.get("bear_case", ""),
            "investment_horizon": judgment.get("investment_horizon", ""),
            "key_drivers": judgment.get("key_drivers", []),
            "key_data": judgment.get("key_data", ""),
            "duration_score": int(judgment.get("duration_score", 0) or 0),
            "strength_score": int(judgment.get("strength_score", 0) or 0),
            "driver_stability": int(judgment.get("driver_stability", 0) or 0),
            "sources": sources,
            "analyzed_at": datetime.now().isoformat(),
            "method": method,
        }

    # Fallback: Tavily만 있고 Gemini 실패 시 — 답변 품질로 confidence 판단
    if search_text:
        text_lower = search_text.lower()
        structural_kw = ["growth", "demand", "capex", "backlog", "billion",
                         "surge", "record", "structural", "expansion", "projected"]
        risk_kw = ["decline", "overcapacity", "slowdown", "weak", "cut"]
        pos = sum(1 for k in structural_kw if k in text_lower)
        neg = sum(1 for k in risk_kw if k in text_lower)

        if pos >= 5 and neg <= 1:
            tv_confidence = "높음"
            tv_structural = True
        elif pos >= 3:
            tv_confidence = "보통"
            tv_structural = True
        elif neg >= 3:
            tv_confidence = "보통"
            tv_structural = False
        else:
            tv_confidence = "낮음"
            tv_structural = True

        return {
            "theme": theme_name,
            "is_structural": tv_structural,
            "confidence": tv_confidence,
            "verdict": search_text[:200],
            "bull_case": "",
            "bear_case": "",
            "investment_horizon": "",
            "key_drivers": [],
            "key_data": "",
            "duration_score": 0,
            "strength_score": 0,
            "driver_stability": 0,
            "sources": sources,
            "analyzed_at": datetime.now().isoformat(),
            "method": "tavily_only",
        }

    # 둘 다 실패
    return {
        "theme": theme_name,
        "is_structural": False,
        "confidence": "낮음",
        "verdict": "분석 데이터 부족",
        "duration_score": 0,
        "strength_score": 0,
        "driver_stability": 0,
        "sources": [],
        "analyzed_at": datetime.now().isoformat(),
        "method": "none",
    }


def analyze_all_themes(theme_names: List[str]) -> List[Dict]:
    """여러 테마에 대해 Tavily+Gemini 구조적 분석 수행.
    - 오늘 이미 Gemini 분석이 완료된 캐시가 있으면 재사용
    - Gemini 실패 시 이전 'tavily+gemini' 캐시를 보존 (덮어쓰지 않음)
    """
    existing = load_analysis()
    existing_map = {r["theme"]: r for r in existing}
    today = datetime.now().strftime("%Y-%m-%d")

    # 오늘자 LLM 분석 결과가 충분히 있으면 캐시 사용 (Gemini 또는 OpenAI)
    LLM_METHODS = {"tavily+gemini", "tavily+openai"}
    if existing:
        first_date = existing[0].get("analyzed_at", "")[:10]
        covers_all = all(name in existing_map for name in theme_names)
        has_llm = any(
            existing_map.get(n, {}).get("method") in LLM_METHODS
            for n in theme_names
        )
        has_3axis = any(
            existing_map.get(n, {}).get("duration_score", 0) > 0
            for n in theme_names
        )
        if first_date == today and covers_all and has_llm and has_3axis:
            print(f"[구조적 분석] 오늘({today}) 캐시 사용 ({len(existing)}개)")
            return existing

    tavily_client = _get_tavily_client()
    gemini_key = _get_gemini_api_key()
    openai_key = _get_openai_api_key()

    methods = []
    if tavily_client: methods.append("Tavily")
    if gemini_key: methods.append("Gemini")
    if openai_key: methods.append("OpenAI(fallback)")
    source = " + ".join(methods) if methods else "없음"
    print(f"[구조적 분석] {len(theme_names)}개 테마 (소스: {source})")

    gemini_failed = False  # rate limit 시 이후 테마는 Gemini 스킵

    results = []
    for i, name in enumerate(theme_names, 1):
        print(f"  [{i}/{len(theme_names)}] {name}...")

        # 이전 LLM 결과 (fallback용)
        old = existing_map.get(name, {})
        old_is_good = old.get("method") in LLM_METHODS and old.get("duration_score", 0) > 0

        # Tavily 검색
        search_text, sources = "", []
        if tavily_client:
            search_text, sources = _tavily_search(name, tavily_client)

        # Gemini 판단 (이전에 실패했으면 스킵) → 실패 시 OpenAI fallback
        judgment = None
        method = ""
        if search_text and gemini_key and not gemini_failed:
            judgment = _gemini_judge(name, search_text)
            if judgment:
                method = "tavily+gemini"
            else:
                gemini_failed = True
                print("  [Gemini rate limit] 이후 테마는 OpenAI fallback 또는 Tavily만 사용")
        if judgment is None and search_text and openai_key:
            print(f"    → OpenAI fallback 시도")
            judgment = _openai_judge(name, search_text)
            if judgment:
                method = "tavily+openai"

        # 결과 조립
        if judgment:
            result = {
                "theme": name,
                "is_structural": judgment.get("is_structural", False),
                "confidence": judgment.get("confidence", "낮음"),
                "verdict": judgment.get("verdict", ""),
                "bull_case": judgment.get("bull_case", ""),
                "bear_case": judgment.get("bear_case", ""),
                "investment_horizon": judgment.get("investment_horizon", ""),
                "key_drivers": judgment.get("key_drivers", []),
                "key_data": judgment.get("key_data", ""),
                "duration_score": int(judgment.get("duration_score", 0) or 0),
                "strength_score": int(judgment.get("strength_score", 0) or 0),
                "driver_stability": int(judgment.get("driver_stability", 0) or 0),
                "sources": sources,
                "analyzed_at": datetime.now().isoformat(),
                "method": method,
            }
        elif old_is_good:
            # Gemini 실패 + 이전에 성공한 캐시가 있으면 보존
            print(f"    → Gemini 실패, 이전 캐시 유지 ({old.get('analyzed_at','')[:10]})")
            result = old
        elif search_text:
            result = {
                "theme": name,
                "is_structural": True,
                "confidence": "보통",
                "verdict": search_text[:200],
                "bull_case": "",
                "bear_case": "",
                "investment_horizon": "",
                "key_drivers": [],
                "key_data": "",
                "duration_score": 0,
                "strength_score": 0,
                "driver_stability": 0,
                "sources": sources,
                "analyzed_at": datetime.now().isoformat(),
                "method": "tavily_only",
            }
        else:
            result = {
                "theme": name,
                "is_structural": False,
                "confidence": "낮음",
                "verdict": "분석 데이터 부족",
                "duration_score": 0,
                "strength_score": 0,
                "driver_stability": 0,
                "sources": [],
                "analyzed_at": datetime.now().isoformat(),
                "method": "none",
            }

        results.append(result)

    save_analysis(results)
    structural = sum(1 for r in results if r["is_structural"])
    gemini_count = sum(1 for r in results if r.get("method") == "tavily+gemini")
    cached_count = sum(1 for r in results if r.get("theme") in existing_map
                       and r is existing_map.get(r.get("theme")))
    print(f"[구조적 분석] 완료: {structural}/{len(results)}개 구조적 "
          f"(Gemini {gemini_count}개, 캐시유지 {cached_count}개, "
          f"Tavily {len(results)-gemini_count-cached_count}개)")
    return results


def save_analysis(results: List[Dict]):
    os.makedirs(os.path.dirname(ANALYSIS_FILE), exist_ok=True)
    with open(ANALYSIS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def load_analysis() -> List[Dict]:
    if os.path.exists(ANALYSIS_FILE):
        with open(ANALYSIS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    themes = [
        "광통신", "HBM(고대역메모리)", "전력반도체", "조선",
        "방위산업", "원자력발전", "2차전지(배터리)",
    ]
    results = analyze_all_themes(themes)

    print(f"\n{'='*70}")
    for r in results:
        tag = "O 구조적" if r["is_structural"] else "X 비구조"
        print(f"\n[{tag}/{r['confidence']}] {r['theme']}  ({r.get('method','')})")
        if r.get("verdict"):
            print(f"  판정: {r['verdict'][:80]}")
        if r.get("bull_case"):
            print(f"  근거: {r['bull_case'][:80]}")
        if r.get("bear_case"):
            print(f"  리스크: {r['bear_case'][:80]}")
        if r.get("key_data"):
            print(f"  핵심: {r['key_data'][:80]}")
        if r.get("investment_horizon"):
            print(f"  시계: {r['investment_horizon']}")
