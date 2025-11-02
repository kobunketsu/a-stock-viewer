import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
from akshare_wrapper import akshare

# 添加src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from grid_strategy import GridStrategy


class TestGridStrategy(unittest.TestCase):
    """网格策略测试类"""
    
    def setUp(self):
        """测试前的准备工作"""
        self.strategy = GridStrategy(symbol="159300", symbol_name="沪深300ETF")
        self.strategy.base_price = 4.0
        self.strategy.price_range = (3.9, 4.3)
        self.strategy.up_sell_rate = 0.01
        self.strategy.up_callback_rate = 0.003
        self.strategy.down_buy_rate = 0.01
        self.strategy.down_rebound_rate = 0.003
        self.strategy.shares_per_trade = 1000
        self.strategy.initial_positions = 5000
        self.strategy.positions = self.strategy.initial_positions
        self.strategy.initial_cash = 100000
        self.strategy.cash = self.strategy.initial_cash
        
        # 生成模拟数据
        dates = pd.date_range(start="2024-01-01", end="2024-01-10", freq='D')
        self.mock_hist_data = pd.DataFrame({
            '日期': dates,
            '开盘': [4.0, 4.1, 4.0, 3.9, 4.0, 4.1, 4.2, 4.1, 4.0, 3.9],
            '收盘': [4.0, 4.1, 4.0, 3.9, 4.0, 4.1, 4.2, 4.1, 4.0, 3.9],
            '最高': [4.1, 4.2, 4.1, 4.0, 4.1, 4.2, 4.3, 4.2, 4.1, 4.0],
            '最低': [3.9, 4.0, 3.9, 3.8, 3.9, 4.0, 4.1, 4.0, 3.9, 3.8],
            '成交量': [1000000] * len(dates),
            '成交额': [4000000] * len(dates)
        })
    
    def test_initialization(self):
        """测试策略初始化"""
        # 测试正常初始化
        self.assertEqual(self.strategy.symbol, "159300")
        self.assertEqual(self.strategy.symbol_name, "沪深300ETF")
        self.assertEqual(self.strategy.initial_positions, 5000)
        self.assertEqual(self.strategy.initial_cash, 100000)
        
        # 测试参数验证
        strategy = GridStrategy(symbol="159300", symbol_name="沪深300ETF")
        strategy.initial_cash = -1000  # 负数现金
        with self.assertRaises(ValueError):
            strategy.backtest()
        
        strategy = GridStrategy(symbol="159300", symbol_name="沪深300ETF")
        strategy.initial_positions = -1000  # 负数持仓
        with self.assertRaises(ValueError):
            strategy.backtest()
        
        strategy = GridStrategy(symbol="159300", symbol_name="沪深300ETF")
        strategy.price_range = (4.3, 3.9)  # 无效的价格区间
        with self.assertRaises(ValueError):
            strategy.backtest()
    
    def test_buy_operation(self):
        """测试买入操作"""
        # 测试正常买入
        result = self.strategy.buy(4.0, "2024-01-01")
        self.assertTrue(result)
        self.assertEqual(len(self.strategy.trades), 1)
        self.assertEqual(self.strategy.positions, 6000)
        self.assertEqual(self.strategy.cash, 96000)
        
        # 测试价格超出范围的买入
        result = self.strategy.buy(3.8, "2024-01-01")
        self.assertFalse(result)
        self.assertEqual(self.strategy.failed_trades["买入价格超范围"], 1)
        
        # 测试现金不足的买入
        self.strategy.cash = 0
        result = self.strategy.buy(4.0, "2024-01-01")
        self.assertFalse(result)
        self.assertEqual(self.strategy.failed_trades["现金不足"], 1)
    
    def test_sell_operation(self):
        """测试卖出操作"""
        # 测试正常卖出
        result = self.strategy.sell(4.0, "2024-01-01")
        self.assertTrue(result)
        self.assertEqual(len(self.strategy.trades), 1)
        self.assertEqual(self.strategy.positions, 4000)
        self.assertEqual(self.strategy.cash, 104000)
        
        # 测试价格超出范围的卖出
        result = self.strategy.sell(4.4, "2024-01-01")
        self.assertFalse(result)
        self.assertEqual(self.strategy.failed_trades["卖出价格超范围"], 1)
        
        # 测试持仓不足的卖出
        self.strategy.positions = 0
        result = self.strategy.sell(4.0, "2024-01-01")
        self.assertFalse(result)
        self.assertEqual(self.strategy.failed_trades["无持仓"], 1)
    
    @patch('akshare.fund_etf_hist_em')
    def test_backtest(self, mock_hist_data):
        """测试回测功能"""
        # 设置模拟数据
        mock_hist_data.return_value = self.mock_hist_data
        
        # 执行回测
        profit_rate = self.strategy.backtest(
            start_date="2024-01-01",
            end_date="2024-01-10",
            verbose=True
        )
        
        # 验证回测结果
        self.assertIsInstance(profit_rate, float)
        self.assertTrue(len(self.strategy.trades) > 0)
    
    def test_calculate_profit(self):
        """测试收益计算"""
        self.strategy.initial_cash = 100000
        self.strategy.initial_positions = 5000
        self.strategy.base_price = 4.0
        self.strategy.cash = 80000
        self.strategy.positions = 10000
        
        # 测试收益计算
        self.strategy.calculate_profit(4.2, verbose=True)
        self.assertGreater(self.strategy.final_profit_rate, 0)
        
        # 测试亏损计算
        self.strategy.calculate_profit(3.8, verbose=True)
        self.assertLess(self.strategy.final_profit_rate, 0)
    
    def test_ma_protection_edge_cases(self):
        """测试均线保护的边界条件"""
        self.strategy.ma_protection = True
        self.strategy.ma_period = 5
        
        # 测试价格等于均线的情况
        self.assertTrue(self.strategy._check_ma_protection(4.0, 4.0, True))
        self.assertTrue(self.strategy._check_ma_protection(4.0, 4.0, False))
        
        # 测试均线为None的情况
        self.assertTrue(self.strategy._check_ma_protection(4.0, None, True))
        self.assertTrue(self.strategy._check_ma_protection(4.0, None, False))
        
        # 测试ma_protection为False的情况
        self.strategy.ma_protection = False
        self.assertTrue(self.strategy._check_ma_protection(4.0, 4.0, True))
        self.assertTrue(self.strategy._check_ma_protection(4.0, 4.0, False))
    
    def test_trade_failure_recording(self):
        """测试交易失败记录"""
        # 测试买入失败记录
        self.strategy.cash = 0  # 设置现金为0
        self.strategy.buy(4.0, '2024-01-01')
        self.assertEqual(self.strategy.failed_trades['现金不足'], 1)
        
        # 测试卖出失败记录
        self.strategy.positions = 0  # 设置持仓为0
        self.strategy.sell(4.0, '2024-01-01')
        self.assertEqual(self.strategy.failed_trades['无持仓'], 1)
        
        # 测试价格超出范围的失败记录
        self.strategy.buy(3.8, '2024-01-01')  # 低于最低价
        self.assertEqual(self.strategy.failed_trades['买入价格超范围'], 1)
        
        self.strategy.sell(4.4, '2024-01-01')  # 高于最高价
        self.assertEqual(self.strategy.failed_trades['卖出价格超范围'], 1)
    
    def test_stock_data_fetching(self):
        """测试股票数据获取"""
        # 设置为股票类型
        self.strategy.security_type = "STOCK"
        
        # 测试回测
        with patch('akshare.stock_zh_a_hist') as mock_hist_data:
            mock_hist_data.return_value = self.mock_hist_data
            profit_rate = self.strategy.backtest('2024-01-01', '2024-01-05')
            self.assertIsInstance(profit_rate, float)
    
    def test_empty_data_handling(self):
        """测试空数据处理"""
        with patch('akshare.fund_etf_hist_em') as mock_hist_data:
            # 设置返回空数据
            mock_hist_data.return_value = pd.DataFrame()
            
            # 测试空数据异常
            with self.assertRaises(Exception):
                self.strategy.backtest('2024-01-01', '2024-01-05')
    
    def test_verbose_output(self):
        """测试详细输出模式"""
        with patch('akshare.fund_etf_hist_em') as mock_hist_data:
            # 设置模拟数据
            mock_hist_data.return_value = self.mock_hist_data
            
            # 测试带详细输出的回测
            profit_rate = self.strategy.backtest('2024-01-01', '2024-01-05', verbose=True)
            self.assertIsInstance(profit_rate, float)
            
            # 测试带详细输出的收益计算
            self.strategy.calculate_profit(4.0, verbose=True)
    
    def test_invalid_date_format(self):
        """测试无效日期格式"""
        with self.assertRaises(ValueError):
            self.strategy.buy(4.0, "invalid-date")
    
    def test_future_date_trading(self):
        """测试未来日期交易"""
        future_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        self.assertFalse(self.strategy.buy(4.0, future_date))
        self.assertFalse(self.strategy.sell(4.0, future_date))
    
    def test_date_format_conversion(self):
        """测试日期格式转换"""
        # 测试 pd.Timestamp 格式
        timestamp_date = pd.Timestamp('2024-01-01')
        self.assertTrue(self.strategy.buy(4.0, timestamp_date))
        
        # 测试字符串格式
        str_date = '2024-01-01'
        self.assertTrue(self.strategy.buy(4.0, str_date))
    
    def test_ma_protection_with_invalid_data(self):
        """测试均线保护在数据无效时的处理"""
        self.strategy.ma_protection = True
        self.strategy.ma_data = None
        
        # 即使没有MA数据，交易也应该能够进行
        self.assertTrue(self.strategy.buy(4.0, '2024-01-01'))
        self.assertTrue(self.strategy.sell(4.0, '2024-01-01'))

    def test_format_trade_details(self):
        """测试交易详情格式化功能"""
        # 准备测试数据
        results = {
            'total_profit': 10.5,
            'total_trades': 5,
            'failed_trades_summary': {
                '无持仓': 2,
                '现金不足': 1
            },
            'segment_results': [
                {
                    'start_date': '2024-01-01',
                    'end_date': '2024-01-05',
                    'profit_rate': 5.2,
                    'trades': 2
                },
                {
                    'start_date': '2024-01-06',
                    'end_date': '2024-01-10',
                    'profit_rate': 5.3,
                    'trades': 3
                }
            ],
            'output': '详细回测输出内容'
        }
        
        segments = [
            (datetime(2024, 1, 1), datetime(2024, 1, 5)),
            (datetime(2024, 1, 6), datetime(2024, 1, 10))
        ]
        
        # 测试不启用分段回测的情况
        output_lines = self.strategy.format_trade_details(
            results=results,
            enable_segments=False,
            segments=None,
            profit_calc_method="mean"
        )
        
        # 验证输出内容
        self.assertIsInstance(output_lines, list)
        self.assertTrue(any('详细回测输出内容' in line for line in output_lines))
        
        # 测试启用分段回测的情况
        output_lines = self.strategy.format_trade_details(
            results=results,
            enable_segments=True,
            segments=segments,
            profit_calc_method="mean"
        )
        
        # 验证输出内容
        self.assertTrue(any('分段 1 回测' in line for line in output_lines))
        self.assertTrue(any('分段 2 回测' in line for line in output_lines))
        self.assertTrue(any('多段回测汇总' in line for line in output_lines))
        self.assertTrue(any('平均收益率: 5.25%' in line for line in output_lines))
        self.assertTrue(any('总交易次数: 5' in line for line in output_lines))
        self.assertTrue(any('无持仓: 2 次' in line for line in output_lines))
        self.assertTrue(any('现金不足: 1 次' in line for line in output_lines))
        
        # 测试使用中位数计算方法
        output_lines = self.strategy.format_trade_details(
            results=results,
            enable_segments=True,
            segments=segments,
            profit_calc_method="median"
        )
        
        # 验证输出内容
        self.assertTrue(any('中位数收益率: 10.50%' in line for line in output_lines))

    def test_run_strategy_details(self):
        """测试策略详情运行功能"""
        with patch('akshare.fund_etf_hist_em') as mock_hist_data:
            # 设置模拟数据
            mock_hist_data.return_value = self.mock_hist_data
            
            # 准备测试参数
            strategy_params = {
                'up_sell_rate': 0.01,
                'up_callback_rate': 0.003,
                'down_buy_rate': 0.01,
                'down_rebound_rate': 0.003,
                'shares_per_trade': 1000
            }
            
            start_date = datetime(2024, 1, 1)
            end_date = datetime(2024, 1, 10)
            
            # 测试单一时间段
            results = self.strategy.run_strategy_details(
                strategy_params=strategy_params,
                start_date=start_date,
                end_date=end_date
            )
            
            # 验证结果格式
            self.assertIsInstance(results, dict)
            self.assertIn('total_profit', results)
            self.assertIn('total_trades', results)
            self.assertIn('failed_trades_summary', results)
            self.assertIn('segment_results', results)
            self.assertIn('output', results)
            
            # 验证结果内容
            self.assertIsInstance(results['total_profit'], float)
            self.assertIsInstance(results['total_trades'], int)
            self.assertIsInstance(results['failed_trades_summary'], dict)
            self.assertIsInstance(results['segment_results'], list)
            self.assertEqual(len(results['segment_results']), 1)
            
            # 测试多时间段
            segments = [
                (datetime(2024, 1, 1), datetime(2024, 1, 5)),
                (datetime(2024, 1, 6), datetime(2024, 1, 10))
            ]
            
            results = self.strategy.run_strategy_details(
                strategy_params=strategy_params,
                start_date=start_date,
                end_date=end_date,
                segments=segments
            )
            
            # 验证多时间段结果
            self.assertEqual(len(results['segment_results']), 2)
            for segment_result in results['segment_results']:
                self.assertIn('start_date', segment_result)
                self.assertIn('end_date', segment_result)
                self.assertIn('profit_rate', segment_result)
                self.assertIn('trades', segment_result)
                self.assertIn('failed_trades', segment_result)
            
            # 验证输出字符串
            self.assertIsInstance(results['output'], str)
            self.assertGreater(len(results['output']), 0)

    def test_format_trial_details(self):
        """测试试验结果格式化功能"""
        # 创建模拟的trial对象
        class MockTrial:
            def __init__(self):
                self.value = -10.5  # 负的收益率
                self.params = {
                    'up_sell_rate': 0.01,
                    'up_callback_rate': 0.003,
                    'down_buy_rate': 0.01,
                    'down_rebound_rate': 0.003,
                    'shares_per_trade': 1000
                }
                self.user_attrs = {
                    'trade_count': 5,
                    'segment_results': [
                        {
                            'start_date': '2024-01-01',
                            'end_date': '2024-01-05',
                            'profit_rate': 5.2,
                            'trades': 2,
                            'failed_trades': {
                                '无持仓': 1,
                                '现金不足': 1
                            }
                        },
                        {
                            'start_date': '2024-01-06',
                            'end_date': '2024-01-10',
                            'profit_rate': 5.3,
                            'trades': 3,
                            'failed_trades': {
                                '无持仓': 1
                            }
                        }
                    ]
                }
        
        trial = MockTrial()
        
        # 获取格式化输出
        output_lines = self.strategy.format_trial_details(trial)
        
        # 验证输出内容
        self.assertIsInstance(output_lines, list)
        
        # 验证参数组合信息
        self.assertTrue(any('参数组合详情' in line for line in output_lines))
        self.assertTrue(any('总收益率: 10.50%' in line for line in output_lines))
        
        # 验证参数详情
        self.assertTrue(any('参数详情' in line for line in output_lines))
        self.assertTrue(any('上涨卖出: 1.00%' in line for line in output_lines))
        self.assertTrue(any('上涨回调: 0.30%' in line for line in output_lines))
        self.assertTrue(any('下跌买入: 1.00%' in line for line in output_lines))
        self.assertTrue(any('下跌反弹: 0.30%' in line for line in output_lines))
        self.assertTrue(any('每次交易股数: 1,000' in line for line in output_lines))
        
        # 验证交易统计
        self.assertTrue(any('交易次数: 5' in line for line in output_lines))
        
        # 验证分段回测信息
        self.assertTrue(any('分段回测详情' in line for line in output_lines))
        self.assertTrue(any('分段 1:' in line for line in output_lines))
        self.assertTrue(any('分段 2:' in line for line in output_lines))
        self.assertTrue(any('时间段: 2024-01-01 - 2024-01-05' in line for line in output_lines))
        self.assertTrue(any('收益率: 5.20%' in line for line in output_lines))
        self.assertTrue(any('交易次数: 2' in line for line in output_lines))
        
        # 验证失败交易统计
        self.assertTrue(any('失败交易统计' in line for line in output_lines))
        self.assertTrue(any('无持仓: 1 次' in line for line in output_lines))
        self.assertTrue(any('现金不足: 1 次' in line for line in output_lines))

if __name__ == '__main__':
    unittest.main() 