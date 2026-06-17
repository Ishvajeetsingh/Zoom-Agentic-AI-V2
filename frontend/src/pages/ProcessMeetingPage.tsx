import { useState, useMemo } from "react";
import { Video, RotateCcw, Search, CheckCircle, XCircle } from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { ProcessingTimeline, type TimelineStep } from "../components/common/ProcessingTimeline";
import { CompletionCard } from "../components/common/CompletionCard";
import { LoadingState } from "../components/common/LoadingState";
import { EmptyState } from "../components/common/EmptyState";
import { discoverMeetings, discoverTranscripts, orchestrateZoomMeeting, type OrchestrateZoomResponse } from "../api/zoom";
import { ingestZoomMeeting } from "../api/zoom";
import { runPipeline } from "../api/transcripts";
import type { PipelineResponse, DiscoveredMeeting, DiscoverTranscriptsResponse } from "../types/api";
import type { ZoomIngestResponse } from "../types/api";

type Phase =
  | "discover"
  | "selecting"
  | "checking-transcript"
  | "orchestrating"
  | "form"
  | "ingesting"
  | "pipeline"
  | "done"
  | "error";

const ORCHESTRATE_STEPS: TimelineStep[] = [
  { key: "auth", label: "Authenticate with Zoom", description: "Obtain OAuth access token", status: "waiting" },
  { key: "ingest", label: "Ingest Meeting", description: "Fetch and save meeting recording metadata", status: "waiting" },
  { key: "transcript", label: "Discover Transcript", description: "Locate VTT/CC transcript in recording files", status: "waiting" },
  { key: "download", label: "Download Transcript", description: "Download VTT file from Zoom cloud", status: "waiting" },
  { key: "parse", label: "Parse Transcript", description: "Extract speaker segments and timestamps", status: "waiting" },
  { key: "clean", label: "Clean Transcript", description: "Normalize speakers, remove fillers and artifacts", status: "waiting" },
  { key: "chunk", label: "Semantic Chunking", description: "Split transcript into topic-coherent chunks", status: "waiting" },
  { key: "generate", label: "Generate Questions", description: "Create quiz questions using LLM", status: "waiting" },
  { key: "generate_learning_outputs", label: "Generate Learning Outputs", description: "Extract key concepts and learning objectives", status: "waiting" },
  { key: "synthesize", label: "Synthesize Insights", description: "Produce insights and summary from processed data", status: "waiting" },
];

const INGEST_STEPS: TimelineStep[] = [
  { key: "auth", label: "Authenticate with Zoom", description: "Obtain OAuth access token", status: "waiting" },
  { key: "fetch", label: "Fetch Recording Metadata", description: "Retrieve meeting and recording details", status: "waiting" },
  { key: "meeting", label: "Save Meeting Record", description: "Upsert meeting into database", status: "waiting" },
  { key: "transcript", label: "Find Transcript File", description: "Locate VTT/CC transcript in recording files", status: "waiting" },
];

const PIPELINE_STEPS: TimelineStep[] = [
  { key: "download", label: "Download Transcript", description: "Download VTT file from Zoom cloud", status: "waiting" },
  { key: "parse", label: "Parse Transcript", description: "Extract speaker segments and timestamps", status: "waiting" },
  { key: "clean", label: "Clean Transcript", description: "Normalize speakers, remove fillers and artifacts", status: "waiting" },
  { key: "chunk", label: "Semantic Chunking", description: "Split transcript into topic-coherent chunks", status: "waiting" },
  { key: "generate", label: "Generate Questions", description: "Create quiz questions using LLM", status: "waiting" },
  { key: "generate_learning_outputs", label: "Generate Learning Outputs", description: "Extract key concepts and learning objectives", status: "waiting" },
  { key: "synthesize", label: "Synthesize Insights", description: "Produce insights and summary from processed data", status: "waiting" },
];

function setStep(steps: TimelineStep[], key: string, status: TimelineStep["status"], desc?: string): TimelineStep[] {
  return steps.map((s) =>
    s.key === key ? { ...s, status, description: desc ?? s.description } : s
  );
}

function markPreviousCompleted(steps: TimelineStep[], upToKey: string): TimelineStep[] {
  let found = false;
  return steps.map((s) => {
    if (s.key === upToKey) found = true;
    return !found && s.status !== "failed" ? { ...s, status: "completed" as const } : s;
  });
}

export function ProcessMeetingPage() {
  const [meetingUuid, setMeetingUuid] = useState("");
  const [phase, setPhase] = useState<Phase>("discover");
  const [meetingSearch, setMeetingSearch] = useState("");
  const [discoveredMeetings, setDiscoveredMeetings] = useState<DiscoveredMeeting[]>([]);
  const [selectedMeeting, setSelectedMeeting] = useState<DiscoveredMeeting | null>(null);
  const [transcriptInfo, setTranscriptInfo] = useState<DiscoverTranscriptsResponse | null>(null);
  const [orchestrateSteps, setOrchestrateSteps] = useState<TimelineStep[]>(ORCHESTRATE_STEPS);
  const [ingestSteps, setIngestSteps] = useState<TimelineStep[]>(INGEST_STEPS);
  const [pipelineSteps, setPipelineSteps] = useState<TimelineStep[]>(PIPELINE_STEPS);
  const [ingestResult, setIngestResult] = useState<ZoomIngestResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [completionStats, setCompletionStats] = useState<{ label: string; value: string }[]>([]);
  const [orchestrateResult, setOrchestrateResult] = useState<OrchestrateZoomResponse | null>(null);

  const reset = () => {
    setPhase("discover");
    setMeetingUuid("");
    setDiscoveredMeetings([]);
    setSelectedMeeting(null);
    setTranscriptInfo(null);
    setOrchestrateSteps(ORCHESTRATE_STEPS.map((s) => ({ ...s })));
    setIngestSteps(INGEST_STEPS.map((s) => ({ ...s })));
    setPipelineSteps(PIPELINE_STEPS.map((s) => ({ ...s })));
    setIngestResult(null);
    setErrorMsg(null);
    setCompletionStats([]);
    setOrchestrateResult(null);
    setMeetingSearch("");
  };

  const handleDiscoverMeetings = async () => {
    setPhase("discover");
    setDiscoveredMeetings([]);
    setSelectedMeeting(null);
    setTranscriptInfo(null);
    setErrorMsg(null);

    try {
      const result = await discoverMeetings();
      setDiscoveredMeetings(result.meetings);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to discover meetings";
      setErrorMsg(msg);
      setPhase("error");
    }
  };

  const handleSelectMeeting = async (meeting: DiscoveredMeeting) => {
    setSelectedMeeting(meeting);
    setPhase("checking-transcript");
    setErrorMsg(null);

    try {
      const result = await discoverTranscripts(meeting.meeting_id);
      setTranscriptInfo(result);

      if (result.transcripts_found && result.transcript_ids.length > 0) {
        setPhase("orchestrating");
        runOrchestrate(meeting.uuid);
      } else {
        setPhase("error");
        setErrorMsg("No transcript found for this meeting. The meeting may not have had cloud transcription enabled. Try selecting a meeting with a transcript indicator.");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to discover transcripts";
      setErrorMsg(msg);
      setPhase("error");
    }
  };

  const runOrchestrate = async (uuid: string) => {
    let steps = ORCHESTRATE_STEPS.map((s) => ({ ...s }));
    steps = setStep(steps, "auth", "running", "Requesting OAuth token...");
    setOrchestrateSteps([...steps]);

    try {
      await new Promise((r) => setTimeout(r, 600));
      steps = markPreviousCompleted(setStep(steps, "auth", "completed"), "auth");
      steps = setStep(steps, "ingest", "running", "Fetching meeting recording metadata...");
      setOrchestrateSteps([...steps]);

      const result = await orchestrateZoomMeeting(uuid);

      steps = markPreviousCompleted(setStep(steps, "ingest", "completed"), "ingest");

      if (result.transcript_id) {
        steps = markPreviousCompleted(setStep(steps, "transcript", "completed"), "transcript");
        steps = setStep(steps, "download", "running", "Downloading VTT from Zoom...");
        setOrchestrateSteps([...steps]);
      } else {
        steps = setStep(steps, "transcript", "failed", "No transcript found");
        setOrchestrateSteps([...steps]);
        setPhase("error");
        setErrorMsg("Orchestration completed but no transcript was found for this meeting.");
        return;
      }

      setOrchestrateResult(result);

      const stepKeys = ["download", "parse", "clean", "chunk", "generate", "generate_learning_outputs", "synthesize"];
      const stepLabels: Record<string, string> = {
        download: "Downloading VTT from Zoom...",
        parse: "Extracting speaker segments...",
        clean: "Normalizing and cleaning...",
        chunk: "Building semantic chunks...",
        generate: "Running LLM question generation...",
        generate_learning_outputs: "Generating learning outputs...",
        synthesize: "Synthesizing insights...",
      };

      let currentIdx = stepKeys.indexOf("download");

      const advanceInterval = setInterval(() => {
        if (currentIdx < stepKeys.length - 1) {
          steps = markPreviousCompleted(steps, stepKeys[currentIdx]);
          steps = setStep(steps, stepKeys[currentIdx], "completed");
          currentIdx++;
          steps = setStep(steps, stepKeys[currentIdx], "running", stepLabels[stepKeys[currentIdx]]);
          setOrchestrateSteps([...steps]);
        }
      }, 2000);

      const pipelineResult: PipelineResponse = await runPipeline(result.transcript_id);

      clearInterval(advanceInterval);

      const completedKeys = new Set(
        pipelineResult.steps.filter((s) => s.status === "completed").map((s) => s.step)
      );
      const failedStep = pipelineResult.steps.find((s) => s.status === "failed");

      steps = ORCHESTRATE_STEPS.map((s) => ({
        ...s,
        status: completedKeys.has(s.key)
          ? ("completed" as const)
          : s.key === failedStep?.step
            ? ("failed" as const)
            : s.status === "running"
              ? s.status
              : ("waiting" as const),
      }));

      const alreadyCompleted = new Set(
        [...steps].filter((s) => s.status === "completed").map((s) => s.key)
      );
      steps = steps.map((s) => {
        if (alreadyCompleted.has(s.key)) return { ...s, status: "completed" as const };
        if (s.key === failedStep?.step) return { ...s, status: "failed" as const };
        if (s.status === "running") return s;
        return { ...s, status: "waiting" as const };
      });

      setOrchestrateSteps([...steps]);

      if (failedStep) {
        const errMsg = pipelineResult.errors.length ? pipelineResult.errors.join("; ") : `Step ${failedStep.step} failed`;
        setErrorMsg(errMsg);
        setPhase("error");
      } else {
        for (const key of stepKeys) {
          steps = setStep(steps, key, "completed");
        }
        setOrchestrateSteps([...steps]);
        setPhase("done");
        setCompletionStats([
          { label: "Meeting", value: selectedMeeting?.topic ?? result.meeting_id },
          { label: "Transcript ID", value: result.transcript_id },
          { label: "Run ID", value: result.run_id },
          { label: "Status", value: result.status },
        ]);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Orchestration failed";
      const failedStep = steps.find((s) => s.status === "running");
      if (failedStep) {
        steps = setStep(steps, failedStep.key, "failed", msg);
        setOrchestrateSteps([...steps]);
      }
      setPhase("error");
      setErrorMsg(msg);
    }
  };

  const handleIngest = async () => {
    if (!meetingUuid.trim()) return;
    setPhase("ingesting");
    setErrorMsg(null);
    let steps = INGEST_STEPS.map((s) => ({ ...s }));

    steps = setStep(steps, "auth", "running", "Requesting OAuth token...");
    setIngestSteps([...steps]);

    try {
      await new Promise((r) => setTimeout(r, 600));
      steps = markPreviousCompleted(setStep(steps, "auth", "completed"), "auth");
      steps = setStep(steps, "fetch", "running", "Calling Zoom Recording API...");
      setIngestSteps([...steps]);

      const result = await ingestZoomMeeting({ meeting_uuid: meetingUuid.trim() });

      steps = markPreviousCompleted(setStep(steps, "fetch", "completed"), "fetch");
      steps = setStep(steps, "meeting", "completed", "Meeting record saved");
      if (result.recording_found) {
        steps = setStep(steps, "transcript", "completed", "Transcript file found");
      } else {
        steps = setStep(steps, "transcript", "failed", "No transcript file found in recording");
      }
      setIngestSteps([...steps]);
      setIngestResult(result);

      if (result.transcript_id && result.recording_found) {
        setPhase("pipeline");
        runPipelineSteps(result.transcript_id);
      } else if (!result.recording_found) {
        setPhase("error");
        setErrorMsg("No transcript recording found for this meeting. The meeting may not have had cloud transcription enabled.");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Ingestion failed";
      steps = setStep(
        steps,
        steps.find((s) => s.status === "running")?.key ?? "fetch",
        "failed",
        msg
      );
      setIngestSteps([...steps]);
      setPhase("error");
      setErrorMsg(msg);
    }
  };

  const runPipelineSteps = async (transcriptId: string) => {
    const stepKeys = ["download", "parse", "clean", "chunk", "generate", "generate_learning_outputs", "synthesize"];
    const stepLabels: Record<string, string> = {
      download: "Downloading VTT from Zoom...",
      parse: "Extracting speaker segments...",
      clean: "Normalizing and cleaning...",
      chunk: "Building semantic chunks...",
      generate: "Running LLM question generation...",
      generate_learning_outputs: "Generating learning outputs...",
      synthesize: "Synthesizing insights...",
    };

    let steps = PIPELINE_STEPS.map((s) => ({ ...s }));
    let currentIdx = 0;

    steps = setStep(steps, stepKeys[0], "running", stepLabels[stepKeys[0]]);
    setPipelineSteps([...steps]);

    const advanceInterval = setInterval(() => {
      if (currentIdx < stepKeys.length - 1) {
        steps = markPreviousCompleted(steps, stepKeys[currentIdx]);
        steps = setStep(steps, stepKeys[currentIdx], "completed");
        currentIdx++;
        steps = setStep(steps, stepKeys[currentIdx], "running", stepLabels[stepKeys[currentIdx]]);
        setPipelineSteps([...steps]);
      }
    }, 2000);

    try {
      const result: PipelineResponse = await runPipeline(transcriptId);

      clearInterval(advanceInterval);

      const completedKeys = new Set(
        result.steps.filter((s) => s.status === "completed").map((s) => s.step)
      );
      const failedStep = result.steps.find((s) => s.status === "failed");

      steps = PIPELINE_STEPS.map((s) => ({
        ...s,
        status: completedKeys.has(s.key)
          ? ("completed" as const)
          : s.key === failedStep?.step
            ? ("failed" as const)
            : s.status === "running"
              ? s.status
              : ("waiting" as const),
      }));

      setPipelineSteps([...steps]);

      if (failedStep) {
        const errMsg = result.errors.length ? result.errors.join("; ") : `Step ${failedStep.step} failed`;
        setErrorMsg(errMsg);
        setPhase("error");
      } else {
        for (const key of stepKeys) {
          steps = setStep(steps, key, "completed");
        }
        setPipelineSteps([...steps]);
        setPhase("done");
        setCompletionStats([
          { label: "Meeting ID", value: ingestResult?.meeting_id ?? "" },
          { label: "Transcript ID", value: transcriptId },
          { label: "Topic", value: ingestResult?.topic ?? "N/A" },
          { label: "Zoom UUID", value: ingestResult?.zoom_uuid ?? meetingUuid },
        ]);
      }
    } catch (err) {
      clearInterval(advanceInterval);
      const msg = err instanceof Error ? err.message : "Pipeline failed";
      const failedStep = steps.find((s) => s.status === "running");
      if (failedStep) {
        steps = setStep(steps, failedStep.key, "failed", msg);
        setPipelineSteps([...steps]);
      }
      setPhase("error");
      setErrorMsg(msg);
    }
  };

  const filteredMeetings = useMemo(() => {
    if (!meetingSearch.trim()) return discoveredMeetings;
    const q = meetingSearch.toLowerCase();
    return discoveredMeetings.filter(
      (m) =>
        (m.topic?.toLowerCase().includes(q) ?? false) ||
        m.meeting_id.toLowerCase().includes(q) ||
        (m.start_time?.toLowerCase().includes(q) ?? false)
    );
  }, [discoveredMeetings, meetingSearch]);

  const formatDate = (iso: string | null) => {
    if (!iso) return "N/A";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  const formatDuration = (mins: number | null) => {
    if (mins == null) return "N/A";
    if (mins < 60) return `${mins} min`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  };

  return (
    <AppShell>
      <div className="process-page">
        <div className="page-header">
          <h1>Process Zoom Meeting</h1>
          <p className="page-header-subtitle">
            Discover, select, and process Zoom meeting recordings automatically
          </p>
        </div>

        {phase === "discover" && (
          <div className="process-form">
            <div className="panel" style={{ marginBottom: 24 }}>
              <div className="panel-header">
                <h2 className="panel-title">Discover Meetings</h2>
              </div>
              <p style={{ marginBottom: 16, color: "var(--text-secondary, #6b7280)" }}>
                Fetch your recent Zoom meetings from the Zoom API. Select one to automatically discover transcripts and start processing.
              </p>
              <button className="btn-primary" onClick={handleDiscoverMeetings}>
                <Search size={18} /> Discover Meetings
              </button>
            </div>

            <div className="panel" style={{ marginBottom: 24 }}>
              <div className="panel-header">
                <h2 className="panel-title">Manual UUID Entry</h2>
              </div>
              <div className="form-group">
                <label className="form-label">Meeting UUID</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="e.g. /Mv5TxyCQVM8wOQ=="
                  value={meetingUuid}
                  onChange={(e) => setMeetingUuid(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleIngest()}
                />
                <p className="form-hint">
                  Find this in the Zoom portal under Past Meetings, or from the recording URL.
                </p>
              </div>
              <button className="btn-primary" onClick={() => { setPhase("form"); handleIngest(); }} disabled={!meetingUuid.trim()}>
                <Video size={18} /> Ingest & Process
              </button>
            </div>

            {discoveredMeetings.length > 0 && (
              <div className="panel">
                <div className="panel-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
                  <h2 className="panel-title">Discovered Meetings ({discoveredMeetings.length})</h2>
                  <div style={{ position: "relative" }}>
                    <input
                      className="form-input"
                      type="text"
                      placeholder="Search by topic, meeting ID, or date..."
                      value={meetingSearch}
                      onChange={(e) => setMeetingSearch(e.target.value)}
                      style={{ paddingLeft: 36, minWidth: 280 }}
                    />
                    <Search size={16} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#9ca3af" }} />
                  </div>
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table className="meeting-table" style={{ width: "100%" }}>
                    <thead>
                      <tr>
                        <th>Topic</th>
                        <th>Meeting ID</th>
                        <th>Start Time</th>
                        <th>Duration</th>
                        <th>Participants</th>
                        <th>Transcript</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredMeetings.length === 0 && (
                        <tr>
                          <td colSpan={7} style={{ textAlign: "center", padding: 24 }}>
                            No meetings match your search.
                          </td>
                        </tr>
                      )}
                      {filteredMeetings.map((m) => (
                        <tr key={m.uuid}>
                          <td style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {m.topic ?? "Untitled"}
                          </td>
                          <td style={{ fontFamily: "monospace", fontSize: 13 }}>{m.meeting_id}</td>
                          <td style={{ whiteSpace: "nowrap" }}>{formatDate(m.start_time)}</td>
                          <td>{formatDuration(m.duration_minutes)}</td>
                          <td>{m.participant_count ?? "N/A"}</td>
                          <td>
                            {m.has_transcript ? (
                              <span style={{ color: "#16a34a", display: "inline-flex", alignItems: "center", gap: 4 }}>
                                <CheckCircle size={16} /> Yes
                              </span>
                            ) : (
                              <span style={{ color: "#dc2626", display: "inline-flex", alignItems: "center", gap: 4 }}>
                                <XCircle size={16} /> No
                              </span>
                            )}
                          </td>
                          <td>
                            <button
                              className="btn-primary"
                              style={{ padding: "6px 16px", fontSize: 13 }}
                              onClick={() => handleSelectMeeting(m)}
                              disabled={selectedMeeting?.uuid === m.uuid}
                            >
                              <Video size={14} /> Process
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {discoveredMeetings.length === 0 && Object.keys(discoveredMeetings).length === 0 && phase === "discover" && !errorMsg && (
              <EmptyState
                title="No meetings discovered yet"
                message="Click 'Discover Meetings' to fetch your recent Zoom meetings."
              />
            )}
          </div>
        )}

        {phase === "checking-transcript" && selectedMeeting && (
          <div className="panel" style={{ marginBottom: 24 }}>
            <div className="panel-header">
              <h2 className="panel-title">Checking Transcript Availability</h2>
            </div>
            <LoadingState message={`Discovering transcripts for: ${selectedMeeting.topic ?? selectedMeeting.meeting_id}`} />
          </div>
        )}

        {phase === "orchestrating" && (
          <div className="panel" style={{ marginBottom: 24 }}>
            <div className="panel-header">
              <h2 className="panel-title">Processing: {selectedMeeting?.topic ?? selectedMeeting?.meeting_id ?? "Meeting"}</h2>
            </div>
            <ProcessingTimeline steps={orchestrateSteps} />
          </div>
        )}

        {phase === "form" && (
          <div className="process-form">
            <div className="form-group">
              <label className="form-label">Meeting UUID</label>
              <input
                className="form-input"
                type="text"
                placeholder="e.g. /Mv5TxyCQVM8wOQ=="
                value={meetingUuid}
                onChange={(e) => setMeetingUuid(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleIngest()}
              />
              <p className="form-hint">
                Find this in the Zoom portal under Past Meetings, or from the recording URL.
              </p>
            </div>
            <button className="btn-primary" onClick={handleIngest} disabled={!meetingUuid.trim()}>
              <Video size={18} /> Ingest & Process
            </button>
          </div>
        )}

        {(phase === "ingesting" || phase === "pipeline") && (
          <>
            <div className="panel" style={{ marginBottom: 24 }}>
              <div className="panel-header">
                <h2 className="panel-title">Ingestion</h2>
              </div>
              <ProcessingTimeline steps={ingestSteps} />
            </div>

            {ingestResult?.transcript_id && (
              <div className="panel" style={{ marginBottom: 24 }}>
                <div className="panel-header">
                  <h2 className="panel-title">Processing Pipeline</h2>
                </div>
                <ProcessingTimeline steps={pipelineSteps} />
              </div>
            )}
          </>
        )}

        {(phase === "error" && errorMsg) && (
          <div className="process-error-box">
            <span>&#9888;</span>
            <p>{errorMsg}</p>
          </div>
        )}

        {(phase === "done" && (orchestrateResult || ingestResult)) && (
          <CompletionCard
            stats={completionStats}
            actions={
              <>
                {(orchestrateResult?.transcript_id || ingestResult?.transcript_id) && (
                  <a href={`#/transcripts/${orchestrateResult?.transcript_id ?? ingestResult?.transcript_id}`} className="btn-primary">
                    View Transcript
                  </a>
                )}
                <button className="btn-secondary" onClick={reset}>
                  <RotateCcw size={16} /> Process Another
                </button>
              </>
            }
          />
        )}

        {(phase === "ingesting" || phase === "pipeline" || phase === "orchestrating" || phase === "checking-transcript") && (
          <div style={{ marginTop: 16 }}>
            <button className="btn-secondary" onClick={reset}>
              <RotateCcw size={16} /> Start Over
            </button>
          </div>
        )}

        {phase === "error" && (
          <div style={{ marginTop: 16 }}>
            <button className="btn-secondary" onClick={reset}>
              <RotateCcw size={16} /> Start Over
            </button>
          </div>
        )}
      </div>
    </AppShell>
  );
}
