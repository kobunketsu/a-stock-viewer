import csv
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

import akshare as ak
import pandas as pd


class ExportService:
    """ETF数据导出服务"""
    
    @staticmethod
    def export_chart_data(code: str) -> Optional[str]:
        """导出K线图数据
        Args:
            code: ETF代码
        Returns:
            str: 合并后的文件路径,失败返回None
        """
        try:
            # 确保导出目录存在
            export_dir = os.path.join("data", "export")
            os.makedirs(export_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            daily_filename = f"{code}_daily_data_{timestamp}.csv"
            weekly_filename = f"{code}_weekly_data_{timestamp}.csv"
            monthly_filename = f"{code}_monthly_data_{timestamp}.csv"
            # 添加上证指数文件名
            sh_index_filename = f"sh000001_daily_data_{timestamp}.csv"
            
            daily_filepath = os.path.join(export_dir, daily_filename)
            weekly_filepath = os.path.join(export_dir, weekly_filename)
            monthly_filepath = os.path.join(export_dir, monthly_filename)
            sh_index_filepath = os.path.join(export_dir, sh_index_filename)

            # 获取平均成本数据时添加调试信息
            try:
                print("开始获取平均成本数据...")
                cyq_data = ak.stock_cyq_em(symbol=code, adjust="")
                print(f"cyq_data columns: {cyq_data.columns.tolist()}")
                print(f"cyq_data head:\n{cyq_data.head()}")
                
                if not cyq_data.empty:
                    cost_df = cyq_data[['日期', '平均成本']].copy()  # 使用copy()避免SettingWithCopyWarning
                    cost_df['日期'] = pd.to_datetime(cost_df['日期'])
                    cost_df = cost_df.set_index('日期')
                    print(f"处理后的cost_df head:\n{cost_df.head()}")
                else:
                    print("cyq_data 为空")
                    cost_df = pd.DataFrame()
            except Exception as e:
                print(f"获取平均成本数据出错: {str(e)}")
                cost_df = pd.DataFrame()
            
            # 获取各周期数据（添加重试机制）
            max_retries = 3
            retry_delay = 2  # 秒
            
            daily_data = None
            for attempt in range(max_retries):
                try:
                    print(f"尝试获取日线数据 (第{attempt + 1}次)...")
                    daily_data = ak.fund_etf_hist_em(
                        symbol=code,
                        period='daily',
                        adjust="qfq"
                    )
                    print(f"成功获取日线数据，长度: {len(daily_data)}")
                    break
                except Exception as e:
                    print(f"获取日线数据失败 (第{attempt + 1}次): {str(e)}")
                    if attempt < max_retries - 1:
                        print(f"等待{retry_delay}秒后重试...")
                        import time
                        time.sleep(retry_delay)
                    else:
                        print("获取日线数据失败，使用空DataFrame")
                        daily_data = pd.DataFrame()
            
            # 合并数据时添加调试信息
            if not cost_df.empty:
                print("\n合并前daily_data:")
                print(f"daily_data columns: {daily_data.columns.tolist()}")
                print(f"daily_data head:\n{daily_data.head()}")
                
                daily_data = daily_data.copy()  # 使用copy()避免SettingWithCopyWarning
                daily_data['日期'] = pd.to_datetime(daily_data['日期'])
                daily_data = daily_data.set_index('日期')
                daily_data = daily_data.join(cost_df['平均成本'])
                
                
                print("\n合并后daily_data:")
                print(f"daily_data columns: {daily_data.columns.tolist()}")
                print(f"daily_data head:\n{daily_data.head()}")
            
            # 获取周线数据
            weekly_data = None
            for attempt in range(max_retries):
                try:
                    print(f"尝试获取周线数据 (第{attempt + 1}次)...")
                    weekly_data = ak.fund_etf_hist_em(
                        symbol=code,
                        period='weekly',
                        adjust="qfq"
                    )
                    print(f"成功获取周线数据，长度: {len(weekly_data)}")
                    break
                except Exception as e:
                    print(f"获取周线数据失败 (第{attempt + 1}次): {str(e)}")
                    if attempt < max_retries - 1:
                        print(f"等待{retry_delay}秒后重试...")
                        import time
                        time.sleep(retry_delay)
                    else:
                        print("获取周线数据失败，使用空DataFrame")
                        weekly_data = pd.DataFrame()
            
            # 获取月线数据
            monthly_data = None
            for attempt in range(max_retries):
                try:
                    print(f"尝试获取月线数据 (第{attempt + 1}次)...")
                    monthly_data = ak.fund_etf_hist_em(
                        symbol=code,
                        period='monthly',
                        adjust="qfq"
                    )
                    print(f"成功获取月线数据，长度: {len(monthly_data)}")
                    break
                except Exception as e:
                    print(f"获取月线数据失败 (第{attempt + 1}次): {str(e)}")
                    if attempt < max_retries - 1:
                        print(f"等待{retry_delay}秒后重试...")
                        import time
                        time.sleep(retry_delay)
                    else:
                        print("获取月线数据失败，使用空DataFrame")
                        monthly_data = pd.DataFrame()
            
            # 检查是否有任何数据可用
            if daily_data.empty and weekly_data.empty and monthly_data.empty:
                print("警告：所有数据获取都失败，无法导出")
                return None
            
            # 至少有一个数据源可用就继续
            available_data = []
            if not daily_data.empty:
                available_data.append("日线")
            if not weekly_data.empty:
                available_data.append("周线")
            if not monthly_data.empty:
                available_data.append("月线")
            
            print(f"可用数据源: {', '.join(available_data)}")
            
            # 处理各周期数据
            def process_data(df: pd.DataFrame) -> pd.DataFrame:
                if not isinstance(df.index, pd.DatetimeIndex):
                    df = df.copy()  # 使用copy()避免SettingWithCopyWarning
                    df['日期'] = pd.to_datetime(df['日期'])
                    df = df.set_index('日期')
                return df.sort_index(ascending=False)
            
            daily_data = process_data(daily_data)
            weekly_data = process_data(weekly_data)
            monthly_data = process_data(monthly_data)
            
            # 过滤有效交易数据（成交量>0）
            valid_daily = daily_data[daily_data['成交量'] > 0]
            valid_weekly = weekly_data[weekly_data['成交量'] > 0]
            valid_monthly = monthly_data[monthly_data['成交量'] > 0]
            
            # 获取所需数据（包含额外数据用于KDJ计算）
            def get_recent_data(df: pd.DataFrame, count: int, extra: int = 9) -> pd.DataFrame:
                """获取最近的交易数据，额外包含用于计算KDJ的数据"""
                total_count = count + extra * 2  # 前后各保留extra条数据
                recent = df.head(total_count)
                return recent.sort_index()
            
            recent_daily = get_recent_data(valid_daily, 60)
            recent_weekly = get_recent_data(valid_weekly, 20)
            recent_monthly = get_recent_data(valid_monthly, 12)
            
            # 准备表头（移除成交额）
            headers = [
                "日期", "开盘", "最高", "最低", "收盘", 
                "涨跌幅", "振幅", 
                "成交量(万)",  
                "换手率",
                "平均成本",
            ]
            # 添加MA线表头
            ma_lines = [5, 10, 20]
            for ma in ma_lines:
                headers.append(f"MA{ma}")
            # 添加KDJ表头
            headers += ["KDJ(9,3,3)"]
            
            # 导出数据
            def export_period_data(data: pd.DataFrame, filepath: str, period_name: str, required_count: int) -> Optional[pd.DataFrame]:
                """导出指定周期的数据"""
                try:
                    # 计算指标
                    data_with_indicators = ExportService._export_data_to_csv(data, filepath, headers, period_name)
                    # 只保留需要的记录数
                    if len(data_with_indicators) > required_count:
                        data_with_indicators = data_with_indicators.head(required_count)
                    return data_with_indicators
                except Exception as e:
                    raise Exception(f"导出{period_name}数据失败: {str(e)}")
            
            # 导出各周期数据（只导出可用的数据）
            if not recent_daily.empty:
                try:
                    export_period_data(recent_daily, daily_filepath, 'day', 60)
                    print("日线数据导出成功")
                except Exception as e:
                    print(f"日线数据导出失败: {str(e)}")
            else:
                print("跳过日线数据导出（数据为空）")
            
            if not recent_weekly.empty:
                try:
                    export_period_data(recent_weekly, weekly_filepath, 'week', 20)
                    print("周线数据导出成功")
                except Exception as e:
                    print(f"周线数据导出失败: {str(e)}")
            else:
                print("跳过周线数据导出（数据为空）")
            
            if not recent_monthly.empty:
                try:
                    export_period_data(recent_monthly, monthly_filepath, 'month', 12)
                    print("月线数据导出成功")
                except Exception as e:
                    print(f"月线数据导出失败: {str(e)}")
            else:
                print("跳过月线数据导出（数据为空）")
            
            # 获取上证指数数据
            try:
                # 获取上证指数数据
                sh_index_data = ak.index_zh_a_hist(
                    symbol="000001",
                    period="daily",
                    start_date=(datetime.now() - timedelta(days=120)).strftime("%Y%m%d"),  # 获取足够的数据以确保有60个交易日
                    end_date=datetime.now().strftime("%Y%m%d")
                )
                
                if not sh_index_data.empty:
                    # 处理日期格式
                    sh_index_data = sh_index_data.copy()  # 使用copy()避免SettingWithCopyWarning
                    sh_index_data['日期'] = pd.to_datetime(sh_index_data['日期'])
                    sh_index_data = sh_index_data.set_index('日期')
                    sh_index_data = sh_index_data.sort_index(ascending=False)
                    
                    # 过滤有效交易数据
                    valid_sh_index = sh_index_data[sh_index_data['成交量'] > 0]
                    
                    # 获取最近60个交易日数据
                    recent_sh_index = valid_sh_index.head(60)
                    
                    # 准备上证指数表头
                    sh_index_headers = [
                        "日期", "开盘", "收盘", "最高", "最低", 
                        "涨跌幅", "振幅", 
                        "成交量(亿)", "换手率"  # 修改成交量单位为亿
                    ]
                    
                    # 导出上证指数数据
                    ExportService._export_index_data_to_csv(recent_sh_index, sh_index_filepath, sh_index_headers)
                    
                else:
                    print("获取上证指数数据失败")
                
            except Exception as e:
                print(f"导出上证指数数据时发生错误: {str(e)}")
            
            # 添加导出新闻数据的功能
            try:
                # 生成新闻数据文件名
                news_filename = f"{code}_news_{timestamp}.csv"
                news_filepath = os.path.join(export_dir, news_filename)
                
                # 获取个股新闻数据
                news_df = ak.stock_news_em(symbol=code)
                
                if not news_df.empty:
                    # 转换日期格式并设置为索引
                    news_df = news_df.copy()  # 使用copy()避免SettingWithCopyWarning
                    news_df['发布时间'] = pd.to_datetime(news_df['发布时间'])
                    news_df = news_df.set_index('发布时间')
                    news_df = news_df.sort_index(ascending=False)
                    
                    # 过滤最近一周的新闻
                    one_week_ago = datetime.now() - timedelta(days=7)
                    recent_news = news_df[news_df.index >= one_week_ago]
                    
                    if not recent_news.empty:
                        # 准备新闻数据表头
                        news_headers = ["日期时间", "新闻标题", "新闻链接"]
                        
                        # 准备导出数据
                        news_export_data: List[List[str]] = []
                        for idx, row in recent_news.iterrows():
                            if isinstance(idx, pd.Timestamp):  # 类型检查
                                news_row = [
                                    idx.strftime("%Y-%m-%d %H:%M:%S"),
                                    row['新闻标题'],
                                    row['新闻链接']
                                ]
                                news_export_data.append(news_row)
                        
                        # 写入CSV文件
                        with open(news_filepath, "w", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f)
                            writer.writerow(news_headers)
                            writer.writerows(news_export_data)
                        
                        print(f"成功导出{len(news_export_data)}条新闻数据")
                    else:
                        print("最近一周没有相关新闻")
                else:
                    print("未获取到新闻数据")
                    
            except Exception as e:
                print(f"导出新闻数据时发生错误: {str(e)}")
            
            # 添加分时数据导出
            try:
                # 生成分时数据文件名
                intraday_filename = f"{code}_intraday_{timestamp}.csv"
                intraday_filepath = os.path.join(export_dir, intraday_filename)
                
                # 获取分时数据
                try:
                    intraday_df = ak.stock_intraday_em(symbol=code)
                    print(f"成功获取分时数据，长度: {len(intraday_df)}")
                except Exception as e:
                    print(f"获取分时数据失败: {str(e)}")
                    print("跳过分时数据导出，继续其他数据导出")
                    intraday_df = pd.DataFrame()  # 创建空DataFrame
                
                if not intraday_df.empty:
                    # 数据预处理
                    # 1. 确保时间列格式正确
                    intraday_df = intraday_df.copy()  # 使用copy()避免SettingWithCopyWarning
                    intraday_df['时间'] = pd.to_datetime(intraday_df['时间']).dt.strftime('%H:%M')
                    
                    # 2. 转换买卖盘性质的显示格式
                    nature_map = {
                        '买盘': '买',
                        '卖盘': '卖',
                        '中性盘': '平'
                    }
                    intraday_df['买卖盘性质'] = intraday_df['买卖盘性质'].map(nature_map)
                    
                    # 3. 按时间分组,合并同一分钟内的所有数据
                    # 计算买卖盘统计信息
                    time_grouped = intraday_df.groupby('时间').agg({
                        '成交价': ['last', 'mean', 'max', 'min'],  # 最后价格、平均价格、最高价、最低价
                        '手数': 'sum',  # 总手数
                        '买卖盘性质': lambda x: (x == '买').sum()  # 买盘次数
                    }).reset_index()
                    
                    # 展平列名
                    time_grouped.columns = ['时间', '成交价', '平均价', '最高价', '最低价', '总手数', '买盘次数']
                    
                    # 计算卖盘次数和买卖盘性质
                    time_grouped['卖盘次数'] = intraday_df.groupby('时间').size() - time_grouped['买盘次数']
                    time_grouped['买卖盘性质'] = time_grouped.apply(
                        lambda row: '买' if row['买盘次数'] > row['卖盘次数'] 
                        else '卖' if row['卖盘次数'] > row['买盘次数'] 
                        else '平', axis=1
                    )
                    
                    # 使用合并后的数据
                    grouped_df = time_grouped[['时间', '成交价', '总手数', '买卖盘性质']].copy()
                    grouped_df = grouped_df.rename(columns={'总手数': '手数'})
                    
                    # 添加平均成本列（暂时为空，后续可以集成成本数据）
                    grouped_df['平均成本'] = ''
                    
                    # 4. 按时间排序
                    grouped_df = grouped_df.sort_values('时间')
                    
                    # 5. 计算RSI指标
                    try:
                        from indicators import (calculate_intraday_rsi,
                                                calculate_rsi)

                        # 创建用于RSI计算的数据框
                        # 按时间分组，获取每个时间点的最后成交价
                        price_df = intraday_df.groupby('时间')['成交价'].last().reset_index()
                        price_df = price_df.copy()  # 使用copy()避免SettingWithCopyWarning
                        price_df['时间'] = pd.to_datetime(price_df['时间'], format='%H:%M')
                        price_df = price_df.set_index('时间')
                        price_df = price_df.rename(columns={'成交价': 'close'})
                        
                        # 添加开盘价、最高价、最低价（使用成交价）
                        price_df['open'] = price_df['close']
                        price_df['high'] = price_df['close']
                        price_df['low'] = price_df['close']
                        price_df['volume'] = 0  # 分时数据没有成交量信息
                        
                        print(f"分时价格数据长度: {len(price_df)}")
                        
                        # 计算1分钟RSI6
                        rsi_1min_6 = calculate_rsi(price_df, period=6, price_col="close")
                        
                        # 计算5分钟RSI6
                        # 将1分钟数据重采样为5分钟
                        price_df_5min = price_df.resample('5T', offset='1min').agg({
                            'open': 'first',
                            'close': 'last',
                            'high': 'max',
                            'low': 'min',
                            'volume': 'sum'
                        }).dropna()
                        
                        # 获取历史数据用于5分钟RSI6计算
                        # 这里使用前一交易日的最后5根5分钟K线作为历史数据
                        # 由于无法获取历史数据，我们使用当前数据的前5根作为历史数据
                        if len(price_df_5min) >= 5:
                            # 使用前5根作为历史数据
                            historical_5min = price_df_5min.head(5)
                            combined_5min = pd.concat([historical_5min, price_df_5min])
                            
                            # 计算5分钟RSI6
                            rsi_5min_6_combined = calculate_intraday_rsi(combined_5min, period=6, price_col="close")
                            rsi_5min_6 = rsi_5min_6_combined.iloc[len(historical_5min):]
                            
                            # 插值到1分钟
                            rsi_5min_6_1min = rsi_5min_6.reindex(price_df.index, method='ffill')
                        else:
                            # 数据不足时，使用前一交易日收盘价
                            rsi_5min_6_1min = calculate_intraday_rsi(price_df_5min, period=6, price_col="close")
                            rsi_5min_6_1min = rsi_5min_6_1min.reindex(price_df.index, method='ffill')
                        
                        # 将RSI数据添加到原始数据中
                        # 创建时间到RSI值的映射
                        time_to_rsi_1min = dict(zip(price_df.index.strftime('%H:%M'), rsi_1min_6))
                        time_to_rsi_5min = dict(zip(price_df.index.strftime('%H:%M'), rsi_5min_6_1min))
                        
                        grouped_df['RSI6_1min'] = grouped_df['时间'].map(time_to_rsi_1min)
                        grouped_df['RSI6_5min'] = grouped_df['时间'].map(time_to_rsi_5min)
                        
                        # 格式化RSI数据为2位小数
                        grouped_df['RSI6_1min'] = grouped_df['RSI6_1min'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
                        grouped_df['RSI6_5min'] = grouped_df['RSI6_5min'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
                        
                        print(f"RSI计算完成，1分钟RSI6范围: {rsi_1min_6.min():.2f} - {rsi_1min_6.max():.2f}")
                        print(f"RSI计算完成，5分钟RSI6范围: {rsi_5min_6_1min.min():.2f} - {rsi_5min_6_1min.max():.2f}")
                        
                        # 检查映射结果
                        rsi_1min_valid = grouped_df['RSI6_1min'].notna().sum()
                        rsi_5min_valid = grouped_df['RSI6_5min'].notna().sum()
                        print(f"RSI数据映射结果: RSI6_1min {rsi_1min_valid}/{len(grouped_df)} 个有效值, RSI6_5min {rsi_5min_valid}/{len(grouped_df)} 个有效值")
                        
                        if rsi_1min_valid == 0 or rsi_5min_valid == 0:
                            print("警告: RSI数据映射失败!")
                            print(f"时间映射字典键: {list(time_to_rsi_1min.keys())}")
                            print(f"grouped_df时间列: {grouped_df['时间'].unique()}")
                        
                    except Exception as e:
                        print(f"计算RSI指标时发生错误: {str(e)}")
                        print("RSI计算失败，将导出不包含RSI数据的分时文件")
                        # 如果RSI计算失败，添加空列
                        grouped_df['RSI6_1min'] = ''
                        grouped_df['RSI6_5min'] = ''
                    
                    # 准备分时数据表头（按照您提供的格式：时间,成交价,手数,买卖盘性质,平均成本,RSI6_1min）
                    intraday_headers = ["时间", "成交价", "手数", "买卖盘性质", "平均成本", "RSI6_1min"]
                    
                    # 格式化数据以匹配您的示例格式
                    export_data = []
                    for _, row in grouped_df.iterrows():
                        # 格式化成交价保留2位小数
                        price = f"{row['成交价']:.2f}" if pd.notna(row['成交价']) else "0.00"
                        # 格式化手数
                        volume = f"{int(row['手数'])}" if pd.notna(row['手数']) else "0"
                        # 格式化平均成本（暂时为空）
                        cost = row['平均成本'] if pd.notna(row['平均成本']) and row['平均成本'] != '' else ""
                        # 格式化RSI
                        rsi = row['RSI6_1min'] if pd.notna(row['RSI6_1min']) and row['RSI6_1min'] != '' else ""
                        
                        export_data.append([
                            row['时间'],
                            price,
                            volume,
                            row['买卖盘性质'],
                            cost,
                            rsi
                        ])
                    
                    # 导出分时数据
                    with open(intraday_filepath, 'w', newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        writer.writerow(intraday_headers)
                        writer.writerows(export_data)
                    print(f"成功导出分时数据到: {intraday_filepath}")
                    print(f"原始记录数: {len(intraday_df)}, 合并后记录数: {len(grouped_df)}")
                else:
                    print("未获取到分时数据")
                
            except Exception as e:
                print(f"导出分时数据时发生错误: {str(e)}")
            
            # 直接合并文件
            merged_file = ExportService.merge_exported_files(code)
            if merged_file:
                return merged_file
            
            return None
            
        except Exception as e:
            print(f"导出过程中发生错误: {str(e)}")
            return None

    @staticmethod
    def _export_data_to_csv(data: pd.DataFrame, filepath: str, headers: List[str], period: str) -> pd.DataFrame:
        """导出数据到CSV文件"""
        try:
            # 计算KDJ前确保数据量足够
            min_data_length = 9  # KDJ计算需要的最小数据量
            if len(data) < min_data_length:
                raise ValueError(f"需要至少{min_data_length}条数据计算KDJ指标")
            
            # 计算KDJ指标
            data = ExportService.calculate_kdj(data)
            
            # 截取有效数据（去除前面用于计算的缓冲数据）
            valid_data = data.tail(-9) if len(data) > 9 else data
            
            # 计算MA均线
            ma_lines = [5, 10, 20]  # 默认MA线
            for ma in ma_lines:
                valid_data[f'MA{ma}'] = valid_data['收盘'].rolling(window=ma, min_periods=1).mean()
            
            # 添加平均成本数据时的调试信息
            if period == 'day':
                print("\n导出日线数据时的valid_data信息:")
                print(f"valid_data columns: {valid_data.columns.tolist()}")
                print(f"valid_data head:\n{valid_data.head()}")
            
            # 准备数据
            export_data: List[List[str]] = []
            for idx, row in valid_data.iterrows():
                if isinstance(idx, pd.Timestamp):
                    date_str = idx.strftime("%Y%m%d")
                    
                    # 处理成交量（转换为万单位）
                    volume = row['成交量'] / 10000 if pd.notnull(row['成交量']) else 0
                    
                    # 基础数据（调整换手率格式）
                    row_data = [
                        date_str,
                        f"{row['开盘']:.3f}".rstrip('0').rstrip('.') if row['开盘'] else '',
                        f"{row['最高']:.3f}".rstrip('0').rstrip('.') if row['最高'] else '',
                        f"{row['最低']:.3f}".rstrip('0').rstrip('.') if row['最低'] else '',
                        f"{row['收盘']:.3f}".rstrip('0').rstrip('.') if row['收盘'] else '',
                        f"{row['涨跌幅']:.3f}" if row['涨跌幅'] else '-',
                        f"{row['振幅']:.3f}" if row['振幅'] else '-',
                        f"{volume:.2f}",
                        f"{row['换手率']:.1f}" if row['换手率'] else '0.0',
                    ]
                    
                    # 添加平均成本数据
                    if period == 'day':
                        try:
                            cost_value = row.get('平均成本', '')
                            row_data.append(f"{cost_value:.3f}".rstrip('0').rstrip('.') if pd.notnull(cost_value) and cost_value != '' else '')
                        except Exception as e:
                            print(f"处理平均成本数据出错: {str(e)}")
                            row_data.append('')
                    else:
                        row_data.append('')  # 周线和月线添加一个空值
                    
                    # 添加MA数据（改为整数）
                    for ma in ma_lines:
                        ma_value = row.get(f"MA{ma}")
                        if pd.notnull(ma_value):
                            formatted = f"{int(round(ma_value))}"  # 四舍五入取整
                            row_data.append(formatted)
                        else:
                            row_data.append("")
                    
                    # 添加KDJ数据（改为整数）
                    kdj_str = f"K{int(round(row['K']))}D{int(round(row['D']))}J{int(round(row['J']))}"
                    row_data.append(kdj_str)
                    
                    export_data.append(row_data)
            
            # 写入CSV文件
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(export_data)
                
            return valid_data
            
        except Exception as e:
            raise Exception(f"导出{period}数据失败: {str(e)}")

    @staticmethod
    def _export_index_data_to_csv(data: pd.DataFrame, filepath: str, headers: List[str]) -> None:
        """导出上证指数数据到CSV文件"""
        try:
            export_data: List[List[str]] = []
            for idx, row in data.iterrows():
                # 处理日期格式
                if isinstance(idx, pd.Timestamp):  # 类型检查
                    date_str = idx.strftime("%Y%m%d")

                    # 处理成交量（转换为亿单位）
                    volume = row['成交量'] / 100000000 if pd.notnull(row['成交量']) else 0  # 转换为亿

                    # 格式化数据（移除涨跌额和成交额，价格取整，去除百分号）
                    row_data = [
                        date_str,
                        f"{int(round(row['开盘']))}" if pd.notnull(row['开盘']) else '',  # 价格取整
                        f"{int(round(row['收盘']))}" if pd.notnull(row['收盘']) else '',  # 价格取整
                        f"{int(round(row['最高']))}" if pd.notnull(row['最高']) else '',  # 价格取整
                        f"{int(round(row['最低']))}" if pd.notnull(row['最低']) else '',  # 价格取整
                        f"{row['涨跌幅']:.2f}" if pd.notnull(row['涨跌幅']) else '-',  # 去除%
                        f"{row['振幅']:.2f}" if pd.notnull(row['振幅']) else '-',  # 去除%
                        f"{volume:.2f}",  # 成交量使用亿为单位，保留2位小数
                        f"{row['换手率']:.2f}" if pd.notnull(row['换手率']) else '-'  # 去除%
                    ]
                    export_data.append(row_data)

            # 写入CSV文件
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(export_data)

        except Exception as e:
            raise Exception(f"导出上证指数数据失败: {str(e)}") from e

    @staticmethod
    def calculate_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
        """计算KDJ指标"""
        try:
            # 计算N日内的最高价和最低价
            df['low_n'] = df['最低'].rolling(window=n).min()
            df['high_n'] = df['最高'].rolling(window=n).max()
            
            # 计算RSV
            df['RSV'] = (df['收盘'] - df['low_n']) / (df['high_n'] - df['low_n']) * 100
            
            # 计算K、D、J值
            df['K'] = df['RSV'].ewm(alpha=1/m1, adjust=False).mean()
            df['D'] = df['K'].ewm(alpha=1/m2, adjust=False).mean()
            df['J'] = 3 * df['K'] - 2 * df['D']
            
            # 删除中间计算列
            df = df.drop(['low_n', 'high_n', 'RSV'], axis=1)
            
            # 处理无效值
            df[['K', 'D', 'J']] = df[['K', 'D', 'J']].fillna(0)
            
            return df
            
        except Exception as e:
            print(f"计算KDJ指标时发生错误: {str(e)}")
            return df


    @staticmethod
    def merge_exported_files(code: str) -> Optional[str]:
        """合并导出的日线、周线和月线数据文件"""
        try:
            # 获取导出目录下最新的对应代码的文件
            export_dir = os.path.join("data", "export")
            files: Dict[str, Optional[str]] = {
                'daily': None,
                'weekly': None,
                'monthly': None
            }
            
            # 查找最新的文件
            for filename in os.listdir(export_dir):
                if filename.startswith(str(code)):
                    filepath = os.path.join(export_dir, filename)
                    if '_daily_' in filename:
                        files['daily'] = filepath
                    elif '_weekly_' in filename:
                        files['weekly'] = filepath
                    elif '_monthly_' in filename:
                        files['monthly'] = filepath
            
            # 检查是否找到所有文件
            if not all(files.values()):
                missing = [k for k, v in files.items() if v is None]
                raise ValueError(f"缺少文件: {', '.join(missing)}")
            
            # 读取并合并数据
            dfs: List[pd.DataFrame] = []
            period_map = {
                'daily': 'D',    # 日线用D表示
                'weekly': 'W',   # 周线用W表示
                'monthly': 'M'   # 月线用M表示
            }
            
            for period, filepath in files.items():
                if filepath:  # 类型检查
                    df = pd.read_csv(filepath)
                    # 使用简化的数据类型标识
                    df.insert(0, '数据类型', period_map[period])
                    dfs.append(df)
            
            # 合并数据框
            merged_df = pd.concat(dfs, axis=0)
            
            # 生成合并文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            merged_filename = f"{code}_merged_data_{timestamp}.csv"
            merged_filepath = os.path.join(export_dir, merged_filename)
            
            # 保存合并后的文件
            merged_df.to_csv(merged_filepath, index=False, encoding='utf-8')
            
            # 删除原始文件
            for filepath in files.values():
                if filepath:  # 类型检查
                    os.remove(filepath)
            
            print(f"文件已合并: {merged_filepath}")
            return merged_filepath
            
        except Exception as e:
            print(f"合并文件失败: {str(e)}")
            return None 