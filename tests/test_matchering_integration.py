#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Matchering集成测试
测试load_track_with_matchering功能
"""

import pytest
import time
import os
import tempfile
import numpy as np
import soundfile as sf
from realtimemix import AudioEngine


def wait_for_playback(duration: float, tolerance: float = 0.1):
    """等待播放完成的辅助函数"""
    time.sleep(duration + tolerance)


class TestMatcheringIntegration:
    """Matchering集成测试"""
    
    def test_basic_matchering_loading(self, audio_engine, test_audio_files):
        """测试基本的matchering加载功能"""
        # 先加载主音轨作为参考
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']  # 10秒音频
        success = audio_engine.load_track(main_track, main_file)
        assert success
        
        # 使用matchering加载副音轨
        sub_track = "sub"
        sub_file = test_audio_files['44100_5.0_1']  # 5秒音频
        
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=2.0,
            reference_duration_sec=3.0
        )
        assert success
        assert sub_track in audio_engine.track_states
        
        # 测试播放匹配后的音轨
        audio_engine.play(sub_track)
        assert audio_engine.track_states[sub_track]['playing']
        time.sleep(1.0)
        audio_engine.stop(sub_track)
    
    def test_matchering_without_reference_track(self, audio_engine, test_audio_files):
        """测试在没有参考音轨时使用matchering"""
        sub_track = "sub"
        sub_file = test_audio_files['44100_5.0_1']
        
        # 尝试在没有加载参考音轨的情况下使用matchering
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id="nonexistent_main",
            reference_start_sec=0.0
        )
        assert not success
        assert sub_track not in audio_engine.track_states
    
    def test_matchering_with_different_reference_positions(self, audio_engine, test_audio_files):
        """测试不同参考位置的matchering"""
        # 加载长的主音轨
        main_track = "main"
        main_file = test_audio_files['44100_30.0_2']  # 30秒音频
        audio_engine.load_track(main_track, main_file)
        
        sub_file = test_audio_files['44100_2.0_1']
        
        # 测试不同的参考位置
        test_positions = [
            (0.0, 5.0),    # 开头
            (10.0, 5.0),   # 中间
            (20.0, 5.0),   # 后面
            (25.0, 5.0)    # 接近结尾
        ]
        
        for i, (start_sec, duration_sec) in enumerate(test_positions):
            sub_track = f"sub_{i}"
            success = audio_engine.load_track_with_matchering(
                track_id=sub_track,
                file_path=sub_file,
                reference_track_id=main_track,
                reference_start_sec=start_sec,
                reference_duration_sec=duration_sec
            )
            assert success
            assert sub_track in audio_engine.track_states
    
    def test_matchering_beyond_reference_length(self, audio_engine, test_audio_files):
        """测试参考片段超出音轨长度的情况"""
        # 加载短的主音轨
        main_track = "main"
        main_file = test_audio_files['44100_5.0_2']  # 5秒音频
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_2.0_1']
        
        # 尝试从超出音轨长度的位置开始
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=10.0,  # 超出5秒的音轨长度
            reference_duration_sec=3.0
        )
        # 应该会回退到从头开始，但仍然成功
        assert success
    
    def test_matchering_with_very_short_reference(self, audio_engine, test_audio_files):
        """测试非常短的参考片段"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_5.0_2']
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_2.0_1']
        
        # 使用非常短的参考片段
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=1.0,
            reference_duration_sec=0.5  # 只有0.5秒
        )
        # 可能成功也可能失败，取决于matchering的要求
        # 但不应该崩溃
        if success:
            assert sub_track in audio_engine.track_states
    
    def test_matchering_with_different_audio_formats(self, audio_engine, test_audio_files):
        """测试不同音频格式的matchering"""
        # 主音轨：立体声，44100Hz
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']
        audio_engine.load_track(main_track, main_file)
        
        # 测试不同格式的副音轨
        test_cases = [
            ('sub_mono', test_audio_files['44100_5.0_1']),      # 单声道，同采样率
            ('sub_hires', test_audio_files['48000_5.0_2']),     # 立体声，高采样率
            ('sub_lowres', test_audio_files['22050_5.0_1'])     # 单声道，低采样率
        ]
        
        for sub_track, sub_file in test_cases:
            success = audio_engine.load_track_with_matchering(
                track_id=sub_track,
                file_path=sub_file,
                reference_track_id=main_track,
                reference_start_sec=2.0,
                reference_duration_sec=5.0
            )
            assert success
            assert sub_track in audio_engine.track_states
    
    def test_matchering_with_silent_padding(self, audio_engine, test_audio_files):
        """测试带静音填充的matchering"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_3.0_1']
        
        # 使用静音填充
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=2.0,
            reference_duration_sec=5.0,
            silent_lpadding_ms=500.0,  # 500ms前置静音
            silent_rpadding_ms=200.0   # 200ms后置静音
        )
        assert success
        assert sub_track in audio_engine.track_states
    
    def test_matchering_temp_file_cleanup(self, audio_engine, test_audio_files):
        """测试临时文件清理"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_3.0_1']
        
        # 记录临时目录数量（在/tmp中）
        import tempfile
        temp_dir = tempfile.gettempdir()
        temp_dirs_before = [d for d in os.listdir(temp_dir) 
                           if d.startswith('realtimemix_matchering_')]
        
        # 执行matchering
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=2.0
        )
        assert success
        
        # 卸载轨道
        audio_engine.unload_track(sub_track)
        
        # 检查临时目录是否被清理
        temp_dirs_after = [d for d in os.listdir(temp_dir) 
                          if d.startswith('realtimemix_matchering_')]
        
        # 应该没有新增未清理的临时目录
        assert len(temp_dirs_after) <= len(temp_dirs_before)


class TestMatcheringEdgeCases:
    """Matchering边界情况测试"""
    
    def test_matchering_with_very_loud_audio(self, audio_engine, test_audio_files):
        """测试很响的音频matchering"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['high_volume']
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_2.0_1']
        
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=0.0,
            reference_duration_sec=1.0
        )
        # 应该能处理高音量音频
        assert success
    
    def test_matchering_with_very_quiet_audio(self, audio_engine, test_audio_files):
        """测试很安静的音频matchering"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['low_volume']
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_2.0_1']
        
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=0.0,
            reference_duration_sec=1.0
        )
        # 应该能处理低音量音频
        assert success
    
    def test_matchering_with_silence_reference(self, audio_engine, test_audio_files):
        """测试以静音作为参考的matchering"""
        # 加载静音主音轨
        main_track = "main"
        main_file = test_audio_files['silence']
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_2.0_1']
        
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=0.0,
            reference_duration_sec=1.0
        )
        # 可能成功也可能失败，但不应该崩溃
        # matchering可能无法处理完全静音的参考
        if not success:
            assert sub_track not in audio_engine.track_states
    
    def test_matchering_with_complex_waveform(self, audio_engine, test_audio_files):
        """测试复杂波形的matchering"""
        # 使用复杂波形作为主音轨
        main_track = "main"
        main_file = test_audio_files['complex']
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_2.0_1']
        
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=1.0,
            reference_duration_sec=3.0
        )
        assert success
        assert sub_track in audio_engine.track_states
    
    def test_matchering_duplicate_track_id(self, audio_engine, test_audio_files):
        """测试重复轨道ID的matchering"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        sub_file1 = test_audio_files['44100_2.0_1']
        sub_file2 = test_audio_files['48000_3.0_2']
        
        # 首次加载
        success1 = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file1,
            reference_track_id=main_track,
            reference_start_sec=1.0
        )
        assert success1
        
        # 重复加载相同ID（应该替换）
        success2 = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file2,
            reference_track_id=main_track,
            reference_start_sec=2.0
        )
        assert success2
        assert sub_track in audio_engine.track_states


class TestMatcheringPerformance:
    """Matchering性能测试"""
    
    def test_matchering_processing_time(self, audio_engine, test_audio_files):
        """测试matchering处理时间"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_5.0_1']
        
        # 测量处理时间
        start_time = time.time()
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=2.0,
            reference_duration_sec=5.0
        )
        processing_time = time.time() - start_time
        
        assert success
        # 处理时间应该在合理范围内（这里设置为30秒上限）
        assert processing_time < 30.0
        
        print(f"Matchering processing time: {processing_time:.2f} seconds")
    
    def test_multiple_matchering_operations(self, audio_engine, test_audio_files):
        """测试多次matchering操作"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_15.0_2']
        audio_engine.load_track(main_track, main_file)
        
        # 执行多次matchering操作
        sub_files = [
            test_audio_files['44100_2.0_1'],
            test_audio_files['48000_3.0_2'],
            test_audio_files['22050_1.0_1']
        ]
        
        for i, sub_file in enumerate(sub_files):
            sub_track = f"sub_{i}"
            success = audio_engine.load_track_with_matchering(
                track_id=sub_track,
                file_path=sub_file,
                reference_track_id=main_track,
                reference_start_sec=i * 2.0,  # 不同的参考位置
                reference_duration_sec=2.0
            )
            assert success
            assert sub_track in audio_engine.track_states
        
        # 验证所有轨道都已成功加载
        for i in range(len(sub_files)):
            assert f"sub_{i}" in audio_engine.track_states


@pytest.mark.skipif(
    not pytest.importorskip("matchering", reason="matchering not available"),
    reason="Matchering library not installed"
)
class TestMatcheringErrorHandling:
    """Matchering错误处理测试"""
    
    def test_matchering_with_invalid_file(self, audio_engine, test_audio_files):
        """测试无效文件的matchering"""
        # 加载有效的主音轨
        main_track = "main"
        main_file = test_audio_files['44100_5.0_2']
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        invalid_file = "/nonexistent/file.wav"
        
        # 尝试用无效文件进行matchering
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=invalid_file,
            reference_track_id=main_track,
            reference_start_sec=0.0
        )
        assert not success
        assert sub_track not in audio_engine.track_states
    
    def test_matchering_library_unavailable(self, monkeypatch, audio_engine, test_audio_files):
        """测试matchering库不可用的情况"""
        # 模拟matchering库不可用
        import realtimemix.engine
        monkeypatch.setattr(realtimemix.engine, 'mg', None)
        
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_5.0_2']
        audio_engine.load_track(main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_2.0_1']
        
        # 尝试使用matchering
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=0.0
        )
        assert not success 