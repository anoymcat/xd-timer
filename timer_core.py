"""计时核心：纯 Python，不依赖 tkinter / Win32，便于离线单元测试。

- GameClock  : 游戏内时间（API 的 gameData.gameTime），两次轮询之间按本地单调时钟插值。
- TimerModel : (英雄, 槽位) -> 就绪时刻（游戏时间，秒）。UI 只读它来渲染，
               所以重建窗口（改缩放）不会丢计时。
- 若干 CD 计算 / 格式化函数。
"""
from __future__ import annotations
import math
import time
from typing import Dict, Optional, Tuple

# --- Teleport (patch 26.19, 2026-09-23) ---
# 原生 TP：10:00 前 360s；10:00 起升级为 Unleashed Teleport，CD 随等级 330→240。
# 上单（任务强化）的 Unleashed Teleport：300→210（26.19 由 330→240 下调）。
# 等级插值按 1→18 线性处理 [需核实：游戏内 tab 悬浮可见真实值]。
TP_BASE_CD = 360
TP_UNLEASH_TIME = 600
TP_UNLEASHED_CD = (330, 240)
TP_UNLEASHED_CD_TOP = (300, 210)


class GameClock:
    """API 每 2s 才给一次 gameTime；两次之间用 monotonic 插值，并限制最多外推
    max_extrapolate 秒（游戏暂停 / 接口卡住时不会一直往前跑）。"""

    def __init__(self, max_extrapolate: float = 3.0, monotonic=time.monotonic):
        self._t: Optional[float] = None
        self._mono = 0.0
        self._max = max_extrapolate
        self._monotonic = monotonic

    def sync(self, game_time: float):
        self._t = float(game_time)
        self._mono = self._monotonic()

    def reset(self):
        self._t = None

    @property
    def synced(self) -> bool:
        return self._t is not None

    def now(self) -> float:
        if self._t is None:
            return 0.0
        dt = min(max(0.0, self._monotonic() - self._mono), self._max)
        return self._t + dt


class TimerModel:
    """key = (champ, slot)，slot 如 "S1" / "S2" / "R" / "UTP"。值 = 就绪时刻（游戏秒）。"""

    def __init__(self):
        self._ready: Dict[Tuple[str, str], float] = {}

    def start(self, key, cooldown: float, used_at: float):
        self._ready[key] = used_at + cooldown

    def adjust(self, key, delta: float):
        if key in self._ready:
            self._ready[key] += delta

    def reset(self, key):
        self._ready.pop(key, None)

    def clear(self):
        self._ready.clear()

    def is_active(self, key) -> bool:
        return key in self._ready

    def ready_at(self, key) -> Optional[float]:
        return self._ready.get(key)

    def remaining(self, key, now: float) -> Optional[float]:
        r = self._ready.get(key)
        return None if r is None else r - now


def apply_haste(base_cd: float, haste: float) -> float:
    """实际CD = 基础CD × 100 / (100 + 急速)。"""
    if haste <= 0:
        return float(base_cd)
    return base_cd * 100.0 / (100.0 + haste)


def rank_from_level(level: int) -> int:
    """大招等级按 6/11/16 估算；<6 返回 0（还没大）。"""
    lvl = level or 1
    if lvl >= 16: return 3
    if lvl >= 11: return 2
    if lvl >= 6:  return 1
    return 0


def level_scaled(start: float, end: float, level: int) -> float:
    """等级 1→18 线性插值。"""
    lvl = min(max(int(level or 1), 1), 18)
    return start + (end - start) * (lvl - 1) / 17.0


def teleport_cd(game_time: float, level: int, is_top: bool) -> float:
    """原生 TP 的基础 CD（未计急速）。"""
    if game_time < TP_UNLEASH_TIME:
        return float(TP_BASE_CD)
    start, end = TP_UNLEASHED_CD_TOP if is_top else TP_UNLEASHED_CD
    return level_scaled(start, end, level)


def fmt_countdown(remaining: float) -> str:
    """倒计时：>=60s 显示 m:ss，否则显示秒数（向上取整，0.2s 也显示 1）。"""
    sec = max(0, math.ceil(remaining))
    if sec >= 60:
        m, s = divmod(sec, 60)
        return f"{m}:{s:02}"
    return str(sec)


def fmt_clock(game_time: float) -> str:
    """报点时间：游戏时钟 mm:ss（向上取整：时钟显示到这一秒时技能已就绪）。"""
    sec = max(0, math.ceil(game_time))
    m, s = divmod(sec, 60)
    return f"{m}:{s:02}"
