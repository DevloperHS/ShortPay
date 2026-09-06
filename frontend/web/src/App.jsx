import { useEffect, useState } from 'react'
import { Truck, Sun, Moon, RefreshCw, ArrowLeft, ArrowUpRight, Check, FileText, FileUp, X } from 'lucide-react'

const columns = ['Out of scope', 'Auto-closed', 'Major exceptions', 'Short-paid', 'Paid as billed']
const money = cents => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format((cents || 0) / 100)
const clock = value => (value || '').slice(0, 5)

async function api(path, body) {
  const response = await fetch(`/api/ui${path}`, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Please try again.')
  return data
}

function ImportInvoice({ navigate }) {
  const [tab, setTab] = useState('text')
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submitText(event) {
    event.preventDefault()
    if (!text.trim()) return
    setBusy(true); setError('')
    try {
      const result = await api('/ingest', { invoice_text: text.trim() })
      navigate(`/cases/${encodeURIComponent(result.invoice_id)}`)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function submitPdf(event) {
    event.preventDefault()
    if (!file) {
      setError('Choose a carrier PDF before extracting.')
      return
    }
    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      setError('PDF only.')
      return
    }
    if (file.size > 15 * 1024 * 1024) {
      setError('PDF exceeds 15 MB.')
      return
    }
    setBusy(true); setError('')
    try {
      const form = new FormData()
      form.append('invoice_pdf', file, file.name)
      const res = await fetch('/api/ui/ingest/pdf', {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: form,
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data.detail || data.error || 'PDF extraction failed.')
      }
      navigate(`/cases/${encodeURIComponent(data.invoice_id)}`)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  function onFileChange(e) {
    setError('')
    const chosen = e.target.files && e.target.files[0]
    if (!chosen) return
    if (!chosen.name.toLowerCase().endsWith('.pdf') && chosen.type !== 'application/pdf') {
      setError('PDF only.')
      return
    }
    if (chosen.size > 15 * 1024 * 1024) {
      setError('PDF exceeds 15 MB.')
      return
    }
    setFile(chosen)
  }

  return <details className="import"><summary>Import carrier invoice</summary>
    <div className="import-nav" role="tablist">
      <button
        type="button"
        className={`tab-btn${tab === 'text' ? ' active' : ''}`}
        onClick={() => { setTab('text'); setError('') }}
      >
        <FileText size={15} /> Paste invoice text
      </button>
      <button
        type="button"
        className={`tab-btn${tab === 'pdf' ? ' active' : ''}`}
        onClick={() => { setTab('pdf'); setError('') }}
      >
        <FileUp size={15} /> Upload PDF
      </button>
    </div>

    {tab === 'text' ? (
      <form onSubmit={submitText}>
        <label htmlFor="invoice">Invoice text</label>
        <textarea
          id="invoice"
          required
          placeholder="Paste carrier invoice text (UPS, FedEx, DHL, or generic EDI format)..."
          value={text}
          onChange={e => setText(e.target.value)}
          rows={5}
          disabled={busy}
        />
        <button className="primary" disabled={busy || !text.trim()}>
          {busy ? 'Extracting and matching...' : 'Extract and match'}
        </button>
      </form>
    ) : (
      <form onSubmit={submitPdf}>
        <label htmlFor="invoice-pdf">Carrier invoice PDF</label>
        {!file ? (
          <label className="drop-zone" htmlFor="invoice-pdf">
            <FileUp size={28} />
            <span>Choose a carrier PDF or drag & drop</span>
            <small>PDF format · Up to 15 MB</small>
            <input
              id="invoice-pdf"
              type="file"
              accept=".pdf,application/pdf"
              disabled={busy}
              onChange={onFileChange}
              style={{ display: 'none' }}
            />
          </label>
        ) : (
          <div className="file-card">
            <div className="file-meta">
              <FileText size={20} />
              <div>
                <strong>{file.name}</strong>
                <small>{Math.max(1, Math.round(file.size / 1024))} KB · PDF document</small>
              </div>
            </div>
            <button
              type="button"
              className="icon-btn"
              title="Remove file"
              onClick={() => setFile(null)}
              disabled={busy}
            >
              <X size={16} />
            </button>
          </div>
        )}
        <button className="primary" disabled={busy || !file}>
          {busy ? 'Extracting invoice facts from PDF...' : 'Upload and match PDF'}
        </button>
      </form>
    )}
    {error && <p role="alert">{error}</p>}
  </details>
}

function Packet({ item }) {
  const proposal = item.erp_proposal
  const packet = item.dispute_packet
  if (!proposal && !packet) return null
  return <section className="packet" aria-label="Short-pay packet">
    <h2>Short-pay packet</h2>
    {proposal && <p>Propose ERP payable {money(proposal.authorized_amount_cents)} to {proposal.system_of_record_target}.</p>}
    {packet && <>
      <p>Dispute {money(packet.disputed_total_cents)} with the carrier. Attach {packet.attached_evidence.join(', ')}.</p>
      <ul>{packet.dispute_lines.map(line => <li key={line.charge_type}>{line.charge_type.replaceAll('_', ' ')} {money(line.disputed_amount_cents)}. {line.explanation}</li>)}</ul>
    </>}
  </section>
}

function CaseDetail({ item, reload }) {
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  async function decide(action) {
    setBusy(true); setError('')
    try {
      const latest = await api(`/cases/${encodeURIComponent(item.invoice_id)}`)
      if (latest.disposition !== 'NeedsReview') throw new Error('This case has changed. Refresh before continuing.')
      if (action === 'ApproveShortPay' && latest.expected_cents !== item.expected_cents) {
        throw new Error('Authorized payable changed. Refresh before continuing.')
      }
      await api(`/cases/${encodeURIComponent(item.invoice_id)}/decide`, {
        action_type: action,
        override_reason: reason.trim(),
        expected_payable_cents: item.expected_cents,
      })
      reload()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const liftgateNote = item.destination_has_dock ? 'dock present' : 'no dock'
  return <>
    <header className="heading"><div><p>{item.disposition}</p><h1>{item.carrier_name}</h1><p>{item.shipment_id} / {item.invoice_id} / BOL {item.bill_of_lading}</p></div></header>
    <section className="metrics" aria-label="Invoice amounts">
      {[['Carrier billed', item.billed_cents], ['Authorized payable', item.expected_cents], ['Dispute amount', item.dispute_cents]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{money(value)}</strong></div>)}
    </section>
    <section className="review"><h2>Charge review</h2>
      <div className="table-wrap"><table><thead><tr><th>Fact</th><th>Allowed / authorized</th><th>Actual / billed</th></tr></thead><tbody>
        {item.arrived_at && <tr><th>Dwell</th><td>{item.allowed_dwell_minutes} min free</td><td>{clock(item.arrived_at)} → {clock(item.departed_at)} ({item.dwell_minutes} min)</td></tr>}
        {item.lines.map((line, i) => <tr key={i}><th>{line.charge_type.replaceAll('_', ' ')}</th><td>{money(line.expected_cents)}{line.charge_type === 'LIFTGATE' ? ` (${liftgateNote})` : ''}{line.charge_type === 'DETENTION' ? ` (${item.completed_detention_hours} completed hour${item.completed_detention_hours === 1 ? '' : 's'} × rate)` : ''}</td><td>{money(line.billed_cents)}</td></tr>)}
        <tr><th>Payable</th><td>{money(item.expected_cents)}</td><td>{money(item.billed_cents)} billed</td></tr>
      </tbody></table></div>
    </section>
    <Packet item={item} />
    {item.disposition === 'NeedsReview' ? <section className="decisions"><h2>Controller decision</h2><p>Pay {money(item.expected_cents)} / dispute {money(item.dispute_cents)}</p>
      <button className="primary" disabled={busy} onClick={() => decide('ApproveShortPay')}><Check size={16} />{busy ? 'Submitting...' : `Approve ${money(item.expected_cents)} and generate carrier short-pay notice`}</button>
      <details><summary>Pay as billed instead</summary><form onSubmit={e => { e.preventDefault(); decide('OverridePayAsBilled') }}>
        <label htmlFor="reason">Override reason</label><textarea id="reason" required value={reason} disabled={busy} onChange={e => setReason(e.target.value)} />
        <button disabled={busy || !reason.trim()}>Confirm pay as billed</button>
      </form></details>{error && <p role="alert">{error}</p>}
    </section> : <p role="status">Current disposition: {item.disposition}{item.skip_reason ? ` / ${item.skip_reason}` : ''}</p>}
  </>
}

export default function App() {
  const [path, setPath] = useState(location.pathname)
  const [theme, setTheme] = useState(document.documentElement.dataset.theme || 'light')
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const detail = path.startsWith('/cases/')
  const navigate = next => { history.pushState(null, '', next); setPath(next); window.scrollTo(0, 0) }
  useEffect(() => { const pop = () => setPath(location.pathname); addEventListener('popstate', pop); return () => removeEventListener('popstate', pop) }, [])
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('shortpay-theme', theme) } catch { /* Storage may be disabled. */ }
  }, [theme])
  useEffect(() => {
    let active = true
    setData(null); setError('')
    api(detail ? path : '/cases').then(value => { if (active) setData(value) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [path, revision, detail])
  const link = (event, next) => { if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate(next) } }
  return <><header className="site-header"><a className="brand" href="/" onClick={e => link(e, '/')}><Truck /><strong>Shortpay</strong><span>Freight audit desk</span></a>
    <button title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`} aria-label="Toggle color theme" aria-pressed={theme === 'dark'} onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}</button></header>
    <main><div className="toolbar">{detail ? <a href="/" onClick={e => link(e, '/')}><ArrowLeft size={16} />Audit board</a> : <span>Pre-pay control room</span>}<button title="Refresh cases" aria-label="Refresh cases" onClick={() => setRevision(v => v + 1)}><RefreshCw size={16} /></button></div>
      {error ? <section role="alert"><h2>Unable to load cases</h2><p>{error}</p><button onClick={() => setRevision(v => v + 1)}>Try again</button></section> : !data ? <p role="status">Loading audit data...</p> : detail ? <CaseDetail key={path} item={data} reload={() => setRevision(v => v + 1)} /> : <>
        <div className="heading"><div><h1>Audit board</h1><p>Weekend freight audit</p></div><div><span>Open exceptions</span><strong>{data.filter(c => c.kanban.column === 'Major exceptions').length}</strong></div></div>
        <ImportInvoice navigate={navigate} />
        <section className="board" aria-label="Freight audit cases">{columns.map(column => {
          const cases = data.filter(c => c.kanban.column === column)
          return <section className="lane" key={column}><h2>{column}<span>{cases.length}</span></h2>{cases.map(item => <a className={`case${item.kanban.column === 'Major exceptions' ? ' exception' : ''}`} style={item.kanban.color ? { '--exception': item.kanban.color } : undefined} key={item.invoice_id} href={`/cases/${encodeURIComponent(item.invoice_id)}`} onClick={e => link(e, `/cases/${encodeURIComponent(item.invoice_id)}`)}>
            <div><b>{item.carrier_name}</b><ArrowUpRight size={16} /></div><h3>{item.shipment_id}</h3><small>{item.invoice_id}</small><p>{item.kanban.subtitle}</p><footer><span>Billed<strong>{money(item.billed_cents)}</strong></span><span>Dispute<strong>{money(item.dispute_cents)}</strong></span></footer>
          </a>)}{!cases.length && <p className="empty">No cases in this lane</p>}</section>
        })}</section>
      </>}
    </main></>
}
