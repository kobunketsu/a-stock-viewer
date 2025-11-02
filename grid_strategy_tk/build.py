import os
import shutil
import subprocess


def clean_build():
    """清理旧的构建文件"""
    dirs_to_clean = ['build', 'dist']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)

def build_exe():
    """构建exe文件"""
    try:
        # 清理旧文件
        clean_build()
        
        # 执行PyInstaller打包
        subprocess.run([
            'pyinstaller',
            '--clean',
            '--noconfirm',
            'build_config.spec'
        ], check=True)
        
        print("打包完成！输出文件位于 dist/GridStrategyTK.exe")
        
    except subprocess.CalledProcessError as e:
        print(f"打包过程出错: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == '__main__':
    build_exe() 