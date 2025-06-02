#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大文件加载优化演示
展示AudioEngine的大文件分块加载功能
"""

import time
import os
import threading
import numpy as np
import soundfile as sf
from audiomixer import AudioEngine


def create_test_large_file(filename: str, duration_minutes: float = 10, sample_rate: int = 48000):
    """
    创建测试用的大音频文件
    :param filename: 文件名
    :param duration_minutes: 持续时间（分钟）
    :param sample_rate: 采样率
    """
    print(f"创建测试文件: {filename} ({duration_minutes}分钟)")
    
    # 计算总样本数
    duration_seconds = duration_minutes * 60
    total_samples = int(duration_seconds * sample_rate)
    
    # 生成测试音频（多种频率混合的正弦波）
    t = np.linspace(0, duration_seconds, total_samples, False)
    
    # 混合多个频率以创建更复杂的音频
    frequencies = [220, 440, 880, 1760]  # A音符的各个八度
    audio = np.zeros_like(t)
    
    for i, freq in enumerate(frequencies):
        amplitude = 0.1 / (i + 1)  # 高频成分振幅较小
        audio += amplitude * np.sin(2 * np.pi * freq * t)
    
    # 添加一些随机噪声
    audio += 0.01 * np.random.randn(len(audio))
    
    # 创建立体声
    stereo_audio = np.column_stack([audio, audio * 0.8])  # 右声道稍弱
    
    # 保存文件
    sf.write(filename, stereo_audio, sample_rate)
    
    file_size = os.path.getsize(filename)
    print(f"文件创建完成: {file_size / (1024*1024):.1f}MB")
    
    return filename


class LoadingProgressMonitor:
    """加载进度监控器"""
    
    def __init__(self):
        self.progresses = {}
        self.lock = threading.Lock()
    
    def progress_callback(self, track_id: str, progress: float, message: str):
        """进度回调函数"""
        with self.lock:
            self.progresses[track_id] = {
                'progress': progress,
                'message': message,
                'timestamp': time.time()
            }
            print(f"[{track_id}] {progress*100:.1f}% - {message}")
    
    def completion_callback(self, track_id: str, success: bool, error: str = None):
        """完成回调函数"""
        if success:
            print(f"✓ {track_id} 加载完成!")
        else:
            print(f"✗ {track_id} 加载失败: {error}")
    
    def get_summary(self):
        """获取进度摘要"""
        with self.lock:
            return dict(self.progresses)


def demonstrate_large_file_loading():
    """演示大文件加载优化"""
    print("=== 大文件加载优化演示 ===\n")
    
    # 创建测试文件
    test_files = []
    
    # 小文件（50MB）
    small_file = "test_small.wav"
    if not os.path.exists(small_file):
        create_test_large_file(small_file, duration_minutes=2.5, sample_rate=48000)
    test_files.append(("小文件", small_file))
    
    # 大文件（200MB）
    large_file = "test_large.wav"
    if not os.path.exists(large_file):
        create_test_large_file(large_file, duration_minutes=10, sample_rate=48000)
    test_files.append(("大文件", large_file))
    
    # 初始化音频引擎
    print("\n初始化音频引擎...")
    engine = AudioEngine(sample_rate=48000, buffer_size=1024, channels=2)
    
    # 配置大文件设置
    engine.set_large_file_settings(
        threshold_mb=100,      # 100MB以上使用分块加载
        max_memory_mb=256,     # 最大内存使用256MB
        chunk_size_frames=16384  # 每块16384帧
    )
    
    engine.start()
    
    try:
        # 创建进度监控器
        monitor = LoadingProgressMonitor()
        
        print("\n开始加载文件...")
        print("-" * 60)
        
        # 记录开始时间
        start_times = {}
        
        # 加载所有文件
        for name, filepath in test_files:
            track_id = f"track_{name}"
            file_size = os.path.getsize(filepath)
            
            print(f"\n开始加载 {name}: {filepath}")
            print(f"文件大小: {file_size / (1024*1024):.1f}MB")
            
            start_times[track_id] = time.time()
            
            success = engine.load_track(
                track_id=track_id,
                source=filepath,
                on_complete=monitor.completion_callback,
                progress_callback=monitor.progress_callback
            )
            
            if not success:
                print(f"无法开始加载 {name}")
        
        print("\n等待加载完成...")
        
        # 等待所有加载完成
        max_wait = 300  # 最多等待5分钟
        wait_start = time.time()
        
        while time.time() - wait_start < max_wait:
            tracks = engine.list_tracks()
            loaded_count = len(tracks)
            expected_count = len(test_files)
            
            if loaded_count >= expected_count:
                break
            
            time.sleep(1)
            
            # 显示当前状态
            memory_stats = engine.get_memory_usage()
            print(f"当前内存使用: {memory_stats['total_memory_mb']:.1f}MB / {memory_stats['max_memory_mb']:.1f}MB")
        
        print("\n=== 加载结果 ===")
        
        # 显示加载时间统计
        for name, filepath in test_files:
            track_id = f"track_{name}"
            if track_id in start_times:
                elapsed = time.time() - start_times[track_id]
                file_size = os.path.getsize(filepath)
                speed = (file_size / (1024*1024)) / elapsed  # MB/s
                
                print(f"{name}:")
                print(f"  文件大小: {file_size / (1024*1024):.1f}MB")
                print(f"  加载时间: {elapsed:.1f}秒")
                print(f"  加载速度: {speed:.1f}MB/s")
        
        # 显示内存使用情况
        print("\n=== 内存使用情况 ===")
        memory_stats = engine.get_memory_usage()
        print(f"总内存使用: {memory_stats['total_memory_mb']:.1f}MB")
        print(f"音轨数量: {memory_stats['track_count']}")
        print(f"大文件阈值: {memory_stats['large_file_threshold_mb']:.1f}MB")
        print(f"分块大小: {memory_stats['chunk_size_frames']}帧")
        
        print("\n各音轨内存使用:")
        for track_id, info in memory_stats['track_memory'].items():
            print(f"  {track_id}: {info['size_mb']:.1f}MB ({info['samples']}样本)")
        
        # 显示音轨信息
        print("\n=== 音轨信息 ===")
        tracks = engine.list_tracks()
        for track in tracks:
            print(f"{track['track_id']}:")
            print(f"  时长: {track['duration']:.1f}秒")
            print(f"  采样率: {track['sample_rate']}Hz -> {track['engine_sample_rate']}Hz")
            print(f"  声道数: {track['channels']}")
            print(f"  文件路径: {track['file_path']}")
        
        # 测试播放
        print("\n=== 测试播放 ===")
        if tracks:
            first_track = tracks[0]['track_id']
            print(f"开始播放第一个音轨: {first_track}")
            engine.play(first_track, volume=0.2, loop=False)
            
            # 播放5秒
            time.sleep(5)
            engine.stop(first_track, fade_out=True)
            print("播放测试完成")
        
        # 性能统计
        print("\n=== 性能统计 ===")
        perf_stats = engine.get_performance_stats()
        print(f"CPU使用率: {perf_stats['cpu_usage']:.1f}%")
        print(f"峰值电平: {perf_stats['peak_level']:.3f}")
        print(f"活动音轨: {perf_stats['active_tracks']}")
        print(f"缓冲区欠载次数: {perf_stats['underrun_count']}")
        
        # 内存优化测试
        print("\n=== 内存优化测试 ===")
        optimization_result = engine.optimize_memory()
        print(f"清理缓存项: {optimization_result['cache_entries_cleared']}")
        print(f"清理缓冲池: {optimization_result['buffer_pool_cleared']}")
        print(f"释放内存: {optimization_result['memory_freed_mb']:.1f}MB")
        
    except Exception as e:
        print(f"演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("\n关闭音频引擎...")
        engine.shutdown()
        
        # 清理测试文件（可选）
        cleanup = input("\n是否删除测试文件? (y/N): ").lower().strip()
        if cleanup == 'y':
            for _, filepath in test_files:
                try:
                    os.remove(filepath)
                    print(f"已删除: {filepath}")
                except Exception as e:
                    print(f"删除失败 {filepath}: {e}")


def compare_loading_methods():
    """比较不同加载方法的性能"""
    print("\n=== 加载方法性能对比 ===")
    
    # 创建中等大小的测试文件（150MB）
    test_file = "test_comparison.wav"
    if not os.path.exists(test_file):
        create_test_large_file(test_file, duration_minutes=7.5, sample_rate=48000)
    
    file_size = os.path.getsize(test_file)
    print(f"测试文件: {test_file} ({file_size / (1024*1024):.1f}MB)")
    
    # 测试1: 小阈值（强制使用优化加载）
    print("\n1. 使用优化加载方法...")
    engine1 = AudioEngine()
    engine1.set_large_file_settings(threshold_mb=50)  # 50MB阈值
    engine1.start()
    
    start_time = time.time()
    success = engine1.load_track("test1", test_file)
    if success:
        # 等待加载完成
        while not engine1.is_track_loaded("test1"):
            time.sleep(0.1)
    optimized_time = time.time() - start_time
    
    memory1 = engine1.get_memory_usage()
    engine1.shutdown()
    
    # 测试2: 大阈值（使用传统加载）
    print("\n2. 使用传统加载方法...")
    engine2 = AudioEngine()
    engine2.set_large_file_settings(threshold_mb=500)  # 500MB阈值，强制传统方式
    engine2.start()
    
    start_time = time.time()
    success = engine2.load_track("test2", test_file)
    if success:
        # 等待加载完成
        while not engine2.is_track_loaded("test2"):
            time.sleep(0.1)
    traditional_time = time.time() - start_time
    
    memory2 = engine2.get_memory_usage()
    engine2.shutdown()
    
    # 结果对比
    print("\n=== 性能对比结果 ===")
    print(f"文件大小: {file_size / (1024*1024):.1f}MB")
    print(f"优化加载时间: {optimized_time:.1f}秒 ({(file_size / (1024*1024)) / optimized_time:.1f}MB/s)")
    print(f"传统加载时间: {traditional_time:.1f}秒 ({(file_size / (1024*1024)) / traditional_time:.1f}MB/s)")
    print(f"性能提升: {((traditional_time - optimized_time) / traditional_time * 100):.1f}%")
    
    # 清理
    try:
        os.remove(test_file)
        print(f"已删除测试文件: {test_file}")
    except Exception as e:
        print(f"删除失败: {e}")


if __name__ == "__main__":
    print("大文件加载优化演示程序")
    print("=" * 50)
    
    try:
        # 主演示
        demonstrate_large_file_loading()
        
        # 性能对比
        compare_loading_methods()
        
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n程序执行出错: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n演示完成!") 