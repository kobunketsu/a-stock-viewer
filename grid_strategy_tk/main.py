import os
import sys

# 添加src目录到Python路径
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if src_path not in sys.path:
    sys.path.append(src_path)

from app import create_main_window


def main():
    """
    程序入口函数
    """
    try:
        # 创建并启动主窗口
        main_window = create_main_window()
        main_window.root.mainloop()
    except Exception as e:
        print(f"Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 