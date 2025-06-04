#!/usr/bin/env python3
"""
左右静音填充功能演示脚本

展示如何使用新的 silent_lpadding_ms 和 silent_rpadding_ms 参数
来分别控制音频前后的静音时长。

功能演示：
1. 只添加左侧静音（音频前）
2. 只添加右侧静音（音频后） 
3. 左右不同长度的静音
4. 传统的前后相同静音（兼容性）
"""

import time
import os
from audiomixer import AudioEngine


def demo_padding_combinations():
    """演示不同的静音填充组合"""
    
    print("=== 左右静音填充功能演示 ===\n")
    
    # 检查音频文件
    audio_file = "副音轨.wav"
    if not os.path.exists(audio_file):
        print(f"❌ 错误：找不到演示音频文件 '{audio_file}'")
        print("请确保工作目录中有音频文件")
        return
    
    print(f"✅ 找到演示音频文件: {audio_file}")
    
    # 初始化音频引擎
    engine = AudioEngine(
        sample_rate=48000,
        buffer_size=1024,
        channels=2,
        max_tracks=8,
        enable_streaming=False  # 小文件演示，禁用流式播放
    )
    
    engine.start()
    print("✅ 音频引擎已启动\n")
    
    try:
        # 演示1：只添加左侧静音（前500ms）
        print("=== 演示1：只添加左侧静音 ===")
        engine.load_track("demo1", audio_file, 
                         silent_lpadding_ms=500.0,  # 前面500ms静音
                         silent_rpadding_ms=0.0)    # 后面无静音
        
        # 等待加载完成
        time.sleep(2)
        
        info1 = engine.get_track_info("demo1")
        if info1:
            print(f"轨道: demo1")
            print(f"  原始时长: ~6.36秒")
            print(f"  添加静音后: {info1['duration']:.2f}秒")
            print(f"  左侧静音: {info1['silent_lpadding_ms']}ms")
            print(f"  右侧静音: {info1['silent_rpadding_ms']}ms")
            print("  播放测试...")
            
            engine.play("demo1")
            time.sleep(2)  # 播放一小段
            engine.stop("demo1")
            print("  ✅ 播放完成\n")
        else:
            print("  ❌ 轨道加载失败\n")
        
        # 演示2：只添加右侧静音（后800ms）
        print("=== 演示2：只添加右侧静音 ===")
        engine.load_track("demo2", audio_file,
                         silent_lpadding_ms=0.0,    # 前面无静音
                         silent_rpadding_ms=800.0)  # 后面800ms静音
        
        # 等待加载完成
        time.sleep(2)
        
        info2 = engine.get_track_info("demo2")
        if info2:
            print(f"轨道: demo2")
            print(f"  原始时长: ~6.36秒")
            print(f"  添加静音后: {info2['duration']:.2f}秒")
            print(f"  左侧静音: {info2['silent_lpadding_ms']}ms")
            print(f"  右侧静音: {info2['silent_rpadding_ms']}ms")
            print("  播放测试...")
            
            engine.play("demo2")
            time.sleep(2)
            engine.stop("demo2")
            print("  ✅ 播放完成\n")
        else:
            print("  ❌ 轨道加载失败\n")
        
        # 演示3：左右不同长度的静音
        print("=== 演示3：左右不同长度的静音 ===")
        engine.load_track("demo3", audio_file,
                         silent_lpadding_ms=200.0,  # 前面200ms静音
                         silent_rpadding_ms=1000.0) # 后面1000ms静音
        
        # 等待加载完成
        time.sleep(2)
        
        info3 = engine.get_track_info("demo3")
        if info3:
            print(f"轨道: demo3")
            print(f"  原始时长: ~6.36秒")
            print(f"  添加静音后: {info3['duration']:.2f}秒")
            print(f"  左侧静音: {info3['silent_lpadding_ms']}ms")
            print(f"  右侧静音: {info3['silent_rpadding_ms']}ms")
            print("  播放测试...")
            
            engine.play("demo3")
            time.sleep(2)
            engine.stop("demo3")
            print("  ✅ 播放完成\n")
        else:
            print("  ❌ 轨道加载失败\n")
        
        # 演示4：传统的前后相同静音（兼容性）
        print("=== 演示4：传统的前后相同静音 ===")
        engine.load_track("demo4", audio_file,
                         silent_lpadding_ms=300.0,  # 前面300ms静音
                         silent_rpadding_ms=300.0)  # 后面300ms静音
        
        # 等待加载完成
        time.sleep(2)
        
        info4 = engine.get_track_info("demo4")
        if info4:
            print(f"轨道: demo4")
            print(f"  原始时长: ~6.36秒")
            print(f"  添加静音后: {info4['duration']:.2f}秒")
            print(f"  左侧静音: {info4['silent_lpadding_ms']}ms")
            print(f"  右侧静音: {info4['silent_rpadding_ms']}ms")
            print(f"  总静音: {info4['silent_padding_ms']}ms (兼容性参数)")
            print("  播放测试...")
            
            engine.play("demo4")
            time.sleep(2)
            engine.stop("demo4")
            print("  ✅ 播放完成\n")
        else:
            print("  ❌ 轨道加载失败\n")
        
        # 显示所有轨道的汇总信息
        print("=== 所有演示轨道汇总 ===")
        tracks = engine.list_tracks()
        for track in tracks:
            print(f"轨道 {track['track_id']}:")
            print(f"  时长: {track['duration']:.2f}秒")
            print(f"  左侧静音: {track['silent_lpadding_ms']}ms")
            print(f"  右侧静音: {track['silent_rpadding_ms']}ms")
            print(f"  总静音增加: {track['silent_lpadding_ms'] + track['silent_rpadding_ms']}ms")
            print()
        
        print("✅ 演示完成！")
        print("\n🎉 新功能优势：")
        print("   - 可以分别控制前后静音时长")
        print("   - 适用于不同的音频制作需求")
        print("   - 兼容原有的API设计")
        print("   - 支持流式播放和预加载模式")
        
    except KeyboardInterrupt:
        print("\n用户中断演示")
    except Exception as e:
        print(f"❌ 演示过程中出现错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n清理资源...")
        engine.shutdown()
        print("✅ 资源清理完成")


if __name__ == "__main__":
    demo_padding_combinations() 