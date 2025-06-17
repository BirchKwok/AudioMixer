#!/usr/bin/env python3
"""
实时音频回调功能使用示例

这个示例展示如何在实际应用中使用RealtimeMix的实时音频回调功能，
实现主音轨播放过程中的音频插入、静音和恢复。

应用场景：
- 语音播放中插入提示音
- 音乐播放中插入语音通知  
- 广播节目中的实时插播
- 音频教学中的定时提示
"""

import time
import numpy as np
from typing import Optional
from realtimemix import AudioEngine


class AudioCallbackManager:
    """音频回调管理器"""
    
    def __init__(self, sample_rate: int = 48000):
        """初始化音频回调管理器"""
        self.sample_rate = sample_rate
        self.engine = AudioEngine(
            sample_rate=sample_rate,
            buffer_size=1024,
            channels=2,
            enable_streaming=False
        )
        
        self.callback_queue = []  # 回调队列
        self.main_track_volume = 1.0  # 主音轨原始音量
        
        print("🎵 音频回调管理器初始化完成")
    
    def start(self) -> bool:
        """启动音频引擎"""
        try:
            self.engine.start()
            print("✅ 音频引擎启动成功")
            return True
        except Exception as e:
            print(f"❌ 音频引擎启动失败: {e}")
            return False
    
    def stop(self):
        """停止音频引擎"""
        try:
            self.engine.shutdown()
            print("✅ 音频引擎已停止")
        except Exception as e:
            print(f"❌ 音频引擎停止失败: {e}")
    
    def generate_beep(self, frequency: float = 800.0, duration: float = 0.5) -> np.ndarray:
        """生成提示音"""
        frames = int(duration * self.sample_rate)
        t = np.linspace(0, duration, frames, False)
        
        # 生成正弦波提示音
        beep = np.sin(2 * np.pi * frequency * t) * 0.7
        
        # 添加包络
        envelope = np.ones_like(beep)
        fade_frames = int(0.02 * self.sample_rate)  # 20ms渐变
        envelope[:fade_frames] = np.linspace(0, 1, fade_frames)
        envelope[-fade_frames:] = np.linspace(1, 0, fade_frames)
        
        beep *= envelope
        return np.column_stack((beep, beep)).astype(np.float32)
    
    def generate_notification_sound(self, duration: float = 1.0) -> np.ndarray:
        """生成通知音"""
        frames = int(duration * self.sample_rate)
        t = np.linspace(0, duration, frames, False)
        
        # 生成双音调通知音 (800Hz + 1000Hz)
        tone1 = np.sin(2 * np.pi * 800 * t) * 0.4
        tone2 = np.sin(2 * np.pi * 1000 * t) * 0.3
        notification = tone1 + tone2
        
        # 添加颤音效果
        tremolo = 0.3 * np.sin(2 * np.pi * 6 * t) + 0.7
        notification *= tremolo
        
        # 添加包络
        envelope = np.ones_like(notification)
        fade_frames = int(0.05 * self.sample_rate)  # 50ms渐变
        envelope[:fade_frames] = np.linspace(0, 1, fade_frames)
        envelope[-fade_frames:] = np.linspace(1, 0, fade_frames)
        
        notification *= envelope
        return np.column_stack((notification, notification)).astype(np.float32)
    
    def load_main_audio(self, audio_data: np.ndarray, track_id: str = "main_audio") -> bool:
        """加载主音频"""
        try:
            success = self.engine.load_track(track_id, audio_data, sample_rate=self.sample_rate)
            if success:
                print(f"✅ 主音频 '{track_id}' 加载成功")
                return True
            else:
                print(f"❌ 主音频 '{track_id}' 加载失败")
                return False
        except Exception as e:
            print(f"❌ 加载主音频失败: {e}")
            return False
    
    def load_callback_sounds(self):
        """加载回调音频"""
        try:
            # 加载提示音
            beep_sound = self.generate_beep(frequency=800.0, duration=0.8)
            self.engine.load_track("beep", beep_sound, sample_rate=self.sample_rate)
            
            # 加载通知音
            notification_sound = self.generate_notification_sound(duration=1.5)
            self.engine.load_track("notification", notification_sound, sample_rate=self.sample_rate)
            
            print("✅ 回调音频加载完成")
            return True
        except Exception as e:
            print(f"❌ 加载回调音频失败: {e}")
            return False
    
    def create_audio_callback(self, callback_type: str, track_id: str = "main_audio"):
        """创建音频回调函数"""
        def audio_callback(track_id: str, target_time: float, actual_time: float):
            try:
                precision_ms = abs(actual_time - target_time) * 1000
                print(f"🎯 [{callback_type}] 回调触发! 时间: {actual_time:.2f}s (精度: {precision_ms:.1f}ms)")
                
                # 记录主音轨原始音量
                main_info = self.engine.get_track_info(track_id)
                if main_info:
                    self.main_track_volume = main_info.get('volume', 1.0)
                
                # 主音轨静音
                print(f"🔇 主音轨静音...")
                self.engine.mute(track_id)
                
                # 播放回调音频
                if callback_type == "beep":
                    print("🔊 播放提示音...")
                    self.engine.play("beep", volume=0.8)
                    recovery_delay = 0.9  # 提示音时长 + 缓冲
                elif callback_type == "notification":
                    print("🔔 播放通知音...")
                    self.engine.play("notification", volume=0.7)
                    recovery_delay = 1.6  # 通知音时长 + 缓冲
                else:
                    print(f"🔊 播放自定义回调音频...")
                    recovery_delay = 1.0
                
                # 设置恢复定时器
                import threading
                def restore_main_audio():
                    try:
                        print("🔊 恢复主音轨播放...")
                        # 停止回调音频
                        if callback_type == "beep":
                            self.engine.stop("beep", fade_out=False)
                        elif callback_type == "notification":
                            self.engine.stop("notification", fade_out=False)
                        
                        # 恢复主音轨
                        self.engine.unmute(track_id)
                        print("✅ 主音轨已恢复")
                    except Exception as e:
                        print(f"❌ 恢复主音轨失败: {e}")
                
                timer = threading.Timer(recovery_delay, restore_main_audio)
                timer.start()
                
            except Exception as e:
                print(f"❌ 回调处理失败: {e}")
        
        return audio_callback
    
    def register_timed_callback(self, track_id: str, target_time: float, 
                              callback_type: str = "beep", tolerance: float = 0.015) -> bool:
        """注册定时回调"""
        try:
            callback_func = self.create_audio_callback(callback_type, track_id)
            success = self.engine.register_position_callback(
                track_id=track_id,
                target_time=target_time,
                callback_func=callback_func,
                tolerance=tolerance
            )
            
            if success:
                print(f"✅ 回调注册成功: {callback_type} @ {target_time}s")
                return True
            else:
                print(f"❌ 回调注册失败: {callback_type} @ {target_time}s")
                return False
                
        except Exception as e:
            print(f"❌ 注册回调失败: {e}")
            return False
    
    def play_with_callbacks(self, track_id: str = "main_audio", volume: float = 0.8) -> bool:
        """播放带回调的音频"""
        try:
            print(f"🎵 开始播放音频: {track_id}")
            self.engine.play(track_id, volume=volume)
            return True
        except Exception as e:
            print(f"❌ 播放音频失败: {e}")
            return False
    
    def monitor_playback(self, track_id: str, duration: float):
        """监控播放状态"""
        print(f"⏳ 监控播放状态 ({duration:.1f}s)...")
        start_time = time.time()
        
        while time.time() - start_time < duration:
            current_time = time.time() - start_time
            
            # 每3秒显示状态
            if int(current_time) % 3 == 0 and current_time - int(current_time) < 0.1:
                playing_tracks = self.engine.get_playing_tracks()
                is_muted = self.engine.is_muted(track_id)
                print(f"⏱️  {current_time:.1f}s - 播放轨道: {playing_tracks}, 主轨静音: {is_muted}")
            
            time.sleep(0.1)
        
        print("⏹️ 停止播放...")
        self.engine.stop_all_tracks(fade_out=False)


def demo_simple_callback():
    """简单回调演示"""
    print("\n" + "="*50)
    print("🎯 简单音频回调演示")
    print("="*50)
    
    # 创建管理器
    manager = AudioCallbackManager()
    
    try:
        # 启动引擎
        if not manager.start():
            return
        
        # 生成演示音频 (10秒, 440Hz低音)
        duration = 10.0
        frames = int(duration * manager.sample_rate)
        t = np.linspace(0, duration, frames, False)
        
        # 低频背景音
        background = np.sin(2 * np.pi * 220 * t) * 0.4
        # 添加颤音
        tremolo = 0.3 * np.sin(2 * np.pi * 3 * t) + 0.7
        background *= tremolo
        
        # 立体声
        audio_data = np.column_stack((background, background)).astype(np.float32)
        
        # 加载音频
        if not manager.load_main_audio(audio_data):
            return
        
        # 加载回调音频
        if not manager.load_callback_sounds():
            return
        
        time.sleep(0.5)  # 等待加载完成
        
        # 注册回调
        manager.register_timed_callback("main_audio", 3.0, "beep")
        manager.register_timed_callback("main_audio", 7.0, "notification")
        
        # 开始播放
        manager.play_with_callbacks("main_audio", volume=0.6)
        
        # 监控播放
        manager.monitor_playback("main_audio", 10.0)
        
        print("✅ 简单回调演示完成")
        
    except KeyboardInterrupt:
        print("\n⏹️ 演示被用户中断")
    except Exception as e:
        print(f"❌ 演示失败: {e}")
    finally:
        manager.stop()


def demo_multiple_callbacks():
    """多回调演示"""
    print("\n" + "="*50)
    print("🎯 多回调音频演示")
    print("="*50)
    
    # 创建管理器
    manager = AudioCallbackManager()
    
    try:
        # 启动引擎
        if not manager.start():
            return
        
        # 生成更长的演示音频 (15秒, 多频率混合)
        duration = 15.0
        frames = int(duration * manager.sample_rate)
        t = np.linspace(0, duration, frames, False)
        
        # 复合背景音 (多个正弦波)
        freq1 = 220.0  # 低音
        freq2 = 330.0  # 中音
        audio1 = np.sin(2 * np.pi * freq1 * t) * 0.3
        audio2 = np.sin(2 * np.pi * freq2 * t) * 0.2
        
        background = audio1 + audio2
        
        # 立体声
        audio_data = np.column_stack((background, background)).astype(np.float32)
        
        # 加载音频
        if not manager.load_main_audio(audio_data):
            return
        
        # 加载回调音频
        if not manager.load_callback_sounds():
            return
        
        time.sleep(0.5)  # 等待加载完成
        
        # 注册多个回调
        callback_schedule = [
            (2.5, "beep"),
            (6.0, "notification"),
            (9.5, "beep"),
            (13.0, "notification")
        ]
        
        for target_time, callback_type in callback_schedule:
            manager.register_timed_callback("main_audio", target_time, callback_type)
        
        # 开始播放
        manager.play_with_callbacks("main_audio", volume=0.7)
        
        # 监控播放
        manager.monitor_playback("main_audio", 15.0)
        
        print("✅ 多回调演示完成")
        
    except KeyboardInterrupt:
        print("\n⏹️ 演示被用户中断")
    except Exception as e:
        print(f"❌ 演示失败: {e}")
    finally:
        manager.stop()


def main():
    """主程序"""
    print("🎵 RealtimeMix 实时音频回调使用示例")
    print("这个示例展示如何在音频播放中实时插入回调音频")
    print("包括主音轨静音、回调音频播放、主音轨恢复等功能")
    
    try:
        # 运行简单演示
        demo_simple_callback()
        
        # 短暂停顿
        print("\n⏸️ 准备下一个演示...")
        time.sleep(2)
        
        # 运行多回调演示
        demo_multiple_callbacks()
        
        print("\n🎉 所有演示完成!")
        print("\n💡 主要功能:")
        print("  ✅ 实时音频回调触发")
        print("  ✅ 主音轨自动静音")
        print("  ✅ 插入音频播放")
        print("  ✅ 主音轨自动恢复")
        print("  ✅ 高精度时间控制")
        print("  ✅ 多回调点支持")
        
    except KeyboardInterrupt:
        print("\n⏹️ 程序被用户中断")
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")


if __name__ == "__main__":
    main() 