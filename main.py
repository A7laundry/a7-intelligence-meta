"""
A7 Lavanderia - Facebook Ads Automation
CLI Principal - Interface de linha de comando interativa para gerenciar campanhas
"""

import sys
import json
from meta_client import MetaAdsClient
from optimizer import CampaignOptimizer
from config import CAMPAIGN_TEMPLATES, AUDIENCES, AD_COPY_TEMPLATES


def print_header():
    print("\n" + "=" * 60)
    print("  A7 LAVANDERIA - Facebook Ads Automation")
    print("  Meta Marketing API v21.0")
    print("=" * 60)


def print_menu():
    print("\n📋 MENU PRINCIPAL:")
    print("-" * 40)
    print("  1. Criar campanha completa")
    print("  2. Listar campanhas")
    print("  3. Listar ad sets")
    print("  4. Ativar/Pausar campanha")
    print("  5. Relatório de performance")
    print("  6. Rodar otimização (simulação)")
    print("  7. Rodar otimização (execução)")
    print("  8. Upload de imagem")
    print("  9. Upload de vídeo")
    print(" 10. Criar audiência customizada")
    print(" 11. Criar audiência lookalike")
    print("  0. Sair")
    print("-" * 40)


def select_from_dict(options: dict, label: str) -> str:
    """Exibe opções de um dicionário e retorna a chave selecionada."""
    keys = list(options.keys())
    print(f"\n{label}:")
    for i, key in enumerate(keys, 1):
        item = options[key]
        name = item.get("name", item.get("headline", key))
        print(f"  {i}. {name}")

    while True:
        try:
            choice = int(input("\nEscolha: ")) - 1
            if 0 <= choice < len(keys):
                return keys[choice]
            print("Opção inválida.")
        except ValueError:
            print("Digite um número válido.")


def cmd_create_full_campaign(client: MetaAdsClient):
    """Cria uma campanha completa via CLI."""
    print("\n🚀 CRIAR CAMPANHA COMPLETA")
    print("=" * 40)

    template_key = select_from_dict(CAMPAIGN_TEMPLATES, "Templates de campanha")
    audience_key = select_from_dict(AUDIENCES, "Público-alvo")
    copy_key = select_from_dict(AD_COPY_TEMPLATES, "Template de copy")

    image_path = input("\nCaminho da imagem (Enter para pular): ").strip() or None
    video_path = input("Caminho do vídeo (Enter para pular): ").strip() or None
    name_suffix = input("Sufixo para o nome (Enter para pular): ").strip() or ""

    print("\n📋 Resumo:")
    print(f"  Template:  {CAMPAIGN_TEMPLATES[template_key]['name']}")
    print(f"  Público:   {AUDIENCES[audience_key]['name']}")
    print(f"  Copy:      {AD_COPY_TEMPLATES[copy_key]['headline']}")
    print(f"  Budget:    R$ {CAMPAIGN_TEMPLATES[template_key]['daily_budget_cents']/100:.2f}/dia")

    confirm = input("\nConfirmar criação? (s/n): ").strip().lower()
    if confirm == "s":
        result = client.create_full_campaign(
            template_key=template_key,
            audience_key=audience_key,
            copy_key=copy_key,
            image_path=image_path,
            video_path=video_path,
            name_suffix=name_suffix,
        )
        return result
    else:
        print("Operação cancelada.")
        return None


def cmd_list_campaigns(client: MetaAdsClient):
    """Lista campanhas da conta."""
    print("\n📋 CAMPANHAS DA CONTA")
    print("=" * 40)

    filter_choice = input("Filtrar por status (ACTIVE/PAUSED/all): ").strip().upper()
    status_filter = filter_choice if filter_choice in ("ACTIVE", "PAUSED") else None

    campaigns = client.list_campaigns(status_filter)

    if not campaigns:
        print("Nenhuma campanha encontrada.")
        return

    for i, camp in enumerate(campaigns, 1):
        status_icon = "🟢" if camp["status"] == "ACTIVE" else "⏸️" if camp["status"] == "PAUSED" else "📦"
        print(f"\n{status_icon} {i}. {camp['name']}")
        print(f"   ID: {camp['id']}")
        print(f"   Objetivo: {camp.get('objective', 'N/A')}")
        print(f"   Status: {camp['status']}")


def cmd_list_ad_sets(client: MetaAdsClient):
    """Lista ad sets."""
    print("\n📋 AD SETS")
    print("=" * 40)

    campaign_id = input("ID da campanha (Enter para todos): ").strip() or None
    ad_sets = client.list_ad_sets(campaign_id)

    if not ad_sets:
        print("Nenhum ad set encontrado.")
        return

    for i, ad_set in enumerate(ad_sets, 1):
        status_icon = "🟢" if ad_set["status"] == "ACTIVE" else "⏸️"
        budget = int(ad_set.get("daily_budget", 0)) / 100
        print(f"\n{status_icon} {i}. {ad_set['name']}")
        print(f"   ID: {ad_set['id']}")
        print(f"   Status: {ad_set['status']} | Budget: R$ {budget:.2f}/dia")


def cmd_toggle_campaign(client: MetaAdsClient):
    """Ativa ou pausa uma campanha."""
    print("\n🔄 ATIVAR/PAUSAR CAMPANHA")
    print("=" * 40)

    campaign_id = input("ID da campanha: ").strip()
    if not campaign_id:
        print("ID obrigatório.")
        return

    print("  1. ACTIVE (ativar)")
    print("  2. PAUSED (pausar)")
    print("  3. ARCHIVED (arquivar)")

    choice = input("Escolha: ").strip()
    status_map = {"1": "ACTIVE", "2": "PAUSED", "3": "ARCHIVED"}
    status = status_map.get(choice)

    if status:
        confirm = input(f"Confirmar {status} para {campaign_id}? (s/n): ").strip().lower()
        if confirm == "s":
            client.update_campaign_status(campaign_id, status)
        else:
            print("Operação cancelada.")
    else:
        print("Opção inválida.")


def cmd_report(optimizer: CampaignOptimizer):
    """Gera relatório de performance."""
    print("\n📊 RELATÓRIO DE PERFORMANCE")
    print("=" * 40)

    print("Período:")
    print("  1. Hoje")
    print("  2. Ontem")
    print("  3. Últimos 7 dias")
    print("  4. Últimos 30 dias")

    choice = input("Escolha: ").strip()
    preset_map = {"1": "today", "2": "yesterday", "3": "last_7d", "4": "last_30d"}
    date_preset = preset_map.get(choice, "last_7d")

    report = optimizer.generate_report(date_preset)
    print(report)


def cmd_optimize(optimizer: CampaignOptimizer, dry_run: bool = True):
    """Roda otimização."""
    mode = "SIMULAÇÃO" if dry_run else "EXECUÇÃO"
    print(f"\n🔧 OTIMIZAÇÃO - {mode}")
    print("=" * 40)

    if not dry_run:
        confirm = input("⚠️  Isso vai modificar campanhas reais. Continuar? (s/n): ").strip().lower()
        if confirm != "s":
            print("Operação cancelada.")
            return

    result = optimizer.run_optimization(dry_run=dry_run)

    print(f"\n📋 Resumo:")
    print(f"  Ad Sets analisados: {result['ad_sets_analyzed']}")
    print(f"  Ações {'sugeridas' if dry_run else 'executadas'}: {len(result['actions'])}")

    if result["actions"]:
        print(f"\n🔷 Detalhes:")
        for action in result["actions"]:
            print(f"  - {action['ad_set_name']}: {action['action']} ({action['reason']})")


def cmd_upload_image(client: MetaAdsClient):
    """Upload de imagem."""
    path = input("\nCaminho da imagem: ").strip()
    if path:
        image_hash = client.upload_image(path)
        print(f"\n✅ Image hash: {image_hash}")
        print("Use este hash ao criar anúncios.")


def cmd_upload_video(client: MetaAdsClient):
    """Upload de vídeo."""
    path = input("\nCaminho do vídeo: ").strip()
    if path:
        title = input("Título do vídeo: ").strip() or "A7 Video Ad"
        video_id = client.upload_video(path, title)
        print(f"\n✅ Video ID: {video_id}")
        print("Use este ID ao criar anúncios.")


def cmd_create_custom_audience(client: MetaAdsClient):
    """Cria audiência customizada."""
    print("\n👥 CRIAR AUDIÊNCIA CUSTOMIZADA")
    print("=" * 40)

    name = input("Nome da audiência: ").strip()
    description = input("Descrição: ").strip()
    retention = input("Dias de retenção (padrão 30): ").strip()
    retention_days = int(retention) if retention else 30

    client.create_custom_audience_website(name, description, retention_days)


def cmd_create_lookalike(client: MetaAdsClient):
    """Cria audiência lookalike."""
    print("\n👥 CRIAR AUDIÊNCIA LOOKALIKE")
    print("=" * 40)

    source_id = input("ID da audiência fonte: ").strip()
    country = input("País (padrão BR): ").strip() or "BR"
    ratio = input("Ratio % (padrão 0.02 = 2%): ").strip()
    ratio_val = float(ratio) if ratio else 0.02

    client.create_lookalike_audience(source_id, country, ratio_val)


def main():
    """Loop principal do CLI."""
    # Comandos de linha de comando diretos
    if "--check-token" in sys.argv:
        client = MetaAdsClient()
        client.check_token_validity()
        return

    if "--refresh-token" in sys.argv:
        client = MetaAdsClient()
        client.refresh_long_lived_token()
        return

    print_header()

    client = MetaAdsClient()
    optimizer = CampaignOptimizer()

    # Verificação de token na inicialização
    client.check_token_validity()

    while True:
        print_menu()
        choice = input("\n👉 Escolha uma opção: ").strip()

        try:
            if choice == "1":
                cmd_create_full_campaign(client)
            elif choice == "2":
                cmd_list_campaigns(client)
            elif choice == "3":
                cmd_list_ad_sets(client)
            elif choice == "4":
                cmd_toggle_campaign(client)
            elif choice == "5":
                cmd_report(optimizer)
            elif choice == "6":
                cmd_optimize(optimizer, dry_run=True)
            elif choice == "7":
                cmd_optimize(optimizer, dry_run=False)
            elif choice == "8":
                cmd_upload_image(client)
            elif choice == "9":
                cmd_upload_video(client)
            elif choice == "10":
                cmd_create_custom_audience(client)
            elif choice == "11":
                cmd_create_lookalike(client)
            elif choice == "0":
                print("\n👋 Até logo! A7 Intelligence")
                sys.exit(0)
            else:
                print("❌ Opção inválida. Tente novamente.")
        except KeyboardInterrupt:
            print("\n\n👋 Até logo! A7 Intelligence")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Erro: {e}")
            print("Verifique suas credenciais e tente novamente.")


if __name__ == "__main__":
    main()
