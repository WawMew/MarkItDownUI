# 文档转 Markdown 工具（MarkItDownUI）

基于 **PyQt6 + Microsoft MarkItDown** 的 Windows 桌面工具：把 PDF、Word、PPT、Excel、HTML 等文档批量转成 Markdown，保留标题层级、列表与表格结构，支持实时预览与一键导出。

> 仓库地址：**https://github.com/WawMew/MarkItDownUI**

## 功能

| 功能      | 说明                                                                         |
| ------- | -------------------------------------------------------------------------- |
| 批量转换    | 多选文件，或添加文件夹递归收集；支持拖拽导入                                                     |
| 实时预览    | 「渲染预览」与「Markdown 源码」双标签页，超宽图片自动缩放                                          |
| 导出控制    | 保存到源目录或指定目录；不覆盖同名文件时自动追加 `_1` 序号                                           |
| 图片内嵌    | 可选把文档内嵌图片以 base64 无损写入 .md（默认关闭）                                           |
| LLM OCR | 勾选开关后用旁边的齿轮按钮配置，让兼容 OpenAI 接口的视觉大模型识别图片与扫描件中的文字，配置窗口内置「测试连接」               |
| 快捷键     | `Ctrl+O` 添加文件、`Ctrl+Shift+O` 添加文件夹、`Ctrl+Enter` 开始、`Ctrl+S` 导出、`Delete` 移除 |
| 界面语言    | 标题区下拉框切换简体中文 / English；切换后界面就地重建，文件列表、转换结果与日志都不丢                           |

## 支持的格式

共 24 种扩展名：

`.pdf` `.docx` `.pptx` `.xlsx` `.csv` `.html` `.htm` `.txt` `.text` `.md` `.markdown` `.json` `.jsonl` `.xml` `.epub` `.ipynb` `.msg` `.zip` `.png` `.jpg` `.jpeg` `.mp3` `.wav` `.m4a`

- `.png` / `.jpg` / `.jpeg` 默认只读 EXIF 元数据；开启 LLM OCR 后可由视觉模型读出图中文字
- `.mp3` / `.wav` / `.m4a` 需系统另装 `ffmpeg`
- 不支持 `.doc` / `.xls` / `.ppt`（旧版二进制）及 `.bmp` / `.gif` / `.tiff` / `.webp`，请先另存为对应新格式

## 使用

**方式 1：exe（推荐，零依赖）**

`dist\MarkItDownUI.exe` 双击启动界面，可复制到任意 Windows 64 位电脑运行（约 124.2 MB，单文件自包含）。也可命令行调用：

```bat
MarkItDownUI.exe D:\文档\报告.pdf -o D:\output
```

> 命令行模式下 exe 会先把工作目录切到自己所在的位置，所以**待转换文件请用绝对路径**；只写文件名或相对路径会提示「未找到可转换的文件」。

**方式 2：源码运行**

双击 `启动程序.bat`，脚本会自动用 `.venv\Scripts\python.exe` 运行 `ui.py`。环境搭建：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

命令行参数：`-o 目录` 指定输出目录 | `--no-overwrite` 不覆盖同名 .md | `--no-save` 只转换不写文件 | `--keep-images` 内嵌图片 | `--llm-ocr` 启用 LLM OCR | `--lang en` 输出英文提示

## LLM OCR（可选）

服务兼容 OpenAI 接口即可：

| 项      | 说明                                                |
| ------ | ------------------------------------------------- |
| 接口地址   | `https://api.openai.com/v1`；留空用 OpenAI 官方         |
| API 密钥 | 留空则读环境变量 `OPENAI_API_KEY`；本地无鉴权服务（Ollama、vLLM）可留空 |
| 模型     | 必须支持图片输入，如 `gpt-4o`、`qwen-vl-max`、`glm-4v`        |

填好后先点配置窗口里的**测试连接**：它会拿一张测试图真实调用一次模型。**这一步别省**

命令行同样可用：

```bat
MarkItDownUI.exe D:\扫描件.pdf --llm-ocr --llm-base-url https://api.deepseek.com/v1 --llm-model deepseek-vl2 --llm-api-key sk-xxx
MarkItDownUI.exe --test-llm --llm-base-url https://api.deepseek.com/v1 --llm-model deepseek-vl2 --llm-api-key sk-xxx
```

- 密钥保存在程序目录的 `config/config.json`

## 关于图片

不勾选LLM OCR，MarkItDown 默认**丢弃**文档内嵌图片，只在 .md 里留下 `data:image/png;base64...` 这个失效引用（三个点是字面量）。勾选「将文档中的图片内嵌进 .md」（或命令行加 `--keep-images`）后，图片以 base64 原样写入，字节级无损、可离线查看，代价是 .md 体积约增加 1/3。

> ⚠️ **若 .md 要喂给大模型，务必保持此开关关闭。** base64 是纯文本，会占满上下文，而模型并不能「看见」图片。

## 已知限制

- **音频无法转写**：需 `ffmpeg` 与语音识别组件，未实现。
- **旧版 Office 格式**：`.doc` / `.xls` / `.ppt` 无对应转换器，请先另存为 `.docx` / `.xlsx` / `.pptx`。
- **预览截断**：源码标签页最多渲染 200 万字符以防界面卡死，**导出的 .md 内容始终完整**。
- **杀软可能误报**：PyInstaller onefile 的常见现象，添加信任即可。

## 项目结构

```
MarkItDownUI/
├─ main.py              程序入口（exe 用）：有参数走命令行，无参数启动界面
├─ ui.py                图形界面（PyQt6）
├─ converter.py         转换后端（无 Qt 依赖，可独立命令行运行；含 LLM OCR 封装）
├─ i18n.py              中英文案表与取词函数（无 Qt 依赖，后端与界面共用）
├─ config.py            配置读写（存到 config/config.json，不写注册表）
├─ requirements.txt     依赖清单
├─ LICENSE              MIT 许可证（Copyright (c) 2026 WawMew）
├─ MarkItDownUI.spec    PyInstaller 打包配置
├─ .gitignore           排除 .venv / build / dist / __pycache__ / config
├─ .gitattributes       声明 .bat 为 CRLF，防止换行规范化破坏
├─ 启动程序.bat          双击启动图形界面
├─ 构建exe.bat           双击重新打包 exe
├─ 示例文档/             4 个测试样例
├─ config/config.json   本机设置（首次运行自动生成，含密钥，已 gitignore）
├─ dist/MarkItDownUI.exe  打包产物（约 124.2 MB，自包含）
└─ .venv/               项目虚拟环境（约 658 MB，可删除重建）
```

后端 `converter.py` 与界面完全解耦：界面通过 `QThread` 调用后端，用信号回传进度与单项结果，因此转换大文件不卡界面，且随时可取消。

## 技术栈

Python 3.13 · PyQt6 6.11 · MarkItDown 0.1.7（Microsoft）· markitdown-ocr 0.1.0 · PyInstaller onefile

## 许可

本项目基于 [MIT License](LICENSE) 发布，Copyright (c) 2026 WawMew。

转换内核 MarkItDown 由 Microsoft 以 MIT 许可发布，其版权归 Microsoft 所有。
