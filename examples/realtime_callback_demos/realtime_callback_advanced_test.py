#!/usr/bin/env python3
"""
高级实时音频回调功能测试

这个脚本测试更复杂的音频回调场景：
1. 多个回调点音频插入
2. 主音轨静音/恢复测试
3. 回调音频重叠处理
4. 精度和性能测试
5. 错误恢复测试
"""

import os
import sys
import time
import threading
import numpy as np
from typing import Optional, Callable, Dict, Any, List
from realtimemix import AudioEngine


class AdvancedCallbackTester:
    """高级实时音频回调功能测试器"""
    
    def __init__(self, sample_rate: int = 48000, buffer_size: int = 1024, verbose: bool = True):
        """初始化高级测试器"""
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.verbose = verbose
        
        # 初始化音频引擎
        self.engine = AudioEngine(
            sample_rate=sample_rate,
            buffer_size=buffer_size,
            channels=2,
            enable_streaming=False,
            max_tracks=32
        )
        
        # 测试结果记录
        self.test_results = {
            'callbacks': [],
            'mute_events': [],
            'unmute_events': [],
            'audio_insertions': [],
            'timing_precision': [],
            'test_passed': False
        }
        
        # 回调计数器
        self.callback_counter = 0
        self.active_callback_audio = None
        
        self._print("🚀 高级音频回调测试器初始化完成")
    
    def _print(self, message: str, level: str = "INFO"):
        """打印日志消息"""
        if not self.verbose:
            return
            
        prefix_map = {
            "INFO": "ℹ️",
            "SUCCESS": "✅", 
            "WARNING": "⚠️",
            "ERROR": "❌",
            "TEST": "🧪",
            "CALLBACK": "🎯"
        }
        
        prefix = prefix_map.get(level, "ℹ️")
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        print(f"[{timestamp}] {prefix} {message}")
    
    def generate_test_audio(self, duration: float, frequency: float = 440.0, 
                          amplitude: float = 0.5, modulation: Optional[str] = None) -> np.ndarray:
        """生成多样化的测试音频"""
        frames = int(duration * self.sample_rate)
        t = np.linspace(0, duration, frames, False)
        
        # 基础正弦波
        audio_signal = np.sin(2 * np.pi * frequency * t) * amplitude
        
        # 添加调制效果
        if modulation == "tremolo":
            # 颤音效果
            tremolo_freq = 5.0  # 5Hz颤音
            tremolo = 0.3 * np.sin(2 * np.pi * tremolo_freq * t) + 0.7
            audio_signal *= tremolo
        elif modulation == "sweep":
            # 频率扫描
            freq_sweep = frequency + 200 * t / duration
            audio_signal = np.sin(2 * np.pi * freq_sweep * t) * amplitude
        
        # 添加包络
        envelope = np.ones_like(audio_signal)
        fade_frames = int(0.05 * self.sample_rate)  # 50ms渐变
        
        if fade_frames > 0:
            envelope[:fade_frames] = np.linspace(0, 1, fade_frames)
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
        """加载多个测试音轨"""
        try:
            # 主音轨 (20秒, 440Hz低音)
            main_audio = self.generate_test_audio(
                duration=20.0, 
                frequency=220.0, 
                amplitude=0.6,
                modulation="tremolo"
            )
            success = self.engine.load_track("main_track", main_audio, sample_rate=self.sample_rate)
            if not success:
                self._print("主音轨加载失败", "ERROR")
                return False
            
            # 多个回调音频轨道
            callback_configs = [
                {"name": "callback_beep", "freq": 880.0, "duration": 1.5, "mod": None},
                {"name": "callback_chirp", "freq": 1320.0, "duration": 2.0, "mod": "sweep"},
                {"name": "callback_tone", "freq": 660.0, "duration": 1.0, "mod": "tremolo"},
                {"name": "callback_signal", "freq": 1760.0, "duration": 0.8, "mod": None},
            ]
            
            for config in callback_configs:
                audio = self.generate_test_audio(
                    duration=config["duration"],
                    frequency=config["freq"],
                    amplitude=0.8,
                    modulation=config["mod"]
                )
                success = self.engine.load_track(config["name"], audio, sample_rate=self.sample_rate)
                if not success:
                    self._print(f"回调音频 {config['name']} 加载失败", "ERROR")
                    return False
            
            # 等待加载完成
            time.sleep(0.5)
            
            # 验证所有轨道加载状态
            track_names = ["main_track"] + [c["name"] for c in callback_configs]
            for track_name in track_names:
                if not self.engine.is_track_loaded(track_name):
                    self._print(f"轨道 {track_name} 未正确加载", "ERROR")
                    return False
            
            self._print(f"成功加载 {len(track_names)} 个测试音轨", "SUCCESS")
            return True
            
        except Exception as e:
            self._print(f"加载测试音轨失败: {e}", "ERROR")
            return False
    
    def create_callback_handler(self, callback_id: str, audio_track: str) -> Callable:
        """创建特定回调处理器"""
        def callback_handler(track_id: str, target_time: float, actual_time: float):
            try:
                self.callback_counter += 1
                precision_ms = abs(actual_time - target_time) * 1000
                
                self._print(f"回调 #{self.callback_counter} [{callback_id}] 触发!", "CALLBACK")
                self._print(f"  目标时间: {target_time:.3f}s, 实际时间: {actual_time:.3f}s", "CALLBACK")
                self._print(f"  时间精度: {precision_ms:.2f}ms", "CALLBACK")
                
                # 记录回调事件
                callback_event = {
                    'callback_id': callback_id,
                    'target_time': target_time,
                    'actual_time': actual_time,
                    'precision_ms': precision_ms,
                    'audio_track': audio_track,
                    'timestamp': time.time()
                }
                self.test_results['callbacks'].append(callback_event)
                self.test_results['timing_precision'].append(precision_ms)
                
                # 如果有音频正在播放，等待其完成
                if self.active_callback_audio:
                    self._print(f"等待前一个回调音频完成...", "WARNING")
                    return
                
                # 执行音频插入流程
                self._execute_audio_insertion(audio_track, callback_id)
                
            except Exception as e:
                self._print(f"回调处理器错误: {e}", "ERROR")
        
        return callback_handler
    
    def _execute_audio_insertion(self, audio_track: str, callback_id: str):
        """执行音频插入流程"""
        try:
            # 1. 主音轨静音
            self._print(f"[{callback_id}] 主音轨静音...", "CALLBACK")
            mute_success = self.engine.mute("main_track")
            mute_event = {
                'callback_id': callback_id,
                'success': mute_success,
                'timestamp': time.time()
            }
            self.test_results['mute_events'].append(mute_event)
            
            if not mute_success:
                self._print(f"[{callback_id}] 主音轨静音失败", "ERROR")
                return
            
            # 2. 播放回调音频
            self._print(f"[{callback_id}] 播放回调音频: {audio_track}", "CALLBACK")
            self.active_callback_audio = audio_track
            self.engine.play(audio_track, volume=0.9)
            
            # 记录音频插入
            audio_insertion = {
                'callback_id': callback_id,
                'audio_track': audio_track,
                'start_time': time.time(),
                'timestamp': time.time()
            }
            self.test_results['audio_insertions'].append(audio_insertion)
            
            # 3. 获取音频时长并启动恢复定时器
            track_info = self.engine.get_track_info(audio_track)
            if track_info:
                duration = track_info.get('duration', 1.0)
                recovery_delay = duration + 0.05  # 额外50ms确保播放完成
                
                self._print(f"[{callback_id}] 设置恢复定时器: {recovery_delay:.2f}s", "CALLBACK")
                recovery_timer = threading.Timer(
                    recovery_delay, 
                    self._restore_main_track, 
                    args=(callback_id, audio_track)
                )
                recovery_timer.start()
            else:
                self._print(f"[{callback_id}] 无法获取音频时长信息", "WARNING")
                # 使用默认恢复时间
                recovery_timer = threading.Timer(1.5, self._restore_main_track, args=(callback_id, audio_track))
                recovery_timer.start()
                
        except Exception as e:
            self._print(f"音频插入执行失败: {e}", "ERROR")
    
    def _restore_main_track(self, callback_id: str, audio_track: str):
        """恢复主音轨播放"""
        try:
            self._print(f"[{callback_id}] 恢复主音轨播放...", "CALLBACK")
            
            # 停止回调音频
            self.engine.stop(audio_track, fade_out=False)
            self.active_callback_audio = None
            
            # 恢复主音轨
            unmute_success = self.engine.unmute("main_track")
            unmute_event = {
                'callback_id': callback_id,
                'audio_track': audio_track,
                'success': unmute_success,
                'timestamp': time.time()
            }
            self.test_results['unmute_events'].append(unmute_event)
            
            if unmute_success:
                self._print(f"[{callback_id}] 主音轨已恢复", "SUCCESS")
            else:
                self._print(f"[{callback_id}] 主音轨恢复失败", "ERROR")
                
        except Exception as e:
            self._print(f"主音轨恢复失败: {e}", "ERROR")
    
    def run_multiple_callback_test(self) -> Dict[str, Any]:
        """运行多个回调点测试"""
        try:
            self._print("开始多个回调点测试", "TEST")
            
            # 配置多个回调点
            callback_configs = [
                {'time': 3.0, 'audio': 'callback_beep', 'id': 'beep_3s'},
                {'time': 7.5, 'audio': 'callback_chirp', 'id': 'chirp_7.5s'},
                {'time': 12.0, 'audio': 'callback_tone', 'id': 'tone_12s'},
                {'time': 16.5, 'audio': 'callback_signal', 'id': 'signal_16.5s'},
            ]
            
            # 注册所有回调
            for config in callback_configs:
                handler = self.create_callback_handler(config['id'], config['audio'])
                success = self.engine.register_position_callback(
                    track_id="main_track",
                    target_time=config['time'],
                    callback_func=handler,
                    tolerance=0.020  # 20ms容忍度
                )
                
                if not success:
                    self._print(f"回调 {config['id']} 注册失败", "ERROR")
                    return self.test_results
                
                self._print(f"注册回调: {config['id']} @ {config['time']}s", "TEST")
            
            # 开始播放主音轨
            self._print("开始播放主音轨...", "TEST")
            self.engine.play("main_track", volume=0.7)
            start_time = time.time()
            
            # 监控播放状态
            total_duration = 20.0
            self._print(f"监控播放状态 ({total_duration}s)...", "TEST")
            
            last_status_time = 0
            while time.time() - start_time < total_duration:
                current_time = time.time() - start_time
                
                # 每2秒显示一次状态
                if current_time - last_status_time >= 2.0:
                    playing_tracks = self.engine.get_playing_tracks()
                    main_info = self.engine.get_track_info("main_track")
                    is_muted = self.engine.is_muted("main_track")
                    
                    self._print(f"⏱️  {current_time:.1f}s - 播放轨道: {playing_tracks}, 主音轨静音: {is_muted}")
                    last_status_time = current_time
                
                time.sleep(0.1)
            
            # 停止所有播放
            self._print("停止所有播放...", "TEST")
            self.engine.stop_all_tracks(fade_out=False)
            
            # 生成测试报告
            return self._generate_advanced_report()
            
        except Exception as e:
            self._print(f"多回调测试执行失败: {e}", "ERROR")
            return self.test_results
    
    def _generate_advanced_report(self) -> Dict[str, Any]:
        """生成高级测试报告"""
        report = {
            'test_passed': False,
            'summary': {},
            'details': self.test_results.copy(),
            'statistics': {}
        }
        
        # 计算统计信息
        callbacks_count = len(self.test_results['callbacks'])
        mute_events_count = len(self.test_results['mute_events'])
        unmute_events_count = len(self.test_results['unmute_events'])
        audio_insertions_count = len(self.test_results['audio_insertions'])
        
        # 检查测试是否通过
        callbacks_success = callbacks_count > 0
        mute_success = mute_events_count > 0 and all(e['success'] for e in self.test_results['mute_events'])
        unmute_success = unmute_events_count > 0 and all(e['success'] for e in self.test_results['unmute_events'])
        insertion_success = audio_insertions_count > 0
        
        report['test_passed'] = all([callbacks_success, mute_success, unmute_success, insertion_success])
        
        # 生成摘要
        report['summary'] = {
            'callbacks_triggered': callbacks_count,
            'mute_events': mute_events_count,
            'unmute_events': unmute_events_count,
            'audio_insertions': audio_insertions_count,
            'all_mutes_successful': mute_success,
            'all_unmutes_successful': unmute_success,
        }
        
        # 生成精度统计
        if self.test_results['timing_precision']:
            precisions = self.test_results['timing_precision']
            report['statistics'] = {
                'average_precision_ms': np.mean(precisions),
                'max_precision_ms': np.max(precisions),
                'min_precision_ms': np.min(precisions),
                'std_precision_ms': np.std(precisions),
                'precision_under_10ms': sum(1 for p in precisions if p <= 10.0) / len(precisions),
                'precision_under_20ms': sum(1 for p in precisions if p <= 20.0) / len(precisions),
            }
        
        return report
    
    def print_advanced_report(self, report: Dict[str, Any]):
        """打印高级测试报告"""
        print("\n" + "="*70)
        print("🧪 高级实时音频回调功能测试报告")
        print("="*70)
        
        if report.get('test_passed', False):
            print("🎉 测试结果: 全部通过 ✅")
        else:
            print("❌ 测试结果: 部分失败")
        
        summary = report.get('summary', {})
        print(f"\n📊 测试摘要:")
        print(f"  • 回调触发次数: {summary.get('callbacks_triggered', 0)}")
        print(f"  • 主音轨静音事件: {summary.get('mute_events', 0)}")
        print(f"  • 主音轨恢复事件: {summary.get('unmute_events', 0)}")
        print(f"  • 音频插入次数: {summary.get('audio_insertions', 0)}")
        print(f"  • 静音操作成功率: {'✅' if summary.get('all_mutes_successful', False) else '❌'}")
        print(f"  • 恢复操作成功率: {'✅' if summary.get('all_unmutes_successful', False) else '❌'}")
        
        stats = report.get('statistics', {})
        if stats:
            print(f"\n📈 精度统计:")
            print(f"  • 平均精度: {stats.get('average_precision_ms', 0):.2f}ms")
            print(f"  • 最佳精度: {stats.get('min_precision_ms', 0):.2f}ms")
            print(f"  • 最差精度: {stats.get('max_precision_ms', 0):.2f}ms")
            print(f"  • 精度标准差: {stats.get('std_precision_ms', 0):.2f}ms")
            print(f"  • <10ms 成功率: {stats.get('precision_under_10ms', 0)*100:.1f}%")
            print(f"  • <20ms 成功率: {stats.get('precision_under_20ms', 0)*100:.1f}%")
        
        print("\n" + "="*70)


def main():
    """主测试程序"""
    print("🎵 RealtimeMix 高级实时音频回调功能测试")
    print("="*60)
    print("测试场景:")
    print("  1. 多个时间点回调音频插入")
    print("  2. 主音轨静音/恢复自动化")
    print("  3. 回调音频重叠处理")
    print("  4. 高精度时间控制")
    print("  5. 系统性能和稳定性")
    print("="*60)
    
    # 创建高级测试器
    tester = AdvancedCallbackTester(verbose=True)
    
    try:
        # 启动音频引擎
        if not tester.start_engine():
            return False
        
        # 加载测试音轨
        if not tester.load_test_tracks():
            return False
        
        # 运行高级测试
        print("\n🚀 开始高级测试...")
        report = tester.run_multiple_callback_test()
        
        # 打印详细报告
        tester.print_advanced_report(report)
        
        return report.get('test_passed', False)
        
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