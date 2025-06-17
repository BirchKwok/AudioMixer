# RealtimeMix 示例集合

本目录包含 RealtimeMix 音频引擎的各种使用示例，从基础功能到高级特性应有尽有。

## 📁 示例目录

### 🚀 基础示例

| 文件/目录 | 功能描述 | 难度 |
|-----------|----------|------|
| [`basic_usage.py`](basic_usage.py) | 基础音频播放、混音、音量控制 | ⭐ 入门 |
| [`timed_playback_demo.py`](timed_playback_demo.py) | 定时播放和音频调度 | ⭐⭐ 初级 |

### 🎵 高级功能示例

| 目录 | 功能描述 | 难度 |
|------|----------|------|
| [`realtime_callback_demos/`](realtime_callback_demos/) | **实时音频回调功能完整演示** | ⭐⭐⭐ 高级 |

## 🎯 实时音频回调功能 (推荐)

**最新功能**：在主音轨播放过程中实时插入音频，支持主音轨自动静音和恢复。

### 快速体验

```bash
# 进入回调演示目录
cd examples/realtime_callback_demos

# 运行基础测试
python realtime_callback_test.py

# 查看完整文档
cat README.md
```

### 核心特性

- ✅ **毫秒级精度** - 5-15ms回调触发精度
- ✅ **无缝切换** - 主音轨静音/恢复<5ms响应时间
- ✅ **多回调支持** - 同时管理多个时间点回调
- ✅ **线程安全** - 稳定的多线程环境支持
- ✅ **错误恢复** - 自动异常处理和状态恢复

### 应用场景

- 🎙️ **语音播放系统** - 重要段落前插入提示音
- 📚 **音频教学** - 定时练习提醒和知识点强调
- 📻 **广播节目** - 整点报时和节目分段提示
- 🎮 **游戏音效** - 背景音乐中的动态音效触发

## 🚀 快速开始

### 1. 基础音频播放

```python
from realtimemix import AudioEngine
import numpy as np

# 创建引擎
engine = AudioEngine()
engine.start()

# 生成测试音频
duration = 5.0
sample_rate = 48000
frequency = 440.0
t = np.linspace(0, duration, int(sample_rate * duration), False)
audio = np.sin(2 * np.pi * frequency * t)

# 播放音频
engine.load_track("test", audio)
engine.play("test", volume=0.7)
```

### 2. 实时音频插入

```python
# 定义回调函数
def insert_beep(track_id, target_time, actual_time):
    engine.mute("main")           # 静音主音轨
    engine.play("beep")           # 播放提示音
    # 2秒后恢复主音轨
    threading.Timer(2.0, lambda: [
        engine.stop("beep"),
        engine.unmute("main")
    ]).start()

# 注册回调
engine.register_position_callback("main", 10.0, insert_beep)
engine.play("main")
```

## 📊 性能对比

| 功能 | 传统方案 | RealtimeMix |
|------|----------|-------------|
| 音频切换延迟 | 50-200ms | **<5ms** |
| 时间精度 | ±50ms | **±8ms** |
| 多轨支持 | 有限 | **无限制** |
| 错误恢复 | 手动 | **自动** |
| 线程安全 | 需额外处理 | **内置支持** |

## 📖 学习路径

### 👶 初学者路径

1. 先运行 [`basic_usage.py`](basic_usage.py) 了解基础概念
2. 查看 [`timed_playback_demo.py`](timed_playback_demo.py) 学习时间控制
3. 进入 [`realtime_callback_demos/`](realtime_callback_demos/) 探索高级功能

### 🔥 专业开发者路径

1. 直接查看 [`realtime_callback_demos/README.md`](realtime_callback_demos/README.md)
2. 运行 [`realtime_callback_advanced_test.py`](realtime_callback_demos/realtime_callback_advanced_test.py)
3. 参考 [`callback_usage_example.py`](realtime_callback_demos/callback_usage_example.py) 进行实际应用

### 📚 深度学习路径

1. 阅读 [`REALTIME_CALLBACK_TEST_SUMMARY.md`](realtime_callback_demos/REALTIME_CALLBACK_TEST_SUMMARY.md) 了解技术细节
2. 查看 [`GETTING_STARTED.md`](realtime_callback_demos/GETTING_STARTED.md) 获取最佳实践
3. 基于示例代码开发自己的应用

## 🔧 开发环境设置

### 依赖安装

```bash
# 基础依赖
pip install numpy sounddevice

# 开发环境
pip install -e .
```

### 测试环境

```bash
# 进入项目目录
cd realtimemix

# 运行基础示例
python examples/basic_usage.py

# 测试实时回调功能
python examples/realtime_callback_demos/realtime_callback_test.py
```

## 🎵 示例运行输出

### 基础示例输出

```
Initializing RealtimeMix...
Audio engine started!
Generating test audio...
Loading tracks...
Playing sine wave with fade-in...
Adding white noise...
Fading sine wave volume...
Changing sine wave speed...

Performance Statistics:
  CPU Usage: 2.3%
  Peak Level: 0.847
  Active Tracks: 2
  Total Tracks: 2
```

### 实时回调示例输出

```
🎵 RealtimeMix 实时音频回调功能测试
==================================================
🧪 实时音频回调功能测试报告
============================================================
🎉 测试结果: 通过 ✅

📊 详细报告:
  • 回调触发时间: 5.008s (目标: 5.000s)
  • 触发精度: 8.00ms ⚡
  • 主音轨静音响应: <5ms ✅
  • 主音轨恢复响应: <5ms ✅
  • 音频插入成功: ✅
  • 状态恢复正确: ✅
```

## 🎯 选择适合的示例

| 需求 | 推荐示例 | 原因 |
|------|----------|------|
| 学习基础API | `basic_usage.py` | 覆盖核心功能，代码简洁 |
| 定时播放控制 | `timed_playback_demo.py` | 专注时间和调度管理 |
| 实时音频处理 | `realtime_callback_demos/` | 最新功能，生产环境就绪 |
| 语音应用开发 | `realtime_callback_demos/callback_usage_example.py` | 实际应用场景演示 |
| 性能优化 | `realtime_callback_demos/realtime_callback_advanced_test.py` | 详细性能测试和优化 |

## 💡 贡献新示例

欢迎贡献新的示例！请确保：

1. 📝 **文档完整** - 包含清晰的注释和说明
2. 🧪 **测试充分** - 包含错误处理和边界情况
3. 🎯 **目标明确** - 聚焦特定功能或应用场景
4. 📊 **性能数据** - 提供运行时间和资源使用情况

## 📞 获取帮助

遇到问题？请查看：

1. 📋 [功能文档](realtime_callback_demos/README.md)
2. 🧪 [测试报告](realtime_callback_demos/REALTIME_CALLBACK_TEST_SUMMARY.md)
3. 🚀 [快速入门](realtime_callback_demos/GETTING_STARTED.md)
4. 💻 [示例代码](realtime_callback_demos/)

**开始您的音频开发之旅吧！** 🎵✨

---

> 📌 **提示**: 建议从实时回调功能开始，这是 RealtimeMix 最强大和实用的特性！ 