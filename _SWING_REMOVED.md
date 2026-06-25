# ⚠️ Swing 전략 제거됨

## 이유

백테스트 결과 **효과가 없거나 역효과**였습니다:

### ❌ 문제점
- **거래량 급증**: -1.75%p 역효과 (최악)
- **눌림목 패턴**: -0.67%p 역효과
- **섹터 패닉** 필터 없음 (극단적 날 취약)
- **시장 상황** 무시 (KOSPI 급락 날 대응 불가)

### 📊 백테스트 결과
- 평균적인 날: 약간 플러스 (+0.5%p)
- 극단적인 날: 큰 마이너스 (-3~5%)
- 결론: 리스크 대비 보상 낮음

---

## 현재 구조 (2개 전략)

```
strategies/
├── long_term/    # 07:00 - 전날까지 데이터 (펀더멘털)
└── intraday/     # 10:00 - 9~10시 차트 (기술적)
```

---

## Swing 폴더 정리

### 수동 삭제 필요
```
strategies/swing/ 폴더가 잠겨있어 수동 삭제 필요

방법:
1. 에디터/IDE 모두 닫기
2. Windows 탐색기에서 strategies/swing 폴더 삭제
```

### 백업 위치
```
archive/swing/ (나중에 참고 가능)
```

---

## 대안

### 옵션 1: Long Term만 사용 (추천)
```bash
# 매일 아침 7시
python strategies/long_term/run_scan.py

# 검증된 펀더멘털 전략
# 단순하고 안정적
```

### 옵션 2: Long Term + Intraday
```bash
# 07:00 - 장기 투자
python strategies/long_term/run_scan.py

# 10:00 - 당일 매매
python strategies/intraday/run_scan_10am.py

# 전업 트레이더만 권장
```

---

## Swing이 필요하다면?

### 간단한 대안
```
Long Term 결과를 그대로 사용
단지 보유 기간만 1주일로

이유:
- Long Term 점수제가 더 안정적
- 백테스트 검증됨
- Swing 특화 불필요
```

---

## 참고 문서

- `archive/old_docs/BACKTEST_RESULTS.md` - 백테스트 상세
- `archive/old_docs/FINAL_IMPROVEMENTS.md` - 실패 원인 분석
- `archive/swing/` - 전체 코드 백업
