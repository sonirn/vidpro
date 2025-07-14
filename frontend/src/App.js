import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import AuthComponent from './components/AuthComponent';
import UserDashboard from './components/UserDashboard';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const VideoUpload = ({ onUploadSuccess }) => {
  const [file, setFile] = useState(null);
  const [userPrompt, setUserPrompt] = useState('');
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const { getAuthHeaders } = useAuth();

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      setFile(droppedFile);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    if (userPrompt) {
      formData.append('context', userPrompt);
    }

    try {
      const response = await axios.post(`${API}/upload`, formData, {
        headers: { 
          'Content-Type': 'multipart/form-data',
          ...getAuthHeaders()
        }
      });
      
      onUploadSuccess(response.data);
      setFile(null);
      setUserPrompt('');
    } catch (error) {
      console.error('Upload failed:', error);
      alert('Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-xl p-8 max-w-2xl mx-auto">
      <h2 className="text-3xl font-bold text-gray-800 mb-6 text-center">Upload Your Sample Video</h2>
      
      <div 
        className={`border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300 ${
          dragOver ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <div className="space-y-4">
          <div className="mx-auto w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>
          
          {file ? (
            <div className="text-center">
              <p className="text-lg font-semibold text-gray-700">{file.name}</p>
              <p className="text-sm text-gray-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
            </div>
          ) : (
            <div>
              <p className="text-xl font-semibold text-gray-700 mb-2">Drop your video here</p>
              <p className="text-gray-500 mb-4">or click to browse</p>
              <p className="text-sm text-gray-400">Supports MP4, MOV, AVI • Max 60 seconds</p>
            </div>
          )}
          
          <input
            type="file"
            accept="video/*"
            onChange={handleFileChange}
            className="hidden"
            id="video-upload"
          />
          <label
            htmlFor="video-upload"
            className="inline-block bg-gradient-to-r from-blue-500 to-purple-600 text-white px-6 py-3 rounded-lg font-semibold cursor-pointer hover:from-blue-600 hover:to-purple-700 transition-all duration-200"
          >
            Choose Video
          </label>
        </div>
      </div>

      <div className="mt-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Additional Context (Optional)
        </label>
        <textarea
          value={userPrompt}
          onChange={(e) => setUserPrompt(e.target.value)}
          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
          rows="3"
          placeholder="Describe what you want to emphasize or any specific requirements..."
        />
      </div>

      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        className={`w-full mt-6 py-4 px-6 rounded-lg font-semibold text-white transition-all duration-200 ${
          !file || uploading 
            ? 'bg-gray-400 cursor-not-allowed' 
            : 'bg-gradient-to-r from-green-500 to-blue-600 hover:from-green-600 hover:to-blue-700 transform hover:scale-105'
        }`}
      >
        {uploading ? (
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-3"></div>
            Uploading & Analyzing...
          </div>
        ) : (
          'Upload & Analyze Video'
        )}
      </button>
    </div>
  );
};

const VideoStatus = ({ videoId, onStatusChange }) => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const { getAuthHeaders } = useAuth();

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await axios.get(`${API}/status/${videoId}`, {
          headers: getAuthHeaders()
        });
        setStatus(response.data);
        onStatusChange(response.data);
        setLoading(false);
      } catch (error) {
        console.error('Error fetching status:', error);
        setLoading(false);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 3000); // Poll every 3 seconds

    return () => clearInterval(interval);
  }, [videoId, onStatusChange, getAuthHeaders]);

  if (loading) {
    return (
      <div className="bg-white rounded-2xl shadow-xl p-8 max-w-2xl mx-auto">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-3/4 mb-4"></div>
          <div className="h-2 bg-gray-200 rounded w-full"></div>
        </div>
      </div>
    );
  }

  if (!status) return null;

  const getStatusColor = () => {
    switch (status.status) {
      case 'completed': return 'text-green-600';
      case 'error': return 'text-red-600';
      case 'generating': return 'text-blue-600';
      default: return 'text-yellow-600';
    }
  };

  const getStatusText = () => {
    switch (status.status) {
      case 'uploaded': return 'Video uploaded successfully';
      case 'analyzing': return 'Analyzing your video...';
      case 'planning': return 'Creating video plan...';
      case 'analyzed': return 'Analysis complete! Review your plan below.';
      case 'generating': return 'Generating your video...';
      case 'completed': return 'Your video is ready!';
      case 'error': return 'An error occurred';
      default: return 'Processing...';
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-xl p-8 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-2xl font-bold text-gray-800">Video Processing Status</h3>
        <span className={`text-lg font-semibold ${getStatusColor()}`}>
          {getStatusText()}
        </span>
      </div>

      <div className="mb-6">
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm text-gray-600">Progress</span>
          <span className="text-sm font-semibold text-gray-800">{status.progress}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-3">
          <div 
            className="bg-gradient-to-r from-blue-500 to-purple-600 h-3 rounded-full transition-all duration-300"
            style={{ width: `${status.progress}%` }}
          ></div>
        </div>
      </div>

      {status.error_message && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
          <p className="text-red-800">{status.error_message}</p>
        </div>
      )}

      {status.plan && (
        <div className="bg-gray-50 rounded-lg p-6 mb-4">
          <h4 className="text-lg font-semibold text-gray-800 mb-3">Video Creation Plan</h4>
          <div className="text-gray-700 whitespace-pre-wrap max-h-96 overflow-y-auto">
            {status.plan}
          </div>
        </div>
      )}

      {status.final_video_url && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <p className="text-green-800 font-semibold mb-2">Video Generation Complete!</p>
          <a 
            href={status.final_video_url} 
            download
            className="inline-block bg-green-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-green-700 transition-colors"
          >
            Download Video
          </a>
        </div>
      )}
    </div>
  );
};

const ChatInterface = ({ videoId, currentPlan, onPlanUpdate }) => {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [sessionId] = useState(() => `session_${Date.now()}`);
  const { getAuthHeaders } = useAuth();

  const sendMessage = async () => {
    if (!inputMessage.trim()) return;

    const userMessage = { role: 'user', content: inputMessage };
    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');

    try {
      const response = await axios.post(`${API}/chat/${videoId}`, {
        message: inputMessage,
        video_id: videoId,
        session_id: sessionId
      }, {
        headers: getAuthHeaders()
      });

      const botMessage = { role: 'assistant', content: response.data.response };
      setMessages(prev => [...prev, botMessage]);

      if (response.data.updated_plan) {
        onPlanUpdate(response.data.updated_plan);
      }
    } catch (error) {
      console.error('Chat error:', error);
      const errorMessage = { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' };
      setMessages(prev => [...prev, errorMessage]);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-xl p-6 max-w-4xl mx-auto mt-6">
      <h3 className="text-xl font-bold text-gray-800 mb-4">Chat to Modify Your Plan</h3>
      
      <div className="h-64 overflow-y-auto bg-gray-50 rounded-lg p-4 mb-4">
        {messages.length === 0 ? (
          <p className="text-gray-500 text-center">Ask me to modify your video plan or ask questions about the generation process.</p>
        ) : (
          messages.map((msg, index) => (
            <div key={index} className={`mb-3 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
              <div className={`inline-block p-3 rounded-lg max-w-xs ${
                msg.role === 'user' 
                  ? 'bg-blue-500 text-white' 
                  : 'bg-white border border-gray-200'
              }`}>
                {msg.content}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="flex space-x-2">
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="Type your message..."
          className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <button
          onClick={sendMessage}
          className="bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600 transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  );
};

const MainApp = () => {
  const [currentStep, setCurrentStep] = useState('upload'); // 'upload', 'processing', 'chat', 'generate'
  const [videoId, setVideoId] = useState(null);
  const [videoStatus, setVideoStatus] = useState(null);
  const [currentPlan, setCurrentPlan] = useState('');
  const [showDashboard, setShowDashboard] = useState(false);
  const { getAuthHeaders } = useAuth();

  const handleUploadSuccess = (uploadData) => {
    setVideoId(uploadData.video_id);
    setCurrentStep('processing');
    setShowDashboard(false);
    
    // Start analysis automatically
    setTimeout(() => {
      startVideoAnalysis(uploadData.video_id);
    }, 1000);
  };

  const startVideoAnalysis = async (videoId) => {
    try {
      await axios.post(`${API}/analyze/${videoId}`, {
        video_id: videoId,
        user_prompt: ''
      }, {
        headers: getAuthHeaders()
      });
    } catch (error) {
      console.error('Error starting video analysis:', error);
      alert('Failed to start video analysis. Please try again.');
    }
  };

  const handleStatusChange = (status) => {
    setVideoStatus(status);
    if (status.plan) {
      setCurrentPlan(status.plan);
    }
    if (status.status === 'planned') {
      setCurrentStep('chat');
    }
  };

  const handlePlanUpdate = (newPlan) => {
    setCurrentPlan(newPlan);
  };

  const startVideoGeneration = async () => {
    try {
      await axios.post(`${API}/generate-video`, {
        video_id: videoId,
        final_plan: currentPlan,
        session_id: `session_${Date.now()}`
      }, {
        headers: getAuthHeaders()
      });
      setCurrentStep('processing');
    } catch (error) {
      console.error('Error starting video generation:', error);
      alert('Failed to start video generation. Please try again.');
    }
  };

  const resetApp = () => {
    setCurrentStep('upload');
    setVideoId(null);
    setVideoStatus(null);
    setCurrentPlan('');
    setShowDashboard(false);
  };

  const showUserDashboard = () => {
    setShowDashboard(true);
  };

  const startNewProject = () => {
    setShowDashboard(false);
    resetApp();
  };

  if (showDashboard) {
    return <UserDashboard onStartNewProject={startNewProject} />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900">
      <div className="container mx-auto px-4 py-8">
        {/* Header with Dashboard Button */}
        <div className="flex justify-between items-center mb-8">
          <div className="text-center flex-1">
            <h1 className="text-5xl font-bold bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent mb-4">
              AI Video Generator
            </h1>
            <p className="text-xl text-gray-300 max-w-2xl mx-auto">
              Upload your sample video and let AI create a similar masterpiece in 9:16 format
            </p>
          </div>
          <button
            onClick={showUserDashboard}
            className="bg-white/10 hover:bg-white/20 text-white font-medium py-2 px-4 rounded-xl transition-all duration-200 border border-white/20"
          >
            Dashboard
          </button>
        </div>

        {currentStep === 'upload' && (
          <VideoUpload onUploadSuccess={handleUploadSuccess} />
        )}

        {currentStep === 'processing' && videoId && (
          <VideoStatus 
            videoId={videoId} 
            onStatusChange={handleStatusChange}
          />
        )}

        {currentStep === 'chat' && videoId && currentPlan && (
          <div className="space-y-6">
            <VideoStatus 
              videoId={videoId} 
              onStatusChange={handleStatusChange}
            />
            <ChatInterface 
              videoId={videoId}
              currentPlan={currentPlan}
              onPlanUpdate={handlePlanUpdate}
            />
            <div className="text-center">
              <button
                onClick={startVideoGeneration}
                className="bg-gradient-to-r from-green-500 to-blue-600 text-white px-8 py-4 rounded-lg font-semibold text-lg hover:from-green-600 hover:to-blue-700 transform hover:scale-105 transition-all duration-200"
              >
                Generate Video
              </button>
            </div>
          </div>
        )}

        {/* Reset button */}
        {currentStep !== 'upload' && (
          <div className="text-center mt-8">
            <button
              onClick={resetApp}
              className="text-gray-300 hover:text-gray-100 underline"
            >
              Start Over
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

const App = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mb-4"></div>
          <p className="text-white">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <AuthProvider>
      <AuthenticatedApp />
    </AuthProvider>
  );
};

const AuthenticatedApp = () => {
  const { user } = useAuth();

  if (!user) {
    return <AuthComponent />;
  }

  return <MainApp />;
};

export default App;