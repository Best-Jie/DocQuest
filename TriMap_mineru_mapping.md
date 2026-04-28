# Tri-Map 与 MinerU 输出字段映射

## 1. 目的

本文档用于明确：

1. Tri-Map 当前阶段选择 `MinerU` 作为唯一文档解析后端
2. MinerU `content_list.json` 中哪些字段进入 `text / image / table` 三路原始 evidence
3. 哪些块类型应保留，哪些应默认过滤
4. 现阶段 `parsed_document.json` 与 evidence 文件的统一输出规则

参考：

- MinerU 输出说明文档：https://opendatalab.github.io/MinerU/zh/reference/output_files/

---

## 2. 当前采用的 MinerU 输入

当前 Tri-Map 直接读取每个文档对应的：

- `*_content_list.json`
- 若存在，也兼容 `*_content_list_v2.json`

以及同目录下的：

- `images/`

当前代码会在 `tri_map_config.toml` 中指定：

- `tri_map.mineru.output_root`

然后根据 `doc_id` 的 stem，例如 `2003.13032.pdf -> 2003.13032`，递归搜索：

- `**/2003.13032_content_list.json`
- `**/2003.13032_content_list_v2.json`

---

## 3. Tri-Map 三路 evidence 的总体原则

Tri-Map 当前阶段把 MinerU 的输出视为三类原始证据来源：

- `text` 路：正文块、标题块、列表块
- `image` 路：图片 / 图示块
- `table` 路：表格块

注意：

- 这里的 `summary`、`retrieval`、`QA` 还在后续阶段
- 当前阶段只负责稳定地产生统一 evidence

---

## 4. 块类型保留规则

### 4.1 保留进入 evidence 的类型

| MinerU type | 去向 | 说明 |
| --- | --- | --- |
| `text` | text route | v1 正文或标题块 |
| `title` | text route | v2 标题块 |
| `paragraph` | text route | v2 正文块 |
| `list` | text route | 列表块，保留为文本证据 |
| `image` | image route | 图片、子图、图示等 |
| `table` | table route | 表格截图与结构化表内容 |

### 4.2 默认过滤的类型

| MinerU type | 当前处理 |
| --- | --- |
| `aside_text` | 默认过滤 |
| `page_aside_text` | 默认过滤 |
| `page_footnote` | 默认过滤 |
| `page_header` | 默认过滤 |
| `page_footer` | 默认过滤 |
| `page_number` | 默认过滤 |

原因：

- 这些块多数不是主证据
- 如果直接进入 evidence，容易污染 retrieval 和 summary

后续如果某类任务确实依赖脚注，可再单独加开关。

---

## 5. Text Map 字段映射

### 5.1 `type = text / title / paragraph`

MinerU v1 常见字段：

```json
{
  "type": "text",
  "text": "...",
  "text_level": 1,
  "bbox": [x1, y1, x2, y2],
  "page_idx": 0
}
```

MinerU v2 常见字段：

```json
{
  "type": "title",
  "content": {
    "title_content": [
      {
        "type": "text",
        "content": "..."
      }
    ],
    "level": 1
  },
  "bbox": [x1, y1, x2, y2]
}
```

当前映射规则：

- `page = page_idx + 1`
- `text -> text`
- `bbox -> bbox`
- 如果块类型是 `title`，或 v1 `text` 中存在 `text_level`，则 `source_type = title`
- 否则 `source_type = paragraph`

映射后输出示例：

```json
{
  "doc_id": "2003.13032.pdf",
  "block_id": "mineru_text_p1_b1",
  "page": 1,
  "section": "",
  "text": "Named Entities in Medical Case Reports: Corpus and Experiments",
  "source_type": "title",
  "bbox": [147, 102, 842, 122],
  "source": "mineru_vlm"
}
```

### 5.2 `type = list`

MinerU 常见字段：

```json
{
  "type": "list",
  "sub_type": "text",
  "list_items": [
    "- item 1",
    "- item 2"
  ],
  "bbox": [...],
  "page_idx": 0
}
```

当前映射规则：

- `list_items` 用换行拼接成一个文本块
- `source_type = list`

原因：

- 列表经常是 FetaTab / PaperTab 问题的关键证据
- 不能因为它不是自然段就丢掉

---

## 6. Image Map 字段映射

MinerU 常见字段：

```json
{
  "type": "image",
  "img_path": "images/xxx.jpg",
  "image_caption": ["Figure 1: ..."],
  "image_footnote": [],
  "bbox": [...],
  "page_idx": 1
}
```

当前映射规则：

- `img_path` 解析为相对于 `content_list.json` 所在目录的路径
- 解析后图片会复制到 Tri-Map 当前文档输出目录
- `image_caption` 拼接后写入 `caption`
- `image_footnote` 拼接后写入 `ocr_text`
- `type` 当前统一映射为 `figure`

映射后输出示例：

```json
{
  "doc_id": "2003.13032.pdf",
  "image_id": "mineru_img_p2_b1",
  "page": 2,
  "type": "figure",
  "caption": "Figure 1: Annotated entities (WebAnno)",
  "summary": "",
  "image_path": "tmp/tri_map/PaperTab/parsed/2003.13032/raw_img_p2_b1_xxx.jpg",
  "bbox": [94, 403, 468, 434],
  "ocr_text": "",
  "source": "mineru_vlm"
}
```

说明：

- 当前阶段不做子图合并
- 即使 `(a)(b)(c)` 属于同一大图，也先保持“一块一个 evidence”

---

## 7. Table Map 字段映射

MinerU 常见字段：

```json
{
  "type": "table",
  "img_path": "images/xxx.jpg",
  "table_caption": ["Table 1: ..."],
  "table_footnote": [],
  "table_body": "<table>...</table>",
  "bbox": [...],
  "page_idx": 1
}
```

当前映射规则：

- `img_path` 解析为表格截图路径，并复制到 Tri-Map 输出目录
- `table_caption` 拼接后写入 `caption`
- `table_footnote` 拼接后写入 `ocr_text`
- `table_body` 直接保留为 `html`
- 额外从 `table_body` 中解析：
  - `schema`
  - `n_rows`
  - `rows`

当前 evidence 输出示例：

```json
{
  "doc_id": "2003.13032.pdf",
  "table_id": "mineru_table_p2_b1",
  "page": 2,
  "caption": "Table 1: Summary overview of relevant and comparable corpora.",
  "summary": "",
  "schema": ["Corpus", "Annotated entities", "Relationships", "# documents"],
  "n_rows": 8,
  "rows": [
    ["BC5CDR", "chemicals (4,409), diseases (5,818)", "chemical-disease (3116)", "1,500 PubMed articles"]
  ],
  "table_image_path": "tmp/tri_map/PaperTab/parsed/2003.13032/raw_table_p2_b1_xxx.jpg",
  "bbox": [82, 79, 905, 167],
  "ocr_text": "",
  "html": "<table>...</table>",
  "markdown": null,
  "sqlite_table_name": "",
  "source": "mineru_vlm"
}
```

---

## 8. `parsed_document.json` 中的统一表示

当前 parser 输出统一为：

- `ParsedDocument`
- 每页对应一个 `ParsedPage`
- 每页包含：
  - `text_blocks`
  - `image_regions`
  - `table_regions`

注意：

- MinerU 当前没有直接给整页图片路径
- 因此 `ParsedPage.page_image_path` 目前为空字符串
- `ParsedPage.text_path` 当前指向该文档的 `content_list.json`

这不会影响后续 summary / retrieval / QA，因为它们实际消费的是 evidence 文件，而不是整页缓存。

---

## 9. 当前实现边界

当前版本已经做到：

1. 用 MinerU 取代 `pdffigures2`
2. 稳定生成三路原始 evidence
3. 对表格保留截图 + HTML + 简单行结构

当前还没做：

1. section 级别结构恢复
2. 子图合并
3. 表格写入 SQLite
4. summary builder
5. retrieval
6. branch-wise QA
7. merge

---

## 10. 一句话结论

当前 Tri-Map 的 MinerU 接入原则可以概括为：

> 直接把 MinerU 的 `content_list` 视为 modality-aware block stream，再稳定映射成 text / image / table 三路原始 evidence。
