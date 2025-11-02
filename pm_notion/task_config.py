# 项目文档数据库属性
PROJECT_PAGE_ID = "167d3e1525b580118972cd15600dce73"
PROJECT_DATABASE_NAME = "开发任务"

# 任务状态枚举
class TaskStatus:
    NOT_STARTED = "未开始"
    IN_PROGRESS = "进行中"
    COMPLETED = "已完成"
    BLOCKED = "阻塞中"

# 任务类型枚举
class TaskType:
    REQUIREMENT = "需求"
    OPTIMIZATION = "优化"
    BUG = "缺陷"

# 任务优先级枚举
class TaskPriority:
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"

# 任务状态图标配置
STATUS_EMOJIS = {
    TaskStatus.NOT_STARTED: "📌",    # 默认图标
    TaskStatus.IN_PROGRESS: "🔄",    # 进行中
    TaskStatus.COMPLETED: "✅",      # 已完成
    TaskStatus.BLOCKED: "⛔"         # 阻塞中
}

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

# 任务类型颜色配置
TYPE_COLORS = {
    TaskType.REQUIREMENT: "blue",      # 蓝色表示需求
    TaskType.OPTIMIZATION: "green",    # 绿色表示优化
    TaskType.BUG: "red"               # 红色表示缺陷
} 