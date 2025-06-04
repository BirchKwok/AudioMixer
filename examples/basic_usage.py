#!/usr/bin/env python3
"""
Basic RealtimeMix Usage Example

This example demonstrates the core functionality of the RealtimeMix library.
"""

import numpy as np
import time
from realtimemix import AudioEngine


def main():
    # Initialize the audio engine
    print("Initializing RealtimeMix...")
    engine = AudioEngine(
        sample_rate=48000,
        buffer_size=1024,
        channels=2,
        max_tracks=16
    )
    
    try:
        # Start the audio engine
        engine.start()
        print("Audio engine started!")
        
        # Generate some test audio data
        print("Generating test audio...")
        
        # Create a sine wave (440 Hz - A note)
        duration = 3.0  # seconds
        sample_rate = 48000
        frequency = 440.0
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        sine_wave = 0.3 * np.sin(2 * np.pi * frequency * t)
        
        # Convert to stereo
        stereo_sine = np.column_stack([sine_wave, sine_wave]).astype(np.float32)
        
        # Generate white noise
        noise_duration = 2.0
        noise_samples = int(sample_rate * noise_duration)
        white_noise = 0.1 * np.random.randn(noise_samples, 2).astype(np.float32)
        
        # Load the audio data into tracks
        print("Loading tracks...")
        engine.load_track("sine_wave", stereo_sine)
        engine.load_track("white_noise", white_noise)
        
        # Play the sine wave with fade-in
        print("Playing sine wave with fade-in...")
        engine.play("sine_wave", fade_in=True, loop=True)
        
        # Wait a bit, then add noise
        time.sleep(2)
        print("Adding white noise...")
        engine.play("white_noise", volume=0.5)
        
        # Demonstrate volume control
        time.sleep(1)
        print("Fading sine wave volume...")
        for volume in np.linspace(1.0, 0.3, 20):
            engine.set_volume("sine_wave", volume)
            time.sleep(0.1)
        
        # Demonstrate speed control
        time.sleep(1)
        print("Changing sine wave speed...")
        for speed in np.linspace(1.0, 1.5, 10):
            engine.set_speed("sine_wave", speed)
            time.sleep(0.2)
        
        # Reset speed
        engine.set_speed("sine_wave", 1.0)
        
        # Show performance stats
        time.sleep(1)
        stats = engine.get_performance_stats()
        print(f"\nPerformance Statistics:")
        print(f"  CPU Usage: {stats['cpu_usage']:.1f}%")
        print(f"  Peak Level: {stats['peak_level']:.3f}")
        print(f"  Active Tracks: {stats['active_tracks']}")
        print(f"  Total Tracks: {stats['total_tracks']}")
        
        # Stop tracks with fade-out
        print("\nStopping tracks with fade-out...")
        engine.stop("white_noise", fade_out=True)
        time.sleep(1)
        engine.stop("sine_wave", fade_out=True)
        
        # Wait for fade-out to complete
        time.sleep(2)
        
        print("Example completed successfully!")
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Always cleanup
        print("Shutting down audio engine...")
        engine.shutdown()
        print("Done!")


if __name__ == "__main__":
    main() 