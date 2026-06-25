#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
아침 프리마켓 스캐너 (8:00~8:50)

실행 방법:
  python run_morning_premarket.py

동작:
1. 전날 선정된 후보 종목 로드 (symposium/data/short_term/latest.json)
2. 8:00~8:50 동안 매 10분마다 프리마켓 데이터 수집
3. 8:45 최종 스캔 후 텔레그램 전송
4. 자동 종료

스케줄:
- 08:00 - 1차 스캔
- 08:10 - 2차 스캔
- 08:20 - 3차 스캔
- 08:30 - 4차 스캔 (동시호가 시작)
- 08:40 - 5차 스캔
- 08:50 - 최종 스캔 + 텔레그램 전송
"""

import sys
import os
import io
import json
from datetime import datetime, time as dt_time
import time

# 윈도우 콘솔 인코딩
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# symposium 모듈 경로
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "symposium"))

from screener.short_term.premarket import scan_premarket_candidates, is_premarket_time
from screener.short_term.telegram_notifier import send_telegram_message

# 데이터 디렉토리
DATA_DIR = os.path.join(
    os.path.dirname(__file__),
    "symposium", "screener", "data", "short_term"
)


def load_yesterday_candidates() -> list:
    """
    전날 선정된 후보 종목 로드

    우선순위:
    1. today.json (오늘 날짜 파일)
    2. latest.json (심볼릭 링크)
    3. 가장 최근 날짜 파일
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_file = os.path.join(DATA_DIR, f"{today_str}.json")

    # 1. 오늘 날짜 파일
    if os.path.exists(today_file):
        print(f"[로드] {today_file}")
        with open(today_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("picks", [])

    # 2. 가장 최근 파일 찾기
    if os.path.exists(DATA_DIR):
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
        if files:
            files.sort(reverse=True)
            latest_file = os.path.join(DATA_DIR, files[0])
            print(f"[로드] {latest_file} (최근 파일)")
            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("picks", [])

    print("[경고] 전날 후보 종목 없음 - 빈 리스트 반환")
    return []


def format_premarket_message(results: list, scan_time: str) -> str:
    """
    텔레그램 메시지 포맷팅

    results: 프리마켓 스캔 결과 (premarket_score 추가됨)
    scan_time: 스캔 시각 (예: "08:45")
    """
    now = datetime.now().strftime("%Y-%m-%d")

    # 프리마켓 점수 기준 정렬
    sorted_results = sorted(
        results,
        key=lambda x: (x.get("premarket_score", 0), x.get("score", 0)),
        reverse=True
    )

    top_picks = sorted_results[:10]

    msg = f"📈 <b>아침 프리마켓 분석</b> ({scan_time})\n"
    msg += f"📅 {now}\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"

    if not top_picks:
        msg += "⚠️ 매수 후보 없음\n"
        return msg

    msg += f"<b>💎 오늘의 매수 후보 TOP {len(top_picks)}</b>\n\n"

    for idx, pick in enumerate(top_picks, 1):
        name = pick.get("name", "")
        ticker = pick.get("ticker", "")

        # 점수
        total_score = pick.get("score", 0)
        pm_score = pick.get("premarket_score", 0)
        entry_score = pick.get("entry_score", 0)
        theme_score = pick.get("theme_score", 0)

        # 프리마켓 데이터
        pm_detail = pick.get("premarket_detail", "N/A")
        pm_data = pick.get("premarket_data", {})
        expected_price = pm_data.get("expected_price", 0)
        gap_pct = pm_data.get("expected_change_pct", 0)

        # RSI
        rsi = pick.get("rsi", 50)

        msg += f"<b>{idx}. {name}</b> ({ticker.replace('.KS', '').replace('.KQ', '')})\n"

        if pm_score > 0:
            msg += f"  🚀 프리마켓: <b>{pm_detail}</b>\n"
            if expected_price > 0:
                msg += f"  💰 예상가: {expected_price:,}원 ({gap_pct:+.1f}%)\n"
        else:
            msg += f"  ⏸️ 프리마켓: {pm_detail}\n"

        msg += f"  📊 점수: {total_score:.1f} (PM+{pm_score} / 진입{entry_score} / 테마{theme_score})\n"
        msg += f"  📈 RSI: {rsi:.0f}\n"

        # 진입 시그널
        entry_detail = pick.get("entry_detail", "")
        if entry_detail and entry_detail != "중립":
            msg += f"  ✅ {entry_detail}\n"

        # 테마
        theme_detail = pick.get("theme_detail", "")
        if theme_detail and theme_detail != "테마 없음":
            msg += f"  🔥 {theme_detail}\n"

        msg += "\n"

    msg += f"━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"⏰ 장 시작: 09:00\n"
    msg += f"💡 시초가 확인 후 진입 추천\n"

    return msg


def run_morning_scan():
    """
    아침 프리마켓 스캔 실행
    """
    print("\n" + "=" * 80)
    print("아침 프리마켓 스캔 시작")
    print(f"현재 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 1. 전날 후보 로드
    candidates = load_yesterday_candidates()

    if not candidates:
        print("[종료] 스캔할 후보 종목 없음")
        return

    print(f"[후보] {len(candidates)}개 종목 로드됨")

    # 2. 프리마켓 데이터 수집
    print(f"\n[프리마켓 스캔] 진행 중...")
    results = scan_premarket_candidates(candidates, max_workers=8)

    # 3. 결과 출력
    print(f"\n{'='*80}")
    print(f"프리마켓 스캔 결과 (TOP 15)")
    print(f"{'='*80}")
    print(f"{'순위':<4} {'종목명':<15} {'프리마켓':<6} {'기존점수':<8} {'프리마켓 신호':<30}")
    print("-" * 80)

    top_results = results[:15]
    for idx, item in enumerate(top_results, 1):
        print(
            f"{idx:<4} "
            f"{item.get('name', '')[:14]:<15} "
            f"{item.get('premarket_score', 0):>6} "
            f"{item.get('score', 0):>8.1f} "
            f"{item.get('premarket_detail', '')[:30]:<30}"
        )

    # 4. 텔레그램 전송 (8:45 이후만)
    now = datetime.now()
    scan_time = now.strftime("%H:%M")

    if now.hour == 8 and now.minute >= 45:
        print(f"\n[텔레그램] 최종 결과 전송 중...")
        msg = format_premarket_message(results, scan_time)

        try:
            send_telegram_message(msg, parse_mode="HTML")
            print("[텔레그램] 전송 완료 ✓")
        except Exception as e:
            print(f"[텔레그램] 전송 실패: {e}")
    else:
        print(f"\n[스킵] 텔레그램 전송은 08:45 이후 실행 (현재 {scan_time})")

    print(f"\n{'='*80}")
    print("아침 프리마켓 스캔 완료")
    print(f"{'='*80}\n")


def schedule_morning_scans():
    """
    8:00~8:50 스케줄 실행

    매 10분마다 스캔, 8:50 최종 전송 후 종료
    """
    scan_times = [
        dt_time(8, 0),   # 08:00
        dt_time(8, 10),  # 08:10
        dt_time(8, 20),  # 08:20
        dt_time(8, 30),  # 08:30 (동시호가 시작)
        dt_time(8, 40),  # 08:40
        dt_time(8, 50),  # 08:50 (최종)
    ]

    executed_scans = set()

    print("=" * 80)
    print("아침 프리마켓 스케줄러 시작")
    print("=" * 80)
    print("스케줄:")
    for t in scan_times:
        print(f"  - {t.strftime('%H:%M')}")
    print("\n대기 중... (Ctrl+C로 중단)")
    print("=" * 80)

    try:
        while True:
            now = datetime.now()
            current_time = now.time()

            # 8:50 지나면 종료
            if current_time > dt_time(8, 55):
                print("\n[종료] 스케줄 완료 (08:50 이후)")
                break

            # 8시 이전이면 대기
            if current_time < dt_time(8, 0):
                wait_seconds = (datetime.combine(now.date(), dt_time(8, 0)) - now).total_seconds()
                print(f"[대기] 08:00까지 {int(wait_seconds)}초 남음...")
                time.sleep(min(60, wait_seconds))
                continue

            # 스케줄된 시간 체크
            for scan_time in scan_times:
                time_key = scan_time.strftime("%H:%M")

                if time_key in executed_scans:
                    continue

                # 스케줄 시간 도달 (±1분 허용)
                time_diff = (
                    datetime.combine(now.date(), current_time) -
                    datetime.combine(now.date(), scan_time)
                ).total_seconds()

                if -60 <= time_diff <= 60:
                    print(f"\n{'='*80}")
                    print(f"[실행] {time_key} 스캔")
                    print(f"{'='*80}")

                    run_morning_scan()

                    executed_scans.add(time_key)

                    # 8:50 스캔 완료 후 종료
                    if scan_time == dt_time(8, 50):
                        print("\n[완료] 최종 스캔 완료 - 프로그램 종료")
                        return

                    break

            # 30초 대기
            time.sleep(30)

    except KeyboardInterrupt:
        print("\n\n[중단] 사용자가 스케줄러를 중단했습니다")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="아침 프리마켓 스캐너")
    parser.add_argument(
        "--now",
        action="store_true",
        help="즉시 1회 실행 (스케줄 없이)"
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="스케줄 모드 (8:00~8:50 자동 실행)"
    )

    args = parser.parse_args()

    if args.now:
        # 즉시 실행
        run_morning_scan()
    elif args.schedule:
        # 스케줄 모드
        schedule_morning_scans()
    else:
        # 기본: 프리마켓 시간이면 즉시 실행, 아니면 스케줄
        if is_premarket_time():
            print("[모드] 프리마켓 시간 - 즉시 실행")
            run_morning_scan()
        else:
            print("[모드] 프리마켓 시간 외 - 스케줄 대기")
            schedule_morning_scans()
