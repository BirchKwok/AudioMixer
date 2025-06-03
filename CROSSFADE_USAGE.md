# 交叉淡入淡出（Crossfade）功能使用指南

AudioEngine 现在内置了专业级的交叉淡入淡出功能，让用户可以零门槛实现无缝音轨切换。

## 🎵 核心功能

### 1. 响度匹配 (`match_loudness`)
自动分析两个音轨的响度，计算合适的音量比例：

```python
from audiomixer import AudioEngine

engine = AudioEngine()
engine.start()

# 加载音轨
engine.load_track("main", "main_track.wav")
engine.load_track("sub", "sub_track.wav")

# 响度匹配
main_vol, sub_vol = engine.match_loudness("main", "sub", target_loudness=0.7)
print(f"建议音量 - 主音轨: {main_vol:.3f}, 副音轨: {sub_vol:.3f}")
```

### 2. 交叉淡入淡出 (`crossfade`)
在两个音轨之间执行专业级的无缝切换：

```python
# 播放主音轨
engine.set_volume("main", 0.7)
engine.play("main", loop=True)

# 等待一段时间后切换到副音轨
time.sleep(5)

# 自动响度匹配的交叉淡入淡出（推荐）
engine.crossfade("main", "sub", duration=1.0)

# 或者手动指定目标音量
# engine.crossfade("main", "sub", duration=1.0, to_track_volume=0.6)
```

## 📖 API参考

### `calculate_rms_loudness(track_id, duration=2.0)`
计算音轨的RMS响度。

**参数：**
- `track_id` (str): 音轨ID
- `duration` (float): 分析时长（秒）

**返回：**
- `float`: RMS响度值

### `match_loudness(track1_id, track2_id, target_loudness=0.7)`
匹配两个音轨的响度。

**参数：**
- `track1_id` (str): 第一个音轨ID（通常是主音轨）
- `track2_id` (str): 第二个音轨ID（通常是副音轨）
- `target_loudness` (float): 目标响度级别（0.0-1.0）

**返回：**
- `tuple[float, float]`: (第一个音轨建议音量, 第二个音轨建议音量)

### `crossfade(from_track, to_track, duration=1.0, to_track_volume=None, to_track_loop=False)`
在两个音轨之间执行交叉淡入淡出。

**参数：**
- `from_track` (str): 源音轨ID（将淡出）
- `to_track` (str): 目标音轨ID（将淡入）  
- `duration` (float): 交叉淡入淡出持续时间（秒）
- `to_track_volume` (float, optional): 目标音轨的最终音量。如果为None，将自动使用响度匹配
- `to_track_loop` (bool): 目标音轨是否循环播放

**返回：**
- `bool`: 是否成功开始交叉淡入淡出

## 🚀 完整示例

```python
#!/usr/bin/env python3
from audiomixer import AudioEngine
import time

def main():
    # 初始化音频引擎
    engine = AudioEngine(
        sample_rate=48000,
        buffer_size=1024,
        channels=2,
        enable_streaming=True
    )
    
    try:
        engine.start()
        
        # 加载音轨（自动音量标准化）
        engine.load_track("main_track", "main.wav", auto_normalize=True)
        engine.load_track("sub_track", "sub.wav", auto_normalize=True)
        
        # 播放主音轨
        engine.play("main_track", fade_in=True, loop=True)
        print("主音轨播放中...")
        
        # 等待5秒
        time.sleep(5)
        
        # 前静音
        print("300ms静音...")
        time.sleep(0.3)
        
        # 无缝切换到副音轨（自动响度匹配）
        print("切换到副音轨...")
        engine.crossfade("main_track", "sub_track", duration=0.5)
        
        # 播放副音轨
        time.sleep(10)  # 或根据实际时长
        
        # 后静音
        print("300ms静音...")
        time.sleep(0.3)
        
        # 切换回主音轨
        print("切换回主音轨...")
        engine.crossfade("sub_track", "main_track", duration=0.5, to_track_loop=True)
        
        # 继续播放
        time.sleep(5)
        
        print("测试完成！")
        
    finally:
        engine.shutdown()

if __name__ == "__main__":
    main()
```

## 🎯 优势对比

### ❌ 之前的复杂实现：
```python
# 需要用户自己实现复杂的函数
def calculate_rms_loudness(engine, track_id, duration=2.0):
    # 50多行复杂代码...
    
def match_loudness(engine, track1_id, track2_id):
    # 30多行复杂代码...
    
def crossfade_transition(engine, from_track, to_track, duration=1.0):
    # 40多行复杂代码...

# 使用时需要调用复杂函数
main_vol, sub_vol = match_loudness(engine, "main", "sub")
crossfade_transition(engine, "main", "sub", 0.5)
```

### ✅ 现在的简洁API：
```python
# 零门槛使用
engine.crossfade("main_track", "sub_track", 0.5)
```

## 🔧 技术特性

- **自动响度匹配**：确保切换时用户听不出音量差异
- **线程安全**：后台执行，不阻塞主线程
- **专业级质量**：平滑的交叉淡入淡出曲线
- **零配置**：默认参数即可获得最佳效果
- **灵活控制**：支持自定义时长、音量、循环等参数

现在用户可以用一行代码实现专业级的无缝音轨切换！ 