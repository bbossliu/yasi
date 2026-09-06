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
