"""
本地解密工具 - 解密服务器上的 .enc 图片
用法:
  python decrypt.py file.enc                  # 解密单个文件
  python decrypt.py --pull                    # 从服务器拉取所有 .enc 并解密
  python decrypt.py --pull --delete           # 拉取、解密、删除服务器上的 .enc
"""
import sys, os, struct, argparse, subprocess
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PRIVATE_KEY_PATH = Path(__file__).parent / "private_key.pem"
DECRYPT_OUTPUT_DIR = Path(__file__).parent / "decrypted"

def load_private_key():
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)

def decrypt_file(enc_path: Path, private_key) -> bytes:
    data = enc_path.read_bytes()
    key_len = struct.unpack(">I", data[:4])[0]
    encrypted_aes_key = data[4:4+key_len]
    nonce = data[4+key_len:4+key_len+12]
    encrypted_data = data[4+key_len+12:]
    aes_key = private_key.decrypt(
        encrypted_aes_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    aesgcm = AESGCM(aes_key)
    return aesgcm.decrypt(nonce, encrypted_data, None)

def main():
    parser = argparse.ArgumentParser(description="Decrypt .enc images")
    parser.add_argument("files", nargs="*", help="Files to decrypt")
    parser.add_argument("--pull", action="store_true", help="Pull all .enc from server")
    parser.add_argument("--delete", action="store_true", help="Delete .enc on server after pull")
    args = parser.parse_args()

    DECRYPT_OUTPUT_DIR.mkdir(exist_ok=True)
    private_key = load_private_key()

    if args.pull:
        print("Pulling .enc files from server...")
        pull_dir = DECRYPT_OUTPUT_DIR / "enc"
        pull_dir.mkdir(exist_ok=True)
        result = subprocess.run(
            ["scp", "H100:~/ComfyUI/output/*.enc", str(pull_dir)],
            capture_output=True, text=True
        )
        enc_files = list(pull_dir.glob("*.enc"))
        if not enc_files:
            print("No .enc files found on server.")
            return
        print(f"Downloaded {len(enc_files)} files")
        for ef in enc_files:
            out_name = ef.stem  # removes .enc, keeps .png
            out_path = DECRYPT_OUTPUT_DIR / out_name
            try:
                decrypted = decrypt_file(ef, private_key)
                out_path.write_bytes(decrypted)
                print(f"  Decrypted: {out_path.name}")
                ef.unlink()  # remove local .enc
            except Exception as e:
                print(f"  Failed: {ef.name} - {e}")
        if args.delete:
            print("Deleting .enc files on server...")
            subprocess.run(["ssh", "H100", "rm -f ~/ComfyUI/output/*.enc"], check=True)
            print("Server cleaned.")
        print(f"\nDecrypted images in: {DECRYPT_OUTPUT_DIR}")
    else:
        if not args.files:
            parser.print_help()
            return
        for f in args.files:
            fp = Path(f)
            out_name = fp.stem
            out_path = DECRYPT_OUTPUT_DIR / out_name
            try:
                decrypted = decrypt_file(fp, private_key)
                out_path.write_bytes(decrypted)
                print(f"Decrypted: {out_path}")
            except Exception as e:
                print(f"Failed: {fp} - {e}")

if __name__ == "__main__":
    main()
