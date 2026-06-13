# DeskTimer — 开发说明

> 跑在副屏的《英雄联盟》召唤师技能 CD 计时器。普通桌面窗口，数据来自官方本地 API，手动触发。
> 本文件是跨机器接续开发的上下文锚点：随 git 走，换机 `git clone` 即可恢复关键决策。

## 1. 项目概述

基于参考项目 `lovelybbq/lol-spell-timer`（Python / tkinter）改造而来：去掉其 overlay（无边框 + 置顶 + 半透明），改成**普通副屏窗口**，跑源码、不打包。自用，不对外分发。

**免责定位**：不用于腾讯运营服务器（国服），仅海外 Riot 官方环境。详见 `README.md` 免责声明。

## 2. 当前状态（均已落地并验证）

- ✅ 普通桌面窗口（已移除全部 overlay 行为）。
- ✅ 数据管线实测通过：2999 API 可读、敌我分队正确、敌方英雄→DDragon 英文头像映射正确、召唤师技能识别正确。
- ✅ localhost 2999 代理绕过、命名中性化、离线调试开关、桌面快捷方式 + 自定义图标。
- ✅ 已提交私有仓库 `anoymcat/xd-timer`。
- ⏳ 未实测：真实"靴子 haste"套用（测试时 AI 未出明朗之靴；公式与逻辑已确认）。

## 3. 架构与关键实现

### 数据源
- `https://127.0.0.1:2999/liveclientdata/allgamedata`，`verify=False`，每 2s 轮询（`GameDataManager`）。
- **localhost 必须绕过系统代理**：`fetch_data` 传 `proxies={"http": None, "https": None}`。若机器走 VPN/代理，127.0.0.1 会被劫持导致连接失败。DDragon（外网）请求**保持**走系统代理。
- 敌我判断：用 `activePlayer.summonerName` 在 `allPlayers` 中匹配队伍（含 Riot tagline，如 `内向腼腆#74139`），排除同队即敌方。
- 英雄名：`rawChampionName`（如 `game_character_displayname_Qiyana`）→ `split("_")[-1]` → DDragon 英文 key → 头像。`championName` 为中文，仅作 fallback。
- 召唤师技能：`summonerSpells` 的 `rawDisplayName`（英文 key）经 `_clean_spell_name` 关键词匹配。

### CD 计算
- 公式：`实际CD = 基础CD × 100 / (100 + 召唤师技能急速)`。
- haste **仅来自装备靴子**：`3158→10`、`3171→20`、`223158→10`（Arena）。**不计星界洞悉**（合规接口读不到敌方符文）。
- 基础 CD 启动时由 `DDragonManager` 从 `summoner.json` 拉取覆盖硬编码值。闪现 = 300s。

### 窗口（已去 overlay）
- 普通 tkinter 窗口：有标题栏、进任务栏、不置顶。
- 已移除：`overrideredirect(True)`、`wm_attributes("-topmost")`、`wm_attributes("-alpha")`；以及第二处 Win32 置顶 `_apply_native_styles` / `WS_EX_TOPMOST | WS_EX_NOACTIVATE`。
- 保留：自定义拖动把手、pin、`config.json` 记忆位置、系统托盘退出、单实例 mutex。
- `DEBUG_DUMMY`（环境变量 `DESKTIMER_DEBUG=1`）：无对局时也显示 dummy 敌方，便于离线调试窗口形态。

### 触发
- 窗口内左键点图标计时、右键重置。**无全局键盘钩子**。

## 4. 设计约束（安全 / 合规）

- 仅用官方本地 API；**不**读内存、注入、挂钩、截屏、发送输入。
- 普通窗口，不盖在游戏上。
- **跑源码，不打包 exe**（避免未签名 exe 被杀软误报 / 特征匹配）。
- 进程（`pythonw.exe`）、窗口标题、托盘、mutex 命名均中性。
- 不用于腾讯服务器；自用、不分发。

## 5. 文件结构

| 文件 | 作用 |
|---|---|
| `main.py` | 主程序（数据轮询 + UI + 计时） |
| `download_assets.py` | 从 DDragon 下载英雄/技能图标到 `assets/` |
| `make_icon.py` | 程序化生成应用图标 `ico/icon.ico` |
| `start.bat` | 启动器（`pythonw` 无黑窗，`%~dp0` 可移植） |
| `setup.bat` / `requirements.txt` | 环境（requests / urllib3 / Pillow / pystray） |
| `ico/icon.ico` | 应用图标（桌面快捷方式用） |
| `assets/`、`venv/`、`config.json` | 运行时生成，已 gitignore |

## 6. 运行环境

- Windows + Anaconda Python（本机在 `E:\Anaconda3`，注意系统 `python` 是 Microsoft Store 占位符，不可用）。
- venv 由 Anaconda python 创建：`E:\Anaconda3\python.exe -m venv venv`。
- 桌面快捷方式 `DeskTimer.lnk` → `venv\Scripts\pythonw.exe main.py`，工作目录为项目根。

## 7. 精度局限（已接受）

- 敌方带星界洞悉（+18）时，本工具算出的 CD **偏长**（敌方闪现实际比显示更早回来，偏"假安全"）。
- 传送 CD 随等级/游戏时间变化，当前按定值处理。

## 8. 许可

- 参考项目 `lovelybbq/lol-spell-timer` **无 LICENSE**（= 保留所有权利）。本项目复制并改造其代码，**仅自用、不对外分发**（仓库为私有）。
