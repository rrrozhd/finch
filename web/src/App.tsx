import { useEffect, useRef, useState } from 'react'
import { Upload as UploadIcon, Loader2, Send, ShieldCheck, Calculator, Link2, Check, Sparkles, FileArchive, ChevronDown } from 'lucide-react'
import { api, money, type Next, type UploadResponse } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ResultsView } from '@/Results'
import { cn } from '@/lib/utils'

type Stage = 'upload' | 'questions' | 'results'

export default function App() {
  const [stage, setStage] = useState<Stage>('upload')
  const [up, setUp] = useState<UploadResponse | null>(null)

  const onUploaded = (r: UploadResponse) => {
    setUp(r)
    setStage(r.next ? 'questions' : 'results')
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b bg-card/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="grid size-9 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
              <Calculator className="size-5" />
            </div>
            <div className="leading-tight">
              <h1 className="font-semibold tracking-tight">Finch</h1>
              <p className="text-xs text-muted-foreground">NYC 1099 freelancers · Form 1040-ES + NY IT-2105</p>
            </div>
          </div>
          <Steps stage={stage} />
        </div>
      </header>
      <main className="mx-auto max-w-5xl space-y-6 px-4 py-8">
        {stage === 'upload' && <UploadStage onDone={onUploaded} />}
        {up && stage !== 'upload' && <Summary up={up} />}
        {up && stage === 'questions' && <Chat session={up.session} first={up.next} onDone={() => setStage('results')} />}
        {up && stage === 'results' && <ResultsView session={up.session} />}
      </main>
    </div>
  )
}

function Steps({ stage }: { stage: Stage }) {
  const all: [Stage, string][] = [['upload', 'Upload'], ['questions', 'Questions'], ['results', 'Results']]
  const idx = all.findIndex(([s]) => s === stage)
  return (
    <ol className="hidden items-center gap-2 text-sm sm:flex" aria-label="Progress">
      {all.map(([s, label], i) => (
        <li key={s} className="flex items-center gap-2" aria-current={i === idx ? 'step' : undefined}>
          {i > 0 && <span className={cn('h-px w-6', i <= idx ? 'bg-primary' : 'bg-border')} />}
          <span
            className={cn(
              'grid size-6 place-items-center rounded-full border text-xs font-medium',
              i < idx && 'border-primary bg-primary text-primary-foreground',
              i === idx && 'border-primary text-primary',
              i > idx && 'text-muted-foreground',
            )}
          >
            {i < idx ? <Check className="size-3.5" /> : i + 1}
          </span>
          <span className={i <= idx ? 'font-medium' : 'text-muted-foreground'}>{label}</span>
        </li>
      ))}
    </ol>
  )
}

const PILLARS = [
  { icon: ShieldCheck, title: 'Sandboxed', text: 'Files are unpacked and OCR’d in an isolated Daytona sandbox.' },
  { icon: Calculator, title: 'Code does the math', text: 'AI only labels transactions; PolicyEngine and IRS rules compute.' },
  { icon: Link2, title: 'Every dollar traced', text: 'Click any number to see the bank rows and receipts behind it.' },
]

function UploadStage({ onDone }: { onDone: (r: UploadResponse) => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [drag, setDrag] = useState(false)
  const [name, setName] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)

  const send = async (f: File | undefined) => {
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.zip')) return setErr('Please choose a .zip file.')
    setErr(null)
    setName(f.name)
    setBusy(true)
    try {
      onDone(await api.upload(f))
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  const sample = async () => {
    setErr(null)
    try {
      const r = await fetch('/api/demo-zip')
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
      await send(new File([await r.blob()], 'maya_2026.zip', { type: 'application/zip' }))
    } catch (e) {
      setErr(String(e))
    }
  }

  return (
    <div className="space-y-8">
      <section className="space-y-3 text-center">
        <Badge variant="secondary" className="bg-accent text-accent-foreground">Tax year 2026 · Q4 payment due Jan 15</Badge>
        <h2 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">Know exactly what to pay this quarter.</h2>
        <p className="mx-auto max-w-xl text-pretty text-muted-foreground">
          Drop in your bank exports and receipts. We categorize every transaction, ask only what your files can’t tell us,
          and compute your federal, New York State and NYC estimated payments.
        </p>
      </section>

      <Card className="shadow-sm">
        <CardContent className="p-6">
          {busy ? (
            <div className="space-y-4 rounded-xl border border-dashed bg-muted/40 p-12 text-center" role="status">
              <Loader2 className="mx-auto size-8 animate-spin text-primary" />
              <div className="space-y-1">
                <p className="font-medium">Reading {name}…</p>
                <p className="text-sm text-muted-foreground">Unpacking in a Daytona sandbox, OCR on receipts, categorizing transactions. Usually 30–60 seconds.</p>
              </div>
              <Progress value={null} className="mx-auto max-w-sm" />
            </div>
          ) : (
            <button
              type="button"
              onClick={() => input.current?.click()}
              onDragOver={(e) => (e.preventDefault(), setDrag(true))}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDrag(false)
                send(e.dataTransfer.files[0])
              }}
              className={cn(
                'group w-full rounded-xl border-2 border-dashed p-12 text-center transition-colors focus-visible:outline-2 focus-visible:outline-ring',
                drag ? 'border-primary bg-accent' : 'border-input hover:border-primary/50 hover:bg-accent/50',
              )}
            >
              <span className="mx-auto mb-4 grid size-12 place-items-center rounded-full bg-accent text-primary transition-transform group-hover:scale-105">
                <UploadIcon className="size-5" />
              </span>
              <p className="font-medium">Drop your .zip here, or click to browse</p>
              <p className="mt-1 text-sm text-muted-foreground">Bank exports (.csv), spreadsheets (.xlsx), receipts (.jpg/.png) · up to 50 MB</p>
            </button>
          )}
          <input ref={input} type="file" accept=".zip" hidden onChange={(e) => (send(e.target.files?.[0]), (e.target.value = ''))} />
          {!busy && (
            <div className="mt-4 flex flex-col items-center justify-center gap-2 text-sm text-muted-foreground sm:flex-row">
              <span>No files handy?</span>
              <Button variant="outline" size="sm" onClick={sample}>
                <Sparkles /> Try with sample data (Maya, NYC creator)
              </Button>
            </div>
          )}
          {err && <p className="mt-3 text-center text-sm text-destructive" role="alert">{err}</p>}
        </CardContent>
      </Card>

      <section className="grid gap-4 sm:grid-cols-3">
        {PILLARS.map(({ icon: Icon, title, text }) => (
          <div key={title} className="flex gap-3 rounded-xl border bg-card p-4">
            <Icon className="mt-0.5 size-5 shrink-0 text-primary" />
            <div>
              <p className="text-sm font-medium">{title}</p>
              <p className="text-sm text-muted-foreground">{text}</p>
            </div>
          </div>
        ))}
      </section>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border bg-muted/30 px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
    </div>
  )
}

function Summary({ up }: { up: UploadResponse }) {
  const s = up.summary
  const [open, setOpen] = useState(false)
  const vision = s.receipts.filter((r) => r.path !== 'ocr').length
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><FileArchive className="size-4 text-primary" /> What we found</CardTitle>
        <CardDescription>Rules handle the obvious rows; the AI only sees merchants rules can’t place.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Transactions" value={s.transactions} />
          <Stat label="Receipts" value={s.receipts.length} />
          <Stat label="Sorted by rules" value={s.rules} />
          <Stat label="Merchants sent to AI" value={s.llm_merchants} />
        </div>
        {s.receipts.length > 0 && (
          <div>
            <Button variant="ghost" size="sm" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="-ml-2">
              <ChevronDown className={cn('transition-transform', open && 'rotate-180')} />
              Receipts: {s.receipts.length - vision} read by OCR, {vision} by vision fallback
            </Button>
            {open && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Receipt</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                    <TableHead className="text-right">OCR confidence</TableHead>
                    <TableHead>Read by</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {s.receipts.map((r) => (
                    <TableRow key={r.file}>
                      <TableCell className="max-w-48 truncate font-mono text-xs">{r.file}</TableCell>
                      <TableCell>{r.date ?? '—'}</TableCell>
                      <TableCell className="text-right tabular-nums">{money(r.total)}</TableCell>
                      <TableCell className="text-right tabular-nums">{Math.round(r.confidence <= 1 ? r.confidence * 100 : r.confidence)}%</TableCell>
                      <TableCell>
                        <Badge variant={r.path === 'ocr' ? 'secondary' : 'outline'} className={r.path === 'ocr' ? '' : 'border-amber-300 bg-amber-50 text-amber-800'}>
                          {r.path === 'ocr' ? 'OCR' : 'Vision fallback'}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

type Msg = { who: 'agent' | 'user'; text: string }

function quickReplies(field: string | undefined): string[] {
  if (!field) return []
  if (field.startsWith('merchant:')) return ['Business', 'Personal']
  if (field === 'in_nyc') return ['Yes', 'No']
  if (field === 'filing_status') return ['Single']
  if (field === 'state') return ['New York']
  return []
}

function Chat({ session, first, onDone }: { session: string; first: Next; onDone: () => void }) {
  const [next, setNext] = useState<Next>(first)
  const [msgs, setMsgs] = useState<Msg[]>(first ? [{ who: 'agent', text: first.question }] : [])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [answered, setAnswered] = useState(0)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [msgs, busy])

  const reply = async (t: string) => {
    if (!next || !t.trim() || busy) return
    t = t.trim()
    setMsgs((m) => [...m, { who: 'user', text: t }])
    setText('')
    setBusy(true)
    try {
      const r = await api.answer(session, next.field, t)
      if (!r.ok) {
        // keep the same field; backend asks for clarification
        setMsgs((m) => [...m, { who: 'agent', text: r.clarify ?? "Sorry, I didn't catch that — could you rephrase?" }])
        return
      }
      setAnswered((n) => n + 1)
      if (!r.next) return onDone()
      setNext(r.next)
      setMsgs((m) => [...m, { who: 'agent', text: r.next!.question }])
    } catch (err) {
      setMsgs((m) => [...m, { who: 'agent', text: `Something went wrong: ${err}` }])
    } finally {
      setBusy(false)
    }
  }

  const chips = quickReplies(next?.field)
  return (
    <Card className="shadow-sm">
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="space-y-1.5">
          <CardTitle>A few questions</CardTitle>
          <CardDescription>Only what your files can’t tell us. We never guess about a charge — we ask.</CardDescription>
        </div>
        <Badge variant="secondary" className="shrink-0 tabular-nums">{answered} answered</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <ScrollArea className="h-80 rounded-xl border bg-muted/30 p-4">
          <div className="space-y-3" aria-live="polite">
            {msgs.map((m, i) => (
              <div key={i} className={cn('flex items-end gap-2', m.who === 'user' ? 'justify-end' : 'justify-start')}>
                {m.who === 'agent' && (
                  <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground" aria-hidden>
                    <Calculator className="size-3.5" />
                  </span>
                )}
                <div
                  className={cn(
                    'max-w-[80%] rounded-2xl px-3.5 py-2 text-sm shadow-xs',
                    m.who === 'user' ? 'rounded-br-sm bg-primary text-primary-foreground' : 'rounded-bl-sm border bg-card',
                  )}
                >
                  {m.text}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex items-center gap-2 pl-9 text-sm text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" /> Thinking…
              </div>
            )}
            <div ref={end} />
          </div>
        </ScrollArea>
        {chips.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {chips.map((c) => (
              <Button key={c} type="button" variant="outline" size="sm" disabled={busy} onClick={() => reply(c)} className="rounded-full">
                {c}
              </Button>
            ))}
          </div>
        )}
        <form onSubmit={(e) => (e.preventDefault(), reply(text))} className="flex gap-2">
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your answer…" disabled={busy} aria-label="Your answer" className="h-10" />
          <Button type="submit" disabled={busy || !text.trim()} className="h-10">
            <Send /> Send
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
