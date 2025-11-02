import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime, timedelta
from segment_utils import build_segments, get_segment_days, BATCH_TO_DAYS_MAP

class TestSegmentUtils(unittest.TestCase):
    """时间段工具测试类"""
    
    def setUp(self):
        """测试前的准备工作"""
        self.start_date = datetime(2024, 1, 1)
        self.end_date = datetime(2024, 3, 31)
        
        # 生成模拟交易日历数据
        dates = pd.date_range(start=self.start_date, end=self.end_date, freq='B')
        self.mock_calendar = pd.DataFrame({
            'trade_date': dates,
            'open': 1  # 1表示交易日
        })

    def test_get_segment_days(self):
        """测试获取段天数"""
        # 测试正常批次
        for batch, days in BATCH_TO_DAYS_MAP.items():
            self.assertEqual(get_segment_days(batch), days)
        
        # 测试边界值
        self.assertEqual(get_segment_days(0), BATCH_TO_DAYS_MAP[1])  # 小于最小值
        self.assertEqual(get_segment_days(6), BATCH_TO_DAYS_MAP[5])  # 大于最大值
        self.assertEqual(get_segment_days(-1), BATCH_TO_DAYS_MAP[1])  # 负数

    @patch('akshare.tool_trade_date_hist_sina')
    def test_build_segments_normal(self, mock_calendar):
        """测试正常构建时间段"""
        mock_calendar.return_value = self.mock_calendar
        
        # 测试不同的批次
        for batch in BATCH_TO_DAYS_MAP.keys():
            segments = build_segments(self.start_date, self.end_date, batch)
            
            # 验证时间段
            self.assertGreater(len(segments), 0)
            for start, end in segments:
                self.assertLessEqual(start, end)
                self.assertGreaterEqual(start, self.start_date)
                self.assertLessEqual(end, self.end_date)

    @patch('akshare.tool_trade_date_hist_sina')
    def test_build_segments_empty_calendar(self, mock_calendar):
        """测试空日历情况"""
        mock_calendar.return_value = pd.DataFrame()
        
        segments = build_segments(self.start_date, self.end_date, 1)
        
        # 应该返回单个时间段
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0], (self.start_date, self.end_date))

    @patch('akshare.tool_trade_date_hist_sina')
    def test_build_segments_api_error(self, mock_calendar):
        """测试API错误情况"""
        mock_calendar.side_effect = Exception("API错误")
        
        segments = build_segments(self.start_date, self.end_date, 1)
        
        # 应该使用工作日日历作为备选
        self.assertGreater(len(segments), 0)
        for start, end in segments:
            self.assertLessEqual(start, end)

    def test_build_segments_invalid_dates(self):
        """测试无效日期"""
        # 结束日期早于开始日期
        segments = build_segments(self.end_date, self.start_date, 1)
        
        # 应该返回单个时间段
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0], (self.end_date, self.start_date))

    def test_build_segments_same_date(self):
        """测试相同日期"""
        segments = build_segments(self.start_date, self.start_date, 1)
        
        # 应该返回单个时间段
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0], (self.start_date, self.start_date))

    @patch('akshare.tool_trade_date_hist_sina')
    def test_build_segments_boundary_conditions(self, mock_calendar):
        """测试边界条件"""
        mock_calendar.return_value = self.mock_calendar
        
        # 测试最小批次（最长周期）
        min_batch_segments = build_segments(self.start_date, self.end_date, 1)
        self.assertGreater(len(min_batch_segments), 0)
        
        # 测试最大批次（最短周期）
        max_batch_segments = build_segments(self.start_date, self.end_date, 5)
        self.assertGreater(len(max_batch_segments), 0)
        
        # 最小批次（长周期）应该产生更少的时间段
        self.assertGreater(len(max_batch_segments), len(min_batch_segments))
        
        # 验证时间段长度与周期的关系
        min_batch_days = (min_batch_segments[0][1] - min_batch_segments[0][0]).days
        max_batch_days = (max_batch_segments[0][1] - max_batch_segments[0][0]).days
        self.assertGreater(min_batch_days, max_batch_days)

if __name__ == '__main__':
    unittest.main() 