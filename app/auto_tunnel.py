import os
import sys
import re
import json
import time
import subprocess
import urllib.request
import sqlite3
import threading

# รองรับภาษาไทยและ emoji บน Windows Console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "app", "poster.db")
CLOUDFLARED_EXE = os.path.join(BASE_DIR, "cloudflared.exe")
NGROK_EXE = os.path.join(BASE_DIR, "ngrok.exe")
NGROK_STATIC_DOMAIN = "https://glitter-nervous-diaphragm.ngrok-free.dev"

def get_line_token() -> str:
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        row = conn.execute("SELECT value FROM settings WHERE key='line_channel_token'").fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception as e:
        print(f"[DB Error] reading line_channel_token: {e}")
        return ""

def set_public_url(url: str):
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.execute("""
            INSERT INTO settings (key, value) VALUES ('public_url', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (url.strip(),))
        conn.commit()
        conn.close()
        print(f"[DB] Saved public_url: {url}")
    except Exception as e:
        print(f"[DB Error] saving public_url: {e}")

def update_line_webhook(token: str, webhook_url: str) -> bool:
    if not token:
        print("[!] LINE Channel Token not found in settings.")
        return False
    for attempt in range(1, 6):
        try:
            req = urllib.request.Request(
                'https://api.line.me/v2/bot/channel/webhook/endpoint',
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                data=json.dumps({"endpoint": webhook_url}).encode('utf-8'),
                method='PUT'
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    print(f"[OK] LINE Webhook updated successfully to: {webhook_url}")
                    return True
        except Exception as e:
            if attempt < 5:
                time.sleep(2)
            else:
                print(f"[!] Failed to update LINE Webhook after 5 attempts: {e}")
    return False

def check_tunnel_health(url: str) -> bool:
    """ส่งคำขอไปยัง {url}/health เพื่อทดสอบว่าภายนอกยังเชื่อมต่อเข้าเครื่องได้จริงหรือไม่"""
    try:
        health_url = f"{url}/health"
        req = urllib.request.Request(health_url, headers={'User-Agent': 'Tunnel-Watchdog/1.0'})
        with urllib.request.urlopen(req, timeout=8) as res:
            return res.status == 200
    except Exception:
        return False

def run_tunnel_cycle():
    """รัน Cloudflare tunnel 1 รอบ พร้อม Watchdog Heartbeat เฝ้าระวังการหลุด 24 ชม."""
    if not os.path.exists(CLOUDFLARED_EXE):
        print(f"[X] cloudflared.exe not found at: {CLOUDFLARED_EXE}")
        time.sleep(10)
        return

    print("\n" + "=" * 60)
    print("  Starting Cloudflare Tunnel & Self-Healing Watchdog")
    print("=" * 60)
    print("Target local server: http://localhost:8000")

    cmd = [CLOUDFLARED_EXE, "tunnel", "--url", "http://localhost:8000"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1
    )

    tunnel_url = None
    captured_event = threading.Event()

    def read_output():
        nonlocal tunnel_url
        try:
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    m = re.search(r'https://([a-zA-Z0-9\-]+)\.trycloudflare\.com', line)
                    if m and not tunnel_url:
                        subdomain = m.group(1).lower()
                        if subdomain not in ['api', 'www', 'dash', 'blog', 'developers']:
                            tunnel_url = m.group(0)
                            captured_event.set()
        except Exception:
            pass

    reader_thread = threading.Thread(target=read_output, daemon=True)
    reader_thread.start()

    # รอรับ URL สูงสุด 35 วินาที
    if not captured_event.wait(timeout=35) or not tunnel_url:
        print("[!] ไม่ได้รับ trycloudflare URL (เน็ตอาจหลุดหรือติดหน้าล็อกอิน Wi-Fi) รอ 10 วิก่อนลองใหม่...")
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        time.sleep(10)
        return

    # บันทึก URL ลงฐานข้อมูล + อัปเดต LINE Webhook
    set_public_url(tunnel_url)
    webhook_url = f"{tunnel_url}/api/line/webhook"

    print("\n" + "=" * 60)
    print(f"[*] Cloudflare Tunnel is ONLINE!")
    print(f"[*] Web URL: {tunnel_url}")
    print(f"[*] LINE Webhook: {webhook_url}")
    print("=" * 60)

    token = get_line_token()
    if token:
        print("\n[*] รอ Cloudflare DNS เผยแพร่ทั่วโลกก่อนอัปเดต LINE...")
        for _ in range(15):
            if check_tunnel_health(tunnel_url):
                break
            time.sleep(2)

        print("[*] Auto-updating LINE Webhook in LINE Developers...")
        if update_line_webhook(token, webhook_url):
            print("[*] LINE Bot is 100% READY! ส่งรูปหรือข้อความในไลน์ได้เลย\n")

    print("=" * 60)
    print("(Self-Healing Watchdog Active: ตรวจเช็คสถานะการเชื่อมต่อทุก 60 วิ)")
    print("=" * 60 + "\n")

    # Watchdog Heartbeat Loop
    fail_count = 0
    while True:
        time.sleep(60)

        # 1. ตรวจสอบว่า Process หลุดหรือไม่
        if proc.poll() is not None:
            print(f"\n[!] cloudflared process terminated (code: {proc.returncode}). Restarting tunnel...")
            break

        # 2. ตรวจสอบว่าภายนอกยังเชื่อมต่อเข้า {tunnel_url}/health ได้จริงหรือไม่
        is_healthy = check_tunnel_health(tunnel_url)
        if is_healthy:
            fail_count = 0
        else:
            fail_count += 1
            print(f"[{time.strftime('%H:%M:%S')}] [Watchdog] Tunnel check failed ({fail_count}/2)...")

            if fail_count >= 2:
                print("\n[!] Tunnel URL กลายเป็น Dead/Unreachable (คอมสลีปหรือหมดอายุ). กำลังขอ URL ใหม่และรีซิงค์ LINE...")
                break

    try:
        proc.terminate()
        proc.wait(timeout=4)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

def main():
    while True:
        try:
            run_tunnel_cycle()
        except KeyboardInterrupt:
            print("\n[Stop] Tunnel watcher stopped by user.")
            break
        except Exception as e:
            print(f"[Error in tunnel loop] {e}")
        time.sleep(3)

if __name__ == "__main__":
    main()
