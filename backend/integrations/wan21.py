"""
Wan 2.1 Open Source Model Integration

This module provides integration with Wan 2.1 open-source video generation models.
Supports T2V-1.3B, T2V-14B, I2V-14B, and FLF2V-14B models.
"""

import os
import asyncio
import subprocess
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Optional, List, Any, Union
from dataclasses import dataclass
from enum import Enum
import logging
import time
import uuid

logger = logging.getLogger(__name__)

class Wan21Model(Enum):
    """Available Wan 2.1 models"""
    T2V_1_3B = "t2v-1.3b"
    T2V_14B = "t2v-14b"
    I2V_14B = "i2v-14b"
    FLF2V_14B = "flf2v-14b"

class Wan21Task(Enum):
    """Available Wan 2.1 tasks"""
    TEXT_TO_VIDEO = "text2video"
    IMAGE_TO_VIDEO = "image2video"
    FIRST_LAST_FRAME_TO_VIDEO = "first_last_frame2video"

@dataclass
class Wan21Config:
    """Configuration for Wan 2.1 models"""
    model: Wan21Model
    size: str = "832*480"  # Default 480p resolution
    ckpt_dir: str = ""
    offload_model: bool = True
    t5_cpu: bool = True
    sample_shift: int = 8
    sample_guide_scale: float = 6.0
    use_prompt_extend: bool = False
    prompt_extend_method: str = "local_qwen"
    prompt_extend_target_lang: str = "en"

class Wan21Generator:
    """Main class for Wan 2.1 video generation"""
    
    def __init__(self, config: Wan21Config):
        self.config = config
        self.wan21_root = Path("/app/wan21/Wan2.1")
        self.models_dir = Path("/app/wan21/models")
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if Wan 2.1 is properly installed
        if not self.wan21_root.exists():
            raise RuntimeError("Wan 2.1 not found. Please ensure it's properly installed.")
            
        # Model paths mapping
        self.model_paths = {
            Wan21Model.T2V_1_3B: self.models_dir / "Wan2.1-T2V-1.3B",
            Wan21Model.T2V_14B: self.models_dir / "Wan2.1-T2V-14B",
            Wan21Model.I2V_14B: self.models_dir / "Wan2.1-I2V-14B-720P",
            Wan21Model.FLF2V_14B: self.models_dir / "Wan2.1-FLF2V-14B-720P"
        }
        
        # Set checkpoint directory
        if not self.config.ckpt_dir:
            self.config.ckpt_dir = str(self.model_paths[self.config.model])
    
    async def ensure_model_downloaded(self) -> bool:
        """Ensure the required model is downloaded"""
        model_path = Path(self.config.ckpt_dir)
        
        if model_path.exists() and any(model_path.iterdir()):
            logger.info(f"Model {self.config.model.value} already exists at {model_path}")
            return True
            
        logger.info(f"Downloading model {self.config.model.value}...")
        
        # Model download URLs
        model_urls = {
            Wan21Model.T2V_1_3B: "Wan-AI/Wan2.1-T2V-1.3B",
            Wan21Model.T2V_14B: "Wan-AI/Wan2.1-T2V-14B", 
            Wan21Model.I2V_14B: "Wan-AI/Wan2.1-I2V-14B-720P",
            Wan21Model.FLF2V_14B: "Wan-AI/Wan2.1-FLF2V-14B-720P"
        }
        
        try:
            # Download using huggingface-cli
            cmd = [
                "huggingface-cli", "download", 
                model_urls[self.config.model],
                "--local-dir", str(model_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.wan21_root)
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"Model {self.config.model.value} downloaded successfully")
                return True
            else:
                logger.error(f"Model download failed: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"Error downloading model: {e}")
            return False

    async def generate_video(self, 
                           prompt: str,
                           image_path: Optional[str] = None,
                           first_frame_path: Optional[str] = None,
                           last_frame_path: Optional[str] = None,
                           output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate video using Wan 2.1
        
        Args:
            prompt: Text prompt for video generation
            image_path: Path to image for I2V generation
            first_frame_path: Path to first frame for FLF2V generation
            last_frame_path: Path to last frame for FLF2V generation
            output_path: Path to save generated video
            
        Returns:
            Dict containing generation results
        """
        
        # Ensure model is downloaded
        if not await self.ensure_model_downloaded():
            return {
                "success": False,
                "error": "Failed to download model",
                "video_path": None
            }
        
        # Create temporary output directory if not provided
        if not output_path:
            output_path = f"/tmp/wan21_output_{uuid.uuid4().hex}.mp4"
        
        # Build command based on model type
        cmd = await self._build_command(
            prompt=prompt,
            image_path=image_path,
            first_frame_path=first_frame_path,
            last_frame_path=last_frame_path,
            output_path=output_path
        )
        
        try:
            logger.info(f"Executing Wan 2.1 generation: {' '.join(cmd)}")
            
            # Execute the generation command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.wan21_root)
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("Video generation completed successfully")
                
                # Check if output file exists
                if Path(output_path).exists():
                    return {
                        "success": True,
                        "video_path": output_path,
                        "model_used": self.config.model.value,
                        "prompt": prompt,
                        "stdout": stdout.decode(),
                        "stderr": stderr.decode()
                    }
                else:
                    return {
                        "success": False,
                        "error": "Video file not generated",
                        "stdout": stdout.decode(),
                        "stderr": stderr.decode()
                    }
            else:
                logger.error(f"Video generation failed: {stderr.decode()}")
                return {
                    "success": False,
                    "error": f"Generation failed with return code {process.returncode}",
                    "stdout": stdout.decode(),
                    "stderr": stderr.decode()
                }
                
        except Exception as e:
            logger.error(f"Error during video generation: {e}")
            return {
                "success": False,
                "error": str(e),
                "video_path": None
            }

    async def _build_command(self, 
                           prompt: str,
                           image_path: Optional[str] = None,
                           first_frame_path: Optional[str] = None,
                           last_frame_path: Optional[str] = None,
                           output_path: str = None) -> List[str]:
        """Build the command for Wan 2.1 generation"""
        
        cmd = [
            "python", "generate.py",
            "--task", self.config.model.value,
            "--size", self.config.size,
            "--ckpt_dir", self.config.ckpt_dir,
            "--prompt", prompt
        ]
        
        # Add model-specific parameters
        if self.config.model == Wan21Model.T2V_1_3B:
            cmd.extend([
                "--sample_shift", str(self.config.sample_shift),
                "--sample_guide_scale", str(self.config.sample_guide_scale)
            ])
        
        # Add memory optimization flags
        if self.config.offload_model:
            cmd.append("--offload_model")
            cmd.append("True")
            
        if self.config.t5_cpu:
            cmd.append("--t5_cpu")
        
        # Add image for I2V generation
        if image_path and self.config.model == Wan21Model.I2V_14B:
            cmd.extend(["--image", image_path])
            
        # Add frames for FLF2V generation
        if first_frame_path and last_frame_path and self.config.model == Wan21Model.FLF2V_14B:
            cmd.extend(["--first_frame", first_frame_path])
            cmd.extend(["--last_frame", last_frame_path])
        
        # Add prompt extension if enabled
        if self.config.use_prompt_extend:
            cmd.append("--use_prompt_extend")
            cmd.extend(["--prompt_extend_method", self.config.prompt_extend_method])
            cmd.extend(["--prompt_extend_target_lang", self.config.prompt_extend_target_lang])
        
        # Add output path
        if output_path:
            cmd.extend(["--output", output_path])
            
        return cmd
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model"""
        return {
            "model": self.config.model.value,
            "size": self.config.size,
            "ckpt_dir": self.config.ckpt_dir,
            "offload_model": self.config.offload_model,
            "t5_cpu": self.config.t5_cpu,
            "model_downloaded": Path(self.config.ckpt_dir).exists()
        }

class Wan21Service:
    """Service wrapper for Wan 2.1 integration"""
    
    def __init__(self):
        self.generators = {}
        
    def get_generator(self, model: Wan21Model, size: str = "832*480") -> Wan21Generator:
        """Get or create a generator for the specified model"""
        
        key = f"{model.value}_{size}"
        
        if key not in self.generators:
            config = Wan21Config(
                model=model,
                size=size,
                offload_model=True,
                t5_cpu=True
            )
            self.generators[key] = Wan21Generator(config)
            
        return self.generators[key]
    
    async def generate_text_to_video(self, 
                                   prompt: str, 
                                   model: Wan21Model = Wan21Model.T2V_1_3B,
                                   size: str = "832*480") -> Dict[str, Any]:
        """Generate video from text prompt"""
        
        generator = self.get_generator(model, size)
        return await generator.generate_video(prompt=prompt)
    
    async def generate_image_to_video(self, 
                                    prompt: str,
                                    image_path: str,
                                    model: Wan21Model = Wan21Model.I2V_14B,
                                    size: str = "1280*720") -> Dict[str, Any]:
        """Generate video from image and text prompt"""
        
        generator = self.get_generator(model, size)
        return await generator.generate_video(prompt=prompt, image_path=image_path)
    
    async def generate_first_last_frame_to_video(self, 
                                               prompt: str,
                                               first_frame_path: str,
                                               last_frame_path: str,
                                               model: Wan21Model = Wan21Model.FLF2V_14B,
                                               size: str = "1280*720") -> Dict[str, Any]:
        """Generate video from first and last frames"""
        
        generator = self.get_generator(model, size)
        return await generator.generate_video(
            prompt=prompt,
            first_frame_path=first_frame_path,
            last_frame_path=last_frame_path
        )
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available models"""
        return [
            {
                "model": Wan21Model.T2V_1_3B.value,
                "name": "Text-to-Video 1.3B",
                "description": "Lightweight text-to-video model (8.19GB VRAM)",
                "supported_resolutions": ["832*480"],
                "task": "text2video"
            },
            {
                "model": Wan21Model.T2V_14B.value,
                "name": "Text-to-Video 14B",
                "description": "High-quality text-to-video model (24GB+ VRAM)",
                "supported_resolutions": ["832*480", "1280*720"],
                "task": "text2video"
            },
            {
                "model": Wan21Model.I2V_14B.value,
                "name": "Image-to-Video 14B",
                "description": "High-quality image-to-video model (24GB+ VRAM)",
                "supported_resolutions": ["1280*720"],
                "task": "image2video"
            },
            {
                "model": Wan21Model.FLF2V_14B.value,
                "name": "First-Last-Frame-to-Video 14B",
                "description": "First and last frame to video model (24GB+ VRAM)",
                "supported_resolutions": ["1280*720"],
                "task": "first_last_frame2video"
            }
        ]

# Global service instance
wan21_service = Wan21Service()