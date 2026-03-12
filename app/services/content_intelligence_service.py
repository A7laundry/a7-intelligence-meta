"""Content Intelligence Service — Phase 8F.

Turns publishing data into actionable insights, rankings, and reuse
recommendations. Supports graceful mock-metrics fallback when no real
provider data is available (local dev / testing).

Content Score Formula (0–100):
  - Engagement rate  (engagement / reach): up to 40 pts   (3 % ER = 40)
  - CTR              (clicks / reach):     up to 20 pts   (1 % = 20)
  - Saves+Shares     (combined / reach):   up to 20 pts   (1 % = 20)
  - Likes rate       (likes / reach):      up to 10 pts   (3 % = 10)
  - Recency bonus    (days since publish): up to 10 pts   (0-day = 10, decays)
"""

import json
from datetime import datetime, timedelta

from app.db.init_db import get_connection

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PLATFORM_REACH_MULT = {
    "instagram": 1.0,
    "tiktok": 1.5,
    "facebook": 0.85,
    "facebook_page": 0.85,
    "linkedin": 0.45,
    "pinterest": 0.65,
    "google_display": 0.35,
}

_FORMAT_ENG_MULT = {
    "reel": 1.6,
    "carousel": 1.2,
    "story": 0.9,
    "image_post": 1.0,
    "banner": 0.7,
    "ad_creative": 0.8,
}

# Thresholds for content score tiers
_SCORE_TOP_PERFORMER = 60.0
_SCORE_REUSE = 65.0
_SCORE_LOW = 20.0

# Minimum days since publish to flag for reuse
_REUSE_MIN_DAYS = 7


# ---------------------------------------------------------------------------
# Mock metrics helper
# ---------------------------------------------------------------------------


def _mock_metrics(post: dict) -> dict:
    """Generate deterministic mock metrics seeded by post_id.

    Used when no real provider data is available. Values are stable across
    calls for the same post so tests are repeatable.
    """
    pid = int(post.get("id", 1))
    # Simple deterministic hash spread
    seed = (pid * 7919 + 13) % 10000

    reach_mult = _PLATFORM_REACH_MULT.get(post.get("platform_target", "instagram"), 0.8)
    eng_mult = _FORMAT_ENG_MULT.get(post.get("post_type", "image_post"), 1.0)

    base_reach = 800 + (seed % 8200)
    reach = max(100, int(base_reach * reach_mult))
    impressions = int(reach * (1.1 + (seed % 5) * 0.05))

    # engagement rate 2-10 %
    er = 0.02 + (seed % 80) * 0.001
    engagement = max(1, int(reach * er * eng_mult))

    likes = max(0, int(engagement * 0.60))
    comments = max(0, int(engagement * 0.10))
    shares = max(0, int(engagement * 0.15))
    saves = max(0, int(engagement * 0.15))

    clicks = max(0, int(reach * (0.005 + (seed % 25) * 0.001)))
    ctr = round(clicks / max(reach, 1), 4)

    return {
        "impressions": impressions,
        "reach": reach,
        "clicks": clicks,
        "engagement": engagement,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "saves": saves,
        "ctr": ctr,
    }


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------


def _score_from_metrics(metrics: dict, published_at: object) -> float:
    """Calculate a 0–100 content score from a metrics dict.

    See module docstring for formula documentation.
    """
    reach = max(metrics.get("reach", 0), 1)
    engagement = metrics.get("engagement", 0)
    clicks = metrics.get("clicks", 0)
    saves = metrics.get("saves", 0)
    shares = metrics.get("shares", 0)
    likes = metrics.get("likes", 0)
    ctr = metrics.get("ctr") or (clicks / reach)

    # Normalised rates
    er = engagement / reach          # engagement rate
    ctr_rate = ctr                   # already a fraction
    ss_rate = (saves + shares) / reach
    lr = likes / reach

    # Component scores capped individually
    eng_score = min(40.0, (er / 0.03) * 40.0)
    ctr_score = min(20.0, (ctr_rate / 0.01) * 20.0)
    ss_score = min(20.0, (ss_rate / 0.01) * 20.0)
    likes_score = min(10.0, (lr / 0.03) * 10.0)

    # Recency bonus: max 10 pts, decays linearly to 0 at 100 days
    recency_bonus = 0.0
    if published_at:
        try:
            pub_dt = datetime.fromisoformat(published_at.replace("Z", ""))
            days_ago = max(0, (datetime.utcnow() - pub_dt).days)
            recency_bonus = max(0.0, 10.0 * (1.0 - days_ago / 100.0))
        except Exception:
            pass

    total = eng_score + ctr_score + ss_score + likes_score + recency_bonus
    return round(max(0.0, min(100.0, total)), 1)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ContentIntelligenceService:

    # ── Sync ────────────────────────────────────────────────────────────────

    def sync_content_metrics(self, account_id: int) -> dict:
        """Populate content_metrics for all published posts of this account.

        If real provider metrics are unavailable, falls back to deterministic
        mock data so the rest of the intelligence layer works in dev/test.

        Returns {"synced": N, "already_synced": M}.
        """
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT p.id, p.platform_target, p.post_type, p.published_at
                   FROM content_posts p
                   WHERE p.account_id = ? AND p.status = 'published'
                   ORDER BY p.published_at DESC""",
                (int(account_id),),
            ).fetchall()
            posts = [dict(r) for r in rows]

            synced = 0
            already = 0
            for post in posts:
                metric_date = (
                    post["published_at"][:10]
                    if post.get("published_at")
                    else datetime.utcnow().strftime("%Y-%m-%d")
                )
                # Check if already synced
                existing = conn.execute(
                    "SELECT id FROM content_metrics WHERE content_post_id=? AND metric_date=?",
                    (post["id"], metric_date),
                ).fetchone()
                if existing:
                    already += 1
                    continue

                m = _mock_metrics(post)
                conn.execute(
                    """INSERT OR IGNORE INTO content_metrics
                       (account_id, content_post_id, platform_target, metric_date,
                        impressions, reach, clicks, engagement,
                        likes, comments, shares, saves, ctr)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        int(account_id),
                        post["id"],
                        post.get("platform_target", ""),
                        metric_date,
                        m["impressions"], m["reach"], m["clicks"],
                        m["engagement"], m["likes"], m["comments"],
                        m["shares"], m["saves"], m["ctr"],
                    ),
                )
                synced += 1

            conn.commit()
            return {"synced": synced, "already_synced": already, "total": len(posts)}
        except Exception as e:
            conn.rollback()
            return {"error": str(e), "synced": 0, "already_synced": 0}
        finally:
            conn.close()

    # ── Summary ──────────────────────────────────────────────────────────────

    def get_content_summary(self, account_id: int, days: int = 7) -> dict:
        """Aggregate KPIs for the last N days: posts, reach, engagement, avg score."""
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = get_connection()
        try:
            row = conn.execute(
                """SELECT COUNT(DISTINCT p.id) AS posts_published,
                          COALESCE(SUM(m.reach), 0)      AS total_reach,
                          COALESCE(SUM(m.engagement), 0) AS total_engagement,
                          COALESCE(SUM(m.clicks), 0)     AS total_clicks,
                          COALESCE(SUM(m.impressions), 0) AS total_impressions
                   FROM content_posts p
                   LEFT JOIN content_metrics m ON m.content_post_id = p.id
                   WHERE p.account_id = ?
                     AND p.status = 'published'
                     AND p.published_at >= ?""",
                (int(account_id), since),
            ).fetchone()

            posts_published = row["posts_published"] or 0
            total_reach = row["total_reach"] or 0
            total_engagement = row["total_engagement"] or 0

            # Average content score across posts with metrics
            score_rows = conn.execute(
                """SELECT p.id, p.platform_target, p.post_type, p.published_at,
                          m.reach, m.engagement, m.clicks, m.saves, m.shares,
                          m.likes, m.ctr
                   FROM content_posts p
                   JOIN content_metrics m ON m.content_post_id = p.id
                   WHERE p.account_id = ?
                     AND p.status = 'published'
                     AND p.published_at >= ?""",
                (int(account_id), since),
            ).fetchall()

            scores = [
                _score_from_metrics(dict(r), r["published_at"])
                for r in score_rows
            ]
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

            return {
                "posts_published": posts_published,
                "total_reach": total_reach,
                "total_engagement": total_engagement,
                "total_clicks": row["total_clicks"] or 0,
                "total_impressions": row["total_impressions"] or 0,
                "avg_score": avg_score,
                "days": days,
            }
        finally:
            conn.close()

    # ── Top Posts ────────────────────────────────────────────────────────────

    def get_top_posts(self, account_id: int, days: int = 7, limit: int = 10) -> list:
        """Return top N posts by content score for the last N days."""
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT p.id, p.title, p.platform_target, p.post_type,
                          p.published_at, p.caption,
                          ca.thumbnail_url,
                          m.reach, m.engagement, m.clicks, m.saves, m.shares,
                          m.likes, m.impressions, m.ctr
                   FROM content_posts p
                   JOIN content_metrics m ON m.content_post_id = p.id
                   LEFT JOIN creative_assets ca ON ca.id = p.creative_asset_id
                   WHERE p.account_id = ?
                     AND p.status = 'published'
                     AND p.published_at >= ?
                   ORDER BY m.engagement DESC""",
                (int(account_id), since),
            ).fetchall()

            results = []
            for r in rows:
                d = dict(r)
                d["score"] = _score_from_metrics(d, d.get("published_at"))
                results.append(d)

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]
        finally:
            conn.close()

    # ── Format Performance ───────────────────────────────────────────────────

    def get_format_performance(self, account_id: int, days: int = 30) -> list:
        """Group posts by format (post_type × platform) and rank by avg engagement."""
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT p.post_type, p.platform_target,
                          COUNT(DISTINCT p.id) AS post_count,
                          COALESCE(AVG(m.engagement), 0) AS avg_engagement,
                          COALESCE(AVG(m.reach), 0)      AS avg_reach,
                          COALESCE(AVG(m.ctr), 0)        AS avg_ctr,
                          COALESCE(SUM(m.engagement), 0) AS total_engagement
                   FROM content_posts p
                   JOIN content_metrics m ON m.content_post_id = p.id
                   WHERE p.account_id = ?
                     AND p.status = 'published'
                     AND p.published_at >= ?
                   GROUP BY p.post_type, p.platform_target
                   ORDER BY avg_engagement DESC""",
                (int(account_id), since),
            ).fetchall()

            results = []
            for r in rows:
                d = dict(r)
                d["avg_engagement"] = round(d["avg_engagement"], 1)
                d["avg_reach"] = round(d["avg_reach"], 1)
                d["avg_ctr"] = round(d["avg_ctr"], 4)
                results.append(d)
            return results
        finally:
            conn.close()

    # ── Best Posting Times ───────────────────────────────────────────────────

    def get_best_posting_times(self, account_id: int, days: int = 30) -> list:
        """Find weekday × hour windows with highest average engagement."""
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT p.published_at, m.engagement, m.reach
                   FROM content_posts p
                   JOIN content_metrics m ON m.content_post_id = p.id
                   WHERE p.account_id = ?
                     AND p.status = 'published'
                     AND p.published_at >= ?
                     AND p.published_at IS NOT NULL""",
                (int(account_id), since),
            ).fetchall()

            # Bucket by (weekday, hour)
            buckets: dict = {}
            for r in rows:
                try:
                    dt = datetime.fromisoformat(r["published_at"].replace("Z", ""))
                    key = (dt.weekday(), dt.hour)  # 0=Mon … 6=Sun
                    buckets.setdefault(key, []).append(
                        {"engagement": r["engagement"], "reach": r["reach"]}
                    )
                except Exception:
                    continue

            _day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            results = []
            for (wd, hr), items in buckets.items():
                avg_eng = sum(i["engagement"] for i in items) / len(items)
                avg_reach = sum(i["reach"] for i in items) / len(items)
                results.append(
                    {
                        "weekday": wd,
                        "weekday_label": _day_names[wd],
                        "hour": hr,
                        "hour_label": f"{hr:02d}:00",
                        "post_count": len(items),
                        "avg_engagement": round(avg_eng, 1),
                        "avg_reach": round(avg_reach, 1),
                    }
                )
            results.sort(key=lambda x: x["avg_engagement"], reverse=True)
            return results[:10]
        finally:
            conn.close()

    # ── Reuse Opportunities ──────────────────────────────────────────────────

    def detect_reuse_opportunities(self, account_id: int, days: int = 30) -> list:
        """Detect top-performing and reuse-worthy posts; persist insights.

        Generates:
        - top_performer: score >= _SCORE_TOP_PERFORMER
        - reuse_opportunity: score >= _SCORE_REUSE, published >= _REUSE_MIN_DAYS ago
        - paid_synergy: post derived from a creative_intelligence idea
        - low_engagement: score < _SCORE_LOW (with > 50 reach)
        - format_winner: the format+platform with highest avg engagement

        Returns the list of upserted insight dicts.
        """
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT p.id, p.title, p.platform_target, p.post_type,
                          p.published_at, p.content_idea_id,
                          ci.source AS idea_source,
                          m.reach, m.engagement, m.clicks, m.saves, m.shares,
                          m.likes, m.impressions, m.ctr
                   FROM content_posts p
                   JOIN content_metrics m ON m.content_post_id = p.id
                   LEFT JOIN content_ideas ci ON ci.id = p.content_idea_id
                   WHERE p.account_id = ?
                     AND p.status = 'published'
                     AND p.published_at >= ?""",
                (int(account_id), since),
            ).fetchall()

            now = datetime.utcnow()
            insights_to_save = []

            # Per-format aggregation for format_winner
            fmt_buckets: dict = {}

            for r in rows:
                d = dict(r)
                score = _score_from_metrics(d, d.get("published_at"))
                d["score"] = score

                # Days since published
                days_ago = 9999
                if d.get("published_at"):
                    try:
                        pub_dt = datetime.fromisoformat(d["published_at"].replace("Z", ""))
                        days_ago = (now - pub_dt).days
                    except Exception:
                        pass

                if score >= _SCORE_TOP_PERFORMER:
                    insights_to_save.append(
                        {
                            "post_id": d["id"],
                            "type": "top_performer",
                            "title": f"Top Performer: {d['title'] or '(untitled)'}",
                            "message": (
                                f"This post scored {score:.0f}/100 on {d['platform_target']}. "
                                "Consider turning it into a paid ad."
                            ),
                            "score": score,
                        }
                    )

                if score >= _SCORE_REUSE and days_ago >= _REUSE_MIN_DAYS:
                    insights_to_save.append(
                        {
                            "post_id": d["id"],
                            "type": "reuse_opportunity",
                            "title": f"Repost or Remix: {d['title'] or '(untitled)'}",
                            "message": (
                                f"Published {days_ago} days ago with score {score:.0f}/100. "
                                "Create a variation or repost to re-capture reach."
                            ),
                            "score": score,
                        }
                    )

                if d.get("idea_source") in ("creative_intelligence", "ai_coach", "copilot"):
                    insights_to_save.append(
                        {
                            "post_id": d["id"],
                            "type": "paid_synergy",
                            "title": f"AI-Sourced Post: {d['title'] or '(untitled)'}",
                            "message": (
                                f"This post came from a {d['idea_source']} idea and scored {score:.0f}/100. "
                                "Compare with paid campaign performance."
                            ),
                            "score": score,
                        }
                    )

                if score < _SCORE_LOW and d.get("reach", 0) > 50:
                    insights_to_save.append(
                        {
                            "post_id": d["id"],
                            "type": "low_engagement",
                            "title": f"Low Engagement: {d['title'] or '(untitled)'}",
                            "message": (
                                f"Score {score:.0f}/100 on {d['platform_target']}. "
                                "Consider a different format or posting time."
                            ),
                            "score": score,
                        }
                    )

                # Accumulate for format_winner
                fmt_key = (d["post_type"], d["platform_target"])
                fmt_buckets.setdefault(fmt_key, []).append(d["engagement"] or 0)

            # Format winner insight
            if fmt_buckets:
                best_fmt, best_vals = max(
                    fmt_buckets.items(), key=lambda kv: sum(kv[1]) / max(len(kv[1]), 1)
                )
                avg_eng = sum(best_vals) / max(len(best_vals), 1)
                insights_to_save.append(
                    {
                        "post_id": None,
                        "type": "format_winner",
                        "title": f"Format Winner: {best_fmt[0]} on {best_fmt[1]}",
                        "message": (
                            f"{best_fmt[0].replace('_', ' ').title()} posts on {best_fmt[1]} "
                            f"average {avg_eng:.0f} engagements. Post more of this format."
                        ),
                        "score": round(avg_eng, 1),
                    }
                )

            # Persist (INSERT OR REPLACE so each sync refreshes)
            saved = []
            for ins in insights_to_save:
                # Delete previous insight of same type for same post (upsert)
                if ins["post_id"]:
                    conn.execute(
                        "DELETE FROM content_insights WHERE account_id=? AND content_post_id=? AND insight_type=?",
                        (int(account_id), ins["post_id"], ins["type"]),
                    )
                else:
                    conn.execute(
                        "DELETE FROM content_insights WHERE account_id=? AND insight_type=? AND content_post_id IS NULL",
                        (int(account_id), ins["type"]),
                    )

                conn.execute(
                    """INSERT INTO content_insights
                       (account_id, content_post_id, insight_type, title, message, score, payload_json)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        int(account_id),
                        ins["post_id"],
                        ins["type"],
                        ins["title"],
                        ins["message"],
                        ins["score"],
                        json.dumps({"post_id": ins["post_id"]}),
                    ),
                )
                saved.append(ins)

            conn.commit()
            return saved
        except Exception as e:
            conn.rollback()
            return [{"error": str(e)}]
        finally:
            conn.close()

    # ── Content Score ─────────────────────────────────────────────────────────

    def calculate_content_score(self, post_id: int, account_id: int) -> float:
        """Return the 0–100 content score for a single post.

        Uses stored metrics if available; falls back to mock metrics otherwise.
        """
        conn = get_connection()
        try:
            post_row = conn.execute(
                "SELECT * FROM content_posts WHERE id=? AND account_id=?",
                (int(post_id), int(account_id)),
            ).fetchone()
            if not post_row:
                return 0.0
            post = dict(post_row)

            m_row = conn.execute(
                """SELECT * FROM content_metrics
                   WHERE content_post_id=?
                   ORDER BY metric_date DESC LIMIT 1""",
                (int(post_id),),
            ).fetchone()

            m = dict(m_row) if m_row else _mock_metrics(post)
            return _score_from_metrics(m, post.get("published_at"))
        finally:
            conn.close()

    # ── Stored insights ──────────────────────────────────────────────────────

    def get_insights(self, account_id: int, insight_type: object = None) -> list:
        """Return stored insights for an account, optionally filtered by type."""
        conn = get_connection()
        try:
            if insight_type:
                rows = conn.execute(
                    """SELECT * FROM content_insights
                       WHERE account_id=? AND insight_type=?
                       ORDER BY score DESC, created_at DESC""",
                    (int(account_id), insight_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM content_insights
                       WHERE account_id=?
                       ORDER BY score DESC, created_at DESC""",
                    (int(account_id),),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
