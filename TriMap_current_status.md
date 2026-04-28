# Tri-Map 当前阶段代码与中间结果说明

## 1. 现在做到哪一步了

目前 Tri-Map 的第一阶段已经切换到：

**MinerU-only 文档解析底座**

也就是说，当前不再保留原来的 `pdffigures2 + 页面级 TXT/PNG fallback` 方案，而是直接使用：

- MinerU 负责把 PDF 解析成结构化 block
- Tri-Map parser 负责把 MinerU block 转成统一的 `parsed_document.json`
- evidence builder 负责把统一结构导出成三路原始 evidence

当前已经跑通的能力是：

1. 输入单个 PDF
2. 从 MinerU 输出目录自动找到对应的 `content_list.json` 或 `content_list_v2.json`
3. 生成 `parsed_document.json`
4. 生成三类 evidence：
   - `text_units.jsonl`
   - `image_units.json`
   - `table_units.json`
5. 表格 evidence 不再只是截图，而是已经保留：
   - `html`
   - `schema`
   - `n_rows`
   - `rows`

换句话说，现在 Tri-Map 的“底座”已经不再是粗页面级表示，而是：

> 基于 MinerU block 的 text / image / table 三路原始证据生成器

---

## 2. 你现在实际使用的解析命令

你现在实际使用的 MinerU 命令是：

```bash
/new-data/new-ywj/external_tools/MinerU/.venv/bin/mineru \
  -p /new-data/new-ywj/DocQuest/data/PaperTab/documents/2003.13032.pdf \
  -o /new-data/new-ywj/tool_outputs/mineru/papertab_2003_13032_remote \
  -b vlm-http-client \
  -u "http://10.10.109.214:30000"
```

这一步的职责是：

- 把 PDF 交给 MinerU 的 `vlm-http-client` 后端解析
- 在指定输出目录下生成：
  - `*_content_list.json`
  - `*_content_list_v2.json`
  - `images/`

Tri-Map 当前不负责调用远程 VLM 解析本身。  
Tri-Map 当前负责的是：

> 消费你已经产出的 MinerU 结果，并把它们整理成三路原始 evidence

---

## 3. 现在有哪些关键代码文件

### 配置文件

- [config/tri_map_config.toml](/new-data/new-ywj/DocQuest/config/tri_map_config.toml)

作用：

- 这是 Tri-Map 当前的专用配置文件
- 现在已经明确指定：
  - parser backend = `mineru`
  - MinerU 输出根目录
  - 默认过滤哪些 block type

当前最关键的配置项是：

```toml
[tri_map.mineru]
output_root = "/new-data/new-ywj/tool_outputs/mineru"
copy_visual_assets = true
ignored_types = ["aside_text", "page_aside_text", "page_footnote", "page_header", "page_footer", "page_number"]
```

---

### 入口脚本

- [scripts/build_tri_map_evidence.py](/new-data/new-ywj/DocQuest/scripts/build_tri_map_evidence.py)

作用：

1. 读取 `tri_map_config.toml`
2. 根据 `dataset-name` 和 `doc-id` 找到目标 PDF
3. 根据 `doc_id` 去 MinerU 输出目录搜索对应的 `content_list`
4. 调用 parser 生成 `parsed_document.json`
5. 调用 evidence builder 生成三类 evidence 文件

当前这个脚本有两个重要特点：

1. 不再依赖 `BaseDataset`
2. 不再依赖 `pymupdf`

这么做的目的很明确：

- 减少旧代码链路的耦合
- 让 Tri-Map 的 MinerU 底座可以独立运行

---

### 解析器

- [mydatasets/tri_map_parser.py](/new-data/new-ywj/DocQuest/mydatasets/tri_map_parser.py)

作用：

- 读取 MinerU `content_list.json` 或 `content_list_v2.json`
- 统一转成 `ParsedDocument`

当前 parser 的核心逻辑是：

1. 根据 `doc_id` 自动搜索：
   - `*_content_list_v2.json`
   - `*_content_list.json`
2. 同时兼容 MinerU v1 / v2 两种结构
3. 把以下 block 映射到 Tri-Map 三路：
   - `text / title / paragraph` -> `RawTextBlock`
   - `list` -> `RawTextBlock`
   - `image` -> `RawImageRegion`
   - `table` -> `RawTableRegion`
4. 默认过滤：
   - `aside_text`
   - `page_aside_text`
   - `page_footnote`
   - `page_header`
   - `page_footer`
   - `page_number`
5. 把图片和表格截图复制到 Tri-Map 当前文档输出目录

当前 parser 已经不是“页面级粗切分器”，而是：

> MinerU block 到 Tri-Map 统一中间表示的转换器

---

### Evidence 构建器

- [mydatasets/tri_map_evidence_builder.py](/new-data/new-ywj/DocQuest/mydatasets/tri_map_evidence_builder.py)

作用：

- 读取 `parsed_document.json`
- 转成后续 Tri-Map 可直接使用的 evidence 文件：
  - `text_units.jsonl`
  - `image_units.json`
  - `table_units.json`

相比之前，这一步现在有一个关键增强：

- 会从表格的 `html` 中解析出：
  - `schema`
  - `n_rows`
  - `rows`

所以现在的 table branch 输入已经明显强于“只有截图”的版本。

---

## 4. 当前这套代码是怎么跑通的

当前单文档流程可以理解为下面 4 步。

### 第一步：先用 MinerU 解析 PDF

以 `2003.13032.pdf` 为例，你先运行：

```bash
/new-data/new-ywj/external_tools/MinerU/.venv/bin/mineru \
  -p /new-data/new-ywj/DocQuest/data/PaperTab/documents/2003.13032.pdf \
  -o /new-data/new-ywj/tool_outputs/mineru/papertab_2003_13032_remote \
  -b vlm-http-client \
  -u "http://10.10.109.214:30000"
```

MinerU 输出目录中会出现：

- [2003.13032_content_list.json](/new-data/new-ywj/tool_outputs/mineru/papertab_2003_13032_remote/2003.13032/vlm/2003.13032_content_list.json)
- [2003.13032_content_list_v2.json](/new-data/new-ywj/tool_outputs/mineru/papertab_2003_13032_remote/2003.13032/vlm/2003.13032_content_list_v2.json)
- `images/`

---

### 第二步：Tri-Map 读取 MinerU 输出

运行：

```bash
python scripts/build_tri_map_evidence.py \
  --config config/tri_map_config.toml \
  --dataset-name PaperTab \
  --doc-id 2003.13032.pdf \
  --page-limit 3
```

这个脚本会：

1. 找到原始 PDF：
   - `data/PaperTab/documents/2003.13032.pdf`
2. 去 `tri_map.mineru.output_root` 下搜索对应的 content list
3. 调用 `TriMapParser.parse_document()`

---

### 第三步：生成 `parsed_document.json`

当前 parser 会把 MinerU 的 block 统一写成：

- `pages[i].text_blocks`
- `pages[i].image_regions`
- `pages[i].table_regions`

当前样例输出路径：

- [parsed_document.json](/new-data/new-ywj/DocQuest/tmp/tri_map/PaperTab/parsed/2003.13032/parsed_document.json)

---

### 第四步：生成 evidence

`TriMapEvidenceBuilder.build_from_parsed_document()` 会把统一结构导出成：

- [text_units.jsonl](/new-data/new-ywj/DocQuest/tmp/tri_map/PaperTab/parsed/2003.13032/evidence/text_units.jsonl)
- [image_units.json](/new-data/new-ywj/DocQuest/tmp/tri_map/PaperTab/parsed/2003.13032/evidence/image_units.json)
- [table_units.json](/new-data/new-ywj/DocQuest/tmp/tri_map/PaperTab/parsed/2003.13032/evidence/table_units.json)

这三类文件就是后面：

- summary
- retrieval
- branch-wise QA

的直接输入。

---

## 5. 当前已经验证过的样例

### PaperTab: `2003.13032.pdf`

运行命令：

```bash
python scripts/build_tri_map_evidence.py \
  --config config/tri_map_config.toml \
  --dataset-name PaperTab \
  --doc-id 2003.13032.pdf \
  --page-limit 3
```

当前验证结果：

- `text_units = 46`
- `image_units = 7`
- `table_units = 4`

这说明目前前三页已经能够同时跑出：

- 文本 evidence
- 图片 evidence
- 表格 evidence

这和之前 `pdffigures2` 版本最大的区别是：

- 现在 table branch 已经真正可用

---

## 6. 当前 evidence 长什么样

### 6.1 Text evidence

示例：

```json
{
  "doc_id": "2003.13032.pdf",
  "block_id": "mineru_text_p1_b1",
  "page": 1,
  "text": "Named Entities in Medical Case Reports: Corpus and Experiments",
  "source_type": "title",
  "bbox": [147.0, 102.0, 842.0, 122.0],
  "source": "mineru_vlm"
}
```

解释：

- 文本块现在直接来自 MinerU block
- 不再是整页 TXT 的粗切分结果
- `source_type` 能区分 `title / paragraph / list`

---

### 6.2 Image evidence

示例：

```json
{
  "doc_id": "2003.13032.pdf",
  "image_id": "mineru_img_p2_b1",
  "page": 2,
  "type": "figure",
  "caption": "(a) Factor and case annotation",
  "image_path": "tmp/tri_map/PaperTab/parsed/2003.13032/raw_img_p2_b1_6847....jpg",
  "bbox": [92.0, 203.0, 467.0, 239.0],
  "ocr_text": "",
  "source": "mineru_vlm"
}
```

解释：

- 图片块来自 MinerU 的 `image`
- 截图路径已经复制到 Tri-Map 当前输出目录
- 后续 image summary / retrieval / QA 可以直接消费

---

### 6.3 Table evidence

示例：

```json
{
  "doc_id": "2003.13032.pdf",
  "table_id": "mineru_table_p2_b1",
  "page": 2,
  "caption": "Table 1: Summary overview of relevant and comparable corpora.",
  "schema": ["Corpus", "Annotated entities", "Relationships", "# documents"],
  "n_rows": 8,
  "rows": [
    ["BC5CDR", "chemicals (4,409), diseases (5,818)", "chemical-disease (3116)", "1,500 PubMed articles"]
  ],
  "table_image_path": "tmp/tri_map/PaperTab/parsed/2003.13032/raw_table_p2_b1_c728....jpg",
  "html": "<table>...</table>",
  "source": "mineru_vlm"
}
```

解释：

- 表格不再只是图片截图
- 已经保留 HTML
- 已经能直接恢复行列结构

这正是当前 Tri-Map 最关键的底层提升。

---

## 7. 你现在应该怎么理解这套代码

你可以把当前第一阶段理解成一句话：

> 我们已经实现了一个基于 MinerU 的三路原始 evidence 生成器，它能把 PDF 转成 text / image / table 三类统一证据。

更具体地说：

- `build_tri_map_evidence.py`
  - 负责调度
- `tri_map_parser.py`
  - 负责把 MinerU 输出转成统一结构
- `tri_map_evidence_builder.py`
  - 负责把统一结构导出成后续模块可直接消费的 evidence 文件

也就是说，我们现在做的仍然不是最终问答，而是在做 Tri-Map 的“底座”。

---

## 8. 当前还没做好的地方

目前仍然是第一阶段版本，主要限制有：

1. 还没有 text / image / table summary builder
2. 还没有 router
3. 还没有 branch retrieval
4. 还没有 branch-wise QA
5. 还没有 merge
6. 还没有把 table 写入 SQLite
7. 还没有做 section 级结构恢复
8. 还没有做子图合并

所以目前的状态应理解为：

- 文档解析底座已经换成 MinerU
- 三路原始 evidence 已经能生成
- 后面的问答层还没开始实现

---

## 9. 下一步最自然的工作

当前最自然的后续方向有两个：

### 方向 A：开始做 summary builder

在已有 evidence 的基础上做：

- text summary builder
- image summary builder
- table summary builder

这是最自然的下一步，因为三路原始输入已经齐了。

### 方向 B：先把 table store 做出来

即：

- 把 `table_units.json` 进一步写入 SQLite
- 为后续 `table retrieval / table QA` 做准备

如果你想尽快看到“三路结构”的雏形，方向 A 更直接。  
如果你想先把表格链路做扎实，方向 B 更稳。

---

## 10. 一句话总结

当前 Tri-Map 的真实状态可以概括为：

> 已经完成 MinerU-only 的三路 evidence 底座，实现了 text / image / table 原始证据生成，并在 `2003.13032.pdf` 上验证通过；后续工作重点是 summary、retrieval、QA 和 merge。
