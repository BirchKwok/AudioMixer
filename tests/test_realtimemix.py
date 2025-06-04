"""
Basic tests for RealtimeMix library
"""

import pytest
import numpy as np
import time
from realtimemix import AudioEngine


class TestAudioEngine:
    """Test cases for AudioEngine class"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.engine = AudioEngine(
            sample_rate=48000,
            buffer_size=1024,
            channels=2,
            max_tracks=8
        )
    
    def teardown_method(self):
        """Cleanup after each test method"""
        if self.engine.is_running:
            self.engine.shutdown()
    
    def test_engine_initialization(self):
        """Test that engine initializes correctly"""
        assert self.engine.sample_rate == 48000
        assert self.engine.buffer_size == 1024
        assert self.engine.channels == 2
        assert self.engine.max_tracks == 8
        assert not self.engine.is_running
        assert len(self.engine.tracks) == 0
    
    def test_engine_start_stop(self):
        """Test engine start and stop functionality"""
        # Start engine
        self.engine.start()
        assert self.engine.is_running
        
        # Stop engine
        self.engine.shutdown()
        assert not self.engine.is_running
    
    def test_load_track_from_array(self):
        """Test loading track from numpy array"""
        # Create test audio data
        duration = 1.0
        samples = int(self.engine.sample_rate * duration)
        audio_data = np.random.randn(samples, 2).astype(np.float32)
        
        # Load track
        result = self.engine.load_track("test_track", audio_data)
        assert result is True
        
        # Wait for loading to complete
        time.sleep(0.1)
        
        # Check track is loaded
        assert "test_track" in self.engine.tracks
        assert self.engine.tracks["test_track"].shape == audio_data.shape
    
    def test_track_states_initialization(self):
        """Test that track states are initialized correctly"""
        audio_data = np.random.randn(1000, 2).astype(np.float32)
        self.engine.load_track("test", audio_data)
        
        time.sleep(0.1)  # Wait for loading
        
        state = self.engine.track_states["test"]
        assert state['position'] == 0
        assert state['volume'] == 1.0
        assert state['playing'] is False
        assert state['loop'] is False
        assert state['paused'] is False
        assert state['speed'] == 1.0
    
    def test_track_playback_control(self):
        """Test basic playback control functions"""
        # Load test track
        audio_data = np.random.randn(1000, 2).astype(np.float32)
        self.engine.load_track("test", audio_data)
        time.sleep(0.1)
        
        # Start engine
        self.engine.start()
        
        # Test play
        self.engine.play("test")
        state = self.engine.track_states["test"]
        assert state['playing'] is True
        assert "test" in self.engine.active_tracks
        
        # Test pause
        self.engine.pause("test")
        assert state['paused'] is True
        
        # Test resume
        self.engine.resume("test")
        assert state['paused'] is False
        
        # Test stop
        self.engine.stop("test", fade_out=False)
        assert state['playing'] is False
        assert "test" not in self.engine.active_tracks
    
    def test_volume_control(self):
        """Test volume control functionality"""
        audio_data = np.random.randn(1000, 2).astype(np.float32)
        self.engine.load_track("test", audio_data)
        time.sleep(0.1)
        
        # Test volume setting
        self.engine.set_volume("test", 0.5)
        assert self.engine.track_states["test"]['volume'] == 0.5
        
        # Test volume bounds
        self.engine.set_volume("test", -0.1)
        assert self.engine.track_states["test"]['volume'] == 0.0
        
        self.engine.set_volume("test", 1.5)
        assert self.engine.track_states["test"]['volume'] == 1.0
    
    def test_speed_control(self):
        """Test speed control functionality"""
        audio_data = np.random.randn(1000, 2).astype(np.float32)
        self.engine.load_track("test", audio_data)
        time.sleep(0.1)
        
        # Test speed setting
        result = self.engine.set_speed("test", 1.5)
        assert result is True
        assert self.engine.track_states["test"]['speed'] == 1.5
        
        # Test speed bounds
        self.engine.set_speed("test", 0.05)  # Too low
        assert self.engine.track_states["test"]['speed'] == 0.1
        
        self.engine.set_speed("test", 5.0)  # Too high
        assert self.engine.track_states["test"]['speed'] == 4.0
    
    def test_loop_control(self):
        """Test loop control functionality"""
        audio_data = np.random.randn(1000, 2).astype(np.float32)
        self.engine.load_track("test", audio_data)
        time.sleep(0.1)
        
        # Test loop setting
        result = self.engine.set_loop("test", True)
        assert result is True
        assert self.engine.track_states["test"]['loop'] is True
        
        result = self.engine.set_loop("test", False)
        assert result is True
        assert self.engine.track_states["test"]['loop'] is False
    
    def test_seek_functionality(self):
        """Test seek functionality"""
        audio_data = np.random.randn(48000, 2).astype(np.float32)  # 1 second
        self.engine.load_track("test", audio_data)
        time.sleep(0.1)
        
        # Test seek
        self.engine.seek("test", 0.5)  # Seek to 0.5 seconds
        expected_position = int(0.5 * self.engine.sample_rate)
        assert self.engine.track_states["test"]['position'] == expected_position
        
        # Test get_position
        position = self.engine.get_position("test")
        assert abs(position - 0.5) < 0.01  # Allow small floating point error
    
    def test_duration_calculation(self):
        """Test duration calculation"""
        duration_sec = 2.0
        samples = int(self.engine.sample_rate * duration_sec)
        audio_data = np.random.randn(samples, 2).astype(np.float32)
        
        self.engine.load_track("test", audio_data)
        time.sleep(0.1)
        
        calculated_duration = self.engine.get_duration("test")
        assert abs(calculated_duration - duration_sec) < 0.01
    
    def test_unload_track(self):
        """Test track unloading"""
        audio_data = np.random.randn(1000, 2).astype(np.float32)
        self.engine.load_track("test", audio_data)
        time.sleep(0.1)
        
        # Verify track is loaded
        assert "test" in self.engine.tracks
        
        # Unload track
        result = self.engine.unload_track("test")
        assert result is True
        assert "test" not in self.engine.tracks
        assert "test" not in self.engine.track_states
    
    def test_clear_all_tracks(self):
        """Test clearing all tracks"""
        # Load multiple tracks
        for i in range(3):
            audio_data = np.random.randn(1000, 2).astype(np.float32)
            self.engine.load_track(f"test_{i}", audio_data)
        
        time.sleep(0.1)
        assert len(self.engine.tracks) == 3
        
        # Clear all tracks
        self.engine.clear_all_tracks()
        assert len(self.engine.tracks) == 0
        assert len(self.engine.track_states) == 0
    
    def test_performance_stats(self):
        """Test performance statistics"""
        stats = self.engine.get_performance_stats()
        
        # Check that all expected keys are present
        expected_keys = ['peak_level', 'cpu_usage', 'underrun_count', 
                        'active_tracks', 'total_tracks', 'loading_queue']
        for key in expected_keys:
            assert key in stats
            assert isinstance(stats[key], (int, float))
    
    def test_invalid_track_operations(self):
        """Test operations on non-existent tracks"""
        # These should not raise exceptions
        self.engine.play("non_existent")
        self.engine.stop("non_existent")
        self.engine.pause("non_existent")
        self.engine.resume("non_existent")
        self.engine.set_volume("non_existent", 0.5)
        
        # These should return False/0.0 for non-existent tracks
        assert self.engine.set_speed("non_existent", 1.5) is False
        assert self.engine.set_loop("non_existent", True) is False
        assert self.engine.get_position("non_existent") == 0.0
        assert self.engine.get_duration("non_existent") == 0.0
        assert self.engine.unload_track("non_existent") is False


class TestBufferPool:
    """Test cases for BufferPool class"""
    
    def test_buffer_pool_creation(self):
        """Test buffer pool creation and basic operations"""
        from realtimemix import BufferPool
        
        pool = BufferPool(buffer_size=1024, channels=2, pool_size=4)
        
        # Get buffers from pool
        buffers = []
        for _ in range(6):  # More than pool size
            buffer = pool.get_buffer()
            assert buffer.shape == (1024, 2)
            assert buffer.dtype == np.float32
            buffers.append(buffer)
        
        # Return buffers to pool
        for buffer in buffers[:4]:  # Only return up to pool size
            pool.return_buffer(buffer)


class TestAudioProcessor:
    """Test cases for AudioProcessor class"""
    
    def test_volume_application(self):
        """Test volume application"""
        from realtimemix import AudioProcessor
        
        # Create test audio data
        audio = np.ones((100, 2), dtype=np.float32)
        original = audio.copy()
        
        # Apply volume
        AudioProcessor.apply_volume_inplace(audio, 0.5)
        
        # Check result
        expected = original * 0.5
        np.testing.assert_array_almost_equal(audio, expected)
    
    def test_fade_application(self):
        """Test fade effect application"""
        from realtimemix import AudioProcessor
        
        # Create test audio data
        audio = np.ones((100, 2), dtype=np.float32)
        fade_env = np.linspace(0, 1, 100)
        
        # Apply fade
        AudioProcessor.apply_fade_inplace(audio, fade_env)
        
        # Check that fade was applied correctly
        assert audio[0, 0] == 0.0  # Start of fade
        assert audio[-1, 0] == 1.0  # End of fade
    
    def test_soft_limiter(self):
        """Test soft limiter functionality"""
        from realtimemix import AudioProcessor
        
        # Create audio data that clips
        audio = np.ones((100, 2), dtype=np.float32) * 2.0  # Above threshold
        
        # Apply soft limiter
        compression_ratio = AudioProcessor.soft_limiter_inplace(audio, threshold=0.98)
        
        # Check that limiting occurred
        assert compression_ratio < 1.0
        assert np.max(np.abs(audio)) <= 0.98


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 