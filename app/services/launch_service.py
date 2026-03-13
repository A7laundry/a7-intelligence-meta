"""
LaunchService — Campaign Launch Console backend.

Flow: create_job → add_items → validate_job → publish_job (or draft_job)

Modes:
  draft    — store plan only, no Meta API calls
  validate — run validation only, no publish
  publish  — validate then create real Meta entities
"""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime
from typing import Optional

from app.db.init_db import get_connection


# ── Constants ──────────────────────────────────────────────────────────────

VALID_OBJECTIVES = {
    "OUTCOME_LEADS", "OUTCOME_SALES", "OUTCOME_TRAFFIC",
    "OUTCOME_ENGAGEMENT", "OUTCOME_AWARENESS", "OUTCOME_APP_PROMOTION",
}
VALID_CTAS = {
    "LEARN_MORE", "SIGN_UP", "GET_QUOTE", "CONTACT_US",
    "BOOK_TRAVEL", "DOWNLOAD", "SUBSCRIBE",
}
VALID_OPTIMIZATION_GOALS = {
    "LEAD_GENERATION", "LINK_CLICKS", "IMPRESSIONS",
    "REACH", "LANDING_PAGE_VIEWS", "OFFSITE_CONVERSIONS",
}
MAX_BATCH_SIZE = 100
_now = lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


class LaunchService:

    # ── Job management ─────────────────────────────────────────────────────

    @staticmethod
    def create_job(account_id: int, job_name: str, mode: str = "draft",
                   template_id: Optional[int] = None, notes: str = "") -> dict:
        """Create a new launch job and return it."""
        if mode not in ("draft", "validate", "publish"):
            raise ValueError(f"Invalid mode: {mode}")
        conn = get_connection()
        try:
            cur = conn.execute(
                """INSERT INTO launch_jobs
                   (account_id, job_name, mode, status, created_at, template_id, notes,
                    total_items, success_count, failed_count)
                   VALUES (?, ?, ?, 'pending', ?, ?, ?, 0, 0, 0)""",
                (account_id, job_name, mode, _now(), template_id, notes),
            )
            job_id = cur.lastrowid
            conn.commit()
            return LaunchService.get_job(job_id)
        finally:
            conn.close()

    @staticmethod
    def get_job(job_id: int) -> Optional[dict]:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM launch_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def list_jobs(account_id: Optional[int] = None, limit: int = 50) -> list:
        conn = get_connection()
        try:
            if account_id:
                rows = conn.execute(
                    "SELECT * FROM launch_jobs WHERE account_id = ? ORDER BY created_at DESC LIMIT ?",
                    (account_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM launch_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def delete_job(job_id: int) -> bool:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM launch_logs WHERE launch_job_id = ?", (job_id,))
            conn.execute("DELETE FROM launch_items WHERE launch_job_id = ?", (job_id,))
            cur = conn.execute("DELETE FROM launch_jobs WHERE id = ?", (job_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # ── Item management ────────────────────────────────────────────────────

    @staticmethod
    def add_items(job_id: int, items: list, defaults: dict = None) -> list:
        """
        Bulk-add items to a launch job.
        items: list of dicts with at minimum: lp_url
        defaults: dict of default values applied to all items
        """
        defaults = defaults or {}
        conn = get_connection()
        added = []
        try:
            for idx, item in enumerate(items):
                merged = {**defaults, **item}
                cur = conn.execute(
                    """INSERT INTO launch_items
                       (launch_job_id, lp_url, campaign_name, adset_name, ad_name,
                        objective, budget, budget_type, headline, primary_text,
                        description, cta, creative_key, creative_id,
                        geo, age_min, age_max, placements, optimization_goal,
                        pixel_id, page_id, instagram_actor_id,
                        utm_source, utm_campaign,
                        validation_status, publish_status,
                        created_at, row_index)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending','pending',?,?)""",
                    (
                        job_id,
                        merged.get("lp_url", ""),
                        merged.get("campaign_name"),
                        merged.get("adset_name"),
                        merged.get("ad_name"),
                        merged.get("objective", "OUTCOME_LEADS"),
                        merged.get("budget", 0),
                        merged.get("budget_type", "DAILY"),
                        merged.get("headline"),
                        merged.get("primary_text"),
                        merged.get("description"),
                        merged.get("cta", "LEARN_MORE"),
                        merged.get("creative_key"),
                        merged.get("creative_id"),
                        merged.get("geo", "BR"),
                        merged.get("age_min", 18),
                        merged.get("age_max", 65),
                        merged.get("placements", "automatic"),
                        merged.get("optimization_goal", "LEAD_GENERATION"),
                        merged.get("pixel_id"),
                        merged.get("page_id"),
                        merged.get("instagram_actor_id"),
                        merged.get("utm_source"),
                        merged.get("utm_campaign"),
                        _now(),
                        idx,
                    ),
                )
                added.append(cur.lastrowid)
            # update total_items count
            conn.execute(
                "UPDATE launch_jobs SET total_items = (SELECT COUNT(*) FROM launch_items WHERE launch_job_id = ?) WHERE id = ?",
                (job_id, job_id),
            )
            conn.commit()
            return added
        finally:
            conn.close()

    @staticmethod
    def get_items(job_id: int) -> list:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM launch_items WHERE launch_job_id = ? ORDER BY row_index",
                (job_id,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["validation_errors"] = json.loads(d["validation_errors"] or "[]")
                except Exception:
                    d["validation_errors"] = []
                result.append(d)
            return result
        finally:
            conn.close()

    # ── CSV / textarea parse ───────────────────────────────────────────────

    @staticmethod
    def parse_csv_input(raw: str) -> tuple:
        """
        Parse CSV or tab-separated LP import.
        Returns (items, parse_errors).
        Accepted headers (case-insensitive):
          lp_url, headline, primary_text, creative_key, budget,
          utm_source, utm_campaign, cta, ad_name_suffix
        """
        lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
        if not lines:
            return [], ["Input is empty"]

        # Detect header
        first = lines[0].lower()
        delimiter = "\t" if "\t" in first else ","
        has_header = any(k in first for k in ("lp_url", "url", "headline", "budget"))

        if has_header:
            header_line = lines[0]
            data_lines = lines[1:]
        else:
            # Assume first column is lp_url
            header_line = "lp_url,headline,primary_text,budget"
            data_lines = lines

        headers = [h.strip().lower() for h in header_line.split(delimiter)]

        items = []
        errors = []
        for i, line in enumerate(data_lines):
            cols = [c.strip() for c in line.split(delimiter)]
            row = {}
            for j, h in enumerate(headers):
                row[h] = cols[j] if j < len(cols) else ""
            # Normalize url field
            if "url" in row and "lp_url" not in row:
                row["lp_url"] = row.pop("url")
            if not row.get("lp_url"):
                errors.append(f"Row {i+2}: missing lp_url")
                continue
            # Parse budget as float
            if row.get("budget"):
                try:
                    row["budget"] = float(row["budget"])
                except ValueError:
                    errors.append(f"Row {i+2}: invalid budget '{row['budget']}'")
                    row["budget"] = 0
            items.append(row)
        return items, errors

    # ── Naming patterns ────────────────────────────────────────────────────

    @staticmethod
    def apply_naming_patterns(items: list, account_name: str,
                               template: Optional[dict] = None) -> list:
        """Generate campaign/adset/ad names for items that don't have them."""
        camp_pat = (template or {}).get(
            "campaign_name_pattern", "A7-{ACCOUNT}-{OBJECTIVE}-{DATE}-{INDEX}"
        )
        adset_pat = (template or {}).get(
            "adset_name_pattern", "{GEO}-18-65-auto"
        )
        ad_pat = (template or {}).get(
            "ad_name_pattern", "{LPKEY}-{CTA}"
        )
        date_str = datetime.utcnow().strftime("%Y%m%d")
        acc_slug = re.sub(r"[^A-Z0-9]", "", account_name.upper())[:10]

        for i, item in enumerate(items):
            obj_slug = item.get("objective", "LEADS").replace("OUTCOME_", "")[:6]
            lp_key = _lp_slug(item.get("lp_url", ""))
            cta = item.get("cta", "LEARN_MORE")[:3]
            geo = item.get("geo", "BR").upper()

            if not item.get("campaign_name"):
                item["campaign_name"] = (
                    camp_pat
                    .replace("{ACCOUNT}", acc_slug)
                    .replace("{OBJECTIVE}", obj_slug)
                    .replace("{DATE}", date_str)
                    .replace("{INDEX}", str(i + 1).zfill(2))
                )
            if not item.get("adset_name"):
                item["adset_name"] = (
                    adset_pat
                    .replace("{GEO}", geo)
                    .replace("{AUDIENCE}", "broad")
                    .replace("{PLACEMENT}", "auto")
                )
            if not item.get("ad_name"):
                item["ad_name"] = (
                    ad_pat
                    .replace("{LPKEY}", lp_key)
                    .replace("{CREATIVEKEY}", item.get("creative_key", "ck")[:8])
                    .replace("{CTA}", cta)
                )
        return items

    # ── Validation engine ──────────────────────────────────────────────────

    @staticmethod
    def validate_job(job_id: int, assets: Optional[dict] = None) -> dict:
        """
        Run full validation on all items of a job.
        assets: dict with keys: page_ids, pixel_ids, instagram_actor_ids (lists of strings)
        Returns summary dict with per-item results.
        """
        conn = get_connection()
        try:
            job_row = conn.execute(
                "SELECT * FROM launch_jobs WHERE id=?", (job_id,)
            ).fetchone()
            account_id = dict(job_row)["account_id"] if job_row else None

            rows = conn.execute(
                "SELECT * FROM launch_items WHERE launch_job_id = ?",
                (job_id,),
            ).fetchall()

            seen_urls = {}
            summary = {"valid": 0, "warning": 0, "error": 0, "blocked": 0}

            for row in rows:
                item = dict(row)
                errors, warnings = [], []

                # A. URL validation
                url = item.get("lp_url", "")
                if not url:
                    errors.append("Missing LP URL")
                elif not _is_valid_url(url):
                    errors.append(f"Invalid URL: {url}")
                else:
                    if url in seen_urls:
                        errors.append(f"Duplicate URL (also in row {seen_urls[url]})")
                    else:
                        seen_urls[url] = item["row_index"]

                # B. Budget
                budget = item.get("budget") or 0
                if budget <= 0:
                    errors.append("Budget must be > 0")
                elif budget < 1:
                    warnings.append("Budget is very low (< R$1)")

                # C. Objective
                if item.get("objective") not in VALID_OBJECTIVES:
                    errors.append(f"Invalid objective: {item.get('objective')}")

                # D. CTA
                if item.get("cta") and item.get("cta") not in VALID_CTAS:
                    warnings.append(f"Unknown CTA: {item.get('cta')}")

                # E. Ad content
                if not item.get("headline"):
                    warnings.append("Missing headline — will use default from creative")
                if not item.get("primary_text"):
                    warnings.append("Missing primary_text — will use default from creative")

                # F. Creative validation
                creative_key = item.get("creative_key")
                if not creative_key and not item.get("creative_id"):
                    warnings.append("No creative_key — assign before live publish")
                elif creative_key and account_id:
                    from app.services.creative_service_launch import CreativeLaunchService
                    result = CreativeLaunchService.validate_creative_key(account_id, creative_key)
                    if not result["valid"]:
                        warnings.append(f"Creative: {result['error']}")

                # G. Page / pixel (if assets provided)
                if assets:
                    page_id = item.get("page_id")
                    if page_id and assets.get("page_ids") and page_id not in assets["page_ids"]:
                        errors.append(f"Page {page_id} not accessible for this account")
                    pixel_id = item.get("pixel_id")
                    if pixel_id and assets.get("pixel_ids") and pixel_id not in assets["pixel_ids"]:
                        warnings.append(f"Pixel {pixel_id} not found — conversion tracking may fail")

                # H. Names
                for field, label in [("campaign_name", "campaign"), ("adset_name", "adset"), ("ad_name", "ad")]:
                    if not item.get(field):
                        warnings.append(f"No {label} name — will auto-generate")

                # Determine status
                if errors:
                    status = "blocked" if any(
                        "duplicate" in e.lower() or "invalid url" in e.lower() or "budget" in e.lower()
                        for e in errors
                    ) else "error"
                elif warnings:
                    status = "warning"
                else:
                    status = "valid"

                all_msgs = errors + warnings
                conn.execute(
                    "UPDATE launch_items SET validation_status=?, validation_errors=? WHERE id=?",
                    (status, json.dumps(all_msgs), item["id"]),
                )
                summary[status] = summary.get(status, 0) + 1

            # Update job status
            conn.execute(
                "UPDATE launch_jobs SET status='validated' WHERE id=?", (job_id,)
            )
            # Log validation event
            _log(conn, job_id, None, "validate", "info",
                 f"Validation complete: {summary}")
            conn.commit()
            return summary
        finally:
            conn.close()

    # ── Publish engine ─────────────────────────────────────────────────────

    @classmethod
    def publish_job(cls, job_id: int, dry_run: bool = True) -> dict:
        """
        Execute launch job.
        dry_run=True  → store plan only, no Meta API
        dry_run=False → create real Meta entities
        Returns execution summary.
        """
        conn = get_connection()
        try:
            job = conn.execute(
                "SELECT * FROM launch_jobs WHERE id=?", (job_id,)
            ).fetchone()
            if not job:
                raise ValueError(f"Job {job_id} not found")

            # Only publish valid/warning items; skip blocked/error
            items = conn.execute(
                """SELECT * FROM launch_items
                   WHERE launch_job_id=?
                   AND validation_status IN ('valid','warning')
                   AND publish_status='pending'
                   ORDER BY row_index""",
                (job_id,),
            ).fetchall()

            if not items:
                return {"error": "No publishable items (all are blocked/errored or already published)"}

            conn.execute(
                "UPDATE launch_jobs SET status='publishing' WHERE id=?", (job_id,)
            )
            conn.commit()

            # Load account for Meta client
            account = conn.execute(
                "SELECT * FROM ad_accounts WHERE id=?", (job["account_id"],)
            ).fetchone()
            if not account:
                raise ValueError("Account not found")

            success, failed = 0, 0

            for item in items:
                item = dict(item)
                try:
                    if dry_run:
                        # Simulate only — store draft payload
                        draft = cls._build_meta_payload(item, dict(account))
                        conn.execute(
                            "UPDATE launch_items SET publish_status='success', published_at=? WHERE id=?",
                            (_now(), item["id"]),
                        )
                        _log(conn, job_id, item["id"], "create_campaign",
                             "info",
                             "DRY RUN — payload generated (no Meta API call)",
                             request_payload=json.dumps(draft))
                        success += 1
                    else:
                        # LIVE PUBLISH
                        cls._publish_item(conn, job_id, item, dict(account))
                        success += 1
                except Exception as e:
                    failed += 1
                    conn.execute(
                        "UPDATE launch_items SET publish_status='failed', error_message=? WHERE id=?",
                        (str(e), item["id"]),
                    )
                    _log(conn, job_id, item["id"], "error", "error",
                         f"Item failed: {e}")

            final_status = "completed" if failed == 0 else ("failed" if success == 0 else "partial")
            conn.execute(
                "UPDATE launch_jobs SET status=?, success_count=?, failed_count=?, published_at=? WHERE id=?",
                (final_status, success, failed, _now(), job_id),
            )
            conn.commit()
            return {"status": final_status, "success": success, "failed": failed,
                    "dry_run": dry_run}
        finally:
            conn.close()

    @staticmethod
    def _build_meta_payload(item: dict, account: dict) -> dict:
        """Build the full Meta API payload for preview/dry-run."""
        lp_url = item["lp_url"]
        utm = ""
        if item.get("utm_source") or item.get("utm_campaign"):
            utm = f"?utm_source={item.get('utm_source','a7')}&utm_campaign={item.get('utm_campaign','launch')}"

        # Resolve image_hash from creative library if creative_key is set
        image_hash = None
        creative_key = item.get("creative_key")
        if creative_key:
            from app.services.creative_service_launch import CreativeLaunchService
            image_hash = CreativeLaunchService.resolve_image_hash(
                account.get("id", 0), creative_key
            )

        return {
            "campaign": {
                "name": item.get("campaign_name", ""),
                "objective": item.get("objective", "OUTCOME_LEADS"),
                "status": "PAUSED",
                "special_ad_categories": [],
            },
            "adset": {
                "name": item.get("adset_name", ""),
                "optimization_goal": item.get("optimization_goal", "LEAD_GENERATION"),
                "billing_event": "IMPRESSIONS",
                "daily_budget": int((item.get("budget") or 50) * 100),  # in cents
                "targeting": {
                    "geo_locations": {"countries": [item.get("geo", "BR")]},
                    "age_min": item.get("age_min", 18),
                    "age_max": item.get("age_max", 65),
                },
                "status": "PAUSED",
            },
            "ad": {
                "name": item.get("ad_name", ""),
                "creative": {
                    "page_id": item.get("page_id") or account.get("page_id"),
                    "instagram_actor_id": item.get("instagram_actor_id") or account.get("instagram_actor_id"),
                    "link": lp_url + utm,
                    "headline": item.get("headline", ""),
                    "body": item.get("primary_text", ""),
                    "call_to_action": {"type": item.get("cta", "LEARN_MORE")},
                    "image_hash": image_hash,  # None in dry-run if not uploaded; real hash in live
                },
                "status": "PAUSED",
            },
        }

    @classmethod
    def _publish_item(cls, conn, job_id: int, item: dict, account: dict):
        """Live publish: create campaign → adset → ad on Meta. Raises on failure."""
        from meta_client import MetaAdsClient

        client = MetaAdsClient(
            account_id=account["external_account_id"],
            access_token=account["access_token"],
        )

        item_id = item["id"]
        payload = cls._build_meta_payload(item, account)

        # Step 1: Create Campaign
        _log(conn, job_id, item_id, "create_campaign", "info",
             "Creating campaign...", request_payload=json.dumps(payload["campaign"]))
        camp = client.create_campaign_direct(
            name=payload["campaign"]["name"],
            objective=payload["campaign"]["objective"],
        )
        meta_campaign_id = camp.get("id") or camp.get("campaign_id")
        if not meta_campaign_id:
            raise RuntimeError(f"Campaign creation returned no ID: {camp}")
        conn.execute(
            "UPDATE launch_items SET meta_campaign_id=? WHERE id=?",
            (meta_campaign_id, item_id),
        )
        _log(conn, job_id, item_id, "create_campaign", "success",
             f"Campaign created: {meta_campaign_id}",
             response_payload=json.dumps(camp))
        conn.commit()

        # Step 2: Create Ad Set
        _log(conn, job_id, item_id, "create_adset", "info",
             "Creating ad set...")
        adset = client.create_ad_set_direct(
            campaign_id=meta_campaign_id,
            name=payload["adset"]["name"],
            daily_budget=payload["adset"]["daily_budget"],
            optimization_goal=item.get("optimization_goal", "LEAD_GENERATION"),
            targeting=payload["adset"]["targeting"],
            pixel_id=item.get("pixel_id") or account.get("pixel_id"),
        )
        meta_adset_id = adset.get("id") or adset.get("adset_id")
        if not meta_adset_id:
            raise RuntimeError(f"Ad set creation returned no ID: {adset}")
        conn.execute(
            "UPDATE launch_items SET meta_adset_id=? WHERE id=?",
            (meta_adset_id, item_id),
        )
        _log(conn, job_id, item_id, "create_adset", "success",
             f"Ad set created: {meta_adset_id}")
        conn.commit()

        # Step 3: Create Ad
        _log(conn, job_id, item_id, "create_ad", "info", "Creating ad...")
        ad_creative = payload["ad"]["creative"]
        image_hash = ad_creative.get("image_hash")
        creative_key = item.get("creative_key")
        if creative_key and not image_hash:
            raise RuntimeError(
                f"Creative '{creative_key}' has no valid Meta image_hash — upload first"
            )
        ad = client.create_ad_direct(
            ad_set_id=meta_adset_id,
            name=payload["ad"]["name"],
            page_id=ad_creative["page_id"],
            link=ad_creative["link"],
            headline=ad_creative["headline"],
            body=ad_creative["body"],
            call_to_action_type=item.get("cta", "LEARN_MORE"),
            instagram_actor_id=ad_creative.get("instagram_actor_id"),
            image_hash=image_hash,
        )
        meta_ad_id = ad.get("id") or ad.get("ad_id")
        if not meta_ad_id:
            raise RuntimeError(f"Ad creation returned no ID: {ad}")
        conn.execute(
            "UPDATE launch_items SET meta_ad_id=?, publish_status='success', published_at=? WHERE id=?",
            (meta_ad_id, _now(), item_id),
        )
        _log(conn, job_id, item_id, "create_ad", "success",
             f"Ad created: {meta_ad_id}")
        conn.commit()

    # ── Templates ──────────────────────────────────────────────────────────

    @staticmethod
    def create_template(account_id: int, data: dict) -> dict:
        conn = get_connection()
        try:
            cur = conn.execute(
                """INSERT INTO launch_templates
                   (account_id, template_name, objective, budget_type, default_budget,
                    geo, age_min, age_max, placements, optimization_goal, billing_event,
                    cta, campaign_name_pattern, adset_name_pattern, ad_name_pattern,
                    special_ad_category, attribution_setting, notes, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    account_id,
                    data.get("template_name", "Default"),
                    data.get("objective", "OUTCOME_LEADS"),
                    data.get("budget_type", "DAILY"),
                    data.get("default_budget", 50.0),
                    data.get("geo", "BR"),
                    data.get("age_min", 18),
                    data.get("age_max", 65),
                    data.get("placements", "automatic"),
                    data.get("optimization_goal", "LEAD_GENERATION"),
                    data.get("billing_event", "IMPRESSIONS"),
                    data.get("cta", "LEARN_MORE"),
                    data.get("campaign_name_pattern", "A7-{ACCOUNT}-{OBJECTIVE}-{DATE}-{INDEX}"),
                    data.get("adset_name_pattern", "{GEO}-18-65-auto"),
                    data.get("ad_name_pattern", "{LPKEY}-{CTA}"),
                    data.get("special_ad_category", "NONE"),
                    data.get("attribution_setting", "7d_click"),
                    data.get("notes", ""),
                    _now(),
                ),
            )
            template_id = cur.lastrowid
            conn.commit()
            row = conn.execute("SELECT * FROM launch_templates WHERE id=?", (template_id,)).fetchone()
            return dict(row)
        finally:
            conn.close()

    @staticmethod
    def list_templates(account_id: int) -> list:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM launch_templates WHERE account_id=? ORDER BY created_at DESC",
                (account_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Assets discovery ───────────────────────────────────────────────────

    @staticmethod
    def discover_assets(account_id: int) -> dict:
        """
        Fetch account assets from Meta API (pages, pixels, IG actors).
        Falls back to stored data if Meta API call fails.
        """
        from app.services.account_service import AccountService
        account = AccountService.get_by_id(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        result = {
            "account_id": account_id,
            "account_name": account.get("account_name", ""),
            "external_account_id": account.get("external_account_id", ""),
            "currency": account.get("currency", "BRL"),
            "timezone": account.get("timezone", "America/Sao_Paulo"),
            "pages": [],
            "pixels": [],
            "instagram_actors": [],
            "errors": [],
        }

        try:
            from meta_client import MetaAdsClient
            client = MetaAdsClient(
                account_id=account["external_account_id"],
                access_token=account["access_token"],
            )
            try:
                result["pages"] = client.get_pages()
            except Exception as e:
                result["errors"].append(f"Pages: {e}")
            try:
                result["pixels"] = client.get_pixels()
            except Exception as e:
                result["errors"].append(f"Pixels: {e}")
            try:
                result["instagram_actors"] = client.get_instagram_actors()
            except Exception as e:
                result["errors"].append(f"Instagram actors: {e}")
            try:
                info = client.get_account_info()
                result["currency"] = info.get("currency", result["currency"])
                result["timezone"] = info.get("timezone_name", result["timezone"])
                # Cache on account
                conn = get_connection()
                try:
                    conn.execute(
                        "UPDATE ad_accounts SET currency=?, timezone=? WHERE id=?",
                        (result["currency"], result["timezone"], account_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
            except Exception as e:
                result["errors"].append(f"Account info: {e}")
        except Exception as e:
            result["errors"].append(f"Meta client init failed: {e}")

        # Supplement with stored values
        result["stored_page_id"] = account.get("page_id")
        result["stored_pixel_id"] = account.get("pixel_id")
        result["stored_instagram_actor_id"] = account.get("instagram_actor_id")

        return result

    # ── Logs ───────────────────────────────────────────────────────────────

    @staticmethod
    def get_logs(job_id: int) -> list:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM launch_logs WHERE launch_job_id=? ORDER BY id",
                (job_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── Helpers ────────────────────────────────────────────────────────────────

def _lp_slug(url: str) -> str:
    """Extract a short slug from a URL for naming."""
    try:
        path = urllib.parse.urlparse(url).path.strip("/")
        parts = [p for p in path.split("/") if p]
        slug = parts[-1] if parts else "lp"
        return re.sub(r"[^a-zA-Z0-9]", "", slug)[:12].upper() or "LP"
    except Exception:
        return "LP"


def _is_valid_url(url: str) -> bool:
    try:
        p = urllib.parse.urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def _log(conn, job_id: int, item_id: Optional[int], step: str,
         status: str, message: str,
         request_payload: str = None, response_payload: str = None):
    conn.execute(
        """INSERT INTO launch_logs
           (launch_job_id, launch_item_id, step, status, message,
            request_payload, response_payload, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (job_id, item_id, step, status, message,
         request_payload, response_payload, _now()),
    )
