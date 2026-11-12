import os
import re
from PIL import Image, ImageEnhance, ImageDraw
from typing import Tuple
from .database import get_setting

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
STATIC_DIR = os.path.join(BASE_DIR, "static")
DEFAULT_WATERMARK = os.path.join(STATIC_DIR, "watermark_translucent.png")
FALLBACK_WATERMARK = os.path.join(STATIC_DIR, "logo_original.png")

def is_watermark_enabled() -> bool:
    """ตรวจสอบการตั้งค่าเปิด/ปิดลายน้ำ (ค่าเริ่มต้นคือเปิดใช้งาน '1')"""
    val = get_setting("watermark_enabled", "1")
    return val in ["1", "true", "True", True]

def prepare_watermark_asset() -> str:
    """เตรียมไฟล์ลายน้ำมุมมนแบบโปร่งแสงสวยงาม หากยังไม่มีให้สร้างขึ้นอัตโนมัติ"""
    if os.path.exists(DEFAULT_WATERMARK):
        return DEFAULT_WATERMARK

    if not os.path.exists(FALLBACK_WATERMARK):
        return ""

    try:
        orig = Image.open(FALLBACK_WATERMARK).convert("RGBA")
        w, h = orig.size
        radius = int(w * 0.08)
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, w, h], radius=radius, fill=255)

        # แปลงให้พื้นหลังสีขาวโปร่งแสงเนียนๆ แต่เส้นสีดำยังคงคมชัด
        datas = list(orig.getdata())
        new_data = []
        for item in datas:
            r, g, b, a = item
            if r > 230 and g > 230 and b > 230:
                new_data.append((255, 255, 255, 180))
            else:
                new_data.append((r, g, b, 235))

        badge = Image.new("RGBA", (w, h))
        badge.putdata(new_data)
        badge.putalpha(mask)
        badge.save(DEFAULT_WATERMARK, "PNG")
        return DEFAULT_WATERMARK
    except Exception as e:
        print(f"Error preparing watermark asset: {e}")
        return FALLBACK_WATERMARK

def calculate_watermark_position(base_w: int, base_h: int, wm_w: int, wm_h: int, position: str) -> Tuple[int, int]:
    """คำนวณพิกัด (X, Y) สำหรับแต่ละมุมของภาพ"""
    margin_x = int(base_w * 0.035)
    margin_y = int(base_h * 0.035)

    pos = (position or "").lower().strip()
    if pos == "bottom_left":
        return (margin_x, base_h - wm_h - margin_y)
    elif pos == "top_right":
        return (base_w - wm_w - margin_x, margin_y)
    elif pos == "top_left":
        return (margin_x, margin_y)
    else: # default: bottom_right
        return (base_w - wm_w - margin_x, base_h - wm_h - margin_y)

def apply_smart_watermark(image_path: str, position: str = "bottom_right", scale: float = 0.18, opacity: float = 0.90) -> str:
    """
    ประทับลายน้ำโลโก้ลงบนรูปภาพตามตำแหน่งที่ AI วิเคราะห์ (bottom_right, bottom_left, top_right, top_left)
    และบันทึกเป็นไฟล์ใหม่ _wm.jpg เพื่อไม่ให้ทับไฟล์ต้นฉบับ
    ส่งคืน: path ของรูปภาพที่ติดลายน้ำแล้ว
    """
    if not is_watermark_enabled():
        return image_path

    # แปลง path สัมพัทธ์ให้เป็น path เต็ม
    full_image_path = None
    if os.path.exists(image_path):
        full_image_path = os.path.abspath(image_path)
    else:
        clean_rel = image_path.lstrip("/\\").replace("/", os.sep)
        cand1 = os.path.join(PROJECT_ROOT, clean_rel)
        cand2 = os.path.join(BASE_DIR, clean_rel)
        if os.path.exists(cand1):
            full_image_path = cand1
        elif os.path.exists(cand2):
            full_image_path = cand2

    if not full_image_path or not os.path.exists(full_image_path):
        return image_path

    # ถ้าไฟล์ที่ส่งมามีลายน้ำเดิมอยู่แล้ว ให้หาไฟล์ต้นฉบับที่แท้จริง
    dir_name = os.path.dirname(full_image_path)
    base_name, file_ext = os.path.splitext(os.path.basename(full_image_path))
    clean_base = re.sub(r'_wm(_[a-z_]+)?$', '', base_name)
    for ext in [file_ext, '.jpg', '.jpeg', '.png', '.webp', '.JPG', '.PNG']:
        orig_cand = os.path.join(dir_name, clean_base + ext)
        if os.path.exists(orig_cand):
            full_image_path = orig_cand
            break

    wm_asset = prepare_watermark_asset()
    if not wm_asset or not os.path.exists(wm_asset):
        return image_path

    try:
        # เปิดรูปภาพต้นฉบับ
        base_img = Image.open(full_image_path).convert("RGBA")
        bw, bh = base_img.size

        # ปรับขนาดลายน้ำให้เหมาะสมกับรูปภาพ (ประมาณ 18-20% ของความกว้างภาพ)
        wm_img = Image.open(wm_asset).convert("RGBA")
        target_w = max(int(bw * scale), 120)
        target_h = int(target_w * (wm_img.height / wm_img.width))
        wm_resized = wm_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # ปรับความโปร่งแสงตามค่า opacity
        if opacity < 1.0:
            alpha = wm_resized.split()[3]
            alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
            wm_resized.putalpha(alpha)

        # จัดการตำแหน่ง
        norm_pos = (position or "bottom_right").lower().strip()
        if norm_pos not in ["bottom_right", "bottom_left", "top_right", "top_left"]:
            norm_pos = "bottom_right"

        # คำนวณตำแหน่งที่วาง
        xy = calculate_watermark_position(bw, bh, target_w, target_h, norm_pos)

        # แปะลายน้ำลงบนรูปภาพ
        base_img.paste(wm_resized, xy, wm_resized)

        # สร้างชื่อไฟล์ผลลัพธ์แยกตามตำแหน่ง เพื่อไม่ให้ชนแคชเบราว์เซอร์
        out_filename = f"{clean_base}_wm_{norm_pos}.jpg"
        out_full_path = os.path.join(dir_name, out_filename)

        # บันทึกเป็นไฟล์ JPG คุณภาพสูง 95%
        base_img.convert("RGB").save(out_full_path, "JPEG", quality=95)

        # ส่งคืน path สำหรับเว็บ
        return f"/static/uploads/{out_filename}"

    except Exception as e:
        print(f"Error applying watermark: {e}")
        return image_path
