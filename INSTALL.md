# AudioMixer 安装指南

## 项目结构
```
AudioMixer/
├── audiomixer/                  # 主要的Python包
│   ├── __init__.py             # 主要的AudioEngine类和相关功能
│   └── py.typed                # 类型注解标记文件
├── examples/                   # 使用示例
│   └── basic_usage.py         # 基础用法示例
├── tests/                     # 单元测试
│   └── test_audiomixer.py     # 主要测试文件
├── pyproject.toml             # 项目配置和依赖
├── README.md                  # 项目文档
├── LICENSE                    # MIT许可证
└── INSTALL.md                 # 本安装指南
```

## 安装方式

### 1. 从源码安装 (开发模式)

```bash
# 克隆仓库
git clone https://github.com/yourusername/audiomixer.git
cd audiomixer

# 安装为可编辑模式 (推荐开发使用)
pip install -e .

# 或安装所有可选依赖
pip install -e .[all]
```

### 2. 构建并安装

```bash
# 安装构建工具
pip install build

# 构建分发包
python -m build

# 安装构建的包
pip install dist/audiomixer-1.0.0-py3-none-any.whl
```

### 3. 发布到PyPI (维护者使用)

```bash
# 安装发布工具
pip install twine

# 构建包
python -m build

# 上传到测试PyPI
twine upload --repository testpypi dist/*

# 上传到正式PyPI
twine upload dist/*
```

## 依赖说明

### 核心依赖 (自动安装)
- `numpy >= 1.19.0` - 数组处理
- `sounddevice >= 0.4.0` - 音频设备接口
- `soundfile >= 0.10.0` - 音频文件读取

### 可选依赖

#### 高质量音频处理
```bash
pip install audiomixer[high-quality]
```
包含:
- `librosa >= 0.8.0` - 高质量重采样
- `scipy >= 1.7.0` - 信号处理

#### 时间伸缩功能
```bash
pip install audiomixer[time-stretch]
```
包含:
- `pyrubberband >= 0.3.0` - 高质量时间伸缩

#### 所有可选功能
```bash
pip install audiomixer[all]
```

#### 开发工具
```bash
pip install audiomixer[dev]
```
包含:
- `pytest >= 6.0` - 测试框架
- `pytest-cov` - 测试覆盖率
- `black` - 代码格式化
- `flake8` - 代码风格检查
- `mypy` - 类型检查
- `pre-commit` - Git钩子

## 验证安装

### 1. 基本导入测试
```bash
python -c "from audiomixer import AudioEngine; print('AudioMixer installed successfully!')"
```

### 2. 运行单元测试
```bash
pytest tests/ -v
```

### 3. 运行示例
```bash
python examples/basic_usage.py
```

## 开发环境设置

### 1. 创建虚拟环境
```bash
python -m venv audiomixer-env
source audiomixer-env/bin/activate  # Linux/Mac
# 或
audiomixer-env\Scripts\activate     # Windows
```

### 2. 安装开发依赖
```bash
pip install -e .[dev,all]
```

### 3. 设置pre-commit钩子
```bash
pre-commit install
```

### 4. 代码格式化
```bash
black audiomixer/ tests/ examples/
```

### 5. 类型检查
```bash
mypy audiomixer/
```

## 常见问题

### Q: 安装时提示缺少音频库
A: 某些系统可能需要额外安装音频系统库:

**Ubuntu/Debian:**
```bash
sudo apt-get install portaudio19-dev python3-dev
```

**macOS:**
```bash
brew install portaudio
```

**Windows:**
通常Python包已包含必要的库文件。

### Q: 导入时提示没有音频设备
A: 确保系统有可用的音频输出设备，在虚拟环境或容器中可能需要特殊配置。

### Q: 测试运行失败
A: 确保系统音频子系统正常工作，某些CI环境可能没有音频支持。

### Q: 可选依赖安装失败
A: 可选依赖(如librosa, pyrubberband)可能需要额外的系统库，可以只安装核心功能:
```bash
pip install audiomixer  # 仅核心功能
```

## 系统要求

- Python 3.8+
- 支持的操作系统: Windows, macOS, Linux
- 音频输出设备
- 对于某些高级功能，可能需要额外的系统库

## 许可证

本项目采用MIT许可证，详见LICENSE文件。 