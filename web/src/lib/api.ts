export type Next = { field: string; question: string } | null

export type Receipt = { file: string; confidence: number; path: 'ocr' | 'vision'; total: number | null; date: string | null }

export type UploadResponse = {
  session: string
  summary: { transactions: number; receipts: Receipt[]; rules: number; llm_merchants: number; documents?: number; inferred?: Inferred[] }
  next: Next
}

export type Inferred = { field: string; value: string | number; source: string }

export type AnswerResponse = { ok: boolean; clarify?: string; unsupported?: boolean; next: Next }

export type Plan = {
  required: number
  method: 'prior_year_safe_harbor' | '90pct_current_year' | 'none_required'
  current_90: number
  prior_safe_harbor: number
  paid: number
  next_due: string | null
  next_amount: number
  april_balance: number
}

export type SourceRow = { key: string; source: string; by: string; amount: number; description: string; merchant?: string }

export type SourceGroup = 'gross_income' | 'deductible_expenses' | 'paid_fed' | 'paid_ny' | 'review'

export type Results = {
  net_profit: number
  annual: {
    self_employment_tax: number
    adjusted_gross_income: number
    qualified_business_income_deduction: number
    taxable_income: number
    income_tax: number
    ny_income_tax: number
    nyc_income_tax: number
  }
  federal_total: number
  ny_total: number
  federal: Plan
  ny: Plan
  notes: string[]
  inputs: { gross_income: number; deductible_expenses: number; [k: string]: unknown }
  expense_by_category: Record<string, number>
  sources: Record<SourceGroup, SourceRow[]>
  pay_links: { federal: string; ny: string }
  computed_at: string
}

export type HistoryRow = {
  value: unknown
  source: string
  by: string
  reason: string | null
  at: string
  superseded_at: string | null
  current: boolean
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 300) || r.statusText}`)
  return r.json()
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  upload(file: File) {
    const fd = new FormData()
    fd.append('file', file)
    return req<UploadResponse>('/api/upload', { method: 'POST', body: fd })
  },
  answer: (session: string, field: string, text: string) =>
    req<AnswerResponse>('/api/answer', json({ session, field, text })),
  results: (session: string) => req<Results>(`/api/results/${encodeURIComponent(session)}`),
  correct: (b: { session: string; key: string; category: string; business_pct: number; reason: string; same_merchant?: boolean }) =>
    req<{ history: HistoryRow[] }>('/api/correct', json({ ...b, schedule_c_category: null })),
  review: (session: string) => req<Review>(`/api/review/${encodeURIComponent(session)}`),
  chat: (session: string, text: string) => req<AgentReply>('/api/chat', json({ session, text })),
  resume: (session: string, approve: boolean) => req<AgentReply>('/api/chat/resume', json({ session, approve })),
}

export type Review = {
  profile: { field: string; value: string | number; source: string; by: string }[]
  guessed: SourceRow[]
  gross_income: number
  deductible_expenses: number
  transactions: number
}

export type AgentReply = { reply?: string; pending?: { tool: string; args: Record<string, unknown> }[] }

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
export const money = (n: number | null | undefined) => (n == null ? '—' : usd.format(n))
