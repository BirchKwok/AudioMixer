#!/usr/bin/env python3
"""
响度匹配功能演示脚本

展示如何使用不同的响度匹配算法进行音轨响度平衡。
"""

import numpy as np
from realtimemix import AudioEngine
import time


def create_test_audio(duration=3.0, frequency=440, sample_rate=48000, volume=0.5):
    """创建测试音频数据"""
    samples = int(duration * sample_rate)
    t = np.linspace(0, duration, samples, False)
    # 创建正弦波
    audio = volume * np.sin(2 * np.pi * frequency * t)
    # 转换为立体声
    stereo_audio = np.column_stack([audio, audio])
    return stereo_audio.astype(np.float32)


def main():
    print("=== 响度匹配功能演示 ===\n")
    
    # 创建音频引擎
    engine = AudioEngine(sample_rate=48000, buffer_size=1024)
    
    try:
        # 启动引擎
        engine.start()
        print("音频引擎已启动")
        
        # 创建不同响度的测试音频
        print("\n1. 创建测试音频...")
        audio1 = create_test_audio(duration=5.0, frequency=440, volume=0.8)  # 较大音量
        audio2 = create_test_audio(duration=5.0, frequency=880, volume=0.3)  # 较小音量
        
        # 加载音轨
        engine.load_track("track1", audio1)
        engine.load_track("track2", audio2)
        print("已加载两个不同响度的测试音轨")
        
        # 演示不同的响度匹配算法
        print("\n2. 测试不同的响度匹配算法...")
        
        algorithms = [
            ("rms", "RMS均方根"),
            ("peak", "峰值响度"),
            ("lufs", "LUFS广播标准"),
            ("a_weighted", "A权重响度"),
            ("matchering", "Matchering算法")
        ]
        
        for method, name in algorithms:
            print(f"\n测试 {name} ({method}):")
            try:
                vol1, vol2 = engine.match_loudness("track1", "track2", target_loudness=0.7, method=method)
                print(f"  建议音量 - Track1: {vol1:.3f}, Track2: {vol2:.3f}")
                print(f"  音量比例: {vol2/vol1:.3f}")
            except Exception as e:
                print(f"  错误: {e}")
        
        # 演示交叉淡入淡出功能
        print("\n3. 演示带响度匹配的交叉淡入淡出...")
        
        # 播放第一个音轨
        engine.play("track1", volume=0.7)
        print("开始播放 Track1...")
        time.sleep(2)
        
        # 使用RMS算法进行交叉淡入淡出
        print("执行交叉淡入淡出 (使用RMS算法)...")
        engine.crossfade("track1", "track2", duration=2.0, loudness_match_method="rms")
        time.sleep(3)
        
        # 停止播放
        engine.stop_all_tracks()
        print("演示完成")
        
        # 显示性能统计
        print("\n4. 性能统计:")
        stats = engine.get_performance_stats()
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.4f}")
            else:
                print(f"  {key}: {value}")
        
    except Exception as e:
        print(f"演示过程中发生错误: {e}")
    
    finally:
        # 清理资源
        engine.shutdown()
        print("\n音频引擎已关闭")


if __name__ == "__main__":
    main() 