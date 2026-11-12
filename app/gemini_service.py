import json
import os
import re
from typing import Dict, Any, List
from .database import get_setting, get_page

def build_contact_block(phone: str, line_id: str, service_area: str) -> str:
    """สร้างบล็อกข้อมูลติดต่อมาตรฐานสำหรับปิดท้ายแคปชัน"""
    lines = []
    if phone and phone.strip():
        lines.append(f"📞 โทร: {phone.strip()}")
    if line_id and line_id.strip():
        lines.append(f"📲 LINE: {line_id.strip()}")
    if service_area and service_area.strip():
        loc = service_area.strip()
        lines.append(f"📍 {loc if loc.startswith('พิกัด') else 'พิกัดร้าน ' + loc}")
    return "\n".join(lines)

def ensure_contact_and_hashtags(caption_text: str, phone: str, line_id: str, service_area: str, page_name: str = "") -> str:
    """
    รับประกันว่าทุกแคปชันจะมี:
    1. บล็อกข้อมูลติดต่อ (โทร, LINE, พิกัดร้าน) ครบถ้วน
    2. แฮชแท็กอันแรกสุดต้องเป็นชื่อร้าน #{page_name} เสมอ ตามด้วยแฮชแท็กอื่นๆ
    """
    contact_block = build_contact_block(phone, line_id, service_area)
    text = caption_text.strip()

    # ดึงแฮชแท็กทั้งหมดออกจากท้ายข้อความ
    hash_match = re.search(r'(\n*(?:#[^\s#]+(?:\s+|$))+)$', text)

    clean_shop = re.sub(r'[\s\.\-_/]+', '', page_name).strip() if page_name else ""
    shop_tag = f"#{clean_shop}" if clean_shop else "#ศรศิลป์"

    if hash_match:
        main_part = text[:hash_match.start()].strip()
        hashes_str = hash_match.group(1).strip()
        tags = re.findall(r'#[^\s#]+', hashes_str)
        # นำ shop_tag มาไว้ตำแหน่งแรกสุด และไม่ให้มีชื่อร้านซ้ำซ้อน
        other_tags = [t for t in tags if t.lower() != shop_tag.lower()]
        ordered_tags = [shop_tag] + other_tags
        final_hashes = " ".join(ordered_tags)
    else:
        main_part = text
        final_hashes = f"{shop_tag} #รับทำกรอบรูป #สั่งตัดกรอบรูป #แต่งบ้าน #ของขวัญ"

    # เช็คว่าใน main_part มีข้อมูลติดต่อครบหรือไม่
    clean_phone = phone.replace("-", "").strip() if phone else ""
    has_phone = bool(clean_phone and (clean_phone in main_part.replace("-", "") or phone in main_part))
    has_line = bool(line_id and line_id.strip() in main_part)
    has_loc = bool(service_area and ("http" in main_part or "maps" in main_part or "พิกัด" in main_part or service_area.strip() in main_part))

    if has_phone and has_line and has_loc:
        return f"{main_part}\n\n{final_hashes}"
    else:
        if contact_block:
            return f"{main_part}\n\n{contact_block}\n\n{final_hashes}"
        else:
            return f"{main_part}\n\n{final_hashes}"

def ensure_contact_in_caption(caption_text: str, phone: str, line_id: str, service_area: str, page_name: str = "") -> str:
    return ensure_contact_and_hashtags(caption_text, phone, line_id, service_area, page_name)

def generate_captions_with_gemini(image_path: str, page_id: str, extra_notes: str = "", category: str = "all") -> Dict[str, Any]:
    """
    วิเคราะห์รูปภาพด้วย Gemini AI และแต่งแคปชันภาษาไทย 3 สไตล์ + คอมเมนต์แรก
    โทนภาษา: พรีเมี่ยม งานเนี๊ยบ สุภาพ ดึงดูด ไม่โอเวอร์ อย่างน้อย 4 ประโยค พร้อมเบอร์โทร ไลน์ โลเคชั่น และแฮชแท็กชื่อร้านอันแรกสุด
    รองรับหมวดหมู่งานเฉพาะทาง: auspicious (มงคล), gift (ของขวัญ), wedding (แต่งงาน), mirror (กระจก), all (ทั่วไป)
    """
    api_key = get_setting("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
    page = get_page(page_id) or {}
    page_name = page.get("name", "ศรศิลป์")
    phone = page.get("phone", "064-964-5353")
    line_id = page.get("line_id", "0649645353")
    service_area = page.get("service_area", "พิกัดร้าน https://maps.app.goo.gl/uMoSsvqq3JveQo479")

    # ถ้าไม่มี API Key หรือเกิดปัญหา ให้ใช้ Fallback แคปชันคุณภาพสูงทันที
    clean_page_name = re.sub(r'[\s\.\-_/]+', '', page_name) if page_name else "ศรศิลป์"
    if not api_key:
        return get_fallback_captions(page_id, page_name, phone, line_id, service_area, extra_notes)

    category_guidance = ""
    if category == "auspicious":
        category_guidance = f"""
🌟 [เน้นหมวดพิเศษ: กรอบรูปภาพมงคล / เสริมฮวงจุ้ย / สิ่งศักดิ์สิทธิ์ / พระเกจิ / ท้าวเวสสุวรรณ / รัชกาลที่ 9-10]:
- เน้นความสิริมงคล ความสงบ เสริมบารมี คุ้มครองเคหสถาน และเสริมโชคลาภการค้าขาย
- อธิบายถึงความพิถีพิถันในการเข้ากรอบอย่างสมเกียรติ ยกระดับความงามและความศักดิ์สิทธิ์
- แฮชแท็กเฉพาะที่ต้องใส่: #{clean_page_name} #กรอบรูปมงคล #ภาพมงคลเสริมฮวงจุ้ย #กรอบรูปพระ #ท้าวเวสสุวรรณ #เสริมโชคลาภบารมี
"""
    elif category == "gift":
        category_guidance = f"""
🎓 [เน้นหมวดพิเศษ: กรอบของขวัญ / รับปริญญา / วันเกิด / งานเกษียณ / วันสำคัญ]:
- เน้นความประทับใจ การส่งมอบความทรงจำอันทรงคุณค่าที่อยู่ได้นานนับสิบปี
- สื่อถึงความยินดีและความหมายลึกซึ้งของชิ้นงาน เหมาะเป็นของขวัญชิ้นเดียวในโลก
- แฮชแท็กเฉพาะที่ต้องใส่: #{clean_page_name} #ของขวัญรับปริญญา #กรอบของขวัญ #ของขวัญวันเกิด #ของขวัญงานเกษียณ #ของขวัญชิ้นเดียวในโลก
"""
    elif category == "wedding":
        category_guidance = f"""
💍 [เน้นหมวดพิเศษ: กรอบรูปแต่งงาน / พรีเวดดิ้ง / รูปครอบครัว / คู่ชีวิต]:
- เน้นความรัก ความอบอุ่น ความผูกพัน และการเก็บรักษาช่วงเวลาที่สวยงามที่สุดไว้ตลอดไป
- ชูการเลือกสีกรอบและกระจกถนอมภาพ ไม่ให้สีซีดจางเมื่อเวลาผ่านไป
- แฮชแท็กเฉพาะที่ต้องใส่: #{clean_page_name} #กรอบรูปแต่งงาน #พรีเวดดิ้ง #ภาพครอบครัว #บันทึกความทรงจำ #ของแต่งบ้านคู่รัก
"""
    elif category == "mirror":
        category_guidance = f"""
🪞 [เน้นหมวดพิเศษ: กรอบกระจกเงาติดผนัง / กระจกแต่งบ้าน / มินิมอลโมเดิร์น]:
- เน้นดีไซน์เรียบหรู ขยายพื้นที่ห้องให้ดูกว้างและสว่างขึ้น เข้าได้กับทั้งบ้าน คอนโด คาเฟ่
- ชูวัสดุคุณภาพ กระจกเงาใสคมชัด กรอบแข็งแรงทนทาน เข้ามุมเนียนสนิท
- แฮชแท็กเฉพาะที่ต้องใส่: #{clean_page_name} #กระจกแต่งห้อง #กระจกเงาติดผนัง #กระจกมินิมอล #ของแต่งบ้าน #กระจกเงา
"""

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        clean_page_name = re.sub(r'[\s\.\-_/]+', '', page_name) or "ศรศิลป์"
        prompt = f"""
คุณคือนักเขียนแคปชันโซเชียลมีเดียและการตลาดมืออาชีพสำหรับเพจ: {page_name}
ประเภทธุรกิจ: ร้านรับทำกรอบรูป สั่งตัดกรอบรูป งานศิลปะ กรอบเสื้อฟุตบอล/เสื้อกีฬา กรอบภาพมงคล กรอบกระจก/กรอบลอย
ข้อมูลร้านสำหรับใส่ในทุกแคปชัน:
- เบอร์โทรติดต่อ: {phone}
- LINE ID: {line_id}
- พิกัดร้าน / โลเคชั่น: {service_area}
โน้ตเพิ่มเติมจากหน้างาน: {extra_notes}
{category_guidance}
🎯 กฎเหล็กและข้อกำหนดสไตล์การเขียนแคปชัน (ต้องปฏิบัติตามอย่างเคร่งครัด):
1. **วิเคราะห์และเจาะจงตามรูปภาพจริง (สำคัญที่สุด):**
   - วิเคราะห์ภาพที่แนบมาอย่างละเอียด ระบุให้ชัดเจนว่าคือชิ้นงานอะไร เช่น เสื้อฟุตบอล/เสื้อกีฬา, ภาพวาดสีน้ำมัน, ภาพมงคล (เช่น ปลาคาร์ฟ, ม้า 8 ตัว, มังกร), พระบรมฉายาลักษณ์/รูปเคารพ, ใบปริญญาบัตร/เกียรติบัตร, งานปัก, ภาพครอบครัว/แต่งงาน, กรอบลอย หรือกระจกเงา
   - บรรยายลักษณะเฉพาะของกรอบและชิ้นงานในรูป เช่น โทนสีกรอบ, ลวดลาย, คิ้วสองชั้น, หรือการจัดวางทรง ให้ตรงกับรูปภาพนั้นๆ โดยตรง
2. **ความยาวของเนื้อหาแคปชัน (ต้องมีอย่างน้อย 4 ประโยคขึ้นไป):**
   - ส่วนเนื้อหาบรรยาย (ก่อนข้อมูลติดต่อ) **ต้องมีความยาวอย่างน้อย 4 ประโยคขึ้นไป** เพื่อเล่าเรื่องและอธิบายชิ้นงานอย่างมีมิติ ไม่สั้นห้วน 1-2 บรรทัด
   - ให้เล่าถึงเรื่องราวของชิ้นงาน การดูแลใส่ใจในการทำ การเลือกกรอบที่เข้ากัน และการปกป้องผลงานให้อยู่ได้นาน
3. **ระดับภาษาและการใช้คำ (เบาๆ ลง เป็นธรรมชาติ ไม่ยัดเยียด):**
   - ภาษาสุภาพ เรียบง่าย สวยงาม จริงใจ **ไม่เวอร์ ไม่โอเวอร์**
   - **คำว่า "งานเนี๊ยบ" หรือ "พรีเมี่ยม" ให้เบาๆ ลง ไม่ต้องยัดเยียดหรือใส่ซ้ำซ้อนทุกประโยค** (มีได้ไม่เกิน 1 ครั้ง หรือไม่ต้องใส่เลยก็ได้ถ้าไม่จำเป็น)
   - ใช้คำบรรยายฝีมือที่เป็นธรรมชาติแทน เช่น "ใส่ใจทุกขั้นตอน", "เก็บขอบมุมเรียบร้อย", "เข้ามุมเนียนตา", "คัดสรรวัสดุอย่างดี", "แข็งแรงทนทาน", "ช่วยให้ภาพดูโดดเด่น", "ลงตัวกับทุกมุมบ้าน"
4. **โครงสร้างและข้อมูลติดต่อ:**
   - ท้ายเนื้อหา (ก่อนแฮชแท็ก) **ต้องใส่ข้อมูลติดต่อครบถ้วนทั้ง 3 อย่างเสมอ**:
     📞 โทร: {phone}
     📲 LINE: {line_id}
     📍 {service_area}
5. **กฎของแฮชแท็ก (Hashtags):**
   - **แฮชแท็กอันแรกสุดต้องเป็นชื่อร้าน #{clean_page_name} เสมอ!**
   - แฮชแท็กถัดไป ให้ใส่แฮชแท็กที่ตรงกับรูปภาพและงานกรอบรูปอย่างเป็นธรรมชาติ เช่น ประเภทงาน (#กรอบภาพมงคล, #ม้า8ตัว, #กรอบเสื้อบอล), บรรยากาศ (#แต่งบ้าน, #ของขวัญ, #ภาพติดผนัง), และบริการ (#รับทำกรอบรูป, #สั่งตัดกรอบรูป) รวม 4-6 แฮชแท็ก (ไม่ต้องยัดเยียดแฮชแท็กพรีเมี่ยมเนี๊ยบทุกอัน)
6. **ตำแหน่งวางลายน้ำโลโก้ (watermark_position):**
   - วิเคราะห์ภาพจริงเพื่อหามุมที่มีพื้นที่ว่าง (Negative Space / ฉากหลัง / พื้นโต๊ะ / กำแพง) และไม่บดบังจุดเด่นหรือชิ้นงานในภาพเด็ดขาด (เช่น ไม่บังหน้าคน, ไม่ทับพระพุทธรูป, ไม่ทับม้าหรือภาพมงคล, ไม่ทับกลางเสื้อบอล)
   - ตอบค่า watermark_position เป็นหนึ่งในนี้เท่านั้น: "bottom_right", "bottom_left", "top_right", "top_left"

เนื้อหา 3 สไตล์ (แต่ละสไตล์ต้องเขียนอย่างน้อย 4 ประโยคขึ้นไป และเจาะจงตามรูป):
- แบบที่ 1: "แบบใส่ใจรายละเอียด" -> ชูความประณีต ช่างใส่ใจทุกขั้นตอน ขอบมุมเรียบร้อย วัสดุแข็งแรงทนทาน วางมุมไหนก็ดูลงตัว
- แบบที่ 2: "แบบคุณค่าและความทรงจำ" -> เน้นเรื่องราว เปลี่ยนชิ้นงานจริงในรูปให้กลายเป็นงานศิลปะทรงคุณค่า เหมาะประดับบ้านหรือมอบเป็นของขวัญ
- แบบที่ 3: "แบบสั่งทำตามใจลูกค้า" -> สั่งตัดได้ทุกขนาด มีกรอบและแมตช์สีให้เลือกหลากหลาย ตอบโจทย์ทุกสไตล์ ปรึกษาและประเมินราคาฟรี พร้อมพิกัดหน้าร้าน

ตอบกลับเป็น JSON โครงสร้างนี้เท่านั้น:
{{
  "watermark_position": "bottom_right หรือ bottom_left หรือ top_right หรือ top_left",
  "captions": [
    {{"style": "แบบใส่ใจรายละเอียด", "text": "..."}},
    {{"style": "แบบคุณค่าและความทรงจำ", "text": "..."}},
    {{"style": "แบบสั่งตัดตามใจลูกค้า", "text": "..."}}
  ],
  "first_comment": "ข้อความคอมเมนต์แรกสำหรับปักหมุดข้อมูลติดต่อครบถ้วน (เบอร์โทร, ไลน์, พิกัดร้าน)..."
}}
"""

        # อ่านไฟล์ภาพ
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        candidate_models = ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3-flash-preview", "gemini-3.8-flash", "gemini-flash-latest"]
        response = None
        for mod in candidate_models:
            try:
                response = client.models.generate_content(
                    model=mod,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        prompt
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=1500,
                        temperature=0.4
                    )
                )
                if response and response.text:
                    break
            except Exception as mod_err:
                print(f"Model {mod} failed: {mod_err}, trying next...")
                continue

        if not response or not response.text:
            return get_fallback_captions(page_id, page_name, phone, line_id, service_area, extra_notes)

        response_text = response.text.strip()
        # ตัด markdown ```json ออกถ้ามี
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            response_text = "\n".join(lines).strip()

        data = json.loads(response_text)

        raw_pos = str(data.get("watermark_position", "bottom_right")).lower().strip()
        if raw_pos not in ["bottom_right", "bottom_left", "top_right", "top_left"]:
            raw_pos = "bottom_right"
        data["watermark_position"] = raw_pos

        # รับประกัน 100% ว่าทุกแคปชันจะมี เบอร์, ไลน์, โลเคชั่น และแฮชแท็กชื่อร้านอันแรกเสมอ
        for c in data.get("captions", []):
            c["text"] = ensure_contact_and_hashtags(c.get("text", ""), phone, line_id, service_area, page_name)

        if not data.get("first_comment"):
            contact_blk = build_contact_block(phone, line_id, service_area)
            data["first_comment"] = f"📌 {page_name} ยินดีให้บริการครับ!\n{contact_blk}\n(บริการประเมินราคาฟรี ปรึกษาได้ตลอดครับ)"

        return data

    except Exception as e:
        print(f"Gemini API Error: {e}, falling back to default templates")
        return get_fallback_captions(page_id, page_name, phone, line_id, service_area, extra_notes)


def get_fallback_captions(page_id: str, page_name: str, phone: str, line_id: str, service_area: str, extra_notes: str) -> Dict[str, Any]:
    """สร้างแคปชันจำลองคุณภาพสูงเมื่อยังไม่ได้ต่อ Gemini API หรือระบบออฟไลน์"""
    note_txt = f" ({extra_notes})" if extra_notes else ""
    contact_blk = build_contact_block(phone, line_id, service_area)
    clean_shop = re.sub(r'[\s\.\-_/]+', '', page_name).strip() if page_name else "ศรศิลป์"
    shop_tag = f"#{clean_shop}"

    if "ศิลป์" in page_name or "กรอบ" in page_name or page_id == "slidetruck":
        return {
            "watermark_position": "bottom_right",
            "captions": [
                {
                    "style": "แบบใส่ใจรายละเอียด",
                    "text": (
                        f"🖼️ เพิ่มความลงตัวให้กับภาพถ่ายและผลงานชิ้นสำคัญ ด้วยงานกรอบรูปสั่งทำจากทางร้าน\n"
                        f"ช่างของเราใส่ใจทุกขั้นตอนการเข้ามุม เก็บงานเรียบร้อยสวยงามทุกมิติ\n"
                        f"คัดสรรวัสดุกรอบคุณภาพ แข็งแรงทนทาน ช่วยขับเน้นให้ชิ้นงานของคุณดูโดดเด่นสะดุดตา\n"
                        f"นำไปจัดวางมุมไหนของบ้านหรือที่ทำงานก็ดูดี พร้อมปกป้องผลงานให้อยู่ได้ยาวนานครับ{note_txt}\n\n"
                        f"{contact_blk}\n\n"
                        f"{shop_tag} #รับทำกรอบรูป #สั่งตัดกรอบรูป #ของแต่งบ้าน #กรอบรูปสวย #ร้านกรอบรูป"
                    )
                },
                {
                    "style": "แบบคุณค่าและความทรงจำ",
                    "text": (
                        f"✨ ทุกเรื่องราวและความทรงจำมีความหมายที่น่าจดจำเสมอ\n"
                        f"เราพร้อมช่วยดูแลและเปลี่ยนชิ้นงานสำคัญ ไม่ว่าจะเป็นเสื้อกีฬา ภาพมงคล หรือภาพครอบครัว ให้เป็นงานศิลปะที่มีคุณค่า\n"
                        f"พิถีพิถันในการประกอบและจัดวางทรงอย่างตั้งใจ เพื่อให้ภาพของคุณออกมาสวยงามที่สุด\n"
                        f"เหมาะสำหรับนำไปประดับตกแต่งบ้าน หรือส่งต่อเป็นของขวัญชิ้นพิเศษในโอกาสสำคัญครับ{note_txt}\n\n"
                        f"{contact_blk}\n\n"
                        f"{shop_tag} #กรอบรูปของขวัญ #กรอบภาพมงคล #กรอบเสื้อบอล #ของแต่งบ้าน #ภาพติดผนัง"
                    )
                },
                {
                    "style": "แบบสั่งทำตามใจลูกค้า",
                    "text": (
                        f"🎨 อยากได้กรอบรูปโทนสีไหน หรือขนาดเท่าไหร่ สามารถสั่งทำตามต้องการได้เลยครับ\n"
                        f"ทางร้านมีแบบไม้ ลวดลาย และเฉดสีกรอบให้เลือกหลากหลาย เข้ากับทุกสไตล์ห้อง\n"
                        f"ประกอบงานด้วยความชำนาญ เก็บงานเรียบร้อย ในราคาที่สมเหตุสมผลและจับต้องได้\n"
                        f"ยินดีให้คำแนะนำและประเมินราคาฟรี สนใจทักเข้ามาปรึกษาแบบกันก่อนได้เลยครับ{note_txt}\n\n"
                        f"{contact_blk}\n\n"
                        f"{shop_tag} #สั่งตัดกรอบรูป #กรอบรูปสั่งทำ #ร้านทำกรอบรูป #กรอบรูปตามสั่ง #รับทำกรอบรูป"
                    )
                }
            ],
            "first_comment": f"📌 {page_name} ยินดีให้บริการครับ!\n{contact_blk}\n(บริการประเมินราคาฟรี ปรึกษาแบบและขนาดได้ตลอดครับ)"
        }
    elif "สไลด์" in page_name:
        return {
            "captions": [
                {
                    "style": "แบบด่วน",
                    "text": f"🚨 รถเสีย สตาร์ทไม่ติด รถอุบัติเหตุ เรียกเราได้ตลอด 24 ชม.! บริการรถสไลด์ รถยก มืออาชีพ ปลอดภัย 100% รถโหลดเตี้ยก็ขึ้นได้ ไร้รอยขีดข่วน พร้อมบริการในเขต {service_area}{note_txt} โทรด่วน: {phone} 🚗💨 #รถสไลด์ #รถยก #บริการรถยกลาก24ชม #รถเสีย"
                },
                {
                    "style": "แบบเล่าเรื่องหน้างาน",
                    "text": f"✨ ภารกิจยกรถส่งมอบศูนย์บริการวันนี้ ดูแลส่งถึงมือช่างอย่างทะนุถนอม ปลอดภัยไร้กังวลครับ {note_txt} ขอบคุณลูกค้าทุกท่านที่ไว้ใจเรียกใช้บริการ รถทุกคันเราดูแลเหมือนรถเราเอง สนใจสอบถามคิวงานได้ตลอดครับ 🛠️ #รถสไลด์ใกล้ฉัน #บริการยกรถ #รถสไลด์กทม"
                },
                {
                    "style": "แบบโปรโมชัน",
                    "text": f"💯 สไลด์เดี่ยว สไลด์ถาดกองพื้น ราคาเป็นกันเอง ตกลงราคาก่อนเริ่มงาน ไม่มีบวกเพิ่มแน่นอน! วิ่งประจำโซน {service_area}{note_txt} โทรเช็กราคาประเมินฟรีที่ {phone} หรือทักแชทได้เลยครับ 🤝 #รถสไลด์ราคาถูก #รถยกรถสไลด์ #ยกรถด่วน"
                }
            ],
            "first_comment": f"📌 ขอบคุณที่ไว้วางใจใช้บริการครับ!\n📞 สอบถามด่วน / เรียกใช้บริการ โทร: {phone}\n📲 แอดไลน์: {line_id}\n(พร้อมบริการ 24 ชั่วโมง ทุกวันครับ)"
        }
    else:
        # ค่าเริ่มต้นสำหรับร้านกรอบรูป (ศรศิลป์ กรอบรูป)
        return {
            "captions": [
                {
                    "style": "แบบใส่ใจรายละเอียด",
                    "text": (
                        f"🖼️ เพิ่มความลงตัวให้กับภาพถ่ายและผลงานชิ้นสำคัญ ด้วยงานกรอบรูปสั่งทำจากทางร้าน\n"
                        f"ช่างของเราใส่ใจทุกขั้นตอนการเข้ามุม เก็บงานเรียบร้อยสวยงามทุกมิติ\n"
                        f"คัดสรรวัสดุกรอบคุณภาพ แข็งแรงทนทาน ช่วยขับเน้นให้ชิ้นงานของคุณดูโดดเด่นสะดุดตา\n"
                        f"นำไปจัดวางมุมไหนของบ้านหรือที่ทำงานก็ดูดี พร้อมปกป้องผลงานให้อยู่ได้ยาวนานครับ ✨{note_txt}\n\n"
                        f"{contact_blk}\n\n"
                        f"{shop_tag} #รับทำกรอบรูป #สั่งตัดกรอบรูป #ของแต่งบ้าน #กรอบรูปสวย #ร้านกรอบรูป"
                    )
                },
                {
                    "style": "แบบคุณค่าและความทรงจำ",
                    "text": (
                        f"🌟 ทุกเรื่องราวและความทรงจำมีความหมายที่น่าจดจำเสมอ\n"
                        f"เราพร้อมช่วยดูแลและเปลี่ยนชิ้นงานสำคัญ ไม่ว่าจะเป็นเสื้อกีฬา ภาพมงคล หรือภาพครอบครัว ให้เป็นงานศิลปะที่มีคุณค่า\n"
                        f"พิถีพิถันในการประกอบและจัดวางทรงอย่างตั้งใจ เพื่อให้ภาพของคุณออกมาสวยงามที่สุด\n"
                        f"เหมาะสำหรับนำไปประดับตกแต่งบ้าน หรือส่งต่อเป็นของขวัญชิ้นพิเศษในโอกาสสำคัญครับ 🏡{note_txt}\n\n"
                        f"{contact_blk}\n\n"
                        f"{shop_tag} #กรอบรูปของขวัญ #กรอบภาพมงคล #กรอบเสื้อบอล #ของแต่งบ้าน #ภาพติดผนัง"
                    )
                },
                {
                    "style": "แบบสั่งทำตามใจลูกค้า",
                    "text": (
                        f"🎨 อยากได้กรอบรูปโทนสีไหน หรือขนาดเท่าไหร่ สามารถสั่งทำตามต้องการได้เลยครับ\n"
                        f"ทางร้านมีแบบไม้ ลวดลาย และเฉดสีกรอบให้เลือกหลากหลาย เข้ากับทุกสไตล์ห้อง\n"
                        f"ประกอบงานด้วยความชำนาญ เก็บงานเรียบร้อย ในราคาที่สมเหตุสมผลและจับต้องได้\n"
                        f"ยินดีให้คำแนะนำและประเมินราคาฟรี สนใจทักเข้ามาปรึกษาแบบกันก่อนได้เลยครับ{note_txt}\n\n"
                        f"{contact_blk}\n\n"
                        f"{shop_tag} #สั่งตัดกรอบรูป #กรอบรูปสั่งทำ #ร้านทำกรอบรูป #กรอบรูปตามสั่ง #รับทำกรอบรูป"
                    )
                }
            ],
            "first_comment": f"📌 {page_name} ยินดีให้บริการครับ!\n{contact_blk}\n(บริการประเมินราคาฟรี ปรึกษาแบบและขนาดได้ตลอดครับ)"
        }


def chat_with_gemini_copilot(
    user_message: str,
    page_id: str,
    image_path: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    current_captions: Optional[List[Dict[str, str]]] = None,
    first_comment: Optional[str] = None
) -> Dict[str, Any]:
    """
    สนทนาโต้ตอบอย่างชาญฉลาดเหมือนพาร์ทเนอร์/ผู้ช่วยการตลาด (ไม่ใช่แค่บอท)
    สามารถรับคำสั่งปรับแก้แคปชัน เปลี่ยนโทนภาษา ใส่พิกัด หรือตั้งเวลาโพสต์ได้
    """
    api_key = get_setting("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
    page = get_page(page_id) or {}
    page_name = page.get("name", "เพจบริการ")
    phone = page.get("phone", "08X-XXX-XXXX")
    line_id = page.get("line_id", "@contact")
    service_area = page.get("service_area", "ทั่วประเทศ")

    clean_page_name = re.sub(r'[\s\.\-_/]+', '', page_name) if page_name else "ศรศิลป์"
    if not api_key:
        return {
            "needs_api_key": True,
            "reply_text": (
                "💡 เพื่อเปิดใช้งาน **\"AI ผู้ช่วยการตลาดอัจฉริยะ\"** เต็มรูปแบบ (คุยโต้ตอบ สั่งแก้คำ ปรับโทนกวนๆ หรือดัดแปลงตามสั่ง):\n\n"
                "ระบบต้องการ **Gemini API Key (ฟรี)** ครับ!\n\n"
                "วิธีรับคีย์ฟรี (ใช้เวลา 1 นาที):\n"
                "1. เข้าเว็บ https://aistudio.google.com/app/apikey (ล็อกอินด้วย Gmail)\n"
                "2. กดปุ่ม 'Create API key' แล้วคัดลอกรหัสที่ขึ้นต้นด้วย AIzaSy...\n"
                "3. **นำรหัสนั้นมาวางส่งในแชทนี้ได้เลยครับ!** บอทจะบันทึกและเชื่อมต่อสมองกล AI ให้ทันที 🧠✨"
            )
        }

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        # จัดเตรียมประวัติการคุย
        formatted_history = []
        if history:
            for h in history[-8:]:
                formatted_history.append(f"{h.get('role', 'user')}: {h.get('content', '')}")
        history_context = "\n".join(formatted_history) if formatted_history else "เพิ่งเริ่มการสนทนา"

        # แคปชันปัจจุบัน (ถ้ามี)
        drafts_context = ""
        if current_captions:
            for i, c in enumerate(current_captions, 1):
                drafts_context += f"- แบบที่ {i} [{c.get('style')}]: {c.get('text')}\n"

        prompt = f"""
คุณคือ "น้องโพสต์อีส" AI อัจฉริยะคู่หูพาร์ทเนอร์และผู้ช่วยส่วนตัวสารพัดประโยชน์ของลูกพี่/เจ้าของธุรกิจ:
- ธุรกิจปัจจุบันที่ดูแล: {page_name} (เบอร์โทร: {phone}, LINE ID: {line_id}, พื้นที่: {service_area})

🌟 ความสามารถและบทบาทของคุณ:
1. 💬 คุยเล่น สัพเพเหระ และเป็นเพื่อนคู่คิด (คุยได้ทุกเรื่องตามใจลูกพี่! สั่งอะไรก็พร้อมทำให้หมด):
   - คุยเล่นทั่วไป, ถามสารทุกข์สุกดิบ, เล่าเรื่องตลก, เล่นมุกฮาๆ, ให้กำลังใจเวลาเหนื่อย, แนะนำเพลง, แนะนำของกินเที่ยงนี้
   - ตอบคำถามความรู้ทั่วไป, ปรึกษาไอเดียธุรกิจ, ปรึกษาปัญหาชีวิต, หรือสั่งให้ทำอะไรก็ทำได้หมด (เช่น "แต่งกลอนให้หน่อย", "แปลภาษา", "คิดชื่อร้านเท่ๆ", "เล่าเรื่องตลกสั้นๆ", "คำนวณเลข", "เล่นเกมทายปัญหา")
   - มีบุคลิกฉลาด ร่าเริง อารมณ์ดี กวนๆ น่ารัก เป็นกันเองสุดๆ เรียกผู้ใช้ว่า "ลูกพี่" หรือ "พี่" ได้อย่างสนิทสนม ไม่ใช่บอทแข็งๆ ทื่อๆ!

2. 📝 ผู้เชี่ยวชาญการตลาดและโพสต์คอนเทนต์ (ใส่ใจรายละเอียด สุภาพ จริงใจ ไม่เวอร์):
   - เมื่อลูกพี่ส่งข้อมูลหน้างาน หรือสั่งแต่ง/แก้แคปชัน (เช่น "แต่งแคปชันให้หน่อย", "สั้นลง", "ทางการ", "เน้นใส่ใจ", "เน้นโปรโมชัน") ให้จัดแคปชันให้อย่างมืออาชีพ
   - กฎเหล็กของแคปชัน:
     * ความยาวเนื้อหาต้องมีอย่างน้อย 4 ประโยคขึ้นไป และเขียนให้เจาะจงเกี่ยวข้องกับชิ้นงานในรูปภาพจริง
     * โทนสุภาพ จริงใจ สวยงาม ไม่เวอร์ ไม่โอเวอร์ และให้คำว่า 'งานเนี๊ยบ' หรือ 'พรีเมี่ยม' เบาๆ ลง ไม่ยัดเยียดซ้ำซ้อน เน้นใส่ใจรายละเอียด เก็บงานเรียบร้อย แข็งแรงทนทาน
     * ท้ายแคปชันทุกอัน (ก่อนแฮชแท็ก) ต้องลงท้ายด้วย:
       📞 โทร: {phone}
       📲 LINE: {line_id}
       📍 {service_area}
     * แฮชแท็กอันแรกสุดต้องเป็นชื่อร้าน #{clean_page_name} เสมอ ตามด้วยแฮชแท็กอื่นๆ ที่เกี่ยวกับรูปภาพ
   - เมื่อผู้ใช้สั่งเรื่องแคปชัน ให้ใส่ "has_captions": true และส่งแคปชันใน captions
   - หากผู้ใช้แค่คุยเล่น ชวนคุย หรือสั่งงานทั่วไปที่ไม่ใช่แคปชัน ให้ใส่ "has_captions": false และตอบพูดคุยอย่างเต็มที่ใน reply_text

3. ⏰ รับคำสั่งตั้งเวลาโพสต์:
   - ถ้าผู้ใช้สั่งเวลา เช่น "โพสต์ตอน 6 โมงเย็น", "พรุ่งนี้ 9 โมง" ให้แปลงเป็น YYYY-MM-DDTHH:mm ใน schedule_datetime

ประวัติการสนทนาที่ผ่านมา:
{history_context}

แคปชันที่เคยร่างไว้ล่าสุด (ถ้ามี):
{drafts_context}

ข้อความล่าสุดจากผู้ใช้:
"{user_message}"

กรุณาตอบกลับในรูปแบบ JSON ตามโครงสร้างนี้เท่านั้น (ห้ามใส่ Markdown code block ครอบ หรือถ้ามีให้ตัดออก):
{{
  "reply_text": "ข้อความที่คุณคุยตอบผู้ใช้ (คุยเล่น ตอบคำถาม เล่นมุก ทำตามสั่ง หรือคุยตอบอย่างมีชีวิตชีวา)",
  "has_captions": true หรือ false (เป็น true เฉพาะเมื่อมีแคปชันใหม่/ปรับแคปชันให้ผู้ใช้เลือก),
  "captions": [
    {{
      "style": "ชื่อสไตล์ เช่น สไตล์กวนๆ วัยรุ่น หรือ แคปชันเปิดร้าน",
      "text": "เนื้อหาแคปชันพร้อมแฮชแท็ก"
    }}
  ],
  "first_comment": "คอมเมนต์แรกสำหรับปักหมุดข้อมูลติดต่อ (ใส่เฉพาะกรณีมีแคปชัน)",
  "schedule_datetime": "YYYY-MM-DDTHH:mm หรือ null ถ้าไม่ได้ระบุเวลา"
}}
"""
        contents = []
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                img_bytes = f.read()
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

        contents.append(prompt)

        candidate_models = ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3-flash-preview", "gemini-3.8-flash", "gemini-flash-latest"]
        response = None
        for mod in candidate_models:
            try:
                response = client.models.generate_content(
                    model=mod,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.7
                    )
                )
                if response and response.text:
                    break
            except Exception as mod_err:
                print(f"Copilot model {mod} failed: {mod_err}, trying next...")
                continue

        if not response or not response.text:
            return {
                "reply_text": "ขออภัยครับ ตอนนี้การเชื่อมต่อ AI มีความหนาแน่นชั่วคราว ลองส่งข้อความอีกครั้งนะครับ",
                "has_captions": False
            }

        response_text = response.text.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            response_text = "\n".join(lines).strip()

        try:
            data = json.loads(response_text)
        except Exception as json_err:
            m = re.search(r'"reply_text"\s*:\s*"((?:\\.|[^"\\])*)"', response_text)
            if m:
                val = m.group(1).replace('\\"', '"').replace('\\n', '\n')
                data = {"reply_text": val, "has_captions": False}
            else:
                clean_lines = []
                for ln in response_text.split("\n"):
                    if not any(k in ln for k in ['"reply_text"', '"has_captions"', '"captions"', '"first_comment"', '{', '}']):
                        clean_lines.append(ln.strip().strip('",'))
                clean_txt = "\n".join(l for l in clean_lines if l)
                data = {"reply_text": clean_txt if clean_txt else response_text, "has_captions": False}

        # รับประกันว่าแคปชันที่ AI แต่งในแชทจะมีเบอร์โทร ไลน์ โลเคชั่น และแฮชแท็กชื่อร้านอันแรกเสมอ
        if data.get("has_captions") and data.get("captions"):
            for c in data.get("captions", []):
                c["text"] = ensure_contact_and_hashtags(c.get("text", ""), phone, line_id, service_area, page_name)

        return data

    except Exception as e:
        print(f"Gemini Copilot Error: {e}")
        return {
            "error": str(e),
            "reply_text": f"ขออภัยครับ เกิดข้อผิดพลาดในการประมวลผลของ AI: {e}"
        }
