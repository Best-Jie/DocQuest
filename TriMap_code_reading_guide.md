# Tri-Map 代码导读

## 1. 这份文档是干什么的

这份文档不是研究计划，也不是接口规范。  
它的目的很简单：

> 帮你从“我运行了 MinerU 命令”一直读到“Tri-Map 生成了三路 evidence 文件”。

如果你现在的困惑是：

- 我到底先做了什么？
- 代码到底从哪里开始看？
- 每个文件在这条链里干什么？
- 我怎么确认现在的实现是对的？

那就按这份文档读。

---

## 2. 先从整体流程理解

当前真实流程只有两段：

### 第一步：你先用 MinerU 解析 PDF

你实际运行的是：

```bash
/new-data/new-ywj/external_tools/MinerU/.venv/bin/mineru \
  -p /new-data/new-ywj/DocQuest/data/PaperTab/documents/2003.13032.pdf \
  -o /new-data/new-ywj/tool_outputs/mineru/papertab_2003_13032_remote \
  -b vlm-http-client \
  -u "http://10.10.109.214:30000"
```

这一步是“文档解析”。

它的输出不是 Tri-Map 自己定义的格式，而是 MinerU 自己的格式，例如：

- `2003.13032_content_list.json`
- `2003.13032_content_list_v2.json`
- `images/`

### 第二步：Tri-Map 再把 MinerU 输出转成三路 evidence

你运行：

```bash
python scripts/build_tri_map_evidence.py \
  --config config/tri_map_config.toml \
  --dataset-name PaperTab \
  --doc-id 2003.13032.pdf \
  --page-limit 3
```

这一步是“格式对齐 + evidence 导出”。

它最终产生：

- `parsed_document.json`
- `text_units.jsonl`
- `image_units.json`
- `table_units.json`

所以你可以把当前系统理解成：

> MinerU 负责解析，Tri-Map 负责对齐和导出 evidence。

---

## 3. 现在最重要的代码文件只有 4 个

### 3.1 [config/tri_map_config.toml](/new-data/new-ywj/DocQuest/config/tri_map_config.toml)

你先看这个文件。

原因：

- 它告诉你 Tri-Map 去哪里找 PDF
- 去哪里找 MinerU 输出
- 默认忽略哪些 block 类型

你只要先知道这一点就够了：

- `dataset.document_path` 决定原始 PDF 在哪里
- `tri_map.mineru.output_root` 决定 MinerU 输出在哪里

---

### 3.2 [scripts/build_tri_map_evidence.py](/new-data/new-ywj/DocQuest/scripts/build_tri_map_evidence.py)

这个文件是入口。

你可以按下面顺序读：

#### A. 先看 `main()`

这里决定：

- 读哪个配置
- 数据集名字是什么
- 文档 id 是什么
- MinerU 根目录是什么

#### B. 再看 `parse_one_document()`

这里就是单文档主线：

1. 算出 `pdf_path`
2. 算出输出目录 `tmp/tri_map/.../parsed/<doc_name>`
3. 调用 `parser.parse_document(...)`
4. 调用 `evidence_builder.build_from_parsed_document(...)`

所以这个脚本本质上只是调度器。

它自己不负责：

- 解析 MinerU JSON 细节
- 解析 HTML table

这些都交给下面两个文件。

---

### 3.3 [mydatasets/tri_map_parser.py](/new-data/new-ywj/DocQuest/mydatasets/tri_map_parser.py)

这个文件是当前最核心的代码。

它的职责只有一句话：

> 把 MinerU block 变成 Tri-Map 的统一中间表示。

建议你按这个顺序读：

#### A. 先看 `parse_document()`

这是总入口。

它做的事情是：

1. 找到对应的 `content_list`
2. 把 MinerU 的 block 一页一页迭代出来
3. 根据 block type 分别转成：
   - `RawTextBlock`
   - `RawImageRegion`
   - `RawTableRegion`
4. 最后写出 `parsed_document.json`

#### B. 再看 `_resolve_content_list_path()`

这个函数负责：

- 根据 `doc_id` 找到对应的 MinerU 输出文件
- 优先找 `content_list_v2.json`
- 找不到再退回 `content_list.json`

这个函数解决的是：

> “给我一个 PDF 名字，我怎么在 MinerU 输出目录里找到它对应的解析结果？”

#### C. 再看 `_iter_blocks()`

这个函数非常关键，因为它处理了 MinerU v1 和 v2 的差异：

- v1 是一个扁平 list，每个 block 自带 `page_idx`
- v2 是按 page 分组的 list of list

所以这个函数解决的是：

> “不管 MinerU 给我的格式长什么样，我都统一迭代成 `(page_num, block)`。”

#### D. 再看三段分支逻辑

在 `parse_document()` 里你会看到：

- `if block_type in {"text", "title", "paragraph"}`
- `if block_type == "list"`
- `if block_type == "image"`
- `if block_type == "table"`

这四段就是当前 Tri-Map 的核心映射规则。

你可以把它理解成：

- 文本怎么进 text route
- 图片怎么进 image route
- 表格怎么进 table route

#### E. 最后再看 `_extract_*` 这些辅助函数

比如：

- `_extract_text_value()`
- `_extract_list_value()`
- `_extract_image_caption()`
- `_extract_table_html()`

这些函数的作用不是“控制流程”，而是：

> 把 MinerU v1/v2 里不同字段路径上的值抽出来。

所以读法上应该是：

- 先看主流程
- 再回头看这些 helper

不然容易淹没在细节里。

---

### 3.4 [mydatasets/tri_map_evidence_builder.py](/new-data/new-ywj/DocQuest/mydatasets/tri_map_evidence_builder.py)

这个文件的职责也很单一：

> 把 `parsed_document.json` 导出成后续模块真正要消费的 evidence 文件。

建议按这个顺序读：

#### A. 先看 `build_from_parsed_document()`

它做的就是三件事：

1. 遍历每页的 `text_blocks`
2. 遍历每页的 `image_regions`
3. 遍历每页的 `table_regions`

然后分别写出：

- `text_units.jsonl`
- `image_units.json`
- `table_units.json`

#### B. 再看表格相关 helper

最值得看的有两个：

- `_extract_table_rows()`
- `_extract_schema()`

这两个函数解决的是：

> “MinerU 已经给了 HTML table，我怎么把它变成更好用的 `schema + rows`？”

所以这个文件的重点不是“解析器”，而是“导出器”。

---

## 4. 当前数据流到底长什么样

你可以把当前数据流画成这样：

```text
PDF
  -> MinerU
  -> content_list(.json / _v2.json) + images/
  -> TriMapParser
  -> parsed_document.json
  -> TriMapEvidenceBuilder
  -> text_units.jsonl + image_units.json + table_units.json
```

如果你记不住所有细节，至少记住这一张图。

---

## 5. 你怎么检查代码有没有按预期工作

最简单的方法不是先看代码，而是先看输出文件。

### 先看：

- [parsed_document.json](/new-data/new-ywj/DocQuest/tmp/tri_map/PaperTab/parsed/2003.13032/parsed_document.json)

你要检查：

- 页数对不对
- 每页 `text_blocks / image_regions / table_regions` 数量对不对

### 再看：

- [text_units.jsonl](/new-data/new-ywj/DocQuest/tmp/tri_map/PaperTab/parsed/2003.13032/evidence/text_units.jsonl)
- [image_units.json](/new-data/new-ywj/DocQuest/tmp/tri_map/PaperTab/parsed/2003.13032/evidence/image_units.json)
- [table_units.json](/new-data/new-ywj/DocQuest/tmp/tri_map/PaperTab/parsed/2003.13032/evidence/table_units.json)

你要检查：

- 文本 evidence id 是否合理
- 图片路径是否真的存在
- 表格是否已经有 `schema / n_rows / rows`

如果输出文件对了，说明代码主线基本就对了。

---

## 6. 你现在最该记住的几个判断

### 判断 1

当前 Tri-Map 不是在做问答，它是在做问答前的底座。

### 判断 2

MinerU 不是“可选增强”，而是当前唯一解析后端。

### 判断 3

`tri_map_parser.py` 负责“对齐”，`tri_map_evidence_builder.py` 负责“导出”。

### 判断 4

当前最有价值的进展不是图片，而是：

> table evidence 已经不再只是截图，而是已经有结构化 rows 了。

### 判断 5

后面所有 summary / retrieval / QA 都应该直接建立在当前 evidence 文件上，而不是重新回头读 MinerU 原始 JSON。

---

## 7. 你下一次自己读代码时的顺序

建议你每次都按这个顺序读：

1. `tri_map_config.toml`
2. `build_tri_map_evidence.py`
3. `tri_map_parser.py`
4. `tri_map_evidence_builder.py`
5. 输出目录里的 `parsed_document.json`
6. 输出目录里的三类 evidence

这个顺序的好处是：

- 先知道入口
- 再知道主流程
- 再看细节
- 最后回到结果验证

这样不容易迷路。

---

## 8. 如果你要继续往下做，应该接哪里

当前最自然的下一步不是再折腾 parser，而是直接从 evidence 往后接：

1. `text summary builder`
2. `image summary builder`
3. `table summary builder`
4. `router`
5. `branch retrieval`
6. `branch-wise QA`
7. `merge`

也就是说，当前代码已经够你进入下一阶段了。

---

## 9. 一句话总结

如果你只想记住一句话，那就是：

> 你现在做成的是一条 “MinerU 解析结果 -> Tri-Map 三路原始 evidence” 的稳定转换链路，而不是最终 QA 系统本身。
