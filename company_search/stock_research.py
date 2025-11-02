import csv
import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List

from openai import OpenAI

# 配置常量
CSV_PATH = "company_search/company_list.csv"
JSON_PATH = "company_search/company_astock_list.json"
RETRY_LIMIT = 3
REQUEST_INTERVAL = 3  # 请求间隔秒数
DEBUG_MODE = True  # 调试模式开关
DEBUG_START = 1  # 调试模式起始索引
DEBUG_END = 4    # 调试模式结束索引（不包含）

# 初始化Kimi客户端
client = OpenAI(
    api_key="sk-baXmq2pe9AgZF5JFEyyPFUVtc4d7aXS9RJAh2p8e7sZeS6Bo",
    base_url="https://api.moonshot.cn/v1",
)

def build_query(company: Dict) -> str:
    """构建查询提示词，只发送必要的变量部分"""
    return f"{company['企业名']}（成立时间：{company['成立']}，地区：{company['地区']}）"

def parse_table(text: str) -> str:
    """解析表格数据并返回标准化结果字符串
    新解析规则:
    1. 严格匹配格式：**公司名称(股票代码)-持股比例**
    2. 保留所有符合格式的记录
    3. 多个结果用分号分隔
    """
    # 更新正则表达式匹配星号包裹的内容
    pattern = r'\*\*([^\*]+?)\((\d+)\)\s*-\s*([\d.]+)%\*\*'  # 匹配**包裹的内容
    matches = re.findall(pattern, text)
    
    # 构建结果列表时保留原始格式
    results = [f"{name}({code})-{percent}%" for name, code, percent in matches]
    
    return ";".join(results) if results else "无"

def search_impl(arguments: Dict[str, Any]) -> Any:
    """处理搜索请求"""
    return arguments

def query_kimi(prompt: str) -> str:
    """带重试机制的API查询，优化系统角色描述"""
    system_message = {
        "role": "system",
        "content": (
            "你是企业信息调研专家，擅长从公开市场查询目标企业的各种信息，包括投资和股权结构等专业咨询，并能确认其可靠性。"
            "\n\n"
            "请严格按照以下格式输出每个结果："
            "\n"
            "A股上市公司名称(股票代码)-持股比例（截至IPO前）, 举个例子: 腾讯控股(00700)-100%"
            "\n"
            "要求："
            "\n"
            "1. 只输出确认可靠的信息。"
            "\n"
            "2. 不需要有开头文字类似'以下是...', 直接给出结果，文字不含特殊格式(如加粗), 不需要输出其他公司介绍等信息, 多个关联公司用|分隔, 例如: 腾讯控股(00700)-100%|阿里巴巴(09988)-100%"            
        )
    }
    user_message = {
        "role": "user",
        "content": f"请帮我找到以下企业的所有A股关联上市企业，并给出持股百分比：\n{prompt}"
    }
    
    messages = [system_message, user_message]
    
    for _ in range(RETRY_LIMIT):
        try:
            finish_reason = None
            while finish_reason is None or finish_reason == "tool_calls":
                completion = client.chat.completions.create(
                    model="moonshot-v1-auto",
                    messages=messages,
                    temperature=0,
                    tools=[
                        {
                            "type": "builtin_function",
                            "function": {
                                "name": "$web_search",
                            }
                        }
                    ]                
                )
                
                choice = completion.choices[0]
                finish_reason = choice.finish_reason
                
                if finish_reason == "tool_calls":
                    messages.append(choice.message)
                    for tool_call in choice.message.tool_calls:
                        if tool_call.function.name == "$web_search":
                            # 处理搜索请求
                            tool_call_arguments = json.loads(tool_call.function.arguments)
                            tool_result = search_impl(tool_call_arguments)
                            
                            # 添加工具调用结果
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_call.function.name,
                                "content": json.dumps(tool_result)
                            })
            
            return choice.message.content or ""
            
        except Exception as e:
            print(f"查询失败: {str(e)}, 10秒后重试...")
            time.sleep(10)
    return ""

def main():
    # 读取现有数据
    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            existing = {item['企业名']: item for item in json.load(f)}
    except FileNotFoundError:
        existing = {}

    # 处理CSV数据
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        records = list(reader)
        
        # 调试模式只处理指定范围的记录
        if DEBUG_MODE:
            records = records[DEBUG_START:DEBUG_END]
            print(f"【调试模式】处理记录范围: {DEBUG_START} - {DEBUG_END-1}")
            print(f"将处理以下企业: {[r['企业名'] for r in records]}")

        total = len(records)
        for idx, row in enumerate(records, 1):
            if row['企业名'] in existing:
                print(f"跳过已存在记录: {row['企业名']}")
                continue
            
            print(f"正在处理 [{idx}/{total}]: {row['企业名']}")
            prompt = build_query(row)
            response = query_kimi(prompt)
            time.sleep(REQUEST_INTERVAL)  # 控制请求频率
            
            # 构建结果对象
            result = {
                "企业名": row['企业名'],
                "成立": row['成立'],
                "地区": row['地区'],
                "赛道": row['赛道'],
                # "关联A股": parse_table(response),
                "关联A股": response  # 原始响应作为介绍
            }
            
            existing[row['企业名']] = result
            
            # 实时保存
            with open(JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(list(existing.values()), f, ensure_ascii=False, indent=2)
            
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{current_time}] 完成处理: {row['企业名']} -> 关联A股: {result['关联A股']}\n")
            time.sleep(30)

if __name__ == "__main__":
    main()
    
    # 临时测试
    # test_prompt = "测试腾讯公司的关联上市公司"
    # print("测试查询:", test_prompt)
    # response = query_kimi(test_prompt)
    # print("API响应:", response) 