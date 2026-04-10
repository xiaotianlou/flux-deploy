#!/bin/bash
# FLUX Dev + NSFW MASTER FLUX LoRA + PuLID 一键部署脚本
# 用法: CIVITAI_TOKEN=xxx bash deploy.sh [GPU_ID] [PORT]
# 例子: CIVITAI_TOKEN=abc123 bash deploy.sh 1 8189

set -e

GPU_ID=${1:-0}
PORT=${2:-8189}
INSTALL_DIR=~/ComfyUI

if [ -z "$CIVITAI_TOKEN" ]; then
    echo "ERROR: 需要设置 CIVITAI_TOKEN 环境变量"
    echo "用法: CIVITAI_TOKEN=your_token bash deploy.sh [GPU_ID] [PORT]"
    exit 1
fi

echo "=== FLUX 部署开始 ==="
echo "GPU: $GPU_ID, Port: $PORT, Dir: $INSTALL_DIR"

# Step 1: ComfyUI
if [ ! -d "$INSTALL_DIR" ]; then
    echo "[1/7] 安装 ComfyUI..."
    git clone https://github.com/comfyanonymous/ComfyUI.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    echo "[1/7] ComfyUI 已存在, 跳过"
    cd "$INSTALL_DIR"
    source venv/bin/activate
fi

# Step 2: Custom Nodes
echo "[2/7] 安装 Custom Nodes..."
cd "$INSTALL_DIR/custom_nodes"

if [ ! -d "ComfyUI-GGUF" ]; then
    git clone https://github.com/city96/ComfyUI-GGUF.git
    pip install -r ComfyUI-GGUF/requirements.txt
fi

if [ ! -d "ComfyUI-PuLID-Flux-Enhanced" ]; then
    git clone https://github.com/sipie800/ComfyUI-PuLID-Flux-Enhanced.git
    pip install -r ComfyUI-PuLID-Flux-Enhanced/requirements.txt
    pip install facenet-pytorch --no-deps
fi

# Step 3: FLUX Dev FP16
echo "[3/7] 下载 FLUX Dev FP16..."
mkdir -p "$INSTALL_DIR/models/diffusion_models"
cd "$INSTALL_DIR/models/diffusion_models"
[ -f "flux1-dev-F16.gguf" ] || wget -c 'https://huggingface.co/city96/FLUX.1-dev-gguf/resolve/main/flux1-dev-F16.gguf'

# Step 4: CLIP + VAE
echo "[4/7] 下载 CLIP 和 VAE..."
mkdir -p "$INSTALL_DIR/models/clip"
cd "$INSTALL_DIR/models/clip"
[ -f "clip_l.safetensors" ] || wget -c 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors'
[ -f "t5xxl_fp16.safetensors" ] || wget -c 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors'

mkdir -p "$INSTALL_DIR/models/vae"
cd "$INSTALL_DIR/models/vae"
[ -f "ae.safetensors" ] || wget -c 'https://huggingface.co/ffxvs/vae-flux/resolve/main/ae.safetensors'

# Step 5: NSFW MASTER FLUX LoRA
echo "[5/7] 下载 Seqing Master LoRA..."
mkdir -p "$INSTALL_DIR/models/loras"
cd "$INSTALL_DIR/models/loras"
[ -f "seqing_master.safetensors" ] || wget -c "https://civitai.com/api/download/models/746602?token=${CIVITAI_TOKEN}" -O seqing_master.safetensors

# Step 6: PuLID + InsightFace
echo "[6/7] 下载 PuLID 和 InsightFace..."
mkdir -p "$INSTALL_DIR/models/pulid"
cd "$INSTALL_DIR/models/pulid"
[ -f "pulid_flux_v0.9.1.safetensors" ] || wget -c 'https://huggingface.co/guozinan/PuLID/resolve/main/pulid_flux_v0.9.1.safetensors'

mkdir -p "$INSTALL_DIR/models/insightface/models/antelopev2"
cd "$INSTALL_DIR/models/insightface/models/antelopev2"
if [ ! -f "glintr100.onnx" ]; then
    wget -c 'https://huggingface.co/MonsterMMORPG/tools/resolve/main/antelopev2.zip'
    unzip -o antelopev2.zip
    mv antelopev2/* . 2>/dev/null || true
    rmdir antelopev2 2>/dev/null || true
    rm -f antelopev2.zip
fi

# Step 7: Upscale (可选)
echo "[7/7] 下载 Upscale 模型..."
mkdir -p "$INSTALL_DIR/models/upscale_models"
cd "$INSTALL_DIR/models/upscale_models"
[ -f "RealESRGAN_x2.pth" ] || wget -c 'https://huggingface.co/ai-forever/Real-ESRGAN/resolve/main/RealESRGAN_x2.pth'

# 设置权限
chmod 700 "$INSTALL_DIR/input" "$INSTALL_DIR/output" 2>/dev/null || true

echo ""
echo "=== 部署完成 ==="
echo ""
echo "启动命令:"
echo "  cd $INSTALL_DIR && source venv/bin/activate"
echo "  CUDA_VISIBLE_DEVICES=$GPU_ID python main.py --listen 127.0.0.1 --port $PORT"
echo ""
echo "后台启动:"
echo "  CUDA_VISIBLE_DEVICES=$GPU_ID nohup python main.py --listen 127.0.0.1 --port $PORT > /tmp/comfyui.log 2>&1 &"
echo ""
echo "本地访问: ssh -L $PORT:localhost:$PORT YOUR_SERVER"
echo "浏览器打开: http://localhost:$PORT"
