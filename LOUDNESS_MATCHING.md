# 响度匹配功能文档

## 概述

`match_loudness` 方法现已支持多种响度匹配算法，为用户提供更灵活的响度平衡选项。默认使用 Matchering 算法，同时提供 RMS、峰值、LUFS 和 A权重等主流算法选择。

## 新增功能

### 多算法支持

现在 `match_loudness` 方法支持以下算法：

| 算法 | 方法名 | 说明 | 适用场景 |
|------|--------|------|----------|
| **Matchering** | `"matchering"` | 使用 Matchering 进行响度优化（默认） | 音乐制作、母带处理 |
| **RMS** | `"rms"` | 均方根响度测量 | 通用响度匹配，简单有效 |
| **峰值** | `"peak"` | 基于音频峰值的响度测量 | 防止削波，保护设备 |
| **LUFS** | `"lufs"` | 广播标准响度测量 | 广播、流媒体平台 |
| **A权重** | `"a_weighted"` | 人耳感知加权的响度测量 | 更接近人耳感知的响度 |

## API 使用方法

### match_loudness 方法

```python
def match_loudness(
    self, 
    track1_id: str, 
    track2_id: str, 
    target_loudness: float = 0.7,
    method: str = "matchering"
) -> tuple[float, float]:
```

**参数：**
- `track1_id`: 第一个音轨ID（通常是主音轨）
- `track2_id`: 第二个音轨ID（通常是副音轨）
- `target_loudness`: 目标响度级别（0.0-1.0）
- `method`: 响度匹配算法，默认为 `"matchering"`

**返回值：**
- `tuple[float, float]`: (第一个音轨建议音量, 第二个音轨建议音量)

### crossfade 方法增强

```python
def crossfade(
    self,
    from_track: str,
    to_track: str,
    duration: float = 1.0,
    to_track_volume: Optional[float] = None,
    to_track_loop: bool = False,
    loudness_match_method: str = "matchering",
) -> bool:
```

**新增参数：**
- `loudness_match_method`: 当 `to_track_volume` 为 None 时使用的响度匹配算法

## 使用示例

### 基本响度匹配

```python
from realtimemix import AudioEngine

engine = AudioEngine()
engine.start()

# 加载音轨
engine.load_track("main", "main_track.wav")
engine.load_track("background", "background.wav")

# 使用默认 Matchering 算法
vol1, vol2 = engine.match_loudness("main", "background", 0.7)
engine.set_volume("main", vol1)
engine.set_volume("background", vol2)
```

### 使用不同算法

```python
# 使用 RMS 算法（快速、简单）
vol1, vol2 = engine.match_loudness("main", "background", 0.7, method="rms")

# 使用 LUFS 算法（广播标准）
vol1, vol2 = engine.match_loudness("main", "background", 0.7, method="lufs")

# 使用峰值算法（防止削波）
vol1, vol2 = engine.match_loudness("main", "background", 0.7, method="peak")

# 使用 A权重算法（人耳感知）
vol1, vol2 = engine.match_loudness("main", "background", 0.7, method="a_weighted")
```

### 交叉淡入淡出中的响度匹配

```python
# 使用 RMS 算法进行交叉淡入淡出
engine.crossfade(
    "current_track", 
    "next_track", 
    duration=2.0, 
    loudness_match_method="rms"
)

# 使用 LUFS 算法进行交叉淡入淡出
engine.crossfade(
    "current_track", 
    "next_track", 
    duration=1.5, 
    loudness_match_method="lufs"
)
```

### 批量处理不同算法

```python
# 比较不同算法的结果
algorithms = ["rms", "peak", "lufs", "a_weighted", "matchering"]
results = {}

for method in algorithms:
    vol1, vol2 = engine.match_loudness("track1", "track2", method=method)
    results[method] = (vol1, vol2)
    print(f"{method}: Track1={vol1:.3f}, Track2={vol2:.3f}")
```

## 算法详细说明

### 1. Matchering 算法
- **特点**: 基于机器学习的母带处理算法
- **优势**: 智能化响度优化，适合音乐制作
- **依赖**: 需要安装 `matchering` 库
- **回退**: 如果库不可用，自动回退到 RMS 算法

### 2. RMS 算法
- **特点**: 计算音频信号的均方根值
- **优势**: 计算快速，稳定可靠
- **适用**: 通用响度匹配，实时处理

### 3. 峰值算法
- **特点**: 基于音频信号的最大绝对值
- **优势**: 防止音频削波，保护设备
- **适用**: 需要严格控制峰值的场景

### 4. LUFS 算法
- **特点**: 广播行业标准的响度测量
- **优势**: 符合国际广播标准（ITU-R BS.1770）
- **适用**: 广播、流媒体、专业音频制作
- **实现**: 包含 K权重滤波器的简化实现

### 5. A权重算法
- **特点**: 模拟人耳对不同频率的敏感度
- **优势**: 更接近人耳的主观感受
- **适用**: 需要考虑人耳感知的响度匹配
- **依赖**: 可选的 `scipy` 库用于频域处理

## 错误处理

所有算法都包含完善的错误处理机制：

1. **无效方法名**: 自动回退到 RMS 算法
2. **计算失败**: 自动回退到简单算法
3. **依赖缺失**: 自动使用替代实现
4. **音轨不存在**: 返回默认音量值

```python
# 示例：错误处理
try:
    vol1, vol2 = engine.match_loudness("track1", "track2", method="invalid")
    # 系统会自动使用 RMS 算法并记录警告
except Exception as e:
    print(f"处理错误: {e}")
```

## 性能对比

| 算法 | 计算速度 | 内存使用 | 精确度 | 依赖库 |
|------|----------|----------|--------|--------|
| RMS | 最快 | 最低 | 中等 | 无 |
| 峰值 | 最快 | 最低 | 低 | 无 |
| LUFS | 中等 | 中等 | 高 | scipy (可选) |
| A权重 | 慢 | 高 | 高 | scipy (可选) |
| Matchering | 慢 | 高 | 最高 | matchering |

## 最佳实践

1. **实时处理**: 建议使用 RMS 或峰值算法
2. **离线处理**: 可以使用 LUFS 或 Matchering 算法
3. **广播应用**: 推荐使用 LUFS 算法
4. **音乐制作**: 推荐使用 Matchering 算法
5. **一般应用**: RMS 算法是最佳平衡选择

## 注意事项

1. 不同算法可能产生不同的结果，选择时应考虑具体应用场景
2. 复杂算法（如 LUFS、A权重）可能需要更多计算时间
3. 某些算法依赖第三方库，在部署时需要考虑依赖管理
4. 建议在生产环境中对不同算法进行测试，选择最适合的方案 