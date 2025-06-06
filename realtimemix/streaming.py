from .utils import *


class StreamingTrackData:
    """
    流式音频轨道数据管理类

    该类负责管理大型音频文件的流式加载和播放，通过分块加载和缓冲区管理
    来避免将整个音频文件加载到内存中，适用于长音频文件的播放。

    主要功能：
    - 流式音频文件加载
    - 音频缓冲区管理
    - 实时重采样和声道转换
    - 跳转和位置管理
    - 性能监控

    Attributes:
        track_id (str): 轨道唯一标识符
        file_path (str): 音频文件路径
        engine_sample_rate (int): 引擎采样率
        engine_channels (int): 引擎声道数
        buffer_seconds (float): 缓冲区时长（秒）
        audio_buffer (deque): 音频数据缓冲区
        buffer_lock (threading.RLock): 缓冲区访问锁
        max_buffer_frames (int): 最大缓冲帧数
        file_sample_rate (int): 文件原始采样率
        file_channels (int): 文件原始声道数
        total_frames (int): 文件总帧数
        duration (float): 文件时长（秒）
        file_position (int): 文件读取位置
        playback_position (int): 播放位置
        loader_thread (threading.Thread): 加载线程
        loading (bool): 是否正在加载
        eof_reached (bool): 是否到达文件末尾
        seek_requested (tuple): 跳转请求
        buffer_underruns (int): 缓冲区下溢次数
        chunks_loaded (int): 已加载的块数
        _last_sample (np.ndarray): 用于平滑过渡的音频样本
    """

    def __init__(
        self,
        track_id: str,
        file_path: str,
        engine_sample_rate: int = 48000,
        engine_channels: int = 2,
        buffer_seconds: float = 15.0,
    ):
        """
        初始化流式轨道数据管理器

        Args:
            track_id (str): 轨道唯一标识符
            file_path (str): 音频文件路径
            engine_sample_rate (int, optional): 引擎采样率. Defaults to 48000.
            engine_channels (int, optional): 引擎声道数. Defaults to 2.
            buffer_seconds (float, optional): 缓冲区时长（秒）. Defaults to 15.0.


        Raises:
            Exception: 如果文件无法读取或格式不支持

        Example:
            >>> streaming_track = StreamingTrackData(
            ...     track_id="bgm1",
            ...     file_path="/path/to/audio.wav",
            ...     engine_sample_rate=48000,
            ...     engine_channels=2,
            ...     buffer_seconds=15.0
            ... )
        """
        self.track_id = track_id
        self.file_path = file_path
        self.engine_sample_rate = engine_sample_rate
        self.engine_channels = engine_channels
        self.buffer_seconds = buffer_seconds

        # 音频缓冲区 - 使用deque进行高效的FIFO操作
        self.audio_buffer = deque()
        self.buffer_lock = threading.RLock()
        self.max_buffer_frames = int(buffer_seconds * engine_sample_rate)

        # 文件信息
        self.file_sample_rate = 44100
        self.file_channels = 2
        self.total_frames = 0
        self.duration = 0.0

        # 位置状态
        self.file_position = 0  # 文件读取位置（文件采样率下的帧数）
        self.playback_position = 0  # 播放位置（引擎采样率下的帧数）

        # 流式加载控制
        self.loader_thread = None
        self.loading = False
        self.eof_reached = False
        self.seek_requested = None  # 跳转请求：(position_seconds, callback)

        # 性能统计
        self.buffer_underruns = 0
        self.chunks_loaded = 0

        # 初始化音频平滑相关状态
        self._last_sample = np.zeros((1, engine_channels), dtype=np.float32)

        self._initialize_file()

    def _initialize_file(self):
        """
        初始化文件信息

        读取音频文件的基本信息，包括采样率、声道数、总帧数和时长。

        Raises:
            Exception: 如果无法读取文件信息
        """
        try:
            with sf.SoundFile(self.file_path) as f:
                self.total_frames = f.frames
                self.file_sample_rate = f.samplerate
                self.file_channels = f.channels
                self.duration = f.frames / f.samplerate

                logger.info(f"流式轨道初始化: {self.track_id}")
                logger.info(f"  采样率: {self.file_sample_rate}Hz -> {self.engine_sample_rate}Hz")
                logger.info(f"  声道: {self.file_channels} -> {self.engine_channels}")
                logger.info(f"  时长: {self.duration:.1f}秒")

        except Exception as e:
            logger.error(f"无法读取文件信息: {e}")
            raise

    def start_streaming(self):
        """
        开始流式加载

        启动后台线程进行音频数据的流式加载。如果已经在加载中，则不会重复启动。

        Note:
            这是一个非阻塞操作，加载将在后台进行
        """
        if self.loading:
            return

        self.loading = True
        self.eof_reached = False
        self.loader_thread = threading.Thread(target=self._stream_loader, daemon=True)
        self.loader_thread.start()
        logger.info(f"开始流式加载: {self.track_id}")

    def stop_streaming(self):
        """
        停止流式加载

        停止后台加载线程并等待其结束。会设置加载标志为False，
        然后等待加载线程结束（最多1秒）。
        """
        self.loading = False
        if self.loader_thread and self.loader_thread.is_alive():
            self.loader_thread.join(timeout=1.0)
        logger.debug(f"停止流式加载: {self.track_id}")

    def _stream_loader(self):
        """
        流式加载线程的主循环

        在后台循环运行，负责：
        - 处理跳转请求
        - 检查缓冲区状态
        - 读取和处理音频块
        - 控制加载速度

        Note:
            这是一个内部方法，由start_streaming()启动的线程调用
        """
        chunk_frames = 4096  # 每次读取的帧数

        try:
            with sf.SoundFile(self.file_path) as f:
                f.seek(self.file_position)

                while self.loading:
                    # 处理跳转请求
                    if self.seek_requested is not None:
                        seek_pos, callback = self.seek_requested
                        self.seek_requested = None
                        self._handle_seek(f, seek_pos, callback)
                        continue

                    # 检查缓冲区状态
                    with self.buffer_lock:
                        current_buffer_frames = sum(chunk.shape[0] for chunk in self.audio_buffer)

                    if current_buffer_frames >= self.max_buffer_frames:
                        time.sleep(0.05)  # 缓冲区满，等待
                        continue

                    # 读取音频块
                    remaining = self.total_frames - self.file_position
                    if remaining <= 0:
                        self.eof_reached = True
                        time.sleep(0.1)
                        continue

                    read_frames = min(chunk_frames, remaining)
                    chunk = f.read(read_frames, dtype="float32", always_2d=True)

                    if chunk.shape[0] == 0:
                        break

                    # 处理音频块：重采样 + 声道转换
                    processed_chunk = self._process_chunk(chunk)

                    # 添加到缓冲区
                    with self.buffer_lock:
                        self.audio_buffer.append(processed_chunk)
                        self.chunks_loaded += 1

                    self.file_position += read_frames

                    # 控制加载速度
                    time.sleep(0.01)

        except Exception as e:
            logger.error(f"流式加载出错: {e}")
            self.loading = False

    def _handle_seek(self, f, position_seconds, callback):
        """
        处理跳转请求

        Args:
            f (sf.SoundFile): 音频文件对象
            position_seconds (float): 目标位置（秒）
            callback (callable): 跳转完成后的回调函数

        Note:
            跳转操作会清空当前缓冲区并重新定位文件读取位置
        """
        try:
            # 计算文件位置
            target_file_frame = int(position_seconds * self.file_sample_rate)
            target_file_frame = max(0, min(target_file_frame, self.total_frames - 1))

            # 清空缓冲区
            with self.buffer_lock:
                self.audio_buffer.clear()

            # 跳转文件位置
            f.seek(target_file_frame)
            self.file_position = target_file_frame
            self.playback_position = int(position_seconds * self.engine_sample_rate)

            # 重置EOF状态
            self.eof_reached = False

            if callback:
                callback(True)

            logger.debug(f"流式跳转完成: {position_seconds:.1f}s")

        except Exception as e:
            logger.error(f"流式跳转失败: {e}")
            if callback:
                callback(False)

    def _process_chunk(self, chunk):
        """
        处理音频块：重采样、声道转换

        对读取的音频块进行必要的处理，包括采样率转换和声道转换，
        以匹配引擎的要求。

        Args:
            chunk (np.ndarray): 原始音频数据块

        Returns:
            np.ndarray: 处理后的音频数据块
        """
        # 重采样
        if self.file_sample_rate != self.engine_sample_rate:
            chunk = self._resample_chunk(chunk)

        # 声道转换
        if self.file_channels != self.engine_channels:
            chunk = self._convert_channels(chunk)

        return chunk.astype(np.float32)

    def _resample_chunk(self, chunk):
        """
        高质量音频块重采样

        使用scipy或线性插值对音频块进行重采样，优先使用高质量的算法。

        Args:
            chunk (np.ndarray): 输入音频数据

        Returns:
            np.ndarray: 重采样后的音频数据
        """
        if self.file_sample_rate == self.engine_sample_rate:
            return chunk

        try:
            # 尝试使用scipy进行高质量重采样
            from scipy import signal

            ratio = self.engine_sample_rate / self.file_sample_rate
            new_length = int(chunk.shape[0] * ratio)

            if new_length <= 0:
                return np.zeros((1, chunk.shape[1]), dtype=np.float32)

            resampled = np.zeros((new_length, chunk.shape[1]), dtype=np.float32)
            for ch in range(chunk.shape[1]):
                resampled[:, ch] = signal.resample(chunk[:, ch], new_length)

            return resampled

        except ImportError:
            # 降级到线性插值
            ratio = self.engine_sample_rate / self.file_sample_rate
            new_length = int(chunk.shape[0] * ratio)

            if new_length <= 0:
                return np.zeros((1, chunk.shape[1]), dtype=np.float32)

            resampled = np.zeros((new_length, chunk.shape[1]), dtype=np.float32)
            for ch in range(chunk.shape[1]):
                old_indices = np.arange(chunk.shape[0])
                new_indices = np.linspace(0, chunk.shape[0] - 1, new_length)
                resampled[:, ch] = np.interp(new_indices, old_indices, chunk[:, ch])

            return resampled

    def _convert_channels(self, chunk):
        """
        声道转换

        根据引擎要求的声道数转换音频数据的声道。

        Args:
            chunk (np.ndarray): 输入音频数据

        Returns:
            np.ndarray: 转换后的音频数据

        Note:
            - 单声道转立体声：复制声道
            - 立体声转单声道：混合声道
            - 其他情况：截取或零填充
        """
        if self.file_channels == self.engine_channels:
            return chunk

        if self.engine_channels == 2 and self.file_channels == 1:
            # 单声道转立体声
            return np.repeat(chunk, 2, axis=1)
        elif self.engine_channels == 1 and self.file_channels == 2:
            # 立体声转单声道
            return np.mean(chunk, axis=1, keepdims=True)
        else:
            # 其他情况：截取或填充
            if self.engine_channels < self.file_channels:
                return chunk[:, : self.engine_channels]
            else:
                padded = np.zeros((chunk.shape[0], self.engine_channels), dtype=np.float32)
                padded[:, : self.file_channels] = chunk
                return padded

    def get_audio_data(self, frames_needed):
        """
        获取音频数据用于播放

        从缓冲区中提取指定帧数的音频数据。如果缓冲区中的数据不足，
        会返回零填充的数据并记录下溢。

        Args:
            frames_needed (int): 需要的音频帧数

        Returns:
            np.ndarray: 音频数据，形状为 (frames_needed, engine_channels)

        Note:
            这个方法是线程安全的，会自动管理缓冲区访问
        """
        with self.buffer_lock:
            # 从缓冲区收集数据
            output = np.zeros((frames_needed, self.engine_channels), dtype=np.float32)
            frames_filled = 0

            # 记录上一次的音频样本，用于平滑过渡
            last_sample = getattr(
                self, "_last_sample", np.zeros((1, self.engine_channels), dtype=np.float32)
            )

            # 检查缓冲区状态
            buffer_frames_available = sum(chunk.shape[0] for chunk in self.audio_buffer)

            # 如果缓冲区严重不足且未到文件末尾，触发紧急加载
            if (
                buffer_frames_available < frames_needed // 2
                and not self.eof_reached
                and self.loading
            ):
                # 尝试唤醒加载线程或增加加载优先级
                pass  # 后续可以添加更积极的加载策略

            # 从缓冲区块中提取数据
            while frames_filled < frames_needed and self.audio_buffer:
                chunk = self.audio_buffer[0]
                available_in_chunk = chunk.shape[0]
                needed_from_chunk = min(available_in_chunk, frames_needed - frames_filled)

                # 验证chunk数据有效性
                if np.any(np.isnan(chunk)) or np.any(np.isinf(chunk)):
                    logger.warning(
                        f"Invalid chunk data detected in track {self.track_id}, skipping"
                    )
                    self.audio_buffer.popleft()
                    continue

                # 复制数据
                try:
                    output[frames_filled : frames_filled + needed_from_chunk] = chunk[
                        :needed_from_chunk
                    ]
                    frames_filled += needed_from_chunk

                    # 更新last_sample为有效数据
                    if needed_from_chunk > 0:
                        last_sample = chunk[needed_from_chunk - 1 : needed_from_chunk]
                except Exception as e:
                    logger.error(f"Error copying chunk data: {e}")
                    self.audio_buffer.popleft()
                    continue

                # 如果使用了整个chunk，移除它
                if needed_from_chunk == available_in_chunk:
                    self.audio_buffer.popleft()
                else:
                    # 否则更新chunk（移除已使用的部分）
                    remaining_chunk = chunk[needed_from_chunk:]
                    self.audio_buffer[0] = remaining_chunk
                    break

            # 如果缓冲区数据不足，进行智能填充
            if frames_filled < frames_needed:
                remaining_frames = frames_needed - frames_filled

                # 只有在非EOF或有有效last_sample时才记录下溢
                if not self.eof_reached:
                    self.buffer_underruns += 1
                    if self.buffer_underruns % 10 == 1:  # 每10次下溢记录一次日志，避免日志泛滥
                        logger.warning(
                            f"Buffer underrun #{self.buffer_underruns} in track {self.track_id}, missing {remaining_frames} frames"
                        )

                # 智能填充策略
                if frames_filled > 0 or (
                    hasattr(self, "_last_sample") and np.any(last_sample != 0)
                ):
                    # 有历史数据：使用渐进式淡出
                    fade_length = min(remaining_frames, 128)  # 增加淡出长度以获得更平滑的过渡

                    if fade_length > 0 and last_sample.shape[0] > 0:
                        # 创建更平滑的淡出曲线（指数+线性组合）
                        linear_fade = np.linspace(1.0, 0.0, fade_length)
                        exp_fade = np.exp(-np.arange(fade_length) * 0.05)  # 更缓和的指数衰减
                        combined_fade = (linear_fade * 0.3 + exp_fade * 0.7)[
                            :, np.newaxis
                        ]  # 组合衰减

                        try:
                            fade_chunk = last_sample * combined_fade
                            output[frames_filled : frames_filled + fade_length] = fade_chunk
                            frames_filled += fade_length
                        except Exception as e:
                            logger.error(f"Error applying fade: {e}")

                    # 剩余部分使用低级白噪声而不是完全静音，以避免数字静音造成的不自然感
                    if frames_filled < frames_needed:
                        remaining_silence = frames_needed - frames_filled
                        # 添加极低级别的抖动噪声来打破数字静音
                        noise_level = 1e-6  # 非常低的噪声级别
                        noise = np.random.normal(
                            0, noise_level, (remaining_silence, self.engine_channels)
                        ).astype(np.float32)
                        output[frames_filled:] = noise
                elif self.eof_reached:
                    # 文件结束：完全静音是合适的
                    pass  # output已经初始化为零
                else:
                    # 没有历史数据且非EOF：可能是初始化阶段，添加轻微抖动
                    noise_level = 1e-7
                    noise = np.random.normal(
                        0, noise_level, (remaining_frames, self.engine_channels)
                    ).astype(np.float32)
                    output[frames_filled:] = noise

            # 保存最后的样本用于下次调用（确保数据有效）
            if frames_filled > 0:
                try:
                    valid_end_index = frames_filled - 1
                    if valid_end_index >= 0:
                        self._last_sample = output[valid_end_index : valid_end_index + 1].copy()
                        # 验证保存的样本
                        if np.any(np.isnan(self._last_sample)) or np.any(
                            np.isinf(self._last_sample)
                        ):
                            self._last_sample = np.zeros(
                                (1, self.engine_channels), dtype=np.float32
                            )
                except Exception as e:
                    logger.error(f"Error saving last sample: {e}")
                    self._last_sample = np.zeros((1, self.engine_channels), dtype=np.float32)

            # 更新播放位置（仅基于实际填充的帧数）
            self.playback_position += min(frames_filled, frames_needed)

            # 验证输出数据
            if np.any(np.isnan(output)) or np.any(np.isinf(output)):
                logger.error(f"Invalid output data in track {self.track_id}, clearing")
                output.fill(0)

            # 应用软限制防止削波
            peak = np.max(np.abs(output))
            if peak > 0.99:
                output *= 0.95 / peak
                logger.debug(
                    f"Applied peak limiting in streaming track {self.track_id}: {peak:.3f} -> 0.95"
                )

            return output

    def seek_to(self, position_seconds, callback=None):
        """
        请求跳转到指定位置

        异步请求跳转到音频文件的指定时间位置。跳转操作会在
        后台加载线程中处理。

        Args:
            position_seconds (float): 目标位置（秒）
            callback (callable, optional): 跳转完成回调函数，
                接收一个bool参数表示是否成功

        Example:
            >>> def on_seek_complete(success):
            ...     print(f"跳转{'成功' if success else '失败'}")
            >>> streaming_track.seek_to(30.0, on_seek_complete)
        """
        self.seek_requested = (position_seconds, callback)

    def get_position_seconds(self):
        """
        获取当前播放位置（秒）

        Returns:
            float: 当前播放位置（秒）
        """
        return self.playback_position / self.engine_sample_rate

    def get_buffer_status(self):
        """
        获取缓冲区状态

        返回详细的缓冲区状态信息，用于监控和调试。

        Returns:
            dict: 包含以下键的字典：
                - buffer_seconds (float): 缓冲区时长（秒）
                - buffer_frames (int): 缓冲区帧数
                - max_buffer_seconds (float): 最大缓冲区时长
                - chunks (int): 缓冲区块数
                - underruns (int): 下溢次数
                - eof_reached (bool): 是否到达文件末尾
                - loading (bool): 是否正在加载
                - file_position_seconds (float): 文件读取位置（秒）
                - chunks_loaded (int): 已加载的块数

        Example:
            >>> status = streaming_track.get_buffer_status()
            >>> print(f"缓冲区: {status['buffer_seconds']:.1f}秒")
            >>> print(f"下溢次数: {status['underruns']}")
        """
        with self.buffer_lock:
            buffer_frames = sum(chunk.shape[0] for chunk in self.audio_buffer)
            buffer_seconds = (
                buffer_frames / self.engine_sample_rate if self.engine_sample_rate > 0 else 0
            )

        return {
            "buffer_seconds": buffer_seconds,
            "buffer_frames": buffer_frames,
            "max_buffer_seconds": self.buffer_seconds,
            "chunks": len(self.audio_buffer),
            "underruns": self.buffer_underruns,
            "eof_reached": self.eof_reached,
            "loading": self.loading,
            "file_position_seconds": self.file_position / self.file_sample_rate,
            "chunks_loaded": self.chunks_loaded,
        }
