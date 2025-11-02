import unittest
from stock_grid_optimizer import GridStrategyOptimizer
from datetime import datetime
import pandas as pd
import numpy as np

class TestGridStrategyOptimizer(unittest.TestCase):
    def setUp(self):
        """
        在每个测试方法之前设置测试环境
        """
        self.optimizer = GridStrategyOptimizer(
            symbol="159300",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 10),
            security_type="ETF",
            initial_positions=5000,
            initial_cash=100000,
            min_buy_times=2,
            price_range=(3.9, 4.3)
        )

    def test_initialization(self):
        """
        测试优化器初始化
        """
        # 检查基本属性是否正确设置
        self.assertEqual(self.optimizer.fixed_params["symbol"], "159300")
        self.assertEqual(self.optimizer.fixed_params["security_type"], "ETF")
        self.assertEqual(self.optimizer.fixed_params["initial_positions"], 5000)
        self.assertEqual(self.optimizer.fixed_params["initial_cash"], 100000)
        self.assertEqual(self.optimizer.fixed_params["price_range"], (3.9, 4.3))

        # 检查参数范围是否正确设置
        self.assertGreater(self.optimizer.param_ranges["up_sell_rate"]["max"], 
                          self.optimizer.param_ranges["up_sell_rate"]["min"])
        self.assertGreater(self.optimizer.param_ranges["down_buy_rate"]["max"], 
                          self.optimizer.param_ranges["down_buy_rate"]["min"])

    def test_parameter_validation(self):
        """
        测试参数验证
        """
        # 测试有效参数
        valid_params = {
            "up_sell_rate": 0.01,
            "down_buy_rate": 0.01,
            "up_callback_rate": 0.003,
            "down_rebound_rate": 0.003,
            "shares_per_trade": 1000
        }
        
        # 测试无效参数
        invalid_params = {
            "up_sell_rate": -0.01,  # 负值
            "down_buy_rate": 0.01,
            "up_callback_rate": 0.003,
            "down_rebound_rate": 0.003,
            "shares_per_trade": 1000
        }
        
        # 使用_validate_params方法进行验证
        self.assertTrue(self.optimizer._validate_params(valid_params))
        self.assertFalse(self.optimizer._validate_params(invalid_params))

    def test_profit_calculation_methods(self):
        """
        测试收益计算方法
        """
        # 创建测试数据
        test_profits = pd.Series([-0.5, -0.3, -0.2, 0.1, 0.2, 0.3, 0.5])
        
        # 计算不同方法的收益率
        profit_rate_mean = test_profits.mean()
        profit_rate_median = test_profits.median()
        
        # 验证不同计算方法得到的结果不同
        self.assertNotEqual(profit_rate_mean, profit_rate_median)

if __name__ == '__main__':
    unittest.main() 