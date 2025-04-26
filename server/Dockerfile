ARG CUDA_VERSION=12.4.1
ARG UBUNTU_VERSION=22.04

# 使用官方 NVIDIA CUDA 映像檔 (預設使用CUDA 12.4.1, cuDNN 9, Ubuntu 22.04)
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-ubuntu${UBUNTU_VERSION}

# 設定環境變數
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV TZ=Asia/Taipei
# 設定 DEBIAN_FRONTEND 為非互動模式，避免 apt 安裝過程中斷
ENV DEBIAN_FRONTEND=noninteractive

# 安裝基礎工具和 Python 3.12 (使用 deadsnakes PPA)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        gnupg \
        curl \
        ffmpeg && \
    # 添加 deadsnakes PPA 以安裝較新的 Python 版本
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && \
    # 安裝 Python 3.12, venv, dev
    # *** 移除 python3.12-distutils ***
    # 因為 distutils 在 Python 3.12 中已被移除，其功能由 setuptools 提供
    apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3.12-dev && \
    # 使用 ensurepip 為 python3.12 安裝/升級 pip 和 setuptools
    # setuptools 會處理好 distutils 的需求
    python3.12 -m ensurepip --upgrade && \
    # 清理 apt 快取
    rm -rf /var/lib/apt/lists/*

# 設定工作目錄
WORKDIR /app

# 先複製 requirements.txt 以利用 Docker 的層快取
COPY requirements.txt .

# 使用 python3.12 的 pip 安裝 Python 依賴
# 現在應該可以正常工作了
RUN python3.12 -m pip install --no-cache-dir -r requirements.txt

# 建立模型目錄 (好習慣)
RUN mkdir -p /app/models

# 複製應用程式碼
COPY ./app /app/app

# 開放 port
EXPOSE 8000

# 設定預設啟動命令 (使用 uvicorn)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]