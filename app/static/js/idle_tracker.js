/**
 * idle_tracker.js - ตรวจจับการไม่มีการขยับ/ใช้งานหน้าเว็บ (Auto-Logout on 1-Hour Inactivity)
 * สำหรับระบบ ศรศิลป์ กรอบรูป
 */
(function() {
    // กำหนดเวลา 1 ชั่วโมง (3,600,000 มิลลิวินาที)
    let IDLE_TIMEOUT_MS = 60 * 60 * 1000;
    // แจ้งเตือนล่วงหน้า 2 นาทีก่อนหมดเวลา (58 นาที = 3,480,000 มิลลิวินาที)
    let WARNING_THRESHOLD_MS = 58 * 60 * 1000;
    
    const STORAGE_KEY = 'sornsiri_last_activity_ts';
    let warningElement = null;
    let isWarningShown = false;
    let lastThrottledWrite = 0;

    function getLastActivity() {
        const stored = localStorage.getItem(STORAGE_KEY);
        const parsed = stored ? parseInt(stored, 10) : 0;
        return isNaN(parsed) || parsed <= 0 ? Date.now() : parsed;
    }

    function recordActivity(force = false) {
        const now = Date.now();
        // Throttle บันทึกลง localStorage ทุก 2 วินาทีเพื่อประหยัดทรัพยากร
        if (force || now - lastThrottledWrite > 2000) {
            lastThrottledWrite = now;
            try {
                localStorage.setItem(STORAGE_KEY, now.toString());
            } catch (e) {
                // Ignore storage errors in private browsing
            }
        }
        if (isWarningShown) {
            hideWarning();
        }
    }

    function createWarningModal() {
        if (document.getElementById('idle-warning-modal')) {
            return document.getElementById('idle-warning-modal');
        }

        const modal = document.createElement('div');
        modal.id = 'idle-warning-modal';
        modal.className = 'fixed bottom-6 right-6 z-50 max-w-sm w-full bg-slate-900/95 border border-amber-500/40 rounded-2xl p-5 shadow-2xl backdrop-blur-xl transition-all duration-300 transform translate-y-4 opacity-0 pointer-events-none';
        modal.innerHTML = `
            <div class="flex items-start gap-3.5">
                <div class="w-10 h-10 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-xl flex-shrink-0 animate-pulse">
                    ⏳
                </div>
                <div class="flex-1 space-y-1.5">
                    <h4 class="text-sm font-bold text-amber-300 flex items-center justify-between">
                        <span>แจ้งเตือนเซสชันความปลอดภัย</span>
                    </h4>
                    <p class="text-xs text-slate-300 leading-relaxed">
                        ไม่มีการขยับหน้าเว็บมาแล้วเกือบ 1 ชม. ระบบจะออกจากระบบอัตโนมัติในอีก 
                        <span id="idle-countdown-sec" class="font-mono font-bold text-amber-400 bg-amber-500/20 px-1.5 py-0.5 rounded">120</span> วินาที
                    </p>
                    <div class="pt-2 flex items-center gap-2">
                        <button type="button" id="btn-stay-logged-in" class="flex-1 py-2 px-3 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs rounded-xl shadow transition">
                            ขยับใช้งานต่อ
                        </button>
                        <a href="/logout?reason=manual" class="py-2 px-3 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs rounded-xl border border-slate-700 transition">
                            ออกทันที
                        </a>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        modal.querySelector('#btn-stay-logged-in').addEventListener('click', (e) => {
            e.stopPropagation();
            recordActivity(true);
        });

        return modal;
    }

    function showWarning(remainingSeconds) {
        if (!warningElement) {
            warningElement = createWarningModal();
        }
        const countdownEl = warningElement.querySelector('#idle-countdown-sec');
        if (countdownEl) {
            countdownEl.innerText = Math.max(0, Math.ceil(remainingSeconds));
        }

        if (!isWarningShown) {
            isWarningShown = true;
            warningElement.classList.remove('translate-y-4', 'opacity-0', 'pointer-events-none');
            warningElement.classList.add('translate-y-0', 'opacity-100', 'pointer-events-auto');
        }
    }

    function hideWarning() {
        if (warningElement && isWarningShown) {
            isWarningShown = false;
            warningElement.classList.remove('translate-y-0', 'opacity-100', 'pointer-events-auto');
            warningElement.classList.add('translate-y-4', 'opacity-0', 'pointer-events-none');
        }
    }

    function doAutoLogout() {
        try {
            localStorage.removeItem(STORAGE_KEY);
        } catch (e) {}
        window.location.href = '/logout?reason=idle';
    }

    function checkInactivity() {
        const now = Date.now();
        const lastActive = getLastActivity();
        const elapsed = now - lastActive;

        if (elapsed >= IDLE_TIMEOUT_MS) {
            doAutoLogout();
            return;
        }

        if (elapsed >= WARNING_THRESHOLD_MS) {
            const remainingSec = (IDLE_TIMEOUT_MS - elapsed) / 1000;
            showWarning(remainingSec);
        } else {
            if (isWarningShown) {
                hideWarning();
            }
        }
    }

    // บันทึกกิจกรรมเมื่อมีการขยับเมาส์ คลิก แตะหน้าจอ พิมพ์ หรือเลื่อนหน้าเว็บ
    const activityEvents = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'click'];
    activityEvents.forEach(eventType => {
        window.addEventListener(eventType, () => recordActivity(false), { passive: true });
    });

    // ซิงค์ข้ามแท็บผ่าน localStorage
    window.addEventListener('storage', (e) => {
        if (e.key === STORAGE_KEY) {
            if (isWarningShown) {
                hideWarning();
            }
        }
    });

    // ตรวจสอบทันทีเมื่อเปิดแท็บกลับมาหรือโฟกัสหน้าต่าง
    window.addEventListener('focus', checkInactivity);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            checkInactivity();
        }
    });

    // ตรวจสอบเป็นระยะทุก 2.5 วินาที
    setInterval(checkInactivity, 2500);

    // บันทึกเวลาเริ่มต้นเมื่อเปิดหน้า
    if (!localStorage.getItem(STORAGE_KEY)) {
        recordActivity(true);
    }

    // Dev Helper สำหรับทดสอบ
    window.setIdleTimeoutForTesting = function(seconds) {
        IDLE_TIMEOUT_MS = seconds * 1000;
        WARNING_THRESHOLD_MS = Math.max(1000, (seconds - 15) * 1000);
        console.log(`[IdleTracker] Idle timeout set to ${seconds}s for testing.`);
    };
    window.simulateIdleLogout = function() {
        doAutoLogout();
    };

    console.log('[IdleTracker] 1-hour inactivity monitor activated (60 min).');
})();
