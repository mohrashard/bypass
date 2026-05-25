// NexusTab.tsx
// Drop this into your src/ folder and render it inside the activeTab === 'nexus' branch in App.tsx
// Replace:  <div className="text-center py-24 ...">Nexus Studio — coming soon</div>
// With:     <NexusTab />

import { useState, useEffect, useRef, useCallback } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { save } from '@tauri-apps/plugin-dialog';
import { listen } from '@tauri-apps/api/event';

// ── CodeMirror loaded via CDN in the iframe trick ─────────────────────────
// We use a textarea + a lightweight in-app editor approach that works
// without npm packages — CodeMirror 6 is injected into a hidden iframe
// so it doesn't conflict with the preview iframe.

const DEFAULT_HTML = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }

  /*
   * ✅ NEXUS ENGINE RULE: Always use 100vw / 100vh for body dimensions.
   * The engine sets the viewport to your chosen resolution (e.g. 1080x1920).
   * Never hardcode pixel widths — use vw/vh/% so it scales to any aspect ratio.
   */
  body {
    width: 100vw; height: 100vh;
    background: #0a0a0f;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Segoe UI', sans-serif;
    overflow: hidden;
  }

  .card {
    opacity: 0;
    transform: translateY(60px) scale(0.92);
    animation: rise 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.1s forwards;
    text-align: center;
  }

  @keyframes rise {
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .title {
    font-size: 5vw;         /* ✅ vw scales correctly at any resolution/aspect ratio */
    font-weight: 900;
    background: linear-gradient(135deg, #fff 0%, #a78bfa 50%, #ec4899 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    line-height: 1.1;
    letter-spacing: -0.03em;
  }

  .sub {
    margin-top: 2vh;
    font-size: 1.8vw;
    color: #6b7280;
    font-weight: 400;
    letter-spacing: 0.4em;
    text-transform: uppercase;
    opacity: 0;
    animation: fade 0.5s ease 0.7s forwards;
  }

  @keyframes fade { to { opacity: 1; } }

  .glow {
    position: absolute;
    width: 40vw; height: 40vw;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(167,139,250,0.15) 0%, transparent 70%);
    animation: pulse 3s ease-in-out infinite;
    pointer-events: none;
  }

  @keyframes pulse {
    0%, 100% { transform: scale(1); opacity: 0.5; }
    50% { transform: scale(1.1); opacity: 1; }
  }
</style>
</head>
<body>
  <div class="glow"></div>
  <div class="card">
    <div class="title">NEXUS ENGINE</div>
    <div class="sub">HTML · TO · MP4</div>
  </div>
</body>
</html>`;

// ── Types ──────────────────────────────────────────────────────────────────

interface RenderOptions {
  duration: number;
  fps: number;
  width: number;
  height: number;
  bgColor: string;
}

const PRESETS = [
  { label: '16:9 — 1080p', width: 1920, height: 1080, fps: 60, icon: '▬' },
  { label: '16:9 — 4K', width: 3840, height: 2160, fps: 30, icon: '▬' },
  { label: '9:16 — 1080p', width: 1080, height: 1920, fps: 60, icon: '▮' },
  { label: '1:1 — 1080p', width: 1080, height: 1080, fps: 60, icon: '■' },
];

// ── Component ──────────────────────────────────────────────────────────────

export default function NexusTab() {
  const [html, setHtml] = useState(DEFAULT_HTML);
  const [previewHtml, setPreviewHtml] = useState(DEFAULT_HTML);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [isRendering, setIsRendering] = useState(false);
  const [renderLog, setRenderLog] = useState<string[]>([]);
  const [lastOutput, setLastOutput] = useState<string | null>(null);
  const [editorFontSize, setEditorFontSize] = useState(13);
  const [activePreset, setActivePreset] = useState(0);

  const [renderOptions, setRenderOptions] = useState<RenderOptions>({
    duration: 5,
    fps: 60,
    width: 1920,
    height: 1080,
    bgColor: '#000000',
  });

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const previewRef = useRef<HTMLIFrameElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Live preview debounce ──────────────────────────────────────────────
  useEffect(() => {
    if (!autoRefresh) return;
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(() => {
      setPreviewHtml(html);
    }, 400);
    return () => { if (refreshTimer.current) clearTimeout(refreshTimer.current); };
  }, [html, autoRefresh]);

  // ── Tauri event listener for render progress ───────────────────────────
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    (async () => {
      unlisten = await listen<string>('nexus-stdout', (event) => {
        const raw = event.payload ?? '';
        const lines = raw.split('\n').filter(l => l.trim().length > 0);
        if (lines.length > 0) setRenderLog(prev => [...prev, ...lines]);
      });
    })();
    return () => unlisten?.();
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [renderLog]);

  // ── Preset apply ──────────────────────────────────────────────────────
  const applyPreset = (idx: number) => {
    setActivePreset(idx);
    const p = PRESETS[idx];
    setRenderOptions(prev => ({ ...prev, width: p.width, height: p.height, fps: p.fps }));
  };

  // ── Tab key in textarea ────────────────────────────────────────────────
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = textareaRef.current!;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const newVal = html.substring(0, start) + '  ' + html.substring(end);
      setHtml(newVal);
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 2;
      });
    }
  }, [html]);

  // ── Render ────────────────────────────────────────────────────────────
  const handleRender = async () => {
    if (isRendering) return;

    // Ask user where to save
    const savePath = await save({
      defaultPath: 'nexus_output.mp4',
      filters: [{ name: 'MP4 Video', extensions: ['mp4'] }],
    }).catch(() => null);

    if (!savePath) return;

    setIsRendering(true);
    setRenderLog(['', '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', '[🚀] NEXUS ENGINE STARTING...', '']);
    setLastOutput(null);

    try {
      const result = await invoke<string>('run_nexus_engine', {
        html,
        outputPath: savePath,
        optionsJson: JSON.stringify(renderOptions),
      });
      setLastOutput(result);
      setRenderLog(prev => [
        ...prev,
        '',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        `[✅] Render complete → ${result}`,
      ]);
    } catch (err) {
      setRenderLog(prev => [...prev, '', `[❌] ERROR: ${String(err)}`]);
    } finally {
      setIsRendering(false);
    }
  };

  // ── Refresh preview manually ───────────────────────────────────────────
  const forceRefresh = () => setPreviewHtml(html + ' ');

  // ── Preview scale to fit panel ─────────────────────────────────────────
  const previewScale = Math.min(
    1,
    // rough panel width / render width — CSS handles the rest
    540 / renderOptions.width,
  );
  const aspectRatio = renderOptions.height / renderOptions.width;

  return (
    <div className="flex flex-col h-full gap-0 min-h-0" style={{ fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>

      {/* ── Top bar ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800 bg-zinc-950/80 flex-shrink-0">
        <span className="text-[10px] font-bold tracking-[0.2em] text-purple-400 uppercase">Nexus Studio</span>
        <span className="text-zinc-700 text-xs">|</span>

        {/* Presets */}
        {PRESETS.map((p, i) => (
          <button
            key={i}
            onClick={() => applyPreset(i)}
            className={`text-[10px] px-2 py-0.5 rounded font-medium tracking-wide transition-colors flex items-center gap-1 ${activePreset === i
                ? 'bg-purple-600/30 text-purple-300 border border-purple-600/50'
                : 'text-zinc-500 hover:text-zinc-300 border border-transparent'
              }`}
          >
            <span className="text-[8px] opacity-70">{p.icon}</span>
            {p.label}
          </button>
        ))}

        <div className="flex-1" />

        {/* Font size */}
        <div className="flex items-center gap-1">
          <button onClick={() => setEditorFontSize(s => Math.max(10, s - 1))}
            className="text-zinc-500 hover:text-zinc-300 text-xs w-5 h-5 flex items-center justify-center rounded hover:bg-zinc-800">−</button>
          <span className="text-[10px] text-zinc-600 w-6 text-center">{editorFontSize}</span>
          <button onClick={() => setEditorFontSize(s => Math.min(20, s + 1))}
            className="text-zinc-500 hover:text-zinc-300 text-xs w-5 h-5 flex items-center justify-center rounded hover:bg-zinc-800">+</button>
        </div>

        {/* Auto-refresh toggle */}
        <label className="flex items-center gap-1.5 cursor-pointer group">
          <div
            onClick={() => setAutoRefresh(v => !v)}
            className={`relative w-7 h-4 rounded-full transition-colors ${autoRefresh ? 'bg-purple-600' : 'bg-zinc-700'}`}
          >
            <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${autoRefresh ? 'left-3.5' : 'left-0.5'}`} />
          </div>
          <span className="text-[10px] text-zinc-500 group-hover:text-zinc-400">Live</span>
        </label>

        {!autoRefresh && (
          <button onClick={forceRefresh}
            className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 transition-colors border border-zinc-700">
            ↻ Refresh
          </button>
        )}
      </div>

      {/* ── Main split layout ──────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">

        {/* ── LEFT: Code Editor ─────────────────────────────────────────── */}
        <div className="flex flex-col w-[48%] min-w-0 border-r border-zinc-800/80">

          {/* Editor header */}
          <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900/60 border-b border-zinc-800/50 flex-shrink-0">
            <div className="flex gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
              <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/60" />
            </div>
            <span className="text-[10px] text-zinc-600 ml-1 tracking-widest uppercase">index.html</span>
            <div className="flex-1" />
            <button
              onClick={() => setHtml(DEFAULT_HTML)}
              className="text-[9px] text-zinc-600 hover:text-zinc-400 transition-colors tracking-wider uppercase"
            >
              Reset
            </button>
          </div>

          {/* Textarea editor with line numbers */}
          <div className="flex-1 relative overflow-hidden bg-zinc-950">
            <div className="absolute inset-0 flex overflow-hidden">

              {/* Line numbers */}
              <LineNumbers html={html} fontSize={editorFontSize} />

              {/* Code textarea */}
              <textarea
                ref={textareaRef}
                value={html}
                onChange={e => setHtml(e.target.value)}
                onKeyDown={handleKeyDown}
                spellCheck={false}
                className="flex-1 resize-none border-none outline-none bg-transparent text-zinc-200 leading-relaxed p-3 pl-2 overflow-auto"
                style={{
                  fontSize: editorFontSize,
                  fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
                  lineHeight: '1.6',
                  caretColor: '#a78bfa',
                  tabSize: 2,
                  whiteSpace: 'pre',
                  overflowWrap: 'normal',
                }}
              />
            </div>
          </div>
        </div>

        {/* ── RIGHT: Preview + Render Panel ─────────────────────────────── */}
        <div className="flex flex-col flex-1 min-w-0 bg-zinc-950">

          {/* Preview header */}
          <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900/60 border-b border-zinc-800/50 flex-shrink-0">
            <span className="text-[10px] text-zinc-600 tracking-widest uppercase">Preview</span>
            <span className="text-zinc-700 text-[10px]">{renderOptions.width}×{renderOptions.height}</span>
            <div className="flex-1" />
            {isRendering && (
              <span className="text-[10px] text-purple-400 animate-pulse tracking-wider">● RENDERING</span>
            )}
          </div>

          {/* iframe preview — scaled to fit */}
          <div className="flex-1 relative overflow-hidden flex items-center justify-center bg-[#080810] min-h-0">
            {/* Checkerboard bg */}
            <div className="absolute inset-0 opacity-20"
              style={{
                backgroundImage: 'repeating-conic-gradient(#333 0% 25%, transparent 0% 50%)',
                backgroundSize: '20px 20px',
              }}
            />

            <PreviewFrame html={previewHtml} width={renderOptions.width} height={renderOptions.height} />
          </div>

          {/* ── Render panel ────────────────────────────────────────────── */}
          <div className="border-t border-zinc-800 bg-zinc-900/50 flex-shrink-0">

            {/* Options row */}
            <div className="flex items-center gap-3 px-3 py-2 flex-wrap">
              <RenderInput
                label="Duration (s)"
                value={renderOptions.duration}
                min={0.5} max={300} step={0.5}
                onChange={v => setRenderOptions(p => ({ ...p, duration: v }))}
              />
              <RenderInput
                label="FPS"
                value={renderOptions.fps}
                min={24} max={120} step={6}
                onChange={v => setRenderOptions(p => ({ ...p, fps: v }))}
              />
              <RenderInput
                label="Width"
                value={renderOptions.width}
                min={360} max={7680} step={2}
                onChange={v => setRenderOptions(p => ({ ...p, width: v }))}
              />
              <RenderInput
                label="Height"
                value={renderOptions.height}
                min={360} max={4320} step={2}
                onChange={v => setRenderOptions(p => ({ ...p, height: v }))}
              />

              <div className="flex flex-col gap-0.5">
                <span className="text-[9px] text-zinc-600 uppercase tracking-wider">BG Color</span>
                <div className="flex items-center gap-1.5">
                  <input
                    type="color"
                    value={renderOptions.bgColor}
                    onChange={e => setRenderOptions(p => ({ ...p, bgColor: e.target.value }))}
                    className="w-7 h-6 rounded cursor-pointer border-0 bg-transparent"
                  />
                  <span className="text-[10px] text-zinc-500 font-mono">{renderOptions.bgColor}</span>
                </div>
              </div>

              <div className="flex-1" />

              {/* Stats badge */}
              <div className="text-[9px] text-zinc-600 font-mono text-right leading-relaxed">
                <div>{(renderOptions.duration * renderOptions.fps).toLocaleString()} frames</div>
                <div>~{Math.round(renderOptions.duration * renderOptions.fps * 0.08)} MB est.</div>
              </div>
            </div>

            {/* Render button */}
            <div className="px-3 pb-3">
              <button
                onClick={handleRender}
                disabled={isRendering}
                className={`w-full py-3 rounded-xl font-bold text-sm tracking-widest uppercase transition-all flex items-center justify-center gap-2 ${isRendering
                    ? 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
                    : 'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white shadow-[0_0_24px_rgba(167,139,250,0.35)] active:scale-[0.99]'
                  }`}
              >
                {isRendering ? (
                  <>
                    <span className="animate-spin text-base">⚙️</span>
                    Rendering...
                  </>
                ) : (
                  <>
                    <span>🎬</span>
                    Render to MP4
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Bottom: Render log (collapsible) ──────────────────────────── */}
      {renderLog.length > 0 && (
        <div className="border-t border-zinc-800 bg-black flex-shrink-0" style={{ maxHeight: 180 }}>
          <div className="flex items-center gap-2 px-4 py-1.5 border-b border-zinc-900">
            <div className="flex gap-1.5">
              <div className="w-2 h-2 rounded-full bg-red-500/60" />
              <div className="w-2 h-2 rounded-full bg-yellow-500/60" />
              <div className="w-2 h-2 rounded-full bg-emerald-500/60" />
            </div>
            <span className="text-[9px] text-zinc-600 font-mono tracking-widest uppercase ml-1">Nexus Engine Output</span>
            {isRendering && <span className="ml-auto text-[9px] text-purple-400 animate-pulse tracking-wider">● LIVE</span>}
            {lastOutput && <span className="ml-auto text-[9px] text-emerald-400 tracking-wide truncate max-w-48">{lastOutput}</span>}
          </div>
          <div className="overflow-y-auto p-3 h-[140px]">
            {renderLog.map((line, i) => (
              <div key={i} className={`text-[10px] font-mono leading-5 ${line.startsWith('[✅]') ? 'text-emerald-400' :
                  line.startsWith('[❌]') ? 'text-red-400' :
                    line.startsWith('[🚀]') ? 'text-purple-400 font-semibold' :
                      line.startsWith('[🎬]') ? 'text-pink-400 font-semibold' :
                        line.startsWith('[⚙️]') ? 'text-zinc-300' :
                          line.startsWith('━') ? 'text-zinc-700' :
                            'text-zinc-500'
                }`}>
                {line || '\u00A0'}
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function LineNumbers({ html, fontSize }: { html: string; fontSize: number }) {
  const count = (html.match(/\n/g) || []).length + 1;
  return (
    <div
      className="select-none text-right pr-3 pt-3 text-zinc-700 overflow-hidden flex-shrink-0"
      style={{
        fontSize,
        fontFamily: "'JetBrains Mono', monospace",
        lineHeight: '1.6',
        minWidth: `${String(count).length * (fontSize * 0.6) + 24}px`,
        background: 'rgba(0,0,0,0.3)',
        borderRight: '1px solid rgba(255,255,255,0.04)',
      }}
    >
      {Array.from({ length: count }, (_, i) => (
        <div key={i}>{i + 1}</div>
      ))}
    </div>
  );
}

function PreviewFrame({ html, width, height }: { html: string; width: number; height: number }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.3);

  useEffect(() => {
    const update = () => {
      if (!containerRef.current) return;
      const { clientWidth, clientHeight } = containerRef.current;
      const scaleW = (clientWidth - 24) / width;
      const scaleH = (clientHeight - 24) / height;
      setScale(Math.min(scaleW, scaleH, 1));
    };
    update();
    const ro = new ResizeObserver(update);
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [width, height]);

  const blob = new Blob([html], { type: 'text/html' });
  const src = URL.createObjectURL(blob);

  return (
    <div ref={containerRef} className="absolute inset-0 flex items-center justify-center">
      <div
        style={{
          width: width,
          height: height,
          transform: `scale(${scale})`,
          transformOrigin: 'center center',
          flexShrink: 0,
          boxShadow: '0 0 0 1px rgba(255,255,255,0.06), 0 24px 80px rgba(0,0,0,0.8)',
          borderRadius: 4,
          overflow: 'hidden',
        }}
      >
        <iframe
          src={src}
          width={width}
          height={height}
          style={{ border: 'none', display: 'block', pointerEvents: 'none' }}
          sandbox="allow-scripts allow-same-origin"
          title="Nexus Preview"
        />
      </div>
    </div>
  );
}

function RenderInput({
  label, value, min, max, step, onChange
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[9px] text-zinc-600 uppercase tracking-wider">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={e => onChange(Number(e.target.value))}
        className="w-20 bg-zinc-950 border border-zinc-800 text-zinc-300 text-[11px] rounded px-2 py-1 outline-none focus:border-purple-600 font-mono"
      />
    </div>
  );
}