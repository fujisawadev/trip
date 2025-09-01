from dotenv import load_dotenv
load_dotenv()
import os
from sqlalchemy import create_engine, text

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise SystemExit("DATABASE_URL not set")
if db_url.startswith("postgres:"):
    db_url = db_url.replace("postgres:", "postgresql:", 1)
engine = create_engine(db_url, pool_pre_ping=True)

PAGE_ID = 167
with engine.connect() as conn:
    total = conn.execute(text("select count(*) from event_log where page_id=:pid"), {"pid": PAGE_ID}).scalar()
    views = conn.execute(text("select count(*) from event_log where page_id=:pid and event_type=view"), {"pid": PAGE_ID}).scalar()
    clicks = conn.execute(text("select count(*) from event_log where page_id=:pid and event_type=click"), {"pid": PAGE_ID}).scalar()
    print("total=", total, "views=", views, "clicks=", clicks)
    rows = conn.execute(text("""
        select id, created_at, user_id, page_id, event_type, coalesce(ota,),
               left(coalesce(session_id,),8) as sid,
               left(coalesce(client_key,),8) as ckey,
               dwell_ms, is_bot
        from event_log
        where page_id=:pid
        order by created_at desc
        limit 20
    """), {"pid": PAGE_ID}).fetchall()
    for r in rows:
        print("\t".join([(str(x) if x is not None else "") for x in r]))
