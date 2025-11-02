#!/usr/bin/env python3
"""音频通知模块 - 用于Mac端播放买卖信号警告音效"""

import os
import platform
import subprocess
import threading
import time
from typing import Optional


class AudioNotifier:
    """音频通知器"""
    
    def __init__(self):
        self.system = platform.system()
        self.sound_enabled = True
        self._init_sounds()
    
    def _init_sounds(self):
        """初始化音效文件路径"""
        if self.system == "Darwin":  # macOS
            # macOS系统音效路径
            self.buy_sound = "/System/Library/Sounds/Glass.aiff"
            self.sell_sound = "/System/Library/Sounds/Sosumi.aiff"
            self.alert_sound = "/System/Library/Sounds/Ping.aiff"
            # 布林带音效 - 使用不同音调的音效
            self.bollinger_breakthrough_sound = "/System/Library/Sounds/Funk.aiff"  # 突破音效
            self.bollinger_breakdown_sound = "/System/Library/Sounds/Bottle.aiff"  # 跌破音效
        elif self.system == "Windows":  # Windows
            # Windows音效资源路径（相对于程序目录）
            base_path = os.path.join(os.path.dirname(__file__), "..", "resources", "sounds")
            self.buy_sound = os.path.join(base_path, "buy_signal.wav")
            self.sell_sound = os.path.join(base_path, "sell_signal.wav")
            self.alert_sound = os.path.join(base_path, "alert.wav")
            # 布林带音效
            self.bollinger_breakthrough_sound = os.path.join(base_path, "bollinger_breakthrough.wav")
            self.bollinger_breakdown_sound = os.path.join(base_path, "bollinger_breakdown.wav")
        else:
            # 其他系统使用默认音效
            self.buy_sound = None
            self.sell_sound = None
            self.alert_sound = None
            self.bollinger_breakthrough_sound = None
            self.bollinger_breakdown_sound = None
    
    def play_buy_signal(self):
        """播放买入信号音效"""
        if self.sound_enabled:
            self._play_sound(self.buy_sound, "买入信号")
    
    def play_sell_signal(self):
        """播放卖出信号音效"""
        if self.sound_enabled:
            self._play_sound(self.sell_sound, "卖出信号")
    
    def play_alert(self):
        """播放一般警告音效"""
        if self.sound_enabled:
            self._play_sound(self.alert_sound, "警告")
    
    def play_bollinger_breakthrough(self):
        """播放布林带突破音效"""
        if self.sound_enabled:
            self._play_sound(self.bollinger_breakthrough_sound, "布林带突破")
    
    def play_bollinger_breakdown(self):
        """播放布林带跌破音效"""
        if self.sound_enabled:
            self._play_sound(self.bollinger_breakdown_sound, "布林带跌破")
    
    def _play_sound(self, sound_file: Optional[str], signal_type: str):
        """播放音效文件"""
        try:
            if self.system == "Darwin" and sound_file and os.path.exists(sound_file):
                # macOS使用afplay命令播放音效
                subprocess.run(['afplay', sound_file], 
                             capture_output=True, 
                             timeout=5)
                print(f"🔊 播放{signal_type}音效")
            else:
                # 使用Python内置的beep音效（如果支持）
                self._play_beep()
                print(f"🔊 播放{signal_type}提示音")
        except Exception as e:
            print(f"播放音效失败: {e}")
            # 降级到beep音效
            self._play_beep()
    
    def _play_beep(self):
        """播放beep音效（降级方案）"""
        try:
            # 尝试使用系统命令播放beep
            if self.system == "Darwin":
                print('\a', end='', flush=True)
            else:
                # 其他系统使用Python的print bell字符
                print('\a', end='', flush=True)
        except:
            # 最后的降级方案：打印提示
            print("🔔 音效播放失败，请检查系统设置")
    
    def enable_sound(self):
        """启用音效"""
        self.sound_enabled = True
        print("🔊 音效通知已启用")
    
    def disable_sound(self):
        """禁用音效"""
        self.sound_enabled = False
        print("🔇 音效通知已禁用")
    
    def test_sounds(self):
        """测试所有音效"""
        print("🔊 测试音效...")
        time.sleep(0.5)
        self.play_buy_signal()
        time.sleep(1)
        self.play_sell_signal()
        time.sleep(1)
        self.play_alert()
        time.sleep(1)
        self.play_bollinger_breakthrough()
        time.sleep(1)
        self.play_bollinger_breakdown()
        print("✅ 音效测试完成")

# 全局音频通知器实例
audio_notifier = AudioNotifier()

def notify_buy_signal():
    """买入信号通知"""
    audio_notifier.play_buy_signal()

def notify_sell_signal():
    """卖出信号通知"""
    audio_notifier.play_sell_signal()

def notify_alert():
    """一般警告通知"""
    audio_notifier.play_alert()

def notify_bollinger_breakthrough():
    """布林带突破通知"""
    audio_notifier.play_bollinger_breakthrough()

def notify_bollinger_breakdown():
    """布林带跌破通知"""
    audio_notifier.play_bollinger_breakdown()

if __name__ == "__main__":
    # 测试音效
    audio_notifier.test_sounds()
