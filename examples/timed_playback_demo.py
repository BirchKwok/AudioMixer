#!/usr/bin/env python3
"""
RealtimeMix 内置定时功能演示

演示如何使用内置的定时停止、延迟播放和自动调度功能，
无需外部Timer，所有定时操作都由AudioEngine内部管理。
"""

import numpy as np
import time
from realtimemix import AudioEngine


def generate_test_audio(frequency, duration, sample_rate=48000):
    """生成测试音频信号"""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    sine_wave = 0.3 * np.sin(2 * np.pi * frequency * t)
    return np.column_stack([sine_wave, sine_wave]).astype(np.float32)


def main():
    print("=== RealtimeMix 内置定时功能演示 ===")
    
    # 初始化音频引擎
    engine = AudioEngine(
        sample_rate=48000,
        buffer_size=1024,
        channels=2,
        max_tracks=8
    )
    
    try:
        engine.start()
        print("✅ 音频引擎已启动")
        
        # 生成测试音频
        print("\n📢 生成测试音频...")
        engine.load_track("tone_440", generate_test_audio(440, 10.0))  # A音，10秒
        engine.load_track("tone_523", generate_test_audio(523, 8.0))   # C音，8秒
        engine.load_track("tone_659", generate_test_audio(659, 6.0))   # E音，6秒
        engine.load_track("background", generate_test_audio(220, 30.0)) # 背景音，30秒
        
        print("✅ 测试音频已生成")
        
        # 演示1：定时播放功能
        print("\n🎵 演示1：定时播放功能")
        print("播放背景音乐5秒后自动淡出停止...")
        engine.play_for_duration("background", 5.0, fade_in=True, fade_out=True)
        
        time.sleep(6)  # 等待播放完成
        print("✅ 背景音乐已自动停止")
        
        # 演示2：延迟停止功能
        print("\n🎵 演示2：延迟停止功能")
        print("开始播放440Hz音调，3秒后自动用1秒时间淡出...")
        engine.play("tone_440", fade_in=True)
        engine.stop("tone_440", delay_sec=3.0, fade_duration=1.0)
        
        time.sleep(5)  # 等待淡出完成
        print("✅ 440Hz音调已延迟停止")
        
        # 演示3：多轨定时调度
        print("\n🎵 演示3：多轨定时调度")
        print("安排音频序列播放：立即播放523Hz → 2秒后播放659Hz → 4秒后播放440Hz")
        
        # 立即播放第一个
        engine.play_for_duration("tone_523", 1.5, fade_in=True)
        
        # 2秒后播放第二个
        engine.play("tone_659", fade_in=True)
        engine.pause("tone_659")  # 先暂停
        # 安排2秒后恢复，播放1.5秒后停止
        engine.stop("tone_659", delay_sec=2.0 + 1.5, fade_duration=0.5)
        
        # 简化：直接用延迟播放
        def delayed_play():
            engine.resume("tone_659")
        
        import threading
        threading.Timer(2.0, delayed_play).start()
        
        # 4秒后播放第三个
        threading.Timer(4.0, lambda: engine.play_for_duration("tone_440", 1.5)).start()
        
        time.sleep(7)  # 等待序列播放完成
        print("✅ 音频序列播放完成")
        
        # 演示4：定时任务管理
        print("\n🎵 演示4：定时任务管理")
        print("安排多个定时停止任务，然后查看和取消...")
        
        # 播放背景音
        engine.play("background", loop=True, volume=0.3)
        
        # 安排多个定时停止
        engine.stop("background", delay_sec=10.0, fade_duration=2.0)
        
        # 查看定时任务
        tasks = engine.get_scheduled_tasks()
        print(f"当前定时任务: {list(tasks.keys())}")
        
        # 等待2秒后取消任务
        time.sleep(2)
        cancelled = engine.cancel_scheduled_task("background", "stop")
        print(f"任务取消结果: {cancelled}")
        
        # 立即停止
        engine.stop("background", fade_out=True, fade_duration=1.0)
        time.sleep(1.5)
        
        # 演示5：复杂的音频调度场景
        print("\n🎵 演示5：复杂音频调度场景")
        print("模拟播客场景：intro音乐 → 主要内容 → outro音乐")
        
        # 重新加载更长的音频用于演示
        engine.load_track("intro", generate_test_audio(440, 5.0))
        engine.load_track("main", generate_test_audio(523, 8.0))
        engine.load_track("outro", generate_test_audio(659, 3.0))
        
        # intro音乐播放3秒后淡出
        engine.play_for_duration("intro", 3.0, fade_in=True, fade_out=True)
        
        # 2秒后开始主要内容，播放5秒
        engine.play("main")
        engine.pause("main")
        threading.Timer(2.0, lambda: engine.resume("main")).start()
        engine.stop("main", delay_sec=2.0 + 5.0, fade_duration=1.0)
        
        # 7秒后播放outro
        threading.Timer(7.0, lambda: engine.play_for_duration("outro", 2.0, fade_in=True)).start()
        
        time.sleep(10)
        print("✅ 播客场景演示完成")
        
        # 性能统计
        stats = engine.get_performance_stats()
        print(f"\n📊 性能统计:")
        print(f"   CPU使用率: {stats['cpu_usage']:.1f}%")
        print(f"   峰值电平: {stats['peak_level']:.3f}")
        print(f"   活跃轨道: {stats['active_tracks']}")
        
        print("\n🎉 所有演示完成！内置定时功能工作正常。")
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
    finally:
        # 清理
        print("\n🔧 正在清理资源...")
        engine.cancel_all_scheduled_tasks()  # 取消所有定时任务
        engine.shutdown()
        print("✅ 清理完成")


if __name__ == "__main__":
    main() 