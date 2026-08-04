import { useState, useEffect, useRef } from 'react';
import { invoke, convertFileSrc } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import { listen } from '@tauri-apps/api/event';
import NexusTab from './NexusTab';
import LeadEngineTab from './LeadEngineTab';
import NexusAutomatorTab from './NexusAutomatorTab';
import CarouselTab from './CarouselTab';

const NOISE_PATTERNS = [
  /UserWarning/, /FutureWarning/, /DeprecationWarning/,
  /warnings\.warn/, /Already up to date/, /^\s*warnings\.warn\(/,
  /will be changed to use/, /TorchCodec/, /We recommend that you port/,
  /inference_feedback_manager/, /Created TensorFlow Lite XNNPACK delegate/,
  /portable_clearcut_uploader/, /Source Location Trace/, /wireless\/android\/play/
];
function isNoisyLine(line: string): boolean {
  return NOISE_PATTERNS.some((re) => re.test(line));
}

const OPTIONS_META: Record<string, string> = {
  extractMp3: '🎵 Extract MP3 Audio',
  mergeEngine: '🔄 Audio Merger Engine',
  removeSilence: '✂️ Remove Dead Air',
  jumpCutZooms: '🔍 Jump Cut Zooms (Requires Chop)',
  stabilizerEngine: '⚖️ Video Stabilizer Engine',
  hookEngine: '🎣 0-Second Hook Engine',
  burnCaptions: '📝 Burn Viral Captions',
  studioAudio: '🎙️ Studio Audio Enhancer',
  maskEngine: '🎭 Video Masking Engine',
  blurBackground: '🌫️ AI Background FX',
  autoZoom: '🧠 Semantic Smart-Zooms',
  motionTracking: '🎯 Dynamic Motion Tracking',
  makeVertical: '📱 Face-Tracking Vertical',
  cinematicColor: '🎨 Cinematic Color Grade',
  applyBeautyFilter: '✨ Custom Beauty Filter',
  bottomGlow: '🌌 Cinematic Bottom Glow',
  autoTransitions: '✨ Auto Sentence Transitions',
  enhanceAiImage: '🖼️ AI Image Watermark Remover',
};

export interface SceneConfig {
  id: string;
  timestamp: number;
  bgImagePath: string;
  bgImageName: string;
  textBehind: string;
  textY?: number;
  textSize?: number;
  textAnimation?: string;
  bgScale?: number;
  subjectScale?: number;
  subjectY?: number;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'utility' | 'nexus' | 'lead' | 'automator' | 'carousel'>('utility');
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPreviewVertical, setIsPreviewVertical] = useState(false);
  const [showSafeZone, setShowSafeZone] = useState(false);
  const [terminalLines, setTerminalLines] = useState<string[]>([]);
  const consoleEndRef = useRef<HTMLDivElement>(null);

  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  
  // ── NEW: Transcription Workflow State ──
  const [showTranscriptionUI, setShowTranscriptionUI] = useState(false);
  const [rawTranscriptJson, setRawTranscriptJson] = useState<any[]>([]);
  const [perfectScript, setPerfectScript] = useState("");
  const [correctedTranscriptJson, setCorrectedTranscriptJson] = useState<any[]>([]);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isGroqFixing, setIsGroqFixing] = useState(false);

  const [timelineScenes, setTimelineScenes] = useState<SceneConfig[]>([
    { id: 'scene-0', timestamp: 0.0, bgImagePath: '', bgImageName: '', textBehind: '', textY: 50, textSize: 100, textAnimation: 'slide-up' }
  ]);
  const [selectedSceneId, setSelectedSceneId] = useState<string>('scene-0');
  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoDuration, setVideoDuration] = useState(1);

  const [options, setOptions] = useState({
    enhanceAiImage: false,
    hookEngine: false,
    hookPrimaryText: '',
    hookSecondaryText: '',
    hookPrimaryStyle: 's-electric-teal',
    hookSecondaryStyle: 's-crimson-red',
    hookBgColor: 'transparent',
    hookYPercent: 40,
    hookSizePercent: 100,
    hookDuration: 1.5,
    startingHook: 'none',
    cinematicGrade: 'none',
    extractMp3: false,
    mergeEngine: false,
    mergeAudioPath: '',
    mergeAudioName: '',
    
    // ── NEW: Stabilizer State ──
    stabilizerEngine: false,
    stabilizerBackend: 'cpu',      // 'cpu' | 'gpu'
    stabilizerMode: 'camera_shake', // 'camera_shake' | 'action_cam' | 'smooth_tripod'
    stabilizerSmoothing: 10,       // 1 - 30
    stabilizerCrop: 5,             // 0% - 15% crop limit
    stabilizerZoom: true,          // Auto-scale to remove black edges

    maskEngine: false,
    enable3dDepth: false,

    // Mask State
    maskRatio: '4:5',
    maskBorderRadius: 18,
    maskScale: 85,
    maskBgMode: 'image',
    maskBgColor: '#09090b',
    maskBgImagePath: '',
    maskBgImageName: '',
    removeSilence: true,
    protectStartHook: false,
    protectStartSeconds: 2.0,
    protectEndHook: false,
    protectEndSeconds: 2.0,
    jumpCutZooms: false,
    burnCaptions: false,
    studioAudio: false,
    blurBackground: false,
    autoZoom: false,
    motionTracking: false,
    zoomIntensity: 1.15,
    zoomSpeed: 0.5,
    makeVertical: false,
    cinematicColor: false,
    applyBeautyFilter: false,
    beautyFilterMath: '',
    bottomGlow: false,
    autoTransitions: false,
    glowColor: '#000000',

    captionFont: 'Montserrat',
    captionPrimaryStyle: 'p-silver-translucent',
    captionSecondaryStyle: 's-dark-blue-glow',
    captionMixedStyle: false,

    siMainStyle: 'si-main-blue',
    siPrimaryStyle: 'si-pri-silver',
    siSecondaryStyle: 'si-sec-gold',

    captionAnimation: 'spring-up',
    captionLanguage: 'en',
    captionBottomPercent: 22,
    captionScale: 100,
    geminiApiKey: '',
    useManualGemini: false,
    manualGeminiJson: '',
    manualSrtText: '',

    bgMode: 'blur',
    bgColor: '#09090b',
    bgImagePath: '',
    bgImageName: '',
    bgImagePaths: [] as string[],
    textBehindSubject: false,
    sceneTransition: false,
    parallaxDrift: false,
    autoSfx: false,
    bgScale: 100,
    subjectScale: 100,
    subjectY: 0,
    keyingMode: 'chroma',
    colorGradeStyle: 'pro-max',
    outputRatio: '9:16',
  });

  useEffect(() => {
    const unlistenPromise = listen<string>('engine-stdout', (event) => {
      const raw = event.payload ?? '';
      const incoming = raw.split('\n').filter(
        (l) => l.trim().length > 0 && !isNoisyLine(l)
      );
      if (incoming.length > 0) setTerminalLines((prev) => [...prev, ...incoming]);
    });

    return () => {
      unlistenPromise.then(unlisten => unlisten());
    };
  }, []);

  // Auto-load the output file when the pipeline prints "PIPELINE COMPLETE"
  useEffect(() => {
    if (terminalLines.length === 0) return;
    const lastLine = terminalLines[terminalLines.length - 1];
    const match = lastLine.match(/PIPELINE COMPLETE\.?\s*Final output:\s*(.+)/);
    if (match && match[1]) {
      const newPath = match[1].trim();
      setSelectedFilePath(newPath);
    }
  }, [terminalLines]);

  useEffect(() => {
    consoleEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [terminalLines]);

  const handleSelectFile = async () => {
    const selected = await open({
      multiple: false,
      filters: [{ name: 'Media', extensions: ['mp4', 'mov', 'mkv', 'webm', 'jpg', 'jpeg', 'png', 'webp'] }],
    }).catch(() => null);
    if (selected && typeof selected === 'string') {
      setSelectedFilePath(selected);
      setTerminalLines([]);
    }
  };

  const handleLivePreview = async (sceneId?: string) => {
    if (!selectedFilePath) {
      alert("Please select a video file first");
      return;
    }
    
    // Default to global options
    let previewOptions = { ...options };
    
    // If a scene is provided, override with scene-specific values
    if (sceneId) {
      const scene = timelineScenes.find(s => s.id === sceneId);
      if (scene) {
        previewOptions = {
          ...previewOptions,
          bgMode: scene.bgImagePath ? 'image' : 'color',
          bgImagePath: scene.bgImagePath || '',
          bgScale: scene.bgScale ?? 100,
          subjectScale: scene.subjectScale ?? 100,
          subjectY: scene.subjectY ?? 0,
        };
      }
    }
    
    try {
      setIsPreviewLoading(true);
      const out = await invoke<string>('run_python_engine', {
        videoPath: selectedFilePath,
        processType: 'preview_engine',
        optionsJson: JSON.stringify(previewOptions),
      });
      const match = out.match(/\[PREVIEW_READY\] (.*)/);
      if (match && match[1]) {
        const pPath = match[1].trim();
        setPreviewSrc(convertFileSrc(pPath) + "?t=" + Date.now());
      } else {
        console.error("Preview failed:", out);
      }
    } catch (e) {
      console.error("Preview exception:", e);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  useEffect(() => {
    if (!previewSrc || isPreviewLoading) return;
    const timer = setTimeout(() => {
      handleLivePreview();
    }, 400);
    return () => clearTimeout(timer);
  }, [options.bgScale, options.subjectScale, options.subjectY, options.bgImagePath, options.bgMode]);

  const handleSelectBgImage = async () => {
    const selected = await open({
      multiple: true,
      filters: [{ name: 'Image', extensions: ['jpg', 'jpeg', 'png', 'webp'] }],
    }).catch(() => null);
    
    if (selected) {
      const paths = Array.isArray(selected) ? selected : [selected];
      setOptions((prev) => ({
        ...prev,
        bgImagePaths: paths,
        bgImagePath: paths[0],
        bgImageName: paths[0].split(/[\\/]/).pop() ?? 'image.jpg',
      }));
    }
  };

  const handleSelectMergeAudio = async () => {
    const selected = await open({
      multiple: false,
      filters: [{ name: 'Audio', extensions: ['mp3', 'wav', 'm4a', 'flac', 'aac'] }],
    }).catch(() => null);
    if (selected && typeof selected === 'string') {
      setOptions((prev) => ({
        ...prev,
        mergeAudioPath: selected,
        mergeAudioName: selected.split(/[\\/]/).pop() ?? 'audio.mp3',
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

  const handleGeneratePrompt = async () => {
    if (!selectedFilePath || isProcessing) return;
    setIsProcessing(true);
    setTerminalLines(['Extracting Audio and Running Whisper (this may take 10-20s)...']);
    try {
      const output = await invoke<string>('run_python_engine', {
        videoPath: selectedFilePath,
        processType: 'pipeline',
        optionsJson: JSON.stringify({ ...options, generatePromptOnly: true }),
      });
      
      const startTag = '[PROMPT_START]';
      const endTag = '[PROMPT_END]';
      const startIndex = output.indexOf(startTag);
      const endIndex = output.indexOf(endTag);
      
      if (startIndex !== -1 && endIndex !== -1) {
        const promptText = output.substring(startIndex + startTag.length, endIndex).trim();
        await navigator.clipboard.writeText(promptText);
        setTerminalLines((prev) => [...prev, '', `✅ AI Prompt with exact duration and Whisper timestamps copied to clipboard!`]);
        alert('AI Prompt copied to clipboard! You can now paste it into ChatGPT/Claude.');
      } else {
        setTerminalLines((prev) => [...prev, '', `❌ Failed to extract prompt from engine output.`]);
      }
    } catch (error) {
      setTerminalLines((prev) => [...prev, '', `❌ ERROR: ${String(error)}`]);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSplit = () => {
    if (videoRef.current) {
      const time = videoRef.current.currentTime;
      const newScene: SceneConfig = { id: `scene-${Date.now()}`, timestamp: time, bgImagePath: '', bgImageName: '', textBehind: '', textY: 50, textSize: 100, textAnimation: 'slide-up' };
      setTimelineScenes(prev => {
        const updated = [...prev, newScene].sort((a, b) => a.timestamp - b.timestamp);
        return updated;
      });
      setSelectedSceneId(newScene.id);
    }
  };

  const handleUndoSplit = () => {
    setTimelineScenes(prev => {
      if (prev.length <= 1) return prev;
      const updated = [...prev];
      updated.pop();
      if (selectedSceneId === updated[updated.length - 1]?.id || !updated.find(s => s.id === selectedSceneId)) {
        setSelectedSceneId(updated[updated.length - 1].id);
      }
      return updated;
    });
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if typing in an input field
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) return;

      if (e.code === 'Space') {
        e.preventDefault();
        if (videoRef.current) {
          if (videoRef.current.paused) {
            videoRef.current.play();
          } else {
            videoRef.current.pause();
          }
        }
      } else if (e.key.toLowerCase() === 'x') {
        e.preventDefault();
        handleSplit();
      } else if (e.key.toLowerCase() === 'z' && (e.ctrlKey || e.metaKey)) {
        // Bonus: Ctrl+Z for undo
        e.preventDefault();
        handleUndoSplit();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        if (videoRef.current) {
          videoRef.current.pause();
          videoRef.current.currentTime = Math.max(0, videoRef.current.currentTime - 0.0333);
        }
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        if (videoRef.current) {
          videoRef.current.pause();
          videoRef.current.currentTime = Math.min(videoRef.current.duration, videoRef.current.currentTime + 0.0333);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const updateScene = (id: string, updates: Partial<SceneConfig>) => {
    setTimelineScenes(prev => prev.map(s => s.id === id ? { ...s, ...updates } : s));
  };

  const handleSelectSceneBg = async (sceneId: string) => {
    const selected = await open({
      multiple: false,
      filters: [{ name: 'Image', extensions: ['jpg', 'jpeg', 'png', 'webp'] }],
    }).catch(() => null);
    
    if (selected && typeof selected === 'string') {
      updateScene(sceneId, {
        bgImagePath: selected,
        bgImageName: selected.split(/[\\\/]/).pop() ?? 'image.jpg',
      });
    }
  };




  const handlePreProcess = async () => {
    if (!selectedFilePath || isProcessing) return;
    setIsProcessing(true);
    const willStabilize = options.stabilizerEngine;
    const stages = [
      willStabilize ? '1. Stabilize' : null,
      options.mergeAudioPath ? '2. Merge Audio' : null,
    ].filter(Boolean).join(' → ');
    
    setTerminalLines([`⚙️ Phase 1: ${stages}`]);
    try {
      const output: string = await invoke('run_python_engine', {
        videoPath: selectedFilePath,
        processType: 'pipeline',
        optionsJson: JSON.stringify({
          ...options,
          removeSilence: false, 
          mergeEngine: !!options.mergeAudioPath,
          stabilizerEngine: willStabilize,
          blurBackground: false,
          burnCaptions: false,
          cinematicColor: false,
          cinematicGrade: 'none',
          bottomGlow: false,
          hookEngine: false,
          autoTransitions: false,
          autoZoom: false,
          motionTracking: false,
          studioAudio: false,
          applyBeautyFilter: false,
          maskEngine: false,
          enhanceAiImage: false,
        }),
      });
      
      const match = output.match(/Final output:\s*(.*)/);
      if (match && match[1]) {
        setSelectedFilePath(match[1].trim());
        setTerminalLines((prev) => [...prev, '', `✅ Merged video loaded into player!`]);
      }
    } catch (error) {
      const errStr = String(error);
      if (!errStr.includes('terminated')) {
        setTerminalLines((prev) => [...prev, '', `❌ ERROR: ${errStr}`]);
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const handleChopVideo = async () => {
    if (!selectedFilePath || isProcessing) return;
    setIsProcessing(true);
    setTerminalLines([`⚙️ Phase 2: Chopping Dead Air...`]);
    try {
      const output: string = await invoke('run_python_engine', {
        videoPath: selectedFilePath,
        processType: 'pipeline',
        optionsJson: JSON.stringify({
          ...options,
          removeSilence: false, 
          chopAndLoadOnly: true, // Only chop
          mergeEngine: false,
          jumpCutZooms: false,
          stabilizerEngine: false,
          blurBackground: false,
          burnCaptions: false,
          cinematicColor: false,
          cinematicGrade: 'none',
          bottomGlow: false,
          hookEngine: false,
          autoTransitions: false,
          autoZoom: false,
          motionTracking: false,
          studioAudio: false,
          applyBeautyFilter: false,
          maskEngine: false,
          enhanceAiImage: false,
        }),
      });
      
      const match = output.match(/Final output:\s*(.*)/);
      if (match && match[1]) {
        setSelectedFilePath(match[1].trim());
        setTerminalLines((prev) => [...prev, '', `✅ Chopped fast-paced video loaded into player!`]);
      }
    } catch (error) {
      const errStr = String(error);
      if (!errStr.includes('terminated')) {
        setTerminalLines((prev) => [...prev, '', `❌ ERROR: ${errStr}`]);
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const handleChopAndTranscribe = async () => {
    if (!selectedFilePath || isTranscribing || isProcessing) return;
    setIsTranscribing(true);
    setTerminalLines([`⚙️ Booting Deepgram Nova-2 AI...`]);
    try {
      const out: string = await invoke('run_python_engine', {
        videoPath: selectedFilePath,
        processType: 'transcribe_engine',
        optionsJson: JSON.stringify({
          ...options,
          transcribeAction: "transcribe",
          removeSilence: true, // We execute the chop here!
        }),
      });
      // Parse JSON from output
      const match = out.match(/__JSON_START__([\s\S]*?)__JSON_END__/);
      if (match) {
         const data = JSON.parse(match[1]);
         setRawTranscriptJson(data.segments);
         setShowTranscriptionUI(true);
         setTerminalLines((prev) => [...prev, '', `✅ Transcription Ready for Review!`]);
      } else {
         setTerminalLines((prev) => [...prev, '', `❌ Failed to parse Whisper JSON`]);
      }
    } catch (error) {
      setTerminalLines((prev) => [...prev, '', `❌ ERROR: ${String(error)}`]);
    } finally {
      setIsTranscribing(false);
    }
  };

  const handleGroqFix = async () => {
    if (!selectedFilePath || isGroqFixing || !perfectScript) return;
    setIsGroqFixing(true);
    setTerminalLines([`🤖 Sending to Groq LLM for perfect spelling sync...`]);
    try {
      const out: string = await invoke('run_python_engine', {
        videoPath: selectedFilePath,
        processType: 'transcribe_engine',
        optionsJson: JSON.stringify({
          transcribeAction: "groq_fix",
          rawSegments: rawTranscriptJson,
          perfectScript: perfectScript
        }),
      });
      const match = out.match(/__JSON_START__([\s\S]*?)__JSON_END__/);
      if (match) {
         const data = JSON.parse(match[1]);
         setCorrectedTranscriptJson(data);
         setTerminalLines((prev) => [...prev, '', `✅ Groq synced perfectly!`]);
      } else {
         setTerminalLines((prev) => [...prev, '', `❌ Failed to parse Groq JSON`]);
      }
    } catch (error) {
      setTerminalLines((prev) => [...prev, '', `❌ ERROR: ${String(error)}`]);
    } finally {
      setIsGroqFixing(false);
    }
  };

  const handleExtractMp3 = async () => {
    if (!selectedFilePath || isProcessing) return;
    setIsProcessing(true);
    setTerminalLines(['Extracting Raw MP3...']);
    try {
      await invoke<string>('run_python_engine', {
        videoPath: selectedFilePath,
        processType: 'pipeline',
        optionsJson: JSON.stringify({ extractMp3Only: true }),
      });
      setTerminalLines((prev) => [...prev, '', `✅ Raw MP3 Extracted!`]);
    } catch (error) {
      setTerminalLines((prev) => [...prev, '', `❌ ERROR: ${String(error)}`]);
    } finally {
      setIsProcessing(false);
    }
  };

    const handleRunPipeline = async () => {
      if (!selectedFilePath || isProcessing) return;
      setIsProcessing(true);
      setTerminalLines(['Initializing Python Engine...']);
      
      const hasTimelineBg = timelineScenes.some(s => s.bgImagePath !== '');
      const hasTimelineText = timelineScenes.some(s => s.textBehind !== '');
      const hasTimelineCuts = timelineScenes.length > 1;
      
      const finalOptions = {
        ...options,
        timelineScenes,
        removeSilence: options.removeSilence, 
        manualGeminiJson: correctedTranscriptJson.length > 0 ? JSON.stringify(correctedTranscriptJson) : (rawTranscriptJson.length > 0 ? JSON.stringify(rawTranscriptJson) : undefined),
        
        // Auto-enable if timeline has backgrounds or text
        blurBackground: options.blurBackground || hasTimelineBg || hasTimelineText,
        textBehindSubject: options.textBehindSubject || hasTimelineText,
        
        // Auto-enable transitions if timeline has cuts
        sceneTransition: options.sceneTransition || hasTimelineCuts,
        autoSfx: options.autoSfx || hasTimelineCuts
      };
      
      try {
        await invoke<string>('run_python_engine', {
          videoPath: selectedFilePath,
          processType: 'pipeline',
          optionsJson: JSON.stringify(finalOptions),
        });
      } catch (error) {
        const errorStr = String(error);
        if (errorStr.includes("terminated")) {
          setTerminalLines((prev) => [...prev, '', `🛑 RENDER CANCELLED BY USER.`]);
        } else {
          setTerminalLines((prev) => [...prev, '', `❌ FATAL CRASH: ${errorStr}`]);
        }
      } finally {
        setIsProcessing(false);
      }
    };

  const handleStopPipeline = async () => {
    try {
      await invoke('stop_engine');
    } catch (error) {
      console.error("Failed to stop engine:", error);
    }
  };

  const activeCount = Object.entries(options)
    .filter(([k, v]) => OPTIONS_META[k] && v === true).length;

  const isBusy = isProcessing;

  return (
    <main className="h-screen h-[100dvh] overflow-hidden text-white font-sans flex flex-col bg-[#09090b]">

      <nav className="border-b border-zinc-800 bg-zinc-950 px-4 py-3 flex justify-center gap-3">
        {([['utility', '⚙️ Utility Pipe', 'emerald'], ['nexus', '🧠 Nexus Studio', 'purple'], ['lead', '🚀 Lead Engine', 'orange'], ['automator', '🎬 Automator', 'pink'], ['carousel', '🖼️ Carousels', 'blue']] as const).map(
          ([tab, label, color]) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`px-6 py-2 rounded-lg font-medium text-sm transition-all ${activeTab === tab
                ? color === 'emerald'
                  ? 'bg-emerald-600 text-white shadow-[0_0_12px_rgba(5,150,105,0.4)]'
                  : color === 'purple'
                  ? 'bg-purple-600 text-white shadow-[0_0_12px_rgba(147,51,234,0.4)]'
                  : color === 'orange'
                  ? 'bg-orange-600 text-white shadow-[0_0_12px_rgba(234,88,12,0.4)]'
                  : color === 'pink'
                  ? 'bg-pink-600 text-white shadow-[0_0_12px_rgba(219,39,119,0.4)]'
                  : 'bg-blue-600 text-white shadow-[0_0_12px_rgba(37,99,235,0.4)]'
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

            <div className="flex flex-col gap-3">
              {selectedFilePath ? (
                <div className="flex flex-col gap-3">
                  <div className="flex gap-3">
                    <div className="flex-1 bg-zinc-900 border border-zinc-700 rounded-xl overflow-hidden flex flex-col">
                      <video 
                        ref={videoRef}
                        src={convertFileSrc(selectedFilePath)} 
                        controls 
                        className="w-full h-56 bg-black object-contain"
                        onLoadedMetadata={(e) => setVideoDuration(e.currentTarget.duration || 1)}
                      />
                      <div className="p-3 border-t border-zinc-800 bg-zinc-950 flex flex-col gap-2">
                        <div className="flex justify-between items-center">
                            <span className="text-xs font-bold text-zinc-400">TIMELINE SPLITTER</span>
                            <div className="flex gap-2">
                              <button 
                                onClick={() => { 
                                  setSelectedFilePath(null); 
                                  setTimelineScenes([{ id: 'scene-0', timestamp: 0.0, bgImagePath: '', bgImageName: '', textBehind: '', textY: 50, textSize: 100, textAnimation: 'slide-up' }]); 
                                  setSelectedSceneId('scene-0'); 
                                }} 
                                className="text-xs bg-red-900/40 hover:bg-red-900 px-3 py-1 rounded text-red-300 font-bold transition-colors"
                              >
                                🗑️ Clear Video
                              </button>
                              <button onClick={handleUndoSplit} className="text-xs bg-zinc-800 hover:bg-zinc-700 px-3 py-1 rounded text-zinc-300 font-bold transition-colors">
                                ↩️ Undo
                              </button>
                              
                              <div className="flex gap-1 bg-zinc-900 border border-zinc-700 p-0.5 rounded">
                                <button 
                                  onClick={() => { if(videoRef.current) { videoRef.current.pause(); videoRef.current.currentTime -= 0.0333; } }} 
                                  className="text-[10px] bg-zinc-800 hover:bg-zinc-700 px-2 py-1 rounded text-zinc-300 font-bold transition-colors shadow-sm"
                                  title="Previous Frame (Left Arrow)"
                                >
                                  ◀
                                </button>
                                <button 
                                  onClick={() => { if(videoRef.current) { videoRef.current.pause(); videoRef.current.currentTime += 0.0333; } }} 
                                  className="text-[10px] bg-zinc-800 hover:bg-zinc-700 px-2 py-1 rounded text-zinc-300 font-bold transition-colors shadow-sm"
                                  title="Next Frame (Right Arrow)"
                                >
                                  ▶
                                </button>
                              </div>

                              <button onClick={handleSplit} className="text-xs bg-emerald-600 hover:bg-emerald-500 px-3 py-1 rounded text-white font-bold flex items-center gap-1 transition-colors">
                                <span>✂️</span> Split at Playhead
                              </button>
                            </div>
                        </div>
                        <div className="relative h-8 bg-zinc-800 rounded overflow-hidden flex">
                            {timelineScenes.map((scene, idx) => {
                              const nextTime = idx < timelineScenes.length - 1 ? timelineScenes[idx+1].timestamp : videoDuration;
                              const widthPercent = Math.max(0, ((nextTime - scene.timestamp) / videoDuration) * 100);
                              const isSelected = selectedSceneId === scene.id;
                              return (
                                <div 
                                  key={scene.id} 
                                  onClick={() => setSelectedSceneId(scene.id)}
                                  className={`h-full border-r border-zinc-900 cursor-pointer transition-colors flex items-center justify-center ${isSelected ? 'bg-purple-600' : 'bg-zinc-600 hover:bg-zinc-500'}`}
                                  style={{ width: `${widthPercent}%` }}
                                >
                                    <span className="text-[10px] font-mono font-bold">{idx + 1}</span>
                                </div>
                              );
                            })}
                        </div>
                      </div>
                    </div>
                    <div className="w-1/3 flex flex-col gap-3">
                      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-3 flex flex-col justify-center items-center text-center">
                        <span className="text-xl mb-1">🎵</span>
                        <h3 className="text-xs font-bold text-zinc-300 mb-1">Step 1: Extract MP3</h3>
                        <button 
                          onClick={handleExtractMp3}
                          disabled={isProcessing}
                          className="w-full bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-600 text-[10px] font-bold py-1.5 px-2 rounded transition-colors disabled:opacity-50 mt-1">
                          Export Raw Audio
                        </button>
                      </div>
                      <div className="flex-1 bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex flex-col justify-center items-center text-center">
                        <span className="text-2xl mb-1">✂️</span>
                        <h3 className="text-sm font-bold text-zinc-300 mb-2">Step 2: Pre-Process</h3>
                        
                        <button
                          onClick={handleSelectMergeAudio}
                          className="w-full mb-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-600 text-[10px] font-bold py-1.5 px-2 rounded transition-colors truncate"
                        >
                          {options.mergeAudioName ? `✅ ${options.mergeAudioName}` : '1. Upload Adobe Audio'}
                        </button>
                        
                        <button 
                          onClick={handlePreProcess}
                          disabled={isProcessing}
                          className="w-full mb-2 bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold py-2 px-4 rounded transition-colors disabled:opacity-50">
                          2. Clean & Merge Now
                        </button>
                        
                        <button 
                          onClick={handleChopVideo}
                          disabled={isProcessing}
                          className="w-full mb-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold py-2 px-4 rounded transition-colors disabled:opacity-50">
                          3. Chop & Load Video
                        </button>

                        <div className="w-full mb-2 bg-zinc-950/50 rounded-lg p-2 flex flex-col gap-2 border border-zinc-800">
                          <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider text-left">✂️ Chopper Protection</span>
                          <div className="flex items-center justify-between gap-2">
                            <label className="flex items-center gap-1.5 cursor-pointer text-xs text-zinc-300">
                              <input type="checkbox" checked={options.protectStartHook} onChange={() => setOptions(o => ({...o, protectStartHook: !o.protectStartHook}))} className="accent-emerald-500" />
                              Start Hook
                            </label>
                            {options.protectStartHook && (
                              <div className="flex items-center gap-1">
                                <input type="number" step="0.1" min="0" max="10" value={options.protectStartSeconds} onChange={(e) => setOptions(o => ({...o, protectStartSeconds: parseFloat(e.target.value) || 0}))} className="w-12 bg-zinc-800 text-white text-[10px] px-1 py-0.5 rounded outline-none border border-zinc-700" />
                                <span className="text-[10px] text-zinc-500">sec</span>
                              </div>
                            )}
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <label className="flex items-center gap-1.5 cursor-pointer text-xs text-zinc-300">
                              <input type="checkbox" checked={options.protectEndHook} onChange={() => setOptions(o => ({...o, protectEndHook: !o.protectEndHook}))} className="accent-emerald-500" />
                              End Hook
                            </label>
                            {options.protectEndHook && (
                              <div className="flex items-center gap-1">
                                <input type="number" step="0.1" min="0" max="10" value={options.protectEndSeconds} onChange={(e) => setOptions(o => ({...o, protectEndSeconds: parseFloat(e.target.value) || 0}))} className="w-12 bg-zinc-800 text-white text-[10px] px-1 py-0.5 rounded outline-none border border-zinc-700" />
                                <span className="text-[10px] text-zinc-500">sec</span>
                              </div>
                            )}
                          </div>
                        </div>

                        <button 
                          onClick={handleChopAndTranscribe}
                          disabled={isTranscribing}
                          className="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold py-2 px-4 rounded transition-colors disabled:opacity-50">
                          4. Transcribe (Deepgram AI)
                        </button>
                        <button 
                          onClick={handleExtractMp3}
                          disabled={isProcessing}
                          className="w-full bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-[10px] font-bold py-2 px-4 rounded transition-colors border border-zinc-700 disabled:opacity-50">
                          5. Extract Audio (For Zap Subs)
                        </button>
                      </div>
                    </div>
                  </div>
                  
                  {/* Selected Scene Settings Panel */}
                  {selectedSceneId && (
                    <div className="bg-zinc-900 border border-purple-500/50 rounded-xl p-4 flex gap-4">
                      {(() => {
                        const scene = timelineScenes.find(s => s.id === selectedSceneId);
                        if (!scene) return null;
                        const idx = timelineScenes.findIndex(s => s.id === selectedSceneId) + 1;
                        return (
                          <>
                            <div className="flex flex-col gap-2 w-1/2">
                              <span className="text-xs font-bold text-zinc-400">SCENE {idx} BACKGROUND</span>
                              <button onClick={() => handleSelectSceneBg(scene.id)} className="bg-zinc-800 border border-zinc-700 hover:border-zinc-500 rounded p-4 flex flex-col items-center justify-center min-h-[80px]">
                                {scene.bgImagePath ? (
                                  <div className="bg-zinc-950 px-3 py-2 rounded-lg border border-zinc-700">
                                    <span className="text-xs text-emerald-400 font-medium truncate w-full">{scene.bgImageName}</span>
                                  </div>
                                ) : (
                                  <span className="text-xs text-zinc-500 flex flex-col items-center gap-1"><span className="text-lg">🖼️</span> Upload BG</span>
                                )}
                              </button>

                              <div className="flex flex-col gap-2 mt-2 pt-2 border-t border-zinc-800/50">
                                <div className="flex items-center gap-2">
                                  <span className="text-[10px] text-zinc-500 font-bold min-w-[60px]">BG ZOOM</span>
                                  <input type="range" min="100" max="250" value={scene.bgScale ?? 100} onChange={(e) => updateScene(scene.id, { bgScale: parseInt(e.target.value) })} className="flex-1 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-emerald-500" />
                                  <span className="text-[10px] text-zinc-500 w-8 text-right font-mono">{scene.bgScale ?? 100}%</span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-[10px] text-zinc-500 font-bold min-w-[60px]">SUBJ SIZE</span>
                                  <input type="range" min="30" max="150" value={scene.subjectScale ?? 100} onChange={(e) => updateScene(scene.id, { subjectScale: parseInt(e.target.value) })} className="flex-1 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-purple-500" />
                                  <span className="text-[10px] text-zinc-500 w-8 text-right font-mono">{scene.subjectScale ?? 100}%</span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-[10px] text-zinc-500 font-bold min-w-[60px]">SUBJ Y-POS</span>
                                  <input type="range" min="-100" max="100" value={scene.subjectY ?? 0} onChange={(e) => updateScene(scene.id, { subjectY: parseInt(e.target.value) })} className="flex-1 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-purple-500" />
                                  <span className="text-[10px] text-zinc-500 w-8 text-right font-mono">{(scene.subjectY ?? 0) > 0 ? '+' : ''}{scene.subjectY ?? 0}%</span>
                                </div>
                                <div className="flex gap-2 mt-1">
                                  <button 
                                    onClick={() => updateScene(scene.id, { bgScale: 100, subjectScale: 100, subjectY: 0 })}
                                    className="text-[10px] uppercase font-bold tracking-wider py-1.5 px-3 bg-zinc-800/50 hover:bg-zinc-700/50 text-zinc-400 hover:text-zinc-300 rounded border border-zinc-800/80 transition-colors w-1/3">
                                    Reset
                                  </button>
                                  <button 
                                    onClick={() => handleLivePreview(scene.id)} 
                                    disabled={isPreviewLoading}
                                    className="text-[10px] uppercase font-bold tracking-wider py-1.5 px-3 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded border border-zinc-700 flex-1 disabled:opacity-50 transition-colors">
                                    {isPreviewLoading ? 'Generating...' : 'Load Live Preview Frame'}
                                  </button>
                                </div>
                              </div>
                            </div>

                            <div className="flex flex-col gap-2 flex-1 relative">
                              <div className="flex justify-between items-center">
                                <span className="text-xs font-bold text-zinc-400">SANDWICH TEXT (TEXT BEHIND SUBJECT)</span>
                                <button 
                                  onClick={() => {
                                    setTimelineScenes(prev => prev.map(s => ({
                                      ...s,
                                      textY: scene.textY,
                                      textSize: scene.textSize,
                                      bgScale: scene.bgScale,
                                      subjectScale: scene.subjectScale,
                                      subjectY: scene.subjectY
                                    })));
                                  }}
                                  className="text-[10px] bg-purple-600/20 hover:bg-purple-600/40 text-purple-400 border border-purple-500/30 px-2 py-0.5 rounded transition-colors uppercase font-bold"
                                >
                                  Apply to All
                                </button>
                              </div>
                              <input 
                                type="text" 
                                placeholder="Enter text to slide up..." 
                                value={scene.textBehind}
                                onChange={(e) => updateScene(scene.id, { textBehind: e.target.value })}
                                className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm outline-none focus:border-purple-500 text-white"
                              />
                              <div className="flex gap-4 items-center">
                                <div className="flex items-center gap-2 flex-1">
                                  <span className="text-[10px] text-zinc-500 font-bold min-w-[30px]">POS Y</span>
                                  <input type="range" min="0" max="100" value={scene.textY ?? 50} onChange={(e) => updateScene(scene.id, { textY: parseInt(e.target.value) })} className="flex-1 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-purple-500" />
                                  <span className="text-[10px] text-zinc-500 w-6 text-right font-mono">{scene.textY ?? 50}%</span>
                                </div>
                                <div className="flex items-center gap-2 flex-1">
                                  <span className="text-[10px] text-zinc-500 font-bold min-w-[30px]">SIZE</span>
                                  <input type="range" min="50" max="250" value={scene.textSize ?? 100} onChange={(e) => updateScene(scene.id, { textSize: parseInt(e.target.value) })} className="flex-1 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-purple-500" />
                                  <span className="text-[10px] text-zinc-500 w-6 text-right font-mono">{scene.textSize ?? 100}%</span>
                                </div>
                              </div>
                              
                              <div className="relative bg-black rounded-lg overflow-hidden border border-zinc-700 pointer-events-none mt-2 mx-auto" style={{ width: '200px', height: '355px' }}>
                                {previewSrc ? (
                                  <img src={previewSrc} className="w-full h-full object-cover" />
                                ) : selectedFilePath ? (
                                  <video src={convertFileSrc(selectedFilePath)} className="w-full h-full object-cover opacity-60" preload="auto" muted playsInline onLoadedMetadata={(e) => { e.currentTarget.currentTime = 2.0; }} />
                                ) : (
                                  <div className="w-full h-full flex items-center justify-center text-zinc-600"><span className="text-[10px] uppercase font-semibold">No Video</span></div>
                                )}
                                <div
                                  className="absolute left-0 right-0 flex justify-center w-full transition-all duration-75"
                                  style={{ top: `${scene.textY ?? 50}%`, transform: 'translateY(-50%)' }}
                                >
                                  <div 
                                    className="text-white font-bold uppercase tracking-widest text-center" 
                                    style={{ 
                                      fontSize: `${(scene.textSize ?? 100) * 0.28}px`,
                                      textShadow: '0 2px 4px rgba(0,0,0,0.8), 0 0 10px rgba(0,0,0,0.5)',
                                      fontFamily: 'Impact, sans-serif'
                                    }}
                                  >
                                    {scene.textBehind || 'SANDWICH'}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </>
                        );
                      })()}
                    </div>
                  )}

                  <div className="flex justify-between items-center bg-zinc-900 border border-zinc-800 p-2 rounded-lg mt-2">
                    <span className="text-xs text-zinc-400 font-bold ml-2">SUBJECT EXTRACTION (GREEN SCREEN)</span>
                    <select
                      value={options.keyingMode}
                      onChange={(e) => setOptions(prev => ({...prev, keyingMode: e.target.value}))}
                      className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-purple-500"
                    >
                      <option value="chroma">FFmpeg Chroma Key (Best for Green Screen)</option>
                      <option value="chroma-dark">FFmpeg Chroma Key (Dark Green Screen)</option>
                      <option value="ai">MediaPipe AI (No Green Screen needed)</option>
                    </select>
                  </div>
                  
                  <div className="flex justify-between items-center bg-zinc-900 border border-zinc-800 p-2 rounded-lg mt-2">
                    <span className="text-xs text-zinc-400 font-bold ml-2">OUTPUT ASPECT RATIO</span>
                    <select
                      value={options.outputRatio}
                      onChange={(e) => setOptions(prev => ({...prev, outputRatio: e.target.value}))}
                      className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-purple-500"
                    >
                      <option value="9:16">9:16 (Vertical / TikTok)</option>
                      <option value="16:9">16:9 (Horizontal / YouTube)</option>
                      <option value="source">Match Source</option>
                    </select>
                  </div>
                  
                  {/* Phase 3: Transcription Editor UI */}
                  {showTranscriptionUI && rawTranscriptJson.length > 0 && (
                    <div className="mt-4 bg-zinc-900 border border-emerald-500/50 rounded-xl p-5 flex flex-col gap-4">
                      <div className="flex items-center justify-between">
                        <h3 className="text-sm font-bold text-emerald-400 uppercase tracking-widest flex items-center gap-2">
                          <span className="text-lg">🤖</span> Groq Transcription Sync
                        </h3>
                        <span className="text-xs text-zinc-500 font-mono">PHASE 3</span>
                      </div>
                      
                      <div className="flex gap-4 h-[300px]">
                        <div className="flex-1 flex flex-col gap-2">
                          <span className="text-xs font-bold text-zinc-400">PASTE PERFECT SCRIPT HERE</span>
                          <textarea 
                            value={perfectScript}
                            onChange={(e) => setPerfectScript(e.target.value)}
                            placeholder="Enter the correct script with spelling and | for director cuts..."
                            className="flex-1 w-full bg-zinc-950 border border-zinc-700 rounded-lg p-3 text-sm text-zinc-300 outline-none focus:border-emerald-500 resize-none font-mono"
                          />
                          <button 
                            onClick={handleGroqFix}
                            disabled={isGroqFixing || !perfectScript}
                            className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2 px-4 rounded transition-colors disabled:opacity-50">
                            {isGroqFixing ? "Syncing..." : "Auto-Fix spelling with Groq"}
                          </button>
                        </div>
                        
                        <div className="flex-1 flex flex-col gap-2">
                          <span className="text-xs font-bold text-zinc-400">CORRECTED TIMESTAMPS JSON</span>
                          <div className="flex-1 bg-zinc-950 border border-zinc-700 rounded-lg p-3 overflow-y-auto font-mono text-xs text-sky-300 whitespace-pre-wrap select-text">
                            {correctedTranscriptJson.length > 0 
                              ? JSON.stringify(correctedTranscriptJson, null, 2) 
                              : "// Waiting for Groq correction..."}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  
                </div>
              ) : (
                <div onClick={handleSelectFile}
                  className="w-full border-2 border-dashed border-zinc-700 bg-zinc-900 hover:border-zinc-500 hover:bg-zinc-800 rounded-xl p-10 flex flex-col items-center justify-center cursor-pointer transition-colors">
                  <div className="text-center space-y-2">
                    <span className="text-4xl">📁</span>
                    <p className="font-medium">Click to select your raw video or image</p>
                    <p className="text-sm text-zinc-500">MP4, MOV, MKV, WEBM, JPG, PNG, WEBP</p>
                  </div>
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

                    {/* ── AUDIO MERGER ENGINE UI ── */}
                    {key === 'mergeEngine' && options.mergeEngine && (
                      <div className="flex flex-col gap-3 p-3 ml-2 rounded-lg bg-zinc-900/80 border border-zinc-800">
                        <div className="text-xs text-zinc-500 italic pb-2 border-b border-zinc-800/50">
                          Replaces the original video audio with the enhanced audio file and boosts volume slightly.
                        </div>
                        <div className="flex items-center justify-between">
                          <button
                            onClick={(e) => { e.preventDefault(); handleSelectMergeAudio(); }}
                            className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-300 transition-colors border border-zinc-600 shadow-sm active:scale-95 whitespace-nowrap"
                          >
                            {options.mergeAudioName ? 'Change Audio' : 'Select Audio'}
                          </button>
                          <span className="text-[11px] text-sky-400 font-mono truncate max-w-[150px] ml-3" title={options.mergeAudioPath}>
                            {options.mergeAudioName || 'No file selected'}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* ── NEW: STABILIZER ENGINE UI CONTROLS ── */}
                    {key === 'stabilizerEngine' && options.stabilizerEngine && (
                      <div className="flex flex-col gap-3 p-3 ml-2 rounded-lg bg-zinc-900/80 border border-zinc-800">
                        <div className="flex items-center justify-between pb-2 border-b border-zinc-800/50">
                          <span className="text-xs text-sky-400 font-semibold uppercase tracking-wider">Motion Stabilization</span>
                          <span className="text-[10px] text-zinc-500 font-mono">2-Pass Track</span>
                        </div>
                        
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-zinc-400 font-medium">Engine Backend</span>
                          <select 
                            value={options.stabilizerBackend || 'cpu'} 
                            onChange={(e) => setOptions((prev) => ({ ...prev, stabilizerBackend: e.target.value }))}
                            className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-[10px] rounded p-1 outline-none focus:border-sky-500 font-medium">
                            <option value="cpu">🐢 MediaPipe (CPU - Legacy)</option>
                            <option value="gpu">🚀 PyTorch (GPU - Fast)</option>
                          </select>
                        </div>

                        <div className="flex items-center justify-between">
                          <span className="text-xs text-zinc-400 font-medium">Mode</span>
                          <select 
                            value={options.stabilizerMode} 
                            onChange={(e) => setOptions((prev) => ({ ...prev, stabilizerMode: e.target.value }))}
                            className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-[10px] rounded p-1 outline-none focus:border-sky-500 font-medium">
                            <option value="camera_shake">📱 Handheld Fix</option>
                            <option value="action_cam">🏃 Action Cam</option>
                            <option value="smooth_tripod">🎬 Cinematic Glide</option>
                          </select>
                        </div>

                        <div className="flex items-center gap-3">
                          <span className="text-xs text-zinc-400 font-medium min-w-[70px]">Smoothing</span>
                          <input
                            type="range" min="1" max="30"
                            value={options.stabilizerSmoothing}
                            onChange={(e) => setOptions((prev) => ({ ...prev, stabilizerSmoothing: parseInt(e.target.value) }))}
                            className="flex-1 h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-sky-500"
                          />
                          <span className="text-xs text-zinc-500 font-mono w-6 text-right">{options.stabilizerSmoothing}</span>
                        </div>

                        <div className="flex items-center gap-3">
                          <span className="text-xs text-zinc-400 font-medium min-w-[70px]">Max Crop</span>
                          <input
                            type="range" min="0" max="15"
                            value={options.stabilizerCrop}
                            onChange={(e) => setOptions((prev) => ({ ...prev, stabilizerCrop: parseInt(e.target.value) }))}
                            className="flex-1 h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-sky-500"
                          />
                          <span className="text-xs text-zinc-500 font-mono w-6 text-right">{options.stabilizerCrop}%</span>
                        </div>

                        <div className="flex items-center justify-between pt-2 border-t border-zinc-800/50">
                          <span className="text-xs text-zinc-400 font-medium">Auto-Zoom Compensation</span>
                          <input 
                            type="checkbox" 
                            checked={options.stabilizerZoom} 
                            onChange={(e) => setOptions((prev) => ({ ...prev, stabilizerZoom: e.target.checked }))} 
                            className="w-4 h-4 accent-sky-500 cursor-pointer"
                          />
                        </div>
                      </div>
                    )}

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

                    {key === 'applyBeautyFilter' && options.applyBeautyFilter && (
                      <div className="flex flex-col gap-2 p-3 ml-2 rounded-lg bg-emerald-900/30 border border-emerald-800/50">
                        <div className="flex items-center gap-2">
                          <span className="text-xl">✨</span>
                          <span className="text-xs text-emerald-300 font-semibold tracking-wide">AI FACE MESH ACTIVE</span>
                        </div>
                        <p className="text-[10px] text-emerald-400/80 leading-relaxed">
                          OpenCV will draw a 468-point 3D mask over your face, exclude your eyes and lips, apply high-end bilateral skin smoothing, lift shadows for a glowing complexion, and subtly slim the jawline.
                        </p>
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
                            <option value="chroma">🟩 FFmpeg Hard Key</option>
                            <option value="chroma-dark">🟩 FFmpeg Hard Key (Dark)</option>
                            <option value="webgl">🌐 WebGL Soft Key (GPU)</option>
                          </select>
                        </div>
                        
                        <div className="flex flex-col gap-2 pb-2 mb-2 border-b border-zinc-800/50">
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-zinc-400 font-medium tracking-wide flex items-center gap-2">
                              <span>🍔</span> Text Behind Subject
                            </span>
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input type="checkbox" className="sr-only peer"
                                checked={options.textBehindSubject}
                                onChange={(e) => setOptions(prev => ({...prev, textBehindSubject: e.target.checked}))}
                              />
                              <div className="w-8 h-4 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-emerald-500"></div>
                            </label>
                          </div>
                          
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-zinc-400 font-medium tracking-wide flex items-center gap-2">
                              <span>🎬</span> CapCut Scene Slide
                            </span>
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input type="checkbox" className="sr-only peer"
                                checked={options.sceneTransition}
                                onChange={(e) => setOptions(prev => ({...prev, sceneTransition: e.target.checked}))}
                              />
                              <div className="w-8 h-4 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-emerald-500"></div>
                            </label>
                          </div>
                          
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-zinc-400 font-medium tracking-wide flex items-center gap-2">
                              <span>🌌</span> 3D Parallax Drift
                            </span>
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input type="checkbox" className="sr-only peer"
                                checked={options.parallaxDrift}
                                onChange={(e) => setOptions(prev => ({...prev, parallaxDrift: e.target.checked}))}
                              />
                              <div className="w-8 h-4 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-emerald-500"></div>
                            </label>
                          </div>
                          
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-zinc-400 font-medium tracking-wide flex items-center gap-2">
                              <span>🔊</span> Auto-SFX Engine
                            </span>
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input type="checkbox" className="sr-only peer"
                                checked={options.autoSfx}
                                onChange={(e) => setOptions(prev => ({...prev, autoSfx: e.target.checked}))}
                              />
                              <div className="w-8 h-4 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-emerald-500"></div>
                            </label>
                          </div>
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
                          <div className="flex flex-col gap-3">
                            <div className="flex flex-col gap-2">
                              <div className="flex items-center justify-between">
                                <span className="text-xs text-zinc-400 font-medium">Background Playlist</span>
                                <button onClick={handleSelectBgImage}
                                  className={`text-xs px-3 py-1.5 rounded border transition-colors ${options.bgImagePaths && options.bgImagePaths.length > 0
                                    ? 'bg-emerald-950/50 border-emerald-700/50 text-emerald-400'
                                    : 'bg-zinc-950 border-zinc-700 hover:border-zinc-500 text-zinc-300'}`}>
                                  {options.bgImagePaths && options.bgImagePaths.length > 0 ? `${options.bgImagePaths.length} Images Selected` : 'Choose Images...'}
                                </button>
                              </div>
                              {options.bgImagePaths && options.bgImagePaths.length > 0 && (
                                <div className="flex flex-col gap-1 p-2 bg-zinc-950 border border-zinc-800 rounded">
                                  {options.bgImagePaths.map((p, idx) => (
                                    <div key={idx} className="flex justify-between items-center text-[10px] text-zinc-400 font-mono">
                                      <span>Scene {idx + 1}</span>
                                      <span className="truncate max-w-[120px]">{p.split(/[\\/]/).pop()}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                            
                            <div className="flex flex-col gap-2 pt-2 border-t border-zinc-800/50 mt-1">
                              <div className="flex items-center gap-3">
                                <span className="text-[10px] text-zinc-500 font-medium tracking-wider min-w-[70px]">BG ZOOM</span>
                                <input type="range" min="100" max="250" value={options.bgScale} onChange={(e) => setOptions((prev) => ({ ...prev, bgScale: parseInt(e.target.value) }))} className="flex-1 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-emerald-500" />
                                <span className="text-[10px] text-zinc-500 w-8 text-right font-mono">{options.bgScale}%</span>
                              </div>
                              <div className="flex items-center gap-3">
                                <span className="text-[10px] text-zinc-500 font-medium tracking-wider min-w-[70px]">SUBJ SIZE</span>
                                <input type="range" min="30" max="150" value={options.subjectScale} onChange={(e) => setOptions((prev) => ({ ...prev, subjectScale: parseInt(e.target.value) }))} className="flex-1 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-purple-500" />
                                <span className="text-[10px] text-zinc-500 w-8 text-right font-mono">{options.subjectScale}%</span>
                              </div>
                              <div className="flex items-center gap-3">
                                <span className="text-[10px] text-zinc-500 font-medium tracking-wider min-w-[70px]">SUBJ Y-POS</span>
                                <input type="range" min="-100" max="100" value={options.subjectY} onChange={(e) => setOptions((prev) => ({ ...prev, subjectY: parseInt(e.target.value) }))} className="flex-1 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-purple-500" />
                                <span className="text-[10px] text-zinc-500 w-8 text-right font-mono">{options.subjectY > 0 ? '+' : ''}{options.subjectY}%</span>
                              </div>
                              <div className="flex gap-2 mt-2">
                                <button 
                                  onClick={() => setOptions(prev => ({ ...prev, bgScale: 100, subjectScale: 100, subjectY: 0 }))}
                                  className="text-[10px] uppercase font-bold tracking-wider py-1.5 px-3 bg-zinc-800/50 hover:bg-zinc-700/50 text-zinc-400 hover:text-zinc-300 rounded border border-zinc-800/80 transition-colors w-1/3">
                                  Reset
                                </button>
                                <button 
                                  onClick={() => handleLivePreview()} 
                                  disabled={isPreviewLoading}
                                  className="text-[10px] uppercase font-bold tracking-wider py-1.5 px-3 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded border border-zinc-700 flex-1 disabled:opacity-50 transition-colors">
                                  {isPreviewLoading ? 'Generating...' : 'Load Live Preview Frame'}
                                </button>
                              </div>
                              {previewSrc && (
                                <div className="mt-2 w-full max-h-[350px] bg-zinc-950 border border-zinc-800 rounded overflow-hidden flex items-center justify-center relative group">
                                  <img src={previewSrc} alt="Preview" className="w-full h-full object-contain" />
                                  <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                                    <button onClick={() => setPreviewSrc(null)} className="text-xs text-white/80 bg-white/10 px-3 py-1.5 rounded-full hover:bg-white/20 hover:text-white">Close Preview</button>
                                  </div>
                                </div>
                              )}
                            </div>
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
                            <option value="manual_srt">📝 Manual Subtitles (SRT)</option>
                          </select>
                        </div>

                        {options.captionLanguage === 'manual_srt' && (
                          <div className="flex flex-col gap-2 pb-2 mb-2 border-b border-zinc-800/50">
                            <span className="text-xs text-orange-400 font-semibold uppercase tracking-wider">Paste Subtitles</span>
                            <textarea
                              placeholder="Paste formatted SRT with timings here..."
                              value={options.manualSrtText}
                              onChange={(e) => setOptions((prev) => ({ ...prev, manualSrtText: e.target.value }))}
                              className="bg-black border border-zinc-700 text-zinc-300 text-xs rounded p-2 outline-none focus:border-orange-500 w-full h-32 font-mono resize-none"
                            />
                          </div>
                        )}

                        {options.captionLanguage === 'si' && (
                          <div className="flex flex-col gap-2 pb-2 mb-2 border-b border-zinc-800/50">

                            <div className="flex items-center justify-between">
                              <span className="text-xs text-orange-400 font-semibold uppercase tracking-wider">Gemini API Options</span>
                              <label className="flex items-center gap-1 cursor-pointer">
                                <input type="checkbox" checked={options.useManualGemini}
                                  onChange={(e) => setOptions((prev) => ({ ...prev, useManualGemini: e.target.checked }))}
                                  className="accent-orange-500 w-3 h-3 cursor-pointer" />
                                <span className="text-[10px] text-zinc-300">Manual Override</span>
                              </label>
                            </div>

                            {!options.useManualGemini ? (
                              <input type="password" placeholder="Paste Google AI Studio Key..."
                                value={options.geminiApiKey}
                                onChange={(e) => setOptions((prev) => ({ ...prev, geminiApiKey: e.target.value }))}
                                className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1.5 outline-none focus:border-orange-500 w-full" />
                            ) : (
                              <div className="flex flex-col gap-2 mt-1 bg-zinc-950 p-2 rounded border border-zinc-800">
                                <p className="text-[10px] text-zinc-400 leading-tight">
                                  1. Copy the prompt. 2. Upload your audio to Gemini Web. 3. Paste prompt. 4. Paste the resulting JSON array here.
                                </p>
                                <button
                                  onClick={handleGeneratePrompt}
                                  className="w-full bg-orange-600/20 text-orange-400 border border-orange-500/50 hover:bg-orange-500 hover:text-white transition-colors rounded py-1.5 text-xs font-semibold uppercase tracking-wider"
                                >
                                  Copy Prompt
                                </button>
                                <textarea
                                  placeholder='Paste the raw JSON array here ([{"phrase": "...", "start": 0.0, "end": 1.0}])'
                                  value={options.manualGeminiJson}
                                  onChange={(e) => setOptions((prev) => ({ ...prev, manualGeminiJson: e.target.value }))}
                                  className="bg-black border border-zinc-700 text-zinc-300 text-xs rounded p-2 outline-none focus:border-orange-500 w-full h-24 font-mono resize-none"
                                />
                              </div>
                            )}
                          </div>
                        )}

                        {(options.captionLanguage === 'en' || options.captionLanguage === 'manual_srt') && (
                          <>
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-zinc-400 font-medium">Typography</span>
                              <select value={options.captionFont}
                                onChange={(e) => setOptions((prev) => ({ ...prev, captionFont: e.target.value }))}
                                className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-emerald-500">
                                <option value="Montserrat">Montserrat (Modern)</option>
                                <option value="Proxima Nova">Proxima Nova (Premium)</option>
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
                                <option value="p-silver-translucent">6. Silver Translucent Glow</option>
                                <option value="p-sunset-glow">7. Sunset Warm Glow</option>
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
                                <option value="s-dark-blue-glow">6. Dark Blue Glow</option>
                                <option value="s-matrix-green">7. Matrix Hacker Green</option>
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
                            <option value="ease-slide-up">✨ Ease Slide Up (TikTok)</option>
                            <option value="slide-right">⚡ Fast Slide Right</option>
                            <option value="none">⏹️ Hard Cut (None)</option>
                          </select>
                        </div>

                        <div className="border-t border-zinc-800/50 pt-3 mt-2 mb-2 flex flex-col gap-2">

                          <div className="flex items-center justify-between mb-1">
                            <div className="flex items-center gap-3">
                              <span className="text-xs text-sky-400 font-semibold uppercase tracking-wider">Position Preview</span>
                              <button
                                onClick={(e) => {
                                  e.preventDefault();
                                  setIsPreviewVertical(!isPreviewVertical);
                                }}
                                className="px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] text-zinc-300 transition-colors border border-zinc-600 flex items-center gap-1.5 shadow-sm active:scale-95"
                              >
                                {isPreviewVertical ? '📱 9:16 View' : '🖥️ 16:9 View'}
                              </button>

                              {isPreviewVertical && (
                                <button
                                  onClick={(e) => {
                                    e.preventDefault();
                                    setShowSafeZone(!showSafeZone);
                                  }}
                                  className={`px-2 py-0.5 rounded text-[10px] transition-colors border flex items-center gap-1.5 shadow-sm active:scale-95 ${showSafeZone ? 'bg-fuchsia-600 border-fuchsia-500 text-white' : 'bg-zinc-800 border-zinc-600 text-zinc-300 hover:bg-zinc-700'}`}
                                >
                                  🛡️ Safe Zone
                                </button>
                              )}
                            </div>
                            <span className="text-xs text-zinc-400 font-mono">{options.captionBottomPercent}% from bottom</span>
                          </div>

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

                            {isPreviewVertical && showSafeZone && (
                              <div className="absolute inset-0 pointer-events-none z-10 flex flex-col justify-between">
                                <div className="w-full bg-red-500/20 flex items-center justify-center text-[8px] font-bold text-white/50" style={{ height: '8%' }}>TOP ZONE</div>
                                <div className="flex-1 flex justify-between">
                                  <div className="bg-red-500/20" style={{ width: '5%' }}></div>
                                  <div className="bg-red-500/20 flex items-center justify-center text-[8px] font-bold text-white/50" style={{ width: '12%' }}>UI</div>
                                </div>
                                <div className="w-full bg-red-500/20 flex items-center justify-center text-[8px] font-bold text-white/50" style={{ height: '22%' }}>BOTTOM ZONE</div>
                                <div className="absolute top-[8%] bottom-[22%] left-[5%] right-[12%] border border-dashed border-green-500/60 rounded"></div>
                              </div>
                            )}

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

                          <div className="flex items-center gap-3 mt-1">
                            <span className="text-[10px] text-zinc-500 font-medium tracking-wider">SMALL</span>
                            <input
                              type="range" min="50" max="200"
                              value={options.captionScale}
                              onChange={(e) => setOptions((prev) => ({ ...prev, captionScale: parseInt(e.target.value) }))}
                              className="flex-1 h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-purple-500"
                            />
                            <span className="text-[10px] text-zinc-500 font-medium tracking-wider">LARGE</span>
                            <span className="text-xs text-zinc-400 font-mono w-10 text-right">{options.captionScale}%</span>
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

                      </div>
                    )}

                    {key === 'maskEngine' && options.maskEngine && (
                      <div className="flex flex-col gap-3 p-3 ml-2 rounded-lg bg-zinc-900/80 border border-zinc-800">

                        <div className="flex items-center justify-between mb-1 border-b border-zinc-800/50 pb-2">
                          <span className="text-xs text-sky-400 font-semibold uppercase tracking-wider">Mask Preview</span>
                        </div>

                        <div
                          className="relative rounded-lg overflow-hidden border border-zinc-700 mx-auto w-full max-w-[220px] flex items-center justify-center transition-all duration-300 shadow-inner"
                          style={{
                            aspectRatio: '9/16',
                            backgroundColor: options.maskBgMode === 'color' ? options.maskBgColor : '#000',
                            backgroundImage: options.maskBgMode === 'image' && options.maskBgImagePath ? `url(${convertFileSrc(options.maskBgImagePath)})` : 'none',
                            backgroundSize: 'cover',
                            backgroundPosition: 'center'
                          }}
                        >
                          <div
                            className="relative overflow-hidden shadow-[0_0_25px_rgba(0,0,0,0.6)] transition-all duration-300 flex items-center justify-center bg-zinc-800"
                            style={{
                              aspectRatio: options.maskRatio.replace(':', '/'),
                              height: `${options.maskScale}%`,
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
                            <option value="poth-rakke">🌴 Poth Rakke (Tropical Yellow)</option>
                            <option value="studio-blue">🔵 Studio Blue Backdrop (Skin-Safe)</option>
                            {/* ── NEW: M22 Rescue Engine ── */}
                            <option value="m22-to-iphone-4k">✨ M22 4K Rescue (Denoise & Upscale)</option>
                          </select>
                        </div>

                        {options.colorGradeStyle === 'm22-to-iphone-4k' && (
                          <div className="mt-1 p-2 bg-emerald-950/30 border border-emerald-900/50 rounded flex flex-col gap-1">
                            <span className="text-[10px] text-emerald-400 font-semibold uppercase tracking-wider">Active: Spatial Denoise + Lanczos 4K</span>
                            <span className="text-[10px] text-zinc-400 leading-tight">Removes low-light sensor grain and digitally upscales to 3840x2160 for high-bitrate social media uploads.</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="flex flex-col gap-3 p-3 rounded-lg bg-zinc-900/80 border border-zinc-800 mt-3">
                <div className="flex items-center justify-between pb-2 mb-2 border-b border-zinc-800/50">
                  <span className="text-xs text-sky-400 font-semibold uppercase tracking-wider">Cinematic Grade Engine</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-400 font-medium">The Pro Look</span>
                  <select
                    value={options.cinematicGrade}
                    onChange={(e) => setOptions((prev) => ({ ...prev, cinematicGrade: e.target.value }))}
                    className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-sky-500 font-medium max-w-[160px]"
                  >
                    <option value="none">⏹️ Off</option>
                    <option value="capcut_studio">🎬 CapCut Studio</option>
                    <option value="cinematic_cold">❄️ Cinematic Cold</option>
                    <option value="warm_podcast">🎙️ Warm Podcast</option>
                    <option value="blurred_bg">🌫️ Blurred BG</option>
                    <option value="m22-to-iphone-4k">📱 M22→iPhone 4K</option>
                    <option value="neon-blue">🔵 Neon Blue Studio</option>
                    <option value="cyber-warm">🍊 Teal & Orange</option>
                    <option value="poth-rakke">🌴 Poth Rakke</option>
                    <option value="studio-blue">🎬 Studio Blue</option>
                  </select>
                </div>
              </div>

              {options.hookEngine && (
                <div className="flex flex-col gap-3 p-3 rounded-lg bg-zinc-900/80 border border-zinc-800 mt-3">
                  <div className="flex items-center justify-between pb-2 mb-2 border-b border-zinc-800/50">
                    <span className="text-xs text-orange-400 font-semibold uppercase tracking-wider">0-Second Hook Engine</span>
                  </div>

                <div className="flex flex-col gap-2 border-b border-zinc-800/50 pb-3 mb-1">
                  
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-zinc-400 font-medium">Primary Line</span>
                    <select
                      value={options.hookPrimaryStyle}
                      onChange={(e) => setOptions((prev) => ({ ...prev, hookPrimaryStyle: e.target.value }))}
                      className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-[10px] rounded p-1 outline-none focus:border-orange-500 font-medium max-w-[140px]"
                    >
                      <option value="s-electric-teal">🌊 Electric Teal (Cyan)</option>
                      <option value="s-crimson-red">🔴 Crimson Red (Red)</option>
                      <option value="s-hormozi-yellow">🟡 Hormozi Yellow (Yellow)</option>
                      <option value="p-clean-white">⚪ Clean White (White)</option>
                      <option value="p-neon-base">🔵 Neon Base (Cyan/White)</option>
                      <option value="p-glass-silver">🪞 Glass Silver (Silver)</option>
                      <option value="p-heavy-stroke">⬛ Heavy Stroke (White/Black)</option>
                    </select>
                  </div>
                  <input 
                    type="text" 
                    placeholder="E.g. GET 3X" 
                    value={options.hookPrimaryText}
                    onChange={(e) => setOptions((prev) => ({ ...prev, hookPrimaryText: e.target.value }))}
                    className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1.5 outline-none focus:border-orange-500 w-full font-medium"
                  />

                  <div className="flex items-center justify-between mt-1 mb-1">
                    <span className="text-xs text-zinc-400 font-medium">Secondary Line</span>
                    <select
                      value={options.hookSecondaryStyle}
                      onChange={(e) => setOptions((prev) => ({ ...prev, hookSecondaryStyle: e.target.value }))}
                      className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-[10px] rounded p-1 outline-none focus:border-orange-500 font-medium max-w-[140px]"
                    >
                      <option value="s-crimson-red">🔴 Crimson Red (Red)</option>
                      <option value="s-electric-teal">🌊 Electric Teal (Cyan)</option>
                      <option value="s-hormozi-yellow">🟡 Hormozi Yellow (Yellow)</option>
                      <option value="p-clean-white">⚪ Clean White (White)</option>
                      <option value="p-neon-base">🔵 Neon Base (Cyan/White)</option>
                      <option value="p-glass-silver">🪞 Glass Silver (Silver)</option>
                      <option value="p-heavy-stroke">⬛ Heavy Stroke (White/Black)</option>
                    </select>
                  </div>
                  <input 
                    type="text" 
                    placeholder="E.g. FOLLOWERS" 
                    value={options.hookSecondaryText}
                    onChange={(e) => setOptions((prev) => ({ ...prev, hookSecondaryText: e.target.value }))}
                    className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1.5 outline-none focus:border-orange-500 w-full font-medium"
                  />

                  <div className="flex items-center justify-between mt-2 mb-1">
                    <span className="text-xs text-zinc-400 font-medium">Glass Background</span>
                    <select
                      value={options.hookBgColor}
                      onChange={(e) => setOptions((prev) => ({ ...prev, hookBgColor: e.target.value }))}
                      className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-[10px] rounded p-1 outline-none focus:border-orange-500 font-medium max-w-[140px]"
                    >
                      <option value="transparent">❌ None (Transparent)</option>
                      <option value="rgba(255, 255, 255, 0.15)">⚪ Frosted White</option>
                      <option value="rgba(0, 0, 0, 0.4)">⬛ Dark Glass</option>
                      <option value="rgba(0, 100, 255, 0.25)">🔵 Blue Glass</option>
                      <option value="dark-blue-glow">🌌 Dark Blue Glow</option>
                      <option value="silver-glow">✨ Silver Glow</option>
                      <option value="rgba(0, 255, 255, 0.15)">🌊 Cyan Tint</option>
                      <option value="rgba(255, 0, 0, 0.15)">🔴 Red Tint</option>
                    </select>
                  </div>

                  {(options.hookPrimaryText || options.hookSecondaryText) && (
                    <div className="flex items-center gap-3 mt-2">
                      <span className="text-[10px] text-zinc-500 font-medium tracking-wider min-w-[70px]">DURATION</span>
                      <input type="range" min="0.5" max="3" step="0.1" value={options.hookDuration} onChange={(e) => setOptions((prev) => ({ ...prev, hookDuration: parseFloat(e.target.value) }))} className="flex-1 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-orange-500" />
                      <span className="text-[10px] text-zinc-500 w-8 text-right font-mono">{options.hookDuration}s</span>
                    </div>
                  )}

                  <div className="border-t border-zinc-800/50 pt-3 mt-2 flex flex-col gap-2">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-sky-400 font-semibold uppercase tracking-wider">Position Preview</span>
                        <button
                          onClick={(e) => {
                            e.preventDefault();
                            setIsPreviewVertical(!isPreviewVertical);
                          }}
                          className="px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] text-zinc-300 transition-colors border border-zinc-600 flex items-center gap-1.5 shadow-sm active:scale-95"
                        >
                          {isPreviewVertical ? '📱 9:16 View' : '🖥️ 16:9 View'}
                        </button>

                        {isPreviewVertical && (
                          <button
                            onClick={(e) => {
                              e.preventDefault();
                              setShowSafeZone(!showSafeZone);
                            }}
                            className={`px-2 py-0.5 rounded text-[10px] transition-colors border flex items-center gap-1.5 shadow-sm active:scale-95 ${showSafeZone ? 'bg-fuchsia-600 border-fuchsia-500 text-white' : 'bg-zinc-800 border-zinc-600 text-zinc-300 hover:bg-zinc-700'}`}
                          >
                            🛡️ Safe Zone
                          </button>
                        )}
                      </div>
                      <span className="text-xs text-zinc-400 font-mono">{options.hookYPercent}% from top</span>
                    </div>

                    <div className={`relative bg-black rounded-lg overflow-hidden border border-zinc-700 group pointer-events-none mx-auto transition-all duration-300 ease-in-out ${isPreviewVertical ? 'w-48 h-[340px]' : 'w-full h-44'}`}>
                      {selectedFilePath ? (
                        <video src={convertFileSrc(selectedFilePath)} className="w-full h-full object-cover opacity-60" preload="auto" muted playsInline onLoadedMetadata={(e) => e.currentTarget.currentTime = 0.0} />
                      ) : (
                        <div className="w-full h-full flex flex-col items-center justify-center text-zinc-600 space-y-2">
                          <span className="text-2xl">🖼️</span>
                          <span className="text-[10px] uppercase tracking-wider font-semibold">Awaiting Video</span>
                        </div>
                      )}
                      
                      {isPreviewVertical && showSafeZone && (
                        <div className="absolute inset-0 pointer-events-none z-10 flex flex-col justify-between">
                          <div className="w-full bg-red-500/20 flex items-center justify-center text-[8px] font-bold text-white/50" style={{ height: '8%' }}>TOP ZONE</div>
                          <div className="flex-1 flex justify-between">
                            <div className="bg-red-500/20" style={{ width: '5%' }}></div>
                            <div className="bg-red-500/20 flex items-center justify-center text-[8px] font-bold text-white/50" style={{ width: '12%' }}>UI</div>
                          </div>
                          <div className="w-full bg-red-500/20 flex items-center justify-center text-[8px] font-bold text-white/50" style={{ height: '22%' }}>BOTTOM ZONE</div>
                        </div>
                      )}

                      <div className="absolute left-0 right-0 flex flex-col items-center justify-center w-full transition-all duration-75 ease-out" style={{ top: `${options.hookYPercent}%`, transform: `translateY(-50%) scale(${options.hookSizePercent / 100})`, transformOrigin: 'center center' }}>
                        <div style={{
                          background: options.hookBgColor === 'dark-blue-glow' ? 'rgba(0, 20, 60, 0.6)' : 
                                      options.hookBgColor === 'silver-glow' ? 'rgba(255, 255, 255, 0.1)' : 
                                      options.hookBgColor !== 'transparent' ? options.hookBgColor : 'transparent',
                          border: options.hookBgColor === 'dark-blue-glow' ? '2px solid rgba(0, 150, 255, 0.4)' : 
                                  options.hookBgColor === 'silver-glow' ? '2px solid rgba(255, 255, 255, 0.6)' : 
                                  options.hookBgColor !== 'transparent' ? '2px solid rgba(255, 255, 255, 0.15)' : 'none',
                          borderRadius: options.hookBgColor !== 'transparent' ? '16px' : '0',
                          padding: options.hookBgColor !== 'transparent' ? '12px 20px' : '0',
                          boxShadow: options.hookBgColor === 'dark-blue-glow' ? '0 0 30px rgba(0, 100, 255, 0.8), inset 0 1px 0 rgba(255,255,255,0.2)' : 
                                     options.hookBgColor === 'silver-glow' ? '0 0 30px rgba(200, 220, 255, 0.7), inset 0 1px 0 rgba(255,255,255,0.5)' : 
                                     options.hookBgColor !== 'transparent' ? '0 10px 30px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.2)' : 'none',
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}>
                          {options.hookPrimaryText && (
                            <div className="bg-orange-500/80 backdrop-blur-md border border-orange-400 text-white px-3 py-1 rounded shadow-2xl font-bold text-[10px] uppercase tracking-widest leading-none mb-1">
                              {options.hookPrimaryText}
                            </div>
                          )}
                          {options.hookSecondaryText && (
                            <div className="bg-white/90 backdrop-blur-md border border-zinc-200 text-black px-3 py-1 rounded shadow-2xl font-bold text-[10px] uppercase tracking-widest leading-none">
                              {options.hookSecondaryText}
                            </div>
                          )}
                          {(!options.hookPrimaryText && !options.hookSecondaryText) && (
                            <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-600 text-white px-4 py-1.5 rounded-md shadow-2xl font-bold text-[11px] uppercase tracking-widest whitespace-nowrap">
                              Hook Engine Preview
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col gap-2 mt-2">
                      <div className="flex items-center gap-3">
                        <span className="text-[10px] text-zinc-500 font-medium tracking-wider w-10">TOP</span>
                        <input
                          type="range" min="5" max="95"
                          value={options.hookYPercent}
                          onChange={(e) => setOptions((prev) => ({ ...prev, hookYPercent: parseInt(e.target.value) }))}
                          className="flex-1 h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-sky-500"
                        />
                        <span className="text-[10px] text-zinc-500 font-medium tracking-wider w-10 text-right">BOTTOM</span>
                      </div>
                      
                      <div className="flex items-center gap-3">
                        <span className="text-[10px] text-zinc-500 font-medium tracking-wider w-10">SMALL</span>
                        <input
                          type="range" min="50" max="180"
                          value={options.hookSizePercent}
                          onChange={(e) => setOptions((prev) => ({ ...prev, hookSizePercent: parseInt(e.target.value) }))}
                          className="flex-1 h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-fuchsia-500"
                        />
                        <span className="text-[10px] text-zinc-500 font-medium tracking-wider w-10 text-right">{options.hookSizePercent}%</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-400 font-medium">Visual & SFX Impact</span>
                  <select
                    value={options.startingHook}
                    onChange={(e) => setOptions((prev) => ({ ...prev, startingHook: e.target.value }))}
                    className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded p-1 outline-none focus:border-orange-500 font-medium max-w-[160px]"
                  >
                    <option value="none">⏹️ Off</option>
                    <option value="capcut_drop">⬇️ CapCut Hologram Drop</option>
                    <option value="drop_in">☄️ AE Drop-In (Elastic)</option>
                    <option value="flash_drop">💥 AE Flash Drop</option>
                    <option value="flash">⚡ Studio Bloom Flash</option>
                    <option value="glitch">📺 Cyber Pixel-Sort</option>
                    <option value="impact">🎬 Push-In Impact</option>
                    <option value="blur_zoom">🔍 Cinematic Blur-Zoom</option>
                  </select>
                </div>

                {options.startingHook !== 'none' && (
                  <p className="text-[10px] text-orange-400/80 italic mt-1 leading-tight">
                    This will trigger a 350ms pattern-interrupt and mix in the corresponding SFX file at the exact moment the first frame of audio starts.
                  </p>
                )}
              </div>
              )}
            </div>

            {isProcessing ? (
              <div className="flex gap-2">
                <button disabled className="flex-1 py-4 rounded-xl font-bold text-base bg-emerald-600/40 text-white/50 cursor-not-allowed">
                  <span className="flex items-center justify-center gap-2">
                    <span className="animate-spin">⚙️</span> Processing locally…
                  </span>
                </button>
                <button onClick={handleStopPipeline} className="px-6 py-4 rounded-xl font-bold text-base bg-red-600 hover:bg-red-500 shadow-[0_0_20px_rgba(220,38,38,0.35)] transition-all flex items-center justify-center gap-2 text-white">
                  <span>🛑 Stop</span>
                </button>
              </div>
            ) : (
              <button onClick={handleRunPipeline}
                disabled={!selectedFilePath || (activeCount === 0 && timelineScenes.length <= 1 && timelineScenes.every(s => !s.bgImagePath && !s.textBehind))}
                className="w-full py-4 rounded-xl font-bold text-base bg-emerald-600 hover:bg-emerald-500 active:scale-[0.99] shadow-[0_0_20px_rgba(5,150,105,0.35)] disabled:opacity-40 disabled:cursor-not-allowed transition-all">
                RENDER VIDEO
              </button>
            )}

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
      ) : activeTab === 'lead' ? (
        <LeadEngineTab />
      ) : activeTab === 'automator' ? (
        <NexusAutomatorTab />
      ) : activeTab === 'carousel' ? (
        <CarouselTab />
      ) : null}
    </main>
  );
}