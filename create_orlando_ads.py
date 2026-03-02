"""
A7 Orlando Campaigns — Create all ads with creatives.
Run after Meta app is in LIVE mode.

Usage: python3 create_orlando_ads.py
       python3 create_orlando_ads.py --dry-run   (preview only)
"""
import sys
from meta_client import MetaAdsClient
from config import META_CONFIG

client = MetaAdsClient()
dry_run = "--dry-run" in sys.argv

# Image hashes (already uploaded to Meta)
IMAGES = {
    "laundry_hero":      "2449832e5c38d7894c0173eac4a6126b",
    "laundry_lifestyle": "5a339c4b9642d7e9169618dc21413485",
    "laundry_family":    "cc4ebceb1cb8b03b3a46cdb51089b2d5",
    "carpet_home":       "20be6db2314c2175398435815a427250",
    "vacation_rental":   "6cad83bf5b9ef750fc371d545c67ef14",
    "carpet_pets":       "9ed78645ed21cfadb44ceb6e97ebc44f",
}

# ============================================================
# AD PLAN: 3 variations (A/B/C) per ad set = 15 ads total
# ============================================================
ADS = [
    # --- CAMPAIGN: Laundry Service ---
    # Ad Set: Vacation Rental - Laundry (120241319187480052)
    {
        "ad_set_id": "120241319187480052",
        "name": "Rental Laundry A — Professional Service",
        "image": IMAGES["vacation_rental"],
        "headline": "Professional Laundry for Vacation Rentals",
        "primary_text": "Keep your Airbnb spotless between guests! A7 Laundry offers fast turnaround for vacation rental owners in Orlando. Free pickup & delivery.",
        "description": "Fast Turnaround • Free Pickup • Orlando FL",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com",
    },
    {
        "ad_set_id": "120241319187480052",
        "name": "Rental Laundry B — First Clean FREE",
        "image": IMAGES["laundry_hero"],
        "headline": "First Laundry Clean FREE for Rentals",
        "primary_text": "Vacation rental owners: your first laundry turnover is FREE! A7 handles sheets, towels & linens. Same-day service in Orlando. Recurring discounts up to 30% off.",
        "description": "First Clean FREE • Same-Day • Orlando FL",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com",
    },
    {
        "ad_set_id": "120241319187480052",
        "name": "Rental Laundry C — Save 30%",
        "image": IMAGES["laundry_lifestyle"],
        "headline": "Save 30% on Recurring Laundry Service",
        "primary_text": "Stop stressing about turnovers. A7 Laundry picks up, washes, folds & delivers for your rental property. Up to 30% off recurring plans. Orlando's most trusted laundry.",
        "description": "Up to 30% OFF • 4.9 Stars • Orlando FL",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com",
    },

    # Ad Set: Families 28-55 - Laundry (120241319187200052)
    {
        "ad_set_id": "120241319187200052",
        "name": "Family Laundry A — Stop Wasting Weekends",
        "image": IMAGES["laundry_family"],
        "headline": "Stop Wasting Weekends on Laundry",
        "primary_text": "Get 5+ hours back every week! A7 Laundry picks up, washes, folds & delivers — starting at just $1.99/day. Buy 1 bag, get 1 FREE on your first order.",
        "description": "From $59.90/mo • Free Pickup & Delivery",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com",
    },
    {
        "ad_set_id": "120241319187200052",
        "name": "Family Laundry B — Buy 1 Get 1 FREE",
        "image": IMAGES["laundry_hero"],
        "headline": "Buy 1 Bag, Get 1 FREE",
        "primary_text": "Tired of spending your weekends doing laundry? A7 Laundry does it for you! We pick up, wash, fold & deliver. Hotel-fresh results guaranteed. First order: Buy 1 bag, get 1 FREE!",
        "description": "4.9 Google Rating • 2,000+ Families • Orlando FL",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com",
    },
    {
        "ad_set_id": "120241319187200052",
        "name": "Family Laundry C — Less Than Netflix",
        "image": IMAGES["laundry_lifestyle"],
        "headline": "Less Than Netflix — $1.99/day",
        "primary_text": "Your daily coffee costs more than our laundry service. Plans from $1.99/day. Free pickup & delivery. No contracts. Join 2,000+ Orlando families.",
        "description": "No Contracts • Free Delivery • Orlando FL",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com",
    },

    # --- CAMPAIGN: Carpet Cleaning ---
    # Ad Set: Homeowners - Carpet (120241319187870052)
    {
        "ad_set_id": "120241319187870052",
        "name": "Carpet Home A — 3 Rooms $107",
        "image": IMAGES["carpet_home"],
        "headline": "3 Rooms Carpet Cleaning — $107",
        "primary_text": "Deep carpet cleaning with hot-water extraction at 200°F — eliminates 99.9% of bacteria! Safe for kids & pets. Save $28 when you book 3 rooms. Same-day service available in Orlando.",
        "description": "From $45/room • Eco-Friendly • Satisfaction Guaranteed",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com/carpet-cleaning.html",
    },
    {
        "ad_set_id": "120241319187870052",
        "name": "Carpet Home B — 99.9% Bacteria Free",
        "image": IMAGES["laundry_hero"],
        "headline": "99.9% Bacteria Eliminated",
        "primary_text": "Hot-water extraction at 200°F goes deep into carpet fibers. Eco-friendly, safe for kids & pets. Book 3 rooms for just $107. Same-day service in Orlando.",
        "description": "Hot-Water 200°F • Same-Day • Orlando FL",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com/carpet-cleaning.html",
    },
    {
        "ad_set_id": "120241319187870052",
        "name": "Carpet Home C — Same-Day Service",
        "image": IMAGES["carpet_home"],
        "headline": "Same-Day Carpet Cleaning — Orlando",
        "primary_text": "Need your carpets cleaned today? A7 offers same-day deep cleaning service. 200°F hot-water extraction kills 99.9% of bacteria. From $45/room. 100% satisfaction guaranteed.",
        "description": "Same-Day Available • From $45/room • 4.9 Stars",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com/carpet-cleaning.html",
    },

    # Ad Set: Pet Owners - Carpet (120241319188390052)
    {
        "ad_set_id": "120241319188390052",
        "name": "Carpet Pets A — Pet Stains Fixed",
        "image": IMAGES["carpet_pets"],
        "headline": "Pet Stains & Odors? We Fix That",
        "primary_text": "Our enzyme-based pet treatment goes deep into carpet fibers to eliminate stains and odors for good. Hot-water extraction at 200°F kills 99.9% of bacteria. Safe for your furry friends! 3 rooms for just $107.",
        "description": "Pet Treatment +$25/room • Eco-Friendly • Same-Day",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com/carpet-cleaning.html",
    },
    {
        "ad_set_id": "120241319188390052",
        "name": "Carpet Pets B — Safe for Pets",
        "image": IMAGES["carpet_pets"],
        "headline": "Deep Clean That's Safe for Pets",
        "primary_text": "Eco-friendly carpet cleaning that eliminates pet stains, odors, and 99.9% of bacteria. Your pets can walk on it the same day! Enzyme-based treatment. 3 rooms from $107 in Orlando.",
        "description": "Eco-Friendly • Pet-Safe • Same-Day Ready",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com/carpet-cleaning.html",
    },
    {
        "ad_set_id": "120241319188390052",
        "name": "Carpet Pets C — 3 Rooms $107",
        "image": IMAGES["carpet_home"],
        "headline": "3 Rooms + Pet Treatment — $107",
        "primary_text": "Pet owners love A7! Our enzyme-based deep clean removes the toughest stains and odors. Hot-water extraction at 200°F. Book 3 rooms for $107 + pet treatment. Orlando's top-rated carpet cleaning.",
        "description": "4.9 Stars • 100% Satisfaction • Orlando FL",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com/carpet-cleaning.html",
    },

    # --- CAMPAIGN: Vacation Rental Turnover ---
    # Ad Set: Airbnb Hosts - Turnover (120241319188650052)
    {
        "ad_set_id": "120241319188650052",
        "name": "Turnover A — Turnover Cleaning",
        "image": IMAGES["vacation_rental"],
        "headline": "Vacation Rental Turnover Cleaning",
        "primary_text": "Keep your Airbnb spotless between guests! A7 offers same-day laundry & carpet cleaning for vacation rental owners in Orlando. First clean FREE. Recurring discounts up to 30% off.",
        "description": "Same-Day Service • First Clean FREE • Orlando FL",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com",
    },
    {
        "ad_set_id": "120241319188650052",
        "name": "Turnover B — First Clean FREE",
        "image": IMAGES["laundry_hero"],
        "headline": "First Turnover Clean FREE",
        "primary_text": "Airbnb & VRBO hosts: your first turnover cleaning is on us! Laundry, carpet, deep clean — all handled. Same-day service. Recurring plans up to 30% off. Orlando, Kissimmee, Winter Park.",
        "description": "Laundry + Carpet + Deep Clean • Orlando FL",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com",
    },
    {
        "ad_set_id": "120241319188650052",
        "name": "Turnover C — 5-Star Reviews",
        "image": IMAGES["vacation_rental"],
        "headline": "Get 5-Star Reviews Every Time",
        "primary_text": "Guests notice clean. A7 handles full turnover: laundry, carpet, linens — same-day. 4.9-star rated. First clean FREE. Serving Orlando, Kissimmee, Winter Park, Dr. Phillips, Lake Nona.",
        "description": "4.9 Stars • Same-Day • Serving All Orlando",
        "cta": "MESSAGE_PAGE",
        "link": "https://a7laundry.com",
    },
]


def create_ad(ad_config):
    """Create a single ad via Meta API."""
    import requests, json

    # Step 1: Create creative
    creative_payload = {
        "name": f"Creative - {ad_config['name']}",
        "object_story_spec": json.dumps({
            "page_id": META_CONFIG["page_id"],
            "link_data": {
                "message": ad_config["primary_text"],
                "link": ad_config["link"],
                "name": ad_config["headline"],
                "description": ad_config["description"],
                "call_to_action": {
                    "type": ad_config["cta"],
                    "value": {"link": ad_config["link"]},
                },
                "image_hash": ad_config["image"],
            },
        }),
        "access_token": META_CONFIG["access_token"],
    }

    r = requests.post(
        f"https://graph.facebook.com/v21.0/{META_CONFIG['ad_account_id']}/adcreatives",
        data=creative_payload,
    )
    resp = r.json()
    if "error" in resp:
        return None, resp["error"].get("error_user_msg", resp["error"].get("message"))

    creative_id = resp["id"]

    # Step 2: Create ad
    ad_payload = {
        "name": ad_config["name"],
        "adset_id": ad_config["ad_set_id"],
        "creative": json.dumps({"creative_id": creative_id}),
        "status": "ACTIVE",
        "access_token": META_CONFIG["access_token"],
    }

    r2 = requests.post(
        f"https://graph.facebook.com/v21.0/{META_CONFIG['ad_account_id']}/ads",
        data=ad_payload,
    )
    resp2 = r2.json()
    if "error" in resp2:
        return None, resp2["error"].get("error_user_msg", resp2["error"].get("message"))

    return resp2["id"], None


# ============================================================
# EXECUTE
# ============================================================
print("=" * 60)
print("A7 Orlando — Ad Creation Script")
print(f"Mode: {'DRY RUN (preview)' if dry_run else 'LIVE (creating ads)'}")
print(f"Total ads to create: {len(ADS)}")
print("=" * 60)

ad_sets_summary = {}
for ad in ADS:
    asid = ad["ad_set_id"]
    if asid not in ad_sets_summary:
        ad_sets_summary[asid] = []
    ad_sets_summary[asid].append(ad["name"])

print("\nPlan:")
for asid, names in ad_sets_summary.items():
    print(f"\n  Ad Set {asid}:")
    for n in names:
        print(f"    → {n}")

if dry_run:
    print("\n✅ Dry run complete. Remove --dry-run to create ads.")
    sys.exit(0)

print("\nCreating ads...\n")
success = 0
failed = 0

for ad in ADS:
    ad_id, error = create_ad(ad)
    if ad_id:
        print(f"  ✓ {ad['name']} → Ad ID: {ad_id}")
        success += 1
    else:
        print(f"  ✗ {ad['name']} → {error}")
        failed += 1

print(f"\n{'=' * 60}")
print(f"Done: {success} created, {failed} failed")
print(f"{'=' * 60}")
