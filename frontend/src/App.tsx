import { useEffect, useState } from "react";
import { Lock, ShieldCheck } from "lucide-react";
import { PublicResultsPage } from "./pages/PublicResultsPage";

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
import { AtlasPage } from "./pages/AtlasPage";

import { PUBLIC_DEMO_MODE } from "./config";


type Route =
  | { page: "dashboard" }
  | { page: "atlas" }
  | { page: "transcripts" }
  | { page: "transcript-detail"; transcriptId: string }
  | { page: "questions" }
  | { page: "public-results"; transcriptId: string }
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


type PageName = Route["page"];


/*
 * Pages that must never load in the public portfolio build.
 *
 * This is a frontend UX restriction only.
 * The actual security boundary remains:
 *
 * 1. FastAPI PUBLIC_DEMO_MODE
 * 2. Separate sanitized Neon database
 */
const DEMO_PROTECTED_PAGES = new Set<PageName>([
  "atlas",
  "transcripts",
  "transcript-detail",
  "questions",
  "runs",
  "meeting-detail",
  "process-meeting",
  
  "webhooks",
  "insights",
  "learning",
  "zoom-accounts",
  "sync",
]);


function parseHash(hash: string): Route {
  if (
    !hash ||
    hash === "#/" ||
    hash === "#"
  ) {
    return {
      page: "dashboard",
    };
  }

  const publicResultsMatch =
  hash.match(
    /^#\/public-results\/([^/]+)$/
  );

if (publicResultsMatch) {
  return {
    page: "public-results",
    transcriptId: publicResultsMatch[1],
  };
}
  const transcriptDetailMatch =
    hash.match(
      /^#\/transcripts\/([^/]+)$/
    );

  if (transcriptDetailMatch) {
    return {
      page: "transcript-detail",
      transcriptId:
        transcriptDetailMatch[1],
    };
  }


  const meetingDetailMatch =
    hash.match(
      /^#\/meetings\/([^/]+)$/
    );

  if (meetingDetailMatch) {
    return {
      page: "meeting-detail",
      meetingId:
        meetingDetailMatch[1],
    };
  }


  const insightDetailMatch =
    hash.match(
      /^#\/insights\/([^/]+)$/
    );

  if (insightDetailMatch) {
    return {
      page: "insights",
    };
  }


  const learningDetailMatch =
    hash.match(
      /^#\/learning\/([^/]+)$/
    );

  if (learningDetailMatch) {
    return {
      page: "learning",
    };
  }


  const routeMap: Record<
    string,
    Exclude<
      Route["page"],
      "not-found"
    >
  > = {
    "#/": "dashboard",
    "#/atlas": "atlas",
    "#/transcripts": "transcripts",
    "#/questions": "questions",
    "#/runs": "runs",
    "#/meetings": "meetings",
    "#/process-meeting":
      "process-meeting",
    "#/upload-transcript":
      "upload-transcript",
    "#/queue": "queue",
    "#/webhooks": "webhooks",
    "#/insights": "insights",
    "#/learning": "learning",
    "#/zoom-accounts":
      "zoom-accounts",
    "#/sync": "sync",
    "#/settings": "settings",
  };


  const mapped =
    routeMap[hash];

  if (mapped) {
    return {
      page: mapped,
    } as Route;
  }


  return {
    page: "not-found",
  };
}


/*
 * Public portfolio notice.
 *
 * Protected pages are intentionally represented
 * rather than removed from the product.
 */
function DemoProtectedPage({
  feature,
}: {
  feature: string;
}) {
  return (
    <div className="app-shell">

      <div
        className="app-body"
        style={{
          display: "flex",
          flex: 1,
        }}
      >

        <main className="app-content">

          <div
            style={{
              maxWidth: 720,
              margin: "70px auto",
              textAlign: "center",
            }}
          >

            <div
              style={{
                width: 64,
                height: 64,
                borderRadius: 18,
                margin: "0 auto 22px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background:
                  "rgba(99, 102, 241, 0.10)",
                border:
                  "1px solid rgba(99, 102, 241, 0.18)",
              }}
            >
              <Lock
                size={28}
                strokeWidth={1.8}
              />
            </div>


            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                fontWeight: 700,
                padding: "6px 10px",
                borderRadius: 20,
                marginBottom: 18,
                background:
                  "rgba(16, 185, 129, 0.08)",
                border:
                  "1px solid rgba(16, 185, 129, 0.18)",
              }}
            >
              <ShieldCheck size={14} />

              PUBLIC PORTFOLIO DEMO
            </div>


            <h1
              style={{
                marginBottom: 12,
              }}
            >
              {feature}
            </h1>


            <p
              style={{
                fontSize: 16,
                lineHeight: 1.7,
                opacity: 0.68,
                maxWidth: 600,
                margin:
                  "0 auto 26px",
              }}
            >
              This feature is part of the
              full Zoom Agentic AI system,
              but access is disabled in the
              public portfolio deployment
              because it can use private
              meeting content or connected
              Zoom account information.
            </p>


            <div
              style={{
                maxWidth: 560,
                margin: "0 auto 28px",
                padding: 20,
                borderRadius: 14,
                textAlign: "left",
                background:
                  "rgba(255, 255, 255, 0.035)",
                border:
                  "1px solid rgba(128, 128, 128, 0.16)",
              }}
            >

              <div
                style={{
                  fontWeight: 700,
                  marginBottom: 12,
                }}
              >
                Full implementation includes
              </div>


              <div
                style={{
                  display: "grid",
                  gap: 9,
                  fontSize: 14,
                  opacity: 0.72,
                }}
              >
                <div>
                  ✓ Zoom meeting ingestion
                  and synchronization
                </div>

                <div>
                  ✓ Transcript processing
                  and chunking
                </div>

                <div>
                  ✓ Agentic question
                  generation
                </div>

                <div>
                  ✓ Meeting insights and
                  learning outputs
                </div>

                <div>
                  ✓ Transcript-grounded
                  Atlas AI conversations
                </div>
              </div>

            </div>


            <button
              type="button"
              onClick={() => {
                window.location.hash =
                  "#/";
              }}
              style={{
                cursor: "pointer",
                padding: "10px 18px",
                borderRadius: 9,
                border:
                  "1px solid rgba(128, 128, 128, 0.25)",
                background:
                  "transparent",
                fontWeight: 600,
              }}
            >
              Return to Dashboard
            </button>

          </div>

        </main>

      </div>

    </div>
  );
}


function PlaceholderPage({
  title,
}: {
  title: string;
}) {
  return (
    <div className="app-shell">

      <div
        className="app-body"
        style={{
          display: "flex",
          flex: 1,
        }}
      >

        <main className="app-content">

          <div className="page-header">

            <h1>
              {title}
            </h1>

            <p className="page-header-subtitle">
              This page is coming soon.
            </p>

          </div>

        </main>

      </div>

    </div>
  );
}


function getFeatureName(
  page: PageName
): string {

  const names: Partial<
    Record<PageName, string>
  > = {
    atlas: "Atlas AI",
    transcripts: "Transcripts",
    "transcript-detail":
      "Transcript Details",
    questions:
      "Generated Questions",
    runs:
      "Processing Run Details",
    "meeting-detail":
      "Meeting Details",
    "process-meeting":
      "Process Meeting",
    "upload-transcript":
      "Upload Transcript",
    webhooks:
      "Webhook Management",
    insights:
      "Meeting Insights",
    learning:
      "Learning Outputs",
    "zoom-accounts":
      "Zoom Account Management",
    sync:
      "Automatic Zoom Sync",
  };

  return (
    names[page] ??
    "Protected Feature"
  );
}


export default function App() {

  const [route, setRoute] =
    useState<Route>(
      () =>
        parseHash(
          window.location.hash
        )
    );


  useEffect(() => {

    const handleHashChange =
      () => {

        setRoute(
          parseHash(
            window.location.hash
          )
        );
      };


    window.addEventListener(
      "hashchange",
      handleHashChange
    );


    return () =>
      window.removeEventListener(
        "hashchange",
        handleHashChange
      );

  }, []);


  /*
   * Portfolio-mode route interception.
   *
   * This happens BEFORE any protected
   * page component is mounted, which means
   * those components cannot accidentally
   * make private API requests.
   */
  if (
    PUBLIC_DEMO_MODE &&
    DEMO_PROTECTED_PAGES.has(
      route.page
    )
  ) {

    return (
      <DemoProtectedPage
        feature={
          getFeatureName(
            route.page
          )
        }
      />
    );
  }


  switch (route.page) {

    case "dashboard":
      return <DashboardPage />;

    case "atlas":
      return <AtlasPage />;

    case "transcripts":
      return <TranscriptListPage />;

    case "transcript-detail":
  return (
    <TranscriptDetailPage
      transcriptId={route.transcriptId}
    />
  );

case "public-results":
  return (
    <PublicResultsPage
      transcriptId={route.transcriptId}
    />
  );

case "questions":
  return <QuestionsPage />;

    case "runs":
      return <RunsPage />;

    case "meetings":
      return <MeetingsPage />;

    case "meeting-detail":
      return (
        <MeetingDetailPage
          meetingId={
            route.meetingId
          }
        />
      );

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
      return (
        <PlaceholderPage
          title="Settings"
        />
      );

    default:
      return <DashboardPage />;
  }
}