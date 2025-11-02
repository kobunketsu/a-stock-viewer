import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import akshare as ak
import pandas as pd


def calculate_concept_avg_cost(concept_name: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> pd.DataFrame:
    """
    计算概念板块的平均成本（使用线程池并行处理所有成分股）
    :param concept_name: 概念板块名称
    :param progress_callback: 进度回调函数，参数格式(current: int, total: int)
    :return: DataFrame with columns ['日期', '平均成本']
    """
    try:
        print(f"\n开始计算概念板块 [{concept_name}] 的累计平均成本...")
        start_time = time.time()

        # 获取概念板块成分股
        concept_list = ak.stock_board_concept_name_em()
        print("\n可用的概念板块列表:")
        for idx, row in concept_list.iterrows():
            print(f"{idx+1}. {row['板块名称']}")

        # 获取指定板块成分股
        stocks_df = ak.stock_board_concept_cons_em(symbol=concept_name)
        if stocks_df.empty:
            print("未获取到成分股数据")
            return pd.DataFrame(columns=['日期', '平均成本'])

        total_stocks = len(stocks_df)
        print(f"共获取到 {total_stocks} 只成分股")

        # 存储所有成分股的筹码数据
        all_chip_data = []
        failed_stocks = []

        def fetch_stock_chip_data(stock_info):
            """获取单个股票的筹码数据"""
            try:
                code = stock_info['代码']
                name = stock_info.get('名称', code)
                chip_df = ak.stock_cyq_em(symbol=code)

                if not chip_df.empty:
                    # 只保留日期和平均成本列
                    chip_df = chip_df[['日期', '平均成本']]
                    return {'success': True, 'data': chip_df, 'code': code, 'name': name}
                return {'success': False, 'code': code, 'name': name, 'error': '数据为空'}

            except Exception as e:
                return {'success': False, 'code': code, 'name': name, 'error': str(e)}

        # 使用线程池并行处理
        with ThreadPoolExecutor(max_workers=8) as executor:
            # 创建所有任务
            futures = {
                executor.submit(fetch_stock_chip_data, row): row
                for _, row in stocks_df.iterrows()
            }

            # 收集结果
            for index, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result['success']:
                    all_chip_data.append(result['data'])
                    print(f"\r进度: [{index}/{total_stocks}] {result['name']}({result['code']}) 数据获取成功", end="")
                else:
                    failed_stocks.append(f"{result['name']}({result['code']}): {result['error']}")
                    print(f"\r进度: [{index}/{total_stocks}] {result['name']}({result['code']}) 获取失败", end="")
                
                # 新增回调通知
                if progress_callback:
                    progress_callback(index, total_stocks)

        print("\n")  # 换行

        # 输出失败统计
        if failed_stocks:
            print(f"\n获取失败的股票({len(failed_stocks)}):")
            for failed in failed_stocks:
                print(f"- {failed}")

        if not all_chip_data:
            print("未获取到任何有效数据")
            return pd.DataFrame(columns=['日期', '平均成本'])

        # 合并所有成分股的数据
        combined_df = pd.concat(all_chip_data, ignore_index=True)

        # 转换日期列为datetime类型
        combined_df['日期'] = pd.to_datetime(combined_df['日期'])

        # 按日期分组累加平均成本
        result_df = combined_df.groupby('日期')['平均成本'].sum().reset_index()

        # 按日期排序
        result_df = result_df.sort_values('日期')

        end_time = time.time()
        print(f"\n计算完成: 生成了 {len(result_df)} 个交易日的累计平均成本数据")
        print(f"总耗时: {(end_time - start_time):.2f}秒")
        print(f"成功率: {len(all_chip_data)}/{total_stocks} ({len(all_chip_data)/total_stocks*100:.1f}%)")

        return result_df

    except Exception as e:
        print(f"计算概念板块累计平均成本失败: {str(e)}")
        return pd.DataFrame(columns=['日期', '平均成本'])