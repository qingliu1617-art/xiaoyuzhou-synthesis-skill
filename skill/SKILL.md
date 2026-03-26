---
name: podcast-synthesis
description: >
  Synthesize multiple podcast/interview transcripts from the same industry into a
  structured, multi-perspective analysis report. Accepts two input types:
  (A) 小宇宙 episode URLs (the skill will transcribe audio first, then synthesize), or
  (B) pre-existing transcript files (.txt, .docx, .md).
  Trigger when the user provides 2 or more 小宇宙 links, transcript files, or a mix —
  and asks for analysis, synthesis, a report, or even just "help me understand this
  industry". Also trigger when the user mentions 小宇宙, podcast transcripts,
  interview transcripts, or says things like "I have a few podcast conversations" or
  "these are interviews with founders".
  The skill produces: (1) .txt verbatim transcripts per episode (if audio URLs were
  given), and (2) a .docx industry analysis report with charts, clearly labeled
  sources, and cross-interview tensions surfaced.
  Do NOT trigger for single-transcript summarization or general research without
  provided transcripts or URLs.
---

# 播客/访谈综合分析 Skill

## 核心理念

单一访谈容易形成片面视角。这个skill的价值在于：把同一行业中不同背景、不同立场的人说的话放在一起，找到他们的共识、分歧和盲点，生成一份比任何单篇访谈都更有深度的行业洞察。

The core value: cross-referencing multiple voices reveals tensions, blind spots, and non-obvious truths that no single interviewee can see alone.

---

## 两种输入模式

| 模式 | 输入 | 处理 |
|------|------|------|
| **A：音频链接** | 小宇宙节目 URL | Step 0 → 转录为 .txt → Step 1–6 合成报告 |
| **B：已有逐字稿** | .txt / .docx / .md 文件 | 直接进入 Step 1–6 |

两种模式可以混合使用（例如：2 个 URL + 1 个已有逐字稿文件）。

---

## Step 0: 转录（仅限音频链接输入）

**如果用户提供的是小宇宙节目链接**（URL 包含 xiaoyuzhou.fm），执行以下操作：

### 0.1 获取 API Key

在开始转录前，检查用户是否已提供千问 API Key：
- 如果用户已在对话中提供 → 直接使用
- 如果未提供 → 询问：「请提供您的千问 API Key（阿里云 DashScope），用于音频转录。」

### 0.2 运行转录脚本

使用 `scripts/transcribe.py` 处理每个 URL：

```bash
python scripts/transcribe.py \
  "https://www.xiaoyuzhou.fm/episode/xxx" \
  "https://www.xiaoyuzhou.fm/episode/yyy" \
  --api-key <QWEN_API_KEY> \
  --output-dir <用户工作目录>
```

脚本会自动：
1. 从小宇宙页面解析节目标题和音频下载地址（通过 `__NEXT_DATA__` JSON）
2. 下载 MP3 音频文件
3. 用 ffmpeg 将长于 25 分钟的音频切分为多段
4. 调用 `qwen-audio-turbo` API 逐段转录
5. 合并并保存为 `[节目标题].txt`，文件头包含来源 URL 和元数据

### 0.3 逐字稿作为交付物

每个 `.txt` 逐字稿文件都是**独立交付物**，需保存到用户工作目录并展示给用户，即使他们没有明确要求。格式：

```
# 逐字稿：[节目标题]
**播客**：[播客名称]
**发布日期**：[日期]
**来源**：[小宇宙 URL]
**转录模型**：qwen-audio-turbo
---
[逐字稿正文...]
```

### 0.4 错误处理

| 错误类型 | 处理方式 |
|----------|----------|
| 页面无法访问 / 结构变化 | 告知用户，跳过该 URL，继续处理其余 |
| API Key 无效 | 停止，提示用户检查 API Key |
| 音频下载超时 | 重试 1 次，失败则告知用户 |
| 转录 API 失败 | 自动重试 3 次（指数退避），最终失败则保留已转录部分并标注 |

---

## Step 1: 读取与提炼

**读取所有提供的逐字稿文件**，对每位受访者建立一张心智地图：

- 背景与立场（创业者/投资人/学者/从业者）
- 他们认为行业的核心问题是什么
- 他们自己押注的方向（如果有）
- 他们与其他受访者观点不同的地方

关键：带着"他们为什么这么说"的问题去读，而不只是"他们说了什么"。一个在硬件公司工作的人说"硬件被低估"和一个纯软件创业者说同样的话，含义完全不同。

---

## Step 2: 补充外部数据

在读完逐字稿后，**主动搜索以下类型的数据**来支撑或挑战访谈观点：

- 行业融资规模和趋势（近2年）
- 关键技术指标或市场数据
- 代表性公司的融资/估值情况
- 政策背景（如适用）
- 竞争格局（中国 vs 海外，如适用）

**来源标注规则（严格执行）**：
- 受访者原话或观点 → 标注 `（来源：[姓名/公司]，访谈）`
- 第三方数据 → 标注 `（来源：[媒体/机构名称]）`
- 你自己的分析推断 → 标注 `（研究推断）` 或在文中明确说"研究者判断"
- 绝不混淆这三类来源

---

## Step 3: 找到分析骨架

好的行业分析不是"每个人说了什么的摘要"，而是**围绕一个核心问题展开的论证**。在读完所有材料后，提炼出这个问题——它通常是受访者们都在隐隐回答、但没有人明说的那个问题。

例如：
- "这个行业离真正有用还差什么？"（障碍型）
- "谁会赢，为什么？"（竞争型）
- "这是泡沫还是拐点？"（估值型）
- "这里最大的非共识判断是什么？"（洞察型）

如果用户没有指定，**主动判断**哪个问题最能统摄这些访谈内容，并在报告开头说明你的选择。

---

## Step 4: 生成分析图表

在开始写报告前，用 matplotlib 生成以下图表（保存为 PNG，嵌入报告）：

**必须生成（如数据允许）：**
1. **行业融资趋势图**（柱状图 + 折线双轴）— 如果能找到融资数据
2. **技术/行业S曲线定位图**— 标注当前行业处于哪个阶段，以及类似行业的历史轨迹作为参照
3. **受访者观点对比图**— 策略矩阵（散点图）或雷达图，展示不同受访者在关键维度上的差异

**可选生成（根据内容决定）：**
4. 关键指标演进图（如模型性能、市场规模等有时间轴的数据）
5. 竞争格局对比图（如中美对比）

图表设计规范：
- 中文标签使用 `Droid Sans Fallback` 字体
- 配色方案：主色 `#1F4E79`（深蓝）、强调色 `#ED7D31`（橙）、对比色 `#C00000`（红）
- 每张图底部必须标注数据来源
- 图表描述性而非装饰性——每张图必须能独立传递一个核心观点

---

## Step 5: 撰写报告

使用 `python-docx` 生成 `.docx` 报告。参考 docx skill（如可用）获取具体的创建规范。

### 报告结构模板

```
封面
  标题（行业名称 + 核心问题）
  副标题（访谈来源说明）
  元数据表（研究时间、受访者列表、来源说明）

执行摘要（1页）
  3-5个核心发现，每条20-50字
  用表格呈现，颜色区分不同性质的发现

一、行业定位（用数据说话）
  1-2张图表定锚
  "行业在哪里"的客观描述

二、技术/行业曲线（结构性判断）
  当前阶段的判断 + 与历史类比
  S曲线图

三、核心挑战/关卡框架（报告主体）
  从访谈中归纳出2-4个核心障碍或驱动力
  每个障碍：定义 → 受访者怎么看 → 关键引语 → 不同观点的碰撞

四、受访者的不同押注
  不是"每个人的背景介绍"，而是"他们在哪里押注了不同的赌注"
  策略矩阵图

五、竞争格局/外部视角
  行业的地理/机构分布
  如果有中美对比，必须客观呈现两侧

六、战略启示（如用户指定）
  针对特定公司/角色的具体建议
  每条建议标注来自哪个访谈的逻辑

结语：观测信号
  3-5个可追踪的具体信号（必须来自访谈推断或有来源的数据，不能凭空捏造）
  明确标注哪些是访谈推断，哪些有外部来源

附录：数据来源说明
```

### 引语框（Pull Quote）的使用

每个主要论点用一个引语框（带左边框的灰色区块）来锚定，格式：
> 引号内的原话（必须是受访者说的，不能改写）
> — 姓名，职位（访谈）

**不要在引语框里放你的推断或合成内容**。

### 关于"观测信号"的诚实性原则

结语中的观测信号必须满足以下条件之一：
- 直接来自访谈中受访者提到的门槛或判断标准
- 来自有来源的第三方数据
- 如果是研究推断，**明确标注"研究推断"**，并说明推断依据

不要为了让结语看起来"更完整"而编造没有依据的具体数字。

---

## Step 6: 质量检查清单

在保存文件前检查：

- [ ] 所有引语都来自实际的逐字稿，没有改写或合成
- [ ] 每个数据点都有来源标注
- [ ] 访谈观点、第三方数据、研究推断三类来源清晰区分
- [ ] 报告围绕一个核心问题展开，而非简单摘要
- [ ] 受访者之间的分歧和张力被明确呈现，而非被平均化
- [ ] 图表每张都有标题和数据来源标注
- [ ] "观测信号"部分没有无依据的具体数字

---

## 输出规范

- 格式：`.docx` 文件，保存到用户工作目录
- 文件名：`[行业名称]行业深度研究报告.docx`
- 图表：先生成为 PNG，再嵌入 docx
- 长度参考：执行摘要1页，主体每章节1-3页，总计10-20页
- 语言：跟随用户提供的逐字稿语言（中文逐字稿→中文报告）
