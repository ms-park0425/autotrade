# Archive (아카이브)

## 이 폴더는?

프로젝트 재구성 전 기존 파일들의 백업입니다.

---

## 폴더 구조

```
archive/
├── old_scripts/        # 기존 실행 스크립트
│   ├── run_short_term.py
│   ├── run_morning_premarket.py
│   └── run_daily_morning.py
│
├── old_docs/           # 기존 문서
│   ├── SHORT_TERM_README.md
│   ├── DAILY_MORNING_GUIDE.md
│   └── ...
│
└── backtest_scripts/   # 백테스트 및 분석 스크립트
    ├── backtest_*.py
    ├── analyze_*.py
    ├── verify_*.py
    └── *.csv (결과 파일)
```

---

## 새 구조로 마이그레이션

### 기존 → 신규 매핑

| 기존 파일 | 새 파일 |
|----------|---------|
| `run_short_term.py` | `strategies/swing/run_scan.py` |
| `run_morning_premarket.py` | `strategies/swing/run_premarket.py` |
| `run_daily_morning.py` | `strategies/swing/run_scan.py` (통합) |
| `symposium/run_v2.py` | `strategies/long_term/run_scan.py` |

---

## 복원 방법

필요 시 이 폴더에서 복원 가능:

```bash
# 특정 스크립트 복원
cp archive/old_scripts/run_short_term.py .

# 전체 복원
cp archive/old_scripts/*.py .
cp archive/old_docs/*.md .
```

---

## 삭제 가능 시점

새 구조가 안정화되면 (약 1~2주 후) 이 폴더를 삭제해도 됩니다.

```bash
# 확인 후 삭제
rm -rf archive/
```
