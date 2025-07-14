import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';

const UserDashboard = ({ onStartNewProject }) => {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  const { user, logout, getAuthHeaders } = useAuth();

  useEffect(() => {
    fetchUserVideos();
  }, []);

  const fetchUserVideos = async () => {
    try {
      const backendUrl = process.env.REACT_APP_BACKEND_URL;
      const response = await fetch(`${backendUrl}/api/videos`, {
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch videos');
      }

      const data = await response.json();
      setVideos(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getStatusColor = (status) => {
    const colors = {
      'uploaded': 'bg-blue-500/20 text-blue-300',
      'analyzing': 'bg-yellow-500/20 text-yellow-300',
      'analyzed': 'bg-green-500/20 text-green-300',
      'planning': 'bg-purple-500/20 text-purple-300',
      'planned': 'bg-indigo-500/20 text-indigo-300',
      'generating': 'bg-orange-500/20 text-orange-300',
      'completed': 'bg-green-500/20 text-green-300',
      'error': 'bg-red-500/20 text-red-300',
      'expired': 'bg-gray-500/20 text-gray-300',
    };
    return colors[status] || 'bg-gray-500/20 text-gray-300';
  };

  const getDaysUntilExpiration = (expiresAt) => {
    const expiry = new Date(expiresAt);
    const now = new Date();
    const diffTime = expiry - now;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mb-4"></div>
          <p className="text-white">Loading your videos...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">
              Welcome back, {user?.name || user?.email}!
            </h1>
            <p className="text-gray-300">
              Manage your video projects and track their progress
            </p>
          </div>
          <div className="flex items-center space-x-4">
            <button
              onClick={onStartNewProject}
              className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white font-semibold py-2 px-6 rounded-xl transition-all duration-200 transform hover:scale-[1.02]"
            >
              New Project
            </button>
            <button
              onClick={logout}
              className="bg-white/10 hover:bg-white/20 text-white font-medium py-2 px-4 rounded-xl transition-all duration-200 border border-white/20"
            >
              Logout
            </button>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-500/20 border border-red-500/30 rounded-xl p-4 mb-6">
            <p className="text-red-200">{error}</p>
          </div>
        )}

        {/* Videos Grid */}
        {videos.length === 0 ? (
          <div className="text-center py-16">
            <div className="bg-black/30 backdrop-blur-xl rounded-3xl p-12 max-w-md mx-auto">
              <div className="text-6xl mb-6">🎬</div>
              <h2 className="text-2xl font-bold text-white mb-4">
                No videos yet
              </h2>
              <p className="text-gray-300 mb-8">
                Start by uploading your first video to begin the AI-powered generation process
              </p>
              <button
                onClick={onStartNewProject}
                className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white font-semibold py-3 px-8 rounded-xl transition-all duration-200 transform hover:scale-[1.02]"
              >
                Upload Your First Video
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {videos.map((video) => (
              <div
                key={video.id}
                className="bg-black/30 backdrop-blur-xl rounded-2xl p-6 border border-white/10 hover:border-white/20 transition-all duration-200"
              >
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white truncate">
                    {video.filename}
                  </h3>
                  <span className={`px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(video.status)}`}>
                    {video.status}
                  </span>
                </div>

                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Created:</span>
                    <span className="text-gray-300">{formatDate(video.created_at)}</span>
                  </div>

                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Expires:</span>
                    <span className={`${getDaysUntilExpiration(video.expires_at) <= 1 ? 'text-red-300' : 'text-gray-300'}`}>
                      {getDaysUntilExpiration(video.expires_at)} days
                    </span>
                  </div>

                  {video.progress > 0 && (
                    <div>
                      <div className="flex justify-between text-sm text-gray-400 mb-1">
                        <span>Progress</span>
                        <span>{video.progress}%</span>
                      </div>
                      <div className="w-full bg-gray-700 rounded-full h-2">
                        <div
                          className="bg-gradient-to-r from-purple-600 to-blue-600 h-2 rounded-full transition-all duration-300"
                          style={{ width: `${video.progress}%` }}
                        ></div>
                      </div>
                    </div>
                  )}

                  {video.error_message && (
                    <div className="bg-red-500/20 border border-red-500/30 rounded-lg p-3">
                      <p className="text-red-200 text-xs">{video.error_message}</p>
                    </div>
                  )}

                  {video.final_video_url && (
                    <button className="w-full bg-gradient-to-r from-green-600 to-blue-600 hover:from-green-700 hover:to-blue-700 text-white font-medium py-2 px-4 rounded-lg transition-all duration-200 text-sm">
                      Download Video
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="mt-16 text-center">
          <p className="text-gray-400 text-sm">
            Videos are automatically deleted after 7 days • Generate unlimited videos
          </p>
        </div>
      </div>
    </div>
  );
};

export default UserDashboard;