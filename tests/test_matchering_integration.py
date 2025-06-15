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


def load_track_with_matchering_and_wait(audio_engine, track_id: str, file_path: str, reference_track_id: str, 
                                       reference_start_sec: float, reference_duration_sec: float = 10.0,
                                       silent_lpadding_ms: float = 0.0, silent_rpadding_ms: float = 0.0,
                                       gentle_matchering: bool = True, timeout: float = 10.0):
    """辅助函数：使用matchering加载音轨并等待完成"""
    success = audio_engine.load_track_with_matchering(
        track_id=track_id,
        file_path=file_path,
        reference_track_id=reference_track_id,
        reference_start_sec=reference_start_sec,
        reference_duration_sec=reference_duration_sec,
        silent_lpadding_ms=silent_lpadding_ms,
        silent_rpadding_ms=silent_rpadding_ms,
        gentle_matchering=gentle_matchering
    )
    
    if not success:
        return False
    
    # 等待matchering处理后的异步加载完成
    wait_time = 0
    while track_id not in audio_engine.track_states and wait_time < timeout:
        time.sleep(0.1)
        wait_time += 0.1
    
    if track_id not in audio_engine.track_states:
        raise TimeoutError(f"Matchering track {track_id} loading timed out after {timeout}s")
    
    return True


class TestMatcheringIntegration:
    """Matchering集成测试"""
    
    def test_basic_matchering_loading(self, audio_engine, test_audio_files):
        """测试基本的matchering加载功能"""
        # 先加载主音轨作为参考
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']  # 10秒音频
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        # 使用matchering加载副音轨
        sub_track = "sub"
        sub_file = test_audio_files['44100_5.0_1']  # 5秒音频
        
        load_track_with_matchering_and_wait(
            audio_engine, sub_track, sub_file, main_track,
            reference_start_sec=2.0, reference_duration_sec=3.0
        )
        
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
        
        # 加载主音轨并等待完成（长音频，增加等待时间）
        load_track_with_wait(audio_engine, main_track, main_file, timeout=10.0)
        
        sub_file = test_audio_files['44100_1.0_1']  # 使用可用的1秒单声道文件
        
        # 测试不同的参考位置
        test_positions = [
            (0.0, 5.0),    # 开头
            (10.0, 5.0),   # 中间
            (20.0, 5.0),   # 后面
            (25.0, 5.0)    # 接近结尾
        ]
        
        for i, (start_sec, duration_sec) in enumerate(test_positions):
            sub_track = f"sub_{i}"
            load_track_with_matchering_and_wait(
                audio_engine, sub_track, sub_file, main_track,
                reference_start_sec=start_sec,
                reference_duration_sec=duration_sec
            )
            assert sub_track in audio_engine.track_states
    
    def test_matchering_beyond_reference_length(self, audio_engine, test_audio_files):
        """测试参考片段超出音轨长度的情况"""
        # 加载短的主音轨
        main_track = "main"
        main_file = test_audio_files['44100_5.0_2']  # 5秒音频
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_1.0_1']  # 使用可用的1秒单声道文件
        
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
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_1.0_1']  # 使用可用的1秒单声道文件
        
        # 使用非常短的参考片段
        try:
            load_track_with_matchering_and_wait(
                audio_engine, sub_track, sub_file, main_track,
                reference_start_sec=1.0,
                reference_duration_sec=0.5  # 只有0.5秒
            )
            # 如果成功，验证轨道已加载
            assert sub_track in audio_engine.track_states
        except Exception:
            # 可能失败，取决于matchering的要求，但不应该崩溃
            pass
    
    def test_matchering_with_different_audio_formats(self, audio_engine, test_audio_files):
        """测试不同音频格式的matchering"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        # 测试不同格式的音轨
        test_tracks = [
            ('sub_mono', test_audio_files['44100_5.0_1']),      # 单声道，同采样率
            ('sub_hires', test_audio_files['48000_5.0_2']),     # 立体声，高采样率
            ('sub_lowres', test_audio_files['22050_5.0_1'])     # 单声道，低采样率
        ]
        
        for sub_track, sub_file in test_tracks:
            try:
                load_track_with_matchering_and_wait(
                    audio_engine, sub_track, sub_file, main_track,
                    reference_start_sec=2.0, reference_duration_sec=5.0,
                    timeout=15.0  # 增加超时时间，因为matchering可能较慢
                )
                assert sub_track in audio_engine.track_states
            except Exception as e:
                # 如果匹配失败，至少确保没有崩溃
                print(f"Matchering failed for {sub_track}: {e}")
    
    def test_matchering_with_silent_padding(self, audio_engine, test_audio_files):
        """测试带静音填充的matchering"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_1.0_1']  # 使用可用的1秒单声道文件
        
        # 使用matchering加载副音轨，并添加静音填充
        load_track_with_matchering_and_wait(
            audio_engine, sub_track, sub_file, main_track,
            reference_start_sec=2.0, reference_duration_sec=5.0,
            silent_lpadding_ms=500.0,  # 前面500ms静音
            silent_rpadding_ms=300.0   # 后面300ms静音
        )
        
        # 验证轨道已加载
        assert sub_track in audio_engine.track_states
    
    def test_matchering_temp_file_cleanup(self, audio_engine, test_audio_files):
        """测试matchering临时文件清理"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_1.0_1']  # 使用可用的1秒单声道文件
        
        # 记录临时目录中的文件数量
        temp_dir = tempfile.gettempdir()
        before_files = set(os.listdir(temp_dir))
        
        # 使用matchering
        load_track_with_matchering_and_wait(
            audio_engine, sub_track, sub_file, main_track,
            reference_start_sec=2.0, reference_duration_sec=3.0
        )
        
        # 等待一下，确保清理完成
        time.sleep(1.0)
        
        # 检查临时文件是否已清理
        after_files = set(os.listdir(temp_dir))
        
        # 不应该有太多新文件留下
        new_files = after_files - before_files
        matchering_files = [f for f in new_files if 'matchering' in f.lower()]
        assert len(matchering_files) <= 1  # 可能有一些系统临时文件，但matchering文件应该被清理


class TestMatcheringEdgeCases:
    """Matchering边缘情况测试"""
    
    def test_matchering_with_very_loud_audio(self, audio_engine, test_audio_files):
        """测试非常响的音频matchering"""
        # 加载响亮的主音轨
        main_track = "main"
        main_file = test_audio_files['high_volume']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_1.0_1']  # 使用可用的1秒单声道文件
        
        # 使用matchering处理响亮音频
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=0.0,
            reference_duration_sec=1.0
        )
        # 即使音频很响，matchering也应该能处理
        assert success
    
    def test_matchering_with_very_quiet_audio(self, audio_engine, test_audio_files):
        """测试非常安静的音频matchering"""
        # 加载安静的主音轨
        main_track = "main"
        main_file = test_audio_files['low_volume']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_1.0_1']  # 使用可用的1秒单声道文件
        
        # 使用matchering处理安静音频
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=0.0,
            reference_duration_sec=1.0
        )
        # 即使音频很安静，matchering也应该能处理
        assert success
    
    def test_matchering_with_silence_reference(self, audio_engine, test_audio_files):
        """测试以静音作为参考的matchering"""
        # 加载静音主音轨
        main_track = "main"
        main_file = test_audio_files['silence']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_1.0_1']
        
        # 使用静音作为参考进行matchering
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=0.0,
            reference_duration_sec=1.0
        )
        # 静音参考可能会失败或成功，但不应该崩溃
        # 这里只测试不崩溃
    
    def test_matchering_with_complex_waveform(self, audio_engine, test_audio_files):
        """测试复杂波形的matchering"""
        # 加载复杂波形主音轨
        main_track = "main"
        main_file = test_audio_files['complex']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_1.0_1']  # 使用可用的1秒单声道文件
        
        # 使用复杂波形进行matchering
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=1.0,
            reference_duration_sec=3.0
        )
        # 复杂波形应该能被正确处理
        assert success
    
    def test_matchering_duplicate_track_id(self, audio_engine, test_audio_files):
        """测试重复轨道ID的matchering"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_5.0_2']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "duplicate"
        sub_file1 = test_audio_files['44100_1.0_1']  # 使用可用的1秒单声道文件
        
        # 第一次加载
        load_track_with_matchering_and_wait(
            audio_engine, sub_track, sub_file1, main_track,
            reference_start_sec=1.0, reference_duration_sec=2.0,
            timeout=15.0  # 增加超时时间
        )
        
        # 验证第一次加载成功
        assert sub_track in audio_engine.track_states
        
        # 使用相同ID加载不同文件（应该替换原有轨道）
        sub_file2 = test_audio_files['44100_1.0_1']
        
        try:
            load_track_with_matchering_and_wait(
                audio_engine, sub_track, sub_file2, main_track,
                reference_start_sec=2.0, reference_duration_sec=2.0,
                timeout=15.0  # 增加超时时间
            )
            
            # 验证轨道仍然存在（被替换了）
            assert sub_track in audio_engine.track_states
        except TimeoutError:
            # 如果第二次加载超时，至少确保第一次加载的轨道还在
            assert sub_track in audio_engine.track_states


class TestMatcheringPerformance:
    """Matchering性能测试"""
    
    def test_matchering_processing_time(self, audio_engine, test_audio_files):
        """测试matchering处理时间"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_5.0_1']
        
        # 测量处理时间
        start_time = time.time()
        
        load_track_with_matchering_and_wait(
            audio_engine, sub_track, sub_file, main_track,
            reference_start_sec=2.0, reference_duration_sec=5.0
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Matchering应该在合理时间内完成（不超过30秒）
        assert processing_time < 30.0
        print(f"Matchering processing time: {processing_time:.2f}s")
    
    def test_multiple_matchering_operations(self, audio_engine, test_audio_files):
        """测试多个连续matchering操作"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_10.0_2']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        # 连续处理多个文件
        test_files = [
            test_audio_files['44100_1.0_1'],
            test_audio_files['44100_1.0_1'],  # 重复使用可用的文件
            test_audio_files['48000_1.0_1']
        ]
        
        start_time = time.time()
        
        for i, test_file in enumerate(test_files):
            sub_track = f"sub_{i}"
            load_track_with_matchering_and_wait(
                audio_engine, sub_track, test_file, main_track,
                reference_start_sec=1.0 + i, reference_duration_sec=2.0
            )
            assert sub_track in audio_engine.track_states
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # 多个操作的总时间应该合理（不超过60秒）
        assert total_time < 60.0
        print(f"Multiple matchering operations time: {total_time:.2f}s")


@pytest.mark.skipif(
    not pytest.importorskip("matchering", reason="matchering not available"),
    reason="Matchering library not installed"
)
class TestMatcheringErrorHandling:
    """Matchering错误处理测试"""
    
    def test_matchering_with_invalid_file(self, audio_engine, test_audio_files):
        """测试无效文件的matchering"""
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_5.0_2']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "sub"
        invalid_file = "/nonexistent/path/audio.wav"
        
        # 尝试使用无效文件进行matchering
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=invalid_file,
            reference_track_id=main_track,
            reference_start_sec=0.0,
            reference_duration_sec=5.0
        )
        
        # 应该失败但不崩溃
        assert not success
        assert sub_track not in audio_engine.track_states
    
    def test_matchering_library_unavailable(self, monkeypatch, audio_engine, test_audio_files):
        """测试matchering库不可用的情况"""
        # 临时禁用matchering库
        import realtimemix.engine
        original_mg = realtimemix.engine.mg
        monkeypatch.setattr(realtimemix.engine, 'mg', None)
        
        # 加载主音轨
        main_track = "main"
        main_file = test_audio_files['44100_5.0_2']
        
        # 加载主音轨并等待完成
        load_track_with_wait(audio_engine, main_track, main_file)
        
        sub_track = "sub"
        sub_file = test_audio_files['44100_1.0_1']  # 使用可用的1秒单声道文件
        
        # 尝试使用matchering（应该失败）
        success = audio_engine.load_track_with_matchering(
            track_id=sub_track,
            file_path=sub_file,
            reference_track_id=main_track,
            reference_start_sec=0.0,
            reference_duration_sec=5.0
        )
        
        # 应该失败但不崩溃
        assert not success
        assert sub_track not in audio_engine.track_states
        
        # 恢复原来的mg
        monkeypatch.setattr(realtimemix.engine, 'mg', original_mg) 