# FetaTab 错误案例分析报告

## 1. 背景与目标

最近针对 DocQuest 在 FetaTab 数据集上的问答错误案例进行了持续复盘。本报告的目标有三点：

1. 基于实验结果文件，对 FetaTab 的整体错误分布进行系统归纳。
2. 结合手工记录的错误案例，分析当前方法在问答链路中的薄弱环节。
3. 从错误模式中提炼可落地的改进方向，并进一步挖掘可能的创新点。

本报告关注的结果文件为：

- [2025-08-21-18-16_results.json](/new-data/new-ywj/DocQuest/results/FetaTab/ftb_gpt/2025-08-21-18-16_results.json)

参考的手工记录文件为：

- [师兄问答错误案例分析.pdf](/new-data/new-ywj/DocQuest/师兄问答错误案例分析.pdf)

## 2. 数据来源与说明

本报告综合使用了两类证据来源：

### 2.1 结果文件统计

直接对 [2025-08-21-18-16_results.json](/new-data/new-ywj/DocQuest/results/FetaTab/ftb_gpt/2025-08-21-18-16_results.json) 进行整体统计，提取如下字段进行分析：

- `question`
- `answer`
- `ans_ftb_gpt`
- `binary_correctness`
- `location`
- `r_general`
- `r_text`
- `r_image`

### 2.2 手工记录 PDF

由于 [师兄问答错误案例分析.pdf](/new-data/new-ywj/DocQuest/师兄问答错误案例分析.pdf) 是 Chromium 导出的图像型 PDF，本地无法直接稳定抽取文本，因此采用了嵌入图像提取与 OCR 的方式恢复部分内容。OCR 恢复到的关键信息包括：

- 总体结果表：FetaTab 准确率约 `0.725`
- 消融结果趋势：Full 模型优于各删减版本
- 多个结构化错例截图，例如：
  - `Smallville` 季度收视表
  - `Billy Elliot` 奖项表
  - `Cleopa Msuya` 任期表
  - `Punjab Chief Ministers` 时间线表
  - `Category 4 hurricanes` 统计表
  - `largest islands` 排名表

说明：PDF OCR 适合恢复“趋势”和“典型案例类型”，但不适合用来严格逐字引用所有内容。因此报告中的精确统计以结果 JSON 为准，PDF 作为补充印证。

## 3. 整体结果概览

对 FetaTab 结果文件的整体统计如下：

| 指标 | 数值 |
| --- | ---: |
| 总样本数 | 997 |
| 正确样本数 | 723 |
| 错误样本数 | 274 |
| 整体准确率 | 0.7252 |

这与手工记录 PDF 中恢复出的 `FetaTab = 0.725` 一致，说明当前分析对象与手工复盘记录对应的是同一批实验结果。

### 3.1 一个关键现象：错误并非随机

FetaTab 的错误并不是“模型偶发答错”，而是高度集中在结构化问答场景，尤其是：

- 表格问答
- 排名与 Top-k 选择
- 时间区间与任期拼接
- 奖项类多字段抽取
- 数值口径与统计对象对齐

这意味着当前方法的瓶颈，更多在于**结构化证据定位与裁决**，而不是一般性的语言理解能力不足。

## 4. 从结果文件得到的系统性统计

### 4.1 错例中的 agent 冲突非常高

在 `274` 条错误样本中：

- `257` 条样本中，`general / text / image` 三个 agent 给出了三种不同答案
- `17` 条样本中，至少有两个 agent 给出相同答案
- `35` 条错误样本中，至少有一个 agent 输出 `not answerable`

这表明当前系统最主要的问题不是“所有 agent 一起失败”，而是：

> 三个 agent 往往各自抓住了不同线索，但最终汇总阶段没有可靠地处理冲突。

### 4.2 最终答案存在明显的 text 分支偏置

通过对 `ans_ftb_gpt` 与 `r_general / r_text / r_image` 的相似度进行粗略对齐，可以观察到：

| 结果集合 | final 更接近 text | final 更接近 image | final 更接近 general |
| --- | ---: | ---: | ---: |
| 全部样本 | 643 | 278 | 76 |
| 错误样本 | 159 | 77 | 38 |

这说明最终答案整体上更倾向跟随 `text agent`，即使在 FetaTab 这种高度结构化、表格/图像占比较高的数据集中也是如此。这种偏置会导致：

- 当图像分支已经抓到正确表格信息时，最终仍可能被文本分支覆盖
- 当文本分支把整页文字摘要成“看起来合理但不精确”的答案时，汇总器容易误选

### 4.3 错例中的 location 主要停留在 Page 级

对错误样本的 `location` 统计：

| 位置类型 | 数量 |
| --- | ---: |
| 仅 `Page` | 249 |
| `Table + Page` | 11 |
| `Figure + Page` | 1 |
| 无显式位置 | 13 |

这和 FetaTab 的任务特点并不匹配。FetaTab 很多问题真正需要的是：

- 表格中的某一行
- 列表中的某几项
- 时间线中的某两个时间段
- 奖项表中的“年份 + 类别 + 结果”三元组

而不是仅仅知道“答案大致在第几页”。

### 4.4 问题类型上的粗粒度错误率

基于问题表面模式做粗分类后，得到如下趋势：

| 问题类型 | 样本数 | 错误数 | 粗略错误率 |
| --- | ---: | ---: | ---: |
| `location` 类 | 18 | 7 | 0.3889 |
| `counting` 类 | 88 | 32 | 0.3636 |
| `numeric / calculation` 类 | 78 | 23 | 0.2949 |
| `enumeration / list` 类 | 245 | 64 | 0.2612 |
| `time` 类 | 85 | 22 | 0.2588 |

这说明当前系统在 FetaTab 上的困难点主要不是开放式问答，而是：

- 定位类问题
- 数值类问题
- 计数类问题
- 需要严格满足筛选条件的列表类问题

## 5. 典型错误类型归纳

结合结果文件与手工记录，可以将错误大致归纳为五类。

### 5.1 页找到了，但表格行选错

这是最常见的一类错误。

现象：

- 系统能够定位到相关页
- 但无法在页内进一步定位到正确的表格行、列表项或字段组合
- 最终答案通常“看起来相关”，但不是问题实际需要的那一行

典型案例：

- `Into the Woods`
- `Billy Elliot`
- `Nadiya Hussain`

本质问题：

> 当前系统大多只做到 page-level grounding，没有做到 row-level / item-level grounding。

### 5.2 排名 / Top-k / 限定条件未对齐

现象：

- 模型能读到列表内容
- 但没有严格执行问题中的筛选条件
- 常见表现包括：
  - 需要前 2 个，却答成整个列表
  - 需要“美国 hard rock”，答成全球 hard rock
  - 需要 largest islands，却沿着另一个人口表读下去

典型案例：

- `largest islands`
- `longest-running prime-time American television series`
- `best-selling United States hard rock artist`

本质问题：

> 模型识别到了候选实体，但没有把问题中的操作符转化为严格的筛选逻辑。

### 5.3 时间区间与任期拼接失败

现象：

- 只回答一个时间段，漏掉另一个时间段
- 人物和时间对应关系部分正确，但跨段拼接错误
- 对“接替者”“前任”“后任”这类时间线关系理解不稳

典型案例：

- `Cleopa Msuya`
- `Punjab Chief Ministers`
- 各类 Prime Minister / Chief Minister 任期问题

本质问题：

> 系统缺少针对时间线表格的结构化抽取能力，尤其缺少“多段任期合并”和“时序关系约束”。

### 5.4 数值口径混淆

现象：

- 能抽到正确数字，但计算对象错了
- 混淆“占比变化”“百分点变化”“绝对增长”“相对增长率”
- 把 generation 当成 share，把 count 当成 rate

典型案例：

- `Renewable energy in Germany`
- hurricane 统计类问题
- 各类 speed / percentage / average 类问题

本质问题：

> 问题中的统计口径没有被形式化建模，导致模型在多个合理但不同的数值定义之间随意切换。

### 5.5 多 agent 冲突后汇总失败

现象：

- `general`、`text`、`image` 三个分支往往分别抓到了不同证据
- 最终答案没有选择“证据最一致的那一个”
- 而是生成了一个自然语言上看似顺滑、但事实上错误的融合答案

典型案例：

- `First and Last and Always`
- `List of surviving Avro Lancasters`
- `2018 Indianapolis 500`

本质问题：

> 当前 `SumAgent` 更像一个摘要器，而不是证据裁决器。

## 6. 代表案例分析

以下选取几类最有代表性的案例，说明错误是如何在当前管线中产生的。

### 6.1 案例一：`First and Last and Always`

问题：

> Which two tracks did Eldritch write on the album "No time to cry"?

标注答案：

> Blood Money 和 Bury Me Deep

错误现象：

- `image agent` 实际给出了正确答案
- `general agent` 误答为 `No Time to Cry` 和 `Walk Away`
- 最终答案跟随了错误的 `general` 分支

根因分析：

- Page 5 包含与 Eldritch、Walk Away、No Time to Cry 相关的叙述，容易误导 general 分支
- 真正的证据在 Page 7/8 的 track listing / bonus track 表里
- 汇总器没有识别“image 分支才是唯一与表格证据一致的答案”

说明：

> 这是典型的“正确证据已经出现，但汇总阶段仍然选错”的案例。

### 6.2 案例二：`Renewable energy in Germany`

问题：

> In terms of gross electricity consumption, what was the percentage rise of renewable electricity usage between 1990 and 2017?

标注答案：

> 从 1990 年的 3.4% 上升到 2017 年的 36.2%

错误现象：

- `general agent` 算出相对增幅
- `text agent` 给出百分点差
- `image agent` 又把 generation 的增长率算了出来
- 最终答案选了最偏离标注风格的一个

根因分析：

- 问题要求的是“按 gross electricity consumption 口径的 share 变化”
- 系统没有先统一“要回答的是哪一种统计口径”
- 多分支各按自己的理解进行了不同的数值推理

说明：

> 这类问题的核心不是算术能力，而是统计口径识别与答案规范化。

### 6.3 案例三：`Into the Woods`

问题：

> What awards was into the woods nominated for and which ones did it win?

标注答案聚焦于：

- `Best Musical Revival`：Won
- `Best Performance in a Supporting Role in a Musical (Michael Xavier)`：Nominated

错误现象：

- 模型把整个 awards section 的多个年份、多个奖项全部泛化总结
- 最终生成“赢了很多 Tony / Drama Desk / Olivier”的大段概括
- 答案范围大于问题范围

根因分析：

- location 已经命中了 awards 区域，说明“页级定位”基本没有问题
- 真正失败的是页内结构对齐，没有收缩到 2011 Laurence Olivier Award 对应的那几行

说明：

> 这是典型的“页对了，但证据单元没选对”。

### 6.4 案例四：`2018 Indianapolis 500`

问题：

> What driver had the fastest speed at the 2018 Indianapolis 500, what was that speed, and who were the two drivers behind that speed?

标注答案：

> Tony Kanaan，226.680 mph，后面是 Ed Carpenter 和 Gabby Chaves

错误现象：

- 最终答案答成了 `Will Power, 228.194 mph`
- 中间分支混入了：
  - 正赛结果页
  - Fast Nine qualifying 页
  - practice speed 页

根因分析：

- 该文档中存在多张“速度榜”表格
- 问题真正需要的是 practice page
- location 却偏向了 race / qualifying 区域
- 反思阶段又依赖 location 扩页，因此错误会持续放大

说明：

> 这是典型的“相似表格类型混淆 + 上游 location 出错引发级联失败”。

### 6.5 案例五：`List of surviving Avro Lancasters`

问题：

> Where are the surviving, airworthy Avro Lancasters located?

标注答案：

> Canadian Warplane Heritage Museum 和 RAF Coningsby

错误现象：

- 模型抓到了 `PA474 @ RAF Coningsby`
- 也提到了 `FM213`
- 但没有准确落出 `Canadian Warplane Heritage Museum`
- 还误把 `NX611` 这种“under restoration to airworthiness”的飞机带入最终答案

根因分析：

- 正确证据分散在两页表格中
- 模型没有稳定地区分 `Airworthy` 和 `Under restoration to airworthiness`
- 汇总器没有过滤冲突状态

说明：

> 这是典型的“状态列语义混淆 + 多页表格证据整合失败”。

## 7. 从管线角度看薄弱环节

将当前方法抽象为：

`location -> retrieval -> single-agent understanding -> sum -> reflect`

则薄弱点可以分为四层。

### 7.1 `location` 仍然太粗

目前在大多数错例中，`location` 只精确到 `Page`。但对于 FetaTab，这通常不够，因为真正的答案常常位于：

- 表格的一行
- 某列中满足条件的若干项
- 某个时间区段
- 某个奖项记录

也就是说，FetaTab 需要的不是 page-level retrieval，而更接近 evidence-unit retrieval。

### 7.2 页内结构化证据选择缺失

这是当前最重要的瓶颈。

当前系统常见做法是：

- 把整页文本喂给 `text agent`
- 把整页图像喂给 `image agent`
- 再让 agent 自己从整页中“找答案”

这对于自然段叙述尚可，但对表格、列表、奖项表、时间线表明显不够。

### 7.3 `SumAgent` 缺少冲突裁决能力

从统计上看，大多数错例中的三个 agent 并不是没有信息，而是信息不一致。当前 `SumAgent` 的问题在于：

- 它更像自由摘要器
- 缺少对“哪个 agent 的证据更精确”的判断
- 没有要求输出可检查的证据对齐过程

### 7.4 `ReflectAgent` 只检查“是否回答”，不检查“是否答对”

这意味着当前反思模块只能修复：

- 空答
- 明显不完整的回答

却无法修复：

- 行选错
- 年份拼接错
- 口径错
- won / nominated 混淆

## 8. 可落地的改进方向

下面的改进方向都可以直接从当前错例集出发验证。

### 8.1 从页级检索升级为证据单元检索

建议将结构化检索粒度从 `Page` 进一步细化到：

- `Page -> Table -> Row -> Cell`
- `Page -> List -> Item`
- `Page -> Timeline -> Span`

最直接的收益：

- 奖项问题不再依赖整页摘要
- 任期问题可以按区间对齐
- 排名问题可以按行过滤，而不是从整页生成

### 8.2 增加问题操作符识别器

很多错例的根因不是“没看懂内容”，而是“没识别清楚问题对答案的操作约束”。建议为问题增加一个轻量级 operator 分类器，例如：

- `lookup`
- `filter + lookup`
- `top-k`
- `count`
- `compare`
- `temporal span`
- `arithmetic`
- `won vs nominated`

这样后续的证据抽取与答案生成就能采用不同模板，而不是全部交给自由生成。

### 8.3 把最终汇总改为结构化裁决

建议 `SumAgent` 不再直接输出自由文本，而是先输出结构化中间表示，例如：

```json
{
  "answer_slots": {},
  "supporting_evidence_units": [],
  "preferred_agent": "",
  "rejected_candidates": []
}
```

这样可以强制汇总阶段回答几个关键问题：

- 这个答案来自哪个 agent？
- 对应的是哪一页、哪一行、哪一个 evidence unit？
- 为什么另一个 agent 的答案被否决？

### 8.4 把 reflect 改成证据一致性检查

建议将 reflect 从“回答完整性检查”升级为“证据一致性检查”：

- 每个关键槽位是否都能在证据中找到？
- 问题问的是 count 还是 list？
- 问的是 won，还是 nominated？
- 是否存在第二段时间区间被漏掉？
- 是否把 generation 和 share 混用了？

这一阶段完全可以采用“规则 + 模型”混合方式，而不是纯生成式判断。

## 9. 值得深入做成创新点的方向

如果要从错例分析进一步推进到论文级创新，我认为以下三个方向最有潜力。

### 9.1 Error-Driven Evidence Unit Alignment

核心思想：

- 不再停留在 page-level structural map
- 将 DMAP 扩展到 evidence-unit level structural map

为什么值得做：

- 当前大量错例不是页错，而是页内证据单元选错
- 这正好说明 page-level RAG 已经触达上限

可以形成的创新点：

- 面向表格、列表、时间线的细粒度结构对齐
- 让“human-aligned”不仅体现在页结构，也体现在人类阅读时真正依赖的证据粒度

### 9.2 Conflict-Aware Multi-Agent Aggregation

核心思想：

- 把 agent disagreement 当作不确定性信号，而不是把冲突答案直接摘要融合

为什么值得做：

- 错例里大多数样本都存在 agent 间强冲突
- 当前汇总阶段恰恰缺少冲突消解能力

可以形成的创新点：

- disagreement-aware routing
- disagreement-triggered re-retrieval
- disagreement-triggered evidence verification

### 9.3 Operator-Aware Table QA in Long Documents

核心思想：

- 不先让模型直接回答问题，而是先识别问题要执行的结构化操作

为什么值得做：

- 当前高频错例集中在：
  - top-k
  - count
  - compare
  - time span
  - won vs nominated
  - percentage / share / total 口径区分

可以形成的创新点：

- 操作符感知的结构化证据选择
- 面向长文档表格问答的答案规范化

## 10. 建议的实验路线

为了把“分析结论”转化成“可验证的研究工作”，建议按如下顺序推进。

### 第一阶段：构建错例标签集

从当前 `274` 条错例中先挑出 `80~100` 条做半自动标注。每条至少标记：

- `error_type`
- `operator_type`
- `evidence_granularity_needed`
- `failure_stage`

### 第二阶段：验证两个关键假设

建议重点验证：

1. 大多数 FetaTab 错例属于“页内证据单元选择失败”，而不是“页找错”
2. 大多数 FetaTab 错例属于“多 agent 冲突未被正确裁决”，而不是“所有 agent 都没抓到证据”

如果这两个假设成立，那么后续创新方向就会非常清晰。

### 第三阶段：做最小改动版 baseline

在不重写整个系统的前提下，优先做两个模块：

- operator classifier
- structured final resolver

如果只做这两个模块就能把 FetaTab 从 `0.725` 拉高，那么就已经说明：

> 当前瓶颈主要不在 backbone 模型本身，而在问答控制逻辑。

### 第四阶段：推进到细粒度结构映射

在 baseline 有效果后，再继续扩展：

- page-level -> table/list/timeline unit-level
- free-form aggregation -> conflict-aware evidence adjudication

## 11. 结论

综合手工记录与结果文件的分析，可以得出三个核心判断：

1. FetaTab 的主要错误不是“看不懂文档”，而是“没有对齐到正确的结构化证据单元”。
2. 当前系统的大量错例并不是 retrieval 全面失败，而是多个 agent 给出了不同但部分相关的答案，最终汇总没有正确裁决。
3. 从研究角度看，最值得深入的方向不是简单替换更强模型，而是围绕以下三个关键词展开：
   - 细粒度结构映射
   - 操作符感知问答
   - 冲突感知汇总

一句话概括：

> 当前 DocQuest 在 FetaTab 上最有价值的突破口，不是更强的生成模型，而是把“页级多模态问答”推进为“证据单元级、操作符感知、可裁决的结构化问答”。

## 附录 A：本次分析中重点参考的错误案例

以下案例在本次报告中被重点用于归纳错误类型：

- `List of surviving Avro Lancasters`
- `First and Last and Always`
- `Renewable energy in Germany`
- `Into the Woods`
- `2018 Indianapolis 500`
- `Smallville`
- `Billy Elliot`
- `Cleopa Msuya`
- `Punjab Chief Ministers`
- `largest islands`

## 附录 B：与手工记录 PDF 的对应关系

从 OCR 恢复出的 PDF 内容中，能够确认以下信息与本报告一致：

- FetaTab 总体准确率约为 `0.725`
- Full 配置优于删减配置
- 典型错例集中在：
  - 排名表
  - 奖项表
  - 时间线表
  - 统计频率表
  - 人口/岛屿等列表表

这进一步说明，本报告中提出的“结构化证据单元选择失败”并不是事后推断，而是与你已有的手工复盘结论基本一致。
