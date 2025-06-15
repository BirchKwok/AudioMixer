# RealtimeMix 测试套件

这是一个全面的多维度测试套件，用于验证 `realtimemix` 库的功能、性能和稳定性。

## 📁 测试结构

```
tests/
├── conftest.py                    # 测试配置和通用 fixtures
├── test_basic_functionality.py   # 基本功能测试
├── test_matchering_integration.py # Matchering 集成测试
├── test_advanced_features.py     # 高级功能测试
├── test_benchmarks.py           # 性能基准测试
├── test_runner.py               # 测试运行器
├── pytest.ini                  # pytest 配置
├── requirements-test.txt        # 测试依赖
└── README.md                   # 本文件
```

## 🧪 测试套件说明

### 1. 基本功能测试 (`test_basic_functionality.py`)
- **AudioEngine 初始化和配置**
- **音轨加载/卸载操作**
- **播放控制（播放、停止、音量调节）**
- **多轨道管理**
- **错误处理和边界条件**
- **流式播放 vs 预加载模式**
- **性能统计收集**

### 2. Matchering 集成测试 (`test_matchering_integration.py`)
- **基本 matchering 功能**
- **不同参考位置的匹配**
- **多种音频格式支持**
- **边界条件处理**
- **临时文件清理**
- **错误处理和恢复**
- **性能测试**

### 3. 高级功能测试 (`test_advanced_features.py`)
- **无缝音轨切换**
- **交叉淡化模拟**
- **多轨道混音**
- **同步播放**
- **资源管理**
- **并发操作**
- **复杂应用场景**

### 4. 性能基准测试 (`test_benchmarks.py`)
- **加载速度基准**
- **播放延迟测试**
- **CPU 使用率监控**
- **内存使用扩展性**
- **最大并发轨道数**
- **长期稳定性**
- **资源效率**

## 🚀 快速开始

### 安装测试依赖

```bash
# 安装测试依赖
pip install -r tests/requirements-test.txt
```

### 运行测试

#### 1. 使用测试运行器（推荐）

```bash
# 快速检查
python tests/test_runner.py quick

# 运行基本功能测试
python tests/test_runner.py basic

# 运行 matchering 集成测试
python tests/test_runner.py matchering

# 运行高级功能测试
python tests/test_runner.py advanced

# 运行性能基准测试
python tests/test_runner.py performance

# 运行所有测试
python tests/test_runner.py all

# 详细输出
python tests/test_runner.py all -v

# 不生成报告
python tests/test_runner.py basic --no-report
```

#### 2. 直接使用 pytest

```bash
# 运行所有测试
pytest tests/

# 运行特定测试文件
pytest tests/test_basic_functionality.py

# 详细输出
pytest tests/ -v

# 并行测试
pytest tests/ -n auto

# 生成覆盖率报告
pytest tests/ --cov=realtimemix --cov-report=html
```

## 📊 测试报告

测试运行器会自动生成详细的测试报告：

- **JSON 报告**: 包含完整的测试数据和结果
- **HTML 报告**: 美观的可视化测试报告

报告存储在 `tests/reports/` 目录中。

## 🎯 测试覆盖范围

### 功能覆盖
- ✅ 音频引擎初始化和配置
- ✅ 音轨加载（预加载和流式）
- ✅ 播放控制和状态管理
- ✅ 音量控制和动态调整
- ✅ Matchering 音频匹配
- ✅ 多轨道同时播放
- ✅ 错误处理和恢复
- ✅ 资源管理和清理

### 性能覆盖
- ✅ 加载速度基准
- ✅ 播放延迟测试
- ✅ CPU 使用率监控
- ✅ 内存使用分析
- ✅ 并发性能测试
- ✅ 长期稳定性验证

### 兼容性覆盖
- ✅ 多种采样率 (22050, 44100, 48000, 96000 Hz)
- ✅ 多种声道配置 (单声道, 立体声)
- ✅ 不同音频格式和时长
- ✅ 各种音量级别 (静音, 低音量, 高音量)

## 🔧 自定义测试

### 添加新测试

1. 在适当的测试文件中添加新的测试函数
2. 使用 pytest 标记进行分类
3. 利用 `conftest.py` 中的 fixtures

### 示例测试函数

```python
import pytest

def test_custom_feature(audio_engine, test_audio_files):
    """测试自定义功能"""
    # 测试逻辑
    assert True

@pytest.mark.slow
def test_slow_operation(audio_engine):
    """慢速测试示例"""
    # 耗时操作
    pass

@pytest.mark.matchering
def test_matchering_feature(audio_engine, test_audio_files):
    """需要 matchering 的测试"""
    # matchering 相关测试
    pass
```

### 自定义 Fixtures

在 `conftest.py` 中添加新的 fixtures：

```python
@pytest.fixture
def custom_engine():
    """自定义引擎配置"""
    engine = AudioEngine(
        sample_rate=96000,
        buffer_size=512,
        channels=2
    )
    engine.start()
    yield engine
    engine.shutdown()
```

## 📈 性能基准

### 基准指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 音轨加载时间 | < 10% 音频时长 | 加载效率 |
| 播放启动延迟 | < 50ms | 响应速度 |
| CPU 使用率 | < 50% (8轨道) | 资源效率 |
| 内存使用 | < 50MB/轨道 | 内存效率 |
| 最大并发轨道 | ≥ 8 | 扩展性 |

### 性能监控

测试套件会自动监控以下性能指标：
- CPU 使用率
- 内存使用量
- 音频缓冲区欠载次数
- 峰值音频电平
- 文件句柄使用

## 🐛 故障排除

### 常见问题

1. **Matchering 库未安装**
   ```bash
   pip install matchering
   ```

2. **音频设备问题**
   - 确保系统有可用的音频输出设备
   - 检查音频驱动程序

3. **权限问题**
   - 确保有写入临时目录的权限
   - 检查音频设备访问权限

4. **内存不足**
   - 减少并发测试数量
   - 使用流式播放模式

### 调试技巧

```bash
# 启用详细日志
pytest tests/ -v -s --log-cli-level=DEBUG

# 只运行失败的测试
pytest tests/ --lf

# 在第一个失败时停止
pytest tests/ -x

# 禁用捕获以查看实时输出
pytest tests/ -s
```

## 🤝 贡献指南

### 添加新测试

1. 确定测试类别（基本/高级/性能/集成）
2. 编写清晰的测试函数和文档
3. 添加适当的 pytest 标记
4. 更新此 README 文档

### 代码风格

- 遵循 PEP 8 规范
- 使用类型提示
- 编写清晰的文档字符串
- 添加必要的注释

### 提交测试

1. 运行完整测试套件确保通过
2. 检查代码风格
3. 更新相关文档
4. 提交 Pull Request

## 📞 支持

如果在使用测试套件时遇到问题：

1. 查看此 README 的故障排除部分
2. 检查测试报告中的详细错误信息
3. 运行快速检查诊断环境问题
4. 提交 Issue 并附上详细的错误信息

---

**注意**: 此测试套件需要真实的音频设备和相关权限。在 CI/CD 环境中可能需要特殊配置。

## 位置回调测试 (test_position_callbacks.py)

专门测试实时音频位置回调机制的测试文件，包含以下测试类：

### TestBasicPositionCallbacks
- 基本回调注册和移除功能
- 回调清理功能
- 回调存储验证

### TestCallbackPrecision  
- 回调触发时间精度测试
- 不同容忍度设置测试
- 5-20ms精度要求验证

### TestMultiTrackCallbacks
- 多轨道同时回调功能
- 轨道间回调隔离测试
- 并发播放回调验证

### TestGlobalPositionListeners
- 全局位置监听器注册/移除
- 全局监听器功能验证
- 位置数据收集测试

### TestCallbackStatistics
- 回调统计信息验证
- 性能指标测试
- 统计数据结构检查

### TestErrorHandling
- 无效轨道回调处理
- 回调函数异常处理
- 错误边界条件测试

### TestPerformanceAndMemory
- 大量回调性能测试
- 内存清理验证
- 线程资源管理

### TestCallbackThreadBehavior
- 回调线程启动验证
- 自适应频率调整测试
- 线程生命周期管理

## 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行位置回调测试
python -m pytest tests/test_position_callbacks.py -v

# 运行特定测试类
python -m pytest tests/test_position_callbacks.py::TestCallbackPrecision -v

# 运行精度测试
python -c "from tests.test_position_callbacks import run_precision_test; run_precision_test()"

# 运行性能测试  
python -c "from tests.test_position_callbacks import run_performance_test; run_performance_test()"
```

## 测试覆盖

位置回调测试覆盖了以下API：

- `register_position_callback()` - 注册位置回调
- `remove_position_callback()` - 移除位置回调
- `add_global_position_listener()` - 添加全局监听器
- `remove_global_position_listener()` - 移除全局监听器
- `clear_all_position_callbacks()` - 清空所有回调
- `get_position_callback_stats()` - 获取回调统计

## 测试环境要求

- Python 3.8+
- pytest
- numpy
- realtimemix 音频引擎
- 音频设备（用于实际播放测试）

## 注意事项

1. **音频设备**: 测试需要可用的音频输出设备
2. **测试时间**: 完整测试套件需要约2-3分钟
3. **并发测试**: 某些测试涉及实际音频播放，可能受系统负载影响
4. **精度要求**: 在不同系统上，回调精度可能略有差异（通常在5-20ms范围内）

## 故障排除

如果测试失败：

1. 检查音频设备是否可用
2. 确认系统负载不过高
3. 验证依赖包版本
4. 查看测试日志中的具体错误信息

## 开发指南

添加新的位置回调测试时：

1. 继承适当的测试基类
2. 使用 `CallbackTracker` 工具类跟踪回调
3. 考虑测试环境的性能限制
4. 添加适当的错误处理测试
5. 确保测试清理资源

## 配置

测试配置位于：
- `conftest.py` - pytest 配置和共享fixtures
- `pytest.ini` - pytest 运行配置
- `requirements-test.txt` - 测试依赖包

## 持续集成

这些测试设计为在CI环境中运行，包括：
- 自动资源清理
- 合理的超时设置
- 跨平台兼容性
- 错误容忍机制 