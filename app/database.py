import sqlite3
import os
import hashlib
import secrets
import jwt
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "poster.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    conn.execute("PRAGMA journal_mode=WAL;")
    cursor = conn.cursor()

    # ตารางเพจร้าน
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pages (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        icon TEXT NOT NULL,
        facebook_page_id TEXT DEFAULT '',
        facebook_access_token TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        line_id TEXT DEFAULT '',
        service_area TEXT DEFAULT ''
    )
    """)

    # ตารางคิวโพสต์
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        page_id TEXT NOT NULL,
        image_path TEXT NOT NULL,
        caption TEXT NOT NULL,
        first_comment TEXT DEFAULT '',
        caption_style TEXT DEFAULT 'แบบด่วน',
        scheduled_at DATETIME,
        status TEXT DEFAULT 'draft', -- draft, scheduled, published, failed
        facebook_post_id TEXT DEFAULT '',
        error_message TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        published_at DATETIME,
        FOREIGN KEY (page_id) REFERENCES pages (id)
    )
    """)

    # ตารางตั้งค่าระบบ (API Keys)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # ตารางผู้ใช้งานสำหรับเข้าสู่ระบบหลังบ้าน
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ตาราง Session เข้าสู่ระบบ
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        expires_at DATETIME NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # บัญชีแอดมินเริ่มต้น (admin / admin1234)
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        pwd_hash, salt = hash_password("admin1234")
        cursor.execute("INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)", ("admin", pwd_hash, salt))

    # ข้อมูลเริ่มต้นสำหรับเพจศรศิลป์ กรอบรูป
    cursor.execute("SELECT COUNT(*) FROM pages")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO pages (id, name, icon, phone, line_id, service_area) VALUES
        ('slidetruck', 'ศรศิลป์ กรอบรูป', '🖼️', '064-964-5353', '0649645353', 'ทั่วประเทศ / หน้าร้านและจัดส่งปลอดภัย')
        """)

    # ลบเพจ pigfeed ออกจากฐานข้อมูลถ้ามีค้างอยู่
    cursor.execute("DELETE FROM pages WHERE id = 'pigfeed'")

    # ค่าเริ่มต้น Settings
    cursor.execute("SELECT COUNT(*) FROM settings")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO settings (key, value) VALUES
        ('gemini_api_key', ''),
        ('line_channel_token', ''),
        ('line_channel_secret', ''),
        ('admin_line_user_id', ''),
        ('last_line_user_id', ''),
        ('watermark_enabled', 'true'),
        ('watermark_position', 'auto'),
        ('watermark_opacity', '0.85'),
        ('watermark_scale', '0.18')
        """)

    conn.commit()
    conn.close()

# --- Functions จัดการ Pages ---
def get_all_pages() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_page(page_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE id = ?", (page_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_page(page_id: str, fb_page_id: str, fb_token: str, phone: str, line_id: str, service_area: str, name: Optional[str] = None, icon: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    if name is not None and icon is not None:
        cursor.execute("""
        UPDATE pages 
        SET facebook_page_id = ?, facebook_access_token = ?, phone = ?, line_id = ?, service_area = ?, name = ?, icon = ?
        WHERE id = ?
        """, (fb_page_id, fb_token, phone, line_id, service_area, name, icon, page_id))
    elif name is not None:
        cursor.execute("""
        UPDATE pages 
        SET facebook_page_id = ?, facebook_access_token = ?, phone = ?, line_id = ?, service_area = ?, name = ?
        WHERE id = ?
        """, (fb_page_id, fb_token, phone, line_id, service_area, name, page_id))
    else:
        cursor.execute("""
        UPDATE pages 
        SET facebook_page_id = ?, facebook_access_token = ?, phone = ?, line_id = ?, service_area = ?
        WHERE id = ?
        """, (fb_page_id, fb_token, phone, line_id, service_area, page_id))
    conn.commit()
    conn.close()

# --- Functions จัดการ Posts ---
def create_post(page_id: str, image_path: str, caption: str, first_comment: str, 
                caption_style: str, scheduled_at: Optional[str], status: str = 'scheduled') -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO posts (page_id, image_path, caption, first_comment, caption_style, scheduled_at, status)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (page_id, image_path, caption, first_comment, caption_style, scheduled_at, status))
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return post_id

def get_all_posts(status_filter: Optional[str] = None, page_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = """
    SELECT p.*, g.name as page_name, g.icon as page_icon
    FROM posts p
    JOIN pages g ON p.page_id = g.id
    WHERE 1=1
    """
    params = []
    if status_filter and status_filter != 'all':
        query += " AND p.status = ?"
        params.append(status_filter)
    if page_filter and page_filter != 'all':
        query += " AND p.page_id = ?"
        params.append(page_filter)
    
    query += " ORDER BY CASE WHEN p.status = 'scheduled' THEN p.scheduled_at ELSE p.created_at END DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_post(post_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT p.*, g.name as page_name, g.icon as page_icon, g.phone, g.line_id
    FROM posts p
    JOIN pages g ON p.page_id = g.id
    WHERE p.id = ?
    """, (post_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_post_status(post_id: int, status: str, fb_post_id: str = '', error_message: str = ''):
    conn = get_connection()
    cursor = conn.cursor()
    published_at = datetime.now().isoformat() if status == 'published' else None
    cursor.execute("""
    UPDATE posts 
    SET status = ?, facebook_post_id = ?, error_message = ?, published_at = COALESCE(?, published_at)
    WHERE id = ?
    """, (status, fb_post_id, error_message, published_at, post_id))
    conn.commit()
    conn.close()

def update_post_details(post_id: int, caption: str, scheduled_at: Optional[str]):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE posts 
    SET caption = ?, scheduled_at = ?
    WHERE id = ?
    """, (caption, scheduled_at, post_id))
    conn.commit()
    conn.close()

def delete_post(post_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()

def auto_spread_scheduled_posts(interval_days: int = 1, target_hour: int = 18, target_minute: int = 0) -> List[Dict[str, Any]]:
    """
    จัดตารางคิวโพสต์ที่รอเวลาอยู่ทั้งหมด ให้กระจายออกไปวันละ 1 โพสต์ตามเวลาที่กำหนด (เช่น 18:00 น.)
    ไม่ให้มีโพสต์ชนกันในวันเดียวกัน
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, page_id, caption, scheduled_at, status 
    FROM posts 
    WHERE status IN ('scheduled', 'draft')
    ORDER BY CASE WHEN scheduled_at IS NOT NULL AND scheduled_at != '' THEN scheduled_at ELSE id END ASC
    """)
    rows = cursor.fetchall()
    
    if not rows:
        conn.close()
        return []
        
    now = datetime.now()
    # กำหนดวันเริ่มต้น: ถ้าวันนี้ยังไม่ถึงเวลาเป้าหมาย (เช่น ยังไม่ 18:00) ให้เริ่มวันนี้ได้ ไม่งั้นเริ่มพรุ่งนี้
    first_slot = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if first_slot <= now + timedelta(minutes=10):
        first_slot += timedelta(days=1)
        
    updated = []
    current_slot = first_slot
    for r in rows:
        pid = r["id"]
        sched_str = current_slot.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE posts SET scheduled_at = ?, status = 'scheduled' WHERE id = ?", (sched_str, pid))
        updated.append({
            "id": pid,
            "scheduled_at": sched_str,
            "caption": r["caption"][:40] if r["caption"] else ""
        })
        current_slot += timedelta(days=interval_days)
        
    conn.commit()
    conn.close()
    return updated

def get_pending_scheduled_posts() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    SELECT p.*, g.name as page_name, g.facebook_page_id, g.facebook_access_token, g.phone, g.line_id
    FROM posts p
    JOIN pages g ON p.page_id = g.id
    WHERE p.status = 'scheduled' AND p.scheduled_at <= ?
    """, (now_str,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# --- Functions จัดการ Settings ---
def get_setting(key: str, default: str = '') -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else default

def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO settings (key, value) VALUES (?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, value))
    conn.commit()
    conn.close()

# --- Functions จัดการ User & Authentication ---
def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return hashed, salt

def verify_password(password: str, password_hash: str, salt: str) -> bool:
    hashed, _ = hash_password(password, salt)
    return secrets.compare_digest(hashed, password_hash)

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_admin_credentials(current_username: str, new_username: str, new_password: Optional[str] = None) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    if new_password and new_password.strip():
        pwd_hash, salt = hash_password(new_password.strip())
        cursor.execute("UPDATE users SET username = ?, password_hash = ?, salt = ? WHERE username = ?", (new_username.strip(), pwd_hash, salt, current_username.strip()))
    else:
        cursor.execute("UPDATE users SET username = ? WHERE username = ?", (new_username.strip(), current_username.strip()))
    affected = cursor.rowcount
    if affected > 0 and new_username.strip() != current_username.strip():
        cursor.execute("UPDATE sessions SET username = ? WHERE username = ?", (new_username.strip(), current_username.strip()))
    conn.commit()
    conn.close()
    return affected > 0

def create_session(username: str, days: int = 7) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=days)
    expires_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sessions (token, username, expires_at) VALUES (?, ?, ?)", (token, username, expires_str))
    conn.commit()
    conn.close()
    return token

def verify_session(token: str) -> Optional[str]:
    if not token:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Clean expired sessions
    cursor.execute("DELETE FROM sessions WHERE expires_at < ?", (now_str,))
    conn.commit()
    cursor.execute("SELECT username FROM sessions WHERE token = ? AND expires_at >= ?", (token, now_str))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def delete_session(token: str):
    if not token:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()

def clear_all_sessions():
    """ล้างเซสชันทั้งหมด บังคับล็อกอินใหม่ทุกครั้งที่เปิด/รันเซิร์ฟเวอร์ใหม่"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions")
    conn.commit()
    conn.close()

# --- JWT Authentication System ---
JWT_ALGORITHM = "HS256"

def get_jwt_secret() -> str:
    secret = get_setting("jwt_secret_key", "")
    if not secret:
        secret = secrets.token_hex(32)
        set_setting("jwt_secret_key", secret)
    return secret

def create_jwt_token(username: str, hours: int = 8) -> str:
    """สร้าง JWT Token (HS256) สำหรับยืนยันตัวตนผู้ใช้งาน (อายุ 8 ชั่วโมง)"""
    secret = get_jwt_secret()
    now_utc = datetime.now(timezone.utc)
    payload = {
        "sub": username.strip(),
        "iat": int(now_utc.timestamp()),
        "exp": int((now_utc + timedelta(hours=hours)).timestamp()),
        "type": "access_token"
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)

def verify_jwt_token(token: str) -> Optional[str]:
    """ตรวจสอบความถูกต้องและวันหมดอายุของ JWT Token คืนค่า username ถ้าถูกต้อง"""
    if not token or not token.strip():
        return None
    token = token.strip()
    secret = get_jwt_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

