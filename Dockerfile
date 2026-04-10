# FLUX Dev + NSFW MASTER FLUX LoRA + PuLID 容器化部署
# 构建: docker build -t flux-comfyui --build-arg CIVITAI_TOKEN=xxx .
# 运行: docker run --gpus '"device=1"' -p 8189:8189 -v ./output:/app/ComfyUI/output -v ./input:/app/ComfyUI/input flux-comfyui
# Podman: podman build -t flux-comfyui --build-arg CIVITAI_TOKEN=xxx .
#         podman run --device /dev/nvidia1 --device /dev/nvidiactl -p 8189:8189 -v ./output:/app/ComfyUI/output -v ./input:/app/ComfyUI/input flux-comfyui

FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

ARG CIVITAI_TOKEN
ENV DEBIAN_FRONTEND=noninteractive

# System deps
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv git wget unzip \
    libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git && \
    cd ComfyUI && \
    python3 -m venv venv && \
    . venv/bin/activate && \
    pip install --no-cache-dir -r requirements.txt

# Custom Nodes
RUN cd /app/ComfyUI/custom_nodes && \
    git clone https://github.com/city96/ComfyUI-GGUF.git && \
    git clone https://github.com/sipie800/ComfyUI-PuLID-Flux-Enhanced.git && \
    . /app/ComfyUI/venv/bin/activate && \
    pip install --no-cache-dir -r ComfyUI-GGUF/requirements.txt && \
    pip install --no-cache-dir -r ComfyUI-PuLID-Flux-Enhanced/requirements.txt && \
    pip install --no-cache-dir facenet-pytorch --no-deps

# Models - FLUX Dev FP16
RUN cd /app/ComfyUI/models/diffusion_models && \
    wget -q 'https://huggingface.co/city96/FLUX.1-dev-gguf/resolve/main/flux1-dev-F16.gguf'

# Models - CLIP
RUN cd /app/ComfyUI/models/clip && \
    wget -q 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors' && \
    wget -q 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors'

# Models - VAE
RUN cd /app/ComfyUI/models/vae && \
    wget -q 'https://huggingface.co/ffxvs/vae-flux/resolve/main/ae.safetensors'

# Models - Seqing LoRA
RUN cd /app/ComfyUI/models/loras && \
    wget -q "https://civitai.com/api/download/models/746602?token=${CIVITAI_TOKEN}" \
    -O seqing_master.safetensors

# Models - PuLID
RUN mkdir -p /app/ComfyUI/models/pulid && \
    cd /app/ComfyUI/models/pulid && \
    wget -q 'https://huggingface.co/guozinan/PuLID/resolve/main/pulid_flux_v0.9.1.safetensors'

# Models - InsightFace
RUN mkdir -p /app/ComfyUI/models/insightface/models/antelopev2 && \
    cd /app/ComfyUI/models/insightface/models/antelopev2 && \
    wget -q 'https://huggingface.co/MonsterMMORPG/tools/resolve/main/antelopev2.zip' && \
    unzip -o antelopev2.zip && mv antelopev2/* . 2>/dev/null; \
    rmdir antelopev2 2>/dev/null; rm -f antelopev2.zip

# Models - Upscale
RUN cd /app/ComfyUI/models/upscale_models && \
    wget -q 'https://huggingface.co/ai-forever/Real-ESRGAN/resolve/main/RealESRGAN_x2.pth'

# Permissions
RUN chmod 700 /app/ComfyUI/input /app/ComfyUI/output

EXPOSE 8189

WORKDIR /app/ComfyUI

CMD ["/bin/bash", "-c", "source venv/bin/activate && python main.py --listen 0.0.0.0 --port 8189"]
