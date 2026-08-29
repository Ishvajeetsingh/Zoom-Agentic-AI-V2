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
  Lock,
  ShieldCheck,
} from "lucide-react";

import { getOllamaStatus } from "../../api/ollama";
import { PUBLIC_DEMO_MODE } from "../../config";


interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  protectedInDemo?: boolean;
}


const NAV_ITEMS: NavItem[] = [
  {
    label: "Dashboard",
    href: "#/",
    icon: <LayoutDashboard size={20} />,
  },
  {
    label: "Atlas",
    href: "#/atlas",
    icon: <Compass size={20} />,
    protectedInDemo: true,
  },
  {
    label: "Meetings",
    href: "#/meetings",
    icon: <Video size={20} />,
  },
  {
    label: "Queue",
    href: "#/queue",
    icon: <Activity size={20} />,
  },
  {
    label: "Webhooks",
    href: "#/webhooks",
    icon: <Webhook size={20} />,
    protectedInDemo: true,
  },
  {
    label: "Insights",
    href: "#/insights",
    icon: <Lightbulb size={20} />,
    protectedInDemo: true,
  },
  {
    label: "Learning Outputs",
    href: "#/learning",
    icon: <BookOpen size={20} />,
    protectedInDemo: true,
  },
  {
    label: "Zoom Accounts",
    href: "#/zoom-accounts",
    icon: <Users size={20} />,
    protectedInDemo: true,
  },
  {
    label: "Auto Sync",
    href: "#/sync",
    icon: <RefreshCw size={20} />,
    protectedInDemo: true,
  },
  {
    label: "Settings",
    href: "#/settings",
    icon: <Settings size={20} />,
  },
];


const ACTION_ITEMS: NavItem[] = [
  {
    label: "Process Meeting",
    href: "#/process-meeting",
    icon: <Zap size={20} />,
    protectedInDemo: true,
  },
  {
  label: "Upload Transcript",
  href: "#/upload-transcript",
  icon: <Upload size={20} />,
},
];


function isActiveLink(
  currentHash: string,
  href: string
): boolean {
  if (href === "#/") {
    return (
      currentHash === "#/" ||
      currentHash === "#" ||
      currentHash === ""
    );
  }

  return currentHash.startsWith(href);
}


export function Sidebar() {
  const [currentHash, setCurrentHash] =
    useState(window.location.hash || "#/");

  const [ollamaOnline, setOllamaOnline] =
    useState(false);

  const [primaryModel, setPrimaryModel] =
    useState("qwen3:8b");


  // =========================================================
  // HASH NAVIGATION
  // =========================================================

  useEffect(() => {
    const handleHashChange = () => {
      setCurrentHash(
        window.location.hash || "#/"
      );
    };

    window.addEventListener(
      "hashchange",
      handleHashChange
    );

    return () => {
      window.removeEventListener(
        "hashchange",
        handleHashChange
      );
    };
  }, []);


  // =========================================================
  // OLLAMA STATUS
  //
  // Only used by the normal/local application.
  // Public portfolio mode does not call local Ollama.
  // =========================================================

  useEffect(() => {
    if (PUBLIC_DEMO_MODE) {
      return;
    }

    const check = async () => {
      try {
        const data = await getOllamaStatus();

        if (data.online) {
          setOllamaOnline(true);

          const qwen = data.models?.find(
            (model) =>
              model.name.startsWith("qwen3")
          );

          setPrimaryModel(
            qwen
              ? qwen.name
              : data.models?.[0]?.name ?? "N/A"
          );
        } else {
          setOllamaOnline(false);
          setPrimaryModel("Unavailable");
        }
      } catch {
        setOllamaOnline(false);
        setPrimaryModel("Unavailable");
      }
    };

    check();

    const interval = setInterval(
      check,
      30000
    );

    return () => {
      clearInterval(interval);
    };
  }, []);


  // =========================================================
  // NAVIGATION
  // =========================================================

  const handleClick = (
    href: string
  ) => {
    setCurrentHash(href);
  };


  const renderNavItem = (
    item: NavItem
  ) => {
    const isProtected =
      PUBLIC_DEMO_MODE &&
      item.protectedInDemo;

    return (
      <a
        key={item.href}
        href={item.href}
        className={
          `sidebar-link ${
            isActiveLink(
              currentHash,
              item.href
            )
              ? "active"
              : ""
          } ${
            isProtected
              ? "demo-protected"
              : ""
          }`
        }
        onClick={() =>
          handleClick(item.href)
        }
        title={
          isProtected
            ? "Protected in public portfolio demo"
            : undefined
        }
      >
        <span className="sidebar-link-icon">
          {item.icon}
        </span>

        <span>
          {item.label}
        </span>

        {isProtected && (
          <Lock
            size={13}
            style={{
              marginLeft: "auto",
              opacity: 0.55,
            }}
          />
        )}
      </a>
    );
  };


  return (
    <aside className="sidebar">

      {PUBLIC_DEMO_MODE && (
        <div
          style={{
            margin: "4px 12px 18px",
            padding: "10px 12px",
            borderRadius: 10,
            background:
              "rgba(59, 130, 246, 0.08)",
            border:
              "1px solid rgba(59, 130, 246, 0.18)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              fontSize: 12,
              fontWeight: 700,
            }}
          >
            <ShieldCheck size={14} />

            Public Portfolio Demo
          </div>

          <div
            style={{
              fontSize: 10,
              opacity: 0.6,
              marginTop: 4,
              lineHeight: 1.4,
            }}
          >
            Read-only mode. Sensitive
            meeting content is protected.
          </div>
        </div>
      )}


      <div className="sidebar-section-label">
        Navigation
      </div>


      <nav className="sidebar-nav">
        {NAV_ITEMS.map(
          renderNavItem
        )}
      </nav>


      <div
        className="sidebar-section-label"
        style={{
          marginTop: 28,
        }}
      >
        Actions
      </div>


      <nav className="sidebar-nav">
        {ACTION_ITEMS.map(
          renderNavItem
        )}
      </nav>


      <div className="sidebar-spacer" />


      <div className="sidebar-footer">

        {PUBLIC_DEMO_MODE ? (
          <div className="sidebar-model-info">

            <span className="sidebar-model-dot" />

            <div>
              <div className="sidebar-model-label">
                Deployment
              </div>

              <div className="sidebar-model-name">
                Read-only Demo
              </div>
            </div>

            <ShieldCheck
              size={16}
              style={{
                marginLeft: "auto",
                opacity: 0.5,
              }}
            />

          </div>
        ) : (
          <div className="sidebar-model-info">

            <span
              className={
                `sidebar-model-dot ${
                  ollamaOnline
                    ? ""
                    : "offline"
                }`
              }
            />

            <div>
              <div className="sidebar-model-label">
                LLM Engine
              </div>

              <div className="sidebar-model-name">
                {primaryModel}
              </div>
            </div>

            <Cpu
              size={16}
              style={{
                marginLeft: "auto",
                opacity: 0.4,
              }}
            />

          </div>
        )}


        <div className="sidebar-version">
          Zoom Agentic AI v0.1.0
        </div>

      </div>

    </aside>
  );
}