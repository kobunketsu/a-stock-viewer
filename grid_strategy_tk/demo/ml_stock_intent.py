#DeepSeek获取的用来深度学习预测股票主力操盘意图的代码，运气起来有很多问题，需要优化
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.layers import LSTM, Attention, Dense, Dropout, Input
from tensorflow.keras.models import Model

# 数据预处理
df = pd.read_csv('/Users/kobunketsu/工程/A Stock/data/export/002990_merged_data_20250226_095958.csv')

# 计算关键指标
df['market_cost_change'] = df['平均成本'].pct_change()
df['volume_ratio'] = 1 + df['量比涨幅']/100  # 换算为量比绝对值
df['volume_momentum'] = df['volume_ratio'].pct_change()

# 技术指标解析
def parse_kdj(kdj_str):
    k = float(kdj_str.split('K')[1].split('D')[0])
    d = float(kdj_str.split('D')[1].split('J')[0])
    j = float(kdj_str.split('J')[1])
    return k, d, j

df[['K','D','J']] = df['KDJ(9,3,3)'].apply(parse_kdj).apply(pd.Series)

# 特征工程
features = ['涨跌幅', 'market_cost_change', 'volume_momentum',
           'MA5', 'MA10', 'MA20', 'K','D','J', '换手率', '振幅']
targets = ['建仓', '试盘', '洗盘', '拉升', '出货', '反弹', '砸盘']

# 生成训练序列
SEQ_LENGTH = 5  # 使用5天窗口分析
def create_sequences(data, seq_length):
    X, y = [], []
    for i in range(len(data)-seq_length-3):  # 预测未来3天走势
        seq = data[i:i+seq_length]
        target = data[i+seq_length:i+seq_length+3]['涨跌幅'].mean()
        X.append(seq[features].values)
        y.append(target)
    return np.array(X), np.array(y)

X, y = create_sequences(df, SEQ_LENGTH)

# 数据标准化
scaler = StandardScaler()
X = scaler.fit_transform(X.reshape(-1, len(features))).reshape(X.shape)

# 构建深度时序模型
def build_model(input_shape):
    inputs = Input(shape=input_shape)
    
    # 时序特征提取
    lstm_out = LSTM(64, return_sequences=True)(inputs)
    attn = Attention()([lstm_out, lstm_out])
    pooled = tf.reduce_mean(attn, axis=1)
    
    # 空间特征提取
    dense = Dense(32, activation='relu')(pooled)
    dense = Dropout(0.3)(dense)
    
    # 多任务输出
    intent_output = Dense(7, activation='softmax', name='intent')(dense)
    price_output = Dense(1, activation='tanh', name='price')(dense)
    
    model = Model(inputs=inputs, outputs=[intent_output, price_output])
    
    model.compile(optimizer=tf.keras.optimizers.Adam(0.001),
                loss={'intent': 'categorical_crossentropy',
                      'price': 'mse'},
                metrics={'intent': 'accuracy',
                         'price': 'mae'})
    return model

# 自定义损失函数
class CustomLoss(tf.keras.losses.Loss):
    def __init__(self, alpha=0.7):
        super().__init__()
        self.alpha = alpha
        
    def call(self, y_true, y_pred):
        # 意图分类损失
        intent_loss = tf.keras.losses.categorical_crossentropy(y_true[0], y_pred[0])
        
        # 价格预测损失
        price_loss = tf.keras.losses.mse(y_true[1], y_pred[1])
        
        # 动态权重调整
        total_loss = self.alpha*intent_loss + (1-self.alpha)*price_loss
        return total_loss

# 改进的混合模型
model = build_model((SEQ_LENGTH, len(features)))
model.compile(optimizer=tf.keras.optimizers.Adam(0.0005),
            loss=CustomLoss(alpha=0.6),
            metrics={'intent': 'accuracy'})

# 时间序列交叉验证
tscv = TimeSeriesSplit(n_splits=5)
for train_index, test_index in tscv.split(X):
    X_train, X_test = X[train_index], X[test_index]
    y_train, y_test = y[train_index], y[test_index]
    
    # 转换标签为操作意图
    y_intent = np.zeros((len(y_train), 7))
    for i, ret in enumerate(y_train):
        if ret > 0.05:  # 大幅上涨
            y_intent[i] = [0,0,0,1,0,0,0]  # 拉升
        elif ret < -0.05:  # 大幅下跌
            y_intent[i] = [0,0,0,0,0,0,1]  # 砸盘
        else:
            y_intent[i] = [0.1,0.2,0.2,0.1,0.2,0.1,0.1]  # 中性分布
    
    model.fit(X_train, y_intent,
            epochs=100,
            batch_size=16,
            validation_split=0.2,
            verbose=1)

# 智能参数优化模块
def optimize_params(df, initial_params):
    # 使用强化学习优化关键参数
    # 此处实现参数搜索算法（示例代码）
    best_params = initial_params.copy()
    best_score = -np.inf
    
    for _ in range(100):
        # 随机扰动参数
        trial_params = initial_params * np.random.normal(1, 0.1, initial_params.shape)
        
        # 计算参数得分
        score = evaluate_params(df, trial_params)
        
        if score > best_score:
            best_score = score
            best_params = trial_params
            
    return best_params

# 可视化模块
import matplotlib.pyplot as plt
import plotly.graph_objects as go


def visualize_analysis(date_range):
    # 生成动态三维可视化
    fig = go.Figure(data=[
        go.Scatter3d(
            x=df['涨跌幅'],
            y=df['market_cost_change'],
            z=df['volume_momentum'],
            mode='markers',
            marker=dict(
                size=8,
                color=df['intent_prob'],
                colorscale='Viridis',
                opacity=0.8
            )
        )
    ])
    
    fig.update_layout(
        scene=dict(
            xaxis_title='Price Change',
            yaxis_title='Cost Change',
            zaxis_title='Volume Momentum'
        ),
        title='三维市场意图分析'
    )
    fig.show()

# 最终预测函数
def predict_intent(historical_data):
    # 输入格式：[SEQ_LENGTH x features]
    processed_data = scaler.transform(historical_data)
    intent_probs, price_pred = model.predict(np.array([processed_data]))
    
    return {
        'intent_probs': dict(zip(targets, intent_probs[0])),
        'price_forecast': float(price_pred[0][0])
    }

# 使用示例
sample_data = df[features].iloc[-SEQ_LENGTH:].values
prediction = predict_intent(sample_data)
print("预测结果:", prediction)