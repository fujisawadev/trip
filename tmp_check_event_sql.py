from run import app
from app import db
from sqlalchemy import text

PAGE_ID = 167
with app.app_context():
    conn = db.engine.connect()
    total = conn.execute(text("select count(*) from event_log where page_id=:pid"), {"pid": PAGE_ID}).scalar()
    views = conn.execute(text("select count(*) from event_log where page_id=:pid and event_type=:t"), {"pid": PAGE_ID, "t":"view"}).scalar()
    clicks = conn.execute(text("select count(*) from event_log where page_id=:pid and event_type=:t"), {"pid": PAGE_ID, "t":"click"}).scalar()
    print("total=", total, "views=", views, "clicks=", clicks)
    rows = conn.execute(text("""
        select id, to_char(created_at at time zone Asia/Tokyo,YYYY-MM-DD
