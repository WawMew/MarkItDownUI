# -*- coding: utf-8 -*-
"""
多语言支持（简体中文 ⇄ English）
================================================================
设计：**中文原文就是消息键**。代码里直接写

    译("开始转换")               # 中文界面下原样返回
    译("列表共 {n} 个文件", n=5)  # 切到英文时查表 + 填充参数

这么设计有三个好处：

1. 漏翻不会出事 —— 查不到就原样返回中文，绝不抛异常、也不会显示成空白或乱码；
2. 代码可读 —— 读 `译("开始转换")` 就知道这行在说什么，不用去翻翻译表；
3. 打包省事 —— 纯 Python 字典，不像 Qt 的 .ts/.qm 那样要额外编译和携带资源文件。

为什么不用 Qt 自带的翻译机制：本项目的后端 converter.py 也要翻译，而它是纯
Python、刻意不依赖 Qt（可单独命令行运行）。共用一份字典表最省事。

本模块**不导入 Qt**，也不做任何持久化 —— 语言的选择由界面层存进 QSettings。
"""

from __future__ import annotations

中文 = "zh_CN"
英文 = "en"

默认语言 = 中文

# 语言代码 → 在界面上显示的名字（下拉框里用；两种语言下都显示各自的本族名，
# 这样英文用户也能一眼找到 "English"）
语言标签 = {
    中文: "简体中文",
    英文: "English",
}

# 下拉框顺序
语言顺序 = [中文, 英文]

_当前语言 = 默认语言


# ────────────────────────────────────────────────────────────────
# 英文翻译表
# ────────────────────────────────────────────────────────────────

英文表: dict[str, str] = {
    # ── 通用 / 按钮 ───────────────────────────────────────
    "文档转 Markdown 工具": "Document to Markdown",
    "文档转 Markdown": "Document to Markdown",
    "确定": "OK",
    "取消": "Cancel",
    "提示": "Notice",
    "显示": "Show",
    "浏览…": "Browse…",
    "恢复默认": "Reset",
    "测试连接": "Test connection",
    "开始转换": "Start",
    "文件": "File",
    "状态": "Status",
    # 句末标点也要跟着语言走：英文用它拼句子时不能出现中文句号
    "。": ".",
    # 列举多个项目的连接符（中文用顿号，英文用逗号）
    "、": ", ",

    # ── 标题区 ────────────────────────────────────────────
    "支持 PDF / Word / PPT / Excel / HTML 等格式，保留标题层级、列表与表格结构"
    "　|　可选 LLM OCR，识别图片与扫描件中的文字":
        "Converts PDF / Word / PPT / Excel / HTML and more, keeping heading levels, "
        "lists and tables　|　Optional LLM OCR for text inside images and scans",
    "列表共 {n} 个文件": "Files in list: {n}",

    # ── 文件列表分组 ──────────────────────────────────────
    "文件列表": "Files",
    "添加文件…": "Add files…",
    "添加文件夹…": "Add folder…",
    "移除选中": "Remove selected",
    "清空列表": "Clear list",
    "支持拖拽导入文件或文件夹": "Drag files or folders here to import",

    # ── 中部区域 ──────────────────────────────────────────
    "转换日志": "Log",
    "渲染预览": "Preview",
    "Markdown 源码": "Markdown source",
    "导出当前文件…": "Export current…",
    "导出全部结果": "Export all",
    "复制源码": "Copy source",

    # ── 导出设置 ──────────────────────────────────────────
    "导出设置": "Output settings",
    "保存到源文件所在目录": "Save next to each source file",
    "统一保存到指定目录：": "Save all into one folder:",
    "请选择 .md 文件的输出目录": "Choose the folder for the .md files",
    "覆盖已存在的同名 .md 文件": "Overwrite existing .md files",
    "转换完成后自动导出 .md 文件": "Export .md automatically after conversion",
    "将文档中的图片内嵌进 .md（base64 原样保留）":
        "Embed images into the .md (base64, byte-for-byte)",
    "关闭时（默认）：MarkItDown 会丢弃文档内嵌的图片，.md 里只剩一个加载不出来的引用。\n"
    "开启后：图片以 base64 原样写进 .md，字节级无损、可离线查看，\n"
    "代价是 .md 体积增加约 1/3（10 张 1 MB 的图约多出 13 MB），纯文本可读性也变差。\n\n"
    "与「启用 LLM OCR」二选一：勾上本项会自动取消 LLM OCR。":
        "Off (default): MarkItDown drops embedded images, leaving a reference in the .md "
        "that cannot be loaded.\n"
        "On: images are written into the .md as base64 — byte-for-byte, viewable offline.\n"
        "Cost: the .md grows by roughly 1/3 (ten 1 MB images add about 13 MB) and is "
        "harder to read as plain text.\n\n"
        "Mutually exclusive with “Enable LLM OCR”: ticking this clears LLM OCR.",
    "启用 LLM OCR 识别图片与扫描件中的文字":
        "Enable LLM OCR for text in images and scans",
    "MarkItDown 内核没有任何本地 OCR —— 扫描件 PDF 提取为空、图片只读 EXIF 元数据。\n"
    "开启后由官方插件 markitdown-ocr 接管 PDF / Word / PPT / Excel：\n"
    "内嵌图片、以及「整页抽不出文字」的扫描页会送给视觉模型，用识别结果替换图片。\n\n"
    "模型与密钥点右侧齿轮按钮配置。文档中的图片会上传到该服务（按图计费），"
    "请自行确认数据可以离机。\n\n"
    "与「图片内嵌」二选一：勾上本项会自动取消图片内嵌。":
        "The MarkItDown core has no OCR of its own — a scanned PDF extracts to nothing and "
        "images yield only EXIF metadata.\n"
        "When enabled, the official markitdown-ocr plugin takes over PDF / Word / PPT / "
        "Excel:\n"
        "embedded images, plus scanned pages that yield no text at all, are sent to a "
        "vision model and replaced by its transcription.\n\n"
        "Set the model and key with the gear button on the right. Images from your "
        "documents are uploaded to that service (billed per image) — make sure the data "
        "may leave your machine.\n\n"
        "Mutually exclusive with “Embed images”: ticking this clears that option.",

    # ── 底栏与状态 ────────────────────────────────────────
    "就绪": "Ready",
    "准备就绪，等待添加文件。": "Ready. Add files to get started.",
    "正在准备转换引擎 …": "Preparing the conversion engine…",
    "正在取消，请等待当前文件处理结束 …":
        "Cancelling — waiting for the current file to finish…",
    "已请求取消，将在当前文件处理完成后停止。":
        "Cancellation requested; stopping after the current file.",
    "正在转换 {已完成}/{总数}：{文件名}": "Converting {已完成}/{总数}: {文件名}",
    "转换结束：成功 {成功} 个，失败 {失败} 个。":
        "Finished: {成功} succeeded, {失败} failed.",
    "转换过程发生异常。": "An unexpected error occurred during conversion.",

    # ── 条目状态词（也是内部状态键） ──────────────────────
    "待转换": "Pending",
    "转换中": "Converting",
    "已完成": "Done",
    "已导出": "Exported",
    "无文本": "No text",
    "失败": "Failed",
    "{原因} · 等待转换": "{原因} · waiting",
    "等待转换": "Waiting to be converted",

    # ── 条目状态文本（结果表） ────────────────────────────
    "{状态}（{字符数} 字符）": "{状态} ({字符数} chars)",
    "{状态}\n字符数：{字符数}\n用时：{耗时} 秒":
        "{状态}\nCharacters: {字符数}\nTime: {耗时} s",
    " · OCR {数量}": " · OCR {数量}",
    "\nLLM OCR：识别 {识别数} 处（调用模型 {调用数} 次）":
        "\nLLM OCR: {识别数} region(s) recognised ({调用数} model call(s))",
    " · 含图 {数量}": " · {数量} images",
    "\n已内嵌图片：{数量} 张（base64 约 {大小} KB）":
        "\nEmbedded images: {数量} (base64 ~{大小} KB)",
    " · ⚠ 丢图 {数量}": " · ⚠ {数量} images dropped",
    "\n⚠ 原文中的 {数量} 张图片未保留（勾选「图片内嵌进 .md」可保留）":
        "\n⚠ {数量} image(s) from the source were not kept "
        "(enable “Embed images into the .md” to keep them)",
    " · ⚠ OCR 失败 {数量}": " · ⚠ {数量} OCR failures",
    "\n输出：{路径}": "\nOutput: {路径}",
    "未提取到文本\n原因：{原因}": "No text extracted\nReason: {原因}",
    "失败原因：{错误}": "Reason: {错误}",

    # ── 文件对话框 ────────────────────────────────────────
    "选择要转换的文档": "Select documents to convert",
    "选择包含文档的文件夹": "Select a folder containing documents",
    "导出为 Markdown 文件": "Export as Markdown",
    "Markdown 文件 (*.md);;所有文件 (*.*)": "Markdown files (*.md);;All files (*.*)",
    "选择输出目录": "Choose the output folder",

    # ── 消息框 ────────────────────────────────────────────
    "请先添加需要转换的文档。": "Add the documents you want to convert first.",
    "请先选择输出目录，或改为保存到源文件所在目录。":
        "Choose an output folder, or switch to saving next to each source file.",
    "无法创建输出目录": "Cannot create the output folder",
    "LLM OCR 配置不完整": "Incomplete LLM OCR settings",
    "{问题}\n\n可取消勾选「启用 LLM OCR 识别」，或点它右侧的齿轮按钮补齐配置后重试。":
        "{问题}\n\nEither clear the “Enable LLM OCR” checkbox, or click the gear button "
        "next to it, complete the settings and try again.",
    "确认清空": "Clear the list",
    "确定要清空文件列表吗？（已导出的 .md 文件不会被删除）":
        "Clear the file list? (Already exported .md files are not deleted.)",
    "转换完成": "Conversion finished",
    "转换失败": "Conversion failed",
    "转换正在运行": "Conversion in progress",
    "正在转换": "Conversion in progress",
    "转换仍在进行中，确定要退出吗？": "A conversion is still running. Quit anyway?",
    "导出失败": "Export failed",
    "导出完成": "Export finished",

    # ── 转换完成汇总 ──────────────────────────────────────
    "共处理 {总数} 个文件": "Processed {总数} file(s)",
    "成功：{数量} 个": "Succeeded: {数量}",
    "未提取到文本：{数量} 个": "No text extracted: {数量}",
    "失败：{数量} 个": "Failed: {数量}",
    "已导出 .md：{数量} 个": ".md exported: {数量}",
    "LLM OCR：识别 {数量} 处文字，调用模型 {调用数} 次":
        "LLM OCR: {数量} region(s) recognised, {调用数} model call(s)",
    "已内嵌图片：{数量} 张": "Images embedded: {数量}",
    "未保留图片：{数量} 张（勾选「图片内嵌进 .md」可保留）":
        "Images not kept: {数量} (enable “Embed images into the .md” to keep them)",
    "总用时：{耗时} 秒": "Total time: {耗时} s",

    # ── 预览 ──────────────────────────────────────────────
    "尚未转换，转换完成后这里会实时显示 Markdown 预览。":
        "Nothing converted yet. The Markdown preview appears here as soon as a file "
        "finishes.",
    "<b>转换失败</b>": "<b>Conversion failed</b>",
    "<b>未提取到文本</b>": "<b>No text extracted</b>",
    "该文件已跳过导出，不会生成空的 .md 文件。":
        "Export was skipped for this file — no empty .md is created.",
    "… 内容过长（共 {总数} 字符），源码视图仅显示前 {上限} 个字符；"
    "导出的 .md 文件内容完整。":
        "… Content is long ({总数} characters); the source view shows the first "
        "{上限} only. The exported .md file is complete.",
    "（文档较长，此处仅渲染前 {上限} 个字符；完整内容见「Markdown 源码」页签或已导出的 .md 文件）":
        "(Long document: only the first {上限} characters are rendered. See the "
        "“Markdown source” tab or the exported .md file for the full text.)",
    "提示：{文件名} 内容较长（{字符数} 字符），预览已截断显示。":
        "Note: {文件名} is long ({字符数} characters); the preview is truncated.",
    "提示：{文件名} 内容达 {字符数} 字符，源码视图已截断显示。":
        "Note: {文件名} is {字符数} characters; the source view is truncated.",
    "提示：预览图片自适应缩放未生效（{类型}），不影响导出结果。":
        "Note: preview image auto-scaling did not apply ({类型}); exported files are "
        "unaffected.",

    # ── 导出 ──────────────────────────────────────────────
    "当前预览的文件没有可导出的文本内容。":
        "The file being previewed has no text to export.",
    "还没有可导出的转换结果，请先执行转换。":
        "Nothing to export yet — run a conversion first.",
    "当前没有可复制的 Markdown 内容。": "There is no Markdown content to copy.",
    "已复制 {数量} 个字符到剪贴板。": "Copied {数量} characters to the clipboard.",
    "已导出 → {路径}": "Exported → {路径}",
    "已导出：{文件名}": "Exported: {文件名}",
    "已导出（{字符数} 字符）": "Exported ({字符数} chars)",
    "输出：{路径}": "Output: {路径}",
    "已导出 {数量} 个 .md 文件。": "Exported {数量} .md file(s).",
    "失败 {数量} 个：\n{列表}": "Failed: {数量}\n{列表}",
    "导出失败 {文件名}：{异常}": "Export failed — {文件名}: {异常}",
    "[错误] {错误}": "[Error] {错误}",

    # ── 启动日志 ──────────────────────────────────────────
    "欢迎使用「文档转 Markdown」工具，转换引擎：Microsoft MarkItDown。":
        "Welcome to Document to Markdown. Converter: Microsoft MarkItDown.",
    "使用步骤：① 添加文件或直接把文件 / 文件夹拖入列表 → ② 设置导出位置 → ③ 点击「开始转换」。":
        "Steps: (1) add files, or drag files / folders into the list → "
        "(2) choose where to save → (3) click “Start”.",
    "如需识别图片、扫描件里的文字：勾选「启用 LLM OCR 识别」，"
    "再点它右侧的齿轮按钮，填入兼容 OpenAI 接口的模型与密钥。":
        "To read text inside images and scans: tick “Enable LLM OCR”, then click the "
        "gear button next to it and fill in an OpenAI-compatible model and API key.",
    "提示：未安装 LLM OCR 依赖，图片与扫描件中的文字无法识别；"
    "需要时执行 pip install {包名} openai。":
        "Note: the LLM OCR dependencies are not installed, so text in images and scans "
        "cannot be read. To enable it: pip install {包名} openai",

    # ── 文件列表操作日志 ──────────────────────────────────
    "已加入 {数量} 个文件。": "Added {数量} file(s).",
    "跳过 {数量} 个已在列表中的文件。": "Skipped {数量} file(s) already in the list.",
    "未在所选位置找到受支持的文档。":
        "No supported documents found in the selected location.",

    # ── LLM OCR 设置窗口 ──────────────────────────────────
    "LLM OCR 设置": "LLM OCR settings",
    "填入任意兼容 OpenAI 接口的服务即可（OpenAI、DeepSeek、通义、智谱、Ollama、vLLM …）。"
    "模型必须支持图片输入，纯文本模型识别不了图片里的文字。":
        "Works with any service that follows the OpenAI API (OpenAI, DeepSeek, Qwen, "
        "Zhipu, Ollama, vLLM …). The model must accept image input — text-only models "
        "cannot read text in images.",
    "模型服务": "Model service",
    "接口地址": "Endpoint",
    "如 https://api.openai.com/v1（留空 = OpenAI 官方）":
        "e.g. https://api.openai.com/v1 (blank = OpenAI)",
    "模型": "Model",
    "需支持图片输入：gpt-4o / qwen-vl-max / glm-4v / llava …":
        "Must accept images: gpt-4o / qwen-vl-max / glm-4v / llava …",
    "API 密钥": "API key",
    "如 sk-xxxxxxxxxxxxxxxx（留空 = 读环境变量 OPENAI_API_KEY）":
        "e.g. sk-xxxxxxxxxxxxxxxx (blank = read OPENAI_API_KEY)",
    "识别提示词": "OCR prompt",
    "发送给模型的指令，一般无需修改。":
        "Instruction sent to the model. Usually no need to change it.",
    "用一张真实的小图调用一次模型，确认「地址 + 密钥 + 模型」可用。":
        "Sends one real image to the model to verify endpoint + key + model.",
    "尚未测试。": "Not tested yet.",
    "· 识别会把文档中的图片上传到上面配置的服务（按图计费），请自行确认数据可以离机；"
    "密钥不会写进导出的 .md。\n"
    "· 开启后 PDF / Word / PPT / Excel 中的图片会变成识别出的文字，原图不再内嵌。\n"
    "· 没有可识别文字的文件不会产生任何调用；模型报错会记进主界面日志，不会静默失败。":
        "· Recognition uploads images from your documents to the service configured "
        "above (billed per image) — make sure the data may leave your machine. The key is "
        "never written into exported .md files.\n"
        "· With this on, images in PDF / Word / PPT / Excel become recognised text and the "
        "originals are no longer embedded.\n"
        "· Files with nothing to recognise make no calls at all; model errors are "
        "written to the main log instead of failing silently.",
    "已恢复默认：地址留空表示使用 OpenAI 官方接口。":
        "Reset done: a blank endpoint means the official OpenAI API.",
    "正在调用模型 …（本地服务或大模型可能需十几秒）":
        "Calling the model… (a local service or a large model can take ten seconds or more)",
    "[LLM] 正在测试 {接口} · {模型} …": "[LLM] Testing {接口} · {模型}…",
    "[LLM] 配置已更新：{接口} · {模型}": "[LLM] Settings updated: {接口} · {模型}",
    "[LLM] 已启用，转换时图片与扫描页会交由该模型识别。":
        "[LLM] Enabled — images and scanned pages will be sent to this model.",
    "[LLM] 配置已清空，LLM OCR 暂不可用。":
        "[LLM] Settings cleared — LLM OCR is unavailable.",
    "OpenAI 官方接口": "OpenAI (default endpoint)",

    # ── LLM 状态标签 ──────────────────────────────────────
    "⚠ 缺少 OCR 依赖": "⚠ OCR dependencies missing",
    "OCR 插件 {包名}": "OCR plugin {包名}",
    "openai 客户端库": "openai client library",
    "请执行 pip install {包名} openai 后重启本程序。":
        "Run pip install {包名} openai, then restart this program.",
    "⚠ 未配置模型": "⚠ No model configured",
    "未配置模型": "No model configured",
    "点右侧齿轮按钮，填入兼容 OpenAI 接口的地址、模型与密钥。":
        "Click the gear button to set an OpenAI-compatible endpoint, model and key.",
    "接口：{接口}\n模型：{模型}\n点右侧齿轮按钮可修改。":
        "Endpoint: {接口}\nModel: {模型}\nClick the gear button to edit.",

    # ── 语言切换 ──────────────────────────────────────────
    "界面语言": "Language",
    "切换界面语言": "Switch the interface language",
    "界面语言已切换为 {名称}。": "Interface language switched to {名称}.",
    "正在转换，结束后才能切换界面语言。":
        "A conversion is running — the interface language can be changed once it finishes.",

    # ── 后端：文件类型 ────────────────────────────────────
    "PDF 文档": "PDF document",
    "Word 文档": "Word document",
    "PowerPoint 演示文稿": "PowerPoint presentation",
    "Excel 工作簿": "Excel workbook",
    "CSV 表格": "CSV table",
    "网页文件": "Web page",
    "纯文本": "Plain text",
    "JSON 数据": "JSON data",
    "JSON Lines 数据": "JSON Lines data",
    "XML 数据": "XML data",
    "电子书": "E-book",
    "Jupyter Notebook": "Jupyter Notebook",
    "Outlook 邮件": "Outlook message",
    "压缩包": "Archive",
    "图片（仅读取元数据）": "Image (metadata only)",
    "音频（需系统安装 ffmpeg）": "Audio (requires ffmpeg)",
    "未知类型": "Unknown type",
    "未知": "unknown",

    # ── 后端：结果为空的原因 ──────────────────────────────
    "已启用 LLM OCR，但模型没有返回任何文字：请先用「测试连接」确认接口可用，"
    "再确认这张图里确实有文字":
        "LLM OCR is on but the model returned no text: use “Test connection” to verify "
        "the endpoint, then check that this image really contains text.",
    "MarkItDown 内置的图片转换器只读取 EXIF 元数据（尺寸、拍摄时间、GPS 等），"
    "不做字符识别（OCR），所以图中的文字读不出来；开启「LLM OCR 识别」即可读出":
        "MarkItDown's built-in image converter reads only EXIF metadata (size, capture "
        "time, GPS) and does no character recognition, so text in the image cannot be "
        "read. Turn on “LLM OCR” to read it.",
    "音频转写需要系统已安装 ffmpeg 与语音识别组件，当前环境未就绪":
        "Audio transcription needs ffmpeg and a speech-recognition component, which are "
        "not available in this environment.",
    "已启用 LLM OCR，但这一页仍未提取到文字：请确认文件能正常打开，"
    "并检查「测试连接」是否通过":
        "LLM OCR is on but this page still yielded no text: make sure the file opens "
        "normally and that “Test connection” passes.",
    "该 PDF 没有文本层（多为扫描件或图片型 PDF），开启「LLM OCR 识别」即可提取其中的文字":
        "This PDF has no text layer (usually a scan or an image-only PDF). Turn on "
        "“LLM OCR” to extract its text.",
    "该文件没有可提取的文本内容": "This file has no extractable text.",

    # ── 后端：图片处理 ────────────────────────────────────
    "原文中的 {数量} 张图片已被丢弃（MarkItDown 默认不保留图片）"
    "；勾选「图片内嵌进 .md」即可保留":
        "{数量} image(s) from the source were dropped (MarkItDown keeps no images by "
        "default); enable “Embed images into the .md” to keep them.",

    # ── 后端：文件过滤器 ──────────────────────────────────
    "全部支持的格式 ({通配})": "All supported formats ({通配})",
    "文档类 (*.pdf *.docx *.pptx *.xlsx *.csv *.txt *.md *.html *.json *.xml *.epub *.ipynb *.msg *.zip)":
        "Documents (*.pdf *.docx *.pptx *.xlsx *.csv *.txt *.md *.html *.json *.xml "
        "*.epub *.ipynb *.msg *.zip)",
    "图片类（仅元数据） (*.png *.jpg *.jpeg)": "Images (metadata only) (*.png *.jpg *.jpeg)",
    "音频类（需 ffmpeg） (*.mp3 *.wav *.m4a)": "Audio (needs ffmpeg) (*.mp3 *.wav *.m4a)",
    "所有文件 (*.*)": "All files (*.*)",

    # ── 后端：LLM 配置校验与连接测试 ──────────────────────
    "请先填写模型名称（需支持图片输入，如 gpt-4o / qwen-vl-max / "
    "glm-4v / doubao-vision 等）":
        "Enter a model name first (it must accept image input, e.g. gpt-4o / "
        "qwen-vl-max / glm-4v / doubao-vision).",
    "未安装 OCR 插件，请在项目环境执行：pip install {包名}":
        "The OCR plugin is not installed. Run: pip install {包名}",
    "未安装 openai 客户端库，请在项目环境执行：pip install openai":
        "The openai client library is not installed. Run: pip install openai",
    "未安装 openai 客户端库，无法启用 LLM OCR。请执行：pip install openai":
        "Cannot enable LLM OCR: the openai client library is not installed. "
        "Run: pip install openai",
    "调用失败：{类型}: {异常}": "Request failed: {类型}: {异常}",
    "初始化 LLM 客户端失败：{类型}: {异常}":
        "Failed to initialise the LLM client: {类型}: {异常}",
    "连接成功（模型 {模型} 有响应，但没有返回文字 —— 测试图里本来也没有字，属正常）。":
        "Connected (model {模型} responded but returned no text — the test image "
        "contains none, which is expected).",
    "连接成功，模型 {模型} 已返回 {字符数} 个字符。":
        "Connected. Model {模型} returned {字符数} characters.",

    # ── 后端：引擎加载 ────────────────────────────────────
    "正在加载 MarkItDown 转换引擎 …": "Loading the MarkItDown engine…",
    "未安装 markitdown 依赖，请执行：pip install \"markitdown[all]\"":
        "markitdown is not installed. Run: pip install \"markitdown[all]\"",
    "LLM OCR 已启用：{接口} · 模型 {模型}": "LLM OCR enabled: {接口} · model {模型}",
    "当前 MarkItDown 版本不支持插件机制，无法启用 LLM OCR，"
    "请升级：pip install -U \"markitdown[all]\"":
        "This MarkItDown version has no plugin support, so LLM OCR cannot be enabled. "
        "Upgrade with: pip install -U \"markitdown[all]\"",
    "转换引擎就绪：MarkItDown {版本}": "Engine ready: MarkItDown {版本}",

    # ── 后端：单文件转换 ──────────────────────────────────
    "文件不存在：{路径}": "File not found: {路径}",
    "（无扩展名）": "(no extension)",
    "。旧版二进制格式不受支持，请先用 Office / WPS 另存为 .docx / .xlsx / .pptx":
        ". Legacy binary formats are not supported — save the file as .docx / .xlsx / "
        ".pptx in Office or WPS first.",
    "。图片转换器只受理 .png / .jpg / .jpeg，请先转换图片格式":
        ". The image converter only accepts .png / .jpg / .jpeg — convert the image "
        "first.",
    "暂不支持的文件类型：{扩展}{提示}": "Unsupported file type: {扩展}{提示}",

    # ── 后端：批量转换日志 ────────────────────────────────
    "没有待转换的文件。": "No files to convert.",
    "开始转换，共 {总数} 个文件。": "Converting {总数} file(s).",
    "图片内嵌已开启：HTML / EPUB 等格式的图片会以 base64 写入 .md；"
    "PDF / Word / PPT / Excel 的图片会被 LLM OCR 替换成识别出的文字。":
        "Embed images is on: images in HTML / EPUB and similar are written as base64; "
        "images in PDF / Word / PPT / Excel are replaced by LLM OCR text.",
    "图片内嵌已开启：文档中的图片会以 base64 原样写入 .md（体积约 +1/3）。":
        "Embed images is on: images are written into the .md as base64 (size +1/3).",
    "LLM OCR 已开启：{接口} · 模型 {模型}。识别会调用视觉模型，按图计费、耗时更长。":
        "LLM OCR is on: {接口} · model {模型}. Recognition calls a vision model — "
        "billed per image and slower.",
    "任务已取消，剩余 {数量} 个文件未处理。":
        "Cancelled: {数量} file(s) left unprocessed.",
    "文件不存在或已被移动": "File is missing or was moved",
    "[{序号}/{总数}] {文件名}  —— {类型}": "[{序号}/{总数}] {文件名}  — {类型}",
    "    未提取到文本：{原因}": "    No text extracted: {原因}",
    "，已内嵌 {数量} 张图片（base64 约 {大小} KB）":
        ", {数量} image(s) embedded (base64 ~{大小} KB)",
    "，⚠ 丢弃了 {数量} 张图片": ", ⚠ {数量} image(s) dropped",
    "，OCR 识别 {数量} 处": ", {数量} OCR region(s)",
    "，调用了模型 {数量} 次但没有返回文字":
        ", {数量} model call(s) but no text returned",
    "，未发现需要识别的图片": ", no images needed recognition",
    "有 {数量} 次 OCR 调用失败：{错误}": "{数量} OCR call(s) failed: {错误}",
    "    已完成，{字符数} 字符，用时 {耗时} 秒{备注}":
        "    Done: {字符数} characters in {耗时}s{备注}",
    "    转换失败：{错误}": "    Conversion failed: {错误}",
    "    已导出 → {路径}": "    Exported → {路径}",
    "    导出失败：{类型}: {异常}": "    Export failed: {类型}: {异常}",
    "    已跳过导出，避免生成空的 .md 文件。":
        "    Export skipped to avoid an empty .md file.",
    "    ⚠ LLM OCR 调用失败（模型 {模型}）：{错误}":
        "    ⚠ LLM OCR call failed (model {模型}): {错误}",

    # ── 后端：批处理小结 ──────────────────────────────────
    "全部结束：成功 {成功} 个": "All done: {成功} succeeded",
    "，未提取到文本 {数量} 个（见上方原因）":
        ", {数量} with no text (see the reasons above)",
    "，失败 {数量} 个，共导出 {导出} 个 .md 文件，总用时 {耗时} 秒。":
        ", {数量} failed, {导出} .md file(s) exported, {耗时}s total.",
    "图片：已内嵌 {数量} 张（base64 原样保留）。":
        "Images: {数量} embedded (base64).",
    "图片：有 {数量} 张图片未保留，勾选「图片内嵌进 .md」可保留。":
        "Images: {数量} not kept — enable “Embed images into the .md” to keep them.",
    "LLM OCR：共识别 {数量} 处文字，调用模型 {调用数} 次":
        "LLM OCR: {数量} region(s) recognised, {调用数} model call(s)",
    "，其中 {数量} 次失败（详见上方日志）。":
        ", {数量} of which failed (see the log above).",
    "提示：本次没有任何图片需要识别。若期望识别扫描件却毫无动静，"
    "请先用界面的「测试连接」确认接口可用。":
        "Note: nothing needed recognition this run. If you expected scanned pages to be "
        "processed, use “Test connection” first to verify the endpoint.",

    # ── 后端：命令行 ──────────────────────────────────────
    "文档转 Markdown 工具（后端，基于 Microsoft MarkItDown）":
        "Document to Markdown (backend, powered by Microsoft MarkItDown)",
    "待转换的文件或目录，可多个": "files or folders to convert (one or more)",
    "输出目录，默认与源文件同目录": "output folder (default: next to each source file)",
    "不覆盖已存在的同名 .md": "do not overwrite existing .md files",
    "只转换不写文件（仅打印字符数）":
        "convert only, do not write files (prints character counts)",
    "把文档内嵌图片以 base64 原样写进 .md（体积约 +1/3；默认丢弃）":
        "embed images as base64 in the .md (size +1/3; dropped by default)",
    "LLM OCR（可选）": "LLM OCR (optional)",
    "用视觉大模型识别图片与扫描件中的文字，需先安装：pip install {包名} openai":
        "Read text in images and scans with a vision model. Requires: "
        "pip install {包名} openai",
    "启用 LLM OCR（识别 PDF / Word / PPT / Excel 里的图片与扫描整页）":
        "enable LLM OCR (recognises images and scanned pages in PDF / Word / PPT / Excel)",
    "兼容 OpenAI 接口的服务地址，如 https://api.deepseek.com/v1；留空用 OpenAI 官方":
        "OpenAI-compatible endpoint, e.g. https://api.deepseek.com/v1 (blank = OpenAI)",
    "接口密钥；留空则读取环境变量 OPENAI_API_KEY（本地无鉴权服务可随意留空）":
        "API key; falls back to the OPENAI_API_KEY environment variable (blank is fine "
        "for local services without authentication)",
    "视觉模型名，需支持图片输入，如 gpt-4o / qwen-vl-max / glm-4v / doubao-vision":
        "vision model name, must accept images, e.g. gpt-4o / qwen-vl-max / glm-4v / "
        "doubao-vision",
    "自定义识别提示词": "custom OCR prompt",
    "只测试「地址 + 密钥 + 模型」是否可用，不转换任何文件":
        "only test endpoint + key + model; convert nothing",
    "界面语言：zh 或 en，默认跟随系统": "interface language: zh or en (default: follow the system)",
    "未找到可转换的文件。": "No convertible files found.",
    "错误：{异常}": "Error: {异常}",
    "完成：成功 {成功} 个": "Done: {成功} succeeded",
    "，未提取到文本 {数量} 个": ", {数量} with no text",
    "，失败 {数量} 个。": ", {数量} failed.",
    "已内嵌图片：{数量} 张": "Images embedded: {数量}",
    "未保留图片：{数量} 张（加 --keep-images 可保留）":
        "Images not kept: {数量} (use --keep-images to keep them)",
    "LLM OCR：识别 {数量} 处，调用模型 {调用数} 次":
        "LLM OCR: {数量} region(s) recognised, {调用数} model call(s)",

    # ── 默认 OCR 提示词（英文界面下发给模型的指令） ────────
    "提取这张图片中的全部文字或表格，按原始阅读顺序输出，尽量用 Markdown 代码块标记。"
    "如果图片不是文字也不是表格，请描述这个文件":
        "Extract all text or tables from this image, in the original reading order. "
        "Wrap the result in a Markdown code block where possible. "
        "If the image is neither text nor a table, describe the file.",

    # ── 启动失败（main.py） ───────────────────────────────
    "启动失败": "Startup failed",
    "运行出错": "Runtime error",
    "程序启动失败。\n\n": "The program failed to start.\n\n",
    "程序运行中发生未预期的错误。\n\n": "An unexpected error occurred while running.\n\n",
    "完整信息已写入：\n{路径}": "Full details were written to:\n{路径}",
}


# ────────────────────────────────────────────────────────────────
# 翻译表：语言代码 → 对照表
# ────────────────────────────────────────────────────────────────

翻译表: dict[str, dict[str, str]] = {
    英文: 英文表,
}


# ────────────────────────────────────────────────────────────────
# 语言管理
# ────────────────────────────────────────────────────────────────

def 可用语言() -> list[tuple[str, str]]:
    """[(语言代码, 显示名), …]，供下拉框使用。"""
    return [(代码, 语言标签[代码]) for 代码 in 语言顺序]


def 规范化(代码) -> str:
    """把各种写法归一到语言代码：zh / zh_CN / zh-CN / Chinese → zh_CN；en / en_US → en。"""
    文本 = str(代码 or "").strip().replace("-", "_")
    if not 文本:
        return 默认语言
    主语言 = 文本.split("_")[0].lower()
    for 语言代码 in 语言顺序:
        if 语言代码.lower() == 文本.lower():
            return 语言代码
        if 语言代码.split("_")[0].lower() == 主语言:
            return 语言代码
    return 默认语言


def 设置语言(代码) -> str:
    """切换当前语言，返回规范化后的代码。"""
    global _当前语言
    _当前语言 = 规范化(代码)
    return _当前语言


def 当前语言() -> str:
    return _当前语言


def 是英文() -> bool:
    return _当前语言 == 英文


def 跟随系统() -> str:
    """
    按系统界面语言猜一个默认值（首次启动时用）。

    只用标准库判断，因为后端命令行也会调用它，不能依赖 Qt。
    Windows 走 GetUserDefaultUILanguage（比 locale 可靠，且不受 Python 的
    UTF-8 模式与 LANG 环境变量影响）；其它平台看环境变量。
    """
    import os

    if os.name == "nt":
        try:
            import ctypes

            语言ID = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
            # 主语言 ID 占低 10 位，中文为 0x04（2052 = 简体，1028 = 繁体）
            if (语言ID & 0x3FF) == 0x04:
                return 中文
            return 英文
        except Exception:
            pass

    for 变量 in ("LC_ALL", "LC_MESSAGES", "LANG"):
        值 = (os.environ.get(变量) or "").strip().lower()
        if 值:
            return 中文 if 值.startswith("zh") else 英文
    return 默认语言


# ────────────────────────────────────────────────────────────────
# 取词
# ────────────────────────────────────────────────────────────────

def 译(原文: str, **参数) -> str:
    """
    取当前语言下的文案。

    参数直接作为命名占位符填充：译("列表共 {n} 个文件", n=5)。
    查不到译文、或参数对不上时，一律原样返回中文，绝不抛异常 —— 界面文案
    出问题不应该把整个程序带崩。
    """
    文本 = 原文
    if _当前语言 != 默认语言:
        表 = 翻译表.get(_当前语言)
        if 表:
            文本 = 表.get(原文, 原文)
    if 参数:
        try:
            文本 = 文本.format(**参数)
        except (KeyError, IndexError, ValueError):
            pass
    return 文本


# 短别名：调用点很多，写 t(...) 或 译(...) 都行
t = 译


def 已翻译条目数(代码: str | None = None) -> int:
    """统计某语言的条目数（自检脚本用）。"""
    return len(翻译表.get(代码 or _当前语言, {}))
