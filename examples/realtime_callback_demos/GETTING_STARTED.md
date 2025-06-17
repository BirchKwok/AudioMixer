# 🚀 实时音频回调功能 - 快速入门指南

> 3分钟学会使用 RealtimeMix 实时音频回调功能

## 💡 核心概念

**实时音频回调** 允许您在主音轨播放到特定时间点时：
1. 🔇 自动静音主音轨
2. 🎵 播放插入的音频片段  
3. 🔊 自动恢复主音轨播放

## ⚡ 快速示例

### 基础用法

```python
from realtimemix import AudioEngine
import numpy as np
import time

# 1. 创建音频引擎
engine = AudioEngine()
engine.start()

# 2. 生成测试音频
def generate_tone(duration, frequency, sample_rate=48000):
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    return np.sin(2 * np.pi * frequency * t)

# 主音轨：15秒 440Hz 音调
main_audio = generate_tone(15.0, 440.0)
# 插入音频：2秒 880Hz 音调  
callback_audio = generate_tone(2.0, 880.0)

# 3. 加载音轨
engine.load_track("main", main_audio)
engine.load_track("callback", callback_audio)

# 4. 定义回调函数
def insert_audio(track_id, target_time, actual_time):
    print(f"⏰ 在 {actual_time:.2f}s 时触发回调")
    
    # 静音主音轨
    engine.mute("main")
    
    # 播放插入音频
    engine.play("callback", volume=0.8)
    
    # 2.1秒后恢复主音轨
    def restore():
        engine.stop("callback", fade_out=False)
        engine.unmute("main")
        print("🔊 主音轨已恢复")
    
    import threading
    threading.Timer(2.1, restore).start()

# 5. 注册回调（在5秒时触发）
engine.register_position_callback("main", 5.0, insert_audio)

# 6. 开始播放
print("🎵 开始播放，将在5秒时插入音频...")
engine.play("main", volume=0.7)

# 7. 等待播放完成
time.sleep(16)
engine.stop_all_tracks()
```

## 🎯 实际应用示例

### 语音播放中的提示音

```python
# 在语音重要段落前插入"注意"提示音
def voice_with_alerts():
    engine.load_track("voice", voice_audio)
    engine.load_track("alert", alert_beep)
    
    # 在关键时间点插入提示音
    key_points = [30.5, 65.2, 120.8]  # 重要段落开始时间
    
    for time_point in key_points:
        engine.register_position_callback("voice", time_point, insert_alert)
    
    engine.play("voice")
```

### 教学音频的定时提醒

```python
# 教学内容中的练习提醒
def educational_content():
    engine.load_track("lesson", lesson_audio)
    engine.load_track("reminder", practice_chime)
    
    # 每10分钟提醒练习
    for i in range(1, 6):  # 5次提醒
        reminder_time = i * 600  # 10分钟 = 600秒
        engine.register_position_callback("lesson", reminder_time, practice_reminder)
    
    engine.play("lesson")
```

## 📋 3个关键步骤

### 1️⃣ 准备音频资源

```python
# 主音轨
main_track = load_audio_file("background_music.wav")
engine.load_track("background", main_track)

# 插入音频片段
notification = load_audio_file("notification.wav")
engine.load_track("notify", notification)
```

### 2️⃣ 定义回调函数

```python
def my_callback(track_id, target_time, actual_time):
    # 记录触发时间
    precision = abs(actual_time - target_time) * 1000  # 毫秒
    print(f"回调精度: {precision:.1f}ms")
    
    # 静音主音轨
    engine.mute(track_id)
    
    # 播放插入音频
    engine.play("notify", volume=0.9)
    
    # 定时恢复 (插入音频时长 + 100ms缓冲)
    def restore():
        engine.stop("notify", fade_out=False)
        engine.unmute(track_id)
    
    threading.Timer(notification_duration + 0.1, restore).start()
```

### 3️⃣ 注册并播放

```python
# 注册回调（容忍度15ms）
success = engine.register_position_callback(
    "background", 
    target_time=45.0,  # 45秒时触发
    callback_func=my_callback,
    tolerance=0.015    # 15ms精度
)

if success:
    engine.play("background")
    print("✅ 回调已注册，开始播放")
else:
    print("❌ 回调注册失败")
```

## ⚙️ 高性能配置

```python
# 低延迟配置
engine = AudioEngine(
    sample_rate=48000,
    buffer_size=256,        # 更小的缓冲区 = 更低延迟
    stream_latency="low"    # 低延迟模式
)

# 高精度回调
engine.register_position_callback(
    track_id="main",
    target_time=10.0,
    callback_func=callback,
    tolerance=0.005  # 5ms 高精度
)
```

## 🔧 常用工具函数

```python
# 安全的回调函数模板
def safe_audio_callback(insert_duration):
    def callback(track_id, target_time, actual_time):
        try:
            # 保存原始状态
            original_volume = engine.get_track_info(track_id).get('volume', 1.0)
            was_muted = engine.is_muted(track_id)
            
            # 执行插入
            engine.mute(track_id)
            engine.play("insert_track", volume=0.8)
            
            # 安全恢复
            def restore():
                engine.stop("insert_track", fade_out=False)
                if not was_muted:  # 只有原本没静音才恢复
                    engine.unmute(track_id)
                    engine.set_volume(track_id, original_volume)
            
            threading.Timer(insert_duration + 0.05, restore).start()
            
        except Exception as e:
            print(f"回调错误: {e}")
            # 紧急恢复
            engine.unmute(track_id)
    
    return callback

# 使用方式
my_callback = safe_audio_callback(insert_duration=2.0)
engine.register_position_callback("main", 10.0, my_callback)
```

## 🎵 运行示例

```bash
# 进入演示目录
cd examples/realtime_callback_demos

# 运行基础测试
python realtime_callback_test.py

# 运行高级测试  
python realtime_callback_advanced_test.py

# 查看使用示例
python callback_usage_example.py
```

## 📈 性能指标

我们的测试显示：

| 指标 | 表现 |
|------|------|
| **触发精度** | 5-15ms |
| **成功率** | 100% |
| **静音响应** | <5ms |
| **恢复响应** | <5ms |

## 🆘 遇到问题？

**Q: 回调触发不准确？**
```python
# A: 降低缓冲区大小，提高精度
engine = AudioEngine(buffer_size=256)
```

**Q: 主音轨恢复失败？**
```python
# A: 添加错误恢复机制
def safe_restore():
    try:
        engine.unmute("main")
    except:
        engine.set_volume("main", original_volume)  # 强制恢复
```

**Q: 多个回调冲突？**
```python
# A: 检查时间间隔，确保回调不重叠
min_interval = max_callback_duration + 0.5  # 至少500ms间隔
```

---

## 📖 更多资源

- 📋 [完整功能文档](README.md)
- 🧪 [详细测试报告](REALTIME_CALLBACK_TEST_SUMMARY.md)
- 💻 [源码示例](realtime_callback_test.py)

**开始您的实时音频之旅吧！** 🎵✨ 