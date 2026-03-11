"""
Testes para DashboardFetcher — agregação de dados e demo mode.
"""

from unittest.mock import patch, MagicMock


class TestDashboardFetcher:
    """Testes para o fetcher de dados do dashboard."""

    def _make_fetcher(self, meta_available=False, google_available=False):
        """Cria DashboardFetcher com clients mockados."""
        with patch("dashboard_fetcher.DashboardFetcher._init_clients"):
            from dashboard_fetcher import DashboardFetcher
            fetcher = DashboardFetcher()
            fetcher.meta_available = meta_available
            fetcher.google_available = google_available
            fetcher.meta_client = MagicMock() if meta_available else None
            fetcher.google_client = MagicMock() if google_available else None
            return fetcher

    def test_demo_data_structure(self):
        """Demo data deve ter estrutura correta."""
        from dashboard_fetcher import DashboardFetcher

        data = DashboardFetcher.generate_demo_data("7d")

        assert data["demo"] is True
        assert "summary" in data
        assert "meta" in data["summary"]
        assert "google" in data["summary"]
        assert "total" in data["summary"]
        assert "campaigns" in data
        assert "daily_trend" in data

    def test_demo_data_ranges(self):
        """Demo data deve funcionar para todos os ranges."""
        from dashboard_fetcher import DashboardFetcher

        for range_key in ("today", "7d", "30d"):
            data = DashboardFetcher.generate_demo_data(range_key)
            assert data["demo"] is True
            assert data["summary"]["total"]["spend"] > 0

    def test_demo_data_daily_trend_length(self):
        """Daily trend deve ter o número correto de dias."""
        from dashboard_fetcher import DashboardFetcher

        data_7d = DashboardFetcher.generate_demo_data("7d")
        assert len(data_7d["daily_trend"]) == 7

        data_30d = DashboardFetcher.generate_demo_data("30d")
        assert len(data_30d["daily_trend"]) == 30

    def test_demo_data_summary_totals(self):
        """Total summary deve ser soma de Meta + Google."""
        from dashboard_fetcher import DashboardFetcher

        data = DashboardFetcher.generate_demo_data("7d")

        meta_spend = data["summary"]["meta"]["spend"]
        google_spend = data["summary"]["google"]["spend"]
        total_spend = data["summary"]["total"]["spend"]

        # Total deve ser aproximadamente meta + google (com arredondamento)
        assert abs(total_spend - (meta_spend + google_spend)) < 0.01

    def test_fallback_to_demo_when_no_clients(self):
        """Quando nenhum client disponível, deve usar demo data."""
        fetcher = self._make_fetcher(meta_available=False, google_available=False)

        data = fetcher.build_dashboard_data("7d")

        assert data["demo"] is True

    def test_fetch_meta_data_not_available(self):
        """fetch_meta_data deve retornar None quando Meta não disponível."""
        fetcher = self._make_fetcher(meta_available=False)

        result = fetcher.fetch_meta_data("last_7d")

        assert result is None

    def test_fetch_google_data_not_available(self):
        """fetch_google_data deve retornar None quando Google não disponível."""
        fetcher = self._make_fetcher(google_available=False)

        result = fetcher.fetch_google_data("last_7d")

        assert result is None

    def test_meta_summary_with_mock_data(self):
        """fetch_meta_data deve calcular métricas corretamente."""
        fetcher = self._make_fetcher(meta_available=True)

        fetcher.meta_client.get_account_insights.return_value = [{
            "spend": "150.00",
            "impressions": "10000",
            "clicks": "300",
            "ctr": "3.0",
            "cpc": "0.50",
            "actions": [
                {"action_type": "lead", "value": "10"},
                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "5"},
            ],
            "action_values": [
                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "500.00"},
            ],
        }]
        fetcher.meta_client.list_campaigns.return_value = []

        result = fetcher.fetch_meta_data("last_7d")

        assert result is not None
        summary = result["summary"]
        assert summary["spend"] == 150.00
        assert summary["impressions"] == 10000
        assert summary["clicks"] == 300
        assert summary["conversions"] == 10
        assert summary["cpa"] == 15.00  # 150/10
        assert summary["roas"] > 0  # deve calcular ROAS corretamente agora

    def test_campaigns_list(self):
        """Demo data deve ter campanhas para ambas plataformas."""
        from dashboard_fetcher import DashboardFetcher

        data = DashboardFetcher.generate_demo_data("7d")

        assert len(data["campaigns"]["meta"]) == 3
        assert len(data["campaigns"]["google"]) == 3

        for campaign in data["campaigns"]["meta"]:
            assert "id" in campaign
            assert "name" in campaign
            assert "spend" in campaign
            assert "cpa" in campaign

    def test_write_json(self, tmp_path):
        """write_json deve criar arquivo JSON válido."""
        fetcher = self._make_fetcher()

        import json
        import dashboard_fetcher
        original_dir = dashboard_fetcher.DASHBOARD_DIR
        dashboard_fetcher.DASHBOARD_DIR = str(tmp_path)

        try:
            data = {"test": True, "value": 42}
            fetcher.write_json("7d", data)

            filepath = tmp_path / "dashboard-data-7d.json"
            assert filepath.exists()

            with open(filepath) as f:
                loaded = json.load(f)
            assert loaded == data
        finally:
            dashboard_fetcher.DASHBOARD_DIR = original_dir
