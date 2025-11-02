import tkinter as tk

from PIL import ImageGrab
from window_manager import WindowManager


class BaseWindow:
    """基础窗口类，提供通用的窗口功能"""
    
    def __init__(self, parent):
        self.parent = parent
        self.window = None
    
    def create_window(self):
        """创建窗口，子类必须实现此方法"""
        raise NotImplementedError("子类必须实现create_window方法")
    
    def setup_window(self):
        """设置窗口的通用属性"""
        if self.window:
            # 添加Command+W快捷键绑定
            self.window.bind('<Command-w>', lambda e: self._on_closing())
            
            # 添加窗口关闭协议
            self.window.protocol("WM_DELETE_WINDOW", self._on_closing)
            
            # 设置窗口管理器
            WindowManager.setup_window(self.window)
    
    def show(self):
        """显示窗口"""
        if self.window is None:
            self.create_window()
            self.setup_window()
        else:
            WindowManager.bring_to_front(self.window)
    
    def _on_closing(self):
        """窗口关闭的统一处理"""
        if hasattr(self, 'on_closing'):
            self.on_closing()  # 调用子类的on_closing方法(如果存在)
        
        if self.window:
            WindowManager.setup_window_close(self.window)
            self.window.destroy()
            self.window = None 
    
    def capture_to_clipboard(self):
        """截取当前窗口到剪贴板"""
        try:
            # 确保窗口在最前
            self.window.lift()
            self.window.update()
            
            # 获取窗口位置和大小
            x = self.window.winfo_rootx()
            y = self.window.winfo_rooty() 
            width = self.window.winfo_width()
            height = self.window.winfo_height()
            
            # 等待一下确保窗口完全显示
            self.window.after(100)
            
            # 截取窗口图像
            from PIL import Image, ImageGrab
            image = ImageGrab.grab(bbox=(x, y, x+width, y+height))
            
            # 转换为RGB模式(去除alpha通道)
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            
            # 创建临时文件保存图片
            import os
            import tempfile
            
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            image.save(temp_file.name, format='JPEG', quality=95)
            temp_file.close()
            
            # 使用osascript将图片复制到剪贴板
            os.system(f"osascript -e 'set the clipboard to (read (POSIX file \"{temp_file.name}\") as JPEG picture)'")
            
            # 删除临时文件
            os.unlink(temp_file.name)
            
            print("capture_success")
            
        except Exception as e:
            print(f"capture_failed: {str(e)}")