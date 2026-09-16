# -*- coding: utf-8 -*-
"""
文档转 Markdown —— PyQt6 图形界面
================================================================
功能：
  · 选择本地文档（支持多选、文件夹递归导入、拖拽导入）
  · 批量转换，后台线程执行，界面不卡顿
  · 带真实进度的进度条 + 转换日志
  · 实时预览生成的 Markdown（渲染视图 / 源码视图）
  · 一键导出为 .md 文件（单个另存 / 批量导出 / 转换后自动导出）

依赖：PyQt6 与 markitdown（见 requirements.txt）
运行：python ui.py
"""

from __future__ import annotations

import os
import sys
import traceback

from PyQt6.QtCore import QSettings, Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QKeySequence, QTextCursor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import converter as 后端

# 预览渲染上限：超长文档只渲染前若干字符，避免界面卡顿（源码视图仍完整）
预览字符上限 = 400_000

# 源码视图上限：开启「图片内嵌」后 base64 会让 .md 膨胀到几十 MB，
# 这里设置一个宽松的安全阀，超长时只显示开头并提示（导出内容不受影响）
源码字符上限 = 2_000_000

状态颜色 = {
    "待转换": "#6b7280",
    "转换中": "#2563eb",
    "已完成": "#059669",
    "已导出": "#059669",
    "无文本": "#b45309",
    "失败": "#dc2626",
}


# ────────────────────────────────────────────────────────────────
# 样式表（浅色主题）
# ────────────────────────────────────────────────────────────────

样式表 = """
QWidget {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #1f2937;
}
QMainWindow, QWidget#rootContainer { background: #eef1f6; }

QLabel#TitleLabel { font-size: 19px; font-weight: 700; color: #111827; }
QLabel#SubTitleLabel { font-size: 12px; color: #7b8794; }
QLabel#SectionLabel { font-size: 12px; font-weight: 600; color: #6b7280; }
QLabel#StatusLabel { color: #4b5563; }

QGroupBox {
    background: #ffffff;
    border: 1px solid #e3e8f0;
    border-radius: 10px;
    margin-top: 14px;
    padding: 14px 14px 12px 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: #4b5563;
    font-weight: 600;
    background: #eef1f6;
}

QTreeWidget, QPlainTextEdit, QTextBrowser, QLineEdit {
    background: #ffffff;
    border: 1px solid #e3e8f0;
    border-radius: 8px;
    selection-background-color: #dbeafe;
    selection-color: #1e3a8a;
}
QTreeWidget { padding: 4px; outline: 0; }
QTreeWidget::item { padding: 5px 4px; border-radius: 5px; }
QTreeWidget::item:hover { background: #f2f6fd; }
QTreeWidget::item:selected { background: #dbeafe; color: #1e3a8a; }
QHeaderView::section {
    background: #f7f9fc;
    border: 0;
    border-bottom: 1px solid #e3e8f0;
    padding: 7px 8px;
    color: #6b7280;
    font-weight: 600;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #d6dce7;
    border-radius: 7px;
    padding: 6px 14px;
    color: #374151;
}
QPushButton:hover { background: #f4f7fc; border-color: #b8c4d8; }
QPushButton:pressed { background: #e8eef8; }
QPushButton:disabled { color: #aab2bf; background: #f6f7f9; border-color: #e9ecf1; }

QPushButton#PrimaryButton {
    background: #2563eb;
    border: 1px solid #2563eb;
    color: #ffffff;
    font-weight: 600;
    font-size: 14px;
    padding: 8px 26px;
    border-radius: 8px;
}
QPushButton#PrimaryButton:hover { background: #1d4ed8; border-color: #1d4ed8; }
QPushButton#PrimaryButton:pressed { background: #1e40af; }
QPushButton#PrimaryButton:disabled { background: #a9c1f0; border-color: #a9c1f0; color: #ffffff; }

QProgressBar {
    border: 1px solid #e3e8f0;
    border-radius: 7px;
    background: #ffffff;
    height: 18px;
    text-align: center;
    color: #374151;
}
QProgressBar::chunk { background: #2563eb; border-radius: 6px; }

QTabWidget::pane {
    border: 1px solid #e3e8f0;
    border-radius: 10px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    padding: 8px 18px;
    margin-right: 4px;
    border: 1px solid transparent;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    color: #6b7280;
}
QTabBar::tab:selected {
    background: #ffffff;
    border: 1px solid #e3e8f0;
    border-bottom-color: #ffffff;
    color: #2563eb;
    font-weight: 600;
}
QTabBar::tab:hover:!selected { color: #2563eb; }

QRadioButton, QCheckBox { spacing: 7px; }
QRadioButton:disabled, QCheckBox:disabled { color: #aab2bf; }

QSplitter::handle { background: transparent; }
QSplitter::handle:horizontal { width: 8px; }
QSplitter::handle:vertical { height: 8px; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #ccd4e0; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #adb9c9; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #ccd4e0; border-radius: 5px; min-width: 28px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QFrame#分隔线 { background: #e3e8f0; max-height: 1px; border: 0; }
"""


# ────────────────────────────────────────────────────────────────
# 带拖放能力的文件列表
# ────────────────────────────────────────────────────────────────

class 文件树(QTreeWidget):
    """支持把文件 / 文件夹直接拖入列表。信号名必须为 ASCII，否则 PyQt 会崩溃。"""

    filesDropped = pyqtSignal(list)

    def __init__(self, 父=None):
        super().__init__(父)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setColumnCount(2)
        self.setHeaderLabels(["文件", "状态"])
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setStretchLastSection(False)

    def dragEnterEvent(self, 事件):
        if 事件.mimeData().hasUrls():
            事件.acceptProposedAction()
        else:
            super().dragEnterEvent(事件)

    def dragMoveEvent(self, 事件):
        if 事件.mimeData().hasUrls():
            事件.acceptProposedAction()
        else:
            super().dragMoveEvent(事件)

    def dropEvent(self, 事件):
        if not 事件.mimeData().hasUrls():
            super().dropEvent(事件)
            return
        路径列表 = [u.toLocalFile() for u in 事件.mimeData().urls() if u.isLocalFile()]
        路径列表 = [p for p in 路径列表 if p]
        if 路径列表:
            self.filesDropped.emit(路径列表)
        事件.acceptProposedAction()


# ────────────────────────────────────────────────────────────────
# 后台转换线程
# ────────────────────────────────────────────────────────────────

class 转换线程(QThread):
    """耗时转换放在后台线程，保证界面流畅、进度条实时刷新。"""

    log = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)
    item_done = pyqtSignal(object)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, 配置: 后端.转换配置, 父=None):
        super().__init__(父)
        self.配置 = 配置
        self._已取消 = False

    def 请求取消(self):
        self._已取消 = True

    def run(self):
        try:
            结果 = 后端.运行(
                self.配置,
                日志=lambda 文本: self.log.emit(str(文本)),
                进度=lambda 已完成, 总数, 名: self.progress.emit(已完成, 总数, 名),
                单项完成=lambda 项: self.item_done.emit(项),
                取消检查=lambda: self._已取消,
            )
            self.done.emit(结果)
        except Exception as 异常:
            self.failed.emit(
                f"{type(异常).__name__}: {异常}\n\n{traceback.format_exc()}"
            )


# ────────────────────────────────────────────────────────────────
# 主窗口
# ────────────────────────────────────────────────────────────────

class 主窗口(QMainWindow):

    def __init__(self):
        super().__init__()
        self.设置 = QSettings("WorkBuddy", "MarkItDownUI")
        self.结果表: dict[str, 后端.单项结果] = {}
        self.工作线程: 转换线程 | None = None
        self.当前路径: str | None = None

        self.setWindowTitle("文档转 Markdown 工具")
        self.resize(1220, 800)
        self.setMinimumSize(960, 640)

        self._构建界面()
        self.setStyleSheet(样式表)
        self._读取设置()
        self._写日志("欢迎使用「文档转 Markdown」工具，转换引擎：Microsoft MarkItDown。")
        self._写日志("使用步骤：① 添加文件或直接把文件 / 文件夹拖入列表 → ② 设置导出位置 → ③ 点击「开始转换」。")
        self._刷新计数()

    # ── 界面构建 ──────────────────────────────────────────

    def _构建界面(self):
        根 = QWidget()
        根.setObjectName("rootContainer")
        self.setCentralWidget(根)
        布局 = QVBoxLayout(根)
        布局.setContentsMargins(16, 14, 16, 14)
        布局.setSpacing(12)

        布局.addLayout(self._建标题区())
        布局.addWidget(self._建文件组(), 0)
        布局.addWidget(self._建中部区域(), 1)
        布局.addWidget(self._建输出设置组(), 0)
        布局.addLayout(self._建底栏())

        self._建快捷键()

    def _建标题区(self) -> QHBoxLayout:
        行 = QHBoxLayout()
        左 = QVBoxLayout()
        左.setSpacing(2)
        标题 = QLabel("文档转 Markdown")
        标题.setObjectName("TitleLabel")
        副标题 = QLabel("支持 PDF / Word / PPT / Excel / HTML 等格式，保留标题层级、列表与表格结构")
        副标题.setObjectName("SubTitleLabel")
        左.addWidget(标题)
        左.addWidget(副标题)
        行.addLayout(左)
        行.addStretch(1)

        self.计数标签 = QLabel("列表共 0 个文件")
        self.计数标签.setObjectName("SubTitleLabel")
        行.addWidget(self.计数标签, 0, Qt.AlignmentFlag.AlignBottom)
        return 行

    def _建文件组(self) -> QGroupBox:
        组 = QGroupBox("文件列表")
        行 = QHBoxLayout(组)
        行.setContentsMargins(0, 4, 0, 0)
        行.setSpacing(8)

        self.按钮_添加文件 = QPushButton("添加文件…")
        self.按钮_添加文件夹 = QPushButton("添加文件夹…")
        self.按钮_移除 = QPushButton("移除选中")
        self.按钮_清空 = QPushButton("清空列表")

        self.按钮_添加文件.clicked.connect(lambda: self.添加文件())
        self.按钮_添加文件夹.clicked.connect(lambda: self.添加文件夹())
        self.按钮_移除.clicked.connect(lambda: self.移除选中())
        self.按钮_清空.clicked.connect(lambda: self.清空列表())

        行.addWidget(self.按钮_添加文件)
        行.addWidget(self.按钮_添加文件夹)
        行.addWidget(self.按钮_移除)
        行.addWidget(self.按钮_清空)
        行.addStretch(1)

        提示 = QLabel("支持拖拽导入文件或文件夹")
        提示.setObjectName("SubTitleLabel")
        行.addWidget(提示)
        return 组

    def _建中部区域(self) -> QSplitter:
        分割 = QSplitter(Qt.Orientation.Horizontal)
        分割.setChildrenCollapsible(False)

        # ---- 左：文件树 + 日志 ----
        左分割 = QSplitter(Qt.Orientation.Vertical)
        左分割.setChildrenCollapsible(False)

        self.文件树 = 文件树()
        self.文件树.itemSelectionChanged.connect(lambda: self._选择变化())
        self.文件树.filesDropped.connect(lambda 路径列表: self._添加路径(路径列表))
        左分割.addWidget(self.文件树)

        日志容器 = QWidget()
        日志布局 = QVBoxLayout(日志容器)
        日志布局.setContentsMargins(0, 0, 0, 0)
        日志布局.setSpacing(6)
        日志标题 = QLabel("转换日志")
        日志标题.setObjectName("SectionLabel")
        日志布局.addWidget(日志标题)
        self.日志框 = QPlainTextEdit()
        self.日志框.setReadOnly(True)
        self.日志框.setMaximumBlockCount(5000)
        self.日志框.setFont(QFont("Consolas", 9))
        日志布局.addWidget(self.日志框)
        左分割.addWidget(日志容器)
        左分割.setStretchFactor(0, 3)
        左分割.setStretchFactor(1, 2)
        左分割.setSizes([440, 240])

        分割.addWidget(左分割)

        # ---- 右：预览 ----
        右容器 = QWidget()
        右布局 = QVBoxLayout(右容器)
        右布局.setContentsMargins(0, 0, 0, 0)
        右布局.setSpacing(8)

        self.标签页 = QTabWidget()
        self.预览 = QTextBrowser()
        self.预览.setOpenExternalLinks(True)
        self.预览.setFont(QFont("Microsoft YaHei UI", 10))
        self.源码 = QPlainTextEdit()
        self.源码.setReadOnly(True)
        self.源码.setFont(QFont("Consolas", 10))
        self.源码.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.标签页.addTab(self.预览, "渲染预览")
        self.标签页.addTab(self.源码, "Markdown 源码")
        右布局.addWidget(self.标签页, 1)

        按钮行 = QHBoxLayout()
        按钮行.setSpacing(8)
        self.按钮_导出当前 = QPushButton("导出当前文件…")
        self.按钮_导出全部 = QPushButton("导出全部结果")
        self.按钮_复制 = QPushButton("复制源码")
        self.按钮_导出当前.clicked.connect(lambda: self.导出当前())
        self.按钮_导出全部.clicked.connect(lambda: self.导出全部())
        self.按钮_复制.clicked.connect(lambda: self.复制源码())
        按钮行.addWidget(self.按钮_导出当前)
        按钮行.addWidget(self.按钮_导出全部)
        按钮行.addWidget(self.按钮_复制)
        按钮行.addStretch(1)
        右布局.addLayout(按钮行)

        分割.addWidget(右容器)
        分割.setStretchFactor(0, 4)
        分割.setStretchFactor(1, 7)
        分割.setSizes([430, 760])

        self.右容器 = 右容器
        return 分割

    def _建输出设置组(self) -> QGroupBox:
        组 = QGroupBox("导出设置")
        布局 = QVBoxLayout(组)
        布局.setContentsMargins(0, 4, 0, 0)
        布局.setSpacing(9)

        行一 = QHBoxLayout()
        行一.setSpacing(8)
        self.单选_同目录 = QRadioButton("保存到源文件所在目录")
        self.单选_指定目录 = QRadioButton("统一保存到指定目录：")
        self.单选_同目录.setChecked(True)
        组_单选 = QButtonGroup(self)
        组_单选.addButton(self.单选_同目录)
        组_单选.addButton(self.单选_指定目录)
        self.单选_同目录.toggled.connect(lambda _: self._刷新输出控件())

        self.输入_输出目录 = QLineEdit()
        self.输入_输出目录.setPlaceholderText("请选择 .md 文件的输出目录")
        self.输入_输出目录.setEnabled(False)
        self.按钮_浏览 = QPushButton("浏览…")
        self.按钮_浏览.setEnabled(False)
        self.按钮_浏览.clicked.connect(lambda: self.选择输出目录())

        行一.addWidget(self.单选_同目录)
        行一.addSpacing(8)
        行一.addWidget(self.单选_指定目录)
        行一.addWidget(self.输入_输出目录, 1)
        行一.addWidget(self.按钮_浏览)
        布局.addLayout(行一)

        行二 = QHBoxLayout()
        行二.setSpacing(16)
        self.勾选_覆盖 = QCheckBox("覆盖已存在的同名 .md 文件")
        self.勾选_覆盖.setChecked(True)
        self.勾选_自动导出 = QCheckBox("转换完成后自动导出 .md 文件")
        self.勾选_自动导出.setChecked(True)
        self.勾选_自动导出.toggled.connect(lambda _: self._刷新输出控件())
        行二.addWidget(self.勾选_覆盖)
        行二.addWidget(self.勾选_自动导出)
        行二.addStretch(1)
        布局.addLayout(行二)

        行三 = QHBoxLayout()
        行三.setSpacing(8)
        self.勾选_图片内嵌 = QCheckBox("将文档中的图片内嵌进 .md（base64 原样保留）")
        self.勾选_图片内嵌.setToolTip(
            "关闭时（默认）：MarkItDown 会丢弃文档内嵌的图片，.md 里只剩一个加载不出来的引用。\n"
            "开启后：图片以 base64 原样写进 .md，字节级无损、可离线查看，\n"
            "代价是 .md 体积增加约 1/3（10 张 1 MB 的图约多出 13 MB），纯文本可读性也变差。"
        )
        行三.addWidget(self.勾选_图片内嵌)
        行三.addStretch(1)
        布局.addLayout(行三)
        return 组

    def _建底栏(self) -> QHBoxLayout:
        行 = QHBoxLayout()
        行.setSpacing(12)

        进度区 = QVBoxLayout()
        进度区.setSpacing(4)
        self.进度条 = QProgressBar()
        self.进度条.setRange(0, 100)
        self.进度条.setValue(0)
        self.进度条.setTextVisible(True)
        self.进度条.setFormat("就绪")
        进度区.addWidget(self.进度条)

        self.状态标签 = QLabel("准备就绪，等待添加文件。")
        self.状态标签.setObjectName("StatusLabel")
        进度区.addWidget(self.状态标签)
        行.addLayout(进度区, 1)

        self.按钮_取消 = QPushButton("取消")
        self.按钮_取消.setEnabled(False)
        self.按钮_取消.clicked.connect(lambda: self.取消转换())
        行.addWidget(self.按钮_取消, 0, Qt.AlignmentFlag.AlignBottom)

        self.按钮_开始 = QPushButton("开始转换")
        self.按钮_开始.setObjectName("PrimaryButton")
        self.按钮_开始.clicked.connect(lambda: self.开始转换())
        行.addWidget(self.按钮_开始, 0, Qt.AlignmentFlag.AlignBottom)
        return 行

    def _建快捷键(self):
        快捷键表 = [
            ("Ctrl+O", lambda: self.添加文件()),
            ("Ctrl+Shift+O", lambda: self.添加文件夹()),
            ("Ctrl+Return", lambda: self.开始转换()),
            ("Ctrl+S", lambda: self.导出当前()),
            ("Delete", lambda: self.移除选中()),
        ]
        for 按键, 回调 in 快捷键表:
            动作 = QAction(self)
            动作.setShortcut(QKeySequence(按键))
            动作.triggered.connect(lambda _=False, 函数=回调: 函数())
            self.addAction(动作)

    # ── 设置持久化 ────────────────────────────────────────

    def _读取设置(self):
        模式 = str(self.设置.value("输出方式", "同目录"))
        self.单选_指定目录.setChecked(模式 == "指定目录")
        self.单选_同目录.setChecked(模式 != "指定目录")
        self.输入_输出目录.setText(str(self.设置.value("输出目录", "")))
        self.勾选_覆盖.setChecked(self._设置取布尔("覆盖已有", True))
        self.勾选_自动导出.setChecked(self._设置取布尔("自动导出", True))
        self.勾选_图片内嵌.setChecked(self._设置取布尔("图片内嵌", False))
        self._上次目录 = str(self.设置.value("last_dir", os.path.expanduser("~")))

        几何 = self.设置.value("geometry")
        if 几何:
            self.restoreGeometry(几何)
        self._刷新输出控件()

    def _设置取布尔(self, 键: str, 默认: bool) -> bool:
        值 = self.设置.value(键, 默认)
        if isinstance(值, bool):
            return 值
        return str(值).lower() in ("true", "1", "yes")

    def _保存设置(self):
        self.设置.setValue("输出方式", "指定目录" if self.单选_指定目录.isChecked() else "同目录")
        self.设置.setValue("输出目录", self.输入_输出目录.text().strip())
        self.设置.setValue("覆盖已有", self.勾选_覆盖.isChecked())
        self.设置.setValue("自动导出", self.勾选_自动导出.isChecked())
        self.设置.setValue("图片内嵌", self.勾选_图片内嵌.isChecked())
        self.设置.setValue("last_dir", getattr(self, "_上次目录", ""))
        self.设置.setValue("geometry", self.saveGeometry())

    # ── 文件列表操作 ──────────────────────────────────────

    def 添加文件(self):
        if self._运行中():
            return
        路径列表, _ = QFileDialog.getOpenFileNames(
            self, "选择要转换的文档", getattr(self, "_上次目录", ""),
            后端.构建文件过滤器(),
        )
        if 路径列表:
            self._上次目录 = os.path.dirname(路径列表[0])
            self._添加路径(路径列表)

    def 添加文件夹(self):
        if self._运行中():
            return
        目录 = QFileDialog.getExistingDirectory(
            self, "选择包含文档的文件夹", getattr(self, "_上次目录", "")
        )
        if 目录:
            self._上次目录 = 目录
            self._添加路径([目录])

    def _添加路径(self, 路径列表):
        if self._运行中():
            return
        文件列表 = 后端.收集文件(路径列表)
        现有 = {self._路径(item) for item in self._全部条目()}
        新增 = 0
        跳过 = 0
        for 路径 in 文件列表:
            键 = 路径.lower() if os.name == "nt" else 路径
            if 键 in 现有:
                跳过 += 1
                continue
            现有.add(键)
            self._新增条目(路径)
            新增 += 1

        if 新增:
            self._写日志(f"已加入 {新增} 个文件。")
        if 跳过:
            self._写日志(f"跳过 {跳过} 个已在列表中的文件。")
        if not 文件列表:
            self._写日志("未在所选位置找到受支持的文档。")
        self._刷新计数()

    def _新增条目(self, 路径: str) -> QTreeWidgetItem:
        条目 = QTreeWidgetItem(self.文件树)
        条目.setText(0, os.path.basename(路径))
        条目.setToolTip(0, 路径)
        条目.setToolTip(1, f"{后端.文件类型说明(路径)} · 等待转换")
        条目.setData(0, Qt.ItemDataRole.UserRole, 路径)
        条目.setText(1, "待转换")
        条目.setForeground(1, QBrush(QColor(状态颜色["待转换"])))
        return 条目

    def 移除选中(self):
        if self._运行中():
            return
        条目列表 = self.文件树.selectedItems()
        if not 条目列表:
            return
        for 条目 in 条目列表:
            路径 = self._路径(条目)
            self.结果表.pop(路径, None)
            索引 = self.文件树.indexOfTopLevelItem(条目)
            self.文件树.takeTopLevelItem(索引)
        self._刷新计数()
        self._选择变化()

    def 清空列表(self):
        if self._运行中():
            return
        if self.文件树.topLevelItemCount() and QMessageBox.question(
            self, "确认清空", "确定要清空文件列表吗？（已导出的 .md 文件不会被删除）"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.文件树.clear()
        self.结果表.clear()
        self.当前路径 = None
        self._刷新计数()
        self._选择变化()

    def _全部条目(self) -> list[QTreeWidgetItem]:
        return [self.文件树.topLevelItem(i) for i in range(self.文件树.topLevelItemCount())]

    def _全部路径(self) -> list[str]:
        return [self._路径(条目) for 条目 in self._全部条目()]

    @staticmethod
    def _路径(条目: QTreeWidgetItem) -> str:
        return 条目.data(0, Qt.ItemDataRole.UserRole)

    def _刷新计数(self):
        self.计数标签.setText(f"列表共 {self.文件树.topLevelItemCount()} 个文件")

    def _设置条目状态(self, 条目: QTreeWidgetItem, 文本: str, 提示: str = ""):
        条目.setText(1, 文本)
        颜色 = 状态颜色.get(文本.split("（")[0].split(" ")[0], "#4b5563")
        条目.setForeground(1, QBrush(QColor(颜色)))
        if 提示:
            条目.setToolTip(1, 提示)

    # ── 转换流程 ──────────────────────────────────────────

    def 开始转换(self):
        if self._运行中():
            return
        路径列表 = self._全部路径()
        if not 路径列表:
            QMessageBox.information(self, "提示", "请先添加需要转换的文档。")
            return

        输出方式 = "指定目录" if self.单选_指定目录.isChecked() else "同目录"
        输出目录 = self.输入_输出目录.text().strip()
        if 输出方式 == "指定目录":
            if not 输出目录:
                QMessageBox.warning(self, "提示", "请先选择输出目录，或改为保存到源文件所在目录。")
                return
            try:
                os.makedirs(输出目录, exist_ok=True)
            except Exception as 异常:
                QMessageBox.critical(self, "无法创建输出目录", f"{输出目录}\n\n{异常}")
                return

        配置 = 后端.转换配置(
            文件列表=路径列表,
            输出方式=输出方式,
            输出目录=os.path.abspath(输出目录) if 输出目录 else 后端.BASE_DIR,
            覆盖已有=self.勾选_覆盖.isChecked(),
            自动保存=self.勾选_自动导出.isChecked(),
            图片内嵌=self.勾选_图片内嵌.isChecked(),
        )

        # 重置状态
        self.结果表.clear()
        for 条目 in self._全部条目():
            self._设置条目状态(条目, "待转换", "等待转换")
        self.文件树.setCurrentItem(self.文件树.topLevelItem(0))
        self.进度条.setRange(0, len(路径列表))
        self.进度条.setValue(0)
        self.进度条.setFormat(f"0 / {len(路径列表)}")
        self.状态标签.setText("正在准备转换引擎 …")
        self._写日志("─" * 56)

        self._设置运行态(True)

        self.工作线程 = 转换线程(配置, self)
        self.工作线程.log.connect(lambda 文本: self._写日志(文本))
        self.工作线程.progress.connect(lambda i, n, 名: self._进度更新(i, n, 名))
        self.工作线程.item_done.connect(lambda 项: self._单项完成(项))
        self.工作线程.done.connect(lambda 汇总: self._转换完成(汇总))
        self.工作线程.failed.connect(lambda 错误: self._转换失败(错误))
        self.工作线程.finished.connect(lambda: self._线程结束())
        self.工作线程.start()

    def 取消转换(self):
        if self.工作线程 is not None:
            self.工作线程.请求取消()
            self.按钮_取消.setEnabled(False)
            self.状态标签.setText("正在取消，请等待当前文件处理结束 …")
            self._写日志("已请求取消，将在当前文件处理完成后停止。")

    def _进度更新(self, 已完成: int, 总数: int, 文件名: str):
        self.进度条.setRange(0, 总数)
        self.进度条.setValue(已完成)
        self.进度条.setFormat(f"{已完成} / {总数}")
        if 已完成 < 总数:
            self.状态标签.setText(f"正在转换 {已完成 + 1}/{总数}：{文件名}")

    def _单项完成(self, 结果: 后端.单项结果):
        self.结果表[结果.源文件] = 结果
        条目 = self._找到条目(结果.源文件)

        if 结果.成功 and not 结果.为空:
            文本 = f"{结果.状态}（{结果.字符数} 字符）"
            提示 = f"{结果.状态}\n字符数：{结果.字符数}\n用时：{结果.耗时:.1f} 秒"
            if 结果.内嵌图片数:
                文本 += f" · 含图 {结果.内嵌图片数}"
                提示 += f"\n已内嵌图片：{结果.内嵌图片数} 张（base64 约 {结果.内嵌图片字节 / 1024:.0f} KB）"
            elif 结果.丢弃图片数:
                文本 += f" · ⚠ 丢图 {结果.丢弃图片数}"
                提示 += f"\n⚠ {结果.警告}"
            if 结果.输出文件:
                提示 += f"\n输出：{结果.输出文件}"
        elif 结果.为空:
            文本 = "无文本"
            提示 = f"未提取到文本\n原因：{结果.警告}"
        else:
            文本 = "失败"
            提示 = f"失败原因：{结果.错误}"

        if 条目 is not None:
            self._设置条目状态(条目, 文本, 提示)

        # 实时预览：当前选中的文件转换完成即刷新
        if self.当前路径 == 结果.源文件:
            self._刷新预览(结果.源文件)

    def _转换完成(self, 汇总: dict):
        总数 = 汇总.get("总数", 0)
        成功 = 汇总.get("成功数", 0)
        失败 = 汇总.get("失败数", 0)
        导出数 = len(汇总.get("导出文件列表", []))
        self.进度条.setValue(max(总数, self.进度条.maximum()))
        self.进度条.setFormat(f"{总数} / {总数}")
        self.状态标签.setText(f"转换结束：成功 {成功} 个，失败 {失败} 个。")

        当前 = self.文件树.currentItem()
        if 当前 is not None:
            self._刷新预览(self._路径(当前))

        QMessageBox.information(
            self,
            "转换完成",
            f"共处理 {总数} 个文件\n"
            f"成功：{成功} 个\n"
            f"未提取到文本：{汇总.get('无文本数', 0)} 个\n"
            f"失败：{失败} 个\n"
            f"已导出 .md：{导出数} 个\n"
            + (
                f"已内嵌图片：{汇总['内嵌图片数']} 张\n"
                if 汇总.get("内嵌图片数") else ""
            )
            + (
                f"未保留图片：{汇总['丢弃图片数']} 张（勾选「图片内嵌进 .md」可保留）\n"
                if 汇总.get("丢弃图片数") else ""
            )
            + f"总用时：{汇总.get('耗时', 0):.1f} 秒",
        )

    def _转换失败(self, 错误: str):
        self.状态标签.setText("转换过程发生异常。")
        self._写日志(f"[错误] {错误}")
        QMessageBox.critical(self, "转换失败", 错误[:1500])

    def _线程结束(self):
        if self.工作线程 is not None:
            self.工作线程.deleteLater()
            self.工作线程 = None
        self._设置运行态(False)

    def _设置运行态(self, 运行中: bool):
        self.按钮_开始.setEnabled(not 运行中)
        self.按钮_取消.setEnabled(运行中)
        for 控件 in (
            self.按钮_添加文件, self.按钮_添加文件夹, self.按钮_移除, self.按钮_清空,
            self.单选_同目录, self.单选_指定目录, self.勾选_覆盖, self.勾选_自动导出,
            self.勾选_图片内嵌,
        ):
            控件.setEnabled(not 运行中)
        if not 运行中:
            self._刷新输出控件()

    def _运行中(self) -> bool:
        return self.工作线程 is not None and self.工作线程.isRunning()

    def _找到条目(self, 路径: str) -> QTreeWidgetItem | None:
        for 条目 in self._全部条目():
            if self._路径(条目) == 路径:
                return 条目
        return None

    # ── 预览 ──────────────────────────────────────────────

    def _选择变化(self):
        条目列表 = self.文件树.selectedItems()
        路径 = self._路径(条目列表[0]) if 条目列表 else None
        self.当前路径 = 路径
        self._刷新预览(路径)

    def _刷新预览(self, 路径: str | None):
        占位 = (
            "<div style='color:#8b95a3;font-family:\"Microsoft YaHei UI\";"
            "padding:36px 12px;text-align:center;'>"
            "尚未转换，转换完成后这里会实时显示 Markdown 预览。</div>"
        )
        if not 路径:
            self.预览.setHtml(占位)
            self.源码.setPlainText("")
            self.按钮_导出当前.setEnabled(False)
            return

        结果 = self.结果表.get(路径)
        if 结果 is None:
            self.预览.setHtml(占位)
            self.源码.setPlainText("")
            self.按钮_导出当前.setEnabled(False)
            return

        if not 结果.成功:
            self.预览.setHtml(
                "<div style='color:#dc2626;font-family:\"Microsoft YaHei UI\";padding:24px;'>"
                f"<b>转换失败</b><br><br>{self._转义(结果.错误)}</div>"
            )
            self.源码.setPlainText("")
            self.按钮_导出当前.setEnabled(False)
            return

        if 结果.为空:
            self.预览.setHtml(
                "<div style='color:#b45309;font-family:\"Microsoft YaHei UI\";padding:24px;line-height:1.7;'>"
                "<b>未提取到文本</b><br><br>"
                f"{self._转义(结果.警告)}"
                "<br><br><span style='color:#8b95a3;'>该文件已跳过导出，不会生成空的 .md 文件。</span></div>"
            )
            self.源码.setPlainText("")
            self.按钮_导出当前.setEnabled(False)
            return

        内容 = 结果.内容
        if len(内容) > 源码字符上限:
            self.源码.setPlainText(
                内容[:源码字符上限]
                + f"\n\n… 内容过长（共 {len(内容):,} 字符），源码视图仅显示前 "
                f"{源码字符上限:,} 个字符；导出的 .md 文件内容完整。"
            )
            self._写日志(
                f"提示：{结果.文件名} 内容达 {len(内容):,} 字符，源码视图已截断显示。"
            )
        else:
            self.源码.setPlainText(内容)
        self.源码.moveCursor(QTextCursor.MoveOperation.Start)

        if len(内容) > 预览字符上限:
            截断 = 内容[:预览字符上限]
            # 避免把一段 base64 图片数据从中间切断（半截的 data URI 渲染不出图）
            换行位置 = 截断.rfind("\n")
            if 换行位置 > 预览字符上限 * 0.8:
                截断 = 截断[:换行位置]
            self.预览.setMarkdown(截断)
            self.预览.append(
                f"<div style='color:#b45309;padding:10px 0;'>"
                f"（文档较长，此处仅渲染前 {预览字符上限:,} 个字符；"
                f"完整内容见「Markdown 源码」页签或已导出的 .md 文件）</div>"
            )
            self._写日志(f"提示：{结果.文件名} 内容较长（{len(内容):,} 字符），预览已截断显示。")
        else:
            self.预览.setMarkdown(内容)
        self._约束预览图片宽度()
        self.预览.moveCursor(QTextCursor.MoveOperation.Start)
        self.按钮_导出当前.setEnabled(True)

    def _约束预览图片宽度(self):
        """把预览中宽度超过可视区的图片按比例缩小，避免插图把版面撑出滚动条。"""
        try:
            文档 = self.预览.document()
            可用宽 = max(self.预览.viewport().width() - 24, 160)
            块 = 文档.begin()
            while 块.isValid():
                迭代 = 块.begin()
                while not 迭代.atEnd():
                    片段 = 迭代.fragment()
                    if 片段.isValid() and 片段.charFormat().isImageFormat():
                        格式 = 片段.charFormat().toImageFormat()
                        资源 = 文档.resource(0, QUrl(格式.name()))
                        宽 = 资源.width() if hasattr(资源, "width") else 0
                        高 = 资源.height() if hasattr(资源, "height") else 0
                        if 宽 > 可用宽 and 高 > 0:
                            光标 = QTextCursor(文档)
                            光标.setPosition(片段.position())
                            光标.setPosition(
                                片段.position() + 片段.length(),
                                QTextCursor.MoveMode.KeepAnchor,
                            )
                            格式.setWidth(可用宽)
                            格式.setHeight(int(高 * 可用宽 / 宽))
                            光标.setCharFormat(格式)
                    迭代 += 1
                块 = 块.next()
        except Exception as 异常:
            # 预览缩放失败不影响转换结果，但要说清楚，方便排查
            self._写日志(
                f"提示：预览图片自适应缩放未生效（{type(异常).__name__}），不影响导出结果。"
            )

    @staticmethod
    def _转义(文本: str) -> str:
        return (
            文本.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br>")
        )

    # ── 导出 ──────────────────────────────────────────────

    def 导出当前(self):
        路径 = self.当前路径
        结果 = self.结果表.get(路径) if 路径 else None
        if 结果 is None or not 结果.成功 or 结果.为空:
            QMessageBox.information(self, "提示", "当前预览的文件没有可导出的文本内容。")
            return

        配置 = self._当前输出配置()
        默认路径 = 结果.输出文件 or 后端.计算输出路径(结果.源文件, 配置)
        目标, _ = QFileDialog.getSaveFileName(
            self, "导出为 Markdown 文件", 默认路径, "Markdown 文件 (*.md);;所有文件 (*.*)"
        )
        if not 目标:
            return
        if not os.path.splitext(目标)[1]:
            目标 += ".md"
        try:
            后端.保存文本(目标, 结果.内容)
        except Exception as 异常:
            QMessageBox.critical(self, "导出失败", f"{目标}\n\n{异常}")
            return
        结果.输出文件 = 目标
        条目 = self._找到条目(结果.源文件)
        if 条目 is not None:
            self._设置条目状态(条目, f"已导出（{结果.字符数} 字符）", f"输出：{目标}")
        self._写日志(f"已导出 → {目标}")
        self.状态标签.setText(f"已导出：{os.path.basename(目标)}")

    def 导出全部(self):
        成功结果 = [r for r in self.结果表.values() if r.成功 and not r.为空]
        if not 成功结果:
            QMessageBox.information(self, "提示", "还没有可导出的转换结果，请先执行转换。")
            return

        配置 = self._当前输出配置()
        导出数 = 0
        失败列表: list[str] = []
        for 结果 in 成功结果:
            try:
                目标 = 后端.计算输出路径(结果.源文件, 配置)
                后端.保存文本(目标, 结果.内容)
                结果.输出文件 = 目标
                导出数 += 1
                条目 = self._找到条目(结果.源文件)
                if 条目 is not None:
                    self._设置条目状态(条目, f"已导出（{结果.字符数} 字符）", f"输出：{目标}")
                self._写日志(f"已导出 → {目标}")
            except Exception as 异常:
                失败列表.append(f"{结果.文件名}：{异常}")
                self._写日志(f"[错误] 导出失败 {结果.文件名}：{异常}")

        提示 = f"已导出 {导出数} 个 .md 文件。"
        if 失败列表:
            提示 += f"\n失败 {len(失败列表)} 个：\n" + "\n".join(失败列表[:8])
        self.状态标签.setText(提示.split("\n")[0])
        QMessageBox.information(self, "导出完成", 提示)

    def 复制源码(self):
        文本 = self.源码.toPlainText()
        if not 文本:
            QMessageBox.information(self, "提示", "当前没有可复制的 Markdown 内容。")
            return
        QApplication.clipboard().setText(文本)
        self.状态标签.setText(f"已复制 {len(文本):,} 个字符到剪贴板。")

    def 选择输出目录(self):
        目录 = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.输入_输出目录.text().strip() or getattr(self, "_上次目录", "")
        )
        if 目录:
            self.输入_输出目录.setText(目录)

    def _当前输出配置(self) -> 后端.转换配置:
        return 后端.转换配置(
            输出方式="指定目录" if self.单选_指定目录.isChecked() else "同目录",
            输出目录=self.输入_输出目录.text().strip() or 后端.BASE_DIR,
            覆盖已有=self.勾选_覆盖.isChecked(),
            自动保存=self.勾选_自动导出.isChecked(),
            图片内嵌=self.勾选_图片内嵌.isChecked(),
        )

    def _刷新输出控件(self):
        指定 = self.单选_指定目录.isChecked()
        self.输入_输出目录.setEnabled(指定 and not self._运行中())
        self.按钮_浏览.setEnabled(指定 and not self._运行中())

    # ── 其它 ──────────────────────────────────────────────

    def _写日志(self, 文本: str):
        self.日志框.appendPlainText(文本)
        滚动条 = self.日志框.verticalScrollBar()
        滚动条.setValue(滚动条.maximum())

    def closeEvent(self, 事件):
        if self._运行中():
            选择 = QMessageBox.question(
                self, "正在转换", "转换仍在进行中，确定要退出吗？"
            )
            if 选择 != QMessageBox.StandardButton.Yes:
                事件.ignore()
                return
            self.工作线程.请求取消()
            self.工作线程.wait(3000)
        self._保存设置()
        事件.accept()


def main() -> int:
    应用 = QApplication(sys.argv)
    应用.setApplicationName("MarkItDownUI")
    应用.setApplicationDisplayName("文档转 Markdown 工具")
    应用.setFont(QFont("Microsoft YaHei UI", 10))
    窗口 = 主窗口()
    窗口.show()
    return 应用.exec()


if __name__ == "__main__":
    sys.exit(main())
