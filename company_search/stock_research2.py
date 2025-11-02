def build_query(company: Dict) -> str:
    """构建查询提示词，只发送必要的变量部分"""
    return f"{company['企业名']}（成立时间：{company['成立']}，地区：{company['地区']}）"

def query_kimi(prompt: str) -> str:
    """带重试机制的API查询，优化系统角色描述"""
    system_message = {
        "role": "system",
        "content": (
            "你是企业信息调研专家，擅长从公开市场查询目标企业的各种信息，包括投资和股权结构等专业咨询，并能确认其可靠性。"
            "\n\n"
            "请按照以下格式输出结果："
            "\n"
            "A股上市公司 | 持股比例（截至IPO前） | 持股方式"
            "\n"
            "要求："
            "\n"
            "1. 只输出确认可靠的信息。"
            "\n"
            "2. 持股比例请转换为百分比数值。"
            "\n"
            "3. 上市公司名称后标注股票代码，如：腾讯控股(00700)。"
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