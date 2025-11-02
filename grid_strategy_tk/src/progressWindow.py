import tkinter as tk
from tkinter import ttk
import threading

class ProgressWindow:
    def __init__(self, parent):
        self.root = tk.Toplevel(parent)
        self.root.title("任务进度")
        self.root.protocol("WM_DELETE_WINDOW", self.on_cancel)
        
        # 进度标签
        self.label = ttk.Label(self.root, text="")
        self.label.pack(pady=10)
        
        # 进度条
        self.progress = ttk.Progressbar(self.root, orient=tk.HORIZONTAL, length=300, mode='determinate')
        self.progress.pack(pady=5)
        
        # 取消按钮
        self.cancel_btn = ttk.Button(self.root, text="取消", command=self.on_cancel)
        self.cancel_btn.pack(pady=5)
        
        self.is_cancelled = False
        self.task_thread = None

    def show(self, title="任务进度", message="正在处理..."):
        """显示进度窗口"""
        self.root.title(title)
        self.label.config(text=message)
        self.progress["value"] = 0
        self.is_cancelled = False
        self.root.deiconify()

    def update_progress(self, value, message=None):
        """更新进度"""
        if message:
            self.label.config(text=message)
        self.progress["value"] = value
        self.root.update()

    def on_cancel(self):
        """取消任务"""
        self.is_cancelled = True
        self.root.withdraw()

    def run_task(self, task_func, *args):
        """执行带进度的任务"""
        self.show()
        self.task_thread = threading.Thread(target=task_func, args=(self, *args))
        self.task_thread.start()
        self.check_thread()

    def check_thread(self):
        """检查线程状态"""
        if self.task_thread.is_alive():
            self.root.after(100, self.check_thread)
        else:
            self.root.withdraw()