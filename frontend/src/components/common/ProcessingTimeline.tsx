type StepStatus = "completed" | "completed_with_warnings" | "running" | "failed" | "waiting";

export interface TimelineStep {
  key: string;
  label: string;
  description: string;
  status: StepStatus;
  warnings?: string[];
}

interface ProcessingTimelineProps {
  steps: TimelineStep[];
}

const STATUS_ICONS: Record<StepStatus, string> = {
  completed: "\u2713",
  completed_with_warnings: "\u26A0",
  running: "\u25CF",
  failed: "\u2717",
  waiting: "",
};

export function ProcessingTimeline({ steps }: ProcessingTimelineProps) {
  return (
    <div className="process-timeline-vertical">
      {steps.map((step, i) => (
        <div key={step.key} className="process-timeline-step">
          <div className="process-timeline-indicator">
            <div className={`process-timeline-dot ${step.status}`}>
              {STATUS_ICONS[step.status]}
            </div>
            {i < steps.length - 1 && (
              <div
                className={`process-timeline-line ${
                  step.status === "completed" || step.status === "completed_with_warnings"
                    ? "completed"
                    : step.status === "failed"
                    ? "failed"
                    : ""
                }`}
              />
            )}
          </div>
          <div className="process-timeline-content">
            <p className={`process-timeline-title ${step.status}`}>{step.label}</p>
            <p className={`process-timeline-desc ${step.status}`}>{step.description}</p>
            {step.warnings && step.warnings.length > 0 && (
              <div className="process-timeline-warnings">
                {step.warnings.map((w, wi) => (
                  <p key={wi} className="process-timeline-warning">{w}</p>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
