import type {
  DictationResultOut,
  EssayCreate,
  EssayDetail,
  EssayOut,
  ErrorItemOut,
  ForecastOut,
  MatDetailOut,
  MatListOut,
  PromptOut,
  ReviewCardOut,
  SessionOut,
  SessionSummary,
  ShadowingResult,
  SpeakingCardOut,
  TopicOut,
  TurnDetail,
  WordOut,
} from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init)
  if (!resp.ok) {
    const body = await resp.text()
    throw new Error(`API ${resp.status}: ${body}`)
  }
  return resp.json() as Promise<T>
}

export function listPrompts(): Promise<PromptOut[]> {
  return request('/prompts')
}

export function getSample(): Promise<{ title: string; prompt_text: string; content: string }> {
  return request('/sample')
}

export function submitEssay(body: EssayCreate): Promise<EssayOut> {
  return request('/essays', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function listEssays(): Promise<EssayOut[]> {
  return request('/essays')
}

export function getEssay(id: number): Promise<EssayDetail> {
  return request(`/essays/${id}`)
}

export function listErrors(): Promise<ErrorItemOut[]> {
  return request('/errors')
}

export function listSpeakingCards(part: number): Promise<SpeakingCardOut[]> {
  return request(`/speaking/cards?part=${part}`)
}

export function createSpeakingSession(cardId: number): Promise<SessionOut> {
  return request('/speaking/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ card_id: cardId }),
  })
}

export function submitSpeakingTurn(sessionId: number, audio: Blob): Promise<{ practice_id: number }> {
  const form = new FormData()
  form.append('session_id', String(sessionId))
  form.append('audio', audio, 'answer.wav')
  return request('/speaking/turns', { method: 'POST', body: form })
}

export function getSpeakingTurn(practiceId: number): Promise<TurnDetail> {
  return request(`/speaking/turns/${practiceId}`)
}

export function finishSpeakingSession(id: number): Promise<SessionSummary> {
  return request(`/speaking/sessions/${id}/finish`, { method: 'POST' })
}

export function listVocabTopics(): Promise<TopicOut[]> {
  return request('/vocab/topics')
}

export function listVocabWords(topic: string): Promise<WordOut[]> {
  return request(`/vocab/words?topic=${encodeURIComponent(topic)}`)
}

export function getReviewQueue(limit = 20): Promise<{ cards: ReviewCardOut[]; due_total: number }> {
  return request(`/vocab/review/queue?limit=${limit}`)
}

export function submitReview(wordId: number, quality: 1 | 3 | 5): Promise<{ next_due_at: string; interval_days: number }> {
  return request(`/vocab/review/${wordId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quality }),
  })
}

export function getVocabForecast(): Promise<ForecastOut[]> {
  return request('/vocab/forecast')
}

export function listListeningMaterials(): Promise<MatListOut[]> {
  return request('/listening/materials')
}

export function getListeningMaterial(id: number): Promise<MatDetailOut> {
  return request(`/listening/materials/${id}`)
}

export function requestListeningAudio(id: number): Promise<{ status: string; ready_count: number; total: number }> {
  return request(`/listening/materials/${id}/audio`, { method: 'POST' })
}

export function submitDictation(materialId: number, answers: string[]): Promise<DictationResultOut> {
  return request('/listening/dictation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ material_id: materialId, answers }),
  })
}

export function submitShadowing(materialId: number, audio: Blob): Promise<ShadowingResult> {
  const form = new FormData()
  form.append('material_id', String(materialId))
  form.append('audio', audio, 'shadow.wav')
  return request('/listening/shadowing', { method: 'POST', body: form })
}

export function submitAttribution(practiceId: number, sentenceIndex: number, reason: string): Promise<{ id: number }> {
  return request('/listening/attribution', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ practice_id: practiceId, sentence_index: sentenceIndex, reason }),
  })
}
