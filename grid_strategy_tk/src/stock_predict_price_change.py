import concurrent.futures
import queue
import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk

import akshare as ak
import numpy as np
import pandas as pd
from stock_analysis_engine import ETFAnalysisEngine
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from tqdm import tqdm


def get_merged_data(stock_code, start_date, end_date):
    """获取并合并行情数据和筹码数据"""
    print(f"Getting price data for {stock_code} from {start_date} to {end_date}")
    
    # 创建ETFAnalysisEngine实例
    engine = ETFAnalysisEngine()
    
    # 使用engine的load_data方法获取数据
    data = engine.load_data(
        code=stock_code,
        symbol_name='',  # 非板块代码可以传空字符串
        period_mode='day',  # 使用日线数据
        start_date=start_date,
        end_date=end_date,
        period_config={
            'day': {
                'ak_period': 'daily',
                'buffer_ratio': '0.2',
                'min_buffer': '3'
            }
        }
    )
    
    if data.empty:
        print("Failed to get data")
        return pd.DataFrame()
        
    print(f"Retrieved {len(data)} records")
    
    # 计算涨跌幅
    data['price_pct_change'] = data['涨跌幅']
    
    # 计算成本变化
    data['cost_pct_change'] = data['平均成本'].pct_change() * 100
    
    return data

def find_continuous_periods(df):
    """识别连续收盘价低于平均成本的区间"""
    df['below_cost'] = df['收盘'] < df['平均成本']
    df['group'] = (df['below_cost'] != df['below_cost'].shift(1)).cumsum()
    
    # 添加连续时间段输出
    below_cost_df = df[df['below_cost']]
    print("\nContinuous periods below average cost:")
    
    for group_num, group in below_cost_df.groupby('group'):
        start_date = group['日期'].iloc[0].strftime('%Y-%m-%d')
        end_date = group['日期'].iloc[-1].strftime('%Y-%m-%d')
        duration = len(group)
        avg_price = group['收盘'].mean()
        avg_cost = group['平均成本'].mean()
        diff_percent = ((avg_cost - avg_price) / avg_cost * 100)
        
        print(f"Period {group_num}:")
        print(f"  Duration: {duration} days ({start_date} to {end_date})")
        print(f"  Average Price: {avg_price:.2f}")
        print(f"  Average Cost: {avg_cost:.2f}")
        print(f"  Below Cost: {diff_percent:.2f}%")
    
    return below_cost_df

def calculate_features(group_df):
    """计算特征数据集"""
    features = []
    for i in range(5, len(group_df)):
        window = group_df.iloc[i-5:i]
        current = group_df.iloc[i]
        
        # 计算价格与平均成本的差值比例
        price_cost_ratio = ((current['平均成本'] - current['收盘']) / current['平均成本'] * 100)
        
        # 当日特征
        day_features = {
            'price_change': current['price_pct_change'],
            'cost_change': current['cost_pct_change'],
            'price_cost_ratio': price_cost_ratio,  # 价格低于成本的比例特征
            
            # 5日窗口特征
            'price_ma5': window['price_pct_change'].mean(),
            'cost_ma5': window['cost_pct_change'].mean(),
            'price_std5': window['price_pct_change'].std(),
            'trend_direction': np.sign(window['price_pct_change'].sum())
        }
        
        # 目标变量：下一日涨跌
        next_day = group_df.iloc[i+1] if i+1 < len(group_df) else None
        if next_day is not None:
            day_features['target'] = 1 if next_day['price_pct_change'] > 0 else 0
            features.append(day_features)
    
    return pd.DataFrame(features)

def train_prediction_model(stock_code, start_date, end_date):
    """训练预测模型"""
    print(f"Starting model training for {stock_code}")
    
    # 准备数据
    print("Preparing training data...")
    df = get_merged_data(stock_code, start_date, end_date)
    
    # 获取最后一个交易日的数据作为current_data
    if not df.empty:
        last_day = df.iloc[-1]
        current_data = {
            'price_change': last_day['涨跌幅'],  # 当日涨跌幅
            'cost_change': last_day['cost_pct_change'],  # 成本变化率
            'last_5_days': df['涨跌幅'].tail(5).tolist()  # 过去5日涨跌幅
        }
        print("\nCurrent data for last trading day:")
        print(f"Date: {df.index[-1].strftime('%Y-%m-%d')}")
        print(f"Price change: {current_data['price_change']:.2f}%")
        print(f"Cost change: {current_data['cost_change']:.2f}%")
        print(f"Last 5 days changes: {[f'{x:.2f}%' for x in current_data['last_5_days']]}")
    else:
        print("No data available")
        current_data = None
        
    # 识别连续低于成本价的区间
    df['below_cost'] = df['收盘'] < df['平均成本']
    df['group'] = (df['below_cost'] != df['below_cost'].shift(1)).cumsum()
    below_cost_df = df[df['below_cost']]
    
    # 输出连续时间段
    print("\nContinuous periods below average cost:")
    for group_num, group in below_cost_df.groupby('group'):
        start_date = group.index[0].strftime('%Y-%m-%d')
        end_date = group.index[-1].strftime('%Y-%m-%d')
        duration = len(group)
        avg_price = group['收盘'].mean()
        avg_cost = group['平均成本'].mean()
        diff_percent = ((avg_cost - avg_price) / avg_cost * 100)
        
        print(f"Period {group_num}:")
        print(f"  Duration: {duration} days ({start_date} to {end_date})")
        print(f"  Average Price: {avg_price:.2f}")
        print(f"  Average Cost: {avg_cost:.2f}")
        print(f"  Below Cost: {diff_percent:.2f}%")
    
    print(f"Found {len(below_cost_df)} records below cost price")
    
    # 生成特征数据集
    print("Generating features...")
    features_list = []
    for _, group in below_cost_df.groupby('group'):
        if len(group) >= 6:
            features_list.append(calculate_features(group))
    
    if not features_list:
        raise ValueError("没有足够的连续低于成本数据用于训练")
    
    full_df = pd.concat(features_list)
    print(f"Generated {len(full_df)} feature records")
    
    # 准备训练数据
    X = full_df[[
        'price_change', 
        'cost_change', 
        'price_cost_ratio',  # 确保包含这个特征
        'price_ma5', 
        'cost_ma5', 
        'price_std5', 
        'trend_direction'
    ]]
    y = full_df['target']
    
    # 数据标准化
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # 训练模型
    print("Training logistic regression model...")
    model = LogisticRegression()
    model.fit(X_scaled, y)
    print("Model training completed")
    
    return model, scaler, current_data

def predict_next_day(model, scaler, current_price_change, current_cost_change, last_5_days, stock_code, predict_date, price_cost_ratio):
    """预测下一个交易日涨跌概率"""
    print("\nPredicting next day price movement...")
    print(f"Stock: {stock_code}")
    print(f"Prediction date: {predict_date}")
    # 注意：涨跌幅本身就是百分比值，不需要再乘以100
    print(f"Current price change: {current_price_change:.2f}%")
    print(f"Current cost change: {current_cost_change:.2f}%")
    # 显示过去5天的涨跌幅，保留两位小数
    print(f"Last 5 days changes: {[f'{x:.2f}%' for x in last_5_days]}")
    
    # 计算5日特征
    price_ma5 = np.mean(last_5_days)
    cost_ma5 = np.mean([current_cost_change]*5)  # 假设成本变化数据需要调整
    price_std5 = np.std(last_5_days)
    trend_direction = np.sign(np.sum(last_5_days))
    
    # 构建特征向量
    features = np.array([[
        current_price_change,
        current_cost_change,
        price_cost_ratio,  # 包含价格成本差值比例
        price_ma5,
        cost_ma5,
        price_std5,
        trend_direction
    ]])
    
    # 标准化并预测
    scaled_features = scaler.transform(features)
    proba = model.predict_proba(scaled_features)[0]
    
    print(f"Prediction completed - Up: {proba[1]:.2%}, Down: {proba[0]:.2%}")
    return {
        '股票代码': stock_code,
        '预测日期': predict_date,
        '上涨概率': proba[1],
        '下跌概率': proba[0]
    }

def backtest_predictions(stock_code, backtest_start_date, backtest_end_date, train_start_date=None):
    """
    回测验证预测结果，只对股价低于平均成本的日期进行预测
    参数:
    - stock_code: 股票代码
    - backtest_start_date: 回测开始日期
    - backtest_end_date: 回测结束日期
    - train_start_date: 训练数据开始日期，默认为回测开始日期前一年
    """
    print(f"\n开始回测预测 {stock_code}")
    print(f"回测区间: {backtest_start_date} 至 {backtest_end_date}")
    
    # 如果没有指定训练起始日期，默认使用回测开始日期前一年
    if train_start_date is None:
        backtest_start = datetime.strptime(backtest_start_date, "%Y%m%d")
        train_start = (backtest_start - timedelta(days=365)).strftime("%Y%m%d")
    else:
        train_start = train_start_date
        
    print(f"训练数据起始日期: {train_start}")
    
    # 获取数据（包含训练期间的数据）
    df = get_merged_data(stock_code, train_start, backtest_end_date)
    if df.empty:
        print("获取数据失败")
        return pd.DataFrame()
    
    # 确保日期索引按时间排序
    df = df.sort_index()
    
    # 筛选出股价低于平均成本的日期
    df['below_cost'] = df['收盘'] < df['平均成本']
    below_cost_days = df[df['below_cost']]
    
    print(f"总交易日数: {len(df)}")
    print(f"股价低于平均成本的天数: {len(below_cost_days)}")
    
    results = []
    # 只对回测区间进行预测
    backtest_mask = (df.index >= backtest_start_date) & (df.index <= backtest_end_date)
    backtest_df = df[backtest_mask]
    
    # 从回测区间的第6天开始预测
    for i in range(5, len(backtest_df)-1):
        current_date = backtest_df.index[i]
        next_date = backtest_df.index[i+1]
        
        # 只对当前日期股价低于平均成本的情况进行预测
        if not backtest_df['below_cost'].iloc[i]:
            continue
            
        # 获取当前日期的特征
        last_5_days = backtest_df['涨跌幅'].iloc[i-5:i].tolist()
        current_price_change = backtest_df['涨跌幅'].iloc[i]
        current_cost_change = backtest_df['cost_pct_change'].iloc[i]
        
        # 计算价格与平均成本的差值比例
        price_cost_ratio = ((backtest_df['平均成本'].iloc[i] - backtest_df['收盘'].iloc[i]) / backtest_df['平均成本'].iloc[i] * 100)
        
        # 训练模型(使用直到当前日期的所有训练数据)
        train_end_idx = df.index.get_loc(current_date)
        train_df = df.iloc[:train_end_idx+1]
        features_df = calculate_features(train_df[train_df['below_cost']])
        
        if len(features_df) < 10:  # 确保有足够的训练数据
            continue
            
        X = features_df[['price_change', 'cost_change', 'price_cost_ratio', 'price_ma5', 'cost_ma5', 'price_std5', 'trend_direction']]
        y = features_df['target']
        
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        model = LogisticRegression()
        model.fit(X_scaled, y)
        
        # 预测下一天
        prediction = predict_next_day(
            model, 
            scaler,
            current_price_change,
            current_cost_change,
            last_5_days,
            stock_code,
            next_date.strftime('%Y-%m-%d'),
            price_cost_ratio
        )
        
        # 获取实际结果
        actual_change = df['涨跌幅'].iloc[i+1]
        actual_up = actual_change > 0
        predicted_up = prediction['上涨概率'] > 0.5
        
        results.append({
            '预测日期': next_date.strftime('%Y-%m-%d'),
            '上涨概率': prediction['上涨概率'],
            '实际涨跌': actual_change,
            '预测正确': predicted_up == actual_up,
            '收盘价': df['收盘'].iloc[i],
            '平均成本': df['平均成本'].iloc[i],
            '价格低于成本比例': ((df['平均成本'].iloc[i] - df['收盘'].iloc[i]) / df['平均成本'].iloc[i] * 100)
        })
        
        # 打印每日预测结果
        print(f"\n日期: {next_date.strftime('%Y-%m-%d')}")
        print(f"收盘价: {df['收盘'].iloc[i]:.2f}")
        print(f"平均成本: {df['平均成本'].iloc[i]:.2f}")
        # 价格低于成本比例已经计算为百分比，不需要再乘以100
        print(f"低于成本: {((df['平均成本'].iloc[i] - df['收盘'].iloc[i]) / df['平均成本'].iloc[i] * 100):.2f}%")
        # 上涨概率已经是小数形式，使用:.2%会自动转换为百分比
        print(f"预测上涨概率: {prediction['上涨概率']:.2%}")
        # 实际涨跌幅本身就是百分比值，不需要再乘以100
        print(f"实际涨跌幅: {actual_change:.2f}%")
        print(f"预测{'正确' if predicted_up == actual_up else '错误'}")
    
    # 创建结果DataFrame
    results_df = pd.DataFrame(results)
    
    if not results_df.empty:
        # 计算总体准确率
        accuracy = results_df['预测正确'].mean()
        print(f"\n总体预测准确率: {accuracy:.2%}")
        print(f"总预测天数: {len(results_df)}")
    
    return results_df

def get_all_stock_codes():
    """获取所有A股股票代码"""
    try:
        # 获取A股所有股票代码
        stock_info = ak.stock_info_a_code_name()
        # 筛选出以0、3、6开头的股票代码
        valid_codes = stock_info[stock_info['code'].str.match('^[036]')]['code'].tolist()
        return valid_codes
    except Exception as e:
        print(f"获取股票代码失败: {e}")
        return []

def batch_backtest_stocks(backtest_start_date, backtest_end_date, train_start_date=None, max_workers=4):
    """
    批量回测所有A股股票，使用UI显示进度
    
    参数:
    - backtest_start_date: 回测开始日期
    - backtest_end_date: 回测结束日期
    - train_start_date: 训练数据开始日期
    - max_workers: 最大线程数
    
    返回:
    - 包含所有股票回测结果的DataFrame
    """
    # 获取所有股票代码
    stock_codes = get_all_stock_codes()
    total_stocks = len(stock_codes)
    
    # 创建一个队列用于线程间通信
    progress_queue = queue.Queue()
    result_queue = queue.Queue()
    
    # 创建UI窗口
    root = tk.Tk()
    root.title("A股回测进度")
    root.geometry("500x300")
    
    # 设置窗口样式
    style = ttk.Style()
    style.theme_use('default')
    style.configure("TProgressbar", thickness=20)
    
    # 创建标签和进度条
    header_label = ttk.Label(root, text="A股股票回测进度", font=("Arial", 16))
    header_label.pack(pady=10)
    
    info_label = ttk.Label(root, text=f"共计 {total_stocks} 只股票，使用 {max_workers} 个线程")
    info_label.pack(pady=5)
    
    progress_frame = ttk.Frame(root)
    progress_frame.pack(fill=tk.X, padx=20, pady=10)
    
    progress_bar = ttk.Progressbar(progress_frame, style="TProgressbar", length=460, mode="determinate", maximum=total_stocks)
    progress_bar.pack(fill=tk.X)
    
    progress_label = ttk.Label(progress_frame, text="0%")
    progress_label.pack(pady=5)
    
    current_stock_label = ttk.Label(root, text="当前处理: 等待开始...")
    current_stock_label.pack(pady=5)
    
    stats_frame = ttk.Frame(root)
    stats_frame.pack(fill=tk.X, padx=20, pady=10)
    
    completed_label = ttk.Label(stats_frame, text="已完成: 0")
    completed_label.pack(side=tk.LEFT, padx=10)
    
    success_label = ttk.Label(stats_frame, text="成功: 0")
    success_label.pack(side=tk.LEFT, padx=10)
    
    failed_label = ttk.Label(stats_frame, text="失败: 0")
    failed_label.pack(side=tk.LEFT, padx=10)
    
    accuracy_label = ttk.Label(root, text="平均准确率: 等待计算...")
    accuracy_label.pack(pady=5)
    
    # 统计变量
    stats = {
        'completed': 0,
        'success': 0,
        'failed': 0,
        'results': []
    }
    
    # 更新UI的函数
    def update_ui():
        try:
            while True:
                # 非阻塞方式获取队列消息
                try:
                    message = progress_queue.get_nowait()
                    
                    if message['type'] == 'progress':
                        stock_code = message['stock_code']
                        success = message['success']
                        
                        stats['completed'] += 1
                        if success:
                            stats['success'] += 1
                            stats['results'].append(message['result'])
                        else:
                            stats['failed'] += 1
                        
                        # 更新进度条和标签
                        progress_bar['value'] = stats['completed']
                        progress_percent = (stats['completed'] / total_stocks) * 100
                        progress_label.config(text=f"{progress_percent:.1f}%")
                        current_stock_label.config(text=f"当前处理: {stock_code}")
                        completed_label.config(text=f"已完成: {stats['completed']}")
                        success_label.config(text=f"成功: {stats['success']}")
                        failed_label.config(text=f"失败: {stats['failed']}")
                        
                        # 如果有结果，计算平均准确率
                        if stats['results']:
                            avg_accuracy = sum(r['准确率'] for r in stats['results']) / len(stats['results'])
                            accuracy_label.config(text=f"平均准确率: {avg_accuracy:.2%}")
                    
                    elif message['type'] == 'complete':
                        # 回测完成
                        current_stock_label.config(text="处理完成!")
                        
                        # 将结果放入结果队列
                        if stats['results']:
                            result_queue.put(pd.DataFrame(stats['results']))
                        else:
                            result_queue.put(pd.DataFrame())
                        
                        # 添加关闭按钮
                        close_button = ttk.Button(root, text="关闭", command=root.destroy)
                        close_button.pack(pady=10)
                        
                except queue.Empty:
                    break
                    
            # 继续更新UI
            root.after(100, update_ui)
            
        except Exception as e:
            print(f"UI更新错误: {e}")
    
    # 后台线程函数
    def backtest_thread():
        try:
            print(f"开始批量回测A股股票，共 {total_stocks} 只...")
            
            def process_stock(stock_code):
                """处理单个股票的回测"""
                try:
                    # 减少输出信息
                    original_print = print
                    def silent_print(*args, **kwargs):
                        pass
                    
                    # 临时替换print函数以减少输出
                    import builtins
                    builtins.print = silent_print
                    
                    results_df = backtest_predictions(
                        stock_code,
                        backtest_start_date,
                        backtest_end_date,
                        train_start_date
                    )
                    
                    # 恢复print函数
                    builtins.print = original_print
                    
                    if not results_df.empty:
                        accuracy = results_df['预测正确'].mean()
                        prediction_count = len(results_df)
                        result = {
                            '股票代码': stock_code,
                            '预测次数': prediction_count,
                            '准确率': accuracy,
                        }
                        progress_queue.put({
                            'type': 'progress',
                            'stock_code': stock_code,
                            'success': True,
                            'result': result
                        })
                        return result
                    else:
                        progress_queue.put({
                            'type': 'progress',
                            'stock_code': stock_code,
                            'success': False
                        })
                        return None
                except Exception as e:
                    print(f"\n股票 {stock_code} 回测失败: {e}")
                    progress_queue.put({
                        'type': 'progress',
                        'stock_code': stock_code,
                        'success': False
                    })
                    return None
            
            # 使用线程池执行回测
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                futures = [executor.submit(process_stock, code) for code in stock_codes]
                
                # 等待所有任务完成
                concurrent.futures.wait(futures)
            
            # 通知UI线程回测完成
            progress_queue.put({'type': 'complete'})
            
            # 等待结果被处理
            results_df = result_queue.get()
            
            # 保存结果到CSV
            if not results_df.empty:
                output_file = f"batch_backtest_results_{backtest_start_date}_{backtest_end_date}.csv"
                results_df.to_csv(output_file, index=False)
                print(f"\n回测结果已保存到: {output_file}")
                
                # 计算总体统计信息
                avg_accuracy = results_df['准确率'].mean()
                total_predictions = results_df['预测次数'].sum()
                stocks_tested = len(results_df)
                
                print("\n回测统计结果:")
                print(f"测试股票数: {stocks_tested}")
                print(f"总预测次数: {total_predictions}")
                print(f"平均准确率: {avg_accuracy:.2%}")
                
                return results_df
            else:
                print("没有获取到有效的回测结果")
                return pd.DataFrame()
                
        except Exception as e:
            print(f"回测线程错误: {e}")
            progress_queue.put({'type': 'complete'})
            return pd.DataFrame()
    
    # 启动UI更新
    root.after(100, update_ui)
    
    # 启动后台线程
    thread = threading.Thread(target=backtest_thread)
    thread.daemon = True
    thread.start()
    
    # 运行UI主循环
    root.mainloop()
    
    # 等待后台线程完成并获取结果
    thread.join()
    
    try:
        # 尝试从结果队列获取结果
        if not result_queue.empty():
            return result_queue.get()
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

# 使用示例
if __name__ == "__main__":
    print("Starting batch backtesting process...")
    
    backtest_start_date = "20250101"  # 回测开始日期
    backtest_end_date = datetime.now().strftime("%Y%m%d")  # 回测结束日期
    train_start_date = "20210101"  # 训练数据开始日期
    
    # 执行批量回测
    results_df = batch_backtest_stocks(
        backtest_start_date,
        backtest_end_date,
        train_start_date,
        max_workers=8  # 可以根据CPU核心数调整
    )