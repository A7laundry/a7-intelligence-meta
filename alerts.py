"""
A7 Lavanderia - Sistema de Alertas
Monitora métricas e envia notificações quando thresholds são ultrapassados.
"""

import json
import os
import requests
from datetime import datetime, timedelta


ALERTS_LOG_FILE = "alerts_sent.json"


class AlertManager:
    """Gerencia alertas baseado em métricas de campanhas."""

    def __init__(self, alert_config: dict):
        """
        Args:
            alert_config: Configuração de alertas do config.py (ALERT_CONFIG)
        """
        self.config = alert_config
        self.enabled = alert_config.get("enabled", False)
        self.sent_alerts = self._load_sent_alerts()

    def _load_sent_alerts(self) -> dict:
        """Carrega log de alertas enviados (para deduplicação)."""
        if os.path.exists(ALERTS_LOG_FILE):
            try:
                with open(ALERTS_LOG_FILE) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_sent_alerts(self):
        """Salva log de alertas enviados."""
        with open(ALERTS_LOG_FILE, "w") as f:
            json.dump(self.sent_alerts, f, indent=2)

    def _is_duplicate(self, alert_key: str, cooldown_hours: int = 24) -> bool:
        """Verifica se alerta já foi enviado dentro do período de cooldown."""
        last_sent = self.sent_alerts.get(alert_key)
        if not last_sent:
            return False

        last_time = datetime.fromisoformat(last_sent)
        return datetime.now() - last_time < timedelta(hours=cooldown_hours)

    def _mark_sent(self, alert_key: str):
        """Marca alerta como enviado."""
        self.sent_alerts[alert_key] = datetime.now().isoformat()
        self._save_sent_alerts()

    def check_metrics(self, ad_sets_data: list) -> list:
        """
        Analisa métricas e gera lista de alertas.

        Args:
            ad_sets_data: Lista de ad sets com métricas (do optimizer.analyze_ad_sets())

        Returns:
            Lista de alertas gerados
        """
        if not self.enabled:
            return []

        alerts = []
        thresholds = self.config.get("thresholds", {})

        for ad_set in ad_sets_data:
            ad_set_id = ad_set.get("id", "unknown")
            ad_set_name = ad_set.get("name", "Unknown")

            # Alerta: CPA alto
            cpa_max = thresholds.get("cpa_max", 50.0)
            if ad_set.get("cpa", 0) > cpa_max:
                alert_key = f"high_cpa_{ad_set_id}"
                if not self._is_duplicate(alert_key):
                    alerts.append({
                        "type": "HIGH_CPA",
                        "severity": "WARNING",
                        "ad_set_id": ad_set_id,
                        "ad_set_name": ad_set_name,
                        "message": f"CPA de R${ad_set['cpa']:.2f} ultrapassou limite de R${cpa_max:.2f}",
                        "value": ad_set["cpa"],
                        "threshold": cpa_max,
                    })
                    self._mark_sent(alert_key)

            # Alerta: CTR baixo
            ctr_min = thresholds.get("ctr_min", 0.5)
            min_impressions = thresholds.get("min_impressions_for_ctr", 1000)
            if (
                ad_set.get("impressions", 0) >= min_impressions
                and ad_set.get("ctr", 0) < ctr_min
                and ad_set.get("ctr", 0) > 0
            ):
                alert_key = f"low_ctr_{ad_set_id}"
                if not self._is_duplicate(alert_key):
                    alerts.append({
                        "type": "LOW_CTR",
                        "severity": "WARNING",
                        "ad_set_id": ad_set_id,
                        "ad_set_name": ad_set_name,
                        "message": f"CTR de {ad_set['ctr']:.2f}% abaixo do mínimo de {ctr_min}%",
                        "value": ad_set["ctr"],
                        "threshold": ctr_min,
                    })
                    self._mark_sent(alert_key)

            # Alerta: Gasto alto sem conversões
            spend_no_conv = thresholds.get("spend_without_conversions", 100.0)
            if ad_set.get("spend", 0) >= spend_no_conv and ad_set.get("conversions", 0) == 0:
                alert_key = f"no_conv_{ad_set_id}"
                if not self._is_duplicate(alert_key):
                    alerts.append({
                        "type": "NO_CONVERSIONS",
                        "severity": "CRITICAL",
                        "ad_set_id": ad_set_id,
                        "ad_set_name": ad_set_name,
                        "message": f"R${ad_set['spend']:.2f} gastos sem nenhuma conversão",
                        "value": ad_set["spend"],
                        "threshold": spend_no_conv,
                    })
                    self._mark_sent(alert_key)

        return alerts

    def generate_daily_summary(self, ad_sets_data: list) -> str:
        """
        Gera sumário diário com KPIs principais.

        Returns:
            Texto formatado do sumário
        """
        if not ad_sets_data:
            return "Nenhum ad set ativo encontrado."

        total_spend = sum(s.get("spend", 0) for s in ad_sets_data)
        total_conversions = sum(s.get("conversions", 0) for s in ad_sets_data)
        total_clicks = sum(s.get("clicks", 0) for s in ad_sets_data)
        total_impressions = sum(s.get("impressions", 0) for s in ad_sets_data)
        avg_cpa = total_spend / total_conversions if total_conversions > 0 else 0
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0

        summary = (
            f"📊 A7 Daily Summary — {datetime.now().strftime('%d/%m/%Y')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Spend: R${total_spend:.2f}\n"
            f"🎯 Conversions: {total_conversions}\n"
            f"💵 CPA: R${avg_cpa:.2f}\n"
            f"📈 CTR: {avg_ctr:.2f}%\n"
            f"🖱️ Clicks: {total_clicks}\n"
            f"👁️ Impressions: {total_impressions:,}\n"
            f"📋 Active Ad Sets: {len(ad_sets_data)}"
        )

        return summary

    def send_alerts(self, alerts: list):
        """
        Envia alertas via canal configurado.
        Suporta: console, webhook (WhatsApp/Slack/etc).
        """
        channel = self.config.get("channel", "console")

        for alert in alerts:
            severity_icon = "🔴" if alert["severity"] == "CRITICAL" else "⚠️"
            message = f"{severity_icon} [{alert['type']}] {alert['ad_set_name']}: {alert['message']}"

            if channel == "console":
                print(message)

            elif channel == "webhook":
                webhook_url = self.config.get("webhook_url", "")
                if webhook_url:
                    self._send_webhook(webhook_url, message)

    def send_summary(self, summary: str):
        """Envia sumário diário via canal configurado."""
        channel = self.config.get("channel", "console")

        if channel == "console":
            print(summary)
        elif channel == "webhook":
            webhook_url = self.config.get("webhook_url", "")
            if webhook_url:
                self._send_webhook(webhook_url, summary)

    def _send_webhook(self, url: str, message: str):
        """Envia mensagem via webhook genérico (compatível com Slack, Discord, n8n)."""
        try:
            payload = {"text": message, "content": message}
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"✅ Alerta enviado via webhook")
            else:
                print(f"⚠️ Webhook retornou {response.status_code}")
        except Exception as e:
            print(f"❌ Erro ao enviar webhook: {e}")
