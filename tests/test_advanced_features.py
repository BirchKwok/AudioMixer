#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级功能测试
测试复杂的音频处理场景和综合功能
"""

import pytest
import time
import numpy as np
import threading
from realtimemix import AudioEngine
import numpy as np


def wait_for_playback(duration: float, tolerance: float = 0.1):
    """等待播放完成的辅助函数"""
    time.sleep(duration + tolerance)


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


class TestSeamlessMixing:
    """无缝混音测试"""
    
    def test_seamless_track_switching(self, audio_engine, test_audio_files):
        """测试无缝音轨切换"""
        # 加载两个音轨
        track1 = "track1"
        track2 = "track2"
        file1 = test_audio_files['44100_5.0_2']
        file2 = test_audio_files['44100_3.0_2']
        
        audio_engine.load_track(track1, file1)
        audio_engine.load_track(track2, file2)
        
        # 开始播放第一个音轨
        audio_engine.play(track1, volume=0.8)
        time.sleep(1.0)
        
        # 准备第二个音轨但音量为0
        audio_engine.play(track2, volume=0.0)
        time.sleep(0.1)
        
        # 瞬时切换
        audio_engine.set_volume(track1, 0.0)
        audio_engine.set_volume(track2, 0.8)
        
        # 播放一段时间
        time.sleep(1.0)
        
        # 停止播放
        audio_engine.stop(track1)
        audio_engine.stop(track2)
        
        assert not audio_engine.track_states[track1]['playing']
        assert not audio_engine.track_states[track2]['playing']
    
    def test_crossfade_simulation(self, audio_engine, test_audio_files):
        """测试交叉淡化模拟"""
        track1 = "main"
        track2 = "sub"
        file1 = test_audio_files['44100_5.0_2']
        file2 = test_audio_files['44100_3.0_2']
        
        audio_engine.load_track(track1, file1)
        audio_engine.load_track(track2, file2)
        
        # 开始播放主音轨
        audio_engine.play(track1, volume=1.0)
        audio_engine.play(track2, volume=0.0)
        
        time.sleep(1.0)
        
        # 模拟交叉淡化（手动控制音量变化）
        crossfade_duration = 1.0
        steps = 20
        step_duration = crossfade_duration / steps
        
        for i in range(steps + 1):
            progress = i / steps
            volume1 = 1.0 - progress
            volume2 = progress
            
            audio_engine.set_volume(track1, volume1)
            audio_engine.set_volume(track2, volume2)
            time.sleep(step_duration)
        
        # 验证最终状态
        assert audio_engine.track_states[track1]['volume'] == 0.0
        assert audio_engine.track_states[track2]['volume'] == 1.0
        
        time.sleep(0.5)
        audio_engine.stop(track1)
        audio_engine.stop(track2)
    
    def test_multi_track_mixing(self, audio_engine, test_audio_files):
        """测试多轨道混音"""
        tracks = {
            'main': (test_audio_files['44100_5.0_2'], 0.6),
            'harmony': (test_audio_files['44100_5.0_1'], 0.3),
            'bass': (test_audio_files['22050_5.0_1'], 0.4),
            'drums': (test_audio_files['48000_5.0_2'], 0.2)
        }
        
        # 加载所有音轨
        for track_id, (file_path, volume) in tracks.items():
            audio_engine.load_track(track_id, file_path)
        
        # 同时播放所有音轨
        for track_id, (file_path, volume) in tracks.items():
            audio_engine.play(track_id, volume=volume)
            assert audio_engine.track_states[track_id]['playing']
        
        # 播放一段时间
        time.sleep(2.0)
        
        # 动态调整音量
        audio_engine.set_volume('main', 0.8)
        audio_engine.set_volume('harmony', 0.1)
        time.sleep(1.0)
        
        # 停止部分音轨
        audio_engine.stop('bass')
        audio_engine.stop('drums')
        time.sleep(1.0)
        
        # 停止剩余音轨
        audio_engine.stop('main')
        audio_engine.stop('harmony')
        
        # 验证所有音轨都已停止
        for track_id in tracks.keys():
            assert not audio_engine.track_states[track_id]['playing']


class TestSynchronizedPlayback:
    """同步播放测试"""
    
    def test_synchronized_start(self, audio_engine, test_audio_files):
        """测试同步开始播放"""
        tracks = ['track1', 'track2', 'track3']
        files = [
            test_audio_files['44100_3.0_2'],
            test_audio_files['44100_3.0_1'],
            test_audio_files['48000_3.0_2']
        ]
        
        # 加载所有音轨
        for track_id, file_path in zip(tracks, files):
            audio_engine.load_track(track_id, file_path)
        
        # 记录开始时间
        start_time = time.time()
        
        # 快速连续启动所有音轨
        for track_id in tracks:
            audio_engine.play(track_id, volume=0.3)
        
        end_time = time.time()
        startup_time = end_time - start_time
        
        # 验证所有音轨都在播放
        for track_id in tracks:
            assert audio_engine.track_states[track_id]['playing']
        
        # 启动时间应该很短（小于100ms）
        assert startup_time < 0.1
        
        time.sleep(1.0)
        
        # 同步停止
        for track_id in tracks:
            audio_engine.stop(track_id)
    
    def test_timed_playback_sequence(self, audio_engine, test_audio_files):
        """测试定时播放序列"""
        tracks = {
            'intro': test_audio_files['44100_2.0_2'],
            'main': test_audio_files['44100_5.0_2'],
            'outro': test_audio_files['44100_1.0_2']
        }
        
        # 加载所有音轨
        for track_id, file_path in tracks.items():
            audio_engine.load_track(track_id, file_path)
        
        # 播放序列
        # 1. 播放intro
        audio_engine.play('intro', volume=0.8)
        time.sleep(1.5)  # 播放1.5秒
        
        # 2. 在intro还在播放时启动main
        audio_engine.play('main', volume=0.6)
        time.sleep(0.5)  # intro剩余0.5秒
        
        # 3. 停止intro
        audio_engine.stop('intro')
        time.sleep(2.0)  # main播放2秒
        
        # 4. 启动outro与main重叠
        audio_engine.play('outro', volume=0.7)
        time.sleep(0.5)
        
        # 5. 停止main
        audio_engine.stop('main')
        time.sleep(0.5)  # outro剩余时间
        
        # 6. 停止outro
        audio_engine.stop('outro')
        
        # 验证最终状态
        for track_id in tracks.keys():
            assert not audio_engine.track_states[track_id]['playing']


class TestResourceManagement:
    """资源管理测试"""
    
    def test_memory_usage_with_many_tracks(self, audio_engine_no_streaming, test_audio_files):
        """测试大量音轨的内存使用"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 加载大量音轨
        num_tracks = 20
        track_files = [
            test_audio_files['44100_2.0_2'],
            test_audio_files['48000_1.0_1'],
            test_audio_files['22050_3.0_2']
        ]
        
        loaded_tracks = []
        for i in range(num_tracks):
            track_id = f"track_{i}"
            file_path = track_files[i % len(track_files)]
            
            success = audio_engine_no_streaming.load_track(track_id, file_path)
            assert success
            loaded_tracks.append(track_id)
        
        # 检查内存使用
        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = peak_memory - initial_memory
        
        print(f"Memory usage: {initial_memory:.1f}MB -> {peak_memory:.1f}MB (+{memory_increase:.1f}MB)")
        
        # 内存增长应该在合理范围内
        assert memory_increase < 500  # 小于500MB
        
        # 卸载所有音轨
        for track_id in loaded_tracks:
            audio_engine_no_streaming.unload_track(track_id)
        
        # 检查内存是否释放
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_released = peak_memory - final_memory
        
        print(f"Memory after cleanup: {final_memory:.1f}MB (released: {memory_released:.1f}MB)")
        
        # 应该释放了大部分内存
        assert memory_released > memory_increase * 0.7
    
    def test_concurrent_loading_and_unloading(self, audio_engine, test_audio_files):
        """测试并发加载和卸载"""
        def load_unload_worker(worker_id, iterations):
            """工作线程函数"""
            for i in range(iterations):
                track_id = f"worker_{worker_id}_track_{i}"
                file_path = test_audio_files['44100_2.0_2']
                
                # 加载
                success = audio_engine.load_track(track_id, file_path)
                if success:
                    time.sleep(0.1)  # 短暂等待
                    # 卸载
                    audio_engine.unload_track(track_id)
                
                time.sleep(0.05)  # 避免过度竞争
        
        # 启动多个工作线程
        num_workers = 4
        iterations_per_worker = 5
        threads = []
        
        for worker_id in range(num_workers):
            thread = threading.Thread(
                target=load_unload_worker,
                args=(worker_id, iterations_per_worker)
            )
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 验证没有留下未清理的音轨
        remaining_tracks = len(audio_engine.track_states)
        assert remaining_tracks == 0


class TestPerformanceStress:
    """性能压力测试"""
    
    def test_rapid_volume_changes(self, audio_engine, test_audio_files):
        """测试快速音量变化"""
        track_id = "stress_test"
        file_path = test_audio_files['44100_5.0_2']
        
        audio_engine.load_track(track_id, file_path)
        audio_engine.play(track_id, volume=0.5)
        
        # 快速变化音量
        start_time = time.time()
        num_changes = 100
        
        for i in range(num_changes):
            volume = 0.1 + 0.8 * (i % 10) / 10  # 0.1 到 0.9 之间变化
            audio_engine.set_volume(track_id, volume)
            time.sleep(0.01)  # 10ms间隔
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # 验证性能
        assert total_time < 2.0  # 应该在2秒内完成
        assert audio_engine.track_states[track_id]['playing']
        
        audio_engine.stop(track_id)
    
    def test_high_frequency_play_stop(self, audio_engine, test_audio_files):
        """测试高频播放/停止"""
        track_id = "freq_test"
        file_path = test_audio_files['44100_2.0_2']
        
        audio_engine.load_track(track_id, file_path)
        
        # 快速播放/停止循环
        num_cycles = 20
        start_time = time.time()
        
        for i in range(num_cycles):
            audio_engine.play(track_id, volume=0.3)
            time.sleep(0.05)  # 播放50ms
            audio_engine.stop(track_id)
            time.sleep(0.05)  # 停止50ms
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # 验证性能和状态
        assert total_time < 5.0
        assert not audio_engine.track_states[track_id]['playing']
    
    def test_performance_under_load(self, audio_engine, test_audio_files):
        """测试负载下的性能"""
        # 加载多个音轨
        tracks = {}
        for i in range(8):
            track_id = f"load_test_{i}"
            file_path = test_audio_files['44100_3.0_2']
            audio_engine.load_track(track_id, file_path)
            tracks[track_id] = file_path
        
        # 同时播放所有音轨
        for track_id in tracks.keys():
            audio_engine.play(track_id, volume=0.1)  # 低音量避免过载
        
        # 监控性能
        start_time = time.time()
        num_checks = 50
        
        for i in range(num_checks):
            stats = audio_engine.get_performance_stats()
            
            # 验证性能指标
            assert stats['cpu_usage'] < 80  # CPU使用率不应过高
            assert stats['underrun_count'] < 10  # 欠载次数应该很少
            
            time.sleep(0.1)
        
        end_time = time.time()
        monitoring_time = end_time - start_time
        
        # 停止所有播放
        for track_id in tracks.keys():
            audio_engine.stop(track_id)
        
        # 验证监控效率
        assert monitoring_time < 10.0  # 监控本身不应该太耗时


class TestComplexScenarios:
    """复杂场景测试"""
    
    def test_live_mixing_simulation(self, audio_engine, test_audio_files):
        """测试现场混音模拟"""
        # 设置多个音轨模拟现场混音
        tracks = {
            'vocal': test_audio_files['44100_5.0_1'],
            'guitar': test_audio_files['44100_5.0_2'],
            'bass': test_audio_files['22050_5.0_1'],
            'drums': test_audio_files['48000_5.0_2']
        }
        
        # 加载所有音轨
        for track_id, file_path in tracks.items():
            audio_engine.load_track(track_id, file_path)
        
        # 模拟现场混音场景
        # 1. 开始只有鼓点
        audio_engine.play('drums', volume=0.4)
        time.sleep(1.0)
        
        # 2. 加入贝斯
        audio_engine.play('bass', volume=0.3)
        time.sleep(1.0)
        
        # 3. 加入吉他
        audio_engine.play('guitar', volume=0.5)
        time.sleep(1.0)
        
        # 4. 加入人声
        audio_engine.play('vocal', volume=0.7)
        time.sleep(1.0)
        
        # 5. 动态调整混音
        audio_engine.set_volume('drums', 0.2)  # 降低鼓点
        audio_engine.set_volume('vocal', 0.9)  # 突出人声
        time.sleep(1.0)
        
        # 6. 逐渐减少乐器
        audio_engine.stop('guitar')
        time.sleep(0.5)
        audio_engine.stop('bass')
        time.sleep(0.5)
        audio_engine.set_volume('vocal', 0.4)
        audio_engine.set_volume('drums', 0.6)
        time.sleep(1.0)
        
        # 7. 结束
        audio_engine.stop('vocal')
        audio_engine.stop('drums')
        
        # 验证所有音轨都已停止
        for track_id in tracks.keys():
            assert not audio_engine.track_states[track_id]['playing']
    
    def test_broadcast_scenario(self, audio_engine, test_audio_files):
        """测试广播场景"""
        # 模拟广播节目：背景音乐 + 语音插播
        bgm_track = "background"
        voice_track = "announcement"
        
        bgm_file = test_audio_files['44100_10.0_2']
        voice_file = test_audio_files['44100_3.0_1']
        
        audio_engine.load_track(bgm_track, bgm_file)
        audio_engine.load_track(voice_track, voice_file)
        
        # 1. 播放背景音乐
        audio_engine.play(bgm_track, volume=0.6)
        time.sleep(2.0)
        
        # 2. 降低背景音乐音量，准备插播
        audio_engine.set_volume(bgm_track, 0.2)
        time.sleep(0.5)
        
        # 3. 播放语音插播
        audio_engine.play(voice_track, volume=0.8)
        time.sleep(2.0)
        
        # 4. 语音结束，恢复背景音乐
        audio_engine.stop(voice_track)
        audio_engine.set_volume(bgm_track, 0.6)
        time.sleep(1.0)
        
        # 5. 结束背景音乐
        audio_engine.stop(bgm_track)
        
        assert not audio_engine.track_states[bgm_track]['playing']
        assert not audio_engine.track_states[voice_track]['playing']
    
    def test_audio_engine_recovery(self, audio_engine, test_audio_files):
        """测试音频引擎恢复能力"""
        track_id = "recovery_test"
        file_path = test_audio_files['44100_3.0_2']
        
        # 正常操作
        audio_engine.load_track(track_id, file_path)
        audio_engine.play(track_id, volume=0.5)
        time.sleep(0.5)
        
        # 模拟异常操作
        try:
            # 尝试无效操作
            audio_engine.play("nonexistent_track", volume=1.0)
            audio_engine.set_volume("nonexistent_track", 0.5)
            audio_engine.load_track("", "invalid_file.wav")
        except:
            pass  # 忽略异常
        
        # 验证引擎仍然正常工作
        assert audio_engine.is_running
        assert audio_engine.track_states[track_id]['playing']
        
        # 继续正常操作
        audio_engine.set_volume(track_id, 0.8)
        assert audio_engine.track_states[track_id]['volume'] == 0.8
        
        time.sleep(0.5)
        audio_engine.stop(track_id)
        assert not audio_engine.track_states[track_id]['playing'] 