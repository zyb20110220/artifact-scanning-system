FROM python:3.10-slim

# 初始化
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install torch==2.4.1 torchvision==0.19.1 \
    --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860
CMD ["python", "app/app.py"]