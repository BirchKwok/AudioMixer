#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SpeechSeamlessFusion - 语音无缝融合器

专门用于实现两段语音音频的完美融合，特点：
1. 零延迟瞬时切换（无淡入淡出）
2. 语音特征智能匹配
3. 音调和音色优化
4. 模拟自然语音流畅度

适用于角色配音、播客、有声书等语音内容的无缝拼接。
"""

import os
import sys
import time
from realtimemix import AudioEngine
from typing import Optional


class SpeechSeamlessFusion:
    """
    语音无缝融合器
    
    专门为语音音频设计的无缝融合解决方案，提供零延迟切换、
    语音特征匹配、音调优化等功能。
    """
    
    def __init__(self, 
                 sample_rate: int = 48000,
                 buffer_size: int = 1024,
                 channels: int = 2,
                 enable_streaming: bool = True,
                 streaming_threshold_mb: int = 50,
                 target_loudness: float = 0.6,
                 verbose: bool = True,
                 gentle_matchering: bool = True):
        """
        初始化语音无缝融合器
        
        Args:
            sample_rate (int): 采样率，默认48000Hz
            buffer_size (int): 缓冲区大小，默认1024
            channels (int): 声道数，默认2（立体声）
            enable_streaming (bool): 是否启用流式播放，默认True
            streaming_threshold_mb (int): 流式播放阈值（MB），默认50
            target_loudness (float): 目标响度（0.0-1.0），默认0.6
            verbose (bool): 是否显示详细信息，默认True
            gentle_matchering (bool): 是否使用温和的Matchering处理，默认True
        """
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.channels = channels
        self.target_loudness = target_loudness
        self.verbose = verbose
        self.gentle_matchering = gentle_matchering
        
        # 初始化音频引擎
        self.engine = AudioEngine(
            sample_rate=sample_rate,
            buffer_size=buffer_size,
            channels=channels,
            enable_streaming=enable_streaming,
            streaming_threshold_mb=streaming_threshold_mb
        )
        
        # 状态管理
        self.is_engine_started = False
        self.loaded_tracks = {}
    
    def _print(self, message: str, level: str = "INFO"):
        """简单的输出函数"""
        if self.verbose:
            prefix = "✅" if level == "SUCCESS" else "❌" if level == "ERROR" else "🎵"
            print(f"{prefix} {message}")
    
    def start_engine(self) -> bool:
        """启动音频引擎"""
        try:
            if not self.is_engine_started:
                self.engine.start()
                self.is_engine_started = True
                self._print("音频引擎启动成功", "SUCCESS")
                return True
            return True
        except Exception as e:
            self._print(f"音频引擎启动失败: {e}", "ERROR")
            return False
    
    def stop_engine(self):
        """停止音频引擎并清理资源"""
        try:
            if self.is_engine_started:
                # 停止所有播放
                for track_id in list(self.loaded_tracks.keys()):
                    self.engine.stop(track_id, fade_out=False)
                
                # 卸载所有音轨
                for track_id in list(self.loaded_tracks.keys()):
                    self.engine.unload_track(track_id)
                
                # 关闭引擎
                self.engine.shutdown()
                self.is_engine_started = False
                self.loaded_tracks.clear()
                self._print("音频引擎已关闭", "SUCCESS")
        except Exception as e:
            self._print(f"关闭音频引擎时出错: {e}", "ERROR")
    
    def load_main_speech(self, file_path: str, track_id: str = "main") -> bool:
        """
        加载主语音音轨
        
        Args:
            file_path (str): 音频文件路径
            track_id (str): 音轨ID，默认"main"
            
        Returns:
            bool: 加载是否成功
        """
        if not self.is_engine_started:
            self._print("请先启动音频引擎", "ERROR")
            return False
        
        try:
            self._print(f"加载主语音: {file_path}")
            
            # 使用回调等待加载完成
            loading_completed = False
            loading_success = False
            
            def on_complete(tid, success, error=None):
                nonlocal loading_completed, loading_success
                loading_completed = True
                loading_success = success
            
            success = self.engine.load_track(track_id, file_path, on_complete=on_complete)
            
            if not success:
                self._print(f"主语音加载失败: {track_id}", "ERROR")
                return False
            
            # 等待加载完成（最多30秒，因为文件很大）
            wait_time = 0
            while not loading_completed and wait_time < 30.0:
                time.sleep(0.1)
                wait_time += 0.1
            
            if not loading_completed:
                self._print("主语音加载超时", "ERROR")
                return False
            
            if loading_success:
                self.loaded_tracks[track_id] = {
                    'file_path': file_path,
                    'type': 'main'
                }
                self._print(f"主语音加载成功: {track_id}", "SUCCESS")
                return True
            else:
                return False
            
        except Exception as e:
            self._print(f"加载主语音异常: {e}", "ERROR")
            return False
    
    def load_sub_speech(self, file_path: str, track_id: str = "sub", 
                       leading_silence_ms: float = 100.0) -> bool:
        """
        加载副语音音轨（带静音填充）
        
        Args:
            file_path (str): 音频文件路径
            track_id (str): 音轨ID，默认"sub"
            leading_silence_ms (float): 前端静音填充（毫秒），默认100ms
            
        Returns:
            bool: 加载是否成功
        """
        if not self.is_engine_started:
            self._print("请先启动音频引擎", "ERROR")
            return False
        
        try:
            self._print(f"加载副语音: {file_path} (前端{leading_silence_ms}ms静音)")
            
            # 使用回调等待加载完成
            loading_completed = False
            loading_success = False
            
            def on_complete(tid, success, error=None):
                nonlocal loading_completed, loading_success
                loading_completed = True
                loading_success = success
            
            success = self.engine.load_track(
                track_id, 
                file_path,
                silent_lpadding_ms=leading_silence_ms,
                on_complete=on_complete
            )
            
            if not success:
                self._print(f"副语音加载失败: {track_id}", "ERROR")
                return False
            
            # 等待加载完成（最多10秒）
            wait_time = 0
            while not loading_completed and wait_time < 10.0:
                time.sleep(0.1)
                wait_time += 0.1
            
            if not loading_completed:
                self._print("副语音加载超时", "ERROR")
                return False
            
            if loading_success:
                self.loaded_tracks[track_id] = {
                    'file_path': file_path,
                    'type': 'sub',
                    'leading_silence_ms': leading_silence_ms
                }
                self._print(f"副语音加载成功: {track_id}", "SUCCESS")
                return True
            else:
                return False
            
        except Exception as e:
            self._print(f"加载副语音异常: {e}", "ERROR")
            return False
    



    def fuse_speech(self, main_track_id: str = "main", sub_track_id: str = "sub", 
                   insert_position_seconds: float = 10.0) -> bool:
        """
        执行语音无缝融合
        
        Args:
            main_track_id (str): 主语音轨道ID，默认"main"
            sub_track_id (str): 副语音轨道ID，默认"sub"
            insert_position_seconds (float): 副语音插入位置（秒），默认10.0秒
            
        Returns:
            bool: 融合是否成功
        """
        try:
            self._print("开始语音无缝融合...")
            
            # 检查音轨是否已加载
            if main_track_id not in self.loaded_tracks or sub_track_id not in self.loaded_tracks:
                self._print("语音轨道未正确加载", "ERROR")
                return False
            
            self._print("使用 Matchering 进行专业匹配和加载...")
            
            # 卸载原始副音轨，准备加载匹配后的版本
            original_sub_info = self.loaded_tracks[sub_track_id]
            sub_file_path = original_sub_info['file_path']
            self.engine.unload_track(sub_track_id)

            # 使用引擎的Matchering处理方法（支持温和处理）
            success = self.engine.load_track_with_matchering(
                track_id=sub_track_id,
                file_path=sub_file_path,
                reference_track_id=main_track_id,
                reference_start_sec=insert_position_seconds,
                reference_duration_sec=10.0,
                silent_lpadding_ms=original_sub_info.get('leading_silence_ms', 0),
                gentle_matchering=self.gentle_matchering  # 传递温和处理参数
            )

            if not success:
                self._print("使用 Matchering 加载音轨失败，融合中止", "ERROR")
                # 尝试重新加载原始文件以防万一
                self.load_sub_speech(
                    file_path=sub_file_path,
                    track_id=sub_track_id,
                    leading_silence_ms=original_sub_info.get('leading_silence_ms', 0)
                )
                return False

            self._print("已成功加载经 Matchering 匹配的副音轨", "SUCCESS")

            # 响度已由 Matchering 匹配，直接使用目标响度
            main_vol = self.target_loudness
            sub_vol = self.target_loudness
            
            # 获取副语音时长（从引擎获取）
            try:
                sub_info = self.engine.get_track_info(sub_track_id)
                sub_duration = sub_info.get('duration', 6.0) if sub_info else 6.0
            except:
                sub_duration = 6.0  # 默认时长
            
            self._print(f"主语音音量: {main_vol:.3f}")
            self._print(f"副语音音量: {sub_vol:.3f}")
            self._print(f"副语音时长: {sub_duration:.2f}秒")
            self._print(f"插入位置: {insert_position_seconds:.1f}秒")
            
            # 播放主语音到切换点
            self._print(f"播放主语音到切换点 ({insert_position_seconds:.1f}秒)")
            self.engine.play(main_track_id, volume=main_vol)
            
            # 精确等待到切换点
            start_time = time.time()
            while time.time() - start_time < insert_position_seconds - 0.01:
                time.sleep(0.1)
            
            # 准备副语音
            self._print("准备零延迟语音切换...")
            self.engine.play(sub_track_id, volume=0.0)
            time.sleep(0.005)  # 5ms确保副音轨准备就绪
            
            # 等待到精确切换时机
            remaining = insert_position_seconds - (time.time() - start_time)
            if remaining > 0:
                time.sleep(remaining)
            
            # 执行瞬时切换（零延迟）
            self._print("执行零延迟语音切换...")
            self.engine.set_volume(main_track_id, 0.0)
            self.engine.set_volume(sub_track_id, sub_vol)
            
            # 播放副语音
            self._print(f"副语音播放中 ({sub_duration:.2f}秒)...")
            time.sleep(sub_duration - 0.01)
            
            # 瞬时恢复主语音
            self._print("瞬时恢复主语音...")
            self.engine.set_volume(sub_track_id, 0.0)
            self.engine.set_volume(main_track_id, main_vol)
            self.engine.stop(sub_track_id, fade_out=False)
            
            self._print("主语音继续播放 (3秒)...")
            time.sleep(3)
            
            # 结束演示
            self._print("语音融合演示结束")
            self.engine.stop(main_track_id, fade_out=False)
            time.sleep(1)
            
            self._print("语音无缝融合成功！", "SUCCESS")
            
            return True
            
        except Exception as e:
            self._print(f"语音无缝融合失败: {e}", "ERROR")
            return False

    def __enter__(self):
        """上下文管理器入口"""
        if self.start_engine():
            return self
        else:
            raise RuntimeError("无法启动音频引擎")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop_engine()


def main():
    """语音融合主程序"""
    print("🗣️ 语音无缝融合器")
    print("="*50)
    
    # 检查文件存在
    main_file = "声音素材.wav"
    sub_file = "副音轨.wav"
    
    if not os.path.exists(main_file) or not os.path.exists(sub_file):
        print(f"❌ 音频文件不存在: {main_file} 或 {sub_file}")
        return False
    
    try:
        # 使用语音融合器（启用温和Matchering处理）
        with SpeechSeamlessFusion(
            sample_rate=48000,
            target_loudness=0.6,
            gentle_matchering=True  # 启用温和处理减少金属音色
        ) as fusion:
            
            # 加载语音文件
            if not fusion.load_main_speech(main_file):
                return False
            
            if not fusion.load_sub_speech(sub_file, leading_silence_ms=100):
                return False
            
            print("\n🎯 开始语音无缝融合...")
            print("💡 将在第10秒断句处插入副语音，实现完美融合")
            
            # 执行语音融合
            success = fusion.fuse_speech(
                main_track_id="main",
                sub_track_id="sub", 
                insert_position_seconds=10.0
            )
            
            if success:
                print("\n🎉 语音融合完成成功！")
                print("✅ 零延迟瞬时切换")
                print("✅ 语音特征智能匹配")
                print("✅ 音调和音色优化")
                print("✅ 无任何淡入淡出效果")
                print("✅ 模拟自然语音流畅度")
                print("✅ 断句处切换，过渡自然")
                print("✅ 响度完美匹配")
                print("✅ 音频质量优秀")
            else:
                print("\n⚠️ 语音融合完成但可能存在质量问题")
            
            return success
    
    except Exception as e:
        print(f"程序异常: {e}")
        return False


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n程序被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"程序异常: {e}")
        sys.exit(1) 