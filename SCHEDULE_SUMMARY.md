# ⏰ 실행 스케줄 요약

## 📅 매일 일정

```
07:00 - 📊 Long Term (전날까지 데이터)
10:00 - 🔥 Intraday (당일 9~10시 차트)
```

---

## 1️⃣ Long Term - 매일 07:00

### 자동 실행
```bash
python strategies/long_term/run_scan.py --schedule
```

### Windows 작업 스케줄러
```
이름: AutoTrade_LongTerm
트리거: 매일 07:00
작업: python C:\autotrade\strategies\long_term\run_scan.py
```

### 결과
- TOP 20 종목 선정
- 텔레그램 전송
- `strategies/long_term/data/YYYY-MM-DD.json` 저장

---

## 2️⃣ Intraday - 매일 10:00

### 수동 실행 (개발 중)
```bash
python strategies/intraday/run_scan_10am.py --force
```

### Windows 작업 스케줄러 (나중에)
```
이름: AutoTrade_Intraday
트리거: 매일 10:00
작업: python C:\autotrade\strategies\intraday\run_scan_10am.py
```

### 결과
- TOP 5 종목 선정
- 텔레그램 전송
- `strategies/intraday/data/YYYY-MM-DD.json` 저장

---

## 🔧 설정 방법

### 1. Long Term 자동 실행

#### 옵션 A: Python 스크립트로 (추천)
```bash
# 터미널에서 실행 (백그라운드)
python strategies/long_term/run_scan.py --schedule
```
- 계속 실행되며 매일 07:00에 자동 실행
- Ctrl+C로 중단

#### 옵션 B: Windows 작업 스케줄러
```
1. 작업 스케줄러 열기
2. "기본 작업 만들기"
3. 이름: AutoTrade_LongTerm
4. 트리거: 매일 07:00
5. 작업: 프로그램 시작
   - 프로그램: python
   - 인수: C:\autotrade\strategies\long_term\run_scan.py
   - 시작 위치: C:\autotrade
```

### 2. Intraday (나중에)

현재는 **수동 실행**:
```bash
# 매일 10:00에 수동으로
python strategies/intraday/run_scan_10am.py --force
```

증권사 API 연동 완료 후 자동화 가능

---

## 📱 텔레그램 알림

### Long Term (07:00)
```
📊 장기 투자 포트폴리오
📅 2026-06-25 07:00

💎 오늘의 TOP 20

1. 삼성전자 (005930)
   점수: 82.5 = 펀더멘털38 + 테마28 + 기술15 + 수급8
   
   📊 펀더멘털: EPS +25% YoY
   🔥 테마: AI반도체 (구조적)
   📈 기술적: 볼린저 하단, RSI 38

...
```

### Intraday (10:00)
```
🔥 당일 매매 TOP 5 (10:00)
📅 2026-06-25

1. 삼성전자 (005930)
   현재가: 54,200원 (+6.2%)
   점수: 78점
   
   📊 차트: 9~10시 조정없이 상승
   📈 거래량: 4.5배 폭증
   💰 호가창: 매수 75% 우위

...
```

---

## ⚙️ 환경 변수 (.env)

```bash
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## 🧪 테스트

### Long Term 테스트
```bash
# 즉시 1회 실행 (텔레그램 전송)
python strategies/long_term/run_scan.py

# 텔레그램 없이
python strategies/long_term/run_scan.py --no-telegram
```

### 스케줄러 테스트
```bash
# 1분 뒤 실행되도록 시간 수정 후 테스트
# run_scan.py에서 "07:00" → "현재시간+1분" 변경
python strategies/long_term/run_scan.py --schedule
```

---

## ❓ FAQ

### Q: 매일 실행하는데 Long Term이 맞나요?
A: 네! 매일 체크하되:
- 큰 변화 없으면 기존 종목 유지
- 새로운 강세 종목 발견 시 포트폴리오 조정
- 리밸런싱은 필요할 때만

### Q: 주말에는?
A: 주말에도 실행되지만:
- 증시 데이터는 금요일 종가
- 실질적으로는 평일만 의미 있음

### Q: Intraday는 언제 완성되나요?
A: 증권사 API 연동 후:
- 키움 OpenAPI or 한국투자증권 API
- 실시간 데이터 수집 구현 필요
