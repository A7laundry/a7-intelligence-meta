"""
A7 Lavanderia - Facebook Ads Automation
Agendador de Otimizações
Roda otimizações em intervalos definidos (cron job ou loop).
Integrado com sistema de alertas.
"""

import time
import json
import sys
from datetime import datetime
from optimizer import CampaignOptimizer


class OptimizationScheduler:
    """Agenda e executa otimizações automaticamente."""

    def __init__(self, interval_minutes: int = 360, dry_run: bool = True):
        """
        Args:
            interval_minutes: Intervalo entre execuções em minutos (padrão: 6 horas)
            dry_run: Se True, apenas simula (padrão: True por segurança)
        """
        self.interval_minutes = interval_minutes
        self.dry_run = dry_run
        self.optimizer = CampaignOptimizer()
        self.alert_manager = None
        self.history = []
        self._init_alerts()

    def _init_alerts(self):
        """Inicializa sistema de alertas se configurado."""
        try:
            from config import ALERT_CONFIG
            if ALERT_CONFIG.get("enabled", False):
                from alerts import AlertManager
                self.alert_manager = AlertManager(ALERT_CONFIG)
                print("✅ Sistema de alertas ativo")
        except (ImportError, AttributeError):
            pass  # ALERT_CONFIG não definido — alertas desativados

    def run_once(self) -> dict:
        """Executa uma única rodada de otimização + alertas."""
        print(f"\n{'=' * 60}")
        print(f"⏰ Execução: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"   Modo: {'SIMULAÇÃO' if self.dry_run else 'EXECUÇÃO'}")
        print(f"{'=' * 60}")

        try:
            result = self.optimizer.run_optimization(dry_run=self.dry_run)
            self.history.append(result)

            # Salva log em arquivo
            log_file = f"optimization_log_{datetime.now().strftime('%Y%m%d')}.json"
            with open(log_file, "a") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

            print(f"\n📝 Log salvo em: {log_file}")

            # Sistema de alertas
            if self.alert_manager:
                self._run_alerts()

            return result

        except Exception as e:
            print(f"\n❌ Erro na otimização: {e}")
            return {"error": str(e), "timestamp": datetime.now().isoformat()}

    def _run_alerts(self):
        """Executa verificação de alertas e envia notificações."""
        try:
            ad_sets_data = self.optimizer.analyze_ad_sets()

            # Verificar alertas
            alerts = self.alert_manager.check_metrics(ad_sets_data)
            if alerts:
                print(f"\n🔔 {len(alerts)} alerta(s) detectado(s):")
                self.alert_manager.send_alerts(alerts)
            else:
                print(f"\n✅ Sem alertas — métricas dentro dos limites")

            # Sumário diário
            try:
                from config import ALERT_CONFIG
                if ALERT_CONFIG.get("daily_summary", False):
                    summary = self.alert_manager.generate_daily_summary(ad_sets_data)
                    self.alert_manager.send_summary(summary)
            except (ImportError, AttributeError):
                pass

        except Exception as e:
            print(f"⚠️ Erro no sistema de alertas: {e}")

    def run_loop(self):
        """Executa em loop contínuo com intervalo definido."""
        print(f"\n🔄 Iniciando scheduler em loop")
        print(f"   Intervalo: {self.interval_minutes} minutos")
        print(f"   Modo: {'SIMULAÇÃO' if self.dry_run else 'EXECUÇÃO'}")
        print(f"   Alertas: {'ATIVO' if self.alert_manager else 'DESATIVADO'}")
        print(f"   Pressione Ctrl+C para parar\n")

        while True:
            try:
                self.run_once()

                next_run = datetime.now().strftime('%H:%M')
                minutes = self.interval_minutes
                hours = minutes // 60
                mins = minutes % 60
                interval_str = f"{hours}h{mins:02d}min" if hours else f"{mins}min"
                print(f"\n⏳ Próxima execução em {interval_str}...")

                time.sleep(self.interval_minutes * 60)

            except KeyboardInterrupt:
                print(f"\n\n🛑 Scheduler parado pelo usuário.")
                print(f"   Total de execuções: {len(self.history)}")
                break

    def get_summary(self) -> str:
        """Retorna resumo de todas as execuções."""
        if not self.history:
            return "Nenhuma execução registrada."

        total_actions = sum(len(h.get("actions", [])) for h in self.history)
        total_analyzed = sum(h.get("ad_sets_analyzed", 0) for h in self.history)

        summary = []
        summary.append(f"\n📊 RESUMO DO SCHEDULER")
        summary.append(f"   Execuções: {len(self.history)}")
        summary.append(f"   Ad Sets analisados (total): {total_analyzed}")
        summary.append(f"   Ações tomadas (total): {total_actions}")
        summary.append(f"   Primeira execução: {self.history[0].get('timestamp', 'N/A')}")
        summary.append(f"   Última execução: {self.history[-1].get('timestamp', 'N/A')}")

        return "\n".join(summary)


def main():
    """Ponto de entrada do scheduler."""
    print("=" * 60)
    print("  A7 LAVANDERIA - Scheduler de Otimização")
    print("=" * 60)

    # Configuração via argumentos
    dry_run = True
    interval = 360  # 6 horas padrão

    if "--live" in sys.argv:
        dry_run = False
        print("⚠️  MODO EXECUÇÃO ATIVO - Alterações serão aplicadas!")

    if "--interval" in sys.argv:
        idx = sys.argv.index("--interval")
        if idx + 1 < len(sys.argv):
            interval = int(sys.argv[idx + 1])

    if "--once" in sys.argv:
        # Executa apenas uma vez (ideal para cron)
        scheduler = OptimizationScheduler(dry_run=dry_run)
        scheduler.run_once()
    else:
        # Executa em loop contínuo
        scheduler = OptimizationScheduler(
            interval_minutes=interval,
            dry_run=dry_run,
        )
        scheduler.run_loop()
        print(scheduler.get_summary())


if __name__ == "__main__":
    main()
