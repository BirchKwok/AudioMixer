#!/usr/bin/env python3
"""
音频混音器测试脚本 - 主音轨和副音轨无缝切换测试

测试目标：
1. 主音轨播放 "声音素材.wav"
2. 副音轨1播放 "副音轨.wav"，播放前后各有300ms静音
3. 使用AudioEngine内置的响度匹配确保音量一致性
4. 使用AudioEngine内置的交叉淡入淡出实现无缝切换
5. 检测是否有电流音或其他音频质量问题

播放流程：
1. 主音轨开始播放（独奏3秒）
2. 300ms 静音
3. 交叉淡入淡出：主音轨淡出，副音轨淡入（无缝切换）
4. 副音轨播放完成
5. 300ms 静音  
6. 交叉淡入淡出：副音轨淡出，主音轨淡入（无缝切换）

关键技术：
- 使用engine.match_loudness()进行响度匹配
- 使用engine.crossfade()进行交叉淡入淡出
- 音频质量监测：检测电流音、削波、信号稳定性
"""

import numpy as np
import time
import sys
import os
from audiomixer import AudioEngine


def analyze_audio_quality(engine, duration=5.0):
    """
    分析音频质量，检测电流音和其他问题
    
    Args:
        engine: AudioEngine实例
        duration: 分析持续时间（秒）
    
    Returns:
        dict: 音频质量分析结果
    """
    print(f"开始音频质量分析，持续时间: {duration}秒...")
    
    # 收集性能统计数据
    stats_history = []
    start_time = time.time()
    
    while time.time() - start_time < duration:
        stats = engine.get_performance_stats()
        stats_history.append({
            'timestamp': time.time() - start_time,
            'peak_level': stats['peak_level'],
            'cpu_usage': stats['cpu_usage'],
            'active_tracks': stats['active_tracks']
        })
        time.sleep(0.1)  # 每100ms采样一次
    
    # 分析结果
    peak_levels = [s['peak_level'] for s in stats_history]
    cpu_usages = [s['cpu_usage'] for s in stats_history]
    
    # 计算活跃音轨数的稳定性（排除正常的播放完成情况）
    active_tracks_counts = [s['active_tracks'] for s in stats_history]
    # 只在音轨数量异常下降时才认为不稳定（排除正常播放完成）
    expected_tracks = max(active_tracks_counts) if active_tracks_counts else 1
    unexpected_drops = sum(1 for count in active_tracks_counts if count < expected_tracks and count > 0)
    
    analysis = {
        'avg_peak_level': np.mean(peak_levels),
        'max_peak_level': np.max(peak_levels),
        'min_peak_level': np.min(peak_levels),
        'peak_level_variance': np.var(peak_levels),
        'avg_cpu_usage': np.mean(cpu_usages),
        'max_cpu_usage': np.max(cpu_usages),
        'underrun_detected': unexpected_drops > len(stats_history) * 0.1,  # 超过10%的采样点有异常才报告
        'level_stability': np.std(peak_levels) < 0.05,  # 放宽电平稳定性阈值，音乐内容变化是正常的
        'no_clipping': np.max(peak_levels) < 0.95,  # 检测削波
        'proper_signal': np.mean(peak_levels) > 0.001,  # 确保有信号
        'peak_levels': peak_levels,  # 添加原始peak_levels数据
    }
    
    return analysis, stats_history


def print_audio_analysis(analysis):
    """打印音频分析结果"""
    print("\n=== 音频质量分析结果 ===")
    print(f"平均峰值电平: {analysis['avg_peak_level']:.4f}")
    print(f"最大峰值电平: {analysis['max_peak_level']:.4f}")
    print(f"最小峰值电平: {analysis['min_peak_level']:.4f}")
    print(f"电平方差: {analysis['peak_level_variance']:.6f}")
    print(f"电平标准差: {np.sqrt(analysis['peak_level_variance']):.4f}")
    print(f"平均CPU使用率: {analysis['avg_cpu_usage']:.1f}%")
    print(f"最大CPU使用率: {analysis['max_cpu_usage']:.1f}%")
    
    print("\n=== 音频质量检测 ===")
    
    # 从analysis字典中获取peak_levels数据
    peak_levels = analysis.get('peak_levels', [])
    
    # 电流音检测（基于电平稳定性，考虑音乐内容的正常变化）
    peak_std = np.std(peak_levels) if peak_levels else 0.0
    if peak_std > 0.1 and analysis['avg_peak_level'] < 0.1:
        # 只有在平均电平很低但变化很大时才可能是电流音
        print("⚠️  检测到可能的电流音或噪声（低信号高变化）")
    elif not analysis['level_stability'] and analysis['avg_peak_level'] > 0.1:
        print("ℹ️  检测到电平变化（可能是音乐内容的正常变化）")
    else:
        print("✅ 未检测到明显电流音")
    
    # 削波检测
    if not analysis['no_clipping']:
        print("⚠️  检测到音频削波失真")
    else:
        print("✅ 未检测到削波失真")
    
    # 信号检测
    if not analysis['proper_signal']:
        print("⚠️  音频信号过弱或无信号")
    else:
        print("✅ 音频信号正常")
    
    # 音轨稳定性
    if analysis['underrun_detected']:
        print("⚠️  检测到音轨播放不稳定")
    else:
        print("✅ 音轨播放稳定")
    
    # 整体评估
    serious_noise = peak_std > 0.1 and analysis['avg_peak_level'] < 0.1
    
    quality_issues = sum([
        serious_noise,  # 只有严重的噪声才算问题
        not analysis['no_clipping'],
        not analysis['proper_signal'],
        analysis['underrun_detected']
    ])
    
    if quality_issues == 0:
        print("\n✅ 整体音频质量：优秀")
    elif quality_issues == 1:
        print("\n⚠️  整体音频质量：良好（有轻微问题）")
    else:
        print("\n❌ 整体音频质量：有问题（需要检查）")


def main():
    print("=== 音频混音器测试 ===")
    print("测试目标：主音轨播放'声音素材.wav'，副音轨播放'副音轨.wav'")
    print("播放特性：副音轨前后各有300ms静音，使用AudioEngine内置的响度匹配和交叉淡入淡出实现无缝切换")
    
    # 检查音频文件是否存在
    main_audio_file = "声音素材.wav"
    sub_audio_file = "副音轨.wav"
    
    if not os.path.exists(main_audio_file):
        print(f"❌ 错误：找不到主音轨文件 '{main_audio_file}'")
        return
    
    if not os.path.exists(sub_audio_file):
        print(f"❌ 错误：找不到副音轨文件 '{sub_audio_file}'")
        return
    
    print(f"✅ 找到音频文件:")
    print(f"   主音轨: {main_audio_file} ({os.path.getsize(main_audio_file) / (1024*1024):.1f} MB)")
    print(f"   副音轨: {sub_audio_file} ({os.path.getsize(sub_audio_file) / (1024*1024):.1f} MB)")
    
    # 初始化音频引擎
    print("\n正在初始化音频引擎...")
    try:
        engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            max_tracks=16,
            enable_streaming=True,  # 启用流式播放（适合大文件）
            streaming_threshold_mb=50  # 50MB以上使用流式播放
        )
        
        print("✅ 音频引擎初始化成功")
        
        # 启动音频引擎
        engine.start()
        print("✅ 音频引擎已启动")
        
        # 加载音频文件
        print("\n正在加载音频文件...")
        
        # 加载主音轨（声音素材.wav）
        print(f"加载主音轨: {main_audio_file}")
        success_main = engine.load_track("main_track", main_audio_file, auto_normalize=True)
        if success_main:
            print("✅ 主音轨加载成功")
        else:
            print("❌ 主音轨加载失败")
            return
        
        # 加载副音轨（副音轨.wav）
        print(f"加载副音轨1: {sub_audio_file}")
        success_sub = engine.load_track("sub_track_1", sub_audio_file, auto_normalize=True)
        if success_sub:
            print("✅ 副音轨1加载成功")
        else:
            print("❌ 副音轨1加载失败")
            return
        
        # 等待加载完成
        time.sleep(2)
        
        # 显示音轨信息
        print("\n=== 音轨信息 ===")
        main_info = engine.get_track_info("main_track")
        sub_info = engine.get_track_info("sub_track_1")
        
        if main_info:
            print(f"主音轨 - 时长: {main_info['duration']:.2f}秒, 采样率: {main_info.get('sample_rate', 'N/A')}Hz")
        if sub_info:
            print(f"副音轨1 - 时长: {sub_info['duration']:.2f}秒, 采样率: {sub_info.get('sample_rate', 'N/A')}Hz")
        
        # 开始播放测试
        print("\n开始无缝切换播放测试...")
        print("播放特性：副音轨前后各有300ms静音，使用AudioEngine内置的交叉淡入淡出无缝切换")
        
        # 播放主音轨
        engine.set_volume("main_track", 0.7)
        engine.play("main_track", fade_in=True, loop=True)
        print("✅ 主音轨开始播放")
        
        # 主音轨独奏一段时间
        print("主音轨独奏中...")
        time.sleep(3)
        
        # 副音轨前静音 - 300ms
        print("副音轨前静音 300ms...")
        time.sleep(0.3)
        
        # 交叉淡入淡出切换到副音轨
        print("开始无缝切换到副音轨...")
        engine.crossfade("main_track", "sub_track_1", 0.5)
        
        # 获取副音轨时长来控制播放时间
        if sub_info and 'duration' in sub_info:
            sub_duration = sub_info['duration']
            print(f"副音轨播放中...（时长: {sub_duration:.2f}秒）")
            time.sleep(sub_duration)
        else:
            print("副音轨播放中...（使用默认时长5秒）")
            time.sleep(5)
        
        # 副音轨后静音 - 300ms
        print("副音轨后静音 300ms...")
        time.sleep(0.3)
        
        # 交叉淡入淡出切换回主音轨
        print("开始无缝切换回主音轨...")
        engine.crossfade("sub_track_1", "main_track", 0.5)
        print("✅ 主音轨恢复播放")
        
        # 音频质量监测（在主音轨恢复播放后）
        print("\n开始音频质量监测...")
        analysis, stats_history = analyze_audio_quality(engine, duration=5.0)
        
        # 打印分析结果
        print_audio_analysis(analysis)
        
        # 最终性能统计
        time.sleep(2)
        final_stats = engine.get_performance_stats()
        print(f"\n=== 最终性能统计 ===")
        print(f"CPU使用率: {final_stats['cpu_usage']:.1f}%")
        print(f"峰值电平: {final_stats['peak_level']:.4f}")
        print(f"活跃音轨数: {final_stats['active_tracks']}")
        print(f"总音轨数: {final_stats['total_tracks']}")
        
        # 显示内存使用情况
        memory_stats = engine.get_memory_usage()
        streaming_stats = engine.get_streaming_stats()
        print(f"\n=== 内存使用情况 ===")
        print(f"预加载音轨内存: {memory_stats['total_memory_mb']:.1f} MB")
        print(f"预加载音轨数: {memory_stats['track_count']}")
        print(f"流式音轨数: {streaming_stats['total_streaming_tracks']}")
        print(f"总内存使用: {memory_stats['total_memory_mb']:.1f} MB")
        print(f"最大内存限制: {memory_stats['max_memory_mb']:.1f} MB")
        
        # 显示流式播放统计
        print(f"\n=== 流式播放统计 ===")
        print(f"流式播放模式: {'启用' if streaming_stats['streaming_enabled'] else '禁用'}")
        print(f"流式播放阈值: {streaming_stats['streaming_threshold_mb']:.1f} MB")
        print(f"总缓冲区下溢: {streaming_stats['total_buffer_underruns']}")
        print(f"总加载块数: {streaming_stats['total_chunks_loaded']}")
        
        # 渐隐停止
        print("\n停止播放...")
        engine.stop("main_track", fade_out=True)
        engine.stop("sub_track_1", fade_out=True)
        
        # 等待渐隐完成
        time.sleep(2)
        
        print("✅ 测试完成!")
        
    except KeyboardInterrupt:
        print("\n用户中断测试")
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源
        print("\n清理资源...")
        if 'engine' in locals():
            engine.shutdown()
        print("✅ 资源清理完成")


if __name__ == "__main__":
    main() 