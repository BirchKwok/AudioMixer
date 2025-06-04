# 简单测试新的 load_track_unsampled API
from realtimemix import AudioEngine
import numpy as np
import time

def test_basic_functionality():
    print("=== 简单测试 load_track_unsampled API ===\n")
    
    # 创建引擎（48000Hz）
    engine = AudioEngine(sample_rate=48000)
    
    # 创建测试音频数据
    test_sample_rate = 44100
    duration = 1.0
    samples = int(test_sample_rate * duration)
    t = np.linspace(0, duration, samples, False)
    audio_data = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
    audio_data = audio_data.reshape(-1, 1)
    audio_data = np.repeat(audio_data, 2, axis=1)
    
    print(f"创建测试数据: {audio_data.shape}, dtype={audio_data.dtype}")
    
    # 测试回调函数
    def on_complete(track_id, success, error=None):
        if success:
            print(f"✓ 轨道 {track_id} 加载成功")
            info = engine.get_track_info(track_id)
            if info:
                print(f"  - 轨道采样率: {info['sample_rate']}Hz")
                print(f"  - 引擎采样率: {info['engine_sample_rate']}Hz")
                print(f"  - 时长: {info['duration']:.2f}秒")
        else:
            print(f"✗ 轨道 {track_id} 加载失败: {error}")
    
    # 测试1: 普通numpy数组
    print("测试1: 普通NumPy数组")
    success = engine.load_track_unsampled(
        track_id='test1',
        source=audio_data,
        on_complete=on_complete
    )
    
    if success:
        print("API调用成功，等待加载...")
        time.sleep(1)
    else:
        print("API调用失败")
    
    # 测试2: 对比普通load_track
    print("\n测试2: 对比普通 load_track")
    success = engine.load_track(
        track_id='test2',
        source=audio_data,
        sample_rate=44100,
        on_complete=on_complete
    )
    
    if success:
        print("API调用成功，等待加载...")
        time.sleep(1)
    else:
        print("API调用失败")
    
    # 显示所有轨道
    print("\n=== 所有轨道信息 ===")
    tracks = engine.list_tracks()
    for track in tracks:
        print(f"轨道: {track['track_id']}")
        print(f"  - 采样率: {track['sample_rate']}Hz")
        print(f"  - 时长: {track['duration']:.2f}秒")
        print(f"  - 样本数: {track['samples']}")
    
    engine.shutdown()
    print("\n测试完成")

if __name__ == "__main__":
    test_basic_functionality() 