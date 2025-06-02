#!/usr/bin/env python3
"""
AudioMixer 多采样率音轨示例

此示例演示如何使用AudioMixer加载和播放具有不同采样率的音轨。
"""

import numpy as np
import time
from audiomixer import AudioEngine

def generate_test_audio(duration: float, frequency: float, sample_rate: int) -> np.ndarray:
    """生成测试音频数据"""
    frames = int(duration * sample_rate)
    t = np.linspace(0, duration, frames, False)
    # 生成正弦波
    audio = np.sin(2 * np.pi * frequency * t)
    # 转换为立体声
    stereo_audio = np.column_stack([audio, audio])
    return stereo_audio.astype(np.float32) * 0.5

def main():
    print("=== AudioMixer 多采样率音轨示例 ===\n")
    
    # 创建音频引擎（默认48kHz）
    engine = AudioEngine(sample_rate=48000, buffer_size=1024)
    engine.start()
    
    try:
        # 生成不同采样率的测试音频
        print("正在生成不同采样率的测试音频...")
        
        # 音轨1: 44.1kHz - 440Hz正弦波
        audio_44k = generate_test_audio(3.0, 440.0, 44100)
        
        # 音轨2: 48kHz - 880Hz正弦波（与引擎采样率相同）
        audio_48k = generate_test_audio(3.0, 880.0, 48000)
        
        # 音轨3: 96kHz - 1320Hz正弦波
        audio_96k = generate_test_audio(3.0, 1320.0, 96000)
        
        # 音轨4: 22kHz - 660Hz正弦波
        audio_22k = generate_test_audio(3.0, 660.0, 22050)
        
        print("生成完成！\n")
        
        # 加载音轨并指定各自的采样率
        print("正在加载音轨...")
        
        # 注意：即使音频数据是在特定采样率下生成的，我们仍需要显式指定采样率
        engine.load_track("track_44k", audio_44k, sample_rate=44100)
        engine.load_track("track_48k", audio_48k, sample_rate=48000)  # 与引擎采样率相同
        engine.load_track("track_96k", audio_96k, sample_rate=96000)
        engine.load_track("track_22k", audio_22k, sample_rate=22050)
        
        # 等待加载完成
        time.sleep(0.5)
        
        # 显示采样率统计信息
        stats = engine.get_sample_rate_statistics()
        print("\n=== 采样率统计 ===")
        print(f"引擎采样率: {stats['engine_sample_rate']}Hz")
        print(f"总音轨数: {stats['total_tracks']}")
        print(f"原生采样率音轨: {stats['native_rate_tracks']}")
        print(f"需要转换的音轨: {stats['conversion_needed_tracks']}")
        print(f"所有采样率: {stats['unique_sample_rates']}")
        
        print("\n按采样率分组的音轨:")
        for sample_rate, info in stats['tracks_by_rate'].items():
            print(f"  {sample_rate}Hz: {info['count']}个音轨 {info['track_ids']}")
        
        # 显示每个音轨的详细信息
        print("\n=== 音轨详细信息 ===")
        for track_id in ["track_44k", "track_48k", "track_96k", "track_22k"]:
            info = engine.get_track_info(track_id)
            if info:
                print(f"{track_id}:")
                print(f"  采样率: {info['sample_rate']}Hz")
                print(f"  时长: {info['duration']:.2f}秒")
                print(f"  采样数: {info['samples']}")
                print(f"  转换比例: {info['sample_rate_ratio']:.3f}")
                print()
        
        # 演示1: 同时播放所有音轨
        print("=== 演示1: 同时播放所有不同采样率的音轨 ===")
        print("播放所有音轨3秒...")
        
        engine.play("track_44k", volume=0.3)  # 440Hz
        engine.play("track_48k", volume=0.3)  # 880Hz
        engine.play("track_96k", volume=0.3)  # 1320Hz
        engine.play("track_22k", volume=0.3)  # 660Hz
        
        time.sleep(3)
        
        # 停止所有音轨
        engine.stop_all_tracks(fade_out=True)
        time.sleep(1)
        
        # 演示2: 逐个播放不同采样率的音轨
        print("\n=== 演示2: 逐个播放不同采样率的音轨 ===")
        
        tracks_info = [
            ("track_22k", "22.05kHz - 660Hz"),
            ("track_44k", "44.1kHz - 440Hz"),
            ("track_48k", "48kHz - 880Hz (原生)"),
            ("track_96k", "96kHz - 1320Hz")
        ]
        
        for track_id, description in tracks_info:
            print(f"播放 {description}")
            engine.play(track_id, fade_in=True, volume=0.5)
            time.sleep(2)
            engine.stop(track_id, fade_out=True)
            time.sleep(0.5)
        
        # 演示3: 动态调整采样率
        print("\n=== 演示3: 动态调整音轨采样率 ===")
        print("播放22kHz音轨，然后动态调整其采样率...")
        
        engine.play("track_22k", volume=0.5)
        time.sleep(1)
        
        # 动态改变采样率（这会改变音高）
        print("将采样率从22.05kHz调整到44.1kHz...")
        engine.set_track_sample_rate("track_22k", 44100)
        time.sleep(1)
        
        print("将采样率调整到96kHz...")
        engine.set_track_sample_rate("track_22k", 96000)
        time.sleep(1)
        
        print("恢复到原始22.05kHz...")
        engine.set_track_sample_rate("track_22k", 22050)
        time.sleep(1)
        
        engine.stop("track_22k", fade_out=True)
        time.sleep(1)
        
        # 显示性能统计
        perf_stats = engine.get_performance_stats()
        print("\n=== 性能统计 ===")
        print(f"CPU使用率: {perf_stats['cpu_usage']:.1f}%")
        print(f"峰值电平: {perf_stats['peak_level']:.3f}")
        print(f"当前活跃音轨: {perf_stats['active_tracks']}")
        print(f"音频中断次数: {perf_stats['underrun_count']}")
        
        print("\n示例演示完成！")
        
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"错误: {e}")
    finally:
        print("正在关闭音频引擎...")
        engine.shutdown()

if __name__ == "__main__":
    main() 