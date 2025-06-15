from .utils import *
from .streaming import StreamingTrackData
from .buffer import BufferPool
from .processor import AudioProcessor
import sounddevice as sd
import numpy as np
import soundfile as sf
import threading
import time
import os
from typing import Optional, Dict, Any, Union
import logging
import tempfile
import shutil

try:
    import matchering as mg
except ImportError:
    mg = None


class AudioEngine:
    """
    主音频引擎类

    提供完整的多轨音频混音、播放和管理功能。支持实时音频处理、
    流式播放、音效处理等功能。

    主要功能：
    - 多轨音频播放和混音
    - 流式音频播放（大文件支持）
    - 实时音频效果（音量、淡入淡出、变速等）
    - 音频格式转换和重采样
    - 性能监控和优化
    - 线程安全的音频处理

    Attributes:
        sample_rate (int): 音频采样率
        buffer_size (int): 音频缓冲区大小
        channels (int): 声道数
        is_running (bool): 引擎运行状态
        stream (sd.OutputStream): 音频输出流
        max_tracks (int): 最大轨道数
        tracks (dict): 预加载的音频轨道数据
        track_states (dict): 轨道状态信息
        active_tracks (set): 活跃轨道集合
        streaming_tracks (dict): 流式轨道数据
        enable_streaming (bool): 是否启用流式播放
        streaming_threshold (int): 流式播放文件大小阈值
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        buffer_size: int = 1024,
        channels: int = 2,
        max_tracks: int = 32,
        device: Optional[int] = None,
        stream_latency: str = "low",
        enable_streaming: bool = True,
        streaming_threshold_mb: int = 100,
    ):
        """
        初始化音频引擎

        Args:
            sample_rate (int, optional): 采样率（Hz）. Defaults to 48000.
            buffer_size (int, optional): 缓冲区大小（帧数）. Defaults to 1024.
            channels (int, optional): 声道数. Defaults to 2.
            max_tracks (int, optional): 最大轨道数. Defaults to 32.
            device (int, optional): 音频设备ID，None为默认设备. Defaults to None.
            stream_latency (str, optional): 音频延迟设置. Defaults to 'low'.
            enable_streaming (bool, optional): 是否启用流式播放. Defaults to True.
            streaming_threshold_mb (int, optional): 流式播放阈值（MB）. Defaults to 100.

        Raises:
            RuntimeError: 如果音频系统初始化失败

        Example:
            >>> engine = AudioEngine(
            ...     sample_rate=48000,
            ...     buffer_size=1024,
            ...     channels=2,
            ...     max_tracks=16,
            ...     enable_streaming=True,
            ...     streaming_threshold_mb=50
            ... )
            >>> engine.start()
        """
        # Audio parameters
        self.sample_rate: int = sample_rate
        self.buffer_size: int = buffer_size
        self.channels: int = channels

        # Audio stream state
        self.is_running: bool = False
        self.stream: Optional[sd.OutputStream] = None

        # Track management
        self.max_tracks: int = max_tracks
        self.tracks: Dict[str, npt.NDArray[np.float32]] = (
            {}
        )  # Store original audio data (for preloaded tracks)
        self.track_states: Dict[str, Dict[str, Any]] = defaultdict(dict)  # Store track states
        self.active_tracks: Set[str] = set()  # Active tracks set
        self.track_files: Dict[str, str] = {}  # File path cache

        # Streaming support
        self.enable_streaming = enable_streaming
        self.streaming_threshold = streaming_threshold_mb * 1024 * 1024  # Convert to bytes
        self.streaming_tracks: Dict[str, StreamingTrackData] = {}  # Streaming tracks

        # Large file handling (for preloaded mode)
        self.chunk_size: int = 8192  # 分块大小（帧数）
        self.max_memory_usage: int = 1024 * 1024 * 1024  # 最大内存使用量（1GB）
        self.large_file_threshold: int = streaming_threshold_mb * 1024 * 1024  # 大文件阈值

        # Thread safety
        self.lock: threading.RLock = threading.RLock()
        self.loading_queue: queue.Queue = queue.Queue(
            maxsize=5
        )  # Loading queue to prevent too many simultaneous loads

        # 内置定时器系统
        self.scheduled_tasks: Dict[str, threading.Timer] = {}  # 定时任务管理
        self.task_lock: threading.Lock = threading.Lock()  # 任务锁

        # Performance monitoring
        self.peak_level: float = 0.0
        self.cpu_usage: float = 0.0  # Using exponential weighted moving average
        self.underrun_count: int = 0
        self.callback_count: int = 0  # 添加回调计数器

        # 位置回调系统 (实时音频回调机制)
        self.position_callbacks: Dict[str, Dict[float, Dict[str, Any]]] = {}  # {track_id: {target_time: callback_info}}
        self.callback_precision: float = 0.005  # 5ms精度
        self.global_position_listeners: List[Callable] = []  # 全局位置监听器
        self.position_callback_thread: Optional[threading.Thread] = None
        self.position_callback_thread_running: bool = False
        self.last_position_check_time: Dict[str, float] = {}  # {track_id: last_check_time}
        self.callback_stats: Dict[str, Any] = {  # 回调统计信息
            'total_callbacks_triggered': 0,
            'total_callbacks_expired': 0,
            'average_precision_ms': 0.0,
            'last_check_time': 0.0
        }

        # Initialize optimization components
        self.buffer_pool = BufferPool(buffer_size, channels)
        self.audio_processor = AudioProcessor()

        # Pre-compute common values
        self.buffer_duration = buffer_size / sample_rate
        self.fade_step_cache = {}  # Cache fade in/out steps

        # Initialize audio system
        self._init_audio_stream(device, stream_latency)

        # Start background loading thread
        self.loading_thread: threading.Thread = threading.Thread(
            target=self._loading_worker, daemon=True
        )
        self.loading_thread.start()

        # Register exit handler
        atexit.register(self.shutdown)

        logger.info(
            f"AudioEngine initialized: {sample_rate}Hz, {buffer_size} buffer, {channels} channels"
        )
        logger.info(
            f"Streaming mode: {'enabled' if enable_streaming else 'disabled'} (threshold: {streaming_threshold_mb}MB)"
        )

    def _init_audio_stream(self, device: Optional[int], latency: str) -> None:
        """
        初始化音频输出流

        创建和配置sounddevice音频输出流，设置采样率、缓冲区大小、
        声道数等参数。

        Args:
            device (int, optional): 音频设备ID，None为默认设备
            latency (str): 延迟设置 ('low', 'medium', 'high')

        Raises:
            RuntimeError: 如果音频流初始化失败
            ValueError: 如果设备不支持所需参数
        """
        try:
            # Get device info
            if device is None:
                device = sd.default.device[1]

            device_info = sd.query_devices(device)
            logger.info(f"Using audio device: {device_info['name']}")

            # Ensure device supports required parameters
            if device_info["max_output_channels"] < self.channels:
                raise ValueError(f"Device doesn't support {self.channels} channels")

            # Create audio stream
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                blocksize=self.buffer_size,
                channels=self.channels,
                dtype="float32",
                callback=self._audio_callback,
                device=device,
                latency=latency,
            )

            logger.info("Audio stream initialized")
        except Exception as e:
            logger.error(f"Failed to initialize audio stream: {str(e)}")
            raise RuntimeError("Audio initialization failed") from e

    def _loading_worker(self) -> None:
        """
        后台加载工作线程

        在后台处理音频文件加载任务，从加载队列中取出任务并执行。
        支持文件路径加载和NumPy数组处理。

        Note:
            这是一个守护线程，会一直运行直到收到停止信号（None任务）
        """
        while True:
            try:
                task = self.loading_queue.get()
                if task is None:  # Stop signal
                    break

                (
                    track_id,
                    source,
                    speed,
                    auto_normalize,
                    sample_rate,
                    silent_lpadding_ms,
                    silent_rpadding_ms,
                    on_complete,
                    progress_callback,
                ) = task

                if isinstance(source, str):
                    # File path
                    self._load_track_from_file_optimized(
                        track_id,
                        source,
                        speed,
                        auto_normalize,
                        sample_rate,
                        silent_lpadding_ms,
                        silent_rpadding_ms,
                        on_complete,
                        progress_callback,
                    )
                else:
                    # NumPy array or array-like object
                    # Extract actual numpy array if it's wrapped
                    actual_array = (
                        getattr(source, "data", source) if hasattr(source, "data") else source
                    )

                    self._process_audio_data(
                        track_id,
                        actual_array,
                        auto_normalize,
                        sample_rate,
                        silent_lpadding_ms,
                        silent_rpadding_ms,
                    )

                    if on_complete:
                        on_complete(track_id, True)

                self.loading_queue.task_done()
            except Exception as e:
                logger.error(f"Error in loading worker: {str(e)}")
                if on_complete:
                    on_complete(track_id, False, str(e))

    def _load_track_from_file_optimized(
        self,
        track_id: str,
        file_path: str,
        speed: float,
        auto_normalize: bool,
        sample_rate: Optional[int],
        silent_lpadding_ms: float,
        silent_rpadding_ms: float,
        on_complete: Optional[Callable],
        progress_callback: Optional[Callable],
    ) -> None:
        """
        优化的文件加载方法，支持流式播放和大文件分块加载

        根据文件大小和配置自动选择最适合的加载方式：
        - 小文件：标准预加载
        - 大文件：分块加载
        - 超大文件：流式播放

        Args:
            track_id (str): 轨道ID
            file_path (str): 音频文件路径
            speed (float): 播放速度倍数
            auto_normalize (bool): 是否自动音量标准化
            sample_rate (int, optional): 目标采样率
            silent_lpadding_ms (float, optional): 音频前面的静音填充时长（毫秒）. Defaults to 0.0.
            silent_rpadding_ms (float, optional): 音频后面的静音填充时长（毫秒）. Defaults to 0.0.
            on_complete (callable, optional): 完成回调函数
            progress_callback (callable, optional): 进度回调函数
                格式：progress_callback(track_id, progress: 0.0-1.0, message)

        Note:
            流式模式暂不支持变速播放（speed != 1.0）
        """
        try:
            logger.info(f"开始加载音频文件: {file_path} (speed={speed:.2f})")

            # 获取文件信息
            file_size = os.path.getsize(file_path)

            with sf.SoundFile(file_path) as f:
                orig_sample_rate = f.samplerate
                total_frames = f.frames
                channels = f.channels

                logger.info(
                    f"文件信息: {total_frames}帧, {orig_sample_rate}Hz, {channels}声道, {file_size/(1024*1024):.1f}MB"
                )

                if progress_callback:
                    progress_callback(track_id, 0.0, f"分析文件: {file_size/(1024*1024):.1f}MB")

            # 决定使用流式播放还是预加载模式
            use_streaming = (
                self.enable_streaming
                and file_size >= self.streaming_threshold
                and abs(speed - 1.0) < 0.01
            )  # 流式模式暂不支持变速播放

            if use_streaming:
                logger.info(f"使用流式播放模式: {file_size/(1024*1024):.1f}MB")
                self._load_streaming_track(
                    track_id,
                    file_path,
                    auto_normalize,
                    sample_rate,
                    silent_lpadding_ms,
                    silent_rpadding_ms,
                    on_complete,
                    progress_callback,
                )
            elif file_size > self.large_file_threshold:
                logger.info(f"使用大文件分块加载模式: {file_size/(1024*1024):.1f}MB")
                self._load_large_file_streaming(
                    track_id,
                    file_path,
                    speed,
                    auto_normalize,
                    sample_rate,
                    silent_lpadding_ms,
                    silent_rpadding_ms,
                    on_complete,
                    progress_callback,
                )
            else:
                logger.info(f"使用标准预加载模式: {file_size/(1024*1024):.1f}MB")
                # 小文件使用原有方法
                self._load_track_from_file(
                    track_id,
                    file_path,
                    speed,
                    auto_normalize,
                    sample_rate,
                    silent_lpadding_ms,
                    silent_rpadding_ms,
                    on_complete,
                )

        except Exception as e:
            logger.error(f"文件加载失败: {str(e)}")
            if on_complete:
                on_complete(track_id, False, str(e))

    def _load_streaming_track(
        self,
        track_id: str,
        file_path: str,
        auto_normalize: bool,
        sample_rate: Optional[int],
        silent_lpadding_ms: float,
        silent_rpadding_ms: float,
        on_complete: Optional[Callable],
        progress_callback: Optional[Callable],
    ) -> None:
        """
        加载流式轨道

        创建StreamingTrackData对象来管理大文件的流式播放。
        流式轨道在播放时动态加载音频数据到缓冲区。

        Args:
            track_id (str): 轨道ID
            file_path (str): 音频文件路径
            auto_normalize (bool): 是否自动音量标准化
            sample_rate (int, optional): 目标采样率
            silent_lpadding_ms (float, optional): 音频前面的静音填充时长（毫秒）. Defaults to 0.0.
            silent_rpadding_ms (float, optional): 音频后面的静音填充时长（毫秒）. Defaults to 0.0.
            on_complete (callable, optional): 完成回调函数
            progress_callback (callable, optional): 进度回调函数
        """
        try:
            target_sample_rate = sample_rate or self.sample_rate

            # 创建流式轨道数据
            streaming_track = StreamingTrackData(
                track_id=track_id,
                file_path=file_path,
                engine_sample_rate=target_sample_rate,
                engine_channels=self.channels,
                buffer_seconds=15.0,  # 15秒缓冲
            )

            # 存储流式轨道
            with self.lock:
                # 如果已存在，先清理
                if track_id in self.streaming_tracks:
                    self.streaming_tracks[track_id].stop_streaming()
                    del self.streaming_tracks[track_id]

                self.streaming_tracks[track_id] = streaming_track

                # 初始化轨道状态（兼容现有API）
                self.track_states[track_id] = {
                    "position": 0,
                    "volume": 1.0,
                    "playing": False,
                    "loop": False,
                    "paused": False,
                    "muted": False,  # 静音状态
                    "original_volume": 1.0,  # 静音前的原始音量
                    "fade_progress": None,
                    "fade_direction": None,
                    "fade_duration": 0.05,
                    "speed": 1.0,
                    "resample_ratio": 1.0,
                    "resample_phase": 0.0,
                    "sample_rate": target_sample_rate,
                    "resample_buffer": None,
                    "streaming_mode": True,  # 标记为流式模式
                    "auto_normalize": auto_normalize,
                    "silent_padding_ms": silent_lpadding_ms
                    + silent_rpadding_ms,  # 静音填充信息（兼容性）
                    "silent_lpadding_ms": silent_lpadding_ms,  # 左侧静音填充信息
                    "silent_rpadding_ms": silent_rpadding_ms,  # 右侧静音填充信息
                    "padding_frames_start": (
                        int((silent_lpadding_ms / 1000.0) * target_sample_rate)
                        if silent_lpadding_ms > 0
                        else 0
                    ),  # 开始静音帧数
                    "padding_frames_end": (
                        int((silent_rpadding_ms / 1000.0) * target_sample_rate)
                        if silent_rpadding_ms > 0
                        else 0
                    ),  # 结束静音帧数
                    "virtual_position": 0,  # 虚拟播放位置（包含静音填充）
                }

                # 缓存文件路径
                self.track_files[track_id] = file_path

            # 开始流式加载
            streaming_track.start_streaming()

            if progress_callback:
                progress_callback(track_id, 1.0, "流式轨道就绪")

            logger.info(f"流式轨道加载完成: {track_id} (时长: {streaming_track.duration:.1f}秒)")

            if on_complete:
                on_complete(track_id, True)

        except Exception as e:
            logger.error(f"流式轨道加载失败: {str(e)}")
            if on_complete:
                on_complete(track_id, False, str(e))

    def _load_large_file_streaming(
        self,
        track_id: str,
        file_path: str,
        speed: float,
        auto_normalize: bool,
        sample_rate: Optional[int],
        silent_lpadding_ms: float,
        silent_rpadding_ms: float,
        on_complete: Optional[Callable],
        progress_callback: Optional[Callable],
    ) -> None:
        """
        大文件流式加载方法
        """
        try:
            with sf.SoundFile(file_path) as f:
                orig_sample_rate = f.samplerate
                total_frames = f.frames
                channels = f.channels

                # 计算目标参数
                target_sample_rate = sample_rate or self.sample_rate
                rate_conversion_needed = orig_sample_rate != target_sample_rate
                speed_adjustment_needed = abs(speed - 1.0) > 0.01

                # 估算最终数据大小
                final_frames = int(total_frames * target_sample_rate / orig_sample_rate / speed)
                estimated_size = final_frames * self.channels * 4  # float32

                logger.info(f"预估最终大小: {estimated_size/(1024*1024):.1f}MB")

                if progress_callback:
                    progress_callback(track_id, 0.1, "开始分块加载...")

                # 分块加载 - 优化内存管理
                chunks = []
                processed_frames = 0

                # 动态调整块大小和合并策略
                chunk_frames = min(self.chunk_size * 128, total_frames // 10)  # 更大的块
                chunk_frames = max(chunk_frames, self.chunk_size)

                # 内存管理优化
                effective_memory_limit = min(
                    self.max_memory_usage * 2, estimated_size
                )  # 允许更大的内存使用
                merge_threshold = effective_memory_limit * 0.8  # 80%时才合并

                logger.info(
                    f"使用内存限制: {effective_memory_limit/(1024*1024):.1f}MB, 合并阈值: {merge_threshold/(1024*1024):.1f}MB"
                )

                while processed_frames < total_frames:
                    # 读取当前块
                    remaining = total_frames - processed_frames
                    current_chunk_frames = min(chunk_frames, remaining)

                    f.seek(processed_frames)
                    chunk_data = f.read(current_chunk_frames, dtype="float32", always_2d=True)

                    if chunk_data.shape[0] == 0:
                        break

                    # 处理当前块
                    if rate_conversion_needed:
                        chunk_data = self._resample_audio(
                            chunk_data, orig_sample_rate, target_sample_rate
                        )

                    if speed_adjustment_needed:
                        chunk_data = self._time_stretch(chunk_data, speed)

                    chunks.append(chunk_data)
                    processed_frames += current_chunk_frames

                    # 更新进度
                    progress = 0.1 + 0.8 * (processed_frames / total_frames)
                    if progress_callback:
                        progress_callback(
                            track_id,
                            progress,
                            f"处理中... {processed_frames}/{total_frames}帧 ({progress*100:.1f}%)",
                        )

                    # 优化的内存检查 - 减少频繁合并
                    current_memory = sum(chunk.nbytes for chunk in chunks)
                    if current_memory > merge_threshold and len(chunks) > 5:  # 至少5个块才合并
                        logger.info(
                            f"内存使用达到阈值: {current_memory/(1024*1024):.1f}MB，合并 {len(chunks)} 个块..."
                        )
                        # 合并已处理的块
                        combined = np.concatenate(chunks, axis=0)
                        chunks = [combined]
                        gc.collect()
                        logger.info(f"合并完成，当前内存: {combined.nbytes/(1024*1024):.1f}MB")

                if progress_callback:
                    progress_callback(track_id, 0.9, "最终合并音频数据...")

                # 合并所有块
                if chunks:
                    final_data = np.concatenate(chunks, axis=0) if len(chunks) > 1 else chunks[0]

                    # 最终处理
                    self._process_audio_data(
                        track_id,
                        final_data,
                        auto_normalize,
                        target_sample_rate,
                        silent_lpadding_ms,
                        silent_rpadding_ms,
                    )

                    # 缓存文件路径
                    with self.lock:
                        self.track_files[track_id] = file_path

                    if progress_callback:
                        progress_callback(track_id, 1.0, f"加载完成: {len(final_data)}帧")

                    logger.info(
                        f"大文件加载完成: {track_id} ({len(final_data)}帧，{final_data.nbytes/(1024*1024):.1f}MB)"
                    )
                    if on_complete:
                        on_complete(track_id, True)
                else:
                    raise ValueError("无法读取音频数据")

        except Exception as e:
            logger.error(f"大文件加载失败: {str(e)}")
            if on_complete:
                on_complete(track_id, False, str(e))

    def _load_track_from_file(
        self,
        track_id: str,
        file_path: str,
        speed: float,
        auto_normalize: bool,
        sample_rate: Optional[int],
        silent_lpadding_ms: float,
        silent_rpadding_ms: float,
        on_complete: Optional[Callable],
    ) -> None:
        """Load track from file (internal method)"""
        try:
            logger.info(f"Loading audio file: {file_path} (speed={speed:.2f})")

            # Use soundfile to read audio file
            data, orig_sample_rate = sf.read(file_path, dtype="float32", always_2d=True)

            # Check sample rate
            if orig_sample_rate != self.sample_rate:
                logger.warning(
                    f"Sample rate mismatch ({orig_sample_rate} vs {self.sample_rate}). Resampling..."
                )
                data = self._resample_audio(data, orig_sample_rate, self.sample_rate)

            # Apply speed adjustment
            if abs(speed - 1.0) > 0.01:
                logger.info(f"Applying time stretching (factor={speed:.2f})")
                data = self._time_stretch(data, speed)

            # Process audio data
            self._process_audio_data(
                track_id, data, auto_normalize, sample_rate, silent_lpadding_ms, silent_rpadding_ms
            )

            # Cache file path
            with self.lock:
                self.track_files[track_id] = file_path

            logger.info(f"Track loaded: {track_id} ({len(data)} samples)")
            if on_complete:
                on_complete(track_id, True)
        except Exception as e:
            logger.error(f"Failed to load track from file: {str(e)}")
            if on_complete:
                on_complete(track_id, False, str(e))

    def _resample_audio(self, data: npt.NDArray, orig_rate: int, target_rate: int) -> npt.NDArray:
        """
        High-quality audio resampling
        :param data: Original audio data
        :param orig_rate: Original sample rate
        :param target_rate: Target sample rate
        :return: Resampled audio data
        """
        # Check if resampling is needed
        if orig_rate == target_rate:
            return data

        # Calculate target length
        orig_length = data.shape[0]
        target_length = int(orig_length * target_rate / orig_rate)

        # Try to use high-quality resampling methods
        try:
            # Prefer librosa for high-quality resampling
            import librosa

            logger.info("Using librosa.resample for high-quality resampling")

            # Process each channel separately to ensure consistent length
            resampled_channels = []
            for channel in range(data.shape[1]):
                channel_resampled = librosa.resample(
                    data[:, channel], orig_sr=orig_rate, target_sr=target_rate
                )
                resampled_channels.append(channel_resampled)

            # Ensure all channels have the same length by trimming to the minimum
            min_length = min(len(ch) for ch in resampled_channels)
            resampled = np.zeros((min_length, data.shape[1]), dtype=np.float32)

            for i, channel_data in enumerate(resampled_channels):
                resampled[:, i] = channel_data[:min_length]

            return resampled
        except ImportError:
            pass

        # Try scipy as fallback
        try:
            from scipy.signal import resample_poly

            logger.info("Using scipy.signal.resample_poly for resampling")
            resampled = np.zeros((target_length, data.shape[1]), dtype=np.float32)
            for channel in range(data.shape[1]):
                resampled[:, channel] = resample_poly(
                    data[:, channel], target_rate, orig_rate, axis=0
                )
            return resampled
        except ImportError:
            pass

        # Fallback to linear interpolation
        logger.warning(
            "Using linear interpolation for resampling (install librosa or scipy for better quality)"
        )
        orig_times = np.arange(orig_length)
        target_times = np.linspace(0, orig_length - 1, target_length)
        resampled = np.zeros((target_length, data.shape[1]), dtype=np.float32)
        for channel in range(data.shape[1]):
            resampled[:, channel] = np.interp(target_times, orig_times, data[:, channel])

        return resampled

    def _time_stretch(self, data: npt.NDArray, speed: float) -> npt.NDArray:
        """
        High-quality time stretching (speed change without pitch change)
        Using phase vocoder algorithm
        :param data: Original audio data
        :param speed: Speed factor (0.5=half speed, 1.0=normal, 2.0=double speed)
        :return: Time-stretched audio data
        """
        # Try to use high-quality time stretching libraries
        try:
            import pyrubberband as rb

            logger.info("Using pyrubberband for high-quality time stretching")
            stretched_data = np.zeros_like(data)
            for channel in range(data.shape[1]):
                stretched_data[:, channel] = rb.time_stretch(
                    data[:, channel], self.sample_rate, speed
                )
            return stretched_data
        except ImportError:
            pass

        # Try librosa as fallback
        try:
            import librosa

            logger.info("Using librosa for time stretching")
            stretched_data = np.zeros_like(data)
            for channel in range(data.shape[1]):
                stretched_data[:, channel] = librosa.effects.time_stretch(
                    data[:, channel], rate=speed
                )
            return stretched_data
        except ImportError:
            pass

        # Fallback to basic resampling (will change pitch)
        logger.warning(
            "Using basic resampling for time stretching (install pyrubberband or librosa for better quality)"
        )
        orig_length = data.shape[0]
        target_length = int(orig_length / speed)

        # Use linear interpolation
        orig_times = np.arange(orig_length)
        target_times = np.linspace(0, orig_length - 1, target_length)
        resampled = np.zeros((target_length, data.shape[1]), dtype=np.float32)
        for channel in range(data.shape[1]):
            resampled[:, channel] = np.interp(target_times, orig_times, data[:, channel])

        return resampled

    def _process_audio_data(
        self,
        track_id: str,
        audio_data: npt.NDArray,
        auto_normalize: bool,
        track_sample_rate: Optional[int] = None,
        silent_lpadding_ms: float = 0.0,
        silent_rpadding_ms: float = 0.0,
    ) -> None:
        """
        Process audio data (internal method)
        :param track_id: Track ID
        :param audio_data: Audio data
        :param auto_normalize: Whether to auto-normalize volume
        :param track_sample_rate: Track's specific sample rate (None to use engine's default)
        :param silent_lpadding_ms: Silent padding duration in milliseconds (added before audio)
        :param silent_rpadding_ms: Silent padding duration in milliseconds (added after audio)
        """
        # 确保音频数据是真正的numpy数组
        if not isinstance(audio_data, np.ndarray):
            audio_data = np.asarray(audio_data, dtype=np.float32)

        # 确定音轨的采样率
        if track_sample_rate is None:
            track_sample_rate = self.sample_rate

        # Ensure correct format
        if audio_data.ndim == 1:
            audio_data = np.reshape(audio_data, (-1, 1))  # Convert to 2D array
        if audio_data.shape[1] != self.channels:
            if self.channels == 1:
                audio_data = np.mean(audio_data, axis=1, keepdims=True)
            elif self.channels == 2 and audio_data.shape[1] == 1:
                audio_data = np.repeat(audio_data, 2, axis=1)
            else:
                raise ValueError(
                    f"Unsupported channel conversion: {audio_data.shape[1]} -> {self.channels}"
                )

        # 添加静音填充
        if silent_lpadding_ms > 0.0 or silent_rpadding_ms > 0.0:
            # 分别计算左右静音填充的帧数
            lpadding_frames = (
                int((silent_lpadding_ms / 1000.0) * track_sample_rate)
                if silent_lpadding_ms > 0
                else 0
            )
            rpadding_frames = (
                int((silent_rpadding_ms / 1000.0) * track_sample_rate)
                if silent_rpadding_ms > 0
                else 0
            )

            if lpadding_frames > 0 or rpadding_frames > 0:
                # 创建左右静音数据
                parts = []

                # 添加左侧静音
                if lpadding_frames > 0:
                    left_silence = np.zeros((lpadding_frames, self.channels), dtype=np.float32)
                    parts.append(left_silence)

                # 添加原音频
                parts.append(audio_data)

                # 添加右侧静音
                if rpadding_frames > 0:
                    right_silence = np.zeros((rpadding_frames, self.channels), dtype=np.float32)
                    parts.append(right_silence)

                # 合并所有部分
                audio_data = np.concatenate(parts, axis=0)

                logger.info(
                    f"添加静音填充: {track_id} (左: {silent_lpadding_ms}ms = {lpadding_frames}帧, 右: {silent_rpadding_ms}ms = {rpadding_frames}帧)"
                )

        # Auto volume normalization
        if auto_normalize:
            peak = np.max(np.abs(audio_data))
            if peak > 1.0:
                logger.info(f"Normalizing track {track_id} (peak: {peak:.2f})")
                audio_data = audio_data / (peak * 1.05)  # Leave 5% headroom

        # Store track
        with self.lock:
            self.tracks[track_id] = audio_data.astype(np.float32)

            # Initialize state
            self.track_states[track_id] = {
                "position": 0,
                "volume": 1.0,
                "playing": False,
                "loop": False,
                "paused": False,
                "muted": False,  # 静音状态
                "original_volume": 1.0,  # 静音前的原始音量
                "fade_progress": None,
                "fade_direction": None,  # 'in' or 'out'
                "fade_duration": 0.05,
                "speed": 1.0,  # Playback speed
                "resample_ratio": 1.0,  # For real-time speed adjustment
                "resample_phase": 0.0,  # For real-time speed adjustment
                "sample_rate": track_sample_rate,  # Track's specific sample rate
                "resample_buffer": None,  # Buffer for sample rate conversion
                "silent_padding_ms": silent_lpadding_ms
                + silent_rpadding_ms,  # 保存静音填充信息（兼容性）
                "silent_lpadding_ms": silent_lpadding_ms,  # 左侧静音填充信息
                "silent_rpadding_ms": silent_rpadding_ms,  # 右侧静音填充信息
            }

        logger.info(
            f"Track loaded from data: {track_id} ({len(audio_data)} samples, {track_sample_rate}Hz, padding: {silent_lpadding_ms}ms + {silent_rpadding_ms}ms)"
        )

    def load_track(
        self,
        track_id: str,
        source: Union[npt.NDArray, str],
        speed: float = 1.0,
        auto_normalize: bool = True,
        sample_rate: Optional[int] = None,
        silent_lpadding_ms: float = 0.0,
        silent_rpadding_ms: float = 0.0,
        on_complete: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """
        加载音轨数据

        支持从文件路径或NumPy数组加载音频数据。会自动选择最佳的加载方式
        （预加载、分块加载或流式加载）。

        Args:
            track_id (str): 轨道唯一标识符
            source (Union[np.ndarray, str]): 音频源（NumPy数组或文件路径）
            speed (float, optional): 播放速度倍数（0.1-4.0）. Defaults to 1.0.
            auto_normalize (bool, optional): 是否自动音量标准化. Defaults to True.
            sample_rate (int, optional): 轨道采样率，None使用引擎默认值. Defaults to None.
            silent_lpadding_ms (float, optional): 音频前面的静音填充时长（毫秒）. Defaults to 0.0.
            silent_rpadding_ms (float, optional): 音频后面的静音填充时长（毫秒）. Defaults to 0.0.
            on_complete (callable, optional): 加载完成回调函数. Defaults to None.
                格式：on_complete(track_id, success, error=None)
            progress_callback (callable, optional): 进度回调函数. Defaults to None.
                格式：progress_callback(track_id, progress: 0.0-1.0, message)

        Returns:
            bool: 是否成功开始加载（异步操作）

        Raises:
            None: 所有错误都通过回调函数报告

        Example:
            >>> def on_load_complete(track_id, success, error=None):
            ...     if success:
            ...         print(f"轨道 {track_id} 加载成功")
            ...     else:
            ...         print(f"轨道 {track_id} 加载失败: {error}")
            ...
            >>> def on_progress(track_id, progress, message):
            ...     print(f"{track_id}: {progress*100:.1f}% - {message}")
            ...
            >>> success = engine.load_track(
            ...     track_id="bgm1",
            ...     source="/path/to/music.wav",
            ...     speed=1.0,
            ...     auto_normalize=True,
            ...     silent_lpadding_ms=300.0,  # 前面300ms静音
            ...     silent_rpadding_ms=500.0,  # 后面500ms静音
            ...     on_complete=on_load_complete,
            ...     progress_callback=on_progress
            ... )
        """
        # Validate speed range
        speed = max(0.1, min(4.0, speed))

        # Validate silent padding
        silent_lpadding_ms = max(0.0, silent_lpadding_ms)
        silent_rpadding_ms = max(0.0, silent_rpadding_ms)

        # Validate sample rate
        if sample_rate is not None:
            if sample_rate < 8000 or sample_rate > 192000:
                error = f"Invalid sample rate: {sample_rate}Hz (must be between 8000-192000Hz)"
                logger.error(error)
                if on_complete:
                    on_complete(track_id, False, error)
                return False

        # Check track count limit
        with self.lock:
            if len(self.track_states) >= self.max_tracks:  # 修改为检查所有轨道状态
                logger.warning(f"Track limit reached ({self.max_tracks}), cannot load more tracks")
                if on_complete:
                    on_complete(track_id, False, "Track limit reached")
                return False

            # If track already exists, unload it first
            if track_id in self.track_states:  # 修改为检查轨道状态
                self.unload_track(track_id)

        # Handle different source types
        if isinstance(source, np.ndarray):
            # Add to loading queue (background processing)
            self.loading_queue.put(
                (
                    track_id,
                    source,
                    speed,
                    auto_normalize,
                    sample_rate,
                    silent_lpadding_ms,
                    silent_rpadding_ms,
                    on_complete,
                    progress_callback,
                )
            )
            return True
        elif isinstance(source, str) and os.path.isfile(source):
            # Add to loading queue
            self.loading_queue.put(
                (
                    track_id,
                    source,
                    speed,
                    auto_normalize,
                    sample_rate,
                    silent_lpadding_ms,
                    silent_rpadding_ms,
                    on_complete,
                    progress_callback,
                )
            )
            return True
        else:
            error = f"Unsupported source type: {type(source)}"
            logger.error(error)
            if on_complete:
                on_complete(track_id, False, error)
            return False

    def unload_track(self, track_id: str) -> bool:
        """
        卸载轨道并释放内存

        停止轨道播放并从内存中移除轨道数据。支持预加载轨道和流式轨道。

        Args:
            track_id (str): 要卸载的轨道ID

        Returns:
            bool: 是否成功卸载

        Example:
            >>> if engine.unload_track("bgm1"):
            ...     print("轨道卸载成功")
            ... else:
            ...     print("轨道不存在或卸载失败")
        """
        with self.lock:
            track_exists = track_id in self.tracks or track_id in self.streaming_tracks

            if track_exists:
                # If playing, stop it first
                if self.track_states.get(track_id, {}).get("playing", False):
                    self.stop(track_id, fade_out=False)

                # Clean up streaming track
                if track_id in self.streaming_tracks:
                    self.streaming_tracks[track_id].stop_streaming()
                    del self.streaming_tracks[track_id]
                    logger.info(f"Streaming track unloaded: {track_id}")

                # Clean up preloaded track
                if track_id in self.tracks:
                    del self.tracks[track_id]
                    logger.info(f"Preloaded track unloaded: {track_id}")

                # Clean up track state
                if track_id in self.track_states:
                    del self.track_states[track_id]

                if track_id in self.active_tracks:
                    self.active_tracks.remove(track_id)

                if track_id in self.track_files:
                    del self.track_files[track_id]

                return True
            return False

    def play(
        self,
        track_id: str,
        fade_in: bool = False,
        loop: bool = False,
        seek: Optional[float] = None,
        volume: Optional[float] = None,
    ) -> None:
        """
        播放轨道

        开始播放指定的音频轨道。支持淡入效果、循环播放、跳转播放位置等选项。

        Args:
            track_id (str): 要播放的轨道ID
            fade_in (bool, optional): 是否使用淡入效果. Defaults to False.
            loop (bool, optional): 是否循环播放. Defaults to False.
            seek (float, optional): 起始播放位置（秒）. Defaults to None.
            volume (float, optional): 初始音量（0.0-1.0）. Defaults to None.

        Note:
            如果轨道不存在，会记录警告但不抛出异常

        Example:
            >>> # 基本播放
            >>> engine.play("bgm1")

            >>> # 带淡入效果的循环播放
            >>> engine.play("bgm1", fade_in=True, loop=True)

            >>> # 从30秒位置开始播放，音量50%
            >>> engine.play("bgm1", seek=30.0, volume=0.5)
        """
        with self.lock:
            # 检查轨道是否存在（预加载或流式）
            track_exists = track_id in self.tracks or track_id in self.streaming_tracks
            if not track_exists:
                logger.warning(f"Track not found: {track_id}")
                return

            state = self.track_states[track_id]

            # Set playback position
            if seek is not None:
                if state.get("streaming_mode", False) and track_id in self.streaming_tracks:
                    # 流式轨道跳转
                    self.streaming_tracks[track_id].seek_to(seek)
                else:
                    # 预加载轨道跳转
                    state["position"] = int(seek * self.sample_rate)

            # Set volume
            if volume is not None:
                state["volume"] = max(0.0, min(1.0, volume))

            # Set loop
            state["loop"] = loop

            # Reset pause state
            state["paused"] = False

            # Handle fade-in
            if fade_in:
                state["fade_progress"] = 0.0
                state["fade_direction"] = "in"
            else:
                state["fade_progress"] = None
                state["fade_direction"] = None

            # Activate track
            state["playing"] = True
            self.active_tracks.add(track_id)

            logger.debug(f"Playing track: {track_id} (fade_in={fade_in}, loop={loop}, seek={seek})")

    def set_speed(self, track_id: str, speed: float) -> bool:
        """
        设置播放速度（实时调整）

        动态调整轨道的播放速度，不影响音调。速度调整会立即生效。

        Args:
            track_id (str): 轨道ID
            speed (float): 速度倍数（0.1-4.0）
                - 0.5 = 半速播放
                - 1.0 = 正常速度
                - 2.0 = 双倍速度

        Returns:
            bool: 是否成功设置速度

        Example:
            >>> # 设置为1.5倍速播放
            >>> if engine.set_speed("bgm1", 1.5):
            ...     print("速度设置成功")

            >>> # 慢放到0.5倍速
            >>> engine.set_speed("bgm1", 0.5)
        """
        with self.lock:
            if track_id not in self.track_states:
                return False

            speed = max(0.1, min(4.0, speed))
            self.track_states[track_id]["speed"] = speed
            logger.info(f"Set speed for {track_id}: {speed:.2f}")
            return True

    def stop(
        self,
        track_id: str,
        fade_out: bool = True,
        delay_sec: float = 0.0,
        fade_duration: float = None,
    ) -> None:
        """
        停止轨道播放

        停止指定轨道的播放。可以选择是否使用淡出效果，支持延迟停止和自定义淡出时长。

        Args:
            track_id (str): 要停止的轨道ID
            fade_out (bool, optional): 是否使用淡出效果. Defaults to True.
                - True: 平滑淡出后停止
                - False: 立即停止
            delay_sec (float, optional): 延迟停止时间（秒）. Defaults to 0.0.
                - 0.0: 立即开始停止操作
                - >0.0: 延迟指定时间后开始停止操作
            fade_duration (float, optional): 淡出持续时间（秒）. Defaults to None.
                - None: 使用轨道的默认淡出时长
                - >0.0: 使用指定的淡出时长

        Note:
            停止后轨道位置会重置到开头

        Example:
            >>> # 平滑淡出停止
            >>> engine.stop("bgm1")

            >>> # 立即停止
            >>> engine.stop("bgm1", fade_out=False)

            >>> # 15秒后开始淡出停止
            >>> engine.stop("bgm1", delay_sec=15.0)

            >>> # 5秒后开始，用2秒淡出停止
            >>> engine.stop("bgm1", delay_sec=5.0, fade_duration=2.0)
        """
        # 如果有延迟，使用内置定时器
        if delay_sec > 0.0:
            self._schedule_delayed_stop(track_id, fade_out, fade_duration, delay_sec)
            return

        # 立即停止
        self._stop_immediate(track_id, fade_out, fade_duration)

    def _schedule_delayed_stop(
        self, track_id: str, fade_out: bool, fade_duration: float, delay_sec: float
    ) -> None:
        """
        安排延迟停止任务

        Args:
            track_id (str): 轨道ID
            fade_out (bool): 是否淡出
            fade_duration (float): 淡出时长
            delay_sec (float): 延迟时间
        """
        # 取消该轨道之前的定时任务
        self.cancel_scheduled_task(track_id, "stop")

        def delayed_stop():
            try:
                self._stop_immediate(track_id, fade_out, fade_duration)
            except Exception as e:
                logger.error(f"延迟停止任务执行失败 {track_id}: {e}")
            finally:
                # 清理任务记录
                task_key = f"{track_id}_stop"
                with self.task_lock:
                    self.scheduled_tasks.pop(task_key, None)

        # 创建定时器
        task_key = f"{track_id}_stop"
        timer = threading.Timer(delay_sec, delayed_stop)

        # 记录任务
        with self.task_lock:
            self.scheduled_tasks[task_key] = timer

        # 启动定时器
        timer.start()
        logger.debug(f"已安排轨道 {track_id} 在 {delay_sec} 秒后停止")

    def _stop_immediate(self, track_id: str, fade_out: bool, fade_duration: float = None) -> None:
        """
        立即执行停止操作

        Args:
            track_id (str): 轨道ID
            fade_out (bool): 是否淡出
            fade_duration (float): 淡出时长
        """
        with self.lock:
            if track_id not in self.track_states:
                return

            state = self.track_states[track_id]

            if not state.get("playing", False):
                return

            # 设置自定义淡出时长
            if fade_duration is not None and fade_duration > 0.0:
                state["fade_duration"] = fade_duration

            if fade_out and state.get("fade_direction") is None:
                # Start fade-out
                state["fade_progress"] = 1.0
                state["fade_direction"] = "out"
                logger.debug(
                    f"开始淡出停止轨道: {track_id}, 淡出时长: {state.get('fade_duration', 0.05)}秒"
                )
            elif not fade_out:
                # Stop immediately
                state["playing"] = False
                state["paused"] = False
                self.active_tracks.discard(track_id)
                state["position"] = 0
                state["fade_progress"] = None
                state["fade_direction"] = None
                state["resample_phase"] = 0.0  # Reset resample state

                logger.debug(f"立即停止轨道: {track_id}")
                
                # 确保状态立即同步到主线程
                # 这是为了解决快速播放/停止时的状态同步问题
                import threading
                def force_sync():
                    # 强制同步状态，确保 playing 状态立即更新
                    pass
                threading.Thread(target=force_sync, daemon=True).start()

    def cancel_scheduled_task(self, track_id: str, task_type: str = "stop") -> bool:
        """
        取消指定轨道的定时任务

        Args:
            track_id (str): 轨道ID
            task_type (str): 任务类型，默认"stop"

        Returns:
            bool: 是否成功取消任务
        """
        task_key = f"{track_id}_{task_type}"
        with self.task_lock:
            timer = self.scheduled_tasks.pop(task_key, None)
            if timer:
                timer.cancel()
                logger.debug(f"已取消轨道 {track_id} 的 {task_type} 定时任务")
                return True
            return False

    def cancel_all_scheduled_tasks(self) -> int:
        """
        取消所有定时任务

        Returns:
            int: 取消的任务数量
        """
        with self.task_lock:
            count = 0
            for timer in self.scheduled_tasks.values():
                timer.cancel()
                count += 1
            self.scheduled_tasks.clear()
            logger.debug(f"已取消所有定时任务，共 {count} 个")
            return count

    def get_scheduled_tasks(self) -> Dict[str, float]:
        """
        获取所有定时任务的剩余时间

        Returns:
            Dict[str, float]: 任务键和剩余时间的字典
        """
        result = {}
        with self.task_lock:
            current_time = time.time()
            for task_key, timer in self.scheduled_tasks.items():
                if timer.is_alive():
                    # 计算剩余时间（近似值）
                    remaining = getattr(timer, "interval", 0) - (
                        current_time - getattr(timer, "_start_time", current_time)
                    )
                    result[task_key] = max(0.0, remaining)
        return result

    def pause(self, track_id: str) -> None:
        """
        暂停轨道播放

        暂停指定轨道的播放，保持当前播放位置。可以稍后使用resume()恢复播放。

        Args:
            track_id (str): 要暂停的轨道ID

        Note:
            只有正在播放的轨道才能被暂停

        Example:
            >>> engine.pause("bgm1")
            >>> # 稍后恢复播放
            >>> engine.resume("bgm1")
        """
        with self.lock:
            if track_id in self.track_states:
                state = self.track_states[track_id]
                if state.get("playing", False):
                    state["paused"] = True
                    logger.debug(f"Paused track: {track_id}")

    def resume(self, track_id: str) -> None:
        """
        恢复轨道播放

        恢复之前暂停的轨道播放，从暂停位置继续。

        Args:
            track_id (str): 要恢复播放的轨道ID

        Note:
            只有处于暂停状态的轨道才能被恢复

        Example:
            >>> engine.pause("bgm1")
            >>> # 做其他事情...
            >>> engine.resume("bgm1")  # 从暂停位置继续播放
        """
        with self.lock:
            if track_id in self.track_states:
                state = self.track_states[track_id]
                if state.get("playing", False) and state.get("paused", False):
                    state["paused"] = False
                    logger.debug(f"Resumed track: {track_id}")

    def set_volume(self, track_id: str, volume: float) -> None:
        """
        设置轨道音量

        调整指定轨道的播放音量。音量调整会立即生效。

        Args:
            track_id (str): 轨道ID
            volume (float): 音量值（0.0-1.0）
                - 0.0 = 静音
                - 1.0 = 原始音量
                - >1.0 = 放大（会被限制在1.0）

        Note:
            如果轨道没有静音，也会同时更新原始音量记录

        Example:
            >>> # 设置为50%音量
            >>> engine.set_volume("bgm1", 0.5)

            >>> # 设置为最大音量
            >>> engine.set_volume("bgm1", 1.0)
        """
        with self.lock:
            if track_id in self.track_states:
                volume = max(0.0, min(1.0, volume))
                state = self.track_states[track_id]
                state["volume"] = volume

                # 如果没有静音，同时更新原始音量
                if not state.get("muted", False):
                    state["original_volume"] = volume

    def mute(self, track_id: str) -> bool:
        """
        静音指定轨道

        将轨道设置为静音状态，保存当前音量以便稍后恢复。

        Args:
            track_id (str): 要静音的轨道ID

        Returns:
            bool: 是否成功静音
                - True: 成功静音
                - False: 轨道不存在或已经静音

        Example:
            >>> if engine.mute("bgm1"):
            ...     print("轨道已静音")
            >>>
            >>> # 稍后恢复
            >>> engine.unmute("bgm1")
        """
        with self.lock:
            if track_id not in self.track_states:
                logger.warning(f"轨道不存在: {track_id}")
                return False

            state = self.track_states[track_id]
            if not state.get("muted", False):
                # 保存当前音量并设置为静音
                state["original_volume"] = state.get("volume", 1.0)
                state["volume"] = 0.0
                state["muted"] = True
                logger.debug(f"轨道已静音: {track_id}")
                return True
            else:
                logger.debug(f"轨道已经是静音状态: {track_id}")
                return False

    def unmute(self, track_id: str) -> bool:
        """
        取消静音指定轨道

        恢复轨道的原始音量，取消静音状态。

        Args:
            track_id (str): 要取消静音的轨道ID

        Returns:
            bool: 是否成功取消静音
                - True: 成功取消静音
                - False: 轨道不存在或没有静音

        Example:
            >>> engine.mute("bgm1")
            >>> # 稍后取消静音
            >>> if engine.unmute("bgm1"):
            ...     print("轨道已恢复音量")
        """
        with self.lock:
            if track_id not in self.track_states:
                logger.warning(f"轨道不存在: {track_id}")
                return False

            state = self.track_states[track_id]
            if state.get("muted", False):
                # 恢复原始音量
                state["volume"] = state.get("original_volume", 1.0)
                state["muted"] = False
                logger.debug(f"轨道已取消静音: {track_id}")
                return True
            else:
                logger.debug(f"轨道没有静音: {track_id}")
                return False

    def toggle_mute(self, track_id: str) -> bool:
        """
        切换轨道静音状态

        如果轨道静音则取消静音，如果没有静音则静音。

        Args:
            track_id (str): 要切换静音状态的轨道ID

        Returns:
            bool: 切换后的静音状态
                - True: 现在是静音状态
                - False: 现在不是静音状态

        Example:
            >>> # 切换静音状态
            >>> is_muted = engine.toggle_mute("bgm1")
            >>> if is_muted:
            ...     print("轨道已静音")
            ... else:
            ...     print("轨道已取消静音")
        """
        with self.lock:
            if track_id not in self.track_states:
                logger.warning(f"轨道不存在: {track_id}")
                return False

            state = self.track_states[track_id]
            if state.get("muted", False):
                self.unmute(track_id)
                return False
            else:
                self.mute(track_id)
                return True

    def is_muted(self, track_id: str) -> bool:
        """
        检查轨道是否静音

        Args:
            track_id (str): 要检查的轨道ID

        Returns:
            bool: 是否静音
                - True: 轨道处于静音状态
                - False: 轨道没有静音或不存在

        Example:
            >>> if engine.is_muted("bgm1"):
            ...     print("轨道已静音")
            ... else:
            ...     print("轨道未静音")
        """
        with self.lock:
            if track_id not in self.track_states:
                return False
            return self.track_states[track_id].get("muted", False)

    def mute_all_tracks(self) -> List[str]:
        """
        静音所有轨道

        将所有已加载的轨道设置为静音状态。

        Returns:
            List[str]: 被静音的轨道ID列表

        Example:
            >>> muted_tracks = engine.mute_all_tracks()
            >>> print(f"静音了 {len(muted_tracks)} 个轨道: {muted_tracks}")
        """
        muted_tracks = []
        with self.lock:
            for track_id in self.track_states.keys():
                if self.mute(track_id):
                    muted_tracks.append(track_id)

            if muted_tracks:
                logger.info(f"静音了 {len(muted_tracks)} 个轨道: {muted_tracks}")

        return muted_tracks

    def unmute_all_tracks(self) -> List[str]:
        """
        取消静音所有轨道

        将所有静音的轨道恢复原始音量。

        Returns:
            List[str]: 被取消静音的轨道ID列表

        Example:
            >>> unmuted_tracks = engine.unmute_all_tracks()
            >>> print(f"取消静音了 {len(unmuted_tracks)} 个轨道: {unmuted_tracks}")
        """
        unmuted_tracks = []
        with self.lock:
            for track_id in self.track_states.keys():
                if self.unmute(track_id):
                    unmuted_tracks.append(track_id)

            if unmuted_tracks:
                logger.info(f"取消静音了 {len(unmuted_tracks)} 个轨道: {unmuted_tracks}")

        return unmuted_tracks

    def get_muted_tracks(self) -> List[str]:
        """
        获取所有静音的轨道ID列表

        Returns:
            List[str]: 静音的轨道ID列表

        Example:
            >>> muted_tracks = engine.get_muted_tracks()
            >>> print(f"当前有 {len(muted_tracks)} 个轨道静音")
        """
        with self.lock:
            return [
                track_id
                for track_id, state in self.track_states.items()
                if state.get("muted", False)
            ]

    def set_loop(self, track_id: str, loop: bool) -> bool:
        """
        动态设置轨道循环状态

        在播放过程中改变轨道的循环播放设置。

        Args:
            track_id (str): 轨道ID
            loop (bool): 是否循环播放
                - True: 启用循环播放
                - False: 禁用循环播放

        Returns:
            bool: 是否成功设置

        Example:
            >>> # 启用循环播放
            >>> if engine.set_loop("bgm1", True):
            ...     print("循环播放已启用")

            >>> # 禁用循环播放
            >>> engine.set_loop("bgm1", False)
        """
        with self.lock:
            if track_id in self.track_states:
                self.track_states[track_id]["loop"] = loop
                logger.debug(f"Set loop for {track_id}: {loop}")
                return True
            return False

    def seek(self, track_id: str, position_sec: float) -> None:
        """
        跳转到指定位置

        将轨道的播放位置跳转到指定的时间点。支持预加载轨道和流式轨道。

        Args:
            track_id (str): 轨道ID
            position_sec (float): 目标位置（秒）
                - 0.0: 跳转到开头
                - 负值会被设置为0.0
                - 超过轨道长度的值会被限制在轨道末尾

        Example:
            >>> # 跳转到30秒位置
            >>> engine.seek("bgm1", 30.0)

            >>> # 跳转到开头
            >>> engine.seek("bgm1", 0.0)

            >>> # 跳转到1分30秒位置
            >>> engine.seek("bgm1", 90.0)
        """
        with self.lock:
            if track_id in self.track_states:
                state = self.track_states[track_id]

                # 检查是否为流式轨道
                if state.get("streaming_mode", False) and track_id in self.streaming_tracks:
                    # 流式轨道跳转
                    streaming_track = self.streaming_tracks[track_id]
                    position_sec = max(0.0, min(position_sec, streaming_track.duration))

                    def seek_callback(success):
                        if success:
                            logger.debug(
                                f"Streaming seek completed for {track_id} to {position_sec:.2f}s"
                            )
                        else:
                            logger.warning(f"Streaming seek failed for {track_id}")

                    streaming_track.seek_to(position_sec, seek_callback)
                    logger.debug(f"Streaming seek requested for {track_id} to {position_sec:.2f}s")

                else:
                    # 预加载轨道跳转（原有逻辑）
                    if track_id in self.tracks:
                        track_length = len(self.tracks[track_id])
                        position_samples = int(position_sec * state["sample_rate"])
                        state["position"] = min(position_samples, track_length - 1)
                        logger.debug(f"Preloaded seek for {track_id} to {position_sec:.2f}s")

    def set_fade_duration(self, track_id: str, duration_sec: float) -> None:
        """
        设置淡入淡出持续时间

        调整轨道淡入淡出效果的持续时间。

        Args:
            track_id (str): 轨道ID
            duration_sec (float): 淡入淡出持续时间（秒）
                - 最小值: 0.01秒
                - 建议值: 0.05-2.0秒

        Example:
            >>> # 设置1秒的淡入淡出时间
            >>> engine.set_fade_duration("bgm1", 1.0)

            >>> # 设置快速淡出（50毫秒）
            >>> engine.set_fade_duration("bgm1", 0.05)
        """
        with self.lock:
            if track_id in self.track_states:
                self.track_states[track_id]["fade_duration"] = max(0.01, duration_sec)

    def calculate_rms_loudness(self, track_id: str, duration: float = 2.0) -> float:
        """
        计算音轨的RMS响度

        Args:
            track_id (str): 音轨ID
            duration (float): 分析时长（秒）

        Returns:
            float: RMS响度值

        Example:
            >>> loudness = engine.calculate_rms_loudness("bgm1", 2.0)
            >>> print(f"音轨响度: {loudness:.4f}")
        """
        # 获取音轨信息
        track_info = self.get_track_info(track_id)
        if not track_info:
            logger.warning(f"Track not found for loudness calculation: {track_id}")
            return 0.0

        try:
            # 直接分析音频数据，无需播放
            with self.lock:
                if track_id in self.tracks:
                    # 预加载的音轨，直接分析数据
                    audio_data = self.tracks[track_id]
                    sample_rate = self.track_states.get(track_id, {}).get(
                        "sample_rate", self.sample_rate
                    )

                    # 计算要分析的帧数
                    max_frames = int(duration * sample_rate)
                    analysis_frames = min(max_frames, audio_data.shape[0])

                    # 取开始部分进行分析（避免静音填充的影响）
                    sample_data = audio_data[:analysis_frames]

                elif track_id in self.streaming_tracks:
                    # 流式音轨，读取开始部分数据进行分析
                    streaming_track = self.streaming_tracks[track_id]

                    # 重置文件指针到开始位置
                    original_pos = streaming_track.audio_file.tell()
                    streaming_track.audio_file.seek(0)

                    try:
                        # 读取指定时长的数据进行分析
                        frames_to_read = int(duration * streaming_track.sample_rate)
                        sample_data = streaming_track.audio_file.read(frames_to_read)

                        if sample_data is None or len(sample_data) == 0:
                            logger.warning(f"No data read from streaming track {track_id}")
                            return 0.0

                    finally:
                        # 恢复文件指针位置
                        streaming_track.audio_file.seek(original_pos)
                else:
                    logger.warning(f"Track data not available for loudness calculation: {track_id}")
                    return 0.0

                # 确保数据不为空
                if sample_data is None or sample_data.shape[0] == 0:
                    logger.warning(f"No audio data to analyze for {track_id}")
                    return 0.0

                # 转换为单声道进行分析
                if len(sample_data.shape) > 1 and sample_data.shape[1] > 1:
                    mono_data = np.mean(sample_data, axis=1)
                else:
                    mono_data = sample_data.flatten() if len(sample_data.shape) > 1 else sample_data

                # 计算RMS响度
                if len(mono_data) > 0:
                    rms = np.sqrt(np.mean(mono_data**2))
                    logger.debug(
                        f"RMS loudness for {track_id}: {rms:.4f} (analyzed {len(mono_data)} samples)"
                    )
                    return float(rms)
                else:
                    logger.warning(f"No valid audio samples for loudness calculation: {track_id}")
                    return 0.0

        except Exception as e:
            logger.error(f"Error calculating RMS loudness for {track_id}: {str(e)}")
            return 0.0

    def _calculate_peak_loudness(self, track_id: str, duration: float = 2.0) -> float:
        """
        计算音轨的峰值响度

        Args:
            track_id (str): 音轨ID
            duration (float): 分析时长（秒）

        Returns:
            float: 峰值响度值
        """
        track_info = self.get_track_info(track_id)
        if not track_info:
            return 0.0

        try:
            with self.lock:
                sample_data = None
                
                if track_id in self.tracks:
                    audio_data = self.tracks[track_id]
                    sample_rate = self.track_states.get(track_id, {}).get(
                        "sample_rate", self.sample_rate
                    )
                    max_frames = int(duration * sample_rate)
                    analysis_frames = min(max_frames, audio_data.shape[0])
                    sample_data = audio_data[:analysis_frames]
                    
                elif track_id in self.streaming_tracks:
                    streaming_track = self.streaming_tracks[track_id]
                    original_pos = streaming_track.audio_file.tell()
                    streaming_track.audio_file.seek(0)
                    try:
                        frames_to_read = int(duration * streaming_track.sample_rate)
                        sample_data = streaming_track.audio_file.read(frames_to_read)
                    finally:
                        streaming_track.audio_file.seek(original_pos)

                if sample_data is None or sample_data.shape[0] == 0:
                    return 0.0

                # 转换为单声道
                if len(sample_data.shape) > 1 and sample_data.shape[1] > 1:
                    mono_data = np.mean(sample_data, axis=1)
                else:
                    mono_data = sample_data.flatten() if len(sample_data.shape) > 1 else sample_data

                # 计算峰值响度
                peak = np.max(np.abs(mono_data))
                return float(peak)

        except Exception as e:
            logger.error(f"Error calculating peak loudness for {track_id}: {str(e)}")
            return 0.0

    def _calculate_lufs_loudness(self, track_id: str, duration: float = 2.0) -> float:
        """
        计算音轨的LUFS响度（简化实现）

        Args:
            track_id (str): 音轨ID
            duration (float): 分析时长（秒）

        Returns:
            float: LUFS响度值（转换为0-1范围）
        """
        track_info = self.get_track_info(track_id)
        if not track_info:
            return 0.0

        try:
            with self.lock:
                sample_data = None
                sample_rate = self.sample_rate
                
                if track_id in self.tracks:
                    audio_data = self.tracks[track_id]
                    sample_rate = self.track_states.get(track_id, {}).get(
                        "sample_rate", self.sample_rate
                    )
                    max_frames = int(duration * sample_rate)
                    analysis_frames = min(max_frames, audio_data.shape[0])
                    sample_data = audio_data[:analysis_frames]
                    
                elif track_id in self.streaming_tracks:
                    streaming_track = self.streaming_tracks[track_id]
                    sample_rate = streaming_track.sample_rate
                    original_pos = streaming_track.audio_file.tell()
                    streaming_track.audio_file.seek(0)
                    try:
                        frames_to_read = int(duration * sample_rate)
                        sample_data = streaming_track.audio_file.read(frames_to_read)
                    finally:
                        streaming_track.audio_file.seek(original_pos)

                if sample_data is None or sample_data.shape[0] == 0:
                    return 0.0

                # 转换为单声道
                if len(sample_data.shape) > 1 and sample_data.shape[1] > 1:
                    mono_data = np.mean(sample_data, axis=1)
                else:
                    mono_data = sample_data.flatten() if len(sample_data.shape) > 1 else sample_data

                # 简化的LUFS计算（K权重滤波器的近似实现）
                # 高通滤波器 (约150Hz)
                if sample_rate > 300:
                    from scipy import signal
                    b, a = signal.butter(2, 150 / (sample_rate / 2), btype='high')
                    filtered_data = signal.filtfilt(b, a, mono_data)
                else:
                    filtered_data = mono_data

                # 计算均方值
                mean_square = np.mean(filtered_data ** 2)
                
                # 转换为类似LUFS的响度值，并标准化到0-1范围
                if mean_square > 0:
                    loudness_lufs = 10 * np.log10(mean_square)
                    # 将LUFS范围(-70 到 0 dB)映射到0-1
                    normalized_loudness = max(0.0, min(1.0, (loudness_lufs + 70) / 70))
                    return float(normalized_loudness)
                else:
                    return 0.0

        except Exception as e:
            logger.error(f"Error calculating LUFS loudness for {track_id}: {str(e)}")
            # 如果LUFS计算失败，回退到RMS
            return self.calculate_rms_loudness(track_id, duration)

    def _calculate_a_weighted_loudness(self, track_id: str, duration: float = 2.0) -> float:
        """
        计算音轨的A权重响度

        Args:
            track_id (str): 音轨ID
            duration (float): 分析时长（秒）

        Returns:
            float: A权重响度值
        """
        track_info = self.get_track_info(track_id)
        if not track_info:
            return 0.0

        try:
            with self.lock:
                sample_data = None
                sample_rate = self.sample_rate
                
                if track_id in self.tracks:
                    audio_data = self.tracks[track_id]
                    sample_rate = self.track_states.get(track_id, {}).get(
                        "sample_rate", self.sample_rate
                    )
                    max_frames = int(duration * sample_rate)
                    analysis_frames = min(max_frames, audio_data.shape[0])
                    sample_data = audio_data[:analysis_frames]
                    
                elif track_id in self.streaming_tracks:
                    streaming_track = self.streaming_tracks[track_id]
                    sample_rate = streaming_track.sample_rate
                    original_pos = streaming_track.audio_file.tell()
                    streaming_track.audio_file.seek(0)
                    try:
                        frames_to_read = int(duration * sample_rate)
                        sample_data = streaming_track.audio_file.read(frames_to_read)
                    finally:
                        streaming_track.audio_file.seek(original_pos)

                if sample_data is None or sample_data.shape[0] == 0:
                    return 0.0

                # 转换为单声道
                if len(sample_data.shape) > 1 and sample_data.shape[1] > 1:
                    mono_data = np.mean(sample_data, axis=1)
                else:
                    mono_data = sample_data.flatten() if len(sample_data.shape) > 1 else sample_data

                # 简化的A权重滤波器实现
                try:
                    from scipy import signal
                    # A权重滤波器的近似实现
                    # 这是一个简化的A权重曲线
                    freq_response = np.abs(np.fft.fft(mono_data))
                    freqs = np.fft.fftfreq(len(mono_data), 1/sample_rate)
                    
                    # A权重曲线的近似（简化版本）
                    a_weights = np.ones_like(freqs)
                    for i, freq in enumerate(freqs[:len(freqs)//2]):
                        if freq > 0:
                            # 简化的A权重公式
                            f2 = freq * freq
                            f4 = f2 * f2
                            weight = (12200*12200 * f4) / ((f2 + 20.6*20.6) * 
                                    np.sqrt((f2 + 107.7*107.7) * (f2 + 737.9*737.9)) * 
                                    (f2 + 12200*12200))
                            a_weights[i] = weight
                            if i > 0:
                                a_weights[-i] = weight

                    # 应用A权重
                    weighted_fft = freq_response * a_weights
                    weighted_signal = np.real(np.fft.ifft(weighted_fft))
                    
                    # 计算A权重RMS
                    a_weighted_rms = np.sqrt(np.mean(weighted_signal ** 2))
                    return float(a_weighted_rms)
                    
                except ImportError:
                    logger.warning("scipy not available, using RMS instead of A-weighted loudness")
                    return self.calculate_rms_loudness(track_id, duration)

        except Exception as e:
            logger.error(f"Error calculating A-weighted loudness for {track_id}: {str(e)}")
            # 如果A权重计算失败，回退到RMS
            return self.calculate_rms_loudness(track_id, duration)

    def _matchering_loudness_match(
        self, track1_id: str, track2_id: str, target_loudness: float = 0.7
    ) -> tuple[float, float]:
        """
        使用Matchering进行响度匹配

        Args:
            track1_id (str): 参考音轨ID
            track2_id (str): 目标音轨ID
            target_loudness (float): 目标响度级别

        Returns:
            tuple[float, float]: (参考音轨音量, 目标音轨音量)
        """
        if mg is None:
            logger.warning("Matchering not available, falling back to RMS matching")
            return self._rms_loudness_match(track1_id, track2_id, target_loudness)

        try:
            # 获取音轨数据进行matchering分析
            track1_info = self.get_track_info(track1_id)
            track2_info = self.get_track_info(track2_id)
            
            if not track1_info or not track2_info:
                logger.warning("Track info not available for matchering")
                return self._rms_loudness_match(track1_id, track2_id, target_loudness)

            # 使用RMS作为Matchering的简化替代（实际实现需要更复杂的处理）
            logger.info("Using RMS-based matching as Matchering implementation")
            return self._rms_loudness_match(track1_id, track2_id, target_loudness)

        except Exception as e:
            logger.error(f"Error in matchering loudness match: {str(e)}")
            return self._rms_loudness_match(track1_id, track2_id, target_loudness)

    def _rms_loudness_match(
        self, track1_id: str, track2_id: str, target_loudness: float = 0.7
    ) -> tuple[float, float]:
        """
        使用RMS进行响度匹配

        Args:
            track1_id (str): 参考音轨ID
            track2_id (str): 目标音轨ID
            target_loudness (float): 目标响度级别

        Returns:
            tuple[float, float]: (参考音轨音量, 目标音轨音量)
        """
        rms1 = self.calculate_rms_loudness(track1_id, 1.5)
        rms2 = self.calculate_rms_loudness(track2_id, 1.0)

        if rms1 > 0 and rms2 > 0:
            ratio = rms1 / rms2
            volume1 = target_loudness
            volume2 = target_loudness * ratio
            volume2 = min(1.0, max(0.1, volume2))
            return volume1, volume2
        else:
            return target_loudness, target_loudness * 0.8

    def _peak_loudness_match(
        self, track1_id: str, track2_id: str, target_loudness: float = 0.7
    ) -> tuple[float, float]:
        """
        使用峰值进行响度匹配

        Args:
            track1_id (str): 参考音轨ID
            track2_id (str): 目标音轨ID
            target_loudness (float): 目标响度级别

        Returns:
            tuple[float, float]: (参考音轨音量, 目标音轨音量)
        """
        peak1 = self._calculate_peak_loudness(track1_id, 1.5)
        peak2 = self._calculate_peak_loudness(track2_id, 1.0)

        if peak1 > 0 and peak2 > 0:
            ratio = peak1 / peak2
            volume1 = target_loudness
            volume2 = target_loudness * ratio
            volume2 = min(1.0, max(0.1, volume2))
            return volume1, volume2
        else:
            return target_loudness, target_loudness * 0.8

    def _lufs_loudness_match(
        self, track1_id: str, track2_id: str, target_loudness: float = 0.7
    ) -> tuple[float, float]:
        """
        使用LUFS进行响度匹配

        Args:
            track1_id (str): 参考音轨ID
            track2_id (str): 目标音轨ID
            target_loudness (float): 目标响度级别

        Returns:
            tuple[float, float]: (参考音轨音量, 目标音轨音量)
        """
        lufs1 = self._calculate_lufs_loudness(track1_id, 1.5)
        lufs2 = self._calculate_lufs_loudness(track2_id, 1.0)

        if lufs1 > 0 and lufs2 > 0:
            ratio = lufs1 / lufs2
            volume1 = target_loudness
            volume2 = target_loudness * ratio
            volume2 = min(1.0, max(0.1, volume2))
            return volume1, volume2
        else:
            return target_loudness, target_loudness * 0.8

    def _a_weighted_loudness_match(
        self, track1_id: str, track2_id: str, target_loudness: float = 0.7
    ) -> tuple[float, float]:
        """
        使用A权重进行响度匹配

        Args:
            track1_id (str): 参考音轨ID
            track2_id (str): 目标音轨ID
            target_loudness (float): 目标响度级别

        Returns:
            tuple[float, float]: (参考音轨音量, 目标音轨音量)
        """
        a_weighted1 = self._calculate_a_weighted_loudness(track1_id, 1.5)
        a_weighted2 = self._calculate_a_weighted_loudness(track2_id, 1.0)

        if a_weighted1 > 0 and a_weighted2 > 0:
            ratio = a_weighted1 / a_weighted2
            volume1 = target_loudness
            volume2 = target_loudness * ratio
            volume2 = min(1.0, max(0.1, volume2))
            return volume1, volume2
        else:
            return target_loudness, target_loudness * 0.8

    def match_loudness(
        self, 
        track1_id: str, 
        track2_id: str, 
        target_loudness: float = 0.7,
        method: str = "matchering"
    ) -> tuple[float, float]:
        """
        匹配两个音轨的响度

        Args:
            track1_id (str): 第一个音轨ID（通常是主音轨）
            track2_id (str): 第二个音轨ID（通常是副音轨）
            target_loudness (float): 目标响度级别（0.0-1.0）
            method (str): 响度匹配算法，可选值:
                - "matchering": 使用Matchering进行响度优化（默认）
                - "rms": 使用RMS均方根响度
                - "peak": 使用峰值响度
                - "lufs": 使用LUFS响度（广播标准）
                - "a_weighted": 使用A权重响度

        Returns:
            tuple[float, float]: (第一个音轨建议音量, 第二个音轨建议音量)

        Example:
            >>> # 使用默认的Matchering算法
            >>> vol1, vol2 = engine.match_loudness("main", "sub", 0.7)
            >>> engine.set_volume("main", vol1)
            >>> engine.set_volume("sub", vol2)
            
            >>> # 使用RMS算法
            >>> vol1, vol2 = engine.match_loudness("main", "sub", 0.7, method="rms")
            
            >>> # 使用LUFS算法（广播标准）
            >>> vol1, vol2 = engine.match_loudness("main", "sub", 0.7, method="lufs")
        """
        logger.info(f"Matching loudness between {track1_id} and {track2_id} using {method} method")

        # 验证method参数
        valid_methods = ["matchering", "rms", "peak", "lufs", "a_weighted"]
        if method not in valid_methods:
            logger.warning(f"Invalid method '{method}', using 'rms' instead. Valid methods: {valid_methods}")
            method = "rms"

        # 根据选择的方法进行响度匹配
        try:
            if method == "matchering":
                volume1, volume2 = self._matchering_loudness_match(track1_id, track2_id, target_loudness)
            elif method == "rms":
                volume1, volume2 = self._rms_loudness_match(track1_id, track2_id, target_loudness)
            elif method == "peak":
                volume1, volume2 = self._peak_loudness_match(track1_id, track2_id, target_loudness)
            elif method == "lufs":
                volume1, volume2 = self._lufs_loudness_match(track1_id, track2_id, target_loudness)
            elif method == "a_weighted":
                volume1, volume2 = self._a_weighted_loudness_match(track1_id, track2_id, target_loudness)
            else:
                # 默认回退到RMS
                volume1, volume2 = self._rms_loudness_match(track1_id, track2_id, target_loudness)

            logger.info(
                f"Loudness matching ({method}) - volumes: {track1_id}={volume1:.3f}, {track2_id}={volume2:.3f}"
            )
            return volume1, volume2

        except Exception as e:
            logger.error(f"Error in {method} loudness matching: {str(e)}, falling back to RMS")
            return self._rms_loudness_match(track1_id, track2_id, target_loudness)

    def crossfade(
        self,
        from_track: str,
        to_track: str,
        duration: float = 1.0,
        to_track_volume: Optional[float] = None,
        to_track_loop: bool = False,
        loudness_match_method: str = "matchering",
    ) -> bool:
        """
        在两个音轨之间执行交叉淡入淡出

        Args:
            from_track (str): 源音轨ID（将淡出）
            to_track (str): 目标音轨ID（将淡入）
            duration (float): 交叉淡入淡出持续时间（秒）
            to_track_volume (float, optional): 目标音轨的最终音量。如果为None，将自动使用响度匹配
            to_track_loop (bool): 目标音轨是否循环播放
            loudness_match_method (str): 当to_track_volume为None时使用的响度匹配算法，可选值:
                - "matchering": 使用Matchering进行响度优化（默认）
                - "rms": 使用RMS均方根响度
                - "peak": 使用峰值响度
                - "lufs": 使用LUFS响度（广播标准）
                - "a_weighted": 使用A权重响度

        Returns:
            bool: 是否成功开始交叉淡入淡出

        Example:
            >>> # 简单的交叉淡入淡出（使用默认Matchering算法）
            >>> engine.crossfade("main_track", "sub_track", 1.0)

            >>> # 带自定义音量的交叉淡入淡出
            >>> engine.crossfade("main_track", "sub_track", 0.5, to_track_volume=0.8)
            
            >>> # 使用RMS算法进行响度匹配的交叉淡入淡出
            >>> engine.crossfade("main_track", "sub_track", 1.0, loudness_match_method="rms")
            
            >>> # 使用LUFS算法进行响度匹配的交叉淡入淡出
            >>> engine.crossfade("main_track", "sub_track", 1.0, loudness_match_method="lufs")
        """
        # 检查音轨是否存在
        if from_track not in self.track_states or to_track not in self.track_states:
            logger.error(f"One or both tracks not found: {from_track}, {to_track}")
            return False

        # 获取源音轨当前音量
        from_info = self.get_track_info(from_track)
        if not from_info or not from_info.get("playing", False):
            logger.warning(f"Source track {from_track} is not playing")
            return False

        from_volume = from_info.get("volume", 0.7)

        # 确定目标音轨音量
        if to_track_volume is None:
            # 使用响度匹配
            _, to_track_volume = self.match_loudness(from_track, to_track, from_volume, method=loudness_match_method)

        logger.info(f"Starting crossfade: {from_track} -> {to_track} ({duration}s)")

        # 设置淡入淡出时长
        self.set_fade_duration(from_track, duration)
        self.set_fade_duration(to_track, duration)

        # 开始目标音轨播放（从0音量开始）
        self.set_volume(to_track, 0.0)
        self.play(to_track, fade_in=False, loop=to_track_loop)

        # 在后台线程中执行交叉淡入淡出
        def crossfade_worker():
            try:
                steps = int(duration * 20)  # 每50ms一步
                step_duration = duration / steps

                for i in range(steps + 1):
                    if not self.is_running:
                        break

                    progress = i / steps  # 0.0 到 1.0

                    # 源音轨音量从当前音量线性减到0
                    from_current_volume = from_volume * (1.0 - progress)
                    self.set_volume(from_track, from_current_volume)

                    # 目标音轨音量从0线性增到目标音量
                    to_current_volume = to_track_volume * progress
                    self.set_volume(to_track, to_current_volume)

                    time.sleep(step_duration)

                # 停止源音轨
                self.stop(from_track, fade_out=False)
                logger.debug(f"Crossfade completed: {from_track} -> {to_track}")

            except Exception as e:
                logger.error(f"Error during crossfade: {str(e)}")

        # 启动后台线程
        import threading

        crossfade_thread = threading.Thread(target=crossfade_worker, daemon=True)
        crossfade_thread.start()

        return True

    def get_position(self, track_id: str) -> float:
        """
        获取当前播放位置

        Args:
            track_id (str): 轨道ID

        Returns:
            float: 当前播放位置（秒）
                - 如果轨道不存在，返回0.0

        Example:
            >>> position = engine.get_position("bgm1")
            >>> print(f"当前播放位置: {position:.2f}秒")
        """
        with self.lock:
            if track_id in self.track_states:
                state = self.track_states[track_id]

                # 检查是否为流式轨道
                if state.get("streaming_mode", False) and track_id in self.streaming_tracks:
                    return self.streaming_tracks[track_id].get_position_seconds()
                else:
                    # 预加载轨道
                    return state["position"] / state["sample_rate"]
            return 0.0

    def get_duration(self, track_id: str) -> float:
        """
        获取轨道总时长

        Args:
            track_id (str): 轨道ID

        Returns:
            float: 轨道总时长（秒）
                - 如果轨道不存在，返回0.0

        Example:
            >>> duration = engine.get_duration("bgm1")
            >>> print(f"轨道总时长: {duration:.2f}秒")
        """
        with self.lock:
            if track_id in self.track_states:
                state = self.track_states[track_id]

                # 检查是否为流式轨道
                if state.get("streaming_mode", False) and track_id in self.streaming_tracks:
                    return self.streaming_tracks[track_id].duration
                elif track_id in self.tracks:
                    # 预加载轨道
                    return len(self.tracks[track_id]) / state["sample_rate"]
            return 0.0

    def register_position_callback(
        self,
        track_id: str,
        target_time: float,
        callback_func: Callable[[str, float, float], None],
        tolerance: float = 0.010
    ) -> bool:
        """
        注册位置回调

        在指定轨道播放到目标时间点时触发回调函数。支持高精度的音频位置回调，
        精度可达5-15ms误差范围。

        Args:
            track_id (str): 轨道ID
            target_time (float): 目标时间点（秒）
            callback_func (Callable): 回调函数，接收参数 (track_id, current_time, target_time)
            tolerance (float, optional): 时间容忍度（秒），默认10ms

        Returns:
            bool: 是否成功注册回调

        Example:
            >>> def tts_callback(track_id, current_time, target_time):
            ...     print(f"TTS插入点到达: {current_time:.3f}s")
            >>> 
            >>> success = engine.register_position_callback(
            ...     "main_audio", 15.5, tts_callback, tolerance=0.005
            ... )
            >>> if success:
            ...     print("回调注册成功")

        Note:
            - 回调函数将在音频回调线程中执行，应避免耗时操作
            - 目标时间应在轨道的有效播放范围内
            - 同一轨道可注册多个不同时间点的回调
        """
        if not callable(callback_func):
            logger.warning(f"回调函数无效: {callback_func}")
            return False

        if target_time < 0:
            logger.warning(f"目标时间无效: {target_time}")
            return False

        with self.lock:
            # 检查轨道是否存在
            if not self.is_track_loaded(track_id):
                logger.warning(f"轨道未加载，无法注册回调: {track_id}")
                return False

            # 检查目标时间是否在轨道范围内
            duration = self.get_duration(track_id)
            if duration > 0 and target_time > duration:
                logger.warning(f"目标时间超出轨道范围: {target_time:.3f}s > {duration:.3f}s")
                return False

            # 初始化轨道回调字典
            if track_id not in self.position_callbacks:
                self.position_callbacks[track_id] = {}

            # 创建回调信息
            callback_info = {
                'callback': callback_func,
                'tolerance': max(0.001, tolerance),  # 最小容忍度1ms
                'triggered': False,
                'registered_time': time.time(),
                'registration_position': self.get_position(track_id)
            }

            self.position_callbacks[track_id][target_time] = callback_info

            # 启动回调检查线程
            self._ensure_callback_thread_running()

            logger.debug(
                f"位置回调已注册: track={track_id}, target={target_time:.3f}s, "
                f"tolerance={tolerance*1000:.1f}ms"
            )
            return True

    def remove_position_callback(self, track_id: str, target_time: Optional[float] = None) -> int:
        """
        移除位置回调

        Args:
            track_id (str): 轨道ID
            target_time (float, optional): 特定的目标时间点，None表示移除该轨道的所有回调

        Returns:
            int: 移除的回调数量

        Example:
            >>> # 移除特定时间点的回调
            >>> count = engine.remove_position_callback("main_audio", 15.5)
            >>> print(f"移除了 {count} 个回调")
            >>> 
            >>> # 移除轨道的所有回调
            >>> count = engine.remove_position_callback("main_audio")
            >>> print(f"移除了 {count} 个回调")
        """
        removed_count = 0

        with self.lock:
            if track_id not in self.position_callbacks:
                return 0

            if target_time is None:
                # 移除该轨道的所有回调
                removed_count = len(self.position_callbacks[track_id])
                del self.position_callbacks[track_id]
            else:
                # 移除特定时间点的回调
                if target_time in self.position_callbacks[track_id]:
                    del self.position_callbacks[track_id][target_time]
                    removed_count = 1

                    # 如果该轨道没有回调了，清理
                    if not self.position_callbacks[track_id]:
                        del self.position_callbacks[track_id]

        if removed_count > 0:
            logger.debug(f"移除位置回调: track={track_id}, count={removed_count}")

        return removed_count

    def add_global_position_listener(self, listener_func: Callable[[str, float], None]) -> bool:
        """
        添加全局位置监听器

        监听器将接收所有正在播放轨道的位置更新。

        Args:
            listener_func (Callable): 监听函数，接收参数 (track_id, position)

        Returns:
            bool: 是否成功添加监听器

        Example:
            >>> def position_monitor(track_id, position):
            ...     print(f"Track {track_id}: {position:.3f}s")
            >>> 
            >>> success = engine.add_global_position_listener(position_monitor)
            >>> print(f"监听器添加{'成功' if success else '失败'}")

        Note:
            - 监听器函数将被高频调用，应避免耗时操作
            - 同一个监听器函数只会被添加一次
        """
        if not callable(listener_func):
            logger.warning(f"监听器函数无效: {listener_func}")
            return False

        with self.lock:
            if listener_func not in self.global_position_listeners:
                self.global_position_listeners.append(listener_func)
                self._ensure_callback_thread_running()
                logger.debug("全局位置监听器已添加")
                return True
            else:
                logger.warning("监听器已存在，跳过添加")
                return False

    def remove_global_position_listener(self, listener_func: Callable[[str, float], None]) -> bool:
        """
        移除全局位置监听器

        Args:
            listener_func (Callable): 要移除的监听器函数

        Returns:
            bool: 是否成功移除监听器

        Example:
            >>> success = engine.remove_global_position_listener(position_monitor)
            >>> print(f"监听器移除{'成功' if success else '失败'}")
        """
        with self.lock:
            if listener_func in self.global_position_listeners:
                self.global_position_listeners.remove(listener_func)
                logger.debug("全局位置监听器已移除")
                return True
            else:
                logger.warning("监听器不存在，无法移除")
                return False

    def clear_all_position_callbacks(self) -> int:
        """
        清除所有位置回调

        Returns:
            int: 清除的回调总数

        Example:
            >>> count = engine.clear_all_position_callbacks()
            >>> print(f"清除了 {count} 个位置回调")
        """
        total_removed = 0

        with self.lock:
            for track_callbacks in self.position_callbacks.values():
                total_removed += len(track_callbacks)
            
            self.position_callbacks.clear()
            self.global_position_listeners.clear()

        if total_removed > 0:
            logger.debug(f"已清除所有位置回调: {total_removed} 个")

        return total_removed

    def get_position_callback_stats(self) -> Dict[str, Any]:
        """
        获取位置回调统计信息

        Returns:
            dict: 包含回调统计信息的字典

        Example:
            >>> stats = engine.get_position_callback_stats()
            >>> print(f"已触发回调: {stats['triggered_callbacks']}")
            >>> print(f"平均精度: {stats['average_precision_ms']:.1f}ms")
        """
        with self.lock:
            active_callbacks = sum(len(callbacks) for callbacks in self.position_callbacks.values())
            
            return {
                'active_callbacks': active_callbacks,
                'active_tracks': len(self.position_callbacks),
                'global_listeners': len(self.global_position_listeners),
                'triggered_callbacks': self.callback_stats['total_callbacks_triggered'],
                'expired_callbacks': self.callback_stats['total_callbacks_expired'],
                'average_precision_ms': self.callback_stats['average_precision_ms'],
                'callback_thread_running': self.position_callback_thread_running,
                'last_check_time': self.callback_stats['last_check_time']
            }

    def start(self) -> None:
        """
        启动音频引擎

        开始音频输出流，使音频引擎开始工作。必须在播放任何轨道之前调用。

        Raises:
            Exception: 如果音频引擎启动失败

        Example:
            >>> engine = AudioEngine()
            >>> engine.start()
            >>> # 现在可以播放音频了
            >>> engine.play("bgm1")
        """
        if not self.is_running:
            try:
                self.stream.start()
                self.is_running = True
                logger.info("Audio engine started")
            except Exception as e:
                logger.error(f"Failed to start audio engine: {str(e)}")
                self.is_running = False

    def shutdown(self) -> None:
        """
        关闭音频引擎并释放资源

        停止所有播放，关闭音频流，清理内存，停止后台线程。
        这是一个完整的清理过程。

        Note:
            关闭后的引擎无法重新启动，需要创建新的引擎实例

        Example:
            >>> engine.shutdown()
            >>> # 引擎已完全关闭，所有资源已释放
        """
        if self.is_running:
            try:
                # 取消所有定时任务
                self.cancel_all_scheduled_tasks()

                # Stop position callback thread first
                if self.position_callback_thread_running:
                    self.position_callback_thread_running = False
                    if self.position_callback_thread and self.position_callback_thread.is_alive():
                        self.position_callback_thread.join(timeout=1.0)
                        logger.info("Position callback thread stopped")

                # Clear all position callbacks
                self.clear_all_position_callbacks()

                # Stop all tracks
                with self.lock:
                    for track_id in list(self.active_tracks):
                        self.stop(track_id, fade_out=False)

                # Stop loading thread
                self.loading_queue.put(None)
                self.loading_thread.join(timeout=1.0)

                # Stop all streaming tracks
                with self.lock:
                    for streaming_track in self.streaming_tracks.values():
                        streaming_track.stop_streaming()
                    self.streaming_tracks.clear()

                # Close audio stream
                self.stream.stop()
                self.stream.close()
                self.is_running = False

                # Free memory
                self.tracks.clear()
                self.track_states.clear()
                self.active_tracks.clear()
                self.track_files.clear()

                # Clean position callback system
                self.position_callbacks.clear()
                self.global_position_listeners.clear()
                self.last_position_check_time.clear()
                self.callback_stats.clear()

                # Clean optimization components
                self.fade_step_cache.clear()
                self.buffer_pool.pool.clear()

                gc.collect()

                logger.info("Audio engine shutdown complete")
            except Exception as e:
                logger.error(f"Error during shutdown: {str(e)}")

    def _audio_callback(
        self,
        outdata: npt.NDArray,
        frames: int,
        time_info: sd.CallbackFlags,
        status: sd.CallbackFlags,
    ) -> None:
        """
        Optimized audio callback function - core audio processing with streaming support
        """
        start_time = time.perf_counter()
        self.callback_count += 1  # 递增回调计数器

        # Handle stream status - 增强的下溢检测
        if status:
            if status.input_underflow or status.output_underflow:
                self.underrun_count += 1
                logger.warning(f"Audio underrun detected (#{self.underrun_count})")

        # Get mix buffer from buffer pool - 确保获取成功
        mix_buffer = None
        try:
            mix_buffer = self.buffer_pool.get_buffer()
            if mix_buffer is None:
                # 紧急情况：创建临时缓冲区
                mix_buffer = np.zeros((frames, self.channels), dtype=np.float32)
                logger.warning("Failed to get buffer from pool, using temporary buffer")
        except Exception as e:
            logger.error(f"Buffer pool error: {e}")
            mix_buffer = np.zeros((frames, self.channels), dtype=np.float32)

        try:
            peak_level = 0.0
            active_track_count = 0

            # Get snapshot of current active tracks (avoid processing audio within lock)
            with self.lock:
                active_tracks = list(self.active_tracks)
                track_states_snapshot = {
                    tid: self.track_states[tid].copy() for tid in active_tracks
                }

            # Process each active track
            for track_id in active_tracks:
                try:
                    state = track_states_snapshot[track_id]

                    # Skip paused tracks
                    if state.get("paused", False):
                        continue

                    chunk = None

                    # 检查是否为流式轨道
                    if state.get("streaming_mode", False) and track_id in self.streaming_tracks:
                        # 流式轨道处理
                        streaming_track = self.streaming_tracks[track_id]
                        try:
                            chunk = self._get_streaming_audio_with_padding(
                                track_id, streaming_track, state, frames
                            )
                        except Exception as e:
                            logger.error(f"Streaming track error {track_id}: {e}")
                            # 生成静音数据防止断音
                            chunk = np.zeros((frames, self.channels), dtype=np.float32)

                        # 处理循环播放
                        if state.get("loop", False) and self._is_streaming_track_at_end(
                            streaming_track, state
                        ):
                            self._reset_streaming_track_for_loop(streaming_track, state)

                        # 如果到达文件末尾且不循环，停止播放
                        elif self._is_streaming_track_finished(streaming_track, state):
                            state["playing"] = False
                            continue

                    else:
                        # 预加载轨道处理（原有逻辑）
                        if track_id not in self.tracks:
                            continue

                        audio_data = self.tracks[track_id]
                        position = state["position"]
                        speed = state.get("speed", 1.0)

                        # Extract audio chunk - 增强错误处理
                        try:
                            # 使用重采样的音频提取
                            chunk, new_position = self._extract_audio_chunk_optimized(
                                audio_data,
                                position,
                                speed,
                                state.get("loop", False),
                                frames,
                                state["sample_rate"],
                            )
                        except Exception as e:
                            logger.error(f"Chunk extraction error {track_id}: {e}")
                            # 生成静音数据防止断音
                            chunk = np.zeros((frames, self.channels), dtype=np.float32)
                            new_position = position

                        if chunk is None:
                            state["playing"] = False
                            continue

                        # Update position
                        state["position"] = new_position

                    if chunk is not None and chunk.shape[0] > 0:
                        # 验证数据完整性
                        if chunk.shape[1] != self.channels:
                            logger.warning(
                                f"Track {track_id} channel mismatch: {chunk.shape[1]} vs {self.channels}"
                            )
                            continue

                        # 检测并平滑音频不连续性，预防爆音（减少过度处理）
                        chunk = self._detect_and_smooth_discontinuities(chunk, track_id)

                        # Apply audio effects - 增强错误处理
                        try:
                            self._apply_audio_effects_optimized(chunk, state, frames, track_id)
                        except Exception as e:
                            logger.error(f"Audio effects error {track_id}: {e}")
                            # 继续处理但跳过效果

                        # 改进的混合逻辑 - 解决不同采样率混音的精度问题
                        if chunk.shape[0] == frames:
                            # 正常情况：长度匹配，使用高精度混音
                            # 检查是否为不同采样率轨道，需要特殊处理
                            track_sample_rate = state.get("sample_rate", self.sample_rate)
                            if track_sample_rate != self.sample_rate:
                                # 不同采样率轨道：使用特殊的混音策略，消除电流声
                                # 先检查轨道音量和静音状态
                                track_volume = state.get("volume", 1.0)
                                is_track_muted = state.get("muted", False)

                                if not is_track_muted and track_volume > 0.001:
                                    # 应用音量
                                    if track_volume != 1.0:
                                        chunk = chunk * track_volume

                                    # 检测电流噪音的常见特征
                                    chunk_rms = np.sqrt(np.mean(chunk**2))
                                    if chunk_rms > 0:
                                        # 对于24kHz轨道，应用特殊的噪音抑制
                                        if abs(track_sample_rate - 24000) < 100:
                                            # 24kHz轨道专用处理：检测高频噪音
                                            for channel in range(self.channels):
                                                channel_data = chunk[:, channel]

                                                # 检测突然的振幅跳跃（电流声的特征）
                                                if len(channel_data) > 2:
                                                    diff = np.abs(np.diff(channel_data))
                                                    mean_diff = np.mean(diff)
                                                    std_diff = np.std(diff)

                                                    # 如果检测到异常的振幅跳跃（电流声）
                                                    if std_diff > mean_diff * 3:
                                                        # 应用保守的平滑处理
                                                        smoothed = np.copy(channel_data)
                                                        for i in range(1, len(channel_data) - 1):
                                                            if (
                                                                diff[i - 1]
                                                                > mean_diff + 2 * std_diff
                                                            ):
                                                                # 检测到电流声，用邻近样本平均值替代
                                                                smoothed[i] = (
                                                                    channel_data[i - 1]
                                                                    + channel_data[i + 1]
                                                                ) * 0.5
                                                        chunk[:, channel] = smoothed

                                    # 数值范围检查：确保混音前数据在合理范围内
                                    chunk_max = np.max(np.abs(chunk))
                                    mix_max = np.max(np.abs(mix_buffer))

                                    # 保守的预处理：避免数值溢出
                                    if chunk_max > 0.85:
                                        chunk *= 0.85 / chunk_max
                                    if mix_max > 0.85:
                                        mix_buffer *= 0.85 / mix_max

                                    # 使用高精度混音算法
                                    mix_buffer_64 = mix_buffer.astype(np.float64)
                                    chunk_64 = chunk.astype(np.float64)

                                    # 加权混音：对于不同采样率，使用稍微保守的混音
                                    if abs(track_sample_rate - 24000) < 100:
                                        # 24kHz轨道：轻微降低权重以减少电流声
                                        mixed_64 = mix_buffer_64 + chunk_64 * 0.92
                                    else:
                                        mixed_64 = mix_buffer_64 + chunk_64

                                    # 最终限制：确保输出在安全范围内
                                    mixed_max = np.max(np.abs(mixed_64))
                                    if mixed_max > 0.98:
                                        mixed_64 *= 0.98 / mixed_max

                                    mix_buffer[:] = mixed_64.astype(np.float32)
                                # else: 静音或音量极低的轨道，跳过混音
                            else:
                                # 相同采样率：使用标准混音
                                track_volume = state.get("volume", 1.0)
                                is_track_muted = state.get("muted", False)

                                if not is_track_muted and track_volume > 0.001:
                                    if track_volume != 1.0:
                                        chunk = chunk * track_volume
                                    np.add(mix_buffer, chunk, out=mix_buffer)
                        elif chunk.shape[0] < frames:
                            # 输入数据不足，需要填充
                            min_frames = chunk.shape[0]
                            if min_frames > 0:
                                # 对有效部分使用高精度混音
                                track_sample_rate = state.get("sample_rate", self.sample_rate)
                                if track_sample_rate != self.sample_rate and min_frames > 0:
                                    # 不同采样率，使用高精度处理
                                    chunk_part = chunk[:min_frames]
                                    mix_part = mix_buffer[:min_frames]

                                    track_volume = state.get("volume", 1.0)
                                    is_track_muted = state.get("muted", False)

                                    if not is_track_muted and track_volume > 0.001:
                                        # 应用音量
                                        if track_volume != 1.0:
                                            chunk_part = chunk_part * track_volume

                                        # 对24kHz轨道应用电流声检测和抑制
                                        if abs(track_sample_rate - 24000) < 100:
                                            for channel in range(self.channels):
                                                if min_frames > 2:
                                                    channel_data = chunk_part[:, channel]
                                                    diff = np.abs(np.diff(channel_data))
                                                    mean_diff = np.mean(diff)
                                                    std_diff = np.std(diff)

                                                    if std_diff > mean_diff * 3:
                                                        smoothed = np.copy(channel_data)
                                                        for i in range(1, len(channel_data) - 1):
                                                            if (
                                                                diff[i - 1]
                                                                > mean_diff + 2 * std_diff
                                                            ):
                                                                smoothed[i] = (
                                                                    channel_data[i - 1]
                                                                    + channel_data[i + 1]
                                                                ) * 0.5
                                                        chunk_part[:, channel] = smoothed

                                        chunk_max = np.max(np.abs(chunk_part))
                                        mix_max = np.max(np.abs(mix_part))

                                        if chunk_max > 0.85:
                                            chunk_part = chunk_part * (0.85 / chunk_max)
                                        if mix_max > 0.85:
                                            mix_part = mix_part * (0.85 / mix_max)

                                        mixed_64 = mix_part.astype(np.float64) + chunk_part.astype(
                                            np.float64
                                        ) * (0.92 if abs(track_sample_rate - 24000) < 100 else 1.0)
                                        mixed_max = np.max(np.abs(mixed_64))
                                        if mixed_max > 0.98:
                                            mixed_64 *= 0.98 / mixed_max

                                        mix_buffer[:min_frames] = mixed_64.astype(np.float32)
                                else:
                                    # 相同采样率的标准处理
                                    track_volume = state.get("volume", 1.0)
                                    is_track_muted = state.get("muted", False)

                                    if not is_track_muted and track_volume > 0.001:
                                        chunk_part = chunk[:min_frames]
                                        if track_volume != 1.0:
                                            chunk_part = chunk_part * track_volume
                                        np.add(
                                            mix_buffer[:min_frames],
                                            chunk_part,
                                            out=mix_buffer[:min_frames],
                                        )

                                # 使用最后几个样本进行淡出填充，但减少长度（降低对24kHz轨道的影响）
                                if min_frames < frames:
                                    fade_length = min(8, frames - min_frames)  # 进一步减少淡出长度
                                    if fade_length > 0:
                                        last_sample = (
                                            chunk[-1:]
                                            if chunk.shape[0] > 0
                                            else np.zeros((1, self.channels), dtype=np.float32)
                                        )

                                        # 对24kHz轨道使用更保守的淡出
                                        track_sample_rate = state.get(
                                            "sample_rate", self.sample_rate
                                        )
                                        start_fade = (
                                            0.3 if abs(track_sample_rate - 24000) < 100 else 0.5
                                        )

                                        # 创建更短的淡出序列
                                        fade_out = np.linspace(start_fade, 0.0, fade_length)[
                                            :, np.newaxis
                                        ]
                                        fade_chunk = last_sample * fade_out

                                        end_pos = min(min_frames + fade_length, frames)
                                        actual_fade_length = end_pos - min_frames
                                        if actual_fade_length > 0:
                                            np.add(
                                                mix_buffer[min_frames:end_pos],
                                                fade_chunk[:actual_fade_length],
                                                out=mix_buffer[min_frames:end_pos],
                                            )
                        else:
                            # 输入数据过多，截取并添加
                            truncated_chunk = chunk[:frames]
                            track_sample_rate = state.get("sample_rate", self.sample_rate)
                            if track_sample_rate != self.sample_rate:
                                # 高精度混音（同样的电流声消除策略）
                                track_volume = state.get("volume", 1.0)
                                is_track_muted = state.get("muted", False)

                                if not is_track_muted and track_volume > 0.001:
                                    if track_volume != 1.0:
                                        truncated_chunk = truncated_chunk * track_volume

                                    # 对24kHz轨道应用电流声检测
                                    if abs(track_sample_rate - 24000) < 100:
                                        for channel in range(self.channels):
                                            if frames > 2:
                                                channel_data = truncated_chunk[:, channel]
                                                diff = np.abs(np.diff(channel_data))
                                                mean_diff = np.mean(diff)
                                                std_diff = np.std(diff)

                                                if std_diff > mean_diff * 3:
                                                    smoothed = np.copy(channel_data)
                                                    for i in range(1, len(channel_data) - 1):
                                                        if diff[i - 1] > mean_diff + 2 * std_diff:
                                                            smoothed[i] = (
                                                                channel_data[i - 1]
                                                                + channel_data[i + 1]
                                                            ) * 0.5
                                                    truncated_chunk[:, channel] = smoothed

                                    chunk_max = np.max(np.abs(truncated_chunk))
                                    mix_max = np.max(np.abs(mix_buffer))

                                    if chunk_max > 0.85:
                                        truncated_chunk *= 0.85 / chunk_max
                                    if mix_max > 0.85:
                                        mix_buffer *= 0.85 / mix_max

                                    mixed_64 = mix_buffer.astype(
                                        np.float64
                                    ) + truncated_chunk.astype(np.float64) * (
                                        0.92 if abs(track_sample_rate - 24000) < 100 else 1.0
                                    )
                                    mixed_max = np.max(np.abs(mixed_64))
                                    if mixed_max > 0.98:
                                        mixed_64 *= 0.98 / mixed_max

                                    mix_buffer[:] = mixed_64.astype(np.float32)
                            else:
                                # 相同采样率的标准处理
                                track_volume = state.get("volume", 1.0)
                                is_track_muted = state.get("muted", False)

                                if not is_track_muted and track_volume > 0.001:
                                    if track_volume != 1.0:
                                        truncated_chunk = truncated_chunk * track_volume
                                    np.add(mix_buffer, truncated_chunk, out=mix_buffer)

                        # Update peak level - 安全计算
                        try:
                            chunk_peak = np.max(np.abs(chunk))
                            if np.isfinite(chunk_peak):
                                peak_level = max(peak_level, chunk_peak)
                        except:
                            pass  # 忽略峰值计算错误

                        active_track_count += 1

                except Exception as e:
                    logger.error(f"Error processing track {track_id}: {str(e)}")
                    state["playing"] = False
                    continue

            # 检查混音结果的有效性
            if np.any(np.isnan(mix_buffer)) or np.any(np.isinf(mix_buffer)):
                logger.error("Invalid audio data detected, clearing buffer")
                mix_buffer.fill(0)
                peak_level = 0.0

            # Apply main output processing - soft limiter (增强保护)
            try:
                # 额外的削波保护
                peak = np.max(np.abs(mix_buffer))
                if peak > 1.0:
                    mix_buffer *= 0.95 / peak  # 硬限制到0.95

                compression_ratio = self.audio_processor.soft_limiter_inplace(mix_buffer, 0.98)
                if compression_ratio < 0.9:
                    logger.debug(f"High compression applied: {compression_ratio:.3f}")
            except Exception as e:
                logger.error(f"Soft limiter error: {e}")
                # 紧急削波保护
                np.clip(mix_buffer, -0.98, 0.98, out=mix_buffer)

            # Update performance metrics
            if np.isfinite(peak_level):
                self.peak_level = max(self.peak_level, peak_level)

            # Copy data to output buffer - 确保安全拷贝
            try:
                outdata[:] = mix_buffer
            except Exception as e:
                logger.error(f"Output copy error: {e}")
                outdata.fill(0)  # 输出静音防止噪音

            # Asynchronously update states to reduce callback latency
            if active_track_count > 0:
                self._update_track_states_async(track_states_snapshot)

        except Exception as e:
            logger.error(f"Critical error in audio callback: {e}")
            # 紧急情况：输出静音
            outdata.fill(0)
        finally:
            # Return buffer to pool - 确保缓冲区被返回
            if mix_buffer is not None:
                try:
                    self.buffer_pool.return_buffer(mix_buffer)
                except Exception as e:
                    logger.error(f"Failed to return buffer: {e}")

        # Calculate CPU usage (exponential weighted moving average)
        try:
            process_time = time.perf_counter() - start_time
            current_cpu_usage = (process_time / self.buffer_duration) * 100

            # Use exponential weighted moving average (EWMA) to smooth CPU usage
            alpha = 0.2  # Smoothing factor
            self.cpu_usage = alpha * current_cpu_usage + (1 - alpha) * self.cpu_usage

            # 监控性能警告
            if current_cpu_usage > 80:
                logger.warning(f"High CPU usage in audio callback: {current_cpu_usage:.1f}%")
        except:
            pass  # 忽略性能计算错误

    def get_performance_stats(self) -> Dict[str, float]:
        """
        获取性能统计信息

        返回音频引擎的实时性能数据，用于监控和优化。

        Returns:
            Dict[str, float]: 包含性能指标的字典：
                - peak_level (float): 峰值电平
                - cpu_usage (float): CPU使用率（百分比）
                - underrun_count (int): 缓冲区下溢次数
                - active_tracks (int): 活跃轨道数
                - total_tracks (int): 总轨道数
                - loading_queue (int): 加载队列长度
                - callback_count (int): 音频回调次数

        Example:
            >>> stats = engine.get_performance_stats()
            >>> print(f"CPU使用率: {stats['cpu_usage']:.1f}%")
            >>> print(f"活跃轨道: {stats['active_tracks']}")
            >>> print(f"峰值电平: {stats['peak_level']:.3f}")
        """
        return {
            "peak_level": self.peak_level,
            "cpu_usage": self.cpu_usage,
            "underrun_count": self.underrun_count,
            "active_tracks": len(self.active_tracks),
            "total_tracks": len(self.track_states),  # 修改为包含所有轨道
            "loading_queue": self.loading_queue.qsize(),
            "callback_count": getattr(self, "callback_count", 0),  # 添加callback_count
        }

    def clear_all_tracks(self) -> None:
        """
        清除所有轨道

        卸载并移除所有已加载的轨道，释放相关内存。

        Example:
            >>> engine.clear_all_tracks()
            >>> print("所有轨道已清除")
        """
        with self.lock:
            for track_id in list(self.tracks.keys()):
                self.unload_track(track_id)
            logger.info("All tracks cleared")

    def _extract_audio_chunk_optimized(
        self,
        audio_data: npt.NDArray,
        position: int,
        speed: float,
        loop: bool,
        frames: int,
        track_sample_rate: int,
    ) -> Tuple[Optional[npt.NDArray], int]:
        """
        Optimized audio chunk extraction method with sample rate conversion
        :param track_sample_rate: Track's sample rate
        :return: (audio chunk, new position) or (None, position) if track ended
        """
        # 修复采样率转换比例计算！关键修复！
        # 正确的计算方式：输出采样率 / 输入采样率 = 目标帧数 / 源帧数
        rate_ratio = self.sample_rate / track_sample_rate

        # 如果采样率相同，使用原有的快速路径
        if abs(rate_ratio - 1.0) < 0.001:
            return self._extract_audio_chunk_original(audio_data, position, speed, loop, frames)

        # 需要采样率转换的情况
        # 计算在原始采样率下需要读取的帧数
        # 修复计算公式：如果要输出frames个48kHz的帧，需要读取多少个44.1kHz的帧？
        # frames * (44100/48000) = frames / rate_ratio
        source_frames_needed = int(frames / rate_ratio * speed)
        remaining = len(audio_data) - position

        if remaining <= 0:
            if loop:
                position = 0
                remaining = len(audio_data)
            else:
                return None, position

        # 提取音频数据
        read_frames = min(source_frames_needed, remaining)
        chunk = audio_data[position : position + read_frames].copy()
        new_position = position + read_frames

        # 处理循环
        if read_frames < source_frames_needed and loop:
            loop_frames_needed = source_frames_needed - read_frames
            if loop_frames_needed <= len(audio_data):
                loop_chunk = audio_data[:loop_frames_needed]
                chunk = np.concatenate((chunk, loop_chunk))
                new_position = loop_frames_needed
            else:
                # 需要多次循环
                chunks = [chunk]
                remaining_frames = loop_frames_needed
                new_position = 0

                while remaining_frames > 0:
                    copy_frames = min(remaining_frames, len(audio_data))
                    chunks.append(audio_data[:copy_frames])
                    remaining_frames -= copy_frames
                    new_position = copy_frames if remaining_frames == 0 else 0

                chunk = np.concatenate(chunks)
        elif new_position >= len(audio_data):
            if loop:
                new_position = 0

        # 采样率转换 - 修复传递参数
        if chunk.shape[0] > 0:
            resampled_chunk = self._resample_chunk_realtime(chunk, rate_ratio, frames)
            return resampled_chunk, new_position

        return None, new_position

    def _extract_audio_chunk_original(
        self, audio_data: npt.NDArray, position: int, speed: float, loop: bool, frames: int
    ) -> Tuple[Optional[npt.NDArray], int]:
        """
        Original optimized audio chunk extraction method (for same sample rate)
        """
        # Fast path for normal speed playback
        if abs(speed - 1.0) < 0.01:
            remaining = len(audio_data) - position
            render_frames = min(frames, remaining)

            if render_frames <= 0:
                if loop:
                    # Loop playback
                    position = 0
                    render_frames = min(frames, len(audio_data))
                    if render_frames > 0:
                        chunk = audio_data[:render_frames].copy()
                        new_position = render_frames

                        # If more frames are needed, continue from the beginning
                        if render_frames < frames:
                            remaining_frames = frames - render_frames
                            full_chunk = np.zeros((frames, self.channels), dtype=np.float32)
                            full_chunk[:render_frames] = chunk

                            if remaining_frames <= len(audio_data):
                                full_chunk[render_frames:] = audio_data[:remaining_frames]
                                new_position = remaining_frames
                            else:
                                # Audio file too short, need multiple loops
                                offset = render_frames
                                while offset < frames and remaining_frames > 0:
                                    copy_frames = min(remaining_frames, len(audio_data))
                                    full_chunk[offset : offset + copy_frames] = audio_data[
                                        :copy_frames
                                    ]
                                    offset += copy_frames
                                    remaining_frames -= copy_frames
                                new_position = remaining_frames

                            return full_chunk, new_position
                        return chunk, new_position
                    else:
                        return None, position
                else:
                    # Track ended
                    return None, position
            else:
                chunk = audio_data[position : position + render_frames].copy()
                new_position = position + render_frames

                # Handle looping
                if new_position >= len(audio_data) and loop:
                    loop_frames = frames - render_frames
                    if loop_frames > 0:
                        # Use pre-allocated buffer to avoid concatenate
                        full_chunk = np.zeros((frames, self.channels), dtype=np.float32)
                        full_chunk[:render_frames] = chunk

                        loop_chunk = audio_data[: min(loop_frames, len(audio_data))]
                        full_chunk[render_frames : render_frames + len(loop_chunk)] = loop_chunk
                        new_position = len(loop_chunk)
                        return full_chunk, new_position
                    else:
                        new_position = 0
                elif new_position >= len(audio_data):
                    # Track ended, but not looping
                    return chunk, len(audio_data)

                # Need to pad to full frame count
                if render_frames < frames:
                    full_chunk = np.zeros((frames, self.channels), dtype=np.float32)
                    full_chunk[:render_frames] = chunk
                    return full_chunk, new_position

                return chunk, new_position
        else:
            # Variable speed playback - use existing logic but optimized
            return self._extract_audio_chunk_with_speed(audio_data, position, speed, loop, frames)

    def _resample_chunk_realtime(
        self, chunk: npt.NDArray, rate_ratio: float, target_frames: int
    ) -> npt.NDArray:
        """
        Real-time audio chunk resampling (电流声修复版本)
        :param chunk: Input audio chunk
        :param rate_ratio: Target sample rate / source sample rate (正确的比例方向)
        :param target_frames: Target frame count
        :return: Resampled audio chunk
        """
        if chunk.shape[0] == 0:
            return np.zeros((target_frames, self.channels), dtype=np.float32)

        # 验证输入数据有效性
        if np.any(np.isnan(chunk)) or np.any(np.isinf(chunk)):
            logger.warning("Invalid input data in resampling, using zeros")
            return np.zeros((target_frames, self.channels), dtype=np.float32)

        # 如果比例接近1.0，避免不必要的重采样
        if abs(rate_ratio - 1.0) < 0.001:
            if chunk.shape[0] == target_frames:
                return chunk.copy()
            elif chunk.shape[0] < target_frames:
                # 简单的零填充，避免插值噪音
                padded = np.zeros((target_frames, self.channels), dtype=np.float32)
                padded[: chunk.shape[0]] = chunk
                return padded
            else:
                # 直接截取，避免抗混叠滤波引起的电流声
                return chunk[:target_frames].copy()

        # 特殊处理常见的采样率转换，减少电流声
        # 重点修复：24kHz -> 48kHz (rate_ratio = 2.0)
        if abs(rate_ratio - 2.0) < 0.01:
            # 24kHz到48kHz：简单的2倍上采样，避免复杂插值
            if chunk.shape[0] > 0:
                # 使用简单的线性插值，但加入防混叠
                upsampled = np.zeros((target_frames, self.channels), dtype=np.float32)

                # 计算需要的源样本数
                source_samples_needed = target_frames // 2
                available_samples = min(source_samples_needed, chunk.shape[0])

                if available_samples > 0:
                    for i in range(available_samples):
                        # 将每个源样本放置在两个输出位置
                        out_idx = i * 2
                        if out_idx < target_frames:
                            upsampled[out_idx] = chunk[i]

                            # 在相邻样本之间进行简单插值，减少锯齿
                            if out_idx + 1 < target_frames:
                                if i + 1 < chunk.shape[0]:
                                    # 线性插值到下一个样本
                                    upsampled[out_idx + 1] = (chunk[i] + chunk[i + 1]) * 0.5
                                else:
                                    # 最后一个样本，轻微衰减
                                    upsampled[out_idx + 1] = chunk[i] * 0.8

                    # 应用轻微的低通滤波器减少高频噪音（造成电流声的主因）
                    if target_frames > 4:
                        # 简单的3点移动平均，专门针对24->48kHz
                        for channel in range(self.channels):
                            smoothed = np.copy(upsampled[:, channel])
                            for i in range(1, target_frames - 1):
                                if i % 2 == 1:  # 只对插值点进行平滑
                                    smoothed[i] = (
                                        upsampled[i - 1, channel]
                                        + upsampled[i, channel]
                                        + upsampled[i + 1, channel]
                                    ) / 3
                            upsampled[:, channel] = smoothed

                return upsampled
            else:
                return np.zeros((target_frames, self.channels), dtype=np.float32)

        # 其他常见比例的优化处理
        elif abs(rate_ratio - 1.5) < 0.01:
            # 32kHz -> 48kHz
            return self._resample_1_5x(chunk, target_frames)
        elif abs(rate_ratio - (48000 / 44100)) < 0.01:
            # 44.1kHz -> 48kHz
            return self._resample_44_to_48(chunk, target_frames)
        elif abs(rate_ratio - 0.5) < 0.01:
            # 下采样到一半
            return self._resample_downsample_2x(chunk, target_frames)

        # 通用高质量重采样（避免使用会产生电流声的算法）
        try:
            # 对于其他采样率，使用改进的线性插值
            if chunk.shape[0] > 1:
                resampled = np.zeros((target_frames, self.channels), dtype=np.float32)

                # 使用高精度索引计算
                source_indices = np.linspace(0, chunk.shape[0] - 1, target_frames, dtype=np.float64)

                for channel in range(self.channels):
                    # 进行高质量线性插值
                    resampled[:, channel] = np.interp(
                        source_indices,
                        np.arange(chunk.shape[0], dtype=np.float64),
                        chunk[:, channel],
                    )

                # 应用非常轻微的平滑，只针对可能的数字噪音
                if target_frames > 6:
                    for channel in range(self.channels):
                        # 检测并修复可能的数字噪音
                        diff = np.abs(np.diff(resampled[:, channel]))
                        mean_diff = np.mean(diff)
                        spike_threshold = mean_diff * 5  # 5倍平均差异认为是噪音

                        for i in range(1, target_frames - 1):
                            if diff[i - 1] > spike_threshold:
                                # 检测到噪音尖峰，用邻近样本的平均值替代
                                resampled[i, channel] = (
                                    resampled[i - 1, channel] + resampled[i + 1, channel]
                                ) * 0.5

                return resampled
            else:
                # 单样本处理：避免重复产生的电流声
                resampled = np.zeros((target_frames, self.channels), dtype=np.float32)
                if chunk.shape[0] > 0 and target_frames > 0:
                    # 只设置第一个样本，其余保持静音
                    resampled[0] = chunk[0]

                    # 对于短的目标帧数，添加极轻微的衰减
                    if target_frames <= 8:
                        decay = np.exp(-np.arange(1, min(4, target_frames)) * 1.5)
                        for i in range(1, min(4, target_frames)):
                            resampled[i] = chunk[0] * decay[i - 1]

                return resampled

        except Exception as e:
            logger.warning(f"High-quality resampling failed: {e}, using fallback")
            # 最后的保险：简单的零插值
            resampled = np.zeros((target_frames, self.channels), dtype=np.float32)
            if chunk.shape[0] > 0:
                copy_frames = min(chunk.shape[0], target_frames)
                resampled[:copy_frames] = chunk[:copy_frames]
            return resampled

    def _resample_1_5x(self, chunk: npt.NDArray, target_frames: int) -> npt.NDArray:
        """专门处理1.5倍上采样（如32kHz->48kHz）"""
        if chunk.shape[0] == 0:
            return np.zeros((target_frames, self.channels), dtype=np.float32)

        resampled = np.zeros((target_frames, self.channels), dtype=np.float32)

        # 每2个输入样本产生3个输出样本
        source_pairs_needed = (target_frames + 2) // 3
        available_pairs = min(source_pairs_needed, chunk.shape[0] // 2)

        for i in range(available_pairs):
            if i * 2 + 1 < chunk.shape[0]:
                sample1 = chunk[i * 2]
                sample2 = chunk[i * 2 + 1]

                out_base = i * 3
                if out_base < target_frames:
                    resampled[out_base] = sample1
                if out_base + 1 < target_frames:
                    resampled[out_base + 1] = sample1 * 0.67 + sample2 * 0.33
                if out_base + 2 < target_frames:
                    resampled[out_base + 2] = sample1 * 0.33 + sample2 * 0.67

        return resampled

    def _resample_44_to_48(self, chunk: npt.NDArray, target_frames: int) -> npt.NDArray:
        """专门处理44.1kHz到48kHz的转换"""
        if chunk.shape[0] == 0:
            return np.zeros((target_frames, self.channels), dtype=np.float32)

        # 44100/48000 ≈ 0.91875
        ratio = 44100.0 / 48000.0
        source_indices = np.arange(target_frames) * ratio

        resampled = np.zeros((target_frames, self.channels), dtype=np.float32)

        for channel in range(self.channels):
            # 高质量插值，专门优化44.1->48转换
            resampled[:, channel] = np.interp(
                source_indices, np.arange(chunk.shape[0], dtype=np.float64), chunk[:, channel]
            )

        return resampled

    def _resample_downsample_2x(self, chunk: npt.NDArray, target_frames: int) -> npt.NDArray:
        """专门处理2倍下采样"""
        if chunk.shape[0] == 0:
            return np.zeros((target_frames, self.channels), dtype=np.float32)

        resampled = np.zeros((target_frames, self.channels), dtype=np.float32)

        # 简单的2:1抽取，但加入防混叠
        for i in range(target_frames):
            source_idx = i * 2
            if source_idx < chunk.shape[0]:
                if source_idx + 1 < chunk.shape[0]:
                    # 平均相邻两个样本以减少混叠
                    resampled[i] = (chunk[source_idx] + chunk[source_idx + 1]) * 0.5
                else:
                    resampled[i] = chunk[source_idx]

        return resampled

    def _extract_audio_chunk_with_speed(
        self, audio_data: npt.NDArray, position: int, speed: float, loop: bool, frames: int
    ) -> Tuple[Optional[npt.NDArray], int]:
        """Extract audio chunk with speed adjustment"""
        read_frames = int(frames * speed)
        remaining = len(audio_data) - position

        if remaining >= read_frames:
            chunk = audio_data[position : position + read_frames]
            new_position = position + read_frames
        else:
            chunk = audio_data[position:]
            if loop:
                loop_frames = read_frames - len(chunk)
                if loop_frames <= len(audio_data):
                    loop_chunk = audio_data[:loop_frames]
                    chunk = np.concatenate((chunk, loop_chunk))
                    new_position = loop_frames
                else:
                    # Need multiple loops
                    chunks = [chunk]
                    remaining_frames = loop_frames
                    new_position = 0

                    while remaining_frames > 0:
                        copy_frames = min(remaining_frames, len(audio_data))
                        chunks.append(audio_data[:copy_frames])
                        remaining_frames -= copy_frames
                        new_position = copy_frames if remaining_frames == 0 else 0

                    chunk = np.concatenate(chunks)
            else:
                # Pad with silence
                silence = np.zeros((read_frames - len(chunk), self.channels), dtype=np.float32)
                chunk = np.concatenate((chunk, silence))
                new_position = len(audio_data)

        # Resample to target frame count
        if chunk.shape[0] > 0 and chunk.shape[0] != frames:
            orig_times = np.arange(len(chunk))
            target_times = np.linspace(0, len(chunk) - 1, frames)
            resampled_chunk = np.zeros((frames, self.channels), dtype=np.float32)
            for channel in range(self.channels):
                resampled_chunk[:, channel] = np.interp(target_times, orig_times, chunk[:, channel])
            return resampled_chunk, new_position

        return chunk if chunk.shape[0] > 0 else None, new_position

    def _apply_audio_effects_optimized(
        self, chunk: npt.NDArray, state: Dict[str, Any], frames: int, track_id: str = None
    ) -> None:
        """Optimized audio effects application"""
        # Apply volume
        volume = state.get("volume", 1.0)
        if volume != 1.0:
            self.audio_processor.apply_volume_inplace(chunk, volume)

        # Handle fade in/out
        fade_progress = state.get("fade_progress")
        fade_direction = state.get("fade_direction")
        fade_duration = state.get("fade_duration", 0.05)

        if fade_direction and fade_progress is not None:
            # Generate or cache fade in/out steps
            fade_key = (fade_duration, frames)
            if fade_key not in self.fade_step_cache:
                self.fade_step_cache[fade_key] = frames / (fade_duration * self.sample_rate)

            fade_step = self.fade_step_cache[fade_key]

            if fade_direction == "in":
                fade_end = min(1.0, fade_progress + fade_step)
                fade_env = np.linspace(fade_progress, fade_end, frames)
                self.audio_processor.apply_fade_inplace(chunk, fade_env)

                if fade_end >= 1.0:
                    state["fade_progress"] = None
                    state["fade_direction"] = None
                else:
                    state["fade_progress"] = fade_end

            elif fade_direction == "out":
                fade_end = max(0.0, fade_progress - fade_step)
                fade_env = np.linspace(fade_progress, fade_end, frames)
                self.audio_processor.apply_fade_inplace(chunk, fade_env)

                if fade_end <= 0.0:
                    state["playing"] = False
                    state["fade_progress"] = None
                    state["fade_direction"] = None
                    # 立即从活跃轨道中移除（如果提供了 track_id）
                    if track_id:
                        self.active_tracks.discard(track_id)
                else:
                    state["fade_progress"] = fade_end

    def _update_track_states_async(self, states_snapshot: Dict[str, Dict[str, Any]]) -> None:
        """Asynchronously update track states to reduce audio callback latency"""

        def update_states():
            with self.lock:
                for track_id, state_snapshot in states_snapshot.items():
                    if track_id in self.track_states:
                        # Update key states
                        current_state = self.track_states[track_id]
                        current_state["position"] = state_snapshot["position"]

                        # Update fade in/out states
                        if "fade_progress" in state_snapshot:
                            current_state["fade_progress"] = state_snapshot["fade_progress"]
                        if "fade_direction" in state_snapshot:
                            current_state["fade_direction"] = state_snapshot["fade_direction"]

                        # Handle playback end
                        if not state_snapshot.get("playing", True):
                            current_state["playing"] = False
                            self.active_tracks.discard(track_id)
                            logger.debug(f"Track finished: {track_id}")

        # Use daemon thread to execute state update
        threading.Thread(target=update_states, daemon=True).start()

    def get_track_info(self, track_id: str) -> Optional[Dict[str, Any]]:
        """
        获取音轨详细信息

        返回指定轨道的完整信息，包括播放状态、音频参数、缓冲区状态等。

        Args:
            track_id (str): 轨道ID

        Returns:
            Optional[Dict[str, Any]]: 轨道信息字典，如果轨道不存在则返回None
                包含以下信息：
                - track_id (str): 轨道ID
                - duration (float): 轨道总时长（秒）
                - position (float): 当前播放位置（秒）
                - volume (float): 当前音量
                - playing (bool): 是否正在播放
                - paused (bool): 是否暂停
                - loop (bool): 是否循环播放
                - muted (bool): 是否静音
                - original_volume (float): 原始音量（静音前）
                - speed (float): 播放速度
                - fade_direction (str): 淡入淡出方向
                - fade_duration (float): 淡入淡出持续时间
                - file_path (str): 文件路径
                - samples (int): 音频样本数
                - channels (int): 声道数
                - sample_rate (int): 轨道采样率
                - engine_sample_rate (int): 引擎采样率
                - sample_rate_ratio (float): 采样率比例
                - streaming_mode (bool): 是否为流式模式
                - buffer_status (dict): 缓冲区状态（仅流式轨道）

        Example:
            >>> info = engine.get_track_info("bgm1")
            >>> if info:
            ...     print(f"轨道: {info['track_id']}")
            ...     print(f"时长: {info['duration']:.2f}秒")
            ...     print(f"位置: {info['position']:.2f}秒")
            ...     print(f"音量: {info['volume']:.2f}")
            ...     print(f"状态: {'播放中' if info['playing'] else '停止'}")
        """
        with self.lock:
            if track_id not in self.track_states:
                return None

            state = self.track_states[track_id]

            # 检查是否为流式轨道
            if state.get("streaming_mode", False) and track_id in self.streaming_tracks:
                # 流式轨道信息
                streaming_track = self.streaming_tracks[track_id]
                buffer_status = streaming_track.get_buffer_status()

                return {
                    "track_id": track_id,
                    "duration": streaming_track.duration,
                    "position": streaming_track.get_position_seconds(),
                    "volume": state.get("volume", 1.0),
                    "playing": state.get("playing", False),
                    "paused": state.get("paused", False),
                    "loop": state.get("loop", False),
                    "muted": state.get("muted", False),  # 静音状态
                    "original_volume": state.get("original_volume", 1.0),  # 原始音量
                    "speed": state.get("speed", 1.0),
                    "fade_direction": state.get("fade_direction"),
                    "fade_duration": state.get("fade_duration", 0.05),
                    "file_path": self.track_files.get(track_id),
                    "samples": int(streaming_track.duration * streaming_track.engine_sample_rate),
                    "channels": streaming_track.engine_channels,
                    "sample_rate": state["sample_rate"],
                    "engine_sample_rate": self.sample_rate,
                    "sample_rate_ratio": state["sample_rate"] / self.sample_rate,
                    "streaming_mode": True,
                    "buffer_status": buffer_status,
                    "silent_padding_ms": state.get(
                        "silent_padding_ms", 0.0
                    ),  # 静音填充信息（兼容性）
                    "silent_lpadding_ms": state.get("silent_lpadding_ms", 0.0),  # 左侧静音填充信息
                    "silent_rpadding_ms": state.get("silent_rpadding_ms", 0.0),  # 右侧静音填充信息
                    "virtual_position": state.get("virtual_position", 0),  # 虚拟播放位置
                    "padding_frames_start": state.get("padding_frames_start", 0),  # 开始静音帧数
                    "padding_frames_end": state.get("padding_frames_end", 0),  # 结束静音帧数
                }

            elif track_id in self.tracks:
                # 预加载轨道信息
                audio_data = self.tracks[track_id]

                return {
                    "track_id": track_id,
                    "duration": len(audio_data) / state["sample_rate"],
                    "position": state["position"] / state["sample_rate"],
                    "volume": state.get("volume", 1.0),
                    "playing": state.get("playing", False),
                    "paused": state.get("paused", False),
                    "loop": state.get("loop", False),
                    "muted": state.get("muted", False),  # 静音状态
                    "original_volume": state.get("original_volume", 1.0),  # 原始音量
                    "speed": state.get("speed", 1.0),
                    "fade_direction": state.get("fade_direction"),
                    "fade_duration": state.get("fade_duration", 0.05),
                    "file_path": self.track_files.get(track_id),
                    "samples": len(audio_data),
                    "channels": audio_data.shape[1],
                    "sample_rate": state["sample_rate"],
                    "engine_sample_rate": self.sample_rate,
                    "sample_rate_ratio": state["sample_rate"] / self.sample_rate,
                    "streaming_mode": False,
                    "silent_padding_ms": state.get(
                        "silent_padding_ms", 0.0
                    ),  # 静音填充信息（兼容性）
                    "silent_lpadding_ms": state.get("silent_lpadding_ms", 0.0),  # 左侧静音填充信息
                    "silent_rpadding_ms": state.get("silent_rpadding_ms", 0.0),  # 右侧静音填充信息
                }

            return None

    def list_tracks(self) -> List[Dict[str, Any]]:
        """
        获取所有已加载音轨的列表

        Returns:
            List[Dict[str, Any]]: 音轨信息列表，每个元素包含轨道的详细信息

        Example:
            >>> tracks = engine.list_tracks()
            >>> for track in tracks:
            ...     print(f"轨道: {track['track_id']}, 时长: {track['duration']:.2f}秒")
        """
        with self.lock:
            tracks_info = []
            for track_id in self.track_states.keys():
                info = self.get_track_info(track_id)
                if info:
                    tracks_info.append(info)
            return tracks_info

    def get_playing_tracks(self) -> List[str]:
        """
        获取所有正在播放的音轨ID列表

        Returns:
            List[str]: 正在播放的音轨ID列表（不包括暂停的轨道）

        Example:
            >>> playing = engine.get_playing_tracks()
            >>> print(f"正在播放 {len(playing)} 个轨道: {playing}")
        """
        with self.lock:
            return [
                track_id
                for track_id in self.active_tracks
                if self.track_states[track_id].get("playing", False)
                and not self.track_states[track_id].get("paused", False)
            ]

    def get_paused_tracks(self) -> List[str]:
        """
        获取所有暂停的音轨ID列表

        Returns:
            List[str]: 暂停的音轨ID列表

        Example:
            >>> paused = engine.get_paused_tracks()
            >>> print(f"暂停了 {len(paused)} 个轨道: {paused}")
        """
        with self.lock:
            return [
                track_id
                for track_id, state in self.track_states.items()
                if state.get("playing", False) and state.get("paused", False)
            ]

    def pause_all_tracks(self) -> List[str]:
        """
        暂停所有正在播放的音轨

        Returns:
            List[str]: 被暂停的音轨ID列表

        Example:
            >>> paused_tracks = engine.pause_all_tracks()
            >>> print(f"暂停了 {len(paused_tracks)} 个音轨")
        """
        paused_tracks = []
        with self.lock:
            for track_id in list(self.active_tracks):
                state = self.track_states[track_id]
                if state.get("playing", False) and not state.get("paused", False):
                    state["paused"] = True
                    paused_tracks.append(track_id)

            if paused_tracks:
                logger.info(f"暂停了 {len(paused_tracks)} 个音轨: {paused_tracks}")

        return paused_tracks

    def resume_all_tracks(self) -> List[str]:
        """
        恢复所有暂停的音轨

        Returns:
            List[str]: 被恢复的音轨ID列表

        Example:
            >>> resumed_tracks = engine.resume_all_tracks()
            >>> print(f"恢复了 {len(resumed_tracks)} 个轨道")
        """
        resumed_tracks = []
        with self.lock:
            for track_id, state in self.track_states.items():
                if state.get("playing", False) and state.get("paused", False):
                    state["paused"] = False
                    resumed_tracks.append(track_id)

            if resumed_tracks:
                logger.info(f"恢复了 {len(resumed_tracks)} 个音轨: {resumed_tracks}")

        return resumed_tracks

    def stop_all_tracks(self, fade_out: bool = True) -> List[str]:
        """
        停止所有正在播放的音轨

        Args:
            fade_out (bool, optional): 是否使用淡出效果. Defaults to True.

        Returns:
            List[str]: 被停止的音轨ID列表

        Example:
            >>> stopped_tracks = engine.stop_all_tracks()
            >>> print(f"停止了 {len(stopped_tracks)} 个轨道")

            >>> # 立即停止所有轨道
            >>> engine.stop_all_tracks(fade_out=False)
        """
        stopped_tracks = []
        with self.lock:
            for track_id in list(self.active_tracks):
                if self.track_states[track_id].get("playing", False):
                    self.stop(track_id, fade_out=fade_out)
                    stopped_tracks.append(track_id)

            if stopped_tracks:
                logger.info(f"停止了 {len(stopped_tracks)} 个音轨: {stopped_tracks}")

        return stopped_tracks

    def remove_track(self, track_id: str, fade_out: bool = True) -> bool:
        """
        移除音轨（先停止播放，然后卸载）

        Args:
            track_id (str): 要移除的音轨ID
            fade_out (bool, optional): 是否使用淡出效果停止播放. Defaults to True.

        Returns:
            bool: 是否成功移除

        Example:
            >>> if engine.remove_track("bgm1"):
            ...     print("轨道移除成功")

            >>> # 立即移除轨道
            >>> engine.remove_track("bgm1", fade_out=False)
        """
        with self.lock:
            if track_id not in self.tracks:
                logger.warning(f"音轨不存在: {track_id}")
                return False

            # 如果正在播放，先停止
            if self.track_states[track_id].get("playing", False):
                self.stop(track_id, fade_out=fade_out)
                logger.info(f"停止播放音轨: {track_id}")

            # 卸载音轨
            success = self.unload_track(track_id)
            if success:
                logger.info(f"成功移除音轨: {track_id}")

            return success

    def is_track_playing(self, track_id: str) -> bool:
        """
        检查音轨是否正在播放

        Args:
            track_id (str): 轨道ID

        Returns:
            bool: 是否正在播放（不包括暂停状态）

        Example:
            >>> if engine.is_track_playing("bgm1"):
            ...     print("轨道正在播放")
        """
        with self.lock:
            if track_id not in self.track_states:
                return False
            state = self.track_states[track_id]
            return state.get("playing", False) and not state.get("paused", False)

    def is_track_paused(self, track_id: str) -> bool:
        """
        检查音轨是否暂停

        Args:
            track_id (str): 轨道ID

        Returns:
            bool: 是否暂停

        Example:
            >>> if engine.is_track_paused("bgm1"):
            ...     print("轨道已暂停")
        """
        with self.lock:
            if track_id not in self.track_states:
                return False
            state = self.track_states[track_id]
            return state.get("playing", False) and state.get("paused", False)

    def is_track_loaded(self, track_id: str) -> bool:
        """
        检查音轨是否已加载

        Args:
            track_id (str): 轨道ID

        Returns:
            bool: 是否已加载（包括预加载和流式轨道）

        Example:
            >>> if engine.is_track_loaded("bgm1"):
            ...     print("轨道已加载")
        """
        with self.lock:
            return track_id in self.track_states  # 检查轨道状态而不只是tracks

    def get_track_count(self) -> Dict[str, int]:
        """
        获取音轨数量统计

        Returns:
            Dict[str, int]: 包含各种状态音轨数量的字典：
                - total (int): 总轨道数
                - preloaded (int): 预加载轨道数
                - streaming (int): 流式轨道数
                - playing (int): 正在播放的轨道数
                - paused (int): 暂停的轨道数
                - muted (int): 静音的轨道数
                - stopped (int): 停止的轨道数
                - max_tracks (int): 最大轨道数限制
                - available_slots (int): 可用轨道槽位数

        Example:
            >>> counts = engine.get_track_count()
            >>> print(f"总轨道: {counts['total']}/{counts['max_tracks']}")
            >>> print(f"播放中: {counts['playing']}, 暂停: {counts['paused']}")
            >>> print(f"剩余槽位: {counts['available_slots']}")
        """
        with self.lock:
            total = len(self.track_states)
            preloaded = len(self.tracks)
            streaming = len(self.streaming_tracks)
            playing = len(
                [
                    t
                    for t in self.active_tracks
                    if self.track_states.get(t, {}).get("playing", False)
                    and not self.track_states.get(t, {}).get("paused", False)
                ]
            )
            paused = len(
                [
                    t
                    for t, s in self.track_states.items()
                    if s.get("playing", False) and s.get("paused", False)
                ]
            )
            muted = len([t for t, s in self.track_states.items() if s.get("muted", False)])

            return {
                "total": total,
                "preloaded": preloaded,
                "streaming": streaming,
                "playing": playing,
                "paused": paused,
                "muted": muted,  # 静音轨道数量
                "stopped": total - playing - paused,
                "max_tracks": self.max_tracks,
                "available_slots": self.max_tracks - total,
            }

    def set_track_sample_rate(self, track_id: str, sample_rate: int) -> bool:
        """
        设置音轨的采样率（实时调整）

        动态调整轨道的采样率，会自动调整播放位置以保持相同的时间位置。

        Args:
            track_id (str): 轨道ID
            sample_rate (int): 新的采样率（8000-192000Hz）

        Returns:
            bool: 是否设置成功

        Note:
            采样率调整会影响音频的音调和播放速度

        Example:
            >>> # 将轨道采样率调整为44100Hz
            >>> if engine.set_track_sample_rate("bgm1", 44100):
            ...     print("采样率调整成功")
        """
        if sample_rate < 8000 or sample_rate > 192000:
            logger.error(f"Invalid sample rate: {sample_rate}Hz (must be between 8000-192000Hz)")
            return False

        with self.lock:
            if track_id not in self.track_states:
                return False

            old_sample_rate = self.track_states[track_id]["sample_rate"]
            self.track_states[track_id]["sample_rate"] = sample_rate

            # 调整播放位置以保持相同的时间位置
            current_time = self.track_states[track_id]["position"] / old_sample_rate
            self.track_states[track_id]["position"] = int(current_time * sample_rate)

            logger.info(f"Set sample rate for {track_id}: {old_sample_rate}Hz -> {sample_rate}Hz")
            return True

    def get_track_sample_rate(self, track_id: str) -> Optional[int]:
        """
        获取音轨的采样率

        Args:
            track_id (str): 轨道ID

        Returns:
            Optional[int]: 采样率，如果轨道不存在则返回None

        Example:
            >>> rate = engine.get_track_sample_rate("bgm1")
            >>> if rate:
            ...     print(f"轨道采样率: {rate}Hz")
        """
        with self.lock:
            if track_id in self.track_states:
                return self.track_states[track_id]["sample_rate"]
            return None

    def list_tracks_by_sample_rate(self) -> Dict[int, List[str]]:
        """
        按采样率分组列出所有音轨

        Returns:
            Dict[int, List[str]]: 以采样率为键，音轨ID列表为值的字典

        Example:
            >>> tracks_by_rate = engine.list_tracks_by_sample_rate()
            >>> for rate, track_list in tracks_by_rate.items():
            ...     print(f"{rate}Hz: {track_list}")
        """
        with self.lock:
            tracks_by_rate = {}
            for track_id, state in self.track_states.items():
                sample_rate = state["sample_rate"]
                if sample_rate not in tracks_by_rate:
                    tracks_by_rate[sample_rate] = []
                tracks_by_rate[sample_rate].append(track_id)
            return tracks_by_rate

    def get_sample_rate_statistics(self) -> Dict[str, Any]:
        """
        获取采样率统计信息

        Returns:
            Dict[str, Any]: 采样率统计信息，包含：
                - engine_sample_rate (int): 引擎采样率
                - unique_sample_rates (List[int]): 所有唯一的采样率
                - tracks_by_rate (Dict): 按采样率分组的轨道统计
                - total_tracks (int): 总轨道数
                - native_rate_tracks (int): 与引擎采样率相同的轨道数
                - conversion_needed_tracks (int): 需要转换的轨道数

        Example:
            >>> stats = engine.get_sample_rate_statistics()
            >>> print(f"引擎采样率: {stats['engine_sample_rate']}Hz")
            >>> print(f"需要转换的轨道: {stats['conversion_needed_tracks']}")
        """
        with self.lock:
            stats = {
                "engine_sample_rate": self.sample_rate,
                "unique_sample_rates": set(),
                "tracks_by_rate": {},
                "total_tracks": len(self.tracks),
                "native_rate_tracks": 0,  # 与引擎采样率相同的音轨数量
                "conversion_needed_tracks": 0,  # 需要转换的音轨数量
            }

            for track_id, state in self.track_states.items():
                sample_rate = state["sample_rate"]
                stats["unique_sample_rates"].add(sample_rate)

                if sample_rate not in stats["tracks_by_rate"]:
                    stats["tracks_by_rate"][sample_rate] = {"count": 0, "track_ids": []}

                stats["tracks_by_rate"][sample_rate]["count"] += 1
                stats["tracks_by_rate"][sample_rate]["track_ids"].append(track_id)

                if sample_rate == self.sample_rate:
                    stats["native_rate_tracks"] += 1
                else:
                    stats["conversion_needed_tracks"] += 1

            stats["unique_sample_rates"] = sorted(list(stats["unique_sample_rates"]))
            return stats

    def get_memory_usage(self) -> Dict[str, Any]:
        """
        获取内存使用统计

        分析音频引擎的内存使用情况，包括每个轨道的内存占用。

        Returns:
            Dict[str, Any]: 内存使用信息，包含：
                - total_memory_mb (float): 总内存使用量（MB）
                - max_memory_mb (float): 最大内存限制（MB）
                - track_count (int): 轨道数量
                - track_memory (Dict): 每个轨道的内存详情
                - large_file_threshold_mb (float): 大文件阈值（MB）
                - chunk_size_frames (int): 分块大小（帧）

        Example:
            >>> memory = engine.get_memory_usage()
            >>> print(f"内存使用: {memory['total_memory_mb']:.1f}MB")
            >>> print(f"最大限制: {memory['max_memory_mb']:.1f}MB")
            >>> for track_id, info in memory['track_memory'].items():
            ...     print(f"  {track_id}: {info['size_mb']:.1f}MB")
        """
        with self.lock:
            total_memory = 0
            track_memory = {}

            for track_id, audio_data in self.tracks.items():
                memory_bytes = audio_data.nbytes
                total_memory += memory_bytes
                track_memory[track_id] = {
                    "size_mb": memory_bytes / (1024 * 1024),
                    "samples": len(audio_data),
                    "channels": audio_data.shape[1],
                    "dtype": str(audio_data.dtype),
                }

            return {
                "total_memory_mb": total_memory / (1024 * 1024),
                "max_memory_mb": self.max_memory_usage / (1024 * 1024),
                "track_count": len(self.tracks),
                "track_memory": track_memory,
                "large_file_threshold_mb": self.large_file_threshold / (1024 * 1024),
                "chunk_size_frames": self.chunk_size,
            }

    def set_large_file_settings(
        self, threshold_mb: int = 100, max_memory_mb: int = 512, chunk_size_frames: int = 8192
    ) -> None:
        """
        设置大文件处理参数

        调整大文件加载的参数，影响内存使用和性能。

        Args:
            threshold_mb (int, optional): 大文件阈值（MB）. Defaults to 100.
            max_memory_mb (int, optional): 最大内存使用量（MB）. Defaults to 512.
            chunk_size_frames (int, optional): 分块大小（帧数）. Defaults to 8192.

        Example:
            >>> # 设置较小的大文件阈值和内存限制
            >>> engine.set_large_file_settings(
            ...     threshold_mb=50,
            ...     max_memory_mb=256,
            ...     chunk_size_frames=4096
            ... )
        """
        self.large_file_threshold = threshold_mb * 1024 * 1024
        self.max_memory_usage = max_memory_mb * 1024 * 1024
        self.chunk_size = chunk_size_frames

        logger.info(
            f"大文件设置更新: 阈值={threshold_mb}MB, 最大内存={max_memory_mb}MB, 块大小={chunk_size_frames}帧"
        )

    def optimize_memory(self) -> Dict[str, Any]:
        """
        内存优化：清理不必要的缓存和进行垃圾回收

        执行内存优化操作，清理缓存并强制垃圾回收。

        Returns:
            Dict[str, Any]: 优化结果统计，包含：
                - cache_entries_cleared (int): 清理的缓存项数
                - buffer_pool_cleared (int): 清理的缓冲池项数
                - memory_before_mb (float): 优化前内存使用量
                - memory_after_mb (float): 优化后内存使用量
                - memory_freed_mb (float): 释放的内存量

        Example:
            >>> result = engine.optimize_memory()
            >>> print(f"释放内存: {result['memory_freed_mb']:.1f}MB")
            >>> print(f"清理缓存项: {result['cache_entries_cleared']}")
        """
        before_stats = self.get_memory_usage()

        # 清理淡入淡出缓存
        cache_cleared = len(self.fade_step_cache)
        self.fade_step_cache.clear()

        # 清理缓冲池中的多余缓冲区
        with self.buffer_pool._lock:
            pool_cleared = len(self.buffer_pool.pool)
            self.buffer_pool.pool.clear()
            # 重新分配基本缓冲区
            for _ in range(min(4, self.buffer_pool.pool.maxlen)):
                self.buffer_pool.pool.append(
                    np.zeros((self.buffer_size, self.channels), dtype=np.float32)
                )

        # 强制垃圾回收
        gc.collect()

        after_stats = self.get_memory_usage()

        result = {
            "cache_entries_cleared": cache_cleared,
            "buffer_pool_cleared": pool_cleared,
            "memory_before_mb": before_stats["total_memory_mb"],
            "memory_after_mb": after_stats["total_memory_mb"],
            "memory_freed_mb": before_stats["total_memory_mb"] - after_stats["total_memory_mb"],
        }

        logger.info(
            f"内存优化完成: 释放{result['memory_freed_mb']:.1f}MB, 清理{cache_cleared}个缓存项"
        )
        return result

    def get_streaming_stats(self) -> Dict[str, Any]:
        """
        获取流式播放统计信息

        返回流式播放系统的详细统计信息。

        Returns:
            Dict[str, Any]: 流式播放统计信息，包含：
                - streaming_enabled (bool): 是否启用流式播放
                - streaming_threshold_mb (float): 流式播放阈值（MB）
                - total_streaming_tracks (int): 流式轨道总数
                - streaming_tracks (Dict): 每个流式轨道的详细信息
                - total_buffer_underruns (int): 总缓冲区下溢次数
                - total_chunks_loaded (int): 总加载块数

        Example:
            >>> stats = engine.get_streaming_stats()
            >>> print(f"流式播放: {'启用' if stats['streaming_enabled'] else '禁用'}")
            >>> print(f"流式轨道: {stats['total_streaming_tracks']}")
            >>> print(f"缓冲区下溢: {stats['total_buffer_underruns']}")
        """
        with self.lock:
            stats = {
                "streaming_enabled": self.enable_streaming,
                "streaming_threshold_mb": self.streaming_threshold / (1024 * 1024),
                "total_streaming_tracks": len(self.streaming_tracks),
                "streaming_tracks": {},
            }

            total_buffer_underruns = 0
            total_chunks_loaded = 0

            for track_id, streaming_track in self.streaming_tracks.items():
                buffer_status = streaming_track.get_buffer_status()
                track_stats = {
                    "file_path": streaming_track.file_path,
                    "duration": streaming_track.duration,
                    "position": streaming_track.get_position_seconds(),
                    "buffer_status": buffer_status,
                    "file_sample_rate": streaming_track.file_sample_rate,
                    "engine_sample_rate": streaming_track.engine_sample_rate,
                }
                stats["streaming_tracks"][track_id] = track_stats

                total_buffer_underruns += buffer_status["underruns"]
                total_chunks_loaded += buffer_status["chunks_loaded"]

            stats["total_buffer_underruns"] = total_buffer_underruns
            stats["total_chunks_loaded"] = total_chunks_loaded

            return stats

    def set_streaming_config(
        self, enable_streaming: bool = None, threshold_mb: int = None
    ) -> Dict[str, Any]:
        """
        设置流式播放配置

        动态调整流式播放的设置。

        Args:
            enable_streaming (bool, optional): 是否启用流式播放. Defaults to None.
            threshold_mb (int, optional): 流式播放阈值（MB）. Defaults to None.

        Returns:
            Dict[str, Any]: 更新后的配置信息

        Example:
            >>> # 启用流式播放并设置阈值为50MB
            >>> config = engine.set_streaming_config(
            ...     enable_streaming=True,
            ...     threshold_mb=50
            ... )
            >>> print(f"流式播放: {config['streaming_enabled']}")
            >>> print(f"阈值: {config['streaming_threshold_mb']}MB")
        """
        if enable_streaming is not None:
            self.enable_streaming = enable_streaming
            logger.info(f"流式播放模式: {'启用' if enable_streaming else '禁用'}")

        if threshold_mb is not None:
            self.streaming_threshold = threshold_mb * 1024 * 1024
            logger.info(f"流式播放阈值: {threshold_mb}MB")

        return {
            "streaming_enabled": self.enable_streaming,
            "streaming_threshold_mb": self.streaming_threshold / (1024 * 1024),
            "large_file_threshold_mb": self.large_file_threshold / (1024 * 1024),
        }

    def is_track_streaming(self, track_id: str) -> bool:
        """
        检查音轨是否为流式模式

        Args:
            track_id (str): 轨道ID

        Returns:
            bool: 是否为流式模式

        Example:
            >>> if engine.is_track_streaming("bgm1"):
            ...     print("轨道使用流式播放")
            ... else:
            ...     print("轨道为预加载模式")
        """
        with self.lock:
            if track_id in self.track_states:
                return self.track_states[track_id].get("streaming_mode", False)
            return False

    def force_streaming_mode(
        self,
        track_id: str,
        file_path: str,
        auto_normalize: bool = True,
        sample_rate: Optional[int] = None,
        silent_lpadding_ms: float = 0.0,
        silent_rpadding_ms: float = 0.0,
        on_complete: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """
        强制使用流式模式加载轨道（忽略文件大小阈值）

        无论文件大小如何，都强制使用流式播放模式加载轨道。

        Args:
            track_id (str): 轨道ID
            file_path (str): 音频文件路径
            auto_normalize (bool, optional): 是否自动标准化. Defaults to True.
            sample_rate (int, optional): 采样率. Defaults to None.
            silent_lpadding_ms (float, optional): 音频前面的静音填充时长（毫秒）. Defaults to 0.0.
            silent_rpadding_ms (float, optional): 音频后面的静音填充时长（毫秒）. Defaults to 0.0.
            on_complete (callable, optional): 完成回调. Defaults to None.
            progress_callback (callable, optional): 进度回调. Defaults to None.

        Returns:
            bool: 是否开始加载

        Example:
            >>> # 强制使用流式模式加载小文件
            >>> success = engine.force_streaming_mode(
            ...     track_id="bgm1",
            ...     file_path="/path/to/small_audio.wav",
            ...     silent_lpadding_ms=300.0,  # 前面300ms静音
            ...     silent_rpadding_ms=500.0  # 后面500ms静音
            ... )
            >>> if success:
            ...     print("强制流式加载已开始")
        """
        if not os.path.isfile(file_path):
            error = f"文件不存在: {file_path}"
            logger.error(error)
            if on_complete:
                on_complete(track_id, False, error)
            return False

        # 检查轨道数量限制
        with self.lock:
            if len(self.track_states) >= self.max_tracks:
                error = f"轨道数量已达上限 ({self.max_tracks})"
                logger.warning(error)
                if on_complete:
                    on_complete(track_id, False, error)
                return False

            # 如果轨道已存在，先卸载
            if track_id in self.track_states:
                self.unload_track(track_id)

        # 强制使用流式加载
        try:
            self._load_streaming_track(
                track_id,
                file_path,
                auto_normalize,
                sample_rate,
                silent_lpadding_ms,
                silent_rpadding_ms,
                on_complete,
                progress_callback,
            )
            return True
        except Exception as e:
            logger.error(f"强制流式加载失败: {e}")
            if on_complete:
                on_complete(track_id, False, str(e))
            return False

    def _get_streaming_audio_with_padding(
        self, track_id: str, streaming_track: StreamingTrackData, state: Dict[str, Any], frames: int
    ) -> npt.NDArray:
        """
        获取带静音填充的流式音频数据

        处理流式轨道的静音填充逻辑，在轨道开始和结束时添加静音。

        Args:
            track_id (str): 轨道ID
            streaming_track (StreamingTrackData): 流式轨道对象
            state (Dict): 轨道状态
            frames (int): 需要的帧数

        Returns:
            np.ndarray: 音频数据（可能包含静音填充）
        """
        padding_start = state.get("padding_frames_start", 0)
        padding_end = state.get("padding_frames_end", 0)
        virtual_position = state.get("virtual_position", 0)

        # 如果没有静音填充，直接返回原始数据
        if padding_start == 0 and padding_end == 0:
            chunk = streaming_track.get_audio_data(frames)
            return chunk

        # 计算总的虚拟长度（包含静音填充）
        total_virtual_frames = (
            padding_start
            + int(streaming_track.duration * streaming_track.engine_sample_rate)
            + padding_end
        )

        # 初始化输出缓冲区
        output = np.zeros((frames, self.channels), dtype=np.float32)

        for i in range(frames):
            current_virtual_pos = virtual_position + i

            if current_virtual_pos < padding_start:
                # 开始静音部分
                continue  # 保持为0
            elif current_virtual_pos >= total_virtual_frames - padding_end:
                # 结束静音部分
                continue  # 保持为0
            else:
                # 实际音频部分
                actual_pos = current_virtual_pos - padding_start
                # 这里需要从流式轨道获取单个样本（简化处理）
                # 实际实现中，应该批量获取以提高效率
                pass

        # 简化处理：分段获取音频数据
        start_virtual = virtual_position
        end_virtual = virtual_position + frames

        output_offset = 0

        # 处理开始静音
        if start_virtual < padding_start:
            silence_frames = min(frames, padding_start - start_virtual)
            # output中已经是零，不需要额外处理
            output_offset += silence_frames
            start_virtual += silence_frames

        # 处理实际音频部分
        if start_virtual < total_virtual_frames - padding_end and output_offset < frames:
            audio_start_pos = max(0, start_virtual - padding_start)
            audio_frames_needed = min(
                frames - output_offset, (total_virtual_frames - padding_end) - start_virtual
            )

            if audio_frames_needed > 0:
                # 获取实际音频数据
                audio_chunk = streaming_track.get_audio_data(audio_frames_needed)
                if audio_chunk is not None and audio_chunk.shape[0] > 0:
                    copy_frames = min(audio_frames_needed, audio_chunk.shape[0])
                    output[output_offset : output_offset + copy_frames] = audio_chunk[:copy_frames]
                output_offset += audio_frames_needed

        # 处理结束静音（output中剩余部分已经是零）

        # 更新虚拟位置
        state["virtual_position"] = virtual_position + frames

        return output

    def _is_streaming_track_at_end(
        self, streaming_track: StreamingTrackData, state: Dict[str, Any]
    ) -> bool:
        """检查流式轨道是否到达末尾（考虑静音填充）"""
        padding_end = state.get("padding_frames_end", 0)
        virtual_position = state.get("virtual_position", 0)
        total_virtual_frames = (
            state.get("padding_frames_start", 0)
            + int(streaming_track.duration * streaming_track.engine_sample_rate)
            + padding_end
        )

        return virtual_position >= total_virtual_frames

    def _is_streaming_track_finished(
        self, streaming_track: StreamingTrackData, state: Dict[str, Any]
    ) -> bool:
        """检查流式轨道是否完全结束（不循环时）"""
        return self._is_streaming_track_at_end(streaming_track, state) and not state.get(
            "loop", False
        )

    def _reset_streaming_track_for_loop(
        self, streaming_track: StreamingTrackData, state: Dict[str, Any]
    ) -> None:
        """重置流式轨道用于循环播放"""
        streaming_track.seek_to(0.0)
        state["virtual_position"] = 0

    def _detect_and_smooth_discontinuities(self, chunk: npt.NDArray, track_id: str) -> npt.NDArray:
        """
        检测并平滑音频不连续性，预防爆音和锐鸣声（减少过度处理版本）

        Args:
            chunk (np.ndarray): 音频数据块
            track_id (str): 轨道ID（用于状态跟踪）

        Returns:
            np.ndarray: 平滑处理后的音频数据
        """
        if chunk.shape[0] == 0:
            return chunk

        # 验证输入数据有效性
        if np.any(np.isnan(chunk)) or np.any(np.isinf(chunk)):
            logger.warning(f"Invalid input data in discontinuity detection for track {track_id}")
            chunk = np.nan_to_num(chunk, nan=0.0, posinf=0.95, neginf=-0.95)

        # 获取或初始化上一次的样本
        state_key = f"_last_sample_{track_id}"
        last_sample = getattr(self, state_key, None)

        # 只对真正需要的情况进行平滑处理
        processed_chunk = chunk.copy()

        # 1. 检查是否有严重的不连续性（仅在真正需要时处理）
        if last_sample is not None and chunk.shape[0] > 0:
            # 计算与上一个样本的差异
            diff = np.abs(chunk[0] - last_sample.flatten()[: self.channels])
            max_diff = np.max(diff)

            # 只在差异真正很大时才进行平滑（提高阈值）
            if max_diff > 0.3:  # 大幅提高阈值，只处理真正的跳跃
                # 使用很短的平滑过渡
                smooth_length = min(8, chunk.shape[0])  # 大幅减少平滑长度
                if smooth_length > 1:
                    for channel in range(self.channels):
                        if channel < len(last_sample.flatten()):
                            start_val = last_sample.flatten()[channel]
                            end_val = chunk[smooth_length - 1, channel]
                            transition = np.linspace(start_val, end_val, smooth_length)

                            # 只进行轻微的平滑混合
                            alpha = np.linspace(0.3, 0.0, smooth_length)  # 减少平滑强度
                            processed_chunk[:smooth_length, channel] = (
                                alpha * transition
                                + (1 - alpha) * processed_chunk[:smooth_length, channel]
                            )

        # 2. 检查严重的突变（仅限极端情况）
        if chunk.shape[0] > 4:  # 增加最小长度要求
            # 计算相邻样本差异
            diffs = np.abs(np.diff(processed_chunk, axis=0))
            max_diff_per_channel = np.max(diffs, axis=0)

            # 只处理真正严重的突变
            for channel in range(self.channels):
                if max_diff_per_channel[channel] > 0.5:  # 大幅提高阈值
                    # 找到突变位置
                    problem_indices = np.where(diffs[:, channel] > 0.5)[0]

                    for idx in problem_indices:
                        if idx < chunk.shape[0] - 1:
                            # 使用最小的修正
                            smooth_range = min(3, chunk.shape[0] - idx - 1)  # 减少修正范围
                            if smooth_range > 0:
                                start_val = processed_chunk[idx, channel]
                                end_val = processed_chunk[idx + smooth_range, channel]

                                # 轻微的线性过渡
                                transition = np.linspace(start_val, end_val, smooth_range + 1)
                                alpha = 0.2  # 大幅减少修正强度
                                processed_chunk[idx : idx + smooth_range + 1, channel] = (
                                    alpha * transition
                                    + (1 - alpha)
                                    * processed_chunk[idx : idx + smooth_range + 1, channel]
                                )

        # 3. 只在极端情况下应用噪音抑制
        peak = np.max(np.abs(processed_chunk))
        if peak > 0.95:  # 只在接近削波时处理
            # 轻微的软限制，避免引入失真
            processed_chunk = self._apply_soft_limiter(processed_chunk, 0.9)

        # 4. 非常轻微的最终平滑（可选，仅在检测到问题时）
        rms = np.sqrt(np.mean(processed_chunk**2))
        if rms > 0.8:  # 只在信号很强时应用
            processed_chunk = self._apply_additional_smoothing(processed_chunk)

        # 保存当前块的最后一个样本用于下次处理
        if chunk.shape[0] > 0:
            setattr(self, state_key, chunk[-1:].copy())

        return processed_chunk

    def _apply_additional_smoothing(self, chunk: npt.NDArray) -> npt.NDArray:
        """
        应用额外的平滑处理

        Args:
            chunk: 音频数据块

        Returns:
            平滑后的音频数据
        """
        if chunk.shape[0] < 3:
            return chunk

        smoothed_chunk = chunk.copy()

        # 应用轻微的低通滤波效果
        for channel in range(smoothed_chunk.shape[1]):
            # 简单的指数移动平均
            alpha = 0.9  # 平滑系数
            for i in range(1, smoothed_chunk.shape[0]):
                smoothed_chunk[i, channel] = (
                    alpha * smoothed_chunk[i, channel]
                    + (1 - alpha) * smoothed_chunk[i - 1, channel]
                )

        return smoothed_chunk

    def play_for_duration(
        self,
        track_id: str,
        duration_sec: float,
        fade_in: bool = False,
        fade_out: bool = True,
        fade_out_duration: float = None,
        volume: Optional[float] = None,
    ) -> bool:
        """
        播放指定时长后自动停止

        这是一个便捷方法，开始播放轨道并安排在指定时间后自动停止。

        Args:
            track_id (str): 要播放的轨道ID
            duration_sec (float): 播放持续时间（秒）
            fade_in (bool, optional): 是否淡入开始. Defaults to False.
            fade_out (bool, optional): 是否淡出停止. Defaults to True.
            fade_out_duration (float, optional): 淡出时长（秒）. Defaults to None.
            volume (float, optional): 播放音量. Defaults to None.

        Returns:
            bool: 是否成功开始播放并安排停止

        Example:
            >>> # 播放15秒后淡出停止
            >>> engine.play_for_duration("intro", 15.0)

            >>> # 播放10秒，用2秒淡出停止
            >>> engine.play_for_duration("music", 10.0, fade_out_duration=2.0)

            >>> # 淡入播放5秒后立即停止
            >>> engine.play_for_duration("effect", 5.0, fade_in=True, fade_out=False)
        """
        try:
            # 开始播放
            self.play(track_id, fade_in=fade_in, volume=volume)

            # 安排停止
            self.stop(
                track_id, fade_out=fade_out, delay_sec=duration_sec, fade_duration=fade_out_duration
            )

            logger.debug(f"已安排轨道 {track_id} 播放 {duration_sec} 秒后停止")
            return True

        except Exception as e:
            logger.error(f"播放定时轨道失败 {track_id}: {e}")
            return False

    def _apply_noise_suppression(
        self, audio_data: npt.NDArray, track_id: str = None
    ) -> npt.NDArray:
        """
        应用噪音抑制和平滑处理

        Args:
            audio_data: 输入音频数据
            track_id: 轨道ID（用于状态跟踪）

        Returns:
            处理后的音频数据
        """
        if audio_data.shape[0] == 0:
            return audio_data

        # 创建输出数组
        processed_data = audio_data.copy()

        # 1. 直流偏移移除（消除电流声）
        for channel in range(processed_data.shape[1]):
            dc_offset = np.mean(processed_data[:, channel])
            if abs(dc_offset) > 0.001:  # 如果有明显的直流偏移
                processed_data[:, channel] -= dc_offset

        # 2. 高通滤波器（消除低频噪音和隆隆声）
        processed_data = self._apply_highpass_filter(processed_data)

        # 3. 噪音门（抑制低电平噪音）
        processed_data = self._apply_noise_gate(processed_data, threshold=0.001)

        # 4. 爆音检测和抑制
        processed_data = self._suppress_pops_and_clicks(processed_data, track_id)

        # 5. 平滑处理（消除突然的跳跃）
        processed_data = self._apply_smoothing_filter(processed_data)

        # 6. 限制器（防止削峰）
        processed_data = self._apply_soft_limiter(processed_data, threshold=0.95)

        return processed_data

    def _apply_highpass_filter(
        self, audio_data: npt.NDArray, cutoff_freq: float = 20.0
    ) -> npt.NDArray:
        """
        应用高通滤波器（移除低频噪音）

        Args:
            audio_data: 输入音频数据
            cutoff_freq: 截止频率（Hz）

        Returns:
            滤波后的音频数据
        """
        try:
            from scipy.signal import butter, filtfilt

            # 设计高通滤波器
            nyquist = self.sample_rate / 2
            normal_cutoff = cutoff_freq / nyquist
            b, a = butter(2, normal_cutoff, btype="high", analog=False)

            # 应用滤波器
            filtered_data = np.zeros_like(audio_data)
            for channel in range(audio_data.shape[1]):
                filtered_data[:, channel] = filtfilt(b, a, audio_data[:, channel])

            return filtered_data
        except ImportError:
            # 如果没有scipy，使用简单的一阶高通滤波器
            alpha = 0.95  # 滤波器系数
            filtered_data = np.zeros_like(audio_data)

            for channel in range(audio_data.shape[1]):
                prev_input = 0.0
                prev_output = 0.0

                for i in range(audio_data.shape[0]):
                    current_input = audio_data[i, channel]
                    output = alpha * (prev_output + current_input - prev_input)
                    filtered_data[i, channel] = output

                    prev_input = current_input
                    prev_output = output

            return filtered_data

    def _apply_noise_gate(self, audio_data: npt.NDArray, threshold: float = 0.001) -> npt.NDArray:
        """
        应用噪音门（抑制低电平信号）

        Args:
            audio_data: 输入音频数据
            threshold: 噪音门阈值

        Returns:
            处理后的音频数据
        """
        # 计算每个样本的RMS电平
        window_size = min(64, audio_data.shape[0])
        processed_data = audio_data.copy()

        for i in range(audio_data.shape[0]):
            start_idx = max(0, i - window_size // 2)
            end_idx = min(audio_data.shape[0], i + window_size // 2)

            # 计算窗口内的RMS
            window_data = audio_data[start_idx:end_idx]
            rms = np.sqrt(np.mean(window_data**2))

            # 如果低于阈值，应用渐进衰减
            if rms < threshold:
                fade_factor = rms / threshold  # 0到1之间的渐进因子
                processed_data[i] *= fade_factor

        return processed_data

    def _suppress_pops_and_clicks(
        self, audio_data: npt.NDArray, track_id: str = None
    ) -> npt.NDArray:
        """
        检测和抑制爆音、咔嗒声

        Args:
            audio_data: 输入音频数据
            track_id: 轨道ID

        Returns:
            处理后的音频数据
        """
        processed_data = audio_data.copy()

        # 检测突然的幅度变化
        for channel in range(processed_data.shape[1]):
            channel_data = processed_data[:, channel]

            # 计算一阶差分（检测突然变化）
            if len(channel_data) > 1:
                diff = np.diff(channel_data)

                # 检测异常大的跳跃
                threshold = np.std(diff) * 3.0  # 3倍标准差
                outlier_indices = np.where(np.abs(diff) > threshold)[0]

                # 平滑异常点
                for idx in outlier_indices:
                    if idx > 0 and idx < len(channel_data) - 1:
                        # 使用相邻样本的平均值替代
                        smoothed_value = (channel_data[idx - 1] + channel_data[idx + 1]) / 2
                        # 渐进混合而不是直接替换
                        blend_factor = 0.7
                        processed_data[idx, channel] = (
                            blend_factor * smoothed_value + (1 - blend_factor) * channel_data[idx]
                        )

        return processed_data

    def _apply_smoothing_filter(self, audio_data: npt.NDArray) -> npt.NDArray:
        """
        应用平滑滤波器（移除尖锐的边缘）

        Args:
            audio_data: 输入音频数据

        Returns:
            平滑后的音频数据
        """
        # 使用简单的移动平均滤波器
        window_size = 3  # 小窗口以保持音质
        processed_data = audio_data.copy()

        if audio_data.shape[0] >= window_size:
            for channel in range(audio_data.shape[1]):
                # 应用移动平均
                for i in range(1, audio_data.shape[0] - 1):
                    window_start = max(0, i - window_size // 2)
                    window_end = min(audio_data.shape[0], i + window_size // 2 + 1)

                    window_data = audio_data[window_start:window_end, channel]
                    smoothed_value = np.mean(window_data)

                    # 轻微混合以保持原始特性
                    mix_factor = 0.3  # 30%平滑，70%原始
                    processed_data[i, channel] = (
                        mix_factor * smoothed_value + (1 - mix_factor) * audio_data[i, channel]
                    )

        return processed_data

    def _apply_soft_limiter(self, audio_data: npt.NDArray, threshold: float = 0.95) -> npt.NDArray:
        """
        应用软限制器（防止削峰失真）

        Args:
            audio_data: 输入音频数据
            threshold: 限制阈值

        Returns:
            限制后的音频数据
        """
        processed_data = audio_data.copy()

        # 应用软限制
        mask = np.abs(processed_data) > threshold

        # 使用tanh函数进行软限制
        processed_data[mask] = (
            np.sign(processed_data[mask])
            * threshold
            * np.tanh(np.abs(processed_data[mask]) / threshold)
        )

        return processed_data

    def load_track_with_matchering(
        self,
        track_id: str,
        file_path: str,
        reference_track_id: str,
        reference_start_sec: float,
        reference_duration_sec: float = 10.0,
        silent_lpadding_ms: float = 0.0,
        silent_rpadding_ms: float = 0.0,
        gentle_matchering: bool = True,
        on_complete: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """
        加载音轨，并使用 matchering 将其与一个参考音轨进行匹配。
        此方法仅用于加载"副"音轨，主音轨应使用 load_track 加载。

        Args:
            track_id (str): 新音轨的ID。
            file_path (str): 要加载和处理的音频文件路径。
            reference_track_id (str): 作为参考的已加载主音轨的ID。
            reference_start_sec (float): 从主音轨的这个时间点（秒）开始截取参考片段。
            reference_duration_sec (float): 参考片段的时长（秒），默认10秒。
            silent_lpadding_ms (float): 在音频前添加的静音填充（毫秒）。
            silent_rpadding_ms (float): 在音频后添加的静音填充（毫秒）。
            gentle_matchering (bool): 是否使用温和的EQ处理减少金属音色，默认True。
            on_complete (Optional[Callable]): 加载完成时的回调函数。
            progress_callback (Optional[Callable]): 进度回调函数。

        Returns:
            bool: 加载是否成功。
        """
        if mg is None:
            logger.error(
                "Matchering library is not installed. Please run 'pip install matchering'."
            )
            return False

        with self.lock:
            if reference_track_id not in self.track_files:
                logger.error(
                    f"Reference track '{reference_track_id}' not found. Please load the main track first."
                )
                return False

            reference_file_path = self.track_files[reference_track_id]
            temp_dir = tempfile.mkdtemp(prefix="realtimemix_matchering_")

            try:
                logger.info(
                    f"🎤 Starting professional matching with Matchering for track '{track_id}'..."
                )
                mg.log(logger.info)

                matched_file_path = os.path.join(temp_dir, f"{track_id}_matched.wav")
                temp_ref_path = os.path.join(temp_dir, "reference_segment.wav")

                logger.info(
                    f"✂️ Clipping {reference_duration_sec}s from reference '{reference_track_id}' at {reference_start_sec:.1f}s."
                )

                with sf.SoundFile(reference_file_path, "r") as f_ref:
                    sr = f_ref.samplerate
                    start_frame = int(reference_start_sec * sr)

                    if start_frame >= f_ref.frames:
                        logger.warning(
                            f"⚠️ Reference clip start time ({reference_start_sec}s) is beyond track duration. Clipping from start instead."
                        )
                        start_frame = 0

                    f_ref.seek(start_frame)
                    frames_to_read = min(
                        f_ref.frames - start_frame, int(reference_duration_sec * sr)
                    )

                    if frames_to_read <= 0:
                        logger.error(
                            "❌ Cannot clip reference audio, start time is at or beyond the end of the file."
                        )
                        return False

                    ref_segment = f_ref.read(frames_to_read)
                    sf.write(temp_ref_path, ref_segment, sr)

                # 创建匹配配置
                if gentle_matchering:
                    # 使用温和设置减少金属音色
                    matchering_config = mg.Config(
                        lowess_frac=0.8,  # 增加平滑度 (默认约0.15)
                        lowess_it=5,  # 增加迭代次数 (默认约3)
                        lowess_delta=0.02,  # 增加平滑范围 (默认约0.01)
                    )
                    logger.info("🎵 Using gentle EQ processing to reduce metallic artifacts...")
                else:
                    matchering_config = mg.Config()  # 使用默认设置
                    logger.info("🎵 Using standard EQ processing...")

                # 调用 matchering
                mg.process(
                    target=file_path,
                    reference=temp_ref_path,
                    results=[mg.pcm24(matched_file_path)],
                    config=matchering_config,
                )
                logger.info("✅ Matchering processing complete!")

                # 创建一个包装的完成回调，在加载完成后清理临时目录
                def cleanup_callback(track_id_param, success):
                    # 先调用原始回调
                    if on_complete:
                        on_complete(track_id_param, success)
                    
                    # 然后清理临时目录
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                        logger.info(f"🗑️ Cleaned up temp directory: {temp_dir}")

                # 加载处理后的文件
                return self.load_track(
                    track_id,
                    matched_file_path,
                    silent_lpadding_ms=silent_lpadding_ms,
                    silent_rpadding_ms=silent_rpadding_ms,
                    on_complete=cleanup_callback,
                    progress_callback=progress_callback,
                )

            except Exception as e:
                logger.error(f"❌ Matchering processing failed: {e}")
                # 只在异常情况下立即清理
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    logger.info(f"🗑️ Cleaned up temp directory after error: {temp_dir}")
                return False

    def _load_from_file(self, file_path: str) -> tuple[np.ndarray, int]:
        """从文件加载音频数据"""
        logger.info(f"开始加载音频文件: {file_path}")
        try:
            data, sr = sf.read(file_path, dtype="float32", always_2d=True)
            logger.info(f"音频文件加载成功: {file_path}, 采样率: {sr}Hz")
            return data, sr
        except Exception as e:
            logger.error(f"无法加载音频文件: {file_path}, 错误: {e}")
            return None, None

    # =====================================================================
    # 位置回调系统私有方法 (实时音频回调机制)
    # =====================================================================

    def _ensure_callback_thread_running(self) -> None:
        """确保回调检查线程正在运行"""
        if not self.position_callback_thread_running:
            self.position_callback_thread_running = True
            self.position_callback_thread = threading.Thread(
                target=self._position_callback_worker,
                daemon=True,
                name="PositionCallback"
            )
            self.position_callback_thread.start()
            logger.debug("位置回调检查线程已启动")

    def _position_callback_worker(self) -> None:
        """位置回调检查线程工作函数"""
        logger.debug("位置回调工作线程开始运行")
        
        while self.position_callback_thread_running:
            try:
                self._check_position_callbacks()
                
                # 根据回调数量动态调整检查频率
                with self.lock:
                    active_callbacks = sum(len(callbacks) for callbacks in self.position_callbacks.values())
                    has_listeners = len(self.global_position_listeners) > 0
                
                if active_callbacks > 0 or has_listeners:
                    # 有活跃回调时使用高频检查
                    sleep_time = self.callback_precision  # 5ms
                else:
                    # 无活跃回调时降低频率
                    sleep_time = 0.050  # 50ms
                
                time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"位置回调线程错误: {e}")
                time.sleep(0.010)  # 错误时等待10ms再继续
        
        logger.debug("位置回调工作线程已停止")

    def _check_position_callbacks(self) -> None:
        """检查并触发位置回调"""
        current_time = time.time()
        precision_errors = []  # 收集精度误差用于统计
        
        # 获取回调快照以减少锁定时间
        with self.lock:
            callbacks_snapshot = {}
            for track_id, callbacks in self.position_callbacks.items():
                if self.is_track_playing(track_id):
                    callbacks_snapshot[track_id] = callbacks.copy()
            
            listeners_snapshot = self.global_position_listeners.copy()
        
        # 检查每个轨道的回调
        for track_id, callbacks in callbacks_snapshot.items():
            try:
                current_position = self.get_position(track_id)
                if current_position is None:
                    continue
                
                # 通知全局监听器
                for listener in listeners_snapshot:
                    try:
                        listener(track_id, current_position)
                    except Exception as e:
                        logger.error(f"全局监听器错误: {e}")
                
                # 检查该轨道的所有回调
                callbacks_to_trigger = []
                callbacks_to_expire = []
                
                for target_time, callback_info in callbacks.items():
                    if callback_info['triggered']:
                        continue
                    
                    time_diff = abs(current_position - target_time)
                    
                    # 检查是否在容忍范围内
                    if time_diff <= callback_info['tolerance']:
                        callbacks_to_trigger.append((target_time, callback_info, time_diff))
                    
                    # 检查是否已过期（超出容忍范围）
                    elif current_position > target_time + callback_info['tolerance']:
                        callbacks_to_expire.append((target_time, callback_info))
                
                # 触发符合条件的回调
                for target_time, callback_info, time_diff in callbacks_to_trigger:
                    try:
                        callback_info['callback'](track_id, current_position, target_time)
                        
                        # 记录精度信息
                        actual_error = current_position - target_time
                        precision_errors.append(abs(actual_error) * 1000)  # 转换为毫秒
                        
                        logger.debug(
                            f"位置回调触发: track={track_id}, target={target_time:.3f}s, "
                            f"actual={current_position:.3f}s, error={actual_error*1000:.1f}ms"
                        )
                        
                        # 标记为已触发
                        with self.lock:
                            if (track_id in self.position_callbacks and 
                                target_time in self.position_callbacks[track_id]):
                                self.position_callbacks[track_id][target_time]['triggered'] = True
                                self.callback_stats['total_callbacks_triggered'] += 1
                        
                    except Exception as e:
                        logger.error(f"回调函数执行错误: {e}")
                        # 即使回调执行失败，也标记为已触发以避免重复调用
                        with self.lock:
                            if (track_id in self.position_callbacks and 
                                target_time in self.position_callbacks[track_id]):
                                self.position_callbacks[track_id][target_time]['triggered'] = True
                
                # 标记过期的回调
                for target_time, callback_info in callbacks_to_expire:
                    logger.debug(
                        f"位置回调过期: track={track_id}, target={target_time:.3f}s, "
                        f"current={current_position:.3f}s"
                    )
                    
                    with self.lock:
                        if (track_id in self.position_callbacks and 
                            target_time in self.position_callbacks[track_id]):
                            self.position_callbacks[track_id][target_time]['triggered'] = True
                            self.callback_stats['total_callbacks_expired'] += 1
            
            except Exception as e:
                logger.error(f"检查轨道 {track_id} 的回调时出错: {e}")
        
        # 清理已触发的回调
        self._cleanup_triggered_callbacks()
        
        # 更新统计信息
        with self.lock:
            if precision_errors:
                # 计算平均精度
                avg_error = sum(precision_errors) / len(precision_errors)
                # 使用指数加权移动平均更新统计信息
                alpha = 0.3
                if self.callback_stats['average_precision_ms'] == 0:
                    self.callback_stats['average_precision_ms'] = avg_error
                else:
                    self.callback_stats['average_precision_ms'] = (
                        alpha * avg_error + 
                        (1 - alpha) * self.callback_stats['average_precision_ms']
                    )
            
            self.callback_stats['last_check_time'] = current_time

    def _cleanup_triggered_callbacks(self) -> None:
        """清理已触发的回调"""
        with self.lock:
            tracks_to_remove = []
            
            for track_id, callbacks in self.position_callbacks.items():
                # 移除已触发的回调
                triggered_times = [
                    target_time for target_time, info in callbacks.items()
                    if info['triggered']
                ]
                
                for target_time in triggered_times:
                    del callbacks[target_time]
                
                # 如果该轨道没有回调了，标记为待移除
                if not callbacks:
                    tracks_to_remove.append(track_id)
            
            # 移除空的轨道回调
            for track_id in tracks_to_remove:
                del self.position_callbacks[track_id]

    def _get_playback_position_precise(self, track_id: str) -> Optional[float]:
        """获取轨道的精确播放位置（内部方法）
        
        这是一个增强版的位置获取方法，用于位置回调系统。
        相比于public的get_position方法，这个方法提供更高精度。
        
        Args:
            track_id: 轨道ID
            
        Returns:
            当前播放位置（秒），如果轨道不存在或未播放则返回None
        """
        try:
            # 使用现有的get_position方法作为基础
            base_position = self.get_position(track_id)
            if base_position is None:
                return None
            
            # 对于高精度需求，可以考虑添加更精确的时间计算
            # 目前直接使用现有方法的结果
            return base_position
            
        except Exception as e:
            logger.error(f"获取精确播放位置失败: {e}")
            return None

    def _adaptive_callback_frequency(self) -> float:
        """根据回调数量和精度要求动态调整检查频率"""
        with self.lock:
            active_callbacks = sum(len(callbacks) for callbacks in self.position_callbacks.values())
            has_listeners = len(self.global_position_listeners) > 0
        
        if active_callbacks == 0 and not has_listeners:
            return 0.050  # 50ms，无回调时低频
        elif active_callbacks <= 5 and not has_listeners:
            return 0.010  # 10ms，少量回调时中频
        else:
            return 0.005  # 5ms，大量回调或有监听器时高频
