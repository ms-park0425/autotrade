# 🔵 GCP 설정 가이드

## 📋 체크리스트

```
☑ GCP 가입 완료
☐ VM 인스턴스 생성
☐ SSH 접속
☐ Python 환경 설정
☐ 코드 업로드
☐ 의존성 설치
☐ 환경 변수 설정
☐ Cron 설정
☐ 테스트
```

---

## 1️⃣ VM 인스턴스 생성

### GCP 콘솔 접속
```
https://console.cloud.google.com/
→ Compute Engine → VM 인스턴스
```

### 새 인스턴스 만들기

**기본 설정:**
```
이름: autotrade
리전: us-west1 (오레곤) ⭐ 무료 티어!
영역: us-west1-b

⚠️ 주의: 한국 서울 리전은 유료입니다!
무료 리전: us-west1, us-central1, us-east1
```

**머신 구성:**
```
시리즈: E2
머신 유형: e2-micro (무료 티어)
  - vCPU 2개
  - 메모리 1GB
```

**부팅 디스크:**
```
운영체제: Ubuntu
버전: Ubuntu 22.04 LTS
디스크 크기: 30GB (무료)
디스크 유형: 표준 영구 디스크
```

**방화벽:**
```
☐ HTTP 트래픽 허용 (불필요)
☐ HTTPS 트래픽 허용 (불필요)
```

**만들기 클릭!**

---

## 2️⃣ SSH 접속

### 브라우저에서 SSH

```
VM 인스턴스 목록에서:
autotrade → SSH → 브라우저 창에서 열기
```

**터미널 창이 열리면 성공!**

---

## 3️⃣ Python 환경 설정

### SSH 터미널에서 실행:

```bash
# 시스템 업데이트
sudo apt update
sudo apt upgrade -y

# Python 설치 (Ubuntu 22.04는 Python 3.10 기본)
sudo apt install python3 python3-pip python3-venv -y

# 버전 확인
python3 --version  # Python 3.10.x 확인
pip3 --version

# 작업 디렉토리 생성
mkdir -p ~/autotrade
cd ~/autotrade
```

---

## 4️⃣ 코드 업로드

### 방법 1: Git 사용 (추천)

```bash
# Git 설치
sudo apt install git -y

# GitHub에 코드 푸시 (로컬 PC에서)
cd C:\autotrade
git init
git add strategies/
git add .env
git commit -m "Initial commit"
git push origin main

# GCP에서 클론
cd ~/autotrade
git clone https://github.com/your-username/autotrade.git .
```

### 방법 2: 파일 직접 업로드

**로컬 PC에서:**
```bash
# gcloud CLI 설치 후
gcloud compute scp --recurse C:\autotrade\strategies autotrade:~/autotrade/
gcloud compute scp C:\autotrade\.env autotrade:~/autotrade/
```

### 방법 3: 수동 복사 (간단, 추천)

**SSH 터미널에서 파일 생성:**

```bash
cd ~/autotrade

# 1. strategies 폴더 구조 생성
mkdir -p strategies/long_term/engine
mkdir -p strategies/long_term/config
mkdir -p strategies/long_term/data
mkdir -p strategies/intraday/config
mkdir -p strategies/intraday/data

# 2. .env 파일 생성
nano .env
```

**`.env` 내용 붙여넣기:**
```
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```
(Ctrl+X → Y → Enter로 저장)

**3. 코드 파일들 복사**
```bash
# long_term/run_scan.py
nano strategies/long_term/run_scan.py
# 로컬 파일 내용 복사 붙여넣기

# engine 파일들도 동일하게
nano strategies/long_term/engine/pipeline.py
nano strategies/long_term/engine/scorer.py
# ... 등등
```

---

## 5️⃣ 의존성 설치

```bash
cd ~/autotrade

# requirements.txt 생성
nano requirements.txt
```

**내용:**
```
pandas>=2.0.0
yfinance>=0.2.28
numpy>=1.24.0
python-telegram-bot>=20.0
schedule>=1.2.0
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
```

**설치:**
```bash
pip3 install -r requirements.txt

# 또는 개별 설치
pip3 install pandas yfinance numpy python-telegram-bot schedule requests beautifulsoup4 lxml
```

---

## 6️⃣ 테스트 실행

```bash
cd ~/autotrade

# Long Term 테스트 (텔레그램 없이)
python3 strategies/long_term/run_scan.py --no-telegram

# 에러 확인
# 성공하면 다음 단계
```

**예상 에러 해결:**

```bash
# ModuleNotFoundError 발생 시
pip3 install [모듈명]

# 경로 에러 발생 시
export PYTHONPATH=/home/your_username/autotrade:$PYTHONPATH
```

---

## 7️⃣ Cron 설정 (자동 실행)

```bash
# crontab 편집
crontab -e

# 처음이면 에디터 선택 (nano 추천: 1번)
```

**추가할 내용:**
```bash
# Long Term - 매일 07:00 KST
0 7 * * * cd /home/your_username/autotrade && /usr/bin/python3 strategies/long_term/run_scan.py >> /home/your_username/autotrade/longterm.log 2>&1

# Intraday - 매일 10:00 KST (나중에)
# 0 10 * * * cd /home/your_username/autotrade && /usr/bin/python3 strategies/intraday/run_scan_10am.py >> /home/your_username/autotrade/intraday.log 2>&1
```

**저장 (Ctrl+X → Y → Enter)**

**시간대 설정 확인:**
```bash
# 현재 시간대 확인
timedatectl

# KST로 변경 (필요 시)
sudo timedatectl set-timezone Asia/Seoul

# 확인
date
```

---

## 8️⃣ 테스트

### 수동 테스트
```bash
cd ~/autotrade

# 텔레그램 포함 전체 테스트
python3 strategies/long_term/run_scan.py

# 텔레그램이 오는지 확인!
```

### Cron 테스트
```bash
# 1분 뒤 실행되도록 임시 설정
crontab -e

# 현재 시간 확인
date

# 예: 현재 14:23이면
# 23 14 * * * cd /home/your_username/autotrade && /usr/bin/python3 strategies/long_term/run_scan.py

# 1분 뒤 로그 확인
tail -f ~/autotrade/longterm.log
```

---

## 9️⃣ 로그 확인

```bash
# 실시간 로그 보기
tail -f ~/autotrade/longterm.log

# 최근 50줄 보기
tail -n 50 ~/autotrade/longterm.log

# 에러만 보기
grep "error\|Error\|ERROR" ~/autotrade/longterm.log
```

---

## 🔧 문제 해결

### 1. 메모리 부족
```bash
# swap 파일 생성 (1GB)
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 영구 설정
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 2. 타임존 문제
```bash
# KST 설정
sudo timedatectl set-timezone Asia/Seoul

# cron 재시작
sudo service cron restart
```

### 3. Python 경로 문제
```bash
# Python 위치 확인
which python3

# crontab에 절대 경로 사용
/usr/bin/python3 strategies/long_term/run_scan.py
```

### 4. 환경 변수 문제
```bash
# .env 파일 위치 확인
ls -la ~/autotrade/.env

# 권한 설정
chmod 600 ~/autotrade/.env
```

---

## 📊 모니터링

### 매일 체크
```bash
# SSH 접속 후
cd ~/autotrade

# 오늘 실행 여부 확인
ls -l strategies/long_term/data/$(date +%Y-%m-%d).json

# 로그 확인
tail -n 20 longterm.log
```

### 주간 체크
```bash
# 최근 7일 데이터 파일 확인
ls -lt strategies/long_term/data/ | head -10

# 디스크 사용량 확인
df -h
```

---

## 💡 유용한 명령어

```bash
# VM 종료 (비용 절약 - 하지만 스케줄 작동 안 함!)
# sudo shutdown -h now

# Python 프로세스 확인
ps aux | grep python

# 메모리 사용량 확인
free -h

# 네트워크 사용량 (대략)
vnstat -d
```

---

## 🎉 완료 체크리스트

```
☑ VM 인스턴스 생성 완료
☑ SSH 접속 성공
☑ Python 환경 설정 완료
☑ 코드 업로드 완료
☑ 의존성 설치 완료
☑ 환경 변수 설정 완료
☑ Cron 설정 완료
☑ 수동 테스트 성공 (텔레그램 수신)
☑ 내일 아침 07:00 자동 실행 대기!
```

---

## 다음 단계

1. **내일 아침 07:05 확인**
   - 텔레그램 메시지 받았는지 체크
   - 로그 확인

2. **1주일 모니터링**
   - 매일 정상 작동 확인
   - 데이터 파일 쌓이는지 확인

3. **Intraday 추가** (나중에)
   - 증권사 API 연동
   - 10:00 스케줄 추가
