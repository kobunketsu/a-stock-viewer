"""
ETF API监控和日志记录模块
提供性能监控、错误日志记录和API健康状态检查功能
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


class ETFAPIMonitor:
    """ETF API监控器"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # 设置日志
        self._setup_logging()
        
        # 性能统计
        self.performance_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_response_time': 0.0,
            'api_stats': {
                'eastmoney': {'requests': 0, 'success': 0, 'avg_time': 0.0},
                'ths': {'requests': 0, 'success': 0, 'avg_time': 0.0},
                'sina': {'requests': 0, 'success': 0, 'avg_time': 0.0}
            }
        }
        
        # 错误历史
        self.error_history: List[Dict] = []
        
        # 健康状态
        self.health_status = {
            'last_successful_request': None,
            'consecutive_failures': 0,
            'is_healthy': True
        }
    
    def _setup_logging(self):
        """设置日志记录"""
        # 创建日志文件路径
        log_file = self.log_dir / f"etf_api_{datetime.now().strftime('%Y%m%d')}.log"
        
        # 配置日志格式
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        
        self.logger = logging.getLogger('ETFAPIMonitor')
    
    def log_request(self, api_name: str, success: bool, response_time: float, 
                   error_msg: str = None, data_count: int = 0):
        """记录API请求
        
        @param api_name: API名称
        @param success: 是否成功
        @param response_time: 响应时间（毫秒）
        @param error_msg: 错误信息
        @param data_count: 返回数据条数
        """
        # 更新统计信息
        self.performance_stats['total_requests'] += 1
        self.performance_stats['total_response_time'] += response_time
        
        if success:
            self.performance_stats['successful_requests'] += 1
            self.health_status['last_successful_request'] = datetime.now()
            self.health_status['consecutive_failures'] = 0
            self.health_status['is_healthy'] = True
        else:
            self.performance_stats['failed_requests'] += 1
            self.health_status['consecutive_failures'] += 1
            if self.health_status['consecutive_failures'] >= 5:
                self.health_status['is_healthy'] = False
        
        # 更新API特定统计
        api_stats = self.performance_stats['api_stats'][api_name]
        api_stats['requests'] += 1
        if success:
            api_stats['success'] += 1
        
        # 计算平均响应时间
        if api_stats['requests'] > 0:
            api_stats['avg_time'] = (
                (api_stats['avg_time'] * (api_stats['requests'] - 1) + response_time) 
                / api_stats['requests']
            )
        
        # 记录错误
        if not success and error_msg:
            error_record = {
                'timestamp': datetime.now().isoformat(),
                'api_name': api_name,
                'error_message': error_msg,
                'response_time': response_time
            }
            self.error_history.append(error_record)
            
            # 保持错误历史在合理范围内
            if len(self.error_history) > 1000:
                self.error_history = self.error_history[-500:]
        
        # 记录日志
        if success:
            self.logger.info(
                f"[{api_name}] 请求成功 - 响应时间: {response_time:.2f}ms, "
                f"数据条数: {data_count}"
            )
        else:
            self.logger.error(
                f"[{api_name}] 请求失败 - 响应时间: {response_time:.2f}ms, "
                f"错误: {error_msg}"
            )
    
    def get_performance_summary(self) -> Dict:
        """获取性能摘要
        
        @return: 性能统计字典
        """
        total_requests = self.performance_stats['total_requests']
        if total_requests == 0:
            return {
                'total_requests': 0,
                'success_rate': 0.0,
                'avg_response_time': 0.0,
                'is_healthy': self.health_status['is_healthy']
            }
        
        success_rate = (self.performance_stats['successful_requests'] / total_requests) * 100
        avg_response_time = self.performance_stats['total_response_time'] / total_requests
        
        return {
            'total_requests': total_requests,
            'success_rate': round(success_rate, 2),
            'avg_response_time': round(avg_response_time, 2),
            'is_healthy': self.health_status['is_healthy'],
            'consecutive_failures': self.health_status['consecutive_failures'],
            'last_successful_request': self.health_status['last_successful_request'].isoformat() 
                if self.health_status['last_successful_request'] else None
        }
    
    def get_api_health_status(self) -> Dict:
        """获取各API健康状态
        
        @return: API健康状态字典
        """
        health_status = {}
        
        for api_name, stats in self.performance_stats['api_stats'].items():
            if stats['requests'] == 0:
                health_status[api_name] = {
                    'status': 'unknown',
                    'success_rate': 0.0,
                    'avg_response_time': 0.0,
                    'requests': 0
                }
            else:
                success_rate = (stats['success'] / stats['requests']) * 100
                health_status[api_name] = {
                    'status': 'healthy' if success_rate > 80 else 'degraded' if success_rate > 50 else 'unhealthy',
                    'success_rate': round(success_rate, 2),
                    'avg_response_time': round(stats['avg_time'], 2),
                    'requests': stats['requests']
                }
        
        return health_status
    
    def get_recent_errors(self, hours: int = 24) -> List[Dict]:
        """获取最近的错误记录
        
        @param hours: 最近多少小时的错误
        @return: 错误记录列表
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_errors = []
        for error in self.error_history:
            error_time = datetime.fromisoformat(error['timestamp'])
            if error_time >= cutoff_time:
                recent_errors.append(error)
        
        return recent_errors
    
    def export_performance_report(self, file_path: str = None) -> str:
        """导出性能报告
        
        @param file_path: 导出文件路径，如果为None则自动生成
        @return: 导出文件路径
        """
        if file_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_path = self.log_dir / f"etf_performance_report_{timestamp}.json"
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'performance_summary': self.get_performance_summary(),
            'api_health_status': self.get_api_health_status(),
            'recent_errors': self.get_recent_errors(24),
            'detailed_stats': self.performance_stats
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"性能报告已导出到: {file_path}")
        return str(file_path)
    
    def reset_stats(self):
        """重置统计信息"""
        self.performance_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_response_time': 0.0,
            'api_stats': {
                'eastmoney': {'requests': 0, 'success': 0, 'avg_time': 0.0},
                'ths': {'requests': 0, 'success': 0, 'avg_time': 0.0},
                'sina': {'requests': 0, 'success': 0, 'avg_time': 0.0}
            }
        }
        
        self.error_history.clear()
        self.health_status = {
            'last_successful_request': None,
            'consecutive_failures': 0,
            'is_healthy': True
        }
        
        self.logger.info("统计信息已重置")
    
    def print_status_report(self):
        """打印状态报告"""
        print("\n" + "="*60)
        print("ETF API 监控状态报告")
        print("="*60)
        
        # 性能摘要
        summary = self.get_performance_summary()
        print(f"总请求数: {summary['total_requests']}")
        print(f"成功率: {summary['success_rate']}%")
        print(f"平均响应时间: {summary['avg_response_time']:.2f}ms")
        print(f"系统健康状态: {'健康' if summary['is_healthy'] else '异常'}")
        
        if summary['consecutive_failures'] > 0:
            print(f"连续失败次数: {summary['consecutive_failures']}")
        
        if summary['last_successful_request']:
            print(f"最后成功请求: {summary['last_successful_request']}")
        
        # API健康状态
        print("\n各API健康状态:")
        print("-" * 40)
        health_status = self.get_api_health_status()
        
        for api_name, status in health_status.items():
            status_text = {
                'healthy': '健康',
                'degraded': '降级',
                'unhealthy': '异常',
                'unknown': '未知'
            }.get(status['status'], '未知')
            
            print(f"{api_name:>12}: {status_text:>4} "
                  f"(成功率: {status['success_rate']:>5.1f}%, "
                  f"平均响应: {status['avg_response_time']:>6.1f}ms, "
                  f"请求数: {status['requests']:>3})")
        
        # 最近错误
        recent_errors = self.get_recent_errors(24)
        if recent_errors:
            print(f"\n最近24小时错误数: {len(recent_errors)}")
            print("最近5个错误:")
            for error in recent_errors[-5:]:
                print(f"  {error['timestamp']} - {error['api_name']}: {error['error_message']}")
        
        print("="*60)


# 创建全局监控实例
api_monitor = ETFAPIMonitor()


def log_etf_api_request(api_name: str, success: bool, response_time: float, 
                       error_msg: str = None, data_count: int = 0):
    """记录ETF API请求（便捷函数）
    
    @param api_name: API名称
    @param success: 是否成功
    @param response_time: 响应时间（毫秒）
    @param error_msg: 错误信息
    @param data_count: 返回数据条数
    """
    api_monitor.log_request(api_name, success, response_time, error_msg, data_count)


def get_etf_api_status():
    """获取ETF API状态（便捷函数）
    
    @return: API状态字典
    """
    return {
        'performance': api_monitor.get_performance_summary(),
        'api_health': api_monitor.get_api_health_status()
    }


def print_etf_api_status():
    """打印ETF API状态报告（便捷函数）"""
    api_monitor.print_status_report()


if __name__ == "__main__":
    # 测试监控功能
    print("测试ETF API监控器...")
    
    # 模拟一些请求
    log_etf_api_request('eastmoney', True, 150.5, data_count=1000)
    log_etf_api_request('eastmoney', False, 2000.0, "Connection timeout")
    log_etf_api_request('ths', True, 300.2, data_count=800)
    
    # 打印状态报告
    print_etf_api_status()
    
    # 导出报告
    report_file = api_monitor.export_performance_report()
    print(f"\n性能报告已导出到: {report_file}")
