import logging
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Optional, Tuple, Union

import akshare as ak
import pandas as pd


class AKShareWrapper:
    """AKShare API包装类"""
    
    def __init__(self):
        # 股东数据缓存
        self._holders_cache: Dict[str, Tuple[pd.DataFrame, str]] = {}
        
        # API调用频率控制
        self._last_api_call_time = 0.0
        self._min_call_interval = 1.0  # 最小调用间隔（秒）
        self._api_error_count = 0
        self._max_consecutive_errors = 3  # 最大连续错误次数
        self._cooldown_until = 0.0  # 冷却期结束时间
        self._cooldown_duration = 60.0  # 冷却期持续时间（秒）
        
        # 智能重试配置
        self._base_retry_delay = 2.0  # 基础重试延迟（秒）
        self._max_retry_delay = 30.0  # 最大重试延迟（秒）
        self._retry_backoff_factor = 1.5  # 重试延迟递增因子
        self._max_retries = 3  # 最大重试次数
        
        # 熔断器配置
        self._circuit_breaker_failure_threshold = 5  # 熔断器失败阈值
        self._circuit_breaker_timeout = 300.0  # 熔断器超时时间（秒）
        self._circuit_breaker_failure_count = 0  # 当前失败计数
        self._circuit_breaker_last_failure_time = 0.0  # 上次失败时间
        self._circuit_breaker_state = "CLOSED"  # 熔断器状态: CLOSED, OPEN, HALF_OPEN
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
    
    def _is_in_cooldown(self) -> bool:
        """检查是否在冷却期内"""
        return time.time() < self._cooldown_until
    
    def _start_cooldown(self):
        """开始冷却期"""
        self._cooldown_until = time.time() + self._cooldown_duration
        self.logger.warning(f"API调用进入冷却期，持续 {self._cooldown_duration} 秒")
    
    def _reset_error_count(self):
        """重置错误计数"""
        self._api_error_count = 0
    
    def _increment_error_count(self):
        """增加错误计数"""
        self._api_error_count += 1
        if self._api_error_count >= self._max_consecutive_errors:
            self._start_cooldown()
            self._reset_error_count()
    
    def _wait_for_rate_limit(self):
        """等待API调用频率限制"""
        current_time = time.time()
        time_since_last_call = current_time - self._last_api_call_time
        
        if time_since_last_call < self._min_call_interval:
            sleep_time = self._min_call_interval - time_since_last_call
            time.sleep(sleep_time)
        
        self._last_api_call_time = time.time()
    
    def _is_connection_error(self, error: Exception) -> bool:
        """判断是否为连接错误"""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # 网络连接相关错误
        connection_errors = [
            'connection aborted',
            'remote end closed connection',
            'remote disconnected',
            'connection reset',
            'timeout',
            'network is unreachable',
            'name or service not known',
            'connection refused',
            'connection timeout',
            'read timeout',
            'connect timeout',
            'ssl error',
            'certificate verify failed',
            'connection pool is full',
            'too many connections',
            'connection broken',
            'connection lost',
            'socket error',
            'network error',
            'http error',
            'urllib error',
            'requests error'
        ]
        
        # 检查错误消息
        is_connection_by_msg = any(err in error_str for err in connection_errors)
        
        # 检查错误类型
        connection_error_types = [
            'connectionerror',
            'timeouterror',
            'httperror',
            'urlerror',
            'sslerror',
            'socketerror',
            'requestsconnectionerror',
            'requestsreadtimeout',
            'requestsconnecttimeout',
            'requestshttperror'
        ]
        is_connection_by_type = any(err_type in error_type for err_type in connection_error_types)
        
        return is_connection_by_msg or is_connection_by_type
    
    def _is_circuit_breaker_open(self) -> bool:
        """检查熔断器是否开启"""
        if self._circuit_breaker_state == "OPEN":
            current_time = time.time()
            if current_time - self._circuit_breaker_last_failure_time >= self._circuit_breaker_timeout:
                # 超时后转为半开状态
                self._circuit_breaker_state = "HALF_OPEN"
                self.logger.info("熔断器转为半开状态，允许测试调用")
                return False
            return True
        return False
    
    def _record_circuit_breaker_success(self):
        """记录熔断器成功调用"""
        if self._circuit_breaker_state == "HALF_OPEN":
            # 半开状态下成功，关闭熔断器
            self._circuit_breaker_state = "CLOSED"
            self._circuit_breaker_failure_count = 0
            self.logger.info("熔断器关闭，恢复正常调用")
    
    def _record_circuit_breaker_failure(self):
        """记录熔断器失败调用"""
        self._circuit_breaker_failure_count += 1
        self._circuit_breaker_last_failure_time = time.time()
        
        if self._circuit_breaker_failure_count >= self._circuit_breaker_failure_threshold:
            self._circuit_breaker_state = "OPEN"
            self.logger.warning(f"熔断器开启，失败次数: {self._circuit_breaker_failure_count}")
    
    def _api_call_with_retry(self, func, *args, **kwargs):
        """带重试机制和熔断器的API调用"""
        # 检查熔断器状态
        if self._is_circuit_breaker_open():
            self.logger.warning("熔断器开启，跳过API调用")
            return pd.DataFrame()
        
        # 检查是否在冷却期
        if self._is_in_cooldown():
            remaining_time = self._cooldown_until - time.time()
            self.logger.warning(f"API调用在冷却期内，剩余 {remaining_time:.1f} 秒")
            return pd.DataFrame()
        
        # 等待频率限制
        self._wait_for_rate_limit()
        
        for attempt in range(self._max_retries + 1):
            try:
                result = func(*args, **kwargs)
                # 成功调用，重置错误计数和熔断器
                self._reset_error_count()
                self._record_circuit_breaker_success()
                return result
                
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                self.logger.error(f"API调用失败 (尝试 {attempt + 1}/{self._max_retries + 1}): {error_type}: {error_msg}")
                
                # 记录详细的错误信息用于调试
                if hasattr(e, '__traceback__'):
                    import traceback
                    tb_str = ''.join(traceback.format_tb(e.__traceback__))
                    self.logger.debug(f"详细错误堆栈:\n{tb_str}")
                
                # 如果是连接错误，增加错误计数和熔断器失败计数
                if self._is_connection_error(e):
                    self._increment_error_count()
                    self._record_circuit_breaker_failure()
                    self.logger.warning(f"检测到连接错误，当前错误计数: {self._api_error_count}/{self._max_consecutive_errors}")
                    
                    # 如果达到最大错误次数，进入冷却期
                    if self._api_error_count >= self._max_consecutive_errors:
                        self.logger.error("连续API调用失败次数过多，进入冷却期")
                        return pd.DataFrame()
                else:
                    # 非连接错误，记录但不计入错误计数，但计入熔断器失败计数
                    self._record_circuit_breaker_failure()
                    self.logger.warning(f"非连接错误，不增加错误计数: {error_type}")
                
                # 如果不是最后一次尝试，使用智能退避算法计算等待时间
                if attempt < self._max_retries:
                    # 指数退避算法：基础延迟 * (退避因子 ^ 尝试次数)
                    wait_time = min(
                        self._base_retry_delay * (self._retry_backoff_factor ** attempt),
                        self._max_retry_delay
                    )
                    self.logger.info(f"等待 {wait_time:.1f} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    # 最后一次尝试失败
                    self.logger.error(f"所有重试尝试都失败了，最终错误: {error_type}: {error_msg}")
                    return pd.DataFrame()
    
    def get_api_status(self) -> dict:
        """获取API状态信息
        @return: 包含API状态信息的字典
        """
        current_time = time.time()
        is_cooldown = self._is_in_cooldown()
        remaining_cooldown = max(0, self._cooldown_until - current_time) if is_cooldown else 0
        
        return {
            'is_in_cooldown': is_cooldown,
            'remaining_cooldown': remaining_cooldown,
            'error_count': self._api_error_count,
            'max_consecutive_errors': self._max_consecutive_errors,
            'min_call_interval': self._min_call_interval,
            'last_call_time': self._last_api_call_time,
            'circuit_breaker_state': self._circuit_breaker_state,
            'circuit_breaker_failure_count': self._circuit_breaker_failure_count,
            'circuit_breaker_failure_threshold': self._circuit_breaker_failure_threshold,
            'circuit_breaker_timeout': self._circuit_breaker_timeout
        }
    
    def reset_api_status(self):
        """重置API状态（用于测试或手动恢复）"""
        self._api_error_count = 0
        self._cooldown_until = 0.0
        self._circuit_breaker_failure_count = 0
        self._circuit_breaker_state = "CLOSED"
        self._last_api_call_time = 0.0
        self.logger.info("API状态已重置")
    
    def _get_latest_quarter_date(self) -> str:
        """获取最近有数据的季度末日期（考虑数据发布延迟）
        @return: 日期字符串，格式YYYYMMDD
        """
        today = datetime.now()
        year = today.year
        
        # 生成候选日期，从最近的开始
        candidate_dates = []
        
        # 当前年的季度（按时间倒序）
        quarterly_dates = [
            f"{year}1231",    # Q4（12月31日）
            f"{year}0930",    # Q3（9月30日）
            f"{year}0630",    # Q2（6月30日）
            f"{year}0331",    # Q1（3月31日）
        ]
        candidate_dates.extend(quarterly_dates)
        
        # 前一年的季度
        prev_year_dates = [
            f"{year-1}1231",  # 上一年Q4（12月31日）
            f"{year-1}0930",  # 上一年Q3（9月30日）
            f"{year-1}0630",  # 上一年Q2（6月30日）
            f"{year-1}0331"   # 上一年Q1（3月31日）
        ]
        candidate_dates.extend(prev_year_dates)
        
        # 只保留过去的日期（至少3个月前，考虑数据发布延迟）
        current_date_int = int(today.strftime('%Y%m%d'))
        delay_date = today.replace(day=1) - pd.DateOffset(months=3)  # 3个月前
        delay_date_int = int(delay_date.strftime('%Y%m%d'))
        
        valid_dates = [d for d in candidate_dates if int(d) <= delay_date_int]
        
        if not valid_dates:
            # 兜底：返回上一年最后一个季度
            return f"{year-1}1231"
        
        # 返回最近的有效日期
        return valid_dates[0]

    def _get_quarters_between_dates(self, start_date: str, end_date: str) -> list[str]:
        """获取指定日期范围内的所有季度末日期
        @param start_date: 开始日期字符串，格式YYYY-MM-DD
        @param end_date: 结束日期字符串，格式YYYY-MM-DD
        @return: 季度末日期列表，格式YYYYMMDD
        """
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        quarters = []
        current_year = start_dt.year
        
        # 生成所有可能的季度末日期
        while current_year <= end_dt.year:
            for quarter_end in ["0331", "0630", "0930", "1231"]:
                quarter_date = f"{current_year}{quarter_end}"
                quarter_dt = datetime.strptime(quarter_date, "%Y%m%d")
                
                # 检查是否在指定范围内
                if start_dt <= quarter_dt <= end_dt:
                    quarters.append(quarter_date)
            
            current_year += 1
        
        return quarters

    def _get_holders_data(self, date: str) -> pd.DataFrame:
        """获取指定日期的股东数据，优先使用缓存
        @param date: 日期字符串，格式YYYYMMDD
        @return: DataFrame
        """
        try:
            # 检查缓存
            if date in self._holders_cache:
                cached_df, cache_date = self._holders_cache[date]
                # 如果是当天的数据，直接返回
                if cache_date == datetime.now().strftime('%Y%m%d'):
                    if not cached_df.empty:
                        return cached_df
            
            print(f"正在获取股东数据，日期: {date}")
            
            # 获取新数据 - 添加异常处理来捕获akshare的bug
            try:
                df = ak.stock_hold_num_cninfo(date=date)
            except ValueError as ve:
                if "Length mismatch" in str(ve) and "Expected axis has 0 elements" in str(ve):
                    print(f"akshare库bug：日期 {date} 返回空数据但尝试设置列名，跳过此日期")
                    return pd.DataFrame()
                else:
                    raise ve
            
            # 验证数据格式
            if df is None or df.empty:
                print(f"akshare返回空数据，日期: {date}")
                return pd.DataFrame()
            
            # 创建一个新的DataFrame副本，避免引用问题
            df = df.copy()
            
            # 确保必要的列存在
            required_columns = ['证券代码', '本期股东人数', '上期股东人数', '股东人数增幅', 
                              '本期人均持股数量', '上期人均持股数量', '人均持股数量增幅']
            
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                print(f"股东数据缺少列: {missing_columns}，日期: {date}")
                print(f"实际列名: {list(df.columns)}")
                return pd.DataFrame()
            
            print(f"成功获取股东数据，数据行数: {len(df)}，日期: {date}")
            
            # 更新缓存（使用副本）
            self._holders_cache[date] = (df.copy(), datetime.now().strftime('%Y%m%d'))
            return df
            
        except Exception as e:
            print(f"获取股东数据失败，日期: {date}, 错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    def stock_zh_a_hist(self, symbol: str, period: str = "daily", 
                       start_date: Optional[str] = None, end_date: Optional[str] = None,
                       adjust: str = "") -> pd.DataFrame:
        """获取A股历史数据（支持多API备用机制）
        @param symbol: 股票代码
        @param period: 周期，默认daily
        @param start_date: 开始日期，格式YYYYMMDD
        @param end_date: 结束日期，格式YYYYMMDD
        @param adjust: 复权类型，默认不复权
        @return: DataFrame
        """
        # 尝试多个API接口
        apis_to_try = [
            self._try_akshare_primary,
            self._try_akshare_alternative,
            self._try_akshare_minimal
        ]
        
        for api_func in apis_to_try:
            try:
                result = api_func(symbol, period, start_date, end_date, adjust)
                if not result.empty:
                    self.logger.info(f"成功获取股票历史数据 {symbol}，使用API: {api_func.__name__}")
                    return result
            except Exception as e:
                self.logger.warning(f"API {api_func.__name__} 失败: {e}")
                continue
        
        self.logger.error(f"所有API都失败，无法获取股票历史数据 {symbol}")
        return pd.DataFrame()
    
    def _try_akshare_primary(self, symbol: str, period: str, start_date: Optional[str], 
                           end_date: Optional[str], adjust: str) -> pd.DataFrame:
        """尝试主要akshare接口"""
        def _call_akshare():
            if start_date is not None and end_date is not None:
                return ak.stock_zh_a_hist(symbol=symbol, period=period, 
                                        start_date=start_date, end_date=end_date, adjust=adjust)
            elif start_date is not None:
                return ak.stock_zh_a_hist(symbol=symbol, period=period, 
                                        start_date=start_date, adjust=adjust)
            elif end_date is not None:
                return ak.stock_zh_a_hist(symbol=symbol, period=period, 
                                        end_date=end_date, adjust=adjust)
            else:
                return ak.stock_zh_a_hist(symbol=symbol, period=period, adjust=adjust)
        
        return self._api_call_with_retry(_call_akshare)
    
    def _try_akshare_alternative(self, symbol: str, period: str, start_date: Optional[str], 
                               end_date: Optional[str], adjust: str) -> pd.DataFrame:
        """尝试备用akshare接口（使用不同的参数组合）"""
        def _call_akshare_alt():
            # 尝试使用不同的复权方式
            alt_adjust = "qfq" if adjust == "" else adjust
            if start_date is not None and end_date is not None:
                return ak.stock_zh_a_hist(symbol=symbol, period=period, 
                                        start_date=start_date, end_date=end_date, adjust=alt_adjust)
            elif start_date is not None:
                return ak.stock_zh_a_hist(symbol=symbol, period=period, 
                                        start_date=start_date, adjust=alt_adjust)
            elif end_date is not None:
                return ak.stock_zh_a_hist(symbol=symbol, period=period, 
                                        end_date=end_date, adjust=alt_adjust)
            else:
                return ak.stock_zh_a_hist(symbol=symbol, period=period, adjust=alt_adjust)
        
        return self._api_call_with_retry(_call_akshare_alt)
    
    def _try_akshare_minimal(self, symbol: str, period: str, start_date: Optional[str], 
                           end_date: Optional[str], adjust: str) -> pd.DataFrame:
        """尝试最小化参数的akshare接口"""
        def _call_akshare_min():
            # 只使用最基本的参数
            return ak.stock_zh_a_hist(symbol=symbol, period=period, adjust="")
        
        return self._api_call_with_retry(_call_akshare_min)
    
    def stock_zh_a_spot_em(self) -> pd.DataFrame:
        """获取A股实时行情
        @return: DataFrame
        """
        return self._api_call_with_retry(ak.stock_zh_a_spot_em)
    
    def stock_individual_info_em(self, symbol: str) -> pd.DataFrame:
        """获取个股信息
        @param symbol: 股票代码
        @return: DataFrame
        """
        return self._api_call_with_retry(ak.stock_individual_info_em, symbol=symbol)
    
    def stock_info_a_code_name(self) -> pd.DataFrame:
        """获取A股代码和名称
        @return: DataFrame
        """
        return ak.stock_info_a_code_name()
    
    def stock_cyq_em(self, symbol: str, adjust: str = "qfq") -> pd.DataFrame:
        """获取股票筹码分布
        @param symbol: 股票代码
        @param adjust: 复权类型，默认不复权
        @return: DataFrame
        """
        return ak.stock_cyq_em(symbol=symbol, adjust=adjust)
    
    def stock_board_industry_name_em(self) -> pd.DataFrame:
        """获取行业板块列表
        @return: DataFrame
        """
        return ak.stock_board_industry_name_em()
    
    def stock_board_concept_hist_em(self, symbol: str, period: str = "daily",
                                  start_date: Optional[str] = None, end_date: Optional[str] = None,
                                  adjust: str = "") -> pd.DataFrame:
        """获取概念板块历史数据
        @param symbol: 板块代码
        @param period: 周期，默认daily
        @param start_date: 开始日期，格式YYYYMMDD
        @param end_date: 结束日期，格式YYYYMMDD
        @param adjust: 复权类型，默认不复权
        @return: DataFrame
        """
        try:
            # 直接调用，避免kwargs可能的类型问题
            if start_date is not None and end_date is not None:
                return ak.stock_board_concept_hist_em(symbol=symbol, period=period, 
                                                    start_date=start_date, end_date=end_date, adjust=adjust)
            elif start_date is not None:
                return ak.stock_board_concept_hist_em(symbol=symbol, period=period, 
                                                    start_date=start_date, adjust=adjust)
            elif end_date is not None:
                return ak.stock_board_concept_hist_em(symbol=symbol, period=period, 
                                                    end_date=end_date, adjust=adjust)
            else:
                return ak.stock_board_concept_hist_em(symbol=symbol, period=period, adjust=adjust)
        except Exception as e:
            print(f"获取板块历史数据失败 {symbol}: {str(e)}")
            return pd.DataFrame()
    
    def stock_board_concept_name_em(self) -> pd.DataFrame:
        """获取概念板块列表
        @return: DataFrame
        """
        return ak.stock_board_concept_name_em()
    
    def stock_board_concept_cons_em(self, symbol: str) -> pd.DataFrame:
        """获取概念板块成分股
        @param symbol: 板块代码
        @return: DataFrame
        """
        return ak.stock_board_concept_cons_em(symbol=symbol)
    
        
    def fund_etf_hist_em(self, symbol: str, period: str = "daily",
                        start_date: Optional[str] = None, end_date: Optional[str] = None,
                        adjust: str = "") -> pd.DataFrame:
        """获取ETF历史数据
        @param symbol: ETF代码
        @param period: 周期，默认daily
        @param start_date: 开始日期，格式YYYYMMDD
        @param end_date: 结束日期，格式YYYYMMDD
        @param adjust: 复权类型，默认不复权
        @return: DataFrame
        """
        def _call_akshare():
            # 直接调用，避免kwargs可能的类型问题
            if start_date is not None and end_date is not None:
                return ak.fund_etf_hist_em(symbol=symbol, period=period, 
                                         start_date=start_date, end_date=end_date, adjust=adjust)
            elif start_date is not None:
                return ak.fund_etf_hist_em(symbol=symbol, period=period, 
                                         start_date=start_date, adjust=adjust)
            elif end_date is not None:
                return ak.fund_etf_hist_em(symbol=symbol, period=period, 
                                         end_date=end_date, adjust=adjust)
            else:
                return ak.fund_etf_hist_em(symbol=symbol, period=period, adjust=adjust)
        
        result = self._api_call_with_retry(_call_akshare)
        if result.empty:
            self.logger.error(f"获取ETF历史数据失败 {symbol}: 所有重试尝试都失败了")
        return result
    

    
    def fund_etf_spot_em(self) -> pd.DataFrame:
        """获取ETF实时行情（使用多API备用机制）
        @return: DataFrame
        """
        from etf_data_fetcher import get_etf_spot_data
        return get_etf_spot_data(use_cache=True)
        
    def tool_trade_date_hist_sina(self) -> pd.DataFrame:
        """获取历史交易日期
        @return: DataFrame
        """
        return ak.tool_trade_date_hist_sina()

    def get_holders_historical_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取指定时间范围内的历史股东数据
        @param symbol: 股票代码
        @param start_date: 开始日期，格式YYYY-MM-DD
        @param end_date: 结束日期，格式YYYY-MM-DD
        @return: DataFrame，包含股东人数变化和人均持股变化数据
        """
        try:
            # 获取时间范围内的所有季度末日期
            quarter_dates = self._get_quarters_between_dates(start_date, end_date)
            
            if not quarter_dates:
                print(f"指定时间范围内没有季度数据: {start_date} 到 {end_date}")
                return pd.DataFrame()
            
            all_data = []
            
            for date in quarter_dates:
                try:
                    # 获取当期股东数据
                    df = self._get_holders_data(date)
                    
                    if df.empty:
                        continue
                    
                    # 查找对应的股票数据
                    stock_data = df[df['证券代码'] == symbol]
                    if not stock_data.empty:
                        row = stock_data.iloc[0]
                        
                        # 验证所有必要的字段都存在且有效
                        required_fields = ['本期股东人数', '上期股东人数', '股东人数增幅',
                                         '本期人均持股数量', '上期人均持股数量', '人均持股数量增幅']
                        
                        valid_data = True
                        data_dict = {'日期': pd.to_datetime(date, format='%Y%m%d')}
                        
                        for field in required_fields:
                            if field in row.index and pd.notna(row[field]):
                                data_dict[field] = row[field]
                            else:
                                print(f"字段 {field} 缺失或无效，日期: {date}, 股票: {symbol}")
                                valid_data = False
                                break
                        
                        if valid_data:
                            all_data.append(data_dict)
                        
                except Exception as e:
                    print(f"获取{date}数据失败: {str(e)}")
                    continue
            
            if not all_data:
                print(f"未获取到股票{symbol}的有效股东数据")
                return pd.DataFrame()
            
            # 安全地转换为DataFrame
            try:
                result_df = pd.DataFrame(all_data)
                if '日期' in result_df.columns and not result_df.empty:
                    result_df.set_index('日期', inplace=True)
                    return result_df
                else:
                    print(f"DataFrame创建失败，股票: {symbol}")
                    return pd.DataFrame()
            except Exception as df_error:
                print(f"DataFrame转换失败 {symbol}: {str(df_error)}")
                return pd.DataFrame()
            
        except Exception as e:
            print(f"获取历史股东数据失败 {symbol}: {str(e)}")
            return pd.DataFrame()

    def get_latest_holders_count(self, symbol: str) -> tuple[Optional[float], str]:
        """获取最新的股东人数
        @param symbol: 股票代码
        @return: tuple(股东人数(万), 统计日期)，如果获取失败返回(None, '')
        """
        try:
            # 获取最近的季度末日期
            date = self._get_latest_quarter_date()
            print(f"股票{symbol}选择的查询日期: {date}")
            
            # 获取股东人数数据（使用缓存）
            df = self._get_holders_data(date)
            
            if df.empty:
                print(f"未获取到股东数据，股票: {symbol}，日期: {date}")
                return None, ''
            
            # 查找对应的股票数据
            stock_data = df[df['证券代码'] == symbol]
            if not stock_data.empty:
                row = stock_data.iloc[0]
                
                # 验证本期股东人数字段是否存在且有效
                if '本期股东人数' in row.index and pd.notna(row['本期股东人数']):
                    try:
                        holders_count = float(row['本期股东人数'])
                        # 转换为万为单位，保留一位小数
                        holders_count_wan = round(holders_count / 10000, 1)
                        print(f"股票{symbol}股东人数: {holders_count_wan}万，日期: {date}")
                        return holders_count_wan, date
                    except (ValueError, TypeError) as e:
                        print(f"股东人数数值转换失败 {symbol}: {str(e)}")
                        return None, ''
                else:
                    print(f"股东人数字段缺失或无效 {symbol}, 日期: {date}")
                    return None, ''
            else:
                print(f"未找到股票{symbol}的股东数据，日期: {date}")
            
            return None, ''
            
        except Exception as e:
            print(f"获取股东人数失败 {symbol}: {str(e)}")
            return None, ''
    
    def stock_lhb_jgmmtj_em(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取龙虎榜机构买卖每日统计数据
        
        Args:
            start_date: 开始日期，格式YYYYMMDD
            end_date: 结束日期，格式YYYYMMDD
            
        Returns:
            包含龙虎榜机构买卖数据的DataFrame
        """
        try:
            return ak.stock_lhb_jgmmtj_em(start_date=start_date, end_date=end_date)
        except Exception as e:
            print(f"获取龙虎榜数据失败: {str(e)}")
            return pd.DataFrame()

    def stock_lhb_stock_detail_em(self, symbol: str, date: str, flag: str) -> pd.DataFrame:
        """
        获取个股龙虎榜详情
        
        Args:
            symbol: 股票代码，如"600077"
            date: 日期，格式YYYYMMDD，如"20220310"
            flag: 买卖标志，"买入"或"卖出"
            
        Returns:
            包含龙虎榜详情数据的DataFrame
        """
        try:
            result = ak.stock_lhb_stock_detail_em(symbol=symbol, date=date, flag=flag)
            # 确保返回的是DataFrame而不是None
            if result is None:
                return pd.DataFrame()
            return result
        except Exception as e:
            print(f"获取个股龙虎榜详情失败: {str(e)}")
            return pd.DataFrame()

    def stock_lhb_stock_detail_date_em(self, symbol: str) -> pd.DataFrame:
        """
        获取个股有龙虎榜详情数据的日期列表
        
        Args:
            symbol: 股票代码，如"600077"
            
        Returns:
            包含日期列表的DataFrame
        """
        try:
            return ak.stock_lhb_stock_detail_date_em(symbol=symbol)
        except Exception as e:
            print(f"获取个股龙虎榜日期列表失败: {str(e)}")
            return pd.DataFrame()

    def index_zh_a_hist(self, symbol: str, period: str = "daily", 
                       start_date: Optional[str] = None, end_date: Optional[str] = None,
                       adjust: str = "") -> pd.DataFrame:
        """获取指数历史数据
        @param symbol: 指数代码，上证指数为"000001"
        @param period: 周期，默认daily
        @param start_date: 开始日期，格式YYYYMMDD
        @param end_date: 结束日期，格式YYYYMMDD
        @param adjust: 复权类型，默认不复权（指数数据通常不复权）
        @return: DataFrame
        """
        def _call_akshare():
            # 指数数据通常不需要复权，直接调用
            if start_date is not None and end_date is not None:
                return ak.index_zh_a_hist(symbol=symbol, period=period, 
                                        start_date=start_date, end_date=end_date)
            elif start_date is not None:
                return ak.index_zh_a_hist(symbol=symbol, period=period, 
                                        start_date=start_date)
            elif end_date is not None:
                return ak.index_zh_a_hist(symbol=symbol, period=period, 
                                        end_date=end_date)
            else:
                return ak.index_zh_a_hist(symbol=symbol, period=period)
        
        result = self._api_call_with_retry(_call_akshare)
        if result.empty:
            self.logger.error(f"获取指数历史数据失败 {symbol}: 所有重试尝试都失败了")
        return result
    
    def index_zh_a_hist_min_em(self, symbol: str, period: str = "1", 
                              start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """获取指数分时数据
        @param symbol: 指数代码，上证指数为"000001"
        @param period: 周期，"1"表示1分钟，其他可选值包括"5"、"15"、"30"、"60"
        @param start_date: 开始日期时间，格式为"YYYY-MM-DD HH:MM:SS"
        @param end_date: 结束日期时间，格式为"YYYY-MM-DD HH:MM:SS"
        @return: DataFrame
        """
        try:
            # 指数分时数据通常不需要复权，直接调用
            if start_date is not None and end_date is not None:
                return ak.index_zh_a_hist_min_em(symbol=symbol, period=period, 
                                               start_date=start_date, end_date=end_date)
            elif start_date is not None:
                return ak.index_zh_a_hist_min_em(symbol=symbol, period=period, 
                                               start_date=start_date)
            elif end_date is not None:
                return ak.index_zh_a_hist_min_em(symbol=symbol, period=period, 
                                               end_date=end_date)
            else:
                return ak.index_zh_a_hist_min_em(symbol=symbol, period=period)
        except Exception as e:
            print(f"获取指数分时数据失败 {symbol}: {str(e)}")
            return pd.DataFrame()

# 创建全局单例实例
akshare = AKShareWrapper() 