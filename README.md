# realtimemix

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Version](https://img.shields.io/badge/version-1.1.1-orange.svg)

一个高性能的Python实时音频混音引擎，专为专业音频应用、语音处理和多媒体项目设计。

## ✨ 核心特性

### 🎵 实时音频处理
- **低延迟混音** - 可配置缓冲区大小，支持专业级音频延迟控制
- **多轨并行处理** - 同时处理多达32+个音频轨道，线程安全设计
- **零延迟切换** - 支持瞬时音频切换，无淡入淡出延迟
- **高质量重采样** - 集成librosa/scipy高级音频处理算法

### 🎚️ 专业音频功能
- **Matchering集成** - 内置专业音频匹配技术，自动均衡、响度和频率匹配
- **响度分析与匹配** - RMS响度计算，自动音量级别匹配
- **交叉淡入淡出** - 专业级音频过渡效果
- **温和EQ处理** - 减少金属音色的智能音频处理

### 💾 大文件支持
- **流式播放** - 支持GB级大文件的内存高效播放
- **智能缓存** - 优化的缓冲池和内存管理
- **异步加载** - 非阻塞音频文件加载，支持进度回调
- **静音填充** - 精确的音频时序控制和对齐

### 🔊 音频效果与控制
- **实时音量控制** - 动态音量调节，支持渐变效果
- **变速播放** - 保持音调的速度调节（可选pyrubberband支持）
- **循环播放** - 无缝循环，支持精确循环点控制
- **多种音频格式** - 通过soundfile支持WAV、FLAC、MP3等格式

## 🛠️ 安装

### 基础安装
```bash
pip install realtimemix
```

### 高质量音频处理（推荐）
```bash
pip install realtimemix[high-quality]
```

### Matchering专业音频匹配
```bash
pip install matchering
```

### 时间拉伸功能
```bash
pip install realtimemix[time-stretch]
```

### 完整功能安装
```bash
pip install realtimemix[all]
pip install matchering
```

### 开发环境
```bash
git clone https://github.com/birchkwok/realtimemix.git
cd realtimemix
pip install -e .[dev]
pip install matchering
```

## 🚀 快速开始

### 基础音频播放

```python
import numpy as np
from realtimemix import AudioEngine

# 初始化音频引擎
engine = AudioEngine(
    sample_rate=48000,    # 高采样率
    buffer_size=1024,     # 低延迟缓冲
    channels=2            # 立体声
)

# 启动引擎
engine.start()

# 加载音频文件
engine.load_track("background", "music.wav", auto_normalize=True)
engine.load_track("voice", "speech.wav")

# 播放控制
engine.play("background", loop=True, fade_in=True)
engine.play("voice", volume=0.8)

# 实时控制
engine.set_volume("background", 0.3)  # 降低背景音乐
engine.crossfade("background", "voice", duration=1.5)  # 交叉淡入淡出

# 清理
engine.shutdown()
```

### 专业音频匹配（Matchering）

```python
from realtimemix import AudioEngine

engine = AudioEngine()
engine.start()

# 1. 加载主音轨（参考音轨）
engine.load_track("main_audio", "主音频.wav")

# 2. 使用Matchering加载并匹配副音轨
success = engine.load_track_with_matchering(
    track_id="sub_audio",
    file_path="副音频.wav",
    reference_track_id="main_audio",
    reference_start_sec=10.0,      # 从主音频10秒处开始参考
    reference_duration_sec=5.0,    # 参考5秒片段
    gentle_matchering=True         # 使用温和处理减少金属音色
)

if success:
    # 播放匹配后的音频，音质和响度已自动匹配
    engine.play("main_audio")
    # 在合适时机切换到副音轨，音质完美衔接
    engine.crossfade("main_audio", "sub_audio", duration=0.1)

engine.shutdown()
```

### 语音无缝融合应用

```python
from realtimemix import AudioEngine

class SpeechFusion:
    def __init__(self):
        self.engine = AudioEngine(sample_rate=48000, channels=2)
        self.engine.start()
    
    def fuse_speech(self, main_file: str, insert_file: str, insert_at: float):
        """在指定时间点无缝插入语音片段"""
        
        # 加载主语音
        self.engine.load_track("main", main_file)
        
        # 使用Matchering加载插入语音，自动匹配主语音特征
        success = self.engine.load_track_with_matchering(
            track_id="insert",
            file_path=insert_file,
            reference_track_id="main",
            reference_start_sec=insert_at,
            reference_duration_sec=3.0,
            silent_lpadding_ms=100  # 100ms前置静音对齐
        )
        
        if success:
            # 播放主语音到切换点
            self.engine.play("main")
            self._wait_to_position(insert_at)
            
            # 零延迟瞬时切换
            self.engine.set_volume("main", 0.0)
            self.engine.play("insert", volume=0.8)
            
            # 插入语音播放完毕后恢复主语音
            insert_duration = self._get_track_duration("insert")
            self._wait_duration(insert_duration)
            self.engine.set_volume("insert", 0.0)
            self.engine.set_volume("main", 0.8)
    
    def _wait_to_position(self, seconds: float):
        import time
        time.sleep(seconds)
    
    def _wait_duration(self, seconds: float):
        import time
        time.sleep(seconds)
    
    def _get_track_duration(self, track_id: str) -> float:
        info = self.engine.get_track_info(track_id)
        return info.get('duration', 0.0) if info else 0.0

# 使用示例
fusion = SpeechFusion()
fusion.fuse_speech("长篇语音.wav", "插入片段.wav", insert_at=30.0)
```

### 大文件流式播放

```python
from realtimemix import AudioEngine

# 针对大文件优化的配置
engine = AudioEngine(
    enable_streaming=True,
    streaming_threshold_mb=50,    # 50MB以上启用流式播放
    max_tracks=8                  # 限制并发轨道数
)

engine.start()

# 加载大文件（自动启用流式播放）
def on_progress(track_id, progress, message=""):
    print(f"加载进度 {track_id}: {progress:.1%} - {message}")

def on_complete(track_id, success, error=None):
    if success:
        print(f"大文件 {track_id} 加载成功，开始播放")
        engine.play(track_id)
    else:
        print(f"加载失败: {error}")

engine.load_track(
    "large_audio", 
    "大音频文件.wav",
    progress_callback=on_progress,
    on_complete=on_complete
)

# 异步加载，不阻塞主线程
print("继续执行其他任务...")
```

## 📚 核心API参考

### AudioEngine

#### 构造函数

```python
AudioEngine(
    sample_rate=48000,           # 采样率
    buffer_size=1024,            # 缓冲区大小
    channels=2,                  # 声道数
    max_tracks=32,               # 最大轨道数
    device=None,                 # 音频设备
    stream_latency='low',        # 延迟级别
    enable_streaming=True,       # 启用流式播放
    streaming_threshold_mb=100   # 流式播放阈值
)
```

#### 核心方法

##### 音轨管理

```python
# 基础加载
load_track(track_id, source, speed=1.0, auto_normalize=True, 
          silent_lpadding_ms=0.0, on_complete=None)

# Matchering专业匹配加载
load_track_with_matchering(track_id, file_path, reference_track_id,
                          reference_start_sec, reference_duration_sec=10.0,
                          gentle_matchering=True)

# 卸载音轨
unload_track(track_id)

# 清除所有音轨
clear_all_tracks()
```

##### 播放控制

```python
# 播放
play(track_id, fade_in=False, loop=False, seek=None, volume=None)

# 定时播放
play_for_duration(track_id, duration_sec, fade_in=False, fade_out=True)

# 停止
stop(track_id, fade_out=True, delay_sec=0.0)

# 暂停/恢复
pause(track_id)
resume(track_id)
```

##### 音频效果

```python
# 音量控制
set_volume(track_id, volume)

# 速度控制
set_speed(track_id, speed)

# 交叉淡入淡出
crossfade(from_track, to_track, duration=1.0)

# 响度匹配
match_loudness(track1_id, track2_id, target_loudness=0.7)
```

##### 状态查询

```python
# 获取轨道信息
get_track_info(track_id)

# 播放状态
is_track_playing(track_id)
is_track_paused(track_id)

# 获取播放中的轨道
get_playing_tracks()
```

## 🎯 应用场景

### 🎙️ 语音处理
- **播客制作** - 多人语音混音，智能响度匹配
- **有声书制作** - 章节间无缝切换，背景音乐融合
- **配音工程** - 角色语音替换，音质自动匹配
- **语音合成** - TTS语音与真人语音的自然融合

### 🎵 音乐制作
- **现场演出** - 实时音频混音，低延迟监听
- **音乐制作** - 多轨录音，专业音频处理
- **DJ混音** - BPM同步，交叉淡入淡出
- **音频母带处理** - Matchering专业音质匹配

### 🎮 游戏开发
- **背景音乐系统** - 动态音乐切换，情境音效
- **3D空间音频** - 位置音效，环境声模拟
- **语音聊天** - 实时语音处理，降噪优化
- **音效引擎** - 多层音效混合，性能优化

### 📺 多媒体应用
- **视频配音** - 自动音视频同步，响度标准化
- **直播系统** - 实时音频处理，多源混音
- **教育软件** - 互动音频，语音识别集成
- **会议系统** - 多人语音处理，回声消除

## 🔧 高级配置

### 性能优化

```python
# 低延迟配置（专业音频）
engine = AudioEngine(
    sample_rate=96000,      # 高采样率
    buffer_size=256,        # 极小缓冲区
    channels=2,
    stream_latency='low',
    max_tracks=16
)

# 大文件处理配置
engine = AudioEngine(
    enable_streaming=True,
    streaming_threshold_mb=25,  # 更积极的流式播放
    buffer_size=2048,          # 更大缓冲区
    max_tracks=4               # 限制并发数
)

# 移动设备优化配置
engine = AudioEngine(
    sample_rate=44100,     # 标准采样率
    buffer_size=1024,      # 平衡延迟和性能
    channels=2,
    max_tracks=8,          # 限制资源使用
    stream_latency='medium'
)
```

### Matchering高级设置

```python
# 温和处理（推荐用于语音）
engine.load_track_with_matchering(
    track_id="speech",
    file_path="voice.wav", 
    reference_track_id="main",
    reference_start_sec=15.0,
    gentle_matchering=True        # 减少金属音色
)

# 标准处理（用于音乐）
engine.load_track_with_matchering(
    track_id="music",
    file_path="song.wav",
    reference_track_id="main", 
    reference_start_sec=30.0,
    reference_duration_sec=15.0,  # 更长参考片段
    gentle_matchering=False       # 标准EQ处理
)
```

## 📊 性能特征

- **延迟性能**: 最低 ~5ms（256帧缓冲区@48kHz）
- **内存效率**: 流式播放支持GB级文件，内存占用<100MB
- **CPU利用率**: 多线程优化，典型占用<10%（8轨混音）
- **支持格式**: WAV, FLAC, MP3, M4A, OGG等（通过soundfile）
- **采样率范围**: 8kHz - 192kHz
- **位深支持**: 16-bit, 24-bit, 32-bit（整数和浮点）

## 🐛 故障排除

### 常见问题

**导入错误**: 
```bash
# 确保安装了所有依赖
pip install realtimemix[all]
pip install matchering
```

**音频设备问题**:
```python
# 列出可用设备
import sounddevice as sd
print(sd.query_devices())

# 指定设备
engine = AudioEngine(device=1)  # 使用设备1
```

**Matchering处理失败**:
```python
# 检查音频文件格式和长度
# 确保参考片段至少1秒以上
# 避免使用完全静音的参考片段
```

**内存不足**:
```python
# 启用流式播放
engine = AudioEngine(
    enable_streaming=True,
    streaming_threshold_mb=50
)
```

## 🤝 贡献

欢迎贡献代码！请查看[贡献指南](https://github.com/birchkwok/realtimemix/blob/main/CONTRIBUTING.md)。

### 开发环境设置

```bash
git clone https://github.com/birchkwok/realtimemix.git
cd realtimemix
pip install -e .[dev]
pip install matchering

# 运行测试
pytest tests/ -v

# 代码格式化
black realtimemix/
flake8 realtimemix/
```

## 📄 许可证

本项目采用 [MIT许可证](LICENSE)。

## 🙏 致谢

- [sounddevice](https://github.com/spatialaudio/python-sounddevice) - 跨平台音频I/O
- [soundfile](https://github.com/bastibe/python-soundfile) - 音频文件读写
- [librosa](https://github.com/librosa/librosa) - 高质量音频处理
- [matchering](https://github.com/sergree/matchering) - 专业音频匹配技术
- [numpy](https://github.com/numpy/numpy) - 高性能数值计算

---

**RealtimeMix** - 让音频处理变得简单而专业 🎵

