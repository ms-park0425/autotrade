#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
당일 매매 실시간 모니터링

실행:
  python strategies/intraday/run_monitor.py

동작:
  - 9:00 장 시작과 동시에 실시간 모니터링
  - 1분마다 급등 종목 스캔
  - 조건 충족 시 즉시 텔레그램 알림
"""

import sys
import os
import io
import time
import json
from datetime import datetime, time as dt_time

# 윈도우 콘솔 인코딩
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# (개발 중 - 아직 미구현)


def is_market_time():
    """장중 시간 확인 (9:00~15:30)"""
    now = datetime.now()
    current_time = now.time()
    return dt_time(9, 0) <= current_time <= dt_time(15, 30)


def load_config():
    """설정 파일 로드"""
    config_path = os.path.join(
        os.path.dirname(__file__), "config", "config.json"
    )
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def scan_intraday_candidates():
    """
    당일 매매 후보 스캔

    TODO: 실제 구현 필요
    - 실시간 체결가 수집
    - 거래량 급증 감지
    - 호가창 분석
    - 차트 패턴 인식
    """
    print(f"[스캔] {datetime.now().strftime('%H:%M:%S')} - 당일 매매 후보 검색 중...")

    # 임시: 더미 데이터
    # 실제로는 yfinance, 증권사 API, 또는 크롤링으로 데이터 수집
    candidates = []

    # TODO: 실제 스캔 로직
    # 1. 전날 스윙 후보 로드
    # 2. 시가총액 상위 200개 + 거래대금 상위 100개
    # 3. 실시간 체결가 수집
    # 4. 급등 조건 체크 (1분 +2% 이상, 거래량 급증)
    # 5. 호가창 분석

    return candidates


def send_alert(candidate):
    """
    급등 알림 전송

    Args:
        candidate: 급등 종목 정보
    """
    try:
        from screener.short_term.telegram_notifier import send_telegram_message

        msg = f"🚨 <b>급등 알림!</b>\n\n"
        msg += f"<b>{candidate.get('name', '')}</b> ({candidate.get('ticker', '')})\n"
        msg += f"📊 현재가: {candidate.get('price', 0):,}원 ({candidate.get('change_pct', 0):+.1f}%)\n"
        msg += f"🕐 시간: {datetime.now().strftime('%H:%M')}\n\n"

        msg += f"<b>차트:</b>\n"
        msg += f"  ├─ {candidate.get('pattern', 'N/A')}\n"
        msg += f"  └─ 거래량 {candidate.get('volume_ratio', 0):.1f}배 폭증\n\n"

        msg += f"<b>호가창:</b>\n"
        msg += f"  ├─ 매수 {candidate.get('bid_ratio', 0):.0f}% 우위\n"
        msg += f"  └─ 매수 잔량 {candidate.get('bid_volume_ratio', 0):.1f}배 많음\n\n"

        if candidate.get('news'):
            msg += f"<b>재료:</b> {candidate.get('news', 'N/A')}\n\n"

        msg += f"⚡ 점수: {candidate.get('score', 0):.0f}점"

        send_telegram_message(msg, parse_mode="HTML")
        print(f"[알림] 텔레그램 전송 완료: {candidate.get('name', '')}")

    except Exception as e:
        print(f"[알림] 텔레그램 전송 실패: {e}")


def run_monitor():
    """
    실시간 모니터링 메인 루프
    """
    config = load_config()
    scan_interval = config.get("monitoring", {}).get("scan_interval_seconds", 60)

    print("=" * 80)
    print("🔥 당일 매매 실시간 모니터링 시작")
    print("=" * 80)
    print(f"시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"스캔 간격: {scan_interval}초")
    print(f"알림 조건: 1분 +2% 이상, 거래량 급증")
    print("\n대기 중... (Ctrl+C로 종료)")
    print("=" * 80)

    # 장 시작 대기
    while not is_market_time():
        now = datetime.now()
        if now.time() < dt_time(9, 0):
            wait_seconds = (datetime.combine(now.date(), dt_time(9, 0)) - now).total_seconds()
            print(f"[대기] 09:00까지 {int(wait_seconds)}초 남음...")
            time.sleep(min(60, wait_seconds))
        else:
            print("[종료] 장 마감 시간 경과")
            return

    print(f"\n[시작] 09:00 장 시작 - 모니터링 개시")

    alerted_tickers = set()  # 중복 알림 방지

    try:
        while is_market_time():
            candidates = scan_intraday_candidates()

            for candidate in candidates:
                ticker = candidate.get("ticker", "")
                if ticker not in alerted_tickers:
                    send_alert(candidate)
                    alerted_tickers.add(ticker)

            time.sleep(scan_interval)

    except KeyboardInterrupt:
        print("\n\n[중단] 사용자가 모니터링을 중단했습니다")

    print("\n[종료] 당일 매매 모니터링 종료")


if __name__ == "__main__":
    print("⚠️  주의: 이 모듈은 아직 개발 중입니다")
    print("⚠️  실시간 데이터 수집 로직이 구현되지 않았습니다")
    print("⚠️  증권사 API 연동 또는 크롤링 추가 필요\n")

    import argparse

    parser = argparse.ArgumentParser(description="당일 매매 실시간 모니터링")
    parser.add_argument(
        "--force",
        action="store_true",
        help="경고 무시하고 강제 실행"
    )

    args = parser.parse_args()

    if args.force:
        run_monitor()
    else:
        print("실행하려면 --force 옵션을 사용하세요:")
        print("python strategies/intraday/run_monitor.py --force")
