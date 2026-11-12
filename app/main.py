import os
import shutil
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, File, UploadFile, Form, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .database import (
    init_db, get_all_pages, get_page, update_page,
    create_post, get_all_posts, get_post, update_post_status,
    update_post_details, delete_post, get_setting, set_setting,
    get_user_by_username, verify_password, create_session,
    verify_session, delete_session, update_admin_credentials,
    clear_all_sessions, auto_spread_scheduled_posts,
    create_jwt_token, verify_jwt_token
)
from .gemini_service import generate_captions_with_gemini
from .facebook_service import post_to_facebook_page
from .scheduler_service import start_scheduler, shutdown_scheduler
from .line_service import handle_line_webhook, notify_line_post_published
from .watermark_service import apply_smart_watermark, is_watermark_enabled

@asynccontextmanager
async def lifespan(app: FastAPI):
    # เริ่มต้นฐานข้อมูล ล้างเซสชันเก่า (บังคับล็อกอินใหม่ทุกครั้ง) และรันระบบคิวตรวจโพสต์
    init_db()
    clear_all_sessions()
    start_scheduler()
    yield
    shutdown_scheduler()

app = FastAPI(title="PostEase AI", lifespan=lifespan)

# Static & Templates setup
BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- Auth Helpers (JWT Authentication) ---
def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """ตรวจสอบ JWT Token จาก Cookie หรือ Authorization Header"""
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "").strip()
    if not token:
        return None

    # ยืนยันตัวตนผ่าน JWT
    username = verify_jwt_token(token)
    if not username:
        # Fallback รองรับ session เดิม
        username = verify_session(token)
    if not username:
        return None
    return get_user_by_username(username)

def require_auth(request: Request) -> Dict[str, Any]:
    """Dependency สำหรับ API ป้องกันการเข้าถึงโดยไม่ล็อกอิน"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อนทำรายการ")
    return user

# --- Pydantic Request Models ---
class GenerateCaptionRequest(BaseModel):
    image_path: str
    page_id: str
    extra_notes: Optional[str] = ""
    category: Optional[str] = "all"

class CreatePostRequest(BaseModel):
    page_id: str
    image_path: str
    caption: str
    first_comment: Optional[str] = ""
    caption_style: Optional[str] = "แบบด่วน"
    scheduled_at: Optional[str] = None
    status: Optional[str] = "scheduled"

class UpdatePostRequest(BaseModel):
    caption: str
    scheduled_at: Optional[str] = None

class SettingsUpdateRequest(BaseModel):
    pages: List[Dict[str, Any]]
    settings: Dict[str, str]

class WatermarkSettingsRequest(BaseModel):
    watermark_enabled: bool
    watermark_position: Optional[str] = "auto"
    watermark_opacity: Optional[float] = 0.85
    watermark_scale: Optional[float] = 0.18

class WatermarkPreviewRequest(BaseModel):
    image_path: str
    position: Optional[str] = "bottom_right"
    opacity: Optional[float] = 0.85
    scale: Optional[float] = 0.18

class AutoSpreadRequest(BaseModel):
    interval_days: Optional[int] = 1
    target_hour: Optional[int] = 18
    target_minute: Optional[int] = 0

class ChangePasswordRequest(BaseModel):
    new_username: str
    current_password: str
    new_password: Optional[str] = ""

# --- Public Health Endpoint ---
@app.get("/health")
async def health_check():
    """Endpoint สำหรับ Watchdog และ Cloudflare ตรวจเช็คสถานะเซิร์ฟเวอร์"""
    return {
        "status": "ok",
        "app": "PostEase AI - ศรศิลป์ กรอบรูป",
        "timestamp": datetime.now().isoformat()
    }

# --- Authentication Web Pages ---
@app.get("/login", response_class=HTMLResponse)
async def login_page_get(request: Request, reason: Optional[str] = None):
    user = get_current_user(request)
    if user and reason != "idle":
        return RedirectResponse(url="/", status_code=303)
    
    info_message = None
    if reason == "idle":
        info_message = "⏳ เซสชันหมดอายุเนื่องจากไม่มีการขยับหรือใช้งานหน้าเว็บเกิน 1 ชั่วโมง กรุณาเข้าสู่ระบบใหม่"
    
    response = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "info": info_message}
    )
    if reason == "idle":
        response.delete_cookie(key="session_token")
    return response

class LoginApiRequest(BaseModel):
    username: str
    password: str

@app.post("/api/login")
async def api_login(req: LoginApiRequest):
    """เข้าสู่ระบบผ่าน API และรับ JWT Token (Bearer)"""
    user = get_user_by_username(req.username.strip())
    if not user or not verify_password(req.password, user["password_hash"], user["salt"]):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    token = create_jwt_token(user["username"], hours=8)
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 8 * 3600,
        "username": user["username"]
    }

@app.post("/login", response_class=HTMLResponse)
async def login_page_post(request: Request, username: str = Form(...), password: str = Form(...)):
    user = get_user_by_username(username.strip())
    if not user or not verify_password(password, user["password_hash"], user["salt"]):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง"}
        )
    
    # Login success -> สร้าง JWT Token ปลอดภัย 8 ชั่วโมง
    jwt_token = create_jwt_token(user["username"], hours=8)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="session_token",
        value=jwt_token,
        max_age=8 * 3600,
        httponly=True,
        samesite="lax"
    )
    return response

@app.get("/logout")
@app.post("/logout")
async def logout_action(request: Request, reason: Optional[str] = None):
    token = request.cookies.get("session_token")
    if token:
        delete_session(token)
    redirect_url = f"/login?reason={reason}" if reason else "/login"
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.delete_cookie(key="session_token")
    return response

# --- HTML Web Pages (Protected) ---
@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    pages = get_all_pages()
    active_page = pages[0] if pages else {"id": "slidetruck", "name": "ศรศิลป์ กรอบรูป", "icon": "🖼️"}
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "pages": pages,
            "active_page": active_page,
            "current_user": user
        }
    )

@app.get("/queue", response_class=HTMLResponse)
async def queue_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="queue.html",
        context={"current_user": user}
    )

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    pages = {p["id"]: p for p in get_all_pages()}
    p1 = pages.get("slidetruck") or (list(pages.values())[0] if pages else {})
    gemini_key = get_setting("gemini_api_key", "")
    line_token = get_setting("line_channel_token", "")
    line_secret = get_setting("line_channel_secret", "")

    fb_app_id = get_setting("facebook_app_id", "")
    fb_app_secret = get_setting("facebook_app_secret", "")

    wm_enabled = get_setting("watermark_enabled", "true").lower() in ["1", "true", "yes"]
    wm_pos = get_setting("watermark_position", "auto")
    wm_opacity = get_setting("watermark_opacity", "0.85")
    wm_scale = get_setting("watermark_scale", "0.18")

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "p1": p1,
            "gemini_api_key": gemini_key,
            "line_channel_token": line_token,
            "line_channel_secret": line_secret,
            "facebook_app_id": fb_app_id,
            "facebook_app_secret": fb_app_secret,
            "watermark_enabled": wm_enabled,
            "watermark_position": wm_pos,
            "watermark_opacity": wm_opacity,
            "watermark_scale": wm_scale,
            "current_user": user
        }
    )

# --- API Endpoints ---

@app.post("/api/change-password")
async def api_change_password(req: ChangePasswordRequest, user: Dict[str, Any] = Depends(require_auth)):
    """เปลี่ยนชื่อผู้ใช้หรือรหัสผ่านผู้ดูแลระบบ"""
    if not verify_password(req.current_password, user["password_hash"], user["salt"]):
        return {"success": False, "message": "รหัสผ่านเดิมไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง"}
    
    new_user = req.new_username.strip() if req.new_username.strip() else user["username"]
    new_pass = req.new_password.strip() if req.new_password and req.new_password.strip() else None
    
    success = update_admin_credentials(
        current_username=user["username"],
        new_username=new_user,
        new_password=new_pass
    )
    if success:
        return {"success": True, "message": "บันทึกข้อมูลบัญชีผู้ดูแลระบบเรียบร้อยแล้ว!"}
    else:
        return {"success": False, "message": "ไม่สามารถอัปเดตข้อมูลบัญชีได้"}

@app.post("/api/upload")
async def upload_image(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    user: Dict[str, Any] = Depends(require_auth)
):
    """รับไฟล์รูปภาพ (รองรับทั้งรูปเดียว และอัปโหลดเป็นชุดหลายรูป Multi-Upload)"""
    uploads_dir = os.path.join(BASE_DIR, "static", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    all_files = []
    if files:
        all_files.extend(files)
    if file and file not in all_files:
        all_files.append(file)

    if not all_files:
        raise HTTPException(status_code=400, detail="กรุณาเลือกไฟล์รูปภาพเพื่ออัปโหลด")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    uploaded_paths = []
    uploaded_filenames = []

    for idx, f in enumerate(all_files):
        clean_name = f.filename.replace(" ", "_") if f.filename else f"img_{idx}.jpg"
        safe_filename = f"{timestamp}_{idx}_{clean_name}"
        file_path = os.path.join(uploads_dir, safe_filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(f.file, buffer)

        rel_path = f"/static/uploads/{safe_filename}"
        uploaded_paths.append(rel_path)
        uploaded_filenames.append(safe_filename)

    return {
        "success": True,
        "filename": uploaded_filenames[0],
        "image_path": uploaded_paths[0],
        "image_paths": uploaded_paths,
        "filenames": uploaded_filenames,
        "count": len(uploaded_paths)
    }

@app.get("/api/watermark/settings")
async def api_get_watermark_settings(user: Dict[str, Any] = Depends(require_auth)):
    """ดึงค่าตั้งค่าลายน้ำปัจจุบัน"""
    enabled = get_setting("watermark_enabled", "true").lower() in ["1", "true", "yes"]
    pos = get_setting("watermark_position", "auto")
    try:
        opacity = float(get_setting("watermark_opacity", "0.85"))
    except Exception:
        opacity = 0.85
    try:
        scale = float(get_setting("watermark_scale", "0.18"))
    except Exception:
        scale = 0.18
    return {
        "watermark_enabled": enabled,
        "watermark_position": pos,
        "watermark_opacity": opacity,
        "watermark_scale": scale
    }

@app.post("/api/watermark/settings")
async def api_save_watermark_settings(req: WatermarkSettingsRequest, user: Dict[str, Any] = Depends(require_auth)):
    """บันทึกค่าตั้งค่าลายน้ำ"""
    set_setting("watermark_enabled", "true" if req.watermark_enabled else "false")
    if req.watermark_position:
        set_setting("watermark_position", req.watermark_position)
    if req.watermark_opacity is not None:
        set_setting("watermark_opacity", str(req.watermark_opacity))
    if req.watermark_scale is not None:
        set_setting("watermark_scale", str(req.watermark_scale))
    return {"success": True, "message": "บันทึกการตั้งค่าลายน้ำเรียบร้อยแล้ว"}

@app.post("/api/watermark/preview")
async def api_watermark_preview(req: WatermarkPreviewRequest, user: Dict[str, Any] = Depends(require_auth)):
    """ดูตัวอย่างหรือใส่ลายน้ำตามตำแหน่งที่เลือกบนหน้าเว็บ"""
    clean_path = req.image_path.split("?")[0]
    full_img_path = clean_path
    if clean_path.startswith("/static/"):
        full_img_path = os.path.join(BASE_DIR, clean_path.lstrip("/"))

    wm_res = apply_smart_watermark(
        image_path=full_img_path,
        position=req.position or "bottom_right",
        scale=req.scale or 0.18,
        opacity=req.opacity or 0.85
    )

    if wm_res and "static" in wm_res:
        fn = os.path.basename(wm_res)
        return {"success": True, "watermarked_image_path": f"/static/uploads/{fn}"}
    return {"success": False, "watermarked_image_path": clean_path}

@app.post("/api/posts/auto-spread")
async def api_auto_spread_posts(req: AutoSpreadRequest, user: Dict[str, Any] = Depends(require_auth)):
    """จัดตารางกระจายคิวโพสต์ที่รอเวลาอยู่ ให้ทยอยโพสต์วันละ 1 โพสต์ เวลา 18:00 น."""
    updated = auto_spread_scheduled_posts(
        interval_days=req.interval_days or 1,
        target_hour=req.target_hour or 18,
        target_minute=req.target_minute or 0
    )
    return {
        "success": True,
        "updated_count": len(updated),
        "message": f"จัดตารางกระจายคิว {len(updated)} โพสต์ เรียบร้อยแล้ว (ปล่อยวันละ 1 โพสต์ เวลา 18:00 น.)",
        "posts": updated
    }

@app.post("/api/generate-captions")
async def api_generate_captions(req: GenerateCaptionRequest, user: Dict[str, Any] = Depends(require_auth)):
    """ส่งรูปให้ AI Gemini สแกนและแต่งแคปชัน 3 สไตล์ พร้อมใส่ลายน้ำอัจฉริยะ"""
    full_img_path = req.image_path
    if req.image_path.startswith("/static/"):
        full_img_path = os.path.join(BASE_DIR, req.image_path.lstrip("/"))

    result = generate_captions_with_gemini(
        image_path=full_img_path,
        page_id=req.page_id,
        extra_notes=req.extra_notes or "",
        category=req.category or "all"
    )

    # ประทับลายน้ำตามมุมที่ AI วิเคราะห์ว่าว่างและเหมาะสม
    wm_pos = result.get("watermark_position", "bottom_right")
    wm_res = apply_smart_watermark(full_img_path, position=wm_pos)

    # แปลงกลับเป็น URL สำหรับฝั่งหน้าบ้าน
    if wm_res and "static" in wm_res:
        fn = os.path.basename(wm_res)
        result["watermarked_image_path"] = f"/static/uploads/{fn}"
    else:
        result["watermarked_image_path"] = req.image_path

    return result

@app.get("/api/pages")
async def api_get_pages(user: Dict[str, Any] = Depends(require_auth)):
    """ดึงรายชื่อเพจทั้งหมดพร้อมข้อมูลติดต่อ"""
    return get_all_pages()

@app.get("/api/posts")
async def api_get_posts(status: Optional[str] = "all", page_id: Optional[str] = "all", user: Dict[str, Any] = Depends(require_auth)):
    """ดึงรายการโพสต์ตามฟิลเตอร์"""
    posts = get_all_posts(status_filter=status, page_filter=page_id)
    for p in posts:
        if p.get("image_path") and "uploads" in p["image_path"]:
            # ถ้าเป็น JSON list ของรูปภาพหลายรูป
            raw_path = p["image_path"]
            if raw_path.startswith("[") and raw_path.endswith("]"):
                try:
                    p_list = json.loads(raw_path)
                    p["images"] = p_list
                    p["image_path"] = p_list[0] if p_list else ""
                except Exception:
                    pass
            else:
                fn = os.path.basename(p["image_path"])
                p["image_path"] = f"/static/uploads/{fn}"
                p["images"] = [p["image_path"]]
    return posts

@app.post("/api/posts")
async def api_create_post(req: CreatePostRequest, user: Dict[str, Any] = Depends(require_auth)):
    """บันทึกโพสต์เข้าคิว หรือสั่งโพสต์ทันที"""
    full_img_path = req.image_path
    if req.image_path.startswith("/static/"):
        full_img_path = os.path.join(BASE_DIR, req.image_path.lstrip("/"))

    # ถ้าเลือกโพสต์ทันที
    if req.status == "published":
        page = get_page(req.page_id) or {}
        fb_page_id = page.get("facebook_page_id", "")
        fb_token = page.get("facebook_access_token", "")

        res = post_to_facebook_page(
            page_id=fb_page_id,
            access_token=fb_token,
            image_path=full_img_path,
            caption=req.caption,
            first_comment=req.first_comment or ""
        )

        if not res.get("success"):
            err_msg = res.get("error", "Failed to publish to Facebook")
            post_id = create_post(
                page_id=req.page_id,
                image_path=req.image_path,
                caption=req.caption,
                first_comment=req.first_comment or "",
                caption_style=req.caption_style or "แบบด่วน",
                scheduled_at=None,
                status="failed"
            )
            update_post_status(post_id, "failed", error_message=err_msg)
            return {
                "success": False,
                "error": f"Facebook แจ้งเตือน: {err_msg}"
            }

        fb_post_id = res.get("post_id", "")
        post_id = create_post(
            page_id=req.page_id,
            image_path=req.image_path,
            caption=req.caption,
            first_comment=req.first_comment or "",
            caption_style=req.caption_style or "แบบด่วน",
            scheduled_at=None,
            status="published"
        )
        update_post_status(post_id, "published", fb_post_id=fb_post_id)

        # ยิงแจ้งเตือนเข้า LINE บอททันที
        try:
            created_post = get_post(post_id)
            if created_post:
                notify_line_post_published(created_post, fb_post_id)
        except Exception as n_err:
            print(f"[LINE Notify Warning] {n_err}")

        return {
            "success": True,
            "post_id": post_id,
            "message": f"โพสต์ขึ้นเพจสำเร็จเรียบร้อย! ({res.get('message')})"
        }
    else:
        # ตั้งเวลาล่วงหน้า
        sched_time = req.scheduled_at.replace("T", " ") if req.scheduled_at else None
        post_id = create_post(
            page_id=req.page_id,
            image_path=req.image_path,
            caption=req.caption,
            first_comment=req.first_comment or "",
            caption_style=req.caption_style or "แบบด่วน",
            scheduled_at=sched_time,
            status="scheduled"
        )
        return {
            "success": True,
            "post_id": post_id,
            "message": f"ตั้งเวลาโพสต์สำเร็จ! ระบบจะปล่อยโพสต์เวลา {sched_time}"
        }

@app.put("/api/posts/{post_id}")
async def api_update_post(post_id: int, req: UpdatePostRequest, user: Dict[str, Any] = Depends(require_auth)):
    sched_time = req.scheduled_at.replace("T", " ") if req.scheduled_at else None
    update_post_details(post_id, req.caption, sched_time)
    return {"success": True, "message": "อัปเดตโพสต์เรียบร้อย"}

@app.delete("/api/posts/{post_id}")
async def api_delete_post(post_id: int, user: Dict[str, Any] = Depends(require_auth)):
    delete_post(post_id)
    return {"success": True, "message": "ลบโพสต์เรียบร้อย"}

@app.post("/api/posts/{post_id}/post-now")
async def api_post_now(post_id: int, user: Dict[str, Any] = Depends(require_auth)):
    """สั่งให้โพสต์ที่รอคิวอยู่ โพสต์ทันทีไม่ต้องรอเวลา"""
    post = get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    full_img_path = post["image_path"]
    if full_img_path.startswith("/static/"):
        full_img_path = os.path.join(BASE_DIR, full_img_path.lstrip("/"))

    page = get_page(post["page_id"]) or {}
    fb_page_id = page.get("facebook_page_id", "")
    fb_token = page.get("facebook_access_token", "")

    res = post_to_facebook_page(
        page_id=fb_page_id,
        access_token=fb_token,
        image_path=full_img_path,
        caption=post["caption"],
        first_comment=post.get("first_comment", "")
    )

    if res.get("success"):
        fb_post_id = res.get("post_id", "")
        update_post_status(post_id, "published", fb_post_id=fb_post_id)
        # แจ้งเตือนเข้า LINE บอท
        try:
            notify_line_post_published(post, fb_post_id)
        except Exception as n_err:
            print(f"[LINE Notify Warning] {n_err}")
        return {"success": True, "message": "โพสต์ขึ้นเพจเรียบร้อยแล้ว!"}
    else:
        err = res.get("error", "Error")
        update_post_status(post_id, "failed", error_message=err)
        return {"success": False, "message": f"เกิดข้อผิดพลาด: {err}"}

@app.post("/api/settings")
async def api_save_settings(req: SettingsUpdateRequest, user: Dict[str, Any] = Depends(require_auth)):
    """บันทึกการตั้งค่า Token และข้อมูลเพจ"""
    app_id = req.settings.get("facebook_app_id") or get_setting("facebook_app_id", "")
    app_secret = req.settings.get("facebook_app_secret") or get_setting("facebook_app_secret", "")

    for p in req.pages:
        if p.get("id") == "pigfeed":
            continue
        existing_page = get_page(p["id"]) or {}
        token = p.get("facebook_access_token", "").strip()
        if not token and existing_page.get("facebook_access_token"):
            token = existing_page["facebook_access_token"]

        fb_page_id = p.get("facebook_page_id", "").strip()
        if not fb_page_id and existing_page.get("facebook_page_id"):
            fb_page_id = existing_page["facebook_page_id"]
        
        # ลองอัปเกรดเป็น Permanent Token อัตโนมัติถ้ามี App ID + Secret
        if token and app_id and app_secret and fb_page_id:
            from .facebook_service import exchange_for_never_expiring_page_token
            res = exchange_for_never_expiring_page_token(token, app_id, app_secret, fb_page_id)
            if res.get("success") and res.get("permanent_page_token"):
                token = res["permanent_page_token"]

        update_page(
            page_id=p["id"],
            fb_page_id=fb_page_id,
            fb_token=token,
            phone=p.get("phone", ""),
            line_id=p.get("line_id", ""),
            service_area=p.get("service_area", ""),
            name=p.get("name"),
            icon=p.get("icon")
        )

    for k, v in req.settings.items():
        val = str(v).strip()
        if val or not get_setting(k, ""):
            set_setting(k, val)

    return {"success": True, "message": "บันทึกการตั้งค่าทั้งหมดเรียบร้อย"}

@app.post("/api/line/webhook")
async def api_line_webhook(request: Request, x_line_signature: Optional[str] = Header(None)):
    """Webhook รองรับบอท LINE"""
    body = await request.body()
    body_str = body.decode("utf-8")
    return handle_line_webhook(body_str, x_line_signature or "")

# --- System Health & Diagnostics ---
@app.get("/api/system/health")
async def api_system_health(user: Dict[str, Any] = Depends(require_auth)):
    """ตรวจสอบสถานะสุขภาพของทุกเซอร์วิส (Facebook, Gemini AI, LINE Bot, Public Tunnel)"""
    import httpx
    import asyncio
    import time

    results = {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Facebook Token
        try:
            p = get_page("slidetruck") or {}
            fb_token = p.get("facebook_access_token", "").strip()
            fb_pid = p.get("facebook_page_id", "").strip()
            if fb_token and fb_pid:
                t0 = time.time()
                r = await client.get(f"https://graph.facebook.com/v19.0/{fb_pid}?fields=id,name&access_token={fb_token}")
                lat = int((time.time() - t0) * 1000)
                if r.status_code == 200:
                    data = r.json()
                    results["facebook"] = {
                        "ok": True,
                        "latency_ms": lat,
                        "page_name": data.get("name", "ศรศิลป์ กรอบรูป"),
                        "page_id": data.get("id"),
                        "message": "เชื่อมต่อสมบูรณ์ (Permanent Page Token พร้อมโพสต์)"
                    }
                else:
                    err = r.json().get("error", {}).get("message", "Token error")
                    results["facebook"] = {"ok": False, "message": f"Token ไม่ถูกต้องหรือหมดอายุ: {err}"}
            else:
                results["facebook"] = {"ok": False, "message": "ยังไม่ได้ตั้งค่า Facebook Page ID หรือ Token"}
        except Exception as e:
            results["facebook"] = {"ok": False, "message": f"ทดสอบเชื่อมต่อล้มเหลว: {str(e)}"}

        # 2. Gemini AI Key
        try:
            from .gemini_service import chat_with_gemini_copilot
            t0 = time.time()
            res = await asyncio.to_thread(chat_with_gemini_copilot, [], "Ping")
            lat = int((time.time() - t0) * 1000)
            if res.get("reply_text"):
                results["gemini"] = {
                    "ok": True,
                    "latency_ms": lat,
                    "message": "AI พร้อมใช้งานและตอบสนองได้รวดเร็วปกติ"
                }
            else:
                results["gemini"] = {"ok": False, "message": "AI ไม่ตอบสนองข้อความ"}
        except Exception as e:
            results["gemini"] = {"ok": False, "message": f"Gemini API ขัดข้อง: {str(e)}"}

        # 3. LINE Bot Token
        try:
            line_token = get_setting("line_channel_token", "").strip()
            if line_token:
                t0 = time.time()
                r = await client.get("https://api.line.me/v2/bot/info", headers={"Authorization": f"Bearer {line_token}"})
                lat = int((time.time() - t0) * 1000)
                if r.status_code == 200:
                    b_info = r.json()
                    results["line"] = {
                        "ok": True,
                        "latency_ms": lat,
                        "bot_name": b_info.get("displayName"),
                        "basic_id": b_info.get("basicId"),
                        "message": f"บอท {b_info.get('displayName')} ({b_info.get('basicId')}) พร้อมรับส่งข้อมูล"
                    }
                else:
                    results["line"] = {"ok": False, "message": "LINE Token ไม่ถูกต้องหรือถูกเพิกถอน"}
            else:
                results["line"] = {"ok": False, "message": "ยังไม่ได้ใส่ LINE Channel Token"}
        except Exception as e:
            results["line"] = {"ok": False, "message": f"LINE API ขัดข้อง: {str(e)}"}

        # 4. Public Tunnel / Webhook URL (Non-blocking async request prevents deadlock)
        try:
            pub_url = get_setting("public_url", "").strip()
            if pub_url and pub_url.startswith("http"):
                t0 = time.time()
                r = await client.get(f"{pub_url}/health")
                lat = int((time.time() - t0) * 1000)
                if r.status_code == 200:
                    results["tunnel"] = {
                        "ok": True,
                        "latency_ms": lat,
                        "url": pub_url,
                        "message": "ออนไลน์สมบูรณ์ (คนนอกและ LINE เข้าถึงได้จริง)"
                    }
                else:
                    results["tunnel"] = {"ok": False, "url": pub_url, "message": f"ตอบกลับสถานะ HTTP {r.status_code}"}
            else:
                results["tunnel"] = {"ok": False, "url": "", "message": "ยังไม่ได้เปิด Tunnel หรือไม่พบ Public URL ในระบบ"}
        except Exception as e:
            results["tunnel"] = {"ok": False, "url": get_setting("public_url", ""), "message": f"ไม่สามารถเข้าถึงได้จากภายนอก: {str(e)}"}

    return {"success": True, "results": results}

# --- Database 1-Click Backup ---
@app.get("/api/backup/download")
async def api_download_backup(user: Dict[str, Any] = Depends(require_auth)):
    """ดาวน์โหลดไฟล์ฐานข้อมูล poster.db สำรองเก็บไว้ในเครื่อง"""
    from .database import DB_PATH
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ฐานข้อมูล")
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    download_filename = f"sornsiri_database_backup_{ts}.db"
    return FileResponse(
        path=DB_PATH,
        filename=download_filename,
        media_type="application/octet-stream"
    )
