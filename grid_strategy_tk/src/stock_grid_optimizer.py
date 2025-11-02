import io
import threading
import tkinter as tk
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from tkinter import ttk
from typing import Any, Dict, List, Optional, Tuple

import akshare as ak
import numpy as np
import optuna
import pandas as pd
from akshare_wrapper import akshare
from grid_strategy import GridStrategy  # 导入GridStrategy类
from segment_utils import BATCH_TO_DAYS_MAP, build_segments


class GridStrategyOptimizer:
    """
    网格交易策略优化器
    
    算法说明：
    1. 优化目标
       - 通过调整网格参数最大化回测期间的收益率
       - 保证交易次数满足最小要求，避免过度拟合
       - 确保参数之间的合理关系（如回调率小于主要比率）
    
    2. 参数范围设定
       - 上涨卖出比率 (0.3% ~ 3%)：触发卖出的上涨幅度
       - 上涨回调比率 (0.1% ~ 1%)：确认卖出的回调幅度，不超过卖出比率的30%       
       - 下跌买入比率 (0.3% ~ 3%)：触发买入的下跌幅度
       - 下跌反弹比率 (0.1% ~ 1%)：确认买入的反弹幅度，不超过买入比率的30%
       - 单次交易股数 (1000 ~ 最大可交易股数)：根据资金和最少交易次数计算
    
    3. 优化流程
       a) 第一阶段（粗略搜索）
          - 使用较大的步长快速探索参数空间
          - 识别潜在的优势参数区域
          
       b) 第二阶段（精细搜索）
          - 在第一阶段发现的优势区域进行精细化搜索
          - 使用较小的步长寻找最优参数组合
    
    4. 约束条件
       - 价格范围限制：所有交易必须在指定价格区间内
       - 均线保护（可选）：根据MA均线调整价格范围
       - 资金约束：确保每次交易有足够的资金/持仓
       - 最少交易次数：通过调整单次交易股数确保
    
    5. 评估指标
       - 主要指标：策略收益率
       - 次要指标：交易次数、失败交易统计
    
    6. 特殊功能
       - 支持均线保护机制
       - 动态调整交易股数
       - 详细的交易记录和失败原因统计
    """
    # 添加类常量
    REBOUND_RATE_MAX_RATIO = 0.3  # 回调/反弹率相对于主要率的最大比例
    
    # 添加批次对应的天数映射
    BATCH_TO_DAYS_MAP = {
        1: 60,
        2: 30,
        3: 20,
        4: 10,
        5: 5
    }
    
    def __init__(self, symbol: str = "560610",
                 start_date: datetime = datetime(2024, 11, 1), 
                 end_date: datetime = datetime(2024, 12, 20),
                 security_type: str = "ETF",  # 新增参数：证券类型
                 ma_period: int = None,
                 ma_protection: bool = False,
                 initial_positions: int = 50000,
                 initial_cash: int = 50000,
                 min_buy_times: int = 2,  # 默认2次
                 price_range: tuple = (0.910, 1.010),
                 profit_calc_method: str = "mean",  # 新增：收益计算方法
                 connect_segments: bool = False):  # 新增：是否衔接资金和持仓
        
        # 先初始化基本参数
        self.start_date = start_date
        self.end_date = end_date
        self.security_type = security_type.upper()  # 转换为大写
        
        # 验证价格范围
        if not self._validate_price_range(price_range):
            raise ValueError(f"无效的价格范围: {price_range}")
        
        # 获取证券名称和初始价格
        try:
            if self.security_type == "ETF":
                # 获取ETF基金信息
                # 使用多API备用机制获取ETF数据
                from .etf_data_fetcher import get_etf_spot_data
                etf_df = get_etf_spot_data(use_cache=True)
                security_name = etf_df[etf_df['代码'] == symbol]['名称'].values[0]
                price_df = self._get_etf_price_data(symbol, start_date)
            else:
                # 获取股票信息
                stock_df = ak.stock_zh_a_spot_em()
                security_name = stock_df[stock_df['代码'] == symbol]['名称'].values[0]
                price_df = self._get_stock_price_data(symbol, start_date)
            
            if not price_df.empty:
                base_price = (price_df.iloc[0]['开盘'] + price_df.iloc[0]['收盘']) / 2
                print(f"使用开始日期的中间价格作为基准价: {base_price:.3f}")
            else:
                base_price = price_range[0]  # 使用价格范围的最小值作为默认值
                print(f"无法获取开始日期价格，使用默认基准价: {base_price}")
                
        except Exception as e:
            print(f"获取证券名称或价格失败: {e}")
            security_name = "未知证券"
            base_price = price_range[0]
        
        # 初始化固定参数
        self.fixed_params = {
            "symbol": symbol,
            "symbol_name": security_name,
            "security_type": self.security_type,
            "base_price": base_price,
            "price_range": price_range,
            "initial_positions": initial_positions,
            "initial_cash": initial_cash,
            "start_date": start_date,
            "end_date": end_date
        }
        
        # 如果开启均线保护且提供了均线周期，则更新价格范围
        if ma_protection and ma_period:
            ma_price = self._calculate_ma_price(ma_period)
            if ma_price:
                self._update_price_range_with_ma(ma_price)
        
        # 计算最大可交易股数
        base_price = self.fixed_params["base_price"]
        max_shares_by_cash = int(self.fixed_params["initial_cash"] / base_price)
        max_shares_by_times = int(self.fixed_params["initial_cash"] / 
                                  (min_buy_times * base_price))
        max_shares = min(max_shares_by_cash, max_shares_by_times)

        # 根据证券类型设置最小交易股数
        min_shares_per_trade = 1000 if self.security_type == "ETF" else 100
        if max_shares < min_shares_per_trade:
            max_shares = min_shares_per_trade



        print(f"基于初始资金计算的最大股数: {max_shares_by_cash}")
        print(f"基于最少买入次数计算的最大股数: {max_shares_by_times}")
        print(f"最终使用的最大交易股数: {max_shares}")
        
        # 根据证券类型设置不同的参数范围
        if self.security_type == "ETF":
            # ETF基金参数范围
            self.param_ranges = {
                "up_sell_rate": {
                    "min": 0.003,
                    "max": 0.03,
                    "step": 0.0005
                },
                "down_buy_rate": {
                    "min": 0.003,
                    "max": 0.03,
                    "step": 0.0005
                },
                "up_callback_rate": {
                    "min": 0.001,
                    "max": 0.01,
                    "step": 0.0005
                },
                "down_rebound_rate": {
                    "min": 0.001,
                    "max": 0.01,
                    "step": 0.0005
                },
                "shares_per_trade": {
                    "min": 1000,
                    "max": max_shares,
                    "step": 1000
                }
            }
        else:
            if symbol.startswith("300") :
                self.param_ranges = {
                    "up_sell_rate": {
                        "min": 0.003,
                        "max": 0.2,
                        "step": 0.0005
                    },
                    "down_buy_rate": {
                        "min": 0.003,
                        "max": 0.2,
                        "step": 0.0005
                    },
                    "up_callback_rate": {
                        "min": 0.001,
                        "max": 0.03,
                        "step": 0.0005
                    },
                    "down_rebound_rate": {
                        "min": 0.001,
                        "max": 0.03,
                        "step": 0.0005
                    },
                    "shares_per_trade": {
                        "min": 100,
                        "max": max_shares,
                        "step": 100
                    }
                }                
            else:
                # 股票参数范围
                self.param_ranges = {
                    "up_sell_rate": {
                        "min": 0.003,
                        "max": 0.1,
                        "step": 0.0005
                    },
                    "down_buy_rate": {
                        "min": 0.003,
                        "max": 0.1,
                        "step": 0.0005
                    },
                    "up_callback_rate": {
                        "min": 0.001,
                        "max": 0.03,
                        "step": 0.0005
                    },
                    "down_rebound_rate": {
                        "min": 0.001,
                        "max": 0.03,
                        "step": 0.0005
                    },
                    "shares_per_trade": {
                        "min": 100,
                        "max": max_shares,
                        "step": 100
                    }
                }

        self.progress_window = None  # 添加progress_window属性

        self.min_buy_times = min_buy_times
        self.profit_calc_method = profit_calc_method
        self.connect_segments = connect_segments
        
        # 获取交易日列表
        self.trading_days = self._get_trading_days(start_date, end_date)

    def _validate_price_range(self, price_range: tuple) -> bool:
        """
        验证价格范围是否有效
        @param price_range: (最小价格, 最大价格)的元组
        @return: 价格范围是否有效
        """
        try:
            min_price, max_price = price_range
            
            # 检查是否为数字
            if not (isinstance(min_price, (int, float)) and isinstance(max_price, (int, float))):
                print(f"价格范围必须是数字: {price_range}")
                return False
            
            # 检查是否为正数
            if min_price <= 0 or max_price <= 0:
                print(f"价格必须为正数: {price_range}")
                return False
            
            # 检查最小值是否小于最大值
            if min_price >= max_price:
                print(f"最小价格必须小于最大价格: {price_range}")
                return False
            
            return True
            
        except Exception as e:
            print(f"验证价格范围时发生错误: {e}")
            return False

    def _calculate_ma_price(self, ma_period: int) -> Optional[float]:
        """
        计算开始时间的均线价格
        @param ma_period: 均线周期
        @return: 计算得到的均线价格，失败时返回None
        """
        try:
            start_date_str = (self.start_date - timedelta(days=ma_period*2)).strftime('%Y%m%d')
            end_date_str = self.start_date.strftime('%Y%m%d')
            
            # 根据证券类型获取历史数据
            if self.fixed_params["security_type"] == "ETF":
                df = ak.fund_etf_hist_em(
                    symbol=self.fixed_params["symbol"],
                    start_date=start_date_str,
                    end_date=end_date_str,
                    adjust="qfq"
                )
            else:
                df = akshare.stock_zh_a_hist(
                    symbol=self.fixed_params["symbol"],
                    start_date=start_date_str,
                    end_date=end_date_str,
                    adjust="qfq"
                )
            
            # 确保日期列为索引且按时间升序排列
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.set_index('日期').sort_index()
            
            # 计算移动平均线
            df['MA'] = df['收盘'].rolling(window=ma_period).mean()
            
            # 获取开始日期的收盘价和均线价格
            start_date_data = df.loc[df.index <= self.start_date].iloc[-1]
            close_price = start_date_data['收盘']
            ma_price = start_date_data['MA']
            
            if np.isnan(ma_price):
                print(f"计算均线价格结果为 NaN，使用默认价格范围")
                return None
                
            print(f"开始日期 {self.start_date.strftime('%Y-%m-%d')} 的价格情况:")
            print(f"收盘价: {close_price:.3f}")
            print(f"{ma_period}日均线: {ma_price:.3f}")
            return (close_price, ma_price)
            
        except Exception as e:
            print(f"计算均线价格时发生错误: {e}")
            return None

    def _update_price_range_with_ma(self, price_data: Tuple[float, float]) -> None:
        """
        根据价格和均线的关系更新价格范围
        @param price_data: (收盘价, 均线价格)的元组
        """
        if not price_data:
            return
            
        close_price, ma_price = price_data
        default_range = self.fixed_params["price_range"]
        
        if close_price > ma_price:
            # 价格在均线上方，将均线价格设为最小值
            new_range = (ma_price, default_range[1])
            print(f"价格在均线上方，设置最小价格为均线价格: {ma_price:.3f}")
        else:
            # 价格在均线下方，将均线价格设为最大值
            new_range = (default_range[0], ma_price)
            print(f"价格在均线下方，设置最大价格为均线价格: {ma_price:.3f}")
            
        # 验证新的价格范围
        if self._validate_price_range(new_range):
            self.fixed_params["price_range"] = new_range
            print(f"更新后的价格范围: {new_range}")
        else:
            print(f"保持原有价格范围: {default_range}")

    def _get_trading_days(self, start_date: datetime, end_date: datetime) -> pd.DatetimeIndex:
        """获取交易日列表（剔除非交易日）"""
        try:
            df_calendar = ak.tool_trade_date_hist_sina()
            df_calendar['trade_date'] = pd.to_datetime(df_calendar['trade_date'])
            mask = (df_calendar['trade_date'] >= pd.to_datetime(start_date)) & \
                   (df_calendar['trade_date'] <= pd.to_datetime(end_date))
            trading_days_df = df_calendar.loc[mask].sort_values('trade_date')
            return pd.DatetimeIndex(trading_days_df['trade_date'].values)
        except Exception as e:
            print(f"获取交易日历失败: {e}")
            return pd.date_range(start=start_date, end=end_date, freq='B')

    def _build_segments(self) -> List[Tuple[datetime, datetime]]:
        """构建时间段"""
        return build_segments(
            start_date=self.fixed_params['start_date'],
            end_date=self.fixed_params['end_date'],
            min_buy_times=self.min_buy_times
        )

    def run_backtest(self, params: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """运行多段回测"""
        segments = self._build_segments()
        segment_results = []
        
        # 初始资金和持仓
        current_cash = self.fixed_params["initial_cash"]
        current_positions = self.fixed_params["initial_positions"]
        
        for i, (seg_start, seg_end) in enumerate(segments):
            strategy = GridStrategy(
                symbol=self.fixed_params["symbol"],
                symbol_name=self.fixed_params["symbol_name"]
            )
            
            # 设置固定参数
            strategy.base_price = self.fixed_params["base_price"]
            strategy.price_range = self.fixed_params["price_range"]
            
            # 根据是否衔接资金和持仓
            if self.connect_segments and i > 0:
                strategy.initial_positions = current_positions
                strategy.positions = current_positions
                strategy.initial_cash = current_cash
                strategy.cash = current_cash
            else:
                strategy.initial_positions = self.fixed_params["initial_positions"]
                strategy.positions = strategy.initial_positions
                strategy.initial_cash = self.fixed_params["initial_cash"]
                strategy.cash = strategy.initial_cash
            
            # 设置优化参数
            for param, value in params.items():
                setattr(strategy, param, value)
            
            # 获取月份过滤参数
            month_filter = int(self.progress_window.month_filter_var.get().strip()) if self.progress_window.month_filter_var.get().strip() else None
            
            # 执行回测
            try:
                profit_rate = strategy.backtest(
                    start_date=seg_start,
                    end_date=seg_end,
                    verbose=False,
                    month_filter=month_filter
                )
            except Exception as e:
                print(f"分段回测失败: {str(e)}")
                profit_rate = 0.0  # 失败的分段计为0收益
            
            # 记录本段结果
            segment_results.append({
                'start_date': seg_start,
                'end_date': seg_end,
                'month_filter': month_filter,
                'profit_rate': profit_rate,
                'trades': len(strategy.trades),
                'failed_trades': strategy.failed_trades
            })
            
            # 如果需要衔接，更新资金和持仓
            if self.connect_segments:
                current_cash = strategy.cash
                current_positions = strategy.positions
        
        # 计算综合收益率
        profit_rates = [r['profit_rate'] for r in segment_results]
        if self.profit_calc_method == "median":
            combined_profit = float(np.median(profit_rates))
        else:  # 默认使用平均值
            combined_profit = float(np.mean(profit_rates))
        
        # 汇总统计信息
        total_trades = sum(r['trades'] for r in segment_results)
        combined_failed_trades = {}
        for r in segment_results:
            for reason, count in r['failed_trades'].items():
                combined_failed_trades[reason] = combined_failed_trades.get(reason, 0) + count
        
        stats = {
            "profit_rate": combined_profit,
            "trade_count": total_trades,
            "failed_trades": combined_failed_trades,
            "segment_results": segment_results,
            "params": params,
            "backtest_period": {
                "start": self.fixed_params["start_date"].strftime('%Y-%m-%d'),
                "end": self.fixed_params["end_date"].strftime('%Y-%m-%d')
            }
        }
        
        return combined_profit, stats

    def objective(self, trial: optuna.Trial) -> float:
        """
        Optuna优化目标函数
        """
        # 先生成主要参数
        up_sell_rate = trial.suggest_float(
            "up_sell_rate",
            self.param_ranges["up_sell_rate"]["min"],
            self.param_ranges["up_sell_rate"]["max"],
            step=self.param_ranges["up_sell_rate"]["step"]
        )
        
        down_buy_rate = trial.suggest_float(
            "down_buy_rate",
            self.param_ranges["down_buy_rate"]["min"],
            self.param_ranges["down_buy_rate"]["max"],
            step=self.param_ranges["down_buy_rate"]["step"]
        )
        
        # 基于主要参数动态设置回调/反弹率的范围
        up_callback_max = min(
            up_sell_rate * self.REBOUND_RATE_MAX_RATIO,
            self.param_ranges["up_callback_rate"]["max"]
        )
        up_callback_min = self.param_ranges["up_callback_rate"]["min"]
        
        # 确保最大值不小于最小值
        if up_callback_max < up_callback_min:
            up_callback_max = up_callback_min
        
        up_callback_rate = trial.suggest_float(
            "up_callback_rate",
            up_callback_min,
            up_callback_max,
            step=self.param_ranges["up_callback_rate"]["step"]
        )
        
        down_rebound_max = min(
            down_buy_rate * self.REBOUND_RATE_MAX_RATIO,
            self.param_ranges["down_rebound_rate"]["max"]
        )
        down_rebound_min = self.param_ranges["down_rebound_rate"]["min"]
        
        # 确保最大值不小于最小值
        if down_rebound_max < down_rebound_min:
            down_rebound_max = down_rebound_min
        
        down_rebound_rate = trial.suggest_float(
            "down_rebound_rate",
            down_rebound_min,
            down_rebound_max,
            step=self.param_ranges["down_rebound_rate"]["step"]
        )
        
        shares_per_trade = trial.suggest_int(
            "shares_per_trade",
            self.param_ranges["shares_per_trade"]["min"],
            self.param_ranges["shares_per_trade"]["max"],
            step=self.param_ranges["shares_per_trade"]["step"]
        )
        
        params = {
            "up_sell_rate": up_sell_rate,
            "up_callback_rate": up_callback_rate,
            "down_buy_rate": down_buy_rate,            
            "down_rebound_rate": down_rebound_rate,
            "shares_per_trade": shares_per_trade
        }
        
        # 运行回测
        profit_rate, stats = self.run_backtest(params)
        
        # 记录中间结果
        trial.set_user_attr("trade_count", stats["trade_count"])
        trial.set_user_attr("failed_trades", str(stats["failed_trades"]))
        
        return -profit_rate  # 返回负值因为Optuna默认最小化

    def optimize(self, n_trials: int = 2000) -> Dict[str, Any]:
        """
        分阶段执行参数优化
        """
        total_trials = n_trials * 1.5  # 总试验次数（包括两个阶段）
        current_trial = 0

        def callback(study, trial):
            if self.progress_window:
                try:
                    nonlocal current_trial
                    current_trial += 1
                    # 检查是否需要取消优化
                    if not self.progress_window.optimization_running:
                        study.stop()  # 停止优化
                        return
                    # 计算总体进度
                    self.progress_window.update_progress(current_trial)
                except Exception as e:
                    print(f"进度更新失败: {e}")
                    study.stop()
        
        try:
            # 第一阶段：粗略搜索
            study = optuna.create_study(
                study_name="grid_strategy_optimization_phase1",
                direction="minimize",
                sampler=optuna.samplers.TPESampler(
                    seed=42,
                    n_startup_trials=100,
                    multivariate=True
                )
            )
            
            # 第一阶段优化
            study.optimize(self.objective, n_trials=n_trials, callbacks=[callback])
            
            # 检查是否被取消
            if self.progress_window and not self.progress_window.optimization_running:
                return None
            
            # 获取第一阶段最佳参数周围的范围
            best_params = study.best_params
            refined_ranges = self._get_refined_ranges(best_params)
            
            # 第二阶段：精细搜索
            study_refined = optuna.create_study(
                study_name="grid_strategy_optimization_phase2",
                direction="minimize",
                sampler=optuna.samplers.TPESampler(
                    seed=43,
                    n_startup_trials=50,
                    multivariate=True
                )
            )
            
            # 第二阶段优化
            study_refined.optimize(
                lambda trial: self._refined_objective(trial, refined_ranges), 
                n_trials=n_trials//2,
                callbacks=[callback]
            )
            
            # 只在优化仍在运行时更新最终进度
            if self.progress_window:
                try:
                    self.progress_window.update_progress(total_trials)
                except Exception:
                    pass
            
            return {
                "study": study,
                "sorted_trials": sorted(study.trials, key=lambda t: t.value)  # 按收益率排序
            }
            
        except Exception as e:
            print(f"优化过程发生错误: {e}")
            return None

    def _get_refined_ranges(self, best_params):
        """
        根据最佳参数缩小搜索范围
        """
        refined_ranges = {}
        for param, value in best_params.items():
            if param == "shares_per_trade":
                # 整数参数特殊处理
                refined_ranges[param] = {
                    "min": max(int(value * 0.8), self.param_ranges[param]["min"]),
                    "max": min(int(value * 1.2), self.param_ranges[param]["max"]),
                    "step": self.param_ranges[param]["step"]
                }
            else:
                # 浮点数参数处理
                refined_ranges[param] = {
                    "min": max(value * 0.8, self.param_ranges[param]["min"]),
                    "max": min(value * 1.2, self.param_ranges[param]["max"]),
                    "step": self.param_ranges[param]["step"]
                }
        return refined_ranges

    def _refined_objective(self, trial: optuna.Trial, refined_ranges: Dict[str, Dict[str, float]]) -> float:
        """
        精细搜索目标函数
        """
        # 先生成主要参数
        up_sell_rate = trial.suggest_float(
            "up_sell_rate",
            refined_ranges["up_sell_rate"]["min"],
            refined_ranges["up_sell_rate"]["max"],
            step=refined_ranges["up_sell_rate"]["step"]
        )
        
        down_buy_rate = trial.suggest_float(
            "down_buy_rate",
            refined_ranges["down_buy_rate"]["min"],
            refined_ranges["down_buy_rate"]["max"],
            step=refined_ranges["down_buy_rate"]["step"]
        )
        
        # 基于主要参数动态设置回调/反弹率的范围
        up_callback_max = min(
            up_sell_rate * self.REBOUND_RATE_MAX_RATIO,
            refined_ranges["up_callback_rate"]["max"]
        )
        up_callback_min = refined_ranges["up_callback_rate"]["min"]
        
        # 确保最大值不小于最小值
        if up_callback_max < up_callback_min:
            up_callback_max = up_callback_min
        
        up_callback_rate = trial.suggest_float(
            "up_callback_rate",
            up_callback_min,
            up_callback_max,
            step=refined_ranges["up_callback_rate"]["step"]
        )
        
        down_rebound_max = min(
            down_buy_rate * self.REBOUND_RATE_MAX_RATIO,
            refined_ranges["down_rebound_rate"]["max"]
        )
        down_rebound_min = refined_ranges["down_rebound_rate"]["min"]
        
        # 确保最大值不小于最小值
        if down_rebound_max < down_rebound_min:
            down_rebound_max = down_rebound_min
        
        down_rebound_rate = trial.suggest_float(
            "down_rebound_rate",
            down_rebound_min,
            down_rebound_max,
            step=refined_ranges["down_rebound_rate"]["step"]
        )
        
        shares_per_trade = trial.suggest_int(
            "shares_per_trade",
            refined_ranges["shares_per_trade"]["min"],
            refined_ranges["shares_per_trade"]["max"],
            step=refined_ranges["shares_per_trade"]["step"]
        )
        
        params = {
            "up_sell_rate": up_sell_rate,
            "up_callback_rate": up_callback_rate,            
            "down_buy_rate": down_buy_rate,            
            "down_rebound_rate": down_rebound_rate,
            "shares_per_trade": shares_per_trade
        }
        
        # 运行回测
        profit_rate, stats = self.run_backtest(params)
        
        # 记录中间结果
        trial.set_user_attr("trade_count", stats["trade_count"])
        trial.set_user_attr("failed_trades", str(stats["failed_trades"]))
        
        return -profit_rate

    def _combine_results(self, study: optuna.Study, study_refined: optuna.Study) -> Dict[str, Any]:
        """
        合并两个阶段的结果
        """
        # 获取最佳结果
        best_params = study.best_params
        best_value = -study.best_value
        best_trial = study.best_trial
        
        # 整理优化结果
        optimization_results = {
            "best_params": best_params,
            "best_profit_rate": best_value,
            "best_trade_count": best_trial.user_attrs["trade_count"],
            "best_failed_trades": eval(best_trial.user_attrs["failed_trades"]),
            "study": study,
            "study_refined": study_refined
        }
        
        return optimization_results

    def print_results(self, results: Dict[str, Any], top_n: int = 5) -> None:
        """打印优化结果"""
        # 创建一个StringIO对象来捕获输出
        output = io.StringIO()
        with redirect_stdout(output):
            print("\n=== 参数优化结果 ===")
            print(f"\n回测区间: {self.fixed_params['start_date'].strftime('%Y-%m-%d')} 至 "
                  f"{self.fixed_params['end_date'].strftime('%Y-%m-%d')}")
            
            print("\n=== 使用最佳参数运行详细回测 ===")
            # 使用最佳参数运行详细回测
            best_strategy = GridStrategy(
                symbol=self.fixed_params["symbol"],
                symbol_name=self.fixed_params["symbol_name"]
            )
            
            # 设置固定参数
            best_strategy.base_price = self.fixed_params["base_price"]
            best_strategy.price_range = self.fixed_params["price_range"]
            best_strategy.initial_positions = self.fixed_params["initial_positions"]
            best_strategy.positions = best_strategy.initial_positions
            best_strategy.initial_cash = self.fixed_params["initial_cash"]
            best_strategy.cash = best_strategy.initial_cash
            
            # 设置最佳参数
            best_strategy.up_sell_rate = results["best_params"]["up_sell_rate"]
            best_strategy.up_callback_rate = results["best_params"]["up_callback_rate"]
            best_strategy.down_buy_rate = results["best_params"]["down_buy_rate"]
            best_strategy.down_rebound_rate = results["best_params"]["down_rebound_rate"]
            best_strategy.shares_per_trade = results["best_params"]["shares_per_trade"]
            
            # 运行详细回测
            best_strategy.backtest(
                start_date=self.fixed_params["start_date"],
                end_date=self.fixed_params["end_date"],
                verbose=True  # 启用详细打印
            )
            
            # 获取所有试验结果
            trials = results["study"].trials
            
            # 使用参数组合作为键来去重
            unique_trials = {}
            for trial in trials:
                # 将参数值转换为元组作为字典键
                params_tuple = tuple((k, round(v, 6) if isinstance(v, float) else v) 
                                   for k, v in sorted(trial.params.items()))
                if params_tuple not in unique_trials or trial.value < unique_trials[params_tuple].value:
                    unique_trials[params_tuple] = trial
            
            # 对去重后的结果排序
            sorted_trials = sorted(unique_trials.values(), key=lambda t: t.value)[:top_n]
            
            # 定义需要转换为百分比的参数名称
            rate_params = ['up_sell_rate', 'down_buy_rate', 'up_callback_rate', 'down_rebound_rate']
            
            print(f"\n=== 前 {top_n} 个最佳参数组合（已去重） ===")
            for i, trial in enumerate(sorted_trials, 1):
                profit_rate = -trial.value  # 转换回正的收益率
                print(f"\n第 {i} 名:")
                print(f"收益率: {profit_rate:.2f}%")
                print(f"交易次数: {trial.user_attrs['trade_count']}")
                print("参数组合:")
                for param, value in trial.params.items():
                    if param in rate_params:
                        # 将rate类型参数转换为百分比显示
                        print(f"  {param}: {value*100:.2f}%")
                    else:
                        # 非rate类型参数保持原样显示
                        print(f"  {param}: {value}")
                print("失败交易统计:")
                failed_trades = eval(trial.user_attrs["failed_trades"])
                for reason, count in failed_trades.items():
                    if count > 0:
                        print(f"  {reason}: {count}次")
        
        # 获取捕获的输出
        captured_output = output.getvalue()
        
        # 同时打印到控制台
        print(captured_output)
        
        # 如果存在进度窗口，将输出存储到窗口对象中
        if self.progress_window:
            self.progress_window.capture_output(captured_output)
            # 启用查看交易详情按钮
            self.progress_window.root.after(0, self.progress_window.enable_trade_details_button)

    def _get_etf_price_data(self, symbol: str, date: datetime) -> pd.DataFrame:
        """获取ETF价格数据"""
        date_str = date.strftime('%Y%m%d')
        return ak.fund_etf_hist_em(
            symbol=symbol,
            start_date=date_str,
            end_date=date_str,
            adjust="qfq"
        )

    def _get_stock_price_data(self, symbol: str, date: datetime) -> pd.DataFrame:
        """获取股票价格数据"""
        date_str = date.strftime('%Y%m%d')
        return akshare.stock_zh_a_hist(
            symbol=symbol,
            start_date=date_str,
            end_date=date_str,
            adjust="qfq"
        )

    def _validate_params(self, params: Dict[str, float]) -> bool:
        """
        验证参数是否有效
        
        Args:
            params: 包含策略参数的字典
            
        Returns:
            bool: 参数是否有效
        """
        try:
            # 验证参数是否在有效范围内
            for param_name, value in params.items():
                if param_name not in self.param_ranges:
                    print(f"未知参数: {param_name}")
                    return False
                
                param_range = self.param_ranges[param_name]
                if value < param_range["min"] or value > param_range["max"]:
                    print(f"参数 {param_name} 的值 {value} 超出范围 [{param_range['min']}, {param_range['max']}]")
                    return False
            
            # 验证回调率和反弹率是否小于主要比率
            if params["up_callback_rate"] >= params["up_sell_rate"]:
                print("上涨回调率必须小于上涨卖出率")
                return False
                
            if params["down_rebound_rate"] >= params["down_buy_rate"]:
                print("下跌反弹率必须小于下跌买入率")
                return False
            
            # 验证交易股数是否为正整数
            if not isinstance(params["shares_per_trade"], (int, float)) or params["shares_per_trade"] <= 0:
                print("交易股数必须为正数")
                return False
            
            return True
            
        except Exception as e:
            print(f"参数验证过程中发生错误: {e}")
            return False
