import threading
import time
import tkinter as tk


class WindowManager:
    """窗口管理器，统一处理窗口显示行为"""
    
    @staticmethod
    def setup_window(window: tk.Toplevel):
        """设置窗口显示行为
        
        Args:
            window: 要设置的Toplevel窗口实例
        """
        if window:
            # 设置为独立窗口
            window.attributes('-topmost', True)  # 设置为最顶层
            window.focus_force()  # 强制获取焦点
            
    @staticmethod
    def setup_window_close(window: tk.Toplevel):
        """设置窗口关闭行为
        
        Args:
            window: 要设置的Toplevel窗口实例
        """
        if window:
            window.attributes('-topmost', False)  # 关闭前取消置顶
            
    @staticmethod
    def bring_to_front(window: tk.Toplevel):
        """将窗口带到最前
        
        Args:
            window: 要设置的Toplevel窗口实例
        """
        if window:
            window.attributes('-topmost', True)  # 重新设置为最顶层
            window.lift()  # 提升到最前
            window.focus_force()  # 强制获取焦点
    
    @staticmethod
    def shake_window(window, duration: float = 0.5, intensity: int = 10, repeat_count: int = 3):
        """窗口震动效果
        
        Args:
            window: 要震动的窗口实例
            duration: 单次震动持续时间（秒）
            intensity: 震动强度（像素）
            repeat_count: 重复震动次数，默认3次
        """
        if not window or not window.winfo_exists():
            return
        
        def _shake():
            try:
                # 获取窗口当前位置
                original_x = window.winfo_x()
                original_y = window.winfo_y()
                
                # 重复震动指定次数
                for repeat in range(repeat_count):
                    if not window.winfo_exists():
                        break
                    
                    print(f"🔔 开始第{repeat + 1}次震动")
                    
                    # 震动次数和间隔
                    shake_count = int(duration * 30)  # 每秒30次震动，更频繁
                    interval = duration / shake_count
                    
                    for i in range(shake_count):
                        if not window.winfo_exists():
                            break
                        
                        # 计算震动偏移 - 使用更平滑的衰减函数
                        progress = i / shake_count
                        decay_factor = (1 - progress) * (1 - progress)  # 二次衰减，更平滑
                        
                        # 交替震动方向，幅度逐渐减小
                        direction_x = 1 if i % 2 == 0 else -1
                        direction_y = 1 if i % 3 == 0 else -1
                        
                        offset_x = intensity * direction_x * decay_factor
                        offset_y = intensity * direction_y * decay_factor * 0.7  # Y轴震动稍小
                        
                        # 应用震动偏移
                        new_x = original_x + offset_x
                        new_y = original_y + offset_y
                        
                        # 移动窗口
                        window.geometry(f"+{int(new_x)}+{int(new_y)}")
                        
                        # 短暂延迟
                        time.sleep(interval)
                    
                    # 恢复原始位置
                    if window.winfo_exists():
                        window.geometry(f"+{original_x}+{original_y}")
                    
                    # 如果不是最后一次震动，添加间隔时间
                    if repeat < repeat_count - 1:
                        time.sleep(0.2)  # 每次震动间隔0.2秒
                
                print(f"🔔 完成{repeat_count}次震动")
                    
            except Exception as e:
                print(f"窗口震动失败: {e}")
        
        # 在单独线程中执行震动，避免阻塞主线程
        threading.Thread(target=_shake, daemon=True).start()
    
    @staticmethod
    def shake_and_focus(window, duration: float = 0.5, intensity: int = 10, repeat_count: int = 3):
        """窗口震动并获取焦点
        
        Args:
            window: 要震动的窗口实例
            duration: 单次震动持续时间（秒）
            intensity: 震动强度（像素）
            repeat_count: 重复震动次数，默认3次
        """
        if not window or not window.winfo_exists():
            return
        
        # 先震动
        WindowManager.shake_window(window, duration, intensity, repeat_count)
        
        # 然后获取焦点
        def _focus():
            time.sleep(0.01)  # 减少延迟，让震动更快开始
            if window.winfo_exists():
                try:
                    # 检查窗口是否有attributes方法（Toplevel才有）
                    if hasattr(window, 'attributes'):
                        window.attributes('-topmost', True)
                    window.lift()
                    window.focus_force()
                except Exception as e:
                    print(f"设置窗口焦点失败: {e}")
        
        threading.Thread(target=_focus, daemon=True).start() 