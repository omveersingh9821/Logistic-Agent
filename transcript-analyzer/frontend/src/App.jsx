import React, { useState } from "react";
import TranscriptInput from "./components/TranscriptInput";
import PointsEditor from "./components/PointsEditor";
import ResultsView from "./components/ResultsView";

export default function App() {
  const [transcript, setTranscript] = useState("");
  const [points, setPoints] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleAnalyze() {
    setError("");
    setResult(null);
    if (!transcript.trim()) { setError("Please paste a transcript."); return; }
    if (!points.some((p) => p.trim())) { setError("Please add at least one validation point."); return; }

    setLoading(true);
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript, points }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Analysis failed");
      }
      const data = await res.json();
      setResult(data);
      // Scroll to results
      setTimeout(() => document.getElementById("results")?.scrollIntoView({ behavior: "smooth" }), 100);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setResult(null);
    setError("");
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Transcript Analyzer</h1>
            <p className="text-xs text-gray-400 mt-0.5">Powered by Claude</p>
          </div>
          {result && (
            <button
              onClick={handleReset}
              className="text-sm text-gray-500 hover:text-gray-700 font-medium transition-colors"
            >
              ← New Analysis
            </button>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {!result ? (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <TranscriptInput transcript={transcript} setTranscript={setTranscript} />
              <PointsEditor points={points} setPoints={setPoints} />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-600 text-sm px-4 py-3 rounded-lg">
                {error}
              </div>
            )}

            <div className="flex justify-center">
              <button
                onClick={handleAnalyze}
                disabled={loading}
                className="px-8 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white font-semibold rounded-xl shadow-sm transition-colors flex items-center gap-2"
              >
                {loading ? (
                  <>
                    <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                    </svg>
                    Analyzing...
                  </>
                ) : (
                  "Analyze Transcript"
                )}
              </button>
            </div>
          </div>
        ) : (
          <div id="results">
            <ResultsView result={result} />
          </div>
        )}
      </main>
    </div>
  );
}
