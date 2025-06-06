#!/usr/bin/env python3
"""
使用 load_track_unsampled 处理有电流声的音频文件

此示例展示如何使用 load_track_unsampled 方法处理有电流声、噪音的音频文件。
该方法包含了高级的噪音抑制技术，可以有效减少：
- 电流声和嗡嗡声
- 直流偏移
- 爆音和咔嗒声
- 低频隆隆声
- 高频尖锐噪音
"""

import sys
import os
import time

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from realtimemix import AudioEngine

def on_load_complete(track_id: str, success: bool, error: str = None):
    """加载完成回调"""
    if success:
        print(f"✅ 轨道 {track_id} 加载成功")
        print("   已应用噪音抑制处理")
    else:
        print(f"❌ 轨道 {track_id} 加载失败: {error}")

def on_progress(track_id: str, progress: float, message: str):
    """进度回调"""
    print(f"📊 {track_id}: {progress*100:.1f}% - {message}")

def main():
    print("🎵 使用 load_track_unsampled 处理有电流声的音频文件")
    print("=" * 60)
    
    # 音频文件路径
    audio_file = "声音素材.wav"
    
    # 检查文件是否存在
    if not os.path.exists(audio_file):
        print(f"❌ 音频文件不存在: {audio_file}")
        print("请确保 '声音素材.wav' 文件在当前目录中")
        return
    
    # 获取文件信息
    file_size_mb = os.path.getsize(audio_file) / (1024 * 1024)
    print(f"📁 音频文件: {audio_file}")
    print(f"📊 文件大小: {file_size_mb:.1f} MB")
    
    # 创建音频引擎
    print("\n1. 初始化音频引擎...")
    engine = AudioEngine(
        sample_rate=48000,  # 引擎采样率
        buffer_size=1024,
        channels=2,
        enable_streaming=True,
        streaming_threshold_mb=10  # 10MB以上使用流式播放
    )
    
    try:
        # 启动引擎
        engine.start()
        print("✅ 音频引擎启动成功")
        
        # 使用 load_track_unsampled 加载音频（保持原始采样率 + 噪音抑制）
        print(f"\n2. 加载音频文件（应用噪音抑制）...")
        print("🔧 噪音抑制功能:")
        print("   • 直流偏移移除（消除电流声）")
        print("   • 高通滤波器（消除低频噪音）")
        print("   • 智能噪音门（抑制背景噪音）")
        print("   • 爆音检测和抑制")
        print("   • 实时平滑处理")
        print("   • 软限制器（防止削峰）")
        
        success = engine.load_track_unsampled(
            track_id="clean_audio",
            source=audio_file,
            auto_normalize=True,  # 自动音量标准化
            silent_lpadding_ms=500.0,  # 前面500ms静音缓冲
            silent_rpadding_ms=500.0,  # 后面500ms静音缓冲
            on_complete=on_load_complete,
            progress_callback=on_progress
        )
        
        if not success:
            print("❌ 音频加载启动失败")
            return
        
        # 等待加载完成
        print("\n⏳ 等待加载完成...")
        time.sleep(3)
        
        # 获取音频信息
        info = engine.get_track_info("clean_audio")
        if info:
            print(f"\n📋 音频信息:")
            print(f"   文件路径: {info.get('file_path', '未知')}")
            print(f"   原始采样率: {info['sample_rate']}Hz")
            print(f"   引擎采样率: {info['engine_sample_rate']}Hz")
            print(f"   声道数: {info['channels']}")
            print(f"   时长: {info['duration']:.2f}秒")
            print(f"   加载方式: {'流式播放' if info['streaming_mode'] else '预加载'}")
            print(f"   噪音抑制: {'已启用' if info.get('unsampled_mode') else '未启用'}")
            print(f"   静音填充: {info['silent_lpadding_ms']}ms + {info['silent_rpadding_ms']}ms")
            
            if info['streaming_mode']:
                buffer_status = info.get('buffer_status', {})
                print(f"   流式缓冲: {buffer_status}")
        
        # 播放处理后的音频
        print(f"\n3. 播放处理后的音频...")
        print("🎵 开始播放（已应用噪音抑制）")
        
        # 淡入播放
        engine.play("clean_audio", fade_in=True, volume=0.7)
        
        # 实时监控播放状态
        print("\n📊 实时播放统计:")
        try:
            for i in range(30):  # 播放30秒或到结束
                time.sleep(1)
                
                # 获取播放状态
                position = engine.get_position("clean_audio")
                duration = engine.get_duration("clean_audio")
                stats = engine.get_performance_stats()
                
                # 检查是否播放完毕
                if not engine.is_track_playing("clean_audio"):
                    print("🏁 播放完毕")
                    break
                
                # 显示进度
                progress_pct = (position / duration * 100) if duration > 0 else 0
                print(f"   时间: {position:.1f}s/{duration:.1f}s ({progress_pct:.1f}%) | "
                      f"CPU: {stats['cpu_usage']:.1f}% | "
                      f"峰值: {stats['peak_level']:.3f}")
                
                # 如果播放到末尾，提前退出
                if duration > 0 and position >= duration - 1.0:
                    break
                    
        except KeyboardInterrupt:
            print("\n⚠️  用户手动停止播放")
        
        # 淡出停止
        print("\n🔽 淡出停止...")
        engine.stop("clean_audio", fade_out=True)
        time.sleep(2)
        
        # 显示最终统计
        print(f"\n4. 处理统计:")
        performance = engine.get_performance_stats()
        print(f"   平均CPU使用率: {performance['cpu_usage']:.1f}%")
        print(f"   音频回调次数: {performance['callback_count']}")
        print(f"   缓冲区下溢: {performance['underrun_count']}")
        
        if info and info['streaming_mode']:
            streaming_stats = engine.get_streaming_stats()
            print(f"   流式统计: {streaming_stats}")
        
        print(f"\n✅ 音频处理完成！")
        print(f"📝 效果说明:")
        print(f"   • 保持了原始 {info['sample_rate']}Hz 采样率")
        print(f"   • 自动选择了{'流式播放' if info['streaming_mode'] else '预加载'}模式")
        print(f"   • 应用了完整的噪音抑制处理")
        print(f"   • 添加了静音缓冲区以获得更好的播放体验")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源
        print(f"\n5. 清理资源...")
        engine.shutdown()
        print("🎯 处理完成")

if __name__ == "__main__":
    main() 