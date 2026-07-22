"""
打便携版 DeskTimer：解压即用，目标机无需安装 Python。

做法（不产出 PyInstaller 编译 exe，仍是"官方 python.exe 跑 .py 源码"）：
  1. 从 python-build-standalone 下载 Windows x64 的 install_only 完整发行版
     （含 tkinter；官方 embeddable 版不含 tkinter，不能用）。
  2. 解压到 <out>/python/，用它 pip 安装 requirements.txt 的依赖。
  3. 拷入 main.py / download_assets.py / make_icon.py / assets/ / ico/ 等。
  4. 生成 DeskTimer.vbs（无黑窗启动）+ DeskTimer.bat + 创建桌面快捷方式.vbs。
  5. 打包成 DeskTimer_portable.zip。

用法：先确保 assets/ 已生成（跑过 download_assets.py），然后：
    venv\\Scripts\\python.exe make_portable.py
需要联网（下载解释器 + 装依赖）。
"""
from __future__ import annotations
import io
import os
import re
import sys
import shutil
import tarfile
import zipfile
import subprocess
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "_portable_build")
APPDIR = os.path.join(BUILD, "DeskTimer")
PYDIR = os.path.join(APPDIR, "python")
ZIP_OUT = os.path.join(ROOT, "DeskTimer_portable.zip")

# 打包进便携版的源码/资源（存在才拷）
INCLUDE_FILES = ["main.py", "download_assets.py", "make_icon.py",
                 "requirements.txt", "README.md"]
INCLUDE_DIRS = ["assets", "ico"]

PBS_API = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
# 优先匹配的解释器版本（依次尝试）
PREFERRED = ("cpython-3.12.", "cpython-3.11.")


def log(msg):
    print(f"[portable] {msg}", flush=True)


def pick_asset() -> str:
    """从 python-build-standalone 最新 release 里挑 Windows x64 install_only 完整包。"""
    log("查询 python-build-standalone 最新发行版 ...")
    r = requests.get(PBS_API, timeout=30,
                     headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    assets = [a["browser_download_url"] for a in r.json().get("assets", [])]

    def ok(url, ver):
        name = url.rsplit("/", 1)[-1]
        return (ver in name
                and name.endswith("-x86_64-pc-windows-msvc-install_only.tar.gz"))

    for ver in PREFERRED:
        for url in assets:
            if ok(url, ver):
                return url
    # 兜底：任意 x64 windows install_only
    for url in assets:
        name = url.rsplit("/", 1)[-1]
        if re.search(r"cpython-3\.\d+\..*-x86_64-pc-windows-msvc-install_only\.tar\.gz$", name):
            return url
    raise RuntimeError("未找到合适的 install_only Windows x64 资源")


def download_and_extract_python(url: str):
    log(f"下载解释器：{url.rsplit('/', 1)[-1]}")
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    total = int(resp.headers.get("Content-Length", 0))
    buf = io.BytesIO()
    got = 0
    for chunk in resp.iter_content(chunk_size=1 << 16):
        buf.write(chunk)
        got += len(chunk)
        if total:
            pct = got * 100 // total
            print(f"\r  {got // 1048576}/{total // 1048576} MB ({pct}%)", end="", flush=True)
    print()
    buf.seek(0)
    log("解压解释器 ...")
    with tarfile.open(fileobj=buf, mode="r:gz") as tf:
        tf.extractall(APPDIR)  # 归档内顶层就是 python/ 目录
    exe = os.path.join(PYDIR, "python.exe")
    if not os.path.exists(exe):
        raise RuntimeError(f"解压后未找到 {exe}")
    log(f"解释器就位：{exe}")


def pip_install():
    req = os.path.join(ROOT, "requirements.txt")
    log("安装依赖到便携解释器 ...")
    subprocess.run([os.path.join(PYDIR, "python.exe"), "-m", "pip", "install",
                    "--no-warn-script-location", "-r", req],
                   check=True)


def copy_sources():
    log("拷贝源码与资源 ...")
    for f in INCLUDE_FILES:
        src = os.path.join(ROOT, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(APPDIR, f))
    for d in INCLUDE_DIRS:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(APPDIR, d),
                            dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__"))


def write_launchers():
    log("生成启动器 ...")
    # 无黑窗启动
    vbs = (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        'base = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\\"))\r\n'
        'sh.CurrentDirectory = base\r\n'
        'sh.Run """" & base & "python\\pythonw.exe"" """ & base & "main.py""", 0, False\r\n'
    )
    with open(os.path.join(APPDIR, "DeskTimer.vbs"), "w", encoding="utf-8") as f:
        f.write(vbs)

    bat = (
        "@echo off\r\n"
        'cd /d "%~dp0"\r\n'
        'start "" "%~dp0python\\pythonw.exe" "%~dp0main.py"\r\n'
    )
    with open(os.path.join(APPDIR, "DeskTimer.bat"), "w", encoding="utf-8") as f:
        f.write(bat)

    # 在目标机上生成带图标的桌面快捷方式（解决 .lnk 绝对路径不可移植的问题）
    mk = (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        'base = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\\"))\r\n'
        'desktop = sh.SpecialFolders("Desktop")\r\n'
        'Set lnk = sh.CreateShortcut(desktop & "\\DeskTimer.lnk")\r\n'
        'lnk.TargetPath = base & "DeskTimer.vbs"\r\n'
        'lnk.WorkingDirectory = base\r\n'
        'lnk.IconLocation = base & "ico\\icon.ico"\r\n'
        'lnk.Description = "DeskTimer"\r\n'
        'lnk.Save\r\n'
        'MsgBox "已在桌面创建 DeskTimer 快捷方式", 64, "DeskTimer"\r\n'
    )
    with open(os.path.join(APPDIR, "创建桌面快捷方式.vbs"), "w", encoding="utf-8") as f:
        f.write(mk)

    readme = (
        "DeskTimer 便携版 — 使用说明\r\n"
        "================================\r\n\r\n"
        "1. 直接双击 DeskTimer.vbs 即可运行（无需安装 Python）。\r\n"
        "   （若想要桌面图标：双击一次『创建桌面快捷方式.vbs』。）\r\n\r\n"
        "2. 仅适用于海外 Riot 官方服务器，不用于腾讯国服。自用，不分发。\r\n\r\n"
        "3. 需要先进入对局，窗口才会出现（读游戏本地 API）。\r\n"
        "   托盘图标右键：Always on Top（置顶开关）、Scale（缩放）、Quit（退出）。\r\n\r\n"
        "4. 若首次启动被 SmartScreen/杀软拦截：这是便携 Python 的常见误报，\r\n"
        "   自行判断放行。整包不含编译 exe，跑的是官方 python.exe + 源码。\r\n"
    )
    with open(os.path.join(APPDIR, "使用说明.txt"), "w", encoding="utf-8") as f:
        f.write(readme)


def make_zip():
    log("打包 zip ...")
    if os.path.exists(ZIP_OUT):
        os.remove(ZIP_OUT)
    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for base, _, files in os.walk(APPDIR):
            for fn in files:
                full = os.path.join(base, fn)
                arc = os.path.relpath(full, BUILD)  # zip 内顶层为 DeskTimer/
                z.write(full, arc)
    size = os.path.getsize(ZIP_OUT) / 1048576
    log(f"完成：{ZIP_OUT}  ({size:.1f} MB)")


def main():
    if not os.path.isdir(os.path.join(ROOT, "assets", "champions")):
        log("警告：assets/ 未生成，便携版将缺图标。请先跑 download_assets.py。")
    if os.path.exists(BUILD):
        log("清理旧构建 ...")
        shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(APPDIR, exist_ok=True)

    url = pick_asset()
    download_and_extract_python(url)
    pip_install()
    copy_sources()
    write_launchers()
    make_zip()
    log("全部完成。可把 DeskTimer_portable.zip 拷到 U 盘带走。")


if __name__ == "__main__":
    main()
