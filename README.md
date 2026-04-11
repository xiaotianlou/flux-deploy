# FLUX AI Photo Generator

A self-hosted AI photo generation web app with face consistency, RSA encryption, and admin controls.

## Features

- **FLUX Dev FP16** — High-quality image generation
- **PuLID** — Face identity preservation from a single reference photo
- **LoRA support** — Pluggable style/content LoRAs with password protection
- **RSA + AES-GCM encryption** — Generated images encrypted on disk, only decryptable with your private key
- **Admin dashboard** — Browser-side decryption, GPU on/off toggle, file management
- **Access control** — Access code, terms of use, LoRA password
- **Face detection** — Rejects uploads without a detectable face
- **Cloudflare Tunnel** — Shareable public link, no port forwarding needed

## Architecture

```
Browser → Cloudflare Tunnel → Web UI (FastAPI :8080) → ComfyUI (:8189) → GPU
                                        ↓
                              Encrypt output → .enc file (RSA+AES-GCM)
                              Delete plaintext PNG + input photo
```

## Quick Start

```bash
# 1. Clone
git clone https://github.com/xiaotianlou/flux-deploy.git
cd flux-deploy

# 2. Deploy (downloads all models ~50GB)
CIVITAI_TOKEN=your_token bash deploy.sh [GPU_ID] [PORT]

# 3. Generate RSA keys
python3 -c "
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
key = rsa.generate_private_key(65537, 4096)
open('private_key.pem','wb').write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
open('public_key.pem','wb').write(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
"
cp public_key.pem ~/ComfyUI/

# 4. Start
cd ~/ComfyUI
source venv/bin/activate
CUDA_VISIBLE_DEVICES=0 python main.py --listen 127.0.0.1 --port 8189 &
ACCESS_CODE=yourcode ADMIN_PASSWORD=yourpassword python app.py --port 8080

# 5. (Optional) Public link
cloudflared tunnel --url http://localhost:8080
```

## Requirements

- **GPU**: 24GB+ VRAM (16GB minimum with fp8)
- **Disk**: ~60GB
- **Python**: 3.11+
- **CUDA**: 12.x

## Models Downloaded by deploy.sh

| Model | Size | Source |
|-------|------|--------|
| FLUX Dev FP16 (GGUF) | 23 GB | HuggingFace |
| T5-XXL FP16 | 9.2 GB | HuggingFace |
| CLIP-L | 235 MB | HuggingFace |
| FLUX VAE | 320 MB | HuggingFace |
| PuLID v0.9.1 | 1.1 GB | HuggingFace |
| InsightFace AntelopeV2 | 360 MB | HuggingFace |
| RealESRGAN x2 | 64 MB | HuggingFace |
| LoRA (from Civitai) | 165 MB | Civitai (token required) |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ACCESS_CODE` | Code required to use the web UI |
| `ADMIN_PASSWORD` | Password for the /admin dashboard |
| `CIVITAI_TOKEN` | API token for downloading Civitai models |

## Decrypting Images

Generated images are encrypted on the server. Only you can decrypt them with your private key.

**Browser (Admin page):**
1. Go to `/admin`, enter admin password
2. Click "Load private_key.pem"
3. Click "Decrypt & View All"

**CLI:**
```bash
python decrypt.py --pull           # Download and decrypt all
python decrypt.py --pull --delete  # Download, decrypt, and clean server
python decrypt.py file.enc         # Decrypt a single file
```

## File Structure

```
flux-deploy/
├── app.py              # Web UI + encryption + admin
├── decrypt.py          # Local decryption tool
├── deploy.sh           # One-click deployment script
├── watchdog.sh         # Service health checker
├── Dockerfile          # Container deployment
├── docker-compose.yml  # Docker Compose config
├── public_key.pem      # RSA public key (encryption only)
├── DEPLOY_GUIDE.md     # Detailed deployment guide with pitfalls
├── DISCLAIMER.md       # Legal disclaimer
├── LICENSE             # MIT License
└── .gitignore          # Excludes private_key.pem, *.enc, decrypted/
```

## Known Pitfalls

See [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md) for the full list. Key ones:

- **PuLID node compatibility**: Only `sipie800/ComfyUI-PuLID-Flux-Enhanced` works with ComfyUI 0.18+
- **FLUX VAE download**: Official sources require login, use `ffxvs/vae-flux` mirror
- **FLUX Dev FP16**: Use GGUF format from `city96` to avoid HuggingFace login
- **CHROMA incompatibility**: CHROMA models do NOT work with PuLID

---

## Legal Disclaimer

**This software is provided "as is", without warranty of any kind.** By using this software, you acknowledge and agree to the following:

- **You are solely responsible** for all content you generate and how you use it.
- **You must comply** with all applicable laws and regulations in your jurisdiction.
- **You must not** use this software to generate images of minors in any inappropriate context.
- **You must not** use this software for harassment, defamation, fraud, impersonation, or any illegal purpose.
- **You must obtain explicit consent** from any individual whose likeness is used as input.
- The developers **do not control, endorse, or take responsibility** for any user-generated content.
- The developers **are not liable** for any damages, losses, or legal consequences arising from the use of this software.
- By using this software, you agree to **indemnify and hold harmless** the developers from any claims arising from your use.

See [DISCLAIMER.md](DISCLAIMER.md) for the full legal disclaimer.

## License

[MIT License](LICENSE)
