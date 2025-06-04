# 完整测试新的 load_track_unsampled API
from realtimemix import AudioEngine
import numpy as np
import time
import tempfile
import soundfile as sf
import os

def create_test_audio_file(sample_rate=44100, duration=1.0):
    """创建测试音频文件"""
    samples = int(sample_rate * duration)
    t = np.linspace(0, duration, samples, False)
    # 生成1kHz正弦波
    audio_data = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
    audio_data = audio_data.reshape(-1, 1)  # 单声道
    audio_data = np.repeat(audio_data, 2, axis=1)  # 转换为立体声
    
    # 保存到临时文件
    temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    sf.write(temp_file.name, audio_data, sample_rate)
    temp_file.close()
    return temp_file.name, audio_data

def test_unsampled_api():
    print("=== 测试 load_track_unsampled API ===\n")
    
    # 创建引擎（48000Hz）
    engine = AudioEngine(sample_rate=48000)
    
    # 测试结果记录
    results = []
    
    def on_complete(track_id, success, error=None):
        if success:
            print(f"✓ 轨道 {track_id} 加载成功")
            info = engine.get_track_info(track_id)
            if info:
                print(f"  - 轨道采样率: {info['sample_rate']}Hz")
                print(f"  - 引擎采样率: {info['engine_sample_rate']}Hz")
                print(f"  - 采样率比例: {info['sample_rate_ratio']:.3f}")
                print(f"  - 时长: {info['duration']:.2f}秒")
                results.append((track_id, info['sample_rate'], True))
            else:
                print("  ⚠ 无法获取轨道信息")
                results.append((track_id, None, False))
        else:
            print(f"✗ 轨道 {track_id} 加载失败: {error}")
            results.append((track_id, None, False))
        print()
    
    # 测试1: 加载44100Hz的文件
    print("测试1: 加载44100Hz音频文件")
    test_file_44k, _ = create_test_audio_file(sample_rate=44100, duration=1.0)
    
    try:
        success = engine.load_track_unsampled(
            track_id='file_44k_unsampled',
            source=test_file_44k,
            on_complete=on_complete
        )
        
        if not success:
            print("✗ API调用失败")
        
        time.sleep(1)  # 等待加载完成
        
    finally:
        os.unlink(test_file_44k)  # 删除临时文件
    
    # 测试2: 加载22050Hz的文件
    print("测试2: 加载22050Hz音频文件")
    test_file_22k, _ = create_test_audio_file(sample_rate=22050, duration=1.0)
    
    try:
        success = engine.load_track_unsampled(
            track_id='file_22k_unsampled',
            source=test_file_22k,
            on_complete=on_complete
        )
        
        if not success:
            print("✗ API调用失败")
        
        time.sleep(1)
        
    finally:
        os.unlink(test_file_22k)
    
    # 测试3: 加载普通NumPy数组（不带采样率）
    print("测试3: 加载普通NumPy数组（不带采样率信息）")
    test_sample_rate = 44100
    duration = 1.0
    samples = int(test_sample_rate * duration)
    t = np.linspace(0, duration, samples, False)
    audio_data = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
    audio_data = audio_data.reshape(-1, 1)
    audio_data = np.repeat(audio_data, 2, axis=1)
    
    success = engine.load_track_unsampled(
        track_id='array_no_rate',
        source=audio_data,
        on_complete=on_complete
    )
    
    if not success:
        print("✗ API调用失败")
    
    time.sleep(1)
    
    # 测试4: 加载带采样率属性的NumPy数组
    print("测试4: 加载带采样率属性的NumPy数组")
    
    class AudioArray:
        """音频数组包装类，可以添加采样率属性"""
        def __init__(self, data, sample_rate):
            self.data = data
            self.sample_rate = sample_rate
            # 代理numpy数组的属性和方法
            self.shape = data.shape
            self.dtype = data.dtype
            self.ndim = data.ndim
        
        def __getattr__(self, name):
            # 如果属性不存在，尝试从data获取
            return getattr(self.data, name)
        
        def __getitem__(self, key):
            return self.data[key]
        
        def __len__(self):
            return len(self.data)
        
        def copy(self):
            return AudioArray(self.data.copy(), self.sample_rate)
    
    audio_data_with_rate = AudioArray(audio_data, 44100)
    
    success = engine.load_track_unsampled(
        track_id='array_with_rate',
        source=audio_data_with_rate,
        on_complete=on_complete
    )
    
    if not success:
        print("✗ API调用失败")
    
    time.sleep(1)
    
    # 对比测试：使用常规load_track方法
    print("对比测试: 使用常规 load_track 方法加载相同数据")
    success = engine.load_track(
        track_id='array_regular',
        source=audio_data,
        sample_rate=44100,  # 明确指定采样率
        on_complete=on_complete
    )
    
    if not success:
        print("✗ API调用失败")
    
    time.sleep(1)
    
    # 显示结果总结
    print("=== 测试结果总结 ===")
    for track_id, sample_rate, success in results:
        status = "成功" if success else "失败"
        rate_info = f"{sample_rate}Hz" if sample_rate else "未知"
        print(f"{track_id}: {status} (采样率: {rate_info})")
    
    # 获取所有轨道信息
    print("\n=== 所有已加载轨道信息 ===")
    tracks = engine.list_tracks()
    for track in tracks:
        print(f"轨道: {track['track_id']}")
        print(f"  - 采样率: {track['sample_rate']}Hz")
        print(f"  - 时长: {track['duration']:.2f}秒")
        print(f"  - 流式模式: {track.get('streaming_mode', False)}")
        print()
    
    # 清理
    engine.shutdown()
    print("测试完成")

if __name__ == "__main__":
    test_unsampled_api() 