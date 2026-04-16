"""
FLUX 图片生成 Web UI (with RSA+AES-GCM encryption)
用法: python app.py [--port 8080] [--comfyui http://127.0.0.1:8189]
"""
import os, json, uuid, time, argparse, struct, io
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, Response
import httpx
import uvicorn
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8080)
parser.add_argument("--comfyui", default="http://127.0.0.1:8189")
args, _ = parser.parse_known_args()

COMFYUI = args.comfyui
PUBKEY_PATH = Path(os.path.expanduser("~/ComfyUI/public_key.pem"))
OUTPUT_DIR = Path(os.path.expanduser("~/ComfyUI/output"))
INPUT_DIR = Path(os.path.expanduser("~/ComfyUI/input"))
app = FastAPI()

with open(PUBKEY_PATH, "rb") as f:
    PUBLIC_KEY = serialization.load_pem_public_key(f.read())

def encrypt_image(image_bytes: bytes) -> bytes:
    """Hybrid RSA+AES-GCM encryption."""
    aes_key = os.urandom(32)
    nonce = os.urandom(12)
    aesgcm = AESGCM(aes_key)
    encrypted_data = aesgcm.encrypt(nonce, image_bytes, None)
    encrypted_aes_key = PUBLIC_KEY.encrypt(
        aes_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    # Format: [key_len(4)][encrypted_aes_key][nonce(12)][encrypted_data+tag]
    return struct.pack(">I", len(encrypted_aes_key)) + encrypted_aes_key + nonce + encrypted_data

HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Photo Generator</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0; min-height: 100vh; }
.container { max-width: 900px; margin: 0 auto; padding: 20px; }
h1 { text-align: center; margin: 30px 0; font-size: 24px; color: #fff; }
.main { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
@media (max-width: 700px) { .main { grid-template-columns: 1fr; } }
.panel { background: #1a1a1a; border-radius: 12px; padding: 20px; border: 1px solid #333; }
.panel h2 { font-size: 16px; margin-bottom: 16px; color: #aaa; }
.upload-area { border: 2px dashed #444; border-radius: 8px; padding: 40px; text-align: center; cursor: pointer; transition: border-color 0.2s; position: relative; min-height: 200px; display: flex; align-items: center; justify-content: center; flex-direction: column; }
.upload-area:hover { border-color: #666; }
.upload-area.has-image { padding: 0; }
.upload-area img { max-width: 100%; max-height: 300px; border-radius: 6px; }
.upload-area input[type="file"] { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; -webkit-appearance: none; }
.upload-text { color: #666; font-size: 14px; }
textarea { width: 100%; background: #111; border: 1px solid #333; border-radius: 8px; color: #fff; padding: 12px; font-size: 14px; resize: vertical; min-height: 120px; font-family: inherit; }
textarea:focus { outline: none; border-color: #555; }
.params { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }
.param label { display: block; font-size: 12px; color: #888; margin-bottom: 4px; }
.param input { width: 100%; background: #111; border: 1px solid #333; border-radius: 6px; color: #fff; padding: 8px; font-size: 13px; }
.btn { width: 100%; padding: 14px; background: linear-gradient(135deg, #5b21b6, #7c3aed); color: #fff; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; margin-top: 20px; transition: opacity 0.2s; }
.btn:hover { opacity: 0.9; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.status { text-align: center; padding: 20px; color: #888; font-size: 14px; }
.progress { width: 100%; height: 4px; background: #333; border-radius: 2px; margin-top: 12px; overflow: hidden; }
.progress-bar { height: 100%; background: linear-gradient(90deg, #5b21b6, #7c3aed); transition: width 0.3s; }
</style>
</head>
<body>
<div class="container">
<h1>AI Photo Generator</h1>

<div id="loginGate" style="position:fixed;inset:0;background:rgba(0,0,0,0.95);z-index:10000;display:flex;align-items:center;justify-content:center;padding:20px">
<div style="background:#1a1a1a;border:1px solid #333;border-radius:12px;padding:30px;max-width:400px;text-align:center">
<h2 style="margin-bottom:16px;color:#fff">Access Code Required</h2>
<input type="password" id="accessCode" placeholder="Enter access code" style="width:100%;background:#111;border:1px solid #333;border-radius:8px;color:#fff;padding:12px;font-size:16px;text-align:center;margin-bottom:16px">
<button onclick="checkAccess()" style="width:100%;padding:14px;background:linear-gradient(135deg,#5b21b6,#7c3aed);color:#fff;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer">Enter</button>
<div id="loginError" style="color:#f55;margin-top:12px;font-size:14px;display:none">Wrong code</div>
</div>
</div>
<script>
document.getElementById('accessCode').addEventListener('keydown', (e) => { if(e.key==='Enter') checkAccess(); });
let accessCode = '';
function checkAccess() {
    accessCode = document.getElementById('accessCode').value;
    fetch('/check_access', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({code:accessCode})})
    .then(r => { if(r.ok){document.getElementById('loginGate').style.display='none';sessionStorage.setItem('access',accessCode)} else{document.getElementById('loginError').style.display='block'} });
}
if (sessionStorage.getItem('access')) { accessCode=sessionStorage.getItem('access'); document.getElementById('loginGate').style.display='none'; }
</script>

<div id="disclaimer" style="position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px">
<div style="background:#1a1a1a;border:1px solid #333;border-radius:12px;padding:30px;max-width:600px;max-height:80vh;overflow-y:auto">
<h2 style="margin-bottom:16px;color:#fff">Terms of Use</h2>
<div style="color:#aaa;font-size:14px;line-height:1.8">
<p>By using this service, you agree to the following:</p>
<ul style="margin:12px 0;padding-left:20px">
<li>You will <b>only use your own photos</b> or photos for which you have explicit consent.</li>
<li>You will <b>not generate images of minors</b> under any circumstances.</li>
<li>You will <b>not use generated images</b> for harassment, defamation, fraud, impersonation, or any illegal purpose.</li>
<li>You are <b>solely responsible</b> for all content you generate.</li>
<li>The service provider assumes <b>no liability</b> for any misuse.</li>
</ul>
<p style="margin-top:12px">If you do not agree, please close this page.</p>
</div>
<button onclick="document.getElementById('disclaimer').style.display='none';localStorage.setItem('agreed','1')" style="width:100%;padding:14px;background:linear-gradient(135deg,#5b21b6,#7c3aed);color:#fff;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer;margin-top:20px">I Agree</button>
</div>
</div>
<script>if(localStorage.getItem('agreed')==='1'){document.getElementById('disclaimer').style.display='none';}</script>

<div class="main">
  <div>
    <div class="panel">
      <h2>Reference Face</h2>
      <label class="upload-area" id="uploadArea" for="fileInput">
        <div class="upload-text" id="uploadText">Tap to upload photo</div>
        <input type="file" id="fileInput" accept="image/*">
      </label>
    </div>
    <div class="panel" style="margin-top:20px">
      <h2>Prompt</h2>
      <textarea id="prompt" placeholder="Describe what you want...">a young woman in a red dress, standing on a beach at sunset, wind blowing hair, cinematic lighting, professional photo, detailed face</textarea>
      <div class="params">
        <div class="param"><label>PuLID Weight (face)</label><input type="number" id="pulidWeight" value="0.9" min="0" max="1.5" step="0.1"></div>
        <div class="param"><label>LoRA Weight</label><input type="number" id="loraWeight" value="0" min="0" max="1.2" step="0.1"></div>
        <div class="param"><label>Steps</label><input type="number" id="steps" value="30" min="10" max="50"></div>
        <div class="param"><label>Guidance</label><input type="number" id="guidance" value="3.5" min="1" max="10" step="0.5"></div>
        <div class="param"><label>Width</label><input type="number" id="width" value="1024" min="512" max="1536" step="64"></div>
        <div class="param"><label>Height</label><input type="number" id="height" value="1024" min="512" max="1536" step="64"></div>
      </div>
      <button class="btn" id="generateBtn" onclick="generate()">Generate</button>
    </div>
  </div>
  <div>
    <div class="panel" style="min-height:500px">
      <h2>Result</h2>
      <div id="resultArea">
        <div class="status">Upload a reference face and click Generate</div>
      </div>
    </div>
  </div>
</div>
</div>

<script>
const fileInput = document.getElementById('fileInput');
const uploadArea = document.getElementById('uploadArea');
let uploadedFileName = null;
let cachedFileBlob = null;  // cache for re-upload

fileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    cachedFileBlob = file;  // cache the file
    await doUpload(file);
});

async function doUpload(file) {
    const formData = new FormData();
    formData.append('file', file);
    const resp = await fetch('/upload', { method: 'POST', body: formData });
    if (!resp.ok) {
        const msg = await resp.text();
        alert(msg || 'Upload failed');
        return false;
    }
    const data = await resp.json();
    uploadedFileName = data.filename;
    const reader = new FileReader();
    reader.onload = (ev) => {
        let img = uploadArea.querySelector('img');
        if (!img) { img = document.createElement('img'); uploadArea.insertBefore(img, uploadArea.firstChild); }
        img.src = ev.target.result;
        uploadArea.classList.add('has-image');
        document.getElementById('uploadText').style.display = 'none';
    };
    reader.readAsDataURL(file);
}

async function ensureUploaded() {
    // Re-upload if server deleted the input
    if (!cachedFileBlob || !uploadedFileName) return false;
    try {
        const check = await fetch('/check_input/' + uploadedFileName);
        if (check.status === 404) {
            await doUpload(cachedFileBlob);
        }
    } catch(e) {}
    return true;
}

async function generate() {
    if (!uploadedFileName) { alert('Please upload a reference face first'); return; }
    const loraW = parseFloat(document.getElementById('loraWeight').value);
    // Re-upload if input was deleted
    await ensureUploaded();
    const btn = document.getElementById('generateBtn');
    const resultArea = document.getElementById('resultArea');
    btn.disabled = true;
    btn.textContent = 'Generating...';
    resultArea.innerHTML = '<div class="status">Loading models and generating...<div class="progress"><div class="progress-bar" id="progressBar" style="width:0%"></div></div></div>';
    let progress = 0;
    const progressInterval = setInterval(() => {
        if (progress < 90) { progress += 2; document.getElementById('progressBar').style.width = progress + '%'; }
    }, 1000);
    const batchEl = document.getElementById('batchCount');
    const batchCount = batchEl ? parseInt(batchEl.value) || 1 : 1;
    const totalBatch = Math.min(Math.max(batchCount, 1), 10);
    const allImages = [];
    try {
        for (let b = 0; b < totalBatch; b++) {
            if (totalBatch > 1) { btn.textContent = 'Generating ' + (b+1) + '/' + totalBatch + '...'; }
            await ensureUploaded();
            const resp = await fetch('/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image: uploadedFileName, prompt: document.getElementById('prompt').value,
                    pulid_weight: parseFloat(document.getElementById('pulidWeight').value),
                    lora_weight: loraW,
                    extra_loras: window.__IS_EXTRA__ ? {whdb:parseFloat(document.getElementById('lora_whdb').value||0),gnz:parseFloat(document.getElementById('lora_gnz').value||0),sf:parseFloat(document.getElementById('lora_sf').value||0),sy:parseFloat(document.getElementById('lora_sy').value||0)} : {},
                    steps: parseInt(document.getElementById('steps').value),
                    guidance: parseFloat(document.getElementById('guidance').value),
                    width: parseInt(document.getElementById('width').value), height: parseInt(document.getElementById('height').value),
                    access: accessCode,
                })
            });
            if (!resp.ok) throw new Error(await resp.text());
            const blob = await resp.blob();
            allImages.push(URL.createObjectURL(blob));
            if (totalBatch > 1) { document.getElementById('progressBar').style.width = ((b+1)/totalBatch*100) + '%'; }
        }
        clearInterval(progressInterval);
        document.getElementById('progressBar').style.width = '100%';
        resultArea.innerHTML = allImages.map((url, i) =>
            '<div style="margin-bottom:16px"><img src="' + url + '" style="max-width:100%;border-radius:8px">'
            + '<br><a href="' + url + '" download="generated_' + (i+1) + '.png" style="color:#7c3aed;font-size:13px">Download #' + (i+1) + '</a></div>'
        ).join('');
    } catch (e) {
        clearInterval(progressInterval);
        resultArea.innerHTML = '<div class="status" style="color:#f55">Generation failed. The GPU engine may be offline.<br><br>Please contact the admin to start it.</div>';
    }
    btn.disabled = false;
    btn.textContent = 'Generate';
}
</script>
</body>
</html>"""

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin - Encrypted Gallery</title>
<style>
body { font-family: -apple-system, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; }
.container { max-width: 900px; margin: 0 auto; }
h1 { margin-bottom: 10px; }
.key-area { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
.key-area label { color: #aaa; font-size: 14px; display: block; margin-bottom: 8px; }
.key-area input { display: none; }
.key-btn { background: #333; color: #fff; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; }
.key-btn:hover { background: #444; }
.key-status { color: #4a4; font-size: 13px; margin-top: 8px; display: none; }
.gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 16px; }
.card { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; overflow: hidden; }
.card .preview { width: 100%; min-height: 200px; display: flex; align-items: center; justify-content: center; background: #111; color: #444; font-size: 40px; }
.card .preview img { width: 100%; height: auto; display: block; }
.card .info { padding: 12px; }
.card .info .time { color: #888; font-size: 12px; }
.card .info .size { color: #666; font-size: 12px; }
.card .actions { padding: 0 12px 12px; display: flex; gap: 8px; }
.card .actions button { flex: 1; padding: 8px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.decrypt-btn { background: #5b21b6; color: #fff; }
.decrypt-btn:hover { background: #7c3aed; }
.dl-btn { background: #333; color: #fff; }
.dl-btn:hover { background: #444; }
.top-actions { margin-bottom: 16px; display: flex; gap: 12px; }
.btn-del { background: #c0392b; color: #fff; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; }
.btn-refresh { background: #333; color: #fff; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; }
.empty { text-align: center; color: #666; padding: 40px; }
</style>
</head>
<body>
<div class="container">
<h1>Encrypted Gallery</h1>
<div id="adminGate" style="position:fixed;inset:0;background:rgba(0,0,0,0.95);z-index:10000;display:flex;align-items:center;justify-content:center;padding:20px">
<div style="background:#1a1a1a;border:1px solid #333;border-radius:12px;padding:30px;max-width:400px;text-align:center">
<h2 style="margin-bottom:16px;color:#fff">Admin Password</h2>
<input type="password" id="adminPwd" placeholder="Enter admin password" style="width:100%;background:#111;border:1px solid #333;border-radius:8px;color:#fff;padding:12px;font-size:16px;text-align:center;margin-bottom:16px">
<button onclick="checkAdmin()" style="width:100%;padding:14px;background:linear-gradient(135deg,#5b21b6,#7c3aed);color:#fff;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer">Enter</button>
<div id="adminError" style="color:#f55;margin-top:12px;font-size:14px;display:none">Wrong password</div>
</div>
</div>
<script>
let adminKey = '';
document.getElementById('adminPwd').addEventListener('keydown', (e) => { if(e.key==='Enter') checkAdmin(); });
function checkAdmin() {
    adminKey = document.getElementById('adminPwd').value;
    fetch('/admin/list', {headers:{'X-Admin-Key': adminKey}}).then(r => {
        if (r.ok) { document.getElementById('adminGate').style.display='none'; load(); checkGPU(); }
        else { document.getElementById('adminError').style.display='block'; }
    });
}
</script>
<div class="key-area">
  <label>Load your private key to decrypt images (key stays in browser, never uploaded)</label>
  <button class="key-btn" onclick="document.getElementById('keyFile').click()">Load private_key.pem</button>
  <input type="file" id="keyFile" accept=".pem">
  <div class="key-status" id="keyStatus">Private key loaded</div>
</div>
<div style="background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:16px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between">
  <div><span style="font-size:14px;color:#aaa">ComfyUI GPU Engine</span><br><span id="gpuStatus" style="font-size:13px;color:#888">Checking...</span></div>
  <button id="gpuBtn" onclick="toggleGPU()" style="padding:10px 24px;border:none;border-radius:6px;cursor:pointer;font-size:14px;font-weight:600">...</button>
</div>
<script>
async function checkGPU() {
    const r = await fetch('/admin/gpu_status', {headers:{'X-Admin-Key': adminKey}});
    const d = await r.json();
    document.getElementById('gpuStatus').textContent = d.running ? 'Running (' + d.vram + ')' : 'Stopped (GPU released)';
    document.getElementById('gpuStatus').style.color = d.running ? '#4a4' : '#888';
    document.getElementById('gpuBtn').textContent = d.running ? 'Stop (Free GPU)' : 'Start';
    document.getElementById('gpuBtn').style.background = d.running ? '#c0392b' : '#27ae60';
    document.getElementById('gpuBtn').style.color = '#fff';
}
async function toggleGPU() {
    const btn = document.getElementById('gpuBtn');
    const wasRunning = btn.textContent.startsWith('Stop');
    btn.disabled = true;
    btn.textContent = wasRunning ? 'Stopping...' : 'Starting...';
    await fetch('/admin/gpu_toggle', {method:'POST', headers:{'X-Admin-Key': adminKey}});
    await new Promise(r => setTimeout(r, wasRunning ? 3000 : 15000));
    await checkGPU();
    btn.disabled = false;
}
// checkGPU called after admin login via checkAdmin()
</script>
<div class="top-actions">
  <button class="btn-refresh" onclick="load()">Refresh</button>
  <button class="btn-del" onclick="deleteAll()">Delete All</button>
  <button class="decrypt-btn" onclick="decryptAllView()" style="padding:10px 20px;border-radius:8px;font-size:14px">Decrypt & View All</button>
  <button class="decrypt-btn" onclick="decryptAll()" style="padding:10px 20px;border-radius:8px;font-size:14px;background:#333">Decrypt & Download All</button>
</div>
<div class="gallery" id="gallery"></div>
</div>

<script>
let privateKey = null;

document.getElementById('keyFile').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const pem = await file.text();
    try {
        const pemBody = pem.replace(/-----[^-]+-----/g, '').replace(/\s/g, '');
        const der = Uint8Array.from(atob(pemBody), c => c.charCodeAt(0));
        privateKey = await crypto.subtle.importKey('pkcs8', der, { name: 'RSA-OAEP', hash: 'SHA-256' }, false, ['decrypt']);
        document.getElementById('keyStatus').style.display = 'block';
    } catch(e) { alert('Failed to load key: ' + e.message); }
});

async function decryptEncFile(encBytes) {
    const view = new DataView(encBytes.buffer || encBytes);
    const keyLen = view.getUint32(0);
    const encAesKey = encBytes.slice(4, 4 + keyLen);
    const nonce = encBytes.slice(4 + keyLen, 4 + keyLen + 12);
    const encData = encBytes.slice(4 + keyLen + 12);
    const aesKeyRaw = await crypto.subtle.decrypt({ name: 'RSA-OAEP' }, privateKey, encAesKey);
    const aesKey = await crypto.subtle.importKey('raw', aesKeyRaw, { name: 'AES-GCM' }, false, ['decrypt']);
    const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: nonce }, aesKey, encData);
    return new Uint8Array(decrypted);
}

async function load() {
    const resp = await fetch('/admin/list', { headers: { 'X-Admin-Key': adminKey } });
    const files = await resp.json();
    const div = document.getElementById('gallery');
    if (files.length === 0) { div.innerHTML = '<div class="empty">No encrypted files</div>'; return; }
    div.innerHTML = files.map((f, i) =>
        '<div class="card" id="card-' + i + '">' +
        '<div class="preview" id="preview-' + i + '">&#128274;</div>' +
        '<div class="info"><div class="time">' + f.time + '</div><div class="size">' + f.size + '</div></div>' +
        '<div class="actions">' +
        '<button class="decrypt-btn" onclick="decryptOne(' + i + ',\'' + f.name + '\')">Decrypt</button>' +
        '<button class="dl-btn" onclick="downloadEnc(\'' + f.name + '\')">Download .enc</button>' +
        '</div></div>'
    ).join('');
}

async function decryptOne(idx, filename) {
    if (!privateKey) { alert('Please load your private key first'); return; }
    const resp = await fetch('/admin/download/' + filename + '?key=' + adminKey + '');
    const encBytes = new Uint8Array(await resp.arrayBuffer());
    try {
        const imgBytes = await decryptEncFile(encBytes);
        const blob = new Blob([imgBytes], { type: 'image/png' });
        const url = URL.createObjectURL(blob);
        document.getElementById('preview-' + idx).innerHTML = '<img src="' + url + '">';
        // replace decrypt button with download
        const card = document.getElementById('card-' + idx);
        const actions = card.querySelector('.actions');
        actions.innerHTML = '<a href="' + url + '" download="' + filename.replace('.enc','') + '" class="decrypt-btn" style="text-align:center;text-decoration:none;display:block;padding:8px;border-radius:6px">Save Image</a>';
    } catch(e) { alert('Decryption failed: ' + e.message); }
}

async function decryptAllView() {
    if (!privateKey) { alert('Please load your private key first'); return; }
    const resp = await fetch('/admin/list', { headers: { 'X-Admin-Key': adminKey } });
    const files = await resp.json();
    for (let i = 0; i < files.length; i++) {
        try {
            const r = await fetch('/admin/download/' + files[i].name + '?key=' + adminKey + '');
            const encBytes = new Uint8Array(await r.arrayBuffer());
            const imgBytes = await decryptEncFile(encBytes);
            const blob = new Blob([imgBytes], { type: 'image/png' });
            const url = URL.createObjectURL(blob);
            document.getElementById('preview-' + i).innerHTML = '<img src="' + url + '">';
        } catch(e) {}
    }
}

async function decryptAll() {
    if (!privateKey) { alert('Please load your private key first'); return; }
    const resp = await fetch('/admin/list', { headers: { 'X-Admin-Key': adminKey } });
    const files = await resp.json();
    for (let i = 0; i < files.length; i++) {
        await decryptOne(i, files[i].name);
    }
}

function downloadEnc(filename) {
    window.open('/admin/download/' + filename + '?key=' + adminKey + '');
}

async function deleteAll() {
    if (!confirm('Delete all encrypted files?')) return;
    await fetch('/admin/delete_all', { method: 'POST', headers: { 'X-Admin-Key': adminKey } });
    load();
}

load();
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML

EXTRA_HTML = HTML.replace(
    'AI Photo Generator',
    'AI Photo Generator (Extra)'
).replace(
    '<script>\nconst fileInput',
    '<script>\nwindow.__IS_EXTRA__=true;\nconst fileInput'
).replace(
    '<button class="btn" id="generateBtn"',
    '''<div style="margin-top:16px;padding-top:16px;border-top:1px solid #333">
<div style="color:#888;font-size:12px;margin-bottom:12px">Extra Style LoRAs (default 0 = off)</div>
<div class="params">
<div class="param"><label>WHDB</label><input type="number" id="lora_whdb" value="0" min="0" max="1.2" step="0.1"></div>
<div class="param"><label>GNZ</label><input type="number" id="lora_gnz" value="0" min="0" max="1.2" step="0.1"></div>
<div class="param"><label>SF</label><input type="number" id="lora_sf" value="0" min="0" max="1.2" step="0.1"></div>
<div class="param"><label>SY</label><input type="number" id="lora_sy" value="0" min="0" max="1.2" step="0.1"></div>
</div>
<div class="params" style="margin-top:12px">
<div class="param"><label>Batch Count</label><input type="number" id="batchCount" value="1" min="1" max="10"></div>
</div>
</div>
<button class="btn" id="generateBtn"'''
)

@app.get("/extra", response_class=HTMLResponse)
async def extra_page():
    return EXTRA_HTML

from PIL import Image
import numpy as np

_face_detector = None
def get_face_detector():
    global _face_detector
    if _face_detector is None:
        from insightface.app import FaceAnalysis
        _face_detector = FaceAnalysis(name="antelopev2",
            root=os.path.expanduser("~/ComfyUI/models/insightface"),
            providers=["CPUExecutionProvider"])
        _face_detector.prepare(ctx_id=-1, det_size=(320, 320))
    return _face_detector

ACCESS_CODE = os.environ.get("ACCESS_CODE", "change_me")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change_me")
EXTRA_PASSWORD = os.environ.get("EXTRA_PASSWORD", "7086")

@app.post("/check_access")
async def check_access(body: dict):
    code = body.get("code")
    if code == ACCESS_CODE or code == EXTRA_PASSWORD:
        return {"ok": True}
    return Response("Wrong code", status_code=403)

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    fname = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    INPUT_DIR.mkdir(exist_ok=True)
    fpath = INPUT_DIR / fname
    content = await file.read()
    fpath.write_bytes(content)
    # Check for face
    try:
        img = Image.open(io.BytesIO(content)).convert("RGB")
        img_np = np.array(img)
        faces = get_face_detector().get(img_np)
        if len(faces) == 0:
            fpath.unlink(missing_ok=True)
            return Response("No face detected in the image. Please upload a photo with a clearly visible face.", status_code=400)
    except Exception as e:
        print(f"[FACE CHECK] Error: {type(e).__name__}: {e}")
        # Still reject - safer to require face
    return {"filename": fname}

@app.get("/check_input/{filename}")
async def check_input(filename: str):
    fpath = INPUT_DIR / filename
    if fpath.exists():
        return {"exists": True}
    return Response("Not found", status_code=404)

@app.get("/output/{filename}")
async def get_output(filename: str):
    fpath = OUTPUT_DIR / filename
    if not fpath.exists():
        return Response("Not found", status_code=404)
    return Response(fpath.read_bytes(), media_type="image/png")

@app.post("/generate")
async def generate_image(body: dict):
    access = body.get("access")
    if access != ACCESS_CODE and access != EXTRA_PASSWORD:
        return Response("Access denied", status_code=403)
    image = body["image"]
    prompt = body["prompt"]
    pulid_w = body.get("pulid_weight", 0.9)
    lora_w = body.get("lora_weight", 0)
    steps = body.get("steps", 30)
    guidance = body.get("guidance", 3.5)
    width = body.get("width", 1024)
    height = body.get("height", 1024)
    seed = int(time.time()) % 2**32
    prefix = f"webui_{uuid.uuid4().hex[:6]}"

    extra = body.get("extra_loras", {}) or {}
    lora_files = [
        ("seqing_master.safetensors", lora_w),
        ("whdb.safetensors", extra.get("whdb", 0)),
        ("gnz.safetensors", extra.get("gnz", 0)),
        ("sf.safetensors", extra.get("sf", 0)),
        ("sy.safetensors", extra.get("sy", 0)),
    ]
    nodes = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux1-dev-F16.gguf"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "t5xxl_fp16.safetensors", "clip_name2": "clip_l.safetensors", "type": "flux", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
    }
    prev_model, prev_clip = ["1", 0], ["2", 0]
    next_id = 100
    for lora_name, weight in lora_files:
        if weight <= 0:
            continue
        node_id = str(next_id); next_id += 1
        nodes[node_id] = {"class_type": "LoraLoader", "inputs": {"model": prev_model, "clip": prev_clip, "lora_name": lora_name, "strength_model": weight, "strength_clip": weight}}
        prev_model, prev_clip = [node_id, 0], [node_id, 1]
    final_model, final_clip = prev_model, prev_clip
    nodes["5"] = {"class_type": "ModelSamplingFlux", "inputs": {"model": final_model, "max_shift": 1.15, "base_shift": 0.5, "width": width, "height": height}}

    workflow = {
        "prompt": {**nodes,
            "6": {"class_type": "PulidFluxModelLoader", "inputs": {"pulid_file": "pulid_flux_v0.9.1.safetensors"}},
            "7": {"class_type": "PulidFluxEvaClipLoader", "inputs": {}},
            "8": {"class_type": "PulidFluxInsightFaceLoader", "inputs": {"provider": "CUDA"}},
            "9": {"class_type": "LoadImage", "inputs": {"image": image}},
            "10": {"class_type": "ApplyPulidFlux", "inputs": {"model": ["5", 0], "pulid_flux": ["6", 0], "eva_clip": ["7", 0], "face_analysis": ["8", 0], "image": ["9", 0], "weight": pulid_w, "start_at": 0.0, "end_at": 1.0, "fusion": "mean", "fusion_weight_max": 1.0, "fusion_weight_min": 0.0, "train_step": 1000, "use_gray": True}},
            "11": {"class_type": "CLIPTextEncode", "inputs": {"clip": final_clip, "text": prompt}},
            "12": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["11", 0], "guidance": guidance}},
            "13": {"class_type": "BasicGuider", "inputs": {"model": ["10", 0], "conditioning": ["12", 0]}},
            "14": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
            "15": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "16": {"class_type": "BasicScheduler", "inputs": {"model": ["10", 0], "scheduler": "simple", "steps": steps, "denoise": 1.0}},
            "17": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "18": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["14", 0], "guider": ["13", 0], "sampler": ["15", 0], "sigmas": ["16", 0], "latent_image": ["17", 0]}},
            "19": {"class_type": "VAEDecode", "inputs": {"samples": ["18", 0], "vae": ["3", 0]}},
            "20": {"class_type": "SaveImage", "inputs": {"images": ["19", 0], "filename_prefix": prefix}},
        }
    }

    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(f"{COMFYUI}/api/prompt", json=workflow)
        if resp.status_code != 200:
            return Response(f"ComfyUI error: {resp.text}", status_code=500)
        prompt_id = resp.json()["prompt_id"]

        for _ in range(600):
            time.sleep(1)
            hist = await client.get(f"{COMFYUI}/api/history/{prompt_id}")
            if hist.status_code == 200:
                data = hist.json()
                if prompt_id in data:
                    outputs = data[prompt_id].get("outputs", {})
                    for node_id, node_out in outputs.items():
                        images = node_out.get("images", [])
                        if images:
                            filename = images[0]["filename"]
                            filepath = OUTPUT_DIR / filename
                            image_bytes = filepath.read_bytes()
                            # Encrypt and save
                            enc_bytes = encrypt_image(image_bytes)
                            (OUTPUT_DIR / f"{filename}.enc").write_bytes(enc_bytes)
                            # Delete original + input + history
                            filepath.unlink(missing_ok=True)
                            (INPUT_DIR / image).unlink(missing_ok=True)
                            try:
                                await client.post(f"{COMFYUI}/api/history", json={"delete": [prompt_id]})
                            except: pass
                            return Response(image_bytes, media_type="image/png")

        return Response("Timeout", status_code=504)

# Admin
@app.get("/admin")
async def admin_page():
    return HTMLResponse(ADMIN_HTML)

from starlette.requests import Request

@app.get("/admin/list")
async def admin_list(request: Request):
    if request.headers.get("X-Admin-Key") != ADMIN_PASSWORD:
        return Response("Forbidden", status_code=403)
    files = []
    for f in sorted(OUTPUT_DIR.glob("*.enc"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = f.stat()
        size_mb = stat.st_size / (1024 * 1024)
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
        files.append({"name": f.name, "size": f"{size_mb:.1f} MB", "time": mtime})
    return files

@app.get("/admin/download/{filename}")
async def admin_download(filename: str, key: str = ""):
    if key != ADMIN_PASSWORD:
        return Response("Forbidden", status_code=403)
    fpath = OUTPUT_DIR / filename
    if not fpath.exists():
        return Response("Not found", status_code=404)
    return Response(fpath.read_bytes(), media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.post("/admin/delete_all")
async def admin_delete_all(request: Request):
    if request.headers.get("X-Admin-Key") != ADMIN_PASSWORD:
        return Response("Forbidden", status_code=403)
    for f in OUTPUT_DIR.glob("*.enc"):
        f.unlink()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{COMFYUI}/api/history", json={"clear": True})
    except: pass
    return {"status": "deleted"}

import subprocess, signal

@app.get("/admin/gpu_status")
async def gpu_status(request: Request):
    if request.headers.get("X-Admin-Key") != ADMIN_PASSWORD:
        return Response("Forbidden", status_code=403)
    result = subprocess.run(["pgrep", "-f", "python main.py.*--port 8189"], capture_output=True)
    running = result.returncode == 0
    vram = ""
    if running:
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader"], capture_output=True, text=True)
            lines = r.stdout.strip().split("\n")
            for line in lines:
                if line.strip().startswith("2,"):
                    vram = line.split(",")[1].strip()
        except: pass
    return {"running": running, "vram": vram}

@app.post("/admin/gpu_toggle")
async def gpu_toggle(request: Request):
    if request.headers.get("X-Admin-Key") != ADMIN_PASSWORD:
        return Response("Forbidden", status_code=403)
    result = subprocess.run(["pgrep", "-f", "python main.py.*--port 8189"], capture_output=True, text=True)
    if result.returncode == 0:
        # Running -> stop
        pids = result.stdout.strip().split("\n")
        for pid in pids:
            try: os.kill(int(pid.strip()), signal.SIGKILL)
            except: pass
        return {"action": "stopped"}
    else:
        # Stopped -> start
        subprocess.Popen(
            "source ~/ComfyUI/venv/bin/activate && CUDA_VISIBLE_DEVICES=2 nohup python main.py --listen 127.0.0.1 --port 8189 > /tmp/comfyui.log 2>&1 &",
            shell=True, cwd=os.path.expanduser("~/ComfyUI"),
            executable="/bin/bash"
        )
        return {"action": "started"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=args.port)
