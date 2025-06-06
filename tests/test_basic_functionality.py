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
        loading_completed = False
        
        def on_complete(tid, success, error=None):
            nonlocal loading_completed
            loading_completed = True
        
        audio_engine.load_track(track_id, file_path, on_complete=on_complete)
        
        # 等待加载完成
        wait_time = 0
        while not loading_completed and wait_time < 5.0:
            time.sleep(0.1)
            wait_time += 0.1
        
        assert loading_completed
        
        # 播放
        audio_engine.play(track_id)
        
        # 验证播放状态
        assert audio_engine.track_states[track_id]['playing']
        
        # 等待播放完成
        wait_for_playback(1.0)
        
        # 停止播放
        audio_engine.stop(track_id)
        assert not audio_engine.track_states[track_id]['playing']
    
    def test_volume_control(self, audio_engine, test_audio_files):
        """测试音量控制"""
        track_id = "test_track"
        file_path = test_audio_files['44100_2.0_2']
        
        # 加载音轨
        loading_completed = False
        
        def on_complete(tid, success, error=None):
            nonlocal loading_completed
            loading_completed = True
        
        audio_engine.load_track(track_id, file_path, on_complete=on_complete)
        
        # 等待加载完成
        wait_time = 0
        while not loading_completed and wait_time < 5.0:
            time.sleep(0.1)
            wait_time += 0.1
        
        assert loading_completed
        
        # 测试不同音量级别
        volumes = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5]
        for volume in volumes:
            audio_engine.play(track_id, volume=volume)
            assert audio_engine.track_states[track_id]['volume'] == volume
            time.sleep(0.1)
            audio_engine.stop(track_id)
    
    def test_volume_change_during_playback(self, audio_engine, test_audio_files):
        """测试播放过程中改变音量"""
        track_id = "test_track"
        file_path = test_audio_files['44100_5.0_2']
        
        audio_engine.load_track(track_id, file_path)
        audio_engine.play(track_id, volume=0.5)
        
        # 播放过程中改变音量
        time.sleep(0.5)
        audio_engine.set_volume(track_id, 1.0)
        assert audio_engine.track_states[track_id]['volume'] == 1.0
        
        time.sleep(0.5)
        audio_engine.set_volume(track_id, 0.2)
        assert audio_engine.track_states[track_id]['volume'] == 0.2
        
        audio_engine.stop(track_id)
    
    def test_simultaneous_playback(self, audio_engine, test_audio_files):
        """测试同时播放多个轨道"""
        tracks = {
            'track1': test_audio_files['44100_2.0_2'],
            'track2': test_audio_files['44100_2.0_1'],
            'track3': test_audio_files['48000_1.0_2']
        }
        
        # 加载所有轨道
        for track_id, file_path in tracks.items():
            audio_engine.load_track(track_id, file_path)
        
        # 同时播放所有轨道
        for track_id in tracks.keys():
            audio_engine.play(track_id, volume=0.3)  # 降低音量避免混音过载
            assert audio_engine.track_states[track_id]['playing']
        
        # 播放一段时间
        time.sleep(1.0)
        
        # 停止所有播放
        for track_id in tracks.keys():
            audio_engine.stop(track_id)
            assert not audio_engine.track_states[track_id]['playing']


class TestErrorHandling:
    """错误处理测试"""
    
    def test_load_nonexistent_file(self, audio_engine):
        """测试加载不存在的文件"""
        success = audio_engine.load_track("test", "/nonexistent/file.wav")
        assert not success
        assert "test" not in audio_engine.track_states
    
    def test_play_nonexistent_track(self, audio_engine):
        """测试播放不存在的轨道"""
        # 这应该不会崩溃，只是无效操作
        audio_engine.play("nonexistent_track")
        # 验证没有创建意外的状态
        assert "nonexistent_track" not in audio_engine.track_states
    
    def test_duplicate_track_loading(self, audio_engine, test_audio_files):
        """测试重复加载同一轨道ID"""
        track_id = "test_track"
        file_path1 = test_audio_files['44100_1.0_2']
        file_path2 = test_audio_files['44100_5.0_2']
        
        # 首次加载
        success1 = audio_engine.load_track(track_id, file_path1)
        assert success1
        
        # 重复加载（应该替换原有轨道）
        success2 = audio_engine.load_track(track_id, file_path2)
        assert success2
        
        # 验证轨道仍然存在且可播放
        audio_engine.play(track_id)
        assert audio_engine.track_states[track_id]['playing']
        audio_engine.stop(track_id)
    
    def test_invalid_volume_values(self, audio_engine, test_audio_files):
        """测试无效音量值"""
        track_id = "test_track"
        file_path = test_audio_files['44100_1.0_2']
        
        audio_engine.load_track(track_id, file_path)
        
        # 测试负音量（应该被限制为0）
        audio_engine.play(track_id, volume=-0.5)
        volume = audio_engine.track_states[track_id]['volume']
        assert volume >= 0
        
        # 测试极大音量（应该被合理限制）
        audio_engine.set_volume(track_id, 1000.0)
        volume = audio_engine.track_states[track_id]['volume']
        # 通常音量不应该超过合理范围
        assert volume <= 10.0  # 设置一个合理的上限


class TestStreamingMode:
    """流式播放模式测试"""
    
    def test_streaming_threshold(self, test_audio_files):
        """测试流式播放阈值"""
        # 创建启用流式播放的引擎，阈值很小
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            enable_streaming=True,
            streaming_threshold_mb=0.001  # 很小的阈值，强制使用流式播放
        )
        engine.start()
        
        try:
            # 加载一个相对较大的文件
            track_id = "streaming_test"
            file_path = test_audio_files['44100_10.0_2']
            
            success = engine.load_track(track_id, file_path)
            assert success
            
            # 验证使用了流式播放
            assert track_id in engine.streaming_tracks
            
            # 测试流式播放
            engine.play(track_id)
            time.sleep(2.0)  # 播放2秒
            engine.stop(track_id)
            
        finally:
            engine.shutdown()
    
    def test_preload_vs_streaming(self, test_audio_files):
        """测试预加载与流式播放的区别"""
        # 预加载模式
        engine_preload = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            enable_streaming=False
        )
        engine_preload.start()
        
        # 流式播放模式
        engine_streaming = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            enable_streaming=True,
            streaming_threshold_mb=0.001
        )
        engine_streaming.start()
        
        try:
            file_path = test_audio_files['44100_5.0_2']
            
            # 预加载模式
            success1 = engine_preload.load_track("preload", file_path)
            assert success1
            assert "preload" in engine_preload.tracks
            assert "preload" not in engine_preload.streaming_tracks
            
            # 流式播放模式
            success2 = engine_streaming.load_track("streaming", file_path)
            assert success2
            assert "streaming" in engine_streaming.streaming_tracks
            assert "streaming" not in engine_streaming.tracks
            
        finally:
            engine_preload.shutdown()
            engine_streaming.shutdown()


class TestPerformanceStats:
    """性能统计测试"""
    
    def test_performance_stats_collection(self, audio_engine, test_audio_files):
        """测试性能统计收集"""
        track_id = "perf_test"
        file_path = test_audio_files['44100_2.0_2']
        
        audio_engine.load_track(track_id, file_path)
        audio_engine.play(track_id)
        
        # 播放一段时间以收集统计信息
        time.sleep(1.0)
        
        stats = audio_engine.get_performance_stats()
        
        # 验证统计信息的基本结构
        assert isinstance(stats, dict)
        expected_keys = ['underrun_count', 'peak_level', 'cpu_usage']
        for key in expected_keys:
            assert key in stats
            assert isinstance(stats[key], (int, float))
        
        # 验证数值合理性
        assert stats['underrun_count'] >= 0
        assert 0 <= stats['peak_level'] <= 1.0
        assert stats['cpu_usage'] >= 0
        
        audio_engine.stop(track_id)
    
    def test_track_info(self, audio_engine, test_audio_files):
        """测试轨道信息获取"""
        track_id = "info_test"
        file_path = test_audio_files['44100_5.0_2']  # 5秒音频
        
        audio_engine.load_track(track_id, file_path)
        
        info = audio_engine.get_track_info(track_id)
        assert isinstance(info, dict)
        
        # 验证基本信息
        if 'duration' in info:
            # 允许小的误差
            assert abs(info['duration'] - 5.0) < 0.1
        
        if 'sample_rate' in info:
            assert info['sample_rate'] > 0
        
        if 'channels' in info:
            assert info['channels'] in [1, 2] 