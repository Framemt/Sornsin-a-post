FROM python:3.11-slim

WORKDIR /app

# ตั้งค่าไม่ให้บัฟเฟอร์ stdout
ENV PYTHONUNBUFFERED=1

# ติดตั้ง requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกโฟลเดอร์โปรเจกต์
COPY app/ ./app/

# สร้างโฟลเดอร์สำหรับเก็บรูปอัปโหลด
RUN mkdir -p /app/app/static/uploads

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
