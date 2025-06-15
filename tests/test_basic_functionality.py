#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基本功能测试
测试AudioEngine的核心功能
"""

import pytest
import time
import numpy as np
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


def assert_audio_properties(engine, track_id: str, expected_duration: float = None):
    """验证音频轨道属性的辅助函数"""
    assert track_id in engine.track_states
    
    if expected_duration is not None:
        info = engine.get_track_info(track_id)
        if info and 'duration' in info:
            actual_duration = info['duration']
            # 允许1%的误差
            assert abs(actual_duration - expected_duration) / expected_duration < 0.01


class TestAudioEngineBasics:
    """AudioEngine基础功能测试"""
    
    def test_engine_initialization(self):
        """测试音频引擎初始化"""
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2
        )
        
        assert engine.sample_rate == 48000
        assert engine.buffer_size == 1024
        assert engine.channels == 2
        assert not engine.is_running
        
        # 启动引擎
        engine.start()
        assert engine.is_running
        
        # 关闭引擎
        engine.shutdown()
        assert not engine.is_running
    
    def test_engine_different_configs(self):
        """测试不同配置的引擎初始化"""
        configs = [
            (22050, 512, 1),
            (44100, 1024, 2),
            (48000, 2048, 2),
            (96000, 4096, 2)
        ]
        
        for sr, buffer_size, channels in configs:
            engine = AudioEngine(
                sample_rate=sr,
                buffer_size=buffer_size,
                channels=channels
            )
            engine.start()
            assert engine.is_running
            engine.shutdown()
    
    def test_track_loading(self, audio_engine, test_audio_files):
        """测试音频轨道加载"""
        # 测试加载不同格式的文件
        test_files = [
            ('track1', test_audio_files['44100_5.0_2']),
            ('track2', test_audio_files['48000_1.0_1']),
            ('track3', test_audio_files['22050_10.0_2'])
        ]
        
        for track_id, file_path in test_files:
            # 使用回调来确认加载完成
            loading_completed = False
            loading_error = None
            
            def on_complete(tid, success, error=None):
                nonlocal loading_completed, loading_error
                loading_completed = True
                if not success:
                    loading_error = error
            
            success = audio_engine.load_track(track_id, file_path, on_complete=on_complete)
            assert success
            
            # 等待加载完成（最多5秒）
            wait_time = 0
            while not loading_completed and wait_time < 5.0:
                time.sleep(0.1)
                wait_time += 0.1
            
            assert loading_completed, f"Track {track_id} loading timed out"
            assert loading_error is None, f"Track {track_id} loading failed: {loading_error}"
            assert track_id in audio_engine.track_states
            assert_audio_properties(audio_engine, track_id)
    
    def test_track_unloading(self, audio_engine, test_audio_files):
        """测试音频轨道卸载"""
        track_id = "test_track"
        file_path = test_audio_files['44100_5.0_2']
        
        # 加载轨道
        loading_completed = False
        
        def on_complete(tid, success, error=None):
            nonlocal loading_completed
            loading_completed = True
        
        success = audio_engine.load_track(track_id, file_path, on_complete=on_complete)
        assert success
        
        # 等待加载完成
        wait_time = 0
        while not loading_completed and wait_time < 5.0:
            time.sleep(0.1)
            wait_time += 0.1
        
        assert loading_completed
        assert track_id in audio_engine.track_states
        
        # 卸载轨道
        audio_engine.unload_track(track_id)
        assert track_id not in audio_engine.track_states
    
    def test_multiple_tracks(self, audio_engine, test_audio_files):
        """测试同时加载多个轨道"""
        tracks = {
            'main': test_audio_files['44100_5.0_2'],
            'sub1': test_audio_files['48000_1.0_1'],
            'sub2': test_audio_files['22050_10.0_2'],
            'bgm': test_audio_files['complex']
        }
        
        # 加载所有轨道
        loading_status = {}
        
        def make_callback(track_id):
            def on_complete(tid, success, error=None):
                loading_status[track_id] = success
            return on_complete
        
        for track_id, file_path in tracks.items():
            success = audio_engine.load_track(track_id, file_path, on_complete=make_callback(track_id))
            assert success
        
        # 等待所有轨道加载完成
        wait_time = 0
        while len(loading_status) < len(tracks) and wait_time < 10.0:
            time.sleep(0.1)
            wait_time += 0.1
        
        # 验证所有轨道都已加载
        for track_id in tracks.keys():
            assert track_id in loading_status, f"Track {track_id} loading not completed"
            assert loading_status[track_id], f"Track {track_id} loading failed"
            assert track_id in audio_engine.track_states
        
        # 卸载所有轨道
        for track_id in tracks.keys():
            audio_engine.unload_track(track_id)
            assert track_id not in audio_engine.track_states


class TestPlaybackControls:
    """播放控制测试"""
    
    def test_basic_playback(self, audio_engine, test_audio_files):
        """测试基本播放功能"""
        track_id = "test_track"
        file_path = test_audio_files['44100_1.0_2']
        
        # 加载音轨
        load_track_with_wait(audio_engine, track_id, file_path)
        
        # 播放
        audio_engine.play(track_id)
        assert audio_engine.track_states[track_id]['playing']
        
        # 停止
        audio_engine.stop(track_id)
        time.sleep(0.1)  # 等待状态更新
        assert not audio_engine.track_states[track_id]['playing']
    
    def test_volume_control(self, audio_engine, test_audio_files):
        """测试音量控制"""
        track_id = "test_track"
        file_path = test_audio_files['44100_1.0_2']  # 使用可用的文件
        
        # 加载音轨
        load_track_with_wait(audio_engine, track_id, file_path)
        
        # 测试默认音量
        assert audio_engine.track_states[track_id]['volume'] == 1.0
        
        # 设置音量
        audio_engine.set_volume(track_id, 0.5)
        assert audio_engine.track_states[track_id]['volume'] == 0.5
        
        # 静音
        audio_engine.mute(track_id)
        assert audio_engine.is_muted(track_id)
        
        # 取消静音
        audio_engine.unmute(track_id)
        assert not audio_engine.is_muted(track_id)
    
    def test_volume_change_during_playback(self, audio_engine, test_audio_files):
        """测试播放过程中音量变化"""
        track_id = "test_track"
        file_path = test_audio_files['44100_5.0_2']
        
        # 加载并播放
        load_track_with_wait(audio_engine, track_id, file_path)
        audio_engine.play(track_id)
        
        # 播放过程中改变音量
        time.sleep(0.5)
        audio_engine.set_volume(track_id, 0.3)
        assert audio_engine.track_states[track_id]['volume'] == 0.3
        
        time.sleep(0.5)
        audio_engine.set_volume(track_id, 0.8)
        assert audio_engine.track_states[track_id]['volume'] == 0.8
        
        audio_engine.stop(track_id)
    
    def test_simultaneous_playback(self, audio_engine, test_audio_files):
        """测试同时播放多个轨道"""
        tracks = {
            'track1': test_audio_files['44100_1.0_2'],  # 使用可用的文件
            'track2': test_audio_files['48000_1.0_1'],
            'track3': test_audio_files['22050_1.0_1']
        }
        
        # 加载所有轨道
        for track_id, file_path in tracks.items():
            load_track_with_wait(audio_engine, track_id, file_path)
        
        # 同时播放所有轨道
        for track_id in tracks.keys():
            audio_engine.play(track_id)
            assert audio_engine.track_states[track_id]['playing']
        
        # 播放一段时间
        time.sleep(0.5)
        
        # 停止所有轨道
        for track_id in tracks.keys():
            audio_engine.stop(track_id)
            time.sleep(0.1)
            assert not audio_engine.track_states[track_id]['playing']


class TestErrorHandling:
    """错误处理测试"""
    
    def test_load_nonexistent_file(self, audio_engine):
        """测试加载不存在的文件"""
        track_id = "nonexistent"
        nonexistent_file = "/path/to/nonexistent/file.wav"
        
        loading_completed = False
        loading_error = None
        
        def on_complete(tid, success, error=None):
            nonlocal loading_completed, loading_error
            loading_completed = True
            if not success:
                loading_error = error
        
        success = audio_engine.load_track(track_id, nonexistent_file, on_complete=on_complete)
        
        # 等待加载完成
        wait_time = 0
        while not loading_completed and wait_time < 5.0:
            time.sleep(0.1)
            wait_time += 0.1
        
        # 应该加载失败
        assert loading_error is not None
        assert track_id not in audio_engine.track_states
    
    def test_play_nonexistent_track(self, audio_engine):
        """测试播放不存在的轨道"""
        # 尝试播放不存在的轨道，应该不会崩溃
        audio_engine.play("nonexistent_track")
        # 没有异常就是成功
    
    def test_duplicate_track_loading(self, audio_engine, test_audio_files):
        """测试重复加载同一轨道"""
        track_id = "duplicate_test"
        file_path = test_audio_files['44100_1.0_2']
        
        # 第一次加载
        load_track_with_wait(audio_engine, track_id, file_path)
        assert track_id in audio_engine.track_states
        
        # 播放轨道
        audio_engine.play(track_id)
        was_playing = audio_engine.track_states[track_id]['playing']
        
        # 再次加载同一轨道（应该替换）
        load_track_with_wait(audio_engine, track_id, file_path)
        assert track_id in audio_engine.track_states
        
        # 验证状态
        if was_playing:
            # 如果之前在播放，重新加载后应该重置状态
            pass  # 具体行为取决于实现
    
    def test_invalid_volume_values(self, audio_engine, test_audio_files):
        """测试无效音量值"""
        track_id = "volume_test"
        file_path = test_audio_files['44100_1.0_2']
        
        # 加载轨道
        load_track_with_wait(audio_engine, track_id, file_path)
        
        # 测试超出范围的音量值
        audio_engine.set_volume(track_id, -0.5)  # 负值
        # 应该被限制在合理范围内
        volume = audio_engine.track_states[track_id]['volume']
        assert volume >= 0.0
        
        audio_engine.set_volume(track_id, 2.0)  # 超过1.0
        volume = audio_engine.track_states[track_id]['volume']
        # 音量处理方式取决于实现，但不应该崩溃
        assert isinstance(volume, (int, float))


class TestStreamingMode:
    """流式播放模式测试"""
    
    def test_streaming_threshold(self, test_audio_files):
        """测试流式播放阈值"""
        # 创建低阈值的引擎
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            enable_streaming=True,
            streaming_threshold_mb=1  # 1MB阈值
        )
        engine.start()
        
        try:
            track_id = "streaming_test"
            file_path = test_audio_files['44100_10.0_2']  # 应该触发流式播放
            
            # 加载轨道
            load_track_with_wait(engine, track_id, file_path)
            
            # 验证轨道已加载
            assert track_id in engine.track_states
            
            # 检查是否为流式轨道
            if hasattr(engine, 'streaming_tracks'):
                # 可能是流式轨道
                pass
            
        finally:
            engine.shutdown()
    
    def test_preload_vs_streaming(self, test_audio_files):
        """测试预加载vs流式播放"""
        # 预加载引擎
        preload_engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            enable_streaming=False
        )
        preload_engine.start()
        
        # 流式引擎
        streaming_engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            enable_streaming=True,
            streaming_threshold_mb=1
        )
        streaming_engine.start()
        
        try:
            file_path = test_audio_files['44100_10.0_2']
            
            # 预加载模式
            load_track_with_wait(preload_engine, "preload", file_path)
            assert "preload" in preload_engine.track_states
            
            # 流式模式
            load_track_with_wait(streaming_engine, "streaming", file_path)
            assert "streaming" in streaming_engine.track_states
            
            # 两种模式都应该能正常播放
            preload_engine.play("preload")
            streaming_engine.play("streaming")
            
            time.sleep(0.5)
            
            preload_engine.stop("preload")
            streaming_engine.stop("streaming")
            
        finally:
            preload_engine.shutdown()
            streaming_engine.shutdown()


class TestPerformanceStats:
    """性能统计测试"""
    
    def test_performance_stats_collection(self, audio_engine, test_audio_files):
        """测试性能统计收集"""
        track_id = "perf_test"
        file_path = test_audio_files['44100_1.0_2']  # 使用可用的文件
        
        # 加载并播放
        load_track_with_wait(audio_engine, track_id, file_path)
        audio_engine.play(track_id)
        
        # 运行一段时间收集统计信息
        time.sleep(1.0)
        
        # 获取性能统计
        stats = audio_engine.get_performance_stats()
        assert isinstance(stats, dict)
        
        # 验证常见的统计项
        expected_keys = ['peak_level', 'cpu_usage', 'underrun_count']
        for key in expected_keys:
            if key in stats:
                # 处理numpy类型
                value = stats[key]
                if hasattr(value, 'item'):  # numpy scalar
                    value = value.item()
                assert isinstance(value, (int, float))
        
        audio_engine.stop(track_id)
    
    def test_track_info(self, audio_engine, test_audio_files):
        """测试轨道信息获取"""
        track_id = "info_test"
        file_path = test_audio_files['44100_5.0_2']
        
        # 加载轨道
        load_track_with_wait(audio_engine, track_id, file_path)
        
        # 获取轨道信息
        info = audio_engine.get_track_info(track_id)
        
        # 验证信息可用性
        if info:
            assert isinstance(info, dict)
            # 验证可能的信息字段
            possible_keys = ['duration', 'sample_rate', 'channels', 'format']
            for key in possible_keys:
                if key in info:
                    assert info[key] is not None
        else:
            # 如果不支持详细信息，至少轨道应该存在
            assert track_id in audio_engine.track_states 