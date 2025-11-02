import os
import sys
from notion_manager import *
import _system as s
import requests
from datetime import datetime, timedelta
import time
import json
from task_config import STATUS_EMOJIS, PROJECT_PAGE_ID, PROJECT_DATABASE_NAME, TaskType, TYPE_COLORS

# 任务状态枚举
class TaskStatus:
    NOT_STARTED = "未开始"
    IN_PROGRESS = "进行中"
    COMPLETED = "已完成"
    BLOCKED = "阻塞中"

# 任务优先级枚举
class TaskPriority:
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"

# 状态颜色配置
STATUS_COLORS = {
    TaskStatus.NOT_STARTED: "default",  # 灰色
    TaskStatus.IN_PROGRESS: "blue",     # 蓝色
    TaskStatus.COMPLETED: "green",      # 绿色
    TaskStatus.BLOCKED: "red"           # 红色
}

# 优先级颜色配置
PRIORITY_COLORS = {
    TaskPriority.HIGH: "red",          # 红色
    TaskPriority.MEDIUM: "orange",     # 橙色
    TaskPriority.LOW: "blue"           # 蓝色
}

def load_initial_tasks():
    """从JSON文件加载初始任务配置"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(current_dir, 'task_upload.json')
    
    with open(json_path, 'r', encoding='utf8') as f:
        return json.load(f)

# 加载初始任务配置
INITIAL_TASKS = load_initial_tasks()

def create_task_database():
    """在网格策略优化器页面下创建任务数据库
    @one_time_update 2024-01-03
    @description 创建任务数据库，但不设置属性配置，避免覆盖UI设置
    @status completed
    """
    try:
        # 创建数据库
        page = {
            "parent": {
                "type": "page_id",
                "page_id": PROJECT_PAGE_ID
            },
            "title": newTitle(PROJECT_DATABASE_NAME)["title"],
            "properties": {
                "标题": {
                    "title": {}
                }
            }
        }
        
        # 创建数据库
        createUrl = 'https://api.notion.com/v1/databases'
        response = requests.post(createUrl, headers=headers, json=page)
        
        if response.status_code == 200:
            s.printSucess(f"成功创建数据库: {PROJECT_DATABASE_NAME}")
            return response.json()
        else:
            s.printError(f"创建数据库失败: {response.text}")
            return None
            
    except Exception as e:
        s.printError(f"创建数据库失败: {str(e)}")
        return None

def create_task_page(database_id, title, description, status=TaskStatus.NOT_STARTED, priority=TaskPriority.MEDIUM, task_type=TaskType.REQUIREMENT, start_date=None, end_date=None, parent_task_id=None):
    """创建任务页面"""
    try:
        # 创建新页面
        page = {
            "parent": {
                "database_id": database_id
            },
            "icon": {
                "type": "emoji",
                "emoji": STATUS_EMOJIS.get(status, "📌")  # 只使用状态图标
            },
            "properties": {
                "标题": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                },
                "状态": {
                    "select": {
                        "name": status,
                        "color": STATUS_COLORS.get(status, "default")
                    }
                },
                "优先级": {
                    "select": {
                        "name": priority,
                        "color": PRIORITY_COLORS.get(priority, "default")
                    }
                },
                "任务类型": {
                    "select": {
                        "name": task_type,
                        "color": TYPE_COLORS.get(task_type, "default")
                    }
                },
                "日程": {
                    "type": "date",
                    "date": {
                        "start": start_date,
                        "end": end_date
                    } if start_date else None
                },
                "Deadline": {
                    "type": "date",
                    "date": {
                        "start": end_date
                    } if end_date else None
                },
                "描述": {
                    "rich_text": [
                        {
                            "text": {
                                "content": description
                            }
                        }
                    ]
                }
            }
        }

        # 如果有父任务，添加关联
        if parent_task_id:
            page["properties"]["Parent item"] = {
                "type": "relation",
                "relation": [
                    {
                        "id": parent_task_id
                    }
                ]
            }

        # 添加页面到数据库
        createUrl = 'https://api.notion.com/v1/pages'
        response = requests.post(createUrl, headers=headers, json=page)
        
        if response.status_code == 200:
            created_page = response.json()
            
            # 如果有父任务，更新父任务的子任务关联
            if parent_task_id:
                update_parent_task_relations(parent_task_id, created_page['id'])
                
            s.printSucess(f"成功创建任务: {title}")
            return created_page
        else:
            s.printError(f"创建任务失败: {response.text}")
            return None
        
    except Exception as e:
        s.printError(f"创建任务失败: {str(e)}")
        return None

def create_subtask(parent_task_id, title, description, status=TaskStatus.NOT_STARTED, priority=TaskPriority.MEDIUM, start_date=None, end_date=None):
    """创建子任务"""
    try:
        # 获取父任务所在的数据库ID
        parent_task = requests.get(f"https://api.notion.com/v1/pages/{parent_task_id}", headers=headers).json()
        database_id = parent_task["parent"]["database_id"]
        
        # 查找是否存在同名子任务
        filter_params = {
            "filter": {
                "and": [
                    {
                        "property": "标题",
                        "title": {
                            "equals": title
                        }
                    },
                    {
                        "property": "Parent item",
                        "relation": {
                            "contains": parent_task_id
                        }
                    }
                ]
            }
        }
        readUrl = f"https://api.notion.com/v1/databases/{database_id}/query"
        response = requests.post(readUrl, headers=headers, json=filter_params)
        results = response.json().get('results', [])
        
        if results:
            # 更新现有子任务
            page_id = results[0]['id']
            page = {
                "icon": {
                    "type": "emoji",
                    "emoji": STATUS_EMOJIS.get(status, "📌")  # 使用状态对应的图标
                },
                "properties": {
                    "状态": {
                        "select": {
                            "name": status,
                            "color": STATUS_COLORS.get(status, "default")
                        }
                    },
                    "优先级": {
                        "select": {
                            "name": priority,
                            "color": PRIORITY_COLORS.get(priority, "default")
                        }
                    },
                    "日程": {
                        "type": "date",
                        "date": {
                            "start": start_date,
                            "end": end_date
                        }
                    },
                    "Deadline": {
                        "type": "date",
                        "date": {
                            "start": end_date
                        }
                    },
                    "描述": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": description
                                }
                            }
                        ]
                    }
                }
            }
            updateUrl = f"https://api.notion.com/v1/pages/{page_id}"
            response = requests.patch(updateUrl, headers=headers, json=page)
            
            if response.status_code == 200:
                s.printSucess(f"成功更新子任务: {title}")
                subtask = response.json()
            else:
                s.printError(f"更新子任务失败: {response.text}")
                return None
        else:
            # 创建新子任务
            subtask = create_task_page(
                database_id=database_id,
                title=title,
                description=description,
                status=status,
                priority=priority,
                start_date=start_date,
                end_date=end_date,
                parent_task_id=parent_task_id
            )
        
        if subtask:
            s.printSucess(f"成功创建子任务: {title}")
            # 更新父任务的日程
            update_parent_task_schedule(parent_task_id)
        return subtask
        
    except Exception as e:
        s.printError(f"创建子任务失败: {str(e)}")
        return None

def update_parent_task_relations(parent_task_id, child_task_id):
    """更新父任务的子任务关联"""
    try:
        # 获取父任务当前的子任务列表
        parent_task = requests.get(f"https://api.notion.com/v1/pages/{parent_task_id}", headers=headers).json()
        current_sub_items = parent_task.get("properties", {}).get("Sub-item", {}).get("relation", [])
        
        # 添加新的子任务ID
        current_sub_items.append({"id": child_task_id})
        
        # 更新父任务
        update_data = {
            "properties": {
                "Sub-item": {
                "type": "relation",
                    "relation": current_sub_items
                }
            }
        }
        
        response = requests.patch(
            f"https://api.notion.com/v1/pages/{parent_task_id}",
            headers=headers,
            json=update_data
        )
        
        if response.status_code == 200:
            s.printSucess(f"成功更新父任务关联")
        else:
            s.printError(f"更新父任务关联失败: {response.text}")
            
    except Exception as e:
        s.printError(f"更新父任务关联失败: {str(e)}")

def update_task_status(page_id, new_status):
    """更新任务状态"""
    try:
        # 更新页面
        updateUrl = f"https://api.notion.com/v1/pages/{page_id}"
        page = {
            "properties": {
                "状态": {
                    "select": {
                        "name": new_status,
                        "color": STATUS_COLORS.get(new_status, "default")
                    }
                }
            }
        }
        
        response = requests.patch(updateUrl, headers=headers, json=page)
        
        if response.status_code == 200:
            s.printSucess(f"成功更新任务状态为: {new_status}")
            return response.json()
        else:
            s.printError(f"更新任务状态失败: {response.text}")
            return None
            
    except Exception as e:
        s.printError(f"更新任务状态失败: {str(e)}")
        return None

def update_or_create_task_page(database_id, title, description, status=TaskStatus.NOT_STARTED, priority=TaskPriority.MEDIUM, start_date=None, end_date=None):
    """更新或创建任务页面"""
    try:
        # 查找是否存在同名任务
        filter_params = {
            "filter": {
                "property": "标题",
                "title": {
                    "equals": title
                }
            }
        }
        readUrl = f"https://api.notion.com/v1/databases/{database_id}/query"
        response = requests.post(readUrl, headers=headers, json=filter_params)
        results = response.json().get('results', [])
        
        if results:
            # 更新现有任务
            page_id = results[0]['id']
            page = {
                "icon": {
                    "type": "emoji",
                    "emoji": TASK_EMOJIS.get(title, "📌")  # 如果没有匹配的emoji，使用默认的📌
                },
                "properties": {
                    "状态": {
                        "select": {
                            "name": status,
                            "color": STATUS_COLORS.get(status, "default")
                        }
                    },
                    "优先级": {
                        "select": {
                            "name": priority,
                            "color": PRIORITY_COLORS.get(priority, "default")
                        }
                    },
                    "日程": {
                        "type": "date",
                        "date": {
                            "start": start_date,
                            "end": end_date
                        }
                    },
                    "Deadline": {
                        "type": "date",
                        "date": {
                            "start": end_date
                        }
                    },
                    "描述": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": description
                                }
                            }
                        ]
                    }
                }
            }
            updateUrl = f"https://api.notion.com/v1/pages/{page_id}"
            response = requests.patch(updateUrl, headers=headers, json=page)
            
            if response.status_code == 200:
                s.printSucess(f"成功更新任务: {title}")
                return response.json()
            else:
                s.printError(f"更新任务失败: {response.text}")
                return None
        else:
            # 创建新任务
            return create_task_page(database_id, title, description, status, priority, start_date, end_date)
            
    except Exception as e:
        s.printError(f"更新或创建任务失败: {str(e)}")
        return None

def create_initial_tasks():
    """创建初始任务列表"""
    # 获取现有数据库ID
    database_id = searchDatabaseId(PROJECT_DATABASE_NAME)
    if not database_id:
        s.printError(f"未找到数据库: {PROJECT_DATABASE_NAME}")
        return
    
    # 从今天开始的时间计划
    current_date = datetime.now()
    
    # 创建或更新任务
    for task in INITIAL_TASKS:
        # 设置父任务的时间范围
        parent_start = current_date.strftime("%Y-%m-%d")
        parent_end = (current_date + timedelta(days=task["duration"])).strftime("%Y-%m-%d")
        
        # 创建主任务
        parent_task = update_or_create_task_page(
            database_id=database_id,
            title=task["title"],
            description=task["description"],
            priority=task["priority"],
            start_date=parent_start,
            end_date=parent_end
        )
        
        if parent_task and "subtasks" in task:
            # 子任务的开始时间从父任务的开始时间开始
            subtask_date = datetime.strptime(parent_start, "%Y-%m-%d")
            
            # 创建子任务
            for subtask in task["subtasks"]:
                subtask_start = subtask_date.strftime("%Y-%m-%d")
                subtask_end = (subtask_date + timedelta(days=subtask["duration"])).strftime("%Y-%m-%d")
                
                # 创建子任务
                created_subtask = create_subtask(
                    parent_task_id=parent_task["id"],
                    title=subtask["title"],
                    description=subtask["description"],
                    status=subtask.get("status", TaskStatus.NOT_STARTED),
                    priority=subtask["priority"],
                    start_date=subtask_start,
                    end_date=subtask_end
                )
                
                if created_subtask:
                    # 如果子任务已完成，更新状态
                    if subtask.get("status") == TaskStatus.COMPLETED:
                        update_task_status(created_subtask["id"], TaskStatus.COMPLETED)
                    elif subtask.get("status") == TaskStatus.IN_PROGRESS:
                        update_task_status(created_subtask["id"], TaskStatus.IN_PROGRESS)
                
                # 更新下一个子任务的开始时间
                subtask_date = subtask_date + timedelta(days=subtask["duration"])
                
                # 确保子任务的结束时间不超过父任务的结束时间
                parent_end_date = datetime.strptime(parent_end, "%Y-%m-%d")
                if subtask_date > parent_end_date:
                    subtask_date = parent_end_date
        
        # 更新下一个主任务的开始时间
        current_date = current_date + timedelta(days=task["duration"])



def clean_duplicate_tasks():
    """清理重复的任务，包括主任务和子任务"""
    try:
        # 获取数据库ID
        database_id = searchDatabaseId(PROJECT_DATABASE_NAME)
        if not database_id:
            s.printError(f"未找到数据库: {PROJECT_DATABASE_NAME}")
            return

        # 获取所有任务
        readUrl = f"https://api.notion.com/v1/databases/{database_id}/query"
        response = requests.post(readUrl, headers=headers)
        results = response.json().get('results', [])

        # 按标题分组，只保留最新的一个
        tasks_by_title = {}
        for task in results:
            title = task['properties']['标题']['title'][0]['text']['content']
            # 检查是否为子任务（有Parent item关系）
            is_subtask = bool(task['properties'].get('Parent item', {}).get('relation', []))
            
            # 使用标题和是否为子任务作为键，确保主任务和子任务分开处理
            key = f"{title}_{is_subtask}"
            if key not in tasks_by_title:
                tasks_by_title[key] = []
            tasks_by_title[key].append(task)

        # 删除重复的任务
        for key, tasks in tasks_by_title.items():
            if len(tasks) > 1:
                # 按创建时间排序，保留最新的
                sorted_tasks = sorted(tasks, key=lambda x: x['created_time'], reverse=True)
                title = sorted_tasks[0]['properties']['标题']['title'][0]['text']['content']
                
                # 删除旧的任务
                for task in sorted_tasks[1:]:
                    # 将页面标记为已归档（删除）
                    page = {
                        "archived": True
                    }
                    updateUrl = f"https://api.notion.com/v1/pages/{task['id']}"
                    response = requests.patch(updateUrl, headers=headers, json=page)
                    
                    if response.status_code == 200:
                        s.printSucess(f"成功删除重复任务: {title}")
                    else:
                        s.printError(f"删除任务失败: {response.text}")

    except Exception as e:
        s.printError(f"清理重复任务失败: {str(e)}")
        return None






def update_parent_task_schedule(parent_task_id):
    """更新父任务的日程，结束时间设置为最晚的子任务结束时间"""
    try:
        # 获取父任务信息
        parent_task = requests.get(f"https://api.notion.com/v1/pages/{parent_task_id}", headers=headers).json()
        database_id = parent_task["parent"]["database_id"]
        
        # 获取所有子任务
        filter_params = {
            "filter": {
                "property": "Parent item",
                "relation": {
                    "contains": parent_task_id
                }
            }
        }
        readUrl = f"https://api.notion.com/v1/databases/{database_id}/query"
        response = requests.post(readUrl, headers=headers, json=filter_params)
        subtasks = response.json().get('results', [])
        
        if subtasks:
            # 获取父任务的开始时间
            parent_schedule = parent_task.get("properties", {}).get("日程", {}).get("date", {})
            parent_start = parent_schedule.get("start") if parent_schedule else None
            
            # 找出最晚的子任务结束时间
            latest_end = None
            for subtask in subtasks:
                subtask_schedule = subtask.get("properties", {}).get("日程", {}).get("date", {})
                if subtask_schedule:
                    subtask_end = subtask_schedule.get("end")
                    if subtask_end:
                        if not latest_end or subtask_end > latest_end:
                            latest_end = subtask_end
            
            if parent_start and latest_end:
                # 更新父任务的日程
                update_data = {
                    "properties": {
                        "日程": {
                            "type": "date",
                            "date": {
                                "start": parent_start,
                                "end": latest_end
                            }
                        }
                    }
                }
                
                response = requests.patch(
                    f"https://api.notion.com/v1/pages/{parent_task_id}",
                    headers=headers,
                    json=update_data
                )
                
                if response.status_code == 200:
                    s.printSucess(f"成功更新父任务日程")
                else:
                    s.printError(f"更新父任务日程失败: {response.text}")
            
    except Exception as e:
        s.printError(f"更新父任务日程失败: {str(e)}")
        return None

if __name__ == "__main__":
    # 先清理重复任务
    clean_duplicate_tasks()
    # 等待一下，确保数据库配置更新完成
    time.sleep(2)
    # 创建初始任务列表
    create_initial_tasks()