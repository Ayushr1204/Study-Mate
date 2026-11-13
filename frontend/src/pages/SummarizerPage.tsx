import { useRef, useState, type DragEvent } from 'react'
import { Check, ClipboardCopy, FileText, Upload } from 'lucide-react'
import { Button, Card, Chip, EmptyState, ErrorBanner, Label, Page, PageHeader, Segmented } from '../components/ui'
import { cx, inputClass } from '../components/styles'
import { api } from '../services/api'
import type { DocumentExtract, SummaryResponse } from '../types'

const PARTS = [
  { id: 'summary', label: 'Summary' },
  { id: 'concepts', label: 'Key concepts' },
  { id: 'revision', label: 'Revision notes' },
  { id: 'terms', label: 'Key terms & definitions' },
]
const LENGTHS = [
  { value: 'short', label: 'Short' },
  { value: 'medium', label: 'Medium' },
  { value: 'detailed', label: 'Detailed' },
]
const MAX_BYTES = 5 * 1024 * 1024
const EXTENSIONS = ['.txt', '.md', '.pdf', '.docx']

function toMarkdown(s: SummaryResponse): string {
  const out = [`# ${s.title || 'Summary'}`]
  if (s.summary) out.push('## Summary', s.summary)
  if (s.key_concepts.length) out.push('## Key concepts', s.key_concepts.map((c) => `- ${c}`).join('\n'))
  if (s.revision_notes.length) out.push('## Revision notes', s.revision_notes.map((c) => `- ${c}`).join('\n'))
  if (s.key_terms.length) out.push('## Key terms', s.key_terms.map((t) => `- **${t.term}**: ${t.definition}`).join('\n'))
  return out.join('\n\n')
}

export function SummarizerPage() {
  const [text, setText] = useState('')
  const [parts, setParts] = useState<string[]>(PARTS.map((p) => p.id))
  const [length, setLength] = useState('medium')
  const [file, setFile] = useState<DocumentExtract['info'] | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [result, setResult] = useState<SummaryResponse | null>(null)
  const [copied, setCopied] = useState(false)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = async (f: File | undefined) => {
    if (!f) return
    setUploadError(null)
    const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase()
    if (!EXTENSIONS.includes(ext)) return setUploadError(new Error(`Unsupported file type. Use ${EXTENSIONS.join(', ')}.`))
    if (f.size > MAX_BYTES) return setUploadError(new Error(`File is ${(f.size / 1048576).toFixed(1)} MB; the limit is 5 MB.`))
    setUploading(true)
    try {
      const doc = await api.extractDocument(f)
      setText(doc.text)
      setFile(doc.info)
    } catch (e) {
      setUploadError(e)
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    void handleFile(e.dataTransfer.files[0])
  }

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      setResult(await api.summarize(text, parts, length))
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const copy = () => {
    if (!result) return
    navigator.clipboard
      ?.writeText(toMarkdown(result))
      .then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      })
      .catch(() => undefined)
  }

  const proc = result?.processing as { strategy?: string; chunks?: number; document_tokens?: number; document_truncated?: boolean } | undefined

  return (
    <Page wide>
      <PageHeader title="Notes Summarizer" description="Paste study material or upload a TXT, MD, PDF or DOCX file. Long documents are split and summarized in stages so they fit the model's token budget." />
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-4">
          <Card title="Study material">
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cx('mb-3 flex items-center justify-between gap-3 rounded-md border border-dashed px-3 py-2.5 text-sm transition-colors', dragging ? 'border-accent bg-accent-soft' : 'border-line-strong')}
            >
              <span className="flex items-center gap-2 text-muted">
                <Upload className="size-4" aria-hidden />
                {uploading ? 'Extracting text…' : 'Drop a file here, or choose one (max 5 MB)'}
              </span>
              <Button size="sm" onClick={() => inputRef.current?.click()} disabled={uploading}>Choose file</Button>
              <input ref={inputRef} type="file" accept={EXTENSIONS.join(',')} className="sr-only" aria-label="Upload study material" onChange={(e) => void handleFile(e.target.files?.[0])} />
            </div>
            {!!uploadError && <ErrorBanner error={uploadError} className="mb-3" />}
            {file && (
              <p className="mb-3 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                <Chip tone="accent"><FileText className="size-3" /> {file.filename}</Chip>
                {file.pages !== null && <Chip>{file.pages} pages</Chip>}
                <Chip>{file.characters.toLocaleString()} characters</Chip>
                {file.truncated && <Chip tone="warn">truncated to the server limit</Chip>}
              </p>
            )}
            <Label htmlFor="notes-text">Text</Label>
            <textarea id="notes-text" className={cx(inputClass, 'min-h-72 resize-y font-mono text-[13px] leading-relaxed')} value={text} onChange={(e) => { setText(e.target.value); setFile(null) }} placeholder="Paste your notes, lecture transcript or article here…" />
            <p className="mt-1.5 text-xs text-faint">{text.length.toLocaleString()} characters{text.length > 0 && text.length < 50 ? ' · at least 50 are needed' : ''}</p>
          </Card>

          <Card title="Output">
            <fieldset className="mb-4">
              <legend className="mb-2 text-xs font-medium text-muted">Include</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {PARTS.map((p) => (
                  <label key={p.id} className="flex cursor-pointer items-center gap-2 text-sm">
                    <input type="checkbox" className="size-4 accent-[var(--color-accent)]" checked={parts.includes(p.id)} onChange={(e) => setParts((cur) => (e.target.checked ? [...cur, p.id] : cur.filter((x) => x !== p.id)))} />
                    {p.label}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="flex flex-wrap items-center gap-4">
              <Segmented label="Summary length" options={LENGTHS} value={length} onChange={setLength} />
              <Button variant="primary" onClick={() => void run()} loading={busy} disabled={text.trim().length < 50 || parts.length === 0}>{busy ? 'Summarizing…' : 'Summarize'}</Button>
            </div>
            {!!error && <ErrorBanner error={error} className="mt-4" />}
          </Card>
        </div>

        <Card
          title={result ? result.title || 'Summary' : 'Result'}
          action={result && <Button size="sm" onClick={copy}>{copied ? <Check className="size-3.5 text-ok" /> : <ClipboardCopy className="size-3.5" />} {copied ? 'Copied' : 'Copy as Markdown'}</Button>}
        >
          {!result && !busy && <EmptyState icon={<FileText className="size-7" />} title="Nothing summarized yet">Your summary, key concepts, revision notes and key terms will appear here.</EmptyState>}
          {busy && <p className="py-12 text-center text-sm text-muted" role="status">Running the summarization node…</p>}
          {result && !busy && (
            <div className="space-y-5">
              <div className="flex flex-wrap gap-1.5">
                {proc?.strategy && <Chip tone="info">{proc.strategy}{proc.chunks && proc.chunks > 1 ? ` · ${proc.chunks} chunks` : ''}</Chip>}
                {proc?.document_tokens !== undefined && <Chip>{proc.document_tokens.toLocaleString()} tokens in</Chip>}
                {proc?.document_truncated && <Chip tone="warn">only the first part was summarized</Chip>}
                {result.execution.llm.provider && <Chip tone={result.execution.llm.provider === 'offline' ? 'warn' : 'neutral'}>{result.execution.llm.provider}</Chip>}
                <Chip>{result.execution.duration_ms} ms</Chip>
              </div>
              {result.execution.llm.provider === 'offline' && <p className="rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">No language model is reachable, so this summary was produced by the built-in extractive fallback (it selects the most informative sentences).</p>}
              {result.summary && <section><h3 className="mb-1.5 text-xs font-semibold tracking-wide text-muted uppercase">Summary</h3><p className="text-sm leading-relaxed whitespace-pre-line">{result.summary}</p></section>}
              {result.key_concepts.length > 0 && <section><h3 className="mb-1.5 text-xs font-semibold tracking-wide text-muted uppercase">Key concepts</h3><div className="flex flex-wrap gap-1.5">{result.key_concepts.map((c) => <Chip key={c} tone="accent">{c}</Chip>)}</div></section>}
              {result.revision_notes.length > 0 && <section><h3 className="mb-1.5 text-xs font-semibold tracking-wide text-muted uppercase">Revision notes</h3><ul className="list-disc space-y-1 pl-5 text-sm marker:text-faint">{result.revision_notes.map((n, i) => <li key={i}>{n}</li>)}</ul></section>}
              {result.key_terms.length > 0 && (
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold tracking-wide text-muted uppercase">Key terms</h3>
                  <dl className="divide-y divide-line rounded-md border border-line">
                    {result.key_terms.map((t, i) => <div key={i} className="grid gap-1 px-3 py-2 sm:grid-cols-[10rem_1fr]"><dt className="text-sm font-medium">{t.term}</dt><dd className="text-sm text-muted">{t.definition}</dd></div>)}
                  </dl>
                </section>
              )}
            </div>
          )}
        </Card>
      </div>
    </Page>
  )
}
