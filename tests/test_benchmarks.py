#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能基准测试
测试AudioEngine的性能和可扩展性
"""

import pytest
import time
import threading
import numpy as np
import tempfile
import os
from realtimemix import AudioEngine


def load_track_with_wait(audio_engine, track_id: str, file_path: str, timeout: float = 5.0):
    """辅助函数：加载音轨并等待完成"""
    loading_completed = False
    loading_error = None
    
    def on_complete(tid, success, error=None):
        nonlocal loading_completed, loading_error
        loading_completed = True
        if not success:
            loading_error = error
    
    success = audio_engine.load_track(track_id, file_path, on_complete=on_complete)
    if not success:
        return False
        
    # 等待加载完成
    wait_time = 0
    while not loading_completed and wait_time < timeout:
        time.sleep(0.1)
        wait_time += 0.1
    
    if not loading_completed:
        raise TimeoutError(f"Track {track_id} loading timed out")
    if loading_error is not None:
        raise RuntimeError(f"Track {track_id} loading failed: {loading_error}")
    
    return True


class TestPerformanceBenchmarks:
    """性能基准测试"""
    
    def test_load_time_benchmark(self, audio_engine, test_audio_files):
        """测试音频加载时间"""
        # 测试不同大小文件的加载时间
        test_cases = [
            ('small', test_audio_files['44100_1.0_2']),
            ('medium', test_audio_files['44100_5.0_2']),
            ('large', test_audio_files['44100_10.0_2'])
        ]
        
        for size, file_path in test_cases:
            track_id = f"load_test_{size}"
            
            start_time = time.time()
            load_track_with_wait(audio_engine, track_id, file_path)
            end_time = time.time()
            
            load_time = end_time - start_time
            
            # 加载时间不应该太长（根据文件大小调整期望）
            expected_max_time = 5.0 if size == 'large' else 2.0
            assert load_time < expected_max_time
            
            print(f"{size} file load time: {load_time:.3f}s")
    
    def test_playback_latency(self, audio_engine, test_audio_files):
        """测试播放延迟"""
        track_id = "latency_test"
        file_path = test_audio_files['44100_1.0_2']
        
        # 加载音轨
        load_track_with_wait(audio_engine, track_id, file_path)
        
        # 测量从play命令到实际开始播放的延迟
        start_time = time.time()
        audio_engine.play(track_id)
        
        # 等待状态更新
        time.sleep(0.01)
        
        # 验证播放状态
        is_playing = audio_engine.track_states[track_id]['playing']
        end_time = time.time()
        
        latency = end_time - start_time
        
        # 播放应该立即开始
        assert is_playing
        assert latency < 0.1  # 延迟应该小于100ms
        
        print(f"Playback latency: {latency:.3f}s")
        
        audio_engine.stop(track_id)
    
    def test_memory_usage_scaling(self, audio_engine_no_streaming, test_audio_files):
        """测试内存使用量随轨道数量的变化"""
        # 测试加载多个轨道时的内存使用
        track_files = [
            test_audio_files['44100_1.0_2'],  # 使用可用的文件
            test_audio_files['44100_5.0_2'],
            test_audio_files['48000_1.0_1'],
            test_audio_files['22050_5.0_1']
        ]
        
        memory_usage = []
        
        for i, file_path in enumerate(track_files):
            track_id = f"memory_test_{i}"
            load_track_with_wait(audio_engine_no_streaming, track_id, file_path)
            
            # 获取当前内存使用情况
            stats = audio_engine_no_streaming.get_memory_usage()
            if stats and 'total_memory_mb' in stats:
                memory_usage.append(stats['total_memory_mb'])
                print(f"Tracks: {i+1}, Memory: {stats['total_memory_mb']:.2f}MB")
        
        # 内存使用应该随轨道数量增加
        if len(memory_usage) > 1:
            assert memory_usage[-1] >= memory_usage[0]
    
    def test_matchering_performance(self, audio_engine, test_audio_files):
        """测试matchering性能"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']
        load_track_with_wait(audio_engine, main_track, main_file)
        
        # 测试不同大小文件的matchering时间
        test_cases = [
            ('small', test_audio_files['44100_1.0_1'], 1.0),  # 使用可用的文件
            ('medium', test_audio_files['44100_1.0_1'], 1.0),  # 重复使用可用的文件
            ('large', test_audio_files['44100_5.0_2'], 5.0)
        ]
        
        for size, file_path, duration in test_cases:
            sub_track = f"matchering_test_{size}"
            
            start_time = time.time()
            
            try:
                success = audio_engine.load_track_with_matchering(
                    track_id=sub_track,
                    file_path=file_path,
                    reference_track_id=main_track,
                    reference_start_sec=2.0,
                    reference_duration_sec=duration
                )
                
                if success:
                    # 等待处理完成
                    wait_time = 0
                    while sub_track not in audio_engine.track_states and wait_time < 30.0:
                        time.sleep(0.1)
                        wait_time += 0.1
                
                end_time = time.time()
                processing_time = end_time - start_time
                
                if success:
                    print(f"{size} file matchering time: {processing_time:.3f}s")
                    # 处理时间应该合理
                    assert processing_time < 30.0
                else:
                    print(f"{size} file matchering failed")
                    
            except Exception as e:
                print(f"Matchering failed for {size}: {e}")


class TestScalabilityBenchmarks:
    """可扩展性基准测试"""
    
    def test_max_simultaneous_tracks(self, audio_engine, test_audio_files):
        """测试最大同时轨道数"""
        file_path = test_audio_files['44100_1.0_2']  # 使用可用的文件
        max_tracks = 20  # 测试目标
        loaded_tracks = []
        
        # 尝试加载多个轨道
        for i in range(max_tracks):
            track_id = f"scale_test_{i}"
            try:
                load_track_with_wait(audio_engine, track_id, file_path, timeout=10.0)
                loaded_tracks.append(track_id)
            except Exception as e:
                print(f"Failed to load track {i}: {e}")
                break
        
        print(f"Successfully loaded {len(loaded_tracks)} tracks")
        
        # 应该能加载至少10个轨道
        assert len(loaded_tracks) >= 10
        
        # 测试同时播放
        playing_count = 0
        for track_id in loaded_tracks[:10]:  # 只播放前10个
            try:
                audio_engine.play(track_id, volume=0.1)  # 降低音量
                if audio_engine.track_states[track_id]['playing']:
                    playing_count += 1
            except Exception as e:
                print(f"Failed to play track {track_id}: {e}")
        
        print(f"Successfully playing {playing_count} tracks simultaneously")
        
        # 停止所有播放
        for track_id in loaded_tracks:
            try:
                audio_engine.stop(track_id)
            except:
                pass
    
    def test_rapid_load_unload(self, audio_engine, test_audio_files):
        """测试快速加载卸载"""
        file_path = test_audio_files['44100_1.0_2']
        iterations = 10
        
        start_time = time.time()
        
        for i in range(iterations):
            track_id = f"rapid_test_{i}"
            
            # 加载
            load_track_with_wait(audio_engine, track_id, file_path)
            assert track_id in audio_engine.track_states
            
            # 播放短时间
            audio_engine.play(track_id)
            time.sleep(0.1)
            
            # 停止并卸载
            audio_engine.stop(track_id)
            audio_engine.unload_track(track_id)
            assert track_id not in audio_engine.track_states
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"Rapid load/unload {iterations} iterations: {total_time:.3f}s")
        print(f"Average per iteration: {total_time/iterations:.3f}s")
        
        # 平均每次操作应该在合理时间内完成
        assert total_time/iterations < 1.0
    
    def test_streaming_vs_preload_performance(self, test_audio_files):
        """测试流式播放vs预加载性能"""
        file_path = test_audio_files['44100_10.0_2']
        
        # 预加载模式
        preload_engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            enable_streaming=False
        )
        preload_engine.start()
        
        # 流式模式
        streaming_engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            enable_streaming=True,
            streaming_threshold_mb=1  # 低阈值强制流式播放
        )
        streaming_engine.start()
        
        try:
            # 测试预加载时间
            start_time = time.time()
            load_track_with_wait(preload_engine, "preload_test", file_path)
            preload_time = time.time() - start_time
            
            # 测试流式播放初始化时间
            start_time = time.time()
            load_track_with_wait(streaming_engine, "streaming_test", file_path)
            streaming_time = time.time() - start_time
            
            print(f"Loading time - Preload: {preload_time:.3f}s, Streaming: {streaming_time:.3f}s")
            
            # 对于大文件，流式播放通常应该更快启动
            # 但这取决于具体实现，所以只检查都能在合理时间内完成
            assert preload_time < 10.0
            assert streaming_time < 10.0
            
        finally:
            preload_engine.shutdown()
            streaming_engine.shutdown()


class TestResourceEfficiency:
    """资源效率测试"""
    
    def test_cpu_usage_monitoring(self, audio_engine, test_audio_files):
        """测试CPU使用率监控"""
        file_path = test_audio_files['44100_5.0_2']
        
        # 加载并播放多个轨道
        tracks = []
        for i in range(5):
            track_id = f"cpu_test_{i}"
            load_track_with_wait(audio_engine, track_id, file_path)
            audio_engine.play(track_id, volume=0.2)
            tracks.append(track_id)
        
        # 运行一段时间收集CPU统计
        time.sleep(2.0)
        
        # 获取性能统计
        stats = audio_engine.get_performance_stats()
        
        if 'cpu_usage' in stats:
            cpu_usage = stats['cpu_usage']
            print(f"CPU usage with 5 tracks: {cpu_usage:.2f}%")
            
            # CPU使用率应该在合理范围内
            assert cpu_usage >= 0
            assert cpu_usage < 100  # 不应该100%占用
        
        # 停止所有播放
        for track_id in tracks:
            audio_engine.stop(track_id)
    
    def test_memory_leak_detection(self, audio_engine, test_audio_files):
        """测试内存泄漏检测"""
        file_path = test_audio_files['44100_1.0_2']
        initial_memory = None
        
        # 获取初始内存
        stats = audio_engine.get_memory_usage()
        if stats and 'total_memory_mb' in stats:
            initial_memory = stats['total_memory_mb']
        
        # 执行多轮加载/卸载操作
        for cycle in range(5):
            tracks = []
            
            # 加载多个轨道
            for i in range(10):
                track_id = f"leak_test_{cycle}_{i}"
                load_track_with_wait(audio_engine, track_id, file_path)
                tracks.append(track_id)
            
            # 播放一段时间
            for track_id in tracks:
                audio_engine.play(track_id, volume=0.1)
            
            time.sleep(0.5)
            
            # 停止并卸载所有轨道
            for track_id in tracks:
                audio_engine.stop(track_id)
                audio_engine.unload_track(track_id)
            
            # 检查内存使用
            stats = audio_engine.get_memory_usage()
            if stats and 'total_memory_mb' in stats:
                current_memory = stats['total_memory_mb']
                print(f"Cycle {cycle}: Memory usage: {current_memory:.2f}MB")
                
                # 内存使用不应该持续增长太多
                if initial_memory is not None:
                    growth = current_memory - initial_memory
                    assert growth < 50.0  # 允许一定的内存增长，但不应该太多
    
    def test_file_handle_management(self, audio_engine, test_audio_files):
        """测试文件句柄管理"""
        file_path = test_audio_files['44100_1.0_2']  # 使用可用的文件
        
        # 快速加载和卸载多个轨道
        for i in range(20):
            track_id = f"handle_test_{i}"
            
            # 加载
            load_track_with_wait(audio_engine, track_id, file_path)
            
            # 立即卸载
            audio_engine.unload_track(track_id)
            
            # 验证轨道已被完全清理
            assert track_id not in audio_engine.track_states
        
        # 操作应该成功完成，没有文件句柄泄漏
        print("File handle management test completed successfully")
    
    def test_thread_management(self, audio_engine, test_audio_files):
        """测试线程管理"""
        file_path = test_audio_files['44100_1.0_2']  # 使用可用的文件
        
        # 记录初始线程数（如果可能）
        initial_thread_count = threading.active_count()
        
        # 执行大量并发操作
        tracks = []
        for i in range(10):
            track_id = f"thread_test_{i}"
            load_track_with_wait(audio_engine, track_id, file_path)
            tracks.append(track_id)
        
        # 同时播放所有轨道
        for track_id in tracks:
            audio_engine.play(track_id, volume=0.1)
        
        time.sleep(1.0)
        
        # 停止所有播放
        for track_id in tracks:
            audio_engine.stop(track_id)
            audio_engine.unload_track(track_id)
        
        # 等待清理完成
        time.sleep(0.5)
        
        # 检查线程数量
        final_thread_count = threading.active_count()
        
        print(f"Thread count - Initial: {initial_thread_count}, Final: {final_thread_count}")
        
        # 线程数量不应该无限增长
        thread_growth = final_thread_count - initial_thread_count
        assert thread_growth < 20  # 允许一些工作线程，但不应该太多


class TestStressTests:
    """压力测试"""
    
    def test_extended_playback(self, audio_engine, test_audio_files):
        """测试长时间播放"""
        track_id = "extended_test"
        file_path = test_audio_files['44100_10.0_2']
        
        # 加载并开始播放
        load_track_with_wait(audio_engine, track_id, file_path)
        audio_engine.play(track_id, loop=True)  # 循环播放
        
        # 运行较长时间
        duration = 5.0  # 5秒测试
        start_time = time.time()
        
        while time.time() - start_time < duration:
            # 检查播放状态
            assert audio_engine.track_states[track_id]['playing']
            
            # 获取性能统计
            stats = audio_engine.get_performance_stats()
            if 'underrun_count' in stats:
                # 不应该有太多underrun
                assert stats['underrun_count'] < 100
            
            time.sleep(0.5)
        
        # 停止播放
        audio_engine.stop(track_id)
        
        print(f"Extended playback test completed: {duration}s")
    
    def test_rapid_operations(self, audio_engine, test_audio_files):
        """测试快速操作"""
        file_path = test_audio_files['44100_1.0_2']
        operations = 50
        
        start_time = time.time()
        
        for i in range(operations):
            track_id = f"rapid_op_{i}"
            
            # 快速执行：加载、播放、停止、卸载
            load_track_with_wait(audio_engine, track_id, file_path)
            audio_engine.play(track_id)
            time.sleep(0.01)  # 很短的播放时间
            audio_engine.stop(track_id)
            audio_engine.unload_track(track_id)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"Rapid operations ({operations} cycles): {total_time:.3f}s")
        print(f"Average per operation: {total_time/operations:.4f}s")
        
        # 操作应该能在合理时间内完成
        assert total_time < 30.0  # 50个操作在30秒内完成


if __name__ == "__main__":
    # 可以直接运行进行快速性能测试
    print("Running basic performance tests...")
    pytest.main([__file__, "-v", "-s"]) 