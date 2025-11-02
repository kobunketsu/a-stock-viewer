import os
import sys
from notion_manager import *
import _system as s
import requests
from datetime import datetime
from task_config import PROJECT_DATABASE_NAME

def get_page_content(page_id):
    """获取页面内容"""
    try:
        content = []
        has_more = True
        start_cursor = None
        
        while has_more:
            # 获取页面块
            readUrl = f"https://api.notion.com/v1/blocks/{page_id}/children"
            params = {"page_size": 100}
            if start_cursor:
                params["start_cursor"] = start_cursor
                
            response = requests.get(readUrl, headers=headers, params=params)
            
            if response.status_code != 200:
                s.printError(f"获取页面内容失败: {response.text}")
                return None
                
            result = response.json()
            blocks = result.get('results', [])
            has_more = result.get('has_more', False)
            if has_more:
                start_cursor = result.get('next_cursor')
            
            for block in blocks:
                block_type = block['type']
                if block_type == 'paragraph':
                    text = block.get('paragraph', {}).get('rich_text', [])
                    if text:
                        content.append(text[0]['plain_text'])
                elif block_type == 'heading_1':
                    text = block.get('heading_1', {}).get('rich_text', [])
                    if text:
                        content.append(f"\n# {text[0]['plain_text']}")
                elif block_type == 'heading_2':
                    text = block.get('heading_2', {}).get('rich_text', [])
                    if text:
                        content.append(f"\n## {text[0]['plain_text']}")
                elif block_type == 'heading_3':
                    text = block.get('heading_3', {}).get('rich_text', [])
                    if text:
                        content.append(f"\n### {text[0]['plain_text']}")
                elif block_type == 'bulleted_list_item':
                    text = block.get('bulleted_list_item', {}).get('rich_text', [])
                    if text:
                        content.append(f"- {text[0]['plain_text']}")
                elif block_type == 'numbered_list_item':
                    text = block.get('numbered_list_item', {}).get('rich_text', [])
                    if text:
                        content.append(f"1. {text[0]['plain_text']}")
                elif block_type == 'toggle':
                    text = block.get('toggle', {}).get('rich_text', [])
                    if text:
                        content.append(f"▸ {text[0]['plain_text']}")
                        # 获取toggle内的内容
                        toggle_content = get_page_content(block['id'])
                        if toggle_content:
                            content.extend([f"  {line}" for line in toggle_content])
                    
        return content
        
    except Exception as e:
        s.printError(f"获取页面内容失败: {str(e)}")
        return None

def get_task_details(task_title):
    """获取特定任务的详细信息"""
    try:
        database_id = searchDatabaseId(PROJECT_DATABASE_NAME)
        if not database_id:
            s.printError(f"未找到数据库: {PROJECT_DATABASE_NAME}")
            return None
            
        # 查询特定任务
        readUrl = f"https://api.notion.com/v1/databases/{database_id}/query"
        filter_params = {
            "filter": {
                "property": "标题",
                "title": {
                    "equals": task_title
                }
            }
        }
        
        response = requests.post(readUrl, headers=headers, json=filter_params)
        if response.status_code != 200:
            s.printError(f"查询任务失败: {response.text}")
            return None
            
        tasks = response.json().get('results', [])
        if not tasks:
            s.printError(f"未找到任务: {task_title}")
            return None
            
        task = tasks[0]
        task_id = task['id']
        
        # 获取子任务
        subtasks_filter = {
            "filter": {
                "property": "Parent item",
                "relation": {
                    "contains": task_id
                }
            }
        }
        
        subtasks_response = requests.post(readUrl, headers=headers, json=subtasks_filter)
        if subtasks_response.status_code != 200:
            s.printError(f"查询子任务失败: {subtasks_response.text}")
            return None
            
        subtasks = subtasks_response.json().get('results', [])
        
        # 获取页面内容
        content = get_page_content(task_id)
        
        # 打印任务详情
        print("\n=== 任务详情 ===")
        print(f"标题: {task_title}")
        if task['properties'].get('描述', {}).get('rich_text'):
            print(f"描述: {task['properties']['描述']['rich_text'][0]['text']['content']}")
        print(f"状态: {task['properties']['状态']['select']['name']}")
        if task['properties'].get('完成度', {}).get('number') is not None:
            print(f"完成度: {task['properties']['完成度']['number']*100}%")
            
        if content:
            print("\n=== 页面内容 ===")
            for line in content:
                print(line)
            
        if subtasks:
            print("\n=== 子任务 ===")
            for subtask in subtasks:
                title = subtask['properties']['标题']['title'][0]['text']['content']
                status = subtask['properties']['状态']['select']['name']
                description = ""
                if subtask['properties'].get('描述', {}).get('rich_text'):
                    description = subtask['properties']['描述']['rich_text'][0]['text']['content']
                print(f"\n- {title} ({status})")
                if description:
                    print(f"  描述: {description}")
                # 获取子任务的页面内容
                subtask_content = get_page_content(subtask['id'])
                if subtask_content:
                    print("  详细内容:")
                    for line in subtask_content:
                        print(f"    {line}")
                    
        return task, subtasks, content
        
    except Exception as e:
        s.printError(f"获取任务详情失败: {str(e)}")
        return None

def get_task_by_type(task_type):
    """获取特定类型的所有任务"""
    try:
        database_id = searchDatabaseId(PROJECT_DATABASE_NAME)
        if not database_id:
            s.printError(f"未找到数据库: {PROJECT_DATABASE_NAME}")
            return None
            
        # 查询特定类型的任务
        readUrl = f"https://api.notion.com/v1/databases/{database_id}/query"
        filter_params = {
            "filter": {
                "property": "任务类型",
                "select": {
                    "equals": task_type
                }
            }
        }
        
        response = requests.post(readUrl, headers=headers, json=filter_params)
        if response.status_code != 200:
            s.printError(f"查询任务失败: {response.text}")
            return None
            
        tasks = response.json().get('results', [])
        if not tasks:
            print(f"未找到{task_type}类型的任务")
            return None
            
        print(f"\n=== {task_type}类型任务列表 ===")
        for task in tasks:
            title = task['properties']['标题']['title'][0]['text']['content']
            status = task['properties']['状态']['select']['name']
            completion = task['properties'].get('完成度', {}).get('number', 0) * 100
            print(f"\n- {title}")
            print(f"  状态: {status}")
            print(f"  完成度: {completion}%")
            if task['properties'].get('描述', {}).get('rich_text'):
                description = task['properties']['描述']['rich_text'][0]['text']['content']
                print(f"  描述: {description}")
                
        return tasks
        
    except Exception as e:
        s.printError(f"获取任务列表失败: {str(e)}")
        return None

if __name__ == "__main__":
    # 查询股票代码模糊搜索任务的详情
    get_task_details("股票代码模糊搜索") 