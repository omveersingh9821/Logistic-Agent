import { useState, useEffect } from "react";
import {
  ImageIcon, Loader2, ShieldAlert, ChevronDown, ChevronUp,
  Link2, ArrowRight, SlidersHorizontal, RotateCcw, Zap, Info,
} from "lucide-react";

const API = import.meta.env.VITE_API_URL || "";

function cn(...classes) { return classes.filter(Boolean).join(" "); }

function RawJSON({ data }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-sm font-medium text-slate-600">
        <span className="flex items-center gap-2"><Info size={14} className="text-slate-400" />Raw JSON</span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open && (
        <pre className="p-4 text-[11px] font-mono text-slate-800 bg-slate-50 overflow-x-auto leading-relaxed max-h-96 overflow-y-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function ImageAnalyzer() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [promptOpen, setPromptOpen] = useState(false);
  const [defaultPrompt, setDefaultPrompt] = useState("");
  const [customPrompt, setCustomPrompt] = useState("");

  useEffect(() => {
    fetch(`${API}/api/default-image-prompt`)
      .then(r => r.json())
      .then(d => { setDefaultPrompt(d.prompt); setCustomPrompt(d.prompt); })
      .catch(() => {});
  }, []);

  const isModified = customPrompt.trim() !== defaultPrompt.trim();

  async function handleSubmit(e) {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    setLoading(true); setResult(null); setError(null);
    try {
      const res = await fetch(`${API}/api/analyze-image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmed, custom_prompt: customPrompt }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `Server error ${res.status}`);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">

      {/* Header */}
      <div className="mb-7">
        <div className="flex items-center gap-2.5 mb-1">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center">
            <ImageIcon size={14} className="text-white" strokeWidth={2.5} />
          </div>
          <h1 className="text-xl font-semibold text-slate-800">Image Analyzer</h1>
        </div>
        <p className="text-sm text-slate-500 ml-9">
          Paste any image URL — product photos, package condition, delivery proof. Claude analyzes it visually.
        </p>
      </div>

      {/* URL input */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5 mb-3">
        <form onSubmit={handleSubmit} className="flex gap-3">
          <div className="relative flex-1">
            <Link2 size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-300 pointer-events-none" />
            <input
              type="text"
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://example.com/image.jpg  or any public image URL"
              className="w-full pl-10 pr-4 py-3 text-sm border border-slate-200 rounded-xl bg-slate-50
                focus:outline-none focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-400
                placeholder:text-slate-300 font-mono transition-all"
              required
            />
          </div>
          <button
            type="submit"
            disabled={loading || !url.trim()}
            className="shrink-0 inline-flex items-center gap-2 px-5 py-3 bg-emerald-600 hover:bg-emerald-700
              disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed
              text-white text-sm font-semibold rounded-xl transition-all shadow-sm shadow-emerald-500/30">
            {loading
              ? <><Loader2 size={15} className="animate-spin" />Analyzing…</>
              : <><ArrowRight size={15} />Analyze</>}
          </button>
        </form>
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {["JPG / PNG / WEBP", "S3 / CDN URLs", "Product photos", "Package condition", "Delivery proof"].map(t => (
            <span key={t} className="text-[10px] bg-slate-100 text-slate-400 px-2 py-0.5 rounded font-medium">{t}</span>
          ))}
        </div>
      </div>

      {/* Prompt editor */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm mb-6 overflow-hidden">
        <button
          type="button"
          onClick={() => setPromptOpen(o => !o)}
          className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-slate-50 transition-colors">
          <div className="flex items-center gap-2">
            <SlidersHorizontal size={14} className="text-emerald-400" />
            <span className="text-sm font-medium text-slate-700">Analysis Prompt</span>
            {isModified && (
              <span className="text-[10px] font-semibold bg-emerald-100 text-emerald-600 px-2 py-0.5 rounded-full">
                Custom
              </span>
            )}
          </div>
          {promptOpen ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
        </button>

        {promptOpen && (
          <div className="border-t border-slate-100 p-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[11px] text-slate-400">
                Edit the prompt sent to Claude along with the image.
              </p>
              {isModified && (
                <button
                  type="button"
                  onClick={() => setCustomPrompt(defaultPrompt)}
                  className="flex items-center gap-1 text-[11px] text-emerald-500 hover:text-emerald-700 font-medium">
                  <RotateCcw size={11} /> Reset to default
                </button>
              )}
            </div>
            <textarea
              value={customPrompt}
              onChange={e => setCustomPrompt(e.target.value)}
              rows={10}
              className="w-full text-[12px] font-mono text-slate-700 bg-slate-50 border border-slate-200
                rounded-xl p-3 resize-y focus:outline-none focus:ring-2 focus:ring-emerald-500/30
                focus:border-emerald-400 leading-relaxed transition-all"
              spellCheck={false}
            />
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3.5 mb-5">
          <ShieldAlert size={16} className="text-red-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-red-700">Analysis failed</p>
            <p className="text-xs text-red-600 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="space-y-4">

          {/* Image preview */}
          <div className="border border-slate-200 rounded-xl overflow-hidden bg-white">
            <div className="flex items-center gap-2 px-4 py-3 bg-slate-50 border-b border-slate-100">
              <ImageIcon size={13} className="text-slate-400" />
              <span className="text-sm font-medium text-slate-600">Image</span>
            </div>
            <div className="p-4 flex justify-center bg-slate-50">
              <img
                src={result.image_url}
                alt="Analyzed"
                className="max-h-72 max-w-full rounded-lg object-contain shadow-sm"
                onError={e => { e.target.style.display = "none"; }}
              />
            </div>
          </div>

          {/* Analysis result */}
          <div className="bg-white border border-emerald-200 rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-emerald-50 border-b border-emerald-100 flex items-center gap-2">
              <ImageIcon size={13} className="text-emerald-500" />
              <span className="text-sm font-semibold text-emerald-800">Analysis Result</span>
            </div>
            <div className="p-5">
              <p className="text-[13px] text-slate-700 leading-relaxed whitespace-pre-wrap">{result.result}</p>
            </div>
          </div>

          {/* Token usage */}
          {result.token_usage?.total_tokens > 0 && (
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <Zap size={11} className="text-emerald-400" />Token Usage
              </p>
              <div className="grid grid-cols-3 gap-3 text-center">
                {[
                  { l: "Input",  v: result.token_usage.input_tokens,  cls: "bg-slate-50" },
                  { l: "Output", v: result.token_usage.output_tokens, cls: "bg-slate-50" },
                  { l: "Total",  v: result.token_usage.total_tokens,  cls: "bg-emerald-50 border border-emerald-100" },
                ].map(({ l, v, cls }) => (
                  <div key={l} className={cn("rounded-lg py-2.5", cls)}>
                    <p className="text-lg font-bold text-slate-800">{v?.toLocaleString()}</p>
                    <p className="text-[10px] text-slate-400 font-medium mt-0.5">{l}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <RawJSON data={result} />
        </div>
      )}
    </div>
  );
}
