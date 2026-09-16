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

本模块与界面完全解耦，既可被 GUI（ui.py）调用，也可直接命令行运行：

    python converter.py 文档1.pdf 文档2.docx -o 输出目录
    python converter.py 报告.pdf              # 默认导出到源文件同目录
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass, field

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ────────────────────────────────────────────────────────────────
# 一、支持的文件类型
# ────────────────────────────────────────────────────────────────

# 说明：这里的每一项都经过实测，与 MarkItDown 各转换器真正受理的范围一致。
# 刻意不收录 .doc/.xls/.ppt（旧版二进制，无对应转换器）与 .bmp/.gif/.tiff/.webp
# （图片转换器只受理 png/jpg/jpeg），避免让用户误以为它们能转换。
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


def 空内容原因(路径: str) -> str:
    """结果为空时，按文件类型给出可执行的原因说明（而不是含糊的"无内容"）。"""
    扩展 = os.path.splitext(路径)[1].lower()
    if 扩展 in 图片扩展名:
        return (
            "MarkItDown 内置的图片转换器只读取 EXIF 元数据（尺寸、拍摄时间、GPS 等），"
            "不做字符识别（OCR），所以图中的文字读不出来"
        )
    if 扩展 in 音频扩展名:
        return "音频转写需要系统已安装 ffmpeg 与语音识别组件，当前环境未就绪"
    if 扩展 == ".pdf":
        return "该 PDF 没有文本层（多为扫描件或图片型 PDF），需要 OCR 引擎才能提取文字"
    return "该文件没有可提取的文本内容"


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
    return (
        f"原文中的 {张数} 张图片已被丢弃（MarkItDown 默认不保留图片）"
        "；勾选「图片内嵌进 .md」即可保留"
    )


def 支持的扩展名() -> list[str]:
    """返回全部受支持的扩展名（小写，含点）。"""
    return sorted(类型说明)


def 是支持的(路径: str) -> bool:
    """判断文件扩展名是否在支持列表内。"""
    return os.path.splitext(路径)[1].lower() in 类型说明


def 文件类型说明(路径: str) -> str:
    return 类型说明.get(os.path.splitext(路径)[1].lower(), "未知类型")


def 构建文件过滤器() -> str:
    """供 QFileDialog 使用的文件类型过滤器字符串。"""
    通配 = " ".join("*" + 扩展 for 扩展 in 支持的扩展名())
    return (
        f"全部支持的格式 ({通配});;"
        "文档类 (*.pdf *.docx *.pptx *.xlsx *.csv *.txt *.md *.html *.json *.xml *.epub *.ipynb *.msg *.zip);;"
        "图片类（仅元数据） (*.png *.jpg *.jpeg);;"
        "音频类（需 ffmpeg） (*.mp3 *.wav *.m4a);;"
        "所有文件 (*.*)"
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
# 三、转换引擎
# ────────────────────────────────────────────────────────────────

_引擎 = None


def 引擎版本() -> str:
    try:
        from importlib.metadata import version
        return version("markitdown")
    except Exception:
        return "未知"


def 获取引擎(日志=None):
    """惰性加载 MarkItDown 引擎（首次加载约需数秒，只加载一次）。"""
    global _引擎
    if _引擎 is not None:
        return _引擎

    if 日志:
        日志("正在加载 MarkItDown 转换引擎 …")
    try:
        from markitdown import MarkItDown
    except ImportError as 异常:  # pragma: no cover
        raise RuntimeError(
            "未安装 markitdown 依赖，请执行：pip install \"markitdown[all]\""
        ) from 异常

    try:
        _引擎 = MarkItDown(enable_plugins=False)
    except TypeError:
        # 兼容不支持 enable_plugins 参数的旧版本
        _引擎 = MarkItDown()

    if 日志:
        日志(f"转换引擎就绪：MarkItDown {引擎版本()}")
    return _引擎


def 转换文件(路径: str, 日志=None, 图片内嵌: bool = False) -> str:
    """
    把单个文件转换为 Markdown 文本，异常向上抛出由调用方处理。

    图片内嵌=True 时，文档内嵌图片会以 base64 原样写进结果（体积约 +1/3）；
    为 False（默认）时，图片载荷会被 MarkItDown 丢弃，只留一个失效的引用。
    """
    路径 = os.path.abspath(路径)
    if not os.path.isfile(路径):
        raise FileNotFoundError(f"文件不存在：{路径}")
    if not 是支持的(路径):
        扩展 = os.path.splitext(路径)[1].lower() or "（无扩展名）"
        提示 = ""
        if 扩展 in 旧版格式扩展名:
            提示 = "。旧版二进制格式不受支持，请先用 Office / WPS 另存为 .docx / .xlsx / .pptx"
        elif 扩展 in {".bmp", ".gif", ".tif", ".tiff", ".webp"}:
            提示 = "。图片转换器只受理 .png / .jpg / .jpeg，请先转换图片格式"
        raise ValueError(f"暂不支持的文件类型：{扩展}{提示}")

    引擎 = 获取引擎(日志)
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
# 四、批量转换
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

    if 总数 == 0:
        日志("没有待转换的文件。")
        return {
            "总数": 0, "成功数": 0, "无文本数": 0, "失败数": 0,
            "内嵌图片数": 0, "丢弃图片数": 0,
            "耗时": 0.0, "结果列表": [], "导出文件列表": [],
        }

    日志(f"开始转换，共 {总数} 个文件。")
    if 配置.图片内嵌:
        日志("图片内嵌已开启：文档中的图片会以 base64 原样写入 .md（体积约 +1/3）。")
    获取引擎(日志)          # 预热引擎，避免第一个文件额外等待

    for 序号, 源文件 in enumerate(文件列表, start=1):
        if 取消检查 and 取消检查():
            日志(f"任务已取消，剩余 {总数 - 序号 + 1} 个文件未处理。")
            break

        文件名 = os.path.basename(源文件)
        if 进度:
            进度(序号 - 1, 总数, 文件名)

        结果 = 单项结果(序号=序号, 源文件=源文件)
        单次开始 = time.time()

        if not os.path.isfile(源文件):
            结果.错误 = "文件不存在或已被移动"
        else:
            日志(f"[{序号}/{总数}] {文件名}  —— {文件类型说明(源文件)}")
            try:
                结果.内容 = 转换文件(源文件, 图片内嵌=配置.图片内嵌)
                结果.成功 = True
                结果.耗时 = time.time() - 单次开始
                if 结果.为空:
                    无文本数 += 1
                    结果.警告 = 空内容原因(源文件)
                    日志(f"    未提取到文本：{结果.警告}")
                else:
                    成功数 += 1
                    备注 = ""
                    if 配置.图片内嵌:
                        张数, 载荷 = 统计内嵌图片(结果.内容)
                        结果.内嵌图片数 = 张数
                        结果.内嵌图片字节 = 载荷
                        内嵌图片总数 += 张数
                        if 张数:
                            备注 = f"，已内嵌 {张数} 张图片（base64 约 {载荷 / 1024:.0f} KB）"
                    else:
                        丢弃 = 统计丢弃图片(结果.内容)
                        if 丢弃:
                            结果.丢弃图片数 = 丢弃
                            丢弃图片总数 += 丢弃
                            结果.警告 = 图片丢弃提示(丢弃)
                            备注 = f"，⚠ 丢弃了 {丢弃} 张图片"
                    日志(f"    已完成，{结果.字符数} 字符，用时 {结果.耗时:.1f} 秒{备注}")
            except Exception as 异常:
                结果.耗时 = time.time() - 单次开始
                结果.错误 = f"{type(异常).__name__}: {异常}"
                失败数 += 1
                日志(f"    转换失败：{结果.错误}")

        if 结果.成功 and not 结果.为空 and 配置.自动保存:
            try:
                结果.输出文件 = 计算输出路径(源文件, 配置)
                保存文本(结果.输出文件, 结果.内容)
                导出文件.append(结果.输出文件)
                日志(f"    已导出 → {结果.输出文件}")
            except Exception as 异常:
                结果.输出文件 = ""
                日志(f"    导出失败：{type(异常).__name__}: {异常}")
        elif 结果.为空 and 配置.自动保存:
            日志("    已跳过导出，避免生成空的 .md 文件。")

        结果列表.append(结果)
        if 单项完成:
            单项完成(结果)
        if 进度:
            进度(序号, 总数, 文件名)

    耗时 = time.time() - 起始
    小结 = f"全部结束：成功 {成功数} 个"
    if 无文本数:
        小结 += f"，未提取到文本 {无文本数} 个（见上方原因）"
    小结 += f"，失败 {失败数} 个，共导出 {len(导出文件)} 个 .md 文件，总用时 {耗时:.1f} 秒。"
    日志(小结)
    if 内嵌图片总数:
        日志(f"图片：已内嵌 {内嵌图片总数} 张（base64 原样保留）。")
    if 丢弃图片总数:
        日志(f"图片：有 {丢弃图片总数} 张图片未保留，勾选「图片内嵌进 .md」可保留。")
    return {
        "总数": 总数,
        "成功数": 成功数,
        "无文本数": 无文本数,
        "失败数": 失败数,
        "内嵌图片数": 内嵌图片总数,
        "丢弃图片数": 丢弃图片总数,
        "耗时": 耗时,
        "结果列表": 结果列表,
        "导出文件列表": 导出文件,
    }


# ────────────────────────────────────────────────────────────────
# 五、命令行入口
# ────────────────────────────────────────────────────────────────

def _命令行(argv=None) -> int:
    解析器 = argparse.ArgumentParser(
        description="文档转 Markdown 工具（后端，基于 Microsoft MarkItDown）"
    )
    解析器.add_argument("文件", nargs="*", help="待转换的文件或目录，可多个")
    解析器.add_argument("-o", "--output", default="", help="输出目录，默认与源文件同目录")
    解析器.add_argument("--no-overwrite", action="store_true", help="不覆盖已存在的同名 .md")
    解析器.add_argument("--no-save", action="store_true", help="只转换不写文件（仅打印字符数）")
    解析器.add_argument(
        "--keep-images", action="store_true",
        help="把文档内嵌图片以 base64 原样写进 .md（体积约 +1/3；默认丢弃）",
    )
    参数 = 解析器.parse_args(argv)

    if not 参数.文件:
        解析器.print_help()
        return 0

    文件列表 = 收集文件(参数.文件)
    if not 文件列表:
        print("未找到可转换的文件。")
        return 1

    配置 = 转换配置(
        文件列表=文件列表,
        输出方式="指定目录" if 参数.output else "同目录",
        输出目录=os.path.abspath(参数.output) if 参数.output else BASE_DIR,
        覆盖已有=not 参数.no_overwrite,
        自动保存=not 参数.no_save,
        图片内嵌=参数.keep_images,
    )
    结果 = 运行(配置)
    摘要 = f"\n完成：成功 {结果['成功数']} 个"
    if 结果.get("无文本数"):
        摘要 += f"，未提取到文本 {结果['无文本数']} 个"
    摘要 += f"，失败 {结果['失败数']} 个。"
    if 结果.get("内嵌图片数"):
        摘要 += f"\n已内嵌图片：{结果['内嵌图片数']} 张"
    if 结果.get("丢弃图片数"):
        摘要 += f"\n未保留图片：{结果['丢弃图片数']} 张（加 --keep-images 可保留）"
    print(摘要)
    return 0 if 结果["失败数"] == 0 else 1


if __name__ == "__main__":
    sys.exit(_命令行())
