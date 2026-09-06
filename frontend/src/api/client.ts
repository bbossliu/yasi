import type { EssayCreate, EssayDetail, EssayOut, ErrorItemOut, PromptOut } from './types'

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
