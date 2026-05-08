import React from "react";

function Badge({ status }) {
  const isPositive = status === "positive";
  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
        isPositive
          ? "bg-green-100 text-green-700"
          : "bg-red-100 text-red-600"
      }`}
    >
      <span>{isPositive ? "✓" : "✗"}</span>
      {isPositive ? "Positive" : "Negative"}
    </span>
  );
}

export default function ResultsView({ result }) {
  const { results, summary, positive_count, negative_count } = result;
  const total = results.length;
  const score = total > 0 ? Math.round((positive_count / total) * 100) : 0;

  const scoreColor =
    score >= 75 ? "text-green-600" : score >= 50 ? "text-yellow-600" : "text-red-600";
  const scoreBg =
    score >= 75 ? "bg-green-50 border-green-200" : score >= 50 ? "bg-yellow-50 border-yellow-200" : "bg-red-50 border-red-200";

  return (
    <div className="space-y-5">
      {/* Score banner */}
      <div className={`rounded-xl border p-5 ${scoreBg}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-600 mb-0.5">Overall Score</p>
            <p className={`text-4xl font-bold ${scoreColor}`}>{score}%</p>
            <p className="text-sm text-gray-500 mt-1">
              {positive_count} of {total} points validated
            </p>
          </div>
          <div className="text-right space-y-1">
            <div className="flex items-center justify-end gap-2">
              <span className="w-3 h-3 rounded-full bg-green-400 inline-block" />
              <span className="text-sm text-gray-600">{positive_count} passed</span>
            </div>
            <div className="flex items-center justify-end gap-2">
              <span className="w-3 h-3 rounded-full bg-red-400 inline-block" />
              <span className="text-sm text-gray-600">{negative_count} failed</span>
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-4 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              score >= 75 ? "bg-green-500" : score >= 50 ? "bg-yellow-500" : "bg-red-500"
            }`}
            style={{ width: `${score}%` }}
          />
        </div>
      </div>

      {/* Summary */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-800 mb-2">Summary</h3>
        <p className="text-sm text-gray-600 leading-relaxed">{summary}</p>
      </div>

      {/* Point-by-point */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-800 mb-4">Point-by-Point Results</h3>
        <div className="space-y-3">
          {results.map((r, i) => (
            <div
              key={i}
              className={`rounded-lg border p-4 ${
                r.status === "positive"
                  ? "border-green-200 bg-green-50/50"
                  : "border-red-200 bg-red-50/50"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-800">{r.point}</p>
                  {r.evidence && r.evidence !== "Not found" && (
                    <p className="text-xs text-gray-500 mt-1.5 italic">"{r.evidence}"</p>
                  )}
                  {(r.status === "negative" || r.evidence === "Not found") && (
                    <p className="text-xs text-red-400 mt-1.5">Not found in transcript</p>
                  )}
                </div>
                <Badge status={r.status} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
