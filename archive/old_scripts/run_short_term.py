#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
단기 투자 종목 선정 실행 스크립트

사용법:
  python run_short_term.py              # 기본 (TOP 15, 최소 55점)
  python run_short_term.py --top 10     # TOP 10만
  python run_short_term.py --score 60   # 최소 60점
"""

import sys
import os
import io

# 윈도우 콘솔 인코딩 문제 해결
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# symposium 모듈 import 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "symposium"))

from screener.short_term.pipeline import run_short_term_pipeline


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="단기 투자 종목 선정")
    parser.add_argument("--top", type=int, default=15, help="결과 개수 (기본 15)")
    parser.add_argument("--score", type=float, default=55.0, help="최소 점수 (기본 55)")
    parser.add_argument("--workers", type=int, default=8, help="병렬 작업 수 (기본 8)")
    parser.add_argument("--no-telegram", action="store_true", help="텔레그램 전송 안함")
    parser.add_argument("--compact", action="store_true", help="텔레그램 간단 요약만 (TOP 5)")

    args = parser.parse_args()

    try:
        df = run_short_term_pipeline(
            top_n=args.top,
            min_score=args.score,
            max_workers=args.workers,
            send_telegram=not args.no_telegram,
            telegram_compact=args.compact,
        )

        if df is not None:
            print(f"\n완료: {len(df)}개 종목 선정")
        else:
            print("\n필터 통과 종목 없음")

    except KeyboardInterrupt:
        print("\n\n사용자 중단")
        sys.exit(1)
    except Exception as e:
        print(f"\n오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
