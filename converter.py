# -*- coding: utf-8 -*-
"""
文档转 Markdown —— 转换后端
================================================================
基于 Microsoft MarkItDown，把 PDF / Word / PPT / Excel / HTML / 图片 / 音频
等文档转换为 Markdown 文本，并尽量保留原文的标题层级、列表、表格等结构。

关于图片：MarkItDown 默认会把文档内嵌的图片**整张丢弃**（只留下一个加载不出来的
data URI 引用）。需要保留时，把转换配置的「图片内嵌」打开（底层对应
`keep_data_uris=True`），图片会以 base64 原样写进 Markdown —— 字节级无损，
代价是 .md 体积增加约 1/3。

关于 OCR：MarkItDown 内核**没有本地 OCR**。想读出图片 / 扫描件里的文字，需要把
「LLM OCR」打开 —— 底层是官方插件 markitdown-ocr + 一个兼容 OpenAI 接口的视觉
模型（详见下方「三、LLM OCR」）。默认关闭，关闭时行为与旧版完全一致。

本模块与界面完全解耦，既可被 GUI（ui.py）调用，也可直接命令行运行：

    python converter.py 文档1.pdf 文档2.docx -o 输出目录
    python converter.py 报告.pdf              # 默认导出到源文件同目录
    python converter.py 扫描件.pdf --llm-ocr --llm-model gpt-4o
    python converter.py --test-llm --llm-model gpt-4o      # 只测接口连通性
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass, field

import i18n
from i18n import 译

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ────────────────────────────────────────────────────────────────
# 一、支持的文件类型
# ────────────────────────────────────────────────────────────────

# 说明：这里的每一项都经过实测，与 MarkItDown 各转换器真正受理的范围一致。
# 刻意不收录 .doc/.xls/.ppt（旧版二进制，无对应转换器）与 .bmp/.gif/.tiff/.webp
# （图片转换器只受理 png/jpg/jpeg），避免让用户误以为它们能转换。
#
# 这里的值是**中文原文**，同时也是多语言的消息键；对外展示一律走 文件类型说明()，
# 它负责按当前语言取词。别直接拿这个字典去显示。
类型说明: dict[str, str] = {
    ".pdf": "PDF 文档",
    ".docx": "Word 文档",
    ".pptx": "PowerPoint 演示文稿",
    ".xlsx": "Excel 工作簿",
    ".csv": "CSV 表格",
    ".html": "网页文件",
    ".htm": "网页文件",
    ".txt": "纯文本",
    ".text": "纯文本",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".json": "JSON 数据",
    ".jsonl": "JSON Lines 数据",
    ".xml": "XML 数据",
    ".epub": "电子书",
    ".ipynb": "Jupyter Notebook",
    ".msg": "Outlook 邮件",
    ".zip": "压缩包",
    ".png": "图片（仅读取元数据）",
    ".jpg": "图片（仅读取元数据）",
    ".jpeg": "图片（仅读取元数据）",
    ".mp3": "音频（需系统安装 ffmpeg）",
    ".wav": "音频（需系统安装 ffmpeg）",
    ".m4a": "音频（需系统安装 ffmpeg）",
}

# 需要外部引擎才能真正"读出文字"的类型，用于结果为空时给出准确解释
图片扩展名 = {".png", ".jpg", ".jpeg"}
音频扩展名 = {".mp3", ".wav", ".m4a", ".mp4"}
旧版格式扩展名 = {".doc", ".ppt", ".xls"}


def 空内容原因(路径: str, LLM启用: bool = False) -> str:
    """结果为空时，按文件类型给出可执行的原因说明（而不是含糊的"无内容"）。"""
    扩展 = os.path.splitext(路径)[1].lower()
    if 扩展 in 图片扩展名:
        if LLM启用:
            return 译(
                "已启用 LLM OCR，但模型没有返回任何文字：请先用「测试连接」确认接口可用，"
                "再确认这张图里确实有文字"
            )
        return 译(
            "MarkItDown 内置的图片转换器只读取 EXIF 元数据（尺寸、拍摄时间、GPS 等），"
            "不做字符识别（OCR），所以图中的文字读不出来；开启「LLM OCR 识别」即可读出"
        )
    if 扩展 in 音频扩展名:
        return 译("音频转写需要系统已安装 ffmpeg 与语音识别组件，当前环境未就绪")
    if 扩展 == ".pdf":
        if LLM启用:
            return 译(
                "已启用 LLM OCR，但这一页仍未提取到文字：请确认文件能正常打开，"
                "并检查「测试连接」是否通过"
            )
        return 译("该 PDF 没有文本层（多为扫描件或图片型 PDF），开启「LLM OCR 识别」即可提取其中的文字")
    return 译("该文件没有可提取的文本内容")


# ────────────────────────────────────────────────────────────────
# 图片：MarkItDown 默认会把内嵌图片截成 `data:image/png;base64...`
# （那三个点是字面量），载荷被整个丢弃。开启 keep_data_uris 后才是完整 base64。
# 下面两个正则分别用来统计"真正内嵌的图片"和"被丢弃的图片"。
# ────────────────────────────────────────────────────────────────

内嵌图片模式 = re.compile(r"!\[[^\]]*\]\(data:[\w/+.\-]+;base64,([A-Za-z0-9+/=\s]+)\)")
丢弃图片模式 = re.compile(r"!\[[^\]]*\]\(data:[\w/+.\-]+;base64\.\.\.\)")


def 统计内嵌图片(内容: str) -> tuple[int, int]:
    """返回 (图片张数, base64 载荷总字节数)，用于日志与结果展示。"""
    匹配 = 内嵌图片模式.findall(内容)
    return len(匹配), sum(len(载荷) for 载荷 in 匹配)


def 统计丢弃图片(内容: str) -> int:
    """统计被 MarkItDown 丢弃载荷的图片张数（默认参数下的结果）。"""
    return len(丢弃图片模式.findall(内容))


def 图片丢弃提示(张数: int) -> str:
    return 译(
        "原文中的 {数量} 张图片已被丢弃（MarkItDown 默认不保留图片）"
        "；勾选「图片内嵌进 .md」即可保留",
        数量=张数,
    )


def 支持的扩展名() -> list[str]:
    """返回全部受支持的扩展名（小写，含点）。"""
    return sorted(类型说明)


def 是支持的(路径: str) -> bool:
    """判断文件扩展名是否在支持列表内。"""
    return os.path.splitext(路径)[1].lower() in 类型说明


def 文件类型说明(路径: str) -> str:
    return 译(类型说明.get(os.path.splitext(路径)[1].lower(), "未知类型"))


def 构建文件过滤器() -> str:
    """供 QFileDialog 使用的文件类型过滤器字符串。"""
    通配 = " ".join("*" + 扩展 for 扩展 in 支持的扩展名())
    return ";;".join(
        (
            译("全部支持的格式 ({通配})", 通配=通配),
            译("文档类 (*.pdf *.docx *.pptx *.xlsx *.csv *.txt *.md *.html *.json *.xml *.epub *.ipynb *.msg *.zip)"),
            译("图片类（仅元数据） (*.png *.jpg *.jpeg)"),
            译("音频类（需 ffmpeg） (*.mp3 *.wav *.m4a)"),
            译("所有文件 (*.*)"),
        )
    )


# ────────────────────────────────────────────────────────────────
# 二、Markdown 后处理
# ────────────────────────────────────────────────────────────────

def 规整Markdown(文本: str) -> str:
    """
    轻度规整 Markdown：统一换行符、压掉多余空行（代码块内部保持原样）、
    去掉行尾多余空白、保证文件以单个换行结束。

    刻意不做任何“重排”，以免破坏原文的标题层级、列表缩进和表格结构。
    """
    if not 文本:
        return ""
    文本 = 文本.replace("\r\n", "\n").replace("\r", "\n")

    结果: list[str] = []
    连续空行 = 0
    在代码块内 = False

    for 行 in 文本.split("\n"):
        去空格 = 行.strip()
        if 去空格.startswith("```") or 去空格.startswith("~~~"):
            在代码块内 = not 在代码块内
            连续空行 = 0
            结果.append(行.rstrip())
            continue
        if 在代码块内:
            结果.append(行)
            continue
        if not 去空格:
            连续空行 += 1
            if 连续空行 > 1:      # 最多保留一个空行
                continue
            结果.append("")
            continue
        连续空行 = 0
        结果.append(行.rstrip())

    结果文本 = "\n".join(结果).strip()
    return 结果文本 + "\n" if 结果文本 else ""


# ────────────────────────────────────────────────────────────────
# 三、LLM OCR（可选）
# ────────────────────────────────────────────────────────────────
#
# 为什么需要它：MarkItDown 内核**没有任何本地 OCR** —— 扫描件 PDF 提取出来是空的，
# 图片也只读 EXIF 元数据。想真正"读出图里的字"，开箱可用且无需外部引擎的办法，
# 就是让多模态大模型看图识字，对应官方插件 markitdown-ocr：
#
#     pip install markitdown-ocr openai
#
# 该插件把 pdf / docx / pptx / xlsx 四个转换器整体接管（priority -1.0，高于内置的
# 0.0），遇到内嵌图片、或整页抽不出文字（判定为扫描件，按 300 DPI 整页渲染）时，
# 把图片送给视觉模型，用识别结果替换掉图片本身：
#
#     *[Image OCR]
#     <识别出的文字>
#     [End OCR]*
#
# 两个必须知道的坑（本模块都做了处理）：
#   1. 插件只在 llm_client 与 llm_model **同时**非空时才真正干活；少任何一个都会
#      静默退化，输出与没装插件时一模一样 —— 不报错、不提示，极难发现。
#   2. 插件内部把 LLM 异常整个吞掉，只留一个空字符串。401 / 超时 / 模型不支持图片
#      这类问题于是表现为"识别不出文字"。所以下面用客户端包装把调用次数和错误捞回来。
#
# 客户端可以是任何兼容 OpenAI 接口的服务（OpenAI / DeepSeek / 通义 / 智谱 /
# 本地 vLLM、Ollama 等），只要填对「接口地址 + 密钥 + 模型名」三件套即可。

OCR插件包名 = "markitdown-ocr"

# 下面这个常量是默认提示词的**中文原文**，同时也是多语言的消息键。
# 发给模型的指令应当与界面语言一致，所以对外一律用 默认提示词()，别直接引用它。
默认OCR提示词 = (
    "提取这张图片中的全部文字或表格，按原始阅读顺序输出，尽量用 Markdown 代码块标记。"
    "如果图片不是文字也不是表格，请描述这个文件"
)

OCRBEGIN = "[Image OCR]"


def 默认提示词() -> str:
    """当前界面语言下的默认 OCR 提示词。"""
    return 译(默认OCR提示词)


def 是默认提示词(文本: str) -> bool:
    """
    判断一段提示词是否只是"照抄了默认值"（不管哪个语言的默认值）。

    界面保存配置时用它把默认值折成空串 —— 这样用户切换语言后，提示词会自动
    跟着换成新语言的默认版本，而不是把旧语言的默认文本硬留下来。
    """
    if not (文本 or "").strip():
        return True
    for 语言代码 in (i18n.默认语言, *[码 for 码, _ in i18n.可用语言()]):
        旧语言 = i18n.设置语言(语言代码)
        try:
            默认 = 译(默认OCR提示词)
        finally:
            i18n.设置语言(旧语言)
        if 文本.strip() == 默认.strip():
            return True
    return False


@dataclass
class LLM配置:
    """LLM OCR 的全部参数（纯数据，可安全跨线程传递）。"""

    启用: bool = False
    接口地址: str = ""                       # 留空 = OpenAI 官方 https://api.openai.com/v1
    密钥: str = ""                           # 留空时回退到环境变量 OPENAI_API_KEY
    模型: str = ""                           # 必须是支持图片输入的模型
    提示词: str = field(default_factory=默认提示词)   # 空 = 用当前语言的默认提示词
    超时: float = 120.0                      # 单张图片的识别超时（秒）

    @property
    def 指纹(self) -> tuple:
        """配置指纹：任一项变化都要重建引擎，否则会继续用旧客户端。"""
        return (self.启用, self.接口地址, self.密钥, self.模型, self.提示词, self.超时)

    def 校验(self) -> str:
        """返回阻塞性问题；空字符串表示可以开工。"""
        if not self.启用:
            return ""
        if not (self.模型 or "").strip():
            return 译(
                "请先填写模型名称（需支持图片输入，如 gpt-4o / qwen-vl-max / "
                "glm-4v / doubao-vision 等）"
            )
        if not 插件已安装():
            return 译("未安装 OCR 插件，请在项目环境执行：pip install {包名}", 包名=OCR插件包名)
        if not 客户端库已安装():
            return 译("未安装 openai 客户端库，请在项目环境执行：pip install openai")
        return ""


def 插件已安装() -> bool:
    try:
        from importlib.util import find_spec
        return find_spec("markitdown_ocr") is not None
    except Exception:  # pragma: no cover
        return False


def 客户端库已安装() -> bool:
    try:
        from importlib.util import find_spec
        return find_spec("openai") is not None
    except Exception:  # pragma: no cover
        return False


@dataclass
class LLM统计:
    """一次转换中的 LLM 调用统计，同时充当「插件内部错误」的输出通道。"""

    调用次数: int = 0
    失败次数: int = 0
    识别字符数: int = 0
    错误列表: list = field(default_factory=list)
    日志: object = None                     # 回调，接收一行文本

    def 归零(self):
        self.调用次数 = 0
        self.失败次数 = 0
        self.识别字符数 = 0
        self.错误列表.clear()

    @property
    def 有错误(self) -> bool:
        return bool(self.错误列表)

    @property
    def 首个错误(self) -> str:
        return self.错误列表[0] if self.错误列表 else ""

    def 记录(self, 文本: str):
        if callable(self.日志):
            self.日志(文本)


# 与引擎同生命周期的统计对象：插件拿到的客户端始终指向它，
# 每个文件转换前调用 归零()。
LLM调用统计 = LLM统计()


class _补全代理:
    """代理 chat.completions，登记调用次数并把异常写进日志。"""

    def __init__(self, 真实, 统计: LLM统计):
        self._真实 = 真实
        self._统计 = 统计

    def create(self, **参数):
        self._统计.调用次数 += 1
        try:
            响应 = self._真实.create(**参数)
        except Exception as 异常:
            self._统计.失败次数 += 1
            信息 = f"{type(异常).__name__}: {异常}"
            if 信息 not in self._统计.错误列表:
                self._统计.错误列表.append(信息)
            self._统计.记录(
                译(
                    "    ⚠ LLM OCR 调用失败（模型 {模型}）：{错误}",
                    模型=参数.get("model", ""),
                    错误=信息,
                )
            )
            raise               # 插件会吞掉，但错误已经留痕
        try:
            文本 = 响应.choices[0].message.content or ""
            self._统计.识别字符数 += len(文本)
        except Exception:
            pass
        return 响应

    def __getattr__(self, 名: str):
        return getattr(self._真实, 名)


class _Chat代理:
    def __init__(self, 真实, 统计: LLM统计):
        self._真实 = 真实
        self.completions = _补全代理(真实.completions, 统计)

    def __getattr__(self, 名: str):
        return getattr(self._真实, 名)


class LLM客户端包装:
    """
    对任意 OpenAI 兼容客户端做一层薄包装。

    目的只有一个：把插件吞掉的错误、以及肉眼看不见的调用次数捞回来。
    只要对象长得像 OpenAI 客户端（具备 .chat.completions.create），
    插件就能正常使用 —— 这正是"兼容 OpenAI 接口即可"的含义。
    """

    def __init__(self, 客户端, 统计: LLM统计):
        self._客户端 = 客户端
        self.chat = _Chat代理(客户端.chat, 统计)

    def __getattr__(self, 名: str):
        return getattr(self._客户端, 名)


def 构建LLM客户端(LLM: LLM配置, 统计: LLM统计 | None = None):
    """按配置构造 OpenAI 兼容客户端（密钥缺失时回退到环境变量）。"""
    统计 = 统计 or LLM调用统计
    try:
        from openai import OpenAI
    except ImportError as 异常:
        raise RuntimeError(
            译("未安装 openai 客户端库，无法启用 LLM OCR。请执行：pip install openai")
        ) from 异常

    密钥 = (LLM.密钥 or "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    if not 密钥:
        # 不少自建 / 本地服务（Ollama、vLLM 等）不校验密钥，但 SDK 要求非空
        密钥 = "not-needed"

    参数 = {"api_key": 密钥, "timeout": float(LLM.超时 or 120.0), "max_retries": 1}
    地址 = (LLM.接口地址 or "").strip()
    if 地址:
        参数["base_url"] = 地址

    try:
        return LLM客户端包装(OpenAI(**参数), 统计)
    except Exception as 异常:
        raise RuntimeError(
            译(
                "初始化 LLM 客户端失败：{类型}: {异常}",
                类型=type(异常).__name__,
                异常=异常,
            )
        ) from 异常


# 一张 1×1 的 PNG，仅在 PIL 不可用时兜底
_极小PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _测试用图片() -> str:
    """生成一张小图并转成 data URI（只用于连通性测试）。"""
    import base64

    try:
        import io

        from PIL import Image, ImageDraw

        缓冲 = io.BytesIO()
        图 = Image.new("RGB", (96, 96), "white")
        ImageDraw.Draw(图).rectangle([8, 8, 87, 87], outline="black", width=3)
        图.save(缓冲, format="PNG")
        return "data:image/png;base64," + base64.b64encode(缓冲.getvalue()).decode("ascii")
    except Exception:
        return "data:image/png;base64," + _极小PNG


def 测试LLM连接(LLM: LLM配置, 日志=None) -> tuple[bool, str]:
    """
    发一次真实请求验证「接口地址 + 密钥 + 模型」是否可用。

    返回 (是否成功, 说明文本)。这是唯一能在转换之前发现 401 / 模型不存在 /
    网络不通的办法 —— 否则这些问题会被插件吞成"识别不出文字"。
    """
    问题 = LLM.校验()
    if 问题:
        return False, 问题

    统计 = LLM统计(日志=日志)
    try:
        客户端 = 构建LLM客户端(LLM, 统计)
    except Exception as 异常:
        return False, str(异常)

    模型 = LLM.模型.strip()
    try:
        响应 = 客户端.chat.completions.create(
            model=模型,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": LLM.提示词.strip() or 默认提示词()},
                        {"type": "image_url", "image_url": {"url": _测试用图片()}},
                    ],
                }
            ],
        )
        文本 = (响应.choices[0].message.content or "").strip()
    except Exception as 异常:
        return False, 译("调用失败：{类型}: {异常}", 类型=type(异常).__name__, 异常=异常)

    if not 文本:
        return True, 译(
            "连接成功（模型 {模型} 有响应，但没有返回文字 —— 测试图里本来也没有字，属正常）。",
            模型=模型,
        )
    return True, 译("连接成功，模型 {模型} 已返回 {字符数} 个字符。", 模型=模型, 字符数=len(文本))


# ────────────────────────────────────────────────────────────────
# 四、转换引擎
# ────────────────────────────────────────────────────────────────

_引擎 = None
_引擎键 = None


def 引擎版本() -> str:
    try:
        from importlib.metadata import version
        return version("markitdown")
    except Exception:
        return 译("未知")


def 获取引擎(日志=None, LLM: LLM配置 | None = None):
    """
    惰性加载 MarkItDown 引擎。

    LLM 启用时走插件路径（enable_plugins=True + llm_client + llm_model +
    llm_prompt），否则只用内置转换器，行为与旧版完全一致。
    引擎按配置指纹缓存，配置一改立即重建。
    """
    global _引擎, _引擎键

    LLM = LLM or LLM配置()
    问题 = LLM.校验()
    if 问题:
        raise RuntimeError(问题)

    键 = LLM.指纹
    if _引擎 is not None and _引擎键 == 键:
        LLM调用统计.日志 = 日志
        return _引擎

    if 日志:
        日志(译("正在加载 MarkItDown 转换引擎 …"))
    try:
        from markitdown import MarkItDown
    except ImportError as 异常:  # pragma: no cover
        raise RuntimeError(
            译("未安装 markitdown 依赖，请执行：pip install \"markitdown[all]\"")
        ) from 异常

    if LLM.启用:
        LLM调用统计.日志 = 日志
        客户端 = 构建LLM客户端(LLM, LLM调用统计)      # 依赖缺失时在这里抛出，信息清晰
        模型 = LLM.模型.strip()
        参数 = {
            "enable_plugins": True,
            "llm_client": 客户端,
            "llm_model": 模型,
            "llm_prompt": LLM.提示词.strip() or 默认提示词(),
        }
        if 日志:
            日志(
                译(
                    "LLM OCR 已启用：{接口} · 模型 {模型}",
                    接口=LLM.接口地址.strip() or 译("OpenAI 官方接口"),
                    模型=模型,
                )
            )
    else:
        参数 = {"enable_plugins": False}

    try:
        _引擎 = MarkItDown(**参数)
    except TypeError:
        # 兼容不支持 enable_plugins 参数的旧版本
        if LLM.启用:
            raise RuntimeError(
                译(
                    "当前 MarkItDown 版本不支持插件机制，无法启用 LLM OCR，"
                    "请升级：pip install -U \"markitdown[all]\""
                )
            )
        _引擎 = MarkItDown()

    _引擎键 = 键
    if 日志:
        日志(译("转换引擎就绪：MarkItDown {版本}", 版本=引擎版本()))
    return _引擎


def 转换文件(
    路径: str,
    日志=None,
    图片内嵌: bool = False,
    LLM: "LLM配置 | None" = None,
) -> str:
    """
    把单个文件转换为 Markdown 文本，异常向上抛出由调用方处理。

    图片内嵌=True 时，文档内嵌图片会以 base64 原样写进结果（体积约 +1/3）；
    为 False（默认）时，图片载荷会被 MarkItDown 丢弃，只留一个失效的引用。

    LLM.启用=True 时会额外走 OCR 插件：pdf/docx/pptx/xlsx 里的图片与扫描整页
    会被识别成文字（此时这些格式的「图片内嵌」不再生效，因为图片已被文字替换）；
    html/epub 等插件未接管的格式仍照常内嵌图片，两者互不干扰。
    """
    路径 = os.path.abspath(路径)
    if not os.path.isfile(路径):
        raise FileNotFoundError(译("文件不存在：{路径}", 路径=路径))
    if not 是支持的(路径):
        扩展 = os.path.splitext(路径)[1].lower() or 译("（无扩展名）")
        提示 = ""
        if 扩展 in 旧版格式扩展名:
            提示 = 译("。旧版二进制格式不受支持，请先用 Office / WPS 另存为 .docx / .xlsx / .pptx")
        elif 扩展 in {".bmp", ".gif", ".tif", ".tiff", ".webp"}:
            提示 = 译("。图片转换器只受理 .png / .jpg / .jpeg，请先转换图片格式")
        raise ValueError(译("暂不支持的文件类型：{扩展}{提示}", 扩展=扩展, 提示=提示))

    引擎 = 获取引擎(日志, LLM)
    # keep_data_uris 只能作为 convert() 的 kwargs 传入（MarkItDown.__init__ 不接受它）
    结果 = 引擎.convert(路径, keep_data_uris=True) if 图片内嵌 else 引擎.convert(路径)
    文本 = getattr(结果, "text_content", "") or ""
    return 规整Markdown(文本)


def 保存文本(路径: str, 内容: str, 编码: str = "utf-8") -> str:
    """把 Markdown 文本写入磁盘，自动创建上级目录。"""
    目录 = os.path.dirname(os.path.abspath(路径))
    if 目录:
        os.makedirs(目录, exist_ok=True)
    with open(路径, "w", encoding=编码, newline="\n") as 句柄:
        句柄.write(内容)
    return 路径


def 计算输出路径(源文件: str, 配置: "转换配置") -> str:
    """
    根据配置推导 .md 输出路径：
    - 输出方式为「同目录」→ 与源文件同目录；
    - 输出方式为「指定目录」→ 集中放到配置的输出目录下；
    - 未勾选「覆盖已有」时，自动追加 _1 / _2 避免覆盖既有文件。
    """
    基名 = os.path.splitext(os.path.basename(源文件))[0] + ".md"
    if 配置.输出方式 == "指定目录":
        目录 = 配置.输出目录 or BASE_DIR
    else:
        目录 = os.path.dirname(os.path.abspath(源文件))
    os.makedirs(目录, exist_ok=True)

    目标 = os.path.join(目录, 基名)
    if 配置.覆盖已有 or not os.path.exists(目标):
        return 目标

    根, 扩展 = os.path.splitext(目标)
    序号 = 1
    while os.path.exists(f"{根}_{序号}{扩展}"):
        序号 += 1
    return f"{根}_{序号}{扩展}"


def 收集文件(路径列表, 递归: bool = True) -> list[str]:
    """把文件/目录混合的输入展开成去重后的绝对文件路径列表。"""
    收集: list[str] = []
    已见: set[str] = set()

    def 收录(单个: str) -> None:
        绝对 = os.path.abspath(单个)
        键 = 绝对.lower() if os.name == "nt" else 绝对
        if 键 in 已见:
            return
        已见.add(键)
        收集.append(绝对)

    for 条目 in 路径列表:
        if os.path.isdir(条目):
            遍历 = os.walk(条目) if 递归 else [(条目, [], os.listdir(条目))]
            for 当前目录, _, 文件名列表 in 遍历:
                for 文件名 in 文件名列表:
                    if 文件名.startswith(("~$", ".", "__")):
                        continue
                    完整 = os.path.join(当前目录, 文件名)
                    if os.path.isfile(完整) and 是支持的(完整):
                        收录(完整)
        elif os.path.isfile(条目):
            收录(条目)
    return 收集


# ────────────────────────────────────────────────────────────────
# 五、批量转换
# ────────────────────────────────────────────────────────────────

@dataclass
class 转换配置:
    """一次批量转换的全部参数（纯数据，可安全地传给工作线程）。"""

    文件列表: list = field(default_factory=list)
    输出方式: str = "同目录"          # 「同目录」或「指定目录」
    输出目录: str = BASE_DIR
    覆盖已有: bool = True
    自动保存: bool = True
    图片内嵌: bool = False            # True = 把文档内嵌图片以 base64 保留进 .md
    LLM: LLM配置 = field(default_factory=LLM配置)   # LLM OCR（默认关闭）

    @property
    def 文件数(self) -> int:
        return len(self.文件列表)


@dataclass
class 单项结果:
    """单个文件的转换结果。"""

    序号: int = 0
    源文件: str = ""
    内容: str = ""
    输出文件: str = ""
    成功: bool = False
    错误: str = ""
    警告: str = ""
    耗时: float = 0.0
    内嵌图片数: int = 0
    内嵌图片字节: int = 0
    丢弃图片数: int = 0
    OCR识别数: int = 0                # 结果里 [Image OCR] 块的个数
    LLM调用数: int = 0                # 本次转换实际发起的模型调用次数
    LLM失败数: int = 0

    @property
    def 文件名(self) -> str:
        return os.path.basename(self.源文件)

    @property
    def 字符数(self) -> int:
        return len(self.内容)

    @property
    def 为空(self) -> bool:
        """转换"成功"但一个字都没提取到（典型：扫描件、图片）。"""
        return self.成功 and not self.内容.strip()

    @property
    def 状态(self) -> str:
        if not self.成功:
            return "失败"
        if self.为空:
            return "无文本"
        return "已导出" if self.输出文件 else "已完成"

    def 转字典(self) -> dict:
        return {
            "序号": self.序号,
            "源文件": self.源文件,
            "输出文件": self.输出文件,
            "成功": self.成功,
            "错误": self.错误,
            "警告": self.警告,
            "字符数": self.字符数,
            "内嵌图片数": self.内嵌图片数,
            "丢弃图片数": self.丢弃图片数,
            "OCR识别数": self.OCR识别数,
            "LLM调用数": self.LLM调用数,
            "耗时": round(self.耗时, 3),
        }


def 运行(
    配置: 转换配置,
    日志=print,
    进度=None,
    单项完成=None,
    取消检查=None,
) -> dict:
    """
    执行批量转换。

    参数
    ----
    配置     : 转换配置 实例
    日志     : 回调，接收一行日志文本
    进度     : 回调 (已完成数, 总数, 当前文件名)
    单项完成 : 回调，接收 单项结果（用于界面即时刷新）
    取消检查 : 无参回调，返回 True 时中断本次批处理

    返回
    ----
    dict: {总数, 成功数, 无文本数, 失败数, 耗时, 结果列表, 导出文件列表}
    """
    文件列表 = list(配置.文件列表)
    总数 = len(文件列表)
    起始 = time.time()
    结果列表: list[单项结果] = []
    导出文件: list[str] = []
    成功数 = 失败数 = 无文本数 = 0
    内嵌图片总数 = 丢弃图片总数 = 0
    OCR总数 = LLM调用总数 = LLM失败总数 = 0

    if 总数 == 0:
        日志(译("没有待转换的文件。"))
        return {
            "总数": 0, "成功数": 0, "无文本数": 0, "失败数": 0,
            "内嵌图片数": 0, "丢弃图片数": 0,
            "OCR识别数": 0, "LLM调用数": 0,
            "耗时": 0.0, "结果列表": [], "导出文件列表": [],
        }

    LLM = 配置.LLM
    日志(译("开始转换，共 {总数} 个文件。", 总数=总数))
    if 配置.图片内嵌:
        if LLM.启用:
            日志(
                译(
                    "图片内嵌已开启：HTML / EPUB 等格式的图片会以 base64 写入 .md；"
                    "PDF / Word / PPT / Excel 的图片会被 LLM OCR 替换成识别出的文字。"
                )
            )
        else:
            日志(译("图片内嵌已开启：文档中的图片会以 base64 原样写入 .md（体积约 +1/3）。"))
    if LLM.启用:
        日志(
            译(
                "LLM OCR 已开启：{接口} · 模型 {模型}。识别会调用视觉模型，按图计费、耗时更长。",
                接口=LLM.接口地址.strip() or 译("OpenAI 官方接口"),
                模型=LLM.模型.strip(),
            )
        )
    # 预热引擎。LLM 配置有问题（缺模型、缺依赖）会在这里就抛出，
    # 避免每个文件都报一遍同样的错。
    获取引擎(日志, LLM)

    for 序号, 源文件 in enumerate(文件列表, start=1):
        if 取消检查 and 取消检查():
            日志(译("任务已取消，剩余 {数量} 个文件未处理。", 数量=总数 - 序号 + 1))
            break

        文件名 = os.path.basename(源文件)
        if 进度:
            进度(序号 - 1, 总数, 文件名)

        结果 = 单项结果(序号=序号, 源文件=源文件)
        单次开始 = time.time()

        if not os.path.isfile(源文件):
            结果.错误 = 译("文件不存在或已被移动")
        else:
            日志(
                译(
                    "[{序号}/{总数}] {文件名}  —— {类型}",
                    序号=序号,
                    总数=总数,
                    文件名=文件名,
                    类型=文件类型说明(源文件),
                )
            )
            try:
                LLM调用统计.归零()
                结果.内容 = 转换文件(源文件, 图片内嵌=配置.图片内嵌, LLM=LLM)
                结果.成功 = True
                结果.耗时 = time.time() - 单次开始
                结果.LLM调用数 = LLM调用统计.调用次数
                结果.LLM失败数 = LLM调用统计.失败次数
                结果.OCR识别数 = 结果.内容.count(OCRBEGIN)
                if 结果.为空:
                    无文本数 += 1
                    结果.警告 = 空内容原因(源文件, LLM.启用)
                    日志(译("    未提取到文本：{原因}", 原因=结果.警告))
                else:
                    成功数 += 1
                    备注 = ""
                    if 配置.图片内嵌:
                        张数, 载荷 = 统计内嵌图片(结果.内容)
                        结果.内嵌图片数 = 张数
                        结果.内嵌图片字节 = 载荷
                        内嵌图片总数 += 张数
                        if 张数:
                            备注 = 译(
                                "，已内嵌 {数量} 张图片（base64 约 {大小} KB）",
                                数量=张数,
                                大小=f"{载荷 / 1024:.0f}",
                            )
                    else:
                        丢弃 = 统计丢弃图片(结果.内容)
                        if 丢弃:
                            结果.丢弃图片数 = 丢弃
                            丢弃图片总数 += 丢弃
                            结果.警告 = 图片丢弃提示(丢弃)
                            备注 = 译("，⚠ 丢弃了 {数量} 张图片", 数量=丢弃)
                    if LLM.启用:
                        OCR总数 += 结果.OCR识别数
                        LLM调用总数 += 结果.LLM调用数
                        LLM失败总数 += 结果.LLM失败数
                        if 结果.OCR识别数:
                            备注 += 译("，OCR 识别 {数量} 处", 数量=结果.OCR识别数)
                        elif 结果.LLM调用数:
                            备注 += 译(
                                "，调用了模型 {数量} 次但没有返回文字", 数量=结果.LLM调用数
                            )
                        else:
                            备注 += 译("，未发现需要识别的图片")
                    if 结果.LLM失败数:
                        结果.警告 = 译(
                            "有 {数量} 次 OCR 调用失败：{错误}",
                            数量=结果.LLM失败数,
                            错误=LLM调用统计.首个错误,
                        )
                        日志(f"    ⚠ {结果.警告}")
                    日志(
                        译(
                            "    已完成，{字符数} 字符，用时 {耗时} 秒{备注}",
                            字符数=结果.字符数,
                            耗时=f"{结果.耗时:.1f}",
                            备注=备注,
                        )
                    )
            except Exception as 异常:
                结果.耗时 = time.time() - 单次开始
                结果.错误 = f"{type(异常).__name__}: {异常}"
                失败数 += 1
                日志(译("    转换失败：{错误}", 错误=结果.错误))

        if 结果.成功 and not 结果.为空 and 配置.自动保存:
            try:
                结果.输出文件 = 计算输出路径(源文件, 配置)
                保存文本(结果.输出文件, 结果.内容)
                导出文件.append(结果.输出文件)
                日志(译("    已导出 → {路径}", 路径=结果.输出文件))
            except Exception as 异常:
                结果.输出文件 = ""
                日志(译("    导出失败：{类型}: {异常}", 类型=type(异常).__name__, 异常=异常))
        elif 结果.为空 and 配置.自动保存:
            日志(译("    已跳过导出，避免生成空的 .md 文件。"))

        结果列表.append(结果)
        if 单项完成:
            单项完成(结果)
        if 进度:
            进度(序号, 总数, 文件名)

    耗时 = time.time() - 起始
    小结 = 译("全部结束：成功 {成功} 个", 成功=成功数)
    if 无文本数:
        小结 += 译("，未提取到文本 {数量} 个（见上方原因）", 数量=无文本数)
    小结 += 译(
        "，失败 {数量} 个，共导出 {导出} 个 .md 文件，总用时 {耗时} 秒。",
        数量=失败数,
        导出=len(导出文件),
        耗时=f"{耗时:.1f}",
    )
    日志(小结)
    if 内嵌图片总数:
        日志(译("图片：已内嵌 {数量} 张（base64 原样保留）。", 数量=内嵌图片总数))
    if 丢弃图片总数:
        日志(
            译(
                "图片：有 {数量} 张图片未保留，勾选「图片内嵌进 .md」可保留。",
                数量=丢弃图片总数,
            )
        )
    if LLM.启用:
        日志(
            译(
                "LLM OCR：共识别 {数量} 处文字，调用模型 {调用数} 次",
                数量=OCR总数,
                调用数=LLM调用总数,
            )
            + (
                译("，其中 {数量} 次失败（详见上方日志）。", 数量=LLM失败总数)
                if LLM失败总数
                else 译("。")
            )
        )
        if OCR总数 == 0 and LLM调用总数 == 0 and 成功数 and not 配置.图片内嵌:
            日志(
                译(
                    "提示：本次没有任何图片需要识别。若期望识别扫描件却毫无动静，"
                    "请先用界面的「测试连接」确认接口可用。"
                )
            )
    return {
        "总数": 总数,
        "成功数": 成功数,
        "无文本数": 无文本数,
        "失败数": 失败数,
        "内嵌图片数": 内嵌图片总数,
        "丢弃图片数": 丢弃图片总数,
        "OCR识别数": OCR总数,
        "LLM调用数": LLM调用总数,
        "耗时": 耗时,
        "结果列表": 结果列表,
        "导出文件列表": 导出文件,
    }


# ────────────────────────────────────────────────────────────────
# 六、命令行入口
# ────────────────────────────────────────────────────────────────

def _命令行(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # 语言必须在构造 ArgumentParser 之前定下来 —— 帮助文本是在 parse_args 时
    # 按当前语言生成的，晚一步就会一半中文一半英文。所以先手扫一遍 --lang。
    预扫语言 = ""
    for 下标, 项 in enumerate(argv):
        if 项.startswith("--lang="):
            预扫语言 = 项.split("=", 1)[1]
        elif 项 == "--lang" and 下标 + 1 < len(argv):
            预扫语言 = argv[下标 + 1]
    i18n.设置语言(预扫语言 or i18n.跟随系统())

    解析器 = argparse.ArgumentParser(
        description=译("文档转 Markdown 工具（后端，基于 Microsoft MarkItDown）")
    )
    解析器.add_argument("文件", nargs="*", help=译("待转换的文件或目录，可多个"))
    解析器.add_argument(
        "-o", "--output", default="", help=译("输出目录，默认与源文件同目录")
    )
    解析器.add_argument(
        "--no-overwrite", action="store_true", help=译("不覆盖已存在的同名 .md")
    )
    解析器.add_argument(
        "--no-save", action="store_true",
        help=译("只转换不写文件（仅打印字符数）"),
    )
    解析器.add_argument(
        "--keep-images", action="store_true",
        help=译("把文档内嵌图片以 base64 原样写进 .md（体积约 +1/3；默认丢弃）"),
    )
    解析器.add_argument(
        "--lang", default="", metavar="LANG",
        help=译("界面语言：zh 或 en，默认跟随系统"),
    )

    OCR = 解析器.add_argument_group(
        译("LLM OCR（可选）"),
        译(
            "用视觉大模型识别图片与扫描件中的文字，需先安装：pip install {包名} openai",
            包名=OCR插件包名,
        ),
    )
    OCR.add_argument(
        "--llm-ocr", action="store_true",
        help=译("启用 LLM OCR（识别 PDF / Word / PPT / Excel 里的图片与扫描整页）"),
    )
    OCR.add_argument(
        "--llm-base-url", default="",
        help=译("兼容 OpenAI 接口的服务地址，如 https://api.deepseek.com/v1；留空用 OpenAI 官方"),
    )
    OCR.add_argument(
        "--llm-api-key", default="",
        help=译("接口密钥；留空则读取环境变量 OPENAI_API_KEY（本地无鉴权服务可随意留空）"),
    )
    OCR.add_argument(
        "--llm-model", default="",
        help=译("视觉模型名，需支持图片输入，如 gpt-4o / qwen-vl-max / glm-4v / doubao-vision"),
    )
    OCR.add_argument("--llm-prompt", default="", help=译("自定义识别提示词"))
    OCR.add_argument(
        "--test-llm", action="store_true",
        help=译("只测试「地址 + 密钥 + 模型」是否可用，不转换任何文件"),
    )
    参数 = 解析器.parse_args(argv)

    # --lang 的具体取值已在上面统一设置过，这里只需处理"没给就用系统语言"的情况
    if 参数.lang:
        i18n.设置语言(参数.lang)

    LLM = LLM配置(
        启用=bool(参数.llm_ocr or 参数.test_llm),
        接口地址=参数.llm_base_url,
        密钥=参数.llm_api_key,
        模型=参数.llm_model,
        提示词=参数.llm_prompt.strip() or 默认提示词(),
    )

    if 参数.test_llm:
        成功, 说明 = 测试LLM连接(LLM, 日志=lambda 文本: print(文本))
        print(("✔ " if 成功 else "✘ ") + 说明)
        return 0 if 成功 else 1

    if not 参数.文件:
        解析器.print_help()
        return 0

    文件列表 = 收集文件(参数.文件)
    if not 文件列表:
        print(译("未找到可转换的文件。"))
        return 1

    配置 = 转换配置(
        文件列表=文件列表,
        输出方式="指定目录" if 参数.output else "同目录",
        输出目录=os.path.abspath(参数.output) if 参数.output else BASE_DIR,
        覆盖已有=not 参数.no_overwrite,
        自动保存=not 参数.no_save,
        图片内嵌=参数.keep_images,
        LLM=LLM,
    )
    try:
        结果 = 运行(配置)
    except RuntimeError as 异常:
        print(译("错误：{异常}", 异常=异常))
        return 1

    摘要 = "\n" + 译("完成：成功 {成功} 个", 成功=结果["成功数"])
    if 结果.get("无文本数"):
        摘要 += 译("，未提取到文本 {数量} 个", 数量=结果["无文本数"])
    摘要 += 译("，失败 {数量} 个。", 数量=结果["失败数"])
    if 结果.get("内嵌图片数"):
        摘要 += "\n" + 译("已内嵌图片：{数量} 张", 数量=结果["内嵌图片数"])
    if 结果.get("丢弃图片数"):
        摘要 += "\n" + 译("未保留图片：{数量} 张（加 --keep-images 可保留）", 数量=结果["丢弃图片数"])
    if LLM.启用:
        摘要 += "\n" + 译(
            "LLM OCR：识别 {数量} 处，调用模型 {调用数} 次",
            数量=结果.get("OCR识别数", 0),
            调用数=结果.get("LLM调用数", 0),
        )
    print(摘要)
    return 0 if 结果["失败数"] == 0 else 1


if __name__ == "__main__":
    sys.exit(_命令行())
