import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pandas as pd
from akshare_wrapper import akshare
from trading_utils import (calculate_ma_price, calculate_price_range,
                           get_symbol_info, is_valid_symbol)


class TestMAUtils(unittest.TestCase):
    """均线工具测试类"""
    
    def setUp(self):
        """测试前的准备工作"""
        self.symbol = "159300"
        self.start_date = datetime(2024, 1, 1)
        self.ma_period = 20
        
        # 生成模拟数据
        dates = pd.date_range(start=self.start_date - timedelta(days=self.ma_period*2), 
                            end=self.start_date, 
                            freq='B')
        
        # 创建模拟价格数据
        self.mock_data = pd.DataFrame({
            '日期': dates,
            '收盘': [10.0 + i*0.1 for i in range(len(dates))],
            '开盘': [10.0 + i*0.1 for i in range(len(dates))],
            '最高': [10.0 + i*0.1 + 0.05 for i in range(len(dates))],
            '最低': [10.0 + i*0.1 - 0.05 for i in range(len(dates))],
            '成交量': [1000000 for _ in range(len(dates))],
            '成交额': [10000000 for _ in range(len(dates))]
        })
        
        # 创建模拟ETF数据
        self.mock_etf_data = pd.DataFrame({
            '代码': ['159300', '510300'],
            '名称': ['沪深300ETF', '300ETF']
        })
        
        # 创建模拟股票数据
        self.mock_stock_data = pd.DataFrame({
            '代码': ['000001', '600000'],
            '名称': ['平安银行', '浦发银行']
        })

    @patch('akshare.fund_etf_hist_em')
    def test_calculate_ma_normal(self, mock_hist_data):
        """测试正常计算均线"""
        mock_hist_data.return_value = self.mock_data
        
        close_price, ma_price = calculate_ma_price(
            self.symbol,
            self.start_date,
            self.ma_period
        )
        
        self.assertIsNotNone(close_price)
        self.assertIsNotNone(ma_price)
        self.assertIsInstance(close_price, float)
        self.assertIsInstance(ma_price, float)

    @patch('akshare.stock_zh_a_hist')
    def test_calculate_ma_stock(self, mock_hist_data):
        """测试股票均线计算"""
        mock_hist_data.return_value = self.mock_data
        
        close_price, ma_price = calculate_ma_price(
            "000001",
            self.start_date,
            self.ma_period,
            security_type="STOCK"
        )
        
        self.assertIsNotNone(close_price)
        self.assertIsNotNone(ma_price)
        mock_hist_data.assert_called_once()

    @patch('akshare.fund_etf_hist_em')
    def test_calculate_ma_empty_data(self, mock_hist_data):
        """测试空数据情况"""
        mock_hist_data.return_value = pd.DataFrame()
        
        close_price, ma_price = calculate_ma_price(
            self.symbol,
            self.start_date,
            self.ma_period
        )
        
        self.assertIsNone(close_price)
        self.assertIsNone(ma_price)

    @patch('akshare.fund_etf_hist_em')
    def test_calculate_ma_different_periods(self, mock_hist_data):
        """测试不同均线周期"""
        mock_hist_data.return_value = self.mock_data
        
        # 测试不同的均线周期
        periods = [5, 10, 20, 30]
        for period in periods:
            close_price, ma_price = calculate_ma_price(
                self.symbol,
                self.start_date,
                period
            )
            
            self.assertIsNotNone(close_price)
            self.assertIsNotNone(ma_price)

    @patch('akshare.fund_etf_hist_em')
    def test_calculate_ma_error_handling(self, mock_hist_data):
        """测试错误处理"""
        # 模拟API异常
        mock_hist_data.side_effect = Exception("API错误")
        
        close_price, ma_price = calculate_ma_price(
            self.symbol,
            self.start_date,
            self.ma_period
        )
        
        self.assertIsNone(close_price)
        self.assertIsNone(ma_price)
    
    @patch('akshare.fund_etf_spot_em')
    @patch('akshare.stock_zh_a_spot_em')
    def test_get_symbol_info(self, mock_stock_data, mock_etf_data):
        """测试获取证券信息"""
        # 设置模拟数据
        mock_etf_data.return_value = self.mock_etf_data
        mock_stock_data.return_value = self.mock_stock_data
        
        # 测试ETF
        name, security_type = get_symbol_info("159300")
        self.assertEqual(name, "沪深300ETF")
        self.assertEqual(security_type, "ETF")
        
        # 测试股票
        name, security_type = get_symbol_info("000001")
        self.assertEqual(name, "平安银行")
        self.assertEqual(security_type, "STOCK")
        
        # 测试无效代码
        name, security_type = get_symbol_info("invalid")
        self.assertIsNone(name)
        self.assertEqual(security_type, "STOCK")
    
    @patch('akshare.fund_etf_hist_em')
    @patch('akshare.stock_zh_a_hist')
    def test_calculate_price_range(self, mock_stock_hist, mock_etf_hist):
        """测试计算价格范围"""
        # 设置模拟数据
        mock_etf_hist.return_value = self.mock_data
        mock_stock_hist.return_value = self.mock_data
        
        # 测试ETF
        price_min, price_max = calculate_price_range(
            "159300",
            "2024-01-01",
            "2024-01-10"
        )
        self.assertIsNotNone(price_min)
        self.assertIsNotNone(price_max)
        self.assertLess(price_min, price_max)
        
        # 测试股票
        price_min, price_max = calculate_price_range(
            "000001",
            "2024-01-01",
            "2024-01-10",
            security_type="STOCK"
        )
        self.assertIsNotNone(price_min)
        self.assertIsNotNone(price_max)
        self.assertLess(price_min, price_max)
        
        # 测试空数据
        mock_etf_hist.return_value = pd.DataFrame()
        price_min, price_max = calculate_price_range(
            "159300",
            "2024-01-01",
            "2024-01-10"
        )
        self.assertIsNone(price_min)
        self.assertIsNone(price_max)
    
    @patch('akshare.fund_etf_spot_em')
    @patch('akshare.stock_zh_a_spot_em')
    def test_is_valid_symbol(self, mock_stock_data, mock_etf_data):
        """测试证券代码验证"""
        # 设置模拟数据
        mock_etf_data.return_value = self.mock_etf_data
        mock_stock_data.return_value = self.mock_stock_data
        
        # 测试有效ETF代码
        self.assertTrue(is_valid_symbol("159300"))
        
        # 测试有效股票代码
        self.assertTrue(is_valid_symbol("000001"))
        
        # 测试无效代码
        self.assertFalse(is_valid_symbol("invalid"))
        
        # 测试API异常
        mock_etf_data.side_effect = Exception("API错误")
        self.assertFalse(is_valid_symbol("159300"))

if __name__ == '__main__':
    unittest.main() 