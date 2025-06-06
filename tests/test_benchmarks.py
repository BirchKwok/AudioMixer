#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能基准测试
测试realtimemix库的性能指标和基准
"""

import pytest
import time
import psutil
import os
import statistics
import numpy as np
from realtimemix import AudioEngine
import tempfile
import soundfile as sf


def generate_test_audio(duration: float, sample_rate: int = 44100, channels: int = 1, 
                       frequency: float = 440.0) -> np.ndarray:
    """生成测试音频数据"""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio = np.sin(2 * np.pi * frequency * t) * 0.5
    
    if channels == 2:
        left = np.sin(2 * np.pi * frequency * t) * 0.5
        right = np.sin(2 * np.pi * frequency * 1.5 * t) * 0.5  # 稍微不同的频率
        audio = np.column_stack([left, right])
    else:
        audio = audio.reshape(-1, 1)
    
    return audio


class TestPerformanceBenchmarks:
    """性能基准测试"""
    
    def test_track_loading_speed(self, test_audio_files):
        """测试音轨加载速度"""
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2
        )
        engine.start()
        
        try:
            # 测试不同大小文件的加载时间
            test_cases = [
                ('small', test_audio_files['44100_1.0_2'], 1.0),
                ('medium', test_audio_files['44100_5.0_2'], 5.0),
                ('large', test_audio_files['44100_10.0_2'], 10.0),
                ('xlarge', test_audio_files['44100_30.0_2'], 30.0)
            ]
            
            results = {}
            
            for name, file_path, duration in test_cases:
                times = []
                
                # 多次测量取平均值
                for i in range(5):
                    track_id = f"{name}_{i}"
                    
                    start_time = time.time()
                    success = engine.load_track(track_id, file_path)
                    end_time = time.time()
                    
                    assert success
                    load_time = end_time - start_time
                    times.append(load_time)
                    
                    # 清理
                    engine.unload_track(track_id)
                
                avg_time = statistics.mean(times)
                std_time = statistics.stdev(times) if len(times) > 1 else 0
                
                results[name] = {
                    'duration': duration,
                    'avg_load_time': avg_time,
                    'std_load_time': std_time,
                    'load_ratio': avg_time / duration
                }
                
                print(f"{name}: {avg_time:.3f}±{std_time:.3f}s (ratio: {avg_time/duration:.3f})")
            
            # 验证性能要求
            for name, metrics in results.items():
                # 加载时间不应该超过文件时长的10%
                assert metrics['load_ratio'] < 0.1, f"{name} loading too slow"
                # 加载时间应该在合理范围内
                assert metrics['avg_load_time'] < 5.0, f"{name} loading timeout"
        
        finally:
            engine.shutdown()
    
    def test_playback_latency(self, test_audio_files):
        """测试播放延迟"""
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=256,  # 小缓冲区以降低延迟
            channels=2
        )
        engine.start()
        
        try:
            track_id = "latency_test"
            file_path = test_audio_files['44100_5.0_2']
            
            engine.load_track(track_id, file_path)
            
            # 测量播放启动延迟
            latencies = []
            
            for i in range(10):
                start_time = time.time()
                engine.play(track_id, volume=0.1)  # 低音量避免噪音
                
                # 等待播放状态确认
                while not engine.track_states[track_id]['playing']:
                    time.sleep(0.001)
                
                end_time = time.time()
                latency = (end_time - start_time) * 1000  # 转换为毫秒
                latencies.append(latency)
                
                engine.stop(track_id)
                time.sleep(0.1)
            
            avg_latency = statistics.mean(latencies)
            max_latency = max(latencies)
            
            print(f"Playback latency: {avg_latency:.2f}ms avg, {max_latency:.2f}ms max")
            
            # 验证延迟要求
            assert avg_latency < 50.0, "Average latency too high"
            assert max_latency < 100.0, "Maximum latency too high"
        
        finally:
            engine.shutdown()
    
    def test_cpu_usage_under_load(self, test_audio_files):
        """测试负载下的CPU使用率"""
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2
        )
        engine.start()
        
        try:
            # 加载多个音轨
            num_tracks = 8
            tracks = []
            
            for i in range(num_tracks):
                track_id = f"cpu_test_{i}"
                file_path = test_audio_files['44100_5.0_2']
                engine.load_track(track_id, file_path)
                tracks.append(track_id)
            
            # 监控CPU使用率
            process = psutil.Process(os.getpid())
            cpu_readings = []
            
            # 空载测量
            time.sleep(1.0)
            idle_cpu = process.cpu_percent()
            
            # 开始播放所有音轨
            for track_id in tracks:
                engine.play(track_id, volume=0.1)
            
            # 监控一段时间
            for i in range(20):
                time.sleep(0.5)
                cpu_usage = process.cpu_percent()
                cpu_readings.append(cpu_usage)
            
            # 停止播放
            for track_id in tracks:
                engine.stop(track_id)
            
            avg_cpu = statistics.mean(cpu_readings)
            max_cpu = max(cpu_readings)
            
            print(f"CPU usage: idle={idle_cpu:.1f}%, avg={avg_cpu:.1f}%, max={max_cpu:.1f}%")
            
            # 验证CPU使用率
            assert avg_cpu < 50.0, "Average CPU usage too high"
            assert max_cpu < 80.0, "Peak CPU usage too high"
        
        finally:
            engine.shutdown()
    
    def test_memory_usage_scaling(self, test_audio_files):
        """测试内存使用量随音轨数量的扩展性"""
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            enable_streaming=False  # 禁用流式播放以测试预加载内存使用
        )
        engine.start()
        
        try:
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            memory_measurements = []
            track_counts = [0, 5, 10, 15, 20]
            
            for target_count in track_counts:
                # 加载音轨到目标数量
                current_count = len(engine.track_states)
                for i in range(current_count, target_count):
                    track_id = f"memory_test_{i}"
                    file_path = test_audio_files['44100_3.0_2']
                    engine.load_track(track_id, file_path)
                
                # 测量内存使用
                time.sleep(0.5)  # 等待内存分配稳定
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_usage = current_memory - initial_memory
                
                memory_measurements.append((target_count, memory_usage))
                print(f"Tracks: {target_count}, Memory: {memory_usage:.1f}MB")
            
            # 分析内存扩展性
            if len(memory_measurements) >= 2:
                # 计算每个音轨的平均内存增长
                memory_per_track = []
                for i in range(1, len(memory_measurements)):
                    prev_tracks, prev_memory = memory_measurements[i-1]
                    curr_tracks, curr_memory = memory_measurements[i]
                    
                    if curr_tracks > prev_tracks:
                        tracks_added = curr_tracks - prev_tracks
                        memory_added = curr_memory - prev_memory
                        memory_per_track.append(memory_added / tracks_added)
                
                if memory_per_track:
                    avg_memory_per_track = statistics.mean(memory_per_track)
                    print(f"Average memory per track: {avg_memory_per_track:.2f}MB")
                    
                    # 验证内存使用合理性（每个音轨不应超过50MB）
                    assert avg_memory_per_track < 50.0, "Memory usage per track too high"
        
        finally:
            engine.shutdown()
    
    def test_volume_change_performance(self, test_audio_files):
        """测试音量变化的性能"""
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2
        )
        engine.start()
        
        try:
            track_id = "volume_perf_test"
            file_path = test_audio_files['44100_5.0_2']
            
            engine.load_track(track_id, file_path)
            engine.play(track_id, volume=0.5)
            
            # 测试大量音量变化的性能
            num_changes = 1000
            start_time = time.time()
            
            for i in range(num_changes):
                volume = 0.1 + 0.8 * (i % 100) / 100  # 0.1-0.9之间变化
                engine.set_volume(track_id, volume)
            
            end_time = time.time()
            total_time = end_time - start_time
            
            changes_per_second = num_changes / total_time
            avg_change_time = total_time / num_changes * 1000  # 毫秒
            
            print(f"Volume changes: {changes_per_second:.0f}/s, {avg_change_time:.3f}ms/change")
            
            # 验证性能要求
            assert changes_per_second > 1000, "Volume change rate too low"
            assert avg_change_time < 1.0, "Volume change time too high"
            
            engine.stop(track_id)
        
        finally:
            engine.shutdown()
    
    def test_matchering_performance(self, test_audio_files):
        """测试matchering性能"""
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2
        )
        engine.start()
        
        try:
            # 加载参考音轨
            main_track = "main"
            main_file = test_audio_files['44100_10.0_2']
            engine.load_track(main_track, main_file)
            
            # 测试不同大小文件的matchering时间
            test_files = [
                ('short', test_audio_files['44100_1.0_1'], 1.0),
                ('medium', test_audio_files['44100_3.0_1'], 3.0),
                ('long', test_audio_files['44100_5.0_1'], 5.0)
            ]
            
            for name, file_path, duration in test_files:
                times = []
                
                # 多次测量
                for i in range(3):  # 减少次数因为matchering比较耗时
                    track_id = f"matchering_{name}_{i}"
                    
                    start_time = time.time()
                    success = engine.load_track_with_matchering(
                        track_id=track_id,
                        file_path=file_path,
                        reference_track_id=main_track,
                        reference_start_sec=1.0,
                        reference_duration_sec=3.0
                    )
                    end_time = time.time()
                    
                    if success:
                        processing_time = end_time - start_time
                        times.append(processing_time)
                        engine.unload_track(track_id)
                
                if times:
                    avg_time = statistics.mean(times)
                    processing_ratio = avg_time / duration
                    
                    print(f"Matchering {name}: {avg_time:.2f}s (ratio: {processing_ratio:.2f}x)")
                    
                    # 验证性能要求（处理时间不应超过音频时长的10倍）
                    assert processing_ratio < 10.0, f"Matchering too slow for {name}"
        
        finally:
            engine.shutdown()


class TestScalabilityBenchmarks:
    """可扩展性基准测试"""
    
    def test_max_simultaneous_tracks(self, test_audio_files):
        """测试最大同时播放音轨数"""
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2
        )
        engine.start()
        
        try:
            max_tracks = 0
            track_ids = []
            
            # 逐步增加音轨数量直到性能下降
            for i in range(50):  # 最多测试50个音轨
                track_id = f"scale_test_{i}"
                file_path = test_audio_files['44100_2.0_2']
                
                success = engine.load_track(track_id, file_path)
                if not success:
                    break
                
                track_ids.append(track_id)
                engine.play(track_id, volume=0.05)  # 很低的音量
                
                # 检查性能指标
                time.sleep(0.1)
                stats = engine.get_performance_stats()
                
                if (stats['underrun_count'] > 5 or 
                    stats['cpu_usage'] > 90):
                    # 性能下降，停止测试
                    engine.stop(track_id)
                    break
                
                max_tracks = i + 1
            
            print(f"Maximum simultaneous tracks: {max_tracks}")
            
            # 清理
            for track_id in track_ids:
                engine.stop(track_id)
                engine.unload_track(track_id)
            
            # 验证最低要求
            assert max_tracks >= 8, "Insufficient track scalability"
        
        finally:
            engine.shutdown()
    
    def test_streaming_vs_preload_performance(self, test_audio_files):
        """比较流式播放与预加载的性能"""
        
        # 测试预加载模式
        engine_preload = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            enable_streaming=False
        )
        engine_preload.start()
        
        # 测试流式播放模式
        engine_streaming = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            enable_streaming=True,
            streaming_threshold_mb=1  # 1MB阈值
        )
        engine_streaming.start()
        
        try:
            file_path = test_audio_files['44100_10.0_2']  # 长文件
            
            # 测试预加载性能
            start_time = time.time()
            engine_preload.load_track("preload_test", file_path)
            preload_time = time.time() - start_time
            
            # 测试流式播放性能
            start_time = time.time()
            engine_streaming.load_track("streaming_test", file_path)
            streaming_time = time.time() - start_time
            
            print(f"Loading time - Preload: {preload_time:.3f}s, Streaming: {streaming_time:.3f}s")
            
            # 流式播放的加载时间应该更短
            assert streaming_time < preload_time, "Streaming not faster for large files"
            
            # 测试播放启动性能
            engines = [
                ("preload", engine_preload, "preload_test"),
                ("streaming", engine_streaming, "streaming_test")
            ]
            
            for name, engine, track_id in engines:
                start_time = time.time()
                engine.play(track_id, volume=0.1)
                
                while not engine.track_states[track_id]['playing']:
                    time.sleep(0.001)
                
                startup_time = time.time() - start_time
                print(f"Playback startup - {name}: {startup_time*1000:.2f}ms")
                
                engine.stop(track_id)
        
        finally:
            engine_preload.shutdown()
            engine_streaming.shutdown()
    
    def test_long_term_stability(self, test_audio_files):
        """测试长期稳定性"""
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2
        )
        engine.start()
        
        try:
            track_id = "stability_test"
            file_path = test_audio_files['44100_5.0_2']
            
            engine.load_track(track_id, file_path)
            
            # 运行多次播放/停止循环
            num_cycles = 50  # 减少循环次数以加快测试
            underrun_counts = []
            
            for i in range(num_cycles):
                engine.play(track_id, volume=0.1)
                time.sleep(0.5)  # 播放0.5秒
                
                stats = engine.get_performance_stats()
                underrun_counts.append(stats['underrun_count'])
                
                engine.stop(track_id)
                time.sleep(0.1)  # 短暂停顿
                
                # 检查性能稳定性
                if i > 10:  # 跳过初始几次测量
                    recent_underruns = underrun_counts[-5:]
                    if max(recent_underruns) - min(recent_underruns) > 10:
                        print(f"Instability detected at cycle {i}")
                        break
            
            # 验证稳定性
            final_stats = engine.get_performance_stats()
            print(f"Final underrun count: {final_stats['underrun_count']}")
            
            # 欠载次数不应该过多
            assert final_stats['underrun_count'] < num_cycles * 0.1, "Too many underruns"
        
        finally:
            engine.shutdown()


class TestResourceEfficiency:
    """资源效率测试"""
    
    def test_file_handle_management(self, test_audio_files):
        """测试文件句柄管理"""
        import resource
        
        # 获取初始文件句柄数
        initial_fds = len(os.listdir('/proc/self/fd')) if os.path.exists('/proc/self/fd') else 0
        
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2
        )
        engine.start()
        
        try:
            # 加载和卸载大量文件
            for i in range(20):
                track_id = f"fd_test_{i}"
                file_path = test_audio_files['44100_2.0_2']
                
                engine.load_track(track_id, file_path)
                engine.unload_track(track_id)
            
            # 检查文件句柄是否泄漏
            if os.path.exists('/proc/self/fd'):
                final_fds = len(os.listdir('/proc/self/fd'))
                fd_increase = final_fds - initial_fds
                
                print(f"File descriptor change: {fd_increase}")
                assert fd_increase < 10, "Possible file descriptor leak"
        
        finally:
            engine.shutdown()
    
    def test_thread_management(self, test_audio_files):
        """测试线程管理"""
        import threading
        
        initial_thread_count = threading.active_count()
        
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2
        )
        
        # 启动引擎
        engine.start()
        startup_thread_count = threading.active_count()
        
        try:
            # 执行一些操作
            track_id = "thread_test"
            file_path = test_audio_files['44100_3.0_2']
            
            engine.load_track(track_id, file_path)
            engine.play(track_id, volume=0.1)
            time.sleep(1.0)
            engine.stop(track_id)
            engine.unload_track(track_id)
            
            active_thread_count = threading.active_count()
            
        finally:
            engine.shutdown()
            
        final_thread_count = threading.active_count()
        
        print(f"Threads: initial={initial_thread_count}, startup={startup_thread_count}, "
              f"active={active_thread_count}, final={final_thread_count}")
        
        # 验证线程清理
        assert final_thread_count <= initial_thread_count + 1, "Thread leak detected"


if __name__ == "__main__":
    # 可以直接运行进行快速性能测试
    print("Running basic performance tests...")
    pytest.main([__file__, "-v", "-s"]) 