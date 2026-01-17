# 1. 파이썬 3.10 버전을 베이스로 사용 (가볍고 안정적인 버전)
FROM python:3.10-slim

# 2. 컨테이너 내 작업 폴더 설정
WORKDIR /app

# 3. 시스템 의존성 설치 (git은 라이브러리 설치 시 필요할 수 있음)
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# 4. 필요한 라이브러리 설치 (캐시를 사용하지 않아 이미지 크기 줄임)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 현재 폴더의 모든 코드를 컨테이너 안으로 복사
COPY . .

# 6. 봇 실행 명령어
CMD ["python", "bot.py"]