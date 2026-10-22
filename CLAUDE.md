# DeskTimer — 开发说明

> 《英雄联盟》召唤师技能 / 大招 CD 计时器。普通桌面窗口（可放副屏，也可放主屏游戏之上并在游戏前台时自动禁用），数据来自官方本地 API，手动触发。
> 本文件是跨机器接续开发的上下文锚点：随 git 走，换机 `git clone` 即可恢复关键决策。

## 1. 项目概述

基于参考项目 `lovelybbq/lol-spell-timer`（Python / tkinter）改造而来：去掉其 overlay（无边框 + 置顶 + 半透明），改成**普通副屏窗口**；之后按需加回了置顶和半透明，仍不做无边框、点击穿透（见 §3 窗口）。跑源码、不打包。自用，不对外分发。

**免责定位**：不用于腾讯运营服务器（国服），仅海外 Riot 官方环境。详见 `README.md` 免责声明。

## 2. 当前状态（均已落地并验证）

- ✅ 普通桌面窗口：有标题栏、进任务栏；不做无边框 / 点击穿透 / 不激活。
- ✅ 数据管线实测通过：2999 API 可读、敌我分队正确、敌方英雄→DDragon 英文头像映射正确、召唤师技能识别正确。
- ✅ localhost 2999 代理绕过、命名中性化、离线调试开关、桌面快捷方式 + 自定义图标。
- ✅ 已提交私有仓库 `anoymcat/xd-timer`。
- ✅ 头像加载修复：`rawChampionName` 存在两种格式，改用 `_resolve_champ_name` 解析（见 §3）。
- ✅ 置顶可开关（默认开，托盘切换，存 config）。
- ✅ 星界洞悉手动开关（每敌 +18，眼睛图标切换）+ 上单附赠 Unleashed Teleport 自动/手动按钮（26.19 起 390s）。
- ✅ DPI 感知 + 托盘比例缩放（50–200%）+ 海克斯金双线边框。
- ✅ 大招（R）计时：R 图标 + 按等级估基础 CD + 自动吃装备 Ability Haste（见 §3 大招 R CD）。托盘 "Ultimate (R) Timer" 可开关，存 `show_r`（默认开，切换走 `_rebuild_all`，R 计时保留在 `TimerModel`）。从未合并的 `feat/calibration-and-r-toggle` 分支移植；该分支的 `−20s` 按钮已被 Shift+左键 / 滚轮补记取代，没有移植。
- ✅ 计时状态模型（`timer_core.py`）：按游戏时间（`gameData.gameTime`）计时；改缩放不再丢计时 / 星界 / TP 开关。单元测试 `tests/`。
- ✅ 显示方式：报点时间（就绪时刻，如 14:25，默认）/ 倒计时，托盘切换。
- ✅ 补记：左键自动回溯 3s、Shift+左键回溯 20s、滚轮 ±5s。
- ✅ 原生 TP 按游戏时间 + 等级算 CD；上单任务 TP 改 390s（26.19）。
- ✅ 资源过期提示（`assets/version.txt` vs DDragon 最新版，托盘显示）。
- ✅ 游戏前台自动禁用实测通过（2026-10-21，Windows + 自定义对局）：窗口识别规则命中，游戏前台锁定、Alt-Tab 解锁均正常。
- ✅ 主屏外观（2026-10-21，用户选方案 B）：`-alpha` 半透明（托盘 Opacity，默认 80%，**不**点击穿透）+ DWM 深蓝标题栏 / 金色边框 + 紧凑布局（托盘 Compact layout，默认开）+ 冷却扇形遮罩。调试模式截图确认，**待进游戏实测**。
- ✅ `download_assets.py`：图片只补缺失，JSON 每次重建，`--force` 全量重下。
- ⚠️ 正式对局中锁定未生效（点窗口会计时、QWER 失灵；2026-10-21 用户反馈）。自定义对局实测是正常的。疑似原因（未证实）：正式对局中轮询偶发失败 → 旧逻辑立即判定对局结束、隐藏窗口，下一次成功又 `deiconify` 重新显示；`deiconify` 会激活本窗口、抢走游戏焦点（前台不再是游戏 → 解锁），同时清空计时。2026-10-22 已改为连续 `MISS_LIMIT=3` 次失败才判定结束。待正式对局复测；若仍复现，看 `DESKTIMER_DEBUG=1` 下有无 `Poll missed` / `Data found` 反复出现，以及 `[Lock]` 日志。
- ⏳ 未实测：TP 等级插值是否与游戏内 tooltip 一致。
- ⏳ 未实测：真实"靴子 haste"套用（测试时 AI 未出明朗之靴；公式与逻辑已确认）。

## 3. 架构与关键实现

### 数据源
- `https://127.0.0.1:2999/liveclientdata/allgamedata`，`verify=False`，每 2s 轮询（`GameDataManager`），超时 0.5s（轮询在 UI 线程）。连续 `MISS_LIMIT=3` 次失败才判定对局结束并隐藏窗口；单次失败不动窗口，避免清空计时和 `deiconify` 抢焦点。
- **游戏时间**：`gameData.gameTime`（秒）每次轮询喂给 `GameClock.sync`；两次轮询之间按本地单调时钟插值，最多外推 3s（游戏暂停时不会一直往前跑）。所有计时以它为准。
- **localhost 必须绕过系统代理**：`fetch_data` 传 `proxies={"http": None, "https": None}`。若机器走 VPN/代理，127.0.0.1 会被劫持导致连接失败。DDragon（外网）请求**保持**走系统代理。
- 敌我判断：用 `activePlayer.summonerName` 在 `allPlayers` 中匹配队伍（含 Riot tagline，如 `内向腼腆#74139`），排除同队即敌方。
- **英雄名（`_resolve_champ_name`）**：`rawChampionName` 实测有**两种格式**——`Character_Seraphine_Name`（key 在中间，对局中敌方实际格式）和 `game_character_displayname_Seraphine`（key 在末尾，早期测试格式）。**不能死取 `split("_")[-1]`**（会取到 `Name` → 头像加载失败）。现逻辑：在各段中匹配一个"已知英雄 key"（= `assets/champions/` 已下载文件名，`AssetManager.champion_keys()`），两种格式都命中，并带结构化兜底。
- 召唤师技能：`summonerSpells` 的 `rawDisplayName`（英文 key）经 `_clean_spell_name` 关键词匹配。
- **`position` 可用**：`allPlayers[].position` = `TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY`（排位/征召可靠；盲选/练习可能为空）。用于自动识别上单（附赠 TP）。
- **`level` 可用**：`allPlayers[].level`（每 2s 刷新）→ 估算大招等级。
- **敌方符文只暴露 keystone + 主副系**（`allPlayers[].runes` 无小符文）。星界洞悉是小符文 → **读不到**，只能手动开关。仅 `activePlayer.fullRunes` 有自己的小符文。
- **敌方无 `championStats`**：拿不到敌方总 AH（只有 `activePlayer.championStats.abilityHaste` 是自己的）→ 大招 AH 只能从 `items` 反推（漏符文 AH）。

### CD 计算
- 公式：`实际CD = 基础CD × 100 / (100 + 召唤师技能急速)`。
- **有效急速 = 靴子急速（API 自动） + 星界洞悉（手动 +18）**（`get_haste`）。靴子：`3158→10`、`3171→20`、`223158→10`（Arena），从 `items` 读。
- **星界洞悉（`COSMIC_HASTE=18`）**：接口读不到敌方小符文，故做**每敌手动开关**——行尾一个星界洞悉眼睛图标（`assets/runes/CosmicInsight.png`，来自 CommunityDragon），左键点亮 = 该敌全部技能 +18。复现游戏内 tab tooltip（闪现 300/1.18=254.24s）。
- **原生 TP（`timer_core.teleport_cd`）**：10:00 前 360s；10:00 起升级为 Unleashed Teleport，CD 按等级 330→240，上单（`position=="TOP"`）用任务强化后的 300→210（26.19）。等级插值按 1→18 线性 [需核实]；上单在 10:00 前完成任务时的强化未建模。
- **上单附赠 Unleashed Teleport（`UNLEASHED_TP_CD=390`，26.19 由 420 下调）**：2026 上单任务奖励。若上单**没**原生 TP → 自动加第 3 个 TP 按钮（390s 定值，不随等级）；若**有**原生 TP → 任务只强化（加护盾），不加按钮。`position=="TOP"` 自动判定；盲选等 position 为空时**右键英雄头像**手动加/减（`_toggle_tp`，用 pack/pack_forget 不重建、保住计时）。
- 基础 CD 启动时由 `DDragonManager` 从 `summoner.json` 拉取覆盖硬编码值。闪现 = 300s。
- `SpellTimerWidget` 支持 `base_cd`（绕过 `SPELL_TIMERS`，用于 390）+ `icon_name` + `folder` + `r_cds` + `use_ability_haste`。

### 计时状态与显示（`timer_core.py`）
- `TimerModel`：`(英雄, 槽位)` → 就绪时刻（游戏秒）+ 总 CD，槽位 = `S1` / `S2` / `R` / `UTP`。控件不存状态，`OverlayApp._ui_tick`（每 200ms）统一按模型重绘，所以重建窗口不丢计时。
- **冷却遮罩**：图标上的暗色扇形随剩余比例（`TimerModel.fraction`）从 12 点方向顺时针收缩，同游戏内；两种显示模式都有（报点模式的数字本身不动，靠遮罩看出在走）。`sweep_step` 分 60 档，`AssetManager.sweep_layer` 按 (尺寸, 档) 缓存 PIL 生成的 RGBA 图。补记 / 滚轮只移就绪时刻，总 CD 不变（推迟超过总 CD 时遮罩封顶为满）。
- 显示方式（`config.json` 的 `display_mode`，托盘 Display 切换）：`ready` = 就绪时刻（游戏时钟 mm:ss，向上取整，符合聊天报点习惯），`countdown` = 剩余秒数。
- 补记（录入总比实际施放晚）：左键 = 现在 − `reaction_delay`（默认 3s）；Shift+左键 = 现在 − `late_offset`（默认 20s，打完团才想起来）；运行中的计时器上滚轮每格 ±5s（上 = 推迟，下 = 提前）；右键重置。前两个值可在 `config.json` 改。滚轮用 `bind_all` + `winfo_containing` 分发到指针下的控件。
- `timer_core.py` 不依赖 tkinter / Win32，测试：`python -m unittest discover -s tests`。

### 大招（R）CD
- **两种急速不能混**：召唤师技能吃「召唤师技能急速」（靴子/星界洞悉）；大招吃「技能急速 Ability Haste」（装备/符文），是**另一套数值**。代码里 `get_haste`（召唤师）与 `get_ability_haste`（大招）分开。
- 每个敌人头像右侧加一个 **R 按钮**（`AbilityData.r_info` 有数据才加）：
  - **基础 CD 按等级估**：点击时读敌方**实时** `level`，`rank_from_level` 映射 6/11/16 → 1/2/3 级（<6 不触发）。玩家几乎必到点点 R，够准。
  - **Ability Haste 自动读装备**：敌方 `items` 的 itemID → `item_ah.json` 求和（`parse_enemies` 里算进 `ability_haste`）。
  - 公式同：`R实际CD = R基础[级] × 100 / (100 + AH)`。
- **数据来源（`download_assets.py` 阶段快照到本地，运行时不联网）**：
  - `assets/abilities/<R>.png`：R 图标（DDragon `championFull.json` 的 `spells[3].image.full`）。
  - `assets/abilities/r_index.json`：`{英雄key: {"icon": 文件, "cd": [1,2,3级]}}`。
  - `assets/abilities/item_ah.json`：`{itemId: abilityHaste}`（**Meraki** 静态数据；DDragon/CDragon 不干净地暴露 AH）。
  - `AbilityData.load()` 在 `__main__` 里读这两份 JSON；缺文件则自动降级（不加 R 按钮）。
- **局限**：① 符文/其它 AH（超然 +5 等）读不到 → 少算、CD 偏长；② 重置/充能/变身类大招（诺手/卡特/沃利贝尔…）不符合 base×haste 模型，倒计时不准。R 计时器对**固定 CD 团战大招**最有用。

### 窗口
- 普通 tkinter 窗口：有标题栏、进任务栏、**半透明**（见下）。可放副屏，也可拖到主屏游戏之上（游戏需无边框模式）。
- 已移除且**不再加回**：`overrideredirect(True)`；以及 Win32 的 `WS_EX_NOACTIVATE`、`_apply_native_styles`。
- **`-alpha` 已加回（2026-10-21，用户在三个方案中明确选了 B）**：托盘 Opacity 100/90/80/70/60%，默认 80%，存 `config.json` 的 `alpha`。只做半透明，**不**点击穿透：看得见下面的地面，但点击到不了游戏。代价：置顶 + 半透明 + 覆盖游戏比不透明窗口更接近 overlay 特征，被反作弊注意的风险高于原方案，用户已知悉。被否决的方案 C（`-alpha` + `WS_EX_TRANSPARENT` 点击穿透）与外部透视外挂窗口形态一致，**不做**。
- **标题栏配色（`_Dwm.style_title_bar`）**：对自身 `wm_frame()` hwnd 调 `DwmSetWindowAttribute`：深色模式（20，旧版 19）、标题栏色 35 = `COLOR_BG`、边框色 34 = `COLOR_GOLD`、标题文字色 36（34–36 需 Win11 22000+）。只改自己窗口，失败静默降级。每次显示窗口时（`_apply_window_attrs`）套用。
- **紧凑布局（托盘 "Compact layout"，默认开，存 `compact`）**：`Config.LAYOUTS` 两套基础尺寸——普通 38px 图标 / 22px 眼睛 / 有分隔线；紧凑 26px / 16px / 无分隔线 / 间距 ×0.5（`Config.g`）。再乘托盘缩放比例。两种布局都保留拖动把手（左键拖动、右键 pin，副屏上用得着），标题栏也能拖；pin 也可在托盘 "Pin position" 切换，pin 住时标题栏拖动后 300ms 弹回原位（`_on_configure`；不子类化窗口过程，所以挡不住拖动本身）。位置由 `<Configure>` 记录。窗口 `resizable(False, False)`。
- **`-topmost` 已加回**（可开关，默认开，状态存 `config.json` 的 `topmost` 字段）：托盘菜单 "Always on Top" 勾选切换（`_toggle_topmost` / `_apply_topmost`），显示窗口时（`deiconify` 后）套用。置顶只改自身窗口 Z 序、不接触游戏进程。
- **游戏前台自动禁用（`-disabled`，托盘 "Lock while game focused"，默认开，存 `lock_over_game`）**：放在主屏游戏之上时，非点击穿透的窗口被点到就会被激活、抢走游戏键盘焦点。故当游戏窗口在前台**且**本窗口与游戏在同一显示器时，用 Tk 自带 `wm_attributes("-disabled", True)` 禁用窗口：点击无响应、不抢焦点、不改计时（该区域的点击仍不会传给游戏）。Alt-Tab 出去（游戏不在前台）即恢复可点、可拖动。外线金边亮 = 可用，暗 = 禁用。
  - 检测只**读**窗口信息（`_Win32`：`GetForegroundWindow` + `GetClassNameW` / `GetWindowTextW` + `MonitorFromWindow`），不打开游戏进程、不改任何窗口样式；用轮询而非系统事件回调。游戏窗口识别：类名 `RiotWindowClass` 或标题 `League of Legends (TM) Client`（已实测命中）。任何失败都返回"未锁定"（= 旧行为）。`DESKTIMER_DEBUG=1` 时控制台会打印每次前台窗口切换的类名 / 标题，用于核对识别规则。
  - 窗口在副屏时不锁（不同显示器），保持直接点击的旧用法。
- 仍**不加**：`overrideredirect`、色键透明（`-transparentcolor`）、`WS_EX_NOACTIVATE`、`WS_EX_TOOLWINDOW`、点击穿透（`WS_EX_TRANSPARENT`）。半透明 + 置顶 + 点击穿透 + 覆盖游戏 = 外部透视外挂窗口的典型形态；现在已有前三项，点击穿透是最后一道线。
- pystray 回调在托盘线程，切换置顶经 `root.after(0, ...)` 回到 UI 线程执行。**注意 pystray MenuItem 的 action/checked lambda 参数个数 ≤2**（含默认参数也计数，超了启动即 `ValueError`；用闭包捕获值，别加 `v=val` 默认参）。
- 保留：自定义拖动把手、pin、`config.json` 记忆位置、系统托盘退出、单实例 mutex。
- `DEBUG_DUMMY`（环境变量 `DESKTIMER_DEBUG=1`）：无对局时也显示 dummy 敌方，便于离线调试窗口形态。

### 清晰度 / 缩放 / 边框
- **DPI 感知**：`_enable_dpi_awareness()` 在 `Tk()` **之前**调 `SetProcessDpiAwarenessContext(-4)`（Per-Monitor v2，带旧系统兜底）→ 原生像素渲染，避免 HiDPI 位图拉伸发虚。圆头像遮罩 4× 超采样抗锯齿；计时字体用像素制（负值）。
- **比例缩放**：托盘 `Scale` 子菜单 50/75/100/125/150/175/200%，存 `config.json` 的 `scale`。尺寸从当前布局（普通 / 紧凑，`Config.apply_layout`）的 `BASE_ICON_SIZE`/`BASE_EYE_SIZE` × scale + `Config.s(v)` / `Config.g(v)` 派生；切换 `_set_scale` / `_set_compact`→`_rebuild_all`（重建窗口；计时在 `TimerModel`、星界 / TP 开关在 app 上，`reset_state=False` 时均保留）。
- **海克斯金双线边框**：`_build_shell()` 用嵌套帧（父帧 bg 当"线"色，子帧 pack padx 露出）：金亮外线→深色护城河→暗金内线→深蓝面板。配色 `COLOR_GOLD`/`COLOR_GOLD_DIM`/`COLOR_MOAT`。真圆角/去标题栏需透明窗口那套 = overlay 特征，故不做，走矩形。

### 触发
- 窗口内左键点图标计时（Shift+左键 / 滚轮补记，见 §3 计时状态与显示）、右键重置。**无全局键盘钩子**。

## 4. 设计约束（安全 / 合规）

- 仅用官方本地 API；**不**读内存、注入、挂钩、截屏、发送输入。
- 普通窗口；可放在主屏游戏之上，但游戏在前台时自动禁用。已按用户选择加入 `-alpha` 半透明；仍不加点击穿透 / 不激活 / 无边框等 overlay 样式（见 §3 窗口）。
- **跑源码，不打包 exe**（避免未签名 exe 被杀软误报 / 特征匹配）。便携分发用「便携版 Python + 源码」（官方签名 `python.exe` 解释 `.py`，**非** PyInstaller 编译），仍守此约束。见 §9。
- 进程（`pythonw.exe`）、窗口标题、托盘、mutex 命名均中性。
- 不用于腾讯服务器；自用、不分发。
- 政策层面（公开报道，[需核实] 原文）：Riot 开发者政策据报道自 2025-03-13 起禁止第三方应用提供敌方大招计时（手动、自动均算）；Overwolf 的 Riot 合规指南将追踪敌方召唤师技能 CD 列为禁止。以上约束针对开发者 / 上架应用，本项目自用不在审核链上，但功能内容本身不符合该政策；使用者已知悉并决定保留 R 计时。上面的技术约束只降低被检测的面，不代表合规。

## 5. 文件结构

| 文件 | 作用 |
|---|---|
| `main.py` | 主程序（数据轮询 + UI + 托盘 + 游戏前台禁用） |
| `timer_core.py` | 计时核心：游戏时钟、计时状态模型、CD / 急速 / TP / 格式化函数（无 UI 依赖） |
| `tests/` | `timer_core` 单元测试（`python -m unittest discover -s tests`） |
| `download_assets.py` | 从 DDragon 下载英雄/技能/大招图标到 `assets/`（只补缺失，`--force` 全量），并每次重建 `abilities/r_index.json`、`abilities/item_ah.json`（Meraki） |
| `make_icon.py` | 程序化生成应用图标 `ico/icon.ico` |
| `start.bat` | 启动器（`pythonw` 无黑窗，`%~dp0` 可移植） |
| `setup.bat` / `requirements.txt` | 环境（requests / urllib3 / Pillow / pystray） |
| `ico/icon.ico` | 应用图标（桌面快捷方式用） |
| `make_portable.py` | 打便携 zip（下载独立 Python + 装依赖 + 拷源码/资源）见 §9 |
| `assets/`（含 `champions/`、`spells/`、`runes/`）、`venv/`、`config.json` | 运行时生成，已 gitignore |

## 6. 运行环境

- Windows + Anaconda Python（本机在 `E:\Anaconda3`，注意系统 `python` 是 Microsoft Store 占位符，不可用）。
- venv 由 Anaconda python 创建：`E:\Anaconda3\python.exe -m venv venv`。
- 桌面快捷方式 `DeskTimer.lnk` → `venv\Scripts\pythonw.exe main.py`，工作目录为项目根。

## 7. 精度局限（已接受）

- 星界洞悉（+18）现在可**手动开关**修正；但敌方是否带该符文需自行观察（tab 悬浮敌方技能可见其真实 CD）。未开时算出的 CD 偏长（偏"假安全"）。
- 原生传送 CD 已按游戏时间 + 等级估算，但等级插值方式和上单任务完成时机未核实；上单附赠 Unleashed TP 是 390s 定值（26.19）。
- 录入延迟靠补记（默认回溯 3s / Shift 20s / 滚轮 ±5s）修正，仍是人工估计。

## 8. 许可

- 参考项目 `lovelybbq/lol-spell-timer` **无 LICENSE**（= 保留所有权利）。本项目复制并改造其代码，**仅自用、不对外分发**（仓库为私有）。

## 9. 便携版打包（`make_portable.py`）

- 目标：解压即用，目标机**无需装 Python**；双击 `DeskTimer.vbs`（无黑窗）或 `DeskTimer.bat` 即运行。
- 做法：用 [python-build-standalone](https://github.com/astral-sh/python-build-standalone) 的 `install_only` Windows x64 完整发行版（**含 tkinter**，官方 embeddable 版**不含** tkinter，不可用）解压到 `python/`，`python/python.exe -m pip install -r requirements.txt`，再拷入 `main.py`/`timer_core.py`/`download_assets.py`/`assets/`/`ico/` 等，生成启动器，打 zip。
- 合规：解释器是官方签名 `python.exe`，跑的是 `.py` 源码，**非 PyInstaller 编译 exe**，符合 §4「跑源码不打包」。杀软仍可能对"便携 Python + 读游戏数据脚本"启发式报警，自用可接受。
- `assets/` 需先 `download_assets.py` 生成好再打包，便携版即可离线启动（DDragon 更新失败会回退硬编码 CD）。
