"""Creative Intelligence Service — Tracks ad creative performance, scoring, and fatigue."""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.init_db import get_connection


class CreativeService:
    """Manages creative tracking, scoring, and fatigue detection."""

    def __init__(self):
        self.meta_client = None
        self.meta_available = False
        self._init_client()

    def _init_client(self):
        try:
            from config_default import META_CONFIG
            if META_CONFIG.get("access_token") and META_CONFIG["access_token"] != "SEU_ACCESS_TOKEN_LONGO_PRAZO":
                from meta_client import MetaAdsClient
                self.meta_client = MetaAdsClient()
                self.meta_available = True
        except Exception:
            pass

    def collect_creatives(self):
        """Fetch all ads from Meta and store creative data + metrics."""
        if not self.meta_available:
            return {"collected": 0, "error": "Meta client not available"}

        import requests
        today = datetime.utcnow().strftime("%Y-%m-%d")
        collected = 0

        try:
            # Get all active campaigns
            campaigns = self.meta_client.list_campaigns()

            for campaign in campaigns:
                campaign_id = campaign["id"]
                campaign_name = campaign.get("name", "")

                # Get ad sets for this campaign
                try:
                    ad_sets = self.meta_client.list_ad_sets(campaign_id)
                except Exception:
                    ad_sets = []

                for adset in ad_sets:
                    adset_id = adset["id"]
                    adset_name = adset.get("name", "")

                    # Get ads for this ad set with creative details and insights
                    try:
                        url = f"https://graph.facebook.com/v21.0/{adset_id}/ads"
                        params = {
                            "fields": "id,name,status,creative{id,title,body,thumbnail_url,call_to_action_type,effective_object_story_id}",
                        }
                        headers = {"Authorization": f"Bearer {self.meta_client.access_token}"}
                        resp = requests.get(url, params=params, headers=headers, timeout=30)
                        resp.raise_for_status()
                        ads_data = resp.json().get("data", [])
                    except Exception:
                        ads_data = []

                    for ad in ads_data:
                        ad_id = ad["id"]
                        ad_name = ad.get("name", "")
                        ad_status = ad.get("status", "UNKNOWN")
                        creative = ad.get("creative", {})

                        # Upsert creative record
                        creative_id = self._upsert_creative(
                            ad_id=ad_id,
                            creative_name=ad_name,
                            campaign_id=campaign_id,
                            campaign_name=campaign_name,
                            adset_id=adset_id,
                            adset_name=adset_name,
                            thumbnail_url=creative.get("thumbnail_url", ""),
                            body_text=creative.get("body", ""),
                            headline=creative.get("title", ""),
                            call_to_action=creative.get("call_to_action_type", ""),
                            status=ad_status,
                        )

                        # Get ad-level insights
                        try:
                            url = f"https://graph.facebook.com/v21.0/{ad_id}/insights"
                            params = {
                                "fields": "spend,impressions,clicks,ctr,actions,reach,frequency",
                                "date_preset": "last_7d",
                                "time_increment": 1,
                            }
                            resp = requests.get(url, params=params, headers=headers, timeout=30)
                            resp.raise_for_status()
                            insights_data = resp.json().get("data", [])

                            for day_data in insights_data:
                                metric_date = day_data.get("date_start", today)
                                conversions = 0
                                for action in day_data.get("actions", []):
                                    if action.get("action_type") in ("onsite_conversion.messaging_first_reply", "lead"):
                                        conversions += int(action.get("value", 0))

                                spend = float(day_data.get("spend", 0))
                                self._upsert_metric(
                                    metric_date=metric_date,
                                    creative_id=creative_id,
                                    spend=spend,
                                    impressions=int(day_data.get("impressions", 0)),
                                    clicks=int(day_data.get("clicks", 0)),
                                    ctr=float(day_data.get("ctr", 0)),
                                    conversions=conversions,
                                    cpa=round(spend / conversions, 2) if conversions > 0 else 0,
                                    reach=int(day_data.get("reach", 0)),
                                    frequency=float(day_data.get("frequency", 0)),
                                )
                        except Exception:
                            pass

                        collected += 1

            return {"collected": collected, "date": today}
        except Exception as e:
            return {"collected": collected, "error": str(e)}

    def _upsert_creative(self, **kwargs):
        """Insert or update a creative record, return its ID."""
        conn = get_connection()
        try:
            # Try to find existing
            row = conn.execute(
                "SELECT id FROM creatives WHERE platform = 'meta' AND ad_id = ?",
                (kwargs["ad_id"],),
            ).fetchone()

            if row:
                creative_id = row[0]
                conn.execute(
                    """UPDATE creatives SET
                        creative_name=?, campaign_id=?, campaign_name=?,
                        adset_id=?, adset_name=?, thumbnail_url=?,
                        body_text=?, headline=?, call_to_action=?,
                        status=?, last_seen_at=datetime('now'), updated_at=datetime('now')
                    WHERE id=?""",
                    (kwargs.get("creative_name"), kwargs.get("campaign_id"),
                     kwargs.get("campaign_name"), kwargs.get("adset_id"),
                     kwargs.get("adset_name"), kwargs.get("thumbnail_url"),
                     kwargs.get("body_text"), kwargs.get("headline"),
                     kwargs.get("call_to_action"), kwargs.get("status"),
                     creative_id),
                )
            else:
                cursor = conn.execute(
                    """INSERT INTO creatives
                        (platform, ad_id, creative_name, campaign_id, campaign_name,
                         adset_id, adset_name, thumbnail_url, body_text, headline,
                         call_to_action, status, last_seen_at)
                    VALUES ('meta', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (kwargs["ad_id"], kwargs.get("creative_name"),
                     kwargs.get("campaign_id"), kwargs.get("campaign_name"),
                     kwargs.get("adset_id"), kwargs.get("adset_name"),
                     kwargs.get("thumbnail_url"), kwargs.get("body_text"),
                     kwargs.get("headline"), kwargs.get("call_to_action"),
                     kwargs.get("status")),
                )
                creative_id = cursor.lastrowid

            conn.commit()
            return creative_id
        finally:
            conn.close()

    def _upsert_metric(self, **kwargs):
        """Insert or update a daily metric for a creative."""
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO creative_daily_metrics
                    (metric_date, creative_id, platform, spend, impressions, clicks, ctr,
                     conversions, cpa, reach, frequency)
                VALUES (?, ?, 'meta', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(metric_date, creative_id) DO UPDATE SET
                    spend=excluded.spend, impressions=excluded.impressions,
                    clicks=excluded.clicks, ctr=excluded.ctr,
                    conversions=excluded.conversions, cpa=excluded.cpa,
                    reach=excluded.reach, frequency=excluded.frequency""",
                (kwargs["metric_date"], kwargs["creative_id"],
                 kwargs.get("spend", 0), kwargs.get("impressions", 0),
                 kwargs.get("clicks", 0), kwargs.get("ctr", 0),
                 kwargs.get("conversions", 0), kwargs.get("cpa", 0),
                 kwargs.get("reach", 0), kwargs.get("frequency", 0)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_creatives(self, days=7, status=None, campaign_id=None, fatigue_only=False):
        """Get creatives with aggregated metrics and scores."""
        conn = get_connection()
        try:
            since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

            query = """
                SELECT c.id, c.ad_id, c.creative_name, c.campaign_id, c.campaign_name,
                       c.adset_id, c.adset_name, c.thumbnail_url, c.body_text, c.headline,
                       c.call_to_action, c.status, c.creative_type,
                       COALESCE(SUM(m.spend), 0) as total_spend,
                       COALESCE(SUM(m.impressions), 0) as total_impressions,
                       COALESCE(SUM(m.clicks), 0) as total_clicks,
                       COALESCE(SUM(m.conversions), 0) as total_conversions,
                       COALESCE(AVG(m.ctr), 0) as avg_ctr,
                       COALESCE(AVG(m.frequency), 0) as avg_frequency,
                       COALESCE(MAX(m.frequency), 0) as max_frequency
                FROM creatives c
                LEFT JOIN creative_daily_metrics m
                    ON c.id = m.creative_id AND m.metric_date >= ?
                WHERE 1=1
            """
            params = [since]

            if status:
                query += " AND c.status = ?"
                params.append(status)
            if campaign_id:
                query += " AND c.campaign_id = ?"
                params.append(campaign_id)

            query += " GROUP BY c.id ORDER BY total_spend DESC"

            rows = conn.execute(query, params).fetchall()

            creatives = []
            for r in rows:
                r = dict(r)
                spend = r["total_spend"]
                conversions = r["total_conversions"]
                clicks = r["total_clicks"]
                impressions = r["total_impressions"]

                cpa = round(spend / conversions, 2) if conversions > 0 else 0
                ctr = round(clicks / impressions * 100, 2) if impressions > 0 else 0

                # Score (0-100)
                score = self._compute_score(ctr, conversions, cpa, spend)

                # Fatigue detection
                fatigue_status = self._detect_fatigue(r["id"], r["avg_frequency"], conn)

                if fatigue_only and fatigue_status == "healthy":
                    continue

                creatives.append({
                    "id": r["id"],
                    "ad_id": r["ad_id"],
                    "name": r["creative_name"] or "Unnamed",
                    "campaign": r["campaign_name"] or "",
                    "campaign_id": r["campaign_id"] or "",
                    "adset": r["adset_name"] or "",
                    "thumbnail_url": r["thumbnail_url"] or "",
                    "headline": r["headline"] or "",
                    "body": r["body_text"] or "",
                    "status": r["status"] or "UNKNOWN",
                    "type": r["creative_type"] or "image",
                    "spend": round(spend, 2),
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": ctr,
                    "conversions": conversions,
                    "cpa": cpa,
                    "frequency": round(r["avg_frequency"], 2),
                    "score": score,
                    "fatigue_status": fatigue_status,
                })

            return creatives
        finally:
            conn.close()

    def _compute_score(self, ctr, conversions, cpa, spend):
        """
        Creative Performance Score (0-100).

        Weighted formula:
        - CTR contribution (25%): Higher CTR = better. Baseline 1%, cap at 5%.
        - Conversion contribution (30%): More conversions = better. Cap at 10.
        - CPA efficiency (25%): Lower CPA = better. Inverted scale, baseline $50.
        - Spend weight (20%): More spend with results = more statistical confidence.

        Each component scales 0-100, then weighted average.
        """
        if spend == 0:
            return 0

        # CTR score (0-100): 0% -> 0, 1% -> 50, 3%+ -> 100
        ctr_score = min(100, (ctr / 3.0) * 100)

        # Conversion score (0-100): 0 -> 0, 5 -> 50, 10+ -> 100
        conv_score = min(100, (conversions / 10.0) * 100)

        # CPA score (0-100): $0 -> 100, $25 -> 50, $50+ -> 0 (inverted - lower is better)
        if cpa == 0 and conversions > 0:
            cpa_score = 100
        elif cpa == 0:
            cpa_score = 0
        else:
            cpa_score = max(0, min(100, (1 - cpa / 50.0) * 100))

        # Spend confidence (0-100): $0 -> 0, $50 -> 50, $100+ -> 100
        spend_score = min(100, (spend / 100.0) * 100)

        score = round(
            ctr_score * 0.25 +
            conv_score * 0.30 +
            cpa_score * 0.25 +
            spend_score * 0.20
        )

        return max(0, min(100, score))

    def _detect_fatigue(self, creative_id, avg_frequency, conn=None):
        """
        Detect creative fatigue using heuristics.

        Rules:
        1. HIGH FREQUENCY: avg frequency > 3.0 -> 'warning'
        2. CTR DECLINE: CTR dropped >20% vs 3-day rolling avg -> 'fatigued'
        3. Both conditions -> 'critical'

        Returns: 'healthy', 'warning', 'fatigued', 'critical'
        """
        should_close = False
        if conn is None:
            conn = get_connection()
            should_close = True

        try:
            high_freq = avg_frequency > 3.0

            # Check CTR trend (last 3 days vs prior 3 days)
            rows = conn.execute(
                """SELECT metric_date, ctr FROM creative_daily_metrics
                   WHERE creative_id = ? ORDER BY metric_date DESC LIMIT 6""",
                (creative_id,),
            ).fetchall()

            ctr_declining = False
            if len(rows) >= 4:
                recent = [r["ctr"] for r in rows[:3]]
                prior = [r["ctr"] for r in rows[3:6]]
                avg_recent = sum(recent) / len(recent) if recent else 0
                avg_prior = sum(prior) / len(prior) if prior else 0
                if avg_prior > 0 and avg_recent < avg_prior * 0.8:
                    ctr_declining = True

            if high_freq and ctr_declining:
                return "critical"
            elif ctr_declining:
                return "fatigued"
            elif high_freq:
                return "warning"
            return "healthy"
        finally:
            if should_close:
                conn.close()

    def get_top_creatives(self, days=7, limit=5):
        """Get top performing creatives by score."""
        all_creatives = self.get_creatives(days=days)
        sorted_creatives = sorted(all_creatives, key=lambda c: c["score"], reverse=True)
        return sorted_creatives[:limit]

    def get_fatigued_creatives(self, days=7):
        """Get creatives with fatigue signals."""
        return self.get_creatives(days=days, fatigue_only=True)

    def get_summary(self, days=7):
        """Get creative intelligence summary."""
        all_creatives = self.get_creatives(days=days)
        if not all_creatives:
            return {
                "total_creatives": 0,
                "active_creatives": 0,
                "avg_score": 0,
                "top_performer": None,
                "worst_performer": None,
                "fatigued_count": 0,
                "warning_count": 0,
                "total_spend": 0,
                "total_conversions": 0,
            }

        active = [c for c in all_creatives if c["status"] == "ACTIVE"]
        fatigued = [c for c in all_creatives if c["fatigue_status"] in ("fatigued", "critical")]
        warning = [c for c in all_creatives if c["fatigue_status"] == "warning"]
        sorted_by_score = sorted(all_creatives, key=lambda c: c["score"], reverse=True)

        return {
            "total_creatives": len(all_creatives),
            "active_creatives": len(active),
            "avg_score": round(sum(c["score"] for c in all_creatives) / len(all_creatives)),
            "top_performer": sorted_by_score[0] if sorted_by_score else None,
            "worst_performer": sorted_by_score[-1] if sorted_by_score else None,
            "fatigued_count": len(fatigued),
            "warning_count": len(warning),
            "total_spend": round(sum(c["spend"] for c in all_creatives), 2),
            "total_conversions": sum(c["conversions"] for c in all_creatives),
        }
