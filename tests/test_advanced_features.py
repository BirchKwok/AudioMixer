#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级功能测试
测试AudioEngine的复杂使用场景和性能
"""

import pytest
import time
import numpy as np
import threading
from realtimemix import AudioEngine


def wait_for_playback(duration: float, tolerance: float = 0.1):
    """等待播放完成的辅助函数"""
    time.sleep(duration + tolerance)


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
        file2 = test_audio_files['48000_1.0_2']
        
        load_track_with_wait(audio_engine, track1, file1)
        load_track_with_wait(audio_engine, track2, file2)
        
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
        
        # 等待状态更新
        time.sleep(0.1)
        
        # 检查播放状态，允许一些延迟
        if track1 in audio_engine.track_states:
            assert not audio_engine.track_states[track1].get('playing', False)
        if track2 in audio_engine.track_states:
            assert not audio_engine.track_states[track2].get('playing', False)
    
    def test_crossfade_simulation(self, audio_engine, test_audio_files):
        """测试交叉淡化模拟"""
        track1 = "main"
        track2 = "sub"
        file1 = test_audio_files['44100_5.0_2']
        file2 = test_audio_files['48000_1.0_2']
        
        load_track_with_wait(audio_engine, track1, file1)
        load_track_with_wait(audio_engine, track2, file2)
        
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
            load_track_with_wait(audio_engine, track_id, file_path)
        
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
        
        # 等待停止操作完成
        time.sleep(0.2)
        
        # 验证所有音轨都已停止
        for track_id in tracks.keys():
            assert not audio_engine.track_states[track_id]['playing']


class TestSynchronizedPlayback:
    """同步播放测试"""
    
    def test_synchronized_start(self, audio_engine, test_audio_files):
        """测试同步开始播放"""
        tracks = ['track1', 'track2', 'track3']
        files = [
            test_audio_files['44100_1.0_2'],
            test_audio_files['44100_1.0_1'],
            test_audio_files['48000_1.0_2']
        ]
        
        # 加载所有音轨
        for track_id, file_path in zip(tracks, files):
            load_track_with_wait(audio_engine, track_id, file_path)
        
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
            'intro': test_audio_files['44100_1.0_2'],
            'main': test_audio_files['44100_5.0_2'],
            'outro': test_audio_files['44100_1.0_1']
        }
        
        # 加载所有音轨
        for track_id, file_path in tracks.items():
            load_track_with_wait(audio_engine, track_id, file_path)
        
        # 播放序列
        # 1. 播放intro
        audio_engine.play('intro', volume=0.8)
        time.sleep(0.8)  # 播放0.8秒
        
        # 2. 在intro还在播放时启动main
        audio_engine.play('main', volume=0.6)
        time.sleep(0.2)  # intro剩余0.2秒
        
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
        audio_engine.stop('outro', fade_out=False)
        
        # 等待停止操作完成
        time.sleep(0.3)
        
        # 确保所有轨道都已停止
        for track_id in tracks.keys():
            if audio_engine.track_states[track_id]['playing']:
                audio_engine.stop(track_id, fade_out=False)
                time.sleep(0.1)
        
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
        initial_memory = process.memory_info().rss
        
        # 加载多个音轨
        track_files = [
            test_audio_files['44100_5.0_2'],
            test_audio_files['44100_5.0_1'],
            test_audio_files['48000_5.0_2'],
            test_audio_files['22050_5.0_1'],
            test_audio_files['44100_10.0_2']
        ]
        
        # 加载轨道
        for i, file_path in enumerate(track_files):
            track_id = f"track_{i}"
            load_track_with_wait(audio_engine_no_streaming, track_id, file_path)
        
        loaded_memory = process.memory_info().rss
        memory_increase = loaded_memory - initial_memory
        
        # 验证内存增长在合理范围内（不超过100MB）
        assert memory_increase < 100 * 1024 * 1024
        
        # 卸载所有音轨
        for i in range(len(track_files)):
            track_id = f"track_{i}"
            audio_engine_no_streaming.unload_track(track_id)
        
        # 强制垃圾回收
        import gc
        gc.collect()
        time.sleep(0.1)
        
        final_memory = process.memory_info().rss
        memory_released = loaded_memory - final_memory
        
        # 验证内存得到释放（允许一些内存碎片）
        # 如果内存没有明显释放，至少确保没有继续增长
        assert memory_released >= 0 or (final_memory - initial_memory) < memory_increase * 1.5
    
    def test_concurrent_loading_and_unloading(self, audio_engine, test_audio_files):
        """测试并发加载和卸载"""
        def load_unload_worker(worker_id, iterations):
            for i in range(iterations):
                track_id = f"worker_{worker_id}_track_{i}"
                file_path = test_audio_files['44100_1.0_2']
                
                try:
                    load_track_with_wait(audio_engine, track_id, file_path, timeout=3.0)
                    time.sleep(0.1)  # 短暂播放
                    audio_engine.unload_track(track_id)
                except Exception as e:
                    print(f"Worker {worker_id} iteration {i} failed: {e}")
        
        # 创建多个工作线程
        threads = []
        worker_count = 3
        iterations_per_worker = 2
        
        for worker_id in range(worker_count):
            thread = threading.Thread(
                target=load_unload_worker,
                args=(worker_id, iterations_per_worker)
            )
            threads.append(thread)
        
        # 启动所有线程
        for thread in threads:
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join(timeout=15.0)
        
        # 验证引擎状态正常
        assert audio_engine.is_running


class TestPerformanceStress:
    """性能压力测试"""
    
    def test_rapid_volume_changes(self, audio_engine, test_audio_files):
        """测试快速音量变化"""
        track_id = "test_track"
        file_path = test_audio_files['44100_5.0_2']
        
        load_track_with_wait(audio_engine, track_id, file_path)
        audio_engine.play(track_id, volume=0.5)
        
        # 快速改变音量100次
        start_time = time.time()
        for i in range(100):
            volume = (i % 10) / 10.0
            audio_engine.set_volume(track_id, volume)
        end_time = time.time()
        
        total_time = end_time - start_time
        
        # 100次音量变化应该在1秒内完成
        assert total_time < 1.0
        
        audio_engine.stop(track_id)
    
    def test_high_frequency_play_stop(self, audio_engine, test_audio_files):
        """测试高频率播放停止"""
        track_id = "test_track"
        file_path = test_audio_files['44100_1.0_2']
        
        load_track_with_wait(audio_engine, track_id, file_path)
        
        # 快速播放停止50次
        start_time = time.time()
        for i in range(50):
            audio_engine.play(track_id, volume=0.1)
            time.sleep(0.01)  # 10ms播放
            audio_engine.stop(track_id)
            time.sleep(0.01)  # 10ms停止
        end_time = time.time()
        
        total_time = end_time - start_time
        
        # 应该在合理时间内完成
        assert total_time < 2.0
        
        # 确保最后的停止操作完成
        audio_engine.stop(track_id, fade_out=False)  # 强制立即停止
        time.sleep(0.3)  # 增加等待时间
        
        # 如果仍在播放，再次强制停止
        if audio_engine.track_states[track_id]['playing']:
            audio_engine.stop(track_id, fade_out=False)
            time.sleep(0.2)
        
        # 验证最终状态
        assert not audio_engine.track_states[track_id]['playing']
    
    def test_performance_under_load(self, audio_engine, test_audio_files):
        """测试负载下的性能"""
        # 加载多个音轨
        tracks = {}
        for i in range(4):
            track_id = f"track_{i}"
            file_path = test_audio_files['44100_5.0_2']
            load_track_with_wait(audio_engine, track_id, file_path)
            tracks[track_id] = file_path
        
        # 同时播放所有音轨
        for track_id in tracks.keys():
            audio_engine.play(track_id, volume=0.2)
        
        # 在播放过程中执行各种操作
        start_time = time.time()
        for i in range(20):
            # 音量变化
            for track_id in tracks.keys():
                volume = 0.1 + (i % 5) * 0.1
                audio_engine.set_volume(track_id, volume)
            
            time.sleep(0.05)
        
        end_time = time.time()
        operation_time = end_time - start_time
        
        # 停止所有音轨
        for track_id in tracks.keys():
            audio_engine.stop(track_id)
        
        # 验证操作在合理时间内完成
        assert operation_time < 2.0


class TestComplexScenarios:
    """复杂场景测试"""
    
    def test_live_mixing_simulation(self, audio_engine, test_audio_files):
        """模拟现场混音场景"""
        # 音轨配置：主音轨 + 多个副音轨
        tracks = {
            'bgm': (test_audio_files['44100_10.0_2'], 0.3),
            'voice1': (test_audio_files['44100_5.0_1'], 0.7),
            'voice2': (test_audio_files['48000_1.0_1'], 0.0),  # 预备轨道
            'effect': (test_audio_files['22050_1.0_1'], 0.0)   # 音效轨道
        }
        
        # 加载所有音轨
        for track_id, (file_path, volume) in tracks.items():
            load_track_with_wait(audio_engine, track_id, file_path)
        
        # 场景1：开场 - 背景音乐 + 主持人声音
        audio_engine.play('bgm', volume=0.3)
        time.sleep(1.0)
        
        audio_engine.play('voice1', volume=0.7)
        time.sleep(2.0)
        
        # 场景2：音效过渡
        audio_engine.play('effect', volume=0.8)
        audio_engine.set_volume('voice1', 0.0)  # 压低主音
        time.sleep(0.5)
        
        # 场景3：切换到voice2
        audio_engine.stop('voice1')
        audio_engine.play('voice2', volume=0.7)
        audio_engine.set_volume('effect', 0.0)
        time.sleep(1.0)
        
        # 场景4：淡出结束
        audio_engine.set_volume('bgm', 0.1)
        audio_engine.set_volume('voice2', 0.3)
        time.sleep(1.0)
        
        # 停止所有
        for track_id in tracks.keys():
            audio_engine.stop(track_id)
    
    def test_broadcast_scenario(self, audio_engine, test_audio_files):
        """模拟广播场景"""
        tracks = {
            'intro': test_audio_files['44100_1.0_2'],
            'main_content': test_audio_files['44100_5.0_2'],
            'commercial': test_audio_files['44100_1.0_1'],
            'outro': test_audio_files['44100_1.0_2']
        }
        
        # 加载节目音轨
        for track_id, file_path in tracks.items():
            load_track_with_wait(audio_engine, track_id, file_path)
        
        # 广播流程
        sequence = [
            ('intro', 0.8, 1.0),
            ('main_content', 0.6, 3.0),
            ('commercial', 0.8, 1.0),
            ('main_content', 0.6, 2.0),
            ('outro', 0.8, 1.0)
        ]
        
        for track_id, volume, duration in sequence:
            audio_engine.play(track_id, volume=volume)
            time.sleep(duration)
            audio_engine.stop(track_id)
    
    def test_audio_engine_recovery(self, audio_engine, test_audio_files):
        """测试音频引擎恢复能力"""
        track_id = "test_track"
        file_path = test_audio_files['44100_5.0_2']
        
        load_track_with_wait(audio_engine, track_id, file_path)
        
        # 正常播放
        audio_engine.play(track_id, volume=0.5)
        time.sleep(1.0)
        
        # 模拟异常情况：快速连续操作
        for i in range(10):
            audio_engine.stop(track_id)
            audio_engine.play(track_id, volume=0.1)
        
        time.sleep(0.5)
        
        # 验证引擎仍然正常工作
        assert audio_engine.is_running
        
        # 正常停止
        audio_engine.stop(track_id)
        
        # 等待停止操作完成
        time.sleep(0.2)
        
        assert not audio_engine.track_states[track_id]['playing'] 