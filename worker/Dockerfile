# Build:  docker build -t <your-dockerhub-user>/avatar-studio-worker:latest .
# Push it to Docker Hub, then point a RunPod serverless endpoint at that image
# with a network volume mounted at /runpod-volume (~100 GB) for the weights.
FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-devel

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# InfiniteTalk (inference code; weights come from the network volume at runtime)
RUN git clone --depth 1 https://github.com/MeiGen-AI/InfiniteTalk.git /app/InfiniteTalk
RUN pip install --no-cache-dir xformers==0.0.28 --index-url https://download.pytorch.org/whl/cu121
RUN pip install --no-cache-dir -r /app/InfiniteTalk/requirements.txt

# F5-TTS + worker runtime
RUN pip install --no-cache-dir f5-tts runpod huggingface_hub
ENV INFINITETALK_REPO=/app/InfiniteTalk WEIGHTS_DIR=/runpod-volume/weights

COPY handler.py /app/handler.py
WORKDIR /app
CMD ["python", "-u", "handler.py"]
