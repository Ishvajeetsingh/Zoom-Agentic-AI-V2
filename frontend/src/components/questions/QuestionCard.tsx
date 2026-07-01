import type { Question } from "../../types/api";

interface QuestionCardProps {
  question: Question;
  showAnswer?: boolean;
  index?: number;
}

const DIFFICULTY_LABELS: Record<string, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

const TYPE_LABELS: Record<string, string> = {
  mcq: "Multiple Choice",
  true_false: "True / False",
  short_answer: "Short Answer",
  fill_blank: "Fill in the Blank",
};

const CATEGORY_LABELS: Record<string, string> = {
  quiz: "Quiz",
  concept: "Concept",
  application: "Application",
  meeting: "Meeting",
};

const BLOOM_LABELS: Record<string, string> = {
  remember: "Remember",
  understand: "Understand",
  apply: "Apply",
  analyze: "Analyze",
};

export function QuestionCard({ question, showAnswer = false, index }: QuestionCardProps) {
  return (
    <article className="question-card">
      <div className="question-card-header">
        {index != null && <span className="question-number">Q{index + 1}</span>}
        <span className={`badge badge-difficulty-${question.difficulty}`}>
          {DIFFICULTY_LABELS[question.difficulty] ?? question.difficulty}
        </span>
        <span className="badge badge-type">{TYPE_LABELS[question.question_type] ?? question.question_type}</span>
        {question.category && (
          <span className={`badge badge-category badge-category-${question.category}`}>
            {CATEGORY_LABELS[question.category] ?? question.category}
          </span>
        )}
        {question.bloom_taxonomy && (
          <span className={`badge badge-bloom badge-bloom-${question.bloom_taxonomy}`}>
            {BLOOM_LABELS[question.bloom_taxonomy] ?? question.bloom_taxonomy}
          </span>
        )}
        {question.educational_score != null && (
          <span className="badge badge-score">Edu: {question.educational_score.toFixed(1)}</span>
        )}
        {question.is_duplicate && <span className="badge badge-duplicate">Duplicate</span>}
      </div>

      <p className="question-text">{question.question_text}</p>

      {question.question_type === "mcq" && Array.isArray(question.options) && (
        <ul className="question-options">
          {question.options.map((opt, i) => (
            <li
              key={i}
              className={`question-option ${showAnswer && question.correct_answer === String.fromCharCode(65 + i) ? "correct" : ""}`}
            >
              <span className="option-letter">{String.fromCharCode(65 + i)}</span>
              <span className="option-text">{opt}</span>
            </li>
          ))}
        </ul>
      )}

      {showAnswer && (
        <div className="question-answer-section">
          <p className="question-correct-answer">
            Correct Answer: <strong>{question.correct_answer}</strong>
          </p>
          <p className="question-explanation">{question.explanation}</p>
        </div>
      )}
    </article>
  );
}
