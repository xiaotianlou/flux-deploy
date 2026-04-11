#!/bin/bash
# 服务守护脚本 - 检查并自动重启挂掉的服务
# 用法:
#   手动运行: bash watchdog.sh
#   crontab 每5分钟: */5 * * * * bash ~/ComfyUI/watchdog.sh >> /tmp/watchdog.log 2>&1

cd ~/ComfyUI
source venv/bin/activate

# ComfyUI
if ! pgrep -f "python main.py.*--port 8189" > /dev/null; then
    echo "$(date) - ComfyUI down, restarting..."
    CUDA_VISIBLE_DEVICES=1 nohup python main.py --listen 127.0.0.1 --port 8189 > /tmp/comfyui.log 2>&1 &
    sleep 5
    echo "$(date) - ComfyUI started, pid: $!"
fi

# Web UI
if ! pgrep -f "python app.py.*--port 8080" > /dev/null; then
    echo "$(date) - Web UI down, restarting..."
    ACCESS_CODE="${ACCESS_CODE:-1234}" ADMIN_PASSWORD="${ADMIN_PASSWORD:-change_me}" nohup python app.py --port 8080 > /tmp/webui.log 2>&1 &
    sleep 2
    echo "$(date) - Web UI started, pid: $!"
fi

# Cloudflare Tunnel
if ! pgrep -f "cloudflared tunnel" > /dev/null; then
    echo "$(date) - Cloudflare Tunnel down, restarting..."
    nohup cloudflared tunnel --url http://localhost:8080 > /tmp/cloudflared.log 2>&1 &
    sleep 5
    LINK=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/cloudflared.log | tail -1)
    echo "$(date) - Tunnel started: $LINK"
fi
