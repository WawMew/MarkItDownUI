# -*- coding: utf-8 -*-
"""配置存储：所有设置写进**程序目录下的 config/config.json**。

为什么不用 QSettings：Windows 上 QSettings 默认把设置写进注册表
（`HKEY_CURRENT_USER\\Software\\WorkBuddy\\MarkItDownUI`），那是机器级的、看不见的、
也不方便备份和携带。改成自己维护一个 JSON 文件后，配置就在程序旁边，
可以直接看、直接改、整个文件夹拷走就完成了迁移。

路径规则（按优先级）：
1. 环境变量 `MARKITDOWNUI_CONFIG` 指定的文件 —— 给自动化测试隔离用，设了就不再碰程序目录；
2. 否则 `<程序目录>/config/config.json`；冻结成 exe 后「程序目录」= exe 所在目录。

目录或文件不存在就**自动创建**；文件内容坏掉时改名成 `config.json.broken` 留档后重建，
不会因为一个坏文件让程序起不来。

对外的 API 故意做得跟 QSettings 一样（value / setValue / allKeys / contains /
remove / clear / sync），这样界面代码的改动量最小。

值的类型：JSON 原生的 str / int / float / bool / null 原样存；
bytes（含 QByteArray，例如窗口 geometry）存成 `{"__bytes__": "<base64>"}`，读回来是 bytes。
"""

import base64
import json
import os
import sys

配置目录名 = "config"
配置文件名 = "config.json"
环境变量名 = "MARKITDOWNUI_CONFIG"

# 字节值的 JSON 包装标记。用单个键的对象表示，肉眼一看就知道是二进制。
_BYTES键 = "__bytes__"


def 程序目录() -> str:
    """冻结后 sys.executable 是 exe 自身；源码运行时是本文件所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def 配置目录() -> str:
    指定 = os.environ.get(环境变量名, "").strip()
    if 指定:
        return os.path.dirname(os.path.abspath(指定))
    return os.path.join(程序目录(), 配置目录名)


def 配置路径() -> str:
    指定 = os.environ.get(环境变量名, "").strip()
    if 指定:
        return os.path.abspath(指定)
    return os.path.join(配置目录(), 配置文件名)


def _编码(值):
    """把值转成能直接写进 JSON 的形式。"""
    if isinstance(值, (bytes, bytearray)):
        return {_BYTES键: base64.b64encode(bytes(值)).decode("ascii")}
    if hasattr(值, "toBase64") and hasattr(值, "isEmpty"):        # QByteArray
        return {_BYTES键: bytes(值.toBase64()).decode("ascii")}
    if isinstance(值, (str, int, float, bool)) or 值 is None:
        return 值
    return str(值)          # 兜底：其它类型统一转字符串，至少不丢


def _解码(值):
    if isinstance(值, dict) and set(值.keys()) == {_BYTES键}:
        try:
            return base64.b64decode(str(值[_BYTES键]))
        except Exception:
            return b""
    return 值


class 配置存储:
    """一个 JSON 文件背后的小配置表。用 `打开()` 取实例，别自己 new。"""

    def __init__(self, 路径: str | None = None):
        self.路径 = 路径 or 配置路径()
        self.新建 = False            # 本次是不是刚创建（含从旧注册表迁移）
        self._数据: dict = self._载入()

    # ── 读写文件 ──────────────────────────────────────────

    def _载入(self) -> dict:
        目录 = os.path.dirname(self.路径)
        try:
            os.makedirs(目录, exist_ok=True)
        except Exception:
            return {}

        if not os.path.exists(self.路径):
            self.新建 = True
            数据 = self._迁移旧设置()
            self._写入(数据)
            return 数据

        try:
            with open(self.路径, "r", encoding="utf-8") as 文件:
                内容 = json.load(文件)
            if not isinstance(内容, dict):
                raise ValueError("配置文件的顶层不是对象")
            return 内容
        except Exception:
            # 坏文件不删，改名留档，然后当作全新配置继续跑
            try:
                os.replace(self.路径, self.路径 + ".broken")
            except Exception:
                pass
            self.新建 = True
            return {}

    def _迁移旧设置(self) -> dict:
        """首次运行时，把旧版存在注册表里的设置搬过来，免得用户重填密钥。

        只在「配置文件还不存在」时执行一次；读不到（没装 PyQt6 / 注册表里没有）就返回空。
        注册表里的旧数据**不动**，用户想清可以自己清。
        """
        try:
            from PyQt6.QtCore import QSettings
        except Exception:
            return {}
        try:
            旧 = QSettings("WorkBuddy", "MarkItDownUI")
            键们 = 旧.allKeys()
        except Exception:
            return {}
        数据 = {}
        for 键 in 键们:
            try:
                数据[键] = _编码(旧.value(键))
            except Exception:
                continue
        return 数据

    def _写入(self, 数据: dict):
        目录 = os.path.dirname(self.路径)
        try:
            os.makedirs(目录, exist_ok=True)
        except Exception:
            return
        临时 = self.路径 + ".tmp"
        try:
            with open(临时, "w", encoding="utf-8") as 文件:
                json.dump(数据, 文件, ensure_ascii=False, indent=2)
                文件.write("\n")
            os.replace(临时, self.路径)      # 原子替换，避免写一半断电留下半截文件
        except Exception:
            try:
                if os.path.exists(临时):
                    os.remove(临时)
            except Exception:
                pass

    # ── QSettings 风格 API ────────────────────────────────

    def value(self, 键: str, 默认=None):
        值 = self._数据.get(键, 默认)
        return _解码(值)

    def setValue(self, 键: str, 值):
        self._数据[键] = _编码(值)
        self._写入(self._数据)      # 立即落盘：设置项很少，省掉「忘了 sync 导致丢配置」

    def allKeys(self) -> list[str]:
        return list(self._数据.keys())

    def contains(self, 键: str) -> bool:
        return 键 in self._数据

    def remove(self, 键: str):
        if 键 in self._数据:
            del self._数据[键]
            self._写入(self._数据)

    def clear(self):
        self._数据 = {}
        self._写入(self._数据)

    def sync(self):
        self._写入(self._数据)

    def 全部(self) -> dict:
        """解码后的完整副本，调试用。"""
        return {键: _解码(值) for 键, 值 in self._数据.items()}


_缓存: dict[str, 配置存储] = {}


def 打开(路径: str | None = None) -> 配置存储:
    """按路径取配置实例（同一路径在进程内共享一份，避免两个窗口各自持旧副本）。"""
    实际 = os.path.abspath(路径 or 配置路径())
    if 实际 not in _缓存:
        _缓存[实际] = 配置存储(实际)
    return _缓存[实际]
