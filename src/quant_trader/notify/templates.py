"""
消息模板

生成各种格式的通知消息
"""


def build_daily_report(data: dict, format: str = "markdown") -> str:
    """
    构建每日报告
    
    Args:
        data: 数据字典，包含:
            - trade_date: 交易日期
            - symbol: 标的代码
            - signal: 信号 (BUY/SELL/HOLD)
            - action: 操作
            - cash: 现金
            - position_qty: 持仓数量
            - avg_cost: 平均成本
            - position_value: 持仓市值
            - total_equity: 总权益
            - daily_pnl: 当日盈亏
            - total_return_pct: 累计收益%
            - price: 当日收盘价
        format: 格式 (markdown / html)
        
    Returns:
        str: 格式化后的消息
    """
    # 默认值
    trade_date = data.get("trade_date", "")
    symbol = data.get("symbol", "")
    signal = data.get("signal", "HOLD")
    action = data.get("action", "无")
    cash = data.get("cash", 0)
    position_qty = data.get("position_qty", 0)
    avg_cost = data.get("avg_cost", 0)
    position_value = data.get("position_value", 0)
    total_equity = data.get("total_equity", 0)
    daily_pnl = data.get("daily_pnl", 0)
    total_return_pct = data.get("total_return_pct", 0)
    price = data.get("price", 0)
    
    # 信号 emoji
    signal_emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}.get(signal, "⚪")
    
    # 格式化数字
    def fmt_money(v):
        return f"HKD {v:,.2f}"
    
    def fmt_pct(v):
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.2f}%"
    
    if format == "markdown":
        # 企业微信 Markdown 格式
        content = f"""## 📊 模拟盘日报 · {trade_date}

**标的**: {symbol}
**信号**: {signal_emoji} {signal}
**操作**: {action}

---

### 账户摘要

> 💰 现金: {fmt_money(cash)}
> 📦 持仓: {position_qty} 股 @ {fmt_money(avg_cost)}
> 📈 市值: {fmt_money(position_value)}
> 🏦 总权益: {fmt_money(total_equity)}
> 📊 当日盈亏: {fmt_money(daily_pnl)}
> 📉 累计收益: {fmt_pct(total_return_pct)}

---

> 💡 价格: {price:.2f}
> 📅 更新于: {trade_date}
"""
        return content
    
    elif format == "html":
        # HTML 格式
        # 根据盈亏设置颜色
        pnl_color = "#28a745" if daily_pnl >= 0 else "#dc3545"
        return_pct_color = "#28a745" if total_return_pct >= 0 else "#dc3545"
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; }}
        .header h2 {{ margin: 0; font-size: 24px; }}
        .header .date {{ opacity: 0.9; font-size: 14px; margin-top: 5px; }}
        .content {{ padding: 20px; }}
        .signal {{ text-align: center; padding: 15px; background: #f8f9fa; border-radius: 8px; margin-bottom: 20px; }}
        .signal .emoji {{ font-size: 48px; }}
        .signal .text {{ font-size: 18px; font-weight: bold; margin-top: 10px; }}
        .action {{ text-align: center; color: #666; font-size: 14px; margin-top: 5px; }}
        .summary {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
        .item {{ padding: 15px; background: #f8f9fa; border-radius: 8px; }}
        .item .label {{ font-size: 12px; color: #666; }}
        .item .value {{ font-size: 18px; font-weight: bold; margin-top: 5px; }}
        .pnl {{ grid-column: span 2; text-align: center; padding: 15px; border-radius: 8px; }}
        .pnl .label {{ font-size: 14px; }}
        .pnl .value {{ font-size: 24px; font-weight: bold; margin-top: 5px; }}
        .footer {{ text-align: center; padding: 15px; color: #999; font-size: 12px; border-top: 1px solid #eee; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>📊 模拟盘日报</h2>
            <div class="date">{trade_date}</div>
        </div>
        <div class="content">
            <div class="signal">
                <div class="emoji">{signal_emoji}</div>
                <div class="text">{signal}</div>
                <div class="action">操作: {action}</div>
            </div>
            <div class="summary">
                <div class="item">
                    <div class="label">💰 现金</div>
                    <div class="value">{fmt_money(cash)}</div>
                </div>
                <div class="item">
                    <div class="label">📦 持仓</div>
                    <div class="value">{position_qty} 股</div>
                </div>
                <div class="item">
                    <div class="label">📈 持仓市值</div>
                    <div class="value">{fmt_money(position_value)}</div>
                </div>
                <div class="item">
                    <div class="label">🏦 总权益</div>
                    <div class="value">{fmt_money(total_equity)}</div>
                </div>
                <div class="pnl" style="background: {pnl_color}20;">
                    <div class="label">📊 累计收益</div>
                    <div class="value" style="color: {return_pct_color};">{fmt_pct(total_return_pct)}</div>
                </div>
            </div>
        </div>
        <div class="footer">
            标的: {symbol} | 收盘价: {price:.2f}
        </div>
    </div>
</body>
</html>"""
        return html
    
    else:
        # 纯文本
        lines = [
            f"模拟盘日报 - {trade_date}",
            f"标的: {symbol}",
            f"信号: {signal_emoji} {signal}",
            f"操作: {action}",
            "",
            "账户摘要:",
            f"  现金: {fmt_money(cash)}",
            f"  持仓: {position_qty} 股 @ {fmt_money(avg_cost)}",
            f"  市值: {fmt_money(position_value)}",
            f"  总权益: {fmt_money(total_equity)}",
            f"  累计收益: {fmt_pct(total_return_pct)}",
        ]
        return "\n".join(lines)


def build_alert_message(title: str, content: str, format: str = "markdown") -> str:
    """
    构建告警消息
    
    Args:
        title: 标题
        content: 内容
        format: 格式
        
    Returns:
        str: 格式化后的消息
    """
    if format == "markdown":
        return f"## ⚠️ {title}\n\n{content}"
    elif format == "html":
        return f"""<h2>{title}</h2><p>{content}</p>"""
    else:
        return f"{title}\n\n{content}"
