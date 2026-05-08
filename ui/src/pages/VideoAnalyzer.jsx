import { useState } from "react";
import {
  PackageCheck,
  PackageX,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  Film,
  Hash,
  Loader2,
  AlertCircle,
  ShieldCheck,
  ShieldAlert,
  Info,
  Zap,
} from "lucide-react";

const API = import.meta.env.VITE_API_URL || "";

// ─── helpers ──────────────────────────────────────────────

function DecisionBadge({ decision }) {
  const map = {
    approve: {
      bg: "bg-emerald-50 border-emerald-200",
      text: "text-emerald-700",
      icon: <CheckCircle2 size={18} className="text-emerald-500" />,
      label: "Approved",
    },
    reject: {
      bg: "bg-red-50 border-red-200",
      text: "text-red-700",
      icon: <XCircle size={18} className="text-red-500" />,
      label: "Rejected",
    },
    manual_review: {
      bg: "bg-amber-50 border-amber-200",
      text: "text-amber-700",
      icon: <Clock size={18} className="text-amber-500" />,
      label: "Manual Review",
    },
    error: {
      bg: "bg-slate-50 border-slate-200",
      text: "text-slate-600",
      icon: <AlertCircle size={18} className="text-slate-400" />,
      label: "Error",
    },
  };
  const c = map[decision] ?? map.error;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm font-semibold ${c.bg} ${c.text}`}
    >
      {c.icon}
      {c.label}
    </span>
  );
}

function ConfidenceRing({ score }) {
  const pct = Math.round(score * 100);
  const r = 28;
  const circumference = 2 * Math.PI * r;
  const dash = (pct / 100) * circumference;
  const color =
    pct >= 80 ? "#10b981" : pct >= 55 ? "#f59e0b" : "#ef4444";

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-[72px] h-[72px]">
        <svg width="72" height="72" className="-rotate-90 absolute inset-0">
          <circle cx="36" cy="36" r={r} fill="none" stroke="#e2e8f0" strokeWidth="6" />
          <circle
            cx="36" cy="36" r={r}
            fill="none" stroke={color} strokeWidth="6"
            strokeDasharray={`${dash} ${circumference - dash}`}
            strokeLinecap="round"
            style={{ transition: "stroke-dasharray 0.6s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-lg font-bold text-slate-800 leading-none">{pct}%</span>
        </div>
      </div>
      <span className="text-[10px] text-slate-400 font-medium">confidence</span>
    </div>
  );
}

function EvidenceCard({ title, evidence }) {
  const statusColor = {
    shared: "text-emerald-600 bg-emerald-50 border-emerald-200",
    not_shared: "text-slate-500 bg-slate-50 border-slate-200",
    partial: "text-amber-600 bg-amber-50 border-amber-200",
    invalid: "text-red-600 bg-red-50 border-red-200",
  };
  const s = evidence.status ?? "not_shared";
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
          {title}
        </span>
        <span
          className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${statusColor[s] ?? statusColor.not_shared}`}
        >
          {s.replace("_", " ")}
        </span>
      </div>
      <div className="space-y-1.5 text-[13px] text-slate-600">
        <div className="flex justify-between">
          <span>Total frames</span>
          <span className="font-medium text-slate-800">{evidence.total_frames ?? 0}</span>
        </div>
        <div className="flex justify-between">
          <span>Usable frames</span>
          <span className="font-medium text-slate-800">{evidence.usable_frames ?? 0}</span>
        </div>
        {evidence.detected_awbs?.length > 0 && (
          <div className="pt-1">
            <p className="text-[11px] text-slate-400 font-medium mb-1">AWBs detected</p>
            <div className="flex flex-wrap gap-1">
              {evidence.detected_awbs.map((a) => (
                <code key={a} className="text-[11px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-700 font-mono">
                  {a}
                </code>
              ))}
            </div>
          </div>
        )}
        {evidence.quality_issues?.length > 0 && (
          <div className="pt-1">
            <p className="text-[11px] text-slate-400 font-medium mb-1">Quality issues</p>
            {evidence.quality_issues.slice(0, 3).map((q, i) => (
              <p key={i} className="text-[11px] text-slate-500 truncate">{q}</p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function FlagChip({ flag }) {
  const isNegative =
    flag.includes("NO_") ||
    flag.includes("MISMATCH") ||
    flag.includes("TAMPER") ||
    flag.includes("PRE_OPENED");
  const isPositive = flag.includes("INTACT");
  const isWarning = flag.includes("LOW_") || flag.includes("COMPLETENESS");

  const style = isNegative
    ? "bg-red-50 text-red-700 border-red-200"
    : isPositive
    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : isWarning
    ? "bg-amber-50 text-amber-700 border-amber-200"
    : "bg-slate-100 text-slate-600 border-slate-200";

  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-lg border text-[11px] font-semibold tracking-wide ${style}`}>
      {flag}
    </span>
  );
}

function ConclusionBox({ result }) {
  const decision = result.final_decision;
  const pct = Math.round((result.confidence_score ?? 0) * 100);

  const style = {
    approve:       { border: "border-emerald-200", bg: "bg-emerald-50",  icon: "✅", label: "Claim Approved",      text: "text-emerald-800" },
    reject:        { border: "border-red-200",     bg: "bg-red-50",      icon: "❌", label: "Claim Rejected",      text: "text-red-800"     },
    manual_review: { border: "border-amber-200",   bg: "bg-amber-50",    icon: "🔍", label: "Manual Review Needed", text: "text-amber-800"   },
  }[decision] ?? { border: "border-slate-200",   bg: "bg-slate-50",    icon: "ℹ️", label: "Result",              text: "text-slate-800"   };

  const text = result.conclusion || result.reasoning || "No additional details available from the analysis.";

  return (
    <div className={`border ${style.border} ${style.bg} rounded-xl p-5`}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-base">{style.icon}</span>
        <p className={`text-sm font-semibold ${style.text}`}>{style.label}</p>
        <span className="ml-auto text-xs text-slate-400 font-medium">{pct}% confidence</span>
      </div>
      <p className={`text-sm leading-relaxed ${style.text} opacity-90`}>
        {text}
      </p>
    </div>
  );
}

function FrameDescriptions({ frames }) {
  const [open, setOpen] = useState(false);
  if (!frames?.length) return null;
  const packing = frames.filter((f) => f.source === "packing");
  const unboxing = frames.filter((f) => f.source === "unboxing");

  const Row = ({ f, color }) => (
    <div className="flex gap-2.5 text-sm">
      <span className={`font-mono text-[11px] ${color} px-1.5 py-0.5 rounded shrink-0 self-start mt-0.5 whitespace-nowrap`}>
        @ {typeof f.timestamp_sec === "number" ? f.timestamp_sec.toFixed(1) : "?"}s
      </span>
      <span className="text-slate-600 leading-relaxed">{f.description}</span>
    </div>
  );

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-sm font-medium text-slate-600"
      >
        <span className="flex items-center gap-2">
          <Film size={14} className="text-violet-400" />
          Frame-by-Frame Analysis
          <span className="text-[11px] text-slate-400 font-normal">({frames.length} frames)</span>
        </span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open && (
        <div className="p-4 space-y-4 bg-white">
          {packing.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">Packing Frames</p>
              <div className="space-y-1.5">
                {packing.map((f, i) => (
                  <Row key={i} f={f} color="text-violet-600 bg-violet-50" />
                ))}
              </div>
            </div>
          )}
          {unboxing.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">Unboxing Frames</p>
              <div className="space-y-1.5">
                {unboxing.map((f, i) => (
                  <Row key={i} f={f} color="text-amber-600 bg-amber-50" />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TokenUsage({ usage }) {
  if (!usage || !usage.total_tokens) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
        <Zap size={11} className="text-violet-400" />
        Token Usage
      </p>
      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="bg-slate-50 rounded-lg py-2.5">
          <p className="text-lg font-bold text-slate-800">{usage.input_tokens?.toLocaleString()}</p>
          <p className="text-[10px] text-slate-400 font-medium mt-0.5">Input</p>
        </div>
        <div className="bg-slate-50 rounded-lg py-2.5">
          <p className="text-lg font-bold text-slate-800">{usage.output_tokens?.toLocaleString()}</p>
          <p className="text-[10px] text-slate-400 font-medium mt-0.5">Output</p>
        </div>
        <div className="bg-violet-50 rounded-lg py-2.5 border border-violet-100">
          <p className="text-lg font-bold text-violet-700">{usage.total_tokens?.toLocaleString()}</p>
          <p className="text-[10px] text-violet-400 font-medium mt-0.5">Total</p>
        </div>
      </div>
    </div>
  );
}

function RawJSON({ data }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-sm font-medium text-slate-600"
      >
        <span className="flex items-center gap-2">
          <Info size={14} className="text-slate-400" />
          Raw JSON response
        </span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open && (
        <pre className="p-4 text-[11px] font-mono text-slate-900 bg-slate-50 overflow-x-auto leading-relaxed max-h-96 overflow-y-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ─── main page ────────────────────────────────────────────

export default function VideoAnalyzer() {
  const [form, setForm] = useState({
    case_name: "",
    claim_type: "",
    packing_video: "",
    unboxing_video: "",
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  function handleChange(e) {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const res = await fetch(`${API}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_name: form.case_name,
          claim_type: form.claim_type,
          packing_video: form.packing_video || null,
          unboxing_video: form.unboxing_video || null,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail ?? `Server error ${res.status}`);
      }

      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const completeness = result ? Math.round(result.evidence_completeness * 100) : 0;

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 animate-fade-in">
      {/* Page header */}
      <div className="mb-8">
        <div className="flex items-center gap-2.5 mb-1.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-purple-700 flex items-center justify-center">
            <Film size={14} className="text-white" strokeWidth={2.5} />
          </div>
          <h1 className="text-xl font-semibold text-slate-800">Video Analyzer</h1>
        </div>
        <p className="text-sm text-slate-500 ml-9">
          Analyze packing &amp; unboxing videos to evaluate logistics claims.
        </p>
      </div>

      {/* Form card */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6 mb-6">
        <h2 className="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
          <Hash size={14} className="text-slate-400" />
          Claim Information
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Case ID */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1.5">
              Case Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              name="case_name"
              value={form.case_name}
              onChange={handleChange}
              required
              placeholder="e.g. Tampered/Wrong/Missing RTO received"
              className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-slate-50
                focus:outline-none focus:ring-2 focus:ring-violet-500/30 focus:border-violet-400
                placeholder:text-slate-300 transition-all"
            />
          </div>

          {/* Claim Type */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1.5">
              Claim Type
            </label>
            <input
              type="text"
              name="claim_type"
              value={form.claim_type}
              onChange={handleChange}
              placeholder="e.g. damaged, missing item, wrong item"
              className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-slate-50
                focus:outline-none focus:ring-2 focus:ring-violet-500/30 focus:border-violet-400
                placeholder:text-slate-300 transition-all"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Packing video */}
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1.5">
                Packing Video URL <span className="text-red-400">*</span>
              </label>
              <input
                type="url"
                name="packing_video"
                value={form.packing_video}
                onChange={handleChange}
                required
                placeholder="https://..."
                className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-slate-50
                  focus:outline-none focus:ring-2 focus:ring-violet-500/30 focus:border-violet-400
                  placeholder:text-slate-300 transition-all"
              />
            </div>

            {/* Unboxing video */}
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1.5">
                Unboxing Video URL <span className="text-red-400">*</span>
              </label>
              <input
                type="url"
                name="unboxing_video"
                value={form.unboxing_video}
                onChange={handleChange}
                required
                placeholder="https://..."
                className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-slate-50
                  focus:outline-none focus:ring-2 focus:ring-violet-500/30 focus:border-violet-400
                  placeholder:text-slate-300 transition-all"
              />
            </div>
          </div>

          <div className="pt-1">
            <button
              type="submit"
              disabled={loading || !form.case_name.trim() || !form.packing_video.trim() || !form.unboxing_video.trim()}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-violet-600 hover:bg-violet-700
                disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed
                text-white text-sm font-semibold rounded-xl transition-all shadow-sm
                shadow-violet-500/30 hover:shadow-violet-500/40"
            >
              {loading ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Analyzing…
                </>
              ) : (
                <>
                  <ShieldCheck size={15} />
                  Analyze Claim
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Error state */}
      {error && (
        <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3.5 mb-6 animate-fade-in">
          <ShieldAlert size={16} className="text-red-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-red-700">Analysis failed</p>
            <p className="text-xs text-red-600 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="space-y-4 animate-fade-in">
          {/* Decision header */}
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <p className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">
                  Final Decision
                </p>
                <DecisionBadge decision={result.final_decision} />
                {result.reasoning && (
                  <p className="mt-3 text-sm text-slate-600 leading-relaxed max-w-md">
                    {result.reasoning}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-5 flex-shrink-0">
                <ConfidenceRing score={result.confidence_score ?? 0} />

                <div className="text-center">
                  <p className="text-[10px] text-slate-400 font-medium uppercase tracking-wider mb-1">
                    Evidence
                  </p>
                  <p className="text-2xl font-bold text-slate-800">{completeness}%</p>
                  <p className="text-[10px] text-slate-400">complete</p>
                  <div className="w-16 h-1.5 bg-slate-100 rounded-full mt-1.5">
                    <div
                      className={`h-1.5 rounded-full transition-all duration-500 ${
                        completeness >= 70
                          ? "bg-emerald-400"
                          : completeness >= 40
                          ? "bg-amber-400"
                          : "bg-red-400"
                      }`}
                      style={{ width: `${completeness}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Analysis details */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                Product Match
              </p>
              <p className="text-sm font-semibold text-slate-700 capitalize">
                {result.product_match?.replace(/_/g, " ")}
              </p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                Packaging Integrity
              </p>
              <p className="text-sm font-semibold text-slate-700 capitalize">
                {result.packaging_integrity?.replace(/_/g, " ")}
              </p>
            </div>
          </div>

          {/* AWB chain of custody */}
          {(result.awb_packing || result.awb_unboxing) && (
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">AWB Chain of Custody</p>
              <div className="grid grid-cols-3 gap-3 text-[13px]">
                <div>
                  <p className="text-[10px] text-slate-400 mb-0.5">Packing AWB</p>
                  <code className="font-mono text-slate-700 text-xs">{result.awb_packing || "—"}</code>
                </div>
                <div>
                  <p className="text-[10px] text-slate-400 mb-0.5">Unboxing AWB</p>
                  <code className="font-mono text-slate-700 text-xs">{result.awb_unboxing || "—"}</code>
                </div>
                <div>
                  <p className="text-[10px] text-slate-400 mb-0.5">AWB Match</p>
                  <span className={`text-xs font-semibold ${result.awb_match === "yes" ? "text-emerald-600" : result.awb_match === "no" ? "text-red-600" : "text-amber-600"}`}>
                    {result.awb_match?.replace(/_/g, " ") || "unclear"}
                  </span>
                </div>
              </div>
              {result.recipient_address_match === "no" && (
                <p className="mt-2 text-xs text-red-600 font-medium">Recipient address mismatch between packing and unboxing labels</p>
              )}
            </div>
          )}

          {/* Damage assessment */}
          {(result.item_broken !== "not_assessed" || result.item_missing !== "not_assessed") && (
            <div className={`border rounded-xl p-4 ${result.item_broken === "yes" || result.item_missing === "yes" ? "bg-red-50 border-red-200" : "bg-white border-slate-200"}`}>
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Damage Assessment</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[13px] mb-3">
                {[
                  { label: "Item Broken", val: result.item_broken },
                  { label: "Item Missing", val: result.item_missing },
                  { label: "Loose Items", val: result.loose_items_found },
                  { label: "Accessory Count", val: result.accessory_count_match === "yes" ? "match" : result.accessory_count_match === "no" ? `packed ${result.accessory_count_packing} / received ${result.accessory_count_unboxing}` : "unclear" },
                ].map(({ label, val }) => (
                  <div key={label}>
                    <p className="text-[10px] text-slate-400 mb-0.5">{label}</p>
                    <span className={`text-xs font-semibold ${val === "yes" || val?.startsWith("packed") ? "text-red-600" : val === "no" || val === "match" ? "text-emerald-600" : "text-amber-500"}`}>
                      {val || "unclear"}
                    </span>
                  </div>
                ))}
              </div>
              {result.break_details?.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {result.break_details.map((d, i) => (
                    <span key={i} className="text-[11px] bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-medium">{d}</span>
                  ))}
                </div>
              )}
              {result.outer_packaging_damage?.length > 0 && (
                <div className="mt-2">
                  <p className="text-[10px] text-slate-400 mb-1">Outer Packaging</p>
                  <div className="flex flex-wrap gap-1.5">
                    {result.outer_packaging_damage.map((d, i) => (
                      <span key={i} className="text-[11px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">{d}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Product descriptions */}
          {(result.product_description_packing || result.product_description_unboxing) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {result.product_description_packing && (
                <div className="bg-white border border-slate-200 rounded-xl p-4">
                  <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">What Was Packed</p>
                  <p className="text-sm text-slate-600 leading-relaxed">{result.product_description_packing}</p>
                </div>
              )}
              {result.product_description_unboxing && (
                <div className="bg-white border border-slate-200 rounded-xl p-4">
                  <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">What Was Received</p>
                  <p className="text-sm text-slate-600 leading-relaxed">{result.product_description_unboxing}</p>
                </div>
              )}
            </div>
          )}

          {/* Evidence cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <EvidenceCard title="Packing Video" evidence={result.packing_evidence ?? {}} />
            <EvidenceCard title="Unboxing Video" evidence={result.unboxing_evidence ?? {}} />
          </div>

          {/* Flags */}
          {result.flags?.length > 0 && (
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Flags
              </p>
              <div className="flex flex-wrap gap-2">
                {result.flags.map((f, i) => (
                  <FlagChip key={i} flag={f} />
                ))}
              </div>
            </div>
          )}

          {/* Rejection reasons */}
          {result.rejection_reasons?.length > 0 && (
            <div className="bg-red-50 border border-red-100 rounded-xl p-4">
              <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <AlertTriangle size={12} />
                Rejection Reasons
              </p>
              <ul className="space-y-1.5">
                {result.rejection_reasons.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-red-700">
                    <XCircle size={14} className="text-red-400 mt-0.5 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Processing errors */}
          {result.processing_errors?.length > 0 && (
            <div className="bg-amber-50 border border-amber-100 rounded-xl p-4">
              <p className="text-[10px] font-semibold text-amber-500 uppercase tracking-wider mb-2">
                Processing Notes
              </p>
              {result.processing_errors.map((e, i) => (
                <p key={i} className="text-sm text-amber-700">{e}</p>
              ))}
            </div>
          )}

          {/* Frame descriptions */}
          <FrameDescriptions frames={result.frame_descriptions} />

          {/* Conclusion */}
          <ConclusionBox result={result} />

          {/* Token usage */}
          <TokenUsage usage={result.token_usage} />

          {/* Raw JSON */}
          <RawJSON data={result} />
        </div>
      )}
    </div>
  );
}
