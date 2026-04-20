"""
Create logo video using ffmpeg directly to avoid any dimension issues
"""

from pathlib import Path
import subprocess

# Paths
photos_dir = Path(r"F:\executedcode\bands\copperCreek\photos")
logo_gif = Path(r"F:\executedcode\bands\copperCreek\branding\copperCreekSquare.gif")
output_dir = Path(r"F:\executedcode\bands\copperCreek")

# All video files in order
video_files = [
    # "IMG_4004.MOV",
    # "IMG_4001.MOV", 
    # "IMG_4002.MOV",
    # "IMG_4003.MOV",
    # "IMG_4005.MOV",
    # "IMG_4007.MOV",
    # "IMG_4010.MOV",
    # "IMG_4011.MOV",
    # "IMG_4020.MOV",
    "IMG_4018.MOV"
]

def create_logo_with_ffmpeg():
    """Create logo video using ffmpeg directly in PORTRAIT orientation"""
    print("\n=== Creating Logo with FFmpeg (Portrait) ===\n")
    
    logo_output = output_dir / "logo_ffmpeg_portrait.MOV"
    
    # Create a PORTRAIT (1080x1920) video with the logo centered
    cmd = [
        'ffmpeg',
        '-y',
        '-stream_loop', '10',  # Loop the GIF
        '-i', str(logo_gif),
        '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',  # Silent audio source
        '-t', '3',  # 3 seconds duration
        '-vf', 'scale=1080:1080,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black',  # Center square logo on PORTRAIT
        '-r', '30',  # 30 fps
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-preset', 'medium',
        '-pix_fmt', 'yuv420p',
        '-shortest',
        str(logo_output)
    ]
    
    print("Creating 1080x1920 PORTRAIT logo video...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"Logo created: {logo_output}")
        
        # Verify dimensions
        check_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height', '-of', 'default=noprint_wrappers=1', 
                    str(logo_output)]
        check_result = subprocess.run(check_cmd, capture_output=True, text=True)
        print(f"Dimensions: {check_result.stdout.strip()}")
        
        return logo_output
    else:
        print("Error creating logo:")
        print(result.stderr[-500:])
        return None

def concat_all_videos(logo_mov):
    """Concatenate logo with MOV files, trimming and fading for smaller file size"""
    print("\n=== Processing and Concatenating Videos ===\n")
    
    # Process each video: trim beginning and end
    temp_dir = output_dir / "temp_processed"
    temp_dir.mkdir(exist_ok=True)
    
    all_files_to_concat = [logo_mov]
    
    print("Processing videos (trimming 4s from start and end)...")
    for i, vf in enumerate(video_files):
        input_path = photos_dir / vf
        output_path = temp_dir / f"processed_{i:02d}_{vf}"
        
        # Get video duration
        duration_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                       '-of', 'default=noprint_wrappers=1:nokey=1', str(input_path)]
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
        duration = float(duration_result.stdout.strip())
        
        # Trim 4 seconds from start and end
        trimmed_duration = duration - 8  # Remove 4s from start + 4s from end
        
        if trimmed_duration <= 0:
            print(f"  {vf}: too short to trim, skipping")
            continue
        
        # Check if this is the last video (for fade out)
        is_last = (i == len(video_files) - 1)
        
        # Build video filter
        # Start at 4 seconds, duration is trimmed_duration
        video_filter = 'null'
        audio_filter = 'anull'
        
        if is_last:
            # Add fade out for last video (2 second fade at the end)
            fade_start = trimmed_duration - 2
            video_filter = f'fade=t=out:st={fade_start}:d=2'
            audio_filter = f'afade=t=out:st={fade_start}:d=2'
            print(f"  {vf}: trimming + fade out")
        else:
            print(f"  {vf}: trimming")
        
        # Process video
        cmd = [
            'ffmpeg',
            '-y',
            '-ss', '4',  # Skip first 4 seconds
            '-i', str(input_path),
            '-t', str(trimmed_duration),  # Duration after trim
            '-vf', video_filter,
            '-af', audio_filter,
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',  # Slightly higher CRF for better compression
            '-c:a', 'aac',
            '-b:a', '128k',  # Lower audio bitrate for smaller size
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            all_files_to_concat.append(output_path)
        else:
            print(f"    Error processing {vf}")
            print(result.stderr[-300:])
            return
    
    print(f"\nProcessed {len(all_files_to_concat) - 1} videos")
    
    output_path = output_dir / "copper_creek_montage_short_10.mp4"
    
    # Build command
    cmd = ['ffmpeg', '-y']
    for f in all_files_to_concat:
        cmd.extend(['-i', str(f)])
    
    n = len(all_files_to_concat)
    video_concat = ''.join(f'[{i}:v]' for i in range(n))
    audio_concat = ''.join(f'[{i}:a]' for i in range(n))
    
    filter_complex = f'{video_concat}concat=n={n}:v=1:a=0[v];{audio_concat}concat=n={n}:v=0:a=1[a]'
    
    cmd.extend([
        '-filter_complex', filter_complex,
        '-map', '[v]',
        '-map', '[a]',
        '-c:v', 'libx264',
        '-preset', 'slow',  # Better compression
        '-crf', '25',  # Higher CRF = smaller file size
        '-c:a', 'aac',
        '-b:a', '128k',  # Lower audio bitrate
        '-movflags', '+faststart',  # Optimize for web streaming
        str(output_path)
    ])
    
    print("Concatenating with compression...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"\nSuccess: {output_path}")
        
        # Get duration and file size
        duration_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration,size',
                       '-of', 'default=noprint_wrappers=1', str(output_path)]
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
        
        print("\nFinal montage details:")
        for line in duration_result.stdout.strip().split('\n'):
            if 'duration=' in line:
                duration = float(line.split('=')[1])
                print(f"  Duration: {duration:.1f}s ({duration/60:.1f} minutes)")
            elif 'size=' in line:
                size = int(line.split('=')[1])
                size_mb = size / (1024 * 1024)
                print(f"  File size: {size_mb:.1f} MB")
        
        print("\nOptimizations applied:")
        print("  - Trimmed 4 seconds from start and end of each video")
        print("  - 2 second fade out on last video")
        print("  - Compressed with CRF 25 (good quality, smaller size)")
        print("  - Optimized for web streaming (faststart)")
    else:
        print("\nError:")
        lines = result.stderr.split('\n')
        for line in lines:
            if 'concat' in line.lower() or 'parameters' in line.lower() or 'match' in line.lower():
                print(line)

if __name__ == "__main__":
    logo_mov = create_logo_with_ffmpeg()
    if logo_mov:
        concat_all_videos(logo_mov)
