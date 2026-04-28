# Tri-Map 三路输出格式与 Merge 模块接口说明

## 1. 文档目的

本文档用于明确 Tri-Map DocQA 当前阶段和下一阶段的接口规范，重点定义：

1. 当前已经落地的 evidence 输入格式
2. 三路检索输出格式
3. 三路问答输出格式
4. Merge 模块输入输出格式
5. 为后续 Judge / Verdict Agent 预留的扩展位

设计原则：

- 当前解析后端统一采用 `MinerU`
- 当前阶段先把三路原始 evidence 做扎实
- 下一阶段再实现 summary / retrieval / QA / merge
- 每一路都必须带上“答案 + 证据 + 元信息”，不能只返回一句自由文本

---

## 2. 当前已经落地的输入接口

Tri-Map 当前已经实现到：

1. 文档解析
2. 生成 `parsed_document.json`
3. 生成 text / image / table evidence

当前流程中的接口位置是：

1. `MinerU Output`
2. `ParsedDocument`
3. `Text / Image / Table Evidence`
4. `Router Output`
5. `Branch Retrieval Output`
6. `Branch QA Output`
7. `Merge Input / Output`

其中当前已经真正落地的是前 3 个。

---

## 3. MinerU Output -> ParsedDocument

当前 parser 会消费：

- `*_content_list.json`
- `*_content_list_v2.json`

并统一输出：

```json
{
  "doc_id": "2003.13032.pdf",
  "doc_name": "2003.13032",
  "pdf_path": "...",
  "output_dir": "...",
  "parser_backend": "mineru",
  "pages": [
    {
      "page": 1,
      "text_blocks": [...],
      "image_regions": [...],
      "table_regions": [...]
    }
  ]
}
```

### 当前 block 映射规则

| MinerU block type | Tri-Map target |
| --- | --- |
| `text` | `RawTextBlock` |
| `title` | `RawTextBlock` |
| `paragraph` | `RawTextBlock` |
| `list` | `RawTextBlock` |
| `image` | `RawImageRegion` |
| `table` | `RawTableRegion` |

默认过滤：

- `aside_text`
- `page_aside_text`
- `page_footnote`
- `page_header`
- `page_footer`
- `page_number`

---

## 4. 当前 evidence 文件接口

### 4.1 Text Evidence

输出文件：

- `text_units.jsonl`

单条格式：

```json
{
  "doc_id": "2003.13032.pdf",
  "doc_name": "2003.13032",
  "block_id": "mineru_text_p1_b1",
  "page": 1,
  "section": "",
  "text": "Named Entities in Medical Case Reports: Corpus and Experiments",
  "source_type": "title",
  "bbox": [147.0, 102.0, 842.0, 122.0],
  "source": "mineru_vlm"
}
```

### 4.2 Image Evidence

输出文件：

- `image_units.json`

单条格式：

```json
{
  "doc_id": "2003.13032.pdf",
  "doc_name": "2003.13032",
  "image_id": "mineru_img_p2_b1",
  "page": 2,
  "type": "figure",
  "caption": "(a) Factor and case annotation",
  "summary": "",
  "image_path": "tmp/tri_map/PaperTab/parsed/2003.13032/raw_img_p2_b1_xxx.jpg",
  "bbox": [92.0, 203.0, 467.0, 239.0],
  "ocr_text": "",
  "source": "mineru_vlm"
}
```

### 4.3 Table Evidence

输出文件：

- `table_units.json`

单条格式：

```json
{
  "doc_id": "2003.13032.pdf",
  "doc_name": "2003.13032",
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
  "bbox": [82.0, 79.0, 905.0, 167.0],
  "ocr_text": "",
  "html": "<table>...</table>",
  "markdown": null,
  "sqlite_table_name": "",
  "source": "mineru_vlm"
}
```

---

## 5. Router 输出格式

Router 的职责不是答题，而是根据：

- question
- text summary
- image summary
- table summary

判断：

- 哪些模态 relevant
- 每个模态的候选 evidence ids

推荐输出：

```json
{
  "question": "What awards was Into the Woods nominated for and which ones did it win?",
  "need_text": true,
  "need_image": false,
  "need_table": true,
  "text_candidates": [
    "mineru_text_p11_b3",
    "mineru_text_p12_b2"
  ],
  "image_candidates": [],
  "table_candidates": [
    "mineru_table_p12_b1"
  ],
  "routing_reason": {
    "text": "question refers to award-related textual records",
    "image": "no obvious figure/chart dependency",
    "table": "award question likely answered by structured table rows"
  }
}
```

### 字段说明

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `question` | `str` | 原始问题 |
| `need_text` | `bool` | 是否启用文本分支 |
| `need_image` | `bool` | 是否启用图片分支 |
| `need_table` | `bool` | 是否启用表格分支 |
| `text_candidates` | `list[str]` | 文本候选 `block_id` |
| `image_candidates` | `list[str]` | 图片候选 `image_id` |
| `table_candidates` | `list[str]` | 表格候选 `table_id` |
| `routing_reason` | `dict` | 路由原因说明，可选但建议保留 |

---

## 6. Branch Retrieval 输出格式

每一路 retrieval 的职责是：

- 接收 Router 候选集
- 从该模态的 evidence space 中选出更精确的 evidence

### 6.1 Text Retrieval 输出

```json
{
  "branch": "text",
  "question": "...",
  "selected_evidence": [
    {
      "id": "mineru_text_p12_b2",
      "page": 12,
      "section": "Awards and nominations",
      "score": 0.91,
      "text": "2011 Laurence Olivier Award Best Musical Revival Won ..."
    }
  ]
}
```

### 6.2 Image Retrieval 输出

```json
{
  "branch": "image",
  "question": "...",
  "selected_evidence": [
    {
      "id": "mineru_img_p8_b2",
      "page": 8,
      "score": 0.76,
      "caption": "Top Practice Speeds",
      "image_path": "..."
    }
  ]
}
```

### 6.3 Table Retrieval 输出

```json
{
  "branch": "table",
  "question": "...",
  "selected_evidence": [
    {
      "id": "mineru_table_p12_b1",
      "page": 12,
      "score": 0.94,
      "caption": "Awards and nominations",
      "schema": ["Year", "Award", "Category", "Nominee", "Result"],
      "sqlite_table_name": "table_p12_1",
      "candidate_rows": [8, 9]
    }
  ]
}
```

---

## 7. Branch QA 输出格式

这一部分最关键。  
每一路问答都必须输出统一结构，以便 merge 模块后续可直接处理。

推荐统一 schema：

```json
{
  "branch": "text",
  "question": "...",
  "answer": "...",
  "confidence": 0.82,
  "reasoning_type": "text_lookup",
  "evidence": [
    {
      "id": "mineru_text_p12_b2",
      "page": 12,
      "type": "text_block"
    }
  ],
  "raw_response": "..."
}
```

### 必选字段

| 字段 | 类型 | 是否必须 | 说明 |
| --- | --- | --- | --- |
| `branch` | `str` | 是 | `text` / `image` / `table` |
| `question` | `str` | 是 | 原始问题 |
| `answer` | `str` | 是 | 该分支生成的答案 |
| `confidence` | `float` | 是 | 分支自评置信度，范围建议 `0~1` |
| `reasoning_type` | `str` | 是 | 推理类型，如 `text_lookup` / `table_lookup` / `visual_reading` |
| `evidence` | `list[dict]` | 是 | 该答案依赖的 evidence 列表 |
| `raw_response` | `str` | 否 | 原始模型输出，便于调试 |

### 7.1 Text QA 输出示例

```json
{
  "branch": "text",
  "question": "Where are the surviving, airworthy Avro Lancasters located?",
  "answer": "The airworthy Lancasters are at RAF Coningsby and the Canadian Warplane Heritage Museum.",
  "confidence": 0.78,
  "reasoning_type": "text_lookup",
  "evidence": [
    {
      "id": "mineru_text_p4_b5",
      "page": 4,
      "type": "text_block"
    },
    {
      "id": "mineru_text_p7_b2",
      "page": 7,
      "type": "text_block"
    }
  ]
}
```

### 7.2 Image QA 输出示例

```json
{
  "branch": "image",
  "question": "What driver had the fastest speed ... ?",
  "answer": "Tony Kanaan had the fastest speed at 226.680 mph, followed by Ed Carpenter and Gabby Chaves.",
  "confidence": 0.85,
  "reasoning_type": "visual_table_reading",
  "evidence": [
    {
      "id": "mineru_img_p8_b1",
      "page": 8,
      "type": "image_block"
    }
  ]
}
```

### 7.3 Table QA 输出示例

```json
{
  "branch": "table",
  "question": "What awards was Into the Woods nominated for and which ones did it win?",
  "answer": "Into the Woods won Best Musical Revival and was nominated for Best Performance in a Supporting Role in a Musical (Michael Xavier).",
  "confidence": 0.92,
  "reasoning_type": "table_lookup",
  "evidence": [
    {
      "id": "mineru_table_p12_b1",
      "page": 12,
      "type": "table",
      "rows": [8, 9]
    }
  ]
}
```

---

## 8. 空结果与无法回答的统一格式

如果某一路没有检索到有效证据，建议不要随意返回自然语言，而是统一为：

```json
{
  "branch": "image",
  "question": "...",
  "answer": "not answerable",
  "confidence": 0.0,
  "reasoning_type": "no_evidence",
  "evidence": []
}
```

这样 merge 模块更容易处理。

---

## 9. Merge 模块接口

当前阶段 merge 的目标不是复杂裁决，而是做一个简单、稳定、可扩展的合并层。

### 9.1 Merge 输入

Merge 输入应为三个 branch QA 输出的列表：

```json
{
  "question": "...",
  "branches": [
    { "branch": "text", ... },
    { "branch": "image", ... },
    { "branch": "table", ... }
  ]
}
```

### 9.2 Merge 输出

建议输出格式：

```json
{
  "final_answer": "...",
  "used_branches": ["table", "text"],
  "merge_strategy": "simple_synthesis",
  "supporting_evidence": [
    {
      "branch": "table",
      "id": "mineru_table_p12_b1",
      "page": 12
    }
  ],
  "raw_merge_response": "..."
}
```

### 字段说明

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `final_answer` | `str` | 最终答案 |
| `used_branches` | `list[str]` | 实际参与最终答案生成的分支 |
| `merge_strategy` | `str` | 当前固定为 `simple_synthesis` |
| `supporting_evidence` | `list[dict]` | 最终答案依赖的证据摘要 |
| `raw_merge_response` | `str` | merge 模块原始输出，可选 |

---

## 10. 当前阶段建议的 merge 行为

当前阶段不做复杂裁决，但建议至少遵守这些规则：

1. 如果某一路输出 `not answerable`，不强行纳入最终答案
2. 如果 table 分支有高置信度且 evidence 明确，可优先保留
3. merge 时不要简单拼接三段长答案，应压缩成一个统一简洁答案
4. 最终答案必须尽量保留 evidence 一致的部分，避免把明显冲突的内容无区别拼起来

注意：

这里仍然不叫“裁决”，只是简单 merge 规则。

---

## 11. 为后续 Judge 预留的扩展位

虽然当前阶段不做 Judge，但当前接口已经为后续升级预留了条件。

后续如果要加入 Judge，可以直接复用当前 branch QA 输出，因为其中已经包含：

- answer
- confidence
- evidence
- reasoning_type

届时只需把当前：

- `merge_strategy = simple_synthesis`

升级成：

- `merge_strategy = evidence_aware_judging`

并增加如下字段：

```json
{
  "chosen_branch": "table",
  "rejected_branches": [
    {
      "branch": "text",
      "reason": "too broad"
    }
  ]
}
```

---

## 12. 推荐的 Python 类型定义

如果后面在代码里用 `dataclass` 或 `TypedDict`，推荐可按如下思路定义。

### 12.1 Branch QA Result

```python
from typing import TypedDict, Literal, List

class EvidenceItem(TypedDict, total=False):
    id: str
    page: int
    type: str
    rows: List[int]

class BranchQAResult(TypedDict):
    branch: Literal["text", "image", "table"]
    question: str
    answer: str
    confidence: float
    reasoning_type: str
    evidence: List[EvidenceItem]
    raw_response: str
```

### 12.2 Merge Result

```python
class MergeResult(TypedDict, total=False):
    final_answer: str
    used_branches: List[str]
    merge_strategy: str
    supporting_evidence: List[EvidenceItem]
    raw_merge_response: str
```

---

## 13. 当前最重要的实现建议

如果你马上要开始写代码，最重要的是：

1. 先把 `summary` 的输入输出定住
2. retrieval 必须直接消费当前 evidence 文件，而不是重新回到原始 MinerU JSON
3. 三路 QA 的输出格式必须统一
4. Merge 先简单，但不要写死成只吃字符串
5. evidence 字段必须保留，不然后面 Judge 很难加
6. `not answerable` 的行为必须规范化

---

## 14. 一句话总结

当前阶段的接口设计目标不是“把系统一次做满”，而是：

> 先把 MinerU 产出的三路原始 evidence 接口定稳，再在这个稳定底座上实现 summary、retrieval、branch-wise QA 和 merge。
