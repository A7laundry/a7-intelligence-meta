"""Content Studio Service — ideas, brand kits, prompts, and creative assets."""

from app.db.init_db import get_connection


class ContentStudioService:
    VALID_CONTENT_TYPES = ("post", "reel", "story", "ad_creative", "carousel", "banner")
    VALID_PLATFORMS = ("instagram", "facebook", "google_display", "tiktok", "linkedin")
    VALID_STATUSES = ("idea", "draft", "approved", "rejected")
    VALID_SOURCES = ("copilot", "ai_coach", "manual", "creative_intelligence")
    VALID_IMAGE_TYPES = ("ad_creative", "social_post", "story", "banner")
    VALID_ASSET_TYPES = ("image", "video", "design", "mockup")
    VALID_ASSET_STATUSES = ("draft", "approved", "published", "archived")

    # ── Content Ideas ────────────────────────────────────────────────────────

    def list_ideas(self, account_id=None, status=None, limit=50):
        """Return content ideas, optionally filtered by account and status."""
        conn = get_connection()
        try:
            query = "SELECT * FROM content_ideas"
            params = []
            conditions = []
            if account_id is not None:
                conditions.append("account_id = ?")
                params.append(int(account_id))
            if status and status in self.VALID_STATUSES:
                conditions.append("status = ?")
                params.append(status)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def create_idea(self, account_id, title, description="", content_type="post",
                    platform_target="instagram", status="idea", source="manual"):
        """Insert a new content idea and return its id."""
        if content_type not in self.VALID_CONTENT_TYPES:
            content_type = "post"
        if platform_target not in self.VALID_PLATFORMS:
            platform_target = "instagram"
        if status not in self.VALID_STATUSES:
            status = "idea"
        if source not in self.VALID_SOURCES:
            source = "manual"
        conn = get_connection()
        try:
            cur = conn.execute(
                """INSERT INTO content_ideas
                   (account_id, title, description, content_type, platform_target, status, source)
                   VALUES (?,?,?,?,?,?,?)""",
                (int(account_id), title, description, content_type,
                 platform_target, status, source),
            )
            conn.commit()
            return {"id": cur.lastrowid, "title": title, "status": status}
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def update_idea_status(self, idea_id, status, account_id=None):
        """Update the status of an existing idea."""
        if status not in self.VALID_STATUSES:
            return {"error": f"Invalid status: {status}"}
        conn = get_connection()
        try:
            query = "UPDATE content_ideas SET status = ? WHERE id = ?"
            params = [status, int(idea_id)]
            if account_id is not None:
                query += " AND account_id = ?"
                params.append(int(account_id))
            conn.execute(query, params)
            conn.commit()
            return {"success": True, "idea_id": int(idea_id), "status": status}
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def generate_ideas(self, account_id=1):
        """Generate content ideas from live marketing insights.

        Pulls top campaigns, creative winners, and alerts to create
        content_ideas rows with source='ai_coach' or 'creative_intelligence'.
        Returns list of created idea dicts.
        """
        ideas = []
        account_id = int(account_id) if account_id else 1

        # Gather context from existing services
        top_campaigns = []
        fatigued_creatives = []
        alerts = []

        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            opps = bi.detect_scaling_opportunities(days=7, account_id=account_id)
            for o in opps[:3]:
                top_campaigns.append(o.get("campaign_name", ""))
        except Exception:
            pass

        try:
            from app.services.creative_service import CreativeService
            cs = CreativeService()
            fatigued_creatives = cs.get_fatigued_creatives(days=7, account_id=account_id)[:3]
        except Exception:
            pass

        try:
            from app.services.alerts_service import AlertsService
            svc = AlertsService()
            alerts = svc.get_alerts(resolved=False, account_id=account_id, limit=3)
        except Exception:
            pass

        # Build idea templates from insights
        idea_templates = []

        for campaign_name in top_campaigns:
            if campaign_name:
                idea_templates.append({
                    "title": f"Turn '{campaign_name}' into an Instagram Reel",
                    "description": f"Repurpose the top-performing campaign '{campaign_name}' as a short-form video highlighting the main offer.",
                    "content_type": "reel",
                    "platform_target": "instagram",
                    "source": "ai_coach",
                })
                idea_templates.append({
                    "title": f"Carousel: highlights from '{campaign_name}'",
                    "description": f"Create a multi-slide carousel showcasing the key benefits and results from '{campaign_name}'.",
                    "content_type": "carousel",
                    "platform_target": "facebook",
                    "source": "ai_coach",
                })

        for cr in fatigued_creatives:
            name = cr.get("name", "creative")
            idea_templates.append({
                "title": f"Refresh fatigued creative: {name}",
                "description": f"The creative '{name}' shows fatigue signals. Generate a fresh variant with updated visuals and copy.",
                "content_type": "ad_creative",
                "platform_target": "instagram",
                "source": "creative_intelligence",
            })

        for alert in alerts:
            title = alert.get("title", "")
            if title:
                idea_templates.append({
                    "title": f"Address alert: {title}",
                    "description": f"Create content addressing the performance issue: {alert.get('message', title)}",
                    "content_type": "story",
                    "platform_target": "instagram",
                    "source": "ai_coach",
                })

        # Fallback ideas when no signals available
        if not idea_templates:
            idea_templates = [
                {
                    "title": "Brand awareness Instagram post",
                    "description": "Create an engaging brand awareness post for Instagram showcasing your core value proposition.",
                    "content_type": "post",
                    "platform_target": "instagram",
                    "source": "ai_coach",
                },
                {
                    "title": "Facebook ad creative for conversions",
                    "description": "Design a high-converting Facebook ad creative with a strong call to action.",
                    "content_type": "ad_creative",
                    "platform_target": "facebook",
                    "source": "ai_coach",
                },
                {
                    "title": "Story: limited-time offer",
                    "description": "Create an urgency-driven Instagram story highlighting a time-sensitive offer.",
                    "content_type": "story",
                    "platform_target": "instagram",
                    "source": "ai_coach",
                },
            ]

        for tmpl in idea_templates[:5]:
            result = self.create_idea(
                account_id=account_id,
                title=tmpl["title"],
                description=tmpl.get("description", ""),
                content_type=tmpl.get("content_type", "post"),
                platform_target=tmpl.get("platform_target", "instagram"),
                status="idea",
                source=tmpl.get("source", "ai_coach"),
            )
            if "id" in result:
                ideas.append(result)

        return ideas

    # ── Brand Kit ────────────────────────────────────────────────────────────

    def get_brand_kit(self, account_id=1):
        """Return brand kit for an account, or defaults if not set."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM brand_kits WHERE account_id = ?", (int(account_id),)
            ).fetchone()
            if row:
                return dict(row)
            return self._default_brand_kit(account_id)
        except Exception:
            return self._default_brand_kit(account_id)
        finally:
            conn.close()

    def save_brand_kit(self, account_id, data):
        """Insert or update the brand kit for an account."""
        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT id FROM brand_kits WHERE account_id = ?", (int(account_id),)
            ).fetchone()
            fields = ("brand_name", "primary_color", "secondary_color", "accent_color",
                      "font_family", "logo_url", "style_description")
            if existing:
                sets = ", ".join(f"{f} = ?" for f in fields)
                vals = [data.get(f, "") for f in fields] + [int(account_id)]
                conn.execute(f"UPDATE brand_kits SET {sets} WHERE account_id = ?", vals)
            else:
                cols = "account_id, " + ", ".join(fields)
                placeholders = ", ".join(["?"] * (len(fields) + 1))
                vals = [int(account_id)] + [data.get(f, "") for f in fields]
                conn.execute(f"INSERT INTO brand_kits ({cols}) VALUES ({placeholders})", vals)
            conn.commit()
            return self.get_brand_kit(account_id)
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    @staticmethod
    def _default_brand_kit(account_id):
        return {
            "account_id": account_id,
            "brand_name": "",
            "primary_color": "#000000",
            "secondary_color": "#ffffff",
            "accent_color": "#3B82F6",
            "font_family": "Inter",
            "logo_url": "",
            "style_description": "",
        }

    # ── Creative Prompts ─────────────────────────────────────────────────────

    def list_prompts(self, account_id=None, limit=50):
        """Return creative prompts for an account."""
        conn = get_connection()
        try:
            if account_id is not None:
                rows = conn.execute(
                    "SELECT * FROM creative_prompts WHERE account_id = ? ORDER BY created_at DESC LIMIT ?",
                    (int(account_id), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM creative_prompts ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def create_prompt(self, account_id, content_idea_id=None, prompt_text="",
                      style="photorealistic", aspect_ratio="1:1", image_type="social_post"):
        """Insert a new creative prompt."""
        if image_type not in self.VALID_IMAGE_TYPES:
            image_type = "social_post"
        conn = get_connection()
        try:
            cur = conn.execute(
                """INSERT INTO creative_prompts
                   (account_id, content_idea_id, prompt_text, style, aspect_ratio, image_type)
                   VALUES (?,?,?,?,?,?)""",
                (int(account_id), content_idea_id, prompt_text, style, aspect_ratio, image_type),
            )
            conn.commit()
            return {
                "id": cur.lastrowid,
                "account_id": int(account_id),
                "content_idea_id": content_idea_id,
                "prompt_text": prompt_text,
                "image_type": image_type,
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    # ── Creative Assets ──────────────────────────────────────────────────────

    def list_assets(self, account_id=None, status=None, limit=50):
        """Return creative assets, optionally filtered."""
        conn = get_connection()
        try:
            query = "SELECT * FROM creative_assets"
            params = []
            conditions = []
            if account_id is not None:
                conditions.append("account_id = ?")
                params.append(int(account_id))
            if status and status in self.VALID_ASSET_STATUSES:
                conditions.append("status = ?")
                params.append(status)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def create_asset(self, account_id, content_idea_id=None, asset_type="image",
                     asset_url="", thumbnail_url="", status="draft"):
        """Insert a new creative asset."""
        if asset_type not in self.VALID_ASSET_TYPES:
            asset_type = "image"
        if status not in self.VALID_ASSET_STATUSES:
            status = "draft"
        conn = get_connection()
        try:
            cur = conn.execute(
                """INSERT INTO creative_assets
                   (account_id, content_idea_id, asset_type, asset_url, thumbnail_url, status)
                   VALUES (?,?,?,?,?,?)""",
                (int(account_id), content_idea_id, asset_type, asset_url, thumbnail_url, status),
            )
            conn.commit()
            return {
                "id": cur.lastrowid,
                "account_id": int(account_id),
                "content_idea_id": content_idea_id,
                "asset_type": asset_type,
                "status": status,
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()
