# TranslateBuddy

Dify 文档翻译插件：**格式优先**。翻译交给 workspace 里已配置的模型，插件只负责把文档拆开、翻译、再原位塞回去。

设计文档见 [docs/方案.md](docs/方案.md)。

## 当前状态（M2）

| 能力 | 状态 |
|---|---|
| docx 解析（正文 / 表格 / 页眉页脚 / 脚注批注） | ✅ |
| 段内多格式（run 分组 + `[[n]]` 标签回填，失守时降级） | ✅ |
| xlsx L2 改写（sharedStrings / inlineStr，不经过 openpyxl） | ✅ |
| 作业化：parse_document / translate_shard / render_document | ✅ 断点续跑、分片幂等 |
| 术语表：提示词 + 占位符锁定 | ✅ |
| 同文本去重（表格重复表头只翻一次） | ✅ |
| zip 级就地改写（其余部件字节不变） | ✅ |
| 流式下载（不整块读内存） | ✅ |
| 模型调用（`model-selector` + 反向调用） | ✅ 代码就绪，待接真模型联调 |
| pdf 重排（正文按列重排、表格/页眉页脚锚定、溢出插页） | ✅ |
| doc / xls（LibreOffice） | ⏳ M4 |

### 两种用法

**小文件（≤50 页）**：一个 `翻译文档` 节点搞定。

**大文件（100+ 页）**：`解析文档` → 迭代 `翻译分片` → `回写文档`。
分片结果落在插件工作目录，工作流中断后重跑会命中缓存、不重复花钱。

## 目录

```
manifest.yaml / main.py        插件入口
provider/                      tool provider（无凭证）
tools/translate_document.py    工具实现：下载 → 解析 → 翻译 → 回写 → blob
backend/
  docx_io.py                   DOCX 的 L2 就地改写
  xlsx_io.py                   XLSX 的 L2 就地改写
  formats.py                   按扩展名分发
  jobs.py                      作业 / 分片 / 断点续跑
  glossary.py                  术语占位符锁定
  tags.py                      [[n]] 格式片段标记
  translator.py                批处理 / 去重 / JSON 解析 / 重试
  qa.py                        数字、占位符等基础校验
  files.py                     流式下载
scripts/
  setup_dify_env.py            改 Dify .env（7 项，幂等带备份）
  demo_local.py                不连 Dify 的端到端演示
tests/                         pytest
```

## 本地开发

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/demo_local.py      # 生成 demo_out.docx
```

`demo_local.py` 用词典桩代替模型，验证的是格式链路；接真模型只需把 `stub_invoke` 换成 `session.model.llm.invoke`（`tools/translate_document.py` 里已实现）。

## 装进 Dify

网页端逐步操作见 [docs/联调指南.md](docs/联调指南.md)（Cloud 与自建都适用）。
下面只列命令。

### 打包

```bash
python scripts/package.py                                    # dist/translate_buddy-<version>.difypkg
python scripts/validate_package.py dist/translate_buddy-0.0.2.difypkg
```

### 自托管 Docker

**只有需要传大文件时才改配置**（Cloud 改不了，直接跳过）：

```bash
python scripts/setup_dify_env.py /path/to/dify/docker
cd /path/to/dify/docker && docker compose up -d
```

改的是：上传 500MB、nginx 500M、插件产出 600MB、单次调用 1800s、工作流 7200s、长连接 7200s。
用 `--check` 可以随时核对。

**安装**：Dify 控制台 → 插件 → 安装插件 → 本地文件 → 选 `.difypkg`。
签名校验失败时（自建默认开启），`.env` 设 `FORCE_VERIFYING_SIGNATURE=false` 后重建 `plugin_daemon`。

**使用**：工作流里加「翻译文档」节点，绑定文件变量、选目标语言和模型，结束节点输出 `files`。

## 已知限制

- 域代码（TOC、页码、交叉引用）不重算，翻完在 Word 里按 F9 更新。
- 修订记录里的删除文本不动、新增文本照常翻译。
- 含制表符/图片的单行 run 会被跳过（不破坏排版，但那几个词不翻）。
- 单次调用受 `PLUGIN_MAX_EXECUTION_TIMEOUT`（1800s）限制，大文档走三节点分片工作流。
- PDF 默认是「可读优先」：正文会重排，页数可能变多；表格和页眉页脚保持在原位，不跟着正文移动。
- 扫描件（无文本层）解析出 0 段会直接报错，不做 OCR。
