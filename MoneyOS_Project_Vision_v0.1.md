# MoneyOS 项目立项与产品愿景报告

> **项目代号：MoneyOS**  
> **项目定位：Open-source Personal Finance AI Stack / Personal Finance Intelligence Platform**  
> **文档版本：v0.1**  
> **调研基准日期：2026-08-10**  
> **状态：立项阶段 / 供后续 ChatGPT 项目与开发工作持续使用**

---

## 0. 文档目的

本文档用于统一 MoneyOS 的长期愿景、产品定位、技术原则、行业判断与阶段性开发路线。

它不是一份固定不变的 PRD，也不是当前版本的详细技术实现文档。MoneyOS 明确采用 **递进式演化**：

- 第一版优先解决“能稳定、方便地记账和查询”；
- 后续逐步加入本地 AI、自由分析、长期记忆、多端交互、家庭服务器部署等能力；
- 当前实现可以简单，但底层边界必须允许未来替换模型、升级算力、更换消息渠道、扩展账本和分析能力；
- 不为了“未来可能用到”而提前堆砌复杂工程，但不做会锁死未来架构的短期设计。

本文档应作为后续所有开发讨论中的最高层上下文之一。具体 Schema、API、模块拆分和版本计划可在后续独立文档中细化。

---

# 1. 项目背景

传统个人财务管理工具主要存在以下问题：

1. **录入摩擦大**  
   用户需要打开 App、选择分类、填写金额、选择账户、补充备注。长期坚持记账本身就成为负担。

2. **交互形式仍然是传统软件逻辑**  
   用户需要学习软件预先规定好的菜单、报表、分类和筛选方式，而不是直接表达自己真正想知道的问题。

3. **分析维度被固定 Schema 和 Dashboard 限制**  
   传统系统擅长回答：
   - 本月餐饮支出多少？
   - 交通占比多少？
   - 某账户余额多少？

   但很难自然回答：
   - 今年我和女朋友吃饭花了多少钱？
   - 我花在女朋友身上的各种开销比例是什么？
   - 开始科研以后，我的消费结构发生了什么变化？
   - 去掉旅游和购买设备这些偶发事件后，我真正的日常生活成本是多少？
   - 哪些购买后来被我认为“真的值得”？
   - 大学四年的财务变化反映了怎样的生活轨迹？

4. **AI 往往只是外挂功能**  
   现有项目越来越多地加入 LLM 分类、聊天、MCP 或 Agent，但很多仍属于“传统财务软件 + AI 功能”，而不是从 AI 作为主要交互与分析入口的角度重新思考个人财务管理。

5. **AI 部署条件差异巨大**  
   不同用户可能只有 CPU、普通笔记本、小显卡、云 API，也可能拥有家庭服务器和大显存 GPU。很多 AI 产品将某一种部署方式写死，导致用户必须适应系统，而不是系统适应用户。

MoneyOS 希望解决的不是单一“记账”问题，而是：

> **如何让任何算力条件下的用户，都能拥有一个真正理解自己财务生活的 AI。**

---

# 2. 一句话愿景

> **MoneyOS 是一个随着用户的算力、模型和人生共同成长的 AI 原生个人财务系统。**

英文候选表达：

> **MoneyOS is an AI-native personal finance system that scales with your hardware, your models, and your life.**

另一组适合作为项目主页的表达：

> **Your finances. Your data. Your AI. Any hardware.**

以及两个长期不应轻易改变的产品/工程原则：

> **The ledger remembers what happened. The AI understands what it means.**

> **Freedom to analyze. Discipline to act.**

中文：

> **账本记录事实，AI 理解意义。**

> **自由分析，严格执行。**

---

# 3. MoneyOS 不是什么

MoneyOS **不是**：

- 另一个套壳 ChatGPT 的记账 App；
- “传统记账软件 + AI 聊天框”；
- 依赖特定模型的应用；
- 必须拥有 GPU 才能使用的产品；
- 必须连接云端 AI 才能工作的产品；
- 把所有财务数据塞进向量数据库然后用 RAG 搜索的系统；
- 允许 Agent 任意执行 SQL、修改数据库、运行 Shell 的高权限自动化脚本；
- 为了“智能”而牺牲账本准确性和可审计性的系统；
- 只会告诉用户“少喝奶茶、少旅游、少消费”的节俭教练。

MoneyOS 的核心判断是：

> **AI 不应该成为账本事实本身。AI 应该成为理解、规划、分析和交互层。**

---

# 4. 项目最终定位

MoneyOS 的长期定位不是单纯的 **Personal Finance App**，更接近：

## 4.1 Open-source Personal Finance AI Stack

为个人财务 AI 提供一套完整、可组合的开源技术栈。

## 4.2 Personal Finance Intelligence Platform

在账本和模型之间建立一层长期稳定的“个人财务智能层”。

理想终局：

```text
                   User
                    │
       ┌────────────┼────────────┐
       │            │            │
     Mobile       Web/CLI      Chat Channels
       │            │            │
       └──────── Channel Layer ───┘
                    │
                    ▼
               MoneyOS Brain
                    │
     ┌──────────────┼──────────────┐
     │              │              │
  Memory        Reasoning       Planner
     │              │              │
     └──────────────┼──────────────┘
                    │
             Tool / Skill Layer
                    │
      ┌─────────────┼─────────────┐
      ▼             ▼             ▼
   Ledger       Analytics       Reports
      │             │             │
严格写入 API    SQL / Python    MD / Charts
      │             │
      ▼             ▼
 Financial      Read-only
   Truth         Sandbox
```

模型位于可插拔 Provider 层：

```text
OpenAI / Anthropic / Gemini
Qwen / Llama / DeepSeek
Ollama / vLLM / LM Studio
任意 OpenAI-compatible endpoint
未来本地模型
           │
           ▼
      LLM Provider
           │
        MoneyOS
```

账本也可以逐步抽象为：

```text
            MoneyOS Brain
                 │
       Financial Semantic Layer
                 │
       ┌─────────┼─────────┐
       ▼         ▼         ▼
 MoneyOS     Actual     Firefly III
  Ledger     Budget
```

第一阶段不必实现所有 Adapter，但从架构上不应把 MoneyOS 永久绑定到唯一账本实现。

---

# 5. 行业与开源项目现状

> 以下为 2026-08-10 的调研快照。GitHub 活跃度、Star 数量和具体 AI 功能会持续变化，开发前应重新核验。

## 5.1 Actual Budget

仓库：`actualbudget/actual`

特点：

- 成熟的 local-first 个人财务系统；
- 支持本地使用与同步；
- 开源社区规模很大；
- 证明“数据优先留在用户手中”的个人财务产品存在强需求。

与 AI 相关的独立项目 `sakowicz/actual-ai` 可以使用 OpenAI、Anthropic、Google、Groq、Ollama 等模型对交易进行自动分类，也支持新分类建议。

判断：

> Actual Budget 值得学习它的 local-first 思想、账本产品能力和成熟社区，但 AI 仍更多表现为增强组件，而非整个系统的智能中枢。

---

## 5.2 Firefly III

仓库：`firefly-iii/firefly-iii`

特点：

- 成熟的 self-hosted 个人财务管理系统；
- 支持复式记账思想、预算、分类、标签、报表；
- 有 Docker 和 API 生态；
- 主要面向希望自行托管财务数据的技术用户。

判断：

> Firefly III 是研究成熟 Ledger、账户模型、导入流程、API 生态的重要参考，但其核心产品逻辑仍然是传统财务软件。

---

## 5.3 Sure

仓库：`we-promise/sure`

Sure 是 Maybe Finance 的社区延续项目之一，目标本身就接近“开源 Personal Finance OS”。

2026 年的版本已经明显向 AI 方向演进，包括：

- 本地 Ollama；
- OpenAI-compatible 模型；
- 外部 AI Assistant；
- MCP；
- OpenClaw 组合部署；
- AI 相关安全代理；
- 对小上下文本地模型提供配置适配。

判断：

> Sure 已经证明“个人财务系统 + 本地 LLM + 外部 Agent + MCP”是实际正在发展的路线，因此 MoneyOS 不能把“支持 Ollama”“接 MCP”“可以聊天查账”本身当作核心创新。

Sure 是 MoneyOS 必须长期跟踪的重点项目。

---

## 5.4 Open Accountant / Wilson

仓库：`openaccountant/wilson`

定位接近 privacy-first AI bookkeeper。

公开能力包括：

- 本地 SQLite；
- AI 交易分类；
- Spending analysis；
- 异常消费分析；
- Agent/Tool/Skill 体系；
- 多模型 Provider；
- 面向 AI 的自然语言财务操作与分析。

Open Accountant 还存在单独的 financial skills 生态，覆盖预算、P&L、债务等多个领域。

判断：

> Wilson 与 MoneyOS 当前设想的技术重合度最高，是最值得拆解的直接 AI 竞品之一。

但 MoneyOS 不应仅复制 Wilson，而要在 **Compute-Adaptive、Financial Semantic Model、Dynamic Analytics Runtime、长期人生语义** 等方面形成更明确的技术主线。

---

# 6. 当前行业空位判断

目前市场中已经分别有人做好了：

- 开源记账；
- self-hosted finance；
- local-first；
- AI 自动分类；
- Ollama；
- MCP；
- Agent；
- 自然语言查交易；
- 固定 Dashboard；
- 多 LLM Provider。

因此：

> **这些单项能力都不能单独构成 MoneyOS 的护城河。**

MoneyOS 更值得做深的交集是：

## 6.1 Compute-Adaptive

MoneyOS 不假设用户拥有固定算力。

系统应支持：

### Tier 0：No-AI / CPU

```text
SQLite
规则引擎
基础统计
传统 Dashboard
```

没有模型也应该是一套可工作的财务系统。

### Tier 1：Cloud-assisted

```text
本地账本
本地 SQL / Analytics
+
可选脱敏上下文
+
云 API
```

适合没有 GPU 但希望获得强 AI 的用户。

### Tier 2：Consumer GPU

例如 8GB 显存消费级 GPU：

```text
本地 4B / 8B 模型
按需加载
Batch Inbox
本地工具调用
动态 SQL
基础 Agent
```

### Tier 3：Home Server

```text
24/7 MoneyOS
更强本地模型
长期 Memory
主动洞察
多设备同步
自动 Inbox
后台任务
```

### Tier 4：Advanced Local AI

```text
大模型
复杂规划
多 Agent / 多模型路由
深度财务分析
长周期个人历史推理
```

核心思想：

> **硬件弱时，MoneyOS 优雅降级；硬件强时，MoneyOS 自然解锁更高智能，而不是要求用户迁移到另一个产品。**

---

## 6.2 Model-Agnostic

MoneyOS Core 不应直接依赖某个模型 SDK。

统一抽象：

```text
LLMProvider
├── OllamaProvider
├── OpenAICompatibleProvider
├── OpenAIProvider
├── AnthropicProvider
└── FutureProvider
```

模型只是能力提供者。

MoneyOS 应允许：

- 完全本地；
- 完全 API；
- 本地 + API 混合；
- 小模型做分类、大模型做分析；
- 按任务动态路由模型。

---

## 6.3 Financial Semantic Model

这是 MoneyOS 最值得重点探索的核心之一。

传统财务软件主要回答：

> **What — 钱花在什么类别？**

MoneyOS 还需要理解：

- **Who**：和谁有关？
- **Why**：为什么发生？
- **Where**：在哪里？
- **Event**：属于哪次事件？
- **Goal**：服务于什么目标？
- **Relation**：这笔钱和某个人/项目是什么关系？
- **Actual Cost**：最终真正由用户承担了多少钱？
- **Emotion / Evaluation（可选）**：后来是否认为这笔钱值得？

例如：

```text
Transaction
────────────────────────
Amount:       238
Category:     餐饮
Merchant:     海底捞
Person:       小雪
Relationship: girlfriend
Context:      约会
Event:        七夕约会
Location:     武汉
Payment:      微信
Paid Amount:  238
Actual Cost:  119 / 238
```

于是系统可以自然回答：

> 今年我和女朋友吃饭花了多少钱？

也可以继续回答：

> 给我画一个饼图，分析我花在女朋友身上的各种开销比例。

AI 不是依赖一个提前编写的 `girlfriend_spending_chart()` 函数，而是：

```text
自然语言
   ↓
Semantic Resolution
   ↓
Query Planning
   ↓
SQL / Analytics
   ↓
Visualization Planning
   ↓
Chart Renderer
   ↓
Natural-language Interpretation
```

这才是真正的自由分析。

---

## 6.4 Dynamic Analytics Runtime

V1 可以提供固定工具：

```text
get_monthly_spending()
get_category_summary()
get_cashflow()
plot_category()
```

但终局不能被固定函数锁死。

未来应允许 AI：

1. 自己理解用户问题；
2. 自己决定查询哪些字段；
3. 生成受控的只读 SQL；
4. 必要时进入 Python Analytics Sandbox；
5. 根据数据决定使用：
   - 表格
   - 饼图
   - 柱状图
   - 折线图
   - 热力图
   - 散点图
   - Markdown 报告
6. 返回解释和结论。

复杂问题示例：

> 开始恋爱前后，我的日常消费结构变化了吗？

> 去掉旅行和购买电子设备以后，我过去两年的基础生活成本趋势是什么？

> 我拥有更多余额以后会不会明显增加消费？

> 我大学期间在旅行、摄影、科研和社交上分别投入了多少？这些投入的变化与我的生活阶段有什么关系？

MoneyOS 最终要具备的是：

> **针对任意合理财务问题临时组织分析流程的能力。**

---

# 7. “有脑子的账本”意味着什么

AI 的价值不是代替 SQL 做加减法。

SQL、数据库、确定性程序负责：

- 金额计算；
- 汇总；
- 排序；
- 比例；
- 余额；
- 会计关系；
- 数据校验。

AI 负责：

- 理解自然语言；
- 消除用户表达歧义；
- 提取交易结构；
- 理解人物、事件与生活上下文；
- 规划查询；
- 设计分析；
- 解释结果；
- 发现模式；
- 给出符合用户目标的建议。

长期来看，MoneyOS 的能力可分为四级：

### Level 1 — What happened?

发生了什么？

> 这个月花了多少钱？

### Level 2 — Why?

为什么？

> 为什么这个月支出明显高于上个月？

### Level 3 — What if?

如果……会怎样？

> 如果未来半年维持当前消费水平，现金储备会怎样变化？

### Level 4 — What should I do?

我该怎么做？

> 如果我要在半年后买一台设备，同时保持旅行预算，应该从哪里调整？

MoneyOS 的终局是 Personal Financial Copilot，而不是会说话的计算器。

---

# 8. 核心产品原则

## 8.1 Ledger Is Truth

所有财务事实必须写入确定性的结构化存储。

第一阶段首选：

> **SQLite**

AI Memory、聊天历史、向量检索结果都不能替代正式账本。

---

## 8.2 AI Is Replaceable

今天的小模型、明天的大模型都只是 Provider。

历史数据和核心财务逻辑不依赖具体模型。

---

## 8.3 Freedom to Analyze, Discipline to Act

AI 可以自由：

- 查询；
- 筛选；
- 聚合；
- 做只读 SQL；
- 做受限 Python 数据分析；
- 绘图；
- 生成报告；
- 推理。

AI 不应直接：

- 任意 `UPDATE` 数据库；
- 任意 `DELETE`；
- 任意运行 Shell；
- 任意修改账本文件。

所有写操作必须通过受控业务 API：

```text
AI
 ↓
MoneyOS Tool
 ↓
Schema Validation
 ↓
Business Rules
 ↓
Audit Log
 ↓
Ledger
```

---

## 8.4 Everything Important Is Auditable

重要写操作均记录：

- before；
- after；
- 操作来源；
- Agent / User；
- 时间；
- 修改原因；
- 必要时原始消息。

用户应该能够查看、撤回和纠正 AI 操作。

---

## 8.5 Preserve Raw Input

自然语言原始输入必须尽可能保留。

例如：

```text
“晚上和小李吃海底捞我先付238，他后来转我100”
```

即使 AI 当前解析结果不完美，未来模型升级后也可以重新解析低置信度历史记录。

因此建议保留：

```text
raw_messages
parsed_transactions
parser_version
model_id
confidence
```

---

## 8.6 Privacy by Architecture

MoneyOS 应明确区分：

### Fully Local

数据、模型、分析全部本地。

### Local-first Hybrid

Ledger 本地，仅将必要且可控的信息发送到 API。

### Cloud-connected

用户主动选择更强云模型。

必须让用户明确知道：

> **什么数据正在离开设备。**

不能用“AI 很方便”掩盖隐私边界。

---

## 8.7 Money Serves Life

MoneyOS 不默认把“少花钱”作为最终目标。

用户可以拥有不同价值观，例如：

- 旅行优先；
- 摄影优先；
- 教育投入优先；
- 家庭优先；
- 储蓄优先。

AI 应回答：

> 如何让钱更好地服务于用户自己的目标？

而不是机械评价：

> 奶茶太多、娱乐太多、旅行太贵。

---

# 9. 初期目标用户与真实约束

MoneyOS 的第一批开发与使用应围绕真实场景，而不是假设理想服务器环境。

典型初期条件：

```text
Linux Desktop/Laptop
消费级 NVIDIA GPU（例如 RTX 5060 8GB）
机器主要用于学习、科研、开发
MoneyOS 不能长期占据显存
机器无法 24 小时在线
手机是日间主要录入设备
```

因此第一阶段 AI 应：

- 按需加载；
- 完成任务后释放显存；
- 支持批处理；
- 不依赖电脑 24/7 在线；
- 即使 AI 没有启动，也不影响数据暂存和后续同步。

未来有家庭服务器后，可以平滑升级为 Always-on Agent。

---

# 10. 录入体验目标

产品必须极度重视：

> **记录一笔钱的时间成本。**

理想交互：

```text
麦当劳26
```

```text
地铁2
```

```text
妈妈给了500
```

```text
和小雪海底捞238，我付的，她转我100
```

```text
泰山高铁票 386 两个人
```

用户不需要首先学习 MoneyOS 的 Schema。

MoneyOS 负责将自然语言解析为结构化数据。

复杂或低置信度场景通过确认解决：

```text
我理解为：
- 总支付：238
- 对方返还：100
- 你的最终承担：138
- 场景：与小雪聚餐

是否正确？
```

高置信度简单交易则可以直接入账。

---

# 11. 消息渠道策略

所有入口均通过 Channel Adapter 统一。

```text
ChannelAdapter
├── CLI
├── Web
├── Feishu
├── Telegram
├── Discord
├── Future WeChat Adapter
└── MoneyOS Mobile / PWA
```

统一内部消息格式：

```json
{
  "channel": "feishu",
  "timestamp": "...",
  "content": "麦当劳26",
  "attachments": []
}
```

MoneyOS Agent 不应依赖具体聊天平台。

---

## 11.1 第一阶段：飞书 / 其他可靠消息缓冲

当前电脑不能 24 小时在线，因此可利用支持历史消息拉取的平台：

```text
白天：
手机 → 消息平台 → 暂存

晚上：
MoneyOS 启动
→ 拉取未处理消息
→ 本地解析
→ 入库
→ 回复结果
```

注意：

> 使用第三方消息平台意味着原始消息经过第三方服务器，因此不属于完全本地隐私模式。

---

## 11.2 长期：MoneyOS PWA / Mobile

最终可以提供 local-first 手机 Inbox：

```text
手机本地 Pending Queue
        ↓
电脑/家庭服务器上线
        ↓
局域网 / 安全同步
        ↓
MoneyOS
```

从而降低第三方平台依赖。

---

# 12. 数据模型需要提前支持的财务事实

至少应考虑：

## Transaction Types

```text
expense
income
transfer
refund
reimbursement
investment
adjustment
```

### 为什么需要区分？

银行卡 → 支付宝：

> transfer，不是 expense。

购买基金：

> 资产转换，不是普通消费。

实验室报销：

> reimbursement，应与原支出关联。

退款：

> refund，应关联原订单。

AA / 代付：

> 必须区分“支付金额”和“最终个人承担金额”。

---

# 13. Financial Semantic Layer 初步模型

传统分类：

```text
Category
Merchant
Account
Tag
```

MoneyOS 进一步增加：

```text
Entity
├── Person
├── Organization
├── Place
└── Project

Context
Event
Goal
Relationship
TransactionEntityRelation
```

例如：

```text
Person:
  name: 小雪
  relationship: girlfriend
```

一笔交易可同时关联：

```text
Category: 餐饮
Person: 小雪
Context: 约会
Event: 周末约会
Goal: Relationship
Merchant: 海底捞
```

未来 AI 可据此跨维度分析。

重要设计原则：

> **Category、Person、Event、Goal 是正交维度，不应全部塞进一个标签字符串。**

---

# 14. 长期 Memory 体系

MoneyOS 的“记忆”至少分为四类。

## 14.1 Financial Facts

数据库中的客观事实。

## 14.2 User Financial Profile

用户主动确认的长期设置：

- 预算倾向；
- 价值优先级；
- 固定收入；
- 固定支出；
- 常用账户；
- 财务目标。

## 14.3 Episodic Memory

与财务有关的人生事件：

```text
泰山旅行
开始摄影
开始实习
搬家
恋爱
毕业
购置设备
```

## 14.4 Derived Knowledge

AI 从长期数据中推导出的模式，例如：

```text
周末餐饮支出明显高于工作日
旅行月份交通和餐饮共同上涨
购买电子设备后数月可自由支配消费下降
```

Derived Knowledge 不能与原始事实混为一谈，应能追溯其依据和生成时间。

---

# 15. Analytics / Visualization 设计原则

第一阶段可以预定义稳定工具：

```text
plot_cashflow()
plot_category()
plot_budget()
plot_month_compare()
```

长期应加入通用 Visualization Spec。

Agent 根据问题产生：

```text
data_query
group_by
metric
chart_type
title
filters
```

Renderer 再生成 Plotly / Matplotlib / Web 图表。

这样既保留 AI 的自由，又避免 AI 每次都随意编写高风险代码。

复杂分析再进入只读 Python Sandbox。

---

# 16. 报告能力

MoneyOS 应能够根据自然语言生成：

- 聊天式简短回答；
- 表格；
- 单张图；
- Dashboard；
- Markdown 报告；
- HTML 报告；
- 未来可扩展 PDF。

例如：

> 生成我的 2026 年 7 月财务报告。

流程：

```text
Query Planning
      ↓
Deterministic Metrics
      ↓
Charts
      ↓
AI Interpretation
      ↓
Markdown Report
```

报告必须区分：

- 数据事实；
- AI 推断；
- AI 建议。

---

# 17. 初步技术栈建议

> 这里只代表当前优先选择，不是不可替换的永久决定。

## Core

- Python
- SQLite
- Pydantic / Schema Validation
- SQLAlchemy 或轻量数据库层（待技术选型）

## AI

- Ollama：第一阶段本地推理入口之一
- Qwen 等适合消费级显卡的小模型
- OpenAI-compatible Provider abstraction

## Analytics

- SQL
- Pandas / Polars（二选一或按需）
- DuckDB：未来分析增强
- Python Sandbox：后期

## Visualization

第一阶段：

- Streamlit
- Plotly

后期根据产品成熟度再决定是否迁移到独立 Web 前端。

## Deployment

- Native Python dev environment
- Docker / Docker Compose
- 后期 Home Server 模式

---

# 18. 为什么当前不急于使用向量数据库

大多数核心财务问题是结构化查询：

```text
时间
金额
分类
人物
商户
事件
账户
关系
```

正确解决工具通常是 SQL，而不是 embedding。

Vector Search 更适合未来：

- 长备注；
- 财务日记；
- 发票 OCR 文本；
- AI 历史报告；
- 非结构化人生事件描述。

原则：

> **能通过结构化事实回答的问题，不要为了“AI 感”强行使用 RAG。**

---

# 19. 版本演进路线

## V0.1 — Ledger Foundation

目标：

> 做出可靠账本。

包含：

- SQLite；
- Transaction Schema；
- Account；
- Category；
- 基础 CRUD；
- Audit Log；
- CLI；
- 数据备份。

此阶段可以完全没有 AI。

---

## V0.2 — AI Bookkeeping

目标：

> 自然语言能够稳定变成账目。

包含：

- Local LLM；
- Parser；
- Structured Output；
- Confidence；
- Raw Inbox；
- Review / Confirmation；
- 批量解析。

---

## V0.3 — Personal Dashboard

目标：

> 用户第一次可以真正长期使用。

包含：

- 月/年消费；
- Cashflow；
- Category；
- Budget；
- Account；
- Calendar Heatmap；
- Merchant；
- 基础图表。

---

## V0.4 — Finance Copilot

目标：

> 从“记账软件”进入“AI 财务系统”。

包含：

- 自然语言查询；
- Tool Calling；
- 安全只读 SQL；
- Query Planner；
- 自由组合筛选；
- Markdown Report；
- 图表选择。

---

## V0.5 — Semantic Finance

目标：

> AI 开始理解“钱和人生的关系”。

加入：

- Person；
- Relationship；
- Event；
- Context；
- Goal；
- AA / Reimbursement 等关系；
- Entity Resolution。

核心验收问题：

> 今年我和女朋友吃饭花了多少钱？

> 给我画一个饼图，分析我花在女朋友身上的各种开销比例。

如果不能稳定回答，说明 Semantic Layer 仍然不够成熟。

---

## V0.6 — Channels

包含：

- Feishu Adapter；
- Telegram Adapter；
- 统一 Channel API；
- Offline Inbox / Sync。

---

## V1.0 — MoneyOS Stable

目标：

> 形成可以正式开源推广的完整产品。

要求：

- 稳定数据 Schema；
- Provider abstraction；
- Channel abstraction；
- 完整 Docker；
- Backup / Restore；
- Migration；
- 文档；
- Demo；
- Test；
- Security model；
- Plugin/Skill 基础协议。

---

## V2 — Agentic Finance

包含：

- Dynamic SQL；
- Analytics Sandbox；
- Dynamic Visualization；
- Long-term Memory；
- Derived Insights；
- Proactive analysis；
- Financial Skills；
- 更自由的问题规划。

---

## V3 — Always-on MoneyOS

适用于家庭服务器。

包含：

- 24/7 Agent；
- 自动同步；
- 多设备；
- 更强本地模型；
- Background Insight；
- Notification；
- 更完整主动财务助手。

---

## Future — Personal Financial Intelligence

目标不再局限于：

> “钱花到哪里？”

而是帮助理解：

> **钱、选择、时间、关系、目标和人生阶段之间的长期联系。**

---

# 20. 第一阶段明确“不做”的事情

为了防止项目一开始失控，V0.x 不应同时追求：

- 银行全自动同步；
- 微信/支付宝破解式自动抓账；
- 完整投资组合系统；
- 税务系统；
- 多用户家庭财务；
- 企业会计；
- 多 Agent 大规模编排；
- 自训练财务大模型；
- 原生 Android + iOS 双客户端；
- 极复杂插件市场；
- 自研同步协议；
- 自研向量数据库；
- 全功能 ERP。

原则：

> **先让一个真实用户连续使用 MoneyOS 记账、查询、分析，再扩大边界。**

---

# 21. 开源项目战略

MoneyOS 的目标不仅是“自己能用”，而是最终成为有影响力的 GitHub 开源项目。

因此从早期就需要考虑：

## 21.1 清晰定位

README 第一屏必须让用户明白：

MoneyOS 不是 another budgeting app。

候选：

> **An AI-native, local-first personal finance intelligence platform that runs on anything from a laptop to a home AI server.**

---

## 21.2 Five/Six Pillars

可以逐步固化为：

1. **Local-first**
2. **AI-native**
3. **Compute-Adaptive**
4. **Model-Agnostic**
5. **Auditable**
6. **Long-lived**

如果 Ledger Adapter 成熟，再加入：

7. **Ledger-Agnostic**

---

## 21.3 开箱即用

再好的架构，如果部署需要半天，也很难扩大社区。

长期目标应该包括：

```bash
docker compose up
```

或：

```bash
moneyos init
moneyos start
```

---

## 21.4 Demo 必须非常有冲击力

未来 README / Demo 应优先展示“传统软件不容易做到”的问题，而不是普通分类报表。

例如：

```text
User:
今年我和女朋友吃饭花了多少钱？

MoneyOS:
...
```

继续：

```text
User:
那我花在她身上的钱主要是什么？画个图。
```

MoneyOS 动态生成分析和图表。

再继续：

```text
User:
开始恋爱前后，我的日常消费变化明显吗？
```

这类 Demo 才能让人一眼理解 AI-native 的意义。

---

## 21.5 Contributor-friendly Architecture

未来社区应能够独立开发：

```text
moneyos-channel-telegram
moneyos-channel-feishu
moneyos-ledger-firefly
moneyos-ledger-actual
moneyos-plugin-investment
moneyos-plugin-bank-import
moneyos-skill-budget-coach
```

---

# 22. 关键风险

## 22.1 Scope Explosion

财务是一个无限大的领域。

对策：

> 严格版本化，每阶段只解决一个核心体验。

---

## 22.2 AI Hallucination

财务数据不能接受“听起来合理”。

对策：

- 事实来自数据库；
- 计算来自 SQL/Python；
- AI 解释与事实分离；
- 置信度；
- Audit Log；
- Write API；
- 原始输入保留。

---

## 22.3 Semantic Model Overengineering

一开始设计几十种关系可能让系统无法落地。

对策：

> 先用真实数据和真实问题驱动 Schema 演化。

---

## 22.4 Local Model Capability

消费级小模型 Tool Calling 和 Structured Output 可能不稳定。

对策：

- Compute-aware prompt；
- Schema 简化；
- deterministic fallback；
- 可选 Cloud Provider；
- 模型能力检测；
- 按任务路由。

---

## 22.5 Privacy vs Convenience

飞书、Telegram、云 API 都会改变隐私边界。

对策：

> 明确标记运行模式和数据流向，由用户主动选择。

---

## 22.6 Agent Security

高权限 Agent 容易扩大攻击面。

对策：

- Least Privilege；
- Read-only Analytics；
- Write Tools；
- No arbitrary DB mutation；
- Sandbox；
- Audit；
- 后期考虑 Prompt Injection / Tool Poisoning 防护。

---

# 23. MoneyOS 的核心验收问题

未来所有架构设计都可以用以下问题验证。

## Basic Ledger

> 今天麦当劳 26。

能否准确记录？

## Complex Transaction

> 和朋友海底捞我先付 238，他后来转我 100。

能否正确表示支付与实际承担？

## Semantic Query

> 今年我和女朋友吃饭花了多少钱？

能否正确理解人物关系 + 餐饮 + 时间范围？

## Dynamic Visualization

> 给我画一个饼状图，看看花在女朋友身上的钱都是什么。

能否自己规划查询和图表，而不是依赖专用函数？

## Life Analysis

> 开始科研以后，我的消费结构有什么明显变化？

能否结合时间、事件和交易历史分析？

## Compute Adaptation

> 没有 GPU 时还能否使用？

> RTX 5060 时能否按需加载模型而不长期占显存？

> 有家庭服务器以后能否无痛升级到 24/7？

## Safety

> AI 能否自由分析，但不能在没有受控流程的情况下偷偷修改历史账目？

如果这些问题都能优雅解决，MoneyOS 就基本符合最初愿景。

---

# 24. 推荐的后续文档体系

本文件之后建议逐步建立：

```text
docs/
├── VISION.md
├── ARCHITECTURE.md
├── ROADMAP.md
├── DATA_MODEL.md
├── AI_DESIGN.md
├── SECURITY.md
├── PRIVACY.md
├── CHANNELS.md
├── ANALYTICS.md
├── CONTRIBUTING.md
└── ADR/
```

其中最优先的下一份文档：

> **DATA_MODEL.md**

因为财务事实模型一旦错误，后面 AI 越强，只会更聪明地分析错误的数据。

其次：

> **ARCHITECTURE.md**

明确 Core、Ledger、Agent、Provider、Channel、Analytics 的模块边界。

---

# 25. 下一阶段建议

正式编码前，优先完成以下设计：

1. 定义 MoneyOS V0.1 的最小产品边界；
2. 设计 Transaction / Account / Category / Audit Log；
3. 特别设计：
   - transfer；
   - refund；
   - reimbursement；
   - AA / 代付；
4. 定义 Raw Message 与 Transaction 的关系；
5. 定义 Entity / Person / Event 的最小可扩展形式；
6. 确定项目目录；
7. 创建 GitHub Repository；
8. 编写 README 的最小版本；
9. 实现 CLI + SQLite；
10. 使用真实生活数据连续试用，再进入 AI Parser。

---

# 26. 给后续 AI / ChatGPT 项目的工作原则

后续参与 MoneyOS 的 AI 助手应遵守：

1. 始终将 MoneyOS 视为一个 **长期演进的开源产品**，而不是一次性脚本。
2. 但不要因为长期目标而过度工程化当前版本。
3. 优先采用：
   > 核心原理 + 可运行实现 + 关键坑点。
4. 每个重大技术选择都说明：
   - 当前为什么选它；
   - 替代方案是什么；
   - 是否容易替换；
   - 会不会锁死未来。
5. 数据模型和安全边界的重要性高于 UI 炫酷程度。
6. AI 不拥有财务事实；Ledger 拥有事实。
7. 财务计算优先使用确定性程序，不让 LLM 心算承担关键逻辑。
8. 所有 AI 写操作应通过可审计 Tool/API。
9. 保持 Model / Channel / Deployment 可插拔。
10. 始终考虑低算力用户，而不是默认高端 GPU。
11. 设计自由分析能力时，避免退化成几十个硬编码统计函数。
12. 对竞品保持持续跟踪，尤其关注：
    - Actual Budget
    - Firefly III
    - Sure
    - Open Accountant / Wilson
    - Actual AI
13. 不把已经行业常见的能力包装成项目核心创新。
14. 真正需要做深的是：
    - Compute-Adaptive AI
    - Financial Semantic Model
    - Dynamic Analytics Runtime
    - Auditable Agent
    - Long-term Personal Financial Intelligence

---

# 27. 当前项目北极星

MoneyOS 的最终目标可以浓缩为：

> **让用户不再学习“如何操作一个财务软件”，而是直接向自己的财务数据表达真实问题。**

用户不应该需要提前知道：

- 数据库结构；
- 什么报表；
- 哪个筛选器；
- 什么图；
- 应该用什么模型。

他只需要说：

> **“我想知道……”**

MoneyOS 负责完成：

```text
理解
↓
找到正确的财务事实
↓
设计分析
↓
执行确定性计算
↓
必要时生成可视化
↓
结合长期上下文解释
↓
给出用户真正需要的回答
```

这就是 MoneyOS 所谓：

# **“有脑子的账本”**

---

# 28. 结论

MoneyOS 不需要在第一个版本就成为终极产品。

第一版甚至可以只是：

```text
CLI
+
SQLite
+
一个可靠的 Transaction Model
```

但从第一天开始，整个项目都应该沿着同一个方向演化：

```text
Reliable Ledger
      ↓
AI Bookkeeping
      ↓
Conversational Finance
      ↓
Semantic Finance
      ↓
Dynamic Analytics
      ↓
Always-on Personal Financial Agent
      ↓
Personal Financial Intelligence
```

最终，MoneyOS 希望做到：

> **不管用户只有一台普通电脑、一块消费级 GPU、几个云 API Key，还是拥有自己的家庭 AI Server，都能用同一套系统享受 AI 带来的个人财务管理便利。**

> **算力决定 MoneyOS 此刻有多聪明，但不决定用户能不能拥有 MoneyOS。**

---

## 附录 A：重点竞品仓库

- `actualbudget/actual` — Actual Budget
- `sakowicz/actual-ai` — Actual AI
- `firefly-iii/firefly-iii` — Firefly III
- `we-promise/sure` — Sure
- `openaccountant/wilson` — Open Accountant / Wilson
- `openaccountant/skills` — Open Accountant Financial Skills

> 注：行业发展非常快。在确定正式 README 的“竞品对比”和对外创新表述前，应重新进行一次最新 GitHub / 文档调研。

---

## 附录 B：候选项目标语

### Option 1

**Your finances. Your data. Your AI. Any hardware.**

### Option 2

**The ledger remembers. The AI understands.**

### Option 3

**Personal finance intelligence, on your terms.**

### Option 4

**An AI-native finance system that grows with you.**

---

**MoneyOS — Project Vision v0.1**  
**Last updated: 2026-08-10**
