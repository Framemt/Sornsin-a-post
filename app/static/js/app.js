// PostEase AI Studio - App Controller (ศรศิลป์ กรอบรูป)
let uploadedImages = []; // Array of { originalUrl, watermarkedUrl, filename }
let activeImageIdx = 0;
let currentWatermarkPosition = "auto";
let isWatermarkOn = true;

let currentCaptions = [];
let selectedCaptionIdx = 0;
let publishMode = "now"; // 'now' | 'schedule'

let selectedScheduleDate = new Date();
let selectedDayOffset = 0; // 0=วันนี้, 1=พรุ่งนี้, 2=มะรืนนี้

// ข้อมูลร้านเริ่มต้น (ศรศิลป์ กรอบรูป)
const shopInfo = {
  name: "ศรศิลป์ กรอบรูป",
  phone: "064-964-5353",
  lineId: "0649645353",
  location: "https://maps.app.goo.gl/uMoSsvqq3JveQo479",
  area: "หน้าร้าน และจัดส่งปลอดภัยทั่วประเทศ",
};

// --- 1. การจัดการรูปภาพและการอัปโหลดหลายรูป (Multi-Image / Album) ---

async function previewImages(event) {
  const files = event.target.files;
  if (!files || files.length === 0) return;

  const btnGenerate = document.getElementById("btnGenerateAi");
  const origBtnHtml = btnGenerate.innerHTML;
  btnGenerate.innerHTML = `<span>⏳</span> กำลังอัปโหลดรูปภาพ...`;
  btnGenerate.disabled = true;

  const formData = new FormData();
  for (let i = 0; i < files.length; i++) {
    formData.append("files", files[i]);
  }

  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();

    if (data.success && data.image_paths && data.image_paths.length > 0) {
      uploadedImages = data.image_paths.map((p, idx) => ({
        originalUrl: p,
        watermarkedUrl: p,
        filename: data.filenames ? data.filenames[idx] : `img_${idx}.jpg`,
      }));

      activeImageIdx = 0;
      renderImageGallery();

      // สั่ง AI วิเคราะห์รูปแรกทันที
      requestAiCaptions();
    } else {
      alert("❌ อัปโหลดรูปภาพไม่สำเร็จ: " + (data.error || "เกิดข้อผิดพลาด"));
    }
  } catch (err) {
    alert("❌ เกิดข้อผิดพลาดในการเชื่อมต่อเซิร์ฟเวอร์: " + err);
  } finally {
    btnGenerate.innerHTML = origBtnHtml;
    btnGenerate.disabled = false;
  }
}

function renderImageGallery() {
  if (uploadedImages.length === 0) return;

  const previewContainer = document.getElementById("previewContainer");
  const placeholderView = document.getElementById("placeholderView");
  const thumbnailStrip = document.getElementById("thumbnailStrip");
  const thumbnailGrid = document.getElementById("thumbnailGrid");
  const albumBadge = document.getElementById("albumCountBadge");
  const fbMultiBadge = document.getElementById("fbMultiBadge");

  placeholderView.classList.add("hidden");
  previewContainer.classList.remove("hidden");

  // อัปเดตรูปหลัก
  const activeImg = uploadedImages[activeImageIdx];
  const cacheBuster = `?t=${Date.now()}`;
  const displayUrl =
    isWatermarkOn && activeImg.watermarkedUrl
      ? `${activeImg.watermarkedUrl}${cacheBuster}`
      : activeImg.originalUrl;
  const imgElem = document.getElementById("imagePreview");
  imgElem.src = displayUrl;

  // อัปเดตรูปในการ์ดพรีวิว Facebook
  const fbImg = document.getElementById("fbPreviewImage");
  if (fbImg) fbImg.src = displayUrl;

  // จัดการแท็กนับจำนวนรูป
  if (uploadedImages.length > 1) {
    thumbnailStrip.classList.remove("hidden");
    document.getElementById("thumbCountText").innerText = uploadedImages.length;
    albumBadge.innerText = `อัลบั้ม ${uploadedImages.length} รูป 📸`;
    if (fbMultiBadge) {
      fbMultiBadge.classList.remove("hidden");
      fbMultiBadge.innerText = `+${uploadedImages.length - 1} รูป`;
    }

    thumbnailGrid.innerHTML = "";
    uploadedImages.forEach((img, idx) => {
      const thumb = document.createElement("div");
      thumb.className = `relative w-16 h-16 rounded-xl overflow-hidden cursor-pointer border-2 transition flex-shrink-0 group/th ${
        idx === activeImageIdx
          ? "border-emerald-500 ring-2 ring-emerald-500/50 shadow-md"
          : "border-slate-800 opacity-70 hover:opacity-100"
      }`;
      const tImg = document.createElement("img");
      tImg.src =
        isWatermarkOn && img.watermarkedUrl
          ? `${img.watermarkedUrl}${cacheBuster}`
          : img.originalUrl;
      tImg.className = "w-full h-full object-cover";
      thumb.appendChild(tImg);

      // ปุ่มลบรูปแต่ละใบ (Delete Thumbnail)
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.title = "ลบรูปนี้";
      delBtn.className = "absolute top-1 right-1 w-5 h-5 bg-rose-600/90 hover:bg-rose-500 text-white rounded-full flex items-center justify-center text-[10px] font-bold shadow transition z-10";
      delBtn.innerHTML = "✕";
      delBtn.onclick = (e) => {
        e.stopPropagation();
        removeUploadedImage(idx);
      };
      thumb.appendChild(delBtn);

      thumb.onclick = () => {
        activeImageIdx = idx;
        renderImageGallery();
      };
      thumbnailGrid.appendChild(thumb);
    });
  } else if (uploadedImages.length === 1) {
    thumbnailStrip.classList.remove("hidden");
    document.getElementById("thumbCountText").innerText = "1";
    albumBadge.innerText = "1 รูปภาพ";
    if (fbMultiBadge) fbMultiBadge.classList.add("hidden");

    thumbnailGrid.innerHTML = "";
    const thumb = document.createElement("div");
    thumb.className = "relative w-16 h-16 rounded-xl overflow-hidden border-2 border-emerald-500 ring-2 ring-emerald-500/50 shadow-md flex-shrink-0";
    const tImg = document.createElement("img");
    tImg.src =
      isWatermarkOn && uploadedImages[0].watermarkedUrl
        ? `${uploadedImages[0].watermarkedUrl}${cacheBuster}`
        : uploadedImages[0].originalUrl;
    tImg.className = "w-full h-full object-cover";
    thumb.appendChild(tImg);

    // ปุ่มลบรูป
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.title = "ลบรูปนี้";
    delBtn.className = "absolute top-1 right-1 w-5 h-5 bg-rose-600/90 hover:bg-rose-500 text-white rounded-full flex items-center justify-center text-[10px] font-bold shadow transition z-10";
    delBtn.innerHTML = "✕";
    delBtn.onclick = (e) => {
      e.stopPropagation();
      removeUploadedImage(0);
    };
    thumb.appendChild(delBtn);
    thumbnailGrid.appendChild(thumb);
  } else {
    thumbnailStrip.classList.add("hidden");
    albumBadge.innerText = "รองรับหลายรูป (Album)";
    if (fbMultiBadge) fbMultiBadge.classList.add("hidden");
  }
}

function removeUploadedImage(idx) {
  if (uploadedImages.length <= 1) {
    uploadedImages = [];
    activeImageIdx = 0;
    document.getElementById("previewContainer").classList.add("hidden");
    document.getElementById("placeholderView").classList.remove("hidden");
    document.getElementById("thumbnailStrip").classList.add("hidden");
    document.getElementById("albumCountBadge").innerText = "รองรับหลายรูป (Album)";
    const fbMultiBadge = document.getElementById("fbMultiBadge");
    if (fbMultiBadge) fbMultiBadge.classList.add("hidden");
    const fbImg = document.getElementById("fbPreviewImage");
    if (fbImg) fbImg.src = "";
    return;
  }

  uploadedImages.splice(idx, 1);
  if (activeImageIdx >= uploadedImages.length) {
    activeImageIdx = uploadedImages.length - 1;
  }
  renderImageGallery();
}

// --- 2. การควบคุมลายน้ำแบบ Interactive (Watermark Controls) ---

function toggleWatermarkUsage() {
  const toggle = document.getElementById("watermarkToggle");
  isWatermarkOn = toggle.checked;

  const badge = document.getElementById("wmStatusBadge");
  if (isWatermarkOn) {
    badge.className =
      "text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30";
    badge.innerText = "เปิดใช้งาน";
    // ถ้ามีรูป ให้ใส่ลายน้ำทันที
    if (uploadedImages.length > 0) {
      applyWatermarkToActiveImage(currentWatermarkPosition);
    }
  } else {
    badge.className =
      "text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700";
    badge.innerText = "ปิดลายน้ำ";
    renderImageGallery();
  }
}

async function selectWatermarkPosition(pos) {
  currentWatermarkPosition = pos;

  // อัปเดตสไตล์ปุ่ม
  const buttons = document.querySelectorAll(".wm-btn");
  buttons.forEach((btn) => btn.classList.remove("active"));
  const targetBtn = document.getElementById(`wmBtn-${pos}`);
  if (targetBtn) targetBtn.classList.add("active");

  const posNames = {
    auto: "🤖 AI อัตโนมัติ",
    top_left: "↖️ มุมบนซ้าย",
    top_right: "↗️ มุมบนขวา",
    bottom_left: "↙️ มุมล่างซ้าย",
    bottom_right: "↘️ มุมล่างขวา",
  };
  document.getElementById("activePositionName").innerText =
    posNames[pos] || pos;

  if (uploadedImages.length > 0 && isWatermarkOn) {
    const lbl = document.getElementById("currentImageSizeLabel");
    if (lbl) lbl.innerText = "⏳ กำลังย้ายลายน้ำ...";
    await applyWatermarkToActiveImage(pos);
    if (lbl) lbl.innerText = "พรีวิวรูปภาพ";
  }
}

async function applyWatermarkToActiveImage(pos) {
  if (uploadedImages.length === 0) return;
  const activeImg = uploadedImages[activeImageIdx];
  const actualPos = pos === "auto" ? "bottom_right" : pos;

  try {
    const res = await fetch("/api/watermark/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_path: activeImg.originalUrl,
        position: actualPos,
        opacity: 0.88,
        scale: 0.18,
      }),
    });
    const data = await res.json();
    if (data.success && data.watermarked_image_path) {
      activeImg.watermarkedUrl = data.watermarked_image_path;
      renderImageGallery();
    }
  } catch (err) {
    console.error("Watermark preview error:", err);
  }
}

// --- 3. การสร้างและจัดการแคปชัน (ศรศิลป์ กรอบรูป) ---

function updateDefaultCaptions() {
  const contactBlock = `📞 โทร: ${shopInfo.phone}\n📲 LINE: ${shopInfo.lineId}\n📍 พิกัดร้าน: ${shopInfo.location}\n🚚 จัดส่งปลอดภัยทั่วประเทศครับ`;

  currentCaptions = [
    {
      style: "แบบใส่ใจรายละเอียด",
      title: "⚡ 1. ใส่ใจรายละเอียด",
      text: `🖼️ เพิ่มความลงตัวให้กับภาพถ่ายและผลงานชิ้นสำคัญ ด้วยงานกรอบรูปสั่งทำจากทางร้าน\nช่างของเราใส่ใจทุกขั้นตอนการเข้ามุม เก็บงานเรียบร้อยสวยงามทุกมิติ\nคัดสรรวัสดุกรอบคุณภาพ แข็งแรงทนทาน ช่วยขับเน้นให้ชิ้นงานของคุณดูโดดเด่นสะดุดตา\nนำไปจัดวางมุมไหนของบ้านหรือที่ทำงานก็ดูดี พร้อมปกป้องผลงานให้อยู่ได้ยาวนานครับ ✨\n\n${contactBlock}\n\n#ศรศิลป์กรอบรูป #รับทำกรอบรูป #สั่งตัดกรอบรูป #ของแต่งบ้าน #กรอบรูปสวย #ร้านกรอบรูป`,
    },
    {
      style: "แบบคุณค่าและความทรงจำ",
      title: "✨ 2. คุณค่าและความทรงจำ",
      text: `🌟 ทุกเรื่องราวและความทรงจำมีความหมายที่น่าจดจำเสมอ\nเราพร้อมช่วยดูแลและเปลี่ยนชิ้นงานสำคัญ ไม่ว่าจะเป็นเสื้อกีฬา ภาพมงคล หรือภาพครอบครัว ให้เป็นงานศิลปะที่มีคุณค่า\nพิถีพิถันในการประกอบและจัดวางทรงอย่างตั้งใจ เพื่อให้ภาพของคุณออกมาสวยงามที่สุด\nเหมาะสำหรับนำไปประดับตกแต่งบ้าน หรือส่งต่อเป็นของขวัญชิ้นพิเศษในโอกาสสำคัญครับ 🏡\n\n${contactBlock}\n\n#ศรศิลป์กรอบรูป #กรอบรูปของขวัญ #กรอบภาพมงคล #กรอบเสื้อบอล #ของแต่งบ้าน #ภาพติดผนัง`,
    },
    {
      style: "แบบสั่งทำตามใจลูกค้า",
      title: "🎨 3. สั่งทำตามใจลูกค้า",
      text: `🎨 อยากได้กรอบรูปโทนสีไหน หรือขนาดเท่าไหร่ สามารถสั่งทำตามต้องการได้เลยครับ\nทางร้านมีแบบไม้ ลวดลาย และเฉดสีกรอบให้เลือกหลากหลาย เข้ากับทุกสไตล์ห้อง\nประกอบงานด้วยความชำนาญ เก็บงานเรียบร้อย ในราคาที่สมเหตุสมผลและจับต้องได้\nยินดีให้คำแนะนำและประเมินราคาฟรี สนใจทักเข้ามาปรึกษาแบบกันก่อนได้เลยครับ 🤝\n\n${contactBlock}\n\n#ศรศิลป์กรอบรูป #สั่งตัดกรอบรูป #กรอบรูปสั่งทำ #ร้านทำกรอบรูป #กรอบรูปตามสั่ง #รับทำกรอบรูป`,
    },
  ];

  document.getElementById("firstComment").value =
    `📌 ศรศิลป์ กรอบรูป ยินดีให้บริการครับ!\n${contactBlock}\n(บริการประเมินราคาฟรี ปรึกษาแบบและขนาดได้ตลอดครับ)`;

  renderCaptionCards();
  selectCaption(0);
}

function renderCaptionCards() {
  const container = document.getElementById("captionCardsContainer");
  if (!container) return;

  container.innerHTML = "";
  currentCaptions.forEach((cap, idx) => {
    const isSelected = idx === selectedCaptionIdx;
    const card = document.createElement("div");
    card.id = `card-${idx}`;
    card.onclick = () => selectCaption(idx);
    card.className = `card-interactive bg-slate-900/90 border border-slate-800 p-3 rounded-xl cursor-pointer relative ${
      isSelected ? "active-card" : ""
    }`;

    const badgeColors = [
      "text-emerald-400 bg-emerald-500/15 border-emerald-500/30",
      "text-amber-400 bg-amber-500/15 border-amber-500/30",
      "text-teal-400 bg-teal-500/15 border-teal-500/30",
    ];

    card.innerHTML = `
            <div class="flex items-center justify-between mb-1.5">
                <span class="text-[11px] font-bold px-2 py-0.5 rounded-md border ${badgeColors[idx % 3]}">
                    ${cap.title || cap.style}
                </span>
                ${isSelected ? '<span class="text-emerald-400 text-xs font-semibold check-mark">✓ เลือกอยู่</span>' : ""}
            </div>
            <p class="text-xs text-slate-300 leading-relaxed line-clamp-3 break-words" id="text-${idx}">
                ${cap.text.replace(/\n/g, " ")}
            </p>
        `;
    container.appendChild(card);
  });
}

function selectCaption(idx) {
  selectedCaptionIdx = idx;
  const cards = document.querySelectorAll(".card-interactive");
  cards.forEach((c) => c.classList.remove("active-card"));

  const targetCard = document.getElementById(`card-${idx}`);
  if (targetCard) targetCard.classList.add("active-card");

  // อัปเดตเครื่องหมายถูก
  renderCaptionCards();

  if (currentCaptions[idx]) {
    const finalElem = document.getElementById("finalCaption");
    finalElem.value = currentCaptions[idx].text;
    updateCharCount();
    updateLiveFacebookCard();
  }
}

// อัปเดตพรีวิว Facebook เมื่อผู้ใช้พิมพ์ข้อความแคปชันเอง
document.addEventListener("DOMContentLoaded", () => {
  const finalElem = document.getElementById("finalCaption");
  if (finalElem) {
    finalElem.addEventListener("input", () => {
      updateCharCount();
      updateLiveFacebookCard();
    });
  }
});

function updateCharCount() {
  const val = document.getElementById("finalCaption").value;
  const charElem = document.getElementById("charCount");
  if (charElem) charElem.innerText = `${val.length} ตัวอักษร`;
}

function updateLiveFacebookCard() {
  const val = document.getElementById("finalCaption").value;
  const previewText = document.getElementById("fbPreviewCaption");
  if (previewText) {
    previewText.innerText = val || "(ข้อความแคปชันจะปรากฏตรงนี้)";
  }
}

// --- 2.5 การเลือกหมวดหมู่งานกรอบรูป (Frame Categories) ---
let selectedCategory = "all";

function selectFrameCategory(cat) {
  selectedCategory = cat;
  const labels = {
    all: "🖼️ สั่งทำทั่วไป",
    auspicious: "🌟 กรอบรูปมงคล",
    gift: "🎓 ของขวัญ/ปริญญา",
    wedding: "💍 แต่งงาน/พรีเวดดิ้ง",
    mirror: "🪞 กระจกเงาแต่งบ้าน",
  };

  const labelElem = document.getElementById("selectedCategoryLabel");
  if (labelElem) labelElem.innerText = labels[cat] || labels.all;

  document.querySelectorAll(".cat-btn").forEach((btn) => {
    btn.classList.remove("active", "border-emerald-500", "text-emerald-300", "bg-emerald-500/20");
    btn.classList.add("border-slate-700", "text-slate-300", "bg-slate-800");
  });

  const activeBtn = document.getElementById(`catBtn-${cat}`);
  if (activeBtn) {
    activeBtn.classList.remove("border-slate-700", "text-slate-300", "bg-slate-800");
    activeBtn.classList.add("active", "border-emerald-500", "text-emerald-300", "bg-emerald-500/20");
  }

  // หากมีรูปอยู่แล้ว ให้สั่ง AI เจนแคปชันใหม่ตามหมวดหมู่นั้นทันที
  if (uploadedImages.length > 0) {
    requestAiCaptions();
  }
}

// ขอให้ AI สแกนรูปและสร้างแคปชัน 3 สไตล์
async function requestAiCaptions() {
  if (uploadedImages.length === 0) {
    alert("กรุณาเลือกรูปภาพก่อนครับ");
    return;
  }

  const btn = document.getElementById("btnGenerateAi");
  const origText = btn.innerHTML;
  btn.innerHTML = `<span>⏳</span> AI กำลังวิเคราะห์รูปและติดลายน้ำ...`;
  btn.disabled = true;

  const notes = document.getElementById("extraNotes").value;
  const primaryImg = uploadedImages[0];

  try {
    const res = await fetch("/api/generate-captions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_path: primaryImg.originalUrl,
        page_id: "slidetruck",
        extra_notes: notes,
        category: selectedCategory,
      }),
    });
    const data = await res.json();

    if (data.captions && data.captions.length > 0) {
      currentCaptions = data.captions.map((c, i) => ({
        style: c.style,
        title: `${i + 1}. ${c.style}`,
        text: c.text,
      }));

      if (data.first_comment) {
        document.getElementById("firstComment").value = data.first_comment;
      }

      // นำลายน้ำที่ AI เจาะจงมุมมาใส่รูป
      if (data.watermarked_image_path) {
        primaryImg.watermarkedUrl = data.watermarked_image_path;
        if (data.watermark_position) {
          selectWatermarkPosition(data.watermark_position);
        }
      }

      renderCaptionCards();
      selectCaption(0);
      renderImageGallery();

      // Confetti feedback
      if (typeof confetti === "function") {
        confetti({ particleCount: 40, spread: 50, origin: { y: 0.5 } });
      }
    } else {
      alert("❌ ไม่สามารถแต่งแคปชันได้: " + (data.error || "เกิดข้อผิดพลาด"));
    }
  } catch (err) {
    alert("❌ เกิดข้อผิดพลาดในการเรียก AI: " + err);
  } finally {
    btn.innerHTML = origText;
    btn.disabled = false;
  }
}

// --- 4. การจัดการเวลาและการตั้งเวลาโพสต์ (Thai Time Scheduler) ---

function selectPublishMode(mode) {
  publishMode = mode;
  const modeBtnNow = document.getElementById("modeBtnNow");
  const modeBtnSchedule = document.getElementById("modeBtnSchedule");
  const container = document.getElementById("scheduleTimeContainer");
  const btnText = document.getElementById("submitBtnText");

  if (mode === "schedule") {
    modeBtnSchedule.className =
      "py-2 rounded-lg bg-emerald-600 text-white font-bold transition shadow-sm";
    modeBtnNow.className =
      "py-2 rounded-lg text-slate-400 hover:text-white font-medium transition";
    container.classList.remove("hidden");
    btnText.innerText = "ยืนยันและบันทึกลงคิวโพสต์";

    initTimeSelectors();
    const now = new Date();
    if (now.getHours() < 18) {
      setQuickPresetFixed(0, 18, 0); // เย็นนี้ 18:00
    } else {
      setQuickPresetFixed(1, 18, 0); // พรุ่งนี้ 18:00
    }
  } else {
    modeBtnNow.className =
      "py-2 rounded-lg bg-emerald-600 text-white font-bold transition shadow-sm";
    modeBtnSchedule.className =
      "py-2 rounded-lg text-slate-400 hover:text-white font-medium transition";
    container.classList.add("hidden");
    btnText.innerText = "ยืนยันและโพสต์ทันที";
  }
}

function initTimeSelectors() {
  const hrSel = document.getElementById("timeHourSelect");
  if (hrSel && hrSel.children.length === 0) {
    for (let h = 0; h < 24; h++) {
      const opt = document.createElement("option");
      const val = h.toString().padStart(2, "0");
      opt.value = val;
      opt.innerText = `${val}:00 น.`;
      if (h === 18) opt.selected = true;
      hrSel.appendChild(opt);
    }
  }
}

function updateScheduleState(dateObj) {
  selectedScheduleDate = dateObj;
  const yr = dateObj.getFullYear();
  const mo = (dateObj.getMonth() + 1).toString().padStart(2, "0");
  const da = dateObj.getDate().toString().padStart(2, "0");
  const hr = dateObj.getHours().toString().padStart(2, "0");
  const mi = dateObj.getMinutes().toString().padStart(2, "0");

  const isoStr = `${yr}-${mo}-${da} ${hr}:${mi}:00`;
  document.getElementById("scheduledAt").value = isoStr;

  const thaiMonths = [
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
  ];
  const dateStr = `${dateObj.getDate()} ${thaiMonths[dateObj.getMonth()]}`;
  const timeStr = `${hr}:${mi} น.`;

  document.getElementById("scheduleSummaryText").innerText =
    `กำหนดปล่อยโพสต์: วันที่ ${dateStr} เวลา ${timeStr}`;
}

function setQuickPresetMinutes(mins) {
  const target = new Date();
  target.setMinutes(target.getMinutes() + mins);
  target.setSeconds(0, 0);
  updateScheduleState(target);
}

function setQuickPresetFixed(dayOffset, hour, minute) {
  const target = new Date();
  target.setDate(target.getDate() + dayOffset);
  target.setHours(hour, minute, 0, 0);
  updateScheduleState(target);
}

function onTimeDropdownChange() {
  const hour = parseInt(
    document.getElementById("timeHourSelect").value || "18",
  );
  const minute = parseInt(
    document.getElementById("timeMinuteSelect").value || "00",
  );
  const target = new Date(selectedScheduleDate);
  target.setHours(hour, minute, 0, 0);
  updateScheduleState(target);
}

// --- 5. การกระจายคิวอัตโนมัติ (Smart Auto-Spread) ---

async function autoSpreadAllQueuedPosts() {
  if (
    !confirm(
      "⚡ ยืนยันการจัดตารางคิวโพสต์ทั้งหมด?\nระบบจะกระจายโพสต์ที่รอเวลาอยู่ให้ทยอยโพสต์วันละ 1 โพสต์ เวลา 18:00 น. เรียงตามลำดับ ไม่ชนกันครับ",
    )
  ) {
    return;
  }

  try {
    const res = await fetch("/api/posts/auto-spread", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interval_days: 1, target_hour: 18 }),
    });
    const data = await res.json();
    if (data.success) {
      alert(`✅ ${data.message}`);
      if (typeof confetti === "function") {
        confetti({ particleCount: 70, spread: 60, origin: { y: 0.4 } });
      }
      updateQueueCount();
    } else {
      alert("❌ " + (data.message || "เกิดข้อผิดพลาด"));
    }
  } catch (err) {
    alert("❌ ไม่สามารถกระจายคิวได้: " + err);
  }
}

// --- 6. ส่งข้อมูลโพสต์ (Submit Post) ---

async function submitPost() {
  const caption = document.getElementById("finalCaption").value.trim();
  if (!caption) {
    alert("กรุณาระบุข้อความแคปชันก่อนโพสต์ครับ");
    return;
  }

  if (uploadedImages.length === 0) {
    alert("กรุณาเลือกรูปภาพงานกรอบรูปก่อนครับ");
    return;
  }

  // รูปภาพที่จะใช้โพสต์: ถ้าเปิดลายน้ำให้ใช้ watermarkedUrl
  const finalImagePaths = uploadedImages.map((img) =>
    isWatermarkOn && img.watermarkedUrl ? img.watermarkedUrl : img.originalUrl,
  );

  // ส่งเป็น array string ถ้ามีหลายรูป หรือ path เดียวถ้ามี 1 รูป
  const imagePayload =
    finalImagePaths.length > 1
      ? JSON.stringify(finalImagePaths)
      : finalImagePaths[0];

  const scheduledAt =
    publishMode === "schedule"
      ? document.getElementById("scheduledAt").value
      : null;
  const firstComment = document.getElementById("firstComment").value;
  const styleName = currentCaptions[selectedCaptionIdx]
    ? currentCaptions[selectedCaptionIdx].style
    : "แบบใส่ใจรายละเอียด";

  const btn = document.getElementById("btnSubmitPost");
  const origBtnText = btn.innerHTML;
  btn.innerHTML = `<span>⏳</span> กำลังโพสต์และส่งแจ้งเตือน...`;
  btn.disabled = true;

  try {
    const res = await fetch("/api/posts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: "slidetruck",
        image_path: imagePayload,
        caption: caption,
        first_comment: firstComment,
        caption_style: styleName,
        scheduled_at: scheduledAt,
        status: publishMode === "schedule" ? "scheduled" : "published",
      }),
    });

    const data = await res.json();
    const alertBox = document.getElementById("statusAlert");
    alertBox.classList.remove("hidden");

    if (data.success) {
      alertBox.className =
        "p-3.5 rounded-xl text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 block shadow-lg";
      alertBox.innerText = `✅ ${data.message || "บันทึกสำเร็จเรียบร้อย!"}`;

      // ยิง Confetti เฉลิมฉลอง
      if (typeof confetti === "function") {
        confetti({ particleCount: 100, spread: 80, origin: { y: 0.6 } });
      }

      updateQueueCount();
    } else {
      alertBox.className =
        "p-3.5 rounded-xl text-xs font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40 block shadow-lg";
      alertBox.innerText = `❌ ${data.error || "เกิดข้อผิดพลาดในการโพสต์"}`;
    }
  } catch (e) {
    alert("เกิดข้อผิดพลาด: " + e);
  } finally {
    btn.innerHTML = origBtnText;
    btn.disabled = false;
  }
}

// อัปเดตตัวเลขคิวในหน้าเว็บ
async function updateQueueCount() {
  try {
    const res = await fetch("/api/posts?status=scheduled");
    const posts = await res.json();
    const count = posts ? posts.length : 0;
    const qCountDisp = document.getElementById("queueCountDisplay");
    if (qCountDisp) qCountDisp.innerText = `${count} รายการ`;
    const nBadge = document.getElementById("navQueueBadge");
    if (nBadge) nBadge.innerText = `${count}`;
    const mBadge = document.getElementById("mobileQueueBadge");
    if (mBadge) mBadge.innerText = `${count}`;
  } catch (e) {
    console.error("Queue count error:", e);
  }
}

// เรียกเริ่มทำงานทันที
updateDefaultCaptions();
updateQueueCount();
