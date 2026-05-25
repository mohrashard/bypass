import { useState, useEffect, useRef } from 'react';
import { invoke, convertFileSrc } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import { listen } from '@tauri-apps/api/event';
import NexusTab from './NexusTab';

const NOISE_PATTERNS = [
  /UserWarning/, /FutureWarning/, /DeprecationWarning/,
  /warnings\.warn/, /Already up to date/, /^\s*warnings\.warn\(/,
  /will be changed to use/, /TorchCodec/, /We recommend that you port/,
];
function isNoisyLine(line: string): boolean {
  return NOISE_PATTERNS.some((re) => re.test(line));
}

const OPTIONS_META: Record<string, string> = {
  extractMp3: '🎵 Extract MP3 Audio',
  removeSilence: '✂️ Remove Dead Air',
  aiBroll: '🎥 AI Contextual B-Roll', // 👈 NEW
  burnCaptions: '📝 Burn Viral Captions',
  studioAudio: '🎙️ Studio Audio Enhancer',
  maskEngine: '🎭 Video Masking Engine', // <-- Add this line
  blurBackground: '🌫️ AI Background FX',
  autoZoom: '🧠 Semantic Smart-Zooms',
  makeVertical: '📱 Face-Tracking Vertical',
  cinematicColor: '🎨 Cinematic Color Grade',
  bottomGlow: '🌌 Cinematic Bottom Glow',
  autoTransitions: '✨ Auto Sentence Transitions',
};

export default function App() {
  const [activeTab, setActiveTab] = useState<'utility' | 'nexus'>('utility');
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPreviewVertical, setIsPreviewVertical] = useState(false);
  const [isExportingOverlay, setIsExportingOverlay] = useState(false);
  const [terminalLines, setTerminalLines] = useState<string[]>([]);
  const consoleEndRef = useRef<HTMLDivElement>(null);

  const [options, setOptions] = useState({
    extractMp3: false,
    maskEngine: false,
    enable3dDepth: false, // 👈 NEW

    // NEW: Mask State with Scale
    maskRatio: '4:5',
    maskBorderRadius: 18,
    maskScale: 85, // 👈 NEW: Default to 85%
    maskBgMode: 'image',
    maskBgColor: '#09090b',
    maskBgImagePath: '',
    maskBgImageName: '',
    removeSilence: true,
    aiBroll: false, // 👈 NEW
    burnCaptions: false,
    studioAudio: false,
    blurBackground: false,
    autoZoom: false,
    zoomIntensity: 1.15,
    zoomSpeed: 0.5,
    makeVertical: false,
    cinematicColor: false,
    bottomGlow: false,
    autoTransitions: false,
    glowColor: '#000000',

    captionFont: 'Montserrat',
    captionPrimaryStyle: 'p-clean-white',
    captionSecondaryStyle: 's-hormozi-yellow',
    captionMixedStyle: false,

    // ── NEW: Sinhala Template Defaults ──
    siMainStyle: 'si-main-blue',
    siPrimaryStyle: 'si-pri-silver',
    siSecondaryStyle: 'si-sec-gold',

    captionAnimation: 'spring-up',
    captionLanguage: 'en',
    captionBottomPercent: 22,
    geminiApiKey: '',

    bgMode: 'blur',
    bgColor: '#09090b',
    bgImagePath: '',
    bgImageName: '',
    keyingMode: 'ai',
    colorGradeStyle: 'pro-max',

    exportCaptionOverlay: false,
    greenScreenOverlay: true,
  });

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    (async () => {
      unlisten = await listen<string>('engine-stdout', (event) => {
        const raw = event.payload ?? '';
        const incoming = raw.split('\n').filter(
          (l) => l.trim().length > 0 && !isNoisyLine(l)
        );
        if (incoming.length > 0) setTerminalLines((prev) => [...prev, ...incoming]);
      });
    })();
    return () => unlisten?.();
  }, []);

  useEffect(() => {
    consoleEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [terminalLines]);

  const handleSelectFile = async () => {
    const selected = await open({
      multiple: false,
      filters: [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm'] }],
    }).catch(() => null);
    if (selected && typeof selected === 'string') {
      setSelectedFilePath(selected);
      setSelectedFileName(selected.split(/[\\/]/).pop() ?? 'video.mp4');
      setTerminalLines([]);
    }
  };

  const handleSelectBgImage = async () => {
    const selected = await open({
      multiple: false,
      filters: [{ name: 'Image', extensions: ['jpg', 'jpeg', 'png', 'webp'] }],
    }).catch(() => null);
    if (selected && typeof selected === 'string') {
      setOptions((prev) => ({
        ...prev,
        bgImagePath: selected,
        bgImageName: selected.split(/[\\/]/).pop() ?? 'image.jpg',
      }));
    }
  };

  const handleSelectMaskBgImage = async () => {
    const selected = await open({
      multiple: false,
      filters: [{ name: 'Image', extensions: ['jpg', 'jpeg', 'png', 'webp'] }],
    }).catch(() => null);
    if (selected && typeof selected === 'string') {
      setOptions((prev) => ({
        ...prev,
        maskBgImagePath: selected,
        maskBgImageName: selected.split(/[\\/]/).pop() ?? 'image.jpg',
      }));
    }
  };

  const toggleOption = (key: keyof typeof options) => {
    setOptions((prev) => {
      const val = prev[key];
      if (typeof val === 'boolean') return { ...prev, [key]: !val };
      return prev;
    });
  };

  const handleRunPipeline = async () => {
    if (!selectedFilePath || isProcessing) return;
    setIsProcessing(true);
    setTerminalLines(['Initializing Python Engine...']);
    try {
      await invoke<string>('run_python_engine', {
        videoPath: selectedFilePath,
        processType: 'pipeline',
        optionsJson: JSON.stringify({ ...options, exportCaptionOverlay: false }),
      });
    } catch (error) {
      setTerminalLines((prev) => [...prev, '', `❌ ERROR: ${String(error)}`]);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleExportOverlay = async () => {
    if (!selectedFilePath || isExportingOverlay || isProcessing) return;
    if (!options.burnCaptions) {
      setTerminalLines((prev) => [...prev, '⚠️ Enable "Burn Viral Captions" first so the engine knows which style to export.']);
      return;
    }
    setIsExportingOverlay(true);
    setTerminalLines((prev) => [...prev,
      '',
      '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
    `[📦] Starting CapCut overlay export (${options.captionLanguage === 'si' ? 'Sinhala' : 'English'})...`,
    ]);
    try {
      await invoke<string>('run_python_engine', {
        videoPath: selectedFilePath,
        processType: 'pipeline',
        optionsJson: JSON.stringify({
          ...options,
          removeSilence: false,
          studioAudio: false,
          autoZoom: false,
          cinematicColor: false,
          blurBackground: false,
          bottomGlow: false,
          burnCaptions: false,
          exportCaptionOverlay: true,
        }),
      });
    } catch (error) {
      setTerminalLines((prev) => [...prev, '', `❌ ERROR: ${String(error)}`]);
    } finally {
      setIsExportingOverlay(false);
    }
  };

  const activeCount = Object.entries(options)
    .filter(([k, v]) => OPTIONS_META[k] && v === true).length;

  const isBusy = isProcessing || isExportingOverlay;

  return (
    <main className="min-h-screen text-white font-sans flex flex-col bg-[#09090b]">

      <nav className="border-b border-zinc-800 bg-zinc-950 px-4 py-3 flex justify-center gap-3">
        {([['utility', '⚙️ Utility Pipe', 'emerald'], ['nexus', '🧠 Nexus Studio', 'purple']] as const).map(
          ([tab, label, color]) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`px-6 py-2 rounded-lg font-medium text-sm transition-all ${activeTab === tab
                ? color === 'emerald'
                  ? 'bg-emerald-600 text-white shadow-[0_0_12px_rgba(5,150,105,0.4)]'
                  : 'bg-purple-600 text-white shadow-[0_0_12px_rgba(147,51,234,0.4)]'
                : 'bg-zinc-900 text-zinc-400 hover:text-white hover:bg-zinc-800'}`}>
              {label}
            </button>
          )
        )}
      </nav>

      {activeTab === 'utility' ? (
        <div className="flex-1 p-8 flex justify-center overflow-y-auto">
          <div className="w-full max-w-3xl space-y-5">
            <div className="text-center space-y-1">
              <h1 className="text-4xl font-bold tracking-tight">The Utility Pipe</h1>
              <p className="text-zinc-400 text-sm">Zero timeline. 100% local processing.</p>
            </div>

            <div onClick={handleSelectFile}
              className={`border-2 border-dashed rounded-xl p-10 flex flex-col items-center justify-center cursor-pointer transition-colors ${selectedFilePath
                ? 'border-emerald-500 bg-emerald-500/10'
                : 'border-zinc-700 bg-zinc-900 hover:border-zinc-500 hover:bg-zinc-800'}`}>
              {selectedFilePath ? (
                <div className="text-center space-y-1">
                  <span className="text-4xl">🎬</span>
                  <p className="font-semibold text-emerald-400">{selectedFileName}</p>
                  <p className="text-[11px] text-zinc-500 font-mono mt-1 break-all max-w-md">{selectedFilePath}</p>
                </div>
              ) : (
                <div className="text-center space-y-2">
                  <span className="text-4xl">📁</span>
                  <p className="font-medium">Click to select your raw video</p>
                  <p className="text-sm text-zinc-500">MP4, MOV, MKV, WEBM</p>
                </div>
              )}
            </div>

            <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800">
              <div className="flex items-center justify-between mb-4">
                <p className="text-xs font-semibold text-zinc-400 uppercase tracking-widest">Processing stages</p>
                <span className="text-xs text-zinc-500">{activeCount} selected</span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(OPTIONS_META).map(([key, label]) => (
                  <div key={key} className="flex flex-col gap-2">
                    <div className={`flex items-center justify-between p-3 rounded-lg border transition-colors ${options[key as keyof typeof options]
                      ? 'bg-emerald-950/50 border-emerald-700/50'
                      : 'bg-zinc-950 border-zinc-800 hover:border-zinc-600'}`}>
                      <label className="flex items-center gap-3 cursor-pointer flex-1">
                        <input type="checkbox"
                          checked={options[key as keyof typeof options] as boolean}
                          onChange={() => toggleOption(key as keyof typeof options)}
                          className="w-4 h-4 accent-emerald-500 shrink-0" />
                        <span className="text-sm font-medium text-zinc-300">{label}</span>
                      </label>
                      {key === 'bottomGlow' && options.bottomGlow && (
                        <input type="color" value={options.glowColor as string}
                          onChange={(e) => setOptions((prev) => ({ ...prev, glowColor: e.target.value }))}
                          className="w-7 h-7 p-0 border-0 rounded cursor-pointer bg-transparent shrink-0" />
                      )}
                    </div>

                    {key === 'autoZoom' && options.autoZoom && (
                      <div className="flex flex-col gap-3 p-3 ml-2 rounded-lg bg-zinc-900/80 border border-zinc-800">
                        <div className="text-xs text-zinc-500 italic pb-2 border-b border-zinc-800/50">
                          Detects high-impact words and triggers a smooth cinematic push-in.
                        </div>
                        <div className="flex items-center justify-between pt-1">
                          <span className="text-xs text-zinc-400 font-medium">Push-in Depth</span>
                          <select value={options.zoomIntensity}
                            onChange={(e) => setOptions((prev) => ({ ...prev, zoomIntensity: parseFloat(e.target.value) }))}
                            className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-emerald-500">
                            <option value="1.10">Subtle (10%)</option>
                            <option value="1.15">Standard (15%)</option>
                            <option value="1.25">Aggressive (25%)</option>
                          </select>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-zinc-400 font-medium">Zoom Speed</span>
                          <select value={options.zoomSpeed}
                            onChange={(e) => setOptions((prev) => ({ ...prev, zoomSpeed: parseFloat(e.target.value) }))}
                            className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-emerald-500">
                            <option value="0.25">⚡ Instant Snap (0.25s)</option>
                            <option value="0.5">🚀 Snappy (0.5s)</option>
                            <option value="0.75">🎬 Standard (0.75s)</option>
                            <option value="1.5">🌊 Slow Creep (1.5s)</option>
                          </select>
                        </div>
                      </div>
                    )}

                    {key === 'blurBackground' && options.blurBackground && (
                      <div className="flex flex-col gap-3 p-3 ml-2 rounded-lg bg-zinc-900/80 border border-zinc-800">
                        <div className="flex items-center justify-between pb-2 mb-2 border-b border-zinc-800/50">
                          <span className="text-xs text-purple-400 font-semibold uppercase tracking-wider">Masking Engine</span>
                          <select value={options.keyingMode}
                            onChange={(e) => setOptions((prev) => ({ ...prev, keyingMode: e.target.value }))}
                            className="bg-purple-950/30 border border-purple-900/50 text-purple-300 text-xs rounded p-1 outline-none focus:border-purple-500 font-medium">
                            <option value="ai">🧠 AI Auto-Detect</option>
                            <option value="chroma">🟩 Green Screen</option>
                          </select>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-zinc-400 font-medium">FX Mode</span>
                          <select value={options.bgMode}
                            onChange={(e) => setOptions((prev) => ({ ...prev, bgMode: e.target.value }))}
                            className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-emerald-500">
                            <option value="blur">DSLR Depth Blur</option>
                            <option value="replace">Solid Studio Backdrop</option>
                            <option value="image">Custom Image Upload</option>
                          </select>
                        </div>
                        {options.bgMode === 'replace' && (
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-zinc-400 font-medium">Studio Color</span>
                            <input type="color" value={options.bgColor}
                              onChange={(e) => setOptions((prev) => ({ ...prev, bgColor: e.target.value }))}
                              className="w-6 h-6 p-0 border-0 rounded cursor-pointer bg-transparent" />
                          </div>
                        )}
                        {options.bgMode === 'image' && (
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-zinc-400 font-medium">Background File</span>
                            <button onClick={handleSelectBgImage}
                              className={`text-xs px-3 py-1.5 rounded border transition-colors max-w-[140px] truncate ${options.bgImagePath
                                ? 'bg-emerald-950/50 border-emerald-700/50 text-emerald-400'
                                : 'bg-zinc-950 border-zinc-700 hover:border-zinc-500 text-zinc-300'}`}>
                              {options.bgImageName || 'Choose Image...'}
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {key === 'burnCaptions' && options.burnCaptions && (
                      <div className="flex flex-col gap-3 p-3 ml-2 rounded-lg bg-zinc-900/80 border border-zinc-800">

                        <div className="flex items-center justify-between pb-2 mb-2 border-b border-zinc-800/50">
                          <span className="text-xs text-purple-400 font-semibold uppercase tracking-wider">Language Engine</span>
                          <select value={options.captionLanguage}
                            onChange={(e) => setOptions((prev) => ({ ...prev, captionLanguage: e.target.value }))}
                            className="bg-purple-950/30 border border-purple-900/50 text-purple-300 text-xs rounded p-1 outline-none focus:border-purple-500 font-medium">
                            <option value="en">🇺🇸 English (Whisper)</option>
                            <option value="si">🇱🇰 Sinhala (Gemini+Whisper)</option>
                          </select>
                        </div>

                        {options.captionLanguage === 'si' && (
                          <div className="flex flex-col gap-1 pb-2 mb-2 border-b border-zinc-800/50">
                            <span className="text-xs text-orange-400 font-semibold uppercase tracking-wider">Gemini API Key (Required)</span>
                            <input type="password" placeholder="Paste Google AI Studio Key..."
                              value={options.geminiApiKey}
                              onChange={(e) => setOptions((prev) => ({ ...prev, geminiApiKey: e.target.value }))}
                              className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1.5 outline-none focus:border-orange-500 w-full" />
                          </div>
                        )}

                        {/* ── ENGLISH TEMPLATES ── */}
                        {options.captionLanguage === 'en' && (
                          <>
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-zinc-400 font-medium">Typography</span>
                              <select value={options.captionFont}
                                onChange={(e) => setOptions((prev) => ({ ...prev, captionFont: e.target.value }))}
                                className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-emerald-500">
                                <option value="Montserrat">Montserrat (Modern)</option>
                                <option value="Anton">Anton (Bold/Blocky)</option>
                                <option value="Poppins">Poppins (Clean)</option>
                                <option value="Bangers">Bangers (Comic/Hype)</option>
                                <option value="Oswald">Oswald (Condensed)</option>
                              </select>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-zinc-400 font-medium">Base Style</span>
                              <select value={options.captionPrimaryStyle}
                                onChange={(e) => setOptions((prev) => ({ ...prev, captionPrimaryStyle: e.target.value }))}
                                className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-emerald-500">
                                <option value="p-clean-white">1. Crisp Clean White</option>
                                <option value="p-glass-silver">2. Glass Silver</option>
                                <option value="p-heavy-stroke">3. Heavy Stroke Black</option>
                                <option value="p-soft-yellow">4. Soft Pastel Yellow</option>
                                <option value="p-neon-base">5. Neon Ambient White</option>
                              </select>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-zinc-400 font-medium">Highlight Style</span>
                              <select value={options.captionSecondaryStyle}
                                onChange={(e) => setOptions((prev) => ({ ...prev, captionSecondaryStyle: e.target.value }))}
                                className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-emerald-500">
                                <option value="s-hormozi-yellow">1. Hormozi Bold Yellow</option>
                                <option value="s-electric-teal">2. Electric Teal</option>
                                <option value="s-crimson-red">3. Aggressive Crimson</option>
                                <option value="s-cyber-purple">4. Cyberpunk Purple</option>
                                <option value="s-luxury-gold">5. Luxury Metallic Gold</option>
                                <option value="none">Disable Highlights</option>
                              </select>
                            </div>
                            <div className="flex items-center justify-between mt-2 pt-2 border-t border-zinc-800/50">
                              <div className="flex flex-col">
                                <span className="text-xs text-zinc-400 font-medium">Kinematic Mixed Style</span>
                                <span className="text-[10px] text-zinc-500">Auto-styles words by role (TikTok style)</span>
                              </div>
                              <label className="relative inline-flex items-center cursor-pointer">
                                <input type="checkbox" className="sr-only peer"
                                  checked={options.captionMixedStyle}
                                  onChange={() => toggleOption('captionMixedStyle')} 
                                />
                                <div className="w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
                              </label>
                            </div>
                          </>
                        )}

                        {/* ── SINHALA TEMPLATES ── */}
                        {options.captionLanguage === 'si' && (
                          <>
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-zinc-400 font-medium">Main (Sinhala)</span>
                              <select value={options.siMainStyle}
                                onChange={(e) => setOptions((prev) => ({ ...prev, siMainStyle: e.target.value }))}
                                className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-emerald-500 max-w-[140px]">
                                <option value="si-main-blue">1. Dynamic Blue Glow</option>
                                <option value="si-main-emerald">2. Professional Emerald</option>
                                <option value="si-main-crimson">3. Deep Crimson Impact</option>
                                <option value="si-main-amber">4. Warm Storyteller Amber</option>
                                <option value="si-main-purple">5. Cyberpunk Purple</option>
                                <option value="si-main-white">6. Clean White Shadow</option>
                              </select>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-zinc-400 font-medium">Primary (Eng)</span>
                              <select value={options.siPrimaryStyle}
                                onChange={(e) => setOptions((prev) => ({ ...prev, siPrimaryStyle: e.target.value }))}
                                className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-emerald-500 max-w-[140px]">
                                <option value="si-pri-silver">1. Glass Silver Glow</option>
                                <option value="si-pri-gold">2. Subtle Luxury Gold</option>
                                <option value="si-pri-cyan">3. Electric Cyan High</option>
                                <option value="si-pri-magenta">4. Sharp Magenta Pop</option>
                                <option value="si-pri-slate">5. Modern Dark Slate</option>
                                <option value="si-pri-neon-green">6. High-Vis Neon Green</option>
                              </select>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-zinc-400 font-medium">Secondary (#)</span>
                              <select value={options.siSecondaryStyle}
                                onChange={(e) => setOptions((prev) => ({ ...prev, siSecondaryStyle: e.target.value }))}
                                className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-emerald-500 max-w-[140px]">
                                <option value="si-sec-gold">1. Hormozi Bold Yellow</option>
                                <option value="si-sec-red">2. Alert Urgent Red</option>
                                <option value="si-sec-lime">3. Positive Lime Green</option>
                                <option value="si-sec-pink">4. High-Contrast Pink</option>
                                <option value="si-sec-aqua">5. Deep Aqua Blue</option>
                                <option value="si-sec-white">6. Pure Glowing White</option>
                              </select>
                            </div>
                          </>
                        )}

                        <div className="flex items-center justify-between border-t border-zinc-800/50 pt-2 mt-1">
                          <span className="text-xs text-emerald-400 font-semibold uppercase tracking-wider">Motion In</span>
                          <select value={options.captionAnimation}
                            onChange={(e) => setOptions((prev) => ({ ...prev, captionAnimation: e.target.value }))}
                            className="bg-emerald-950/30 border border-emerald-900/50 text-emerald-300 text-xs rounded p-1 outline-none focus:border-emerald-500 font-medium">
                            <option value="spring-up">🚀 Spring Pop (Hormozi)</option>
                            <option value="slide-up">🌊 Smooth Slide Up</option>
                            <option value="slide-right">⚡ Fast Slide Right</option>
                            <option value="none">⏹️ Hard Cut (None)</option>
                          </select>
                        </div>

                        {/* ── NEW: CAPTION POSITION PREVIEW ── */}
                        <div className="border-t border-zinc-800/50 pt-3 mt-2 mb-2 flex flex-col gap-2">

                          <div className="flex items-center justify-between mb-1">
                            <div className="flex items-center gap-3">
                              <span className="text-xs text-sky-400 font-semibold uppercase tracking-wider">Position Preview</span>
                              {/* ── NEW: Aspect Ratio Toggle Button ── */}
                              <button
                                onClick={(e) => {
                                  e.preventDefault();
                                  setIsPreviewVertical(!isPreviewVertical);
                                }}
                                className="px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] text-zinc-300 transition-colors border border-zinc-600 flex items-center gap-1.5 shadow-sm active:scale-95"
                              >
                                {isPreviewVertical ? '📱 9:16 View' : '🖥️ 16:9 View'}
                              </button>
                            </div>
                            <span className="text-xs text-zinc-400 font-mono">{options.captionBottomPercent}% from bottom</span>
                          </div>

                          {/* ── UPDATED: Dynamic Container that morphs shape ── */}
                          <div className={`relative bg-black rounded-lg overflow-hidden border border-zinc-700 group pointer-events-none mx-auto transition-all duration-300 ease-in-out ${isPreviewVertical ? 'w-48 h-[340px]' : 'w-full h-44'
                            }`}>
                            {selectedFilePath ? (
                              <video
                                key={selectedFilePath}
                                src={convertFileSrc(selectedFilePath)}
                                className="w-full h-full object-cover opacity-60"
                                preload="auto"
                                muted
                                playsInline
                                onLoadedMetadata={(e) => {
                                  e.currentTarget.currentTime = 2.0;
                                }}
                              />
                            ) : (
                              <div className="w-full h-full flex flex-col items-center justify-center text-zinc-600 space-y-2">
                                <span className="text-2xl">🖼️</span>
                                <span className="text-[10px] uppercase tracking-wider font-semibold">Awaiting Video</span>
                              </div>
                            )}

                            {/* The Floating Preview Tag */}
                            <div
                              className="absolute left-0 right-0 flex justify-center w-full transition-all duration-75 ease-out"
                              style={{ bottom: `${options.captionBottomPercent}%` }}
                            >
                              <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-600 text-white px-4 py-1.5 rounded-md shadow-2xl font-bold text-[11px] uppercase tracking-widest whitespace-nowrap">
                                {options.captionLanguage === 'si' ? 'සිංහල කැප්ෂන්' : 'Viral Caption Preview'}
                              </div>
                            </div>
                          </div>

                          <div className="flex items-center gap-3 mt-2">
                            <span className="text-[10px] text-zinc-500 font-medium tracking-wider">BOTTOM</span>
                            <input
                              type="range" min="5" max="90"
                              value={options.captionBottomPercent}
                              onChange={(e) => setOptions((prev) => ({ ...prev, captionBottomPercent: parseInt(e.target.value) }))}
                              className="flex-1 h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-sky-500"
                            />
                            <span className="text-[10px] text-zinc-500 font-medium tracking-wider">TOP</span>
                          </div>
                        </div>

                        <div className="flex items-center justify-between border-t border-zinc-800/50 pt-3 mt-2 mb-2">
                          <div className="flex flex-col">
                            <span className="text-xs text-purple-400 font-semibold uppercase tracking-wider">3D Depth Effect</span>
                            <span className="text-[10px] text-zinc-500">Places text behind the subject</span>
                          </div>
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input type="checkbox" className="sr-only peer"
                              checked={options.enable3dDepth}
                              onChange={() => toggleOption('enable3dDepth')}
                            />
                            <div className="w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-500"></div>
                          </label>
                        </div>

                        <div className="border-t border-zinc-800/50 pt-3 mt-1 flex flex-col gap-2">
                          <label className="flex items-center gap-2 cursor-pointer mb-1 group">
                            <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${options.greenScreenOverlay ? 'bg-emerald-500 border-emerald-500' : 'bg-zinc-900 border-zinc-700 group-hover:border-zinc-500'
                              }`}>
                              {options.greenScreenOverlay && <span className="text-white text-[10px]">✓</span>}
                            </div>
                            <span className="text-xs text-zinc-300 font-medium">Use Green Screen (Highly Recommended)</span>
                            <input type="checkbox" className="hidden"
                              checked={options.greenScreenOverlay}
                              onChange={() => toggleOption('greenScreenOverlay')}
                            />
                          </label>

                          <p className="text-xs text-zinc-500 leading-relaxed">
                            {options.greenScreenOverlay ? (
                              <>Export captions as a fast <span className="text-emerald-400 font-medium">.mp4 (Green Screen)</span> — remove background in CapCut using Chroma Key.</>
                            ) : (
                              <>Export captions as a <span className="text-zinc-300 font-medium">transparent .mov (ProRes)</span> — drag it above your footage. CapCut Proxy destroys alpha channel.</>
                            )}
                          </p>
                          <button
                            onClick={handleExportOverlay}
                            disabled={!selectedFilePath || isBusy}
                            className={`w-full py-2.5 rounded-lg font-semibold text-sm transition-all flex items-center justify-center gap-2 ${isBusy || !selectedFilePath
                              ? 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
                              : options.greenScreenOverlay
                                ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-[0_0_16px_rgba(16,185,129,0.3)] active:scale-[0.99]'
                                : 'bg-sky-600 hover:bg-sky-500 text-white shadow-[0_0_16px_rgba(14,165,233,0.3)] active:scale-[0.99]'
                              }`}
                          >
                            {isExportingOverlay ? (
                              <>
                                <span className="animate-spin">⚙️</span>
                                {options.greenScreenOverlay ? 'Rendering Green Screen...' : 'Rendering ProRes overlay…'}
                              </>
                            ) : (
                              <>
                                <span>📦</span>
                                {options.greenScreenOverlay ? 'Export for CapCut (.mp4 Green Screen)' : 'Export for CapCut (.mov transparent)'}
                              </>
                            )}
                          </button>
                          {!selectedFilePath && (
                            <p className="text-[10px] text-zinc-600 text-center">Select a video file first</p>
                          )}
                        </div>

                      </div>
                    )}

                    {key === 'aiBroll' && options.aiBroll && (
                      <div className="flex flex-col gap-3 p-3 ml-2 rounded-lg bg-zinc-900/80 border border-zinc-800">
                        <div className="text-xs text-zinc-400 italic border-b border-zinc-800/50 pb-2">
                          Gemini acts as the AI Director: it scans your audio, finds the highest-impact moments, and generates cinematic kinetic typography B-roll overlays exactly when needed.
                        </div>

                        {/* Gemini Key is strictly required for this to work */}
                        <div className="flex flex-col gap-1 mt-1">
                          <span className="text-xs text-orange-400 font-semibold uppercase tracking-wider">Gemini API Key (Required)</span>
                          <input type="password" placeholder="Paste Google AI Studio Key..."
                            value={options.geminiApiKey}
                            onChange={(e) => setOptions((prev) => ({ ...prev, geminiApiKey: e.target.value }))}
                            className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1.5 outline-none focus:border-orange-500 w-full" />
                        </div>
                      </div>
                    )}

                    {key === 'maskEngine' && options.maskEngine && (
                      <div className="flex flex-col gap-3 p-3 ml-2 rounded-lg bg-zinc-900/80 border border-zinc-800">

                        <div className="flex items-center justify-between mb-1 border-b border-zinc-800/50 pb-2">
                          <span className="text-xs text-sky-400 font-semibold uppercase tracking-wider">Mask Preview</span>
                        </div>

                        {/* DYNAMIC CSS PREVIEW CANVAS */}
                        <div
                          className="relative rounded-lg overflow-hidden border border-zinc-700 mx-auto w-full max-w-[220px] flex items-center justify-center transition-all duration-300 shadow-inner"
                          style={{
                            aspectRatio: '9/16', // Standard vertical canvas representation
                            backgroundColor: options.maskBgMode === 'color' ? options.maskBgColor : '#000',
                            backgroundImage: options.maskBgMode === 'image' && options.maskBgImagePath ? `url(${convertFileSrc(options.maskBgImagePath)})` : 'none',
                            backgroundSize: 'cover',
                            backgroundPosition: 'center'
                          }}
                        >
                          {/* INNER MASKED VIDEO (With Dynamic Scale & Border Radius) */}
                          <div
                            className="relative overflow-hidden shadow-[0_0_25px_rgba(0,0,0,0.6)] transition-all duration-300 flex items-center justify-center bg-zinc-800"
                            style={{
                              aspectRatio: options.maskRatio.replace(':', '/'),
                              height: `${options.maskScale}%`, // 👈 UPDATED
                              borderRadius: `${options.maskBorderRadius}px`
                            }}
                          >
                            {selectedFilePath ? (
                              <video
                                key={selectedFilePath}
                                src={convertFileSrc(selectedFilePath)}
                                className="w-full h-full object-cover"
                                autoPlay muted loop playsInline
                              />
                            ) : (
                              <span className="text-3xl opacity-40">🎬</span>
                            )}
                          </div>
                        </div>

                        {/* TOOL CONTROLS */}
                        <div className="flex items-center justify-between mt-3">
                          <span className="text-xs text-zinc-400 font-medium">Aspect Ratio</span>
                          <select value={options.maskRatio}
                            onChange={(e) => setOptions((prev) => ({ ...prev, maskRatio: e.target.value }))}
                            className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-sky-500 font-mono">
                            <option value="9:16">9:16 (Vertical)</option>
                            <option value="1:1">1:1 (Square)</option>
                            <option value="4:5">4:5 (Portrait)</option>
                            <option value="16:9">16:9 (Landscape)</option>
                            <option value="4:3">4:3 (Classic)</option>
                          </select>
                        </div>

                        {/* Mask Size Slider */}
                        <div className="flex items-center gap-3 mt-3">
                          <span className="text-xs text-zinc-400 font-medium min-w-[80px]">Mask Size</span>
                          <input
                            type="range" min="30" max="100"
                            value={options.maskScale}
                            onChange={(e) => setOptions((prev) => ({ ...prev, maskScale: parseInt(e.target.value) }))}
                            className="flex-1 h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-sky-500"
                          />
                          <span className="text-xs text-zinc-500 font-mono w-8 text-right">{options.maskScale}%</span>
                        </div>

                        {/* Border Radius Slider */}
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-zinc-400 font-medium min-w-[80px]">Corner Radius</span>
                          <input
                            type="range" min="0" max="150"
                            value={options.maskBorderRadius}
                            onChange={(e) => setOptions((prev) => ({ ...prev, maskBorderRadius: parseInt(e.target.value) }))}
                            className="flex-1 h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-sky-500"
                          />
                          <span className="text-xs text-zinc-500 font-mono w-8 text-right">{options.maskBorderRadius}px</span>
                        </div>

                        <div className="flex items-center justify-between border-t border-zinc-800/50 pt-2 mt-1">
                          <span className="text-xs text-zinc-400 font-medium">Background Layer</span>
                          <select value={options.maskBgMode}
                            onChange={(e) => setOptions((prev) => ({ ...prev, maskBgMode: e.target.value }))}
                            className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-sky-500">
                            <option value="color">Solid Color</option>
                            <option value="image">Upload Image</option>
                          </select>
                        </div>

                        {options.maskBgMode === 'color' ? (
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] text-zinc-500">Canvas Color</span>
                            <input type="color" value={options.maskBgColor}
                              onChange={(e) => setOptions((prev) => ({ ...prev, maskBgColor: e.target.value }))}
                              className="w-6 h-6 p-0 border-0 rounded cursor-pointer bg-transparent" />
                          </div>
                        ) : (
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] text-zinc-500">Canvas Image</span>
                            <button onClick={handleSelectMaskBgImage}
                              className={`text-[10px] px-3 py-1.5 rounded border transition-colors max-w-[140px] truncate font-medium ${options.maskBgImagePath
                                ? 'bg-sky-950/50 border-sky-700/50 text-sky-400'
                                : 'bg-zinc-950 border-zinc-700 hover:border-zinc-500 text-zinc-300'}`}>
                              {options.maskBgImageName || 'Select File...'}
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {key === 'cinematicColor' && options.cinematicColor && (
                      <div className="flex flex-col gap-3 p-3 ml-2 rounded-lg bg-zinc-900/80 border border-zinc-800">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-zinc-400 font-medium">LUT Profile</span>
                          <select value={options.colorGradeStyle}
                            onChange={(e) => setOptions((prev) => ({ ...prev, colorGradeStyle: e.target.value }))}
                            className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-emerald-500">
                            <option value="pro-max">📱 iPhone Pro Max (Natural)</option>
                            <option value="neon-blue">🟦 Neon Blue Studio (Moody)</option>
                            <option value="cyber-warm">🟧 Hollywood Teal & Orange</option>
                          </select>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <button onClick={handleRunPipeline}
              disabled={!selectedFilePath || isBusy || activeCount === 0}
              className="w-full py-4 rounded-xl font-bold text-base bg-emerald-600 hover:bg-emerald-500 active:scale-[0.99] shadow-[0_0_20px_rgba(5,150,105,0.35)] disabled:opacity-40 disabled:cursor-not-allowed transition-all">
              {isProcessing ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="animate-spin">⚙️</span> Processing locally…
                </span>
              ) : 'RENDER VIDEO'}
            </button>

            {terminalLines.length > 0 && (
              <div className="bg-black border border-zinc-800 rounded-xl overflow-hidden">
                <div className="px-4 py-2 border-b border-zinc-800 flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
                  <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/70" />
                  <span className="text-xs text-zinc-500 ml-1 font-mono">ENGINE OUTPUT</span>
                  {isBusy && <span className="ml-auto text-xs text-emerald-400 animate-pulse">● LIVE</span>}
                </div>
                <div className="p-4 max-h-64 overflow-y-auto">
                  {terminalLines.map((line, i) => (
                    <div key={i} className={`text-xs font-mono leading-5 ${line.startsWith('[ERROR]') || line.startsWith('❌') ? 'text-red-400' :
                      line.startsWith('[✅]') ? 'text-emerald-400' :
                        line.startsWith('[⚡]') ? 'text-yellow-400' :
                          line.startsWith('[⚙️]') ? 'text-zinc-300' :
                            line.startsWith('[🎬]') ? 'text-purple-400 font-semibold' :
                              line.startsWith('[📦]') ? 'text-sky-400 font-semibold' :
                                line.startsWith('[📋]') ? 'text-sky-300' :
                                  'text-zinc-500'
                      }`}>
                      {line}
                    </div>
                  ))}
                  <div ref={consoleEndRef} />
                </div>
              </div>
            )}
          </div>
        </div>
      ) : activeTab === 'nexus' ? (
        <NexusTab />
      ) : null}
    </main>
  );
}