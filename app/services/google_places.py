import os
import requests
from typing import Optional


GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")


def get_place_review_summary(place_id: str, timeout_seconds: int = 5) -> Optional[str]:
    """
    指定の Place ID について、レビュー要約テキストを取得する。
    優先順位は editorialSummary → reviewSummary（→ reviewsSummary の保険）。
    可能なら日本語で取得。
    """
    if not GOOGLE_MAPS_API_KEY or not place_id:
        return None

    base_url = f"https://places.googleapis.com/v1/places/{place_id}"

    # editorialSummary を最優先で取得し、無ければ reviewSummary → reviewsSummary の順
    for field_name in ("editorialSummary", "reviewSummary", "reviewsSummary"):
        try:
            resp = requests.get(
                base_url,
                params={
                    "fields": field_name,
                    "languageCode": "ja",
                    "key": GOOGLE_MAPS_API_KEY,
                },
                timeout=timeout_seconds,
            )
            if resp.status_code != 200:
                continue
            data = resp.json() if resp.content else {}
            summary = data.get(field_name)
            if not summary:
                continue

            # 共通のレスポンス形状に対応
            if isinstance(summary, dict):
                # 直接 text を持つケース
                if isinstance(summary.get("text"), str) and summary.get("text").strip():
                    return summary.get("text").strip()
                # reviewSummary の一部で { overview: { text: "..." } } の形
                overview = summary.get("overview") if isinstance(summary.get("overview"), dict) else None
                if overview and isinstance(overview.get("text"), str) and overview.get("text").strip():
                    return overview.get("text").strip()
            # If API returns a simple string (unlikely)
            if isinstance(summary, str) and summary.strip():
                return summary.strip()
        except Exception:
            # Fail quietly; caller will handle None
            continue

    return None



def get_place_name(place_id: str, language_code: str = "en", timeout_seconds: int = 5) -> Optional[str]:
    """指定の Place ID の表示名（指定言語）を返す。"""
    if not GOOGLE_MAPS_API_KEY or not place_id:
        return None
    try:
        base_url = f"https://places.googleapis.com/v1/places/{place_id}"
        resp = requests.get(
            base_url,
            params={
                "fields": "displayName",
                "languageCode": language_code,
                "key": GOOGLE_MAPS_API_KEY,
            },
            timeout=timeout_seconds,
        )
        if resp.status_code != 200:
            return None
        data = resp.json() if resp.content else {}
        dn = data.get("displayName")
        if isinstance(dn, dict):
            txt = dn.get("text")
            if isinstance(txt, str) and txt.strip():
                return txt.strip()
        return None
    except Exception:
        return None


