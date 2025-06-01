# 音轨管理功能说明

您的 AudioEngine 现在支持完整的音轨管理功能，可以随时暂停和移除音轨。

## 核心功能

### 单个音轨控制
- `pause(track_id)` - 暂停指定音轨
- `resume(track_id)` - 恢复指定音轨播放
- `stop(track_id, fade_out=True)` - 停止音轨播放
- `remove_track(track_id, fade_out=True)` - 移除音轨（停止+卸载）

### 批量操作
- `pause_all_tracks()` - 暂停所有正在播放的音轨
- `resume_all_tracks()` - 恢复所有暂停的音轨
- `stop_all_tracks(fade_out=True)` - 停止所有音轨
- `clear_all_tracks()` - 清空所有音轨

### 状态查询
- `get_track_info(track_id)` - 获取音轨详细信息
- `list_tracks()` - 获取所有音轨列表
- `get_playing_tracks()` - 获取正在播放的音轨
- `get_paused_tracks()` - 获取暂停的音轨
- `get_track_count()` - 获取音轨数量统计

### 状态检查
- `is_track_playing(track_id)` - 检查是否正在播放
- `is_track_paused(track_id)` - 检查是否暂停
- `is_track_loaded(track_id)` - 检查是否已加载

## 使用示例

### 基本操作

```python
from audiomixer import AudioEngine
import numpy as np

# 初始化音频引擎
engine = AudioEngine()
engine.start()

# 加载音轨
audio_data = np.random.randn(48000, 2).astype(np.float32)  # 1秒随机噪声
engine.load_track("音轨1", audio_data)

# 播放
engine.play("音轨1", loop=True, volume=0.5)

# 暂停
engine.pause("音轨1")

# 恢复
engine.resume("音轨1")

# 移除
engine.remove_track("音轨1", fade_out=True)

# 关闭
engine.shutdown()
```

### 批量管理

```python
# 加载多个音轨
engine.load_track("背景音乐", music_data)
engine.load_track("音效1", sound1_data)
engine.load_track("音效2", sound2_data)

# 播放所有
engine.play("背景音乐", loop=True)
engine.play("音效1")
engine.play("音效2")

# 查看状态
print("正在播放:", engine.get_playing_tracks())
print("音轨统计:", engine.get_track_count())

# 暂停所有
paused = engine.pause_all_tracks()
print("已暂停:", paused)

# 恢复所有
resumed = engine.resume_all_tracks()
print("已恢复:", resumed)

# 清空所有
engine.clear_all_tracks()
```

### 状态监控

```python
# 获取音轨详细信息
info = engine.get_track_info("音轨1")
if info:
    print(f"音轨: {info['track_id']}")
    print(f"时长: {info['duration']:.1f}秒")
    print(f"当前位置: {info['position']:.1f}秒")
    print(f"音量: {info['volume']:.2f}")
    print(f"状态: {'播放中' if info['playing'] else '已停止'}")
    print(f"是否暂停: {info['paused']}")

# 获取所有音轨
tracks = engine.list_tracks()
for track in tracks:
    status = "播放中" if track['playing'] and not track['paused'] else \
             "暂停" if track['paused'] else "停止"
    print(f"{track['track_id']}: {status}")
```

## 运行示例程序

### 1. 自动演示
运行基本功能演示：
```bash
python example_track_management.py
```

### 2. 交互式控制台
启动实时控制界面：
```bash
python interactive_track_control.py
```

在交互式控制台中，您可以使用以下命令：

**添加音轨：**
- `add 音轨1 440` - 添加440Hz测试音调
- `load 音轨2 /path/to/audio.wav` - 从文件加载

**播放控制：**
- `play 音轨1` - 播放
- `pause 音轨1` - 暂停
- `resume 音轨1` - 恢复
- `stop 音轨1` - 停止
- `remove 音轨1` - 移除

**批量操作：**
- `pause_all` - 暂停所有
- `resume_all` - 恢复所有
- `stop_all` - 停止所有
- `clear_all` - 清空所有

**查询状态：**
- `list` - 显示所有音轨
- `status` - 显示系统状态
- `playing` - 显示正在播放的音轨
- `paused` - 显示暂停的音轨

**其他功能：**
- `volume 音轨1 0.5` - 设置音量
- `loop 音轨1 on` - 设置循环
- `speed 音轨1 1.5` - 设置播放速度
- `seek 音轨1 10` - 跳转到10秒位置

## 特色功能

1. **线程安全** - 所有操作都是线程安全的
2. **淡入淡出** - 支持平滑的音频过渡
3. **实时控制** - 可以在播放过程中随时控制
4. **状态查询** - 完整的状态监控功能
5. **批量操作** - 高效的批量音轨管理
6. **内存管理** - 自动释放音轨占用的内存

## 注意事项

- 移除音轨时会自动停止播放并释放内存
- 支持最多32个同时加载的音轨（可配置）
- 暂停的音轨会保持当前播放位置
- 停止的音轨会重置到开始位置
- 所有操作都支持淡入淡出效果，避免音频突变 