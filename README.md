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

### ⏰ 实时位置回调 **[新功能]**
- **高精度回调** - 5-15ms精度的音频位置回调机制
- **TTS精确插入** - 支持在音频特定位置精确插入语音
- **全局位置监听** - 实时监控所有轨道的播放位置
- **多轨道回调** - 支持多个轨道的独立位置回调管理

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

### 实时位置回调应用

```python
from realtimemix import AudioEngine

# 初始化音频引擎
engine = AudioEngine(sample_rate=48000, buffer_size=1024)
engine.start()

# 加载主音频
engine.load_track("main_audio", "podcast.wav")

# 定义TTS插入回调
def insert_tts_callback(track_id, target_time, actual_time):
    """在指定位置精确插入TTS语音"""
    print(f"🎯 TTS插入触发: {actual_time:.3f}s (目标: {target_time:.3f}s)")
    
    # 降低主音频音量
    engine.set_volume("main_audio", 0.2)
    
    # 播放TTS插入
    engine.load_track("tts_insert", "生成的语音.wav")
    engine.play("tts_insert", volume=0.8)
    
    # 3秒后恢复主音频
    def restore_main():
        engine.stop("tts_insert")
        engine.set_volume("main_audio", 0.8)
    
    # 延迟恢复（实际应用中可以监听TTS播放完成）
    import threading
    threading.Timer(3.0, restore_main).start()

# 注册精确位置回调（在25.5秒处插入TTS）
success = engine.register_position_callback(
    track_id="main_audio",
    target_time=25.5,
    callback_func=insert_tts_callback,
    tolerance=0.010  # 10ms容忍度
)

if success:
    print("✅ 位置回调注册成功")
    
    # 开始播放
    engine.play("main_audio")
    
    # 获取回调统计
    stats = engine.get_position_callback_stats()
    print(f"活跃回调数: {stats['active_callbacks']}")

# 清理
engine.shutdown()
```

### 全局位置监听示例

```python
from realtimemix import AudioEngine

engine = AudioEngine()
engine.start()

# 全局位置监听器
def position_monitor(track_id: str, position: float):
    """监控所有轨道的播放位置"""
    minutes = int(position // 60)
    seconds = position % 60
    print(f"🎵 {track_id}: {minutes:02d}:{seconds:05.2f}")

# 注册全局监听器
engine.add_global_position_listener(position_monitor)

# 加载并播放多个轨道
engine.load_track("bgm", "background.wav")
engine.load_track("voice", "speech.wav")

engine.play("bgm", loop=True, volume=0.3)
engine.play("voice", volume=0.8)

# 移除监听器
engine.remove_global_position_listener(position_monitor)
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

##### 位置回调 **[新功能]**

```python
# 注册位置回调
register_position_callback(track_id, target_time, callback_func, tolerance=0.010)

# 移除位置回调
remove_position_callback(track_id, target_time=None)  # None表示移除该轨道所有回调

# 清空所有位置回调
clear_all_position_callbacks()

# 添加全局位置监听器
add_global_position_listener(listener_func)

# 移除全局位置监听器
remove_global_position_listener(listener_func)

# 获取回调统计信息
get_position_callback_stats()
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

# 获取当前播放位置
get_position(track_id)

# 获取轨道时长
get_duration(track_id)
```

## 🎯 位置回调详细指南

### 基础概念

位置回调机制允许您在音频播放到特定时间点时触发回调函数，实现精确的音频操作控制。

### 核心特性
- **高精度**: 5-15ms的触发精度
- **多轨道支持**: 每个轨道可以独立设置多个回调
- **容忍度可配置**: 可调整触发时间容忍度
- **全局监听**: 支持全局位置监听器
- **自动清理**: 触发后自动清理回调，防止内存泄漏

### 详细使用示例

#### 1. 精确TTS插入

```python
from realtimemix import AudioEngine
import time

engine = AudioEngine()
engine.start()

# 加载主音频
engine.load_track("podcast", "长篇音频.wav")

# 预加载TTS音频
engine.load_track("tts_correction", "纠正语音.wav")

def tts_insert_handler(track_id, target_time, actual_time):
    """TTS插入处理函数"""
    precision_ms = abs(actual_time - target_time) * 1000
    print(f"🎯 TTS插入: 目标{target_time:.3f}s, 实际{actual_time:.3f}s, 精度{precision_ms:.1f}ms")
    
    # 淡出主音频
    engine.set_volume("podcast", 0.1)
    
    # 播放TTS纠正
    engine.play("tts_correction", volume=0.9)
    
    # 监听TTS播放完成
    tts_duration = engine.get_duration("tts_correction")
    
    def restore_main_audio():
        time.sleep(tts_duration)
        engine.stop("tts_correction")
        engine.set_volume("podcast", 0.8)
    
    import threading
    threading.Thread(target=restore_main_audio, daemon=True).start()

# 在句子结束前50ms插入TTS（模拟标点符号检测）
sentence_end_time = 45.2  # 假设在45.2秒处检测到句号
insert_time = sentence_end_time - 0.05  # 提前50ms

success = engine.register_position_callback(
    track_id="podcast",
    target_time=insert_time,
    callback_func=tts_insert_handler,
    tolerance=0.015  # 15ms容忍度
)

if success:
    engine.play("podcast")
    print(f"✅ TTS插入回调已注册在 {insert_time:.3f}s")
```

#### 2. 章节标记和自动切换

```python
def setup_chapter_markers(engine):
    """设置章节标记回调"""
    
    chapters = [
        {"time": 120.0, "name": "第一章", "bgm": "chapter1_bgm.wav"},
        {"time": 300.0, "name": "第二章", "bgm": "chapter2_bgm.wav"},
        {"time": 480.0, "name": "第三章", "bgm": "chapter3_bgm.wav"}
    ]
    
    def chapter_callback(track_id, target_time, actual_time):
        # 找到对应章节
        current_chapter = None
        for chapter in chapters:
            if abs(chapter["time"] - target_time) < 0.1:
                current_chapter = chapter
                break
        
        if current_chapter:
            print(f"📖 进入{current_chapter['name']}")
            
            # 切换背景音乐
            engine.load_track("bgm", current_chapter["bgm"])
            engine.play("bgm", volume=0.3, loop=True, fade_in=True)
    
    # 注册所有章节回调
    for chapter in chapters:
        engine.register_position_callback(
            "main_audio", 
            chapter["time"], 
            chapter_callback,
            tolerance=0.020
        )

# 使用示例
engine.load_track("main_audio", "有声书.wav")
setup_chapter_markers(engine)
engine.play("main_audio")
```

#### 3. 实时字幕同步

```python
def setup_subtitle_sync(engine, subtitle_data):
    """设置字幕同步回调"""
    
    def subtitle_callback(track_id, target_time, actual_time):
        # 从回调中获取字幕文本（可以通过闭包传递）
        subtitle_text = getattr(subtitle_callback, 'current_subtitle', '')
        
        if subtitle_text:
            print(f"💬 [{actual_time:.1f}s] {subtitle_text}")
            
            # 发送字幕到UI（示例）
            # send_subtitle_to_ui(subtitle_text, actual_time)
    
    # 为每个字幕时间点注册回调
    for subtitle in subtitle_data:
        # 创建带有字幕文本的回调函数
        def make_subtitle_callback(text):
            def callback(track_id, target_time, actual_time):
                print(f"💬 [{actual_time:.1f}s] {text}")
            return callback
        
        engine.register_position_callback(
            "audio_track",
            subtitle["start_time"],
            make_subtitle_callback(subtitle["text"]),
            tolerance=0.008  # 8ms精度用于字幕
        )

# 字幕数据示例
subtitles = [
    {"start_time": 5.2, "text": "欢迎收听今天的节目"},
    {"start_time": 8.7, "text": "今天我们要讨论的话题是..."},
    {"start_time": 12.1, "text": "首先让我们来看看背景"}
]

engine.load_track("audio_track", "节目音频.wav")
setup_subtitle_sync(engine, subtitles)
engine.play("audio_track")
```

#### 4. 动态音效插入

```python
def setup_dynamic_sound_effects(engine):
    """设置动态音效插入"""
    
    # 音效配置
    sound_effects = {
        "applause": {"file": "applause.wav", "volume": 0.6},
        "ding": {"file": "notification.wav", "volume": 0.8},
        "whoosh": {"file": "transition.wav", "volume": 0.5}
    }
    
    def sound_effect_callback(track_id, target_time, actual_time):
        effect_name = getattr(sound_effect_callback, 'effect_name', 'ding')
        effect_config = sound_effects.get(effect_name, sound_effects['ding'])
        
        print(f"🔊 播放音效: {effect_name} at {actual_time:.2f}s")
        
        # 加载并播放音效
        effect_track_id = f"effect_{int(actual_time * 1000)}"
        engine.load_track(effect_track_id, effect_config["file"])
        engine.play(effect_track_id, volume=effect_config["volume"])
        
        # 5秒后自动清理音效轨道
        def cleanup_effect():
            time.sleep(5.0)
            if engine.is_track_loaded(effect_track_id):
                engine.unload_track(effect_track_id)
        
        import threading
        threading.Thread(target=cleanup_effect, daemon=True).start()
    
    # 注册音效触发点
    effect_points = [
        {"time": 30.0, "effect": "ding"},      # 重点提醒
        {"time": 60.0, "effect": "applause"},  # 掌声
        {"time": 90.0, "effect": "whoosh"}     # 转场
    ]
    
    for point in effect_points:
        # 创建携带音效名称的回调
        def make_effect_callback(effect_name):
            def callback(track_id, target_time, actual_time):
                print(f"🔊 播放音效: {effect_name} at {actual_time:.2f}s")
                effect_config = sound_effects[effect_name]
                effect_track_id = f"effect_{int(actual_time * 1000)}"
                engine.load_track(effect_track_id, effect_config["file"])
                engine.play(effect_track_id, volume=effect_config["volume"])
            return callback
        
        engine.register_position_callback(
            "main_track",
            point["time"],
            make_effect_callback(point["effect"]),
            tolerance=0.012
        )

engine.load_track("main_track", "演讲音频.wav")
setup_dynamic_sound_effects(engine)
engine.play("main_track")
```

#### 5. 全局位置监听器高级用法

```python
class AudioAnalyzer:
    """音频播放分析器"""
    
    def __init__(self, engine):
        self.engine = engine
        self.position_history = {}
        self.playback_stats = {}
        
        # 注册全局监听器
        engine.add_global_position_listener(self.position_listener)
    
    def position_listener(self, track_id: str, position: float):
        """全局位置监听器"""
        
        # 记录位置历史
        if track_id not in self.position_history:
            self.position_history[track_id] = []
        
        self.position_history[track_id].append({
            'position': position,
            'timestamp': time.time()
        })
        
        # 计算播放速度（实际 vs 期望）
        self._calculate_playback_rate(track_id, position)
        
        # 检测播放异常
        self._detect_playback_issues(track_id, position)
        
        # 定期输出统计
        if len(self.position_history[track_id]) % 50 == 0:  # 每50次更新输出一次
            self._print_stats(track_id)
    
    def _calculate_playback_rate(self, track_id: str, position: float):
        """计算实际播放速率"""
        history = self.position_history[track_id]
        if len(history) < 2:
            return
        
        current_time = time.time()
        last_record = history[-2]
        
        time_diff = current_time - last_record['timestamp']
        position_diff = position - last_record['position']
        
        if time_diff > 0:
            actual_rate = position_diff / time_diff
            expected_rate = 1.0  # 正常播放速率
            
            if track_id not in self.playback_stats:
                self.playback_stats[track_id] = []
            
            self.playback_stats[track_id].append(actual_rate)
    
    def _detect_playback_issues(self, track_id: str, position: float):
        """检测播放问题"""
        if track_id not in self.playback_stats or len(self.playback_stats[track_id]) < 5:
            return
        
        recent_rates = self.playback_stats[track_id][-5:]
        avg_rate = sum(recent_rates) / len(recent_rates)
        
        if avg_rate < 0.9:
            print(f"⚠️ {track_id}: 播放速度慢于预期 ({avg_rate:.3f}x)")
        elif avg_rate > 1.1:
            print(f"⚠️ {track_id}: 播放速度快于预期 ({avg_rate:.3f}x)")
    
    def _print_stats(self, track_id: str):
        """输出统计信息"""
        if track_id in self.playback_stats and self.playback_stats[track_id]:
            rates = self.playback_stats[track_id]
            avg_rate = sum(rates) / len(rates)
            print(f"📊 {track_id}: 平均播放速率 {avg_rate:.3f}x, 采样点数 {len(rates)}")

# 使用分析器
analyzer = AudioAnalyzer(engine)

engine.load_track("test_audio", "测试音频.wav")
engine.play("test_audio")

# 分析器会自动监控播放状态
time.sleep(30)  # 运行30秒进行分析
```

### 性能优化建议

1. **合理设置容忍度**: 
   - TTS插入: 10-15ms
   - 字幕同步: 5-10ms
   - 音效触发: 15-25ms

2. **回调函数优化**:
   - 避免在回调中执行耗时操作
   - 使用异步处理重复性任务
   - 及时清理临时资源

3. **内存管理**:
   - 定期清理已触发的回调
   - 避免在回调中创建大量临时对象
   - 使用对象池管理音频资源

## 🎯 应用场景

### 🎙️ 语音处理
- **播客制作** - 多人语音混音，智能响度匹配
- **有声书制作** - 章节间无缝切换，背景音乐融合
- **配音工程** - 角色语音替换，音质自动匹配
- **语音合成** - TTS语音与真人语音的自然融合
- **实时语音纠错** - 基于位置回调的精确TTS插入 **[新增]**
- **智能字幕同步** - 毫秒级精度的字幕时间轴对齐 **[新增]**

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
- **剧情触发器** - 基于时间轴的精确事件触发 **[新增]**
- **动态配乐** - 根据游戏进度自动调整背景音乐 **[新增]**

### 📺 多媒体应用
- **视频配音** - 自动音视频同步，响度标准化
- **直播系统** - 实时音频处理，多源混音
- **教育软件** - 互动音频，语音识别集成
- **会议系统** - 多人语音处理，回声消除
- **自动剪辑** - 基于音频内容的智能分段和标记 **[新增]**
- **互动媒体** - 精确时间控制的交互式音频体验 **[新增]**

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

### 🎯 位置回调性能
- **回调精度**: 5-15ms（实测平均精度6ms）
- **最大回调数**: 支持1000+个并发位置回调
- **检查频率**: 动态调整（5ms高频 ↔ 50ms低频）
- **内存开销**: 每个回调约200字节
- **线程安全**: 完全线程安全的回调管理

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

**位置回调问题**:
```python
# 回调精度不足
engine = AudioEngine(buffer_size=512)  # 减小缓冲区提高精度

# 回调不触发
# 检查音轨是否正在播放
if engine.is_track_playing("track_id"):
    print("轨道正常播放")

# 获取回调统计信息诊断问题
stats = engine.get_position_callback_stats()
print(f"活跃回调: {stats['active_callbacks']}")
print(f"平均精度: {stats['average_precision_ms']:.1f}ms")

# 清理所有回调重新开始
engine.clear_all_position_callbacks()
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

# 运行位置回调专项测试
pytest tests/test_position_callbacks.py -v

# 快速位置回调测试（无音频播放）
python tests/run_position_callback_tests.py quick

# 回调精度测试
python tests/run_position_callback_tests.py precision

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

