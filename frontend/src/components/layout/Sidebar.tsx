import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  Compass,
  Video,
  Activity,
  Webhook,
  Lightbulb,
  BookOpen,
  Settings,
  Upload,
  Zap,
  Cpu,
  Users,
  RefreshCw,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "#/", icon: <LayoutDashboard size={20} /> },
  { label: "Atlas", href: "#/atlas", icon: <Compass size={20} /> },
  { label: "Meetings", href: "#/meetings", icon: <Video size={20} /> },
  { label: "Queue", href: "#/queue", icon: <Activity size={20} /> },
  { label: "Webhooks", href: "#/webhooks", icon: <Webhook size={20} /> },
  { label: "Insights", href: "#/insights", icon: <Lightbulb size={20} /> },
  { label: "Learning Outputs", href: "#/learning", icon: <BookOpen size={20} /> },
  { label: "Zoom Accounts", href: "#/zoom-accounts", icon: <Users size={20} /> },
  { label: "Auto Sync", href: "#/sync", icon: <RefreshCw size={20} /> },
  { label: "Settings", href: "#/settings", icon: <Settings size={20} /> },
];

const ACTION_ITEMS: NavItem[] = [
  { label: "Process Meeting", href: "#/process-meeting", icon: <Zap size={20} /> },
  { label: "Upload Transcript", href: "#/upload-transcript", icon: <Upload size={20} /> },
];

function isActiveLink(currentHash: string, href: string): boolean {
  if (href === "#/") {
    return currentHash === "#/" || currentHash === "#" || currentHash === "";
  }
  return currentHash.startsWith(href);
}

export function Sidebar() {
  const [currentHash, setCurrentHash] = useState(window.location.hash || "#/");
  const [ollamaOnline, setOllamaOnline] = useState(false);
  const [primaryModel, setPrimaryModel] = useState("qwen3:8b");

  useEffect(() => {
    const handleHashChange = () => setCurrentHash(window.location.hash || "#/");
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch("http://localhost:11434/api/tags");
        const data = await res.json();
        setOllamaOnline(true);
        const qwen = data.models?.find((m: { name: string }) => m.name.startsWith("qwen3"));
        setPrimaryModel(qwen ? qwen.name : data.models?.[0]?.name ?? "N/A");
      } catch {
        setOllamaOnline(false);
      }
    };
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleClick = (href: string) => {
    setCurrentHash(href);
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-section-label">Navigation</div>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <a
            key={item.href}
            href={item.href}
            className={`sidebar-link ${isActiveLink(currentHash, item.href) ? "active" : ""}`}
            onClick={() => handleClick(item.href)}
          >
            <span className="sidebar-link-icon">{item.icon}</span>
            {item.label}
          </a>
        ))}
      </nav>
      <div className="sidebar-section-label" style={{ marginTop: 28 }}>
        Actions
      </div>
      <nav className="sidebar-nav">
        {ACTION_ITEMS.map((item) => (
          <a
            key={item.href}
            href={item.href}
            className={`sidebar-link ${currentHash === item.href ? "active" : ""}`}
            onClick={() => handleClick(item.href)}
          >
            <span className="sidebar-link-icon">{item.icon}</span>
            {item.label}
          </a>
        ))}
      </nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-footer">
        <div className="sidebar-model-info">
          <span className={`sidebar-model-dot ${ollamaOnline ? "" : "offline"}`} />
          <div>
            <div className="sidebar-model-label">LLM Engine</div>
            <div className="sidebar-model-name">{primaryModel}</div>
          </div>
          <Cpu size={16} style={{ marginLeft: "auto", opacity: 0.4 }} />
        </div>
        <div className="sidebar-version">Zoom Agentic AI v0.1.0</div>
      </div>
    </aside>
  );
}
