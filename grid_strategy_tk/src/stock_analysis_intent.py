import numpy as np
import pandas as pd
from scipy.special import softmax


def parse_kdj(kdj_str):
    """解析KDJ字符串并返回KDJ值"""
    if pd.isna(kdj_str):
        return 0, 0, 0
    try:
        k, d, j = map(float, kdj_str.split(','))
        return k, d, j
    except (ValueError, TypeError):
        return 0, 0, 0

def optimized_intent_analysis(close, avg_cost, volume_ratio_change, kdj_k, turnover_rate):
    """
    终极优化版主力意图分析算法
    
    参数说明：
    close: 当日收盘价
    avg_cost: 市场平均成本
    volume_ratio_change: 量比变化率（当日量比/前日量比 -1）
    kdj_k: KDJ指标中的K值（0-100）
    turnover_rate: 换手率（单位：百分比）
    
    返回：
    各意图的概率分布（字典）
    """
    # 核心指标计算 -------------------------------------------------
    # 成本博弈系数（关键指标）
    cost_game = np.clip((avg_cost - close) / close * 100, -15, 15)
    
    # 量能动能因子
    volume_power = np.log1p(abs(volume_ratio_change)*100) * np.sign(volume_ratio_change)
    
    # 筹码稳定度
    stability = np.exp(-abs(kdj_k - 50)/30) * (turnover_rate/10)**0.5
    
    # 主力意图权重计算（经验优化参数）--------------------------------
    intent_weights = {
        '建仓': max(0, (cost_game*0.8 + volume_power*0.5 - stability*1.2)),
        '试盘': abs(volume_power)**1.5 * (1 - abs(cost_game)/15) * 0.7,
        '洗盘': max(0, -cost_game*0.6 + volume_power*(-0.8)) * stability**0.7,
        '拉升': (min(cost_game, 5)*0.5 + volume_power*1.2 + stability**1.5) * (kdj_k/80),
        '出货': max(0, cost_game*1.2 - stability*1.5) * (volume_power>0) * (kdj_k/100)**2,
        '反弹': max(0, -cost_game*1.5 + volume_power*1.8) * (stability<0.6),
        '砸盘': min(0, cost_game*2 + volume_power*(-1.5)) * (1 - kdj_k/100)
    }
    
    # 动态修正因子 -------------------------------------------------
    # 量能异常检测
    if abs(volume_power) > 2:
        intent_weights['试盘'] *= 1.5
        intent_weights['出货'] *= 0.8 if volume_power >0 else 1.2
    
    # 成本博弈极端情况
    if abs(cost_game) > 10:
        intent_weights['砸盘' if cost_game>0 else '建仓'] *= 1.5
    
    # KDJ超买超卖修正
    if kdj_k > 80:
        intent_weights['拉升'] *= 0.7
        intent_weights['出货'] *= 1.3
    elif kdj_k < 20:
        intent_weights['砸盘'] *= 0.5
        intent_weights['反弹'] *= 1.2
    
    # 概率标准化
    probs = softmax(list(intent_weights.values()))
    # 将概率值四舍五入到两位小数
    probs = np.round(probs, decimals=2)
    return dict(zip(intent_weights.keys(), probs))

def backtest(data):
    results = []
    for i in range(len(data)):
        row = data.iloc[i]
        if i == 0: continue
        
        # prob = optimized_intent_analysis(
        #     close=row['收盘'],
        #     avg_cost=row['平均成本'],
        #     volume_ratio_change=0,  # 量比指标已移除
        #     kdj_k=parse_kdj(row['KDJ(9,3,3)'])[0],
        #     turnover_rate=row['换手率']
        # )
        row['前平均成本'] = data.iloc[i-1]['平均成本']
        prob = enhanced_intent_analysis(row)
        # 转换日期格式
        date_str = str(row['日期'])
        formatted_date = pd.to_datetime(date_str, format='%Y%m%d').strftime('%Y-%m-%d')
        
        results.append({
            'date': formatted_date,
            **prob
        })
    return pd.DataFrame(results)


def enhanced_intent_analysis(row):
    """
    强化版主力意图分析算法（基于单行数据）
    
    参数说明：
    row: 包含完整数据字段的pandas Series
    
    返回：
    各意图的概率分布（字典）
    """
    # 核心指标重构 ------------------------------------------------
    close = row['收盘']
    price_change = row['涨跌幅']/100  # 转换为小数
    
    # 成本博弈指标（关键改进）
    cost_game = (row['平均成本'] - close) / close * 100  # 成本溢价百分比
    cost_trend = row['平均成本'] - row['前平均成本']
    
    # 量能特征（量比指标已移除，使用换手率替代）
    turnover_rate = row.get('换手率', 0)
    volume_shock = turnover_rate * 0.1  # 使用换手率作为量能指标
    
    # KDJ指标解析
    k, d, j = map(float, row['KDJ(9,3,3)'][1:].replace('D','J').split('J')[:3])
    
    # 波动性特征
    amplitude = row['振幅']/100  # 转换为小数
    
    # 主力意图权重计算（经验参数优化）------------------------------
    intent_weights = {
        # 砸盘：暴跌特征强化检测
        '砸盘': max(0, 
                  (-price_change*50) *  # 跌幅放大系数
                  (1 + turnover_rate * 0.1) *  # 使用换手率替代量比
                  (1 - k/80)**2 *  # K值越低信号越强
                  (1 + cost_game/10)  # 成本溢价时加强信号
                 ),
        
        # 出货：多维度背离检测
        '出货': (
            max(0, (price_change*30 - cost_trend*100)**1.5) *  # 价格涨幅与成本趋势背离
            (k/100)**3 *  # K值高位强化信号
            np.log1p(row['换手率']) *  # 换手率非线性影响
            (1 if turnover_rate < 2 else 0.8)  # 低换手率出货特征
        ),
        
        # 洗盘：震荡吸筹模式
        '洗盘': 
            (amplitude**2 * 100) *  # 高振幅
            np.clip(-price_change*20, 0, 3) *  # 小幅下跌
            (0.8 - abs(k-50)/50) *  # K值在中位区
            np.exp(-abs(row['换手率']-5)/10  # 换手率5%左右最佳
        ),
        
        # 其他意图保持原有逻辑
        '建仓': max(0, (cost_trend*100 - price_change*30) * (1 - k/80)),
        '试盘': abs(volume_shock) * (0.5 + amplitude*2),
        '拉升': (price_change*40 + cost_trend*50) * (k/80)**0.5,
        '反弹': max(0, (-price_change*30) * (j/50)**2)
    }
    
    # 动态强化修正 -----------------------------------------------
    # 暴跌紧急检测（单日跌幅>7%）
    if price_change < -0.07:
        intent_weights['砸盘'] *= 2.5
        intent_weights['出货'] *= 0.5
    
    # 高位出货特征（价格创新高且换手率>15%）
    if (close == row['最高']) and (row['换手率'] > 15):
        intent_weights['出货'] *= 1.8
        intent_weights['拉升'] *= 0.3
    
    # 洗盘模式强化（中振幅+缩量）
    if (3 < row['振幅'] < 8) and (turnover_rate < 2):
        intent_weights['洗盘'] *= 1.5
    
    # 标准化处理
    probs = softmax(list(intent_weights.values()))
    return dict(zip(intent_weights.keys(), probs))


# 执行回测
df = pd.read_csv('/Users/kobunketsu/工程/A Stock/data/export/002990_merged_data_20250226_095958.csv')
backtest_result = backtest(df)

# 查看关键日期的判断
print(backtest_result[backtest_result['date'].isin(['20250221','20250224','20250114'])])

import plotly.express as px
import plotly.graph_objects as go


def plot_intent_timeline(result_df):
    """
    绘制主力意图演化分析图表
    使用堆叠柱状图展示不同操作意图的占比
    """
    # 确保日期列是datetime类型
    result_df['date'] = pd.to_datetime(result_df['date'])
    
    # 定义颜色映射
    color_map = {
        '建仓': '#2ecc71',  # 绿色
        '试盘': '#3498db',  # 蓝色
        '洗盘': '#9b59b6',  # 紫色
        '拉升': '#e74c3c',  # 红色
        '出货': '#f1c40f',  # 黄色
        '反弹': '#1abc9c',  # 青色
        '砸盘': '#e67e22'   # 橙色
    }
    
    # 创建图表
    fig = go.Figure()
    
    # 添加每种意图的柱状图
    for intent in ['建仓', '试盘', '洗盘', '拉升', '出货', '反弹', '砸盘']:
        fig.add_trace(go.Bar(
            x=result_df['date'],
            y=result_df[intent],
            name=intent,
            marker_color=color_map[intent],
            width=20*60*60*1000,  # 设置柱子宽度为20小时的毫秒数
        ))
    
    # 获取所有有数据的日期点
    date_ticks = result_df['date'].dt.strftime('%Y-%m-%d').tolist()
    
    # 更新布局
    fig.update_layout(
        title='主力操盘意图分析',
        xaxis_title='日期',
        yaxis_title='意图占比',
        barmode='stack',  # 改回堆叠模式
        bargap=0.3,       # 柱子之间的间距
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        ),
        # 设置图表大小
        width=1200,
        height=600,
        # 添加网格线
        xaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='LightGrey',
            tickangle=45,
            tickformat='%Y-%m-%d',  # 设置日期格式
            tickmode='array',    # 使用自定义刻度
            ticktext=date_ticks, # 刻度标签
            tickvals=result_df['date'],  # 刻度位置
            type='date'  # 明确指定x轴类型为日期
        ),
        yaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='LightGrey',
            tickformat=',.0%',  # 显示为百分比格式
            range=[0, 1]  # 固定y轴范围为0-100%
        ),
        # 设置图表边距
        margin=dict(
            l=50,
            r=50,
            t=50,
            b=100
        )
    )
    
    # 添加滑动条并设置其日期格式
    fig.update_xaxes(
        rangeslider_visible=True,
        rangeslider=dict(thickness=0.05),  # 设置滑动条高度
        tickformat='%Y-%m-%d'
    )
    
    # 显示图表
    fig.show()

# 执行回测和绘图
df = pd.read_csv('/Users/kobunketsu/工程/A Stock/data/export/002990_merged_data_20250226_095958.csv')
backtest_result = backtest(df)
plot_intent_timeline(backtest_result)

def export_intent_results(result_df, output_path=None):
    """
    导出主力意图分析结果到CSV文件（每个交易日保留最高概率意图）
    格式：日期, 主力意图, 概率
    
    参数：
    result_df: backtest返回的结果DataFrame
    output_path: 输出文件路径（可选）
    """
    # 找出每个交易日概率最高的意图
    dominant_df = result_df.set_index('date').apply(
        lambda row: pd.Series({
            '主力意图': row.idxmax(),
            '概率': row.max()
        }), axis=1
    ).reset_index()
    
    # 按日期排序
    dominant_df = dominant_df.sort_values(by='date')
    
    # 设置默认保存路径
    if output_path is None:
        output_path = '/Users/kobunketsu/工程/A Stock/data/export/002990_merged_data_20250226_095958_dominant_intent.csv'
    
    # 保存CSV（保留4位小数）
    dominant_df.to_csv(output_path, index=False, float_format='%.4f')
    print(f"主力意图分析结果已保存至: {output_path}")

# 在现有代码最后添加导出功能
export_intent_results(backtest_result)
