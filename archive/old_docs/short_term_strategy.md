# 단기 투자용 Symposium 변형 전략

## 목표
symposium V2의 중장기 스윙 전략을 **단기 (3~10일) 한국 종목 선정**용으로 변형

---

## 핵심 변경사항

### 1. 팩터 가중치 재설계 (100점 만점)

```python
SHORT_TERM_WEIGHTS = {
    "valuation": 10,      # 밸류에이션 (30→10) — 단기에는 저평가보다 모멘텀
    "earnings": 15,       # 실적 (25→15) — 직전 분기 서프라이즈 중심
    "theme": 25,          # 테마 (20→25) — 5~7일 핫테마 집중
    "entry": 35,          # 진입 타이밍 (15→35) — 가장 중요!
    "supply": 15,         # 수급 (10→15) — 3일 연속 순매수 감지
}
```

### 2. 시간 프레임 단축

| 요소 | V2 중장기 | 단기 제안 |
|------|----------|----------|
| 테마 지속성 | 14일 | **5~7일** |
| Peer 수익률 비교 | 3개월 | **1~2주** |
| 수급 추세 | 5일 | **3일** |
| RSI 기준 | 14일 | **9일** (민감도 증가) |
| 이평선 | 20/60일 | **5/20일** |

### 3. 진입 타이밍 팩터 (35점) 상세

#### 매수 신호 (가점)
- **RSI 과매도 반등** (30~40): +10점
- **볼린저밴드 하단 터치 후 반등**: +8점
- **5일선 골든크로스**: +7점
- **1주 급등 후 3~5일 조정** (눌림목): +5점
- **거래량 급증** (20일 평균 2배+): +5점

#### 과열 신호 (감점)
- RSI > 70: -10점
- 3일 연속 상한가 근접 (+25%+): -15점
- 볼린저밴드 상단 2σ 돌파: -8점
- 1주 급등 +30%+: -5점

#### 구현 예시
```python
def calc_entry_timing_short_term(ticker_data):
    score = 8  # 베이스
    
    # RSI (9일)
    rsi_9 = ta_lib.momentum.RSIIndicator(close=ticker_data['Close'], window=9).rsi().iloc[-1]
    if 30 <= rsi_9 <= 40:
        score += 10
    elif rsi_9 > 70:
        score -= 10
    
    # 볼린저밴드
    bb = ta_lib.volatility.BollingerBands(close=ticker_data['Close'], window=20)
    current_price = ticker_data['Close'].iloc[-1]
    if current_price <= bb.bollinger_lband().iloc[-1] * 1.02:  # 하단 근접
        if ticker_data['Close'].iloc[-1] > ticker_data['Close'].iloc[-2]:  # 반등 시작
            score += 8
    elif current_price >= bb.bollinger_hband().iloc[-1] * 0.98:  # 상단 과열
        score -= 8
    
    # 5일/20일 이평선 골든크로스
    ma5 = ticker_data['Close'].rolling(5).mean().iloc[-1]
    ma20 = ticker_data['Close'].rolling(20).mean().iloc[-1]
    ma5_prev = ticker_data['Close'].rolling(5).mean().iloc[-2]
    ma20_prev = ticker_data['Close'].rolling(20).mean().iloc[-2]
    if ma5 > ma20 and ma5_prev <= ma20_prev:
        score += 7
    
    # 거래량 급증
    vol_20d_avg = ticker_data['Volume'].rolling(20).mean().iloc[-1]
    current_vol = ticker_data['Volume'].iloc[-1]
    if current_vol >= vol_20d_avg * 2:
        score += 5
    
    # 눌림목 패턴 (1주 전 고점 대비 3~10% 조정 후 반등)
    ret_1w = (ticker_data['Close'].iloc[-1] / ticker_data['Close'].iloc[-5] - 1) * 100
    ret_1d = (ticker_data['Close'].iloc[-1] / ticker_data['Close'].iloc[-2] - 1) * 100
    if -10 <= ret_1w <= -3 and ret_1d > 1:
        score += 5
    
    # 급등 후 과열 감점
    if ret_1w > 30:
        score -= 5
    
    return max(0, min(35, score))
```

### 4. 수급 팩터 강화 (15점)

```python
def calc_supply_short_term(ticker_kr):
    """네이버 금융 크롤링 — 3일 연속 순매수 감지"""
    score = 0
    
    # 외국인 + 기관 3일 연속 동반 순매수
    if all_consecutive_buy(foreign=3) and all_consecutive_buy(institution=3):
        score = 15
    # 외국인 or 기관 3일 연속
    elif any_consecutive_buy(3):
        score = 10
    # 외국인 + 기관 당일 동반 순매수
    elif today_both_buy():
        score = 8
    
    # 대량거래 + 잔고율 증가 (세력 매집)
    if volume_surge() and inventory_increase():
        score = min(15, score + 3)
    
    # 공매도 비중 감소 (공매도 청산 압력)
    if short_interest_decrease():
        score = min(15, score + 2)
    
    return score
```

### 5. 테마 팩터 단기 최적화 (25점)

#### 변경사항
- **지속성 기준**: 14일 → **5일** (빠른 테마 회전 반영)
- **구조적 판정 약화**: LLM 구조성보다 **당일 등락률 TOP 테마** 우선
- **순환매 감지 강화**: 메타 카테고리 내 선도 테마 교체 시 가점

```python
def calc_theme_score_short_term(ticker, themes, persistence_map, rotation_signals):
    score = 6  # 베이스
    
    # 소속 테마 중 최고 지속성 (5일 기준)
    max_persistence = max([persistence_map.get(t, 0) for t in themes])
    
    if max_persistence >= 80:  # 5일 중 4일 이상 상승
        score = 20
    elif max_persistence >= 60:
        score = 16
    elif max_persistence >= 40:
        score = 12
    
    # 순환매 테마 가산 (선도 테마 교체 감지)
    for signal in rotation_signals:
        if signal['to_theme'] in themes:
            score = min(25, score + 5)
            break
    
    # 당일 등락률 TOP 3 테마 추가 가산
    today_top_themes = get_today_top_3_themes()  # 네이버 263개 테마 당일 등락률
    if any(t in today_top_themes for t in themes):
        score = min(25, score + 3)
    
    return score
```

### 6. 실적 팩터 단기 조정 (15점)

중장기 26E/27E 대신 **직전 분기 실적 서프라이즈** 중심

```python
def calc_earnings_short_term(ticker_info):
    score = 8
    
    # 직전 분기 실적 서프라이즈
    last_earnings_surprise = ticker_info.get('earningsSurprise')  # %
    if last_earnings_surprise:
        if last_earnings_surprise > 20:
            score = 15
        elif last_earnings_surprise > 10:
            score = 13
        elif last_earnings_surprise < -10:
            score = 3
    
    # 다음 실적 발표일 임박 (D-7 이내, 긍정 기대)
    days_to_earnings = ticker_info.get('daysToEarnings')
    if days_to_earnings and days_to_earnings <= 7:
        if last_earnings_surprise and last_earnings_surprise > 0:
            score = min(15, score + 2)  # 연속 서프라이즈 기대
    
    return score
```

### 7. 필터링 조건 변경

| 조건 | V2 중장기 | 단기 제안 |
|------|----------|----------|
| 최소 시총 | 1,000억원 | **500억원** (중소형주 포함) |
| 최소 점수 | 45점 | **55점** (더 엄격) |
| 결과 개수 | TOP 30 | **TOP 10~15** (집중 투자) |
| 유동성 | 필터 없음 | **일평균 거래대금 10억원+** |

---

## 구현 로드맵

### Phase 1: 코어 로직 수정
1. `scorer_short_term.py` 생성 (V2 scorer 복사 후 수정)
2. 팩터별 함수 재구성
   - `calc_entry_timing_short_term()` — 35점
   - `calc_supply_short_term()` — 15점
   - `calc_theme_score_short_term()` — 25점
3. RSI/볼린저/이평선 기간 변경

### Phase 2: 테마 트래커 단기화
1. `theme_tracker.py` → 5일 지속성 모드 추가
2. 당일 등락률 TOP 테마 수집 함수
3. 순환매 감지 민감도 증가

### Phase 3: 유니버스 확장
1. 시총 필터 500억원으로 완화
2. 유동성 필터 추가 (일평균 거래대금)
3. 중소형 성장주 테마 추가 (신재생에너지, 바이오 등)

### Phase 4: 백테스트
1. 과거 6개월 데이터로 시뮬레이션
2. 보유기간별 수익률 분석 (3/5/7/10일)
3. 승률 / 최대낙폭 / 샤프비율 측정

---

## 예상 결과물

```json
{
  "date": "2026-06-24",
  "model": "short_term_kr",
  "top_picks": [
    {
      "rank": 1,
      "ticker": "123456.KS",
      "name": "단기급등주A",
      "score": 78.5,
      "factors": {
        "valuation": 8,
        "earnings": 13,
        "theme": 23,
        "entry": 32,
        "supply": 15
      },
      "signals": [
        "RSI 35 과매도 반등",
        "5일선 골든크로스",
        "외국인+기관 3일 연속 순매수",
        "AI반도체 테마 지속성 80%"
      ],
      "hold_period": "3~7일",
      "target_return": "+15~25%"
    }
  ]
}
```

---

## 주의사항

1. **백테스트 필수**: 단기 전략은 과최적화 위험 높음
2. **슬리피지 고려**: 중소형주는 체결가 불리할 수 있음
3. **손절 규칙**: -5~7% 자동 손절 필수
4. **뉴스 필터**: 악재 발생 종목 즉시 제외
5. **시장 상황**: 약세장에서는 현금 비중 증가

---

## 다음 단계

symposium 코드를 복사해서 위 로직을 구현할까요?
- [ ] `screener/short_term/` 디렉토리 생성
- [ ] `scorer_short_term.py` 작성
- [ ] `theme_tracker` 5일 모드 추가
- [ ] 백테스트 스크립트 작성
