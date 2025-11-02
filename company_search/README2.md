使用Kimi API，对company_list.csv中每条记录进行以下提示词查询：
"
请帮我通过各种信息搜索找到以下企业的所有A股关联上市企业，确认并给出持股百分比
{每条记录名称}（例如：一脉阳光,2014,南昌,数字医疗）

如果有关联企业，请按照以下类型表头输出表格
A股上市公司	持股比例（截至IPO前）持股方式
"
将收到的每条结果追加写入company_astock_list.json, 此文件每条记录结构为
{
    "企业名": string,
    "成立": date,
    "地区": string,
    "赛道": string,
    "关联A股“: [
        {
            "名称": string,
            "代码": string,
            "股份%": float,
        }
    ],
    "公司介绍": string
}

# API使用例子
from openai import OpenAI

client = OpenAI(
    api_key="sk-baXmq2pe9AgZF5JFEyyPFUVtc4d7aXS9RJAh2p8e7sZeS6Bo",
    base_url="https://api.moonshot.cn/v1",
)

history = [
    {"role": "system", "content": "你是企业信息调研专家，善长从公开市场查询搜索目标企业的各种信息，包括投资，股权结构等专业咨询，并能确认其可靠性。"}
]

def chat(query, history):
    history.append({"role": "user", "content": query})
    completion = client.chat.completions.create(
        model="kimi-latest",
        messages=history,
        temperature=0,
        tools=[  # 添加联网搜索工具
            {
                "type": "builtin_function",
                "function": {
                    "name": "$web_search"
                }
            }
        ]
    )
    result = completion.choices[0].message.content
    history.append({"role": "assistant", "content": result})
    return result

