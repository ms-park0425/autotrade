# 🤖 AutoTrade - 3 Strategy Trading System

**2가지 시간대별 전략**으로 효율적인 투자

```
📊 Long Term  → 07:00 전날 데이터로 분석 (몇 개월~수년)
🔥 Intraday   → 10:00 당일 9~10시 차트 분석 (당일)
```

---

## 🚀 Quick Start

```bash
# 장기 투자 - 아침 7:00 실행 (전날 데이터)
python strategies/long_term/run_scan.py

# 당일 매매 - 10:00 실행 (9~10시 차트) [개발 중]
python strategies/intraday/run_scan_10am.py --force
```

📖 **[빠른 시작 가이드](QUICK_START.md)**

---

## 📊 전략 비교

| 전략 | 실행 시간 | 분석 데이터 | 보유기간 | 주요 지표 |
|-----|----------|------------|---------|----------|
| **Long Term** | 07:00 | 전날까지 | 3개월~수년 | 펀더멘털, 구조적 테마, 밸류에이션 |
| **Intraday** | 10:00 | 당일 9~10시 차트 | 당일 | 차트 패턴, 호가창, 거래량 폭증 |

---

## 📁 프로젝트 구조

```
autotrade/
├── strategies/              # 2개 독립 전략 (완전 통합)
│   ├── long_term/          # 📊 장기 투자
│   │   ├── run_scan.py     # 실행 스크립트
│   │   ├── engine/         # 코어 엔진 (pipeline, scorer, universe 등)
│   │   ├── config/         # 전략 설정
│   │   ├── data/           # 결과 저장
│   │   └── README.md       # 상세 가이드
│   │
│   └── intraday/           # 🔥 당일 매매 (개발 중)
│       ├── run_monitor.py  # 실시간 모니터링
│       ├── run_scan_10am.py # 10시 스캔
│       ├── config/
│       ├── data/
│       └── README.md
│
├── archive/                # 기존 파일 백업 (symposium 포함)
│
├── QUICK_START.md          # 빠른 시작
└── README.md               # 이 파일
```

✨ **깔끔하게 정리됨!** 모든 로직이 strategies/ 안에 통합되었습니다.

---

## 1️⃣ Long Term (장기 투자)

### 특징
- 🎯 목표: 앞으로 몇 개월~수년간 오를 종목
- 📊 기준: 펀더멘털(40) + 테마(30) + 기술(20) + 수급(10)
- ⏰ 실행: 주 1회 (일요일 20:00)
- 💎 선정: TOP 20

### 핵심 지표
- ✅ 구조적 테마 (AI반도체, 2차전지, 방위산업 등)
- ✅ EPS 성장률, 실적 서프라이즈
- ✅ PEG Ratio, Forward PE
- ✅ 볼린저밴드 진입점, RSI 과매도
- ✅ 기관/외국인 3개월 누적 매집

### 사용법
```bash
# 즉시 실행
python strategies/long_term/run_scan.py --now

# 자동 스케줄 (매주 일요일 20:00)
python strategies/long_term/run_scan.py --schedule

# 커스텀
python strategies/long_term/run_scan.py --now --top 30 --score 65
```

📖 **[상세 가이드](strategies/long_term/README.md)**

---

## 2️⃣ Intraday (당일 매매) - 개발 중

### 특징
- 🎯 목표: 9~10시 차트로 당일 매매
- 📊 기준: 차트(40) + 거래량(30) + 호가창(20) + 테마(10)
- ⏰ 실행: 10:00 정각 (9~10시 차트 분석)
- 💎 선정: TOP 5

### 핵심 지표
- ✅ 9:00~10:00 급등 패턴 (조정 없이 상승)
- ✅ 거래량 5배 이상 폭증
- ✅ 호가창 매수 70% 우위
- ✅ 당일 신규 테마 출현

### 사용법

```bash
# 10:00 정각 실행 (9~10시 차트 분석)
python strategies/intraday/run_scan_10am.py --force
```

⚠️ **주의**: 증권사 API 연동 필요 (아직 미구현)

📖 **[상세 가이드](strategies/intraday/README.md)**

---

## ⚙️ 설정

### 1. 텔레그램 봇 설정

```bash
# .env 파일 생성
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 2. 전략별 설정 (선택)

각 전략은 독립된 설정 파일:
```
strategies/long_term/config/config.json
strategies/swing/config/config.json
strategies/intraday/config/config.json
```

### 3. 자동 실행 (Windows 작업 스케줄러)

```
작업 1: 장기 투자
  - 트리거: 매일 07:00
  - 작업: python C:\autotrade\strategies\long_term\run_scan.py

작업 2: 당일 매매 (선택)
  - 트리거: 매일 10:00
  - 작업: python C:\autotrade\strategies\intraday\run_scan_10am.py
```

---

## 🎯 전략 선택 가이드

### 직장인 (시간 부족)
```
✅ Long Term (필수)
❌ Intraday (부적합)

이유: 매일 아침 7시 1회만 확인
```

### 전업 트레이더
```
✅ Long Term (기본)
✅ Intraday (추가)

이유: 아침 + 10시 2회 확인
```

---

## 📱 텔레그램 알림 예시

### Long Term (매일 7:00)
```
📊 장기 투자 포트폴리오
📅 2026-06-25 07:00

💎 이번 주 TOP 20

1. 삼성전자 (005930)
   점수: 82.5 = 펀더멘털38 + 테마28 + 기술15 + 수급8
   
   📊 펀더멘털: EPS +25% YoY, 서프라이즈 +12%
   🔥 테마: AI반도체 (구조적)
   📈 기술적: 볼린저 하단, RSI 38
   💰 수급: 3개월 기관 +1.2조

...
```

### Intraday (10:00)
```
🔥 당일 매매 TOP 5 (10:00)
📅 2026-06-25

1. 삼성전자 (005930)
   현재가: 54,200원 (+6.2%)
   점수: 78점
   
   📊 차트 (38점): 9~10시 조정없이 상승, 5분봉 연속양봉
   📈 거래량 (25점): 전일 대비 4.5배 폭증
   💰 호가창 (15점): 매수 75% 우위
   
   ⚡ 진입: 현재가 or 조정 시
   🎯 목표: 57,000원 (+5%)
   ⛔ 손절: 52,500원 (-3%)

...
```

---

## 🔧 기술 스택

- **언어**: Python 3.8+
- **데이터**: yfinance, pandas, FinanceDataReader
- **분석**: pandas, numpy
- **알림**: python-telegram-bot
- **스케줄**: schedule (장기), cron/Windows 작업 스케줄러

---

## 📊 백테스트 (예정)

```bash
# 장기 투자 (3년)
python strategies/long_term/backtest.py --period 3y

# 스윙 투자 (6개월)
python strategies/swing/backtest.py --period 6m

# 당일 매매 (1개월)
python strategies/intraday/backtest.py --period 1m
```

**측정 지표**:
- 승률
- 평균 수익률
- 샤프 비율
- 최대 낙폭 (MDD)

---

## ⚠️ 면책 조항

### 투자 책임
- 이 시스템은 **참고용**입니다
- 최종 투자 판단은 **본인**이 하세요
- 손실 가능성 항상 존재

### 시스템 한계
- 뉴스/공시는 수동 확인 필요
- 시장 급변 시 대응 제한적
- 백테스트 결과 ≠ 미래 수익
- 갑작스런 악재 감지 불가

### 리스크 관리 필수
- ✅ 손절 규칙 반드시 지키기
- ✅ 분산 투자 (1종목 최대 10~20%)
- ✅ 적정 레버리지 유지
- ✅ 생활비 제외한 여유 자금만

---

## 🤝 기여

이슈, PR 환영합니다!

### 개발 로드맵
- [ ] Intraday 실시간 데이터 수집 (증권사 API)
- [ ] 백테스트 자동화
- [ ] 웹 대시보드
- [ ] 뉴스/공시 자동 수집
- [ ] AI 예측 모델 추가

---

## 📞 지원

- 📖 [Quick Start Guide](QUICK_START.md)
- 📖 전략별 상세 가이드
  - [Long Term](strategies/long_term/README.md)
  - [Swing](strategies/swing/README.md)
  - [Intraday](strategies/intraday/README.md)

---

## 📄 라이선스

MIT License

---

## 🙏 감사의 말

이 프로젝트는 다음 오픈소스를 활용합니다:
- yfinance
- FinanceDataReader
- pandas
- python-telegram-bot
