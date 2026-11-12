from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from .database import get_pending_scheduled_posts, update_post_status
from .facebook_service import post_to_facebook_page
from .line_service import notify_line_post_published

scheduler = BackgroundScheduler()

def check_and_publish_pending_posts():
    """ตรวจเช็กโพสต์ที่ถึงเวลาและสั่งโพสต์อัตโนมัติ"""
    pending_posts = get_pending_scheduled_posts()
    if not pending_posts:
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(pending_posts)} pending scheduled posts, publishing...")

    for post in pending_posts:
        post_id = post["id"]
        page_id = post.get("facebook_page_id", "")
        token = post.get("facebook_access_token", "")
        image_path = post["image_path"]
        caption = post["caption"]
        first_comment = post.get("first_comment", "")

        result = post_to_facebook_page(
            page_id=page_id,
            access_token=token,
            image_path=image_path,
            caption=caption,
            first_comment=first_comment
        )

        if result.get("success"):
            fb_id = result.get("post_id", "")
            update_post_status(post_id, status="published", fb_post_id=fb_id)
            print(f"[Success] Post #{post_id} published! ({result.get('message')})")
            # ยิงแจ้งเตือนเข้า LINE บอททันที
            try:
                notify_line_post_published(post, fb_id)
            except Exception as notify_err:
                print(f"[LINE Notify Warning] {notify_err}")
        else:
            err = result.get("error", "Failed to publish")
            update_post_status(post_id, status="failed", error_message=err)
            print(f"[Failed] Post #{post_id} failed: {err}")

def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(
            func=check_and_publish_pending_posts,
            trigger=IntervalTrigger(seconds=30),
            id='check_queue_job',
            name='Check and publish scheduled posts every 30s',
            replace_existing=True
        )
        scheduler.start()
        print("[Scheduler] Background auto-post queue checker started (checking every 30s)")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[Scheduler] Background scheduler stopped")
