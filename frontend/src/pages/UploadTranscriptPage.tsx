import { useCallback, useState } from "react";
import { Upload, FileText, RotateCcw } from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { ProcessingTimeline, type TimelineStep } from "../components/common/ProcessingTimeline";
import { CompletionCard } from "../components/common/CompletionCard";
import { uploadTranscript, runPipeline } from "../api/transcripts";
import type { TranscriptUploadResponse, PipelineResponse } from "../types/api";

type Phase = "form" | "uploading" | "pipeline" | "done" | "error";

const PIPELINE_STEPS: TimelineStep[] = [
  { key: "parse", label: "Parse Transcript", description: "Extract speaker segments and timestamps", status: "waiting" },
  { key: "clean", label: "Clean Transcript", description: "Normalize speakers, remove fillers and artifacts", status: "waiting" },
  { key: "chunk", label: "Semantic Chunking", description: "Split transcript into topic-coherent chunks", status: "waiting" },
  { key: "generate", label: "Generate Questions", description: "Create quiz questions using LLM", status: "waiting" },
  { key: "generate_learning_outputs", label: "Generate Learning Outputs", description: "Extract key concepts and learning objectives", status: "waiting" },
  { key: "synthesize", label: "Synthesize Insights", description: "Prouce insights and summary from processed data", status: "waiting" },
];

function setStep(steps: TimelineStep[], key: string, status: TimelineStep["status"], desc?: string): TimelineStep[] {
  return steps.map((s) =>
    s.key === key ? { ...s, status, description: desc ?? s.description } : s
  );
}



function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadTranscriptPage() {
  const [file, setFile] = useState<File | null>(null);
  const [topic, setTopic] = useState("");
  const [dragging, setDragging] = useState(false);
  const [phase, setPhase] = useState<Phase>("form");
  const [pipelineSteps, setPipelineSteps] = useState<TimelineStep[]>(PIPELINE_STEPS);
  const [uploadResult, setUploadResult] = useState<TranscriptUploadResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [completionStats, setCompletionStats] = useState<{ label: string; value: string }[]>([]);

  const reset = () => {
    setFile(null);
    setTopic("");
    setPhase("form");
    setPipelineSteps(PIPELINE_STEPS.map((s) => ({ ...s })));
    setUploadResult(null);
    setErrorMsg(null);
    setCompletionStats([]);
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) setFile(droppedFile);
  }, []);

  const handleSubmit = async () => {
    if (!file) return;
    setPhase("uploading");
    setErrorMsg(null);

    try {
      const result = await uploadTranscript(file, topic || undefined);
      setUploadResult(result);
      setPhase("pipeline");
      runPipelineSteps(result.transcript_id);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setPhase("error");
      setErrorMsg(msg);
    }
  };

  const runPipelineSteps = async (transcriptId: string) => {
    const stepKeys = ["parse", "clean", "chunk", "generate", "generate_learning_outputs", "synthesize"];
    

    let steps = PIPELINE_STEPS.map((s) => ({ ...s }));
    steps = PIPELINE_STEPS.map(
  (step, index) => ({
    ...step,
    status:
      index === 0
        ? ("running" as const)
        : ("waiting" as const),
  })
);

setPipelineSteps([
  ...steps,
]);

    try {
      const result: PipelineResponse = await runPipeline(transcriptId);

      

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
          { label: "Transcript ID", value: transcriptId },
          { label: "Meeting ID", value: uploadResult?.meeting_id ?? "" },
          { label: "File", value: uploadResult?.transcript_filename ?? file?.name ?? "" },
          { label: "Size", value: uploadResult?.file_size_bytes ? formatFileSize(uploadResult.file_size_bytes) : (file ? formatFileSize(file.size) : "N/A") },
        ]);
      }
    } catch (err) {
      
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

  return (
    <AppShell>
      <div className="process-page">
        <div className="page-header">
          <h1>Upload Transcript</h1>
          <p className="page-header-subtitle">
            Upload a transcript file (VTT, JSON, or TXT) and run the processing pipeline
          </p>
        </div>

        {phase === "form" && (
          <div className="process-form">
            <div
              className={`upload-zone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => { if (!file) document.getElementById("transcript-file-input")?.click(); }}
            >
              {file ? (
                <div className="upload-file-info">
                  <FileText size={32} style={{ color: "var(--c-success)", flexShrink: 0 }} />
                  <div>
                    <div className="upload-file-name">{file.name}</div>
                    <div className="upload-file-size">{formatFileSize(file.size)}</div>
                  </div>
                </div>
              ) : (
                <>
                  <Upload className="upload-zone-icon" size={48} />
                  <p className="upload-zone-title">Drop transcript file here, or click to browse</p>
                  <p className="upload-zone-subtitle">VTT, JSON, SRT, or TXT format</p>
                  <p className="upload-zone-formats">Supported: .vtt, .json, .srt, .txt &middot; Max 50 MB</p>
                </>
              )}
              <input
                id="transcript-file-input"
                type="file"
                accept=".vtt,.json,.srt,.txt"
                style={{ display: "none" }}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); }}
              />
            </div>

            {file && (
              <button
                className="btn-secondary"
                style={{ alignSelf: "flex-start" }}
                onClick={() => setFile(null)}
              >
                Remove file
              </button>
            )}

            <div className="form-group">
              <label className="form-label">Meeting Topic (optional)</label>
              <input
                className="form-input"
                type="text"
                placeholder="e.g. Weekly Team Standup"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />
              <p className="form-hint">A descriptive name for the meeting this transcript belongs to.</p>
            </div>

            <button className="btn-primary" onClick={handleSubmit} disabled={!file}>
              <Upload size={18} /> Upload &amp; Process
            </button>
          </div>
        )}

        {(phase === "uploading" || phase === "pipeline" || phase === "error" || phase === "done") && (
          <>
            <div className="panel" style={{ marginBottom: 24 }}>
              <div className="panel-header">
                <h2 className="panel-title">
                  {phase === "uploading" ? "Uploading..." : "Upload"}
                </h2>
              </div>
              <div style={{ padding: "8px 0", fontSize: "0.875rem", color: "var(--c-text)" }}>
                {phase === "uploading" ? "Uploading file to server..." : `Uploaded: ${uploadResult?.transcript_filename ?? file?.name}`}
              </div>
            </div>

            {uploadResult && (
              <div className="panel" style={{ marginBottom: 24 }}>
                <div className="panel-header">
                  <h2 className="panel-title">Processing Pipeline</h2>
                </div>
                <ProcessingTimeline steps={pipelineSteps} />
              </div>
            )}

            {phase === "error" && errorMsg && (
              <div className="process-error-box">
                <span>&#9888;</span>
                <p>{errorMsg}</p>
              </div>
            )}

            {phase === "done" && (
              <CompletionCard
                stats={completionStats}
                actions={
                  <>
                    <a href={`#/transcripts/${uploadResult?.transcript_id}`} className="btn-primary">
                      View Transcript
                    </a>
                    <button className="btn-secondary" onClick={reset}>
                      <RotateCcw size={16} /> Upload Another
                    </button>
                  </>
                }
              />
            )}

            {phase === "error" && (
              <div style={{ marginTop: 16 }}>
                <button className="btn-secondary" onClick={reset}>
                  <RotateCcw size={16} /> Start Over
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
