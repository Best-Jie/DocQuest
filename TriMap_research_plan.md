# Tri-Map DocQA 研究计划（新版）

## 1. 研究背景

当前 DocQuest / DMAP 框架已经证明：将长文档的结构信息显式建模，并利用 summary 与 location 指导后续问答，能够优于纯页面级多模态问答方法。  
但在 FetaTab 这类强结构化文档问答场景中，现有方法仍存在明显瓶颈：

- 检索和定位主要停留在 `Page` 级别，缺少对文本块、图片、表格等证据单元的细粒度建模
- 页面中不同模态的证据混在一起，文本、图片、表格没有分开建模和分开检索
- 问答阶段仍然以“整页内容”为主要输入，难以稳定锁定正确的表格行、列表项或时间片段

因此，本研究希望在师兄现有工作的基础上，将 page-level 的 document map 进一步拓展为：

**面向文本、图片、表格三类证据的 modality-aware evidence map**

并通过三路独立检索和三路独立问答，验证该结构是否能更适合 FetaTab 这类结构化问题。

## 2. 当前研究问题

本研究试图回答以下问题：

1. 现有 page-level summary + location 是否不足以支持 FetaTab 这类结构化长文档问答？
2. 如果先通过文档解析工具将页面拆解为文本块、图片单元、表格单元，并分别建立 summary 与检索通路，是否能更稳定地定位正确证据？
3. 在不引入复杂裁决模块的前提下，仅通过三路 evidence-based QA 和简单 merge，是否已经能够优于现有 page-level pipeline？

## 3. 研究目标

本研究的总体目标是提出一套新的长文档多模态问答框架：

**Tri-Map DocQA**

其核心思想是：

- 先对文档进行细粒度解析
- 将文档拆分为文本、图片、表格三类证据空间
- 为三类证据分别生成 summary
- 分别做检索
- 分别做问答
- 最后做简单 merge，生成最终答案

当前阶段的重点不是“裁决”，而是先验证：

> modality-aware evidence map + branch-wise QA 是否本身就能带来提升。

## 4. 方法总览

### 4.1 总体框架

整体流程如下：

1. 文档解析
2. 三类证据单元抽取
3. 三类 summary 构建
4. 三路检索
5. 三路各自问答
6. 简单 merge
7. 输出最终答案

可概括为：

`Document -> Parse -> Text/Image/Table Maps -> Retrieval -> Three-branch QA -> Merge -> Final Answer`

### 4.2 为什么要加入文档解析工具

导师提出的关键点是：当前页面级处理仍然过粗。  
即使使用 ColPali，也本质上是把整页 page 当成很多图像 patch 来处理，并没有真正把：

- 文本区域
- 图片区域
- 表格区域

显式拆开。

因此，本研究建议在文档预处理阶段引入专门的文档解析工具，例如：

- MinerU
- 其他支持版面分析 / 目标检测 / OCR / 表格识别的工具

引入这一步的目的是：

1. 更准确地区分页面中的三类信息
2. 为后续三路 summary 和三路检索提供更自然的输入
3. 将原有“整页输入”改造成“证据单元输入”

## 5. 文档解析与三类证据地图

## 5.1 文档解析层

解析层负责把 PDF 页面拆成可用的结构单元。  
它可以基于 MinerU 或类似工具，输出：

- 页面中的文本块
- 页面中的图片 / 图表区域
- 页面中的表格区域
- 这些区域的 bbox、page id、caption、OCR 文本等信息

解析层不直接问答，它只负责为后续建图提供结构化输入。

## 5.2 Text Map

目标：

- 从页面中提取文本块
- 保存文本块级证据
- 构建文档文本 summary

每个文本块建议保存：

```json
{
  "doc_id": "...",
  "block_id": "text_p7_b12",
  "page": 7,
  "section": "...",
  "text": "...",
  "source_type": "paragraph | list | caption",
  "bbox": [x1, y1, x2, y2]
}
```

Text summary 的作用不是代替全文，而是作为 coarse routing 的目录，描述：

- 文档主题
- section 与页码映射
- 哪些文本块适合回答事实性、列表型、时间型问题

## 5.3 Image Map

目标：

- 提取文档中的图片、图表、照片、流程图等视觉单元
- 保存 image path、caption、页面信息
- 构建图片 summary

每个图片单元建议保存：

```json
{
  "doc_id": "...",
  "image_id": "img_p8_figure2",
  "page": 8,
  "type": "figure | chart | photo | page_region",
  "caption": "...",
  "summary": "...",
  "image_path": "...",
  "bbox": [x1, y1, x2, y2]
}
```

Image summary 主要描述：

- 文档中有哪些图
- 图的类型与 caption
- 哪些图适合回答趋势、比较、视觉统计类问题

## 5.4 Table Map

目标：

- 抽取表格区域
- 将表格内容结构化存储
- 构建表格 summary

每个表格单元建议保存：

```json
{
  "doc_id": "...",
  "table_id": "table_p12_1",
  "page": 12,
  "caption": "...",
  "schema": ["Year", "Award", "Category", "Nominee", "Result"],
  "n_rows": 12,
  "sqlite_table_name": "table_p12_1",
  "summary": "..."
}
```

表格内容建议写入 SQLite：

```sql
CREATE TABLE table_p12_1 (
  row_id INTEGER,
  Year TEXT,
  Award TEXT,
  Category TEXT,
  Nominee TEXT,
  Result TEXT
);
```

Table summary 的作用是：

- 告诉系统这篇文档有哪些表
- 每张表讲什么
- 每张表的字段有哪些
- 哪类问题适合路由到该表

## 6. 三类 summary 的定位

这里要特别强调：

**summary 不是最终证据，而是三路检索的“目录”和“导航图”。**

也就是说：

- text summary 用来帮助定位文本证据块
- image summary 用来帮助定位相关图片单元
- table summary 用来帮助定位相关表格单元

后续真正问答时，输入给大模型的应当是：

- `query + selected evidence`

而不是只用 summary 直接回答。

## 7. 三路检索

### 7.1 第一阶段：summary-guided routing

输入：

- question
- text summary
- image summary
- table summary

输出：

- 问题是否需要 text / image / table 分支
- 每个分支的候选 evidence ids
- 对表格分支，可选返回 table shortlist 或 query plan

这一阶段的目标是：

- 不直接答题
- 只做 coarse routing

### 7.2 第二阶段：分支内 evidence retrieval

#### 文本路

- 根据 question 和 routing 结果
- 在 text blocks 中进一步检索相关 evidence

#### 图片路

- 根据 question 和 routing 结果
- 在 image units 中检索相关图片证据

#### 表格路

- 根据 question 和 routing 结果
- 在 table units 中检索相关表格
- 第一版先做“选表 + 取相关行”
- 后续增强版再考虑 SQL 生成与执行

## 8. 三路独立问答

这是当前方案与单纯 summary-routing 的关键区别。

三路检索拿到证据后，并不是直接结束，而是分别进行：

- `question + text evidence -> Text QA`
- `question + image evidence -> Image QA`
- `question + table evidence -> Table QA`

也就是说，每一路都要进行一次基于证据的大模型问答。

建议分别设计：

- `TextEvidenceAgent`
- `ImageEvidenceAgent`
- `TableEvidenceAgent`

它们都应输出统一结构，而不是只输出自由文本。

推荐输出格式：

```json
{
  "branch": "text",
  "answer": "...",
  "confidence": 0.82,
  "evidence": [
    {
      "id": "text_p7_b12",
      "page": 7
    }
  ],
  "reasoning_type": "text_lookup"
}
```

## 9. Merge 模块

当前阶段，导师建议：

- 先不做复杂裁决
- 先观察三路 evidence + 三路 QA 的效果

因此本阶段的最终模块定义为：

**Merge / Synthesis Module**

它的职责是：

- 输入三个 branch answer
- 做一个简单的最终整合
- 输出最终答案

注意：

- 当前 merge 不强调 conflict-aware adjudication
- 但接口设计要为后续 Judge 留扩展空间

换句话说：

**第一阶段先做简单 merge，但 branch 输出必须结构统一。**

## 10. 当前阶段研究假设

本研究当前阶段主要验证以下假设：

### H1

FetaTab 上大量错误不是“没有找到相关页”，而是“没有定位到正确的文本块、图片单元或表格单元”。

### H2

通过文档解析将页面拆解为 text / image / table 三类 evidence maps，比 page-level 表示更适合 FetaTab 这类结构化问题。

### H3

使用 `query + retrieved evidence` 进行三路独立问答，比直接基于页面内容或粗 summary 问答更稳定。

### H4

即使先不引入复杂 Judge，仅通过三路 evidence-based QA + 简单 merge，也有可能优于现有 page-level pipeline。

## 11. 实验设计

### 11.1 数据集

第一阶段重点使用：

- `FetaTab`

后续再考虑扩展到：

- `PaperTab`
- `PaperText`
- `MMLongBench`

### 11.2 对比方法

建议比较以下系统：

1. 师兄原始 DocQuest / DMAP 方法
2. Tri-Map：三类 evidence map + 三路检索 + 三路 QA + 简单 merge
3. Tri-Map 去掉 text 路
4. Tri-Map 去掉 image 路
5. Tri-Map 去掉 table 路

当前阶段不把 Judge 作为主实验项。

### 11.3 分类型评测

建议将 FetaTab 问题细分为：

- awards
- ranking / top-k
- count
- temporal span
- numerical / percentage
- location

除了整体准确率，还应统计：

- 各类型问题的准确率
- 表格类问题的提升幅度
- 图片类问题的提升幅度
- 三路中哪一路最常提供有效证据

### 11.4 消融实验

建议消融：

- 去掉 text summary
- 去掉 image summary
- 去掉 table summary
- page-level retrieval vs evidence-unit-level retrieval
- 不同文档解析方案（如 MinerU / 原始 page extraction）

## 12. 当前阶段预期创新点

如果实验成立，当前阶段可总结的创新点主要是：

### 创新点 1

提出一种 **Tri-Map evidence representation**，将长文档显式拆解为文本、图片、表格三类结构化证据空间。

### 创新点 2

提出一种 **summary-guided multi-branch retrieval**，先基于三类 summary 做 coarse routing，再在各分支内部检索更具体的 evidence。

### 创新点 3

提出一种 **branch-wise evidence-based QA**，每一路都基于 `query + retrieved evidence` 调用大模型独立问答，再做最终整合。

Judge / Verdict Agent 暂时不作为第一阶段主创新点，而作为后续增强方向保留。

## 13. 代码组织建议

### 13.1 是否应该新开目录？

建议：**在当前仓库里新增一套带前缀的新模块，而不是直接混进师兄原文件。**

原因：

1. 可以和原版代码一一对照
2. 边界清楚，便于理解
3. 对你后续学习和维护更友好

推荐方式：

- `agents/tri_map_*.py`
- `retrieval/tri_*.py`
- `mydatasets/tri_map_*.py`
- `scripts/tri_map_*.py`
- `config/tri_map_config.toml`

### 13.2 推荐目录结构

```text
mydatasets/
  tri_map_parser.py
  tri_map_evidence_builder.py
  tri_map_table_store.py

retrieval/
  tri_router.py
  tri_text_retrieval.py
  tri_image_retrieval.py
  tri_table_retrieval.py

agents/
  tri_text_agent.py
  tri_image_agent.py
  tri_table_agent.py
  tri_merge_agent.py
  tri_map_doc_quest.py

scripts/
  build_tri_map_evidence.py
  predict_tri_map.py

config/
  tri_map_config.toml
```

### 13.3 为什么这样适合你

因为你希望后续不仅能运行代码，还要真正看懂。  
所以实现时应坚持：

- 每个文件职责单一
- 输入输出清晰
- 模块名直白
- 新旧代码可对照

## 14. 适合你的开发原则

### 原则 1：先搭骨架，再填逻辑

不要一开始就追求复杂算法，先把模块接口和数据流跑通。

### 原则 2：先做主线，再做增强

当前优先级应是：

1. 文档解析
2. evidence builder
3. 三类 summary
4. 三路 retrieval
5. 三路 QA
6. 简单 merge

Judge 暂时放到后续。

### 原则 3：每个模块都能单独解释

后续实现时，应保证你对每个文件都能回答：

- 它是干什么的？
- 输入是什么？
- 输出是什么？
- 和原版代码的对应关系是什么？

## 15. 分阶段推进计划

### 第一阶段：MVP，2 周

目标：

- 只在 FetaTab 上跑通最小链路

任务：

1. 引入文档解析工具，得到文本块、图片区域、表格区域
2. 构建 text / image / table evidence units
3. 生成三类 summary
4. 实现三路 coarse retrieval
5. 实现三路 QA
6. 实现简单 merge

不做：

- Judge
- SQL 自动生成
- 跨数据集泛化

### 第二阶段：增强版，2~4 周

目标：

- 做强 table 路与分支内检索

任务：

1. 表格结构化存储
2. 行级检索
3. 表格 query plan
4. 更精细的图片证据抽取
5. 可选加入 operator-aware routing

### 第三阶段：扩展版，后续推进

目标：

- 进一步提升多分支整合能力

候选任务：

1. 引入 Judge / Verdict Agent
2. 做 conflict-aware adjudication
3. 做更完整的消融实验与论文表达

## 16. 当前最建议立即做的事

如果现在只做一个最合理的起步动作，我建议是：

### 第一步

先实现一个 `tri_map_parser + tri_map_evidence_builder`，只针对 FetaTab 的一小批文档，生成：

- 文本块
- 图片单元
- 表格单元

以及对应的：

- `text_summary.md`
- `image_summary.md`
- `table_summary.md`

### 第二步

定义统一的 branch 输出格式，让：

- text QA
- image QA
- table QA

都能以同样结构输出结果。

### 第三步

做一个最小的 `merge module`，先不强调裁决，只做简单整合。

### 第四步

优先在典型错例上验证：

- `Into the Woods`
- `First and Last and Always`
- `Renewable energy in Germany`
- `2018 Indianapolis 500`
- `List of surviving Avro Lancasters`

## 17. 结语

当前这项工作的核心，不在于简单换更强模型，而在于将原有的 page-level document map 进一步细化为：

- 文档解析驱动的
- modality-aware 的
- evidence-unit-level 的

三路结构化问答框架。

如果该方案验证有效，那么它将不仅是对师兄工作的工程增强，也可能形成你自己的方法贡献。
