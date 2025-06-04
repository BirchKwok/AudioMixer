"""
RealtimeMix - 高性能多轨音频混音器

提供完整的多轨音频播放、混音和管理功能。支持实时音频处理、
流式播放、音效处理等功能。

主要组件：
- AudioEngine: 主音频引擎
- StreamingTrackData: 流式音频轨道数据管理
- BufferPool: 缓冲池管理
- AudioProcessor: 音频处理器
"""

from .utils import logger
from .streaming import StreamingTrackData
from .buffer import BufferPool  
from .processor import AudioProcessor
from .engine import AudioEngine

# 导出主要类
__all__ = [
    'AudioEngine',
    'StreamingTrackData', 
    'BufferPool',
    'AudioProcessor',
    'logger'
]

__version__ = '1.1.1'
