#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音轨管理示例
演示如何使用AudioEngine的音轨管理功能
"""

import time
import numpy as np
from audiomixer import AudioEngine

def generate_test_audio(frequency, duration, sample_rate=48000):
    """生成测试音频信号"""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # 生成正弦波
    audio = np.sin(2 * np.pi * frequency * t)
    # 添加包络线，避免突然开始/结束
    envelope = np.ones_like(audio)
    fade_samples = int(0.1 * sample_rate)  # 0.1秒淡入淡出
    envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
    envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
    audio *= envelope
    
    # 转换为立体声
    stereo_audio = np.column_stack([audio, audio])
    return stereo_audio.astype(np.float32)

def main():
    print("=== 音轨管理示例 ===")
    
    # 初始化音频引擎
    engine = AudioEngine(sample_rate=48000, buffer_size=1024, channels=2)
    engine.start()
    
    try:
        # 生成一些测试音轨
        print("\n1. 生成测试音轨...")
        track1 = generate_test_audio(440, 5)  # A4音符，5秒
        track2 = generate_test_audio(523, 4)  # C5音符，4秒
        track3 = generate_test_audio(659, 3)  # E5音符，3秒
        
        # 加载音轨
        print("2. 加载音轨...")
        engine.load_track("钢琴_A4", track1)
        engine.load_track("钢琴_C5", track2)
        engine.load_track("钢琴_E5", track3)
        
        # 等待加载完成
        time.sleep(0.5)
        
        # 显示音轨信息
        print("\n3. 音轨信息:")
        tracks = engine.list_tracks()
        for track in tracks:
            print(f"  - {track['track_id']}: {track['duration']:.1f}秒, "
                  f"音量: {track['volume']:.1f}, 状态: {'播放中' if track['playing'] else '已停止'}")
        
        # 显示音轨数量统计
        stats = engine.get_track_count()
        print(f"\n音轨统计: 总计{stats['total']}, 播放中{stats['playing']}, "
              f"暂停{stats['paused']}, 已停止{stats['stopped']}")
        
        # 开始播放所有音轨
        print("\n4. 开始播放所有音轨...")
        engine.play("钢琴_A4", volume=0.3, loop=True)
        engine.play("钢琴_C5", volume=0.3, loop=True)
        engine.play("钢琴_E5", volume=0.3, loop=True)
        
        # 等待2秒
        print("播放2秒...")
        time.sleep(2)
        
        # 显示当前播放状态
        playing_tracks = engine.get_playing_tracks()
        print(f"正在播放的音轨: {playing_tracks}")
        
        # 暂停所有音轨
        print("\n5. 暂停所有音轨...")
        paused = engine.pause_all_tracks()
        print(f"已暂停: {paused}")
        
        # 检查暂停状态
        paused_tracks = engine.get_paused_tracks()
        print(f"暂停中的音轨: {paused_tracks}")
        
        # 等待1秒
        time.sleep(1)
        
        # 恢复播放
        print("\n6. 恢复播放所有音轨...")
        resumed = engine.resume_all_tracks()
        print(f"已恢复: {resumed}")
        
        # 等待2秒
        time.sleep(2)
        
        # 单独暂停一个音轨
        print("\n7. 暂停钢琴_C5...")
        engine.pause("钢琴_C5")
        print(f"钢琴_C5 是否暂停: {engine.is_track_paused('钢琴_C5')}")
        print(f"钢琴_A4 是否播放: {engine.is_track_playing('钢琴_A4')}")
        
        # 等待2秒
        time.sleep(2)
        
        # 移除一个音轨
        print("\n8. 移除钢琴_E5...")
        success = engine.remove_track("钢琴_E5", fade_out=True)
        print(f"移除结果: {'成功' if success else '失败'}")
        
        # 等待1秒让淡出完成
        time.sleep(1)
        
        # 显示剩余音轨
        remaining_tracks = engine.list_tracks()
        print(f"剩余音轨: {[t['track_id'] for t in remaining_tracks]}")
        
        # 等待2秒
        time.sleep(2)
        
        # 停止所有音轨
        print("\n9. 停止所有音轨...")
        stopped = engine.stop_all_tracks(fade_out=True)
        print(f"已停止: {stopped}")
        
        # 等待淡出完成
        time.sleep(1)
        
        # 获取最终状态
        final_stats = engine.get_track_count()
        print(f"\n最终统计: 总计{final_stats['total']}, 播放中{final_stats['playing']}, "
              f"暂停{final_stats['paused']}, 已停止{final_stats['stopped']}")
        
        # 清空所有音轨
        print("\n10. 清空所有音轨...")
        engine.clear_all_tracks()
        
        final_count = len(engine.list_tracks())
        print(f"清空后音轨数量: {final_count}")
        
        print("\n=== 演示完成 ===")
        
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
    finally:
        # 关闭音频引擎
        engine.shutdown()
        print("音频引擎已关闭")

if __name__ == "__main__":
    main() 