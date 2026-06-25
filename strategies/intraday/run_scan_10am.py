#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
당일 매매 10시 스캔

실행:
  python strategies/intraday/run_scan_10am.py

동작:
  - 10:00 정각 실행 (수동 or 스케줄)
  - 9:00~10:00 차트 패턴 분석
  - 지속 가능성 높은 종목만 선정
  - TOP 5 텔레그램 전송
"""

import sys
import os
import io
import json
from datetime import datetime

# 윈도우 콘솔 인코딩
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# (개발 중 - 아직 미구현)


def load_config():
    """설정 파일 로드"""
    config_path = os.path.join(
        os.path.dirname(__file__), "config", "config.json"
    )
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def scan_1h_patterns():
    """
    9:00~10:00 차트 패턴 분석

    TODO: 실제 구현 필요
    - 1시간 캔들 데이터 수집
    - 급등 패턴 인식
    - 거래량 분석
    - 호가창 스냅샷
    """
    print(f"[스캔] 9:00~10:00 차트 패턴 분석 중...")

    # 임시: 더미 데이터
    candidates = []

    # TODO: 실제 스캔 로직
    # 1. 전날 스윙 후보 로드
    # 2. 시가총액 상위 200개 + 거래대금 상위 100개
    # 3. 9:00~10:00 1시간 데이터 수집
    # 4. 차트 패턴 분석 (급등 지속성, 조정 없이 상승)
    # 5. 거래량 폭증 확인 (전일 대비)
    # 6. 호가창 매수 우위 확인

    return candidates


def format_telegram_message(candidates):
    """
    텔레그램 메시지 포맷팅
    """
    now = datetime.now()
    msg = f"📈 <b>당일 매매 TOP {len(candidates)}</b> (10:00)\n"
    msg += f"📅 {now.strftime('%Y-%m-%d')}\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"

    if not candidates:
        msg += "⚠️ 조건 충족 종목 없음\n"
        return msg

    for idx, cand in enumerate(candidates, 1):
        name = cand.get("name", "")
        ticker = cand.get("ticker", "")
        price = cand.get("price", 0)
        change_pct = cand.get("change_1h", 0)
        score = cand.get("score", 0)

        msg += f"<b>{idx}. {name}</b> ({ticker.replace('.KS', '').replace('.KQ', '')})\n"
        msg += f"   현재가: {price:,}원 ({change_pct:+.1f}%)\n"
        msg += f"   점수: {score:.0f}점\n\n"

        # 차트
        chart_score = cand.get("chart_score", 0)
        pattern = cand.get("pattern", "N/A")
        msg += f"   📊 차트 ({chart_score}점)\n"
        msg += f"   - {pattern}\n"

        # 거래량
        volume_score = cand.get("volume_score", 0)
        volume_ratio = cand.get("volume_ratio", 0)
        msg += f"   📈 거래량 ({volume_score}점)\n"
        msg += f"   - 전일 대비 {volume_ratio:.1f}배\n"

        # 호가창
        order_score = cand.get("order_score", 0)
        bid_ratio = cand.get("bid_ratio", 0)
        msg += f"   💰 호가창 ({order_score}점)\n"
        msg += f"   - 매수 {bid_ratio:.0f}% 우위\n"

        # 재료
        if cand.get("theme"):
            msg += f"   🔥 재료: {cand.get('theme', 'N/A')}\n"

        # 추천
        target_price = price * 1.05
        stop_price = price * 0.97
        msg += f"\n   ⚡ 진입 추천: 현재가 or 조정 시\n"
        msg += f"   🎯 목표가: {target_price:,.0f}원 (+5%)\n"
        msg += f"   ⛔ 손절가: {stop_price:,.0f}원 (-3%)\n\n"

    msg += f"━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"⏰ 진입 시간: 10:00~10:30 권장\n"
    msg += f"💡 급등 후 조정 시 진입 추천\n"

    return msg


def send_telegram(candidates):
    """텔레그램 전송"""
    try:
        from screener.short_term.telegram_notifier import send_telegram_message

        msg = format_telegram_message(candidates)
        send_telegram_message(msg, parse_mode="HTML")
        print("[텔레그램] 전송 완료 ✓")

    except Exception as e:
        print(f"[텔레그램] 전송 실패: {e}")


def run_scan(send_telegram_msg=True):
    """
    10시 스캔 실행
    """
    print("\n" + "=" * 80)
    print("🔥 당일 매매 10시 스캔 시작")
    print(f"⏰ 실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 설정 로드
    config = load_config()
    min_score = config.get("filters", {}).get("min_score", 60.0)

    # 스캔 실행
    candidates = scan_1h_patterns()

    # 필터링
    filtered = [c for c in candidates if c.get("score", 0) >= min_score]
    filtered = sorted(filtered, key=lambda x: x.get("score", 0), reverse=True)[:5]

    # 결과 출력
    print(f"\n[결과] {len(filtered)}개 종목 선정")

    if filtered:
        print(f"\n{'='*80}")
        print(f"TOP 5")
        print(f"{'='*80}")
        print(f"{'순위':<4} {'종목명':<20} {'점수':<8} {'1시간 등락':<12} {'거래량':<10}")
        print("-" * 80)

        for idx, cand in enumerate(filtered, 1):
            name = cand.get("name", "")[:18]
            score = cand.get("score", 0)
            change = cand.get("change_1h", 0)
            volume = cand.get("volume_ratio", 0)
            print(f"{idx:<4} {name:<20} {score:>7.0f} {change:>+10.1f}% {volume:>8.1f}배")

        # 텔레그램 전송
        if send_telegram_msg:
            print(f"\n[텔레그램] 전송 중...")
            send_telegram(filtered)
    else:
        print(f"\n⚠️ 조건 충족 종목 없음 (최소 {min_score}점)")

    print(f"\n{'='*80}")
    print("당일 매매 10시 스캔 완료")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    print("⚠️  주의: 이 모듈은 아직 개발 중입니다")
    print("⚠️  실시간 데이터 수집 로직이 구현되지 않았습니다")
    print("⚠️  증권사 API 연동 또는 크롤링 추가 필요\n")

    import argparse

    parser = argparse.ArgumentParser(description="당일 매매 10시 스캔")
    parser.add_argument(
        "--force",
        action="store_true",
        help="경고 무시하고 강제 실행"
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="텔레그램 전송 안 함"
    )

    args = parser.parse_args()

    if args.force:
        run_scan(send_telegram_msg=not args.no_telegram)
    else:
        print("실행하려면 --force 옵션을 사용하세요:")
        print("python strategies/intraday/run_scan_10am.py --force")
