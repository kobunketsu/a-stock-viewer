import numpy as np
import pandas as pd


def _build_step_series(events_by_index: dict[int, float], total_points: int, cumulative: bool = False) -> np.ndarray:
    """按照当前绘图逻辑构造台阶序列。
    - cumulative=False: 使用“最近事件值保持”的方式（当前实现）
    - cumulative=True: 使用“累计求和”的方式（期望行为）
    """
    series = np.zeros(total_points, dtype=float)
    current_value = 0.0
    for i in range(total_points):
        if i in events_by_index:
            if cumulative:
                current_value += float(events_by_index[i])
            else:
                current_value = float(events_by_index[i])
        series[i] = current_value
    return series


def test_hot_money_step_series_should_accumulate_for_605099():
    """场景: 605099 共创草坪
    输入: 2025-08-01 热门资金净买 0.56万股, 2025-08-04 热门资金净买 3.30万股
    验证: 非累计台阶序列会在 8/4 低于“叠加前日”的累计期望值, 累计台阶应为单调不减。
    """
    # 仅构造关键交易日序列以最小化依赖
    trading_dates = pd.to_datetime(["2025-08-01", "2025-08-04"])  # 两个可见点

    # 模拟资金来源事件: 8/01 热门资金 +0.56万股, 8/04 热门资金 +3.30万股
    # 注意: 单位换算为“股”
    hot_events_df = pd.DataFrame(
        {
            "hot_net_shares": [0.56e4, 3.30e4],
        },
        index=trading_dates,
    )

    # 将交易日期映射到索引位置(与绘图代码一致的思想)
    date_to_idx = {pd.Timestamp(d).strftime("%Y-%m-%d"): i for i, d in enumerate(trading_dates)}
    hot_events_by_index: dict[int, float] = {}
    for dt, row in hot_events_df.iterrows():
        idx = date_to_idx.get(pd.Timestamp(dt).strftime("%Y-%m-%d"))
        if idx is not None:
            hot_events_by_index[idx] = float(row.get("hot_net_shares", 0.0))

    # 构造两种台阶: 当前实现(非累计) 与 期望实现(累计)
    non_cum_series = _build_step_series(hot_events_by_index, total_points=len(trading_dates), cumulative=False)
    cum_series = _build_step_series(hot_events_by_index, total_points=len(trading_dates), cumulative=True)

    # 断言: 当前实现第二点为 3.30万股
    assert np.isclose(non_cum_series[-1], 3.30e4), f"非累计序列末值应等于当日事件值 3.30万股, 实际: {non_cum_series[-1]}"

    # 断言: 累计序列第二点为 0.56万 + 3.30万 = 3.86万股
    assert np.isclose(cum_series[-1], 3.86e4), f"累计序列末值应等于两日之和 3.86万股, 实际: {cum_series[-1]}"

    # 关键验证: 当前实现会出现“后日值 < 前日累计”的现象
    assert non_cum_series[-1] < cum_series[-1], (
        "当前绘图为非累计台阶: 8/4 的 3.30万股小于 ‘叠加前日’ 的 3.86万股, 导致视觉上低于 8/1 期望累计位置。"
    )


def test_expected_cumulative_behavior_monotonicity_for_605099():
    """同一数据下, 累计台阶应当单调; 该用例描述期望行为, 若当前实现未采用累计, 此断言用于指导后续修正。"""
    trading_dates = pd.to_datetime(["2025-08-01", "2025-08-04"])  # 两个可见点
    hot_events_by_index = {0: 0.56e4, 1: 3.30e4}
    cum_series = _build_step_series(hot_events_by_index, total_points=len(trading_dates), cumulative=True)

    # 累计应单调不减
    assert cum_series[1] >= cum_series[0], "累计台阶在后一个事件日不应低于前一事件日的累计值"


