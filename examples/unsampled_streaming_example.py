#!/usr/bin/env python3
"""
RealtimeMix - Unsampled 流式播放和噪音抑制示例

此示例展示如何使用 load_track_unsampled 方法：
1. 保持音频的原始采样率
2. 自动选择最佳加载方式（预加载/分块/流式）
3. 应用高级噪音抑制技术
4. 抑制爆音、电流声和爆鸣

特点：
- 支持大文件的流式播放
- 保持原始音质（不重采样）
- 实时噪音抑制和音频平滑
- 智能加载方式选择
"""

import sys
import os
import time
import numpy as np

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from realtimemix import AudioEngine
import soundfile as sf

def create_test_audio_with_noise(filename: str, duration: float = 10.0, sample_rate: int = 44100) -> str:
    """创建包含噪音的测试音频文件"""
    print(f"创建测试音频文件: {filename}")
    
    # 生成基础正弦波
    t = np.linspace(0, duration, int(duration * sample_rate), False)
    frequency = 440.0  # A4音调
    audio = 0.3 * np.sin(2 * np.pi * frequency * t)
    
    # 添加一些噪音来测试噪音抑制
    # 1. 低电平白噪音（模拟电流声）
    noise = 0.005 * np.random.randn(len(audio))
    
    # 2. 直流偏移（模拟电流声）
    dc_offset = 0.02
    
    # 3. 随机爆音（模拟咔嗒声）
    pop_indices = np.random.choice(len(audio), size=20, replace=False)
    pop_amplitude = 0.8
    
    # 4. 低频隆隆声
    low_freq_noise = 0.01 * np.sin(2 * np.pi * 60 * t)  # 60Hz噪音
    
    # 合成最终音频
    noisy_audio = audio + noise + dc_offset + low_freq_noise
    
    # 添加爆音
    for idx in pop_indices:
        noisy_audio[idx] = pop_amplitude * (1 if np.random.random() > 0.5 else -1)
    
    # 转换为立体声
    stereo_audio = np.column_stack([noisy_audio, noisy_audio])
    
    # 保存文件
    sf.write(filename, stereo_audio, sample_rate)
    print(f"已创建测试文件: {filename} ({duration}秒, {sample_rate}Hz)")
    return filename

def on_load_complete(track_id: str, success: bool, error: str = None):
    """加载完成回调"""
    if success:
        print(f"✅ 轨道 {track_id} 加载成功")
    else:
        print(f"❌ 轨道 {track_id} 加载失败: {error}")

def on_progress(track_id: str, progress: float, message: str):
    """进度回调"""
    print(f"📊 {track_id}: {progress*100:.1f}% - {message}")

def main():
    print("🎵 RealtimeMix - Unsampled 流式播放和噪音抑制示例")
    print("=" * 60)
    
    # 创建音频引擎（启用流式播放）
    print("\n1. 初始化音频引擎...")
    engine = AudioEngine(
        sample_rate=48000,  # 引擎采样率
        buffer_size=1024,
        channels=2,
        enable_streaming=True,
        streaming_threshold_mb=5  # 5MB以上使用流式播放
    )
    
    try:
        # 启动引擎
        engine.start()
        print("✅ 音频引擎启动成功")
        
        # 创建测试文件
        print("\n2. 创建测试音频文件...")
        
        # 小文件 - 预加载模式
        small_file = create_test_audio_with_noise(
            "test_small_noisy.wav", 
            duration=3.0, 
            sample_rate=44100
        )
        
        # 大文件 - 流式播放模式
        large_file = create_test_audio_with_noise(
            "test_large_noisy.wav", 
            duration=30.0, 
            sample_rate=96000  # 高采样率
        )
        
        # 测试 1: 小文件预加载（带噪音抑制）
        print("\n3. 测试小文件预加载（带噪音抑制）...")
        success = engine.load_track_unsampled(
            track_id="small_clean",
            source=small_file,
            auto_normalize=True,
            silent_lpadding_ms=200.0,  # 前面200ms静音
            silent_rpadding_ms=300.0,  # 后面300ms静音
            on_complete=on_load_complete,
            progress_callback=on_progress
        )
        
        if success:
            time.sleep(2)  # 等待加载完成
            
            # 获取轨道信息
            info = engine.get_track_info("small_clean")
            if info:
                print(f"📋 小文件信息:")
                print(f"   原始采样率: {info['sample_rate']}Hz")
                print(f"   引擎采样率: {info['engine_sample_rate']}Hz")
                print(f"   流式模式: {info['streaming_mode']}")
                print(f"   时长: {info['duration']:.2f}秒")
                print(f"   静音填充: {info['silent_lpadding_ms']}ms + {info['silent_rpadding_ms']}ms")
            
            # 播放测试
            print("\n🎵 播放小文件（已应用噪音抑制）...")
            engine.play("small_clean", fade_in=True)
            time.sleep(4)
            engine.stop("small_clean", fade_out=True)
        
        # 测试 2: 大文件流式播放（带噪音抑制）
        print("\n4. 测试大文件流式播放（带噪音抑制）...")
        success = engine.load_track_unsampled(
            track_id="large_clean",
            source=large_file,
            auto_normalize=True,
            on_complete=on_load_complete,
            progress_callback=on_progress
        )
        
        if success:
            time.sleep(3)  # 等待加载完成
            
            # 获取轨道信息
            info = engine.get_track_info("large_clean")
            if info:
                print(f"📋 大文件信息:")
                print(f"   原始采样率: {info['sample_rate']}Hz")
                print(f"   引擎采样率: {info['engine_sample_rate']}Hz")
                print(f"   流式模式: {info['streaming_mode']}")
                print(f"   时长: {info['duration']:.2f}秒")
                if info['streaming_mode']:
                    buffer_status = info.get('buffer_status', {})
                    print(f"   缓冲状态: {buffer_status}")
            
            # 播放测试
            print("\n🎵 播放大文件（流式播放 + 噪音抑制）...")
            engine.play("large_clean", fade_in=True)
            
            # 播放一段时间，显示实时统计
            for i in range(10):
                time.sleep(1)
                stats = engine.get_performance_stats()
                pos = engine.get_position("large_clean")
                print(f"   播放位置: {pos:.1f}秒, CPU: {stats['cpu_usage']:.1f}%, 峰值: {stats['peak_level']:.3f}")
            
            engine.stop("large_clean", fade_out=True)
        
        # 测试 3: 强制流式模式
        print("\n5. 测试强制流式模式...")
        success = engine.force_streaming_mode_unsampled(
            track_id="forced_streaming",
            file_path=small_file,  # 即使是小文件也强制使用流式
            auto_normalize=True,
            on_complete=on_load_complete,
            progress_callback=on_progress
        )
        
        if success:
            time.sleep(2)
            info = engine.get_track_info("forced_streaming")
            if info:
                print(f"📋 强制流式模式:")
                print(f"   流式模式: {info['streaming_mode']}")
                print(f"   原始采样率: {info['sample_rate']}Hz")
        
        # 测试 4: 显示流式播放统计
        print("\n6. 流式播放统计信息...")
        streaming_stats = engine.get_streaming_stats()
        print(f"   流式播放启用: {streaming_stats['streaming_enabled']}")
        print(f"   流式轨道数量: {streaming_stats['total_streaming_tracks']}")
        print(f"   缓冲区下溢: {streaming_stats['total_buffer_underruns']}")
        print(f"   已加载块数: {streaming_stats['total_chunks_loaded']}")
        
        # 测试 5: 噪音抑制效果对比
        print("\n7. 创建 NumPy 数组测试（噪音抑制）...")
        
        # 创建带噪音的 NumPy 数组
        duration = 2.0
        sample_rate = 44100
        t = np.linspace(0, duration, int(duration * sample_rate), False)
        
        # 基础音频
        clean_audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        
        # 添加各种噪音
        noisy_audio = clean_audio.copy()
        noisy_audio += 0.01 * np.random.randn(len(clean_audio))  # 白噪音
        noisy_audio += 0.03  # 直流偏移
        
        # 添加一些爆音
        pop_indices = np.random.choice(len(noisy_audio), size=10, replace=False)
        for idx in pop_indices:
            noisy_audio[idx] += 0.9 * (1 if np.random.random() > 0.5 else -1)
        
        # 转换为立体声
        stereo_noisy = np.column_stack([noisy_audio, noisy_audio]).astype(np.float32)
        stereo_noisy.sample_rate = sample_rate  # 添加采样率属性
        
        # 加载并播放
        success = engine.load_track_unsampled(
            track_id="numpy_test",
            source=stereo_noisy,
            auto_normalize=True,
            on_complete=on_load_complete
        )
        
        if success:
            time.sleep(1)
            print("🎵 播放 NumPy 数组（已应用噪音抑制）...")
            engine.play("numpy_test")
            time.sleep(3)
            engine.stop("numpy_test")
        
        print("\n8. 最终统计信息...")
        track_counts = engine.get_track_count()
        print(f"   总轨道数: {track_counts['total']}")
        print(f"   预加载轨道: {track_counts['preloaded']}")
        print(f"   流式轨道: {track_counts['streaming']}")
        
        performance = engine.get_performance_stats()
        print(f"   平均CPU使用率: {performance['cpu_usage']:.1f}%")
        print(f"   缓冲区下溢: {performance['underrun_count']}")
        print(f"   音频回调次数: {performance['callback_count']}")
        
        print("\n✅ 所有测试完成！")
        print("\n特点总结:")
        print("• 自动选择最佳加载方式（预加载/分块/流式）")
        print("• 保持音频原始采样率，确保音质")
        print("• 实时噪音抑制：")
        print("  - 直流偏移移除（消除电流声）")
        print("  - 高通滤波器（消除低频噪音）")
        print("  - 噪音门（抑制低电平噪音）")
        print("  - 爆音检测和抑制")
        print("  - 平滑滤波器（消除尖锐边缘）")
        print("  - 软限制器（防止削峰失真）")
        print("• 支持大文件流式播放")
        print("• 静音填充支持")
        
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理
        print("\n9. 清理资源...")
        engine.shutdown()
        
        # 删除测试文件
        for filename in ["test_small_noisy.wav", "test_large_noisy.wav"]:
            if os.path.exists(filename):
                os.remove(filename)
                print(f"🗑️  删除测试文件: {filename}")
        
        print("🎯 示例结束")

if __name__ == "__main__":
    main() 