import akshare as ak
import numpy as np
import pandas as pd
from akshare_wrapper import akshare


class ZhuliPricePredictor:
    """主力成本预测器"""
    
    def __init__(self, symbol: str, days: int = 90, k_base: float = -0.01, max_k: float = -100):
        """
        初始化预测器
        
        Args:
            symbol: 股票代码
            days: 历史数据天数，默认90天
            k_base: 基础k值
            max_k: 最大k值
        """
        self.symbol = symbol
        self.days = days
        self.k_base = k_base
        self.max_k = max_k
        
    def _get_historical_data(self):
        """获取历史数据"""
        end_date = pd.Timestamp.today().strftime("%Y%m%d")
        start_date = (pd.Timestamp.today() - pd.Timedelta(days=self.days)).strftime("%Y%m%d")
        
        # 获取筹码分布数据
        cyq_df = ak.stock_cyq_em(symbol=self.symbol)
        cyq_df['日期'] = pd.to_datetime(cyq_df['日期'])
        
        # 获取历史行情数据
        hist_df = akshare.stock_zh_a_hist(
            symbol=self.symbol,
            start_date=start_date,
            end_date=end_date,
            adjust=""
        )
        hist_df['日期'] = pd.to_datetime(df['日期'])
        
        # 获取流通市值
        info_df = ak.stock_individual_info_em(symbol=self.symbol)
        float_mv = info_df[info_df['item'] == '流通市值']['value'].iloc[0]
        if isinstance(float_mv, str):
            float_mv = float(float_mv.replace('亿', '').replace('万', '')) * 1e8
        else:
            float_mv = float(float_mv) * 1e8
            
        # 合并数据
        df = pd.merge(hist_df, cyq_df, on='日期', how='inner')
        df = df.sort_values('日期').reset_index(drop=True)
        
        # 计算流通股本
        df['流通股本'] = float_mv / df['收盘']
        
        return df
        
    def _calculate_main_cost(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算主力成本
        
        Args:
            df: 包含必要数据的DataFrame
            
        Returns:
            添加了主力成本和散户成本的DataFrame
        """
        # 初始化结果列
        df.loc[0, '主力成本'] = df.loc[0, '平均成本']
        df.loc[0, '散户成本'] = df.loc[0, '平均成本']
        
        # 计算筹码集中度变化
        df['集中度变化'] = df['70集中度'].diff()
        
        # 计算转换系数k
        valid_delta_H = df['集中度变化'][df['集中度变化'] != 0]
        if len(valid_delta_H) == 0:
            return df
        #关键这个K如何正确设置值关系到最终结果准确性
        k = self.k_base / abs(valid_delta_H.mean())
        k = max(k, self.max_k)
        
        # 迭代计算每日主力成本
        for t in range(1, len(df)):
            S_t = df.loc[t, '流通股本']
            S_t_1 = df.loc[t-1, '流通股本']
            
            delta_H = df.loc[t, '集中度变化']
            if pd.isna(delta_H) or abs(delta_H) < 1e-6:
                df.loc[t, '主力成本'] = df.loc[t-1, '主力成本']
                df.loc[t, '散户成本'] = df.loc[t-1, '散户成本']
                continue
                
            delta_S_main = k * delta_H * S_t
            
            A = np.array([
                [delta_S_main, S_t - df.loc[t-1, '主力成本']],
                [S_t_1, -(S_t_1 - df.loc[t-1, '主力成本'])]
            ])
            
            B = np.array([
                df.loc[t, '平均成本'] * S_t - df.loc[t-1, '散户成本'] * (S_t - df.loc[t-1, '主力成本']),
                df.loc[t-1, '平均成本'] * S_t_1
            ])
            
            try:
                solution = np.linalg.solve(A, B)
                main_cost = solution[0]
                retail_cost = (df.loc[t, '平均成本'] * S_t - main_cost * delta_S_main) / (S_t - delta_S_main)
                
                is_valid = (
                    not np.any(np.isnan([main_cost, retail_cost])) and
                    main_cost > df.loc[t, '收盘'] * 0.5 and
                    main_cost < df.loc[t, '平均成本'] and
                    retail_cost > df.loc[t, '收盘'] * 0.5 and
                    retail_cost > main_cost
                )
                
                if is_valid:
                    df.loc[t, '主力成本'] = main_cost
                    df.loc[t, '散户成本'] = retail_cost
                else:
                    df.loc[t, '主力成本'] = df.loc[t-1, '主力成本']
                    df.loc[t, '散户成本'] = df.loc[t-1, '散户成本']
                    
            except np.linalg.LinAlgError:
                df.loc[t, '主力成本'] = df.loc[t-1, '主力成本']
                df.loc[t, '散户成本'] = df.loc[t-1, '散户成本']
        
        return df
    
    def predict(self) -> pd.DataFrame:
        """
        执行主力成本预测
        
        Returns:
            包含预测结果的DataFrame，主要列包括:
            - 日期
            - 收盘
            - 平均成本
            - 主力成本
            - 散户成本
            - 70集中度
        """
        df = self._get_historical_data()
        result_df = self._calculate_main_cost(df)
        
        return result_df[['日期', '收盘', '平均成本', '主力成本', '散户成本', '70集中度']]

def get_stock_zhuli_price(symbol: str, days: int = 90) -> pd.DataFrame:
    """
    获取股票主力成本预测结果
    
    Args:
        symbol: 股票代码
        days: 历史数据天数，默认90天
        
    Returns:
        包含主力成本预测结果的DataFrame
    """
    predictor = ZhuliPricePredictor(symbol, days)
    return predictor.predict()

if __name__ == "__main__":
    # 测试代码
    symbol = "002601"  # 示例股票代码
    days = 90  # 示例天数
    result = get_stock_zhuli_price(symbol, days)
    print(result)

    # 在测试代码部分添加参数扫描
    for k_test in [-0.005, -0.01, -0.02]:
        predictor = ZhuliPricePredictor(symbol="002601", days=90, k_base=k_test)
        result = predictor.predict()
        print('k_base:',k_test)
        print(result)
        # 计算与机构研报数据的误差
        # 这里需要实际接入验证数据
