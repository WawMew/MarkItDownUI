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

import math
import os
import sys
import traceback
from dataclasses import replace as 替换字段

from PyQt6.QtCore import (
    QByteArray,
    QLibraryInfo,
    QPointF,
    QSize,
    Qt,
    QThread,
    QTranslator,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPixmap,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
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

import config as 配置
import converter as 后端
import i18n
from i18n import 译

# Qt 自己那套组件（文件对话框、消息框按钮、右键菜单…）的文案由它自带的 .qm 提供。
# 这些翻译随 PyQt6 一起装在 PyQt6/Qt6/translations 下，不需要自己编译，加载即可。
_QT翻译器: list[QTranslator] = []

# 预览渲染上限：超长文档只渲染前若干字符，避免界面卡顿（源码视图仍完整）
预览字符上限 = 400_000

# 源码视图上限：开启「图片内嵌」后 base64 会让 .md 膨胀到几十 MB，
# 这里设置一个宽松的安全阀，超长时只显示开头并提示（导出内容不受影响）
源码字符上限 = 2_000_000

# 日志保留行数：与 日志框.setMaximumBlockCount 保持一致。
# 内存里也留一份（而不是只读控件文本），因为切换语言时要能「横幅换语言、正文原样保留」。
日志行数上限 = 5000

状态颜色 = {
    "待转换": "#6b7280",
    "转换中": "#2563eb",
    "已完成": "#059669",
    "已导出": "#059669",
    "无文本": "#b45309",
    "失败": "#dc2626",
}


# ────────────────────────────────────────────────────────────────
# Qt 内置翻译
# ────────────────────────────────────────────────────────────────

def 安装Qt内置翻译(应用, 语言代码: str) -> None:
    """
    加载 Qt 自带的界面翻译（qtbase_zh_CN.qm 等）。

    这些 .qm 随 PyQt6 一起装在 PyQt6/Qt6/translations 下，管的是 **Qt 自己**的文案：
    文件对话框的「打开 / 取消」、消息框标准按钮、文本框右键菜单、日历控件等等。
    应用自身的文案不走这里（见 i18n.py）—— 两边互补，缺一边都会中英混杂。

    失败时静默跳过：没有 Qt 翻译顶多是个别按钮显示英文/中文原文，不影响功能。
    """
    for 翻译器 in _QT翻译器:
        应用.removeTranslator(翻译器)
    _QT翻译器.clear()

    目录 = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not 目录:
        return
    # qtbase 覆盖绝大多数控件；qt 是汇总包（部分发行版才有），能加载就一并装上
    for 前缀 in ("qtbase", "qt"):
        翻译器 = QTranslator()
        try:
            if 翻译器.load(f"{前缀}_{语言代码}", 目录):
                应用.installTranslator(翻译器)
                _QT翻译器.append(翻译器)
        except Exception:
            pass


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

QPushButton#IconButton {
    padding: 0;
    min-width: 30px; max-width: 30px;
    min-height: 26px; max-height: 26px;
    border-radius: 6px;
}
QPushButton#IconButton:hover { background: #eaf1fd; border-color: #9db4da; }
QPushButton#IconButton:pressed { background: #dde8f9; }

QLabel#MutedLabel { font-size: 12px; color: #9aa5b1; }
QLabel#WarnLabel { font-size: 12px; color: #b45309; }
QLabel#OkLabel { font-size: 12px; color: #059669; }
QLabel#HintLabel { font-size: 12px; color: #7b8794; }

QDialog { background: #eef1f6; }
QDialog QLabel { background: transparent; }

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
# 图标
# ────────────────────────────────────────────────────────────────

def 齿轮图标(大小: int = 16, 颜色: str = "#5b6779") -> QIcon:
    """
    用代码画一个齿轮图标。

    不用字体里的 ⚙ 字形：该字符不在 Microsoft YaHei 里，各机器会 fallback 到
    Segoe UI Symbol / Emoji，可能变成彩色 emoji 或豆腐块，尺寸也不受控。
    """
    像素 = QPixmap(大小, 大小)
    像素.fill(Qt.GlobalColor.transparent)
    绘制 = QPainter(像素)
    绘制.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    绘制.translate(大小 / 2.0, 大小 / 2.0)
    绘制.scale(大小 / 16.0, 大小 / 16.0)

    齿数 = 8
    步长 = 2 * math.pi / 齿数
    外径, 内径, 孔径 = 7.4, 4.9, 2.1
    轮廓 = QPainterPath()
    首点 = True
    for 序号 in range(齿数):
        基准 = 序号 * 步长
        # 每个齿贡献「齿顶弧两点 + 齿根弧两点」，相邻齿之间自然形成径向齿侧
        for 角, 半径 in (
            (基准 - 步长 * 0.20, 外径),
            (基准, 外径),
            (基准 + 步长 * 0.20, 外径),
            (基准 + 步长 * 0.50, 内径),
            (基准 + 步长 * 0.80, 内径),
        ):
            x, y = 半径 * math.cos(角), 半径 * math.sin(角)
            if 首点:
                轮廓.moveTo(x, y)
                首点 = False
            else:
                轮廓.lineTo(x, y)
    轮廓.closeSubpath()

    中心孔 = QPainterPath()
    中心孔.addEllipse(QPointF(0.0, 0.0), 孔径, 孔径)

    绘制.fillPath(轮廓.subtracted(中心孔), QColor(颜色))
    绘制.end()
    return QIcon(像素)


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
        self.setHeaderLabels([译("文件"), 译("状态")])
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


class LLM测试线程(QThread):
    """在后台跑一次真实的连通性测试，避免请求超时冻住界面。"""

    done = pyqtSignal(bool, str)

    def __init__(self, LLM, 父=None):
        super().__init__(父)
        self.LLM = LLM

    def run(self):
        try:
            成功, 说明 = 后端.测试LLM连接(self.LLM)
        except Exception as 异常:
            成功, 说明 = False, f"{type(异常).__name__}: {异常}"
        self.done.emit(成功, 说明)


# ────────────────────────────────────────────────────────────────
# LLM OCR 设置窗口
# ────────────────────────────────────────────────────────────────

class LLM设置对话框(QDialog):
    """齿轮按钮弹出的配置窗口：任何兼容 OpenAI 接口的服务都能填。"""

    def __init__(self, 配置: 后端.LLM配置, 父=None):
        super().__init__(父)
        self.setWindowTitle(译("LLM OCR 设置"))
        self.setModal(True)
        self.setMinimumWidth(700)
        self.测试线程: LLM测试线程 | None = None
        self._构建界面()
        self._填入(配置)

    def _构建界面(self):
        布局 = QVBoxLayout(self)
        布局.setContentsMargins(16, 14, 16, 14)
        布局.setSpacing(11)

        副标题 = QLabel(
            译(
                "填入任意兼容 OpenAI 接口的服务即可（OpenAI、DeepSeek、通义、智谱、Ollama、vLLM …）。"
                "模型必须支持图片输入，纯文本模型识别不了图片里的文字。"
            )
        )
        副标题.setObjectName("SubTitleLabel")
        副标题.setWordWrap(True)
        布局.addWidget(副标题)

        组 = QGroupBox(译("模型服务"))
        表单 = QFormLayout(组)
        表单.setContentsMargins(0, 4, 0, 0)
        表单.setHorizontalSpacing(12)
        表单.setVerticalSpacing(10)
        表单.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        表单.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )

        self.输入_地址 = QLineEdit()
        self.输入_地址.setPlaceholderText(译("如 https://api.openai.com/v1（留空 = OpenAI 官方）"))
        表单.addRow(译("接口地址"), self.输入_地址)

        self.输入_模型 = QLineEdit()
        self.输入_模型.setPlaceholderText(
            译("需支持图片输入：gpt-4o / qwen-vl-max / glm-4v / llava …")
        )
        表单.addRow(译("模型"), self.输入_模型)

        密钥行 = QHBoxLayout()
        密钥行.setSpacing(8)
        self.输入_密钥 = QLineEdit()
        self.输入_密钥.setEchoMode(QLineEdit.EchoMode.Password)
        self.输入_密钥.setPlaceholderText(译("如 sk-xxxxxxxxxxxxxxxx（留空 = 读环境变量 OPENAI_API_KEY）"))
        self.勾选_显示密钥 = QCheckBox(译("显示"))
        self.勾选_显示密钥.toggled.connect(
            lambda 选中: self.输入_密钥.setEchoMode(
                QLineEdit.EchoMode.Normal if 选中 else QLineEdit.EchoMode.Password
            )
        )
        密钥行.addWidget(self.输入_密钥, 1)
        密钥行.addWidget(self.勾选_显示密钥)
        表单.addRow(译("API 密钥"), 密钥行)

        self.输入_提示词 = QLineEdit()
        # 占位符里显示当前语言的默认提示词：输入框留空 = 用默认值，
        # 这样切换语言后提示词会跟着换成新语言的版本，不会把旧语言的默认文本固化下来
        self.输入_提示词.setPlaceholderText(后端.默认提示词())
        self.输入_提示词.setToolTip(译("发送给模型的指令，一般无需修改。"))
        表单.addRow(译("识别提示词"), self.输入_提示词)
        布局.addWidget(组)

        测试行 = QHBoxLayout()
        测试行.setSpacing(10)
        self.按钮_测试 = QPushButton(译("测试连接"))
        self.按钮_测试.setToolTip(
            译("用一张真实的小图调用一次模型，确认「地址 + 密钥 + 模型」可用。")
        )
        self.按钮_测试.clicked.connect(lambda: self.测试连接())
        self.提示标签 = QLabel(译("尚未测试。"))
        self.提示标签.setObjectName("HintLabel")
        self.提示标签.setWordWrap(True)
        测试行.addWidget(self.按钮_测试)
        测试行.addWidget(self.提示标签, 1)
        布局.addLayout(测试行)

        说明 = QLabel(
            译(
                "· 识别会把文档中的图片上传到上面配置的服务（按图计费），请自行确认数据可以离机；"
                "密钥不会写进导出的 .md。\n"
                "· 开启后 PDF / Word / PPT / Excel 中的图片会变成识别出的文字，原图不再内嵌。\n"
                "· 没有可识别文字的文件不会产生任何调用；模型报错会记进主界面日志，不会静默失败。"
            )
        )
        说明.setObjectName("HintLabel")
        说明.setWordWrap(True)
        布局.addWidget(说明)

        盒 = QDialogButtonBox()
        self.按钮_恢复 = 盒.addButton(译("恢复默认"), QDialogButtonBox.ButtonRole.ResetRole)
        self.按钮_取消 = 盒.addButton(译("取消"), QDialogButtonBox.ButtonRole.RejectRole)
        self.按钮_确定 = 盒.addButton(译("确定"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.按钮_确定.setObjectName("PrimaryButton")
        self.按钮_确定.setDefault(True)
        self.按钮_恢复.clicked.connect(lambda: self._恢复默认())
        盒.accepted.connect(self.accept)
        盒.rejected.connect(self.reject)
        布局.addWidget(盒)

    # ── 取值 / 填值 ───────────────────────────────────────

    def _填入(self, 配置: 后端.LLM配置):
        self.输入_地址.setText(配置.接口地址)
        self.输入_模型.setText(配置.模型)
        self.输入_密钥.setText(配置.密钥)
        # 只在用户确实自定义过时才填；留空 = 用当前语言的默认提示词（占位符里能看到）
        提示词 = (配置.提示词 or "").strip()
        self.输入_提示词.setText("" if 后端.是默认提示词(提示词) else 提示词)

    def 取值(self) -> 后端.LLM配置:
        """返回界面上的配置；「启用」由主界面的开关决定，不在这里改。"""
        return 后端.LLM配置(
            接口地址=self.输入_地址.text().strip(),
            密钥=self.输入_密钥.text().strip(),
            模型=self.输入_模型.text().strip(),
            提示词=self.输入_提示词.text().strip() or 后端.默认提示词(),
        )

    def _恢复默认(self):
        self.输入_地址.clear()
        self.输入_模型.clear()
        self.输入_密钥.clear()
        self.输入_提示词.clear()      # 留空即恢复为当前语言的默认提示词
        self._设提示(译("已恢复默认：地址留空表示使用 OpenAI 官方接口。"))

    # ── 连通性测试 ────────────────────────────────────────

    def _设提示(self, 文本: str, 错误: bool = False):
        self.提示标签.setText(文本)
        self.提示标签.setStyleSheet(f"color: {'#dc2626' if 错误 else '#4b5563'};")

    def _写日志(self, 文本: str):
        父 = self.parent()
        if 父 is not None and hasattr(父, "_写日志"):
            父._写日志(文本)

    def 测试连接(self):
        if self.测试线程 is not None and self.测试线程.isRunning():
            return
        # 关键：配置的「启用」标志会让 校验() 短路返回，测试时必须显式置 True，
        # 否则空模型也会被放行、真的打出去一个必定失败的请求
        LLM = 替换字段(self.取值(), 启用=True)
        问题 = LLM.校验()
        if 问题:
            self._设提示(问题, 错误=True)
            return
        self.按钮_测试.setEnabled(False)
        self.按钮_确定.setEnabled(False)
        self._设提示(译("正在调用模型 …（本地服务或大模型可能需十几秒）"))
        self._写日志(
            译(
                "[LLM] 正在测试 {接口} · {模型} …",
                接口=LLM.接口地址.strip() or 译("OpenAI 官方接口"),
                模型=LLM.模型.strip(),
            )
        )
        self.测试线程 = LLM测试线程(LLM, self)
        self.测试线程.done.connect(lambda 成功, 说明: self._测试完成(成功, 说明))
        self.测试线程.finished.connect(lambda: self._测试线程结束())
        self.测试线程.start()

    def _测试完成(self, 成功: bool, 说明: str):
        self._设提示(说明, 错误=not 成功)
        self._写日志(f"[LLM] {说明}")

    def _测试线程结束(self):
        self.按钮_测试.setEnabled(True)
        self.按钮_确定.setEnabled(True)
        if self.测试线程 is not None:
            self.测试线程.deleteLater()
            self.测试线程 = None

    # ── 关闭 ──────────────────────────────────────────────

    def _等在跑的线程(self):
        # 网络请求可能正卡着，最多等 1.5 秒，避免关窗口时界面假死
        if self.测试线程 is not None and self.测试线程.isRunning():
            self.测试线程.wait(1500)

    def accept(self):
        self._等在跑的线程()
        super().accept()

    def reject(self):
        self._等在跑的线程()
        super().reject()

    def closeEvent(self, 事件):
        self._等在跑的线程()
        事件.accept()


# ────────────────────────────────────────────────────────────────
# 主窗口
# ────────────────────────────────────────────────────────────────

class 主窗口(QMainWindow):

    def __init__(self):
        super().__init__()
        # 所有设置都落在「程序目录/config/config.json」（见 config.py），不再用注册表
        self.设置 = 配置.打开()
        self._同步勾选中 = False      # 两项互斥互相取反时的重入保护
        self.结果表: dict[str, 后端.单项结果] = {}
        self.工作线程: 转换线程 | None = None
        self.当前路径: str | None = None
        # LLM 参数由弹出式「设置」窗口编辑，这里持有内存副本
        self.LLM配置值 = 后端.LLM配置()
        self._LLM设置窗口: LLM设置对话框 | None = None
        self._快捷键动作: list[QAction] = []
        # 日志拆两段存：横幅随语言换，正文（转换记录）是用户数据，切语言时原样保留
        self._欢迎行: list[str] = []
        self._日志行: list[str] = []

        self.setWindowTitle(译("文档转 Markdown 工具"))
        self.resize(1220, 800)
        self.setMinimumSize(960, 640)

        self._构建界面()
        self.setStyleSheet(样式表)
        self._读取设置()
        self._写欢迎日志()
        self._刷新计数()

    def _欢迎横幅(self) -> list[str]:
        """启动横幅（不随转换变化的几条说明）。单独成列，切换语言时整块换掉。"""
        行 = [
            译("欢迎使用「文档转 Markdown」工具，转换引擎：Microsoft MarkItDown。"),
            译("使用步骤：① 添加文件或直接把文件 / 文件夹拖入列表 → ② 设置导出位置 → ③ 点击「开始转换」。"),
        ]
        if 后端.插件已安装() and 后端.客户端库已安装():
            行.append(
                译(
                    "如需识别图片、扫描件里的文字：勾选「启用 LLM OCR 识别」，"
                    "再点它右侧的齿轮按钮，填入兼容 OpenAI 接口的模型与密钥。"
                )
            )
        else:
            行.append(
                译(
                    "提示：未安装 LLM OCR 依赖，图片与扫描件中的文字无法识别；"
                    "需要时执行 pip install {包名} openai。",
                    包名=后端.OCR插件包名,
                )
            )
        return 行

    def _写欢迎日志(self):
        self._欢迎行 = self._欢迎横幅()
        self._刷新日志()

    def _刷新日志(self):
        """按「横幅 + 正文」重排整个日志框（重建界面、切换语言后调用）。"""
        if getattr(self, "日志框", None) is None:
            return
        self.日志框.setPlainText("\n".join(self._欢迎行 + self._日志行))
        self.日志框.moveCursor(QTextCursor.MoveOperation.End)

    # ── 界面构建 ──────────────────────────────────────────

    def _构建界面(self):
        self._清除快捷键()
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
        标题 = QLabel(译("文档转 Markdown"))
        标题.setObjectName("TitleLabel")
        副标题 = QLabel(
            译(
                "支持 PDF / Word / PPT / Excel / HTML 等格式，保留标题层级、列表与表格结构"
                "　|　可选 LLM OCR，识别图片与扫描件中的文字"
            )
        )
        副标题.setObjectName("SubTitleLabel")
        左.addWidget(标题)
        左.addWidget(副标题)
        行.addLayout(左)
        行.addStretch(1)

        self.计数标签 = QLabel("")
        self.计数标签.setObjectName("SubTitleLabel")
        行.addWidget(self.计数标签, 0, Qt.AlignmentFlag.AlignBottom)

        行.addSpacing(14)
        行.addWidget(self._建语言选择器(), 0, Qt.AlignmentFlag.AlignBottom)
        return 行

    def _建语言选择器(self) -> QWidget:
        """标题区右侧的语言下拉框。"""
        容器 = QWidget()
        布局 = QHBoxLayout(容器)
        布局.setContentsMargins(0, 0, 0, 0)
        布局.setSpacing(6)
        标签 = QLabel(译("界面语言"))
        标签.setObjectName("SubTitleLabel")
        self.下拉_语言 = QComboBox()
        self.下拉_语言.setToolTip(译("切换界面语言"))
        self.下拉_语言.setMinimumWidth(106)
        # 填充期间屏蔽信号：addItem 会自动选中第一项，不屏蔽会误触发一次语言切换
        self.下拉_语言.blockSignals(True)
        for 代码, 名称 in i18n.可用语言():
            self.下拉_语言.addItem(名称, 代码)
        当前 = i18n.当前语言()
        for 下标 in range(self.下拉_语言.count()):
            if self.下拉_语言.itemData(下标) == 当前:
                self.下拉_语言.setCurrentIndex(下标)
                break
        self.下拉_语言.blockSignals(False)
        self.下拉_语言.currentIndexChanged.connect(lambda _: self._语言下拉变化())
        布局.addWidget(标签)
        布局.addWidget(self.下拉_语言)
        return 容器

    def _语言下拉变化(self):
        代码 = self.下拉_语言.currentData()
        if 代码:
            self.切换语言(代码)

    def _建文件组(self) -> QGroupBox:
        组 = QGroupBox(译("文件列表"))
        行 = QHBoxLayout(组)
        行.setContentsMargins(0, 4, 0, 0)
        行.setSpacing(8)

        self.按钮_添加文件 = QPushButton(译("添加文件…"))
        self.按钮_添加文件夹 = QPushButton(译("添加文件夹…"))
        self.按钮_移除 = QPushButton(译("移除选中"))
        self.按钮_清空 = QPushButton(译("清空列表"))

        self.按钮_添加文件.clicked.connect(lambda: self.添加文件())
        self.按钮_添加文件夹.clicked.connect(lambda: self.添加文件夹())
        self.按钮_移除.clicked.connect(lambda: self.移除选中())
        self.按钮_清空.clicked.connect(lambda: self.清空列表())

        行.addWidget(self.按钮_添加文件)
        行.addWidget(self.按钮_添加文件夹)
        行.addWidget(self.按钮_移除)
        行.addWidget(self.按钮_清空)
        行.addStretch(1)

        提示 = QLabel(译("支持拖拽导入文件或文件夹"))
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
        日志标题 = QLabel(译("转换日志"))
        日志标题.setObjectName("SectionLabel")
        日志布局.addWidget(日志标题)
        self.日志框 = QPlainTextEdit()
        self.日志框.setReadOnly(True)
        self.日志框.setMaximumBlockCount(日志行数上限)
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
        self.标签页.addTab(self.预览, 译("渲染预览"))
        self.标签页.addTab(self.源码, 译("Markdown 源码"))
        右布局.addWidget(self.标签页, 1)

        按钮行 = QHBoxLayout()
        按钮行.setSpacing(8)
        self.按钮_导出当前 = QPushButton(译("导出当前文件…"))
        self.按钮_导出全部 = QPushButton(译("导出全部结果"))
        self.按钮_复制 = QPushButton(译("复制源码"))
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
        组 = QGroupBox(译("导出设置"))
        布局 = QVBoxLayout(组)
        布局.setContentsMargins(0, 4, 0, 0)
        布局.setSpacing(9)

        行一 = QHBoxLayout()
        行一.setSpacing(8)
        self.单选_同目录 = QRadioButton(译("保存到源文件所在目录"))
        self.单选_指定目录 = QRadioButton(译("统一保存到指定目录："))
        self.单选_同目录.setChecked(True)
        组_单选 = QButtonGroup(self)
        组_单选.addButton(self.单选_同目录)
        组_单选.addButton(self.单选_指定目录)
        self.单选_同目录.toggled.connect(lambda _: self._刷新输出控件())

        self.输入_输出目录 = QLineEdit()
        self.输入_输出目录.setPlaceholderText(译("请选择 .md 文件的输出目录"))
        self.输入_输出目录.setEnabled(False)
        self.按钮_浏览 = QPushButton(译("浏览…"))
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
        self.勾选_覆盖 = QCheckBox(译("覆盖已存在的同名 .md 文件"))
        self.勾选_覆盖.setChecked(True)
        self.勾选_自动导出 = QCheckBox(译("转换完成后自动导出 .md 文件"))
        self.勾选_自动导出.setChecked(True)
        self.勾选_自动导出.toggled.connect(lambda _: self._刷新输出控件())
        行二.addWidget(self.勾选_覆盖)
        行二.addWidget(self.勾选_自动导出)
        行二.addStretch(1)
        布局.addLayout(行二)

        行三 = QHBoxLayout()
        行三.setSpacing(8)
        self.勾选_图片内嵌 = QCheckBox(译("将文档中的图片内嵌进 .md（base64 原样保留）"))
        self.勾选_图片内嵌.setToolTip(
            译(
                "关闭时（默认）：MarkItDown 会丢弃文档内嵌的图片，.md 里只剩一个加载不出来的引用。\n"
                "开启后：图片以 base64 原样写进 .md，字节级无损、可离线查看，\n"
                "代价是 .md 体积增加约 1/3（10 张 1 MB 的图约多出 13 MB），纯文本可读性也变差。\n\n"
                "与「启用 LLM OCR」二选一：勾上本项会自动取消 LLM OCR。"
            )
        )
        # 注意：PyQt6 里 connect() 直连**中文方法名**会段错误，必须用 lambda 包一层
        self.勾选_图片内嵌.toggled.connect(lambda 勾上: self._图片内嵌被勾选(勾上))
        行三.addWidget(self.勾选_图片内嵌)
        行三.addSpacing(12)

        self.勾选_LLM = QCheckBox(译("启用 LLM OCR 识别图片与扫描件中的文字"))
        self.勾选_LLM.setToolTip(
            译(
                "MarkItDown 内核没有任何本地 OCR —— 扫描件 PDF 提取为空、图片只读 EXIF 元数据。\n"
                "开启后由官方插件 markitdown-ocr 接管 PDF / Word / PPT / Excel：\n"
                "内嵌图片、以及「整页抽不出文字」的扫描页会送给视觉模型，用识别结果替换图片。\n\n"
                "模型与密钥点右侧齿轮按钮配置。文档中的图片会上传到该服务（按图计费），"
                "请自行确认数据可以离机。\n\n"
                "与「图片内嵌」二选一：勾上本项会自动取消图片内嵌。"
            )
        )
        self.勾选_LLM.toggled.connect(lambda 勾上: self._LLM被勾选(勾上))

        self.按钮_LLM设置 = QPushButton()
        self.按钮_LLM设置.setObjectName("IconButton")
        self.按钮_LLM设置.setIcon(齿轮图标(16, "#5b6779"))
        self.按钮_LLM设置.setIconSize(QSize(16, 16))
        self.按钮_LLM设置.setCursor(Qt.CursorShape.PointingHandCursor)
        self.按钮_LLM设置.clicked.connect(lambda: self.打开LLM设置())

        self.LLM状态标签 = QLabel("")
        self.LLM状态标签.setObjectName("MutedLabel")

        行三.addWidget(self.勾选_LLM)
        行三.addWidget(self.按钮_LLM设置)
        行三.addWidget(self.LLM状态标签)
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
        self.进度条.setFormat(译("就绪"))
        进度区.addWidget(self.进度条)

        self.状态标签 = QLabel(译("准备就绪，等待添加文件。"))
        self.状态标签.setObjectName("StatusLabel")
        进度区.addWidget(self.状态标签)
        行.addLayout(进度区, 1)

        self.按钮_取消 = QPushButton(译("取消"))
        self.按钮_取消.setEnabled(False)
        self.按钮_取消.clicked.connect(lambda: self.取消转换())
        行.addWidget(self.按钮_取消, 0, Qt.AlignmentFlag.AlignBottom)

        self.按钮_开始 = QPushButton(译("开始转换"))
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
        self._快捷键动作 = []
        for 按键, 回调 in 快捷键表:
            动作 = QAction(self)
            动作.setShortcut(QKeySequence(按键))
            动作.triggered.connect(lambda _=False, 函数=回调: 函数())
            self.addAction(动作)
            self._快捷键动作.append(动作)

    def _清除快捷键(self):
        """重建界面时先撤掉旧的 QAction，否则每切换一次语言就多堆一份。"""
        for 动作 in list(getattr(self, "_快捷键动作", [])):
            self.removeAction(动作)
            动作.deleteLater()
        self._快捷键动作 = []

    # ── 设置持久化 ────────────────────────────────────────

    def _读取设置(self):
        模式 = str(self.设置.value("输出方式", "同目录"))
        self.单选_指定目录.setChecked(模式 == "指定目录")
        self.单选_同目录.setChecked(模式 != "指定目录")
        self.输入_输出目录.setText(str(self.设置.value("输出目录", "")))
        self.勾选_覆盖.setChecked(self._设置取布尔("覆盖已有", True))
        self.勾选_自动导出.setChecked(self._设置取布尔("自动导出", True))
        self.勾选_图片内嵌.setChecked(self._设置取布尔("图片内嵌", False))

        # LLM OCR：密钥跟其它设置一起放在 config/config.json，不写入任何导出文件
        提示词 = str(self.设置.value("LLM提示词", ""))
        if 后端.是默认提示词(提示词):
            提示词 = ""      # 存的是默认值（可能还是另一种语言的）→ 折成空，跟随界面语言
        self.LLM配置值 = 后端.LLM配置(
            接口地址=str(self.设置.value("LLM接口地址", "")),
            密钥=str(self.设置.value("LLM密钥", "")),
            模型=str(self.设置.value("LLM模型", "")),
            提示词=提示词,
        )
        self.勾选_LLM.setChecked(self._设置取布尔("LLM启用", False))

        # 两项互斥：老配置里万一同时为真，以 LLM OCR 为准（它会接管 PDF/Word/PPT/Excel 的图片）
        if self.勾选_LLM.isChecked() and self.勾选_图片内嵌.isChecked():
            self._同步勾选中 = True
            self.勾选_图片内嵌.setChecked(False)
            self._同步勾选中 = False

        self._上次目录 = str(self.设置.value("last_dir", os.path.expanduser("~")))

        几何 = self.设置.value("geometry")
        if 几何:
            # JSON 里的二进制以 base64 存，读回来是 bytes，restoreGeometry 要 QByteArray
            self.restoreGeometry(几何 if isinstance(几何, QByteArray) else QByteArray(几何))
        self._刷新输出控件()
        self._刷新LLM状态()

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
        self.设置.setValue("LLM启用", self.勾选_LLM.isChecked())
        self.设置.setValue("LLM接口地址", self.LLM配置值.接口地址.strip())
        self.设置.setValue("LLM密钥", self.LLM配置值.密钥.strip())
        self.设置.setValue("LLM模型", self.LLM配置值.模型.strip())
        提示词 = self.LLM配置值.提示词.strip()
        # 用户没改过提示词就存空：换个语言启动时它会自动变成新语言的默认值
        self.设置.setValue("LLM提示词", "" if 后端.是默认提示词(提示词) else 提示词)
        self.设置.setValue("语言", i18n.当前语言())
        self.设置.setValue("last_dir", getattr(self, "_上次目录", ""))
        self.设置.setValue("geometry", self.saveGeometry())

    # ── 语言切换 ──────────────────────────────────────────

    def 切换语言(self, 代码: str):
        """
        切换界面语言：**就地重建整个界面**。

        文案是在构造控件时写进去的，Qt 不会自动重译，所以最省事也最不容易漏的做法
        就是把界面拆掉重建，再把用户状态搬回去 —— 文件列表、转换结果、日志、选中项、
        输出设置与 LLM 配置都放在内存对象里，不受重建影响。
        """
        代码 = i18n.规范化(代码)
        if 代码 == i18n.当前语言():
            return
        if self._运行中():
            # 运行中重建界面，工作线程的回调会打到已销毁的控件上，干脆拒绝
            self._写日志(译("正在转换，结束后才能切换界面语言。"))
            self._同步语言下拉框()
            return

        状态 = self._暂存界面状态()
        i18n.设置语言(代码)
        self.设置.setValue("语言", 代码)

        应用 = QApplication.instance()
        if 应用 is not None:
            安装Qt内置翻译(应用, 代码)
            应用.setApplicationDisplayName(译("文档转 Markdown 工具"))

        self.setWindowTitle(译("文档转 Markdown 工具"))
        self._重建界面()
        self._恢复界面状态(状态)
        self._写日志(译("界面语言已切换为 {名称}。", 名称=i18n.语言标签[代码]))

    def _重建界面(self):
        旧根 = self.centralWidget()
        self._构建界面()          # 内部会 setCentralWidget，旧容器随之交还 Qt 销毁
        self.setStyleSheet(样式表)
        if 旧根 is not None:
            旧根.deleteLater()

    def _暂存界面状态(self) -> dict:
        return {
            "文件": [
                (self._路径(条目), 条目.data(1, Qt.ItemDataRole.UserRole))
                for 条目 in self._全部条目()
            ],
            "当前": self.当前路径,
            "日志行": list(self._日志行),
        }

    def _恢复界面状态(self, 状态: dict):
        for 路径, 状态键 in 状态.get("文件", []):
            条目 = self._新增条目(路径)
            结果 = self.结果表.get(路径)
            if 结果 is not None:
                self._回填条目结果(条目, 结果)
            elif 状态键:
                self._设置条目状态(条目, 状态键, 译(状态键), 译(状态键))
        # 横幅按新语言重写；正文是转换记录（用户数据），原样搬过来
        self._日志行 = list(状态.get("日志行", []))
        self._欢迎行 = self._欢迎横幅()
        self._刷新日志()
        self._刷新计数()
        self._刷新输出控件()
        self._刷新LLM状态()

        路径 = 状态.get("当前")
        条目 = self._找到条目(路径) if 路径 else None
        if 条目 is not None:
            self.文件树.setCurrentItem(条目)
        else:
            self.当前路径 = None
            self._刷新预览(None)
        self.进度条.setValue(0)
        self.状态标签.setText(译("准备就绪，等待添加文件。"))

    def _同步语言下拉框(self):
        """把下拉框拨回当前语言（用户操作被拒绝时用）。"""
        下拉 = getattr(self, "下拉_语言", None)
        if 下拉 is None:
            return
        当前 = i18n.当前语言()
        下拉.blockSignals(True)
        for 下标 in range(下拉.count()):
            if 下拉.itemData(下标) == 当前:
                下拉.setCurrentIndex(下标)
                break
        下拉.blockSignals(False)

    # ── 文件列表操作 ──────────────────────────────────────

    def 添加文件(self):
        if self._运行中():
            return
        路径列表, _ = QFileDialog.getOpenFileNames(
            self, 译("选择要转换的文档"), getattr(self, "_上次目录", ""),
            后端.构建文件过滤器(),
        )
        if 路径列表:
            self._上次目录 = os.path.dirname(路径列表[0])
            self._添加路径(路径列表)

    def 添加文件夹(self):
        if self._运行中():
            return
        目录 = QFileDialog.getExistingDirectory(
            self, 译("选择包含文档的文件夹"), getattr(self, "_上次目录", "")
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
            self._写日志(译("已加入 {数量} 个文件。", 数量=新增))
        if 跳过:
            self._写日志(译("跳过 {数量} 个已在列表中的文件。", 数量=跳过))
        if not 文件列表:
            self._写日志(译("未在所选位置找到受支持的文档。"))
        self._刷新计数()

    def _新增条目(self, 路径: str) -> QTreeWidgetItem:
        条目 = QTreeWidgetItem(self.文件树)
        条目.setText(0, os.path.basename(路径))
        条目.setToolTip(0, 路径)
        条目.setData(0, Qt.ItemDataRole.UserRole, 路径)
        self._设置条目状态(
            条目,
            "待转换",
            译("待转换"),
            译("{原因} · 等待转换", 原因=后端.文件类型说明(路径)),
        )
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
            self,
            译("确认清空"),
            译("确定要清空文件列表吗？（已导出的 .md 文件不会被删除）"),
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
        self.计数标签.setText(
            译("列表共 {n} 个文件", n=self.文件树.topLevelItemCount())
        )

    def _设置条目状态(
        self, 条目: QTreeWidgetItem, 状态键: str, 文本: str, 提示: str = ""
    ):
        """状态键用于取颜色（与显示文本解耦，否则切换语言后颜色就找不到了）。"""
        条目.setText(1, 文本)
        条目.setData(1, Qt.ItemDataRole.UserRole, 状态键)
        条目.setForeground(1, QBrush(QColor(状态颜色.get(状态键, "#4b5563"))))
        if 提示:
            条目.setToolTip(1, 提示)

    def _回填条目结果(self, 条目: QTreeWidgetItem, 结果: 后端.单项结果):
        """按当前语言重算某条结果的展示文本（重建界面、切换语言时用）。"""
        状态键, 文本, 提示 = self._结果展示(结果)
        self._设置条目状态(条目, 状态键, 文本, 提示)

    @staticmethod
    def _结果展示(结果: 后端.单项结果) -> tuple[str, str, str]:
        """把一条转换结果整理成（状态键, 列表显示文本, 悬停提示）。"""
        if 结果.成功 and not 结果.为空:
            状态 = 译(结果.状态)
            文本 = 译("{状态}（{字符数} 字符）", 状态=状态, 字符数=结果.字符数)
            提示 = 译(
                "{状态}\n字符数：{字符数}\n用时：{耗时} 秒",
                状态=状态,
                字符数=结果.字符数,
                耗时=f"{结果.耗时:.1f}",
            )
            if 结果.OCR识别数:
                文本 += 译(" · OCR {数量}", 数量=结果.OCR识别数)
                提示 += 译(
                    "\nLLM OCR：识别 {识别数} 处（调用模型 {调用数} 次）",
                    识别数=结果.OCR识别数,
                    调用数=结果.LLM调用数,
                )
            if 结果.内嵌图片数:
                文本 += 译(" · 含图 {数量}", 数量=结果.内嵌图片数)
                提示 += 译(
                    "\n已内嵌图片：{数量} 张（base64 约 {大小} KB）",
                    数量=结果.内嵌图片数,
                    大小=f"{结果.内嵌图片字节 / 1024:.0f}",
                )
            elif 结果.丢弃图片数:
                文本 += 译(" · ⚠ 丢图 {数量}", 数量=结果.丢弃图片数)
                提示 += 译(
                    "\n⚠ 原文中的 {数量} 张图片未保留（勾选「图片内嵌进 .md」可保留）",
                    数量=结果.丢弃图片数,
                )
            if 结果.LLM失败数:
                文本 += 译(" · ⚠ OCR 失败 {数量}", 数量=结果.LLM失败数)
                提示 += "\n⚠ " + 结果.警告
            if 结果.输出文件:
                提示 += 译("\n输出：{路径}", 路径=结果.输出文件)
            return 结果.状态, 文本, 提示
        if 结果.为空:
            return "无文本", 译("无文本"), 译("未提取到文本\n原因：{原因}", 原因=结果.警告)
        return "失败", 译("失败"), 译("失败原因：{错误}", 错误=结果.错误)

    # ── 转换流程 ──────────────────────────────────────────

    def 开始转换(self):
        if self._运行中():
            return
        路径列表 = self._全部路径()
        if not 路径列表:
            QMessageBox.information(self, 译("提示"), 译("请先添加需要转换的文档。"))
            return

        输出方式 = "指定目录" if self.单选_指定目录.isChecked() else "同目录"
        输出目录 = self.输入_输出目录.text().strip()
        if 输出方式 == "指定目录":
            if not 输出目录:
                QMessageBox.warning(
                    self, 译("提示"), 译("请先选择输出目录，或改为保存到源文件所在目录。")
                )
                return
            try:
                os.makedirs(输出目录, exist_ok=True)
            except Exception as 异常:
                QMessageBox.critical(
                    self, 译("无法创建输出目录"), f"{输出目录}\n\n{异常}"
                )
                return

        LLM = self._收集LLM配置()
        LLM问题 = LLM.校验()
        if LLM问题:
            QMessageBox.warning(
                self,
                译("LLM OCR 配置不完整"),
                译(
                    "{问题}\n\n可取消勾选「启用 LLM OCR 识别」，或点它右侧的齿轮按钮补齐配置后重试。",
                    问题=LLM问题,
                ),
            )
            return

        配置 = 后端.转换配置(
            文件列表=路径列表,
            输出方式=输出方式,
            输出目录=os.path.abspath(输出目录) if 输出目录 else 后端.BASE_DIR,
            覆盖已有=self.勾选_覆盖.isChecked(),
            自动保存=self.勾选_自动导出.isChecked(),
            图片内嵌=self.勾选_图片内嵌.isChecked(),
            LLM=LLM,
        )

        # 重置状态
        self.结果表.clear()
        for 条目 in self._全部条目():
            self._设置条目状态(条目, "待转换", 译("待转换"), 译("等待转换"))
        self.文件树.setCurrentItem(self.文件树.topLevelItem(0))
        self.进度条.setRange(0, len(路径列表))
        self.进度条.setValue(0)
        self.进度条.setFormat(f"0 / {len(路径列表)}")
        self.状态标签.setText(译("正在准备转换引擎 …"))
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
            self.状态标签.setText(译("正在取消，请等待当前文件处理结束 …"))
            self._写日志(译("已请求取消，将在当前文件处理完成后停止。"))

    def _进度更新(self, 已完成: int, 总数: int, 文件名: str):
        self.进度条.setRange(0, 总数)
        self.进度条.setValue(已完成)
        self.进度条.setFormat(f"{已完成} / {总数}")
        if 已完成 < 总数:
            self.状态标签.setText(
                译(
                    "正在转换 {已完成}/{总数}：{文件名}",
                    已完成=已完成 + 1,
                    总数=总数,
                    文件名=文件名,
                )
            )

    def _单项完成(self, 结果: 后端.单项结果):
        self.结果表[结果.源文件] = 结果
        条目 = self._找到条目(结果.源文件)
        if 条目 is not None:
            self._回填条目结果(条目, 结果)

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
        self.状态标签.setText(
            译("转换结束：成功 {成功} 个，失败 {失败} 个。", 成功=成功, 失败=失败)
        )

        当前 = self.文件树.currentItem()
        if 当前 is not None:
            self._刷新预览(self._路径(当前))

        详情 = "\n".join(
            (
                译("共处理 {总数} 个文件", 总数=总数),
                译("成功：{数量} 个", 数量=成功),
                译("未提取到文本：{数量} 个", 数量=汇总.get("无文本数", 0)),
                译("失败：{数量} 个", 数量=失败),
                译("已导出 .md：{数量} 个", 数量=导出数),
            )
        )
        if 汇总.get("LLM调用数"):
            详情 += "\n" + 译(
                "LLM OCR：识别 {数量} 处文字，调用模型 {调用数} 次",
                数量=汇总["OCR识别数"],
                调用数=汇总["LLM调用数"],
            )
        if 汇总.get("内嵌图片数"):
            详情 += "\n" + 译("已内嵌图片：{数量} 张", 数量=汇总["内嵌图片数"])
        if 汇总.get("丢弃图片数"):
            详情 += "\n" + 译(
                "未保留图片：{数量} 张（勾选「图片内嵌进 .md」可保留）",
                数量=汇总["丢弃图片数"],
            )
        详情 += "\n" + 译("总用时：{耗时} 秒", 耗时=f"{汇总.get('耗时', 0):.1f}")

        QMessageBox.information(self, 译("转换完成"), 详情)

    def _转换失败(self, 错误: str):
        self.状态标签.setText(译("转换过程发生异常。"))
        self._写日志(译("[错误] {错误}", 错误=错误))
        QMessageBox.critical(self, 译("转换失败"), 错误[:1500])

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
            self.勾选_图片内嵌, self.勾选_LLM, self.按钮_LLM设置,
        ):
            控件.setEnabled(not 运行中)
        self._刷新输出控件(运行中)
        self._刷新LLM状态(运行中)

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
            + 译("尚未转换，转换完成后这里会实时显示 Markdown 预览。")
            + "</div>"
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
                f"{译('<b>转换失败</b>')}<br><br>{self._转义(结果.错误)}</div>"
            )
            self.源码.setPlainText("")
            self.按钮_导出当前.setEnabled(False)
            return

        if 结果.为空:
            self.预览.setHtml(
                "<div style='color:#b45309;font-family:\"Microsoft YaHei UI\";padding:24px;line-height:1.7;'>"
                f"{译('<b>未提取到文本</b>')}<br><br>"
                f"{self._转义(结果.警告)}"
                "<br><br><span style='color:#8b95a3;'>"
                f"{译('该文件已跳过导出，不会生成空的 .md 文件。')}</span></div>"
            )
            self.源码.setPlainText("")
            self.按钮_导出当前.setEnabled(False)
            return

        内容 = 结果.内容
        if len(内容) > 源码字符上限:
            self.源码.setPlainText(
                内容[:源码字符上限]
                + "\n\n"
                + 译(
                    "… 内容过长（共 {总数} 字符），源码视图仅显示前 {上限} 个字符；"
                    "导出的 .md 文件内容完整。",
                    总数=f"{len(内容):,}",
                    上限=f"{源码字符上限:,}",
                )
            )
            self._写日志(
                译(
                    "提示：{文件名} 内容达 {字符数} 字符，源码视图已截断显示。",
                    文件名=结果.文件名,
                    字符数=f"{len(内容):,}",
                )
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
                "<div style='color:#b45309;padding:10px 0;'>"
                + 译(
                    "（文档较长，此处仅渲染前 {上限} 个字符；"
                    "完整内容见「Markdown 源码」页签或已导出的 .md 文件）",
                    上限=f"{预览字符上限:,}",
                )
                + "</div>"
            )
            self._写日志(
                译(
                    "提示：{文件名} 内容较长（{字符数} 字符），预览已截断显示。",
                    文件名=结果.文件名,
                    字符数=f"{len(内容):,}",
                )
            )
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
                译(
                    "提示：预览图片自适应缩放未生效（{类型}），不影响导出结果。",
                    类型=type(异常).__name__,
                )
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
            QMessageBox.information(
                self, 译("提示"), 译("当前预览的文件没有可导出的文本内容。")
            )
            return

        配置 = self._当前输出配置()
        默认路径 = 结果.输出文件 or 后端.计算输出路径(结果.源文件, 配置)
        目标, _ = QFileDialog.getSaveFileName(
            self,
            译("导出为 Markdown 文件"),
            默认路径,
            译("Markdown 文件 (*.md);;所有文件 (*.*)"),
        )
        if not 目标:
            return
        if not os.path.splitext(目标)[1]:
            目标 += ".md"
        try:
            后端.保存文本(目标, 结果.内容)
        except Exception as 异常:
            QMessageBox.critical(self, 译("导出失败"), f"{目标}\n\n{异常}")
            return
        结果.输出文件 = 目标
        条目 = self._找到条目(结果.源文件)
        if 条目 is not None:
            self._回填条目结果(条目, 结果)
        self._写日志(译("已导出 → {路径}", 路径=目标))
        self.状态标签.setText(译("已导出：{文件名}", 文件名=os.path.basename(目标)))

    def 导出全部(self):
        成功结果 = [r for r in self.结果表.values() if r.成功 and not r.为空]
        if not 成功结果:
            QMessageBox.information(
                self, 译("提示"), 译("还没有可导出的转换结果，请先执行转换。")
            )
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
                    self._回填条目结果(条目, 结果)
                self._写日志(译("已导出 → {路径}", 路径=目标))
            except Exception as 异常:
                失败列表.append(译("导出失败 {文件名}：{异常}", 文件名=结果.文件名, 异常=异常))
                self._写日志(
                    译(
                        "[错误] {错误}",
                        错误=译(
                            "导出失败 {文件名}：{异常}", 文件名=结果.文件名, 异常=异常
                        ),
                    )
                )

        汇总文本 = 译("已导出 {数量} 个 .md 文件。", 数量=导出数)
        if 失败列表:
            汇总文本 += "\n" + 译(
                "失败 {数量} 个：\n{列表}", 数量=len(失败列表), 列表="\n".join(失败列表[:8])
            )
        self.状态标签.setText(汇总文本.split("\n")[0])
        QMessageBox.information(self, 译("导出完成"), 汇总文本)

    def 复制源码(self):
        文本 = self.源码.toPlainText()
        if not 文本:
            QMessageBox.information(
                self, 译("提示"), 译("当前没有可复制的 Markdown 内容。")
            )
            return
        QApplication.clipboard().setText(文本)
        self.状态标签.setText(译("已复制 {数量} 个字符到剪贴板。", 数量=f"{len(文本):,}"))

    def 选择输出目录(self):
        目录 = QFileDialog.getExistingDirectory(
            self,
            译("选择输出目录"),
            self.输入_输出目录.text().strip() or getattr(self, "_上次目录", ""),
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
            LLM=self._收集LLM配置(),
        )

    def _刷新输出控件(self, 运行中: bool | None = None):
        运行中 = self._运行中() if 运行中 is None else 运行中
        指定 = self.单选_指定目录.isChecked()
        self.输入_输出目录.setEnabled(指定 and not 运行中)
        self.按钮_浏览.setEnabled(指定 and not 运行中)

    # ── LLM OCR 设置 ──────────────────────────────────────

    def _收集LLM配置(self) -> 后端.LLM配置:
        """当前生效的 LLM 配置：参数来自「设置」窗口，启不启用看主界面开关。"""
        return 替换字段(
            self.LLM配置值,
            启用=self.勾选_LLM.isChecked(),
            # 必须用 默认提示词()（会按界面语言翻译）；直接引用 默认OCR提示词
            # 会绕开翻译表，英文界面下把中文指令发给模型
            提示词=self.LLM配置值.提示词.strip() or 后端.默认提示词(),
        )

    # ── 两项互斥：「图片内嵌」与「LLM OCR」只能勾一个，也可以都不勾 ──

    def _图片内嵌被勾选(self, 勾上: bool):
        if 勾上 and not self._同步勾选中 and self.勾选_LLM.isChecked():
            self._同步勾选中 = True
            self.勾选_LLM.setChecked(False)
            self._同步勾选中 = False
        self._刷新LLM状态()

    def _LLM被勾选(self, 勾上: bool):
        if 勾上 and not self._同步勾选中 and self.勾选_图片内嵌.isChecked():
            self._同步勾选中 = True
            self.勾选_图片内嵌.setChecked(False)
            self._同步勾选中 = False
        self._刷新LLM状态()

    def _刷新LLM状态(self, 运行中: bool | None = None):
        """刷新开关旁的短状态：依赖是否就绪、有没有配模型。"""
        运行中 = self._运行中() if 运行中 is None else 运行中
        启用 = self.勾选_LLM.isChecked()
        模型 = self.LLM配置值.模型.strip()

        self.勾选_LLM.setEnabled(not 运行中)
        self.按钮_LLM设置.setEnabled(not 运行中)

        有插件 = 后端.插件已安装()
        有客户端 = 后端.客户端库已安装()
        if not (有插件 and 有客户端):
            缺项 = []
            if not 有插件:
                缺项.append(译("OCR 插件 {包名}", 包名=后端.OCR插件包名))
            if not 有客户端:
                缺项.append(译("openai 客户端库"))
            self._设LLM状态(
                译("⚠ 缺少 OCR 依赖"),
                "#b45309",
                译("、").join(缺项)
                + "\n"
                + 译(
                    "请执行 pip install {包名} openai 后重启本程序。",
                    包名=后端.OCR插件包名,
                ),
            )
            return

        if not 模型:
            self._设LLM状态(
                译("⚠ 未配置模型") if 启用 else 译("未配置模型"),
                "#b45309" if 启用 else "#9aa5b1",
                译("点右侧齿轮按钮，填入兼容 OpenAI 接口的地址、模型与密钥。"),
            )
            return

        地址 = self.LLM配置值.接口地址.strip() or 译("OpenAI 官方接口")
        显示 = 模型 if len(模型) <= 24 else 模型[:23] + "…"
        self._设LLM状态(
            显示,
            "#059669" if 启用 else "#9aa5b1",
            译(
                "接口：{接口}\n模型：{模型}\n点右侧齿轮按钮可修改。",
                接口=地址,
                模型=模型,
            ),
        )

    def _设LLM状态(self, 文本: str, 颜色: str, 提示: str):
        self.LLM状态标签.setText(文本)
        self.LLM状态标签.setStyleSheet(f"color: {颜色};")
        self.LLM状态标签.setToolTip(提示)

    def 打开LLM设置(self):
        """齿轮按钮：弹出配置窗口，确定后写回内存与配置文件。"""
        if self._运行中():
            return
        self._LLM设置窗口 = LLM设置对话框(self._收集LLM配置(), self)
        try:
            if self._LLM设置窗口.exec() == QDialog.DialogCode.Accepted:
                新值 = self._LLM设置窗口.取值()
                self.LLM配置值 = 新值
                self._保存设置()
                模型 = 新值.模型.strip()
                接口 = 新值.接口地址.strip() or 译("OpenAI 官方接口")
                if 模型:
                    self._写日志(
                        译("[LLM] 配置已更新：{接口} · {模型}", 接口=接口, 模型=模型)
                    )
                    if self.勾选_LLM.isChecked():
                        self._写日志(
                            译("[LLM] 已启用，转换时图片与扫描页会交由该模型识别。")
                        )
                else:
                    self._写日志(译("[LLM] 配置已清空，LLM OCR 暂不可用。"))
                self._刷新LLM状态()
        finally:
            窗口, self._LLM设置窗口 = self._LLM设置窗口, None
            if 窗口 is not None:
                窗口.deleteLater()

    # ── 其它 ──────────────────────────────────────────────

    def _写日志(self, 文本: str):
        # 日志分成「启动横幅」+「正文」两段：横幅随界面语言变，正文是真正的记录
        行 = getattr(self, "_日志行", None)
        if 行 is None:
            return
        行.append(文本)
        del 行[: max(0, len(行) - 日志行数上限)]
        if getattr(self, "日志框", None) is None:
            return
        self.日志框.appendPlainText(文本)
        滚动条 = self.日志框.verticalScrollBar()
        滚动条.setValue(滚动条.maximum())

    def closeEvent(self, 事件):
        if self._运行中():
            选择 = QMessageBox.question(
                self, 译("正在转换"), 译("转换仍在进行中，确定要退出吗？")
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

    # 语言必须在建窗口之前定下来 —— 界面文案是构造控件时写进去的，
    # 建完再改就只能重建界面了（那正是切换语言时做的事）。
    设置 = 配置.打开()
    语言 = str(设置.value("语言", "")) or i18n.跟随系统()
    i18n.设置语言(语言)
    安装Qt内置翻译(应用, i18n.当前语言())

    应用.setApplicationDisplayName(译("文档转 Markdown 工具"))
    应用.setFont(QFont("Microsoft YaHei UI", 10))
    窗口 = 主窗口()
    窗口.show()
    return 应用.exec()


if __name__ == "__main__":
    sys.exit(main())
