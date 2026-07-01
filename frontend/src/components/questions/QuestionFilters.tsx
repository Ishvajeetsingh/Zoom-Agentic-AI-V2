import { Filter } from "lucide-react";

export interface QuestionFilterValues {
  difficulty: string;
  question_type: string;
  category: string;
  bloom: string;
  top_n: number | "";
  order: "asc" | "desc";
}

interface QuestionFiltersProps {
  filters: QuestionFilterValues;
  onChange: (filters: QuestionFilterValues) => void;
  hideTypeFilter?: boolean;
}

export function QuestionFilters({ filters, onChange, hideTypeFilter }: QuestionFiltersProps) {
  const handleDifficultyChange = (e: { target: { value: string } }) => {
    onChange({ ...filters, difficulty: e.target.value });
  };

  const handleTypeChange = (e: { target: { value: string } }) => {
    onChange({ ...filters, question_type: e.target.value });
  };

  const handleCategoryChange = (e: { target: { value: string } }) => {
    onChange({ ...filters, category: e.target.value });
  };

  const handleBloomChange = (e: { target: { value: string } }) => {
    onChange({ ...filters, bloom: e.target.value });
  };

  const handleTopNChange = (e: { target: { value: string } }) => {
    const val = e.target.value === "" ? "" : parseInt(e.target.value, 10);
    onChange({ ...filters, top_n: val });
  };

  const handleOrderChange = (e: { target: { value: string } }) => {
    onChange({ ...filters, order: e.target.value as "asc" | "desc" });
  };

  return (
    <section className="panel question-filters">
      <div className="panel-header" style={{ marginBottom: 12 }}>
        <h2 className="panel-title" style={{ fontSize: "0.9rem", display: "flex", alignItems: "center", gap: 6 }}>
          <Filter size={14} />
          Filters
        </h2>
      </div>
      <div className="filter-row">
        <label className="filter-label">
          Category
          <select value={filters.category} onChange={handleCategoryChange} className="filter-select">
            <option value="">All</option>
            <option value="quiz">Quiz Questions</option>
            <option value="concept">Concept Understanding</option>
            <option value="application">Application Based</option>
            <option value="meeting">Meeting Questions</option>
          </select>
        </label>

        <label className="filter-label">
          Difficulty
          <select value={filters.difficulty} onChange={handleDifficultyChange} className="filter-select">
            <option value="">All</option>
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
          </select>
        </label>

        <label className="filter-label">
          Bloom Taxonomy
          <select value={filters.bloom} onChange={handleBloomChange} className="filter-select">
            <option value="">All</option>
            <option value="remember">Remember</option>
            <option value="understand">Understand</option>
            <option value="apply">Apply</option>
            <option value="analyze">Analyze</option>
          </select>
        </label>

        {!hideTypeFilter && (
          <label className="filter-label">
            Type
            <select value={filters.question_type} onChange={handleTypeChange} className="filter-select">
              <option value="">All</option>
              <option value="mcq">Multiple Choice</option>
              <option value="true_false">True / False</option>
              <option value="short_answer">Short Answer</option>
            </select>
          </label>
        )}

        <label className="filter-label">
          Top N
          <select value={filters.top_n === "" ? "" : String(filters.top_n)} onChange={handleTopNChange} className="filter-select">
            <option value="">All</option>
            <option value="10">Top 10</option>
            <option value="20">Top 20</option>
            <option value="50">Top 50</option>
          </select>
        </label>

        <label className="filter-label">
          Order
          <select value={filters.order} onChange={handleOrderChange} className="filter-select">
            <option value="asc">Oldest first</option>
            <option value="desc">Newest first</option>
          </select>
        </label>
      </div>
    </section>
  );
}
