import { useEffect, useState } from "react";
import { DashboardPage } from "./pages/DashboardPage";
import { TranscriptListPage } from "./pages/TranscriptListPage";
import { TranscriptDetailPage } from "./pages/TranscriptDetailPage";
import { QuestionsPage } from "./pages/QuestionsPage";
import { RunsPage } from "./pages/RunsPage";
import { MeetingsPage } from "./pages/MeetingsPage";
import { MeetingDetailPage } from "./pages/MeetingDetailPage";
import { ProcessMeetingPage } from "./pages/ProcessMeetingPage";
import { UploadTranscriptPage } from "./pages/UploadTranscriptPage";

import { QueuePage } from "./pages/QueuePage";
import { WebhooksPage } from "./pages/WebhooksPage";
import { InsightsPage } from "./pages/InsightsPage";
import { LearningOutputsPage } from "./pages/LearningOutputsPage";
import { ZoomAccountsPage } from "./pages/ZoomAccountsPage";
import { SyncPage } from "./pages/SyncPage";

function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="app-shell">
      <div className="app-body" style={{ display: "flex", flex: 1 }}>
        <main className="app-content">
          <div className="page-header">
            <h1>{title}</h1>
            <p className="page-header-subtitle">This page is coming soon.</p>
          </div>
        </main>
      </div>
    </div>
  );
}

import { AtlasPage } from "./pages/AtlasPage";

type Route =
  | { page: "dashboard" }
  | { page: "atlas" }
  | { page: "transcripts" }
  | { page: "transcript-detail"; transcriptId: string }
  | { page: "questions" }
  | { page: "runs" }
  | { page: "meetings" }
  | { page: "meeting-detail"; meetingId: string }
  | { page: "process-meeting" }
  | { page: "upload-transcript" }
  | { page: "queue" }
  | { page: "webhooks" }
  | { page: "insights" }
  | { page: "learning" }
  | { page: "zoom-accounts" }
  | { page: "sync" }
  | { page: "settings" }
  | { page: "not-found" };

function parseHash(hash: string): Route {
  if (!hash || hash === "#/" || hash === "#") return { page: "dashboard" };

  const transcriptDetailMatch = hash.match(/^#\/transcripts\/([^/]+)$/);
  if (transcriptDetailMatch) return { page: "transcript-detail", transcriptId: transcriptDetailMatch[1] };

  const meetingDetailMatch = hash.match(/^#\/meetings\/([^/]+)$/);
  if (meetingDetailMatch) return { page: "meeting-detail", meetingId: meetingDetailMatch[1] };

  const insightDetailMatch = hash.match(/^#\/insights\/([^/]+)$/);
  if (insightDetailMatch) return { page: "insights" };

  const learningDetailMatch = hash.match(/^#\/learning\/([^/]+)$/);
  if (learningDetailMatch) return { page: "learning" };

  const routeMap: Record<string, Exclude<Route["page"], "not-found">> = {
    "#/": "dashboard",
    "#/atlas": "atlas",
    "#/transcripts": "transcripts",
    "#/questions": "questions",
    "#/runs": "runs",
    "#/meetings": "meetings",
    "#/process-meeting": "process-meeting",
    "#/upload-transcript": "upload-transcript",
    "#/queue": "queue",
    "#/webhooks": "webhooks",
    "#/insights": "insights",
    "#/learning": "learning",
    "#/zoom-accounts": "zoom-accounts",
    "#/sync": "sync",
    "#/settings": "settings",
  };

  const mapped = routeMap[hash];
  if (mapped) return { page: mapped } as Route;

  return { page: "not-found" };
}

export default function App() {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));

  useEffect(() => {
    const handleHashChange = () => {
      setRoute(parseHash(window.location.hash));
    };
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  switch (route.page) {
    case "dashboard":
      return <DashboardPage />;
    case "atlas":
      return <AtlasPage />;
    case "transcripts":
      return <TranscriptListPage />;
    case "transcript-detail":
      return <TranscriptDetailPage transcriptId={route.transcriptId} />;
    case "questions":
      return <QuestionsPage />;
    case "runs":
      return <RunsPage />;
    case "meetings":
      return <MeetingsPage />;
    case "meeting-detail":
      return <MeetingDetailPage meetingId={route.meetingId} />;
    case "process-meeting":
      return <ProcessMeetingPage />;
    case "upload-transcript":
      return <UploadTranscriptPage />;
    case "queue":
      return <QueuePage />;
    case "webhooks":
      return <WebhooksPage />;
    case "insights":
      return <InsightsPage />;
    case "learning":
      return <LearningOutputsPage />;
    case "zoom-accounts":
      return <ZoomAccountsPage />;
    case "sync":
      return <SyncPage />;
    case "settings":
      return <PlaceholderPage title="Settings" />;
    default:
      return <DashboardPage />;
  }
}
