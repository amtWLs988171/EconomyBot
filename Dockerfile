# 1. 파이썬 3.10 버전을 베이스로 사용
FROM python:3.10-slim

# 2. 컨테이너 내 작업 폴더 설정
WORKDIR /app

# 3. 시스템 의존성 설치 (여기가 중요! 👇)
# VS Code 서버가 설치되려면 curl, wget, procps 같은 도구가 꼭 필요합니다.
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    procps \
    && rm -rf /var/lib/apt/lists/*

# 4. 필요한 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 현재 폴더의 모든 코드를 컨테이너 안으로 복사
COPY . .

# 6. 봇 실행 명령어
CMD ["python", "bot.py"]