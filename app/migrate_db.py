import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "poster.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. ลบเพจ pigfeed
cursor.execute("DELETE FROM pages WHERE id='pigfeed'")

# 2. ปรับแต่งเพจหลัก
cursor.execute("""
UPDATE pages 
SET name='ศรศิลป์ กรอบรูป', icon='🖼️', phone='064-964-5353', line_id='0649645353', service_area='พิกัดร้าน https://maps.app.goo.gl/uMoSsvqq3JveQo479'
WHERE id='slidetruck'
""")

# 3. เพิ่มการตั้งค่า watermark
settings = [
    ('watermark_enabled', '1'),
    ('watermark_position', 'auto'),
    ('watermark_opacity', '90'),
    ('watermark_scale', '18')
]
for k, v in settings:
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))

conn.commit()
rows = cursor.execute("SELECT id, name, icon FROM pages").fetchall()
print("Updated pages in database:")
for r in rows:
    print(r)

conn.close()
