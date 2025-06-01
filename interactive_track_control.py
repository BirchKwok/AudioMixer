#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交互式音轨控制台
提供实时的音轨管理界面
"""

import time
import threading
import os
import numpy as np
from audiomixer import AudioEngine

class InteractiveTrackController:
    def __init__(self):
        self.engine = AudioEngine(sample_rate=48000, buffer_size=1024, channels=2)
        self.running = True
        
    def generate_test_tone(self, frequency, duration=10):
        """生成测试音调"""
        t = np.linspace(0, duration, int(self.engine.sample_rate * duration), False)
        audio = 0.3 * np.sin(2 * np.pi * frequency * t)
        # 添加淡入淡出
        fade_samples = int(0.1 * self.engine.sample_rate)
        envelope = np.ones_like(audio)
        envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
        audio *= envelope
        
        stereo_audio = np.column_stack([audio, audio])
        return stereo_audio.astype(np.float32)
    
    def show_help(self):
        """显示帮助信息"""
        print("\n=== 音轨控制命令 ===")
        print("1. add <track_id> <frequency>  - 添加测试音轨")
        print("2. load <track_id> <file_path> - 从文件加载音轨")
        print("3. play <track_id>             - 播放音轨")
        print("4. pause <track_id>            - 暂停音轨")
        print("5. resume <track_id>           - 恢复音轨")
        print("6. stop <track_id>             - 停止音轨")
        print("7. remove <track_id>           - 移除音轨")
        print("8. volume <track_id> <0.0-1.0> - 设置音量")
        print("9. loop <track_id> <on/off>    - 设置循环")
        print("10. speed <track_id> <factor>  - 设置播放速度")
        print("11. seek <track_id> <seconds>  - 跳转到指定位置")
        print("")
        print("=== 批量操作 ===")
        print("12. pause_all    - 暂停所有音轨")
        print("13. resume_all   - 恢复所有音轨")
        print("14. stop_all     - 停止所有音轨")
        print("15. clear_all    - 清空所有音轨")
        print("")
        print("=== 查询命令 ===")
        print("16. list         - 显示所有音轨")
        print("17. status       - 显示状态统计")
        print("18. info <track_id> - 显示音轨详细信息")
        print("19. playing      - 显示正在播放的音轨")
        print("20. paused       - 显示暂停的音轨")
        print("")
        print("21. help         - 显示此帮助")
        print("22. quit         - 退出程序")
        print("=" * 40)
    
    def show_track_list(self):
        """显示音轨列表"""
        tracks = self.engine.list_tracks()
        if not tracks:
            print("没有已加载的音轨")
            return
        
        print(f"\n已加载的音轨 ({len(tracks)} 个):")
        print("-" * 80)
        print(f"{'音轨ID':<15} {'时长':<8} {'位置':<8} {'音量':<6} {'状态':<8} {'循环':<4} {'速度':<6}")
        print("-" * 80)
        
        for track in tracks:
            status = "播放中" if track['playing'] and not track['paused'] else \
                    "暂停" if track['paused'] else "停止"
            loop_str = "是" if track['loop'] else "否"
            
            print(f"{track['track_id']:<15} "
                  f"{track['duration']:.1f}s{' ':<3} "
                  f"{track['position']:.1f}s{' ':<3} "
                  f"{track['volume']:.2f}{' ':<2} "
                  f"{status:<8} "
                  f"{loop_str:<4} "
                  f"{track['speed']:.2f}")
    
    def show_status(self):
        """显示状态统计"""
        stats = self.engine.get_track_count()
        perf = self.engine.get_performance_stats()
        
        print(f"\n=== 系统状态 ===")
        print(f"音轨总数: {stats['total']}/{stats['max_tracks']}")
        print(f"正在播放: {stats['playing']}")
        print(f"暂停中: {stats['paused']}")
        print(f"已停止: {stats['stopped']}")
        print(f"可用槽位: {stats['available_slots']}")
        print(f"CPU使用率: {perf['cpu_usage']:.1f}%")
        print(f"峰值电平: {perf['peak_level']:.3f}")
        print(f"缓冲区欠载: {perf['underrun_count']}")
    
    def process_command(self, command):
        """处理用户命令"""
        try:
            parts = command.strip().split()
            if not parts:
                return True
            
            cmd = parts[0].lower()
            
            if cmd == "help":
                self.show_help()
            
            elif cmd == "quit":
                return False
            
            elif cmd == "add":
                if len(parts) < 3:
                    print("用法: add <track_id> <frequency>")
                    return True
                track_id = parts[1]
                frequency = float(parts[2])
                audio = self.generate_test_tone(frequency)
                self.engine.load_track(track_id, audio)
                print(f"已添加测试音轨: {track_id} ({frequency}Hz)")
            
            elif cmd == "load":
                if len(parts) < 3:
                    print("用法: load <track_id> <file_path>")
                    return True
                track_id = parts[1]
                file_path = " ".join(parts[2:])  # 支持带空格的路径
                if os.path.exists(file_path):
                    def on_complete(tid, success, error=None):
                        if success:
                            print(f"成功加载音轨: {tid}")
                        else:
                            print(f"加载失败: {tid} - {error}")
                    self.engine.load_track(track_id, file_path, on_complete=on_complete)
                    print(f"正在加载: {track_id} <- {file_path}")
                else:
                    print(f"文件不存在: {file_path}")
            
            elif cmd == "play":
                if len(parts) < 2:
                    print("用法: play <track_id>")
                    return True
                track_id = parts[1]
                if self.engine.is_track_loaded(track_id):
                    self.engine.play(track_id, loop=True)
                    print(f"开始播放: {track_id}")
                else:
                    print(f"音轨不存在: {track_id}")
            
            elif cmd == "pause":
                if len(parts) < 2:
                    print("用法: pause <track_id>")
                    return True
                track_id = parts[1]
                self.engine.pause(track_id)
                print(f"已暂停: {track_id}")
            
            elif cmd == "resume":
                if len(parts) < 2:
                    print("用法: resume <track_id>")
                    return True
                track_id = parts[1]
                self.engine.resume(track_id)
                print(f"已恢复: {track_id}")
            
            elif cmd == "stop":
                if len(parts) < 2:
                    print("用法: stop <track_id>")
                    return True
                track_id = parts[1]
                self.engine.stop(track_id)
                print(f"已停止: {track_id}")
            
            elif cmd == "remove":
                if len(parts) < 2:
                    print("用法: remove <track_id>")
                    return True
                track_id = parts[1]
                success = self.engine.remove_track(track_id)
                if success:
                    print(f"已移除: {track_id}")
                else:
                    print(f"移除失败: {track_id}")
            
            elif cmd == "volume":
                if len(parts) < 3:
                    print("用法: volume <track_id> <0.0-1.0>")
                    return True
                track_id = parts[1]
                volume = float(parts[2])
                self.engine.set_volume(track_id, volume)
                print(f"设置音量: {track_id} = {volume}")
            
            elif cmd == "loop":
                if len(parts) < 3:
                    print("用法: loop <track_id> <on/off>")
                    return True
                track_id = parts[1]
                loop_on = parts[2].lower() in ["on", "true", "1", "yes"]
                self.engine.set_loop(track_id, loop_on)
                print(f"设置循环: {track_id} = {'开' if loop_on else '关'}")
            
            elif cmd == "speed":
                if len(parts) < 3:
                    print("用法: speed <track_id> <factor>")
                    return True
                track_id = parts[1]
                speed = float(parts[2])
                self.engine.set_speed(track_id, speed)
                print(f"设置速度: {track_id} = {speed}x")
            
            elif cmd == "seek":
                if len(parts) < 3:
                    print("用法: seek <track_id> <seconds>")
                    return True
                track_id = parts[1]
                position = float(parts[2])
                self.engine.seek(track_id, position)
                print(f"跳转: {track_id} -> {position}s")
            
            elif cmd == "pause_all":
                paused = self.engine.pause_all_tracks()
                print(f"已暂停 {len(paused)} 个音轨: {paused}")
            
            elif cmd == "resume_all":
                resumed = self.engine.resume_all_tracks()
                print(f"已恢复 {len(resumed)} 个音轨: {resumed}")
            
            elif cmd == "stop_all":
                stopped = self.engine.stop_all_tracks()
                print(f"已停止 {len(stopped)} 个音轨: {stopped}")
            
            elif cmd == "clear_all":
                self.engine.clear_all_tracks()
                print("已清空所有音轨")
            
            elif cmd == "list":
                self.show_track_list()
            
            elif cmd == "status":
                self.show_status()
            
            elif cmd == "info":
                if len(parts) < 2:
                    print("用法: info <track_id>")
                    return True
                track_id = parts[1]
                info = self.engine.get_track_info(track_id)
                if info:
                    print(f"\n=== {track_id} 详细信息 ===")
                    for key, value in info.items():
                        if key == 'duration' or key == 'position':
                            print(f"{key}: {value:.2f}s")
                        elif key == 'volume' or key == 'speed':
                            print(f"{key}: {value:.2f}")
                        else:
                            print(f"{key}: {value}")
                else:
                    print(f"音轨不存在: {track_id}")
            
            elif cmd == "playing":
                playing = self.engine.get_playing_tracks()
                print(f"正在播放的音轨: {playing}")
            
            elif cmd == "paused":
                paused = self.engine.get_paused_tracks()
                print(f"暂停的音轨: {paused}")
            
            else:
                print(f"未知命令: {cmd}，输入 'help' 查看帮助")
        
        except Exception as e:
            print(f"命令执行错误: {e}")
        
        return True
    
    def run(self):
        """运行交互式控制台"""
        print("=== 音轨交互式控制台 ===")
        print("输入 'help' 查看帮助，输入 'quit' 退出")
        
        # 启动音频引擎
        self.engine.start()
        
        try:
            while self.running:
                try:
                    command = input("\n> ").strip()
                    if not self.process_command(command):
                        break
                except KeyboardInterrupt:
                    print("\n\n正在退出...")
                    break
                except EOFError:
                    break
        finally:
            self.engine.shutdown()
            print("音频引擎已关闭，再见！")

def main():
    controller = InteractiveTrackController()
    controller.run()

if __name__ == "__main__":
    main() 