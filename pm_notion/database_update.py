import os
import sys
from notion_manager import *
import _system as s
import requests
import time
from datetime import datetime, timedelta
from task_config import (
    TaskStatus, TaskPriority, STATUS_COLORS, PRIORITY_COLORS, 
    PROJECT_DATABASE_NAME, PROJECT_PAGE_ID, TaskType, TYPE_COLORS,
    STATUS_EMOJIS
)

def update_database_properties():
    """更新数据库属性配置
    @one_time_update 2024-01-04
    @description 添加任务类型字段并保留现有字段，修复完成度显示格式
    """
    try:
        # 获取数据库ID
        database_id = searchDatabaseId(PROJECT_DATABASE_NAME)
        if not database_id:
            s.printError(f"未找到数据库: {PROJECT_DATABASE_NAME}")
            return
            
        # 获取当前数据库配置
        readUrl = f"https://api.notion.com/v1/databases/{database_id}"
        response = requests.get(readUrl, headers=headers)
        if response.status_code != 200:
            s.printError(f"获取数据库配置失败: {response.text}")
            return
        
        current_properties = response.json().get("properties", {})
        
        # 添加或更新任务类型字段
        current_properties["任务类型"] = {
            "type": "select",
            "select": {
                "options": [
                    {
                        "name": TaskType.REQUIREMENT,
                        "color": TYPE_COLORS[TaskType.REQUIREMENT]
                    },
                    {
                        "name": TaskType.OPTIMIZATION,
                        "color": TYPE_COLORS[TaskType.OPTIMIZATION]
                    },
                    {
                        "name": TaskType.BUG,
                        "color": TYPE_COLORS[TaskType.BUG]
                    }
                ]
            }
        }
        
        # 更新完成度字段格式
        current_properties["完成度"] = {
            "type": "number",
            "number": {
                "format": "percent"
            }
        }
        
        # 更新数据库属性
        updateUrl = f"https://api.notion.com/v1/databases/{database_id}"
        response = requests.patch(
            updateUrl,
            headers=headers,
            json={
                "properties": current_properties
            }
        )
        
        if response.status_code == 200:
            s.printSucess("成功更新数据库属性")
        else:
            s.printError(f"更新数据库属性失败: {response.text}")
            
    except Exception as e:
        s.printError(f"更新数据库属性失败: {str(e)}")

def set_initial_task_types():
    """设置初始任务的类型
    @one_time_update 2024-01-04
    @description 为现有任务设置任务类型
    """
    try:
        # 获取数据库ID
        databases = list_databases()
        database_id = None
        for db in databases:
            if db['title'][0]['text']['content'] == PROJECT_DATABASE_NAME:
                database_id = db['id']
                break
        
        if not database_id:
            s.printError(f"未找到数据库: {PROJECT_DATABASE_NAME}")
            return
            
        # 获取所有任务
        readUrl = f"https://api.notion.com/v1/databases/{database_id}/query"
        response = requests.post(readUrl, headers=headers)
        tasks = response.json().get('results', [])
        
        # 设置任务类型
        for task in tasks:
            title = task['properties']['标题']['title'][0]['text']['content']
            task_type = TaskType.REQUIREMENT  # 默认设置为需求类型
            
            # 更新任务类型
            updateUrl = f"https://api.notion.com/v1/pages/{task['id']}"
            response = requests.patch(
                updateUrl,
                headers=headers,
                json={
                    "properties": {
                        "任务类型": {
                            "select": {
                                "name": task_type,
                                "color": TYPE_COLORS[task_type]
                            }
                        }
                    }
                }
            )
            
            if response.status_code == 200:
                s.printSucess(f"成功设置任务类型: {title}")
            else:
                s.printError(f"设置任务类型失败: {title}")
                
    except Exception as e:
        s.printError(f"设置任务类型失败: {str(e)}")

def configure_database_view_subitems(database_id):
    """配置数据库视图的sub-items显示
    @one_time_update 2024-01-03
    @description 配置数据库的sub-items显示方式为nested_in_toggle
    @status completed
    """
    try:
        # 获取数据库的所有视图
        readUrl = f"https://api.notion.com/v1/databases/{database_id}"
        response = requests.get(readUrl, headers=headers)
        database = response.json()
        
        # 更新视图配置
        data = {
            "properties": {
                "Parent item": {
                    "type": "relation",
                    "relation": {
                        "database_id": database_id,
                        "type": "dual_property",
                        "dual_property": {
                            "synced_property_name": "Sub-item",
                            "synced_property_id": "sub_item_field"
                        }
                    }
                },
                "Sub-item": {
                    "type": "relation",
                    "relation": {
                        "database_id": database_id,
                        "type": "dual_property",
                        "dual_property": {
                            "synced_property_name": "Parent item",
                            "synced_property_id": "parent_item_field"
                        }
                    }
                }
            }
        }
        
        # 更新数据库配置
        updateUrl = f"https://api.notion.com/v1/databases/{database_id}"
        response = requests.patch(updateUrl, headers=headers, json=data)
        
        if response.status_code == 200:
            s.printSucess("成功配置数据库视图sub-items显示")
            return response.json()
        else:
            s.printError(f"配置数据库视图sub-items显示失败: {response.text}")
            return None
            
    except Exception as e:
        s.printError(f"配置数据库视图sub-items显示失败: {str(e)}")
        return None

def one_time_database_updates():
    """执行一次性的数据库更新操作
    @one_time_update 2024-01-03
    @description 执行所有一次性的数据库字段和配置更新
    @status completed
    """
    # 更新数据库属性配置
    update_database_properties()
    # 等待一下，确保数据库配置更新完成
    time.sleep(2)
    # 配置数据库视图
    database_id = searchDatabaseId("开发任务")
    if database_id:
        configure_database_view_subitems(database_id)

def test_subtask_creation():
    """测试子任务创建功能"""
    try:
        # 获取数据库ID
        database_id = searchDatabaseId(PROJECT_DATABASE_NAME)
        if not database_id:
            s.printError(f"未找到数据库: {PROJECT_DATABASE_NAME}")
            return

        # 创建一个父任务
        parent_task = create_task_page(
            database_id=database_id,
            title="网格参数优化",
            description="实现网格策略参数的优化算法，包括买入卖出点和交易数量的计算",
            priority=TaskPriority.HIGH,
            start_date=datetime.now().strftime("%Y-%m-%d"),
            end_date=(datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        )

        if not parent_task:
            s.printError("创建父任务失败")
            return

        # 创建一个子任务
        subtask = create_subtask(
            parent_task_id=parent_task['id'],
            title="参数优化算法实现",
            description="实现基于Optuna的网格策略参数优化算法",
            priority=TaskPriority.HIGH,
            start_date=datetime.now().strftime("%Y-%m-%d"),
            end_date=(datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        )

        if subtask:
            s.printSucess("子任务创建成功")
        else:
            s.printError("子任务创建失败")

    except Exception as e:
        s.printError(f"测试子任务创建失败: {str(e)}")

def update_database_select_options():
    """更新数据库的选项配置"""
    try:
        # 获取数据库ID
        database_id = searchDatabaseId(PROJECT_DATABASE_NAME)
        if not database_id:
            s.printError(f"未找到数据库: {PROJECT_DATABASE_NAME}")
            return

        # 先清空选项
        data = {
        "properties": {
                "状态": {
                    "select": {
                        "options": []
                    }
                },
                "优先级": {
                    "select": {
                        "options": []
                    }
                }
            }
        }
        
        # 更新数据库
        updateUrl = f"https://api.notion.com/v1/databases/{database_id}"
        response = requests.patch(updateUrl, headers=headers, json=data)
        
        if response.status_code == 200:
            s.printSucess("成功清空数据库选项")
            
            # 添加新选项
            data = {
                "properties": {
                    "状态": {
                        "select": {
                            "options": [
                                {"name": status, "color": color}
                                for status, color in STATUS_COLORS.items()
                            ]
                        }
                    },
                    "优先级": {
                        "select": {
                            "options": [
                                {"name": priority, "color": color}
                                for priority, color in PRIORITY_COLORS.items()
                            ]
                        }
                    }
                }
            }
            
            # 更新数据库
            response = requests.patch(updateUrl, headers=headers, json=data)
            
            if response.status_code == 200:
                s.printSucess("成功更新数据库选项配置")
                return response.json()
            else:
                s.printError(f"更新数据库选项配置失败: {response.text}")
                return None
        else:
            s.printError(f"清空数据库选项失败: {response.text}")
            return None
            
    except Exception as e:
        s.printError(f"更新数据库选项配置失败: {str(e)}")
        return None
            
def configure_database_view_subitems(database_id):
    """配置数据库视图的sub-items显示
    @one_time_update 2024-01-03
    @description 配置数据库的sub-items显示方式为nested_in_toggle
    @status completed
    """
    try:
        # 获取数据库的所有视图
        readUrl = f"https://api.notion.com/v1/databases/{database_id}"
        response = requests.get(readUrl, headers=headers)
        database = response.json()
        
        # 更新视图配置
        data = {
            "properties": {
                "Sub-items": {
                    "type": "sub_items",
                    "sub_items": {
                        "enabled": True,
                        "show_as": "nested_in_toggle",  # 可选值: nested_in_toggle, parents_only, flattened_list
                        "property": "Parent item"  # 使用Parent item字段作为sub-items的依据
                    }
                }
            }
        }
        
        # 更新数据库配置
        updateUrl = f"https://api.notion.com/v1/databases/{database_id}"
        response = requests.patch(updateUrl, headers=headers, json=data)
        
        if response.status_code == 200:
            s.printSucess("成功配置数据库视图sub-items显示")
            return response.json()
        else:
            s.printError(f"配置数据库视图sub-items显示失败: {response.text}")
            return None
            
    except Exception as e:
        s.printError(f"配置数据库视图sub-items显示失败: {str(e)}")
        return None
                
def update_task_completion_and_tests():
    """更新任务的完成度和测试用例状态
    @description 根据子任务状态更新父任务完成度，并根据测试文件检查测试用例状态
    """
    try:
        # 获取数据库ID
        database_id = searchDatabaseId(PROJECT_DATABASE_NAME)
        if not database_id:
            s.printError(f"未找到数据库: {PROJECT_DATABASE_NAME}")
            return

        # 获取所有任务
        readUrl = f"https://api.notion.com/v1/databases/{database_id}/query"
        response = requests.post(readUrl, headers=headers)
        tasks = response.json().get('results', [])

        # 检查测试用例文件
        test_files = []
        test_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests')
        if os.path.exists(test_dir):
            for root, dirs, files in os.walk(test_dir):
                test_files.extend([os.path.join(root, f) for f in files if f.startswith('test_')])

        # 更新每个任务
        for task in tasks:
            task_id = task['id']
            title = task['properties']['标题']['title'][0]['text']['content']
            
            # 检查是否有对应的测试用例
            has_test = any(title.lower().replace(" ", "_") in test_file.lower() for test_file in test_files)
            
            # 获取子任务
            filter_params = {
                "filter": {
                    "property": "Parent item",
                    "relation": {
                        "contains": task_id
                    }
                }
            }
            subtasks_response = requests.post(readUrl, headers=headers, json=filter_params)
            subtasks = subtasks_response.json().get('results', [])
            
            # 计算完成度和确定状态
            if subtasks:
                completion_rate = 0
                has_in_progress = False
                has_blocked = False
                all_completed = True
                all_not_started = True
                
                for subtask in subtasks:
                    status = subtask['properties']['状态']['select']['name']
                    # 计算完成度
                    if status == TaskStatus.COMPLETED:
                        completion_rate += 1
                        all_not_started = False
                    elif status == TaskStatus.IN_PROGRESS:
                        completion_rate += 0.5
                        has_in_progress = True
                        all_completed = False
                        all_not_started = False
                    elif status == TaskStatus.BLOCKED:
                        has_blocked = True
                        all_completed = False
                        all_not_started = False
                    else:  # NOT_STARTED
                        all_completed = False
                
                completion_rate = (completion_rate / len(subtasks))  # 转换为小数，Notion会自动处理为百分比
                
                # 确定父任务状态
                if has_blocked:
                    parent_status = TaskStatus.BLOCKED
                elif all_completed:
                    parent_status = TaskStatus.COMPLETED
                elif has_in_progress or not all_not_started:
                    parent_status = TaskStatus.IN_PROGRESS
                else:
                    parent_status = TaskStatus.NOT_STARTED
            else:
                # 如果没有子任务，保持当前状态
                status = task['properties']['状态']['select']['name']
                parent_status = status
                if status == TaskStatus.COMPLETED:
                    completion_rate = 1  # 100%
                elif status == TaskStatus.IN_PROGRESS:
                    completion_rate = 0.5  # 50%
                else:
                    completion_rate = 0  # 0%
            
            # 更新任务
            update_data = {
                "icon": {
                    "type": "emoji",
                    "emoji": STATUS_EMOJIS.get(parent_status, "📌")  # 根据状态更新图标
                },
                "properties": {
                    "测试用例": {
                        "checkbox": has_test
                    },
                    "完成度": {
                        "number": completion_rate
                    },
                    "状态": {
                        "select": {
                            "name": parent_status,
                            "color": STATUS_COLORS.get(parent_status, "default")
                        }
                    }
                }
            }
            
            updateUrl = f"https://api.notion.com/v1/pages/{task_id}"
            response = requests.patch(updateUrl, headers=headers, json=update_data)
            
            if response.status_code == 200:
                s.printSucess(f"成功更新任务 {title} 的状态({parent_status})、完成度({completion_rate*100}%)和测试用例状态({has_test})")
            else:
                s.printError(f"更新任务失败: {response.text}")
                
    except Exception as e:
        s.printError(f"更新任务完成度和测试用例状态失败: {str(e)}")
        return None

if __name__ == "__main__":
    # 更新数据库属性配置
    update_database_properties()
    # 更新任务状态
    update_task_completion_and_tests() 