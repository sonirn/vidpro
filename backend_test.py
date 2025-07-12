#!/usr/bin/env python3
"""
Backend API Testing Script for Video Generation Application
Tests all core API endpoints and functionality
"""

import requests
import json
import time
import os
import tempfile
import uuid
from pathlib import Path

# Configuration
BACKEND_URL = "https://01aaca64-0bf3-416f-a5c1-b94b866f5fea.preview.emergentagent.com/api"
TEST_TIMEOUT = 30

class VideoGenerationAPITester:
    def __init__(self):
        self.session = requests.Session()
        self.test_results = []
        self.video_id = None
        self.session_id = str(uuid.uuid4())
        
    def log_test(self, test_name, success, message, details=None):
        """Log test results"""
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "details": details or {}
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name} - {message}")
        if details and not success:
            print(f"   Details: {details}")
    
    def create_test_video_file(self):
        """Create a small test MP4 file for upload testing"""
        try:
            # Create a minimal MP4 file (just headers, not a real video)
            mp4_header = b'\x00\x00\x00\x20ftypmp41\x00\x00\x00\x00mp41isom\x00\x00\x00\x08free'
            
            temp_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
            temp_file.write(mp4_header)
            temp_file.write(b'\x00' * 1000)  # Add some dummy data
            temp_file.close()
            
            return temp_file.name
        except Exception as e:
            self.log_test("Create Test Video", False, f"Failed to create test video: {str(e)}")
            return None
    
    def test_health_check(self):
        """Test GET /api/ endpoint"""
        try:
            response = self.session.get(f"{BACKEND_URL}/", timeout=TEST_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                if "message" in data:
                    self.log_test("Health Check", True, "API is running", {"response": data})
                    return True
                else:
                    self.log_test("Health Check", False, "Invalid response format", {"response": data})
            else:
                self.log_test("Health Check", False, f"HTTP {response.status_code}", {"response": response.text})
        except Exception as e:
            self.log_test("Health Check", False, f"Connection error: {str(e)}")
        return False
    
    def test_video_upload(self):
        """Test POST /api/upload-video endpoint"""
        test_file_path = self.create_test_video_file()
        if not test_file_path:
            return False
            
        try:
            with open(test_file_path, 'rb') as f:
                files = {'file': ('test_video.mp4', f, 'video/mp4')}
                data = {'user_prompt': 'Test video upload for API testing'}
                
                response = self.session.post(
                    f"{BACKEND_URL}/upload-video",
                    files=files,
                    data=data,
                    timeout=TEST_TIMEOUT
                )
            
            # Clean up test file
            os.unlink(test_file_path)
            
            if response.status_code == 200:
                data = response.json()
                if "id" in data and "status" in data:
                    self.video_id = data["id"]
                    self.log_test("Video Upload", True, f"Video uploaded successfully", {
                        "video_id": self.video_id,
                        "status": data["status"],
                        "filename": data.get("filename")
                    })
                    return True
                else:
                    self.log_test("Video Upload", False, "Invalid response format", {"response": data})
            else:
                self.log_test("Video Upload", False, f"HTTP {response.status_code}", {"response": response.text})
        except Exception as e:
            self.log_test("Video Upload", False, f"Upload error: {str(e)}")
            # Clean up test file if it exists
            try:
                os.unlink(test_file_path)
            except:
                pass
        return False
    
    def test_video_status(self):
        """Test GET /api/video-status/{video_id} endpoint"""
        if not self.video_id:
            self.log_test("Video Status", False, "No video ID available from upload test")
            return False
            
        try:
            response = self.session.get(
                f"{BACKEND_URL}/video-status/{self.video_id}",
                timeout=TEST_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                if "id" in data and "status" in data:
                    self.log_test("Video Status", True, f"Status retrieved successfully", {
                        "video_id": data["id"],
                        "status": data["status"],
                        "progress": data.get("progress", 0)
                    })
                    return True
                else:
                    self.log_test("Video Status", False, "Invalid response format", {"response": data})
            elif response.status_code == 404:
                self.log_test("Video Status", False, "Video not found in database", {"video_id": self.video_id})
            else:
                self.log_test("Video Status", False, f"HTTP {response.status_code}", {"response": response.text})
        except Exception as e:
            self.log_test("Video Status", False, f"Status check error: {str(e)}")
        return False
    
    def test_chat_interface(self):
        """Test POST /api/chat endpoint"""
        if not self.video_id:
            self.log_test("Chat Interface", False, "No video ID available for chat test")
            return False
            
        try:
            chat_data = {
                "message": "Can you make the video more colorful and add upbeat music?",
                "video_id": self.video_id,
                "session_id": self.session_id
            }
            
            response = self.session.post(
                f"{BACKEND_URL}/chat",
                json=chat_data,
                timeout=TEST_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                if "response" in data:
                    self.log_test("Chat Interface", True, "Chat response received", {
                        "response_length": len(data["response"]),
                        "has_updated_plan": "updated_plan" in data
                    })
                    return True
                else:
                    self.log_test("Chat Interface", False, "Invalid response format", {"response": data})
            elif response.status_code == 404:
                self.log_test("Chat Interface", False, "Video not found for chat", {"video_id": self.video_id})
            elif response.status_code == 400:
                self.log_test("Chat Interface", False, "Video plan not ready yet", {"video_id": self.video_id})
            else:
                self.log_test("Chat Interface", False, f"HTTP {response.status_code}", {"response": response.text})
        except Exception as e:
            self.log_test("Chat Interface", False, f"Chat error: {str(e)}")
        return False
    
    def test_video_generation(self):
        """Test POST /api/generate-video endpoint"""
        if not self.video_id:
            self.log_test("Video Generation", False, "No video ID available for generation test")
            return False
            
        try:
            generation_data = {
                "video_id": self.video_id,
                "final_plan": "Create a colorful 30-second video with upbeat music showcasing the analyzed content",
                "session_id": self.session_id
            }
            
            response = self.session.post(
                f"{BACKEND_URL}/generate-video",
                json=generation_data,
                timeout=TEST_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                if "message" in data and "video_id" in data:
                    self.log_test("Video Generation", True, "Video generation started", {
                        "message": data["message"],
                        "video_id": data["video_id"]
                    })
                    return True
                else:
                    self.log_test("Video Generation", False, "Invalid response format", {"response": data})
            else:
                self.log_test("Video Generation", False, f"HTTP {response.status_code}", {"response": response.text})
        except Exception as e:
            self.log_test("Video Generation", False, f"Generation error: {str(e)}")
        return False
    
    def test_user_videos(self):
        """Test GET /api/user-videos endpoint"""
        try:
            response = self.session.get(f"{BACKEND_URL}/user-videos", timeout=TEST_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    self.log_test("User Videos", True, f"Retrieved {len(data)} videos", {
                        "video_count": len(data),
                        "has_test_video": any(v.get("id") == self.video_id for v in data) if self.video_id else False
                    })
                    return True
                else:
                    self.log_test("User Videos", False, "Invalid response format - expected list", {"response": data})
            else:
                self.log_test("User Videos", False, f"HTTP {response.status_code}", {"response": response.text})
        except Exception as e:
            self.log_test("User Videos", False, f"User videos error: {str(e)}")
        return False
    
    def test_file_validation(self):
        """Test file type validation"""
        try:
            # Create a text file with .txt extension
            temp_file = tempfile.NamedTemporaryFile(suffix='.txt', delete=False)
            temp_file.write(b'This is not a video file')
            temp_file.close()
            
            with open(temp_file.name, 'rb') as f:
                files = {'file': ('test_file.txt', f, 'text/plain')}
                
                response = self.session.post(
                    f"{BACKEND_URL}/upload-video",
                    files=files,
                    timeout=TEST_TIMEOUT
                )
            
            # Clean up
            os.unlink(temp_file.name)
            
            if response.status_code == 400:
                self.log_test("File Validation", True, "Correctly rejected non-video file", {
                    "status_code": response.status_code
                })
                return True
            else:
                self.log_test("File Validation", False, f"Should have rejected non-video file, got HTTP {response.status_code}")
        except Exception as e:
            self.log_test("File Validation", False, f"File validation test error: {str(e)}")
        return False
    
    def test_mongodb_connection(self):
        """Test MongoDB connection by checking if data persists"""
        if not self.video_id:
            self.log_test("MongoDB Connection", False, "No video ID to test database persistence")
            return False
            
        try:
            # Wait a moment for any background processing
            time.sleep(2)
            
            # Check if video exists in database by calling status endpoint
            response = self.session.get(
                f"{BACKEND_URL}/video-status/{self.video_id}",
                timeout=TEST_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("id") == self.video_id:
                    self.log_test("MongoDB Connection", True, "Data persisted successfully in MongoDB", {
                        "video_id": self.video_id,
                        "status": data.get("status")
                    })
                    return True
                else:
                    self.log_test("MongoDB Connection", False, "Video ID mismatch in database")
            else:
                self.log_test("MongoDB Connection", False, f"Could not retrieve video from database: HTTP {response.status_code}")
        except Exception as e:
            self.log_test("MongoDB Connection", False, f"Database connection test error: {str(e)}")
        return False
    
    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting Video Generation API Tests")
        print(f"Backend URL: {BACKEND_URL}")
        print("=" * 60)
        
        # Core API tests
        tests = [
            ("Health Check", self.test_health_check),
            ("Video Upload", self.test_video_upload),
            ("Video Status", self.test_video_status),
            ("MongoDB Connection", self.test_mongodb_connection),
            ("Chat Interface", self.test_chat_interface),
            ("Video Generation", self.test_video_generation),
            ("User Videos", self.test_user_videos),
            ("File Validation", self.test_file_validation),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n🧪 Running: {test_name}")
            if test_func():
                passed += 1
            time.sleep(1)  # Brief pause between tests
        
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed! Backend API is working correctly.")
        else:
            print("⚠️  Some tests failed. Check the details above.")
        
        return passed, total, self.test_results

def main():
    """Main test execution"""
    tester = VideoGenerationAPITester()
    passed, total, results = tester.run_all_tests()
    
    # Print detailed summary
    print("\n" + "=" * 60)
    print("📋 DETAILED TEST SUMMARY")
    print("=" * 60)
    
    for result in results:
        status = "✅" if result["success"] else "❌"
        print(f"{status} {result['test']}: {result['message']}")
        if result["details"] and not result["success"]:
            print(f"   └─ {result['details']}")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)