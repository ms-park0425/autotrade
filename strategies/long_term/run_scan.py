#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
장기 투자 종목 스캐너

실행:
  python strategies/long_term/run_scan.py --now
  python strategies/long_term/run_scan.py --schedule

목표:
  - 앞으로 몇 개월~수년간 오를 종목 선정
  - 구조적 테마 + 펀더멘털 + 기술적 진입점
  - 매일 아침 07:00 전날까지 데이터 분석
"""

import sys
import os
import io
from datetime import datetime

# 윈도우 콘솔 인코딩
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 엔진 모듈 경로
ENGINE_DIR = os.path.join(os.path.dirname(__file__), "engine")
sys.path.insert(0, ENGINE_DIR)

from pipeline import run_v2_pipeline


def long_term_scan(top_n=20, min_score=70.0, send_telegram=True):
    """
    장기 투자 종목 스캔

    Args:
        top_n: 선정할 종목 수 (기본 20개)
        min_score: 최소 점수 (기본 70점)
        send_telegram: 텔레그램 전송 여부
    """
    now = datetime.now()
    print("\n" + "=" * 80)
    print(f"📊 장기 투자 종목 스캔 시작")
    print(f"⏰ 실행 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print(f"목표: 구조적 테마 기반 장기 성장주 선정")
    print(f"기준: 펌더멘털(40) + 테마(30) + 기술(20) + 수급(10)")
    print(f"설정: TOP {top_n}, 최소 {min_score}점")
    print("=" * 80)

    try:
        result = run_v2_pipeline(
            top_n=top_n,
            min_score=min_score,
            send_telegram=send_telegram,
            telegram_compact=False
        )

        if result and len(result.get("picks", [])) > 0:
            picks = result["picks"]
            print(f"\n✅ 완료: {len(picks)}개 종목 선정")

            # 간단한 결과 출력
            print(f"\n{'='*80}")
            print(f"TOP 10 미리보기")
            print(f"{'='*80}")
            print(f"{'순위':<4} {'종목명':<20} {'점수':<8} {'테마':<30}")
            print("-" * 80)

            for idx, pick in enumerate(picks[:10], 1):
                name = pick.get("name", "")[:18]
                score = pick.get("score", 0)
                themes = pick.get("themes", "")[:28]
                print(f"{idx:<4} {name:<20} {score:>7.1f} {themes:<30}")

            if send_telegram:
                print(f"\n📱 텔레그램 전송 완료")
        else:
            print(f"\n⚠️ 필터 통과 종목 없음 (최소 {min_score}점)")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 80)


def run_scheduler():
    """
    일일 스케줄러 실행

    매일 아침 07:00에 자동 실행
    """
    import schedule
    import time

    # 스케줄 등록
    schedule.every().day.at("07:00").do(
        lambda: long_term_scan(top_n=20, min_score=70.0, send_telegram=True)
    )

    print("=" * 80)
    print("🤖 장기 투자 자동 스캐너 시작")
    print("=" * 80)
    print("📅 스케줄: 매일 아침 07:00")
    print("🎯 목표: 구조적 테마 기반 성장주 선정")
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
            time.sleep(60)  # 1분마다 체크

    except KeyboardInterrupt:
        print("\n\n[종료] 스케줄러를 종료합니다")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="장기 투자 종목 스캐너")
    parser.add_argument(
        "--now",
        action="store_true",
        help="즉시 1회 실행 (스케줄 없이)"
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="스케줄 모드 (매일 아침 07:00)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="선정할 종목 수 (기본 20개)"
    )
    parser.add_argument(
        "--score",
        type=float,
        default=70.0,
        help="최소 점수 (기본 70점)"
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="텔레그램 전송 안 함"
    )

    args = parser.parse_args()

    if args.now:
        # 즉시 실행
        print("[모드] 즉시 실행")
        long_term_scan(
            top_n=args.top,
            min_score=args.score,
            send_telegram=not args.no_telegram
        )
    elif args.schedule:
        # 스케줄 모드
        print("[모드] 스케줄 실행")
        run_scheduler()
    else:
        # 기본: 즉시 실행
        print("[모드] 기본 (즉시 실행)")
        long_term_scan(
            top_n=args.top,
            min_score=args.score,
            send_telegram=not args.no_telegram
        )
