# 텔레그램 알림 설정 가이드

단기 투자 결과를 텔레그램으로 자동 전송하는 방법

---

## 1. 텔레그램 봇 만들기

### 1-1. BotFather에서 봇 생성

1. 텔레그램에서 **@BotFather** 검색
2. 대화 시작 → `/start`
3. `/newbot` 명령어 입력
4. 봇 이름 입력 (예: `My Trading Bot`)
5. 봇 유저네임 입력 (예: `my_trading_bot`)
   - 반드시 `bot`으로 끝나야 함
6. **토큰 받기** → 저장해두기

```
Done! Congratulations on your new bot.
You will find it at t.me/my_trading_bot.
You can now add a description, about section and profile picture...

Use this token to access the HTTP API:
1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345678
                    ↑↑↑
            이 토큰을 복사하세요!
```

---

## 2. Chat ID 확인하기

### 2-1. 봇과 대화 시작

1. 받은 링크 클릭 (예: `t.me/my_trading_bot`)
2. **Start** 버튼 클릭
3. 아무 메시지나 입력 (예: `/start` 또는 `안녕`)

### 2-2. Chat ID 조회

브라우저에서 다음 URL 접속:

```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

**예시:**
```
https://api.telegram.org/bot1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345678/getUpdates
```

**응답 예시:**
```json
{
  "ok": true,
  "result": [
    {
      "update_id": 123456789,
      "message": {
        "message_id": 1,
        "from": {
          "id": 987654321,  ← 이게 당신의 Chat ID!
          "is_bot": false,
          "first_name": "홍길동"
        },
        "chat": {
          "id": 987654321,  ← 여기도 Chat ID
          "first_name": "홍길동",
          "type": "private"
        },
        "date": 1719212345,
        "text": "/start"
      }
    }
  ]
}
```

`"chat": {"id": 987654321}` ← 이 숫자를 복사!

---

## 3. 환경변수 설정

### 3-1. .env 파일 수정

`C:\autotrade\.env` 파일 열어서 추가:

```bash
# 텔레그램 알림
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345678
TELEGRAM_CHAT_ID=987654321
```

### 3-2. symposium/.env에도 추가 (선택)

```bash
cd symposium
cp .env.example .env
# .env 파일 열어서 동일하게 추가
```

---

## 4. 테스트

### 4-1. 테스트 스크립트 실행

```bash
cd C:\autotrade\symposium\screener\short_term
python telegram_notifier.py
```

**성공 시:**
```
[텔레그램] 알림 활성화 (chat_id: 98765432...)
텔레그램 테스트 전송...
[텔레그램] 메시지 전송 성공
```

텔레그램에 메시지가 도착하는지 확인!

### 4-2. 실제 사용

```bash
# 기본 (TOP 10 전송)
python run_short_term.py

# 간단 요약만 (TOP 5)
python run_short_term.py --compact

# 텔레그램 전송 안함
python run_short_term.py --no-telegram
```

---

## 5. 메시지 예시

### 5-1. 기본 메시지 (TOP 10)

```
🎯 단기 투자 종목 선정
📅 2026-06-24 09:05
📊 총 47개 중 TOP 10
🎚️ 최소 55점

━━━━━━━━━━━━━━━━━━━━

🥇 이오테크닉스
039030.KQ
💯 점수: 94.0점
  진입35 · 테마23 · 수급15 · 실적13
📉 1주: -3.5% · RSI: 38

🥈 한화에어로스페이스
012450.KS
💯 점수: 78.5점
  진입32 · 테마25 · 수급10 · 실적9
📉 1주: -5.2% · RSI: 42

...

━━━━━━━━━━━━━━━━━━━━

🔍 상세 신호 TOP 3

[1] 이오테크닉스
⏰ RSI38 과매도반등, 볼린저하단반등, 5일선골든크로스
🎯 광통신 지속성 85% + 당일HOT
💰 외국인+기관 3일연속순매수

...

━━━━━━━━━━━━━━━━━━━━
⚠️ 보유기간: 3~7일
🛑 손절: -5~7%
🎯 목표: +15~25%
```

### 5-2. 간단 요약 (--compact)

```
🎯 단기 TOP 5 (06/24 09:05)

1. 이오테크닉스 039030.KQ
   94점 · RSI38 · 1주-3.5% 📉
2. 한화에어로 012450.KS
   79점 · RSI42 · 1주-5.2% 📉
3. 캐치업종목C 456789.KQ
   76점 · RSI35 · 1주-8.1% 📉
...

⚠️ 보유 3~7일 · 손절 -5%
```

---

## 6. 고급 사용

### 6-1. 그룹 채팅에 전송

1. 그룹 채팅 생성
2. 봇을 그룹에 초대
3. 그룹에서 봇에게 메시지 보내기
4. `/getUpdates`에서 그룹 Chat ID 확인 (음수일 수 있음)
5. `.env`의 `TELEGRAM_CHAT_ID`를 그룹 ID로 변경

### 6-2. 매일 자동 실행 (Windows 작업 스케줄러)

**배치 파일 생성** (`run_short_term_daily.bat`):
```batch
@echo off
cd C:\autotrade
python run_short_term.py --compact
```

**작업 스케줄러 등록:**
1. `작업 스케줄러` 실행
2. `작업 만들기`
3. 트리거: 매일 오전 9시
4. 작업: `run_short_term_daily.bat` 실행

### 6-3. 개별 알림 (추가 개발 가능)

```python
from short_term.telegram_notifier import TelegramNotifier

notifier = TelegramNotifier()

# 과열 신호 알림
notifier.send_alert(
    ticker="039030.KQ",
    name="이오테크닉스",
    signal="⚠️ RSI 75 과열 → 익절 고려",
    score=94.0
)

# 손절 알림
notifier.send_alert(
    ticker="123456.KS",
    name="손실종목",
    signal="🛑 -7% 손절 라인 도달",
    score=None
)
```

---

## 7. 트러블슈팅

### 7-1. "텔레그램 설정 없음" 오류

**원인:** `.env` 파일에 토큰/Chat ID가 없음

**해결:**
1. `.env` 파일 존재 확인
2. `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 올바른지 확인
3. 따옴표 없이 입력했는지 확인

### 7-2. "401 Unauthorized" 오류

**원인:** 봇 토큰이 잘못됨

**해결:**
1. BotFather에서 토큰 재확인
2. 복사할 때 공백/개행 포함 안됐는지 확인

### 7-3. "400 Bad Request: chat not found"

**원인:** Chat ID가 잘못됨

**해결:**
1. 봇과 대화를 먼저 시작했는지 확인 (Start 버튼)
2. `/getUpdates`에서 Chat ID 재확인
3. 음수 ID인 경우 `-` 빠뜨리지 않았는지 확인

### 7-4. 메시지 형식 깨짐

**원인:** Markdown 이스케이프 문제

**해결:**
- 자동으로 `\` 처리됨
- 문제 발생 시 `telegram_notifier.py`의 `parse_mode="HTML"`로 변경

---

## 8. 보안 주의사항

⚠️ **중요:**
- 봇 토큰은 절대 공개하지 마세요
- `.env` 파일을 git에 커밋하지 마세요 (`.gitignore`에 추가됨)
- 토큰 유출 시 BotFather에서 `/revoke` 명령으로 재발급

---

## 9. 참고 링크

- [텔레그램 Bot API 문서](https://core.telegram.org/bots/api)
- [BotFather 가이드](https://core.telegram.org/bots#6-botfather)
- [python-telegram-bot 라이브러리](https://github.com/python-telegram-bot/python-telegram-bot) (고급 기능)

---

설정 완료 후:
```bash
python run_short_term.py
```

텔레그램으로 결과가 자동 전송됩니다! 🎉
