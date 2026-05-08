import React from "react";

export default function TranscriptInput({ transcript, setTranscript }) {
  const wordCount = transcript.trim() ? transcript.trim().split(/\s+/).length : 0;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-gray-800">Transcript</h2>
        <span className="text-xs text-gray-400">{wordCount} words</span>
      </div>
      <textarea
        value={transcript}
        onChange={(e) => setTranscript(e.target.value)}
        placeholder="Paste your transcript here..."
        rows={12}
        className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-transparent resize-y font-mono leading-relaxed"
      />
    </div>
  );
}
