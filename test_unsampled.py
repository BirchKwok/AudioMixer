# 测试新的 load_track_unsampled API
from realtimemix import AudioEngine
import numpy as np
import time

# 创建一个测试引擎
engine = AudioEngine(sample_rate=48000)

# 创建测试音频数据（44100Hz采样率）
test_sample_rate = 44100
duration = 1.0  # 1秒
samples = int(test_sample_rate * duration)
# 生成1kHz正弦波
t = np.linspace(0, duration, samples, False)
audio_data = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
audio_data = audio_data.reshape(-1, 1)  # 单声道
audio_data = np.repeat(audio_data, 2, axis=1)  # 转换为立体声

print('测试 load_track_unsampled API...')

# 测试回调函数
def on_complete(track_id, success, error=None):
    if success:
        print(f'轨道 {track_id} 加载成功')
        # 获取轨道信息验证采样率
        info = engine.get_track_info(track_id)
        if info:
            print(f'轨道采样率: {info["sample_rate"]}Hz')
            print(f'引擎采样率: {info["engine_sample_rate"]}Hz')
            print(f'采样率比例: {info["sample_rate_ratio"]:.3f}')
        else:
            print('无法获取轨道信息')
    else:
        print(f'轨道 {track_id} 加载失败: {error}')

# 加载音频数据（保持原始采样率）
success = engine.load_track_unsampled(
    track_id='test_unsampled',
    source=audio_data,
    on_complete=on_complete
)

if success:
    print('API调用成功，等待加载完成...')
    time.sleep(2)  # 等待异步加载完成
    
    # 获取轨道信息
    info = engine.get_track_info('test_unsampled')
    if info:
        print('\n轨道信息:')
        print(f'- 轨道ID: {info["track_id"]}')
        print(f'- 时长: {info["duration"]:.2f}秒')
        print(f'- 轨道采样率: {info["sample_rate"]}Hz')
        print(f'- 引擎采样率: {info["engine_sample_rate"]}Hz')
        print(f'- 采样率比例: {info["sample_rate_ratio"]:.3f}')
        print(f'- 样本数: {info["samples"]}')
        print(f'- 声道数: {info["channels"]}')
    
else:
    print('API调用失败')

print('\n测试完成')
engine.shutdown() 