import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const TERMINAL_STAGES = ['completed', 'failed'];

export default function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState(
    process.env.REACT_APP_API_BASE_URL || 'http://127.0.0.1:8000'
  );
  const [pollSeconds, setPollSeconds] = useState(4);
  const [jobId, setJobId] = useState('');
  const [lastStatus, setLastStatus] = useState(null);
  const [autoPolling, setAutoPolling] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Form fields
  const [formData, setFormData] = useState({
    title: 'The Last Lighthouse',
    story:
      'A keeper receives a message from the sea. He repairs the old light. A storm arrives. The beam guides lost ships home.',
    style: 'cinematic watercolor',
    target_duration_s: 60,
    aspect_ratio: '16:9',
    fps: 24,
    voiceover_enabled: true,
  });

  const pollingRef = useRef(null);

  const clearMessages = () => {
    setError('');
    setSuccess('');
  };

  const fetchStatus = async (id) => {
    try {
      const response = await axios.get(`${apiBaseUrl}/jobs/${id}`);
      setLastStatus(response.data);
      return response.data;
    } catch (err) {
      setError(`Status fetch failed: ${err.message}`);
      return null;
    }
  };

  const submitJob = async () => {
    clearMessages();
    setLoading(true);

    try {
      const response = await axios.post(`${apiBaseUrl}/generate`, formData);
      setJobId(response.data.job_id);
      setAutoPolling(true);
      setSuccess(`Job submitted: ${response.data.job_id}`);
    } catch (err) {
      setError(`Submit failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const resumeJob = async () => {
    if (!jobId) {
      setError('Provide a job ID first.');
      return;
    }

    clearMessages();
    setLoading(true);

    try {
      await axios.post(`${apiBaseUrl}/jobs/${jobId}/resume`);
      setAutoPolling(true);
      setSuccess('Job requeued for resume.');
    } catch (err) {
      setError(`Resume failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const refreshStatus = async () => {
    if (jobId) {
      clearMessages();
      await fetchStatus(jobId);
    }
  };

  // Auto-polling effect
  useEffect(() => {
    if (!autoPolling || !jobId) return;

    const poll = async () => {
      const status = await fetchStatus(jobId);
      if (status) {
        const stage = String(status.stage || '').toLowerCase();
        if (!TERMINAL_STAGES.includes(stage)) {
          // Schedule next poll
          pollingRef.current = setTimeout(() => {
            poll();
          }, pollSeconds * 1000);
        } else {
          // Job is terminal, stop polling
          setAutoPolling(false);
        }
      }
    };

    poll();

    return () => {
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
      }
    };
  }, [autoPolling, jobId, pollSeconds]);

  const handleFormChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : type === 'number' ? Number(value) : value,
    }));
  };

  const progress = lastStatus ? Math.max(0, Math.min(lastStatus.progress || 0, 1)) : 0;
  const stage = lastStatus ? String(lastStatus.stage || '').toLowerCase() : '';
  const videoUrl = lastStatus?.result_url ? `${apiBaseUrl}${lastStatus.result_url}` : null;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <div className="bg-slate-800 border-b border-slate-700 shadow-lg">
        <div className="max-w-6xl mx-auto px-4 py-6">
          <h1 className="text-4xl font-bold text-white flex items-center gap-2">
            <span className="text-3xl">🎬</span> Agentic Video Generator
          </h1>
          <p className="text-slate-400 mt-2">React UI for submit, status polling, preview, and resume</p>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* API Settings Sidebar */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          <div className="lg:col-span-1">
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 shadow-md">
              <h2 className="text-xl font-semibold text-white mb-4">API Settings</h2>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Backend URL</label>
                  <input
                    type="text"
                    value={apiBaseUrl}
                    onChange={(e) => setApiBaseUrl(e.target.value.replace(/\/$/, ''))}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Polling Interval: {pollSeconds}s
                  </label>
                  <input
                    type="range"
                    min="2"
                    max="20"
                    value={pollSeconds}
                    onChange={(e) => setPollSeconds(Number(e.target.value))}
                    className="w-full"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="lg:col-span-3 space-y-8">
            {/* Alert Messages */}
            {error && (
              <div className="bg-red-900/30 border border-red-700 text-red-200 px-4 py-3 rounded-lg flex justify-between items-center">
                <span>{error}</span>
                <button onClick={clearMessages} className="text-red-400 hover:text-red-300">
                  ✕
                </button>
              </div>
            )}

            {success && (
              <div className="bg-green-900/30 border border-green-700 text-green-200 px-4 py-3 rounded-lg flex justify-between items-center">
                <span>{success}</span>
                <button onClick={clearMessages} className="text-green-400 hover:text-green-300">
                  ✕
                </button>
              </div>
            )}

            {/* Submit Form */}
            <div className="bg-slate-800 rounded-lg p-8 border border-slate-700 shadow-md">
              <h2 className="text-2xl font-semibold text-white mb-6">Submit Generation Request</h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Title</label>
                  <input
                    type="text"
                    name="title"
                    value={formData.title}
                    onChange={handleFormChange}
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Story</label>
                  <textarea
                    name="story"
                    value={formData.story}
                    onChange={handleFormChange}
                    rows="4"
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">Style</label>
                    <input
                      type="text"
                      name="style"
                      value={formData.style}
                      onChange={handleFormChange}
                      className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">Duration (seconds)</label>
                    <input
                      type="number"
                      name="target_duration_s"
                      min="15"
                      max="600"
                      value={formData.target_duration_s}
                      onChange={handleFormChange}
                      className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">Aspect Ratio</label>
                    <select
                      name="aspect_ratio"
                      value={formData.aspect_ratio}
                      onChange={handleFormChange}
                      className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                    >
                      <option value="16:9">16:9</option>
                      <option value="9:16">9:16</option>
                      <option value="1:1">1:1</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">FPS</label>
                    <input
                      type="number"
                      name="fps"
                      min="12"
                      max="60"
                      value={formData.fps}
                      onChange={handleFormChange}
                      className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                <div className="flex items-center">
                  <input
                    type="checkbox"
                    id="voiceover"
                    name="voiceover_enabled"
                    checked={formData.voiceover_enabled}
                    onChange={handleFormChange}
                    className="w-4 h-4 text-blue-600 rounded"
                  />
                  <label htmlFor="voiceover" className="ml-2 text-sm font-medium text-slate-300">
                    Enable voiceover
                  </label>
                </div>

                <button
                  onClick={submitJob}
                  disabled={loading}
                  className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 text-white font-semibold py-3 rounded-lg transition"
                >
                  {loading ? 'Submitting...' : 'Generate Video'}
                </button>
              </div>
            </div>

            {/* Job Status Section */}
            <div className="bg-slate-800 rounded-lg p-8 border border-slate-700 shadow-md">
              <h2 className="text-2xl font-semibold text-white mb-6">Job Status</h2>

              <div className="mb-6">
                <label className="block text-sm font-medium text-slate-300 mb-2">Job ID</label>
                <input
                  type="text"
                  value={jobId}
                  onChange={(e) => setJobId(e.target.value.trim())}
                  placeholder="Paste job ID here"
                  className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Control Buttons */}
              <div className="grid grid-cols-3 gap-4 mb-6">
                <button
                  onClick={refreshStatus}
                  disabled={loading || !jobId}
                  className="bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 text-white font-semibold py-2 rounded-lg transition"
                >
                  Refresh
                </button>

                <button
                  onClick={resumeJob}
                  disabled={loading || !jobId}
                  className="bg-amber-600 hover:bg-amber-700 disabled:bg-slate-800 text-white font-semibold py-2 rounded-lg transition"
                >
                  Resume
                </button>

                <div className="flex items-center justify-center bg-slate-700 rounded-lg px-4">
                  <input
                    type="checkbox"
                    id="autoPolling"
                    checked={autoPolling}
                    onChange={(e) => setAutoPolling(e.target.checked)}
                    className="w-4 h-4 text-blue-600 rounded"
                  />
                  <label htmlFor="autoPolling" className="ml-2 text-sm font-medium text-slate-300">
                    Auto-poll
                  </label>
                </div>
              </div>

              {/* Status JSON */}
              {lastStatus && (
                <div className="space-y-4">
                  <div className="bg-slate-900 rounded p-4 border border-slate-600">
                    <pre className="text-slate-300 text-sm overflow-auto max-h-48">
                      {JSON.stringify(lastStatus, null, 2)}
                    </pre>
                  </div>

                  {/* Progress Bar */}
                  <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-gradient-to-r from-blue-600 to-cyan-500 h-full transition-all duration-300"
                      style={{ width: `${progress * 100}%` }}
                    />
                  </div>
                  <p className="text-sm text-slate-400 text-center">{Math.round(progress * 100)}%</p>

                  {/* Video Output */}
                  {stage === 'completed' && videoUrl && (
                    <div className="space-y-4">
                      <div className="bg-green-900/30 border border-green-700 text-green-200 px-4 py-3 rounded-lg">
                        ✓ Video is ready
                      </div>
                      <div className="rounded-lg overflow-hidden">
                        <video
                          controls
                          className="w-full bg-black"
                          src={videoUrl}
                        />
                      </div>
                      <a
                        href={videoUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-block text-blue-400 hover:text-blue-300 underline text-sm"
                      >
                        Open output: {videoUrl}
                      </a>
                    </div>
                  )}

                  {/* Error State */}
                  {stage === 'failed' && (
                    <div className="bg-red-900/30 border border-red-700 text-red-200 px-4 py-3 rounded-lg">
                      ✕ Job failed: {lastStatus.error || 'Unknown error'}
                    </div>
                  )}

                  {/* Processing State */}
                  {!TERMINAL_STAGES.includes(stage) && (
                    <div className="bg-blue-900/30 border border-blue-700 text-blue-200 px-4 py-3 rounded-lg">
                      ⟳ Processing: {stage || 'Queued'}
                    </div>
                  )}
                </div>
              )}

              {!lastStatus && jobId && (
                <p className="text-slate-400 text-center py-8">Click "Refresh" to fetch status</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
