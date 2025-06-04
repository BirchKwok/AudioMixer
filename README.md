# realtimemix

一个高性能的Python实时音频混音引擎，专为专业音频应用、游戏开发和多媒体项目设计。

## 特性

- **实时音频混音** - 低延迟音频处理，可配置缓冲区大小
- **多轨支持** - 同时处理多达32+个音频轨道
- **高质量音频处理** - 支持各种采样率和声道配置
- **原始采样率保持** - 支持加载音频时保持原始采样率，避免不必要的重采样
- **高级音频效果** - 淡入淡出、音量控制、变速调节和循环播放
- **内存高效** - 优化的缓冲池和内存管理
- **线程安全** - 支持多线程应用程序安全使用
- **文件格式支持** - 通过soundfile加载各种格式的音频文件
- **可选高质量处理** - 使用librosa/scipy进行增强重采样和时间拉伸
- **流式播放** - 大文件流式播放支持，节省内存
- **响度匹配** - 内置响度分析和自动匹配功能
- **交叉淡入淡出** - 专业级音频切换效果

## 安装

### 基础安装
```bash
pip install realtimemix
```

### 含高质量音频处理
```bash
pip install realtimemix[high-quality]
```

### 含时间拉伸支持
```bash
pip install realtimemix[time-stretch]
```

### 含所有可选依赖
```bash
pip install realtimemix[all]
```

### 开发安装
```bash
git clone https://github.com/birchkwok/realtimemix.git
cd realtimemix
pip install -e .[dev]
```

## 快速开始

```python
import numpy as np
from realtimemix import AudioEngine

# 初始化音频引擎
engine = AudioEngine(sample_rate=48000, buffer_size=1024, channels=2)

# 启动音频引擎
engine.start()

# 从文件加载音频
engine.load_track("background_music", "path/to/music.wav", auto_normalize=True)

# 从numpy数组加载音频
audio_data = np.random.randn(48000, 2).astype(np.float32)  # 1秒立体声噪音
engine.load_track("noise", audio_data)

# 加载音频并保持原始采样率（适用于高质量音频处理）
engine.load_track_unsampled("hq_audio", "path/to/high_quality.wav")

# 播放音轨
engine.play("background_music", loop=True, fade_in=True)
engine.play("noise", volume=0.5)

# 控制播放
engine.set_volume("background_music", 0.7)
engine.set_speed("noise", 1.5)  # 播放速度提高50%

# 停止音轨
engine.stop("noise", fade_out=True)

# 清理
engine.shutdown()
```

## 完整API参考

### AudioEngine

音频混音操作的主要类。

#### 构造函数

```python
AudioEngine(sample_rate=48000, buffer_size=1024, channels=2, max_tracks=32, 
           device=None, stream_latency='low', enable_streaming=True, 
           streaming_threshold_mb=100)
```

**参数说明：**
- `sample_rate` (int): 音频采样率（Hz），默认48000
- `buffer_size` (int): 音频缓冲区大小（帧数），默认1024
- `channels` (int): 声道数，默认2（立体声）
- `max_tracks` (int): 最大同时音轨数，默认32
- `device` (int, optional): 音频设备ID，None表示默认设备
- `stream_latency` (str): 流延迟设置 ('low', 'medium', 'high')
- `enable_streaming` (bool): 是否启用流式播放，默认True
- `streaming_threshold_mb` (int): 流式播放文件大小阈值（MB），默认100

**示例：**
```python
# 基础配置
engine = AudioEngine()

# 高性能配置
engine = AudioEngine(
    sample_rate=96000,      # 高采样率
    buffer_size=512,        # 小缓冲区，低延迟
    channels=2,
    max_tracks=16,
    stream_latency='low'
)

# 大文件优化配置
engine = AudioEngine(
    enable_streaming=True,
    streaming_threshold_mb=50,  # 50MB以上文件使用流式播放
    max_tracks=8
)
```

#### 轨道管理方法

##### load_track()

加载音频数据到轨道。

```python
load_track(track_id, source, speed=1.0, auto_normalize=True, 
          sample_rate=None, silent_lpadding_ms=0.0, 
          silent_rpadding_ms=0.0, on_complete=None, 
          progress_callback=None)
```

**参数说明：**
- `track_id` (str): 唯一的轨道标识符
- `source` (str | np.ndarray): 音频文件路径或numpy数组
- `speed` (float): 播放速度，默认1.0
- `auto_normalize` (bool): 是否自动标准化音量，默认True
- `sample_rate` (int, optional): 指定源音频采样率
- `silent_lpadding_ms` (float): 开头静音填充时长（毫秒）
- `silent_rpadding_ms` (float): 结尾静音填充时长（毫秒）
- `on_complete` (callable, optional): 加载完成回调函数
- `progress_callback` (callable, optional): 进度回调函数

**返回值：** `bool` - 加载是否成功启动

**示例：**
```python
# 从文件加载
success = engine.load_track("music", "song.wav")

# 从numpy数组加载
audio_data = np.random.randn(48000, 2).astype(np.float32)
engine.load_track("generated", audio_data, auto_normalize=True)

# 带静音填充
engine.load_track("voice", "voice.wav", 
                 silent_lpadding_ms=500,  # 开头500ms静音
                 silent_rpadding_ms=300)  # 结尾300ms静音

# 异步加载带回调
def on_load_complete(track_id, success, error=None):
    if success:
        print(f"轨道 {track_id} 加载成功")
        engine.play(track_id)
    else:
        print(f"加载失败: {error}")

engine.load_track("async_music", "large_file.wav", 
                 on_complete=on_load_complete)

# 带进度回调
def on_progress(track_id, progress):
    print(f"加载进度 {track_id}: {progress:.1%}")

engine.load_track("big_file", "huge_audio.wav", 
                 progress_callback=on_progress)
```

##### load_track_unsampled()

加载音频数据到轨道（保持原始采样率，不进行重采样）。

与`load_track()`不同，此方法会保持音频文件的原始采样率，不会强制重采样到引擎采样率。这对于需要精确保持音频原始特性的应用场景很有用，例如音频分析、高质量音频处理或需要保持原始音频精度的专业应用。

```python
load_track_unsampled(track_id, source, speed=1.0, auto_normalize=True, 
                   silent_lpadding_ms=0.0, silent_rpadding_ms=0.0, 
                   on_complete=None, progress_callback=None)
```

**参数说明：**
- `track_id` (str): 唯一的轨道标识符
- `source` (str | np.ndarray): 音频文件路径或numpy数组
- `speed` (float): 播放速度倍数，默认1.0
- `auto_normalize` (bool): 是否自动标准化音量，默认True
- `silent_lpadding_ms` (float): 开头静音填充时长（毫秒）
- `silent_rpadding_ms` (float): 结尾静音填充时长（毫秒）
- `on_complete` (callable, optional): 加载完成回调函数
- `progress_callback` (callable, optional): 进度回调函数

**返回值：** `bool` - 加载是否成功启动

**重要说明：**
- **文件路径**：音频将保持原始采样率，不会重采样到引擎采样率
- **NumPy数组**：由于数组本身不包含采样率信息，将使用引擎采样率
  - 如需不同采样率，请使用包装类添加`sample_rate`属性
  - 或使用`load_track()`方法并明确指定`sample_rate`参数
- **播放时处理**：播放时会进行实时采样率转换以适配音频引擎
- **大文件支持**：自动使用分块加载，但不支持流式播放（需保持原始采样率）

**示例：**

**基础用法：**
```python
# 加载文件（保持原始44.1kHz采样率）
engine.load_track_unsampled("hq_music", "music_44k.wav")

# 加载文件并添加静音填充
engine.load_track_unsampled("voice_clip", "voice.wav",
                           silent_lpadding_ms=300,  # 开头300ms静音
                           silent_rpadding_ms=500)  # 结尾500ms静音

# 使用回调监控加载过程
def on_load_complete(track_id, success, error=None):
    if success:
        info = engine.get_track_info(track_id)
        print(f"轨道 {track_id} 加载成功")
        print(f"原始采样率: {info['sample_rate']}Hz")
        print(f"引擎采样率: {info['engine_sample_rate']}Hz")
        engine.play(track_id)
    else:
        print(f"加载失败: {error}")

engine.load_track_unsampled("original_quality", "studio_master.wav",
                           on_complete=on_load_complete)
```

**NumPy数组用法：**
```python
# 普通numpy数组（将使用引擎采样率）
audio_data = np.random.randn(48000, 2).astype(np.float32)
engine.load_track_unsampled("generated", audio_data)

# 带采样率信息的包装数组
class AudioArray:
    def __init__(self, data, sample_rate):
        self.data = data
        self.sample_rate = sample_rate
        self.shape = data.shape
        self.dtype = data.dtype
        self.ndim = data.ndim
    
    def __getattr__(self, name):
        return getattr(self.data, name)
    
    def __getitem__(self, key):
        return self.data[key]

# 44.1kHz的音频数据
audio_44k = np.random.randn(44100, 2).astype(np.float32)
wrapped_audio = AudioArray(audio_44k, 44100)
engine.load_track_unsampled("custom_rate", wrapped_audio)
```

**与普通load_track的对比：**
```python
# 方式1: 普通load_track（重采样到引擎采样率）
engine.load_track("resampled", "music_44k.wav")  # 44.1kHz -> 48kHz

# 方式2: load_track_unsampled（保持原始采样率）
engine.load_track_unsampled("original", "music_44k.wav")  # 保持44.1kHz

# 检查结果
info1 = engine.get_track_info("resampled")
info2 = engine.get_track_info("original")

print(f"普通加载采样率: {info1['sample_rate']}Hz")      # 48000Hz
print(f"原样加载采样率: {info2['sample_rate']}Hz")      # 44100Hz
```

**适用场景：**
- 音频分析应用（需要保持原始采样率精度）
- 高质量音频处理（避免不必要的重采样）
- 多采样率音频混合（每个轨道保持各自最佳采样率）
- 专业音频制作（保持母带质量）
- 音频格式转换工具

##### unload_track()

卸载轨道并释放内存。

```python
unload_track(track_id)
```

**参数说明：**
- `track_id` (str): 要卸载的轨道ID

**返回值：** `bool` - 卸载是否成功

**示例：**
```python
# 卸载单个轨道
if engine.unload_track("old_music"):
    print("轨道卸载成功")

# 批量卸载不需要的轨道
unused_tracks = ["temp1", "temp2", "temp3"]
for track_id in unused_tracks:
    engine.unload_track(track_id)
```

##### clear_all_tracks()

清除所有已加载的轨道。

```python
clear_all_tracks()
```

**示例：**
```python
# 清除所有轨道
engine.clear_all_tracks()
print("所有轨道已清除")

# 重新开始前清理
engine.clear_all_tracks()
engine.load_track("new_session", "new_audio.wav")
```

#### 播放控制方法

##### play()

开始播放轨道。

```python
play(track_id, fade_in=False, loop=False, seek=None, volume=None)
```

**参数说明：**
- `track_id` (str): 要播放的轨道ID
- `fade_in` (bool): 是否淡入，默认False
- `loop` (bool): 是否循环播放，默认False
- `seek` (float, optional): 从指定位置开始播放（秒）
- `volume` (float, optional): 设置播放音量 (0.0-1.0)

**示例：**
```python
# 基本播放
engine.play("music")

# 淡入播放
engine.play("ambient", fade_in=True)

# 循环播放
engine.play("background", loop=True)

# 从指定位置播放
engine.play("song", seek=30.0)  # 从30秒开始

# 设置音量播放
engine.play("effect", volume=0.5)

# 组合参数
engine.play("intro", fade_in=True, volume=0.8, seek=5.0)
```

##### stop()

停止播放轨道。

```python
stop(track_id, fade_out=True, delay_sec=0.0, fade_duration=None)
```

**参数说明：**
- `track_id` (str): 要停止的轨道ID
- `fade_out` (bool): 是否淡出，默认True
- `delay_sec` (float): 延迟停止时间（秒），默认0.0
- `fade_duration` (float, optional): 自定义淡出时长（秒），默认None

**示例：**
```python
# 淡出停止
engine.stop("music")

# 立即停止
engine.stop("effect", fade_out=False)

# 15秒后开始淡出停止（内置定时器）
engine.stop("intro", delay_sec=15.0)

# 5秒后开始，用2秒时间淡出停止
engine.stop("background", delay_sec=5.0, fade_duration=2.0)

# 批量停止
playing_tracks = engine.get_playing_tracks()
for track_id in playing_tracks:
    engine.stop(track_id, fade_out=True)

# 取消之前安排的定时停止
engine.cancel_scheduled_task("music", "stop")
```

##### play_for_duration()

播放指定时长后自动停止。

```python
play_for_duration(track_id, duration_sec, fade_in=False, fade_out=True, 
                 fade_out_duration=None, volume=None)
```

**参数说明：**
- `track_id` (str): 要播放的轨道ID
- `duration_sec` (float): 播放持续时间（秒）
- `fade_in` (bool): 是否淡入开始，默认False
- `fade_out` (bool): 是否淡出停止，默认True
- `fade_out_duration` (float, optional): 淡出时长（秒）
- `volume` (float, optional): 播放音量

**返回值：** `bool` - 是否成功开始播放并安排停止

**示例：**
```python
# 播放15秒后自动淡出停止
engine.play_for_duration("intro", 15.0)

# 播放10秒，用2秒时间淡出停止
engine.play_for_duration("music", 10.0, fade_out_duration=2.0)

# 淡入播放5秒后立即停止
engine.play_for_duration("effect", 5.0, fade_in=True, fade_out=False)

# 播放背景音乐30秒，音量50%
engine.play_for_duration("ambient", 30.0, volume=0.5)
```

##### pause() / resume()

暂停和恢复播放。

```python
pause(track_id)
resume(track_id)
```

**参数说明：**
- `track_id` (str): 要暂停/恢复的轨道ID

**示例：**
```python
# 暂停播放
engine.pause("music")

# 检查状态
if engine.is_track_paused("music"):
    print("轨道已暂停")

# 恢复播放
engine.resume("music")

# 切换暂停状态
if engine.is_track_playing("music"):
    engine.pause("music")
else:
    engine.resume("music")
```

#### 音频属性控制方法

##### set_volume()

设置轨道音量。

```python
set_volume(track_id, volume)
```

**参数说明：**
- `track_id` (str): 轨道ID
- `volume` (float): 音量值 (0.0-1.0)

**示例：**
```python
# 设置音量
engine.set_volume("music", 0.7)

# 渐变音量效果
import time
for volume in np.linspace(1.0, 0.0, 50):
    engine.set_volume("music", volume)
    time.sleep(0.05)  # 2.5秒淡出
```

##### set_speed()

设置播放速度。

```python
set_speed(track_id, speed)
```

**参数说明：**
- `track_id` (str): 轨道ID
- `speed` (float): 播放速度 (0.1-4.0)

**返回值：** `bool` - 设置是否成功

**示例：**
```python
# 加速播放
engine.set_speed("music", 1.5)  # 150%速度

# 慢速播放
engine.set_speed("speech", 0.8)  # 80%速度

# 变速效果
speeds = [1.0, 1.2, 1.5, 1.2, 1.0, 0.8, 1.0]
for speed in speeds:
    engine.set_speed("music", speed)
    time.sleep(1)
```

##### set_loop()

设置循环播放。

```python
set_loop(track_id, loop)
```

**参数说明：**
- `track_id` (str): 轨道ID
- `loop` (bool): 是否循环播放

**返回值：** `bool` - 设置是否成功

**示例：**
```python
# 启用循环
engine.set_loop("background", True)

# 禁用循环
engine.set_loop("effect", False)

# 动态切换循环状态
current_loop = engine.get_track_info("music").get("loop", False)
engine.set_loop("music", not current_loop)
```

##### seek()

跳转到指定播放位置。

```python
seek(track_id, position_sec)
```

**参数说明：**
- `track_id` (str): 轨道ID
- `position_sec` (float): 目标位置（秒）

**示例：**
```python
# 跳转到30秒位置
engine.seek("music", 30.0)

# 跳转到开头
engine.seek("song", 0.0)

# 跳转到中间位置
duration = engine.get_duration("music")
engine.seek("music", duration / 2)
```

#### 静音控制方法

##### mute() / unmute()

静音和取消静音。

```python
mute(track_id)
unmute(track_id)
toggle_mute(track_id)
```

**参数说明：**
- `track_id` (str): 轨道ID

**返回值：** `bool` - 操作是否成功

**示例：**
```python
# 静音
engine.mute("music")

# 取消静音
engine.unmute("music")

# 切换静音状态
engine.toggle_mute("music")

# 检查静音状态
if engine.is_muted("music"):
    print("轨道已静音")

# 批量操作
engine.mute_all_tracks()  # 全部静音
engine.unmute_all_tracks()  # 全部取消静音

# 获取已静音的轨道
muted_tracks = engine.get_muted_tracks()
print(f"已静音轨道: {muted_tracks}")
```

#### 高级音频处理方法

##### calculate_rms_loudness()

计算轨道的RMS响度。

```python
calculate_rms_loudness(track_id, duration=2.0)
```

**参数说明：**
- `track_id` (str): 轨道ID
- `duration` (float): 分析时长（秒），默认2.0

**返回值：** `float` - RMS响度值

**示例：**
```python
# 计算响度
loudness = engine.calculate_rms_loudness("music")
print(f"轨道响度: {loudness:.3f}")

# 分析更长时间
loudness = engine.calculate_rms_loudness("speech", duration=5.0)

# 响度对比
music_loudness = engine.calculate_rms_loudness("music")
voice_loudness = engine.calculate_rms_loudness("voice")
print(f"音乐响度: {music_loudness:.3f}, 语音响度: {voice_loudness:.3f}")
```

##### match_loudness()

匹配两个轨道的响度。

```python
match_loudness(track1_id, track2_id, target_loudness=0.7)
```

**参数说明：**
- `track1_id` (str): 第一个轨道ID
- `track2_id` (str): 第二个轨道ID
- `target_loudness` (float): 目标响度值，默认0.7

**返回值：** `tuple[float, float]` - (轨道1新音量, 轨道2新音量)

**示例：**
```python
# 匹配两个轨道的响度
vol1, vol2 = engine.match_loudness("music", "voice")
print(f"调整后音量 - 音乐: {vol1:.3f}, 语音: {vol2:.3f}")

# 指定目标响度
vol1, vol2 = engine.match_loudness("track1", "track2", target_loudness=0.5)

# 批量响度匹配
tracks = ["music", "voice", "effect"]
for i in range(len(tracks)-1):
    engine.match_loudness(tracks[i], tracks[i+1])
```

##### crossfade()

交叉淡入淡出切换。

```python
crossfade(from_track, to_track, duration=1.0, to_track_volume=None, 
         to_track_loop=False)
```

**参数说明：**
- `from_track` (str): 淡出的轨道ID
- `to_track` (str): 淡入的轨道ID
- `duration` (float): 交叉淡入淡出时长（秒），默认1.0
- `to_track_volume` (float, optional): 淡入轨道的目标音量
- `to_track_loop` (bool): 淡入轨道是否循环，默认False

**返回值：** `bool` - 操作是否成功

**示例：**
```python
# 基本交叉淡入淡出
engine.crossfade("old_music", "new_music", duration=2.0)

# 指定淡入音量
engine.crossfade("music1", "music2", 
                duration=1.5, 
                to_track_volume=0.8)

# 淡入到循环轨道
engine.crossfade("intro", "loop_music", 
                duration=1.0, 
                to_track_loop=True)

# 连续交叉淡入淡出
tracks = ["intro", "verse1", "chorus", "verse2", "outro"]
for i in range(len(tracks)-1):
    # 等待当前轨道播放一段时间
    time.sleep(10)
    # 交叉淡入淡出到下一个轨道
    engine.crossfade(tracks[i], tracks[i+1], duration=1.5)
```

#### 信息查询方法

##### get_track_info()

获取轨道详细信息。

```python
get_track_info(track_id)
```

**参数说明：**
- `track_id` (str): 轨道ID

**返回值：** `dict` - 轨道信息字典

**示例：**
```python
# 获取轨道信息
info = engine.get_track_info("music")
if info:
    print(f"轨道: {info['track_id']}")
    print(f"时长: {info['duration']:.2f}秒")
    print(f"位置: {info['position']:.2f}秒")
    print(f"音量: {info['volume']:.2f}")
    print(f"速度: {info['speed']:.2f}")
    print(f"循环: {info['loop']}")
    print(f"播放中: {info['is_playing']}")
    print(f"暂停: {info['is_paused']}")
    print(f"静音: {info['is_muted']}")

# 检查特定属性
info = engine.get_track_info("voice")
if info and info['is_streaming']:
    print("这是一个流式轨道")
```

##### get_position() / get_duration()

获取播放位置和时长。

```python
get_position(track_id)
get_duration(track_id)
```

**参数说明：**
- `track_id` (str): 轨道ID

**返回值：** `float` - 位置/时长（秒）

**示例：**
```python
# 显示播放进度
position = engine.get_position("music")
duration = engine.get_duration("music")
progress = position / duration if duration > 0 else 0
print(f"播放进度: {position:.1f}/{duration:.1f}秒 ({progress:.1%})")

# 检查是否接近结束
remaining = duration - position
if remaining < 5.0:
    print("轨道即将结束")
```

##### list_tracks()

列出所有轨道信息。

```python
list_tracks()
```

**返回值：** `List[dict]` - 所有轨道信息列表

**示例：**
```python
# 列出所有轨道
tracks = engine.list_tracks()
print(f"总轨道数: {len(tracks)}")

for track in tracks:
    status = "播放中" if track['is_playing'] else "已停止"
    print(f"- {track['track_id']}: {status}, 音量: {track['volume']:.2f}")

# 按状态筛选
playing_tracks = [t for t in tracks if t['is_playing']]
paused_tracks = [t for t in tracks if t['is_paused']]
print(f"播放中: {len(playing_tracks)}, 暂停: {len(paused_tracks)}")
```

##### get_performance_stats()

获取性能统计信息。

```python
get_performance_stats()
```

**返回值：** `dict` - 性能统计字典

**示例：**
```python
# 获取性能统计
stats = engine.get_performance_stats()
print(f"CPU使用率: {stats['cpu_usage']:.1f}%")
print(f"峰值电平: {stats['peak_level']:.3f}")
print(f"活跃轨道: {stats['active_tracks']}")
print(f"总轨道数: {stats['total_tracks']}")
print(f"音频中断次数: {stats['underrun_count']}")

# 性能监控循环
while True:
    stats = engine.get_performance_stats()
    if stats['cpu_usage'] > 80:
        print("⚠️ CPU使用率过高!")
    if stats['peak_level'] > 0.95:
        print("⚠️ 音频电平过高，可能失真!")
    time.sleep(1)
```

#### 引擎控制方法

##### start() / shutdown()

启动和关闭音频引擎。

```python
start()
shutdown()
```

**示例：**
```python
# 启动引擎
try:
    engine.start()
    print("音频引擎已启动")
except RuntimeError as e:
    print(f"启动失败: {e}")

# 使用上下文管理器确保清理
class AudioContext:
    def __init__(self, engine):
        self.engine = engine
    
    def __enter__(self):
        self.engine.start()
        return self.engine
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.engine.shutdown()

# 使用示例
with AudioContext(engine) as audio:
    audio.load_track("music", "song.wav")
    audio.play("music")
    time.sleep(10)
# 自动关闭
```

#### 批量操作方法

```python
# 批量播放控制
pause_all_tracks()          # 暂停所有轨道
resume_all_tracks()         # 恢复所有轨道
stop_all_tracks(fade_out=True)  # 停止所有轨道

# 批量状态查询
get_playing_tracks()        # 获取播放中的轨道列表
get_paused_tracks()         # 获取暂停的轨道列表
get_track_count()          # 获取轨道数量统计

# 定时任务管理
cancel_scheduled_task(track_id, task_type="stop")  # 取消指定轨道的定时任务
cancel_all_scheduled_tasks()                       # 取消所有定时任务
get_scheduled_tasks()                             # 获取所有定时任务信息
```

**示例：**
```python
# 暂停所有轨道
paused = engine.pause_all_tracks()
print(f"已暂停 {len(paused)} 个轨道: {paused}")

# 恢复所有轨道
resumed = engine.resume_all_tracks()
print(f"已恢复 {len(resumed)} 个轨道: {resumed}")

# 淡出停止所有轨道
stopped = engine.stop_all_tracks(fade_out=True)

# 轨道统计
counts = engine.get_track_count()
print(f"轨道统计: {counts}")
# 输出: {'total': 5, 'playing': 2, 'paused': 1, 'stopped': 2}

# 定时任务管理
# 安排多个定时停止
engine.stop("music1", delay_sec=10.0)
engine.stop("music2", delay_sec=20.0)
engine.stop("music3", delay_sec=30.0)

# 查看定时任务
scheduled = engine.get_scheduled_tasks()
for task, remaining_time in scheduled.items():
    print(f"任务 {task}: 剩余 {remaining_time:.1f} 秒")

# 取消特定任务
engine.cancel_scheduled_task("music2", "stop")

# 取消所有定时任务
cancelled_count = engine.cancel_all_scheduled_tasks()
print(f"已取消 {cancelled_count} 个定时任务")
```

#### 内存和流式播放管理

```python
# 内存使用情况
get_memory_usage()          # 获取内存使用统计
optimize_memory()           # 优化内存使用

# 流式播放控制
get_streaming_stats()       # 获取流式播放统计
set_streaming_config()      # 设置流式播放配置
is_track_streaming()        # 检查轨道是否使用流式播放
```

**示例：**
```python
# 内存管理
memory_info = engine.get_memory_usage()
print(f"内存使用: {memory_info}")

if memory_info['total_mb'] > 500:  # 超过500MB
    print("内存使用过高，进行优化...")
    result = engine.optimize_memory()
    print(f"优化结果: {result}")

# 流式播放配置
engine.set_streaming_config(
    enable_streaming=True,
    threshold_mb=50  # 50MB以上文件使用流式播放
)

# 检查流式播放状态
streaming_stats = engine.get_streaming_stats()
print(f"流式播放统计: {streaming_stats}")

for track_id in engine.list_tracks():
    if engine.is_track_streaming(track_id):
        print(f"轨道 {track_id} 使用流式播放")
```

## 高级使用示例

### 音频游戏引擎集成

```python
class GameAudioManager:
    def __init__(self):
        self.engine = AudioEngine(
            sample_rate=48000,
            buffer_size=512,  # 低延迟
            max_tracks=16
        )
        self.engine.start()
    
    def play_background_music(self, music_file):
        self.engine.load_track("bgm", music_file, auto_normalize=True)
        self.engine.play("bgm", loop=True, fade_in=True)
    
    def play_sound_effect(self, effect_file, volume=1.0):
        import uuid
        effect_id = f"sfx_{uuid.uuid4().hex[:8]}"
        self.engine.load_track(effect_id, effect_file)
        self.engine.play(effect_id, volume=volume)
        # 播放完成后自动清理
        duration = self.engine.get_duration(effect_id)
        threading.Timer(duration + 1, 
                       lambda: self.engine.unload_track(effect_id)).start()
    
    def crossfade_music(self, new_music_file):
        self.engine.load_track("bgm_new", new_music_file)
        self.engine.crossfade("bgm", "bgm_new", duration=2.0, to_track_loop=True)
        # 清理旧轨道
        threading.Timer(3.0, lambda: self.engine.unload_track("bgm")).start()

# 使用示例
game_audio = GameAudioManager()
game_audio.play_background_music("background.wav")
game_audio.play_sound_effect("gunshot.wav", volume=0.8)
game_audio.crossfade_music("boss_music.wav")
```

### 播客/直播音频处理

```python
class PodcastMixer:
    def __init__(self):
        self.engine = AudioEngine(
            sample_rate=48000,
            channels=2,
            enable_streaming=True,
            streaming_threshold_mb=30
        )
        self.engine.start()
    
    def add_intro_music(self, music_file, duration_sec=15.0):
        """添加intro音乐，指定时长后自动淡出"""
        self.engine.load_track("intro", music_file)
        # 使用内置定时器，15秒后自动淡出
        self.engine.play_for_duration("intro", duration_sec, fade_in=True)
    
    def add_voice_track(self, voice_file, delay_sec=0):
        """添加语音轨道，支持延迟播放"""
        def load_and_play():
            self.engine.load_track("voice", voice_file, 
                                 silent_lpadding_ms=300,  # 前置静音
                                 silent_rpadding_ms=300)  # 后置静音
            # 与背景音乐匹配响度
            if self.engine.is_track_loaded("bgm"):
                self.engine.match_loudness("voice", "bgm", target_loudness=0.7)
            
            if delay_sec > 0:
                # 使用内置定时功能延迟播放
                self.engine.play("voice")  # 先准备播放状态
                self.engine.pause("voice")  # 暂停
                # delay_sec秒后恢复播放
                self.engine.schedule_resume("voice", delay_sec)
            else:
                self.engine.play("voice")
        
        load_and_play()
    
    def add_background_music(self, music_file, volume=0.3):
        """添加背景音乐"""
        self.engine.load_track("bgm", music_file, auto_normalize=True)
        self.engine.play("bgm", loop=True, volume=volume)
    
    def create_timed_segment(self, segment_tracks, segment_durations):
        """创建定时音频段落"""
        for i, (track_id, duration) in enumerate(zip(segment_tracks, segment_durations)):
            if i == 0:
                # 第一个段落立即播放
                self.engine.play_for_duration(track_id, duration)
            else:
                # 后续段落使用延迟播放
                total_delay = sum(segment_durations[:i])
                self.engine.play_for_duration(track_id, duration, delay_sec=total_delay)

# 使用示例
podcast = PodcastMixer()

# 添加15秒intro音乐（自动淡出）
podcast.add_intro_music("intro.wav", duration_sec=15.0)

# 添加背景音乐
podcast.add_background_music("ambient.wav", volume=0.2)

# 10秒后开始播放语音
podcast.add_voice_track("episode1.wav", delay_sec=10)

# 创建定时段落播放
segments = ["segment1", "segment2", "segment3"]
durations = [30.0, 45.0, 20.0]  # 各段落时长
podcast.create_timed_segment(segments, durations)
```

### 自动音频节目调度器

```python
class AudioScheduler:
    def __init__(self):
        self.engine = AudioEngine()
        self.engine.start()
        self.schedule = []  # 节目时间表
    
    def add_scheduled_item(self, track_id, start_time, duration, fade_in=True, fade_out=True):
        """添加定时播放项目"""
        self.schedule.append({
            'track_id': track_id,
            'start_time': start_time,
            'duration': duration,
            'fade_in': fade_in,
            'fade_out': fade_out
        })
    
    def start_schedule(self):
        """启动节目调度"""
        for item in self.schedule:
            # 使用内置定时器安排播放
            self.engine.play_for_duration(
                item['track_id'],
                item['duration'],
                fade_in=item['fade_in'],
                fade_out=item['fade_out']
            )
            
            # 如果有延迟，先暂停再安排恢复
            if item['start_time'] > 0:
                self.engine.pause(item['track_id'])
                # 使用内置定时器恢复播放
                self.schedule_resume(item['track_id'], item['start_time'])
    
    def schedule_resume(self, track_id, delay_sec):
        """安排延迟恢复播放（这里简化示例，实际可以扩展AudioEngine添加此功能）"""
        def resume_track():
            self.engine.resume(track_id)
        
        timer = threading.Timer(delay_sec, resume_track)
        timer.start()

# 使用示例
scheduler = AudioScheduler()

# 加载节目音频
scheduler.engine.load_track("news", "news.wav")
scheduler.engine.load_track("music", "music.wav")
scheduler.engine.load_track("ads", "ads.wav")

# 安排节目时间表
scheduler.add_scheduled_item("news", 0, 300)      # 立即播放5分钟新闻
scheduler.add_scheduled_item("music", 300, 180)   # 5分钟后播放3分钟音乐
scheduler.add_scheduled_item("ads", 480, 60)      # 8分钟后播放1分钟广告

# 启动调度
scheduler.start_schedule()
```

## 性能优化建议

1. **缓冲区大小**: 较小的缓冲区降低延迟但增加CPU使用率
2. **采样率**: 更高的采样率提高质量但需要更多处理能力
3. **轨道限制**: 将同时播放的轨道数量控制在硬件合理范围内
4. **内存管理**: 及时卸载不使用的轨道以释放内存
5. **流式播放**: 对大文件使用流式播放模式
6. **质量设置**: 使用可选依赖获得最佳音频质量

## 平台支持

- Windows
- macOS
- Linux

## 依赖要求

### 核心依赖
- Python 3.9+
- numpy >= 1.19.0
- sounddevice >= 0.4.0
- soundfile >= 0.10.0

### 可选依赖
- librosa >= 0.8.0 (高质量重采样)
- scipy >= 1.7.0 (信号处理)
- pyrubberband >= 0.3.0 (时间拉伸)

## 开发和贡献

### 运行测试
```bash
# 运行所有测试
pytest tests/ -v

# 运行覆盖率测试
pytest tests/ -v --cov=realtimemix

# 运行特定测试
pytest tests/test_realtimemix.py::TestAudioEngine::test_load_track_from_array -v
```