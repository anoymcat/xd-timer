from __future__ import annotations
import os
import sys
import json
import signal
import ctypes
import threading
import time
import tkinter as tk
from typing import Any, Dict, List, Optional, Tuple
import requests
import urllib3
from PIL import Image, ImageTk, ImageDraw, ImageOps
import pystray 
from timer_core import (GameClock, TimerModel, apply_haste, rank_from_level as _rank_from_level,
                        teleport_cd, fmt_countdown, fmt_clock)

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- SINGLE INSTANCE CHECKER (MUTEX) ---
class SingleInstanceChecker:
    """Prevents multiple instances of the application."""
    def __init__(self, app_name="Global\\DeskTimer_v1"):
        self.mutex_name = app_name
        self.mutex = None

    def is_already_running(self):
        kernel32 = ctypes.windll.kernel32
        self.mutex = kernel32.CreateMutexW(None, False, self.mutex_name)
        last_error = kernel32.GetLastError()
        # ERROR_ALREADY_EXISTS = 183
        if last_error == 183:
            return True
        return False

# --- RESOURCE HELPER ---
def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- CONFIGURATION ---
class Config:
    if getattr(sys, 'frozen', False):
        APP_DIR = os.path.dirname(sys.executable)
    else:
        APP_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_FILE = os.path.join(APP_DIR, "config.json")

    # === ITEM DATABASE (SUMMONER SPELL HASTE) ===
    # Item ID -> Haste Value
    ITEM_HASTE_MAP = {
        3158: 10,    # Ionian Boots of Lucidity (SR/ARAM) -> 10 Haste
        3171: 20,    # Crimson Lucidity (Ornn Upgrade) -> 20 Haste
        223158: 10,  # Ionian Boots (Arena) -> 10 Haste
    }

    # Cosmic Insight (星界洞悉): +18 summoner-spell haste. Enemy minor runes are NOT
    # exposed by the local API, so this is applied via a manual per-enemy toggle.
    COSMIC_HASTE = 18

    # 2026 Top-lane role quest reward: "Unleashed Teleport" granted as a bonus 3rd
    # summoner spell (fixed CD, level-independent) when the top laner did NOT
    # pick Teleport. If they already have TP, the quest only empowers it (no 3rd spell).
    # Patch 26.19: 420 -> 390. Native TP CD (level / game-time based) lives in timer_core.
    UNLEASHED_TP_CD = 390

    # === RETRO-RECORDING (game seconds) ===
    # Recording always lags the real cast (alt-tab + click), so a plain left-click
    # back-dates by REACTION_DELAY; Shift+left-click back-dates by LATE_OFFSET
    # ("remembered after the fight"); mouse wheel on a running timer shifts it by
    # WHEEL_STEP per notch. The first two can be overridden in config.json.
    REACTION_DELAY = 3
    LATE_OFFSET = 20
    WHEEL_STEP = 5

    # === IN-GAME LOCK ===
    # While the game window is foreground AND this window sits on the same monitor,
    # the window is disabled (Tk "-disabled"): clicks do nothing and never steal focus.
    # Alt-tab out -> enabled again (click timers / drag). Window identified read-only
    # via GetForegroundWindow + class name / title. [需核实: class name / title]
    GAME_WINDOW_CLASS = "RiotWindowClass"
    GAME_WINDOW_TITLE = "League of Legends (TM) Client"
    UI_TICK = 200  # ms: timer redraw + foreground check

    # Set by DDragonManager.update_timers(): (local, latest) when assets/ is stale.
    ASSETS_OUTDATED: Optional[Tuple[str, str]] = None

    # === BASE SPELL TIMERS (Seconds) ===
    SPELL_TIMERS = {
        "summonerflash":    300,
        "summonerteleport": 360,
        "summonerheal":     240,
        "summonerboost":    210, # Cleanse
        "summonerexhaust":  210,
        "summonerhaste":    210, # Ghost
        "summonerbarrier":  180,
        "summonerdot":      180, # Ignite
        "summonersmite":    15,
        "summonersnowball": 80,  # ARAM Mark
        "summonerclarity":  240,
        "summonermana":     240
    }
    
    # === VISUALS ===
    GLOBAL_OPACITY = 0.85
    SHOW_SEPARATOR = True

    # --- Scaling ---
    # BASE_* are the 100% design sizes (px). Effective sizes below are recomputed by
    # apply_scale(). DPI awareness (see _enable_dpi_awareness) keeps them crisp.
    BASE_ICON_SIZE = 38
    BASE_EYE_SIZE = 22      # Cosmic Insight toggle icon (smaller than spell icons)
    SCALE = 1.0
    ICON_SIZE = 38          # = round(BASE_ICON_SIZE * SCALE)
    EYE_SIZE = 22           # = round(BASE_EYE_SIZE  * SCALE)
    ROW_PADDING_Y = 6

    COLOR_BG = "#091428"
    COLOR_SEPARATOR = "#0A1F33"
    COLOR_TEXT_ACTIVE = "#F0E6D2"   # LoL parchment white
    COLOR_TEXT_OUTLINE = "#000000"

    # Hextech gold double-line border palette
    COLOR_GOLD = "#C8AA6E"          # bright border gold (outer line)
    COLOR_GOLD_DIM = "#785A28"      # darker gold (inner line)
    COLOR_MOAT = "#010A13"          # near-black blue (moat between the two lines)
    COLOR_BORDER = COLOR_GOLD_DIM   # legacy alias

    COLOR_PINNED = "#8B0000"    # Dark Red
    COLOR_HANDLE = "#785A28"    # soft gold

    FONT_FAMILY = "Arial"
    BASE_FONT_SIZE = 12

    @classmethod
    def apply_scale(cls, scale: float):
        cls.SCALE = scale
        cls.ICON_SIZE = max(1, round(cls.BASE_ICON_SIZE * scale))
        cls.EYE_SIZE = max(1, round(cls.BASE_EYE_SIZE * scale))

    @classmethod
    def s(cls, v) -> int:
        """Scale a base pixel/padding value by the current SCALE (min 1)."""
        return max(1, round(v * cls.SCALE))
    
    # API URLs
    LCL_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
    DDRAGON_VER_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
    DDRAGON_DATA_URL = "https://ddragon.leagueoflegends.com/cdn/{}/data/en_US/summoner.json"
    
    CHECK_INTERVAL = 2000 # Check every 2 seconds

    # Debug switch: when env DESKTIMER_DEBUG=1, show dummy enemies even with no
    # live game running, so the window layout can be tested offline.
    DEBUG_DUMMY = os.environ.get("DESKTIMER_DEBUG", "") == "1"

# --- DDRAGON MANAGER ---
class DDragonManager:
    @staticmethod
    def update_timers():
        print("[DDragon] Checking for updates...")
        try:
            v_resp = requests.get(Config.DDRAGON_VER_URL, timeout=2)
            if v_resp.status_code != 200: return
            version = v_resp.json()[0]
            DDragonManager._check_assets_version(version)

            url = Config.DDRAGON_DATA_URL.format(version)
            d_resp = requests.get(url, timeout=3)
            if d_resp.status_code != 200: return
            
            data = d_resp.json().get("data", {})
            for spell_id, info in data.items():
                cooldowns = info.get("cooldown", [300])
                cd = int(cooldowns[0])
                key = spell_id.lower()
                Config.SPELL_TIMERS[key] = cd
        except Exception as e:
            print(f"[DDragon] Update failed: {e}")

    @staticmethod
    def _check_assets_version(latest: str):
        """assets/version.txt is written by download_assets.py. If it differs from the
        live DDragon version, flag it (shown in the tray); no auto-download."""
        local = None
        try:
            with open(resource_path(os.path.join("assets", "version.txt"))) as f:
                local = f.read().strip()
        except OSError:
            pass
        if local != latest:
            Config.ASSETS_OUTDATED = (local or "none", latest)
            print(f"[Assets] Outdated: {local} -> {latest}. Run download_assets.py")

# --- ABILITY (ULTIMATE) DATA ---
class AbilityData:
    """本地读取 download_assets.py 生成的两份快照：
       r_index.json  -> {champKey: {"icon": file, "cd": [r1,r2,r3]}}
       item_ah.json  -> {itemId: abilityHaste}
    读不到就返回空/0，功能自动降级（不加 R 按钮）。"""
    R_INDEX: Dict[str, Dict] = {}
    ITEM_AH: Dict[int, int] = {}
    _loaded = False

    @classmethod
    def load(cls):
        if cls._loaded:
            return
        cls._loaded = True
        base = resource_path(os.path.join("assets", "abilities"))
        try:
            with open(os.path.join(base, "r_index.json"), encoding="utf-8") as f:
                cls.R_INDEX = json.load(f)
            print(f"[AbilityData] R index: {len(cls.R_INDEX)} champions")
        except Exception as e:
            print(f"[AbilityData] r_index load failed: {e}")
        try:
            with open(os.path.join(base, "item_ah.json"), encoding="utf-8") as f:
                cls.ITEM_AH = {int(k): int(v) for k, v in json.load(f).items()}
            print(f"[AbilityData] item AH map: {len(cls.ITEM_AH)} items")
        except Exception as e:
            print(f"[AbilityData] item_ah load failed: {e}")

    @classmethod
    def item_ah(cls, item_id) -> int:
        try:
            return cls.ITEM_AH.get(int(item_id), 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def r_info(cls, champ_key: str) -> Optional[Dict]:
        return cls.R_INDEX.get(champ_key)

# --- DATA MANAGER ---
class GameDataManager:
    # localhost 2999 MUST bypass any system proxy. When global traffic is routed
    # through a VPN/proxy (e.g. CN client + overseas routing), 127.0.0.1 otherwise
    # gets hijacked and the request fails (curl exit 7 / connection refused).
    # NOTE: DDragon (external) requests intentionally keep the system proxy.
    _NO_PROXY = {"http": None, "https": None}

    @staticmethod
    def fetch_data() -> Optional[Dict]:
        try:
            resp = requests.get(Config.LCL_URL, verify=False, timeout=0.5,
                                proxies=GameDataManager._NO_PROXY)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        return None

    @staticmethod
    def parse_enemies(data: Dict) -> List[Dict]:
        if not data: return GameDataManager._get_dummy_data()
        
        all_players = data.get("allPlayers") or []
        active_data = data.get("activePlayer", {})
        my_name = active_data.get("summonerName")
        
        # --- FIX: Reliable Team Detection ---
        # Look up the player in the full list to get the correct team (ORDER/CHAOS)
        my_team = None
        if my_name:
            for p in all_players:
                if p.get("summonerName") == my_name:
                    my_team = p.get("team")
                    break
        
        # Fallback default
        if not my_team:
            my_team = active_data.get("team", "ORDER")

        enemies = []

        for p in all_players:
            if p.get("team") == my_team: continue
            
            champ_name = GameDataManager._resolve_champ_name(p)
            spells = p.get("summonerSpells", {})
            
            # --- HASTE FROM ITEMS ---
            # summoner-spell haste (boots) and ability haste (all AH items) are DIFFERENT stats.
            items = p.get("items", [])
            current_haste = 0     # summoner-spell haste (for flash/TP/...)
            ability_haste = 0     # ability haste (for R)
            for item in items:
                i_id = item.get("itemID", 0)
                current_haste += Config.ITEM_HASTE_MAP.get(i_id, 0)
                ability_haste += AbilityData.item_ah(i_id)

            enemies.append({
                "champ": champ_name,
                "spell1": GameDataManager._clean_spell_name(spells.get("summonerSpellOne", {}).get("rawDisplayName")),
                "spell2": GameDataManager._clean_spell_name(spells.get("summonerSpellTwo", {}).get("rawDisplayName")),
                "haste": current_haste,
                "ability_haste": ability_haste,
                "level": p.get("level", 1),
                "position": (p.get("position") or "").upper(),
            })
        return enemies

    @staticmethod
    def _resolve_champ_name(p: Dict) -> str:
        """从 rawChampionName 解析出 DDragon 英雄 key。

        Live Client API 的 rawChampionName 存在多种格式：
          - "Character_Seraphine_Name"              -> key 在中间段（对局中敌方实测格式）
          - "game_character_displayname_Seraphine"  -> key 在最后一段（早期测试格式）
        因此不能死取某一段。优先在各段中匹配一个"已知英雄 key"（即已下载的
        头像文件名），两种格式都能正确解析，也能兼容未来格式变化。
        """
        raw = (p.get("rawChampionName") or "").strip()
        if not raw:
            return p.get("championName") or "Unknown"

        tokens = [t for t in raw.split("_") if t]
        valid = AssetManager.champion_keys()
        # 1) 精确匹配已知英雄 key（大小写敏感，DDragon key 就是这样拼写的）
        for t in tokens:
            if t in valid:
                return t
        # 2) 结构化兜底：assets 缺文件 / 新英雄时，按格式提取
        if raw.startswith("Character_") and raw.endswith("_Name"):
            return raw[len("Character_"):-len("_Name")]
        # 3) 最后兜底：老逻辑取最后一段
        return tokens[-1] if tokens else (p.get("championName") or "Unknown")

    @staticmethod
    def _clean_spell_name(raw: Optional[str]) -> str:
        if not raw: return "Unknown"
        raw_lower = raw.lower()
        if "teleport" in raw_lower: return "SummonerTeleport"
        if "smite" in raw_lower: return "SummonerSmite"
        if "flash" in raw_lower: return "SummonerFlash"
        if "ignite" in raw_lower or "dot" in raw_lower: return "SummonerDot"
        if "barrier" in raw_lower: return "SummonerBarrier"
        if "heal" in raw_lower: return "SummonerHeal"
        if "exhaust" in raw_lower: return "SummonerExhaust"
        if "cleanse" in raw_lower or "boost" in raw_lower: return "SummonerBoost"
        if "ghost" in raw_lower or "haste" in raw_lower: return "SummonerHaste"
        parts = raw.split("_")
        for p in reversed(parts):
            if p.startswith("Summoner") and p != "SummonerSpell": return p
        return "Unknown"

    @staticmethod
    def _get_dummy_data():
        return [
            # Top laner WITHOUT native TP -> should get the extra Unleashed TP button.
            {"champ": "Darius", "spell1": "SummonerFlash", "spell2": "SummonerDot",
             "haste": 0, "ability_haste": 20, "level": 16, "position": "TOP"},
            {"champ": "Ornn", "spell1": "SummonerFlash", "spell2": "SummonerTeleport",
             "haste": 20, "ability_haste": 0, "level": 11, "position": "MIDDLE"},
        ]

# --- ASSET MANAGER ---
class AssetManager:
    _champ_keys: Optional[set] = None

    @staticmethod
    def champion_keys() -> set:
        """已下载英雄头像的文件名（= DDragon key）集合，用于校验解析结果。首次调用后缓存。"""
        if AssetManager._champ_keys is None:
            keys = set()
            folder = resource_path(os.path.join("assets", "champions"))
            try:
                for fn in os.listdir(folder):
                    if fn.lower().endswith(".png"):
                        keys.add(os.path.splitext(fn)[0])
            except OSError:
                pass
            AssetManager._champ_keys = keys
        return AssetManager._champ_keys

    @staticmethod
    def load_icon(folder: str, name: str, size: Tuple[int, int], is_round: bool = False) -> ImageTk.PhotoImage:
        path = resource_path(os.path.join("assets", folder, name + ".png"))
        try:
            img = Image.open(path).convert("RGBA")
        except FileNotFoundError:
            img = Image.new("RGBA", size, "#222")
            draw = ImageDraw.Draw(img)
            draw.rectangle([0,0, size[0]-1, size[1]-1], outline="#555")
            text = name[:2] if name else "??"
            draw.text((size[0]//2, size[1]//2), text, fill="#888", anchor="mm")

        img = img.resize(size, Image.Resampling.LANCZOS)
        if is_round:
            # Supersample the circular mask (4x) then downscale for smooth AA edges.
            ss = 4
            big = (size[0] * ss, size[1] * ss)
            mask = Image.new("L", big, 0)
            ImageDraw.Draw(mask).ellipse((0, 0) + big, fill=255)
            mask = mask.resize(size, Image.Resampling.LANCZOS)
            img = ImageOps.fit(img, size, centering=(0.5, 0.5))
            img.putalpha(mask)
        return ImageTk.PhotoImage(img)

    @staticmethod
    def create_dim_layer(size: Tuple[int, int]) -> ImageTk.PhotoImage:
        img = Image.new("RGBA", size, (0, 0, 0, 180))
        return ImageTk.PhotoImage(img)

    @staticmethod
    def load_toggle_pair(folder: str, name: str, size: Tuple[int, int]
                         ) -> Tuple[ImageTk.PhotoImage, ImageTk.PhotoImage]:
        """返回 (on, off) 两张图：on = 原图；off = 去色 + 压暗，表示开关的关闭态。"""
        path = resource_path(os.path.join("assets", folder, name + ".png"))
        try:
            base = Image.open(path).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
        except FileNotFoundError:
            base = Image.new("RGBA", size, (80, 80, 80, 255))
        on_img = base
        # off: 灰度化 + 压暗 + 降透明，看起来"熄灭"
        gray = ImageOps.grayscale(base).point(lambda v: int(v * 0.7))  # L, darkened
        alpha = base.getchannel("A").point(lambda v: int(v * 0.45))
        off_img = Image.merge("RGBA", (gray, gray, gray, alpha))
        return ImageTk.PhotoImage(on_img), ImageTk.PhotoImage(off_img)

# --- SPELL TIMER WIDGET ---
class SpellTimerWidget(tk.Canvas):
    """One clickable icon. Holds NO timer state: the countdown lives in
    app.timers (TimerModel, keyed by (champ, slot)) and is redrawn by app._ui_tick,
    so rebuilding the window (scale change) keeps running timers."""
    def __init__(self, parent, champ_name: str, spell_name: str, slot: str, app_ref,
                 base_cd: Optional[int] = None, icon_name: Optional[str] = None,
                 folder: str = "spells", r_cds: Optional[list] = None,
                 use_ability_haste: bool = False):
        super().__init__(parent, width=Config.ICON_SIZE, height=Config.ICON_SIZE,
                         bg=Config.COLOR_BG, highlightthickness=0)
        self.champ_name = champ_name
        self.spell_name = spell_name
        self.key = (champ_name, slot)    # TimerModel key; slot = S1 / S2 / R / UTP
        self.app_ref = app_ref # Reference to main app to access cache
        self.base_cd_override = base_cd  # e.g. Unleashed TP = 390, bypasses SPELL_TIMERS
        self.r_cds = r_cds               # ultimate: per-rank CDs; base picked by enemy level
        self.use_ability_haste = use_ability_haste  # R uses Ability Haste, not summoner haste
        self._text = None                # last drawn text (None = idle)

        self.icon_img = AssetManager.load_icon(folder, icon_name or spell_name, (Config.ICON_SIZE, Config.ICON_SIZE))
        self.create_image(0, 0, image=self.icon_img, anchor="nw")
        
        self.dim_img = AssetManager.create_dim_layer((Config.ICON_SIZE, Config.ICON_SIZE))
        self.dim_id = self.create_image(0, 0, image=self.dim_img, anchor="nw", state="hidden")

        # Tk fires only the most specific binding, so Shift+click does NOT also fire <Button-1>.
        self.bind("<Button-1>", lambda e: self._start(self.app_ref.reaction_delay))
        self.bind("<Shift-Button-1>", lambda e: self._start(self.app_ref.late_offset))
        self.bind("<Button-3>", self._on_right_click) 
        # Mouse wheel: handled globally by app._on_wheel (-> self.adjust).

        app_ref.register_timer(self)
        self.refresh()

    def _base_cd(self) -> Optional[float]:
        if self.r_cds:
            # Ultimate: rank estimated from the enemy's CURRENT level (cache, live).
            rank = self.app_ref.rank_from_level(self.champ_name)
            if rank <= 0:
                return None  # ult not unlocked yet (level < 6) -> ignore click
            return self.r_cds[min(rank, len(self.r_cds)) - 1]
        if self.base_cd_override is not None:
            return self.base_cd_override
        if self.spell_name == "SummonerTeleport":
            return self.app_ref.teleport_base_cd(self.champ_name)
        return Config.SPELL_TIMERS.get(self.spell_name.lower(), 300)

    def _start(self, ago: float):
        """Start the timer as if the spell was cast `ago` game-seconds earlier."""
        timers = self.app_ref.timers
        if timers.is_active(self.key): return
        base_cd = self._base_cd()
        if base_cd is None: return

        # R -> Ability Haste (items); summoner spells -> summoner-spell haste (+cosmic).
        if self.use_ability_haste:
            current_haste = self.app_ref.get_ability_haste(self.champ_name)
        else:
            current_haste = self.app_ref.get_haste(self.champ_name)
        final_cd = apply_haste(base_cd, current_haste)

        now = self.app_ref.clock.now()
        used_at = max(0.0, now - ago)
        timers.start(self.key, final_cd, used_at)
        print(f"[Timer] {self.champ_name} ({self.spell_name}): Base {base_cd:.0f}s -> Haste {current_haste} "
              f"-> {final_cd:.1f}s, used {fmt_clock(used_at)}, ready {fmt_clock(used_at + final_cd)}")
        self.refresh()

    def _on_right_click(self, event):
        self.app_ref.timers.reset(self.key)
        self.refresh()

    def adjust(self, delta: float):
        """Shift a running timer by delta seconds (mouse wheel)."""
        if self.app_ref.timers.is_active(self.key):
            self.app_ref.timers.adjust(self.key, delta)
            self.refresh()

    def _get_adaptive_font(self, text: str) -> Tuple[str, int, str]:
        # Pixel-based size (negative => pixels in tk) tied to ICON_SIZE, so it tracks
        # both the scale factor and DPI awareness crisply.
        length = len(text)
        factor = 0.47 if length <= 2 else 0.42 if length == 3 else 0.37 if length == 4 else 0.30
        px = max(8, round(Config.ICON_SIZE * factor))
        return (Config.FONT_FAMILY, -px, "bold")

    def _draw_outlined_text(self, text):
        self.delete("timer_text")
        cx, cy = Config.ICON_SIZE // 2, Config.ICON_SIZE // 2
        font_spec = self._get_adaptive_font(text)
        offsets = [(-1, -1), (0, -1), (1, -1), (-1,  0), (1,  0), (-1,  1), (0,  1), (1,  1)]
        for ox, oy in offsets:
            self.create_text(cx + ox, cy + oy, text=text, font=font_spec, fill=Config.COLOR_TEXT_OUTLINE, tags="timer_text", anchor="center")
        self.create_text(cx, cy, text=text, font=font_spec, fill=Config.COLOR_TEXT_ACTIVE, tags="timer_text", anchor="center")

    def refresh(self):
        """Redraw from the model. Display mode: 'ready' = game-clock time it comes
        back (how players call it in chat, e.g. 14:25) / 'countdown' = seconds left."""
        timers = self.app_ref.timers
        remaining = timers.remaining(self.key, self.app_ref.clock.now())
        if remaining is not None and remaining <= 0:
            timers.reset(self.key)
            remaining = None
        if remaining is None:
            if self._text is not None:
                self.delete("timer_text")
                self.itemconfig(self.dim_id, state="hidden")
                self._text = None
            return
        if self.app_ref.display_mode == "ready":
            text = fmt_clock(timers.ready_at(self.key))
        else:
            text = fmt_countdown(remaining)
        if text != self._text:
            self.itemconfig(self.dim_id, state="normal")
            self._draw_outlined_text(text)
            self._text = text

# --- WIN32 (read-only window queries for the in-game lock) ---
class _Win32:
    """Only READS window info (foreground hwnd, class name, title, monitor).
    Never opens the game process, never changes any window style."""
    _user32 = None

    @classmethod
    def _api(cls):
        if cls._user32 is None:
            try:
                u = ctypes.windll.user32
            except AttributeError:
                cls._user32 = False   # non-Windows
                return None
            u.GetForegroundWindow.restype = ctypes.c_void_p
            u.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
            u.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
            u.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            u.MonitorFromWindow.restype = ctypes.c_void_p
            cls._user32 = u
        return cls._user32 or None

    @classmethod
    def _is_game(cls, u, hwnd) -> bool:
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, buf, 256)
        if buf.value == Config.GAME_WINDOW_CLASS:
            return True
        u.GetWindowTextW(hwnd, buf, 256)
        return buf.value == Config.GAME_WINDOW_TITLE

    @classmethod
    def describe_foreground(cls) -> Optional[Tuple[int, str, str]]:
        """(hwnd, class, title) of the foreground window, for DESKTIMER_DEBUG logs."""
        u = cls._api()
        if u is None:
            return None
        try:
            fg = u.GetForegroundWindow() or 0
            cls_buf = ctypes.create_unicode_buffer(256)
            title_buf = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(fg, cls_buf, 256)
            u.GetWindowTextW(fg, title_buf, 256)
            return fg, cls_buf.value, title_buf.value
        except Exception:
            return None

    @classmethod
    def game_foreground_on_same_monitor(cls, root: tk.Tk) -> bool:
        """True if the game window is foreground and on the same monitor as `root`.
        Any failure -> False (window stays usable, i.e. old behaviour)."""
        u = cls._api()
        if u is None:
            return False
        try:
            fg = u.GetForegroundWindow()
            if not fg or not cls._is_game(u, fg):
                return False
            mine = int(root.wm_frame(), 16)
            MONITOR_DEFAULTTONEAREST = 2
            return u.MonitorFromWindow(fg, MONITOR_DEFAULTTONEAREST) == \
                   u.MonitorFromWindow(mine, MONITOR_DEFAULTTONEAREST)
        except Exception:
            return False

# --- MAIN APP ---
class OverlayApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("DeskTimer")
        self.root.configure(bg=Config.COLOR_BG)
        # Normal desktop window: still NO overrideredirect / alpha / WS_EX_NOACTIVATE /
        # click-through. Allowed: "-topmost" (user-toggleable, default on) and Tk's
        # "-disabled" (in-game lock, see Config.GAME_WINDOW_CLASS). The window keeps its
        # border, taskbar entry and is opaque; it may sit over the game on the main
        # screen, but is disabled while the game is foreground so it never takes focus.
        # Do NOT re-add the other overlay attributes — that combo is what anti-cheat flags.

        self.game_active = False
        self.enemy_data_cache = {} # Cache to store fresh enemy data
        self._img_refs = []

        # Timer state lives here (not in widgets) so rebuilds keep running timers.
        self.clock = GameClock()
        self.timers = TimerModel()
        self._timer_widgets: List[SpellTimerWidget] = []
        self._debug_t0 = None     # DEBUG_DUMMY: fake game clock origin
        self._locked = False      # in-game lock (Tk -disabled) currently applied
        self._last_fg = None      # DEBUG_DUMMY: last logged foreground hwnd

        # Per-enemy manual modifiers (reset each game):
        self.cosmic_toggle = {}   # champ -> bool: apply +18 haste (Cosmic Insight)
        self.tp_shown = {}        # champ -> bool: Unleashed TP button currently packed
        self._tp_widgets = {}     # champ -> SpellTimerWidget (extra TP)
        self._eye_widgets = {}    # champ -> tk.Label (cosmic toggle, used as pack anchor)
        # Shared cosmic on/off images (built lazily once assets/tk root exist)
        self._cosmic_on = None
        self._cosmic_off = None

        self.saved_x = 0
        self.saved_y = 0
        self.is_pinned = False
        self.is_topmost = True  # overwritten by _load_config
        self.scale = 1.0        # overwritten by _load_config
        self.display_mode = "ready"   # 'ready' (game-clock time) | 'countdown'
        self.lock_over_game = True
        self.reaction_delay = Config.REACTION_DELAY
        self.late_offset = Config.LATE_OFFSET
        self._load_config()
        Config.apply_scale(self.scale)

        self._drag_data = {"x": 0, "y": 0}

        self.container = None
        self._build_shell()

        self.root.withdraw()
        
        self._setup_tray()
        
        signal.signal(signal.SIGINT, self._graceful_exit)

        # Wheel goes to the widget under the pointer regardless of Tk version/focus.
        self.root.bind_all("<MouseWheel>", self._on_wheel)
        
        self._monitor_game_loop()
        self._ui_tick()

    def _build_shell(self):
        """Build (or rebuild) the window chrome: Hextech gold double-line border +
        drag handle + empty enemies_frame. Sizes derive from Config.SCALE."""
        s = Config.s
        if self.container is not None:
            self.container.destroy()

        # Nested frames form the border: each frame's bg is a "line" colour, and its
        # child packed with padx/pady reveals that colour as a ring of that thickness.
        # gold line -> dark moat -> gold line -> content.
        # outer gold line (dimmed while the in-game lock is on, see _update_lock_visual)
        self.container = tk.Frame(self.root, bg=Config.COLOR_GOLD_DIM if self._locked else Config.COLOR_GOLD)
        self.container.pack()
        moat = tk.Frame(self.container, bg=Config.COLOR_MOAT)               # dark moat
        moat.pack(padx=s(1), pady=s(1))
        gold_inner = tk.Frame(moat, bg=Config.COLOR_GOLD_DIM)              # inner gold line
        gold_inner.pack(padx=s(2), pady=s(2))
        self.inner = tk.Frame(gold_inner, bg=Config.COLOR_BG)
        self.inner.pack(padx=s(1), pady=s(1))

        content = tk.Frame(self.inner, bg=Config.COLOR_BG)
        content.pack(padx=s(6), pady=s(5))

        self.handle = tk.Label(content, text="::::", bg=Config.COLOR_BG, fg=Config.COLOR_HANDLE,
                               font=(Config.FONT_FAMILY, -max(7, s(9)), "bold"), cursor="fleur")
        self.handle.pack(fill="x", pady=(0, s(3)))
        self.handle.bind("<ButtonPress-1>", self._start_drag)
        self.handle.bind("<B1-Motion>", self._do_drag)
        self.handle.bind("<Button-3>", self._toggle_pin)
        self._update_pin_visual()

        self.enemies_frame = tk.Frame(content, bg=Config.COLOR_BG)
        self.enemies_frame.pack()

    def _set_scale(self, scale: float):
        """Tray callback: change UI scale, persist, and rebuild on the UI thread."""
        self.scale = scale
        Config.apply_scale(scale)
        self._cosmic_on = self._cosmic_off = None  # force re-render at the new size
        self._save_config()
        self.root.after(0, self._rebuild_all)
        print(f"[Scale] {int(scale*100)}%")

    def _rebuild_all(self):
        self._build_shell()
        if self.game_active and self.enemy_data_cache:
            # Keep this game's timers / cosmic / TP toggles (state is not in the widgets).
            self._build_enemy_rows(list(self.enemy_data_cache.values()), reset_state=False)
        self.root.geometry(f"+{self.saved_x}+{self.saved_y}")
        self._apply_topmost()

    def get_haste(self, champ_name: str) -> int:
        """Returns effective summoner-spell haste for a champion:
        item haste (auto, from API) + Cosmic Insight (+18) if the user toggled it on.
        """
        data = self.enemy_data_cache.get(champ_name, {})
        haste = data.get('haste', 0)
        if self.cosmic_toggle.get(champ_name):
            haste += Config.COSMIC_HASTE
        return haste

    def get_ability_haste(self, champ_name: str) -> int:
        """Ability Haste (for R) = sum of AH from the enemy's items (auto).
        Note: rune/other AH (e.g. Transcendence) isn't exposed -> may undercount."""
        return self.enemy_data_cache.get(champ_name, {}).get('ability_haste', 0)

    def rank_from_level(self, champ_name: str) -> int:
        """Estimate ultimate rank from the enemy's current level (R at 6/11/16).
        Players almost always level R on cooldown, so this is a good heuristic.
        Returns 0 if the ult isn't unlocked yet (< level 6)."""
        return _rank_from_level(self.enemy_data_cache.get(champ_name, {}).get('level', 1))

    def teleport_base_cd(self, champ_name: str) -> float:
        """Native TP base CD: 360s before 10:00, then Unleashed (level-scaled;
        top laner uses the role-quest range). See timer_core.teleport_cd."""
        data = self.enemy_data_cache.get(champ_name, {})
        return teleport_cd(self.clock.now(), data.get('level', 1), data.get('position') == 'TOP')

    def register_timer(self, widget: "SpellTimerWidget"):
        self._timer_widgets.append(widget)

    def _refresh_timers(self):
        for w in self._timer_widgets:
            w.refresh()

    def _ui_tick(self):
        """Single UI loop: redraw timers from the model + apply the in-game lock."""
        if self.game_active:
            self._refresh_timers()
            self._update_lock()
        self.root.after(Config.UI_TICK, self._ui_tick)

    def _on_wheel(self, event):
        w = self.root.winfo_containing(event.x_root, event.y_root)
        if isinstance(w, SpellTimerWidget) and event.delta:
            notches = max(1, abs(event.delta) // 120)
            sign = 1 if event.delta > 0 else -1   # up = ready later, down = earlier
            w.adjust(sign * notches * Config.WHEEL_STEP)

    # --- In-game lock ---
    def _update_lock(self):
        if Config.DEBUG_DUMMY:
            # Log foreground changes so a wrong GAME_WINDOW_CLASS / TITLE is easy to spot.
            fg = _Win32.describe_foreground()
            if fg and fg[0] != self._last_fg:
                self._last_fg = fg[0]
                print(f"[Lock] foreground class={fg[1]!r} title={fg[2]!r}")
        self._set_locked(self.lock_over_game and _Win32.game_foreground_on_same_monitor(self.root))

    def _set_locked(self, locked: bool):
        if locked == self._locked: return
        self._locked = locked
        print(f"[Lock] {'locked (game focused)' if locked else 'unlocked'}")
        try:
            self.root.wm_attributes("-disabled", locked)
        except tk.TclError:
            pass  # non-Windows
        self._update_lock_visual()

    def _update_lock_visual(self):
        if self.container is not None:
            self.container.config(bg=Config.COLOR_GOLD_DIM if self._locked else Config.COLOR_GOLD)

    def _toggle_lock(self, icon=None, item=None):
        self.lock_over_game = not self.lock_over_game
        self._save_config()
        if not self.lock_over_game:
            self.root.after(0, lambda: self._set_locked(False))
        print(f"[Lock] {'ON' if self.lock_over_game else 'OFF'}")

    def _set_display_mode(self, mode: str):
        self.display_mode = mode
        self._save_config()
        self.root.after(0, self._refresh_timers)
        print(f"[Display] {mode}")

    def _setup_tray(self):
        def quit_app(icon, item):
            print("[Tray] Quitting...")
            self._save_config()
            icon.stop()
            self.root.quit()
            sys.exit(0)

        custom_icon = resource_path("ico/icon.ico")
        flash_icon = resource_path("assets/spells/SummonerFlash.png")
        
        image = None
        if os.path.exists(custom_icon):
            try:
                image = Image.open(custom_icon)
            except: pass
            
        if image is None and os.path.exists(flash_icon):
            image = Image.open(flash_icon)
            
        if image is None:
            image = Image.new('RGB', (64, 64), color=(255, 255, 0))

        def make_scale_item(pct):
            val = pct / 100.0  # closed over below; keep lambdas within pystray's argcount limit
            return pystray.MenuItem(
                f"{pct}%",
                lambda icon, item: self._set_scale(val),
                checked=lambda item: abs(self.scale - val) < 1e-6,
                radio=True,
            )
        scale_menu = pystray.Menu(*[make_scale_item(p) for p in (50, 75, 100, 125, 150, 175, 200)])

        def make_display_item(label, mode):
            return pystray.MenuItem(
                label,
                lambda icon, item: self._set_display_mode(mode),
                checked=lambda item: self.display_mode == mode,
                radio=True,
            )
        display_menu = pystray.Menu(
            make_display_item("Ready time (14:25)", "ready"),
            make_display_item("Countdown", "countdown"),
        )

        items = [
            pystray.MenuItem(
                "Always on Top",
                self._toggle_topmost,
                checked=lambda item: self.is_topmost,
            ),
            pystray.MenuItem(
                "Lock while game focused",
                self._toggle_lock,
                checked=lambda item: self.lock_over_game,
            ),
            pystray.MenuItem("Display", display_menu),
            pystray.MenuItem("Scale", scale_menu),
            pystray.MenuItem("Quit", quit_app),
        ]
        if Config.ASSETS_OUTDATED:
            local, latest = Config.ASSETS_OUTDATED
            items.insert(0, pystray.MenuItem(
                f"Assets outdated: {local} -> {latest} (run download_assets.py)",
                lambda icon, item: None, enabled=False))
        menu = pystray.Menu(*items)
        self.tray_icon = pystray.Icon("DeskTimer", image, "DeskTimer", menu)
        
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _load_config(self):
        if os.path.exists(Config.CONFIG_FILE):
            try:
                with open(Config.CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.saved_x = data.get('x', 0)
                    self.saved_y = data.get('y', 0)
                    self.is_pinned = data.get('pinned', False)
                    self.is_topmost = data.get('topmost', True)
                    self.scale = float(data.get('scale', 1.0))
                    if data.get('display_mode') in ("ready", "countdown"):
                        self.display_mode = data['display_mode']
                    self.lock_over_game = data.get('lock_over_game', True)
                    self.reaction_delay = float(data.get('reaction_delay', Config.REACTION_DELAY))
                    self.late_offset = float(data.get('late_offset', Config.LATE_OFFSET))
                    print(f"[Config] Loaded: Pos({self.saved_x},{self.saved_y}), Pinned({self.is_pinned}), Topmost({self.is_topmost}), Scale({self.scale})")
            except Exception as e:
                print(f"[Config] Load error: {e}")
        else:
            sw = self.root.winfo_screenwidth()
            self.saved_x = sw - 250
            self.saved_y = 100

    def _save_config(self):
        data = {
            'x': self.saved_x,
            'y': self.saved_y,
            'pinned': self.is_pinned,
            'topmost': self.is_topmost,
            'scale': self.scale,
            'display_mode': self.display_mode,
            'lock_over_game': self.lock_over_game,
            'reaction_delay': self.reaction_delay,
            'late_offset': self.late_offset,
        }
        try:
            with open(Config.CONFIG_FILE, 'w') as f:
                json.dump(data, f)
            print("[Config] Settings saved.")
        except Exception as e:
            print(f"[Config] Save error: {e}")

    def _graceful_exit(self, signum, frame):
        print("\n[DeskTimer] Stopping...")
        self._save_config()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
        self.root.destroy()
        sys.exit(0)

    def _apply_topmost(self):
        # Only the "-topmost" attribute; window keeps border / taskbar / opacity.
        try:
            self.root.wm_attributes("-topmost", bool(self.is_topmost))
        except Exception as e:
            print(f"[Topmost] apply failed: {e}")

    def _toggle_topmost(self, icon=None, item=None):
        # Called from the pystray thread -> marshal the Tk call onto the UI thread.
        self.is_topmost = not self.is_topmost
        self.root.after(0, self._apply_topmost)
        self._save_config()
        print(f"[Topmost] {'ON' if self.is_topmost else 'OFF'}")

    def _toggle_pin(self, event):
        self.is_pinned = not self.is_pinned
        self._update_pin_visual()
        self._save_config()

    def _update_pin_visual(self):
        if self.is_pinned:
            self.handle.config(text="🔒 PINNED", fg=Config.COLOR_PINNED, cursor="arrow")
        else:
            self.handle.config(text="::::", fg=Config.COLOR_HANDLE, cursor="fleur")

    def _monitor_game_loop(self):
        data = GameDataManager.fetch_data()
        if data:
            enemies = GameDataManager.parse_enemies(data)
            game_time = (data.get("gameData") or {}).get("gameTime")
            if game_time is not None:
                self.clock.sync(game_time)
        elif Config.DEBUG_DUMMY:
            # Offline UI testing: no live game, show dummy enemies; fake clock from 10:00.
            enemies = GameDataManager._get_dummy_data()
            if self._debug_t0 is None:
                self._debug_t0 = time.monotonic()
            self.clock.sync(600 + time.monotonic() - self._debug_t0)
        else:
            enemies = None

        if enemies is not None:
            # 1. Update cache with fresh data (items/haste)
            for enemy in enemies:
                self.enemy_data_cache[enemy['champ']] = enemy

            # 2. Build UI only when data first appears
            if not self.game_active:
                print("[DeskTimer] Data found, showing window.")
                self._build_enemy_rows(enemies)
                self.root.deiconify()
                self.root.geometry(f"+{self.saved_x}+{self.saved_y}")
                self._apply_topmost()
                self.game_active = True

            # NOTE: We do NOT rebuild UI in loop to preserve running timers.
            # Haste data is fetched from cache dynamically on click.

        else:
            if self.game_active:
                print("[DeskTimer] Data lost, hiding window.")
                self._set_locked(False)
                self.root.withdraw()
                self._save_config()
                self.game_active = False
                self.enemy_data_cache.clear()
                self.cosmic_toggle.clear()
                self.tp_shown.clear()
                self.timers.clear()
                self.clock.reset()

        self.root.after(Config.CHECK_INTERVAL, self._monitor_game_loop)

    def _ensure_cosmic_images(self):
        if self._cosmic_on is None:
            self._cosmic_on, self._cosmic_off = AssetManager.load_toggle_pair(
                "runes", "CosmicInsight", (Config.EYE_SIZE, Config.EYE_SIZE))

    def _build_enemy_rows(self, enemies: List[Dict], reset_state: bool = True):
        # reset_state=True on game start (new game -> fresh timers / modifiers);
        # False on a scale rebuild (keep this game's timers / cosmic / TP toggles).
        self._timer_widgets.clear()
        for widget in self.enemies_frame.winfo_children(): widget.destroy()
        self._img_refs.clear()
        prev_tp_shown = {} if reset_state else dict(self.tp_shown)
        if reset_state:
            self.timers.clear()
            self.cosmic_toggle.clear()
        self.tp_shown.clear()
        self._tp_widgets.clear()
        self._eye_widgets.clear()

        if not enemies: return
        self._ensure_cosmic_images()

        s = Config.s
        for i, enemy in enumerate(enemies):
            if i > 0 and Config.SHOW_SEPARATOR:
                sep = tk.Frame(self.enemies_frame, bg=Config.COLOR_SEPARATOR, height=s(1))
                sep.pack(fill="x", padx=s(10), pady=s(2))

            row = tk.Frame(self.enemies_frame, bg=Config.COLOR_BG)
            row.pack(fill="x", pady=s(Config.ROW_PADDING_Y))

            champ = enemy['champ']
            champ_icon = AssetManager.load_icon("champions", champ, (Config.ICON_SIZE, Config.ICON_SIZE), is_round=True)
            self._img_refs.append(champ_icon)
            lbl = tk.Label(row, image=champ_icon, bg=Config.COLOR_BG, bd=0)
            lbl.pack(side="left", padx=(0, s(8)))
            # Right-click the portrait: manually add/remove the Unleashed TP button
            # (fallback for blind pick / modes where API 'position' is empty).
            lbl.bind("<Button-3>", lambda e, c=champ: self._toggle_tp(c))

            # --- Ultimate (R): icon from DDragon, CD by rank(level), Ability Haste from items ---
            r_info = AbilityData.r_info(champ)
            if r_info and r_info.get('cd'):
                r_icon = os.path.splitext(r_info['icon'])[0]  # e.g. "SeraphineR"
                rw = SpellTimerWidget(row, champ, "R", "R", self, icon_name=r_icon,
                                      folder="abilities", r_cds=r_info['cd'],
                                      use_ability_haste=True)
                rw.pack(side="left", padx=(0, s(6)))
                self._img_refs.append(rw.icon_img)
                self._img_refs.append(rw.dim_img)

            for slot, s_name in (("S1", enemy['spell1']), ("S2", enemy['spell2'])):
                # Pass 'self' (app) reference so the button can query cache
                sw = SpellTimerWidget(row, champ, s_name, slot, self)
                sw.pack(side="left", padx=s(3))
                self._img_refs.append(sw.icon_img)
                self._img_refs.append(sw.dim_img)

            # --- Unleashed Teleport (top-lane role quest reward), created always,
            #     packed only when applicable; toggle preserves running timers. ---
            has_tp = "SummonerTeleport" in (enemy['spell1'], enemy['spell2'])
            is_top = enemy.get('position') == 'TOP'
            tp_widget = SpellTimerWidget(row, champ, "SummonerTeleport", "UTP", self,
                                         base_cd=Config.UNLEASHED_TP_CD, icon_name="SummonerTeleport")
            self._tp_widgets[champ] = tp_widget
            self._img_refs.append(tp_widget.icon_img)
            self._img_refs.append(tp_widget.dim_img)

            # --- Cosmic Insight toggle (far right, small). Off by default. ---
            eye_img = self._cosmic_on if self.cosmic_toggle.get(champ) else self._cosmic_off
            eye = tk.Label(row, image=eye_img, bg=Config.COLOR_BG, bd=0, cursor="hand2")
            eye.pack(side="left", padx=(s(8), 0))
            eye.bind("<Button-1>", lambda e, c=champ: self._toggle_cosmic(c))
            self._eye_widgets[champ] = eye

            # Auto-show Unleashed TP for the top laner who did NOT pick TP
            # (on a rebuild, keep whatever the user had toggled).
            show_tp = prev_tp_shown.get(champ, is_top and not has_tp)
            if show_tp:
                tp_widget.pack(side="left", padx=s(3), before=eye)
                self.tp_shown[champ] = True
            else:
                self.tp_shown[champ] = False

    def _toggle_cosmic(self, champ: str):
        on = not self.cosmic_toggle.get(champ, False)
        self.cosmic_toggle[champ] = on
        eye = self._eye_widgets.get(champ)
        if eye is not None:
            eye.config(image=self._cosmic_on if on else self._cosmic_off)
        print(f"[Cosmic] {champ}: {'+18' if on else 'off'}")

    def _toggle_tp(self, champ: str):
        w = self._tp_widgets.get(champ)
        eye = self._eye_widgets.get(champ)
        if w is None or eye is None: return
        if self.tp_shown.get(champ):
            w.pack_forget()
            self.tp_shown[champ] = False
        else:
            w.pack(side="left", padx=Config.s(3), before=eye)  # keep TP left of the eye toggle
            self.tp_shown[champ] = True
        print(f"[TP] {champ}: {'shown' if self.tp_shown[champ] else 'hidden'}")

    def _start_drag(self, event):
        if self.is_pinned: return 
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _do_drag(self, event):
        if self.is_pinned: return
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        
        self.root.geometry(f"+{x}+{y}")
        self.saved_x = x
        self.saved_y = y

    def run(self):
        self.root.mainloop()

def _enable_dpi_awareness():
    """Make the process DPI-aware BEFORE Tk() so Windows renders at native pixels
    (crisp) instead of bitmap-stretching the window on HiDPI / display scaling.
    Tries newest API first, falls back for older Windows."""
    try:
        # Per-Monitor v2 (Windows 10 1703+): DPI_AWARENESS_CONTEXT = -4
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor (Win 8.1+)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()        # system-DPI (Vista+)
    except Exception:
        pass

if __name__ == "__main__":
    checker = SingleInstanceChecker()
    if checker.is_already_running():
        sys.exit(0)

    _enable_dpi_awareness()
    DDragonManager.update_timers()
    AbilityData.load()
    app = OverlayApp()
    app.run()