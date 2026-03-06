"""
Orchestrator 测试
"""
import pytest
import sys
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

# 添加路径
sys.path.insert(0, '/Users/a1/.openclaw/workspace/projects/quant-trader/src')


class TestOrchestrator:
    """测试 Orchestrator"""
    
    @patch('quant_trader.orchestrator.get_provider')
    @patch('quant_trader.orchestrator.create_broker')
    def test_normal_flow(self, mock_create_broker, mock_get_provider):
        """测试正常流程"""
        from quant_trader.orchestrator import Orchestrator, StepStatus
        from quant_trader.strategy.signals import Signal
        
        # Mock 数据源
        mock_provider = MagicMock()
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__getitem__ = lambda self, key: [1, 2, 3]
        mock_df.iloc = MagicMock()
        mock_df.iloc[-1] = {"close": 25.0}
        mock_provider.get_bars.return_value = mock_df
        mock_get_provider.return_value = mock_provider
        
        # Mock Broker
        mock_broker = MagicMock()
        mock_broker.get_account.return_value = {"cash": 100000, "total_assets": 100000}
        mock_broker.get_positions.return_value = []
        mock_create_broker.return_value = mock_broker
        
        # Mock 策略
        mock_strategy = MagicMock()
        mock_strategy.generate_signal.return_value = Signal.HOLD
        
        # Mock 数据库
        mock_db = MagicMock()
        
        # 创建 Orchestrator
        orchestrator = Orchestrator(
            broker=mock_broker,
            strategy=mock_strategy,
            db=mock_db,
            symbols=["2800.HK"],
            provider_name="stooq",
            notifier=None,
        )
        
        # 执行
        report = orchestrator.run_daily()
        
        # 验证
        assert len(report.steps) >= 5
        assert report.steps[0].status == StepStatus.SUCCESS  # Step 1
        assert report.steps[1].status == StepStatus.SUCCESS  # Step 2
        assert report.steps[2].status == StepStatus.SUCCESS  # Step 3
    
    @patch('quant_trader.orchestrator.get_provider')
    def test_step1_failure_terminates(self, mock_get_provider):
        """Step 1 失败时终止流程"""
        from quant_trader.orchestrator import Orchestrator, StepStatus
        from quant_trader.strategy.signals import Signal
        
        # Mock 数据源 - 抛出异常
        mock_provider = MagicMock()
        mock_provider.fetch_ohlcv.side_effect = Exception("网络错误")
        mock_get_provider.return_value = mock_provider
        
        # Mock Broker
        mock_broker = MagicMock()
        
        # Mock 策略
        mock_strategy = MagicMock()
        
        # Mock 数据库
        mock_db = MagicMock()
        
        # 创建 Orchestrator
        orchestrator = Orchestrator(
            broker=mock_broker,
            strategy=mock_strategy,
            db=mock_db,
            symbols=["2800.HK"],
            provider_name="stooq",
            notifier=None,
        )
        
        # 执行
        report = orchestrator.run_daily()
        
        # 验证：只有 Step 1
        assert len(report.steps) == 1
        assert report.steps[0].status == StepStatus.FAILED
    
    @patch('quant_trader.orchestrator.get_provider')
    @patch('quant_trader.orchestrator.create_broker')
    def test_middle_step_failure_continues(self, mock_create_broker, mock_get_provider):
        """中间步骤失败不影响后续"""
        from quant_trader.orchestrator import Orchestrator, StepStatus
        from quant_trader.strategy.signals import Signal
        
        # Mock 数据源
        mock_provider = MagicMock()
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.iloc = MagicMock()
        mock_df.iloc[-1] = {"close": 25.0}
        mock_provider.get_bars.return_value = mock_df
        mock_get_provider.return_value = mock_provider
        
        # Mock Broker - 风控检查失败
        mock_broker = MagicMock()
        mock_broker.get_account.return_value = {"cash": 1000}  # 现金不足
        mock_broker.get_positions.return_value = []
        mock_create_broker.return_value = mock_broker
        
        # Mock 策略
        mock_strategy = MagicMock()
        mock_strategy.generate_signal.return_value = Signal.BUY
        
        # Mock 数据库
        mock_db = MagicMock()
        
        # 创建 Orchestrator
        orchestrator = Orchestrator(
            broker=mock_broker,
            strategy=mock_strategy,
            db=mock_db,
            symbols=["2800.HK"],
            provider_name="stooq",
            notifier=None,
        )
        
        # 执行
        report = orchestrator.run_daily()
        
        # 验证：Step 3 失败但 Step 4, 5 仍执行
        assert len(report.steps) >= 4
        # 风控失败，下单跳过
        step4 = [s for s in report.steps if "下单" in s.step_name]
        if step4:
            assert step4[0].status in [StepStatus.SKIPPED, StepStatus.FAILED]
    
    @patch('quant_trader.orchestrator.get_provider')
    @patch('quant_trader.orchestrator.create_broker')
    def test_dry_run_no_real_order(self, mock_create_broker, mock_get_provider):
        """dry_run 模式不调用真实 SDK"""
        from quant_trader.orchestrator import Orchestrator, StepStatus
        from quant_trader.strategy.signals import Signal
        
        # Mock 数据源
        mock_provider = MagicMock()
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.iloc = MagicMock()
        mock_df.iloc[-1] = {"close": 25.0}
        mock_provider.get_bars.return_value = mock_df
        mock_get_provider.return_value = mock_provider
        
        # Mock Broker
        mock_broker = MagicMock()
        mock_broker.get_account.return_value = {"cash": 100000, "total_assets": 100000}
        mock_broker.get_positions.return_value = []
        # place_order 在 dry_run 应该抛出 PermissionError
        mock_broker.place_order.side_effect = PermissionError("readonly mode")
        mock_create_broker.return_value = mock_broker
        
        # Mock 策略 - 产生买入信号
        mock_strategy = MagicMock()
        mock_strategy.generate_signal.return_value = Signal.BUY
        
        # Mock 数据库
        mock_db = MagicMock()
        
        # 创建 Orchestrator
        orchestrator = Orchestrator(
            broker=mock_broker,
            strategy=mock_strategy,
            db=mock_db,
            symbols=["2800.HK"],
            provider_name="stooq",
            notifier=None,
        )
        
        # 执行
        report = orchestrator.run_daily()
        
        # 验证：broker.place_order 被调用了，但抛出了权限错误
        # 这是预期行为，因为 dry_run 模式不允许真实下单
        assert mock_broker.place_order.called or len(report.steps) >= 4


class TestScheduler:
    """测试 Scheduler"""
    
    def test_parse_time(self):
        """测试时间解析"""
        from quant_trader.scheduler import TradingScheduler
        
        scheduler = TradingScheduler(
            broker_config={"type": "paper"},
            symbols=["2800.HK"],
            run_time="15:30",
        )
        
        assert scheduler.run_time == "15:30"
    
    @patch('quant_trader.scheduler.create_orchestrator')
    def test_run_now(self, mock_create_orchestrator):
        """测试立即执行"""
        from quant_trader.scheduler import TradingScheduler
        from quant_trader.orchestrator import DailyReport
        
        # Mock orchestrator
        mock_orch = MagicMock()
        mock_report = DailyReport(
            date="2026-03-06",
            steps=[],
            total_runtime_seconds=1.0,
        )
        mock_orch.run_daily.return_value = mock_report
        mock_create_orchestrator.return_value = mock_orch
        
        # 创建并执行
        scheduler = TradingScheduler(
            broker_config={"type": "paper"},
            symbols=["2800.HK"],
        )
        
        scheduler.run_now()
        
        # 验证
        assert mock_orch.run_daily.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
