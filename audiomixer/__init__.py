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
from typing import Union, Optional, Callable, Dict, Set, Tuple, Any
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
                    
                track_id, source, speed, auto_normalize, on_complete = task
                
                if isinstance(source, str):
                    # File path
                    self._load_track_from_file(track_id, source, speed, auto_normalize, on_complete)
                else:
                    # NumPy array
                    self._process_audio_data(track_id, source, auto_normalize)
                    if on_complete:
                        on_complete(track_id, True)
                
                self.loading_queue.task_done()
            except Exception as e:
                logger.error(f"Error in loading worker: {str(e)}")
                if on_complete:
                    on_complete(track_id, False, str(e))

    def _load_track_from_file(self, track_id: str, file_path: str, speed: float,
                            auto_normalize: bool, on_complete: Optional[Callable]) -> None:
        """Load track from file (internal method)"""
        try:
            logger.info(f"Loading audio file: {file_path} (speed={speed:.2f})")
            
            # Use soundfile to read audio file
            data, sample_rate = sf.read(file_path, dtype='float32', always_2d=True)
            
            # Check sample rate
            if sample_rate != self.sample_rate:
                logger.warning(f"Sample rate mismatch ({sample_rate} vs {self.sample_rate}). Resampling...")
                data = self._resample_audio(data, sample_rate, self.sample_rate)
            
            # Apply speed adjustment
            if abs(speed - 1.0) > 0.01:
                logger.info(f"Applying time stretching (factor={speed:.2f})")
                data = self._time_stretch(data, speed)
            
            # Process audio data
            self._process_audio_data(track_id, data, auto_normalize)
            
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
            resampled = np.zeros((target_length, data.shape[1]), dtype=np.float32)
            for channel in range(data.shape[1]):
                resampled[:, channel] = librosa.resample(
                    data[:, channel], 
                    orig_sr=orig_rate, 
                    target_sr=target_rate
                )
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
                           auto_normalize: bool) -> None:
        """
        Process audio data (internal method)
        :param track_id: Track ID
        :param audio_data: Audio data
        :param auto_normalize: Whether to auto-normalize volume
        """
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
            }
        
        logger.info(f"Track loaded from data: {track_id} ({len(audio_data)} samples)")

    def load_track(self, track_id: str, source: Union[npt.NDArray, str], 
                  speed: float = 1.0, auto_normalize: bool = True, 
                  on_complete: Optional[Callable] = None) -> bool:
        """
        Load track data
        :param track_id: Track ID
        :param source: Audio source (numpy array or file path)
        :param speed: Playback speed factor (0.5-2.0)
        :param auto_normalize: Whether to auto-normalize volume
        :param on_complete: Load completion callback function (track_id, success, error=None)
        :return: Whether loading started successfully
        """
        # Validate speed range
        speed = max(0.1, min(4.0, speed))
        
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
            self.loading_queue.put((track_id, source, speed, auto_normalize, on_complete))
            return True
        elif isinstance(source, str) and os.path.isfile(source):
            # Add to loading queue
            self.loading_queue.put((track_id, source, speed, auto_normalize, on_complete))
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
                track_length = len(self.tracks[track_id])
                position_samples = int(position_sec * self.sample_rate)
                self.track_states[track_id]['position'] = min(position_samples, track_length - 1)
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
                return self.track_states[track_id]['position'] / self.sample_rate
            return 0.0
    
    def get_duration(self, track_id: str) -> float:
        """Get track total duration (seconds)"""
        with self.lock:
            if track_id in self.tracks:
                return len(self.tracks[track_id]) / self.sample_rate
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
                        audio_data, position, speed, state.get('loop', False), frames
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
                                     speed: float, loop: bool, frames: int) -> Tuple[Optional[npt.NDArray], int]:
        """
        Optimized audio chunk extraction method
        :return: (audio chunk, new position) or (None, position) if track ended
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

