import io
from contextlib import redirect_stdout
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd
from akshare_wrapper import akshare
from locales.localization import l


class GridStrategy:
    def __init__(self, symbol="560610", symbol_name="国开ETF"):
        self.symbol = symbol
        self.symbol_name = symbol_name
        self.base_price = None  # 移除硬编码的默认值
        self.price_range = None  # 移除硬编码的默认值
        self.up_sell_rate = 0.0045
        self.up_callback_rate = 0.01
        self.down_buy_rate = 0.01
        self.down_rebound_rate = 0.004
        self.shares_per_trade = 50000
        self.initial_positions = 50000
        self.positions = self.initial_positions
        self.initial_cash = 50000
        self.cash = self.initial_cash
        self.trades = []
        self.failed_trades = {
            "无持仓": 0,
            "卖出价格超范围": 0,
            "现金不足": 0,
            "买入价格超范围": 0
        }
        self.final_profit_rate = 0.0
        self.multiple_trade = True
        self.verbose = False
        self.ma_period = None
        self.ma_protection = False
        self.ma_data = None

    def _calculate_buy_prices(self, base_price):
        """
        计算买入触发价和执行价
        """
        trigger_price = base_price * (1 - self.down_buy_rate)
        exec_price = trigger_price * (1 + self.down_rebound_rate)
        return trigger_price, exec_price

    def _calculate_sell_prices(self, base_price):
        """
        计算卖出触发价和执行价
        """
        trigger_price = base_price * (1 + self.up_sell_rate)
        exec_price = trigger_price * (1 - self.up_callback_rate)
        return trigger_price, exec_price

    def _check_ma_protection(self, price, ma_price, is_buy):
        """
        检查均线保护条件
        仅作为价格区间调整的参考，不计入失败交易
        
        Args:
            price: 当前价格
            ma_price: 均线价格
            is_buy: 是否为买入操作
            
        Returns:
            bool: 是否满足均线保护条件
        """
        if not self.ma_protection or ma_price is None:
            return True
        
        if is_buy and price < ma_price:
            return False
        elif not is_buy and price > ma_price:
            return False
        return True

    def buy(self, price, time):
        """
        执行买入操作
        """
        # 验证日期格式
        try:
            if isinstance(time, pd.Timestamp):
                time = time.strftime('%Y-%m-%d')
            datetime.strptime(time, '%Y-%m-%d')
            # 检查是否是未来日期
            if datetime.strptime(time, '%Y-%m-%d') > datetime.now():
                if self.verbose:
                    print(f"不能在未来日期 {time} 进行交易")
                return False
        except ValueError:
            raise ValueError("无效的日期格式，应为 YYYY-MM-DD")
        
        # 检查均线保护
        if self.ma_protection and self.ma_data is not None:
            ma_price = self.ma_data[self.ma_data['日期'] == time]['MA5'].iloc[0]
            if not self._check_ma_protection(price, ma_price, True):
                if self.verbose:
                    print(f"均线保护：当前价格 {price:.3f} 低于均线 {ma_price:.3f}")
                return False
        
        # 首先验证价格是否在允许范围内
        if not (self.price_range[0] <= price <= self.price_range[1]):
            if self.verbose:
                print(f"买入价格 {price:.3f} 超出允许范围 {self.price_range}")
            self.failed_trades["买入价格超范围"] += 1
            return False
            
        amount = price * self.shares_per_trade
        if self.cash >= amount:
            self.positions += self.shares_per_trade
            self.cash -= amount
            self.trades.append({
                "时间": time,
                "操作": "买入",
                "价格": price,
                "数量": self.shares_per_trade,
                "金额": amount
            })
            return True
        else:
            if self.verbose:
                print(f"现金不足，需要 {amount:.2f}，当前现金 {self.cash:.2f}")
            self.failed_trades["现金不足"] += 1
            return False

    def sell(self, price, time):
        """
        执行卖出操作
        """
        # 验证日期格式
        try:
            if isinstance(time, pd.Timestamp):
                time = time.strftime('%Y-%m-%d')
            datetime.strptime(time, '%Y-%m-%d')
            # 检查是否是未来日期
            if datetime.strptime(time, '%Y-%m-%d') > datetime.now():
                if self.verbose:
                    print(f"不能在未来日期 {time} 进行交易")
                return False
        except ValueError:
            raise ValueError("无效的日期格式，应为 YYYY-MM-DD")
        
        # 检查均线保护
        if self.ma_protection and self.ma_data is not None:
            ma_price = self.ma_data[self.ma_data['日期'] == time]['MA5'].iloc[0]
            if not self._check_ma_protection(price, ma_price, False):
                if self.verbose:
                    print(f"均线保护：当前价格 {price:.3f} 高于均线 {ma_price:.3f}")
                return False
        
        # 首先验证价格是否在允许范围内
        if not (self.price_range[0] <= price <= self.price_range[1]):
            if self.verbose:
                print(f"卖出价格 {price:.3f} 超出允许范围 {self.price_range}")
            self.failed_trades["卖出价格超范围"] += 1
            return False
            
        if self.positions >= self.shares_per_trade:
            amount = price * self.shares_per_trade
            self.positions -= self.shares_per_trade
            self.cash += amount
            self.trades.append({
                "时间": time,
                "操作": "卖出",
                "价格": price,
                "数量": self.shares_per_trade,
                "金额": amount
            })
            return True
        else:
            if self.verbose:
                print(f"持仓不足，需要 {self.shares_per_trade}，当前持仓 {self.positions}")
            self.failed_trades["无持仓"] += 1
            return False

    def backtest(self, start_date=None, end_date=None, verbose=False, month_filter=None):
        """
        执行回测
        """
        # 参数验证
        if self.initial_cash < 0:
            raise ValueError("初始现金不能为负数")
        if self.initial_positions < 0:
            raise ValueError("初始持仓不能为负数")
        if self.price_range and self.price_range[0] > self.price_range[1]:
            raise ValueError("价格区间无效：最低价大于最高价")
        
        # 处理日期参数
        if start_date is None:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=20)
        else:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
            
            if start_date > end_date:
                raise ValueError("开始日期不能晚于结束日期")
        
        start_date_str = start_date.strftime('%Y%m%d')
        end_date_str = end_date.strftime('%Y%m%d')
        
        try:
            if verbose:
                print(f"\n=== {self.symbol_name}({self.symbol}) 回测报告 ===")
                print(f"回测区间: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
            
            # 根据证券类型获取历史数据
            if hasattr(self, 'security_type') and self.security_type == "STOCK":
                df = akshare.stock_zh_a_hist(
                    symbol=self.symbol,
                    start_date=start_date_str,
                    end_date=end_date_str,
                    adjust="qfq"
                )
            else:
                # 默认使用ETF数据接口
                df = ak.fund_etf_hist_em(
                    symbol=self.symbol,
                    start_date=start_date_str,
                    end_date=end_date_str,
                    adjust="qfq"
                )
            
            if df.empty:
                raise Exception("未获取到任何数据")
            
            # 转换日期列为datetime类型
            df['日期'] = pd.to_datetime(df['日期'])
            
            # 应用月份过滤
            if month_filter is not None and 1 <= month_filter <= 12:
                df = df[df['日期'].dt.month == month_filter]
                if df.empty:
                    if verbose:
                        print(f"警告: 在{start_date}至{end_date}范围内未找到{month_filter}月数据")
                    self.final_profit_rate = 0.0
                    return 0.0  # 返回0收益率而不是抛出异常
            
            df = df.reset_index(drop=True)
            last_trigger_price_up = self.base_price
            last_trigger_price_down = self.base_price
            
            for i, row in df.iterrows():
                daily_prices = [
                    (row['开盘'], '开盘'),
                    (row['最高'], '最高'),
                    (row['最低'], '最低'),
                    (row['收盘'], '收盘')
                ]
                
                trades_before = len(self.trades)
                
                if verbose:
                    print(f"\n=== {row['日期']} 行情 ===")
                    print(f"开盘: {row['开盘']:.3f}")
                    print(f"最高: {row['最高']:.3f}")
                    print(f"最低: {row['最低']:.3f}")
                    print(f"收盘: {row['收盘']:.3f}")
                
                for current_price, price_type in daily_prices:
                    if verbose:
                        print(f"\n检查{price_type}价格点: {current_price:.3f}")
                    
                    # 处理卖出逻辑
                    if self.positions > 0:
                        sell_trigger_price = last_trigger_price_up * (1 + self.up_sell_rate)
                        if current_price >= sell_trigger_price:
                            # 计算倍数
                            price_diff = (current_price - sell_trigger_price) / sell_trigger_price
                            multiple = int(price_diff / self.up_sell_rate) + 1 if self.multiple_trade else 1
                            multiple = min(multiple, self.positions // self.shares_per_trade)
                            
                            execute_price = sell_trigger_price * (1 - self.up_callback_rate)
                            if execute_price <= current_price:
                                for _ in range(multiple):
                                    if self.sell(execute_price, row['日期']):
                                        last_trigger_price_up = execute_price
                                        last_trigger_price_down = execute_price
                                        if verbose:
                                            print(f"触发卖出 - 触发价: {sell_trigger_price:.3f}, 执行价: {execute_price:.3f}")
                                            print(f"交易份额: {self.shares_per_trade * multiple}, 当前总持仓: {self.positions}")
                            else:
                                if verbose:
                                    print(f"\n无法卖出 - 执行价 {execute_price:.3f} 高于当前价格 {current_price:.3f}")
                                self.failed_trades["卖出价格超范围"] += 1
                    else:
                        if verbose:
                            print("\n无法卖出 - 当前无持仓")
                        self.failed_trades["无持仓"] += 1
                    
                    # 处理买入逻辑
                    buy_trigger_price = last_trigger_price_down * (1 - self.down_buy_rate)
                    if verbose:
                        print(f"\n当前价格: {current_price:.3f}")
                        print(f"上次触发价: {last_trigger_price_down:.3f}")
                        print(f"买入触发价: {buy_trigger_price:.3f}")
                    
                    if current_price <= buy_trigger_price:
                        price_diff = (buy_trigger_price - current_price) / buy_trigger_price
                        multiple = int(price_diff / self.down_buy_rate) + 1 if self.multiple_trade else 1
                        
                        execute_price = buy_trigger_price * (1 + self.down_rebound_rate)
                        required_cash = execute_price * self.shares_per_trade * multiple
                        
                        if self.cash >= required_cash and current_price <= execute_price:
                            for _ in range(multiple):
                                if self.buy(execute_price, row['日期']):
                                    last_trigger_price_down = execute_price
                                    if verbose:
                                        print(f"触发买入 - 触发价: {buy_trigger_price:.3f}, 执行价: {execute_price:.3f}")
                                        print(f"交易份额: {self.shares_per_trade * multiple}, 当前总持仓: {self.positions}")
                        else:
                            if verbose:
                                print(f"\n无法买入 - 所需资金 {required_cash:.2f}, 当前现金 {self.cash:.2f}")
                            self.failed_trades["现金不足"] += 1
                
                # 打印当日交易记录
                if verbose:
                    trades_after = len(self.trades)
                    if trades_after > trades_before:
                        print("\n当日交易:")
                        for trade in self.trades[trades_before:trades_after]:
                            print(f"{trade['操作']} - 价格: {trade['价格']:.3f}, 数量: {trade['数量']}, 金额: {trade['金额']:.2f}")
                    else:
                        print("\n当日无交易")
                    print(f"当日结束持仓: {self.positions}, 现金: {self.cash:.2f}")
            
            # 计算最终收益
            self.calculate_profit(df.iloc[-1]['收盘'], verbose)
            
            return self.final_profit_rate
            
        except Exception as e:
            print(f"回测过程中发生错误: {str(e)}")
            raise

    def calculate_profit(self, last_price, verbose=False):
        """
        计算并打印回测结果
        """
        initial_total = self.initial_cash + (self.initial_positions * self.base_price)
        final_assets = self.cash + (self.positions * last_price)
        profit = final_assets - initial_total
        self.final_profit_rate = (profit / initial_total) * 100
        
        if verbose:
            print("\n=== 回测结果 ===")
            print("策略参数:")
            print(f"基准价格: {self.base_price:.3f}")
            print(f"价格区间: {self.price_range[0]:.3f} - {self.price_range[1]:.3f}")
            print(f"每上涨卖出: {self.up_sell_rate*100:.2f}%")
            print(f"上涨回调: {self.up_callback_rate*100:.2f}%")            
            print(f"每下跌买入: {self.down_buy_rate*100:.2f}%")
            print(f"下跌反弹: {self.down_rebound_rate*100:.2f}%")
            print(f"单次交易股数: {self.shares_per_trade:,}")
            
            print("\n资金状况:")
            print(f"初始现金: {self.initial_cash:,.2f}")
            print(f"初始持仓: {self.initial_positions}股 (按{self.base_price:.3f}元计算)")
            print(f"初始总资产: {initial_total:,.2f}")
            print(f"最终现金: {self.cash:,.2f}")
            print(f"最终持仓: {self.positions}股 (按{last_price:.3f}元计算)")
            print(f"最终总资产: {final_assets:,.2f}")
            print(f"总收益: {profit:,.2f}")
            print(f"收益率: {self.final_profit_rate:.2f}%")
            
            print("\n=== 交易统计 ===")
            print(f"成功交易次数: {len(self.trades)}")
            
            print("\n未成交统计:")
            for reason, count in self.failed_trades.items():
                if count > 0:
                    print(f"{reason}: {count}")
            
            if len(self.trades) > 0:
                print(f"\n=== {self.symbol_name}({self.symbol}) 交易记录 ===")
                df_trades = pd.DataFrame(self.trades)
                print(df_trades)
        
        return self.final_profit_rate

    def run_strategy_details(self, strategy_params, start_date, end_date, segments=None, month_filter=None):
        """
        运行策略详情分析
        
        Args:
            strategy_params (dict): 策略参数字典
            start_date (datetime): 开始日期
            end_date (datetime): 结束日期
            segments (list, optional): 时间段列表，每个元素为(start_date, end_date)元组
            month_filter (int, optional): 月份过滤
            
        Returns:
            dict: 包含以下键的字典：
                - total_profit (float): 总收益率
                - total_trades (int): 总交易次数
                - failed_trades_summary (dict): 失败交易统计
                - segment_results (list): 每个时间段的结果列表
                - output (str): 详细输出信息
        """
        # 初始化结果
        total_profit = 0
        total_trades = 0
        failed_trades_summary = {}
        segment_results = []
        all_output = []
        
        # 如果没有提供时间段，则使用单一时间段
        if not segments:
            segments = [(start_date, end_date)]
        
        # 遍历每个时间段
        for seg_start, seg_end in segments:
            # 重置策略参数
            for param, value in strategy_params.items():
                setattr(self, param, value)
            
            # 重置初始状态
            self.cash = self.initial_cash
            self.positions = self.initial_positions
            self.trades = []
            self.failed_trades = {
                "无持仓": 0,
                "卖出价格超范围": 0,
                "现金不足": 0,
                "买入价格超范围": 0
            }
            
            # 捕获输出
            output = io.StringIO()
            with redirect_stdout(output):
                # 运行回测并获取收益率
                profit_rate = self.backtest(seg_start, seg_end, verbose=True, month_filter=month_filter)
            
            # 收集当前段的结果
            segment_result = {
                'start_date': seg_start.strftime('%Y-%m-%d'),
                'end_date': seg_end.strftime('%Y-%m-%d'),
                'profit_rate': profit_rate,
                'trades': len(self.trades),
                'failed_trades': self.failed_trades.copy()
            }
            
            # 计算统计信息
            total_profit += profit_rate
            total_trades += len(self.trades)
            for reason, count in self.failed_trades.items():
                failed_trades_summary[reason] = failed_trades_summary.get(reason, 0) + count
            
            # 保存输出和段结果
            all_output.append(output.getvalue())
            segment_results.append(segment_result)
        
        return {
            'total_profit': total_profit,
            'total_trades': total_trades,
            'failed_trades_summary': failed_trades_summary,
            'segment_results': segment_results,
            'output': '\n'.join(all_output)
        }

    def format_trade_details(self, results, enable_segments=False, segments=None, profit_calc_method="mean"):
        """
        格式化交易详情显示内容
        
        Args:
            results (dict): run_strategy_details返回的结果字典
            enable_segments (bool): 是否启用分段回测
            segments (list): 时间段列表
            profit_calc_method (str): 收益计算方法，"mean"或"median"
            
        Returns:
            list: 包含所有显示内容的列表，每个元素是一行文本
        """
        output_lines = []
        
        # 显示分段结果
        if enable_segments:
            for i, segment in enumerate(results['segment_results'], 1):
                output_lines.append(f"\n{'='*20} 分段 {i} 回测 {'='*20}")
                output_lines.append(f"时间段: {segment['start_date']} 至 {segment['end_date']}\n")
        
        # 显示详细输出
        output_lines.append(results['output'])
        
        # 如果是多段回测，显示汇总信息
        if enable_segments and segments and len(segments) > 1:
            output_lines.append("\n=== 多段回测汇总 ===")
            output_lines.append(f"总段数: {len(segments)}")
            
            # 根据收益计算方式显示
            if profit_calc_method == "mean":
                avg_profit = results['total_profit'] / len(segments)
                output_lines.append(f"平均收益率: {avg_profit:.2f}%")
            else:  # 中值
                output_lines.append(f"中位数收益率: {results['total_profit']:.2f}%")
            
            output_lines.append(f"总交易次数: {results['total_trades']}")
            output_lines.append("\n失败交易统计:")
            for reason, count in results['failed_trades_summary'].items():
                if count > 0:
                    output_lines.append(f"{reason}: {count} 次")
        
        return output_lines

    def format_trial_details(self, trial):
        """
        格式化试验结果的显示内容
        
        Args:
            trial: Optuna试验对象，包含参数和结果
            
        Returns:
            list: 包含所有显示内容的列表，每个元素是一行文本
        """
        output_lines = []
        
        # 获取收益率
        profit_rate = -trial.value
        
        # 显示参数组合信息
        output_lines.append(l("param_combination_details"))
        output_lines.append(l("total_profit_rate_format").format(profit_rate=profit_rate))
        output_lines.append("")
        
        # 参数名称映射
        param_names = {
            'up_sell_rate': l("up_sell_rate"),
            'up_callback_rate': l("up_callback_rate"),            
            'down_buy_rate': l("down_buy_rate"),
            'down_rebound_rate': l("down_rebound_rate"),
            'shares_per_trade': l("shares_per_trade")
        }
        
        # 显示参数详情
        output_lines.append(l("param_details"))
        for key, value in trial.params.items():
            if key == 'shares_per_trade':
                output_lines.append(f"{param_names[key]}: {value:,}")
            else:
                output_lines.append(f"{param_names[key]}: {value*100:.2f}%")
        
        # 显示交易统计信息
        output_lines.append(f"\n{l('trade_count_format').format(count=trial.user_attrs.get('trade_count', 'N/A'))}")
        
        # 显示分段回测结果（如果有）
        if 'segment_results' in trial.user_attrs:
            output_lines.append(f"\n=== {l('segment_backtest_details')} ===")
            for i, segment in enumerate(trial.user_attrs['segment_results'], 1):
                output_lines.append(f"\n{l('segment_format').format(num=i)}:")
                output_lines.append(l("time_period_format").format(
                    start_date=segment['start_date'],
                    end_date=segment['end_date']
                ))
                output_lines.append(l("profit_rate_format").format(profit_rate=segment['profit_rate']))
                output_lines.append(l("trade_count_format").format(count=segment['trades']))
                
                # 显示失败交易统计（如果有）
                if segment.get('failed_trades'):
                    output_lines.append(f"\n{l('failed_trade_statistics')}:")
                    for reason, count in segment['failed_trades'].items():
                        if count > 0:
                            output_lines.append(l("failed_trade_count_format").format(
                                reason=reason,
                                count=count
                            ))
                            
        return output_lines

if __name__ == "__main__":
    strategy = GridStrategy()
    # 可以指定日期范围
    strategy.backtest('2024-10-15', '2024-12-20')
    # 或使用默认的最近20天
    # strategy.backtest()