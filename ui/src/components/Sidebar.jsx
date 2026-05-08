import { Video, MessageSquare, ChevronRight, X } from "lucide-react";

const NAV_ITEMS = [
  {
    id: "video-analyzer",
    label: "Video Analyzer",
    icon: Video,
  },
  {
    id: "transcript-analyzer",
    label: "Transcript Analyzer",
    icon: MessageSquare,
  },
];

export default function Sidebar({ activePage, onNavigate, isOpen, onClose }) {
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-20 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed top-0 left-0 h-full w-60 z-30 flex flex-col
          bg-slate-900 text-slate-100
          transform transition-transform duration-200
          ${isOpen ? "translate-x-0" : "-translate-x-full"}
          lg:translate-x-0 lg:static lg:z-auto lg:flex-shrink-0
        `}
      >
        {/* Logo */}
        <div className="flex items-center justify-between px-5 py-5 border-b border-slate-700/60">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-purple-700 flex items-center justify-center shadow-lg shadow-violet-900/40">
              <Video size={16} className="text-white" strokeWidth={2.5} />
            </div>
            <div>
              <span className="text-[15px] font-semibold tracking-tight text-white">
                LogiScan
              </span>
              <p className="text-[10px] text-slate-500 leading-none mt-0.5 font-medium">
                Claims Analyzer
              </p>
            </div>
          </div>

          {/* Close on mobile */}
          <button
            onClick={onClose}
            className="lg:hidden text-slate-400 hover:text-white transition-colors p-1 rounded"
          >
            <X size={18} />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 px-2 pb-2">
            Tools
          </p>

          {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
            const active = activePage === id;
            return (
              <button
                key={id}
                onClick={() => {
                  onNavigate(id);
                  onClose();
                }}
                className={`
                  w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium
                  transition-all duration-150 group relative
                  ${
                    active
                      ? "bg-violet-600/20 text-violet-300"
                      : "text-slate-400 hover:text-slate-100 hover:bg-slate-800"
                  }
                `}
              >
                {active && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-violet-500 rounded-full" />
                )}
                <Icon
                  size={16}
                  className={active ? "text-violet-400" : "text-slate-500 group-hover:text-slate-300"}
                  strokeWidth={2}
                />
                <span className="flex-1 text-left">{label}</span>
                {active && (
                  <ChevronRight size={14} className="text-violet-500 opacity-60" />
                )}
              </button>
            );
          })}

          {/* Placeholder future items */}
          {["Batch Reports", "Settings"].map((label) => (
            <button
              key={label}
              disabled
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium
                text-slate-600 cursor-not-allowed opacity-40"
            >
              <span className="w-4 h-4 rounded bg-slate-700 opacity-50" />
              <span className="flex-1 text-left">{label}</span>
              <span className="text-[9px] bg-slate-700 text-slate-500 px-1.5 py-0.5 rounded font-semibold tracking-wide">
                SOON
              </span>
            </button>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-slate-700/60">
          <p className="text-[11px] text-slate-600">v1.0.0 · LogiScan</p>
        </div>
      </aside>
    </>
  );
}
