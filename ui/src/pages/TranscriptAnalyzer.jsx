import { useState } from "react";
import {
  MessageSquare, Loader2, ShieldAlert, ChevronDown, ChevronUp,
  Info, AlertTriangle, CheckCircle2, XCircle, Phone, Package,
  Zap, Link2, AlertCircle, User, Truck, PhoneOff,
  ArrowRight, Flag, Clock, Mic,
} from "lucide-react";

const API = import.meta.env.VITE_API_URL || "";

// ─── tiny helpers ──────────────────────────────────────────────────────────────

function cn(...classes) { return classes.filter(Boolean).join(" "); }

function Chip({ label, variant = "slate" }) {
  const v = {
    green:  "bg-emerald-50 text-emerald-700 border-emerald-200",
    red:    "bg-red-50 text-red-700 border-red-200",
    amber:  "bg-amber-50 text-amber-700 border-amber-200",
    violet: "bg-violet-50 text-violet-700 border-violet-200",
    slate:  "bg-slate-100 text-slate-600 border-slate-200",
  };
  return (
    <span className={cn("inline-flex items-center px-2.5 py-0.5 rounded-full border text-[11px] font-semibold tracking-wide", v[variant] ?? v.slate)}>
      {label}
    </span>
  );
}

function TriBool({ value, yesLabel = "Yes", noLabel = "No", invert = false }) {
  if (value === null || value === undefined)
    return <span className="text-[13px] font-medium text-amber-500">unclear</span>;
  const isPositive = invert ? !value : value;
  return (
    <span className={cn("text-[13px] font-semibold flex items-center gap-1",
      isPositive ? "text-emerald-600" : "text-red-600")}>
      {isPositive
        ? <><CheckCircle2 size={13}/> {yesLabel}</>
        : <><XCircle size={13}/> {noLabel}</>}
    </span>
  );
}

function Row({ label, children }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-slate-100 last:border-0">
      <span className="text-[13px] text-slate-500">{label}</span>
      <div className="text-right">{children}</div>
    </div>
  );
}

function Card({ title, icon: Icon, iconColor = "text-violet-400", accent, children }) {
  const base = accent === "red"   ? "border-red-200 bg-red-50"
             : accent === "amber" ? "border-amber-200 bg-amber-50"
             : accent === "green" ? "border-emerald-200 bg-emerald-50"
             : "border-slate-200 bg-white";
  return (
    <div className={cn("border rounded-xl p-4", base)}>
      {title && (
        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
          {Icon && <Icon size={11} className={iconColor} />}
          {title}
        </p>
      )}
      {children}
    </div>
  );
}

function Quote({ label, text }) {
  if (!text) return null;
  return (
    <div className="mt-2.5">
      <p className="text-[10px] text-slate-400 font-medium mb-1 uppercase tracking-wider">{label}</p>
      <blockquote className="border-l-2 border-violet-300 pl-3 text-[12px] text-slate-600 italic leading-relaxed bg-violet-50/40 py-1 rounded-r">
        "{text}"
      </blockquote>
    </div>
  );
}

function TranscriptBlock({ cleaned, raw }) {
  const [tab, setTab] = useState("cleaned");
  const [open, setOpen] = useState(true);
  const hasContent = cleaned || raw;
  if (!hasContent) return null;

  const display = tab === "cleaned" ? (cleaned || raw) : raw;

  return (
    <div className="border border-violet-200 rounded-xl overflow-hidden">
      {/* header */}
      <div className="flex items-center justify-between px-4 py-3 bg-violet-50">
        <div className="flex items-center gap-2">
          <Mic size={14} className="text-violet-500"/>
          <span className="text-sm font-semibold text-violet-800">Transcript</span>
          {/* tabs */}
          {cleaned && raw && cleaned !== raw && (
            <div className="flex items-center gap-1 ml-2 bg-white border border-violet-200 rounded-lg p-0.5">
              {[["cleaned","Cleaned + Translated"],["raw","Raw Whisper"]].map(([key, label]) => (
                <button key={key} onClick={() => setTab(key)}
                  className={`px-2.5 py-0.5 rounded text-[11px] font-semibold transition-colors ${
                    tab === key ? "bg-violet-600 text-white" : "text-slate-500 hover:text-slate-700"
                  }`}>
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
        <button onClick={() => setOpen(o => !o)} className="text-violet-400 hover:text-violet-600">
          {open ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
        </button>
      </div>
      {/* body */}
      {open && (
        <div className="p-4 bg-white max-h-80 overflow-y-auto">
          <p className="text-[13px] text-slate-700 leading-relaxed whitespace-pre-wrap font-sans">{display}</p>
        </div>
      )}
    </div>
  );
}

function RawJSON({ data }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-sm font-medium text-slate-600">
        <span className="flex items-center gap-2"><Info size={14} className="text-slate-400"/>Raw JSON</span>
        {open ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
      </button>
      {open && (
        <pre className="p-4 text-[11px] font-mono text-slate-800 bg-slate-50 overflow-x-auto leading-relaxed max-h-96 overflow-y-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ─── verdict banner ───────────────────────────────────────────────────────────

function Verdict({ r }) {
  let border, bg, icon, title, sub;

  if (r.fake_ndr_suspected || r.no_call_no_attempt) {
    border = "border-red-300"; bg = "bg-red-50";
    icon = <ShieldAlert size={22} className="text-red-500"/>;
    title = "Fake NDR Suspected";
    sub = "Delivery agent appears to have marked NDR without a genuine attempt or call.";
  } else if (r.ndr_correctly_marked === false) {
    border = "border-amber-300"; bg = "bg-amber-50";
    icon = <AlertTriangle size={22} className="text-amber-500"/>;
    title = "NDR Incorrectly Marked";
    sub = r.ndr_mark_mismatch_reason || "The NDR reason does not match what the customer describes.";
  } else if (r.customer_wants_order === true && r.ndr_correctly_marked !== true) {
    border = "border-violet-300"; bg = "bg-violet-50";
    icon = <Package size={22} className="text-violet-500"/>;
    title = "Customer Wants Order — Re-attempt Needed";
    sub = "Customer has confirmed they want the order. A re-delivery should be scheduled.";
  } else if (r.customer_wants_order === false) {
    border = "border-emerald-300"; bg = "bg-emerald-50";
    icon = <CheckCircle2 size={22} className="text-emerald-500"/>;
    title = "NDR Valid — Customer Refused";
    sub = "Customer confirmed they do not want the order. NDR is correctly marked.";
  } else if (r.ndr_correctly_marked === true) {
    border = "border-emerald-300"; bg = "bg-emerald-50";
    icon = <CheckCircle2 size={22} className="text-emerald-500"/>;
    title = "NDR Correctly Marked";
    sub = "The NDR reason aligns with the customer's account of events.";
  } else {
    border = "border-slate-300"; bg = "bg-slate-50";
    icon = <AlertCircle size={22} className="text-slate-400"/>;
    title = "Manual Review Required";
    sub = "Unable to determine a clear verdict from the transcript.";
  }

  return (
    <div className={cn("border-2 rounded-2xl p-5", border, bg)}>
      <div className="flex items-start gap-4">
        <div className="mt-0.5 shrink-0">{icon}</div>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-slate-800 text-base">{title}</p>
          <p className="text-sm text-slate-600 mt-0.5 leading-relaxed">{sub}</p>
          {r.summary && (
            <p className="text-sm text-slate-600 leading-relaxed mt-3 pt-3 border-t border-black/5">
              {r.summary}
            </p>
          )}
        </div>
        <div className="shrink-0 text-center pl-2">
          <p className="text-2xl font-bold text-slate-800">{Math.round((r.confidence_score ?? 0) * 100)}%</p>
          <p className="text-[10px] text-slate-400 font-medium">confidence</p>
        </div>
      </div>
    </div>
  );
}

// ─── 4-point breakdown ────────────────────────────────────────────────────────

function PointsGrid({ r }) {
  const initiatorLabel = {
    customer: "Customer (Inbound)",
    seller: "Seller (Outbound)",
    logistics_agent: "Logistics Agent (Outbound)",
    unknown: "Unknown",
  }[r.call_initiator] ?? r.call_initiator;

  const initiatorColor = r.call_initiator === "customer" ? "violet"
    : r.call_initiator === "seller" ? "amber"
    : r.call_initiator === "logistics_agent" ? "amber"
    : "slate";

  const actionColor = ["ESCALATE","INVESTIGATE_AGENT","MARK_RTO"].includes(r.recommended_action) ? "red"
    : ["REATTEMPT_DELIVERY","SCHEDULE_DELIVERY","STOP_RTO_REATTEMPT","CLARIFY_AND_REATTEMPT"].includes(r.recommended_action) ? "green"
    : r.recommended_action === "PROCESS_REFUND" ? "amber"
    : "slate";

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">

      {/* Point 1 — Who initiated */}
      <Card title="① Who Initiated" icon={User} iconColor="text-violet-400">
        <div className="space-y-0.5">
          <Row label="Initiated by">
            <Chip label={initiatorLabel} variant={initiatorColor}/>
          </Row>
          <Row label="Direction">
            <span className="text-[13px] font-semibold text-slate-700 capitalize">{r.call_direction}</span>
          </Row>
        </div>
      </Card>

      {/* Point 2 — Delivery & Calls */}
      <Card title="② Delivery & Calls" icon={Phone} iconColor="text-violet-400">
        <div className="space-y-0.5">
          <Row label="Customer wants order">
            <TriBool value={r.customer_wants_order} yesLabel="Yes — wants it" noLabel="No — refused"/>
          </Row>
          <Row label="Delivery attempted">
            <TriBool value={r.delivery_attempted} yesLabel="Yes" noLabel="NOT attempted"/>
          </Row>
          <Row label="Agent called customer">
            <TriBool value={r.delivery_agent_called_customer} yesLabel="Yes" noLabel="Never called"/>
          </Row>
          <Row label="Customer received calls">
            <TriBool value={r.customer_received_calls} yesLabel="Yes" noLabel="No calls received"/>
          </Row>
          {r.call_count_by_agent && (
            <Row label="Agent call attempts">
              <span className="text-[13px] font-semibold text-slate-700">{r.call_count_by_agent}</span>
            </Row>
          )}
        </div>
        {r.no_call_no_attempt && (
          <div className="mt-3 flex items-center gap-2 bg-red-100 border border-red-200 rounded-lg px-3 py-2">
            <PhoneOff size={13} className="text-red-500 shrink-0"/>
            <span className="text-[12px] font-semibold text-red-700">No call + No attempt — Fake NDR</span>
          </div>
        )}
      </Card>

      {/* Point 3 — NDR Mark */}
      <Card title="③ NDR Mark Validation" icon={Flag} iconColor="text-violet-400">
        <div className="space-y-0.5">
          <Row label="NDR reason">
            <Chip
              label={r.ndr_reason?.replace(/_/g, " ") ?? "UNKNOWN"}
              variant={["FAKE_ATTEMPT","WRONG_ADDRESS"].includes(r.ndr_reason) ? "red"
                : r.ndr_reason === "CUSTOMER_REFUSED" ? "amber"
                : ["CUSTOMER_UNAVAILABLE","NO_RESPONSE_CALLS"].includes(r.ndr_reason) ? "slate"
                : "slate"}
            />
          </Row>
          <Row label="NDR correctly marked">
            <TriBool value={r.ndr_correctly_marked} yesLabel="Valid" noLabel="INVALID" invert={false}/>
          </Row>
          <Row label="Fake NDR suspected">
            <TriBool value={r.fake_ndr_suspected} yesLabel="YES — Flag" noLabel="No" invert={true}/>
          </Row>
        </div>
        {r.ndr_mark_mismatch_reason && (
          <p className="mt-2 text-[12px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5 leading-relaxed">
            {r.ndr_mark_mismatch_reason}
          </p>
        )}
      </Card>

      {/* Point 4 — Product */}
      <Card title="④ Product & Order" icon={Package} iconColor="text-amber-400">
        <div className="space-y-0.5">
          {r.product_mentioned ? (
            <Row label="Product">
              <span className="text-[13px] font-semibold text-slate-700">{r.product_mentioned}</span>
            </Row>
          ) : (
            <Row label="Product">
              <span className="text-[12px] text-slate-400">not mentioned</span>
            </Row>
          )}
          {r.order_id_mentioned && (
            <Row label="Order / AWB">
              <code className="text-[11px] font-mono bg-slate-100 px-1.5 py-0.5 rounded text-slate-700">{r.order_id_mentioned}</code>
            </Row>
          )}
          {r.cod_amount_mentioned && (
            <Row label="COD amount">
              <span className="text-[13px] font-semibold text-slate-700">{r.cod_amount_mentioned}</span>
            </Row>
          )}
          {r.product_urgency && (
            <div className="mt-2 flex items-center gap-1.5 text-[12px] text-amber-700 font-medium">
              <Clock size={12} className="text-amber-500"/>
              {r.product_urgency}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

// ─── main page ────────────────────────────────────────────────────────────────

export default function TranscriptAnalyzer() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    setLoading(true); setResult(null); setError(null);
    try {
      const res = await fetch(`${API}/api/analyze-transcript`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmed }),
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

  const r = result;

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">

      {/* Header */}
      <div className="mb-7">
        <div className="flex items-center gap-2.5 mb-1">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-purple-700 flex items-center justify-center">
            <MessageSquare size={14} className="text-white" strokeWidth={2.5}/>
          </div>
          <h1 className="text-xl font-semibold text-slate-800">NDR Transcript Analyzer</h1>
        </div>
        <p className="text-sm text-slate-500 ml-9">
          Paste any URL — MP3 audio, S3, Footwork, or plain text. Audio is transcribed locally via Whisper, then analyzed by Claude.
        </p>
      </div>

      {/* ── Single URL input ── */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5 mb-6">
        <form onSubmit={handleSubmit} className="flex gap-3">
          <div className="relative flex-1">
            <Link2 size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-300 pointer-events-none"/>
            <input
              type="text"
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://s3.amazonaws.com/footwork/…  or any transcript URL"
              className="w-full pl-10 pr-4 py-3 text-sm border border-slate-200 rounded-xl bg-slate-50
                focus:outline-none focus:ring-2 focus:ring-violet-500/30 focus:border-violet-400
                placeholder:text-slate-300 font-mono transition-all"
              required
            />
          </div>
          <button
            type="submit"
            disabled={loading || !url.trim()}
            className="shrink-0 inline-flex items-center gap-2 px-5 py-3 bg-violet-600 hover:bg-violet-700
              disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed
              text-white text-sm font-semibold rounded-xl transition-all shadow-sm shadow-violet-500/30">
            {loading
              ? <><Loader2 size={15} className="animate-spin"/>Analyzing…</>
              : <><ArrowRight size={15}/>Analyze</>}
          </button>
        </form>
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {["MP3 / WAV audio","Footwork S3","AWS presigned",".txt / .json","Hindi","Hinglish","English"].map(t => (
            <span key={t} className="text-[10px] bg-slate-100 text-slate-400 px-2 py-0.5 rounded font-medium">{t}</span>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3.5 mb-5">
          <ShieldAlert size={16} className="text-red-500 mt-0.5 shrink-0"/>
          <div>
            <p className="text-sm font-semibold text-red-700">Analysis failed</p>
            <p className="text-xs text-red-600 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* ── Results ── */}
      {r && !loading && (
        <div className="space-y-4">

          {/* Audio transcribed badge */}
          {r.audio_transcribed && (
            <div className="flex items-center gap-3 bg-violet-50 border border-violet-200 rounded-xl px-4 py-3">
              <Mic size={15} className="text-violet-500 shrink-0"/>
              <div>
                <span className="text-sm text-violet-800 font-semibold">Audio transcribed via OpenAI Whisper API</span>
                <span className="text-sm text-violet-600"> · {r.transcript_length_chars?.toLocaleString()} characters · analyzed by Claude</span>
              </div>
            </div>
          )}

          {/* Transcript — cleaned+translated tab + raw whisper tab */}
          <TranscriptBlock cleaned={r.cleaned_transcript} raw={r.raw_transcript}/>

          {/* Analysis cards */}
          {r.transcript_length_chars > 0 && (
            <>
              <Verdict r={r}/>

              {r.escalation_needed && (
                <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3.5">
                  <AlertTriangle size={15} className="text-red-500 mt-0.5 shrink-0"/>
                  <div>
                    <p className="text-sm font-semibold text-red-700">Escalation Required</p>
                    {r.escalation_reason && <p className="text-xs text-red-600 mt-0.5">{r.escalation_reason}</p>}
                  </div>
                </div>
              )}

              {(r.repeat_ndr || r.rto_already_initiated) && (
                <div className="flex items-center gap-2.5 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
                  <Clock size={14} className="text-amber-500"/>
                  <span className="text-sm text-amber-800 font-medium">
                    {r.repeat_ndr && "Repeat NDR — multiple failed attempts. "}
                    {r.rto_already_initiated && "RTO already initiated on this order."}
                  </span>
                </div>
              )}

              <PointsGrid r={r}/>

              <Card title="Recommended Action" icon={ArrowRight} iconColor="text-violet-400">
                <div className="flex items-center justify-between">
                  <Chip
                    label={r.recommended_action?.replace(/_/g, " ") ?? "—"}
                    variant={["ESCALATE","INVESTIGATE_AGENT","MARK_RTO"].includes(r.recommended_action) ? "red"
                      : ["REATTEMPT_DELIVERY","SCHEDULE_DELIVERY","STOP_RTO_REATTEMPT"].includes(r.recommended_action) ? "green"
                      : r.recommended_action === "PROCESS_REFUND" ? "amber" : "slate"}
                  />
                  <Chip
                    label={r.customer_intent?.replace(/_/g, " ") ?? "UNCLEAR"}
                    variant={r.customer_intent === "WANTS_DELIVERY" ? "green"
                      : r.customer_intent === "WANTS_CANCELLATION" ? "red"
                      : r.customer_intent === "WANTS_REFUND" ? "amber" : "slate"}
                  />
                </div>
                {r.complaint_nature && (
                  <p className="mt-3 text-sm text-slate-600 leading-relaxed">{r.complaint_nature}</p>
                )}
              </Card>

              {r.key_quotes && Object.values(r.key_quotes).some(Boolean) && (
                <Card title="Key Evidence Quotes" icon={MessageSquare} iconColor="text-violet-400">
                  <Quote label="Customer intent" text={r.key_quotes.customer_intent_quote}/>
                  <Quote label="No delivery attempt" text={r.key_quotes.no_attempt_quote}/>
                  <Quote label="No calls received" text={r.key_quotes.no_calls_quote}/>
                  <Quote label="NDR reason" text={r.key_quotes.ndr_reason_quote}/>
                  <Quote label="Product mentioned" text={r.key_quotes.product_quote}/>
                </Card>
              )}

              {(r.resolution_offered || r.resolution_requested) && (
                <Card title="Resolution" icon={CheckCircle2} iconColor="text-emerald-400">
                  {r.resolution_requested && (
                    <div className="mb-2">
                      <p className="text-[10px] text-slate-400 font-medium mb-0.5 uppercase tracking-wider">Customer requested</p>
                      <p className="text-sm text-slate-700">{r.resolution_requested}</p>
                    </div>
                  )}
                  {r.resolution_offered && (
                    <div className={r.resolution_requested ? "pt-2 border-t border-slate-100" : ""}>
                      <p className="text-[10px] text-slate-400 font-medium mb-0.5 uppercase tracking-wider">Agent offered</p>
                      <p className="text-sm text-slate-700">{r.resolution_offered}</p>
                    </div>
                  )}
                </Card>
              )}

              {r.promises_made?.length > 0 && (
                <Card title="Promises Made by Agent" icon={AlertCircle} iconColor="text-amber-400" accent="amber">
                  <ul className="space-y-1">
                    {r.promises_made.map((p, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-amber-800">
                        <span className="text-amber-400 font-bold mt-0.5 shrink-0">•</span>{p}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              {r.fraud_signals?.length > 0 && (
                <Card title="Fraud / Risk Signals" icon={AlertTriangle} iconColor="text-red-400" accent="red">
                  <ul className="space-y-1">
                    {r.fraud_signals.map((s, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-red-800">
                        <AlertTriangle size={13} className="text-red-400 mt-0.5 shrink-0"/>{s}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              <Card title="Call Metadata" icon={Info} iconColor="text-slate-400">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                  {[
                    { label: "Language", val: r.language_detected?.toUpperCase() ?? "—" },
                    { label: "Sentiment", val: r.sentiment ?? "—" },
                    { label: "Direction", val: r.call_direction ?? "—" },
                    { label: "Duration", val: r.call_duration_mentioned ?? "—" },
                  ].map(({ label, val }) => (
                    <div key={label} className="bg-slate-50 rounded-lg py-2.5 px-1">
                      <p className="text-sm font-semibold text-slate-700 capitalize">{val}</p>
                      <p className="text-[10px] text-slate-400 mt-0.5">{label}</p>
                    </div>
                  ))}
                </div>
                <p className="text-[11px] text-slate-400 text-center mt-3">
                  {r.transcript_length_chars?.toLocaleString()} characters analyzed
                </p>
              </Card>
            </>
          )}

          {/* Processing errors */}
          {r.processing_errors?.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <p className="text-[10px] font-semibold text-amber-500 uppercase tracking-wider mb-2">Processing Notes</p>
              {r.processing_errors.map((e, i) => (
                <p key={i} className="text-sm text-amber-700">{e}</p>
              ))}
            </div>
          )}

          {/* Token usage */}
          {r.token_usage?.total_tokens > 0 && (
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <Zap size={11} className="text-violet-400"/>Token Usage
              </p>
              <div className="grid grid-cols-3 gap-3 text-center">
                {[
                  { l: "Input",  v: r.token_usage.input_tokens,  cls: "bg-slate-50" },
                  { l: "Output", v: r.token_usage.output_tokens, cls: "bg-slate-50" },
                  { l: "Total",  v: r.token_usage.total_tokens,  cls: "bg-violet-50 border border-violet-100" },
                ].map(({ l, v, cls }) => (
                  <div key={l} className={cn("rounded-lg py-2.5", cls)}>
                    <p className="text-lg font-bold text-slate-800">{v?.toLocaleString()}</p>
                    <p className="text-[10px] text-slate-400 font-medium mt-0.5">{l}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <RawJSON data={r}/>
        </div>
      )}
    </div>
  );
}
