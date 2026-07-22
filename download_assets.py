"""
Smart Asset Downloader for LoL Tracker.
Checks for LoL updates via DDragon.
- If version changed: Redownloads ALL assets to ensure latest art.
- If version same: Downloads only MISSING assets.
"""

import os
import json
import requests
import shutil

# --- CONFIGURATION ---
ASSETS_DIR = "assets"
CHAMP_DIR = os.path.join(ASSETS_DIR, "champions")
SPELL_DIR = os.path.join(ASSETS_DIR, "spells")
RUNE_DIR = os.path.join(ASSETS_DIR, "runes")
ABILITY_DIR = os.path.join(ASSETS_DIR, "abilities")   # ultimate (R) icons + data
VERSION_FILE = os.path.join(ASSETS_DIR, "version.txt")

# Per-item Ability Haste (Meraki static data — DDragon/CDragon don't expose AH cleanly).
MERAKI_ITEMS_URL = "https://cdn.merakianalytics.com/riot/lol/resources/latest/en-US/items.json"

# Rune icons (from CommunityDragon; DDragon doesn't serve these cleanly).
# Only the ones the app actually uses as toggles.
RUNE_URLS = {
    "CosmicInsight": "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/"
                     "global/default/v1/perk-images/styles/inspiration/cosmicinsight/cosmicinsight.png",
}

# Spells list
SPELL_IDS = [
    "SummonerFlash", "SummonerDot", "SummonerHeal", "SummonerBarrier", "SummonerExhaust",
    "SummonerTeleport", "SummonerSmite", "SummonerBoost", "SummonerMana", "SummonerHaste", "SummonerSnowball"
]

def get_latest_version():
    """Fetches the latest DDragon version (e.g., '14.2.1')."""
    try:
        url = "https://ddragon.leagueoflegends.com/api/versions.json"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()[0]
    except Exception as e:
        print(f"[Error] Could not fetch DDragon version: {e}")
        return None

def get_local_version():
    """Reads the locally stored version from version.txt."""
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    return None

def save_local_version(version):
    """Saves the current version to version.txt."""
    with open(VERSION_FILE, "w") as f:
        f.write(version)

def get_champion_list(version):
    """Fetches the list of all champion names for the specific version."""
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return list(data['data'].keys())
    except Exception as e:
        print(f"[Error] Could not fetch champion list: {e}")
        return []

def download_file(url, path, force=False):
    """
    Downloads a file.
    :param force: If True, overwrites existing file.
    """
    if os.path.exists(path) and not force:
        # File exists and we don't want to force update
        return False
    
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            with open(path, "wb") as f:
                f.write(resp.content)
            print(f" [+] Downloaded: {os.path.basename(path)}")
            return True
        else:
            print(f" [!] Failed (Status {resp.status_code}): {url}")
            return False
    except Exception as e:
        print(f" [!] Error downloading {url}: {e}")
        return False

def create_placeholder():
    """Creates a placeholder image if Pillow is available."""
    placeholder_path = os.path.join(ASSETS_DIR, "placeholder.png")
    if os.path.exists(placeholder_path):
        return

    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (40, 40), (40, 40, 40, 255))
        draw = ImageDraw.Draw(img)
        # Draw a simple '?' or border
        draw.rectangle([0, 0, 39, 39], outline=(100, 100, 100))
        draw.text((15, 10), "?", fill=(200, 200, 200))
        img.save(placeholder_path)
        print(" [i] Created placeholder.png")
    except ImportError:
        print(" [!] Pillow not installed. Skipping placeholder generation.")
    except Exception:
        pass # Font issues usually

def sync_abilities(version, force):
    """下载每个英雄的大招(R)图标，并生成两份本地数据供 main.py 离线读取：
      - assets/abilities/r_index.json  : {champKey: {"icon": file, "cd": [r1,r2,r3]}}
      - assets/abilities/item_ah.json  : {itemId: abilityHaste}
    这样运行时不必再访问外网（R CD 随补丁变，靠重跑本脚本更新）。"""
    os.makedirs(ABILITY_DIR, exist_ok=True)
    print("\n--- Syncing Ultimates (R) ---")
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/championFull.json"
    try:
        data = requests.get(url, timeout=30).json().get("data", {})
    except Exception as e:
        print(f" [!] championFull.json failed: {e}")
        return

    r_index = {}
    for champ, info in data.items():
        spells = info.get("spells", [])
        if len(spells) < 4:
            continue
        r = spells[3]  # index 3 = R
        icon = r.get("image", {}).get("full")
        cd = r.get("cooldown", [])
        if not icon or not cd:
            continue
        r_index[champ] = {"icon": icon, "cd": cd}
        img_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/img/spell/{icon}"
        download_file(img_url, os.path.join(ABILITY_DIR, icon), force=force)
    with open(os.path.join(ABILITY_DIR, "r_index.json"), "w", encoding="utf-8") as f:
        json.dump(r_index, f, ensure_ascii=False)
    print(f" [i] R index: {len(r_index)} champions")

    # item -> ability haste (Meraki)
    print("--- Syncing Item Ability Haste (Meraki) ---")
    try:
        items = requests.get(MERAKI_ITEMS_URL, timeout=30).json()
        item_ah = {}
        for iid, it in items.items():
            ah = (it.get("stats", {}) or {}).get("abilityHaste", {}).get("flat", 0)
            if ah:
                item_ah[str(iid)] = int(ah)
        with open(os.path.join(ABILITY_DIR, "item_ah.json"), "w", encoding="utf-8") as f:
            json.dump(item_ah, f)
        print(f" [i] Item AH map: {len(item_ah)} items")
    except Exception as e:
        print(f" [!] Meraki item AH failed: {e}")


def main():
    # 1. Setup Directories
    os.makedirs(CHAMP_DIR, exist_ok=True)
    os.makedirs(SPELL_DIR, exist_ok=True)
    os.makedirs(RUNE_DIR, exist_ok=True)
    os.makedirs(ABILITY_DIR, exist_ok=True)

    # 2. Check Version
    print("--- LoL Asset Manager ---")
    latest_ver = get_latest_version()
    if not latest_ver:
        print("Could not connect to Riot API. Exiting.")
        return

    local_ver = get_local_version()
    
    force_update = False
    
    if local_ver != latest_ver:
        print(f" [!] Update detected! Local: {local_ver} -> Latest: {latest_ver}")
        print(" [i] Doing a full sync...")
        force_update = True
    else:
        print(f" [OK] Version {latest_ver} is up to date.")
        print(" [i] Checking for missing files only...")

    # 3. Download Champions
    print("\n--- Syncing Champions ---")
    champs = get_champion_list(latest_ver)
    if not champs:
        print("Failed to get champion list.")
        return

    for champ in champs:
        url = f"https://ddragon.leagueoflegends.com/cdn/{latest_ver}/img/champion/{champ}.png"
        path = os.path.join(CHAMP_DIR, f"{champ}.png")
        # Special case: Fiddlesticks in DDragon is just "Fiddlesticks", but sometimes API refers differently. 
        # Usually DDragon names match the key.
        download_file(url, path, force=force_update)

    # 4. Download Spells
    print("\n--- Syncing Spells ---")
    for spell in SPELL_IDS:
        url = f"https://ddragon.leagueoflegends.com/cdn/{latest_ver}/img/spell/{spell}.png"
        path = os.path.join(SPELL_DIR, f"{spell}.png")
        download_file(url, path, force=force_update)

    # 4b. Download Rune icons (CommunityDragon 'latest' — not version-pinned)
    print("\n--- Syncing Runes ---")
    for name, url in RUNE_URLS.items():
        path = os.path.join(RUNE_DIR, f"{name}.png")
        download_file(url, path, force=force_update)

    # 4c. Ultimate (R) icons + per-rank cooldowns, and item -> ability haste map
    sync_abilities(latest_ver, force_update)

    # 5. Finalize
    save_local_version(latest_ver)
    create_placeholder()
    print(f"\n[Success] All assets synced for version {latest_ver}!")

if __name__ == "__main__":
    main()