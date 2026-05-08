import { useState } from "react";
import { Menu } from "lucide-react";
import Sidebar from "./components/Sidebar";
import VideoAnalyzer from "./pages/VideoAnalyzer";
import TranscriptAnalyzer from "./pages/TranscriptAnalyzer";
import ImageAnalyzer from "./pages/ImageAnalyzer";

const PAGES = {
  "video-analyzer": <VideoAnalyzer />,
  "transcript-analyzer": <TranscriptAnalyzer />,
  "image-analyzer": <ImageAnalyzer />,
};

export default function App() {
  const [activePage, setActivePage] = useState("transcript-analyzer");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      <Sidebar
        activePage={activePage}
        onNavigate={setActivePage}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar (mobile) */}
        <header className="lg:hidden flex items-center gap-3 px-4 py-3.5 bg-white border-b border-slate-200 flex-shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <Menu size={20} />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-violet-500 to-purple-700 flex items-center justify-center">
              <span className="text-[10px] text-white font-bold">LS</span>
            </div>
            <span className="text-sm font-semibold text-slate-800">LogiScan</span>
          </div>
        </header>

        {/* Scrollable content */}
        <main className="flex-1 overflow-y-auto">
          {PAGES[activePage]}
        </main>
      </div>
    </div>
  );
}
