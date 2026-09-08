export interface PromptOut {
  title: string
  text: string
}

export interface EssayCreate {
  prompt_title: string
  prompt_text: string
  content: string
  duration_sec: number
}

export interface EssayOut {
  id: number
  module: string
  status: 'pending' | 'done' | 'needs_review'
  total_band: number | null
  prompt_title: string
  word_count: number
  duration_sec: number
  created_at: string
}

export interface BandScores {
  task_response: number
  coherence: number
  lexical: number
  grammar: number
  overall: number
}

export interface Annotation {
  sentence_index: number
  original: string
  issue: string
  suggestion: string
  error_type: string | null
}

export interface FeedbackOut {
  bands: BandScores
  annotations: Annotation[]
  rewrite: string
  is_mock: boolean
}

export interface ErrorItemOut {
  id: number
  error_type: string
  context: string
  created_at: string
}

export interface EssayDetail extends EssayOut {
  prompt_text: string
  content: string
  feedback: FeedbackOut | null
  errors: ErrorItemOut[]
}

export interface SpeakingCardOut {
  id: number
  part: number
  topic: string
  season: string
  payload: { questions?: string[]; cues?: string[] }
}

export interface SessionOut {
  id: number
  part: number
  topic: string
  status: 'active' | 'done'
  question: string
  tts_url: string | null
}

export interface SpeakingBands {
  fluency: number
  lexical: number
  grammar: number
  pronunciation: number
  overall: number
}

export interface SpeakingFeedback {
  bands: SpeakingBands
  annotations: Annotation[]
  rewrite: string
  is_mock: boolean
}

export interface TurnDetail {
  practice_id: number
  status: 'pending' | 'done' | 'needs_review'
  transcript: string | null
  feedback: SpeakingFeedback | null
  next_question: string | null
  next_tts_url: string | null
  session_done: boolean
}

export interface TurnSummaryItem {
  question: string
  transcript: string
  total_band: number | null
}

export interface SessionSummary {
  session_id: number
  avg_band: number | null
  turns: TurnSummaryItem[]
}

export interface TopicOut {
  topic: string
  word_count: number
  mastered_count: number
  due_count: number
}

export interface WordOut {
  id: number
  text: string
  pos: string
  meaning: string
  paraphrase_chain: string[]
  example_sentence: string
  due_at: string | null
  reps: number
}

export interface ReviewCardOut {
  word_id: number
  text: string
  pos: string
  meaning: string
  paraphrase_chain: string[]
  example_sentence: string
  is_new: boolean
}

export interface ForecastOut {
  date: string
  count: number
}

export interface MatListOut {
  id: number
  title: string
  section: number
  sentence_count: number
  ready_count: number
}

export interface MatDetailOut {
  id: number
  title: string
  section: number
  sentences: string[]
  sentences_zh: string[]
  ready_count: number
}

export interface DiffToken {
  type: 'ok' | 'missing' | 'wrong' | 'extra'
  ref: string
  hyp: string
}

export interface DictationResultOut {
  practice_id: number
  accuracy: number
  per_sentence: { diff: { tokens: DiffToken[]; correct: boolean }; correct: boolean }[]
}

export interface ShadowingResult {
  transcript: string
  diff: { tokens: DiffToken[]; correct: boolean }
  is_mock: boolean
}

export interface SkillNodeOut {
  id: number
  code: string
  title: string
  parent_id: number | null
  status: 'unseen' | 'learned' | 'verified'
  can_verify: boolean
  sort_order: number
}

export interface ModuleTree {
  module: string
  nodes: SkillNodeOut[]
}

export interface ClearanceOut {
  module: string
  cleared: boolean
  detail: string
  mastery_rate: number
}

export interface ExamOut {
  id: number
  scores: Record<string, number>
  predicted_band: number | null
  report: { top_errors: { type: string; count: number }[]; weak_nodes: { code: string; title: string }[] } | string
  practice_ids: number[]
  created_at: string
}
