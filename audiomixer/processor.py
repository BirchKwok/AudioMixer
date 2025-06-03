from .utils import *


class AudioProcessor:
    """
    音频处理器类，提供高效的音频处理方法
    
    包含各种音频效果和处理算法的静态方法，
    所有处理都采用就地操作以提高性能。
    """
    
    @staticmethod
    def apply_fade_inplace(chunk: npt.NDArray, fade_env: npt.NDArray) -> None:
        """
        就地应用淡入淡出效果
        
        将淡入淡出包络应用到音频数据上，修改原始数据。
        
        Args:
            chunk (np.ndarray): 音频数据，形状为 (frames, channels)
            fade_env (np.ndarray): 淡入淡出包络，形状为 (frames,)
            
        Note:
            这是一个就地操作，会直接修改输入的音频数据
            
        Example:
            >>> fade_env = np.linspace(0.0, 1.0, 1024)  # 淡入
            >>> AudioProcessor.apply_fade_inplace(audio_chunk, fade_env)
        """
        chunk *= fade_env[:, np.newaxis]
    
    @staticmethod
    def apply_volume_inplace(chunk: npt.NDArray, volume: float) -> None:
        """
        就地应用音量调整
        
        将指定的音量倍数应用到音频数据上。
        
        Args:
            chunk (np.ndarray): 音频数据
            volume (float): 音量倍数（1.0为原始音量）
            
        Note:
            如果volume为1.0，则不进行任何操作以优化性能
        """
        if volume != 1.0:
            chunk *= volume
    
    @staticmethod
    def soft_limiter_inplace(buffer: npt.NDArray, threshold: float = 0.98) -> float:
        """
        软限制器，防止音频削波
        
        当音频峰值超过阈值时，应用软压缩来防止削波失真。
        
        Args:
            buffer (np.ndarray): 音频缓冲区
            threshold (float, optional): 限制阈值. Defaults to 0.98.
            
        Returns:
            float: 压缩比率（1.0表示无压缩）
            
        Example:
            >>> compression_ratio = AudioProcessor.soft_limiter_inplace(audio_buffer, 0.95)
            >>> if compression_ratio < 1.0:
            ...     print(f"应用了 {compression_ratio:.2f} 压缩比")
        """
        peak = np.max(np.abs(buffer))
        if peak > threshold:
            compression_ratio = threshold / peak
            buffer *= compression_ratio
            return compression_ratio
        return 1.0 