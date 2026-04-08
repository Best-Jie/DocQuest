# FetaTab 错误案例分析摘要版

## 1. 结论先行

基于 [2025-08-21-18-16_results.json](/new-data/new-ywj/DocQuest/results/FetaTab/ftb_gpt/2025-08-21-18-16_results.json) 的整体统计与 [师兄问答错误案例分析.pdf](/new-data/new-ywj/DocQuest/师兄问答错误案例分析.pdf) 的手工复盘，FetaTab 的核心问题不是“模型完全看不懂文档”，而是：

1. 找到相关页之后，无法稳定定位到**正确的表格行 / 列表项 / 时间片段**。
2. 多个 agent 往往给出不同但部分相关的答案，最终**汇总阶段不会裁决冲突**。
3. 对于 FetaTab 这类强结构化问题，当前方法仍然主要停留在 **page-level QA**，而没有升级到 **evidence-unit-level QA**。

整体结果：

- 总样本数：`997`
- 正确数：`723`
- 错误数：`274`
- 准确率：`72.5%`

一个关键统计信号是：

- 在 `274` 条错误样本中，有 `257` 条样本里 `general / text / image` 三个 agent 给出了三个不同答案。

这说明当前系统最主要的问题不是“所有模块一起失败”，而是：

> 证据冲突很多，但最终没有做可靠的结构化裁决。

## 2. 问题的几大类

### 2.1 类别一：页找到了，但表格行选错

这是最常见的一类错误。

表现：

- location 已经落到相关页
- 但模型没有进一步缩小到正确的表格行或记录
- 最终答案“看起来相关”，但不是问题真正要的那一行

例子：

- `Into the Woods`

问题：

> What awards was into the woods nominated for and which ones did it win?

标注答案只需要 2011 年 `Laurence Olivier Award` 中的两条信息：

- `Best Musical Revival`：Won
- `Best Performance in a Supporting Role in a Musical (Michael Xavier)`：Nominated

但模型把整个 awards section 全总结了一遍，输出了大量 Tony / Drama Desk / Olivier 奖项，答案范围远大于问题范围。

说明：

> 这类错误的关键不是页没找对，而是页内没有做细粒度结构对齐。

---

### 2.2 类别二：筛选条件 / Top-k / 限定词没有对齐

表现：

- 模型读到了候选列表
- 但没有严格执行问题中的筛选条件
- 结果常常是“给了很多相关信息”，但不满足问题要求

例子：

- `largest islands`

问题：

> What are the largest islands?

标注答案：

- Java
- Honshu
- Great Britain

但模型沿着表格继续输出了更长的岛屿列表，甚至直接把人口信息一起展开，未正确执行“largest”对应的排序与截断。

说明：

> 这类错误本质上不是阅读失败，而是问题中的“操作符”没有被形式化执行。

---

### 2.3 类别三：时间区间 / 任期 / 多段信息拼接失败

表现：

- 能抓到人物和某一段时间
- 但漏掉第二段任期，或把前后关系拼错
- 对“谁接替谁”“任期从何时到何时”这类时间线结构不稳定

例子：

- `Cleopa Msuya`

问题：

> During which dates was Cleopa Msuya a Prime Minister of Tanzania?

标注答案包含两段任期：

- 1980-11-07 到 1983-02-24
- 1994-12-07 到 1995-11-28

模型只回答了第一段任期，遗漏了第二段。

说明：

> 当前系统对 timeline/table 中的多段记录缺少显式拼接能力。

---

### 2.4 类别四：数值口径混淆

表现：

- 模型拿到了正确数字
- 但计算或表达的统计口径错了
- 常见混淆包括：
  - share vs generation
  - 相对增幅 vs 百分点差
  - 总数 vs 满足条件的子集

例子：

- `Renewable energy in Germany`

问题：

> In terms of gross electricity consumption, what was the percentage rise of renewable electricity usage between 1990 and 2017?

标注答案实际是：

- 从 `3.4%` 上升到 `36.2%`

模型却分别给出了：

- 相对增幅
- 百分点差
- 基于发电量的增长率

说明：

> 这类问题的根因不是算术能力不够，而是没有先识别“要比较的到底是哪一个统计对象”。

---

### 2.5 类别五：多 agent 冲突后汇总失败

表现：

- 三个 agent 中可能已经有人答对
- 但最终答案没有跟随正确分支
- 汇总器更像是在写一个“看起来合理”的总结，而不是在做证据裁决

例子：

- `First and Last and Always`

问题：

> Which two tracks did Eldritch write on the album "No time to cry"?

标注答案：

- `Blood Money`
- `Bury Me Deep`

这一题中：

- `image agent` 给出了正确答案
- `general agent` 错答成 `No Time to Cry` 和 `Walk Away`
- 最终答案却跟着错的分支走了

说明：

> 这类错误非常关键，因为它说明系统里已经出现了正确信息，但最终决策机制没有把它保留下来。

## 3. 对当前方法的核心判断

如果把当前方法拆成：

`location -> retrieval -> single-agent QA -> sum -> reflect`

那么 FetaTab 上最明显的薄弱点有三个：

### 3.1 `location` 太粗

当前大多数问题只定位到 `Page`，但 FetaTab 真正需要的是：

- `Table`
- `Row`
- `Cell`
- `List item`
- `Timeline span`

### 3.2 页内证据单元选择缺失

系统现在主要是把整页扔给 agent，再让 agent 自己从整页里“找答案”。  
对自由文本还可以，对表格 / 排名表 / 任期表 / 奖项表明显不够。

### 3.3 汇总器不是裁决器

从错例分布看，当前 `SumAgent` 更像一个自然语言摘要器，而不是：

- 判断哪个 agent 证据最强
- 判断哪个答案满足题目约束
- 在冲突中做结构化决策

## 4. 从这些错误中能挖出的创新点

下面几个方向，是最适合从 FetaTab 错例中直接长出来的创新点。

### 4.1 创新点一：从页级 QA 升级到证据单元级 QA

核心思想：

- 不再只做 `page-level retrieval`
- 而是做 `evidence-unit retrieval`

结构可以细化为：

- `Page -> Table -> Row -> Cell`
- `Page -> List -> Item`
- `Page -> Timeline -> Span`

为什么值得做：

- 当前大量错例不是页错，而是页内选错
- 这说明 page-level 方法已经不够细

一句话概括：

> 把 DMAP 从“页结构地图”推进为“证据单元地图”。

---

### 4.2 创新点二：操作符感知的结构化问答

核心思想：

- 先识别问题类型，再决定如何选证据和组织答案

可重点识别的 operator：

- top-k
- count
- compare
- time span
- won vs nominated
- percentage / total / average

为什么值得做：

- 当前很多错例并不是内容看错，而是“问题限制条件没执行”

一句话概括：

> 让系统先理解“要做什么操作”，再理解“答案是什么”。

---

### 4.3 创新点三：冲突感知的多 agent 汇总

核心思想：

- 把 agent disagreement 当成不确定性信号
- 不是简单总结三份答案，而是做证据裁决

可以引入的机制：

- 证据支持度打分
- 槽位级投票
- disagreement-triggered re-check
- page/table/row 级证据回溯

为什么值得做：

- 当前绝大多数错例里三个 agent 是互相冲突的
- 说明“冲突处理”本身就是系统瓶颈

一句话概括：

> 多 agent 不应该只是“多说几遍”，而应该是“多证据竞争后再裁决”。

## 5. 汇报时可以直接强调的 takeaways

如果这份摘要用于组会或汇报，建议重点强调下面 4 句：

1. 当前 FetaTab 的主要问题不是找不到相关页，而是找到了页之后，无法定位到正确的结构化证据单元。
2. 当前大量错例不是所有 agent 一起失败，而是多个 agent 给出不同答案，但最终没有可靠地裁决冲突。
3. FetaTab 的错误高度集中在表格问答、排名筛选、时间区间拼接和数值口径对齐，这些都属于结构化推理问题。
4. 最值得做的创新，不是简单换更强模型，而是把系统从 page-level QA 推进到 evidence-unit-level、operator-aware、conflict-aware 的结构化 QA。



