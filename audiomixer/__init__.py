import numpy as np
import sounddevice as sd
import threading
import time
from collections import defaultdict
import queue
import atexit
import logging
import soundfile as sf
import os
import gc
import warnings
from typing import Union, Optional, Callable, Dict, Set, Tuple, Any, List
import numpy.typing as npt
from collections import deque


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('AudioEngine')
# Only ignore specific RuntimeWarning
warnings.filterwarnings("ignore", category=RuntimeWarning, message="divide by zero encountered in .*")


class BufferPool:
    """Buffer pool to reduce memory allocation overhead"""
    def __init__(self, buffer_size: int, channels: int, pool_size: int = 8):
        self.buffer_size = buffer_size
        self.channels = channels
        self.pool = deque(maxlen=pool_size)
        self._lock = threading.Lock()
        
        # Pre-allocate buffers
        for _ in range(pool_size):
            self.pool.append(np.zeros((buffer_size, channels), dtype=np.float32))
    
    def get_buffer(self) -> npt.NDArray[np.float32]:
        """Get a buffer from the pool"""
        with self._lock:
            if self.pool:
                buffer = self.pool.popleft()
                buffer.fill(0)  # Clear buffer
                return buffer
        # Pool is empty, create new buffer
        return np.zeros((self.buffer_size, self.channels), dtype=np.float32)
    
    def return_buffer(self, buffer: npt.NDArray[np.float32]) -> None:
        """Return buffer to the pool"""
        with self._lock:
            if len(self.pool) < self.pool.maxlen:
                self.pool.append(buffer)


class AudioProcessor:
    """Audio processor providing efficient audio processing methods"""
    
    @staticmethod
    def apply_fade_inplace(chunk: npt.NDArray, fade_env: npt.NDArray) -> None:
        """Apply fade effect in-place"""
        chunk *= fade_env[:, np.newaxis]
    
    @staticmethod
    def apply_volume_inplace(chunk: npt.NDArray, volume: float) -> None:
        """Apply volume adjustment in-place"""
        if volume != 1.0:
            chunk *= volume
    
    @staticmethod
    def soft_limiter_inplace(buffer: npt.NDArray, threshold: float = 0.98) -> float:
        """Soft limiter to prevent clipping, returns compression ratio"""
        peak = np.max(np.abs(buffer))
        if peak > threshold:
            compression_ratio = threshold / peak
            buffer *= compression_ratio
            return compression_ratio
        return 1.0


class AudioEngine:
    def __init__(self, sample_rate: int = 48000, buffer_size: int = 1024, 
                 channels: int = 2, max_tracks: int = 32, 
                 device: Optional[int] = None, stream_latency: str = 'low'):
        """
        Initialize audio engine
        :param sample_rate: Sample rate (default 48000Hz)
        :param buffer_size: Buffer size (default 1024 frames)
        :param channels: Number of channels (default 2-stereo)
        :param max_tracks: Maximum number of tracks (default 32)
        :param device: Specify audio device ID (None for default device)
        :param stream_latency: Stream latency setting ('low', 'medium', 'high')
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
        self.tracks: Dict[str, npt.NDArray[np.float32]] = {}  # Store original audio data
        self.track_states: Dict[str, Dict[str, Any]] = defaultdict(dict)  # Store track states
        self.active_tracks: Set[str] = set()  # Active tracks set
        self.track_files: Dict[str, str] = {}  # File path cache
        
        # Large file handling
        self.streaming_tracks: Dict[str, Dict[str, Any]] = {}  # 流式加载的音轨
        self.chunk_size: int = 8192  # 分块大小（帧数）
        self.max_memory_usage: int = 512 * 1024 * 1024  # 最大内存使用量（512MB）
        self.large_file_threshold: int = 100 * 1024 * 1024  # 大文件阈值（100MB）
        
        # Thread safety
        self.lock: threading.RLock = threading.RLock()
        self.loading_queue: queue.Queue = queue.Queue(maxsize=5)  # Loading queue to prevent too many simultaneous loads
        
        # Performance monitoring
        self.peak_level: float = 0.0
        self.cpu_usage: float = 0.0  # Using exponential weighted moving average
        self.underrun_count: int = 0
        
        # Initialize optimization components
        self.buffer_pool = BufferPool(buffer_size, channels)
        self.audio_processor = AudioProcessor()
        
        # Pre-compute common values
        self.buffer_duration = buffer_size / sample_rate
        self.fade_step_cache = {}  # Cache fade in/out steps
        
        # Initialize audio system
        self._init_audio_stream(device, stream_latency)
        
        # Start background loading thread
        self.loading_thread: threading.Thread = threading.Thread(target=self._loading_worker, daemon=True)
        self.loading_thread.start()
        
        # Register exit handler
        atexit.register(self.shutdown)
        
        logger.info(f"AudioEngine initialized: {sample_rate}Hz, {buffer_size} buffer, {channels} channels")

    def _init_audio_stream(self, device: Optional[int], latency: str) -> None:
        """Initialize audio output stream"""
        try:
            # Get device info
            if device is None:
                device = sd.default.device[1]
            
            device_info = sd.query_devices(device)
            logger.info(f"Using audio device: {device_info['name']}")
            
            # Ensure device supports required parameters
            if device_info['max_output_channels'] < self.channels:
                raise ValueError(f"Device doesn't support {self.channels} channels")
                
            # Create audio stream
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                blocksize=self.buffer_size,
                channels=self.channels,
                dtype='float32',
                callback=self._audio_callback,
                device=device,
                latency=latency
            )
            
            logger.info("Audio stream initialized")
        except Exception as e:
            logger.error(f"Failed to initialize audio stream: {str(e)}")
            raise RuntimeError("Audio initialization failed") from e

    def _loading_worker(self) -> None:
        """Background loading thread"""
        while True:
            try:
                task = self.loading_queue.get()
                if task is None:  # Stop signal
                    break
                    
                track_id, source, speed, auto_normalize, sample_rate, on_complete, progress_callback = task
                
                if isinstance(source, str):
                    # File path
                    self._load_track_from_file_optimized(track_id, source, speed, auto_normalize, sample_rate, on_complete, progress_callback)
                else:
                    # NumPy array
                    self._process_audio_data(track_id, source, auto_normalize, sample_rate)
                    if on_complete:
                        on_complete(track_id, True)
                
                self.loading_queue.task_done()
            except Exception as e:
                logger.error(f"Error in loading worker: {str(e)}")
                if on_complete:
                    on_complete(track_id, False, str(e))

    def _load_track_from_file_optimized(self, track_id: str, file_path: str, speed: float,
                                      auto_normalize: bool, sample_rate: Optional[int],
                                      on_complete: Optional[Callable], 
                                      progress_callback: Optional[Callable]) -> None:
        """
        优化的文件加载方法，支持大文件分块加载
        :param progress_callback: 进度回调函数(track_id, progress: 0.0-1.0, message)
        """
        try:
            logger.info(f"开始加载音频文件: {file_path} (speed={speed:.2f})")
            
            # 获取文件信息
            with sf.SoundFile(file_path) as f:
                orig_sample_rate = f.samplerate
                total_frames = f.frames
                channels = f.channels
                file_size = os.path.getsize(file_path)
                
                logger.info(f"文件信息: {total_frames}帧, {orig_sample_rate}Hz, {channels}声道, {file_size/(1024*1024):.1f}MB")
                
                if progress_callback:
                    progress_callback(track_id, 0.0, f"分析文件: {file_size/(1024*1024):.1f}MB")
            
            # 判断是否为大文件
            if file_size > self.large_file_threshold:
                logger.info(f"检测到大文件，使用流式加载: {file_size/(1024*1024):.1f}MB")
                self._load_large_file_streaming(track_id, file_path, speed, auto_normalize, 
                                              sample_rate, on_complete, progress_callback)
            else:
                # 小文件使用原有方法
                self._load_track_from_file(track_id, file_path, speed, auto_normalize, 
                                         sample_rate, on_complete)
                
        except Exception as e:
            logger.error(f"文件加载失败: {str(e)}")
            if on_complete:
                on_complete(track_id, False, str(e))

    def _load_large_file_streaming(self, track_id: str, file_path: str, speed: float,
                                 auto_normalize: bool, sample_rate: Optional[int],
                                 on_complete: Optional[Callable], 
                                 progress_callback: Optional[Callable]) -> None:
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
                
                # 分块加载
                chunks = []
                processed_frames = 0
                
                # 计算每次读取的块大小
                chunk_frames = min(self.chunk_size * 64, total_frames // 20)  # 最多分20块
                chunk_frames = max(chunk_frames, self.chunk_size)
                
                while processed_frames < total_frames:
                    # 读取当前块
                    remaining = total_frames - processed_frames
                    current_chunk_frames = min(chunk_frames, remaining)
                    
                    f.seek(processed_frames)
                    chunk_data = f.read(current_chunk_frames, dtype='float32', always_2d=True)
                    
                    if chunk_data.shape[0] == 0:
                        break
                    
                    # 处理当前块
                    if rate_conversion_needed:
                        chunk_data = self._resample_audio(chunk_data, orig_sample_rate, target_sample_rate)
                    
                    if speed_adjustment_needed:
                        chunk_data = self._time_stretch(chunk_data, speed)
                    
                    chunks.append(chunk_data)
                    processed_frames += current_chunk_frames
                    
                    # 更新进度
                    progress = 0.1 + 0.8 * (processed_frames / total_frames)
                    if progress_callback:
                        progress_callback(track_id, progress, 
                                        f"处理中... {processed_frames}/{total_frames}帧 ({progress*100:.1f}%)")
                    
                    # 检查内存使用
                    current_memory = sum(chunk.nbytes for chunk in chunks)
                    if current_memory > self.max_memory_usage:
                        logger.warning(f"内存使用过高: {current_memory/(1024*1024):.1f}MB，开始合并...")
                        # 合并已处理的块
                        if len(chunks) > 1:
                            combined = np.concatenate(chunks, axis=0)
                            chunks = [combined]
                            gc.collect()
                
                if progress_callback:
                    progress_callback(track_id, 0.9, "合并音频数据...")
                
                # 合并所有块
                if chunks:
                    final_data = np.concatenate(chunks, axis=0) if len(chunks) > 1 else chunks[0]
                    
                    # 最终处理
                    self._process_audio_data(track_id, final_data, auto_normalize, target_sample_rate)
                    
                    # 缓存文件路径
                    with self.lock:
                        self.track_files[track_id] = file_path
                    
                    if progress_callback:
                        progress_callback(track_id, 1.0, f"加载完成: {len(final_data)}帧")
                    
                    logger.info(f"大文件加载完成: {track_id} ({len(final_data)}帧)")
                    if on_complete:
                        on_complete(track_id, True)
                else:
                    raise ValueError("无法读取音频数据")
                    
        except Exception as e:
            logger.error(f"大文件加载失败: {str(e)}")
            if on_complete:
                on_complete(track_id, False, str(e))

    def _load_track_from_file(self, track_id: str, file_path: str, speed: float,
                            auto_normalize: bool, sample_rate: Optional[int],
                            on_complete: Optional[Callable]) -> None:
        """Load track from file (internal method)"""
        try:
            logger.info(f"Loading audio file: {file_path} (speed={speed:.2f})")
            
            # Use soundfile to read audio file
            data, orig_sample_rate = sf.read(file_path, dtype='float32', always_2d=True)
            
            # Check sample rate
            if orig_sample_rate != self.sample_rate:
                logger.warning(f"Sample rate mismatch ({orig_sample_rate} vs {self.sample_rate}). Resampling...")
                data = self._resample_audio(data, orig_sample_rate, self.sample_rate)
            
            # Apply speed adjustment
            if abs(speed - 1.0) > 0.01:
                logger.info(f"Applying time stretching (factor={speed:.2f})")
                data = self._time_stretch(data, speed)
            
            # Process audio data
            self._process_audio_data(track_id, data, auto_normalize, sample_rate)
            
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
                    data[:, channel], 
                    orig_sr=orig_rate, 
                    target_sr=target_rate
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
                    data[:, channel],
                    target_rate,
                    orig_rate,
                    axis=0
                )
            return resampled
        except ImportError:
            pass
        
        # Fallback to linear interpolation
        logger.warning("Using linear interpolation for resampling (install librosa or scipy for better quality)")
        orig_times = np.arange(orig_length)
        target_times = np.linspace(0, orig_length-1, target_length)
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
                stretched_data[:, channel] = rb.time_stretch(data[:, channel], self.sample_rate, speed)
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
                    data[:, channel], 
                    rate=speed
                )
            return stretched_data
        except ImportError:
            pass
        
        # Fallback to basic resampling (will change pitch)
        logger.warning("Using basic resampling for time stretching (install pyrubberband or librosa for better quality)")
        orig_length = data.shape[0]
        target_length = int(orig_length / speed)
        
        # Use linear interpolation
        orig_times = np.arange(orig_length)
        target_times = np.linspace(0, orig_length-1, target_length)
        resampled = np.zeros((target_length, data.shape[1]), dtype=np.float32)
        for channel in range(data.shape[1]):
            resampled[:, channel] = np.interp(target_times, orig_times, data[:, channel])
        
        return resampled

    def _process_audio_data(self, track_id: str, audio_data: npt.NDArray, 
                           auto_normalize: bool, track_sample_rate: Optional[int] = None) -> None:
        """
        Process audio data (internal method)
        :param track_id: Track ID
        :param audio_data: Audio data
        :param auto_normalize: Whether to auto-normalize volume
        :param track_sample_rate: Track's specific sample rate (None to use engine's default)
        """
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
                raise ValueError(f"Unsupported channel conversion: {audio_data.shape[1]} -> {self.channels}")
        
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
                'position': 0,
                'volume': 1.0,
                'playing': False,
                'loop': False,
                'paused': False,
                'fade_progress': None,
                'fade_direction': None,  # 'in' or 'out'
                'fade_duration': 0.05,
                'speed': 1.0,  # Playback speed
                'resample_ratio': 1.0,  # For real-time speed adjustment
                'resample_phase': 0.0,  # For real-time speed adjustment
                'sample_rate': track_sample_rate,  # Track's specific sample rate
                'resample_buffer': None,  # Buffer for sample rate conversion
            }
        
        logger.info(f"Track loaded from data: {track_id} ({len(audio_data)} samples, {track_sample_rate}Hz)")

    def load_track(self, track_id: str, source: Union[npt.NDArray, str], 
                  speed: float = 1.0, auto_normalize: bool = True, 
                  sample_rate: Optional[int] = None,
                  on_complete: Optional[Callable] = None,
                  progress_callback: Optional[Callable] = None) -> bool:
        """
        Load track data
        :param track_id: Track ID
        :param source: Audio source (numpy array or file path)
        :param speed: Playback speed factor (0.5-2.0)
        :param auto_normalize: Whether to auto-normalize volume
        :param sample_rate: Track's specific sample rate (None to use engine's default)
        :param on_complete: Load completion callback function (track_id, success, error=None)
        :param progress_callback: Progress callback function (track_id, progress: 0.0-1.0, message)
        :return: Whether loading started successfully
        """
        # Validate speed range
        speed = max(0.1, min(4.0, speed))
        
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
            if len(self.tracks) >= self.max_tracks:
                logger.warning(f"Track limit reached ({self.max_tracks}), cannot load more tracks")
                if on_complete:
                    on_complete(track_id, False, "Track limit reached")
                return False
            
            # If track already exists, unload it first
            if track_id in self.tracks:
                self.unload_track(track_id)
        
        # Handle different source types
        if isinstance(source, np.ndarray):
            # Add to loading queue (background processing)
            self.loading_queue.put((track_id, source, speed, auto_normalize, sample_rate, on_complete, progress_callback))
            return True
        elif isinstance(source, str) and os.path.isfile(source):
            # Add to loading queue
            self.loading_queue.put((track_id, source, speed, auto_normalize, sample_rate, on_complete, progress_callback))
            return True
        else:
            error = f"Unsupported source type: {type(source)}"
            logger.error(error)
            if on_complete:
                on_complete(track_id, False, error)
            return False

    def unload_track(self, track_id: str) -> bool:
        """Unload track and free memory"""
        with self.lock:
            if track_id in self.tracks:
                # If playing, stop it first
                if self.track_states[track_id].get('playing', False):
                    self.stop(track_id, fade_out=False)
                
                # Free resources
                del self.tracks[track_id]
                del self.track_states[track_id]
                
                if track_id in self.active_tracks:
                    self.active_tracks.remove(track_id)
                
                if track_id in self.track_files:
                    del self.track_files[track_id]
                
                logger.info(f"Track unloaded: {track_id}")
                return True
            return False

    def play(self, track_id: str, fade_in: bool = False, loop: bool = False, 
            seek: Optional[float] = None, volume: Optional[float] = None) -> None:
        """
        Play track
        :param track_id: Track ID
        :param fade_in: Whether to use fade-in effect
        :param loop: Whether to loop playback
        :param seek: Start position (seconds)
        :param volume: Initial volume (0.0-1.0)
        """
        with self.lock:
            if track_id not in self.tracks:
                logger.warning(f"Track not found: {track_id}")
                return
            
            state = self.track_states[track_id]
            
            # Set playback position
            if seek is not None:
                state['position'] = int(seek * self.sample_rate)
            
            # Set volume
            if volume is not None:
                state['volume'] = max(0.0, min(1.0, volume))
            
            # Set loop
            state['loop'] = loop
            
            # Reset pause state
            state['paused'] = False
            
            # Handle fade-in
            if fade_in:
                state['fade_progress'] = 0.0
                state['fade_direction'] = 'in'
            else:
                state['fade_progress'] = None
                state['fade_direction'] = None
            
            # Activate track
            state['playing'] = True
            self.active_tracks.add(track_id)
            
            logger.debug(f"Playing track: {track_id} (fade_in={fade_in}, loop={loop}, seek={seek})")
    
    def set_speed(self, track_id: str, speed: float) -> bool:
        """
        Set playback speed (real-time adjustment)
        :param track_id: Track ID
        :param speed: Speed factor (0.5-2.0)
        :return: Whether speed was set successfully
        """
        with self.lock:
            if track_id not in self.track_states:
                return False
            
            speed = max(0.1, min(4.0, speed))
            self.track_states[track_id]['speed'] = speed
            logger.info(f"Set speed for {track_id}: {speed:.2f}")
            return True
    
    def stop(self, track_id: str, fade_out: bool = True) -> None:
        """
        Stop track playback
        :param track_id: Track ID
        :param fade_out: Whether to use fade-out effect
        """
        with self.lock:
            if track_id not in self.track_states:
                return
            
            state = self.track_states[track_id]
            
            if not state.get('playing', False):
                return
            
            if fade_out and state.get('fade_direction') is None:
                # Start fade-out
                state['fade_progress'] = 1.0
                state['fade_direction'] = 'out'
            elif not fade_out:
                # Stop immediately
                state['playing'] = False
                state['paused'] = False
                self.active_tracks.discard(track_id)
                state['position'] = 0
                state['fade_progress'] = None
                state['fade_direction'] = None
                state['resample_phase'] = 0.0  # Reset resample state
                
                logger.debug(f"Stopped track: {track_id}")
    
    def pause(self, track_id: str) -> None:
        """Pause track"""
        with self.lock:
            if track_id in self.track_states:
                state = self.track_states[track_id]
                if state.get('playing', False):
                    state['paused'] = True
                    logger.debug(f"Paused track: {track_id}")
    
    def resume(self, track_id: str) -> None:
        """Resume track playback"""
        with self.lock:
            if track_id in self.track_states:
                state = self.track_states[track_id]
                if state.get('playing', False) and state.get('paused', False):
                    state['paused'] = False
                    logger.debug(f"Resumed track: {track_id}")
    
    def set_volume(self, track_id: str, volume: float) -> None:
        """Set track volume (0.0-1.0)"""
        with self.lock:
            if track_id in self.track_states:
                self.track_states[track_id]['volume'] = max(0.0, min(1.0, volume))
    
    def set_loop(self, track_id: str, loop: bool) -> bool:
        """
        Dynamically set track loop state
        :param track_id: Track ID
        :param loop: Whether to loop playback
        :return: Whether loop was set successfully
        """
        with self.lock:
            if track_id in self.track_states:
                self.track_states[track_id]['loop'] = loop
                logger.debug(f"Set loop for {track_id}: {loop}")
                return True
            return False
    
    def seek(self, track_id: str, position_sec: float) -> None:
        """Seek to specified position (seconds)"""
        with self.lock:
            if track_id in self.track_states:
                state = self.track_states[track_id]
                track_length = len(self.tracks[track_id])
                position_samples = int(position_sec * state['sample_rate'])
                state['position'] = min(position_samples, track_length - 1)
                logger.debug(f"Seek track {track_id} to {position_sec:.2f}s")
    
    def set_fade_duration(self, track_id: str, duration_sec: float) -> None:
        """Set fade in/out duration (seconds)"""
        with self.lock:
            if track_id in self.track_states:
                self.track_states[track_id]['fade_duration'] = max(0.01, duration_sec)
    
    def get_position(self, track_id: str) -> float:
        """Get current playback position (seconds)"""
        with self.lock:
            if track_id in self.track_states:
                state = self.track_states[track_id]
                return state['position'] / state['sample_rate']
            return 0.0
    
    def get_duration(self, track_id: str) -> float:
        """Get track total duration (seconds)"""
        with self.lock:
            if track_id in self.tracks and track_id in self.track_states:
                state = self.track_states[track_id]
                return len(self.tracks[track_id]) / state['sample_rate']
            return 0.0

    def start(self) -> None:
        """Start audio engine"""
        if not self.is_running:
            try:
                self.stream.start()
                self.is_running = True
                logger.info("Audio engine started")
            except Exception as e:
                logger.error(f"Failed to start audio engine: {str(e)}")
                self.is_running = False
    
    def shutdown(self) -> None:
        """Shutdown audio engine and free resources"""
        if self.is_running:
            try:
                # Stop all tracks
                with self.lock:
                    for track_id in list(self.active_tracks):
                        self.stop(track_id, fade_out=False)
                
                # Stop loading thread
                self.loading_queue.put(None)
                self.loading_thread.join(timeout=1.0)
                
                # Close audio stream
                self.stream.stop()
                self.stream.close()
                self.is_running = False
                
                # Free memory
                self.tracks.clear()
                self.track_states.clear()
                self.active_tracks.clear()
                self.track_files.clear()
                
                # Clean optimization components
                self.fade_step_cache.clear()
                self.buffer_pool.pool.clear()
                
                gc.collect()
                
                logger.info("Audio engine shutdown complete")
            except Exception as e:
                logger.error(f"Error during shutdown: {str(e)}")

    def _audio_callback(self, outdata: npt.NDArray, frames: int, 
                       time_info: sd.CallbackFlags, status: sd.CallbackFlags) -> None:
        """
        Optimized audio callback function - core audio processing
        """
        start_time = time.perf_counter()
        
        # Handle stream status
        if status:
            if status.input_underflow or status.output_underflow:
                self.underrun_count += 1
        
        # Get mix buffer from buffer pool
        mix_buffer = self.buffer_pool.get_buffer()
        
        try:
            peak_level = 0.0
            
            # Get snapshot of current active tracks (avoid processing audio within lock)
            with self.lock:
                active_tracks = list(self.active_tracks)
                track_states_snapshot = {tid: self.track_states[tid].copy() for tid in active_tracks}
            
            # Process each active track
            for track_id in active_tracks:
                try:
                    state = track_states_snapshot[track_id]
                    
                    # Skip paused tracks
                    if state.get('paused', False):
                        continue
                    
                    # Get track data
                    audio_data = self.tracks[track_id]
                    position = state['position']
                    speed = state.get('speed', 1.0)
                    
                    # Extract audio chunk
                    chunk, new_position = self._extract_audio_chunk_optimized(
                        audio_data, position, speed, state.get('loop', False), frames, state['sample_rate']
                    )
                    
                    if chunk is None:
                        state['playing'] = False
                        continue
                    
                    # Update position
                    state['position'] = new_position
                    
                    # Apply audio effects
                    self._apply_audio_effects_optimized(chunk, state, frames)
                    
                    # Mix to main buffer
                    if chunk.shape[0] == frames:
                        mix_buffer += chunk
                    else:
                        # Handle length mismatch
                        min_frames = min(chunk.shape[0], frames)
                        mix_buffer[:min_frames] += chunk[:min_frames]
                    
                    # Update peak level
                    chunk_peak = np.max(np.abs(chunk))
                    peak_level = max(peak_level, chunk_peak)
                        
                except Exception as e:
                    logger.error(f"Error processing track {track_id}: {str(e)}")
                    state['playing'] = False
                    continue
            
            # Apply main output processing - soft limiter
            self.audio_processor.soft_limiter_inplace(mix_buffer, 0.98)
            
            # Update performance metrics
            self.peak_level = max(self.peak_level, peak_level)
            
            # Copy data to output buffer
            outdata[:] = mix_buffer
            
            # Asynchronously update states to reduce callback latency
            self._update_track_states_async(track_states_snapshot)
            
        finally:
            # Return buffer to pool
            self.buffer_pool.return_buffer(mix_buffer)
        
        # Calculate CPU usage (exponential weighted moving average)
        process_time = time.perf_counter() - start_time
        current_cpu_usage = (process_time / self.buffer_duration) * 100
        
        # Use exponential weighted moving average (EWMA) to smooth CPU usage
        alpha = 0.2  # Smoothing factor
        self.cpu_usage = alpha * current_cpu_usage + (1 - alpha) * self.cpu_usage

    def get_performance_stats(self) -> Dict[str, float]:
        """Get performance statistics"""
        return {
            'peak_level': self.peak_level,
            'cpu_usage': self.cpu_usage,
            'underrun_count': self.underrun_count,
            'active_tracks': len(self.active_tracks),
            'total_tracks': len(self.tracks),
            'loading_queue': self.loading_queue.qsize()
        }
    
    def clear_all_tracks(self) -> None:
        """Clear all tracks"""
        with self.lock:
            for track_id in list(self.tracks.keys()):
                self.unload_track(track_id)
            logger.info("All tracks cleared")

    def _extract_audio_chunk_optimized(self, audio_data: npt.NDArray, position: int, 
                                     speed: float, loop: bool, frames: int,
                                     track_sample_rate: int) -> Tuple[Optional[npt.NDArray], int]:
        """
        Optimized audio chunk extraction method with sample rate conversion
        :param track_sample_rate: Track's sample rate
        :return: (audio chunk, new position) or (None, position) if track ended
        """
        # 计算采样率转换比例
        rate_ratio = track_sample_rate / self.sample_rate
        
        # 如果采样率相同，使用原有的快速路径
        if abs(rate_ratio - 1.0) < 0.001:
            return self._extract_audio_chunk_original(audio_data, position, speed, loop, frames)
        
        # 需要采样率转换的情况
        # 计算在原始采样率下需要读取的帧数
        source_frames_needed = int(frames * rate_ratio * speed)
        remaining = len(audio_data) - position
        
        if remaining <= 0:
            if loop:
                position = 0
                remaining = len(audio_data)
            else:
                return None, position
        
        # 提取音频数据
        read_frames = min(source_frames_needed, remaining)
        chunk = audio_data[position:position+read_frames].copy()
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
        
        # 采样率转换
        if chunk.shape[0] > 0:
            resampled_chunk = self._resample_chunk_realtime(chunk, rate_ratio, frames)
            return resampled_chunk, new_position
        
        return None, new_position
    
    def _extract_audio_chunk_original(self, audio_data: npt.NDArray, position: int, 
                                    speed: float, loop: bool, frames: int) -> Tuple[Optional[npt.NDArray], int]:
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
                                    full_chunk[offset:offset+copy_frames] = audio_data[:copy_frames]
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
                chunk = audio_data[position:position+render_frames].copy()
                new_position = position + render_frames
                
                # Handle looping
                if new_position >= len(audio_data) and loop:
                    loop_frames = frames - render_frames
                    if loop_frames > 0:
                        # Use pre-allocated buffer to avoid concatenate
                        full_chunk = np.zeros((frames, self.channels), dtype=np.float32)
                        full_chunk[:render_frames] = chunk
                        
                        loop_chunk = audio_data[:min(loop_frames, len(audio_data))]
                        full_chunk[render_frames:render_frames+len(loop_chunk)] = loop_chunk
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
    
    def _resample_chunk_realtime(self, chunk: npt.NDArray, rate_ratio: float, target_frames: int) -> npt.NDArray:
        """
        Real-time audio chunk resampling
        :param chunk: Input audio chunk
        :param rate_ratio: Source sample rate / target sample rate
        :param target_frames: Target frame count
        :return: Resampled audio chunk
        """
        if chunk.shape[0] == 0:
            return np.zeros((target_frames, self.channels), dtype=np.float32)
        
        # 如果比例接近1.0，直接使用线性插值
        if abs(rate_ratio - 1.0) < 0.01:
            if chunk.shape[0] == target_frames:
                return chunk
            else:
                # 简单的线性插值重采样
                orig_times = np.arange(chunk.shape[0])
                target_times = np.linspace(0, chunk.shape[0]-1, target_frames)
                resampled = np.zeros((target_frames, self.channels), dtype=np.float32)
                for channel in range(self.channels):
                    resampled[:, channel] = np.interp(target_times, orig_times, chunk[:, channel])
                return resampled
        
        # 更复杂的重采样情况
        try:
            # 尝试使用高质量重采样
            import scipy.signal
            resampled = np.zeros((target_frames, self.channels), dtype=np.float32)
            for channel in range(self.channels):
                # 使用scipy的resample函数
                resampled[:, channel] = scipy.signal.resample(chunk[:, channel], target_frames)
            return resampled
        except ImportError:
            # 降级到线性插值
            if chunk.shape[0] > 1:
                orig_times = np.arange(chunk.shape[0])
                target_times = np.linspace(0, chunk.shape[0]-1, target_frames)
                resampled = np.zeros((target_frames, self.channels), dtype=np.float32)
                for channel in range(self.channels):
                    resampled[:, channel] = np.interp(target_times, orig_times, chunk[:, channel])
                return resampled
            else:
                # 如果源数据太少，用重复或零填充
                resampled = np.zeros((target_frames, self.channels), dtype=np.float32)
                if chunk.shape[0] > 0:
                    resampled[:] = chunk[0]  # 重复第一个样本
                return resampled
    
    def _extract_audio_chunk_with_speed(self, audio_data: npt.NDArray, position: int, 
                                       speed: float, loop: bool, frames: int) -> Tuple[Optional[npt.NDArray], int]:
        """Extract audio chunk with speed adjustment"""
        read_frames = int(frames * speed)
        remaining = len(audio_data) - position
        
        if remaining >= read_frames:
            chunk = audio_data[position:position+read_frames]
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
            target_times = np.linspace(0, len(chunk)-1, frames)
            resampled_chunk = np.zeros((frames, self.channels), dtype=np.float32)
            for channel in range(self.channels):
                resampled_chunk[:, channel] = np.interp(
                    target_times, orig_times, chunk[:, channel]
                )
            return resampled_chunk, new_position
        
        return chunk if chunk.shape[0] > 0 else None, new_position
    
    def _apply_audio_effects_optimized(self, chunk: npt.NDArray, state: Dict[str, Any], frames: int) -> None:
        """Optimized audio effects application"""
        # Apply volume
        volume = state.get('volume', 1.0)
        if volume != 1.0:
            self.audio_processor.apply_volume_inplace(chunk, volume)
        
        # Handle fade in/out
        fade_progress = state.get('fade_progress')
        fade_direction = state.get('fade_direction')
        fade_duration = state.get('fade_duration', 0.05)
        
        if fade_direction and fade_progress is not None:
            # Generate or cache fade in/out steps
            fade_key = (fade_duration, frames)
            if fade_key not in self.fade_step_cache:
                self.fade_step_cache[fade_key] = frames / (fade_duration * self.sample_rate)
            
            fade_step = self.fade_step_cache[fade_key]
            
            if fade_direction == 'in':
                fade_end = min(1.0, fade_progress + fade_step)
                fade_env = np.linspace(fade_progress, fade_end, frames)
                self.audio_processor.apply_fade_inplace(chunk, fade_env)
                
                if fade_end >= 1.0:
                    state['fade_progress'] = None
                    state['fade_direction'] = None
                else:
                    state['fade_progress'] = fade_end
            
            elif fade_direction == 'out':
                fade_end = max(0.0, fade_progress - fade_step)
                fade_env = np.linspace(fade_progress, fade_end, frames)
                self.audio_processor.apply_fade_inplace(chunk, fade_env)
                
                if fade_end <= 0.0:
                    state['playing'] = False
                    state['fade_progress'] = None
                    state['fade_direction'] = None
                else:
                    state['fade_progress'] = fade_end
    
    def _update_track_states_async(self, states_snapshot: Dict[str, Dict[str, Any]]) -> None:
        """Asynchronously update track states to reduce audio callback latency"""
        def update_states():
            with self.lock:
                for track_id, state_snapshot in states_snapshot.items():
                    if track_id in self.track_states:
                        # Update key states
                        current_state = self.track_states[track_id]
                        current_state['position'] = state_snapshot['position']
                        
                        # Update fade in/out states
                        if 'fade_progress' in state_snapshot:
                            current_state['fade_progress'] = state_snapshot['fade_progress']
                        if 'fade_direction' in state_snapshot:
                            current_state['fade_direction'] = state_snapshot['fade_direction']
                        
                        # Handle playback end
                        if not state_snapshot.get('playing', True):
                            current_state['playing'] = False
                            self.active_tracks.discard(track_id)
                            logger.debug(f"Track finished: {track_id}")
        
        # Use daemon thread to execute state update
        threading.Thread(target=update_states, daemon=True).start()

    def get_track_info(self, track_id: str) -> Optional[Dict[str, Any]]:
        """
        获取音轨详细信息
        :param track_id: 音轨ID
        :return: 音轨信息字典，如果音轨不存在则返回None
        """
        with self.lock:
            if track_id not in self.tracks:
                return None
            
            state = self.track_states[track_id]
            audio_data = self.tracks[track_id]
            
            return {
                'track_id': track_id,
                'duration': len(audio_data) / state['sample_rate'],
                'position': state['position'] / state['sample_rate'],
                'volume': state.get('volume', 1.0),
                'playing': state.get('playing', False),
                'paused': state.get('paused', False),
                'loop': state.get('loop', False),
                'speed': state.get('speed', 1.0),
                'fade_direction': state.get('fade_direction'),
                'fade_duration': state.get('fade_duration', 0.05),
                'file_path': self.track_files.get(track_id),
                'samples': len(audio_data),
                'channels': audio_data.shape[1],
                'sample_rate': state['sample_rate'],
                'engine_sample_rate': self.sample_rate,
                'sample_rate_ratio': state['sample_rate'] / self.sample_rate,
            }
    
    def list_tracks(self) -> List[Dict[str, Any]]:
        """
        获取所有已加载音轨的列表
        :return: 音轨信息列表
        """
        with self.lock:
            tracks_info = []
            for track_id in self.tracks.keys():
                info = self.get_track_info(track_id)
                if info:
                    tracks_info.append(info)
            return tracks_info
    
    def get_playing_tracks(self) -> List[str]:
        """
        获取所有正在播放的音轨ID列表
        :return: 正在播放的音轨ID列表
        """
        with self.lock:
            return [track_id for track_id in self.active_tracks 
                   if self.track_states[track_id].get('playing', False) 
                   and not self.track_states[track_id].get('paused', False)]
    
    def get_paused_tracks(self) -> List[str]:
        """
        获取所有暂停的音轨ID列表
        :return: 暂停的音轨ID列表
        """
        with self.lock:
            return [track_id for track_id, state in self.track_states.items()
                   if state.get('playing', False) and state.get('paused', False)]
    
    def pause_all_tracks(self) -> List[str]:
        """
        暂停所有正在播放的音轨
        :return: 被暂停的音轨ID列表
        """
        paused_tracks = []
        with self.lock:
            for track_id in list(self.active_tracks):
                state = self.track_states[track_id]
                if state.get('playing', False) and not state.get('paused', False):
                    state['paused'] = True
                    paused_tracks.append(track_id)
            
            if paused_tracks:
                logger.info(f"暂停了 {len(paused_tracks)} 个音轨: {paused_tracks}")
        
        return paused_tracks
    
    def resume_all_tracks(self) -> List[str]:
        """
        恢复所有暂停的音轨
        :return: 被恢复的音轨ID列表
        """
        resumed_tracks = []
        with self.lock:
            for track_id, state in self.track_states.items():
                if state.get('playing', False) and state.get('paused', False):
                    state['paused'] = False
                    resumed_tracks.append(track_id)
            
            if resumed_tracks:
                logger.info(f"恢复了 {len(resumed_tracks)} 个音轨: {resumed_tracks}")
        
        return resumed_tracks
    
    def stop_all_tracks(self, fade_out: bool = True) -> List[str]:
        """
        停止所有正在播放的音轨
        :param fade_out: 是否使用淡出效果
        :return: 被停止的音轨ID列表
        """
        stopped_tracks = []
        with self.lock:
            for track_id in list(self.active_tracks):
                if self.track_states[track_id].get('playing', False):
                    self.stop(track_id, fade_out=fade_out)
                    stopped_tracks.append(track_id)
            
            if stopped_tracks:
                logger.info(f"停止了 {len(stopped_tracks)} 个音轨: {stopped_tracks}")
        
        return stopped_tracks
    
    def remove_track(self, track_id: str, fade_out: bool = True) -> bool:
        """
        移除音轨（先停止播放，然后卸载）
        :param track_id: 音轨ID
        :param fade_out: 是否使用淡出效果停止播放
        :return: 是否成功移除
        """
        with self.lock:
            if track_id not in self.tracks:
                logger.warning(f"音轨不存在: {track_id}")
                return False
            
            # 如果正在播放，先停止
            if self.track_states[track_id].get('playing', False):
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
        :param track_id: 音轨ID
        :return: 是否正在播放
        """
        with self.lock:
            if track_id not in self.track_states:
                return False
            state = self.track_states[track_id]
            return state.get('playing', False) and not state.get('paused', False)
    
    def is_track_paused(self, track_id: str) -> bool:
        """
        检查音轨是否暂停
        :param track_id: 音轨ID
        :return: 是否暂停
        """
        with self.lock:
            if track_id not in self.track_states:
                return False
            state = self.track_states[track_id]
            return state.get('playing', False) and state.get('paused', False)
    
    def is_track_loaded(self, track_id: str) -> bool:
        """
        检查音轨是否已加载
        :param track_id: 音轨ID
        :return: 是否已加载
        """
        with self.lock:
            return track_id in self.tracks
    
    def get_track_count(self) -> Dict[str, int]:
        """
        获取音轨数量统计
        :return: 包含各种状态音轨数量的字典
        """
        with self.lock:
            total = len(self.tracks)
            playing = len([t for t in self.active_tracks 
                          if self.track_states[t].get('playing', False) 
                          and not self.track_states[t].get('paused', False)])
            paused = len([t for t, s in self.track_states.items()
                         if s.get('playing', False) and s.get('paused', False)])
            
            return {
                'total': total,
                'playing': playing,
                'paused': paused,
                'stopped': total - playing - paused,
                'max_tracks': self.max_tracks,
                'available_slots': self.max_tracks - total
            }
    
    def set_track_sample_rate(self, track_id: str, sample_rate: int) -> bool:
        """
        设置音轨的采样率（实时调整）
        :param track_id: 音轨ID
        :param sample_rate: 新的采样率
        :return: 是否设置成功
        """
        if sample_rate < 8000 or sample_rate > 192000:
            logger.error(f"Invalid sample rate: {sample_rate}Hz (must be between 8000-192000Hz)")
            return False
        
        with self.lock:
            if track_id not in self.track_states:
                return False
            
            old_sample_rate = self.track_states[track_id]['sample_rate']
            self.track_states[track_id]['sample_rate'] = sample_rate
            
            # 调整播放位置以保持相同的时间位置
            current_time = self.track_states[track_id]['position'] / old_sample_rate
            self.track_states[track_id]['position'] = int(current_time * sample_rate)
            
            logger.info(f"Set sample rate for {track_id}: {old_sample_rate}Hz -> {sample_rate}Hz")
            return True
    
    def get_track_sample_rate(self, track_id: str) -> Optional[int]:
        """
        获取音轨的采样率
        :param track_id: 音轨ID
        :return: 采样率，如果音轨不存在则返回None
        """
        with self.lock:
            if track_id in self.track_states:
                return self.track_states[track_id]['sample_rate']
            return None
    
    def list_tracks_by_sample_rate(self) -> Dict[int, List[str]]:
        """
        按采样率分组列出所有音轨
        :return: 以采样率为键，音轨ID列表为值的字典
        """
        with self.lock:
            tracks_by_rate = {}
            for track_id, state in self.track_states.items():
                sample_rate = state['sample_rate']
                if sample_rate not in tracks_by_rate:
                    tracks_by_rate[sample_rate] = []
                tracks_by_rate[sample_rate].append(track_id)
            return tracks_by_rate
    
    def get_sample_rate_statistics(self) -> Dict[str, Any]:
        """
        获取采样率统计信息
        :return: 采样率统计信息
        """
        with self.lock:
            stats = {
                'engine_sample_rate': self.sample_rate,
                'unique_sample_rates': set(),
                'tracks_by_rate': {},
                'total_tracks': len(self.tracks),
                'native_rate_tracks': 0,  # 与引擎采样率相同的音轨数量
                'conversion_needed_tracks': 0,  # 需要转换的音轨数量
            }
            
            for track_id, state in self.track_states.items():
                sample_rate = state['sample_rate']
                stats['unique_sample_rates'].add(sample_rate)
                
                if sample_rate not in stats['tracks_by_rate']:
                    stats['tracks_by_rate'][sample_rate] = {
                        'count': 0,
                        'track_ids': []
                    }
                
                stats['tracks_by_rate'][sample_rate]['count'] += 1
                stats['tracks_by_rate'][sample_rate]['track_ids'].append(track_id)
                
                if sample_rate == self.sample_rate:
                    stats['native_rate_tracks'] += 1
                else:
                    stats['conversion_needed_tracks'] += 1
            
            stats['unique_sample_rates'] = sorted(list(stats['unique_sample_rates']))
            return stats

    def get_memory_usage(self) -> Dict[str, Any]:
        """
        获取内存使用统计
        :return: 内存使用信息
        """
        with self.lock:
            total_memory = 0
            track_memory = {}
            
            for track_id, audio_data in self.tracks.items():
                memory_bytes = audio_data.nbytes
                total_memory += memory_bytes
                track_memory[track_id] = {
                    'size_mb': memory_bytes / (1024 * 1024),
                    'samples': len(audio_data),
                    'channels': audio_data.shape[1],
                    'dtype': str(audio_data.dtype)
                }
            
            return {
                'total_memory_mb': total_memory / (1024 * 1024),
                'max_memory_mb': self.max_memory_usage / (1024 * 1024),
                'track_count': len(self.tracks),
                'track_memory': track_memory,
                'large_file_threshold_mb': self.large_file_threshold / (1024 * 1024),
                'chunk_size_frames': self.chunk_size
            }

    def set_large_file_settings(self, threshold_mb: int = 100, 
                               max_memory_mb: int = 512, 
                               chunk_size_frames: int = 8192) -> None:
        """
        设置大文件处理参数
        :param threshold_mb: 大文件阈值（MB）
        :param max_memory_mb: 最大内存使用量（MB）
        :param chunk_size_frames: 分块大小（帧数）
        """
        self.large_file_threshold = threshold_mb * 1024 * 1024
        self.max_memory_usage = max_memory_mb * 1024 * 1024
        self.chunk_size = chunk_size_frames
        
        logger.info(f"大文件设置更新: 阈值={threshold_mb}MB, 最大内存={max_memory_mb}MB, 块大小={chunk_size_frames}帧")

    def optimize_memory(self) -> Dict[str, Any]:
        """
        内存优化：清理不必要的缓存和进行垃圾回收
        :return: 优化结果统计
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
                self.buffer_pool.pool.append(np.zeros((self.buffer_size, self.channels), dtype=np.float32))
        
        # 强制垃圾回收
        gc.collect()
        
        after_stats = self.get_memory_usage()
        
        result = {
            'cache_entries_cleared': cache_cleared,
            'buffer_pool_cleared': pool_cleared,
            'memory_before_mb': before_stats['total_memory_mb'],
            'memory_after_mb': after_stats['total_memory_mb'],
            'memory_freed_mb': before_stats['total_memory_mb'] - after_stats['total_memory_mb']
        }
        
        logger.info(f"内存优化完成: 释放{result['memory_freed_mb']:.1f}MB, 清理{cache_cleared}个缓存项")
        return result

