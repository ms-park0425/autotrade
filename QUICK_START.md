# ⚡ Quick Start Guide

## 3개 전략 중 선택

```
📊 Long Term  → 몇 개월~수년 보유 (직장인 추천)
⚡ Swing      → 1주일 단타 (적당한 빈도)
🔥 Intraday   → 당일 매매 (전업 트레이더)
```

---

## 1️⃣ 장기 투자 (Long Term)

### 즉시 실행
```bash
python strategies/long_term/run_scan.py --now
```

### 자동 스케줄 (매주 일요일 20:00)
```bash
python strategies/long_term/run_scan.py --schedule
```

### 커스텀
```bash
# TOP 30, 최소 65점
python strategies/long_term/run_scan.py --now --top 30 --score 65
```

**결과**: 텔레그램으로 받음 (구조적 테마 기반 성장주)

---

## 2️⃣ 스윙 투자 (Swing)

### Step 1: 전날 밤 후보 선정
```bash
python strategies/swing/run_scan.py --top 30 --score 60
```

### Step 2: 당일 아침 프리마켓 스캔
```bash
# 자동 스케줄 (8:00~8:50 매 10분)
python strategies/swing/run_premarket.py --schedule

# 즉시 1회
python strategies/swing/run_premarket.py --now
```

**결과**: 8:50에 텔레그램으로 최종 후보 받음

---

## 3️⃣ 당일 매매 (Intraday) - 개발 중

### 실시간 모니터링
```bash
python strategies/intraday/run_monitor.py --force
```

### 10시 스캔
```bash
python strategies/intraday/run_scan_10am.py --force
```

**주의**: 증권사 API 연동 필요 (아직 미구현)

---

## 추천 워크플로우

### 직장인 (Long + Swing)
```
주말:
  - 일요일 20:00 장기 투자 리밸런싱 (자동)

평일:
  - 전날 23:00 스윙 후보 선정 (자동)
  - 당일 08:00~08:50 프리마켓 스캔 (자동)
  - 당일 09:00 시초가 확인 → 매수
```

### 전업 트레이더 (All)
```
주말:
  - 일요일 20:00 장기 투자 리밸런싱

평일:
  - 08:50 스윙 후보 확인
  - 09:00~10:00 당일 매매 모니터링
  - 14:00 손익 정리
```

---

## 설정

### 텔레그램 봇
```bash
# .env 파일 생성
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 전략별 설정 (선택)
```
strategies/long_term/config/config.json
strategies/swing/config/config.json
strategies/intraday/config/config.json
```

---

## 자동 실행 (Windows)

### 작업 스케줄러 등록

**1. 장기 투자 (주 1회)**
```
이름: AutoTrade 장기 투자
트리거: 매주 일요일 20:00
작업: python C:\autotrade\strategies\long_term\run_scan.py --schedule
```

**2. 스윙 후보 (매일 밤)**
```
이름: AutoTrade 스윙 후보
트리거: 매일 23:00
작업: python C:\autotrade\strategies\swing\run_scan.py
```

**3. 프리마켓 (매일 아침)**
```
이름: AutoTrade 프리마켓
트리거: 매일 07:55
작업: python C:\autotrade\strategies\swing\run_premarket.py --schedule
```

---

## 테스트

### 1. 장기 투자 테스트
```bash
python strategies/long_term/run_scan.py --now --top 5
```
예상: 5개 종목 선정, 텔레그램 수신

### 2. 스윙 투자 테스트
```bash
# 후보 선정
python strategies/swing/run_scan.py --top 10

# 프리마켓 (즉시)
python strategies/swing/run_premarket.py --now
```
예상: 10개 후보 + 프리마켓 점수, 텔레그램 수신

---

## 문제 해결

### "필터 통과 종목 없음"
- 정상 (시장 약세 or 과열)
- 해결: 최소 점수 낮추기 `--score 55`

### "텔레그램 전송 실패"
- `.env` 파일 확인
- 봇 토큰, 채팅 ID 정확한지 체크

### "모듈 없음"
```bash
pip install -r requirements.txt
```

---

## 다음 단계

1. 📖 전략별 상세 가이드
   - `strategies/long_term/README.md`
   - `strategies/swing/README.md`
   - `strategies/intraday/README.md`

2. 🔧 설정 커스터마이징
   - `config/config.json` 수정

3. 📊 백테스트 (예정)
   - 과거 성과 시뮬레이션

---

## 주의사항

⚠️ **투자 책임**
- 이 시스템은 참고용입니다
- 최종 투자 판단은 본인이 하세요
- 손실 가능성 항상 존재

⚠️ **리스크 관리**
- 손절 규칙 반드시 지키기
- 분산 투자 필수
- 적정 레버리지 유지

⚠️ **시스템 한계**
- 뉴스/공시는 수동 확인 필요
- 시장 급변 시 대응 제한적
- 백테스트 결과 ≠ 미래 수익
