"""
Video Processing Service using FFmpeg for Video Generation Platform
"""
import os
import uuid
import logging
import tempfile
import asyncio
import subprocess
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import json

logger = logging.getLogger(__name__)

class VideoProcessor:
    """Handles video processing operations using FFmpeg"""
    
    def __init__(self):
        self.temp_dir = "/tmp/video_processing"
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Verify FFmpeg installation
        if not self._check_ffmpeg_installation():
            raise RuntimeError("FFmpeg not found. Please install FFmpeg for video processing.")
        
        logger.info("VideoProcessor initialized successfully")
    
    def _check_ffmpeg_installation(self) -> bool:
        """Check if FFmpeg is installed and accessible"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    async def get_video_info(self, video_path: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive video information using FFprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                video_path
            ]
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                logger.error(f"FFprobe error: {stderr.decode()}")
                return None
            
            info = json.loads(stdout.decode())
            
            # Extract video stream information
            video_stream = None
            audio_stream = None
            
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video' and video_stream is None:
                    video_stream = stream
                elif stream.get('codec_type') == 'audio' and audio_stream is None:
                    audio_stream = stream
            
            if not video_stream:
                logger.error("No video stream found in file")
                return None
            
            # Calculate aspect ratio
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))
            aspect_ratio = width / height if height > 0 else 0
            
            # Determine if it's vertical (9:16), horizontal (16:9), or square
            if aspect_ratio < 0.75:
                orientation = "vertical"
            elif aspect_ratio > 1.5:
                orientation = "horizontal"
            else:
                orientation = "square"
            
            return {
                'format': info.get('format', {}),
                'video_stream': video_stream,
                'audio_stream': audio_stream,
                'duration': float(info.get('format', {}).get('duration', 0)),
                'width': width,
                'height': height,
                'aspect_ratio': aspect_ratio,
                'orientation': orientation,
                'fps': eval(video_stream.get('r_frame_rate', '0/1')),
                'bitrate': int(info.get('format', {}).get('bit_rate', 0)),
                'size_bytes': int(info.get('format', {}).get('size', 0))
            }
            
        except Exception as e:
            logger.error(f"Error getting video info: {str(e)}")
            return None
    
    async def convert_to_vertical(self, input_path: str, output_path: str, 
                                target_width: int = 1080, target_height: int = 1920) -> Dict[str, Any]:
        """Convert video to 9:16 vertical aspect ratio"""
        try:
            # Get input video info
            video_info = await self.get_video_info(input_path)
            if not video_info:
                return {'success': False, 'error': 'Could not analyze input video'}
            
            input_width = video_info['width']
            input_height = video_info['height']
            input_ratio = input_width / input_height
            target_ratio = target_width / target_height
            
            # Determine scaling and cropping strategy
            if input_ratio > target_ratio:
                # Input is wider, scale by height and crop width
                scale_height = target_height
                scale_width = int(input_width * (target_height / input_height))
                crop_x = (scale_width - target_width) // 2
                crop_y = 0
            else:
                # Input is taller or same ratio, scale by width and crop height  
                scale_width = target_width
                scale_height = int(input_height * (target_width / input_width))
                crop_x = 0
                crop_y = (scale_height - target_height) // 2
            
            # FFmpeg command for scaling and cropping
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-vf', f'scale={scale_width}:{scale_height},crop={target_width}:{target_height}:{crop_x}:{crop_y}',
                '-c:a', 'aac',  # Re-encode audio
                '-c:v', 'libx264',  # Re-encode video
                '-preset', 'fast',  # Encoding speed
                '-crf', '23',  # Quality
                '-y',  # Overwrite output
                output_path
            ]
            
            logger.info(f"Converting video to 9:16: {' '.join(cmd)}")
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                error_msg = f"FFmpeg conversion error: {stderr.decode()}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}
            
            # Verify output file exists and get info
            if not os.path.exists(output_path):
                return {'success': False, 'error': 'Output file was not created'}
            
            output_info = await self.get_video_info(output_path)
            
            logger.info(f"Successfully converted video to 9:16 format")
            
            return {
                'success': True,
                'input_path': input_path,
                'output_path': output_path,
                'input_info': video_info,
                'output_info': output_info,
                'conversion_type': 'vertical_9_16'
            }
            
        except Exception as e:
            error_msg = f"Video conversion error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    async def add_watermark_removal(self, input_path: str, output_path: str) -> Dict[str, Any]:
        """Attempt to remove watermarks from video (basic implementation)"""
        try:
            # This is a basic implementation that applies delogo filter
            # For production, you'd want more sophisticated watermark detection
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-vf', 'delogo=x=0:y=0:w=100:h=50:show=0',  # Adjust coordinates based on watermark position
                '-c:a', 'copy',  # Copy audio without re-encoding
                '-y',
                output_path
            ]
            
            logger.info(f"Applying watermark removal filter")
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                error_msg = f"Watermark removal error: {stderr.decode()}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}
            
            return {
                'success': True,
                'input_path': input_path,
                'output_path': output_path,
                'process_type': 'watermark_removal'
            }
            
        except Exception as e:
            error_msg = f"Watermark removal error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    async def enhance_video_quality(self, input_path: str, output_path: str) -> Dict[str, Any]:
        """Enhance video quality using FFmpeg filters"""
        try:
            # Apply various enhancement filters
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-vf', 'unsharp=5:5:1.0:5:5:0.0,eq=contrast=1.1:brightness=0.1:saturation=1.2',
                '-c:v', 'libx264',
                '-preset', 'slow',  # Better quality
                '-crf', '20',  # Higher quality
                '-c:a', 'aac',
                '-b:a', '128k',
                '-y',
                output_path
            ]
            
            logger.info(f"Enhancing video quality")
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                error_msg = f"Video enhancement error: {stderr.decode()}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}
            
            return {
                'success': True,
                'input_path': input_path,
                'output_path': output_path,
                'process_type': 'quality_enhancement'
            }
            
        except Exception as e:
            error_msg = f"Video enhancement error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    async def combine_videos(self, video_paths: List[str], output_path: str, 
                           transition_duration: float = 0.5) -> Dict[str, Any]:
        """Combine multiple videos with smooth transitions"""
        try:
            if len(video_paths) < 2:
                return {'success': False, 'error': 'At least 2 videos required for combining'}
            
            # Create a temporary concat file
            concat_file = os.path.join(self.temp_dir, f"concat_{uuid.uuid4().hex}.txt")
            
            with open(concat_file, 'w') as f:
                for video_path in video_paths:
                    f.write(f"file '{video_path}'\n")
            
            try:
                # Combine videos using concat demuxer
                cmd = [
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', concat_file,
                    '-c', 'copy',
                    '-y',
                    output_path
                ]
                
                logger.info(f"Combining {len(video_paths)} videos")
                
                result = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await result.communicate()
                
                if result.returncode != 0:
                    error_msg = f"Video combination error: {stderr.decode()}"
                    logger.error(error_msg)
                    return {'success': False, 'error': error_msg}
                
                return {
                    'success': True,
                    'input_videos': video_paths,
                    'output_path': output_path,
                    'video_count': len(video_paths),
                    'process_type': 'video_combination'
                }
                
            finally:
                # Clean up concat file
                if os.path.exists(concat_file):
                    os.remove(concat_file)
            
        except Exception as e:
            error_msg = f"Video combination error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    async def compress_video(self, input_path: str, output_path: str, 
                           target_size_mb: Optional[float] = None) -> Dict[str, Any]:
        """Compress video to reduce file size"""
        try:
            video_info = await self.get_video_info(input_path)
            if not video_info:
                return {'success': False, 'error': 'Could not analyze input video'}
            
            duration = video_info['duration']
            
            if target_size_mb:
                # Calculate target bitrate for desired file size
                target_size_bits = target_size_mb * 8 * 1024 * 1024  # Convert MB to bits
                target_bitrate = int(target_size_bits / duration)  # bits per second
                bitrate_str = f"{target_bitrate}k"
            else:
                # Use a moderate compression
                bitrate_str = "1000k"
            
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-c:v', 'libx264',
                '-b:v', bitrate_str,
                '-c:a', 'aac',
                '-b:a', '128k',
                '-preset', 'fast',
                '-y',
                output_path
            ]
            
            logger.info(f"Compressing video with target bitrate: {bitrate_str}")
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                error_msg = f"Video compression error: {stderr.decode()}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}
            
            output_info = await self.get_video_info(output_path)
            
            return {
                'success': True,
                'input_path': input_path,
                'output_path': output_path,
                'input_size_mb': video_info['size_bytes'] / (1024 * 1024),
                'output_size_mb': output_info['size_bytes'] / (1024 * 1024) if output_info else 0,
                'compression_ratio': (video_info['size_bytes'] / output_info['size_bytes']) if output_info else 1,
                'target_bitrate': bitrate_str,
                'process_type': 'video_compression'
            }
            
        except Exception as e:
            error_msg = f"Video compression error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def cleanup_temp_files(self):
        """Clean up temporary processing files"""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                os.makedirs(self.temp_dir, exist_ok=True)
            logger.info("Cleaned up temporary video processing files")
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {str(e)}")

# Global video processor instance
video_processor = VideoProcessor()