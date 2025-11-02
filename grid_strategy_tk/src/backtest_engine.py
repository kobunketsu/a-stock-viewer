import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import akshare as ak
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from conditions import SignalMark
from tqdm import tqdm

# 添加项目根目录到系统路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from conditions import CostCrossMaCondition, Signal, SignalLevel
from stock_analysis_engine import ETFAnalysisEngine


@dataclass
class TradeRecord:
    """交易记录数据类"""
    date: str
    code: str
    name: str
    action: str  # 'buy' or 'sell'
    price: float
    shares: int
    amount: float
    fee: float
    profit: float = 0.0
    profit_rate: float = 0.0
    reason: str = ""

class BacktestEngine:
    def __init__(self):
        self.analysis_engine = ETFAnalysisEngine()
        self.data_cache_dir = os.path.join(project_root, "data", "cache")
        self.results_dir = os.path.join(project_root, "data", "results")
        
        # 确保目录存在
        os.makedirs(self.data_cache_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        
        # 交易参数
        self.daily_limit = 100000  # 每日交易限额10万
        self.commission_rate = 0.0001  # 佣金费率万一
        self.base_shares = 100  # 基础购买股数
        
        # 回测数据
        self.trade_records: List[TradeRecord] = []
        self.daily_stats: Dict[str, dict] = {}
        self.positions: Dict[str, dict] = {}  # 当前持仓
        self.history_data: Dict[str, pd.DataFrame] = {}  # 历史数据缓存
        
        # 设置日志
        self._setup_logger()
        
    def _setup_logger(self):
        """设置日志"""
        self.logger = logging.getLogger('backtest')
        self.logger.setLevel(logging.INFO)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        
        # 文件处理器
        log_file = os.path.join(self.results_dir, 'backtest.log')
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)

    def _load_stock_list(self) -> List[str]:
        """获取所有300开头的创业板股票列表"""
        try:
            stocks = ak.stock_zh_a_spot_em()
            # 筛选300开头的股票
            growth_stocks = stocks[stocks['代码'].str.startswith('300')]
            return growth_stocks['代码'].tolist()
        except Exception as e:
            self.logger.error(f"获取股票列表失败: {e}")
            return []

    def _load_history_data(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """加载或获取历史数据"""
        cache_file = os.path.join(self.data_cache_dir, f"{code}_history.csv")
        
        # 检查缓存是否存在且是否需要更新
        if os.path.exists(cache_file):
            cached_data = pd.read_csv(cache_file)
            cached_data['日期'] = pd.to_datetime(cached_data['日期'])
            last_date = cached_data['日期'].max()
            
            # 如果缓存数据不够新，进行增量更新
            # 检查是否需要增量更新数据
            start_date_dt = pd.to_datetime(start_date)
            end_date_dt = pd.to_datetime(end_date)
            first_date = cached_data['日期'].min()
            last_date = cached_data['日期'].max()
            
            # 分别处理前后两端的增量更新
            if start_date_dt < first_date:
                # 获取开始日期到第一条记录之间的数据
                start_data = self.analysis_engine.load_data(
                    code=code,
                    symbol_name=code,
                    period_mode='day',
                    start_date=start_date,
                    end_date=first_date.strftime('%Y-%m-%d'),
                    period_config={
                        'day': {
                            'ak_period': 'daily',
                            'buffer_ratio': '0.2',
                            'min_buffer': '10'
                        }
                    },
                    ma_lines=[5, 10, 20],
                    force_refresh=True
                )
                
                if not start_data.empty:
                    start_data = start_data.reset_index()
                    cached_data = pd.concat([start_data, cached_data])
            
            if end_date_dt > last_date:
                # 获取最后一条记录到结束日期之间的数据
                end_data = self.analysis_engine.load_data(
                    code=code,
                    symbol_name=code,
                    period_mode='day',
                    start_date=last_date.strftime('%Y-%m-%d'),
                    end_date=end_date,
                    period_config={
                        'day': {
                            'ak_period': 'daily',
                            'buffer_ratio': '0.2',
                            'min_buffer': '10'
                        }
                    },
                    ma_lines=[5, 10, 20],
                    force_refresh=True
                )
                
                if not end_data.empty:
                    end_data = end_data.reset_index()
                    cached_data = pd.concat([cached_data, end_data])
            
            # 如果有更新，处理并保存数据
            if start_date_dt < first_date or end_date_dt > last_date:
                # 去重
                cached_data = cached_data.drop_duplicates(subset=['日期'], keep='last')
                # 按日期排序
                cached_data = cached_data.sort_values('日期')
                # 保存更新后的数据
                cached_data.to_csv(cache_file, index=False)
            return cached_data
        
        # 如果缓存不存在，获取新数据
        data = self.analysis_engine.load_data(
            code=code,
            symbol_name=code,
            period_mode='day',
            start_date=start_date,
            end_date=end_date,
            period_config={
                'day': {
                    'ak_period': 'daily',
                    'buffer_ratio': '0.2',
                    'min_buffer': '10'
                }
            },
            ma_lines=[5, 10, 20],
            force_refresh=True
        )
        
        if not data.empty:
            # 重置索引，确保日期列存在
            data = data.reset_index()
            # 保存到缓存
            data.to_csv(cache_file, index=False)
        
        return data

    def _check_buy_conditions(self, data: pd.DataFrame, date: str) -> bool:
        """检查买入条件"""
        if data.empty:
            return False
            
        # 获取当日数据
        day_data = data[data['日期'] == date]
        if day_data.empty:
            return False
            
        close_price = day_data['收盘'].iloc[0]
        
        # 检查价格条件
        # 计算涨停价 = 开盘价 * (1 + 19.99%)
        limit_up_price = day_data['开盘'].iloc[0] * (1 + 0.1999)
        if close_price >= 100 or close_price >= limit_up_price * 0.999:
            return False

        # 获取当日和前一日数据
        date_obj = pd.to_datetime(date)
        two_days_data = data[data['日期'] <= date_obj].sort_values('日期', ascending=False).head(2)
        
        # 确保有两天的数据
        if len(two_days_data) < 2:
            return False
            
        # 检查必要的指标是否存在
        required_fields = ['平均成本', 'MA5']
        if not all(field in two_days_data.columns for field in required_fields):
            self.logger.error(f"数据缺少必要字段: {[f for f in required_fields if f not in two_days_data.columns]}")
            return False
            
        # 检查信号条件
        condition = CostCrossMaCondition()
        try:
            # 将DataFrame转换为字典列表，以适应条件检查的数据格式
            data_list = two_days_data.to_dict('records')
            signal = condition.check(data_list)
            
            if signal.triggered:
                self.logger.info(f"触发信号: {signal.description}")
                self.logger.info(f"当日成本: {two_days_data['平均成本'].iloc[0]:.2f}")
                self.logger.info(f"当日MA5: {two_days_data['MA5'].iloc[0]:.2f}")
            
            return signal.triggered and signal.id == 'ma05_cross_up_cost'
        except Exception as e:
            self.logger.error(f"信号检查失败: {e}")
            return False

    def run_backtest(self, start_date: str, end_date: Optional[str] = None):
        """运行回测
        
        Args:
            start_date: 开始日期,格式'YYYY-MM-DD'
            end_date: 结束日期,格式'YYYY-MM-DD',默认为当前日期
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
            
        self.logger.info(f"开始回测 {start_date} 到 {end_date}")
        
        # 获取股票列表
        stock_list = self._load_stock_list()
        self.logger.info(f"获取到 {len(stock_list)} 只创业板股票")
        
        # 创建线程池
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            # 并行加载历史数据
            future_to_stock = {
                executor.submit(self._load_history_data, code, start_date, end_date): code 
                for code in stock_list
            }
            
            # 使用tqdm显示进度
            with tqdm(total=len(future_to_stock), desc="加载历史数据") as pbar:
                # 收集结果
                for future in future_to_stock:
                    code = future_to_stock[future]
                    try:
                        data = future.result()
                        if not data.empty:
                            self.history_data[code] = data
                    except Exception as e:
                        self.logger.error(f"加载股票 {code} 数据失败: {e}")
                    pbar.update(1)
        
        # 按日期进行回测
        date_range = pd.date_range(start_date, end_date)
        for date in date_range:
            date_str = date.strftime('%Y-%m-%d')
            self._process_trading_day(date_str)
            
        # 生成回测报告
        self._generate_report()

    def _process_trading_day(self, date: str):
        """处理单个交易日"""
        # 处理卖出
        self._process_sells(date)
        
        # 处理买入
        self._process_buys(date)
        
        # 更新每日统计
        self._update_daily_stats(date)

    def _process_sells(self, date: str):
        """处理卖出操作"""
        if not self.positions:
            return
        
        date_obj = pd.to_datetime(date)
        sold_positions = []
        
        for code, position in self.positions.items():
            # 获取当日数据
            stock_data = self.history_data.get(code)
            if stock_data is None or stock_data.empty:
                continue
            
            # 获取当日行情
            day_data = stock_data[stock_data['日期'] == date_obj]
            if day_data.empty:
                continue
            
            close_price = day_data['收盘'].iloc[0]
            
            # 判断是否跌停
            if '跌停价' in day_data.columns and close_price <= day_data['跌停价'].iloc[0]:
                self.logger.info(f"{date} {code} 跌停，等待非跌停日卖出")
                continue
            
            # 计算收益
            buy_price = position['price']
            shares = position['shares']
            cost = position['cost']
            
            sell_amount = close_price * shares
            sell_fee = sell_amount * self.commission_rate  # 佣金
            profit = sell_amount - sell_fee - cost
            profit_rate = profit / cost * 100
            
            # 记录交易
            record = TradeRecord(
                date=date,
                code=code,
                name=position['name'],
                action='sell',
                price=close_price,
                shares=shares,
                amount=sell_amount,
                fee=sell_fee,
                profit=profit,
                profit_rate=profit_rate,
                reason="正常卖出"
            )
            self.trade_records.append(record)
            
            # 标记待清除的持仓
            sold_positions.append(code)
            
            self.logger.info(
                f"{date} 卖出 {code} {shares}股，"
                f"买入价 {buy_price:.2f}，卖出价 {close_price:.2f}，"
                f"收益率 {profit_rate:.2f}%"
            )
        
        # 清除已卖出的持仓
        for code in sold_positions:
            del self.positions[code]

    def _process_buys(self, date: str):
        """处理买入操作"""
        date_obj = pd.to_datetime(date)
        buy_candidates = []
        
        # 打印日期分隔线
        self.logger.info(f"\n{'='*50}\n{date} 交易日分析\n{'='*50}")
        
        # 筛选符合买入条件的股票
        for code, data in self.history_data.items():
            try:
                # 获取当日数据
                day_data = data[data['日期'] == date_obj]
                if day_data.empty:
                    continue
                    
                # 打印更多调试信息
                close_price = day_data['收盘'].iloc[0]
                limit_up_price = day_data['开盘'].iloc[0] * (1 + 0.1999)
                
                # 检查价格条件
                if close_price >= 100:
                    self.logger.debug(f"{code} 股价过高: {close_price:.2f}")
                    continue
                    
                if close_price >= limit_up_price * 0.999:
                    self.logger.debug(f"{code} 接近涨停: {close_price:.2f}/{limit_up_price:.2f}")
                    continue
                
                # 获取两天数据用于信号检查
                two_days_data = data[data['日期'] <= date_obj].sort_values('日期', ascending=False).head(2)
                if len(two_days_data) < 2:
                    self.logger.debug(f"{code} 数据不足两天")
                    continue
                    
                # 检查信号条件
                condition = CostCrossMaCondition()
                data_list = two_days_data.to_dict('records')
                signal = condition.check(data_list)
                
                if signal.triggered and signal.id == 'ma05_cross_up_cost':
                    name = day_data['名称'].iloc[0] if '名称' in day_data else code
                    self.logger.info(f"发现买入信号: {code} {name} "
                                   f"收盘价: {close_price:.2f} "
                                   f"信号: {signal.description}")
                    buy_candidates.append({
                        'code': code,
                        'name': name,
                        'price': close_price
                    })
                else:
                    self.logger.debug(f"{code} 未触发信号")
                    
            except Exception as e:
                self.logger.error(f"处理股票 {code} 时出错: {e}")
        
        # 打印候选股票汇总
        if buy_candidates:
            self.logger.info(f"\n今日共发现 {len(buy_candidates)} 只满足条件的股票:")
            for idx, candidate in enumerate(buy_candidates, 1):
                self.logger.info(f"{idx}. {candidate['code']} {candidate['name']} "
                               f"价格: {candidate['price']:.2f}")
        else:
            self.logger.info("\n今日无满足条件的股票")
        
        # 原有的买入逻辑
        if not buy_candidates:
            return
        
        # 按价格从低到高排序
        buy_candidates.sort(key=lambda x: x['price'])
        
        # 计算购买数量
        remaining_limit = self.daily_limit
        final_buys = {}  # 用字典存储每支股票的最终买入数量
        
        # 第一轮：每只股票分配基础份额
        for candidate in buy_candidates:
            code = candidate['code']
            price = candidate['price']
            base_amount = price * self.base_shares
            
            if base_amount <= remaining_limit:
                final_buys[code] = {
                    **candidate,
                    'shares': self.base_shares,
                    'amount': base_amount
                }
                remaining_limit -= base_amount
        
        # 第二轮：循环分配剩余资金，直到无法继续分配
        while remaining_limit > 0:
            allocated = False
            # 按价格从低到高遍历所有股票
            for code, buy in sorted(final_buys.items(), key=lambda x: x[1]['price']):
                price = buy['price']
                additional_shares = self.base_shares  # 每次追加100股
                additional_amount = price * additional_shares
                
                # 如果当前股票可以追加份额
                if additional_amount <= remaining_limit:
                    buy['shares'] += additional_shares
                    buy['amount'] = buy['price'] * buy['shares']  # 更新总金额
                    remaining_limit -= additional_amount
                    allocated = True
                    
                    self.logger.info(
                        f"追加分配: {code} 增加 {additional_shares}股, "
                        f"当前总股数 {buy['shares']}, 剩余资金 {remaining_limit:.2f}"
                    )
            
            # 如果本轮没有任何股票能够分配到份额，说明资金不足以再分配，退出循环
            if not allocated:
                break
        
        # 执行买入（现在每只股票只执行一次买入）
        for code, buy in final_buys.items():
            shares = buy['shares']
            price = buy['price']
            amount = price * shares
            fee = amount * self.commission_rate
            total_cost = amount + fee
            
            # 记录持仓
            self.positions[code] = {
                'name': buy['name'],
                'shares': shares,
                'price': price,
                'cost': total_cost,
                'buy_date': date
            }
            
            # 记录交易（现在每只股票只记录一次交易）
            record = TradeRecord(
                date=date,
                code=code,
                name=buy['name'],
                action='buy',
                price=price,
                shares=shares,
                amount=amount,
                fee=fee,
                reason="成本下穿5日线"
            )
            self.trade_records.append(record)
            
            self.logger.info(
                f"{date} 买入 {code} {shares}股，"
                f"价格 {price:.2f}，总金额 {total_cost:.2f}"
            )

    def _update_daily_stats(self, date: str):
        """更新每日统计数据"""
        # 获取当日交易记录
        day_records = [r for r in self.trade_records if r.date == date]
        
        # 计算当日统计数据
        buys = [r for r in day_records if r.action == 'buy']
        sells = [r for r in day_records if r.action == 'sell']
        
        total_buy_amount = sum(r.amount + r.fee for r in buys)
        total_sell_amount = sum(r.amount - r.fee for r in sells)
        total_profit = sum(r.profit for r in sells)
        avg_profit_rate = np.mean([r.profit_rate for r in sells]) if sells else 0
        
        # 更新每日统计
        self.daily_stats[date] = {
            'buy_count': len(buys),
            'sell_count': len(sells),
            'buy_amount': total_buy_amount,
            'sell_amount': total_sell_amount,
            'profit': total_profit,
            'profit_rate': avg_profit_rate,
            'positions': len(self.positions)
        }

    def _generate_report(self):
        """生成回测报告"""
        self.logger.info("开始生成回测报告...")
        
        # 1. 导出交易记录到CSV
        trades_file = os.path.join(self.results_dir, 'trade_records.csv')
        trades_df = pd.DataFrame([
            {
                '日期': r.date,
                '代码': r.code,
                '名称': r.name,
                '操作': r.action,
                '价格': r.price,
                '数量': r.shares,
                '金额': r.amount,
                '手续费': r.fee,
                '收益': r.profit,
                '收益率': r.profit_rate,
                '交易原因': r.reason
            }
            for r in self.trade_records
        ])
        trades_df.to_csv(trades_file, index=False, encoding='utf-8-sig')
        
        # 2. 计算统计指标
        stats = self._calculate_statistics()
        
        # 3. 生成收益率图表
        self._plot_performance_charts()
        
        # 4. 生成总结报告
        self._generate_summary_report(stats)

    def _calculate_statistics(self) -> dict:
        """计算回测统计指标"""
        # 提取所有卖出记录的收益率
        profit_rates = [r.profit_rate for r in self.trade_records if r.action == 'sell']
        daily_profits = pd.Series({k: v['profit'] for k, v in self.daily_stats.items()})
        daily_amounts = pd.Series({k: v['buy_amount'] for k, v in self.daily_stats.items()})
        
        # 计算基础统计指标
        stats = {
            '总交易次数': len(self.trade_records),
            '买入次数': len([r for r in self.trade_records if r.action == 'buy']),
            '卖出次数': len([r for r in self.trade_records if r.action == 'sell']),
            '总收益': sum(r.profit for r in self.trade_records if r.action == 'sell'),
            '平均收益率': np.mean(profit_rates) if profit_rates else 0,
            '收益率标准差': np.std(profit_rates) if profit_rates else 0,
            '最大单日收益': daily_profits.max() if not daily_profits.empty else 0,
            '最小单日收益': daily_profits.min() if not daily_profits.empty else 0,
            '最大单日买入金额': daily_amounts.max() if not daily_amounts.empty else 0,
            '胜率': len([r for r in profit_rates if r > 0]) / len(profit_rates) if profit_rates else 0,
        }
        
        # 计算高级指标
        if len(daily_profits) > 1:
            # 计算夏普比率 (假设无风险利率为3%)
            returns = daily_profits.pct_change()
            risk_free_rate = 0.03 / 252  # 日化无风险利率
            excess_returns = returns - risk_free_rate
            sharpe_ratio = np.sqrt(252) * excess_returns.mean() / returns.std() if returns.std() != 0 else 0
            
            # 计算最大回撤
            cumulative_returns = (1 + returns).cumprod()
            rolling_max = cumulative_returns.expanding().max()
            drawdowns = (cumulative_returns - rolling_max) / rolling_max
            max_drawdown = drawdowns.min()
            
            stats.update({
                '夏普比率': sharpe_ratio,
                '最大回撤': max_drawdown,
            })
        
        return stats

    def _plot_performance_charts(self):
        """绘制回测表现图表"""
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei']  # 设置中文显示
        plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
        
        # 创建图表
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 15))
        
        # 1. 累计收益曲线
        dates = list(self.daily_stats.keys())
        profits = [self.daily_stats[d]['profit'] for d in dates]
        cumulative_profits = np.cumsum(profits)
        
        ax1.plot(dates, cumulative_profits, 'b-', label='累计收益')
        ax1.set_title('累计收益曲线')
        ax1.set_xlabel('日期')
        ax1.set_ylabel('收益(元)')
        ax1.grid(True)
        ax1.legend()
        
        # 2. 每日交易量
        daily_trades = [self.daily_stats[d]['buy_count'] + self.daily_stats[d]['sell_count'] 
                       for d in dates]
        ax2.bar(dates, daily_trades, alpha=0.6, label='每日交易次数')
        ax2.set_title('每日交易量')
        ax2.set_xlabel('日期')
        ax2.set_ylabel('交易次数')
        ax2.grid(True)
        ax2.legend()
        
        # 3. 每日收益率分布
        daily_returns = [self.daily_stats[d]['profit_rate'] for d in dates]
        ax3.hist(daily_returns, bins=50, alpha=0.6, label='日收益率分布')
        ax3.set_title('收益率分布')
        ax3.set_xlabel('收益率(%)')
        ax3.set_ylabel('频次')
        ax3.grid(True)
        ax3.legend()
        
        # 调整布局并保存
        plt.tight_layout()
        plt.savefig(os.path.join(self.results_dir, 'performance_charts.png'))
        plt.close()

    def _generate_summary_report(self, stats: dict):
        """生成总结报告"""
        report_file = os.path.join(self.results_dir, 'summary_report.txt')
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("回测总结报告\n")
            f.write("=" * 50 + "\n\n")
            
            # 基本信息
            f.write("基本信息:\n")
            f.write("-" * 30 + "\n")
            f.write(f"总交易次数: {stats['总交易次数']}\n")
            f.write(f"买入次数: {stats['买入次数']}\n")
            f.write(f"卖出次数: {stats['卖出次数']}\n")
            f.write(f"胜率: {stats['胜率']:.2%}\n\n")
            
            # 收益信息
            f.write("收益统计:\n")
            f.write("-" * 30 + "\n")
            f.write(f"总收益: {stats['总收益']:.2f}元\n")
            f.write(f"平均收益率: {stats['平均收益率']:.2f}%\n")
            f.write(f"收益率标准差: {stats['收益率标准差']:.2f}%\n")
            f.write(f"最大单日收益: {stats['最大单日收益']:.2f}元\n")
            f.write(f"最小单日收益: {stats['最小单日收益']:.2f}元\n")
            f.write(f"最大单日买入金额: {stats['最大单日买入金额']:.2f}元\n\n")
            
            # 风险指标
            f.write("风险指标:\n")
            f.write("-" * 30 + "\n")
            f.write(f"夏普比率: {stats.get('夏普比率', 'N/A')}\n")
            f.write(f"最大回撤: {stats.get('最大回撤', 'N/A'):.2%}\n")
            
            self.logger.info(f"回测报告已生成: {report_file}")

STARTDATE = '2024-01-01'
def main():
    """主函数"""
    # 创建回测引擎实例
    engine = BacktestEngine()
    
    # 设置回测时间范围
    # 获取2024年第一个交易日
    try:
        # 获取2024年1月的交易日历
        trading_days = ak.tool_trade_date_hist_sina()
        trading_days['trade_date'] = pd.to_datetime(trading_days['trade_date'])
        # 找到2024年第一个交易日
        first_trading_day = trading_days[
            trading_days['trade_date'] >= STARTDATE
        ]['trade_date'].iloc[0]
        start_date = first_trading_day.strftime('%Y-%m-%d')
    except Exception as e:
        print(f"获取交易日历失败，使用默认日期: {e}")
        start_date = STARTDATE
    
    # 运行回测
    try:
        print(f"开始回测，起始日期: {start_date}")
        engine.run_backtest(start_date=start_date)
        print("回测完成，请查看results目录下的回测报告")
        
        # 打印回测结果文件路径
        results_dir = engine.results_dir
        print("\n生成的文件:")
        print(f"1. 交易记录: {os.path.join(results_dir, 'trade_records.csv')}")
        print(f"2. 绩效图表: {os.path.join(results_dir, 'performance_charts.png')}")
        print(f"3. 总结报告: {os.path.join(results_dir, 'summary_report.txt')}")
        print(f"4. 日志文件: {os.path.join(results_dir, 'backtest.log')}")
        
    except Exception as e:
        print(f"回测过程中出现错误: {e}")
        raise

if __name__ == "__main__":
    main() 