# 聚宽优秀开源策略研究

## 目的
这份文档不是整理“谁的收益最高”，而是从聚宽社区公开策略里提炼可迁移的方法结构，服务 OpenHamster 的：

- `strategy knowledge layer`
- `strategy proposal`
- `research debate`
- `risk gate`

当前目标是学习“策略怎么搭起来”，不是把聚宽代码直接搬进仓库。

## 先讲边界
聚宽社区的大量高收益帖子依赖以下条件：

- A 股微盘或小市值风格暴露
- 涨跌停、停牌、ST、复权口径等平台内置规则
- 聚宽特有数据接口、因子库、回测撮合和研究环境
- 对容量、冲击成本、滑点、税费和真实可成交性的弱约束

这些内容不适合直接进入 OpenHamster 当前主线。  
本项目当前是：

- `HK-only`
- `long-only`
- `daily` 级研究和执行
- 强调 `auditability`
- 不引入旧交易兼容层

所以我们只能吸收“结构化策略思路”，不能把社区帖子当成可执行真相。

## 样本来源
本轮优先看的是聚宽公开可访问、且能代表常见方法范式的内容：

- 社区精选/高权重列表入口：
  [聚宽社区列表](https://www.joinquant.com/view/community/list?listType=1&type=isWeight&tags=)
- 小市值 + 择时类：
  [小市值调整持股数量和止损，加入指数 MACD 顶背离](https://www.joinquant.com/community/post/detailMobile?postId=51521)
- 基本面成长估值类：
  [对 PEG 策略进一步修改](https://www.joinquant.com/community/post/detailMobile?postId=7433)
- 多策略组合/公共基类化：
  [多策略最终版](https://www.joinquant.com/community/post/detailMobile?postId=53303)
- 社区经验入口和主题导航：
  [聚宽干货合集](https://www.joinquant.com/community/post/detailMobile?postId=599)
- 因子库能力边界：
  [Alpha191 因子说明](https://www.joinquant.com/data/dict/alpha191)

## 看到的 4 类主流结构

### 1. 小市值轮动 + 市场择时
典型代表：

- [小市值调整持股数量和止损，加入指数 MACD 顶背离](https://www.joinquant.com/community/post/detailMobile?postId=51521)
- [聚宽策略天梯贴](https://www.joinquant.com/community/post/detailMobile?postId=56054)

这类策略的共同点不是“小市值”三个字，而是 4 层结构：

- 先做股票池过滤：
  剔除停牌、ST、涨停、极端成交异常等
- 再做强约束排序：
  小市值、强势、近期活跃度、换手特征
- 再加市场开关：
  典型是指数趋势、MACD、宽度、空仓月
- 最后再叠交易侧规则：
  持仓数限制、卖出屏蔽、行业数限制、止损止盈

对 OpenHamster 有价值的，不是“小盘股暴击”，而是这套结构：

- `universe filter`
- `ranking signal`
- `timing overlay`
- `execution/risk overlay`

这类结构说明，很多所谓高收益策略，本质不是单一 alpha，而是一个多层裁剪系统。

### 2. PEG / 低 PB / 财务筛选类
典型代表：

- [对 PEG 策略进一步修改](https://www.joinquant.com/community/post/detailMobile?postId=7433)
- [低 PB 价值投资策略分享](https://www.joinquant.com/community/post/detailMobile?postId=11549)

这类策略的稳定部分通常是：

- 财务成长或质量条件：
  收入增长、利润增长、ROE、负债或现金流约束
- 估值约束：
  PEG、PB、PE、分位阈值
- 调仓稀疏：
  5 日、周级、季报驱动，不是高频轮动
- 自然仓位控制：
  候选少则自动降仓

这类策略给 OpenHamster 的启发：

- 基本面类方法天然适合进入 `proposal template`
- 它们比微盘情绪类更容易解释，也更适合审计
- 但必须加入“市场状态失效条件”，否则牛熊切换时很容易失灵

最关键的一点是，这类帖子经常把“估值条件”与“市场 regime 判断”绑在一起。  
这对我们的知识层有直接启发：基本面策略不能被记录成静态筛子，必须带 `preferred_market_conditions` 与 `discouraged_market_conditions`。

### 3. 多因子 / 因子库驱动选股
典型代表：

- [Alpha191 因子说明](https://www.joinquant.com/data/dict/alpha191)
- [年化 46.77，alpha191 因子选股](https://www.joinquant.com/community/post/detailMobile?postId=44491)

从聚宽生态看，多因子策略通常不是“191 个因子全都用”，而是：

- 从标准因子库里挑一批候选
- 做标准化、中性化、打分或排序
- 再套一层股票池约束与调仓节奏

对 OpenHamster 的启发不是去复制 `Alpha191`，而是要承认：

- 因子是“原料”，不是策略
- 因子策略需要稳定的预处理与约束语义
- 没有容量、换手、风格暴露控制的因子组合，很容易只是回测优化器产物

这类方法更适合作为 OpenHamster 的：

- `knowledge source`
- `ranking family`
- `candidate generator`

不适合作为当前阶段的直接 baseline。

### 4. 多策略组合 / 公共基类化
典型代表：

- [多策略最终版](https://www.joinquant.com/community/post/detailMobile?postId=53303)

这类帖子最值得学的不是组合了多少子策略，而是工程抽象：

- 把公共过滤逻辑抽到基类
- 把择时函数抽成统一模块
- 把行业限制、换手限制、卖出屏蔽等做成复用规则

这和 OpenHamster 当前方向非常一致。  
我们不应该继续加一堆孤立策略，而应该把社区常见的公共逻辑整理成可审计的元结构：

- `family`
- `entry filter`
- `timing filter`
- `risk overlay`
- `rebalance cadence`

## 从聚宽策略里抽出的共性
无论是小市值、PEG 还是多因子，优秀策略基本都满足下面几条：

### 1. 先缩股票池，再做排序
很少有真正有效的策略是“全市场一次性打分直接买前 N”。  
更常见的做法是：

- 先过滤不可交易和不想交易的标的
- 再在剩余集合上排序

这说明 OpenHamster 的 proposal 结构不该只存“信号公式”，还应该显式保留：

- `universe filters`
- `eligibility assumptions`

### 2. 大多数 alpha 都靠择时层保护
社区里很多看起来是选股策略，实质上收益大头来自：

- 指数趋势过滤
- 宽度过滤
- MACD/均线状态过滤
- 特定月份空仓

也就是说，“选股信号”本身往往没有帖子标题那么决定性。  
真正决定回撤和存活率的，是 `timing overlay`。

### 3. 风控和交易约束常常比信号本体更重要
反复出现的组件包括：

- 持仓数限制
- 行业分散
- 单票仓位上限
- 止损止盈
- 冷却期
- 涨停/强趋势持仓的特殊处理

这与 OpenHamster 的治理视角完全兼容。  
我们应该继续强化“策略提案必须显式声明执行与风险约束”，而不是只看信号本身。

### 4. 很多社区帖子是在做参数与规则堆叠
这是最需要警惕的部分。  
聚宽社区高分帖常见的问题是：

- 多个过滤器不断叠加
- 特殊日历规则越来越多
- 若干 seemingly effective 的小修补同时存在

这类策略在社区回测里看起来很强，但对 OpenHamster 来说通常意味着：

- 可解释性下降
- 新颖性很弱
- 过拟合风险上升
- 审计证据难以压缩

所以这些经验更适合进入 `risk flags`，而不是进入 baseline。

## 对知识层的直接启发
当前知识层只有：

- `trend_following`
- `mean_reversion`
- `breakout`
- `momentum_filter`
- `volatility_filter`

如果继续吸收聚宽社区经验，下一阶段更合理的新增方向不是直接加几十个 baseline，而是补更高层的方法标签。

建议优先新增的候选知识家族：

### `fundamental_growth`
适配来源：

- PEG
- 增长 + 估值
- 财务质量筛选

建议字段重点：

- `preferred_market_conditions`
- `discouraged_market_conditions`
- `rebalance_cadence_preference`
- `common_failure_modes`

### `cross_sectional_ranking`
适配来源：

- 小市值轮动
- 多因子打分
- 排序式选股

建议字段重点：

- `ranking_inputs`
- `liquidity_dependency`
- `crowding_risk`

### `regime_filter`
适配来源：

- 指数 MACD
- 市场宽度
- 牛熊过滤
- 空仓月/风险时段

建议字段重点：

- `macro_dependency`
- `failure_if_missing`
- `interaction_with_primary_strategy`

### `portfolio_construction_overlay`
适配来源：

- 行业数限制
- 持仓数量动态调整
- 单票权重控制

建议字段重点：

- `position_count_logic`
- `weighting_scheme`
- `diversification_constraints`

## 对 OpenHamster 的落地建议

### 不要做的
- 不要把聚宽代码直接转成策略插件
- 不要引入 A 股专属执行假设
- 不要把“高收益帖子”直接当白名单知识
- 不要把参数表面差异当成策略创新

### 应该做的
- 把社区策略提炼成“方法模板”
- 把方法模板映射进知识层，而不是直接映射进 baseline
- 让 `strategy_agent` 学会生成“主策略 + 过滤器 + 风控器”的组合解释
- 让 `research_debate` 和 `risk gate` 能识别“只是规则堆叠”的伪创新

## 建议的第二阶段工作包

### 1. 外部资料转内部知识条目
建立：

- `external_source`
- `structured_method_note`
- `reviewed_knowledge_candidate`

流程应当是：

`社区帖子 -> 结构化摘要 -> 人工/规则审核 -> 内部知识条目`

而不是：

`社区帖子 -> prompt 原文输入 -> 策略生成`

### 2. 新增 3 类 proposal 模板
建议优先加：

- `fundamental_growth_template`
- `cross_sectional_ranking_template`
- `regime_filtered_rotation_template`

### 3. 在质量报告里新增 3 个检查点
- `rule_stack_complexity`
- `regime_dependency_strength`
- `capacity_assumption_clarity`

## 结论
聚宽社区里真正值得学的不是某一条“翻倍策略”，而是这些帖子反复证明的一件事：

优秀开源策略通常不是单一信号，而是一个由

- 股票池约束
- 横截面排序
- 市场状态过滤
- 组合与交易约束

共同组成的策略系统。

这和 OpenHamster 的产品方向是兼容的。  
但兼容点在“结构化方法知识”，不在“直接复刻社区代码”。
