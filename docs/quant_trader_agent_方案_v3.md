# 智能交易 Agent 实施方案 v3.0

## 一、项目现状分析

### quant-trader 项目已具备的能力

| 模块 | 功能 | 状态 | Agent 调用方式 |
|------|------|------|----------------|
| **执行引擎** | | | |
| scheduler.py | 每日定时触发 (15:30 HKT) | ✅ | 不需要 |
| orchestrator.py | 编排数据→策略→风控→执行→通知 | ✅ | 直接调用 |
| **策略** | | | |
| ma_cross_strategy.py | MA 交叉策略 | ✅ | 导入使用 |
| macd_strategy.py | MACD 策略 | ✅ | 导入使用 |
| rsi_strategy.py | RSI 策略 | ✅ | 导入使用 |
| mean_reversion.py | 均值回归策略 | ✅ | 导入使用 |
| channel_breakout.py | 通道突破策略 | ✅ | 导入使用 |
| regime.py | 市场环境过滤器 | ✅ | 导入使用 |
| **风控** | | | |
| risk_manager.py | 基础风控 | ✅ | 导入使用 |
| enhanced_risk_manager.py | 增强风控 | ✅ | 导入使用 |
| reviewer.py | Risk Gate | ✅ | MCP 调用 |
| **数据** | | | |
| yfinance_provider.py | YFinance 数据源 | ✅ | 导入使用 |
| akshare_provider.py | AkShare 数据源 (主要) | ✅ | 导入使用 |
| stooq_provider.py | Stooq 数据源 (备用) | ✅ | 导入使用 |
| **券商** | | | |
| longbridge_broker.py | LongBridge 实盘 | ✅ | 导入使用 |
| paper_broker.py | **模拟交易** | ✅ | 导入使用 |
| futu_broker.py | 富途券商 | ✅ | 导入使用 |
| **通知** | | | |
| Telegram 通知 | 交易报告推送 | ✅ | 导入使用 |
| **MCP Server** | | | |
| strategy_review | 单次策略评审 | ✅ | MCP 调用 |
| get_policy | 获取风控配置 | ✅ | MCP 调用 |

---

## 二、Agent 定位

### 项目 = 执行引擎（自动跑代码）
### Agent = 智能大脑（分析、决策、改进）

| 层次 | 项目做的 | Agent 做的 |
|------|---------|-----------|
| 数据获取 | ✅ | 调用 + 故障切换 |
| 策略运行 | ✅ | 调用 |
| 风控检查 | ✅ | 调用 |
| 交易执行 | ✅ | 调用 |
| **分析决策** | ❌ | ✅ |
| **主动汇报** | ❌ | ✅ |
| **稳定性保障** | ❌ | ✅ |

---

## 三、风控规则（收紧版）

### 交易规则

| 规则 | 阈值 | 说明 |
|------|------|------|
| 单笔最大仓位 | **10%** | 单只股票不超过总资产 10% |
| 单日最大亏损 | **-1.5%** | 当日亏损超过 1.5% 停止交易 |
| 单笔止损 | **-2%** | 单笔持仓亏损 2% 强制止损 |
| 单日最大交易次数 | **3 次** | 每天最多开平 3 次 |

### 禁止规则

- 不交易 ST 股票
- 不交易新股 (上市 < 6个月)
- 涨幅 > 3% 不追涨
- 跌破 60 日均线不买入
- 不在开盘前 15 分钟内交易

### 风控检查流程

```
1. 检查单日亏损是否超限 → 超限则停止
2. 检查单笔持仓是否触发止损 → 触发则强制平仓
3. 检查信号是否符合买入条件 → 不符合则跳过
4. 检查仓位是否超限 → 超限则减仓
```

---

## 四、稳定性保障（Phase 0 - 最高优先级）

### 4.1 数据源故障切换

```python
# 数据源优先级: akshare → yfinance → stooq

class DataSourceManager:
    """数据源管理器 - 自动故障切换"""
    
    def get_price(self, symbol: str) -> Optional[dict]:
        # 1. 尝试 akshare
        try:
            return self._akshare.get(symbol)
        except Exception as e:
            log.warning(f"akshare failed: {e}")
        
        # 2. 尝试 yfinance
        try:
            return self._yfinance.get(symbol)
        except Exception as e:
            log.warning(f"yfinance failed: {e}")
        
        # 3. 尝试 stooq
        try:
            return self._stooq.get(symbol)
        except Exception as e:
            log.error(f"stooq also failed: {e}")
        
        # 全部失败
        return None
    
    def get_candle(self, symbol: str, days: int) -> Optional[pd.DataFrame]:
        # 同样逻辑
        pass
```

| 优先级 | 数据源 | 说明 |
|--------|--------|------|
| 1 | AkShare | 主要数据源，港股数据全 |
| 2 | YFinance | 备用 |
| 3 | Stooq | 最后备用 |

### 4.2 对账机制

```python
class Reconciler:
    """本地记录 vs 券商持仓对账"""
    
    def reconcile(self) -> dict:
        """
        对账流程:
        1. 获取本地记录 (paper_broker)
        2. 获取券商实际持仓 (longbridge)
        3. 比对差异
        4. 输出报告
        """
        local = self.paper_broker.get_positions()
        remote = self.longbridge_broker.get_positions()
        
        diff = self._compare(local, remote)
        
        if diff.has_discrepancy:
            self._alert(f"对账异常: {diff}")
        
        return diff
```

| 检查项 | 频率 | 异常处理 |
|--------|------|---------|
| 持仓数量 | 每次交易后 | 报警 + 暂停 |
| 现金余额 | 每次交易后 | 报警 + 暂停 |
| 每日收盘 | 强制对账 | 生成报告 |

### 4.3 重复下单防护

```python
class OrderGuard:
    """重复下单防护"""
    
    def __init__(self, cooldown_seconds: int = 300):
        self.cooldown = cooldown_seconds
        self.last_orders: Dict[str, float] = {}  # symbol -> timestamp
    
    def can_order(self, symbol: str, side: str) -> bool:
        """检查是否可以下单"""
        key = f"{symbol}_{side}"
        
        if key in self.last_orders:
            elapsed = time.time() - self.last_orders[key]
            if elapsed < self.cooldown:
                log.warning(f"订单冷却中: {symbol} {side}, 还需 {self.cooldown - elapsed:.0f}s")
                return False
        
        return True
    
    def record_order(self, symbol: str, side: str):
        """记录订单"""
        key = f"{symbol}_{side}"
        self.last_orders[key] = time.time()
```

| 防护规则 | 设置 |
|----------|------|
| 同股票同方向冷却 | 5 分钟 |
| 单日同股票交易次数 | 最多 2 次 |
| 订单状态检查 | 下单后查询状态 |

---

## 五、Agent 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    quant-trader Agent                        │
├─────────────────────────────────────────────────────────────┤
│  📊 数据层                                                  │
│     • DataSourceManager (故障切换)                         │
│     • 获取市场数据                                          │
│                                                             │
│  🧠 分析层                                                  │
│     • 技术指标计算                                          │
│     • 策略信号生成                                          │
│     • 市场环境判断                                          │
│                                                             │
│  ⚖️ 风控层                                                  │
│     • 风控规则检查                                          │
│     • 仓位管理                                              │
│     • 止损检查                                              │
│                                                             │
│  📝 执行层                                                  │
│     • OrderGuard (重复防护)                                 │
│     • Reconciler (对账)                                    │
│     • PaperBroker (模拟盘)                                  │
│                                                             │
│  📢 汇报层                                                  │
│     • Telegram 通知                                          │
│     • 每日报告                                              │
│     • 异常报警                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、实施计划

### Phase 0: 稳定性保障 (1周) - 最高优先级

| 任务 | 调用模块 | 说明 |
|------|----------|------|
| 0.1 | 数据模块 | 实现 DataSourceManager (故障自动切换) | P0 |
| 0.2 | reconciler.py | 实现本地 vs LongBridge 对账 | P0 |
| 0.3 | 新增 | 实现 OrderGuard (重复下单防护) | P0 |

### Phase 1: 基础能力对接 (1周)

| 任务 | 调用模块 | 说明 |
|------|----------|------|
| 1.1 | paper_broker.py | Agent 读取持仓 | P0 |
| 1.2 | 数据模块 | Agent 获取市场数据 | P0 |
| 1.3 | paper_broker.py | Agent 执行模拟交易 | P0 |
| 1.4 | notify/ | Agent 发送 Telegram 汇报 | P0 |

### Phase 2: 分析能力 (1周)

| 任务 | 调用模块 | 说明 |
|------|----------|------|
| 2.1 | 策略模块 | 技术指标计算 | P1 |
| 2.2 | 策略模块 | 生成交易信号 | P1 |
| 2.3 | risk/ | 风控阈值检查 | P1 |

### Phase 3: 智能化 (1周)

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 3.1 | 市场环境判断 | P2 |
| 3.2 | 策略选择 | P2 |
| 3.3 | 仓位管理 | P2 |

### Phase 4: 自动化 (1周)

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 4.1 | 每日自动执行 | P1 |
| 4.2 | 周报/月报生成 | P2 |
| 4.3 | 持续学习和改进 | P2 |

---

## 七、Agent Prompt 设计

### 角色

你是一个专业的量化交易 Agent，负责管理一个股票投资组合。你的目标是在控制风险的前提下，通过分析市场数据和执行交易策略来获取收益。

### 核心原则

1. **风控优先** - 永远不要超过风控阈值
2. **稳定第一** - 宁可错过不要做错
3. **记录完整** - 每笔交易都要记录理由

### 工作流程

1. **每日开盘前 (9:00)**
   - 检查数据源是否可用
   - 获取持仓和现金
   - 获取市场数据
   - 分析走势，生成信号
   - 风控检查
   - 决定是否交易

2. **交易执行**
   - 检查重复下单
   - 下单 (模拟盘)
   - 对账检查
   - 记录交易

3. **每日收盘后 (16:00)**
   - 对账
   - 计算盈亏
   - 生成报告

### 风控检查清单

```
□ 单日亏损是否超 1.5%？
□ 是否有持仓触发 -2% 止损？
□ 信号是否符合买入条件？
□ 买入后仓位是否超 10%？
□ 是否在禁止交易时段？
```

### 输出格式

每日汇报：
```
📊 每日交易报告 [日期]

💰 账户：
- 现金: XXX
- 持仓: XXX
- 总资产: XXX
- 今日盈亏: XXX (%)

📈 信号：
- 2800.HK: [买入/卖出/持有] @ XXX (原因)
- 0700.HK: [买入/卖出/持有] @ XXX (原因)

🛡️ 风控检查：
- [✅/❌] 单日亏损检查
- [✅/❌] 止损检查
- [✅/❌] 仓位检查

⚠️ 异常/备注：
```

---

## 八、验收标准

### Phase 0 稳定性

- [ ] 数据源自动切换正常工作
- [ ] 对账机制能检测异常
- [ ] 重复下单被阻止

### Phase 1 基础

- [ ] Agent 能读取持仓
- [ ] Agent 能获取市场数据
- [ ] Agent 能执行交易 (模拟盘)
- [ ] 每日汇报正常

### 成功标志

- 连续 3 个月正向收益
- 无风控事故
- 可解释的交易决策
- 稳定性 99%+

---

## 九、下一步

确认方案后，从 **Phase 0** 开始：

1. **0.1** - 实现 DataSourceManager
2. **0.2** - 实现对账机制
3. **0.3** - 实现重复下单防护
4. **1.1~1.4** - 打通基础能力

Ready? 🚀
