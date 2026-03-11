"""
Testes para CampaignOptimizer — regras de otimização.
"""

from unittest.mock import MagicMock, patch


class TestCampaignOptimizer:
    """Testes para as 3 regras de otimização."""

    def _make_optimizer(self):
        """Cria optimizer com client mockado."""
        with patch("meta_client.requests"):
            from optimizer import CampaignOptimizer
            optimizer = CampaignOptimizer()
            optimizer.client = MagicMock()
            return optimizer

    def test_pause_high_cpa(self, sample_ad_set_high_cpa_insights):
        """Ad set com CPA > 50 deve gerar ação PAUSE."""
        optimizer = self._make_optimizer()

        optimizer.client.list_ad_sets.return_value = [
            {"id": "adset_1", "name": "High CPA Set", "status": "ACTIVE", "daily_budget": "5000"}
        ]
        optimizer.client.get_ad_set_insights.return_value = sample_ad_set_high_cpa_insights

        result = optimizer.run_optimization(dry_run=True)

        assert result["ad_sets_analyzed"] == 1
        pause_actions = [a for a in result["actions"] if a["rule"] == "pause_high_cpa"]
        assert len(pause_actions) == 1
        assert pause_actions[0]["action"] == "PAUSE"

    def test_no_pause_low_cpa(self, sample_ad_set_insights):
        """Ad set com CPA < 50 NÃO deve ser pausado por CPA."""
        optimizer = self._make_optimizer()

        optimizer.client.list_ad_sets.return_value = [
            {"id": "adset_1", "name": "Good Set", "status": "ACTIVE", "daily_budget": "5000"}
        ]
        optimizer.client.get_ad_set_insights.return_value = sample_ad_set_insights

        result = optimizer.run_optimization(dry_run=True)

        pause_cpa_actions = [a for a in result["actions"] if a["rule"] == "pause_high_cpa"]
        assert len(pause_cpa_actions) == 0

    def test_increase_budget_winners(self, sample_ad_set_insights):
        """Ad set com CPA baixo e conversões suficientes deve aumentar budget."""
        optimizer = self._make_optimizer()

        optimizer.client.list_ad_sets.return_value = [
            {"id": "adset_1", "name": "Winner Set", "status": "ACTIVE", "daily_budget": "5000"}
        ]
        optimizer.client.get_ad_set_insights.return_value = sample_ad_set_insights

        result = optimizer.run_optimization(dry_run=True)

        increase_actions = [a for a in result["actions"] if a["rule"] == "increase_budget_winners"]
        assert len(increase_actions) == 1
        assert "INCREASE_BUDGET" in increase_actions[0]["action"]

    def test_pause_low_ctr(self, sample_ad_set_low_ctr_insights):
        """Ad set com CTR < 0.5% e impressões suficientes deve ser pausado."""
        optimizer = self._make_optimizer()

        optimizer.client.list_ad_sets.return_value = [
            {"id": "adset_1", "name": "Low CTR Set", "status": "ACTIVE", "daily_budget": "3000"}
        ]
        optimizer.client.get_ad_set_insights.return_value = sample_ad_set_low_ctr_insights

        result = optimizer.run_optimization(dry_run=True)

        ctr_actions = [a for a in result["actions"] if a["rule"] == "pause_low_ctr"]
        assert len(ctr_actions) == 1

    def test_dry_run_does_not_call_api(self, sample_ad_set_high_cpa_insights):
        """Dry run não deve chamar update_ad_set_status."""
        optimizer = self._make_optimizer()

        optimizer.client.list_ad_sets.return_value = [
            {"id": "adset_1", "name": "Test", "status": "ACTIVE", "daily_budget": "5000"}
        ]
        optimizer.client.get_ad_set_insights.return_value = sample_ad_set_high_cpa_insights

        optimizer.run_optimization(dry_run=True)

        optimizer.client.update_ad_set_status.assert_not_called()
        optimizer.client.update_ad_set_budget.assert_not_called()

    def test_live_run_calls_api(self, sample_ad_set_high_cpa_insights):
        """Live run deve chamar update_ad_set_status para pausar."""
        optimizer = self._make_optimizer()

        optimizer.client.list_ad_sets.return_value = [
            {"id": "adset_1", "name": "Test", "status": "ACTIVE", "daily_budget": "5000"}
        ]
        optimizer.client.get_ad_set_insights.return_value = sample_ad_set_high_cpa_insights

        optimizer.run_optimization(dry_run=False)

        optimizer.client.update_ad_set_status.assert_called_with("adset_1", "PAUSED")

    def test_no_active_ad_sets(self):
        """Sem ad sets ativos, nenhuma ação deve ser gerada."""
        optimizer = self._make_optimizer()

        optimizer.client.list_ad_sets.return_value = [
            {"id": "adset_1", "name": "Paused Set", "status": "PAUSED", "daily_budget": "5000"}
        ]

        result = optimizer.run_optimization(dry_run=True)

        assert result["ad_sets_analyzed"] == 0
        assert len(result["actions"]) == 0

    def test_generate_report_empty(self):
        """Report com nenhum ad set ativo deve retornar mensagem."""
        optimizer = self._make_optimizer()
        optimizer.client.list_ad_sets.return_value = []

        report = optimizer.generate_report("last_7d")
        assert "Nenhum ad set ativo" in report

    def test_extract_cpa_priority(self):
        """CPA deve priorizar messaging > lead > link_click."""
        optimizer = self._make_optimizer()

        cost_per_action = [
            {"action_type": "link_click", "value": "0.50"},
            {"action_type": "onsite_conversion.messaging_conversation_started_7d", "value": "15.00"},
            {"action_type": "lead", "value": "10.00"},
        ]

        cpa = optimizer._extract_cpa(cost_per_action)
        assert cpa == 15.00  # messaging tem prioridade

    def test_extract_conversions_priority(self):
        """Conversions deve priorizar messaging > lead."""
        optimizer = self._make_optimizer()

        actions = [
            {"action_type": "link_click", "value": "100"},
            {"action_type": "lead", "value": "5"},
            {"action_type": "onsite_conversion.messaging_conversation_started_7d", "value": "3"},
        ]

        conversions = optimizer._extract_conversions(actions)
        assert conversions == 3  # messaging tem prioridade
