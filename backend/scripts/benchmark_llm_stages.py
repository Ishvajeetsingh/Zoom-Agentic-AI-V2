"""Representative LLM benchmark for each pipeline stage.

Measures realistic latency for:
  1. Concept Extraction
  2. MCQ Generation
  3. Educational Review
  4. Learning Outputs (flashcards + short questions)
  5. Meeting Insights (large transcript)

Uses representative payloads matching actual pipeline prompts.
"""

from __future__ import annotations

import json
import time
import statistics

import httpx

BASE_URL = "http://localhost:11434"
MODEL = "qwen3:8b"

REPRESENTATIVE_CHUNK = """Professor Zhang: Today we will discuss reinforcement learning, which is a type of machine learning where an agent learns to make decisions by performing actions in an environment to maximize cumulative reward. The key components are the agent, environment, state, action, and reward signal.

Professor Zhang: Unlike supervised learning, reinforcement learning does not require labeled data. Instead, the agent discovers which actions yield the most reward by trying them. This is similar to how humans learn through trial and error. The exploration-exploitation tradeoff is fundamental here.

Student Maria: How does the agent balance between trying new actions and using known good actions? Is there an optimal strategy?

Professor Zhang: Excellent question. The epsilon-greedy strategy is one common approach. With probability epsilon, the agent explores a random action, and with probability 1-epsilon, it exploits the best known action. Over time, epsilon typically decays so the agent exploits more as it learns.

Student James: What about the discount factor? How does that affect long-term versus short-term rewards?

Professor Zhang: The discount factor gamma determines how much the agent values future rewards compared to immediate ones. A gamma close to 1 makes the agent far-sighted, valuing long-term rewards. A gamma near 0 makes the agent myopic, focusing on immediate gains. The choice depends on the problem domain.

Student Maria: We discussed Q-learning last week. How does that fit into this framework?

Professor Zhang: Q-learning is a model-free off-policy algorithm. It learns the optimal action-value function by iteratively updating Q-values using the Bellman equation. The Q-value represents the expected cumulative reward of taking action a in state s and then following the optimal policy afterwards."""


def make_client() -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        timeout=httpx.Timeout(600.0),
    )


def call_generate(client, prompt, system, *, format_json=False, temperature=0.7, max_tokens=1800):
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if format_json:
        payload["format"] = "json"
    start = time.monotonic()
    r = client.post("/api/generate", json=payload)
    elapsed = time.monotonic() - start
    data = r.json()
    return {
        "elapsed": elapsed,
        "prompt_eval_count": data.get("prompt_eval_count", 0),
        "eval_count": data.get("eval_count", 0),
        "total_duration_ns": data.get("total_duration", 0),
    }


def benchmark_concept_extraction(client, runs=3):
    print("=" * 80)
    print("BENCHMARK 1: Concept Extraction (generate_json, temp=0.3, max_tokens=2048)")
    print("=" * 80)

    system = """You are an educational content analyst. Extract key educational concepts from the transcript chunk.

Categories: definition, process, comparison, advantage, disadvantage, application, decision, best_practice, cause_effect, principle.

For each concept return:
- "concept": concise label
- "category": one of the categories above
- "summary": 1-2 sentence educational summary (rephrase as educational content, NOT a copy of transcript wording)
- "bloom_level": highest Bloom level this concept supports — "understand", "apply", or "analyze"

Extract ALL distinct concepts. Return a JSON array:
[{"concept": "...", "category": "...", "summary": "...", "bloom_level": "..."}]"""

    prompt = (
        "Extract educational concepts from this transcript chunk.\n\n"
        f"--- TRANSCRIPT ---\n{REPRESENTATIVE_CHUNK}\n--- END ---\n\n"
        "Return a JSON array of concept objects."
    )

    times = []
    for i in range(runs):
        r = call_generate(client, prompt, system, format_json=True, temperature=0.3, max_tokens=2048)
        print(f"  Run {i + 1}: {r['elapsed']:.2f}s  (prompt_tokens={r['prompt_eval_count']}, completion_tokens={r['eval_count']})")
        times.append(r["elapsed"])
    return times


def benchmark_mcq_generation(client, runs=3):
    print()
    print("=" * 80)
    print("BENCHMARK 2: MCQ Generation (generate, temp=0.7, max_tokens=1800)")
    print("=" * 80)

    system = """You are a university-level assessment author creating rigorous, concept-driven MCQs from educational content extracted from meeting transcripts.

## QUESTION STYLES (use at least 2 per batch)
- "concept_understanding" — Understand a concept/definition/principle
- "application" — Apply a concept to a new situation
- "analysis" — Break down or identify components/relationships
- "comparison" — Compare approaches/solutions/ideas
- "cause_effect" — Why something happens or what results
- "scenario_based" — Given a realistic scenario, determine correct action/outcome
- "best_practice" — Which approach is recommended in a given situation
- "decision_making" — Evaluate options and select the best action

## BLOOM'S TAXONOMY
Avoid pure Remember (rote recall). Target: Understand, Apply, Analyze. At least 60% at Apply/Analyze level.

## ANTI-PATTERNS (STRICTLY AVOID)
Do NOT ask: "What did the speaker/person...", "According to the meeting/Name...", "Who said/mentioned...", "What happened during the meeting...", or paraphrase transcript sentences as questions.

## OUTPUT
4 options (A-D), exactly 1 correct, brief explanation, difficulty (easy|medium|hard), question_style and bloom_level.
Example object:
{
    "question_text": "Which mechanism explains why X occurs in scenario Y?",
    "question_type": "mcq",
    "question_style": "cause_effect",
    "bloom_level": "apply",
    "options": ["A: First plausible answer", "B: Second plausible answer", "C: Third plausible answer", "D: Fourth plausible answer"],
    "correct_answer": "A",
    "explanation": "This occurs because...",
    "difficulty": "medium"
}"""

    concepts_summary = (
        "- [DEFINITION] Reinforcement Learning: A type of ML where an agent learns through trial and error by maximizing cumulative reward\n"
        "- [PROCESS] Exploration-Exploitation Tradeoff: The agent must balance trying new actions vs using known good ones\n"
        "- [APPLICATION] Epsilon-Greedy Strategy: With probability epsilon explore randomly, otherwise exploit best known action\n"
        "- [PRINCIPLE] Discount Factor Gamma: Determines how much future rewards are valued vs immediate ones\n"
        "- [PROCESS] Q-Learning: Model-free off-policy algorithm using Bellman equation to learn optimal action-values"
    )

    prompt = (
        "Generate 4 MCQs from the educational concepts below.\n\n"
        f"--- TRANSCRIPT ---\n{REPRESENTATIVE_CHUNK}\n--- END ---\n\n"
        f"--- CONCEPTS ---\n{concepts_summary}\n--- END ---\n\n"
        "Return ONLY a JSON array of 4 question objects. No other text."
    )

    times = []
    for i in range(runs):
        r = call_generate(client, prompt, system, format_json=False, temperature=0.7, max_tokens=1800)
        print(f"  Run {i + 1}: {r['elapsed']:.2f}s  (prompt_tokens={r['prompt_eval_count']}, completion_tokens={r['eval_count']})")
        times.append(r["elapsed"])
    return times


def benchmark_educational_review(client, runs=3):
    print()
    print("=" * 80)
    print("BENCHMARK 3: Educational Review (generate, temp=0.3, max_tokens=1800)")
    print("=" * 80)

    system = """You are an experienced university professor reviewing an examination paper before it is given to students.

For EVERY MCQ, apply these SIX screening questions. If ANY answer is unsatisfactory, you MUST act:

1. Would this appear in a good university examination? → If NO: rewrite
2. Does this test conceptual understanding, not transcript memory? → If NO: rewrite
3. Can a student answer it just by reading the options? → If YES: rewrite_options (or rewrite if stem is also weak)
4. Are the distractors realistic misconceptions from partial understanding? → If NO: rewrite_options
5. Is the correct answer identifiable because it is longer/more detailed/obviously different? → If YES: rewrite_options
6. Would two partially-informed students genuinely disagree between at least two options? → If NO: rewrite_options

CRITICAL: Questions 3, 5, 6 check OPTION quality. Questions 1, 2, 4 check QUESTION quality.
If only options are weak → action "rewrite_options". If stem is also weak → action "rewrite".

## AUTOMATIC REWRITE RULES (no exceptions)
You MUST rewrite (action "rewrite") any question containing:
- "According to the transcript..." / "According to the discussion..." / "According to the speaker..."
- "What did the speaker..." / "Who said/mentioned/asked..." / "Which participant..."
- Meeting logistics, participant names, or transcript recall

You MUST rewrite options (action "rewrite_options") if:
- Any option is a single-word label
- The correct answer is noticeably longer or more detailed
- Distractors are absurd, obviously wrong, or trivially distinguishable

## ACTION TYPES
- "keep": Both stem and options are strong. You would include this in a university examination.
- "rewrite_options": Stem is good but options are weak
- "rewrite": Stem needs improvement (possibly options too).
- "reject": Cannot be salvaged educationally while remaining transcript-grounded.

## OUTPUT
Return a JSON array. Each element:
{"question_text": "...", "question_type": "mcq", "question_style": "...", "bloom_level": "...", "options": ["A: ...", "B: ...", "C: ...", "D: ..."], "correct_answer": "A", "explanation": "...", "difficulty": "easy|medium|hard", "action": "keep|rewrite_options|rewrite|reject", "original_question_text": "...", "review_reason": "..."}

Do NOT include any other text. Return ONLY the JSON array."""

    sample_mcqs = json.dumps([
        {
            "question_text": "Which strategy does an agent use to balance exploring new actions versus exploiting known good actions in reinforcement learning?",
            "question_type": "mcq",
            "question_style": "application",
            "bloom_level": "apply",
            "options": ["A: Epsilon-greedy strategy", "B: Gradient descent", "C: Backpropagation", "D: Cross-validation"],
            "correct_answer": "A",
            "explanation": "The epsilon-greedy strategy explicitly balances exploration and exploitation.",
            "difficulty": "medium",
        },
        {
            "question_text": "What is the primary effect of setting the discount factor gamma close to 1 in a reinforcement learning algorithm?",
            "question_type": "mcq",
            "question_style": "cause_effect",
            "bloom_level": "apply",
            "options": ["A: The agent becomes far-sighted, valuing long-term rewards more heavily", "B: The agent ignores future rewards entirely", "C: The agent learns faster by focusing only on immediate gains", "D: The discount factor has no effect on reward valuation"],
            "correct_answer": "A",
            "explanation": "A gamma close to 1 makes the agent value future rewards more, making it far-sighted.",
            "difficulty": "medium",
        },
        {
            "question_text": "Which component of Q-learning represents the expected cumulative reward of taking action a in state s?",
            "question_type": "mcq",
            "question_style": "concept_understanding",
            "bloom_level": "understand",
            "options": ["A: Q-value", "B: Reward signal", "C: Policy", "D: Environment"],
            "correct_answer": "A",
            "explanation": "The Q-value directly represents the expected cumulative reward for taking action a in state s.",
            "difficulty": "easy",
        },
        {
            "question_text": "In a scenario where an autonomous vehicle must decide between a known safe route and an unexplored potentially faster route, which reinforcement learning principle best explains the tradeoff it faces?",
            "question_type": "mcq",
            "question_style": "scenario_based",
            "bloom_level": "analyze",
            "options": ["A: The exploration-exploitation tradeoff, where the vehicle must weigh the value of discovered information against known rewards", "B: Supervised learning, where the vehicle should follow the labeled training data", "C: The discount factor, which only applies to financial reward calculations", "D: Q-learning, which cannot handle route selection problems"],
            "correct_answer": "A",
            "explanation": "The exploration-exploitation tradeoff captures the fundamental tension between trying new options and using known good ones.",
            "difficulty": "hard",
        },
    ], indent=2)

    concepts_summary = (
        "- [DEFINITION] Reinforcement Learning: A type of ML where an agent learns through trial and error by maximizing cumulative reward\n"
        "- [PROCESS] Exploration-Exploitation Tradeoff: The agent must balance trying new actions vs using known good ones\n"
        "- [APPLICATION] Epsilon-Greedy Strategy: With probability epsilon explore randomly, otherwise exploit best known action\n"
        "- [PRINCIPLE] Discount Factor Gamma: Determines how much future rewards are valued vs immediate ones\n"
        "- [PROCESS] Q-Learning: Model-free off-policy algorithm using Bellman equation to learn optimal action-values"
    )

    prompt = (
        "Review the following MCQs for BOTH question stem quality AND answer option quality.\n\n"
        f"--- TRANSCRIPT CONTEXT ---\n{REPRESENTATIVE_CHUNK[:1500]}\n--- END ---\n\n"
        f"--- CONCEPTS ---\n{concepts_summary}\n--- END ---\n\n"
        f"--- MCQs TO REVIEW ---\n{sample_mcqs}\n--- END ---\n\n"
        "Return ONLY a JSON array. Each element MUST include ALL fields: question_text, question_type, question_style, bloom_level, options (4 options), correct_answer, explanation, difficulty, action, original_question_text, review_reason. Even for 'keep' actions, return all fields."
    )

    times = []
    for i in range(runs):
        r = call_generate(client, prompt, system, format_json=False, temperature=0.3, max_tokens=1800)
        print(f"  Run {i + 1}: {r['elapsed']:.2f}s  (prompt_tokens={r['prompt_eval_count']}, completion_tokens={r['eval_count']})")
        times.append(r["elapsed"])
    return times


def benchmark_learning_outputs(client, runs=3):
    print()
    print("=" * 80)
    print("BENCHMARK 4: Learning Outputs (generate_json, temp=0.7, max_tokens=1800)")
    print("=" * 80)

    system = """You are an expert educational content creator. Given a transcript chunk from a meeting, generate flashcards and short-answer questions that help learners review the material.

Rules:
- Flashcards must have a clear "front" (question/prompt) and "back" (answer/explanation).
- Short-answer questions must have a concise question and a sample answer.
- Assign difficulty to short questions: easy, medium, or hard.
- Optionally assign a category to flashcards (e.g., "definition", "process", "decision").
- Do NOT invent information not present in the transcript.
- Return a JSON object with two keys.

JSON schema:
{
  "flashcards": [
    {"front": "string", "back": "string", "category": "string or null"}
  ],
  "short_questions": [
    {"question_text": "string", "sample_answer": "string", "difficulty": "easy|medium|hard"}
  ]
}"""

    prompt = (
        "Generate 5 flashcards and 3 short-answer questions "
        "from the following meeting transcript chunk.\n\n"
        f"--- TRANSCRIPT CHUNK ---\n{REPRESENTATIVE_CHUNK}\n--- END CHUNK ---\n\n"
        "Return a JSON object with 'flashcards' and 'short_questions' arrays."
    )

    times = []
    for i in range(runs):
        r = call_generate(client, prompt, system, format_json=True, temperature=0.7, max_tokens=1800)
        print(f"  Run {i + 1}: {r['elapsed']:.2f}s  (prompt_tokens={r['prompt_eval_count']}, completion_tokens={r['eval_count']})")
        times.append(r["elapsed"])
    return times


def benchmark_meeting_insights(client, runs=2, scale=3):
    print()
    print("=" * 80)
    print(f"BENCHMARK 5: Meeting Insights (generate_json, temp=0.5, max_tokens=2000, {scale}x transcript)")
    print("=" * 80)

    system = """You are an expert meeting analyst. Given the full transcript of a meeting, produce a comprehensive analysis with all of the following sections.

Rules:
- The summary should capture the main topics discussed, decisions made, and outcomes. Write 3-5 paragraphs.
- Key concepts should be the most important ideas, terms, or topics discussed. Order by importance (1 = most important). Provide 5-10 concepts.
- Action items should be concrete tasks, follow-ups, or commitments mentioned. Include assignee if mentioned, priority (low/medium/high), and due date if mentioned.
- Key takeaways should be the most important points or conclusions from the meeting that participants should remember.
- Learning outcomes should be what knowledge or skills were gained or reinforced by participants.
- Topics should list the main subjects or themes discussed in the meeting with a brief note on relevance.
- Decisions should capture any decisions that were made during the meeting, who decided, and the rationale.
- Recommendations should be suggestions or advice emerging from the discussion with priority level.
- Do NOT invent information not present in the transcript.
- Return a JSON object with eight keys.

JSON schema:
{
  "summary": "string (3-5 paragraphs)",
  "key_concepts": [{"concept": "string", "description": "string", "importance_order": 1}],
  "action_items": [{"item_text": "string", "assignee": "string or null", "priority": "low|medium|high or null", "due_date": "string or null"}],
  "key_takeaways": [{"takeaway": "string", "context": "string or null"}],
  "learning_outcomes": [{"outcome": "string", "category": "string or null"}],
  "topics": [{"topic": "string", "relevance": "string or null"}],
  "decisions": [{"decision": "string", "rationale": "string or null", "decided_by": "string or null"}],
  "recommendations": [{"recommendation": "string", "priority": "low|medium|high or null", "target_audience": "string or null"}]
}"""

    large_transcript = "\n\n".join([REPRESENTATIVE_CHUNK] * scale)
    print(f"  Transcript size: {len(large_transcript)} chars, {len(large_transcript.split())} words")

    prompt = (
        "Analyze the following meeting transcript and produce a summary, "
        "key concepts, action items, key takeaways, learning outcomes, "
        "topics, decisions, and recommendations.\n\n"
        f"--- FULL MEETING TRANSCRIPT ---\n{large_transcript}\n--- END TRANSCRIPT ---\n\n"
        "Return a JSON object with 'summary', 'key_concepts', 'action_items', "
        "'key_takeaways', 'learning_outcomes', 'topics', 'decisions', and 'recommendations'."
    )

    times = []
    for i in range(runs):
        r = call_generate(client, prompt, system, format_json=True, temperature=0.5, max_tokens=2000)
        print(f"  Run {i + 1}: {r['elapsed']:.2f}s  (prompt_tokens={r['prompt_eval_count']}, completion_tokens={r['eval_count']})")
        times.append(r["elapsed"])
    return times


def main():
    print("LLM Pipeline Stage Benchmark")
    print(f"Model: {MODEL}")
    print(f"Ollama: {BASE_URL}")
    print()

    client = make_client()

    # Verify connectivity
    try:
        r = client.get("/")
        r.raise_for_status()
        print(f"Ollama connection OK (status {r.status_code})")
    except Exception as exc:
        print(f"FATAL: Cannot connect to Ollama: {exc}")
        return

    all_results = {}

    all_results["concept_extraction"] = benchmark_concept_extraction(client, runs=3)
    all_results["mcq_generation"] = benchmark_mcq_generation(client, runs=2)
    all_results["educational_review"] = benchmark_educational_review(client, runs=2)
    all_results["learning_outputs"] = benchmark_learning_outputs(client, runs=2)
    all_results["meeting_insights_3x"] = benchmark_meeting_insights(client, runs=1, scale=3)

    # NOTE: Full-transcript (49x) insights benchmark skipped — takes too long.
    # Extrapolate from 3x result using tokens/s throughput.

    client.close()

    print()
    print("=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)

    for stage, times in all_results.items():
        avg = statistics.mean(times)
        mn = min(times)
        mx = max(times)
        std = statistics.stdev(times) if len(times) >= 2 else 0
        print(f"  {stage:30s}: avg={avg:7.2f}s  min={mn:7.2f}s  max={mx:7.2f}s  std={std:5.2f}  runs={len(times)}")

    print()
    print("NOTE: All stages are LLM-bound (GPU-inference bottleneck).")
    print("CPU-bound or I/O-bound stages (download, parse, clean, chunk,")
    print("validate, dedup, classify, persist, export) are negligible.")
    print()

    # Save raw data
    output_path = "benchmark_results.json"
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"Raw data saved to {output_path}")


if __name__ == "__main__":
    main()
