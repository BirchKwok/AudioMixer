#!/usr/bin/env python3
"""
实时音频回调功能测试

这个脚本测试以下功能：
1. 播放主音轨
2. 在指定时间点实时插入回调音频
3. 插入音频时主音轨自动静音
4. 回调音频播放完毕后主音轨自动恢复音量

测试音频引擎的实时回调、静音/恢复、多轨道同步播放等核心功能
"""

import os
import sys
import time
import threading
import numpy as np
from typing import Optional, Callable, Dict, Any
from realtimemix import AudioEngine


class RealtimeCallbackTester:
    """实时音频回调功能测试器"""
    
    def __init__(self, sample_rate: int = 48000, buffer_size: int = 1024, verbose: bool = True):
        """
        初始化测试器
        
        Args:
            sample_rate (int): 采样率
            buffer_size (int): 缓冲区大小
            verbose (bool): 是否显示详细日志
        """
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.verbose = verbose
        
        # 初始化音频引擎
        self.engine = AudioEngine(
            sample_rate=sample_rate,
            buffer_size=buffer_size,
            channels=2,
            enable_streaming=False,  # 使用预加载模式以确保精确控制
            max_tracks=16
        )
        
        # 测试状态记录
        self.test_results = {
            'callback_triggered': False,
            'main_track_muted': False,
            'callback_audio_played': False,
            'main_track_restored': False,
            'timing_precision': [],
            'volume_changes': []
        }
        
        # 回调音频状态
        self.callback_audio_info = {
            'track_id': None,
            'duration': 0.0,
            'start_time': None,
            'end_time': None
        }
        
        # 主音轨原始音量
        self.main_track_original_volume = 1.0
        
        self._print("✅ 实时音频回调测试器初始化完成")
    
    def _print(self, message: str, level: str = "INFO"):
        """打印日志消息"""
        if not self.verbose:
            return
            
        prefix_map = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "TEST": "🧪"
        }
        
        prefix = prefix_map.get(level, "ℹ️")
        print(f"{prefix} {message}")
    
    def generate_test_audio(self, duration: float, frequency: float = 440.0) -> np.ndarray:
        """
        生成测试音频数据
        
        Args:
            duration (float): 音频时长（秒）
            frequency (float): 频率（Hz）
            
        Returns:
            np.ndarray: 立体声音频数据
        """
        frames = int(duration * self.sample_rate)
        t = np.linspace(0, duration, frames, False)
        
        # 生成正弦波
        audio_signal = np.sin(2 * np.pi * frequency * t) * 0.5
        
        # 添加包络以避免突变
        envelope = np.ones_like(audio_signal)
        fade_frames = int(0.01 * self.sample_rate)  # 10ms渐变
        
        # 渐入
        envelope[:fade_frames] = np.linspace(0, 1, fade_frames)
        # 渐出
        envelope[-fade_frames:] = np.linspace(1, 0, fade_frames)
        
        audio_signal *= envelope
        
        # 转换为立体声
        return np.column_stack((audio_signal, audio_signal)).astype(np.float32)
    
    def start_engine(self) -> bool:
        """启动音频引擎"""
        try:
            self.engine.start()
            self._print("音频引擎启动成功", "SUCCESS")
            return True
        except Exception as e:
            self._print(f"音频引擎启动失败: {e}", "ERROR")
            return False
    
    def stop_engine(self):
        """停止音频引擎"""
        try:
            self.engine.shutdown()
            self._print("音频引擎已停止", "SUCCESS")
        except Exception as e:
            self._print(f"音频引擎停止失败: {e}", "ERROR")
    
    def load_test_tracks(self) -> bool:
        """加载测试音轨"""
        try:
            # 生成主音轨 (15秒, 440Hz)
            main_audio = self.generate_test_audio(duration=15.0, frequency=440.0)
            success = self.engine.load_track("main_track", main_audio, sample_rate=self.sample_rate)
            if not success:
                self._print("主音轨加载失败", "ERROR")
                return False
            
            # 生成回调音频 (3秒, 880Hz - 高音)
            callback_audio = self.generate_test_audio(duration=3.0, frequency=880.0)
            success = self.engine.load_track("callback_audio", callback_audio, sample_rate=self.sample_rate)
            if not success:
                self._print("回调音频加载失败", "ERROR")
                return False
            
            # 等待轨道完全加载
            time.sleep(0.5)
            
            # 验证轨道加载状态
            if not self.engine.is_track_loaded("main_track"):
                self._print("主音轨未正确加载", "ERROR")
                return False
                
            if not self.engine.is_track_loaded("callback_audio"):
                self._print("回调音频未正确加载", "ERROR")
                return False
            
            self._print("所有测试音轨加载成功", "SUCCESS")
            return True
            
        except Exception as e:
            self._print(f"加载测试音轨失败: {e}", "ERROR")
            return False
    
    def audio_insertion_callback(self, track_id: str, target_time: float, actual_time: float):
        """
        音频插入回调函数
        
        在指定时间点触发，执行：
        1. 主音轨静音
        2. 播放回调音频
        3. 记录时间精度
        """
        try:
            self._print(f"🎯 回调触发! 目标时间: {target_time:.3f}s, 实际时间: {actual_time:.3f}s", "TEST")
            
            # 记录回调触发
            self.test_results['callback_triggered'] = True
            precision_ms = abs(actual_time - target_time) * 1000
            self.test_results['timing_precision'].append(precision_ms)
            self._print(f"⏱️ 时间精度: {precision_ms:.2f}ms")
            
            # 记录主音轨原始音量
            main_info = self.engine.get_track_info("main_track")
            if main_info:
                self.main_track_original_volume = main_info.get('volume', 1.0)
            
            # 1. 主音轨静音
            self._print("🔇 主音轨静音中...")
            success = self.engine.mute("main_track")
            if success:
                self.test_results['main_track_muted'] = True
                self.test_results['volume_changes'].append({
                    'time': time.time(),
                    'action': 'mute_main',
                    'success': True
                })
                self._print("✅ 主音轨已静音")
            else:
                self._print("❌ 主音轨静音失败", "ERROR")
                return
            
            # 2. 播放回调音频
            self._print("🔊 开始播放回调音频...")
            callback_info = self.engine.get_track_info("callback_audio")
            if callback_info:
                self.callback_audio_info['duration'] = callback_info.get('duration', 3.0)
                self.callback_audio_info['track_id'] = "callback_audio"
                self.callback_audio_info['start_time'] = time.time()
            
            # 播放回调音频
            self.engine.play("callback_audio", volume=0.8)
            self.test_results['callback_audio_played'] = True
            self._print("✅ 回调音频开始播放")
            
            # 启动定时器来恢复主音轨
            recovery_delay = self.callback_audio_info['duration'] + 0.1  # 额外100ms确保播放完成
            recovery_timer = threading.Timer(recovery_delay, self._restore_main_track)
            recovery_timer.start()
            
        except Exception as e:
            self._print(f"回调处理失败: {e}", "ERROR")
    
    def _restore_main_track(self):
        """恢复主音轨播放"""
        try:
            self._print("🔊 恢复主音轨播放...")
            
            # 停止回调音频
            self.engine.stop("callback_audio", fade_out=False)
            self.callback_audio_info['end_time'] = time.time()
            
            # 恢复主音轨
            success = self.engine.unmute("main_track")
            if success:
                self.test_results['main_track_restored'] = True
                self.test_results['volume_changes'].append({
                    'time': time.time(),
                    'action': 'restore_main',
                    'success': True
                })
                self._print("✅ 主音轨已恢复播放", "SUCCESS")
            else:
                self._print("❌ 主音轨恢复失败", "ERROR")
                
        except Exception as e:
            self._print(f"主音轨恢复失败: {e}", "ERROR")
    
    def run_test(self, callback_time: float = 5.0, main_track_duration: float = 12.0) -> Dict[str, Any]:
        """
        运行实时回调测试
        
        Args:
            callback_time (float): 回调触发时间（秒）
            main_track_duration (float): 主音轨播放总时长（秒）
            
        Returns:
            Dict[str, Any]: 测试结果
        """
        try:
            self._print("🧪 开始实时音频回调功能测试", "TEST")
            self._print(f"📋 测试参数: 回调时间={callback_time}s, 主音轨时长={main_track_duration}s")
            
            # 注册位置回调
            self._print(f"📝 注册位置回调 (时间点: {callback_time}s)")
            success = self.engine.register_position_callback(
                track_id="main_track",
                target_time=callback_time,
                callback_func=self.audio_insertion_callback,
                tolerance=0.015  # 15ms容忍度
            )
            
            if not success:
                self._print("位置回调注册失败", "ERROR")
                return self.test_results
            
            self._print("✅ 位置回调注册成功")
            
            # 开始播放主音轨
            self._print("🎵 开始播放主音轨...")
            self.engine.play("main_track", volume=0.7)
            start_time = time.time()
            
            # 监控播放状态
            self._print(f"⏳ 播放监控中... (总时长: {main_track_duration}s)")
            
            while time.time() - start_time < main_track_duration:
                # 获取当前播放状态
                main_info = self.engine.get_track_info("main_track")
                callback_info = self.engine.get_track_info("callback_audio")
                
                current_time = time.time() - start_time
                
                if self.verbose and int(current_time) % 2 == 0 and current_time - int(current_time) < 0.1:
                    playing_tracks = self.engine.get_playing_tracks()
                    self._print(f"⏱️  {current_time:.1f}s - 播放中的轨道: {playing_tracks}")
                
                time.sleep(0.1)
            
            # 停止所有播放
            self._print("⏹️  停止所有播放...")
            self.engine.stop_all_tracks(fade_out=False)
            
            # 生成测试报告
            return self._generate_test_report()
            
        except Exception as e:
            self._print(f"测试执行失败: {e}", "ERROR")
            return self.test_results
    
    def _generate_test_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        report = {
            'test_passed': False,
            'details': self.test_results.copy(),
            'summary': {}
        }
        
        # 检查各项测试是否通过
        tests_passed = [
            self.test_results['callback_triggered'],
            self.test_results['main_track_muted'],
            self.test_results['callback_audio_played'],
            self.test_results['main_track_restored']
        ]
        
        report['test_passed'] = all(tests_passed)
        
        # 生成摘要
        report['summary'] = {
            'callback_triggered': self.test_results['callback_triggered'],
            'main_track_muted': self.test_results['main_track_muted'],
            'callback_audio_played': self.test_results['callback_audio_played'],
            'main_track_restored': self.test_results['main_track_restored'],
            'timing_precision_ms': self.test_results['timing_precision'],
            'average_precision_ms': np.mean(self.test_results['timing_precision']) if self.test_results['timing_precision'] else 0.0,
            'volume_change_count': len(self.test_results['volume_changes'])
        }
        
        return report
    
    def print_test_report(self, report: Dict[str, Any]):
        """打印测试报告"""
        print("\n" + "="*60)
        print("🧪 实时音频回调功能测试报告")
        print("="*60)
        
        if report.get('test_passed', False):
            print("🎉 测试结果: 通过 ✅")
        else:
            print("❌ 测试结果: 失败")
        
        print("\n📊 详细结果:")
        summary = report['summary']
        
        print(f"  • 回调触发: {'✅' if summary['callback_triggered'] else '❌'}")
        print(f"  • 主音轨静音: {'✅' if summary['main_track_muted'] else '❌'}")
        print(f"  • 回调音频播放: {'✅' if summary['callback_audio_played'] else '❌'}")
        print(f"  • 主音轨恢复: {'✅' if summary['main_track_restored'] else '❌'}")
        
        if summary['timing_precision_ms']:
            print(f"  • 平均时间精度: {summary['average_precision_ms']:.2f}ms")
            print(f"  • 音量变更次数: {summary['volume_change_count']}")
        
        print("\n" + "="*60)


def main():
    """主测试程序"""
    print("🎵 RealtimeMix 实时音频回调功能测试")
    print("="*50)
    print("测试功能:")
    print("  1. 主音轨播放")
    print("  2. 定时音频插入")
    print("  3. 主音轨自动静音")
    print("  4. 回调音频播放")
    print("  5. 主音轨自动恢复")
    print("="*50)
    
    # 创建测试器
    tester = RealtimeCallbackTester(verbose=True)
    
    try:
        # 启动音频引擎
        if not tester.start_engine():
            return False
        
        # 加载测试音轨
        if not tester.load_test_tracks():
            return False
        
        # 运行测试
        print("\n🚀 开始测试...")
        report = tester.run_test(
            callback_time=5.0,  # 5秒时插入音频
            main_track_duration=12.0  # 总播放时长12秒
        )
        
        # 打印报告
        tester.print_test_report(report)
        
        return report['test_passed']
        
    except KeyboardInterrupt:
        print("\n⏹️  测试被用户中断")
        return False
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        return False
    finally:
        # 清理资源
        tester.stop_engine()


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