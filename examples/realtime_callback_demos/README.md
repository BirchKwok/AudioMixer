# RealtimeMix 实时音频回调功能演示

本文件夹包含 RealtimeMix 实时音频回调功能的完整演示和测试示例。

## 📁 文件说明

### 🧪 测试脚本

| 文件名 | 功能描述 | 测试内容 |
|--------|----------|----------|
| [`realtime_callback_test.py`](realtime_callback_test.py) | 基础功能测试 | 单回调点音频插入、静音恢复测试 |
| [`realtime_callback_advanced_test.py`](realtime_callback_advanced_test.py) | 高级功能测试 | 多回调点、性能测试、稳定性验证 |
| [`callback_usage_example.py`](callback_usage_example.py) | 实际使用示例 | 实用场景演示、API使用教程 |

### 📖 文档

| 文件名 | 内容描述 |
|--------|----------|
| [`REALTIME_CALLBACK_TEST_SUMMARY.md`](REALTIME_CALLBACK_TEST_SUMMARY.md) | 完整测试报告和技术文档 |
| [`README.md`](README.md) | 本文档，使用指南 |

## 🚀 快速开始

### 环境要求

```bash
# 确保已安装 RealtimeMix
pip install -e .

# 依赖包
numpy>=1.20.0
sounddevice>=0.4.0
```

### 运行基础测试

```bash
cd examples/realtime_callback_demos
python realtime_callback_test.py
```

**预期输出**：
```
🎵 RealtimeMix 实时音频回调功能测试
==================================================
测试功能:
  1. 主音轨播放
  2. 定时音频插入
  3. 主音轨自动静音
  4. 回调音频播放
  5. 主音轨自动恢复

🧪 实时音频回调功能测试报告
============================================================
🎉 测试结果: 通过 ✅
```

### 运行高级测试

```bash
python realtime_callback_advanced_test.py
```

**预期输出**：
```
🧪 高级实时音频回调功能测试报告
======================================================================
🎉 测试结果: 全部通过 ✅

📊 测试摘要:
  • 回调触发次数: 4
  • 主音轨静音事件: 4
  • 主音轨恢复事件: 4
```

### 运行使用示例

```bash
python callback_usage_example.py
```

## 🎯 功能演示

### 1. 基础音频插入

演示在主音轨播放过程中插入提示音：

```python
from realtimemix import AudioEngine
import numpy as np

# 创建音频引擎
engine = AudioEngine(sample_rate=48000)
engine.start()

# 生成测试音频
main_audio = generate_test_audio(duration=10.0, frequency=440.0)
callback_audio = generate_test_audio(duration=2.0, frequency=880.0)

# 加载音轨
engine.load_track("main", main_audio)
engine.load_track("callback", callback_audio)

# 定义回调函数
def audio_callback(track_id, target_time, actual_time):
    # 主音轨静音
    engine.mute("main")
    
    # 播放回调音频
    engine.play("callback", volume=0.8)
    
    # 设置恢复定时器
    def restore():
        engine.stop("callback", fade_out=False)
        engine.unmute("main")
    
    threading.Timer(2.1, restore).start()

# 注册回调
engine.register_position_callback("main", 5.0, audio_callback)

# 开始播放
engine.play("main", volume=0.7)
```

### 2. 多回调点管理

演示管理多个时间点的音频插入：

```python
# 定义多个回调点
callback_points = [
    {'time': 3.0, 'audio': 'beep', 'type': 'notification'},
    {'time': 7.5, 'audio': 'alert', 'type': 'warning'},
    {'time': 12.0, 'audio': 'chime', 'type': 'info'}
]

# 批量注册回调
for point in callback_points:
    callback_func = create_callback_handler(point['type'], point['audio'])
    engine.register_position_callback(
        "main_track", 
        point['time'], 
        callback_func,
        tolerance=0.015  # 15ms容忍度
    )
```

### 3. 智能回调管理器

使用高级回调管理器处理复杂场景：

```python
class AudioCallbackManager:
    def __init__(self):
        self.engine = AudioEngine()
        self.active_callbacks = []
    
    def register_timed_callback(self, track_id, target_time, callback_type):
        """注册定时回调"""
        callback_func = self.create_audio_callback(callback_type)
        success = self.engine.register_position_callback(
            track_id, target_time, callback_func
        )
        
        if success:
            self.active_callbacks.append({
                'track_id': track_id,
                'time': target_time,
                'type': callback_type
            })
        
        return success
    
    def create_audio_callback(self, callback_type):
        """创建专用回调函数"""
        def callback(track_id, target_time, actual_time):
            self.execute_audio_insertion(callback_type, track_id)
        return callback
```

## 📊 测试结果

### 性能指标

| 指标 | 目标值 | 实际值 | 状态 |
|------|--------|--------|------|
| 回调触发精度 | <20ms | 8-13ms | ✅ 优秀 |
| 多回调成功率 | >95% | 100% | ✅ 完美 |
| 静音响应时间 | <10ms | <5ms | ✅ 优秀 |
| 恢复响应时间 | <10ms | <5ms | ✅ 优秀 |

### 功能覆盖

- ✅ **单回调点触发** - 精确时间控制
- ✅ **多回调点管理** - 同时处理多个回调
- ✅ **主音轨静音** - 瞬时静音响应
- ✅ **音量状态恢复** - 自动恢复原始音量
- ✅ **错误恢复机制** - 异常情况处理
- ✅ **线程安全性** - 多线程环境稳定

## 🎵 应用场景

### 1. 语音播放系统

```python
# 语音内容播放中插入提示音
def voice_with_beeps():
    # 在重要段落前插入提示音
    manager.register_timed_callback("voice", 10.5, "attention_beep")
    manager.register_timed_callback("voice", 25.3, "section_break") 
    manager.register_timed_callback("voice", 45.8, "conclusion_chime")
```

### 2. 音频教学系统

```python
# 教学音频中的定时提醒
def educational_audio():
    # 关键知识点前的提示音
    manager.register_timed_callback("lesson", 120.0, "key_point_alert")
    # 练习时间提醒
    manager.register_timed_callback("lesson", 300.0, "practice_reminder")
    # 总结时段提示
    manager.register_timed_callback("lesson", 450.0, "summary_signal")
```

### 3. 广播节目系统

```python
# 新闻广播中的时间提醒
def news_broadcast():
    # 整点报时
    manager.register_timed_callback("news", 3600.0, "hourly_chime")
    # 重要新闻前的提示音
    manager.register_timed_callback("news", 180.0, "breaking_news_alert")
    # 广告时段分隔音
    manager.register_timed_callback("news", 900.0, "commercial_break")
```

### 4. 游戏音效系统

```python
# 游戏背景音乐中的音效触发
def game_audio():
    # 关卡进度提示
    manager.register_timed_callback("bgm", 60.0, "level_progress")
    # 奖励获得音效
    manager.register_timed_callback("bgm", 120.0, "reward_sound")
    # 危险警告音
    manager.register_timed_callback("bgm", 180.0, "danger_warning")
```

## 🔧 高级配置

### 精度调优

```python
# 高精度配置
engine = AudioEngine(
    sample_rate=48000,      # 高采样率提升精度
    buffer_size=256,        # 小缓冲区降低延迟
    channels=2,
    stream_latency="low"    # 低延迟模式
)

# 回调容忍度设置
engine.register_position_callback(
    track_id="main",
    target_time=5.0,
    callback_func=callback,
    tolerance=0.005  # 5ms高精度模式
)
```

### 性能优化

```python
# 预加载模式（推荐用于回调功能）
engine = AudioEngine(
    enable_streaming=False,  # 禁用流式播放
    max_tracks=16           # 限制轨道数量
)

# 回调函数优化
def optimized_callback(track_id, target_time, actual_time):
    try:
        # 最小化回调函数执行时间
        engine.mute(track_id)
        engine.play("callback", volume=0.8)
        
        # 使用高精度定时器
        timer = threading.Timer(
            callback_duration + 0.05,  # 添加安全缓冲
            restore_function
        )
        timer.start()
        
    except Exception as e:
        # 错误恢复机制
        fallback_restore(track_id)
```

## 🐛 故障排除

### 常见问题

#### 1. 回调触发延迟

**问题**: 回调触发时间不够精确

**解决方案**:
```python
# 降低缓冲区大小
engine = AudioEngine(buffer_size=256)  # 而不是默认的1024

# 使用更严格的容忍度
engine.register_position_callback(..., tolerance=0.005)

# 确保系统音频设置为低延迟模式
engine = AudioEngine(stream_latency="low")
```

#### 2. 静音恢复失败

**问题**: 主音轨无法正确恢复

**解决方案**:
```python
def safe_callback(track_id, target_time, actual_time):
    try:
        # 记录原始状态
        original_volume = engine.get_track_info(track_id)['volume']
        original_muted = engine.is_muted(track_id)
        
        # 执行回调操作
        engine.mute(track_id)
        engine.play("callback")
        
        # 强制恢复机制
        def force_restore():
            engine.stop("callback", fade_out=False)
            if not original_muted:
                engine.unmute(track_id)
                engine.set_volume(track_id, original_volume)
        
        timer = threading.Timer(callback_duration + 0.1, force_restore)
        timer.start()
        
    except Exception as e:
        # 紧急恢复
        emergency_restore(track_id)
```

#### 3. 多回调冲突

**问题**: 多个回调同时触发导致冲突

**解决方案**:
```python
class ConflictResolver:
    def __init__(self):
        self.active_callback = None
        self.callback_queue = []
    
    def safe_callback(self, track_id, target_time, actual_time):
        if self.active_callback:
            # 将回调加入队列
            self.callback_queue.append((track_id, target_time, actual_time))
            return
        
        # 执行回调
        self.active_callback = target_time
        self.execute_callback(track_id, target_time, actual_time)
    
    def on_callback_complete(self):
        self.active_callback = None
        # 处理队列中的下一个回调
        if self.callback_queue:
            next_callback = self.callback_queue.pop(0)
            self.safe_callback(*next_callback)
```

## 📚 API参考

### 核心方法

#### `register_position_callback(track_id, target_time, callback_func, tolerance=0.010)`

注册位置回调函数。

**参数**:
- `track_id` (str): 目标轨道ID
- `target_time` (float): 触发时间点（秒）
- `callback_func` (callable): 回调函数
- `tolerance` (float): 时间容忍度（秒），默认10ms

**回调函数签名**:
```python
def callback_func(track_id: str, target_time: float, actual_time: float):
    """
    track_id: 触发回调的轨道ID
    target_time: 设定的目标时间
    actual_time: 实际触发时间
    """
    pass
```

#### `mute(track_id)` / `unmute(track_id)`

静音/取消静音指定轨道。

**返回值**: `bool` - 操作是否成功

#### `is_muted(track_id)`

检查轨道是否处于静音状态。

**返回值**: `bool` - 是否静音

### 状态查询

#### `get_position_callback_stats()`

获取回调系统统计信息。

**返回值**: 包含以下字段的字典
- `active_callbacks`: 活跃回调数量
- `triggered_callbacks`: 已触发回调总数
- `average_precision_ms`: 平均触发精度（毫秒）

## 📄 许可证

本示例代码遵循与 RealtimeMix 相同的许可证。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来改进这些示例！

---

## 📞 支持

如果您在使用过程中遇到问题，请：

1. 查看 [故障排除](#-故障排除) 部分
2. 阅读完整的 [测试报告](REALTIME_CALLBACK_TEST_SUMMARY.md)
3. 参考 [API参考](#-api参考) 文档
4. 提交 Issue 描述具体问题

**Happy Coding! 🎵** 