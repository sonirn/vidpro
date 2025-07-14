"""
Video Generation Model Selection Service
Intelligently selects the best AI model (RunwayML vs Veo) based on video requirements
"""

import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class ModelSelector:
    def __init__(self):
        self.model_capabilities = {
            "runway_gen4": {
                "max_duration": 10,
                "quality": "high", 
                "speed": "medium",
                "strengths": ["realistic_motion", "image_to_video", "consistent_quality"],
                "best_for": ["short_clips", "product_videos", "social_media"],
                "type": "commercial"
            },
            "runway_gen3": {
                "max_duration": 10,
                "quality": "medium",
                "speed": "fast", 
                "strengths": ["quick_generation", "cost_effective"],
                "best_for": ["drafts", "quick_tests", "simple_scenes"],
                "type": "commercial"
            },
            "veo_2": {
                "max_duration": 8,
                "quality": "high",
                "speed": "medium",
                "strengths": ["natural_motion", "text_to_video", "creative_scenes"],
                "best_for": ["artistic_videos", "complex_scenes", "storytelling"],
                "type": "commercial"
            },
            "veo_3": {
                "max_duration": 10,
                "quality": "very_high", 
                "speed": "slow",
                "strengths": ["physics_simulation", "character_animation", "realistic_lighting"],
                "best_for": ["professional_videos", "complex_physics", "character_driven"],
                "type": "commercial"
            },
            "wan21_t2v_1_3b": {
                "max_duration": 60,
                "quality": "medium",
                "speed": "fast",
                "strengths": ["lightweight", "open_source", "cost_effective", "consumer_gpu"],
                "best_for": ["simple_scenes", "quick_generation", "budget_friendly"],
                "type": "open_source",
                "vram_required": "8.19GB",
                "supports_480p": True,
                "supports_720p": False
            },
            "wan21_t2v_14b": {
                "max_duration": 60,
                "quality": "high",
                "speed": "medium",
                "strengths": ["high_quality", "open_source", "720p_support", "complex_scenes"],
                "best_for": ["complex_scenes", "high_quality", "professional_videos"],
                "type": "open_source",
                "vram_required": "24GB+",
                "supports_480p": True,
                "supports_720p": True
            },
            "wan21_i2v_14b": {
                "max_duration": 60,
                "quality": "high",
                "speed": "medium",
                "strengths": ["image_to_video", "character_consistency", "open_source", "720p_support"],
                "best_for": ["character_videos", "image_animation", "consistent_character"],
                "type": "open_source",
                "vram_required": "24GB+",
                "supports_480p": False,
                "supports_720p": True
            },
            "wan21_flf2v_14b": {
                "max_duration": 60,
                "quality": "high", 
                "speed": "medium",
                "strengths": ["first_last_frame", "precise_control", "open_source", "720p_support"],
                "best_for": ["precise_transitions", "controlled_motion", "specific_outcomes"],
                "type": "open_source",
                "vram_required": "24GB+",
                "supports_480p": False,
                "supports_720p": True
            }
        }
    
    def analyze_video_requirements(self, video_analysis: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze video requirements from analysis and plan
        
        Args:
            video_analysis: Results from Gemini video analysis
            plan: Generated video plan
            
        Returns:
            Analyzed requirements
        """
        try:
            # Extract key characteristics from analysis and plan
            analysis_text = str(video_analysis).lower()
            plan_text = str(plan).lower()
            combined_text = f"{analysis_text} {plan_text}"
            
            requirements = {
                "duration": self._extract_duration(plan),
                "complexity": self._assess_complexity(combined_text),
                "motion_type": self._identify_motion_type(combined_text),
                "scene_type": self._identify_scene_type(combined_text),
                "priority": self._determine_priority(plan),
                "visual_effects": self._detect_visual_effects(combined_text),
                "character_focus": self._assess_character_focus(combined_text)
            }
            
            logger.info(f"Video requirements analyzed: {requirements}")
            return requirements
            
        except Exception as e:
            logger.error(f"Error analyzing video requirements: {str(e)}")
            return self._get_default_requirements()
    
    def _extract_duration(self, plan: Dict[str, Any]) -> int:
        """Extract desired duration from plan"""
        try:
            plan_text = str(plan).lower()
            
            # Look for duration mentions
            if "60 second" in plan_text or "1 minute" in plan_text:
                return 60
            elif "30 second" in plan_text:
                return 30
            elif "15 second" in plan_text:
                return 15
            elif "10 second" in plan_text:
                return 10
            elif "5 second" in plan_text:
                return 5
            else:
                return 8  # Default duration
                
        except Exception:
            return 8
    
    def _assess_complexity(self, text: str) -> str:
        """Assess video complexity from text analysis"""
        high_complexity_indicators = [
            "multiple characters", "complex scene", "detailed animation",
            "special effects", "physics simulation", "realistic lighting",
            "particle effects", "water", "fire", "smoke", "explosion",
            "crowd", "detailed background", "intricate", "sophisticated"
        ]
        
        medium_complexity_indicators = [
            "character movement", "camera motion", "multiple objects",
            "scene transitions", "moderate detail", "background action"
        ]
        
        high_count = sum(1 for indicator in high_complexity_indicators if indicator in text)
        medium_count = sum(1 for indicator in medium_complexity_indicators if indicator in text)
        
        if high_count >= 3:
            return "high"
        elif high_count >= 1 or medium_count >= 3:
            return "medium"
        else:
            return "low"
    
    def _identify_motion_type(self, text: str) -> str:
        """Identify the type of motion in the video"""
        motion_types = {
            "dynamic": ["fast motion", "action", "running", "flying", "dynamic", "energetic"],
            "smooth": ["smooth", "flowing", "gentle", "calm", "slow motion", "graceful"],
            "static": ["static", "still", "minimal motion", "subtle", "stationary"]
        }
        
        scores = {}
        for motion_type, indicators in motion_types.items():
            scores[motion_type] = sum(1 for indicator in indicators if indicator in text)
        
        return max(scores, key=scores.get) if any(scores.values()) else "smooth"
    
    def _identify_scene_type(self, text: str) -> str:
        """Identify the type of scene"""
        scene_types = {
            "product": ["product", "commercial", "advertisement", "showcase", "demo"],
            "narrative": ["story", "narrative", "character", "dialogue", "plot"],
            "abstract": ["abstract", "artistic", "creative", "experimental", "concept"],
            "realistic": ["realistic", "documentary", "real", "natural", "authentic"]
        }
        
        scores = {}
        for scene_type, indicators in scene_types.items():
            scores[scene_type] = sum(1 for indicator in indicators if indicator in text)
        
        return max(scores, key=scores.get) if any(scores.values()) else "realistic"
    
    def _determine_priority(self, plan: Dict[str, Any]) -> str:
        """Determine priority level from plan"""
        try:
            plan_text = str(plan).lower()
            
            if any(word in plan_text for word in ["urgent", "asap", "priority", "important"]):
                return "high"
            elif any(word in plan_text for word in ["quick", "fast", "draft", "test"]):
                return "speed"
            else:
                return "quality"
                
        except Exception:
            return "quality"
    
    def _detect_visual_effects(self, text: str) -> List[str]:
        """Detect required visual effects"""
        effects = []
        effect_indicators = {
            "particles": ["particles", "dust", "sparkles", "glitter"],
            "lighting": ["dramatic lighting", "cinematic lighting", "shadows"],
            "physics": ["physics", "gravity", "collision", "bouncing"],
            "weather": ["rain", "snow", "wind", "storm", "fog"],
            "fire_water": ["fire", "flames", "water", "liquid", "smoke"]
        }
        
        for effect, indicators in effect_indicators.items():
            if any(indicator in text for indicator in indicators):
                effects.append(effect)
        
        return effects
    
    def _assess_character_focus(self, text: str) -> str:
        """Assess focus on characters"""
        character_indicators = [
            "character", "person", "people", "human", "face", "portrait",
            "actor", "performer", "speaking", "dialogue", "emotion"
        ]
        
        character_count = sum(1 for indicator in character_indicators if indicator in text)
        
        if character_count >= 5:
            return "high"
        elif character_count >= 2:
            return "medium"
        else:
            return "low"
    
    def _get_default_requirements(self) -> Dict[str, Any]:
        """Get default requirements for fallback"""
        return {
            "duration": 8,
            "complexity": "medium",
            "motion_type": "smooth",
            "scene_type": "realistic",
            "priority": "quality",
            "visual_effects": [],
            "character_focus": "low"
        }
    
    def select_best_model(self, requirements: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
        """
        Select the best model based on requirements
        
        Args:
            requirements: Video requirements from analysis
            
        Returns:
            Tuple of (provider, model, reasoning)
        """
        try:
            scores = {}
            reasoning = {}
            
            # Score each model
            for model_name, capabilities in self.model_capabilities.items():
                score = 0
                model_reasoning = []
                
                # Duration compatibility
                if requirements["duration"] <= capabilities["max_duration"]:
                    score += 2
                    model_reasoning.append(f"Supports {requirements['duration']}s duration")
                else:
                    score -= 3
                    model_reasoning.append(f"Cannot support {requirements['duration']}s duration")
                
                # Complexity matching
                complexity_scores = {"low": 1, "medium": 2, "high": 3, "very_high": 4}
                quality_scores = {"medium": 2, "high": 3, "very_high": 4}
                
                complexity_needed = complexity_scores.get(requirements["complexity"], 2)
                model_quality = quality_scores.get(capabilities["quality"], 2)
                
                if model_quality >= complexity_needed:
                    score += 2
                    model_reasoning.append(f"Quality level matches complexity needs")
                else:
                    score -= 1
                    model_reasoning.append(f"Quality may not match complexity")
                
                # Priority matching (speed vs quality)
                if requirements["priority"] == "speed" and capabilities["speed"] in ["fast", "medium"]:
                    score += 2
                    model_reasoning.append("Good for speed priority")
                elif requirements["priority"] == "quality" and capabilities["quality"] in ["high", "very_high"]:
                    score += 2
                    model_reasoning.append("Good for quality priority")
                
                # Scene type matching
                if requirements["scene_type"] in capabilities["best_for"]:
                    score += 1
                    model_reasoning.append(f"Optimized for {requirements['scene_type']} scenes")
                
                # Visual effects capability
                if requirements["visual_effects"]:
                    if model_name in ["veo_3", "runway_gen4"]:  # High-end models
                        score += 1
                        model_reasoning.append("Capable of visual effects")
                
                # Character focus
                if requirements["character_focus"] == "high" and model_name == "veo_3":
                    score += 1
                    model_reasoning.append("Excellent for character-focused videos")
                
                # Wan 2.1 specific scoring
                if model_name.startswith("wan21"):
                    # Boost for open source preference
                    score += 1
                    model_reasoning.append("Open source solution")
                    
                    # Boost for longer duration needs
                    if requirements["duration"] > 10:
                        score += 3
                        model_reasoning.append("Supports longer duration videos")
                    
                    # Character image availability
                    if "i2v" in model_name and requirements.get("has_character_image", False):
                        score += 3
                        model_reasoning.append("Perfect for character image input")
                    
                    # Budget consideration
                    if requirements["priority"] == "cost":
                        score += 2
                        model_reasoning.append("Cost-effective solution")
                    
                    # Hardware considerations
                    if "1_3b" in model_name and requirements.get("hardware_constraint", False):
                        score += 2
                        model_reasoning.append("Works on consumer hardware")
                
                # Penalize commercial models for longer durations
                if requirements["duration"] > 10 and model_name.startswith(("runway", "veo")):
                    score -= 2
                    model_reasoning.append("Limited duration for commercial models")
                
                scores[model_name] = score
                reasoning[model_name] = model_reasoning
            
            # Select best model
            best_model = max(scores, key=scores.get)
            
            # Determine provider
            if "runway" in best_model:
                provider = "runway"
                model = best_model.split("_")[1]  # "gen4" or "gen3"
            else:
                provider = "veo"
                model = best_model.replace("_", "-")  # "veo-2" or "veo-3"
            
            selection_reasoning = {
                "selected_model": best_model,
                "score": scores[best_model],
                "reasoning": reasoning[best_model],
                "all_scores": scores,
                "requirements_matched": requirements
            }
            
            logger.info(f"Selected {provider}/{model} with score {scores[best_model]}")
            return provider, model, selection_reasoning
            
        except Exception as e:
            logger.error(f"Error in model selection: {str(e)}")
            # Fallback to Runway Gen4
            return "runway", "gen4", {"error": str(e), "fallback": True}
    
    def get_model_recommendations(self, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get detailed model recommendations with explanations
        
        Args:
            requirements: Video requirements
            
        Returns:
            Detailed recommendations
        """
        provider, model, reasoning = self.select_best_model(requirements)
        
        # Get alternative recommendations
        alternatives = []
        scores = reasoning.get("all_scores", {})
        
        for model_name, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)[1:3]:
            if "runway" in model_name:
                alt_provider = "runway"
                alt_model = model_name.split("_")[1]
            else:
                alt_provider = "veo"
                alt_model = model_name.replace("_", "-")
            
            alternatives.append({
                "provider": alt_provider,
                "model": alt_model,
                "score": score,
                "why": f"Alternative option with score {score}"
            })
        
        return {
            "primary_recommendation": {
                "provider": provider,
                "model": model,
                "reasoning": reasoning
            },
            "alternatives": alternatives,
            "requirements_analysis": requirements,
            "timestamp": datetime.utcnow().isoformat()
        }

# Global instance
model_selector = ModelSelector()