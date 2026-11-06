import { useEffect, useState } from 'react';

type CameraStatus = {
  online: boolean;
  device_id: string | null;
  frame_count: number;
  latest_received_at: string | null;
  latest_age_seconds: number | null;
  buffer_bytes: number;
};
type Analysis = {
  source_type: string;
  source_id: string;
  answer: string;
  question: string;
  inference_mode: string;
  processing_ms: number;
  evidence: { type: string; frame_count: number; buffer_frame_count: number };
  time_window: { start: string; end: string };
  uncertainty: string;
};

async function apiJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: 'no-store', ...options });
  const text = await response.text();
  let body: unknown;
  try { body = JSON.parse(text); } catch { body = {}; }
  if (!response.ok) {
    const detail = (body as { detail?: string }).detail;
    throw new Error(detail || `${response.status}: ${response.statusText}`);
  }
  return body as T;
}

function displayTime(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toLocaleTimeString() : value;
}

export default function App() {
  const [backendMode, setBackendMode] = useState('checking');
  const [espStatus, setEspStatus] = useState<CameraStatus | null>(null);
  const [espPreview, setEspPreview] = useState(false);
  const [espImage, setEspImage] = useState('');
  const [question, setQuestion] = useState('What can you observe in the recent frames?');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<Analysis | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refreshHealth = async () => {
      try {
        const value = await apiJson<{ inference_mode: string }>('/api/v1/health');
        if (!cancelled) setBackendMode(value.inference_mode);
      } catch { if (!cancelled) setBackendMode('unavailable'); }
    };
    void refreshHealth();
    const timer = setInterval(() => { void refreshHealth(); }, 15000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const refreshStatus = async () => {
      try {
        const value = await apiJson<CameraStatus>('/api/v1/sources/esp32/status');
        if (!cancelled) setEspStatus(value);
      } catch { if (!cancelled) setEspStatus(null); }
    };
    void refreshStatus();
    const timer = setInterval(() => { void refreshStatus(); }, 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  useEffect(() => {
    if (!espPreview || !espStatus?.online) return;
    const update = () => setEspImage(`/api/v1/sources/esp32/latest.jpg?t=${Date.now()}`);
    update();
    const timer = setInterval(update, 500);
    return () => clearInterval(timer);
  }, [espPreview, espStatus?.online]);

  const submit = async () => {
    setBusy(true);
    setError('');
    setResult(null);
    try {
      if (question.trim().length < 2) throw new Error('Enter a question first.');
      const data = await apiJson<Analysis>('/api/v1/analyze/esp32', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim() }),
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed.');
    } finally { setBusy(false); }
  };

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="brand-mark">C<span>49</span></div>
        <div className="brand-text"><strong>COMP4990</strong><small>ESP32 video understanding</small></div>
        <div className="header-right">
          <span className="project-version">MVP · v0.2</span>
          <span className={`mode-pill ${backendMode === 'ollama' ? 'mode-live' : ''}`}>
            {backendMode === 'ollama' ? 'VLM configured' : backendMode === 'mock' ? 'Mock AI mode' : 'API ' + backendMode}
          </span>
        </div>
      </header>
      <main className="main-content">
        <div className="intro">
          <div>
            <p className="eyebrow">CAPSTONE · ESP32-S3 CAMERA INTEGRATION</p>
            <h1>Observe. Ask. Understand.</h1>
            <p>ESP32 camera snapshots with a bounded, recent evidence window and on-demand visual question answering.</p>
          </div>
          <div className="intro-tag"><span className="pulse"></span> On-demand analysis</div>
        </div>
        <div className="workspace">
          <section className="panel preview-panel">
            <div className="panel-top">
              <div><h2>ESP32 camera</h2><p>Incoming snapshots from your Wi-Fi camera bridge</p></div>
              <span className="subtle">01 / CAMERA</span>
            </div>
            <div className="video-box">
              {espPreview && espStatus?.online && espImage ? (
                <img className="video" src={espImage} alt="Latest ESP32 JPEG snapshot" onError={() => setError('Could not fetch the latest ESP32 frame.')} />
              ) : (
                <div className="empty-preview">
                  <div className="preview-symbol">▣</div>
                  <strong>{espStatus?.online ? 'ESP32 is connected' : 'Waiting for ESP32 bridge'}</strong>
                  <span>{espStatus?.online ? 'Start preview to view incoming snapshots.' : 'Run the Windows bridge to send JPEG snapshots to this server.'}</span>
                </div>
              )}
              <div className="video-overlay">
                <span className="video-label">ESP32-S3 · SAMPLED JPEG</span>
                <span className={`record-indicator ${espStatus?.online ? 'connected' : ''}`}>
                  {espStatus?.online ? 'RECEIVING' : 'OFFLINE'}
                </span>
              </div>
            </div>
            <div className="source-actions">
              <button className="primary-btn" onClick={() => setEspPreview(value => !value)} disabled={!espStatus?.online}>
                {espPreview ? '■ Stop preview' : '▣ Start preview'}
              </button>
              <span className="muted-small">Preview only. The external bridge keeps collecting until stopped separately.</span>
            </div>
            <div className="metrics">
              <div><span>Recent frames</span><strong>{espStatus?.frame_count ?? 0} <small>/ 30</small></strong></div>
              <div><span>Buffer duration</span><strong>30s <small>max</small></strong></div>
              <div><span>Camera status</span><strong className="status-text">{espStatus?.online ? 'Connected' : 'Offline'}</strong></div>
            </div>
            <p className="small-explainer">
              Source: {espStatus?.device_id || 'unknown'} · Latest received: {displayTime(espStatus?.latest_received_at)}
              {' · '}Approx. buffer size: {Math.round((espStatus?.buffer_bytes ?? 0) / 1024)} KiB.
              {' '}These are sampled snapshots, not continuous recording.
            </p>
          </section>
          <section className="panel analysis-panel">
            <div className="panel-top">
              <div><h2>Ask about the camera</h2><p>Analyze recent ESP32 visual evidence</p></div>
              <span className="subtle">02 / ANALYZE</span>
            </div>
            <label className="field-label" htmlFor="question">YOUR QUESTION</label>
            <textarea id="question" value={question} onChange={event => setQuestion(event.target.value)} maxLength={500} rows={4} placeholder="What happened in the last 30 seconds?" />
            <div className="suggestion-row">
              <button onClick={() => setQuestion('Describe the visible objects and people.')}>Describe scene</button>
              <button onClick={() => setQuestion('Did anything change across these sampled frames?')}>Detect changes</button>
              <button onClick={() => setQuestion('Summarize what is visible, mentioning any uncertainties.')}>Summarize</button>
            </div>
            <button className="analyze-btn" disabled={busy || !espStatus?.online} onClick={() => { void submit(); }}>
              {busy ? 'Processing frames…' : 'Analyze evidence'} <span>→</span>
            </button>
            {error && <div role="alert" className="error-box"><strong>Request failed</strong><div>{error}</div></div>}
            <div className="analysis-result">
              <div className="result-heading">
                <span>ANALYSIS OUTPUT</span>
                {result && <span className={`result-mode ${result.inference_mode === 'mock' ? 'mock' : ''}`}>{result.inference_mode.toUpperCase()}</span>}
              </div>
              {result ? (
                <>
                  <p className="answer">{result.answer}</p>
                  <div className="evidence-section">
                    <strong>Evidence used</strong>
                    <div className="evidence-grid">
                      <div><span>Source</span><b>{result.source_id}</b></div>
                      <div><span>Analyzed frames</span><b>{result.evidence.frame_count} / {result.evidence.buffer_frame_count}</b></div>
                      <div><span>Time window</span><b>{displayTime(result.time_window.start)} – {displayTime(result.time_window.end)}</b></div>
                      <div><span>Processing</span><b>{result.processing_ms} ms</b></div>
                    </div>
                  </div>
                  <div className="uncertainty"><strong>Sampling limitation</strong><p>{result.uncertainty}</p></div>
                </>
              ) : (
                <div className="empty-result"><span>◇</span><p>Analysis appears here with the evidence interval and the number of frames actually examined.</p></div>
              )}
            </div>
          </section>
        </div>
        <footer><span>COMP4990 · ESP32 visual understanding</span><span>Sampled frames ≠ continuous recording · Camera network remains private</span></footer>
      </main>
    </div>
  );
}
