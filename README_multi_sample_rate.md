# AudioMixer 多采样率音轨功能

AudioMixer现在支持每个音轨拥有独立的采样率，提供更灵活的播放选择。

## 功能特点

- **独立采样率支持**: 每个音轨可以设置自己的采样率
- **实时重采样**: 自动处理不同采样率音轨的混音
- **性能优化**: 对于与引擎采样率相同的音轨使用快速路径
- **动态调整**: 支持播放时动态修改音轨采样率
- **详细统计**: 提供采样率使用情况的详细统计信息

## 基本用法

### 1. 加载指定采样率的音轨

```python
from audiomixer import AudioEngine
import numpy as np

# 创建音频引擎（默认48kHz）
engine = AudioEngine(sample_rate=48000)
engine.start()

# 加载不同采样率的音轨
engine.load_track("track1", audio_data_44k, sample_rate=44100)  # 44.1kHz音轨
engine.load_track("track2", audio_data_48k, sample_rate=48000)  # 48kHz音轨（原生）
engine.load_track("track3", audio_data_96k, sample_rate=96000)  # 96kHz音轨
engine.load_track("track4", "audio_file.wav", sample_rate=22050)  # 22.05kHz音轨

# 如果不指定采样率，将使用引擎的默认采样率
engine.load_track("track5", audio_data)  # 使用引擎的48kHz
```

### 2. 获取音轨采样率信息

```python
# 获取特定音轨的采样率
sample_rate = engine.get_track_sample_rate("track1")
print(f"音轨采样率: {sample_rate}Hz")

# 获取音轨详细信息（包含采样率信息）
info = engine.get_track_info("track1")
print(f"音轨采样率: {info['sample_rate']}Hz")
print(f"引擎采样率: {info['engine_sample_rate']}Hz")
print(f"转换比例: {info['sample_rate_ratio']:.3f}")
```

### 3. 查看采样率统计

```python
# 获取采样率统计信息
stats = engine.get_sample_rate_statistics()
print(f"引擎采样率: {stats['engine_sample_rate']}Hz")
print(f"总音轨数: {stats['total_tracks']}")
print(f"原生采样率音轨: {stats['native_rate_tracks']}")
print(f"需要转换的音轨: {stats['conversion_needed_tracks']}")
print(f"所有采样率: {stats['unique_sample_rates']}")

# 按采样率分组查看音轨
tracks_by_rate = engine.list_tracks_by_sample_rate()
for sample_rate, track_ids in tracks_by_rate.items():
    print(f"{sample_rate}Hz: {track_ids}")
```

### 4. 动态调整采样率

```python
# 播放音轨
engine.play("track1", volume=0.5)

# 动态改变采样率（会影响音高）
engine.set_track_sample_rate("track1", 44100)  # 调整到44.1kHz
time.sleep(2)

engine.set_track_sample_rate("track1", 96000)  # 调整到96kHz
time.sleep(2)

# 恢复原始采样率
engine.set_track_sample_rate("track1", 48000)
```

## 技术细节

### 采样率转换算法

1. **快速路径**: 当音轨采样率与引擎采样率相同时，直接使用原始数据，无需转换
2. **线性插值**: 对于简单的采样率转换使用高效的线性插值
3. **高质量重采样**: 如果安装了scipy，使用更高质量的重采样算法

### 性能考虑

- **原生采样率音轨**: 与引擎采样率相同的音轨处理速度最快
- **重采样开销**: 不同采样率的音轨需要额外的CPU资源进行实时重采样
- **内存使用**: 每个音轨保持其原始采样率的数据，重采样在播放时进行

### 支持的采样率范围

- **最小采样率**: 8,000 Hz
- **最大采样率**: 192,000 Hz
- **常用采样率**: 22,050, 44,100, 48,000, 88,200, 96,000, 176,400, 192,000 Hz

## 实际应用场景

### 1. 音乐制作

```python
# 混合不同质量的音频素材
engine.load_track("vocal", "vocal_96k.wav", sample_rate=96000)    # 高质量人声
engine.load_track("drum", "drum_44k.wav", sample_rate=44100)     # 标准鼓组
engine.load_track("bass", "bass_48k.wav", sample_rate=48000)     # 低音
engine.load_track("fx", "fx_22k.wav", sample_rate=22050)         # 音效

# 同时播放所有音轨
for track in ["vocal", "drum", "bass", "fx"]:
    engine.play(track, volume=0.7)
```

### 2. 游戏音频

```python
# 不同质量的游戏音频
engine.load_track("music", "bgm.wav", sample_rate=44100)         # 背景音乐
engine.load_track("voice", "dialogue.wav", sample_rate=22050)    # 对话音频
engine.load_track("sfx_high", "explosion.wav", sample_rate=48000) # 高质量音效
engine.load_track("sfx_low", "footstep.wav", sample_rate=11025)  # 低质量音效
```

### 3. 播客和语音处理

```python
# 混合不同来源的音频
engine.load_track("host", "host_audio.wav", sample_rate=48000)    # 主持人音频
engine.load_track("guest", "guest_audio.wav", sample_rate=44100)  # 嘉宾音频
engine.load_track("intro", "intro_music.wav", sample_rate=22050)  # 片头音乐
```

## 最佳实践

### 1. 性能优化建议

- 尽量使用与引擎采样率相同的音轨以获得最佳性能
- 对于不需要高保真度的音效，可以使用较低的采样率
- 监控CPU使用率，避免同时播放过多需要重采样的音轨

### 2. 质量考虑

- 重要的音频内容（如音乐、人声）使用高采样率
- 背景音效可以使用较低采样率以节省资源
- 避免不必要的采样率转换以保持音质

### 3. 内存管理

- 合理选择音轨采样率以平衡质量和内存使用
- 定期清理不需要的音轨
- 使用性能统计监控系统资源使用情况

## 示例代码

运行提供的示例脚本来体验多采样率功能：

```bash
python example_multi_sample_rate.py
```

这个示例将演示：
- 生成不同采样率的测试音频
- 同时播放多个不同采样率的音轨
- 动态调整音轨采样率
- 查看详细的统计信息

## 注意事项

1. **音高变化**: 动态改变采样率会影响音频的音高
2. **CPU使用**: 大量不同采样率的音轨会增加CPU负载
3. **内存占用**: 每个音轨保持其原始采样率的完整数据
4. **兼容性**: 建议安装scipy以获得更好的重采样质量

通过这个多采样率功能，AudioMixer现在能够处理更复杂的音频场景，为您的应用提供更大的灵活性。 