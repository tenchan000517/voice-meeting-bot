#!/usr/bin/env python3
"""FFmpeg availability test script"""

import subprocess
import sys
import os
import shutil

def test_ffmpeg():
    """Test FFmpeg availability from Python"""
    
    print("=== FFmpeg Availability Test ===")
    
    # Test 1: Check if ffmpeg is in PATH
    print("\n1. Checking PATH for ffmpeg...")
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        print(f"✅ FFmpeg found in PATH: {ffmpeg_path}")
    else:
        print("❌ FFmpeg not found in PATH")
    
    # Test 2: Try to run ffmpeg command
    print("\n2. Testing ffmpeg command execution...")
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        if result.returncode == 0:
            print("✅ FFmpeg command executed successfully")
            print(f"Version: {result.stdout.split()[2]}")
        else:
            print(f"❌ FFmpeg command failed: {result.stderr}")
    except FileNotFoundError:
        print("❌ FFmpeg command not found (FileNotFoundError)")
    except subprocess.TimeoutExpired:
        print("❌ FFmpeg command timed out")
    except Exception as e:
        print(f"❌ FFmpeg command error: {e}")
    
    # Test 3: Check PATH environment variable
    print("\n3. Checking PATH environment variable...")
    path_env = os.environ.get('PATH', '')
    ffmpeg_paths = [p for p in path_env.split(os.pathsep) if 'ffmpeg' in p.lower()]
    if ffmpeg_paths:
        print("✅ FFmpeg paths found in PATH:")
        for path in ffmpeg_paths:
            print(f"   - {path}")
    else:
        print("❌ No FFmpeg paths found in PATH")
    
    # Test 4: Common FFmpeg installation locations
    print("\n4. Checking common FFmpeg locations...")
    common_paths = [
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
        r'C:\tools\ffmpeg\bin\ffmpeg.exe',
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg'
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            print(f"✅ Found: {path}")
        else:
            print(f"❌ Not found: {path}")
    
    # Test 5: Test Whisper's FFmpeg dependency
    print("\n5. Testing Whisper's FFmpeg dependency...")
    try:
        import whisper
        print("✅ Whisper imported successfully")
        
        # Try to use Whisper's audio loading function
        from whisper.audio import load_audio
        print("✅ Whisper audio module imported")
        
        # This would fail if FFmpeg is not available
        print("   Note: Actual audio loading test requires audio file")
        
    except ImportError as e:
        print(f"❌ Whisper import failed: {e}")
    except Exception as e:
        print(f"❌ Whisper audio test failed: {e}")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_ffmpeg()