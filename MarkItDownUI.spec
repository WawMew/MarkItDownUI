# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：把「文档转 Markdown」打成单个 exe。

用法：
    .venv\\Scripts\\python.exe -m PyInstaller MarkItDownUI.spec --noconfirm

体积取舍（本项目只用 QtCore / QtGui / QtWidgets，其余 Qt 模块一律不带）：
- 剔除 QML / Quick / WebEngine / Multimedia / Sql / Pdf 等未使用的 Qt 模块
- 剔除对应的 Qt 插件目录（sqldrivers、multimedia、tls、iconengines 等）
- 翻译文件只保留简体中文（Qt 自带多语言，未用到的语言约 11 MB）
- 剔除 opengl32sw.dll（软件 OpenGL 回退）与 ANGLE 相关 DLL —— 本项目界面走
  光栅渲染（QWidget + QSS），不请求 OpenGL 上下文，用不到它们
- 图片格式插件只保留常用几种（PNG 由 Qt6Gui 内置，无需插件）
"""

import os
import re

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

_规格路径 = globals().get("SPEC") or globals().get("SPECPATH") or ""
项目目录 = os.path.abspath(os.path.dirname(_规格路径)) if _规格路径 else os.path.abspath(os.getcwd())

# ── 需要随包携带的数据文件 ────────────────────────────────────────
# magika：文件类型嗅探的模型与配置（MarkItDown 在初始化时构造它）
# pdfminer：CMap 资源，缺了它 CJK / CID 字体的 PDF 会提取出乱码
# markitdown-ocr 的 dist-info：插件是靠 importlib.metadata 的 entry point
#   （组名 markitdown.plugin）被发现的，只打包代码不打元数据，
#   在 exe 里 enable_plugins=True 会一个插件都找不到 —— 而且不报错。
数据文件 = []
for 包名 in ("magika", "pdfminer", "charset_normalizer"):
    try:
        数据文件 += collect_data_files(包名)
    except Exception:
        pass
try:
    数据文件 += copy_metadata("markitdown-ocr")
except Exception:
    pass

# ── 明确不打包的 Python 模块 ──────────────────────────────────────
排除模块 = [
    # 本项目只用这三个 Qt 模块，其余不引入
    "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtQuickWidgets",
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineQuick",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets",
    "PyQt6.QtSql", "PyQt6.QtTest", "PyQt6.QtDesigner", "PyQt6.QtHelp",
    "PyQt6.QtBluetooth", "PyQt6.QtNfc", "PyQt6.QtPositioning", "PyQt6.QtSensors",
    "PyQt6.QtSerialPort", "PyQt6.QtWebSockets", "PyQt6.QtWebChannel",
    "PyQt6.QtPdf", "PyQt6.QtPdfWidgets", "PyQt6.QtCharts",
    "PyQt6.QtDataVisualization", "PyQt6.QtGraphs", "PyQt6.QtOpenGL",
    "PyQt6.QtOpenGLWidgets", "PyQt6.QtNetworkAuth", "PyQt6.QtRemoteObjects",
    "PyQt6.QtScxml", "PyQt6.QtSpatialAudio", "PyQt6.QtSvg", "PyQt6.QtSvgWidgets",
    "PyQt6.QtTextToSpeech", "PyQt6.QtStateMachine", "PyQt6.QtHttpServer",
    "PyQt6.QtLocation", "PyQt6.QtNetwork", "PyQt6.QtPrintSupport",
    # 标准库中的测试与开发工具
    # 注意：不能排除 distutils —— PyInstaller 自带 hook 要为 setuptools 的
    # 内嵌版本建立别名，排除它会直接导致分析阶段报错。
    "tkinter", "_tkinter", "unittest", "test", "pydoc", "doctest", "pdb",
    "xmlrpc", "lib2to3", "idlelib", "turtledemo", "curses",
    # 其它明确用不到的第三方库
    "IPython", "jupyter", "notebook", "matplotlib", "scipy", "pytest", "nose",
    "sqlalchemy", "torch", "cv2", "sklearn",
    # PyMuPDF：markitdown-ocr 只在「pdfplumber 打不开的畸形 PDF」时用它兜底渲染，
    # 主路径走 pdfplumber + pypdfium2。它自带 26 MB 的 mupdfcpp64.dll，
    # 压缩后仍会让 exe 涨约 20 MB —— 为这点兜底能力不值得，直接排除。
    "pymupdf", "fitz",
]

# ── Qt 二进制的剔除规则 ───────────────────────────────────────────
丢弃DLL前缀 = re.compile(
    r"^Qt6("
    r"Quick|Qml|ShaderTools|Pdf|Designer|Help|Sql|Test|Multimedia|SpatialAudio|"
    r"WebSockets|WebChannel|Bluetooth|Nfc|Positioning|Sensors|SerialPort|"
    r"RemoteObjects|Scxml|StateMachine|TextToSpeech|VirtualKeyboard|Charts|"
    r"DataVisualization|Graphs|Location|NetworkAuth|HttpServer|OpenGL|Svg|Network"
    r")",
    re.I,
)
丢弃杂项DLL = {
    "opengl32sw.dll",          # 软件 OpenGL 回退，约 20 MB
    "d3dcompiler_47.dll",      # 供 ANGLE / Qt Quick 使用
    "libEGL.dll", "libGLESv2.dll",
}
丢弃插件目录 = {
    "sqldrivers", "sceneparsers", "renderers", "qmlls", "qmllint", "assetimporters",
    "webview", "texttospeech", "sensors", "scxmldatamodel", "position",
    "networkinformation", "multimedia", "help", "geometryloaders", "generic",
    "tls", "iconengines",
}
保留翻译 = {"qtbase_zh_CN.qm", "qt_zh_CN.qm", "qtbase_en.qm"}
保留图片格式 = {"qjpeg.dll", "qgif.dll", "qico.dll", "qwebp.dll", "qtiff.dll"}


def 保留(条目) -> bool:
    目标 = 条目[0].replace("\\", "/")
    名 = os.path.basename(目标).lower()

    if "/qml/" in 目标 or 目标.endswith("/qml"):
        return False

    if "/translations/" in 目标:
        return 名 in {t.lower() for t in 保留翻译}

    if "/imageformats/" in 目标:
        return 名 in 保留图片格式

    if "/plugins/" in 目标:
        for 段 in 目标.split("/plugins/")[-1].split("/")[:-1]:
            if 段 in 丢弃插件目录:
                return False

    if 名 in {d.lower() for d in 丢弃杂项DLL}:
        return False
    if 丢弃DLL前缀.match(os.path.basename(目标)):
        return False
    # FFmpeg 系列（多媒体的传递依赖，命名形如 avcodec-61.dll）
    if re.match(r"^(av|sw|postproc)[a-z_]*-\d+\.dll$", 名):
        return False
    return True


a = Analysis(
    [os.path.join(项目目录, "main.py")],
    pathex=[项目目录],
    binaries=[],
    datas=数据文件,
    hiddenimports=[
        # MarkItDown 各转换器的依赖是函数内延迟导入，静态分析容易漏
        "markitdown", "mammoth", "pptx", "openpyxl", "pandas", "xlrd",
        "pdfminer", "pdfminer.high_level", "pdfplumber", "olefile", "pydub",
        "speech_recognition", "youtube_transcript_api", "bs4", "markdownify",
        "defusedxml", "charset_normalizer", "magika", "onnxruntime",
        "markitdown.converters", "markitdown.converter_utils.docx",
        "markitdown.converter_utils.docx.math",
        # ── LLM OCR ──────────────────────────────────────────────
        # 插件与 openai 都是运行期才导入的（前者靠 entry point 加载，
        # 后者在用户勾选 LLM OCR 时才 import），静态分析扫不到，必须显式列出，
        # 否则 exe 里点「测试连接」只会得到 ModuleNotFoundError。
        "markitdown_ocr",
        "markitdown_ocr._plugin",
        "markitdown_ocr._ocr_service",
        "markitdown_ocr._pdf_converter_with_ocr",
        "markitdown_ocr._docx_converter_with_ocr",
        "markitdown_ocr._pptx_converter_with_ocr",
        "markitdown_ocr._xlsx_converter_with_ocr",
        "docx", "docx.oxml", "docx.oxml.ns", "docx.opc.constants", "docx.shared",
        "PIL", "PIL.Image", "PIL.ImageDraw",
        "openai", "openai._client", "openai._base_client", "openai._models",
        "openai.resources", "openai.resources.chat", "openai.resources.chat.completions",
        "openai.types", "openai.types.chat", "httpx2", "httpx2._client",
        "jiter", "pydantic", "pydantic_core", "truststore",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=排除模块,
    noarchive=False,
    optimize=0,
)

# 按上面的规则过滤 Qt 二进制与数据文件
a.binaries = [条目 for 条目 in a.binaries if 保留(条目)]
a.datas = [条目 for 条目 in a.datas if 保留(条目)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MarkItDownUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 图形界面程序，不弹控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
