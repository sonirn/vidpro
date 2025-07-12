"""
RunwayML Gen-4 Turbo and Gen-3 Alpha Turbo Integration
Handles video generation using RunwayML's API
"""

import os
import asyncio
import httpx
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

class RunwayMLError(Exception):
    """Custom exception for RunwayML API errors"""
    pass

class RunwayMLClient:
    def __init__(self):
        self.api_key = os.environ.get('RUNWAY_API_KEY')
        self.base_url = "https://api.runwayml.com/v1"
        self.timeout = 300  # 5 minutes timeout
        
        # Log initialization status
        if self.api_key:
            logger.info("RunwayML client initialized with API key")
        else:
            logger.warning("RunwayML client initialized without API key - generation will fail")
    
    def _check_api_key(self):
        """Check if API key is available"""
        if not self.api_key:
            raise ValueError("RUNWAY_API_KEY environment variable is required")
        
    async def generate_video(
        self,
        prompt: str,
        model: str = "gen4",  # "gen4" or "gen3"
        image_url: Optional[str] = None,
        aspect_ratio: str = "9:16",
        duration: int = 5,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate a video using RunwayML API
        
        Args:
            prompt: Text description for video generation
            model: "gen4" for Gen-4 Turbo or "gen3" for Gen-3 Alpha Turbo
            image_url: Optional image URL for image-to-video generation
            aspect_ratio: Video aspect ratio (default "9:16")
            duration: Video duration in seconds (max 10)
            seed: Random seed for reproducible results
            
        Returns:
            Dict containing task_id and initial status
        """
        # Check API key availability
        self._check_api_key()
        
        try:
            # Determine the endpoint based on model
            if model == "gen4":
                endpoint = f"{self.base_url}/image_to_video"
            elif model == "gen3":
                endpoint = f"{self.base_url}/gen3/image_to_video"
            else:
                raise ValueError(f"Unsupported model: {model}. Use 'gen4' or 'gen3'")
            
            # Prepare request payload
            payload = {
                "promptText": prompt,
                "ratio": aspect_ratio,
                "duration": min(duration, 10),  # Cap at 10 seconds
                "seed": seed or int(datetime.now().timestamp())
            }
            
            # Add image if provided
            if image_url:
                payload["promptImage"] = image_url
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"Generating video with RunwayML {model}: {prompt[:100]}...")
                
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code != 200:
                    error_msg = f"RunwayML API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise RunwayMLError(error_msg)
                
                result = response.json()
                logger.info(f"RunwayML task created: {result.get('id', 'unknown')}")
                
                return {
                    "task_id": result.get("id"),
                    "status": "PENDING",
                    "model": model,
                    "prompt": prompt,
                    "created_at": datetime.utcnow().isoformat()
                }
                
        except httpx.TimeoutException:
            raise RunwayMLError("Request timeout - RunwayML API took too long to respond")
        except Exception as e:
            logger.error(f"RunwayML generation error: {str(e)}")
            raise RunwayMLError(f"Video generation failed: {str(e)}")
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Check the status of a RunwayML generation task
        
        Args:
            task_id: The task ID returned from generate_video
            
        Returns:
            Dict containing status and video URL if completed
        """
        try:
            endpoint = f"{self.base_url}/tasks/{task_id}"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(endpoint, headers=headers)
                
                if response.status_code != 200:
                    error_msg = f"Failed to get task status: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise RunwayMLError(error_msg)
                
                result = response.json()
                
                status_mapping = {
                    "PENDING": "PENDING",
                    "RUNNING": "PROCESSING", 
                    "SUCCEEDED": "COMPLETED",
                    "FAILED": "FAILED"
                }
                
                return {
                    "task_id": task_id,
                    "status": status_mapping.get(result.get("status"), "UNKNOWN"),
                    "progress": result.get("progress", 0),
                    "video_url": result.get("output", {}).get("url") if result.get("status") == "SUCCEEDED" else None,
                    "error": result.get("failure", {}).get("reason") if result.get("status") == "FAILED" else None,
                    "updated_at": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error checking RunwayML task status: {str(e)}")
            raise RunwayMLError(f"Failed to check task status: {str(e)}")
    
    async def wait_for_completion(
        self, 
        task_id: str, 
        max_wait_time: int = 600,  # 10 minutes
        poll_interval: int = 10
    ) -> Dict[str, Any]:
        """
        Wait for a RunwayML task to complete
        
        Args:
            task_id: The task ID to monitor
            max_wait_time: Maximum time to wait in seconds
            poll_interval: How often to check status in seconds
            
        Returns:
            Final task status
        """
        start_time = datetime.now()
        
        while True:
            status = await self.get_task_status(task_id)
            
            if status["status"] in ["COMPLETED", "FAILED"]:
                return status
            
            # Check if we've exceeded max wait time
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > max_wait_time:
                logger.warning(f"RunwayML task {task_id} exceeded max wait time")
                return {
                    "task_id": task_id,
                    "status": "TIMEOUT",
                    "error": f"Task exceeded maximum wait time of {max_wait_time} seconds"
                }
            
            logger.info(f"RunwayML task {task_id} still processing... ({status['progress']}%)")
            await asyncio.sleep(poll_interval)

    def select_best_model(self, video_type: str, duration: int) -> str:
        """
        Select the best RunwayML model based on video requirements
        
        Args:
            video_type: Type of video ("text_to_video", "image_to_video", etc.)
            duration: Desired duration in seconds
            
        Returns:
            Best model name ("gen4" or "gen3")
        """
        # Gen-4 Turbo is generally better for most use cases
        # Gen-3 Alpha Turbo is faster but lower quality
        
        if duration <= 5:
            return "gen4"  # Better quality for short videos
        else:
            return "gen3"  # Faster for longer videos
    
    async def generate_with_retry(
        self,
        prompt: str,
        max_retries: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate video with automatic retry logic
        
        Args:
            prompt: Video generation prompt
            max_retries: Maximum number of retry attempts
            **kwargs: Additional arguments for generate_video
            
        Returns:
            Generation result
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                return await self.generate_video(prompt, **kwargs)
            except RunwayMLError as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"RunwayML attempt {attempt + 1} failed, retrying in {wait_time}s: {str(e)}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All RunwayML retry attempts failed: {str(e)}")
        
        raise last_error

# Global instance
runway_client = RunwayMLClient()