import os
import sys
import time
import argparse
import logging
from typing import Iterable, List, Optional, Tuple

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app, db
from app.models import Spot
from app.models.spot_provider_id import SpotProviderId
from app.services.dataforseo import search_hotels as dfs_search_hotels
from app.services.rakuten_travel import fetch_detail_by_hotel_no as rakuten_fetch_detail
from app.services.rakuten_travel import simple_hotel_search_by_geo as rakuten_simple_geo
from app.utils.rakuten_api import search_hotel as rakuten_search


logger = logging.getLogger(__name__)


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s [%(levelname)s] %(message)s')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill spot_provider_ids for existing spots (dataforseo / rakuten)",
    )
    parser.add_argument("--providers", default="dataforseo,rakuten", help="Comma-separated providers: dataforseo,rakuten")
    parser.add_argument("--user-id", type=int, default=None, help="Filter by user_id")
    parser.add_argument("--spot-ids", type=str, default=None, help="Comma-separated spot ids to process (overrides limit/offset)")
    parser.add_argument("--only-missing", action="store_true", help="Process only spots missing mapping for provider(s)")
    parser.add_argument("--limit", type=int, default=None, help="Max spots to process")
    parser.add_argument("--offset", type=int, default=0, help="Offset for spot query")
    parser.add_argument("--radius-m", type=float, default=100.0, help="Max distance in meters for matching")
    parser.add_argument("--sleep", type=float, default=0.2, help="Sleep seconds between spots (rate limiting)")
    parser.add_argument("--allow-no-geo", action="store_true", help="Allow mapping without distance check when no coordinates available")
    parser.add_argument("--dry-run", action="store_true", help="Do not commit any DB changes")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    return parser.parse_args()


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians((lat2 - lat1))
    dlambda = math.radians((lon2 - lon1))
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def is_lodging_category(category: Optional[str], types_value: Optional[str]) -> bool:
    if category:
        cl = category.lower()
        if any(k in cl for k in ['hotel', 'hostel', 'inn', 'lodging']) or any(k in category for k in ['旅館', 'ホテル']):
            return True
    if types_value:
        try:
            import json
            tlist: List[str] = json.loads(types_value)
        except Exception:
            tlist = [s.strip() for s in types_value.split(',') if s.strip()]
        for t in tlist:
            tl = str(t).lower()
            if any(k in tl for k in ['hotel', 'hostel', 'inn', 'lodging']) or any(k in str(t) for k in ['旅館', 'ホテル']):
                return True
    return False


def select_dfs_item(items: List[dict], spot: Spot) -> Tuple[Optional[dict], Optional[float]]:
    chosen = None
    best_dist_m = None
    if not items:
        return None, None
    if spot.latitude is None or spot.longitude is None:
        return None, None
    for it in items:
        loc = (it.get('location') or {})
        lat = loc.get('latitude')
        lng = loc.get('longitude')
        if lat is None or lng is None:
            continue
        try:
            d_m = haversine_m(float(spot.latitude), float(spot.longitude), float(lat), float(lng))
        except Exception:
            continue
        if best_dist_m is None or d_m < best_dist_m:
            best_dist_m = d_m
            chosen = it
    return chosen, best_dist_m


def backfill_dataforseo(spot: Spot, radius_m: float, allow_no_geo: bool) -> Optional[SpotProviderId]:
    # 前提チェック: 資格情報が無ければスキップ
    if not (os.environ.get('DATAFORSEO_LOGIN') and os.environ.get('DATAFORSEO_PASSWORD')):
        logger.debug("DataForSEO credentials not set; skipping")
        return None

    if not is_lodging_category(spot.category, getattr(spot, 'types', None)):
        return None

    keyword = spot.name
    location_name = os.environ.get('DATAFORSEO_DEFAULT_LOCATION', 'Japan')
    language_code = os.environ.get('DATAFORSEO_DEFAULT_LANGUAGE', 'ja')
    items = dfs_search_hotels(
        keyword=keyword,
        location_name=location_name,
        language_code=language_code,
        currency=os.environ.get('AGODA_CURRENCY', 'JPY'),
        adults=2,
    )
    if not items:
        return None

    chosen, best_dist_m = select_dfs_item(items, spot)
    if chosen and chosen.get('hotel_identifier'):
        if best_dist_m is None and not allow_no_geo:
            return None
        if best_dist_m is not None and best_dist_m > radius_m:
            return None
        exists = SpotProviderId.query.filter_by(spot_id=spot.id, provider='dataforseo').first()
        if not exists:
            mapping = SpotProviderId(
                spot_id=spot.id,
                provider='dataforseo',
                external_id=chosen['hotel_identifier']
            )
            db.session.add(mapping)
            return mapping
    return None


def select_rakuten_basic(spot: Spot) -> Tuple[Optional[dict], Optional[float]]:
    hotels = []
    if spot.latitude and spot.longitude:
        geo_res = rakuten_simple_geo(spot.name, float(spot.latitude), float(spot.longitude), hits=5)
        if geo_res and isinstance(geo_res, dict):
            hotels = geo_res.get('hotels') or []
            hotels = [{'hotel': [h[0]]} for h in hotels if isinstance(h, list) and h]
    if not hotels:
        res = rakuten_search(spot.name, affiliate_id=os.environ.get('RAKUTEN_AFFILIATE_ID'), hits=3)
        hotels = res.get('hotels') if isinstance(res, dict) else []

    best = None
    best_d = None
    for h in hotels:
        try:
            basic = h['hotel'][0]['hotelBasicInfo'] if 'hotel' in h and h['hotel'] else {}
            hlat = basic.get('latitude')
            hlng = basic.get('longitude')
            if (hlat is None or hlng is None) and basic.get('hotelNo'):
                detail = rakuten_fetch_detail(str(basic.get('hotelNo')))
                if detail and isinstance(detail, dict):
                    dhs = detail.get('hotels') or []
                    if dhs and isinstance(dhs[0], dict) and dhs[0].get('hotel'):
                        dinfo = dhs[0]['hotel'][0].get('hotelBasicInfo', {})
                        hlat = dinfo.get('latitude') or hlat
                        hlng = dinfo.get('longitude') or hlng
            if hlat is None or hlng is None or not spot.latitude or not spot.longitude:
                continue
            d = haversine_m(float(spot.latitude), float(spot.longitude), float(hlat), float(hlng))
            if best_d is None or d < best_d:
                best_d = d
                best = basic
        except Exception:
            continue
    return best, best_d


def backfill_rakuten(spot: Spot, radius_m: float, allow_no_geo: bool) -> Optional[SpotProviderId]:
    if not os.environ.get('RAKUTEN_API_KEY'):
        logger.debug("Rakuten API key not set; skipping")
        return None

    if not is_lodging_category(spot.category, getattr(spot, 'types', None)):
        return None

    best, best_d = select_rakuten_basic(spot)
    if best and best.get('hotelNo'):
        if best_d is None and not allow_no_geo:
            return None
        if best_d is not None and best_d > radius_m:
            return None
        exists = SpotProviderId.query.filter_by(spot_id=spot.id, provider='rakuten').first()
        if not exists:
            mapping = SpotProviderId(spot_id=spot.id, provider='rakuten', external_id=str(best['hotelNo']))
            db.session.add(mapping)
            return mapping
    return None


def query_spots(user_id: Optional[int], spot_ids: Optional[List[int]], only_missing: bool, providers: List[str], limit: Optional[int], offset: int) -> Iterable[Spot]:
    q = Spot.query
    if user_id is not None:
        q = q.filter(Spot.user_id == user_id)
    if spot_ids:
        q = q.filter(Spot.id.in_(spot_ids))
    if only_missing:
        # いずれかのプロバイダが未設定のものを対象にする
        from sqlalchemy import or_, and_
        missing_clauses = []
        for p in providers:
            subq = SpotProviderId.query.filter(SpotProviderId.spot_id == Spot.id, SpotProviderId.provider == p).exists()
            missing_clauses.append(~subq)
        if missing_clauses:
            q = q.filter(or_(*missing_clauses))
    q = q.order_by(Spot.id.asc())
    if limit is not None and not spot_ids:
        q = q.offset(offset).limit(limit)
    return q.all()


def main():
    args = parse_args()
    configure_logging(args.verbose)

    providers = [p.strip().lower() for p in (args.providers or '').split(',') if p.strip()]
    allowed = {'dataforseo', 'rakuten'}
    providers = [p for p in providers if p in allowed]
    if not providers:
        logger.error("No valid providers specified. Use --providers=dataforseo,rakuten")
        sys.exit(2)

    spot_ids = None
    if args.spot_ids:
        try:
            spot_ids = [int(s) for s in args.spot_ids.split(',') if s.strip()]
        except Exception:
            logger.error("Invalid --spot-ids. Use comma separated integers.")
            sys.exit(2)

    app = create_app()
    with app.app_context():
        spots = query_spots(args.user_id, spot_ids, args.only_missing, providers, args.limit, args.offset)
        logger.info(f"Found {len(spots)} spots to process")

        created = 0
        skipped = 0
        errors = 0

        for i, spot in enumerate(spots, start=1):
            try:
                logger.info(f"[{i}/{len(spots)}] Spot {spot.id}: {spot.name}")
                before = db.session.new.copy()
                made_any = False

                if 'dataforseo' in providers:
                    m = backfill_dataforseo(spot, radius_m=args.radius_m, allow_no_geo=args.allow_no_geo)
                    if m:
                        logger.info(f"  + dataforseo: {m.external_id}")
                        made_any = True

                if 'rakuten' in providers:
                    m = backfill_rakuten(spot, radius_m=args.radius_m, allow_no_geo=args.allow_no_geo)
                    if m:
                        logger.info(f"  + rakuten: {m.external_id}")
                        made_any = True

                if made_any and not args.dry_run:
                    db.session.commit()
                    created += 1
                else:
                    if made_any:
                        db.session.rollback()  # dry-run の場合はロールバック
                    skipped += 1 if not made_any else 0
            except Exception as e:
                errors += 1
                db.session.rollback()
                logger.warning(f"  ! error: {e}")
            finally:
                if args.sleep and i < len(spots):
                    time.sleep(args.sleep)

        logger.info(f"Done. created={created}, skipped={skipped}, errors={errors}")


if __name__ == "__main__":
    main()


