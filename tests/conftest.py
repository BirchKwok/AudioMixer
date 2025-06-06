#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试配置文件
提供测试用的fixtures和工具函数
"""

import pytest
import numpy as np
import soundfile as sf
import tempfile
import os
import shutil
from pathlib import Path
import time
import logging
from realtimemix import AudioEngine


@pytest.fixture(scope="session")
def test_audio_dir():
    """创建临时目录存放测试音频文件"""
    temp_dir = tempfile.mkdtemp(prefix="realtimemix_test_")
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture(scope="session")
def test_audio_files(test_audio_dir):
    """生成各种测试音频文件"""
    files = {}
    
    # 生成不同类型的测试音频
    sample_rates = [22050, 44100, 48000]
    durations = [1.0, 5.0, 10.0, 30.0]
    channels = [1, 2]
    
    for sr in sample_rates:
        for duration in durations:
            for ch in channels:
                # 生成正弦波音频
                t = np.linspace(0, duration, int(sr * duration), False)
                frequency = 440.0  # A4音符
                audio = np.sin(2 * np.pi * frequency * t)
                
                if ch == 2:
                    # 立体声：左声道440Hz，右声道880Hz
                    left = np.sin(2 * np.pi * 440 * t)
                    right = np.sin(2 * np.pi * 880 * t)
                    audio = np.column_stack([left, right])
                else:
                    audio = audio.reshape(-1, 1)
                
                # 添加音量包络，避免突然开始/结束
                fade_samples = int(0.01 * sr)  # 10ms淡入淡出
                if len(audio) > 2 * fade_samples:
                    fade_in = np.linspace(0, 1, fade_samples)
                    fade_out = np.linspace(1, 0, fade_samples)
                    if ch == 2:
                        audio[:fade_samples] *= fade_in.reshape(-1, 1)
                        audio[-fade_samples:] *= fade_out.reshape(-1, 1)
                    else:
                        audio[:fade_samples, 0] *= fade_in
                        audio[-fade_samples:, 0] *= fade_out
                
                filename = f"test_{sr}hz_{duration}s_{ch}ch.wav"
                filepath = os.path.join(test_audio_dir, filename)
                sf.write(filepath, audio, sr)
                
                key = f"{sr}_{duration}_{ch}"
                files[key] = filepath
    
    # 生成特殊测试文件
    
    # 1. 静音文件
    silence = np.zeros((44100, 2))
    files['silence'] = os.path.join(test_audio_dir, "silence.wav")
    sf.write(files['silence'], silence, 44100)
    
    # 2. 低音量文件
    low_volume = np.sin(2 * np.pi * 440 * np.linspace(0, 2, 88200)) * 0.01
    files['low_volume'] = os.path.join(test_audio_dir, "low_volume.wav")
    sf.write(files['low_volume'], low_volume.reshape(-1, 1), 44100)
    
    # 3. 高音量文件（接近剪切）
    high_volume = np.sin(2 * np.pi * 440 * np.linspace(0, 2, 88200)) * 0.95
    files['high_volume'] = os.path.join(test_audio_dir, "high_volume.wav")
    sf.write(files['high_volume'], high_volume.reshape(-1, 1), 44100)
    
    # 4. 复杂波形（多频率）
    t = np.linspace(0, 5, 220500)
    complex_wave = (np.sin(2 * np.pi * 220 * t) + 
                   0.5 * np.sin(2 * np.pi * 440 * t) + 
                   0.25 * np.sin(2 * np.pi * 880 * t))
    complex_wave = complex_wave / np.max(np.abs(complex_wave)) * 0.8  # 标准化
    files['complex'] = os.path.join(test_audio_dir, "complex.wav")
    sf.write(files['complex'], complex_wave.reshape(-1, 1), 44100)
    
    return files


@pytest.fixture
def audio_engine():
    """创建AudioEngine实例"""
    engine = AudioEngine(
        sample_rate=48000,
        buffer_size=1024,
        channels=2,
        enable_streaming=True,
        streaming_threshold_mb=10
    )
    engine.start()
    yield engine
    engine.shutdown()


@pytest.fixture
def audio_engine_no_streaming():
    """创建不启用流式播放的AudioEngine实例"""
    engine = AudioEngine(
        sample_rate=48000,
        buffer_size=1024,
        channels=2,
        enable_streaming=False
    )
    engine.start()
    yield engine
    engine.shutdown()


@pytest.fixture
def logger():
    """测试用日志器"""
    logger = logging.getLogger("test_realtimemix")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


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