# -*- coding: utf-8 -*-
"""程序入口（打包成 exe 时使用的入口脚本）。

行为：
- 带命令行参数 → 走命令行转换（等同 converter.py 的用法）
- 不带参数     → 启动图形界面

打包成 exe 后没有控制台，若界面启动阶段抛异常会静默退出、用户看不到任何提示，
因此这里捕获异常并写日志 + 弹窗，避免"双击没反应"这种最难排查的情况。
"""

import os
import sys
import traceback


def _程序目录() -> str:
    """冻结后 sys.executable 是 exe 自身；源码运行时是本文件所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _写错误日志(详情: str) -> str:
    路径 = os.path.join(_程序目录(), "启动错误.log")
    try:
        with open(路径, "w", encoding="utf-8") as 文件:
            文件.write(详情)
    except Exception:
        return ""
    return 路径


def _启动图形界面() -> int:
    try:
        import ui
    except Exception:
        详情 = traceback.format_exc()
        日志路径 = _写错误日志(详情)
        提示 = "程序启动失败。\n\n" + 详情.strip().splitlines()[-1]
        if 日志路径:
            提示 += f"\n\n完整信息已写入：\n{日志路径}"
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox

            应用 = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "启动失败", 提示)
        except Exception:
            print(提示, file=sys.stderr)
        return 1

    try:
        return ui.main()
    except Exception:
        详情 = traceback.format_exc()
        日志路径 = _写错误日志(详情)
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox

            应用 = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None,
                "运行出错",
                "程序运行中发生未预期的错误。\n\n" + 详情.strip().splitlines()[-1]
                + (f"\n\n完整信息已写入：\n{日志路径}" if 日志路径 else ""),
            )
        except Exception:
            print(详情, file=sys.stderr)
        return 1


def _保证标准输出可用() -> None:
    """冻结成窗口程序后进程没有控制台，sys.stdout / sys.stderr 可能是 None，
    此时任何 print 都会抛 AttributeError，命令行用法直接失效。
    这里优先附着到启动它的那个控制台（双击启动时附着失败，则丢弃输出）。"""
    if sys.stdout is not None and sys.stderr is not None:
        return
    if os.name == "nt":
        try:
            import ctypes

            # ATTACH_PARENT_PROCESS = -1：附着到父进程（cmd / 终端）的控制台
            if ctypes.windll.kernel32.AttachConsole(-1):
                输出 = open("CONOUT$", "w", encoding="utf-8", buffering=1)
                if sys.stdout is None:
                    sys.stdout = 输出
                if sys.stderr is None:
                    sys.stderr = 输出
        except Exception:
            pass
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main(argv=None) -> int:
    参数 = list(sys.argv[1:] if argv is None else argv)
    _保证标准输出可用()
    # 冻结后工作目录可能是临时解包目录，切到 exe 所在目录，
    # 这样「默认输出到源文件同目录」等相对路径行为符合用户直觉。
    if getattr(sys, "frozen", False):
        try:
            os.chdir(_程序目录())
        except Exception:
            pass

    if 参数:
        import converter

        return converter._命令行(参数)

    return _启动图形界面()


if __name__ == "__main__":
    sys.exit(main())
