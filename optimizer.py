"""
A7 Lavanderia - Facebook Ads Automation
Otimizador Automático de Campanhas
Monitora performance e aplica regras de otimização automaticamente.
"""

import json
from datetime import datetime
from meta_client import MetaAdsClient
from config import OPTIMIZATION_RULES


class CampaignOptimizer:
    """Otimiza campanhas automaticamente baseado em regras pré-definidas."""

    def __init__(self):
        self.client = MetaAdsClient()
        self.log = []

    def _log_action(self, level: str, message: str):
        """Registra ação no log."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
        }
        self.log.append(entry)
        icon = {"INFO": "ℹ️", "WARNING": "⚠️", "ACTION": "🔧", "ERROR": "🔴"}.get(level, "▪️")
        print(f"{icon} [{level}] {message}")

    def analyze_ad_sets(self, date_preset: str = "last_3d") -> list:
        """
        Analisa todos os ad sets ativos e retorna métricas.

        Returns:
            Lista de ad sets com suas métricas
        """
        ad_sets = self.client.list_ad_sets()
        active_sets = [s for s in ad_sets if s.get("status") == "ACTIVE"]

        results = []
        for ad_set in active_sets:
            insights = self.client.get_ad_set_insights(ad_set["id"], date_preset)
            if insights:
                data = insights[0]

                # Extrai métricas principais
                metrics = {
                    "id": ad_set["id"],
                    "name": ad_set.get("name", ""),
                    "daily_budget": int(ad_set.get("daily_budget", 0)),
                    "impressions": int(data.get("impressions", 0)),
                    "clicks": int(data.get("clicks", 0)),
                    "ctr": float(data.get("ctr", 0)),
                    "cpc": float(data.get("cpc", 0)),
                    "spend": float(data.get("spend", 0)),
                    "reach": int(data.get("reach", 0)),
                    "actions": data.get("actions", []),
                    "cost_per_action": data.get("cost_per_action_type", []),
                }

                # Calcula CPA (custo por conversão WhatsApp ou lead)
                cpa = self._extract_cpa(metrics["cost_per_action"])
                metrics["cpa"] = cpa

                # Calcula conversões totais
                conversions = self._extract_conversions(metrics["actions"])
                metrics["conversions"] = conversions

                results.append(metrics)

        return results

    def _extract_cpa(self, cost_per_action_list: list) -> float:
        """Extrai o CPA relevante (conversão ou lead) da lista de ações."""
        priority_actions = [
            "onsite_conversion.messaging_conversation_started_7d",
            "offsite_conversion.fb_pixel_lead",
            "lead",
            "link_click",
        ]

        for action_type in priority_actions:
            for action in cost_per_action_list:
                if action.get("action_type") == action_type:
                    return float(action.get("value", 0))
        return 0.0

    def _extract_conversions(self, actions_list: list) -> int:
        """Extrai número de conversões relevantes."""
        priority_actions = [
            "onsite_conversion.messaging_conversation_started_7d",
            "offsite_conversion.fb_pixel_lead",
            "lead",
        ]

        for action_type in priority_actions:
            for action in actions_list:
                if action.get("action_type") == action_type:
                    return int(action.get("value", 0))
        return 0

    def run_optimization(self, dry_run: bool = True) -> dict:
        """
        Executa todas as regras de otimização.

        Args:
            dry_run: Se True, apenas simula as ações sem executar.
                     SEMPRE rode em dry_run primeiro!

        Returns:
            Relatório de ações tomadas/sugeridas
        """
        mode = "🔵 SIMULAÇÃO" if dry_run else "🟢 EXECUÇÃO"
        self._log_action("INFO", f"=== Iniciando otimização ({mode}) ===")

        ad_sets = self.analyze_ad_sets()
        actions_taken = []

        for ad_set in ad_sets:
            self._log_action("INFO", f"Analisando: {ad_set['name']}")
            self._log_action("INFO", f"  CPA: R${ad_set['cpa']:.2f} | CTR: {ad_set['ctr']:.2f}% | Gasto: R${ad_set['spend']:.2f}")

            # Regra 1: Pausar CPA alto
            rule = OPTIMIZATION_RULES["pause_high_cpa"]
            if ad_set["cpa"] > 0 and ad_set["cpa"] > rule["threshold"]:
                action = {
                    "ad_set_id": ad_set["id"],
                    "ad_set_name": ad_set["name"],
                    "rule": "pause_high_cpa",
                    "reason": f"CPA R${ad_set['cpa']:.2f} > limite R${rule['threshold']:.2f}",
                    "action": "PAUSE",
                }
                actions_taken.append(action)
                self._log_action("WARNING", f"  ⛔ CPA ALTO: R${ad_set['cpa']:.2f} → PAUSAR")

                if not dry_run:
                    self.client.update_ad_set_status(ad_set["id"], "PAUSED")
                    self._log_action("ACTION", f"  Ad Set pausado: {ad_set['id']}")

            # Regra 2: Aumentar budget de winners
            rule = OPTIMIZATION_RULES["increase_budget_winners"]
            if (
                ad_set["cpa"] > 0
                and ad_set["cpa"] < rule["threshold"]
                and ad_set["conversions"] >= rule["min_results"]
            ):
                new_budget = int(ad_set["daily_budget"] * (1 + rule["increase_pct"] / 100))
                action = {
                    "ad_set_id": ad_set["id"],
                    "ad_set_name": ad_set["name"],
                    "rule": "increase_budget_winners",
                    "reason": f"CPA R${ad_set['cpa']:.2f} < R${rule['threshold']:.2f} com {ad_set['conversions']} conversões",
                    "action": f"INCREASE_BUDGET → R${new_budget/100:.2f}/dia",
                }
                actions_taken.append(action)
                self._log_action("INFO", f"  🏆 WINNER: CPA baixo + conversões → Aumentar budget +{rule['increase_pct']}%")

                if not dry_run:
                    self.client.update_ad_set_budget(ad_set["id"], new_budget)
                    self._log_action("ACTION", f"  Budget atualizado: R${new_budget/100:.2f}/dia")

            # Regra 3: Pausar CTR baixo
            rule = OPTIMIZATION_RULES["pause_low_ctr"]
            if (
                ad_set["impressions"] >= rule["min_impressions"]
                and ad_set["ctr"] < rule["threshold"]
            ):
                action = {
                    "ad_set_id": ad_set["id"],
                    "ad_set_name": ad_set["name"],
                    "rule": "pause_low_ctr",
                    "reason": f"CTR {ad_set['ctr']:.2f}% < mínimo {rule['threshold']}% ({ad_set['impressions']} impressões)",
                    "action": "PAUSE",
                }
                actions_taken.append(action)
                self._log_action("WARNING", f"  ⛔ CTR BAIXO: {ad_set['ctr']:.2f}% → PAUSAR")

                if not dry_run:
                    self.client.update_ad_set_status(ad_set["id"], "PAUSED")
                    self._log_action("ACTION", f"  Ad Set pausado: {ad_set['id']}")

        # Resumo
        self._log_action("INFO", f"=== Otimização finalizada ===")
        self._log_action("INFO", f"Ad Sets analisados: {len(ad_sets)}")
        self._log_action("INFO", f"Ações {'sugeridas' if dry_run else 'executadas'}: {len(actions_taken)}")

        return {
            "timestamp": datetime.now().isoformat(),
            "mode": "dry_run" if dry_run else "live",
            "ad_sets_analyzed": len(ad_sets),
            "actions": actions_taken,
        }

    def generate_report(self, date_preset: str = "last_7d") -> str:
        """
        Gera relatório de performance em texto formatado.
        """
        ad_sets = self.analyze_ad_sets(date_preset)

        if not ad_sets:
            return "Nenhum ad set ativo encontrado."

        # Métricas agregadas
        total_spend = sum(s["spend"] for s in ad_sets)
        total_clicks = sum(s["clicks"] for s in ad_sets)
        total_impressions = sum(s["impressions"] for s in ad_sets)
        total_conversions = sum(s["conversions"] for s in ad_sets)
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        avg_cpa = (total_spend / total_conversions) if total_conversions > 0 else 0

        report = []
        report.append("=" * 60)
        report.append(f"📊 RELATÓRIO A7 LAVANDERIA - Facebook Ads")
        report.append(f"📅 Período: {date_preset}")
        report.append(f"🕐 Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        report.append("=" * 60)
        report.append("")
        report.append("RESUMO GERAL:")
        report.append(f"  💰 Investimento total: R$ {total_spend:.2f}")
        report.append(f"  👁️ Impressões: {total_impressions:,}")
        report.append(f"  🖱️ Cliques: {total_clicks:,}")
        report.append(f"  📈 CTR médio: {avg_ctr:.2f}%")
        report.append(f"  🎯 Conversões: {total_conversions}")
        report.append(f"  💵 CPA médio: R$ {avg_cpa:.2f}")
        report.append("")
        report.append("_" * 60)
        report.append("DETALHAMENTO POR AD SET:")
        report.append("-" * 60)

        # Ordena por CPA (melhor primeiro)
        sorted_sets = sorted(ad_sets, key=lambda x: x["cpa"] if x["cpa"] > 0 else float("inf"))

        for i, ad_set in enumerate(sorted_sets, 1):
            status = "🟢" if ad_set["cpa"] > 0 and ad_set["cpa"] < 30 else "🔴" if ad_set["cpa"] > 0 else "⚪"
            report.append(f"\n{status} {i}. {ad_set['name']}")
            report.append(f"   Gasto: R${ad_set['spend']:.2f} | Impressões: {ad_set['impressions']:,}")
            report.append(f"   Cliques: {ad_set['clicks']:,} | CTR: {ad_set['ctr']:.2f}%")
            report.append(f"   Conversões: {ad_set['conversions']} | CPA: R${ad_set['cpa']:.2f}")

        report.append("\n" + "=" * 60)
        return "\n".join(report)


# ==============================================================
# EXECUÇÃO DIRETA
# ==============================================================
if __name__ == "__main__":
    optimizer = CampaignOptimizer()

    # 1. Gera relatório
    print(optimizer.generate_report("last_7d"))

    # 2. Roda otimização em modo simulação
    print("\n\n")
    result = optimizer.run_optimization(dry_run=True)

    print(f"\n🔷 Ações sugeridas:")
    for action in result["actions"]:
        print(f"  - {action['ad_set_name']}: {action['action']} ({action['reason']})")

    # Para executar de verdade, descomente:
    # result = optimizer.run_optimization(dry_run=False)
