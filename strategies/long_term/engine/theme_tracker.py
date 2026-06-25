"""
theme_tracker.py
네이버 금융 전체 테마(263개)의 일일 등락률을 누적 저장하고,
테마 지속성 점수 산출 + 섹터 내 순환매를 감지한다.
"""

import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

_V2_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "v2")
HISTORY_FILE = os.path.join(_V2_DATA_DIR, "theme_history.json")

# ── 메타 카테고리: 순환매 감지를 위한 상위 그룹 ──────────────────────────────
META_CATEGORIES = {
    "AI 하드웨어": [
        "광통신", "HBM(고대역메모리)", "시스템반도체", "전력반도체",
        "반도체장비", "반도체 대표주(테마)", "SOCAMM", "PCB(FPCB 등)",
        "반도체 소재", "온디바이스 AI",
    ],
    "에너지/전력": [
        "원자력발전", "SMR(소형모듈원전)", "LNG(액화천연가스)",
        "태양광에너지", "풍력에너지", "연료전지(수소)",
        "고체산화물 연료전지(SOFC)", "전력설비",
        "초고압 송전 변압기", "전기차 충전",
    ],
    "방산/조선/우주": [
        "조선", "방위산업", "우주항공", "드론(UAM/드론택시)",
        "스페이스X(SpaceX)", "K-방산",
    ],
    "2차전지/모빌리티": [
        "2차전지(배터리)", "2차전지(울트라캡)", "전기차",
        "자율주행", "수소차", "리튬",
    ],
    "바이오/헬스케어": [
        "바이오", "신약개발", "AI신약", "의료기기",
        "바이오시밀러", "GLP-1", "면역항암",
    ],
    "플랫폼/소프트웨어": [
        "클라우드", "SaaS", "메타버스", "게임",
        "스마트팩토리(스마트공장)", "로봇",
    ],
}


def _parse_change(text: str) -> float:
    try:
        return float(text.replace("%", "").replace("+", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def _parse_int(text: str) -> int:
    try:
        return int(text.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


# ── 데이터 수집 ──────────────────────────────────────────────────────────────

def collect_all_themes() -> Dict[str, Dict]:
    """네이버 금융 전체 테마 수집 (7페이지, 약 263개).
    반환: {"테마명": {"today": float, "day3": float, "up": int, "flat": int, "down": int, "theme_no": int}}
    """
    all_themes = {}

    for page in range(1, 8):
        url = f"https://finance.naver.com/sise/theme.naver?&page={page}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            res.raise_for_status()
            soup = BeautifulSoup(res.content, "html.parser")

            for table in soup.find_all("table", class_="type_1"):
                for row in table.find_all("tr"):
                    tds = row.find_all("td")
                    if len(tds) < 6:
                        continue
                    name_tag = tds[0].find("a")
                    if not name_tag:
                        continue

                    name = name_tag.get_text(strip=True)
                    href = name_tag.get("href", "")
                    theme_no = 0
                    if "no=" in href:
                        try:
                            theme_no = int(href.split("no=")[-1].split("&")[0])
                        except ValueError:
                            pass

                    all_themes[name] = {
                        "today": _parse_change(tds[1].get_text(strip=True)),
                        "day3": _parse_change(tds[2].get_text(strip=True)),
                        "up": _parse_int(tds[3].get_text(strip=True)),
                        "flat": _parse_int(tds[4].get_text(strip=True)),
                        "down": _parse_int(tds[5].get_text(strip=True)),
                        "theme_no": theme_no,
                    }
        except Exception as e:
            print(f"[테마 수집 오류 page={page}]: {e}")

    print(f"[테마 히스토리] {len(all_themes)}개 테마 수집 완료")
    return all_themes


# ── 히스토리 저장/로드 ────────────────────────────────────────────────────────

def save_theme_history(today_data: Dict[str, Dict]):
    """오늘자 테마 데이터를 히스토리 파일에 추가."""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    history = {}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

    date_key = datetime.now().strftime("%Y-%m-%d")
    history[date_key] = today_data

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"[테마 히스토리] {date_key} 저장 완료 ({len(today_data)}개 테마)")


def load_theme_history(days: int = 30) -> Dict:
    """최근 N일 히스토리 로드."""
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    # 최근 N일만 필터
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return {d: v for d, v in sorted(history.items()) if d >= cutoff}


# ── 테마 지속성 점수 ──────────────────────────────────────────────────────────

def calc_theme_persistence(history: Dict) -> List[Dict]:
    """테마별 지속성 점수 산출.
    네이버가 제공하는 '오늘 등락률 + 3일 등락률 + 상승/하락 종목 수'를 모두 활용.
    히스토리가 1일뿐이어도 3일 데이터와 종목 건강도로 충분히 판별 가능.
    """
    if not history:
        return []

    dates = sorted(history.keys())
    all_theme_names = set()
    for d in dates:
        all_theme_names.update(history[d].keys())

    results = []
    for name in all_theme_names:
        daily_returns = []
        day3_returns = []
        for d in dates:
            theme_data = history[d].get(name)
            if theme_data:
                daily_returns.append(theme_data["today"])
                day3_returns.append(theme_data.get("day3", 0))

        if not daily_returns:
            continue

        latest = history[dates[-1]].get(name, {})
        today_ret = latest.get("today", 0)
        day3_ret = latest.get("day3", 0)
        up_count = latest.get("up", 0)
        down_count = latest.get("down", 0)
        flat_count = latest.get("flat", 0)
        total_stocks = up_count + down_count + flat_count

        n = len(daily_returns)
        days_positive = sum(1 for r in daily_returns if r > 0)
        days_total = n

        # 연속 상승일 (최근부터 역순)
        consecutive = 0
        for r in reversed(daily_returns):
            if r > 0:
                consecutive += 1
            else:
                break

        # 3일 데이터 활용: day3가 양수 = 3일간 상승 추세
        # 히스토리 1일이어도 3일 등락률로 최소 3일 추세 판단 가능
        if day3_ret > 0 and today_ret > 0:
            # 오늘도 +, 3일도 + → 최소 3일 상승 지속
            consecutive = max(consecutive, 3)
            days_positive = max(days_positive, 3)
            days_total = max(days_total, 3)

        avg_daily = sum(daily_returns) / n if n > 0 else 0
        total_7d = sum(daily_returns[-7:]) if n >= 7 else sum(daily_returns)

        # 가속/감속 판단
        if n >= 5:
            recent_3_avg = sum(daily_returns[-3:]) / 3
            prev_avg = sum(daily_returns[:-3]) / max(1, len(daily_returns[:-3]))
            if recent_3_avg > prev_avg * 1.3 and recent_3_avg > 0:
                acceleration = "가속"
            elif recent_3_avg < prev_avg * 0.5 or recent_3_avg < 0:
                acceleration = "감속"
            else:
                acceleration = "유지"
        else:
            # 히스토리 부족 시: 오늘 vs 3일 평균 비교로 판단
            day3_avg = day3_ret / 3 if day3_ret != 0 else 0
            if today_ret > day3_avg * 1.5 and today_ret > 0.5:
                acceleration = "가속"
            elif today_ret < day3_avg * 0.3 or today_ret < -0.5:
                acceleration = "감속"
            elif today_ret > 0 and day3_ret > 0:
                acceleration = "유지"
            elif today_ret < 0:
                acceleration = "감속"
            else:
                acceleration = "유지"

        # 종목 건강도: 상승 종목 비율 (테마 전체가 오르는지 일부만 오르는지)
        health_ratio = up_count / max(1, total_stocks)  # 0~1

        # ── 지속성 점수 (0-100) ──────────────────────────────────────
        score = 0

        # (1) 양수 비율 (최대 20점)
        pos_ratio = days_positive / max(1, days_total)
        score += min(20, pos_ratio * 25)

        # (2) 연속 상승일 (최대 20점) — 3일 데이터 반영
        score += min(20, consecutive * 5)

        # (3) 3일 누적 수익률 (최대 20점) — 핵심: 네이버 day3 직접 활용
        score += min(20, max(0, day3_ret) * 4)

        # (4) 오늘 수익률 (최대 15점)
        score += min(15, max(0, today_ret) * 3)

        # (5) 종목 건강도 (최대 15점) — 상승종목 80%+ = 견조한 테마
        score += min(15, health_ratio * 18)

        # (6) 7일 누적 보너스 (히스토리 충분할 때만, 최대 10점)
        if n >= 5:
            score += min(10, max(0, total_7d) * 1.5)

        score = round(min(100, score), 1)

        # ── 트렌드 태그 ──────────────────────────────────────────────
        if score >= 70 and consecutive >= 3 and health_ratio >= 0.6:
            trend = "구조적 상승"
        elif score >= 60 and day3_ret > 0 and today_ret > day3_ret / 3:
            trend = "상승 지속"
        elif score >= 50 and acceleration == "가속":
            trend = "신규 부상"
        elif acceleration == "감속" and day3_ret > 0:
            trend = "모멘텀 감속"
        elif today_ret > 3 and (day3_ret <= 0 or health_ratio < 0.4):
            trend = "단발성"
        elif today_ret < -1:
            trend = "하락"
        else:
            trend = "중립"

        results.append({
            "name": name,
            "persistence_score": score,
            "trend": trend,
            "acceleration": acceleration,
            "days_positive": days_positive,
            "days_total": days_total,
            "consecutive": consecutive,
            "avg_daily": round(avg_daily, 2),
            "total_7d": round(total_7d, 2),
            "today": today_ret,
            "day3": day3_ret,
            "up": up_count,
            "down": down_count,
            "health": round(health_ratio * 100, 0),
            "theme_no": latest.get("theme_no", 0),
        })

    results.sort(key=lambda x: x["persistence_score"], reverse=True)
    return results


# ── 순환매 감지 ───────────────────────────────────────────────────────────────

def _match_category(theme_name: str) -> str:
    """테마명이 어떤 메타 카테고리에 속하는지 판별."""
    name_lower = theme_name.lower()
    for category, keywords in META_CATEGORIES.items():
        for kw in keywords:
            if kw.lower() in name_lower or name_lower in kw.lower():
                return category
    return ""


def detect_rotation(persistence_list: List[Dict]) -> List[Dict]:
    """메타 카테고리 내 서브테마 모멘텀 비교로 순환매 감지."""
    # 카테고리별 서브테마 그룹핑
    cat_themes = defaultdict(list)
    for t in persistence_list:
        cat = _match_category(t["name"])
        if cat:
            cat_themes[cat].append(t)

    rotations = []
    for category, themes in cat_themes.items():
        if len(themes) < 2:
            continue

        # 모멘텀 기준 정렬
        themes.sort(key=lambda x: x["today"], reverse=True)

        leader = themes[0]
        rising = [t for t in themes if t["acceleration"] == "가속" and t["name"] != leader["name"]]
        fading = [t for t in themes if t["acceleration"] == "감속"]

        rotations.append({
            "category": category,
            "current_leader": leader["name"],
            "leader_today": leader["today"],
            "leader_persistence": leader["persistence_score"],
            "rising": [{"name": t["name"], "today": t["today"], "score": t["persistence_score"]} for t in rising[:3]],
            "fading": [{"name": t["name"], "today": t["today"], "score": t["persistence_score"]} for t in fading[:3]],
            "rotation_signal": len(rising) > 0 and len(fading) > 0,
            "sub_themes": [{"name": t["name"], "today": t["today"],
                            "persistence": t["persistence_score"],
                            "acceleration": t["acceleration"]} for t in themes],
        })

    rotations.sort(key=lambda x: max(t["persistence"] for t in x["sub_themes"]) if x["sub_themes"] else 0, reverse=True)
    return rotations


# ── 메타 카테고리 시계열 분석 ────────────────────────────────────────────────

def analyze_category_flow(history: Dict) -> List[Dict]:
    """카테고리별 leader 변천(B) + 평균 today% 시계열(C).

    history: load_theme_history(days=N) 반환값 (날짜 → 테마 dict)
    return: 6개 카테고리별 {
        category, today_avg, prev_avg, delta_avg,
        today_leader, prev_leader, leader_changed,
        leader_history: [{date, leader, today}],
        avg_history:    [{date, avg, n}],
    }
    """
    if not history:
        return []

    dates = sorted(history.keys())
    # 카테고리별 일별 (테마명 → today, 카테고리 평균 today)
    cat_daily: Dict[str, Dict[str, Dict]] = {c: {} for c in META_CATEGORIES.keys()}

    for d in dates:
        day_data = history[d] or {}
        cat_buckets: Dict[str, list] = {c: [] for c in META_CATEGORIES.keys()}
        for theme_name, theme_data in day_data.items():
            cat = _match_category(theme_name)
            if not cat:
                continue
            today = theme_data.get("today", 0)
            cat_buckets[cat].append((theme_name, today))

        for cat, themes in cat_buckets.items():
            if not themes:
                continue
            themes.sort(key=lambda x: x[1], reverse=True)
            leader_name, leader_today = themes[0]
            avg = sum(t for _, t in themes) / len(themes)
            cat_daily[cat][d] = {
                "leader": leader_name,
                "leader_today": leader_today,
                "avg": avg,
                "n": len(themes),
            }

    results = []
    for cat in META_CATEGORIES.keys():
        per_day = cat_daily.get(cat, {})
        if not per_day:
            continue
        cat_dates = sorted(per_day.keys())
        today_d = cat_dates[-1]
        prev_d = cat_dates[-2] if len(cat_dates) >= 2 else None

        today_entry = per_day[today_d]
        prev_entry = per_day[prev_d] if prev_d else None

        today_avg = today_entry["avg"]
        prev_avg = prev_entry["avg"] if prev_entry else today_avg
        delta_avg = today_avg - prev_avg

        today_leader = today_entry["leader"]
        prev_leader = prev_entry["leader"] if prev_entry else today_leader
        leader_changed = bool(prev_entry) and prev_leader != today_leader

        results.append({
            "category": cat,
            "today_avg": round(today_avg, 2),
            "prev_avg": round(prev_avg, 2),
            "delta_avg": round(delta_avg, 2),
            "today_leader": today_leader,
            "prev_leader": prev_leader,
            "leader_changed": leader_changed,
            "leader_history": [
                {"date": d, "leader": per_day[d]["leader"],
                 "today": round(per_day[d]["leader_today"], 2)}
                for d in cat_dates
            ],
            "avg_history": [
                {"date": d, "avg": round(per_day[d]["avg"], 2),
                 "n": per_day[d]["n"]}
                for d in cat_dates
            ],
        })

    # 자금 유입 큰 카테고리부터 (delta_avg 내림차순)
    results.sort(key=lambda x: x["delta_avg"], reverse=True)
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 1. 전체 테마 수집 + 히스토리 저장
    print("=" * 60)
    print("  테마 트래커: 전체 테마 수집 + 지속성 분석")
    print("=" * 60)

    today_data = collect_all_themes()
    save_theme_history(today_data)

    # 2. 지속성 분석
    history = load_theme_history(days=14)
    persistence = calc_theme_persistence(history)

    print(f"\n{'='*60}")
    print(f"  구조적 상승 테마 TOP 15 (지속성 점수순)")
    print(f"{'='*60}")
    for i, t in enumerate(persistence[:15], 1):
        trend_tag = {
            "구조적 상승": "[구조]",
            "신규 부상": "[부상]",
            "모멘텀 감속": "[감속]",
            "단발성": "[단발]",
            "하락 추세": "[하락]",
        }.get(t["trend"], "[중립]")

        print(f"  {i:>2}. {t['name']:<28} 지속={t['persistence_score']:>5.1f}  "
              f"오늘={t['today']:>+6.2f}%  7일={t['total_7d']:>+6.2f}%  "
              f"연속{t['consecutive']}일  {trend_tag} {t['acceleration']}")

    # 3. 순환매 감지
    rotations = detect_rotation(persistence)
    if rotations:
        print(f"\n{'='*60}")
        print(f"  순환매 감지")
        print(f"{'='*60}")
        for r in rotations:
            signal = " ** 순환매 진행 **" if r["rotation_signal"] else ""
            print(f"\n  [{r['category']}]{signal}")
            print(f"    리더: {r['current_leader']} ({r['leader_today']:+.2f}%)")
            if r["rising"]:
                names = ", ".join(f"{t['name']}({t['today']:+.1f}%)" for t in r["rising"])
                print(f"    가속: {names}")
            if r["fading"]:
                names = ", ".join(f"{t['name']}({t['today']:+.1f}%)" for t in r["fading"])
                print(f"    감속: {names}")
    print()
