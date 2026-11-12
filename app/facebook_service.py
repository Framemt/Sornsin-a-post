import os
import json
import requests
from datetime import datetime
from typing import Dict, Any, Union, List

FB_GRAPH_URL = "https://graph.facebook.com/v19.0"

def parse_image_paths(image_input: Union[str, List[str]]) -> List[str]:
    """แปลง image_input ทั้งแบบ path เดี่ยว, list ของ paths, หรือ JSON array string ให้เป็น list of paths"""
    if isinstance(image_input, list):
        return [str(p).strip() for p in image_input if p and str(p).strip()]
    if isinstance(image_input, str):
        s = image_input.strip()
        if s.startswith('[') and s.endswith(']'):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(p).strip() for p in parsed if p and str(p).strip()]
            except Exception:
                pass
        if s:
            return [s]
    return []

def post_to_facebook_page(page_id: str, access_token: str, image_path: Union[str, List[str]], caption: str, first_comment: str = "") -> Dict[str, Any]:
    """
    โพสต์รูปลง Facebook Page (รองรับทั้ง 1 รูป และหลายรูป Multi-Photo Album)
    และยิงคอมเมนต์แรกอัตโนมัติผ่าน Facebook Graph API
    หากยังไม่มี Page ID หรือ Token จะทำงานในโหมดจำลอง (Simulation Mode)
    """
    images = parse_image_paths(image_path)
    if not images:
        return {"success": False, "error": "ไม่พบไฟล์รูปภาพสำหรับการโพสต์"}

    num_images = len(images)

    # โหมดจำลอง (Simulation Mode) ถ้ายังไม่ได้ใส่ Token จริง
    if not page_id or not access_token or access_token.strip() == "":
        ts = int(datetime.now().timestamp())
        fake_post_id = f"sim_{ts}"
        print(f"[SIMULATION] โพสต์สำเร็จ {num_images} รูปภาพ (โหมดจำลอง - ยังไม่ได้ใส่ Token จริง)")
        return {
            "success": True,
            "post_id": fake_post_id,
            "comment_id": f"sim_comment_{fake_post_id}",
            "mode": "simulation",
            "message": f"โพสต์สำเร็จ {num_images} รูป (โหมดจำลอง - กรุณาใส่ Token ใน Settings เพื่อโพสต์เพจจริง)"
        }

    try:
        post_id = ""
        # 1 รูปภาพ: โพสต์ตรงเข้า /{page_id}/photos พร้อมแคปชัน
        if num_images == 1:
            img = images[0]
            if not os.path.exists(img):
                return {"success": False, "error": f"ไม่พบไฟล์รูปภาพบนเครื่อง: {img}"}

            upload_url = f"{FB_GRAPH_URL}/{page_id}/photos"
            with open(img, "rb") as image_file:
                files = {"source": image_file}
                data = {
                    "message": caption,
                    "access_token": access_token
                }
                res = requests.post(upload_url, files=files, data=data, timeout=40)
                res_data = res.json()

            if "id" not in res_data:
                err_msg = res_data.get("error", {}).get("message", "Facebook API error")
                return {"success": False, "error": err_msg}

            post_id = res_data.get("post_id") or res_data.get("id")

        else:
            # หลายรูปภาพ (Multi-Photo / Album):
            # Step A: อัปโหลดแต่ละรูปโดยตั้ง published=false เพื่อเอา photo fbid
            media_fbids = []
            for img in images:
                if not os.path.exists(img):
                    continue
                upload_url = f"{FB_GRAPH_URL}/{page_id}/photos"
                with open(img, "rb") as image_file:
                    files = {"source": image_file}
                    data = {
                        "published": "false",
                        "access_token": access_token
                    }
                    res = requests.post(upload_url, files=files, data=data, timeout=40)
                    res_data = res.json()
                    if "id" in res_data:
                        media_fbids.append(res_data["id"])
                    else:
                        err_msg = res_data.get("error", {}).get("message", "Error uploading photo in album")
                        return {"success": False, "error": f"อัปโหลดรูปไม่สำเร็จ: {err_msg}"}

            if not media_fbids:
                return {"success": False, "error": "ไม่มีรูปภาพที่อัปโหลดสำเร็จ"}

            # Step B: โพสต์ feed รวมรูปทั้งหมดเข้าอัลบั้มเดียว
            feed_url = f"{FB_GRAPH_URL}/{page_id}/feed"
            attached = [{"media_fbid": fbid} for fbid in media_fbids]
            feed_data = {
                "message": caption,
                "access_token": access_token,
                "attached_media": json.dumps(attached)
            }
            res = requests.post(feed_url, data=feed_data, timeout=40)
            res_data = res.json()

            if "id" not in res_data:
                err_msg = res_data.get("error", {}).get("message", "Error publishing album post")
                return {"success": False, "error": err_msg}

            post_id = res_data.get("id")

        comment_id = ""
        # 2. ยิงคอมเมนต์แรกอัตโนมัติ (First Comment)
        if first_comment and first_comment.strip() and post_id:
            comment_url = f"{FB_GRAPH_URL}/{post_id}/comments"
            c_data = {
                "message": first_comment,
                "access_token": access_token
            }
            c_res = requests.post(comment_url, data=c_data, timeout=20)
            c_data = c_res.json()
            comment_id = c_data.get("id", "")

        return {
            "success": True,
            "post_id": post_id,
            "comment_id": comment_id,
            "mode": "live",
            "message": f"โพสต์สำเร็จ {num_images} รูป ขึ้นเพจ Facebook และลงคอมเมนต์แรกเรียบร้อย!"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}

def exchange_for_never_expiring_page_token(token: str, app_id: str, app_secret: str, page_id: str) -> Dict[str, Any]:
    """
    แปลง Token ให้เป็น Permanent Page Access Token (ไม่มีวันหมดอายุ)
    """
    try:
        # Step 1: แลก Short-lived token เป็น Long-lived Token
        exchange_url = f"{FB_GRAPH_URL}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": token
        }
        res1 = requests.get(exchange_url, params=params, timeout=15).json()
        if "error" in res1:
            return {"success": False, "error": res1["error"].get("message")}
        
        long_lived_token = res1.get("access_token")
        
        # Step 2: ดึง Permanent Page Token จาก Long-lived Token
        page_url = f"{FB_GRAPH_URL}/{page_id}"
        p_params = {
            "fields": "access_token,name",
            "access_token": long_lived_token
        }
        res2 = requests.get(page_url, params=p_params, timeout=15).json()
        if "access_token" in res2:
            return {
                "success": True, 
                "permanent_page_token": res2["access_token"],
                "page_name": res2.get("name", "")
            }
        
        return {"success": True, "permanent_page_token": long_lived_token}
    except Exception as e:
        return {"success": False, "error": str(e)}

