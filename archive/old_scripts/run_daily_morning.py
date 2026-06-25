#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
매일 아침 자동 실행 스케줄러

실행: python run_daily_morning.py

동작:
- 매일 아침 7시 50분에 자동 실행
- 전날 종가까지 데이터로 단기 종목 선정
- 텔레그램 자동 전송
- 계속 실행 (다음날도 자동)

수동 실행:
- python run_daily_morning.py --now  # 즉시 1회 실행
"""

import sys
import os
import io
import schedule
import time
from datetime import datetime

# 윈도우 콘솔 인코딩
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# symposium 모듈 경로
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "symposium"))

from screener.short_term.pipeline import run_short_term_pipeline


def morning_scan():
    """
    아침 단기 종목 스캔

    - 전날 종가까지 데이터 사용
    - TOP 10 선정
    - 최소 점수 60점
    - 텔레그램 자동 전송
    """
    now = datetime.now()
    print("\n" + "=" * 80)
    print(f"📈 아침 단기 종목 스캔 시작")
    print(f"⏰ 실행 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    try:
        df = run_short_term_pipeline(
            top_n=10,                # TOP 10
            min_score=60.0,          # 최소 60점 (엄격)
            max_workers=8,
            send_telegram=True,      # 텔레그램 전송
            telegram_compact=False   # 상세 정보
        )

        if df is not None and len(df) > 0:
            print(f"\n✅ 완료: {len(df)}개 종목 선정 및 텔레그램 전송")
        else:
            print(f"\n⚠️ 필터 통과 종목 없음 (최소 60점)")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 80)


def run_scheduler():
    """
    스케줄러 실행

    매일 아침 7:50에 자동 실행
    """
    # 스케줄 등록
    schedule.every().day.at("07:50").do(morning_scan)

    print("=" * 80)
    print("🤖 단기 종목 자동 스캐너 시작")
    print("=" * 80)
    print("📅 스케줄: 매일 아침 07:50")
    print("🎯 목표: 전날 데이터 기반 TOP 10 선정")
    print("📱 텔레그램 자동 전송")
    print("\n대기 중... (Ctrl+C로 종료)")
    print("=" * 80)

    # 다음 실행 시간 표시
    next_run = schedule.next_run()
    if next_run:
        print(f"\n⏰ 다음 실행 예정: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

    # 무한 루프
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)  # 30초마다 체크

    except KeyboardInterrupt:
        print("\n\n[종료] 스케줄러를 종료합니다")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="매일 아침 단기 종목 자동 스캐너")
    parser.add_argument(
        "--now",
        action="store_true",
        help="즉시 1회 실행 (스케줄 없이)"
    )
    parser.add_argument(
        "--time",
        type=str,
        default="07:50",
        help="실행 시각 (기본: 07:50, 형식: HH:MM)"
    )

    args = parser.parse_args()

    if args.now:
        # 즉시 실행
        print("[모드] 즉시 실행")
        morning_scan()
    else:
        # 스케줄 모드
        if args.time != "07:50":
            schedule.clear()
            schedule.every().day.at(args.time).do(morning_scan)
            print(f"[모드] 커스텀 스케줄: {args.time}")

        run_scheduler()
