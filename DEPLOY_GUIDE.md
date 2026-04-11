# FLUX Dev + NSFW MASTER FLUX + PuLID 完整部署指南

## 架构概览

```
FLUX Dev FP16 (基座) + seqing_master LoRA (NSFW) + PuLID Enhanced (人脸一致性)
                                    |
                              ComfyUI 0.18.x
                                    |
                         H100 80GB / 任何 24GB+ GPU
```

## 前置要求

- GPU: 24GB+ VRAM (推荐 40GB+, FP16 需要约 30GB)
- 磁盘: 约 60GB
- Python 3.11-3.13
- CUDA 12.x
- Civitai API Token (下载 LoRA 用)

---

## 第一步: 安装 ComfyUI

```bash
cd ~
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 第二步: 下载模型

### 基座模型 (FLUX Dev FP16, GGUF 格式, ~23GB)
```bash
cd ~/ComfyUI/models/diffusion_models
wget 'https://huggingface.co/city96/FLUX.1-dev-gguf/resolve/main/flux1-dev-F16.gguf'
```

> **坑: FLUX Dev safetensors 版本需要 HuggingFace 登录接受协议, GGUF 版本免登录且质量无损**

### CLIP 文本编码器 (~9.5GB)
```bash
cd ~/ComfyUI/models/clip
wget 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors'
wget 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors'
```

> **坑: FLUX 需要 DualCLIPLoader 加载 t5xxl + clip_l, type 选 "flux"**

### VAE (~320MB)
```bash
cd ~/ComfyUI/models/vae
wget 'https://huggingface.co/ffxvs/vae-flux/resolve/main/ae.safetensors'
```

> **坑: 官方 BFL 源和 Comfy-Org 源都需要登录, 用 ffxvs 社区镜像**

### NSFW MASTER FLUX LoRA (~165MB)
```bash
cd ~/ComfyUI/models/loras
wget 'https://civitai.com/api/download/models/746602?token=YOUR_CIVITAI_TOKEN' \
  -O seqing_master.safetensors
```

> Civitai model ID: 667086, version: v1.0
> 推荐 LoRA weight: 0.8 (范围 0.7-0.9)

### PuLID 人脸一致性模型 (~1.1GB)
```bash
mkdir -p ~/ComfyUI/models/pulid
cd ~/ComfyUI/models/pulid
wget 'https://huggingface.co/guozinan/PuLID/resolve/main/pulid_flux_v0.9.1.safetensors'
```

### InsightFace 人脸检测 (~360MB)
```bash
mkdir -p ~/ComfyUI/models/insightface/models/antelopev2
cd ~/ComfyUI/models/insightface/models/antelopev2
wget 'https://huggingface.co/MonsterMMORPG/tools/resolve/main/antelopev2.zip'
unzip antelopev2.zip && mv antelopev2/* . && rmdir antelopev2 && rm antelopev2.zip
```

### Upscale 模型 (可选, ~64MB)
```bash
cd ~/ComfyUI/models/upscale_models
wget 'https://huggingface.co/ai-forever/Real-ESRGAN/resolve/main/RealESRGAN_x2.pth'
```

## 第三步: 安装 Custom Nodes

### ComfyUI-GGUF (加载 GGUF 格式模型)
```bash
cd ~/ComfyUI/custom_nodes
git clone https://github.com/city96/ComfyUI-GGUF.git
source ~/ComfyUI/venv/bin/activate
pip install -r ComfyUI-GGUF/requirements.txt
```

### PuLID-Flux-Enhanced (人脸一致性)
```bash
cd ~/ComfyUI/custom_nodes
git clone https://github.com/sipie800/ComfyUI-PuLID-Flux-Enhanced.git
source ~/ComfyUI/venv/bin/activate
pip install -r ComfyUI-PuLID-Flux-Enhanced/requirements.txt
pip install facenet-pytorch --no-deps
```

> **大坑: PuLID 节点版本兼容性**
> - `balazik/ComfyUI-PuLID-Flux` — 和 ComfyUI 0.18+ 不兼容 (forward_orig signature 报错)
> - `lldacing/ComfyUI_PuLID_Flux_ll` — 部分兼容, 需要 FixPulidFluxPatch 节点但仍有 KeyError
> - `sipie800/ComfyUI-PuLID-Flux-Enhanced` — **唯一正常工作的版本** (有 fix forward signature commit)

> **坑: CHROMA 模型和所有 PuLID 节点都不兼容** (架构修改导致 attn_mask 参数报错)

## 第四步: 启动 ComfyUI

```bash
cd ~/ComfyUI
source venv/bin/activate

# 指定 GPU (例如 GPU 1), 只监听本地
CUDA_VISIBLE_DEVICES=1 python main.py --listen 127.0.0.1 --port 8189
```

### 后台运行
```bash
CUDA_VISIBLE_DEVICES=1 nohup python main.py --listen 127.0.0.1 --port 8189 > /tmp/comfyui.log 2>&1 &
```

### 本地访问 (SSH 端口转发)
```bash
# 在本地 ~/.ssh/config 中添加:
# Host H100
#   LocalForward 8189 localhost:8189

ssh H100
# 然后浏览器打开 http://localhost:8189
```

## 第五步: 导入工作流

把 `FLUX_Seqing_PuLID_workflow.json` 拖入浏览器即可使用。

---

## 工作流节点链路

```
UnetLoaderGGUF (flux1-dev-F16.gguf)
  → LoraLoader (seqing_master.safetensors, weight=0.8)
    → ModelSamplingFlux (max_shift=1.15, base_shift=0.5)
      → ApplyPulidFlux (weight=0.9, fusion=mean)
        → BasicGuider
          → SamplerCustomAdvanced (euler, 30 steps)
            → VAEDecode
              → SaveImage
              → [可选] UpscaleModelLoader + ImageUpscaleWithModel → SaveImage HD

DualCLIPLoader (t5xxl_fp16 + clip_l, type=flux)
  → LoraLoader (shared)
    → CLIPTextEncode
      → FluxGuidance (3.5)
        → BasicGuider
```

## 推荐参数

| 参数 | 推荐值 | 范围 |
|------|--------|------|
| LoRA strength | 0.8 | 0.5-1.0 |
| PuLID weight | 0.9 | 0.6-1.2 |
| PuLID end_at | 1.0 | 0.7-1.0 |
| FluxGuidance | 3.5 | 2.5-5.0 |
| Steps | 30 | 20-30 |
| Sampler | euler | - |
| Resolution | 1024x1024 | 最大 1536x1536 |

## 关键文件结构

```
~/ComfyUI/
├── models/
│   ├── diffusion_models/
│   │   └── flux1-dev-F16.gguf          (23G, FP16 基座)
│   ├── clip/
│   │   ├── clip_l.safetensors          (235M)
│   │   └── t5xxl_fp16.safetensors      (9.2G)
│   ├── vae/
│   │   └── ae.safetensors              (320M)
│   ├── loras/
│   │   └── seqing_master.safetensors   (165M, NSFW MASTER FLUX)
│   ├── pulid/
│   │   └── pulid_flux_v0.9.1.safetensors (1.1G)
│   ├── insightface/models/antelopev2/  (5 个 ONNX)
│   └── upscale_models/
│       └── RealESRGAN_x2.pth           (64M)
├── custom_nodes/
│   ├── ComfyUI-GGUF/
│   └── ComfyUI-PuLID-Flux-Enhanced/
├── input/                               (上传的参考图)
└── output/                              (生成结果)
```

## 安全注意事项

- ComfyUI 用 `--listen 127.0.0.1` 只监听本地, 别人无法访问
- 通过 SSH 端口转发访问
- ComfyUI UI 里"删除"图片只是从界面移除, **磁盘上不会删除**
- 真正删除需要手动 `rm` 对应文件
- input/ 和 output/ 目录权限设为 700
- 生成的敏感图片及时清理: `rm ~/ComfyUI/output/*.png`

## 踩坑记录

1. **FLUX VAE 下载**: 官方源和 Comfy-Org 都要登录, 用 `ffxvs/vae-flux` 镜像
2. **FLUX Dev FP16 下载**: safetensors 要登录, 用 GGUF F16 格式 (city96 镜像), 质量无损
3. **PuLID 兼容性**: 只有 `sipie800/ComfyUI-PuLID-Flux-Enhanced` 兼容 ComfyUI 0.18+
4. **CHROMA vs FLUX Dev**: CHROMA 和 PuLID 不兼容, 人脸一致性必须用标准 FLUX Dev
5. **facenet-pytorch**: 安装时可能 Pillow 冲突, 用 `pip install facenet-pytorch --no-deps`
6. **GGUF 节点**: 用 GGUF 格式需要安装 ComfyUI-GGUF custom node
7. **SSH 端口转发冲突**: LocalForward 8189 如果端口已占用会导致 SSH 连接报 exit 255
