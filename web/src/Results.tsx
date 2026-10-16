import { Fragment, useCallback, useEffect, useState } from 'react'
import { CalendarDays, ExternalLink, Loader2 } from 'lucide-react'
import { api, money, type AgentReply, type HistoryRow, type Plan, type Results, type SourceGroup, type SourceRow } from '@/lib/api'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'

const GROUP_TITLES: Record<SourceGroup, string> = {
  gross_income: 'Gross income',
  deductible_expenses: 'Deductible expenses',
  paid_fed: 'Federal estimated payments made',
  paid_ny: 'NY estimated payments made',
  review: 'Guessed labels to review',
}

export function ResultsView({ session }: { session: string }) {
  const [res, setRes] = useState<Results | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [open, setOpen] = useState<SourceGroup | null>(null)

  const load = useCallback(() => api.results(session).then(setRes, (e) => setErr(String(e))), [session])
  useEffect(() => void load(), [load])

  if (err) return <p className="text-sm text-destructive">{err}</p>
  if (!res) return <p className="flex items-center gap-2 text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Computing your estimates…</p>

  const a = res.annual
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        <PlanCard title="Federal (1040-ES)" plan={res.federal} link={res.pay_links.federal} linkLabel="Pay on IRS Direct Pay" onPaid={() => setOpen('paid_fed')} />
        <PlanCard title="New York State + NYC (IT-2105)" plan={res.ny} link={res.pay_links.ny} linkLabel="Pay on NYS Online Services" onPaid={() => setOpen('paid_ny')} />
      </div>

      {res.sources.review.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/60 shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">We labeled {res.sources.review.length} transactions on a best guess</CardTitle>
            <CardDescription>Only you know these for sure (e.g. was that dinner with a client?). Fix any that are wrong, or tell the assistant below.</CardDescription>
            <CardAction>
              <Button variant="outline" size="sm" onClick={() => setOpen('review')}>Review</Button>
            </CardAction>
          </CardHeader>
        </Card>
      )}

      <AgentChat session={session} onChanged={load} />

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>How we got here</CardTitle>
          <CardDescription>Projected for the full year. Click a highlighted row to see its source rows.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <Line label="Gross income" value={res.inputs.gross_income} onClick={() => setOpen('gross_income')} />
          <Line label="Deductible expenses" value={-res.inputs.deductible_expenses} onClick={() => setOpen('deductible_expenses')} />
          {Object.entries(res.expense_by_category).map(([k, v]) => (
            <Line key={k} label={k} value={-v} indent />
          ))}
          <Separator className="my-2" />
          <Line label="Net profit" value={res.net_profit} strong />
          <Line label="Self-employment tax" value={a.self_employment_tax} />
          <Line label="Adjusted gross income" value={a.adjusted_gross_income} />
          <Line label="QBI deduction" value={-a.qualified_business_income_deduction} />
          <Line label="Taxable income" value={a.taxable_income} />
          <Separator className="my-2" />
          <Line label="Federal income tax" value={a.income_tax} />
          <Line label="Federal total (incl. SE tax)" value={res.federal_total} strong />
          <Line label="NY State income tax" value={a.ny_income_tax} />
          <Line label="NYC income tax" value={a.nyc_income_tax} />
          <Line label="NY total" value={res.ny_total} strong />
        </CardContent>
      </Card>

      {res.notes.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Notes</CardTitle></CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">{res.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
          </CardContent>
        </Card>
      )}
      <p className="text-xs text-muted-foreground">Computed {new Date(res.computed_at).toLocaleString()}. Estimates only — not tax advice.</p>

      <Sheet open={open !== null} onOpenChange={(o) => !o && setOpen(null)}>
        <SheetContent className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-2xl">
          {open && (
            <>
              <SheetHeader>
                <SheetTitle>{GROUP_TITLES[open]}</SheetTitle>
                <SheetDescription>
                  {open === 'deductible_expenses' || open === 'review' ? 'Facts supersede, never overwrite (SurrealDB). Fix a row to record a correction.' : 'Every number traces back to a source row.'}
                </SheetDescription>
              </SheetHeader>
              <SourceTable session={session} rows={res.sources[open] ?? []} fixable={open === 'deductible_expenses' || open === 'review'} onChanged={load} />
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}

const fmtDate = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })

function methodText(p: Plan) {
  if (p.method === 'none_required') return 'Your projected balance is below the threshold, so no estimated payments are required.'
  if (p.method === 'prior_year_safe_harbor')
    return `Safe harbor: last year's tax (${money(p.prior_safe_harbor)}) is less than 90% of this year's (${money(p.current_90)}), so you only need ${money(p.required)}.`
  return `90% of this year's projected tax (${money(p.current_90)}) is less than last year's safe harbor (${money(p.prior_safe_harbor)}), so you need ${money(p.required)}.`
}

function PlanCard({ title, plan, link, linkLabel, onPaid }: { title: string; plan: Plan; link: string; linkLabel: string; onPaid: () => void }) {
  return (
    <Card className="overflow-hidden shadow-sm">
      <div className="h-1 bg-primary" />
      <CardHeader className="space-y-2">
        <CardDescription className="flex items-center justify-between gap-2 font-medium">
          {title}
          {plan.next_due && <Badge variant="secondary" className="bg-accent text-accent-foreground"><CalendarDays /> Due {fmtDate(plan.next_due)}</Badge>}
        </CardDescription>
        <CardTitle className="text-4xl font-semibold tabular-nums tracking-tight">
          {plan.next_due ? money(plan.next_amount) : 'Nothing due'}
        </CardTitle>
        {plan.next_due && <p className="text-sm text-muted-foreground">next estimated payment</p>}
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="rounded-lg bg-muted/50 p-3 text-muted-foreground">{methodText(plan)}</p>
        <div className="space-y-1">
          <Line label="Required for the year" value={plan.required} />
          <Line label="Already paid" value={plan.paid} onClick={onPaid} />
          <Line label="Projected April balance" value={plan.april_balance} />
        </div>
        <a href={link} target="_blank" rel="noopener noreferrer" className={cn(buttonVariants({ size: 'lg' }), 'w-full')}>
          {linkLabel} <ExternalLink />
        </a>
        <p className="text-center text-xs text-muted-foreground">We never pay or file for you.</p>
      </CardContent>
    </Card>
  )
}

function Line({ label, value, onClick, strong, indent }: { label: string; value: number; onClick?: () => void; strong?: boolean; indent?: boolean }) {
  const cls = `flex w-full justify-between gap-4 rounded-md px-2 py-1.5 text-left ${strong ? 'font-semibold text-foreground' : ''} ${indent ? 'pl-6 text-muted-foreground' : ''}`
  const body = (
    <>
      <span className={onClick ? 'text-primary underline decoration-dotted underline-offset-4' : ''}>{label}</span>
      <span className="tabular-nums">{money(value)}</span>
    </>
  )
  return onClick ? <button type="button" onClick={onClick} className={`${cls} hover:bg-accent`}>{body}</button> : <div className={cls}>{body}</div>
}

const BY_STYLE: Record<string, string> = {
  rules: 'bg-neutral-100 text-neutral-700',
  llm: 'bg-violet-100 text-violet-800',
  'llm-guess': 'bg-amber-100 text-amber-800',
  ocr: 'bg-sky-100 text-sky-800',
  vision: 'bg-amber-100 text-amber-800',
  user: 'bg-accent text-accent-foreground',
}

function SourceTable({ session, rows, fixable, onChanged }: { session: string; rows: SourceRow[]; fixable: boolean; onChanged: () => void }) {
  const [fixing, setFixing] = useState<string | null>(null)
  const [history, setHistory] = useState<Record<string, HistoryRow[]>>({})
  if (!rows.length) return <p className="px-4 text-sm text-muted-foreground">No source rows.</p>
  return (
    <div className="px-4 pb-6">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Description</TableHead>
            <TableHead className="text-right">Amount</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>By</TableHead>
            {fixable && <TableHead />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <Fragment key={r.key}>
              <TableRow>
                <TableCell className="max-w-56 whitespace-normal">{r.description}</TableCell>
                <TableCell className="text-right tabular-nums">{money(r.amount)}</TableCell>
                <TableCell className="max-w-32 truncate font-mono text-xs" title={r.source}>{r.source}</TableCell>
                <TableCell><Badge className={BY_STYLE[r.by] ?? ''} variant="secondary">{r.by}</Badge></TableCell>
                {fixable && (
                  <TableCell>
                    <Button size="sm" variant="outline" onClick={() => setFixing(fixing === r.key ? null : r.key)}>Fix</Button>
                  </TableCell>
                )}
              </TableRow>
              {(fixing === r.key || history[r.key]) && (
                <TableRow>
                  <TableCell colSpan={5} className="whitespace-normal bg-muted/40">
                    {fixing === r.key && (
                      <FixForm
                        session={session}
                        rowKey={r.key}
                        merchant={r.merchant}
                        sameCount={r.merchant ? rows.filter((x) => x.merchant === r.merchant).length : 1}
                        onSaved={(h) => {
                          setHistory((m) => ({ ...m, [r.key]: h }))
                          setFixing(null)
                          onChanged()
                        }}
                      />
                    )}
                    {history[r.key] && <History rows={history[r.key]} />}
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function FixForm({ session, rowKey, merchant, sameCount, onSaved }: {
  session: string
  rowKey: string
  merchant?: string
  sameCount: number
  onSaved: (h: HistoryRow[]) => void
}) {
  const [category, setCategory] = useState('business_expense')
  const [all, setAll] = useState(true)
  const [pct, setPct] = useState('100')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const n = Number(pct)
    if (!Number.isFinite(n) || n < 0 || n > 100) return setErr('Business % must be 0–100.')
    setBusy(true)
    setErr(null)
    try {
      onSaved((await api.correct({ session, key: rowKey, category, business_pct: n, reason, same_merchant: sameCount > 1 && all })).history)
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_6rem_2fr_auto] sm:items-end">
      <div className="space-y-1">
        <Label htmlFor="fix-cat">Category</Label>
        <select id="fix-cat" value={category} onChange={(e) => setCategory(e.target.value)} className="h-8 w-full rounded-md border bg-white px-2 text-sm">
          <option value="business_expense">Business expense</option>
          <option value="personal">Personal</option>
        </select>
      </div>
      <div className="space-y-1">
        <Label htmlFor="fix-pct">Business %</Label>
        <Input id="fix-pct" type="number" min={0} max={100} value={pct} onChange={(e) => setPct(e.target.value)} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="fix-reason">Reason</Label>
        <Input id="fix-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. client dinner" />
      </div>
      <Button type="submit" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : 'Save'}</Button>
      {sameCount > 1 && (
        <label className="flex items-center gap-2 text-sm sm:col-span-4">
          <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} className="size-4 accent-primary" />
          Apply to all {sameCount} guessed transactions at {merchant}
        </label>
      )}
      {err && <p className="text-sm text-destructive sm:col-span-4">{err}</p>}
    </form>
  )
}

function History({ rows }: { rows: HistoryRow[] }) {
  return (
    <div className="mt-3 space-y-1">
      <p className="text-xs font-medium text-muted-foreground">History · Facts supersede, never overwrite (SurrealDB)</p>
      {rows.map((h, i) => (
        <div key={i} className={`flex flex-wrap items-center gap-2 text-xs ${h.current ? '' : 'text-muted-foreground line-through'}`}>
          <Badge variant="secondary" className={BY_STYLE[h.by] ?? ''}>{h.by}</Badge>
          <span className="font-mono">{fmtValue(h.value)}</span>
          {h.reason && <span>— {h.reason}</span>}
          <span className="ml-auto">{new Date(h.at).toLocaleString()}</span>
          {h.current && <Badge>current</Badge>}
        </div>
      ))}
    </div>
  )
}

function fmtValue(v: unknown) {
  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>
    if ('category' in o) return `${o.category}${o.business_pct != null ? ` · ${o.business_pct}% business` : ''}`
    return JSON.stringify(v)
  }
  return String(v)
}

type ChatMsg = { who: 'agent' | 'user'; text: string }

function AgentChat({ session, onChanged }: { session: string; onChanged: () => void }) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<AgentReply['pending']>()

  const run = async (call: Promise<AgentReply>, approved?: boolean) => {
    setBusy(true)
    try {
      const r = await call
      if (approved) onChanged() // the approved write superseded a fact: recompute the numbers above
      setPending(r.pending)
      if (r.reply) setMsgs((m) => [...m, { who: 'agent', text: r.reply! }])
    } catch (e) {
      setMsgs((m) => [...m, { who: 'agent', text: `Something went wrong: ${e}` }])
    } finally {
      setBusy(false)
    }
  }
  const send = (t: string) => {
    if (!t.trim() || busy || pending) return
    setMsgs((m) => [...m, { who: 'user', text: t.trim() }])
    setText('')
    run(api.chat(session, t.trim()))
  }
  const decide = (approve: boolean) => {
    setMsgs((m) => [...m, { who: 'user', text: approve ? 'Approved.' : 'Rejected.' }])
    run(api.resume(session, approve), approve)
  }

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle>Ask the agent</CardTitle>
        <CardDescription>Ask why a number is what it is, try a what-if, or ask it to fix a row. It changes nothing without your approval.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {msgs.length > 0 && (
          <div className="max-h-96 space-y-3 overflow-y-auto rounded-xl border bg-muted/30 p-4" aria-live="polite">
            {msgs.map((m, i) => (
              <div key={i} className={cn('flex', m.who === 'user' ? 'justify-end' : 'justify-start')}>
                <div className={cn('max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm',
                  m.who === 'user' ? 'bg-primary text-primary-foreground' : 'border bg-card')}>{m.text}</div>
              </div>
            ))}
            {busy && <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-3.5 animate-spin" /> Working…</p>}
          </div>
        )}
        {pending && (
          <div className="space-y-2 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900" role="alert">
            <p className="font-medium">The agent wants to make {pending.length} change{pending.length > 1 ? 's' : ''}:</p>
            <ul className="max-h-48 space-y-1 overflow-y-auto font-mono text-xs">
              {pending.map((p, i) => (
                <li key={i}>{p.tool} {String(p.args.key)} → {String(p.args.category)} {String(p.args.business_pct)}%: {String(p.args.reason)}</li>
              ))}
            </ul>
            <div className="flex gap-2">
              <Button size="sm" disabled={busy} onClick={() => decide(true)}>Approve{pending.length > 1 ? ` all ${pending.length}` : ''}</Button>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => decide(false)}>Reject</Button>
            </div>
          </div>
        )}
        {msgs.length === 0 && (
          <div className="flex flex-wrap gap-2">
            {['Why do I owe this much next quarter?', 'What if I land a $20k gig in November?', 'Which expenses did you mark personal?'].map((q) => (
              <Button key={q} variant="outline" size="sm" className="rounded-full" onClick={() => send(q)}>{q}</Button>
            ))}
          </div>
        )}
        <form onSubmit={(e) => (e.preventDefault(), send(text))} className="flex gap-2">
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about your taxes…" disabled={busy || !!pending} aria-label="Message the agent" />
          <Button type="submit" disabled={busy || !!pending || !text.trim()}>Send</Button>
        </form>
      </CardContent>
    </Card>
  )
}
