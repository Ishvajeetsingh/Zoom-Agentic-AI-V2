import { useEffect, useState } from "react";
import { Zap } from "lucide-react";
import { getOllamaStatus } from "../../api/ollama";

export function TopBar() {
  const [ollamaStatus, setOllamaStatus] = useState<"online" | "offline">("offline");
  const [modelInfo, setModelInfo] = useState<string>("");

  useEffect(() => {
    const checkOllama = async () => {
  try {
    const data = await getOllamaStatus();

    if (data.online) {
      setOllamaStatus("online");

      const qwen = data.models?.find((m) =>
        m.name.startsWith("qwen3")
      );

      setModelInfo(
        qwen
          ? qwen.name
          : data.models?.[0]?.name ?? "No model"
      );
    } else {
      setOllamaStatus("offline");
      setModelInfo("Unavailable");
    }
  } catch {
    setOllamaStatus("offline");
    setModelInfo("Unavailable");
  }
};
    checkOllama();
    const interval = setInterval(checkOllama, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="topbar">
      <div className="topbar-logo">
        <div className="topbar-logo-icon">
          <Zap size={18} />
        </div>
        <span className="topbar-title">Zoom Agentic AI</span>
      </div>
      <span className="topbar-subtitle">Intelligent Question Generation Platform</span>
      <div className="topbar-spacer" />
      <div className={`topbar-badge ${ollamaStatus === "offline" ? "offline" : ""}`}>
        <span className="topbar-badge-dot" />
        Ollama {ollamaStatus === "online" ? "Online" : "Offline"} &middot; {modelInfo}
      </div>
    </header>
  );
}
