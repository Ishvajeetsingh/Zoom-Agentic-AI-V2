import { useEffect, useState } from "react";
import {
  Zap,
  ShieldCheck,
} from "lucide-react";

import { getOllamaStatus } from "../../api/ollama";
import { PUBLIC_DEMO_MODE } from "../../config";


export function TopBar() {
  const [ollamaStatus, setOllamaStatus] =
    useState<"online" | "offline">("offline");

  const [modelInfo, setModelInfo] =
    useState<string>("");


  useEffect(() => {
    // Public portfolio does not use local Ollama.
    if (PUBLIC_DEMO_MODE) {
      return;
    }

    const checkOllama = async () => {
      try {
        const data =
          await getOllamaStatus();

        if (data.online) {
          setOllamaStatus("online");

          const qwen =
            data.models?.find(
              (model) =>
                model.name.startsWith("qwen3")
            );

          setModelInfo(
            qwen
              ? qwen.name
              : data.models?.[0]?.name ??
                  "No model"
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

    const interval =
      setInterval(
        checkOllama,
        30000
      );

    return () =>
      clearInterval(interval);

  }, []);


  return (
    <header className="topbar">

      <div className="topbar-logo">
        <div className="topbar-logo-icon">
          <Zap size={18} />
        </div>

        <span className="topbar-title">
          Zoom Agentic AI
        </span>
      </div>


      <span className="topbar-subtitle">
        Intelligent Question Generation Platform
      </span>


      <div className="topbar-spacer" />


      {PUBLIC_DEMO_MODE ? (

        <div className="topbar-badge">
          <ShieldCheck size={14} />

          <span>
            Public Demo · Read-only
          </span>
        </div>

      ) : (

        <div
          className={
            `topbar-badge ${
              ollamaStatus === "offline"
                ? "offline"
                : ""
            }`
          }
        >
          <span className="topbar-badge-dot" />

          Ollama{" "}
          {ollamaStatus === "online"
            ? "Online"
            : "Offline"}{" "}
          &middot; {modelInfo}
        </div>

      )}

    </header>
  );
}