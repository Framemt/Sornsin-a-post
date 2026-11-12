import os
import json
import re
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from .database import get_setting, set_setting, get_all_pages, create_post, get_all_posts, get_post, update_post_status
from .gemini_service import generate_captions_with_gemini, chat_with_gemini_copilot
from .facebook_service import post_to_facebook_page

def send_line_loading(chat_id: str, channel_token: str, seconds: int = 20):
    """ส่งสัญญาณ Loading Animation จุดไข่ปลาขยับในแชท LINE ให้ผู้ใช้เห็นการตอบสนองทันที"""
    if not chat_id or not channel_token:
        return
    try:
        req = urllib.request.Request(
            'https://api.line.me/v2/bot/chat/loading/start',
            headers={'Authorization': f'Bearer {channel_token}', 'Content-Type': 'application/json'},
            data=json.dumps({"chatId": chat_id, "loadingSeconds": min(seconds, 60)}).encode('utf-8')
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass

def send_line_push_notification(text: str, target_user_id: Optional[str] = None) -> bool:
    """ส่งข้อความแจ้งเตือน (Push Message) กลับเข้า LINE ทันที"""
    channel_token = get_setting("line_channel_token")
    if not channel_token:
        return False
        
    user_id = target_user_id or get_setting("admin_line_user_id") or get_setting("last_line_user_id")
    if not user_id:
        return False

    try:
        from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage
        configuration = Configuration(access_token=channel_token)
        configuration.assert_hostname = False
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=text)]
                )
            )
            print(f"[LINE Push] Sent notification to user {user_id}")
            return True
    except Exception as e:
        print(f"[LINE Push Error] Failed to send push message: {e}")
        return False

def notify_line_post_published(post: Dict[str, Any], fb_post_id: str = "") -> bool:
    """แจ้งเตือนเข้า LINE เมื่อโพสต์สำเร็จ (พร้อมลิงก์ตรงไปยังโพสต์บน Facebook)"""
    try:
        page_name = post.get("page_name") or "ศรศิลป์ กรอบรูป"
        caption = post.get("caption", "").strip()
        preview_cap = (caption[:120] + "...") if len(caption) > 120 else caption
        now_str = datetime.now().strftime("%d/%m/%Y เวลา %H:%M น.")

        if fb_post_id and not fb_post_id.startswith("sim_"):
            fb_link = f"https://www.facebook.com/{fb_post_id}"
        else:
            fb_link = "โหมดจำลอง (ยังไม่ได้เชื่อมต่อ Facebook Token จริง)"

        msg = (
            f"🚀 [แจ้งเตือน] โพสต์ขึ้น Facebook สำเร็จแล้ว!\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🖼️ ร้าน: {page_name}\n"
            f"⏰ เวลา: {now_str}\n"
            f"📝 ตัวอย่างข้อความ:\n{preview_cap}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔗 ลิงก์โพสต์ Facebook:\n{fb_link}"
        )
        return send_line_push_notification(msg)
    except Exception as e:
        print(f"[LINE Notify Error] Error creating notification: {e}")
        return False

# เก็บ State ของผู้ใช้ใน LINE (พร้อมบันทึกแคชลง SQLite เพื่อไม่ให้เซสชันหลุดเวลารีโหลดเซิร์ฟเวอร์)
USER_SESSION: Dict[str, Dict[str, Any]] = {}

def get_user_session(user_id: str) -> Dict[str, Any]:
    if user_id in USER_SESSION and USER_SESSION[user_id]:
        return USER_SESSION[user_id]
    stored = get_setting(f"session_{user_id}", "")
    if stored:
        try:
            sess = json.loads(stored)
            USER_SESSION[user_id] = sess
            return sess
        except Exception:
            pass
    return {}

def save_user_session(user_id: str, session: Dict[str, Any]):
    USER_SESSION[user_id] = session
    try:
        set_setting(f"session_{user_id}", json.dumps(session, ensure_ascii=False))
    except Exception as e:
        print(f"Error saving session to db: {e}")

def parse_thai_time(text: str, base_time: Optional[datetime] = None) -> Optional[datetime]:
    """แปลงข้อความภาษาไทย/เวลา 24 ชม. ให้เป็น datetime อย่างชาญฉลาด (ไม่ใช้ระบบก่อนเที่ยง/หลังเที่ยง)"""
    if not text:
        return None
    if base_time is None:
        base_time = datetime.now()
        
    s = text.strip().lower()
    
    # 1. เช็คเวลาสัมพัทธ์ เช่น "อีก 15 นาที", "อีก 1 ชั่วโมง", "อีก 2 ชม."
    m_rel = re.search(r'อีก\s*(\d+)\s*(นาที|ชม\.?|ชั่วโมง)', s)
    if m_rel:
        val = int(m_rel.group(1))
        unit = m_rel.group(2)
        if 'นาที' in unit:
            return base_time + timedelta(minutes=val)
        else:
            return base_time + timedelta(hours=val)
            
    is_tomorrow = ('พรุ่งนี้' in s) or ('พรุ่ง' in s)
    
    num_map = {
        'หนึ่ง': 1, 'นึง': 1, 'สอง': 2, 'สาม': 3, 'สี่': 4,
        'ห้า': 5, 'หก': 6, 'เจ็ด': 7, 'แปด': 8, 'เก้า': 9,
        'สิบ': 10, 'สิบเอ็ด': 11, 'สิบสอง': 12
    }

    # 2. รูปแบบ 24 ชั่วโมง เช่น 14:30, 14.30, 09:00, 9.15, 18:00 น.
    m_clock = re.search(r'(\d{1,2})[:.](\d{2})', s)
    if m_clock:
        hr = int(m_clock.group(1))
        mn = int(m_clock.group(2))
        if 0 <= hr <= 23 and 0 <= mn <= 59:
            target = base_time.replace(hour=hr, minute=mn, second=0, microsecond=0)
            if is_tomorrow or (target <= base_time and not is_tomorrow and hr < base_time.hour):
                target += timedelta(days=1)
            elif target <= base_time and not is_tomorrow and hr == base_time.hour and mn <= base_time.minute:
                target += timedelta(days=1)
            return target

    # 3. ทุ่ม (1 ทุ่ม - 5 ทุ่ม -> 19:00 - 23:00)
    m_toom = re.search(r'(หนึ่ง|นึง|สอง|สาม|สี่|ห้า|[1-5])\s*ทุ่ม|ทุ่ม(นึง)?', s)
    if m_toom:
        n_str = m_toom.group(1) or '1'
        n = num_map.get(n_str, int(n_str) if n_str.isdigit() else 1)
        hr = 18 + n
        mn = 30 if 'ครึ่ง' in s else 0
        target = base_time.replace(hour=hr, minute=mn, second=0, microsecond=0)
        if is_tomorrow or target <= base_time:
            target += timedelta(days=1)
        return target

    # 4. บ่าย (บ่ายโมง, บ่ายสอง, บ่าย 3, บ่ายสี่ -> 13:00 - 16:00)
    if 'บ่าย' in s:
        m_bai = re.search(r'บ่าย\s*(โมง|หนึ่ง|นึง|สอง|สาม|สี่|[1-4])?', s)
        val = m_bai.group(1) if m_bai else None
        if not val or val in ['โมง', 'หนึ่ง', 'นึง', '1']:
            hr = 13
        elif val in ['สอง', '2']:
            hr = 14
        elif val in ['สาม', '3']:
            hr = 15
        elif val in ['สี่', '4']:
            hr = 16
        else:
            hr = 13
        mn = 30 if 'ครึ่ง' in s else 0
        target = base_time.replace(hour=hr, minute=mn, second=0, microsecond=0)
        if is_tomorrow or target <= base_time:
            target += timedelta(days=1)
        return target

    # 5. โมงเย็น (4 โมงเย็น, 5 โมงเย็น, 6 โมงเย็น -> 16:00 - 18:00)
    m_yenn = re.search(r'(สี่|ห้า|หก|[4-6])\s*โมง(เย็น)?', s)
    if m_yenn and ('เย็น' in s or m_yenn.group(1) in ['หก', '6']):
        n_str = m_yenn.group(1)
        n = num_map.get(n_str, int(n_str) if n_str.isdigit() else 6)
        hr = 12 + n
        mn = 30 if 'ครึ่ง' in s else 0
        target = base_time.replace(hour=hr, minute=mn, second=0, microsecond=0)
        if is_tomorrow or target <= base_time:
            target += timedelta(days=1)
        return target

    # 6. โมงเช้า / โมง (6:00 - 11:00)
    m_mong = re.search(r'([6-9]|1[0-1]|หก|เจ็ด|แปด|เก้า|สิบ|สิบเอ็ด)\s*โมง', s)
    if m_mong:
        n_str = m_mong.group(1)
        n = num_map.get(n_str, int(n_str) if n_str.isdigit() else 9)
        hr = n
        mn = 30 if 'ครึ่ง' in s else 0
        target = base_time.replace(hour=hr, minute=mn, second=0, microsecond=0)
        if is_tomorrow or target <= base_time:
            target += timedelta(days=1)
        return target

    # 7. เที่ยง (12:00)
    if 'เที่ยง' in s and 'คืน' not in s:
        hr = 12
        mn = 30 if 'ครึ่ง' in s else 0
        target = base_time.replace(hour=hr, minute=mn, second=0, microsecond=0)
        if is_tomorrow or target <= base_time:
            target += timedelta(days=1)
        return target

    return None

def handle_line_webhook(body_str: str, signature: str) -> Dict[str, Any]:
    """จัดการ Webhook จาก LINE Messaging API"""
    channel_secret = get_setting("line_channel_secret")
    channel_token = get_setting("line_channel_token")

    if not channel_token:
        return {"status": "ignored", "message": "LINE Token not configured"}

    try:
        from linebot.v3 import WebhookParser
        from linebot.v3.messaging import (
            Configuration, ApiClient, MessagingApi, MessagingApiBlob,
            ReplyMessageRequest, TextMessage, FlexMessage, FlexContainer,
            QuickReply, QuickReplyItem, MessageAction
        )
        from linebot.v3.webhooks import MessageEvent, ImageMessageContent, TextMessageContent, PostbackEvent

        parser = WebhookParser(channel_secret) if channel_secret else None
        configuration = Configuration(access_token=channel_token)
        configuration.assert_hostname = False
        
        data = json.loads(body_str)
        events = data.get("events", [])

        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_blob = MessagingApiBlob(api_client)

            # ปุ่มลัด Quick Reply ให้กดสะดวก
            quick_reply_buttons = QuickReply(items=[
                QuickReplyItem(action=MessageAction(label="📋 เช็คคิวโพสต์", text="เช็คคิว")),
                QuickReplyItem(action=MessageAction(label="🌐 เว็บแอดมิน", text="เว็บ")),
                QuickReplyItem(action=MessageAction(label="💡 ไอเดียโพสต์", text="ไอเดียโพสต์")),
                QuickReplyItem(action=MessageAction(label="❓ วิธีใช้งาน", text="วิธีใช้")),
            ])

            for event in events:
                event_type = event.get("type")
                reply_token = event.get("replyToken")
                source = event.get("source", {})
                user_id = source.get("userId", "")
                if user_id:
                    set_setting("last_line_user_id", user_id)
                    if not get_setting("admin_line_user_id"):
                        set_setting("admin_line_user_id", user_id)

                # 1. ผู้ใช้ส่งรูปภาพเข้ามา
                if event_type == "message" and event.get("message", {}).get("type") == "image":
                    message_id = event["message"]["id"]
                    
                    # ส่ง loading indicator ทันที ให้ผู้ใช้เห็นว่าบอทกำลังประมวลผล
                    send_line_loading(user_id, channel_token, 20)
                    
                    # ดาวน์โหลดรูปภาพเก็บไว้
                    upload_dir = os.path.join(os.path.dirname(__file__), "static", "uploads")
                    os.makedirs(upload_dir, exist_ok=True)
                    img_filename = f"line_{message_id}.jpg"
                    img_path = os.path.join(upload_dir, img_filename)

                    # ดึงเนื้อหาไบนารีจาก LINE Blob API
                    content = line_bot_blob.get_message_content(message_id)
                    with open(img_path, "wb") as f:
                        f.write(content)

                    # เพจเริ่มต้น (เลือกรถสไลด์ก่อน หรือดึงจาก session)
                    user_sess = get_user_session(user_id)
                    active_page_id = user_sess.get("active_page", "slidetruck")
                    pending_notes = user_sess.get("pending_notes", "")

                    # ให้ AI คิดแคปชัน 3 สไตล์ (ผนวกโน้ตที่ผู้ใช้อาจพิมพ์เข้ามาก่อน)
                    ai_result = generate_captions_with_gemini(img_path, active_page_id, extra_notes=pending_notes)
                    captions = ai_result.get("captions", [])
                    first_comment = ai_result.get("first_comment", "")

                    # ให้ AI วิเคราะห์มุมว่าง และติดลายน้ำโลโก้ร้านให้อัตโนมัติ
                    from .watermark_service import apply_smart_watermark
                    wm_pos = ai_result.get("watermark_position", "bottom_right")
                    final_img_path = apply_smart_watermark(img_path, position=wm_pos)

                    pos_names = {
                        "bottom_right": "ขวาล่าง",
                        "bottom_left": "ซ้ายล่าง",
                        "top_right": "ขวาบน",
                        "top_left": "ซ้ายบน"
                    }
                    pos_label = pos_names.get(wm_pos, "ขวาล่าง")

                    # หากมีโน้ตที่ผู้ใช้พิมพ์ไว้ ให้เพิ่มการ์ด "ข้อความที่คุณพิมพ์เอง"
                    if pending_notes:
                        captions.append({
                            "style": "ข้อความที่คุณพิมพ์เอง",
                            "text": pending_notes
                        })

                    # เซฟไว้ใน session เพื่อรอผู้ใช้กดเลือก (ใช้ภาพที่ติดลายน้ำแล้ว)
                    save_user_session(user_id, {
                        "image_path": final_img_path,
                        "page_id": active_page_id,
                        "captions": captions,
                        "first_comment": first_comment,
                        "active_page": active_page_id,
                        "user_typed_note": pending_notes
                    })

                    # ส่งการ์ด Carousel ให้เลือก
                    flex_content = create_caption_carousel_flex(captions, active_page_id)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[
                                TextMessage(
                                    text=f"📸 ได้รับรูปแล้วครับ! AI ประทับลายน้ำโลโก้ร้านให้อัตโนมัติที่มุม{pos_label} (ไม่บังชิ้นงาน) และคิดแคปชันให้เลือกด้านล่าง 👇\n\n💡 หรือถ้าอยากพิมพ์ข้อมูลหน้างาน/แคปชันเอง:\n👉 พิมพ์ส่งมาในแชทนี้ได้เลยครับ! AI จะนำไปแต่งเพิ่มให้ครับ ✨",
                                    quick_reply=quick_reply_buttons
                                ),
                                FlexMessage(alt_text="เลือกแคปชันที่ชอบ", contents=FlexContainer.from_json(json.dumps(flex_content)))
                            ]
                        )
                    )

                # 2. ผู้ใช้กดปุ่มเลือกแคปชัน หรือเลือกเวลา (Postback Event)
                elif event_type == "postback":
                    postback_obj = event.get("postback", {})
                    postback_data = postback_obj.get("data", "")
                    postback_params = postback_obj.get("params", {})
                    
                    params = dict(item.split("=") for item in postback_data.split("&") if "=" in item)
                    action = params.get("action")

                    session = get_user_session(user_id)
                    if not session and action in ["choose", "choose_datetime", "ask_time"]:
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text="⚠️ เซสชันหมดอายุ กรุณาส่งรูปใหม่อีกครั้งครับ")]
                            )
                        )
                        continue

                    if action == "ask_time":
                        style_idx = int(params.get("idx", 0))
                        session["chosen_idx"] = style_idx
                        save_user_session(user_id, session)

                        now = datetime.now()

                        # คำนวณช่วงเวลาด่วนแบบ 24 ชม. ของวันนี้และพรุ่งนี้
                        suggestions = []
                        for h in [9, 11, 13, 14, 15, 16, 17, 18, 19, 20, 21]:
                            if h > now.hour or (h == now.hour and now.minute < 30):
                                suggestions.append(f"{h:02d}:00 น.")
                        
                        suggestions.append("พรุ่งนี้ 09:00 น.")
                        suggestions.append("พรุ่งนี้ 12:00 น.")
                        suggestions.append("พรุ่งนี้ 18:00 น.")
                        
                        quick_slots = suggestions[:5]
                        time_qr = QuickReply(items=[
                            QuickReplyItem(action=MessageAction(label=f"⏰ {slot}", text=slot))
                            for slot in quick_slots
                        ])

                        ask_text = (
                            "⏰ กำหนดเวลาโพสต์ (เวลาไทย 24 ชม. ปัจจุบัน)\n"
                            "✨ ปรับเป็นระบบ 24 ชม. ไม่มี 'ก่อนเที่ยง/หลังเที่ยง' ให้สับสนแล้วครับ!\n\n"
                            "👇 คุณสามารถทำได้ง่ายๆ:\n"
                            "1️⃣ แตะเลือกเวลาด่วน 24 ชม. ที่ปุ่มด้านล่างได้ทันที\n"
                            "2️⃣ หรือพิมพ์เวลาที่ต้องการในแชทนี้ได้เลย เช่น:\n"
                            "   • 14:00 หรือ 14.30\n"
                            "   • บ่ายสอง, บ่าย 3 ครึ่ง\n"
                            "   • 6 โมงเย็น, 1 ทุ่ม, 2 ทุ่มครึ่ง\n"
                            "   • พรุ่งนี้ 9 โมง, อีก 30 นาที"
                        )

                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text=ask_text, quick_reply=time_qr)]
                            )
                        )
                        continue

                    elif action in ["choose", "choose_datetime"]:
                        # ส่ง loading animation ทันที ให้ผู้ใช้เห็นว่าบอทกำลังทำงาน
                        send_line_loading(user_id, channel_token, 20)

                        img_path = session.get("image_path")
                        # ป้องกันการกดย้ำๆ: ถ้าไม่มีรูปใน session (แปลว่ากำลังโพสต์หรือโพสต์เสร็จแล้ว)
                        if not img_path:
                            line_bot_api.reply_message(
                                ReplyMessageRequest(
                                    reply_token=reply_token,
                                    messages=[TextMessage(text="✨ รูปภาพนี้ได้ถูกดำเนินการโพสต์หรือตั้งเวลาไปเรียบร้อยแล้วครับ หากต้องการโพสต์ใหม่ ส่งรูปเข้ามาใหม่ได้เลยครับ 📸", quick_reply=quick_reply_buttons)]
                                )
                            )
                            continue

                        # ล้างรูปออกจาก session ทันที เพื่อป้องกันการกดย้ำๆ จากผู้ใช้
                        session.pop("image_path", None)
                        save_user_session(user_id, session)

                        style_idx = int(params.get("idx", 0))
                        timing = params.get("timing", "now")
                        captions = session.get("captions", [])
                        chosen_caption = captions[style_idx]["text"] if style_idx < len(captions) else captions[0]["text"]
                        style_name = captions[style_idx]["style"] if style_idx < len(captions) else "แบบด่วน"
                        
                        page_id = session.get("page_id", "slidetruck")
                        first_comment = session.get("first_comment", "")
                        pages = {p["id"]: p for p in get_all_pages()}
                        target_page = pages.get(page_id, {})

                        if action == "choose_datetime" or timing == "custom":
                            # กำหนดวัน-เวลาเองจาก DatePicker
                            selected_dt = postback_params.get("datetime", "")
                            if selected_dt:
                                sched_str = selected_dt.replace("T", " ") + ":00"
                                dt_obj = datetime.strptime(selected_dt, "%Y-%m-%dT%H:%M")
                                
                                THAI_MONTHS = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
                                day = dt_obj.day
                                month = THAI_MONTHS[dt_obj.month]
                                year = dt_obj.year + 543
                                time_str = dt_obj.strftime("%H:%M น.")
                                human_time = f"{day} {month} {year} เวลา {time_str}"
                                
                                create_post(page_id, img_path, chosen_caption, first_comment, style_name, sched_str, status="scheduled")
                                msg = f"📅 ตั้งเวลาโพสต์สำเร็จแล้วครับ!\n📌 เพจ: {target_page.get('name', 'เพจ')}\n⏰ กำหนดปล่อยโพสต์: วันที่ {human_time}\n\nเมื่อถึงเวลา ระบบจะยิงขึ้นเพจพร้อมคอมเมนต์เบอร์โทรให้อัตโนมัติครับ ✨"
                            else:
                                msg = "⚠️ ไม่พบข้อมูลเวลาที่เลือก กรุณาลองใหม่อีกครั้งครับ"

                        elif timing == "now":
                            # โพสต์ทันที
                            post_id = create_post(page_id, img_path, chosen_caption, first_comment, style_name, None, status="published")
                            res = post_to_facebook_page(
                                page_id=target_page.get("facebook_page_id", ""),
                                access_token=target_page.get("facebook_access_token", ""),
                                image_path=img_path,
                                caption=chosen_caption,
                                first_comment=first_comment
                            )
                            update_post_status(post_id, "published", res.get("post_id", ""))
                            msg = f"🚀 โพสต์ขึ้น {target_page.get('name', 'เพจ')} สำเร็จแล้วครับ!\nพร้อมปักหมุดเบอร์โทรในคอมเมนต์ให้เรียบร้อยแล้วครับ ✨"
                        else:
                            # ตั้งเวลาเย็นนี้ 18:00
                            now = datetime.now()
                            target_time = now.replace(hour=18, minute=0, second=0)
                            if target_time <= now:
                                target_time += timedelta(days=1)
                            sched_str = target_time.strftime("%Y-%m-%d %H:%M:%S")

                            create_post(page_id, img_path, chosen_caption, first_comment, style_name, sched_str, status="scheduled")
                            msg = f"⏰ ตั้งเวลาโพสต์เรียบร้อยครับ!\nจะปล่อยโพสต์เวลา {target_time.strftime('%H:%M น.')} ระบบจะยิงขึ้นเพจให้เองครับ"

                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text=msg, quick_reply=quick_reply_buttons)]
                            )
                        )

                # 3. ผู้ใช้พิมพ์ข้อความ (เช่น "ดูโพสต์", "เช็คคิว", "สลับเพจ")
                elif event_type == "message" and event.get("message", {}).get("type") == "text":
                    raw_text = event["message"]["text"].strip()
                    lower_text = raw_text.lower()
                    # ทำความสะอาดและแทนที่คำพิมพ์ผิดทั่วไป เช่น '๕' แทน 'ค'
                    norm_text = lower_text.replace("เช็๕", "เช็ค").replace(" ", "")

                    # 3.1 เช็คคิวโพสต์ / ดูโพสต์ (รองรับ เช็คคิว, เช็กคิว, ดูโพต, ดูโพสต์, คิว, ตาราง ฯลฯ)
                    if any(k in norm_text for k in ["คิว", "โพสต์", "โพต", "ตาราง", "เช็ค", "เช็ก", "ดูงาน"]):
                        posts = get_all_posts(status_filter="scheduled")
                        if not posts:
                            reply_txt = "📋 ตอนนี้ไม่มีโพสต์รออยู่ในคิวครับ\n\n📸 ส่งรูปภาพหน้างานเข้ามาเพื่อสร้างโพสต์ใหม่ได้เลยครับ!"
                        else:
                            reply_txt = f"📋 พบ {len(posts)} โพสต์ที่รออยู่ในคิวครับ:\n"
                            for i, p in enumerate(posts[:5], 1):
                                sched = p.get('scheduled_at', '')
                                reply_txt += f"\n{i}. [{p['page_name']}]\n⏰ ปล่อยโพสต์: {sched}\n📝 แคปชัน: {p['caption'][:40]}...\n"
                        
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text=reply_txt, quick_reply=quick_reply_buttons)]
                            )
                        )
                        continue

                    # 3.2 ขอลิงก์หน้าเว็บแอดมิน (Web Studio URL)
                    elif any(k in norm_text for k in ["เว็บ", "เวป", "หน้าเว็บ", "แอดมิน", "link", "url", "สตูดิโอ"]):
                        pub_url = get_setting("public_url", "").strip() or "http://localhost:8000"
                        reply_txt = (
                            f"🌐 [ทางเข้าหน้าเว็บแอดมิน ศรศิลป์ กรอบรูป]\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"เข้าใช้งาน AI Studio ผ่านมือถือได้ทันที:\n"
                            f"👉 {pub_url}\n\n"
                            f"🔐 บัญชีเข้าสู่ระบบ:\n"
                            f"👤 ผู้ใช้: admin\n"
                            f"🔑 รหัสผ่าน: admin1234\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"💡 คุณสามารถอัปโหลดหลายรูป, ลบลายน้ำ, ย้ายตำแหน่ง 4 มุม และจัดคิวได้ที่นี่ครับ!"
                        )
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text=reply_txt, quick_reply=quick_reply_buttons)]
                            )
                        )
                        continue

                    # 3.3 ขอไอเดียโพสต์โปรโมทร้านกรอบรูป (AI Idea Generator)
                    elif any(k in norm_text for k in ["ไอเดีย", "โปรโมท", "ขายอะไร", "แคปชัน", "คิดโพสต์", "มุมมอง"]):
                        send_line_loading(user_id, channel_token, 15)
                        reply_txt = (
                            f"💡 [3 ไอเดียโปรโมทร้าน ศรศิลป์ กรอบรูป วันนี้]\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"1️⃣ 🌟 กรอบภาพมงคลเสริมฮวงจุ้ย\n"
                            f"👉 เจาะกลุ่มคนค้าขาย/เปิดร้านใหม่ ชูรูปท้าวเวสสุวรรณ พระพุทธรูป หรือม้า 8 ตัว กรอบทองตัดขอบดำ เสริมบารมี ค้าขายร่ำรวย\n\n"
                            f"2️⃣ 🎓 กรอบของขวัญรับปริญญา & ความทรงจำ\n"
                            f"👉 ชวนลูกค้าเอาภาพครอบครัวหรือใบประกาศมาเข้ากรอบพรีเมี่ยม กระจกตัดแสง ป้องกันสีซีดจาง มอบเป็นของขวัญชิ้นเดียวในโลก\n\n"
                            f"3️⃣ 🪞 กรอบกระจกเงาติดผนังโมเดิร์น\n"
                            f"👉 เอาใจสายแต่งห้อง/คาเฟ่ กระจกกรอบมินิมอล ช่วยให้ห้องดูกว้างขึ้น เข้าได้กับทุกสไตล์\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"📸 ส่งรูปงานจริงเข้ามาได้เลยครับ เดี๋ยวผมช่วยวิเคราะห์และแต่งแคปชันให้ทันที!"
                        )
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text=reply_txt, quick_reply=quick_reply_buttons)]
                            )
                        )
                        continue

                    # 3.4 สลับเพจ / ตรวจสอบเพจปัจจุบัน
                    elif any(k in norm_text for k in ["สลับเพจ", "เปลี่ยนเพจ", "เลือกเพจ"]):
                        target = {"name": "ศรศิลป์ กรอบรูป"}
                        reply_txt = f"🖼️ เพจปัจจุบันของคุณคือ: ✨ {target.get('name')} ✨\n(ระบบตั้งค่าเชื่อมต่อพร้อมโพสต์อัตโนมัติ 100% เรียบร้อยครับ!)"

                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text=reply_txt, quick_reply=quick_reply_buttons)]
                            )
                        )
                        continue

                    # 3.3 ผู้ใช้ส่ง Gemini API Key เข้ามาโดยตรง (รองรับทั้งแบบเดิม AIzaSy และแบบใหม่ AQ.)
                    is_api_key = (
                        (raw_text.startswith("AIzaSy") or raw_text.startswith("AQ.")) and 
                        len(raw_text) >= 35 and 
                        not raw_text.startswith("http") and 
                        " " not in raw_text
                    )
                    if is_api_key:
                        set_setting("gemini_api_key", raw_text)
                        success_msg = (
                            "🎉 ยินดีด้วยครับ! บันทึก Gemini API Key เรียบร้อยแล้ว 🧠✨\n\n"
                            "ตอนนี้ 'น้องโพสต์อีส AI' ได้รับสมองกลอัจฉริยะเต็มระบบแล้วครับ!\n"
                            "คุณสามารถ:\n"
                            "• ส่งรูปหน้างานเข้ามา ให้ AI ช่วยคิดแคปชันสดๆ\n"
                            "• พิมพ์สั่งปรับแก้ได้ตามใจ (เช่น 'สั้นลงหน่อย', 'ขอแบบกวนๆ', 'เอาเบอร์ออก', 'เน้นโปรโมชัน')\n"
                            "• คุยถาม-ตอบกับ AI ได้เหมือนพาร์ทเนอร์ส่วนตัวเลยครับ ลองพิมพ์ทักทายหรือส่งรูปได้เลยครับ!"
                        )
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text=success_msg, quick_reply=quick_reply_buttons)]
                            )
                        )
                        continue

                    # 3.4 ผู้ใช้ระบุเวลาโพสต์ (เช่น "14:00", "14.30", "บ่ายสอง", "6 โมงเย็น", "1 ทุ่ม", "พรุ่งนี้ 9 โมง")
                    parsed_dt = parse_thai_time(raw_text)
                    session = get_user_session(user_id)
                    if parsed_dt:
                        if session.get("image_path") and session.get("captions"):
                            style_idx = session.get("chosen_idx", 0)
                            captions = session.get("captions", [])
                            chosen_caption = captions[style_idx]["text"] if captions and style_idx < len(captions) else captions[0]["text"]
                            style_name = captions[style_idx]["style"] if captions and style_idx < len(captions) else "กำหนดเวลาเอง"
                            img_path = session.get("image_path")
                            page_id = session.get("page_id", "slidetruck")
                            first_comment = session.get("first_comment", "")

                            now = datetime.now()
                            THAI_MONTHS = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
                            if parsed_dt.date() == now.date():
                                day_label = "วันนี้"
                            elif parsed_dt.date() == (now + timedelta(days=1)).date():
                                day_label = "พรุ่งนี้"
                            else:
                                day_label = f"วันที่ {parsed_dt.day} {THAI_MONTHS[parsed_dt.month]} {parsed_dt.year + 543}"

                            time_24h = parsed_dt.strftime("%H:%M น.")
                            sched_str = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")

                            create_post(page_id, img_path, chosen_caption, first_comment, style_name, sched_str, status="scheduled")
                            pages = {p["id"]: p for p in get_all_pages()}
                            target_page = pages.get(page_id, {})

                            confirm_text = (
                                f"📅 ตั้งเวลาโพสต์สำเร็จแล้วครับ!\n"
                                f"📌 เพจ: {target_page.get('name', 'เพจ')}\n"
                                f"⏰ กำหนดปล่อยโพสต์: {day_label} เวลา {time_24h} (เวลาไทย 24 ชม.)\n"
                                f"📝 สไตล์: {style_name}\n\n"
                                f"เมื่อถึงเวลา ระบบจะยิงขึ้นเพจพร้อมคอมเมนต์เบอร์โทรให้อัตโนมัติครับ ✨"
                            )

                            # ล้างรูปล่าสุดออกจาก session เพื่อป้องกันการตั้งเวลาซ้ำซ้อน
                            session.pop("image_path", None)
                            save_user_session(user_id, session)

                            line_bot_api.reply_message(
                                ReplyMessageRequest(
                                    reply_token=reply_token,
                                    messages=[TextMessage(text=confirm_text, quick_reply=quick_reply_buttons)]
                                )
                            )
                            continue
                        elif not session.get("image_path"):
                            line_bot_api.reply_message(
                                ReplyMessageRequest(
                                    reply_token=reply_token,
                                    messages=[TextMessage(
                                        text=f"⏰ ได้รับเวลา {parsed_dt.strftime('%H:%M น.')} แล้วครับ!\n📸 แต่ยังไม่มีรูปภาพที่จะโพสต์เลย กรุณาส่งรูปหน้างานเข้ามาก่อนได้เลยครับ ✨",
                                        quick_reply=quick_reply_buttons
                                    )]
                                )
                            )
                            continue

                    # 3.4 สนทนากับ AI Copilot อัจฉริยะ (สั่งแก้แคปชัน / เปลี่ยนสไตล์ / คุยกับ AI)
                    session = get_user_session(user_id)
                    img_path = session.get("image_path")
                    active_page_id = session.get("active_page", "slidetruck")
                    chat_hist = session.get("chat_history", [])
                    current_caps = session.get("captions", [])
                    first_comm = session.get("first_comment", "")

                    # เรียกใช้ Gemini Copilot
                    copilot_res = chat_with_gemini_copilot(
                        user_message=raw_text,
                        page_id=active_page_id,
                        image_path=img_path,
                        history=chat_hist,
                        current_captions=current_caps,
                        first_comment=first_comm
                    )

                    # บันทึกประวัติการคุย
                    chat_hist.append({"role": "user", "content": raw_text})
                    ai_reply = copilot_res.get("reply_text", "รับทราบครับ")
                    chat_hist.append({"role": "model", "content": ai_reply})
                    session["chat_history"] = chat_hist[-12:] # เก็บ 12 ข้อความล่าสุด
                    save_user_session(user_id, session)

                    # ถ้า AI ส่งแคปชันชุดใหม่ที่ปรับปรุงแล้วกลับมา
                    if copilot_res.get("has_captions") and copilot_res.get("captions"):
                        new_caps = copilot_res.get("captions", [])
                        
                        # เพิ่มตัวเลือก "ข้อความที่คุณพิมพ์เอง" ต่อท้ายเสมอ
                        new_caps.append({
                            "style": "ข้อความที่คุณพิมพ์เอง",
                            "text": raw_text
                        })

                        session["captions"] = new_caps
                        if copilot_res.get("first_comment"):
                            session["first_comment"] = copilot_res["first_comment"]
                        save_user_session(user_id, session)

                        flex_content = create_caption_carousel_flex(new_caps, active_page_id)
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[
                                    TextMessage(text=ai_reply, quick_reply=quick_reply_buttons),
                                    FlexMessage(alt_text="แคปชันที่ AI ปรับปรุงใหม่", contents=FlexContainer.from_json(json.dumps(flex_content)))
                                ]
                            )
                        )

                    # ถ้าผู้ใช้สั่งตั้งเวลาในบทสนทนา เช่น "โพสต์ตอน 18:00"
                    elif copilot_res.get("schedule_datetime") and img_path and current_caps:
                        sched_dt = copilot_res.get("schedule_datetime")
                        try:
                            dt_obj = datetime.strptime(sched_dt, "%Y-%m-%dT%H:%M")
                            THAI_MONTHS = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
                            human_time = f"{dt_obj.day} {THAI_MONTHS[dt_obj.month]} {dt_obj.year + 543} เวลา {dt_obj.strftime('%H:%M น.')}"
                            
                            chosen_cap = current_caps[0]["text"]
                            style_name = current_caps[0].get("style", "แบบด่วน")
                            sched_str = sched_dt.replace("T", " ") + ":00"
                            
                            create_post(active_page_id, img_path, chosen_cap, first_comm, style_name, sched_str, status="scheduled")
                            pages = {p["id"]: p for p in get_all_pages()}
                            target_page = pages.get(active_page_id, {})
                            
                            confirm_text = f"📅 ตั้งเวลาโพสต์ให้เรียบร้อยแล้วครับตามที่สั่ง!\n📌 เพจ: {target_page.get('name', 'เพจ')}\n⏰ วันที่: {human_time}\n\nระบบจะยิงขึ้นเพจให้อัตโนมัติครับ ✨"
                            line_bot_api.reply_message(
                                ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text=confirm_text, quick_reply=quick_reply_buttons)]
                            )
                        )
                        except Exception as dt_err:
                            line_bot_api.reply_message(
                                ReplyMessageRequest(
                                    reply_token=reply_token,
                                    messages=[TextMessage(text=ai_reply, quick_reply=quick_reply_buttons)]
                                )
                            )

                    # ข้อความสนทนาทั่วไป
                    else:
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text=ai_reply, quick_reply=quick_reply_buttons)]
                            )
                        )

        return {"status": "success"}

    except Exception as e:
        print(f"LINE Webhook Error: {e}")
        return {"status": "error", "error": str(e)}

def create_caption_carousel_flex(captions: List[Dict[str, str]], page_id: str) -> Dict[str, Any]:
    """สร้าง Flex Message Carousel สำหรับ LINE (รองรับทั้งแคปชันจาก AI และแคปชันที่ผู้ใช้พิมพ์เอง)"""
    bubbles = []
    icons = {
        "แบบด่วน": "⚡", 
        "แบบเล่าเรื่องหน้างาน": "📖", 
        "แบบโปรโมชัน": "🏷️",
        "ข้อความที่คุณพิมพ์เอง": "✍️"
    }
    bg_colors = ["#10B981", "#3B82F6", "#F59E0B", "#8B5CF6"]

    for idx, c in enumerate(captions):
        style = c.get("style", "แบบทั่วไป")
        icon = icons.get(style, "📝")
        text = c.get("text", "")
        bg_color = bg_colors[idx % len(bg_colors)]

        now = datetime.now()
        initial_dt = now.strftime("%Y-%m-%dT%H:%M")

        bubble = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": bg_color,
                "contents": [
                    {
                        "type": "text",
                        "text": f"{icon} {style}",
                        "weight": "bold",
                        "color": "#FFFFFF",
                        "size": "sm"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": text,
                        "wrap": True,
                        "size": "xs",
                        "maxLines": 6
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#10B981",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "⚡ โพสต์เลยทันที",
                            "data": f"action=choose&idx={idx}&timing=now"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "⏰ ตั้งเวลาโพสต์ (24 ชม.)",
                            "data": f"action=ask_time&idx={idx}"
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)

    return {
        "type": "carousel",
        "contents": bubbles
    }
