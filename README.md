# AudioMixer

[![Tests](https://github.com/yourusername/audiomixer/actions/workflows/test.yml/badge.svg)](https://github.com/yourusername/audiomixer/actions/workflows/test.yml)
[![CI/CD Pipeline](https://github.com/yourusername/audiomixer/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/yourusername/audiomixer/actions/workflows/ci-cd.yml)
[![PyPI version](https://badge.fury.io/py/audiomixer.svg)](https://badge.fury.io/py/audiomixer)
[![Python versions](https://img.shields.io/pypi/pyversions/audiomixer.svg)](https://pypi.org/project/audiomixer/)
[![License](https://img.shields.io/github/license/yourusername/audiomixer.svg)](LICENSE)

A high-performance real-time audio mixing engine for Python, designed for professional audio applications, game development, and multimedia projects.

## Features

- **Real-time audio mixing** - Low-latency audio processing with configurable buffer sizes
- **Multi-track support** - Handle up to 32+ simultaneous audio tracks
- **High-quality audio processing** - Support for various sample rates and channel configurations
- **Advanced audio effects** - Fade in/out, volume control, speed adjustment, and looping
- **Memory efficient** - Optimized buffer pooling and memory management
- **Thread-safe** - Safe for use in multi-threaded applications
- **File format support** - Load audio from various formats via soundfile
- **Optional high-quality processing** - Enhanced resampling and time-stretching with librosa/scipy

## Installation

### Basic installation
```bash
pip install audiomixer
```

### With high-quality audio processing
```bash
pip install audiomixer[high-quality]
```

### With time-stretching support
```bash
pip install audiomixer[time-stretch]
```

### With all optional dependencies
```bash
pip install audiomixer[all]
```

### Development installation
```bash
git clone https://github.com/yourusername/audiomixer.git
cd audiomixer
pip install -e .[dev]
```

## Quick Start

```python
import numpy as np
from audiomixer import AudioEngine

# Initialize the audio engine
engine = AudioEngine(sample_rate=48000, buffer_size=1024, channels=2)

# Start the audio engine
engine.start()

# Load an audio file
engine.load_track("background_music", "path/to/music.wav", auto_normalize=True)

# Load audio from numpy array
audio_data = np.random.randn(48000, 2).astype(np.float32)  # 1 second of stereo noise
engine.load_track("noise", audio_data)

# Play tracks
engine.play("background_music", loop=True, fade_in=True)
engine.play("noise", volume=0.5)

# Control playback
engine.set_volume("background_music", 0.7)
engine.set_speed("noise", 1.5)  # Play 50% faster

# Stop tracks
engine.stop("noise", fade_out=True)

# Cleanup
engine.shutdown()
```

## API Reference

### AudioEngine

The main class for audio mixing operations.

#### Constructor
```python
AudioEngine(sample_rate=48000, buffer_size=1024, channels=2, max_tracks=32, device=None, stream_latency='low')
```

**Parameters:**
- `sample_rate` (int): Audio sample rate in Hz (default: 48000)
- `buffer_size` (int): Audio buffer size in frames (default: 1024)
- `channels` (int): Number of audio channels (default: 2 for stereo)
- `max_tracks` (int): Maximum number of simultaneous tracks (default: 32)
- `device` (int, optional): Audio device ID (None for default device)
- `stream_latency` (str): Stream latency setting ('low', 'medium', 'high')

#### Methods

##### Track Management

**`load_track(track_id, source, speed=1.0, auto_normalize=True, on_complete=None)`**
Load audio data into a track.

**`unload_track(track_id)`**
Unload a track and free its memory.

**`clear_all_tracks()`**
Clear all loaded tracks.

##### Playback Control

**`play(track_id, fade_in=False, loop=False, seek=None, volume=None)`**
Start playing a track.

**`stop(track_id, fade_out=True)`**
Stop playing a track.

**`pause(track_id)`**
Pause a track.

**`resume(track_id)`**
Resume a paused track.

##### Audio Properties

**`set_volume(track_id, volume)`**
Set track volume (0.0-1.0).

**`set_speed(track_id, speed)`**
Set playback speed (0.1-4.0).

**`set_loop(track_id, loop)`**
Enable/disable track looping.

**`seek(track_id, position_sec)`**
Seek to a specific position in seconds.

##### Information

**`get_position(track_id)`**
Get current playback position in seconds.

**`get_duration(track_id)`**
Get track duration in seconds.

**`get_performance_stats()`**
Get performance statistics.

##### Engine Control

**`start()`**
Start the audio engine.

**`shutdown()`**
Stop the engine and cleanup resources.

## Advanced Usage

### Callback-based Loading
```python
def load_complete(track_id, success, error=None):
    if success:
        print(f"Track {track_id} loaded successfully")
        engine.play(track_id)
    else:
        print(f"Failed to load {track_id}: {error}")

engine.load_track("music", "song.wav", on_complete=load_complete)
```

### Performance Monitoring
```python
stats = engine.get_performance_stats()
print(f"CPU Usage: {stats['cpu_usage']:.1f}%")
print(f"Peak Level: {stats['peak_level']:.3f}")
print(f"Active Tracks: {stats['active_tracks']}")
```

### Real-time Effects
```python
# Gradual volume fade
import time
for volume in np.linspace(1.0, 0.0, 100):
    engine.set_volume("music", volume)
    time.sleep(0.05)
```

## Requirements

### Core Dependencies
- Python 3.8+
- numpy >= 1.19.0
- sounddevice >= 0.4.0
- soundfile >= 0.10.0

### Optional Dependencies
- librosa >= 0.8.0 (for high-quality resampling)
- scipy >= 1.7.0 (for signal processing)
- pyrubberband >= 0.3.0 (for time-stretching)

## Performance Tips

1. **Buffer Size**: Smaller buffers reduce latency but increase CPU usage
2. **Sample Rate**: Higher sample rates improve quality but require more processing
3. **Track Limit**: Keep the number of simultaneous tracks reasonable for your hardware
4. **Memory Management**: Unload unused tracks to free memory
5. **Quality Settings**: Use optional dependencies for best audio quality

## Platform Support

- Windows
- macOS
- Linux

## Development and Contributing

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=audiomixer

# Run specific test
pytest tests/test_audiomixer.py::TestAudioEngine::test_load_track_from_array -v
```

### Release Process
We use automated releases through GitHub Actions:

1. **For patch releases:**
   ```bash
   python scripts/release.py patch
   git push origin main
   git push origin v1.0.1
   ```

2. **For minor releases:**
   ```bash
   python scripts/release.py minor
   git push origin main
   git push origin v1.1.0
   ```

3. **For major releases:**
   ```bash
   python scripts/release.py major
   git push origin main
   git push origin v2.0.0
   ```

### CI/CD Pipeline
- ✅ **Automated testing** on multiple Python versions (3.8-3.12)
- ✅ **Multi-platform testing** (Ubuntu, Windows, macOS)
- ✅ **Code quality checks** (flake8, mypy, bandit)
- ✅ **Security scanning** (safety, bandit)
- ✅ **Automatic PyPI publishing** on releases
- ✅ **Test PyPI publishing** on main branch commits

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Make your changes and add tests
4. Ensure all tests pass (`pytest tests/ -v`)
5. Submit a pull request

All pull requests are automatically tested on multiple platforms and Python versions.

## Changelog

### Version 1.0.0
- Initial release
- Real-time audio mixing
- Multi-track support
- Audio effects and controls
- High-performance optimization
- Complete CI/CD pipeline
- Comprehensive documentation

## Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/audiomixer/issues
- Documentation: https://github.com/yourusername/audiomixer#readme 