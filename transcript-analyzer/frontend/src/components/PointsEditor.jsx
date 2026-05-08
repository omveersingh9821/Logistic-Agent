import React from "react";

const DEFAULT_POINTS = [
  "Agent greeted the customer professionally",
  "Customer's issue was clearly understood",
  "Agent offered a resolution or next steps",
  "Agent confirmed the customer's details",
  "Call ended with customer satisfaction confirmed",
];

export default function PointsEditor({ points, setPoints }) {
  function addPoint() {
    setPoints([...points, ""]);
  }

  function updatePoint(i, value) {
    const updated = [...points];
    updated[i] = value;
    setPoints(updated);
  }

  function removePoint(i) {
    setPoints(points.filter((_, idx) => idx !== i));
  }

  function loadDefaults() {
    setPoints([...DEFAULT_POINTS]);
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">Validation Points</h2>
        <button
          onClick={loadDefaults}
          className="text-sm text-indigo-600 hover:text-indigo-800 font-medium transition-colors"
        >
          Load defaults
        </button>
      </div>

      <div className="space-y-2">
        {points.map((point, i) => (
          <div key={i} className="flex gap-2 items-center">
            <span className="text-gray-400 text-sm w-6 text-right shrink-0">{i + 1}.</span>
            <input
              type="text"
              value={point}
              onChange={(e) => updatePoint(i, e.target.value)}
              placeholder="Enter a point to validate..."
              className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-transparent"
            />
            <button
              onClick={() => removePoint(i)}
              className="text-gray-300 hover:text-red-400 transition-colors text-lg leading-none"
              title="Remove"
            >
              ×
            </button>
          </div>
        ))}
      </div>

      <button
        onClick={addPoint}
        className="mt-3 flex items-center gap-1 text-sm text-indigo-600 hover:text-indigo-800 font-medium transition-colors"
      >
        <span className="text-lg leading-none">+</span> Add point
      </button>

      {points.length === 0 && (
        <p className="text-sm text-gray-400 mt-2 italic">No points added yet. Click "Load defaults" or add your own.</p>
      )}
    </div>
  );
}
