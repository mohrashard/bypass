import { useState, useRef, useEffect, useCallback } from 'react';
import { invoke, convertFileSrc } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { open } from '@tauri-apps/plugin-dialog';

interface Segment {
  start: number;
  end: number;
  phrase: string;
  htmlCode?: string;
}

const DEFAULT_HTML = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 100vw; height: 100vh;
    background: transparent;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Segoe UI', sans-serif;
    overflow: hidden;
  }
  .card {
    background: rgba(0,0,0,0.8);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 2vw 4vw;
    color: white;
    font-size: 4vw;
    font-weight: bold;
    text-align: center;
    animation: pop 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
  }
  @keyframes pop {
    0% { transform: scale(0.8); opacity: 0; }
    100% { transform: scale(1); opacity: 1; }
  }
</style>
</head>
<body>
  <div class="card">
    <div id="text">ANIMATION TEXT</div>
  </div>
</body>
</html>`;

export default function NexusAutomatorTab() {
  const [videoPath, setVideoPath] = useState<string | null>(null);
  
  const [segments, setSegments] = useState<Segment[]>([]);
  const [history, setHistory] = useState<Segment[][]>([]); // Undo history
  const [activeSegmentIdx, setActiveSegmentIdx] = useState<number | null>(null);
  const [selectedIndices, setSelectedIndices] = useState<number[]>([]);
  const textAreaRef = useRef<HTMLTextAreaElement>(null);
  
  const [videoCurrentTime, setVideoCurrentTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(1);
  
  const [prompt, setPrompt] = useState<string>('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [editorHtml, setEditorHtml] = useState<string>('');
  const [previewHtml, setPreviewHtml] = useState<string>('');
  const [iframeUrl, setIframeUrl] = useState<string>('');
  const [autoRefresh] = useState(true);
  const [editorFontSize, setEditorFontSize] = useState(13);
  
  const [terminalLines, setTerminalLines] = useState<string[]>([]);
  const [isRendering, setIsRendering] = useState(false);
  const consoleEndRef = useRef<HTMLDivElement>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Memoize iframe URL to prevent blinking during playback
  useEffect(() => {
    if (!previewHtml) {
      setIframeUrl('');
      return;
    }
    
    // Inject permanent global volume reduction for preview
    const injectedScript = `
      <script>
        document.addEventListener('DOMContentLoaded', () => {
          // Tone.js
          if (window.Tone && window.Tone.Destination) {
            window.Tone.Destination.volume.value = -15; // Lower by 15 decibels
          }
          // Native Audio/Video
          document.querySelectorAll('audio, video').forEach(media => media.volume = 0.15);
        });
      </script>
    `;
    const finalHtml = previewHtml.includes('</head>') 
      ? previewHtml.replace('</head>', injectedScript + '</head>')
      : injectedScript + previewHtml;

    const blob = new Blob([finalHtml], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    setIframeUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [previewHtml]);

  // ── Listen to Engine Terminal Logs ───────────────────────────────────────
  useEffect(() => {
    const unlistenPromise = listen<string>('automator-stdout', (event) => {
      const raw = event.payload ?? '';
      const incoming = raw.split('\n').filter(l => l.trim().length > 0);
      if (incoming.length > 0) {
        setTerminalLines(prev => [...prev, ...incoming]);
      }
    });
    return () => {
      unlistenPromise.then(unlisten => unlisten());
    };
  }, []);

  useEffect(() => {
    consoleEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [terminalLines]);

  // ── File Loaders ──────────────────────────────────────────────────────────
  const handleLoadVideo = async () => {
    const selected = await open({
      multiple: false,
      filters: [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm'] }],
    }).catch(() => null);
    if (selected && typeof selected === 'string') {
      setVideoPath(selected);
    }
  };

  const handleLoadJSON = async () => {
    const selected = await open({
      multiple: false,
      filters: [{ name: 'JSON', extensions: ['json'] }],
    }).catch(() => null);
    if (selected && typeof selected === 'string') {
      try {
        // Read file contents via Tauri core plugin or fetch if we know the path is absolute.
        // Actually since we don't have fs plugin imported here, we might just ask the python engine to read it,
        // OR we can use convertFileSrc to fetch it.
        const res = await fetch(convertFileSrc(selected));
        const data = await res.json();
        
        // Support either an array of segments or { segments: [] }
        const parsedSegments = Array.isArray(data) ? data : data.segments || [];
        
        if (parsedSegments.length > 0) {
          setHistory(prev => [...prev, segments]); // Save to history
          setSegments(parsedSegments.map((s: any) => ({
            start: s.start,
            end: s.end,
            phrase: (s.phrase || s.text || s.word || "").replace(/<[^>]+>/g, '').trim(),
            htmlCode: '' // Initially empty
          })));
        } else {
          alert("No segments found in JSON.");
        }
      } catch (err) {
        alert("Failed to parse JSON: " + err);
      }
    }
  };

  const handlePasteData = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text) {
        alert("Clipboard is empty.");
        return;
      }

      // Try JSON first
      try {
        const data = JSON.parse(text);
        const parsedSegments = Array.isArray(data) ? data : data.segments || [];
        if (parsedSegments.length > 0) {
          setHistory(prev => [...prev, segments]); // Save to history
          setSegments(parsedSegments.map((s: any) => ({
            start: s.start,
            end: s.end,
            phrase: (s.phrase || s.text || s.word || "").replace(/<[^>]+>/g, '').trim(),
            htmlCode: ''
          })));
          return;
        }
      } catch (e) {
        // Not JSON, fall back to SRT parser
      }

      // Try parsing standard SRT
      const blocks = text.trim().split(/\n\s*\n/);
      const newSegments: Segment[] = [];
      for (const block of blocks) {
        const lines = block.split('\n').map(l => l.trim()).filter(Boolean);
        if (lines.length >= 3) {
          const timeLine = lines[1];
          // Matches 00:00:00,000 --> 00:00:01,500
          const match = timeLine.match(/(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})/);
          if (match) {
            const start = parseInt(match[1])*3600 + parseInt(match[2])*60 + parseInt(match[3]) + parseInt(match[4])/1000;
            const end = parseInt(match[5])*3600 + parseInt(match[6])*60 + parseInt(match[7]) + parseInt(match[8])/1000;
            const rawPhrase = lines.slice(2).join('\n').trim();
            const cleanPhrase = rawPhrase.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
            newSegments.push({ start, end, phrase: cleanPhrase, htmlCode: '' });
          }
        }
      }

      if (newSegments.length > 0) {
        setHistory(prev => [...prev, segments]); // Save to history
        setSegments(newSegments);
        setSelectedIndices([]);
        setActiveSegmentIdx(null);
      } else {
        alert("Could not parse clipboard data as JSON or standard SRT. Please ensure it's copied correctly.");
      }
    } catch (err) {
      alert("Failed to read clipboard. You may need to grant clipboard permissions, or paste manually: " + err);
    }
  };

  // ── Video & Timeline Sync ─────────────────────────────────────────────────
  const handleSelectSegment = (idx: number) => {
    setActiveSegmentIdx(idx);
    const seg = segments[idx];
    
    // Seek video
    if (videoRef.current) {
      videoRef.current.currentTime = seg.start;
      videoRef.current.pause();
    }
    
    // Load code into editor
    const code = seg.htmlCode || DEFAULT_HTML.replace('ANIMATION TEXT', seg.phrase.toUpperCase());
    setEditorHtml(code);
    setPreviewHtml(code);
  };

  const handleToggleCheckbox = (e: React.ChangeEvent<HTMLInputElement>, idx: number) => {
    e.stopPropagation();
    setSelectedIndices(prev => 
      e.target.checked ? [...prev, idx] : prev.filter(i => i !== idx)
    );
  };

  const handleCopySelected = async () => {
    if (selectedIndices.length === 0) return;
    const sorted = [...selectedIndices].sort((a, b) => a - b);
    const combinedPhrase = sorted.map(i => segments[i].phrase).join(' ');
    try {
      await navigator.clipboard.writeText(combinedPhrase);
    } catch (err) {
      alert("Failed to copy to clipboard");
    }
  };

  const handleMergeSelected = () => {
    if (selectedIndices.length < 2) return;
    const sortedIndices = [...selectedIndices].sort((a, b) => a - b);
    
    // Save current state to history before mutating
    setHistory(prev => [...prev, segments]);

    const mergedStart = segments[sortedIndices[0]].start;
    const mergedEnd = segments[sortedIndices[sortedIndices.length - 1]].end;
    const mergedPhrase = sortedIndices.map(i => segments[i].phrase).join(' ');
    
    const newSegments = [...segments];
    // Remove the selected ones from back to front
    for (let i = sortedIndices.length - 1; i >= 0; i--) {
      newSegments.splice(sortedIndices[i], 1);
    }
    
    // Insert the merged one at the position of the first
    newSegments.splice(sortedIndices[0], 0, {
      start: mergedStart,
      end: mergedEnd,
      phrase: mergedPhrase,
      htmlCode: '' // Reset code for new merged segment
    });
    
    setSegments(newSegments);
    setSelectedIndices([]);
    setActiveSegmentIdx(sortedIndices[0]);
  };

  // Sync editor changes back to the active segment
  const handleEditorChange = (newHtml: string) => {
    setEditorHtml(newHtml);
    if (activeSegmentIdx !== null) {
      const newSegments = [...segments];
      newSegments[activeSegmentIdx].htmlCode = newHtml;
      setSegments(newSegments);
    }
  };

  const handleUndo = () => {
    if (history.length === 0) return;
    const previousSegments = history[history.length - 1];
    setSegments(previousSegments);
    setHistory(prev => prev.slice(0, -1));
    setSelectedIndices([]);
    setActiveSegmentIdx(null);
  };

  const handleSplitSegment = (e: React.MouseEvent, idx: number) => {
    e.stopPropagation();
    
    setHistory(prev => [...prev, segments]);

    const seg = segments[idx];
    let p1 = "";
    let p2 = "";
    let ratio = 0.5;

    // Split exactly at cursor position if available
    if (textAreaRef.current && textAreaRef.current.selectionStart > 0 && textAreaRef.current.selectionStart < seg.phrase.length) {
      const caretPos = textAreaRef.current.selectionStart;
      p1 = seg.phrase.slice(0, caretPos).trim();
      p2 = seg.phrase.slice(caretPos).trim();
      ratio = caretPos / seg.phrase.length;
    } else {
      // Fallback: split by words exactly in half
      const words = seg.phrase.trim().split(/\s+/);
      if (words.length < 2) {
         const midStr = Math.floor(seg.phrase.length / 2);
         p1 = seg.phrase.slice(0, midStr);
         p2 = seg.phrase.slice(midStr);
      } else {
         const midIdx = Math.ceil(words.length / 2);
         p1 = words.slice(0, midIdx).join(' ');
         p2 = words.slice(midIdx).join(' ');
         ratio = midIdx / words.length;
      }
    }

    const midTime = seg.start + (seg.end - seg.start) * ratio;

    const newSegments = [...segments];
    newSegments.splice(idx, 1, 
      { start: seg.start, end: midTime, phrase: p1, htmlCode: seg.htmlCode },
      { start: midTime, end: seg.end, phrase: p2, htmlCode: '' }
    );
    setSegments(newSegments);
    setActiveSegmentIdx(idx); // Keep focus on the first half
  };

  const handlePhraseEdit = (e: React.ChangeEvent<HTMLTextAreaElement>, idx: number) => {
    const newSegments = [...segments];
    newSegments[idx].phrase = e.target.value;
    setSegments(newSegments);
  };

  const handleTimeEdit = (idx: number, field: 'start' | 'end', value: number) => {
    if (isNaN(value)) return;
    const newSegments = [...segments];
    newSegments[idx][field] = value;
    setSegments(newSegments);
  };

  // ── Live preview debounce ──────────────────────────────────────────────
  useEffect(() => {
    if (!autoRefresh) return;
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(() => {
      setPreviewHtml(editorHtml);
    }, 400);
    return () => { if (refreshTimer.current) clearTimeout(refreshTimer.current); };
  }, [editorHtml, autoRefresh]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = textareaRef.current!;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const newVal = editorHtml.substring(0, start) + '  ' + editorHtml.substring(end);
      handleEditorChange(newVal);
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 2;
      });
    }
  }, [editorHtml]);

  // ── AI Generation (Phase 3) ────────────────────────────────────────────────
  const handleGenerateAI = async () => {
    if (activeSegmentIdx === null) return;
    setIsGenerating(true);
    
    const seg = segments[activeSegmentIdx];
    const optionsJson = JSON.stringify({
      action: "generate",
      prompt: prompt || "Make it dynamic, premium, and visually striking.",
      phrase: seg.phrase
    });

    try {
      const output = await invoke<string>('run_nexus_automator', {
        optionsJson: optionsJson
      });
      
      const startTag = '__HTML_START__';
      const endTag = '__HTML_END__';
      const startIndex = output.indexOf(startTag);
      const endIndex = output.indexOf(endTag);
      
      if (startIndex !== -1 && endIndex !== -1) {
        const generatedHtml = output.substring(startIndex + startTag.length, endIndex).trim();
        handleEditorChange(generatedHtml);
      } else {
        alert("Failed to parse HTML from engine output. Check terminal/logs.");
      }
    } catch (err) {
      alert("Error calling Groq API: " + String(err));
    } finally {
      setIsGenerating(false);
    }
  };

  // ── Batch Rendering (Phase 5) ──────────────────────────────────────────────
  const handleRenderFinal = async () => {
    if (!videoPath) {
      alert("Please load a base video first!");
      return;
    }
    
    const validSegments = segments.filter(s => s.htmlCode && s.htmlCode.trim() !== "");
    if (validSegments.length === 0) {
      alert("No generated HTML found in any segments. Generate some code first.");
      return;
    }
    
    setIsRendering(true);
    setTerminalLines(["[🎬] Starting Nexus Automator Batch Render...", "[⚙️] Initializing headless chromium engine..."]);
    
    const optionsJson = JSON.stringify({
      action: "render",
      videoPath: videoPath,
      segments: validSegments
    });
    
    try {
      const output = await invoke<string>('run_nexus_automator', {
        optionsJson: optionsJson
      });
      console.log("Render Output:", output);
      setTerminalLines(prev => [...prev, "", "✅ Render Complete!", output]);
    } catch (err) {
      setTerminalLines(prev => [...prev, "", "❌ Render Failed:", String(err)]);
      alert("Render Failed: " + String(err));
    } finally {
      setIsRendering(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 w-full overflow-hidden bg-zinc-950 font-sans text-white">
      {/* ── Top Bar ───────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-4 px-4 py-3 border-b border-zinc-800 bg-zinc-900 flex-shrink-0">
        <span className="text-xs font-bold tracking-[0.2em] text-pink-400 uppercase flex items-center gap-2">
          <span className="text-lg">🎬</span> Nexus Automator
        </span>
        <div className="h-4 w-px bg-zinc-700" />
        
        <button onClick={handleLoadVideo} className="text-xs px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition-colors flex items-center gap-2">
          <span>{videoPath ? '✅ Video Loaded' : '1. Load Video'}</span>
        </button>
        <button onClick={handleLoadJSON} className="text-xs px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition-colors flex items-center gap-2">
          <span>{segments.length > 0 ? `✅ ${segments.length} Segments` : '2. Load SRT'}</span>
        </button>
        <button onClick={handlePasteData} className="text-xs px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition-colors flex items-center gap-2" title="Paste SRT or JSON from Clipboard">
          <span>📋 Paste</span>
        </button>

        <div className="flex-1" />
        <button 
          onClick={handleRenderFinal}
          disabled={isRendering || !videoPath || segments.length === 0}
          className="text-xs px-4 py-1.5 rounded bg-pink-600 hover:bg-pink-500 text-white font-bold tracking-wide transition-colors flex items-center gap-2 shadow-[0_0_12px_rgba(219,39,119,0.3)] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <span>🎥</span> {isRendering ? "Rendering Engine..." : "Render Final"}
        </button>
      </div>

      {/* ── 3-Pane Layout ─────────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        
        {/* ── LEFT PANE: Timeline/Segments ───────────────────────────────── */}
        <div className="w-[300px] border-r border-zinc-800 bg-zinc-950 flex flex-col flex-shrink-0">
          <div className="px-4 py-2 border-b border-zinc-800 bg-zinc-900/50 flex flex-col gap-2">
            <div className="flex justify-between items-center">
              <span className="text-[10px] font-bold text-zinc-500 tracking-wider uppercase">Scenes / Timeline</span>
              {history.length > 0 && (
                <button 
                  onClick={handleUndo}
                  className="text-[10px] font-bold text-zinc-400 hover:text-white transition-colors flex items-center gap-1 bg-zinc-800 px-2 py-1 rounded"
                >
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                  </svg>
                  Undo
                </button>
              )}
            </div>
            {selectedIndices.length > 0 && (
              <div className="flex gap-2">
                <button 
                  onClick={handleCopySelected}
                  className="text-[10px] font-bold bg-zinc-800 text-zinc-300 hover:bg-zinc-700 px-2 py-1 rounded transition-colors flex-1"
                >
                  Copy ({selectedIndices.length})
                </button>
                {selectedIndices.length > 1 && (
                  <button 
                    onClick={handleMergeSelected}
                    className="text-[10px] font-bold bg-pink-600/20 text-pink-400 hover:bg-pink-600/40 px-2 py-1 rounded transition-colors flex-1"
                  >
                    Merge Blocks
                  </button>
                )}
              </div>
            )}
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {segments.length === 0 ? (
              <div className="text-zinc-600 text-xs text-center p-4">No segments loaded.</div>
            ) : (
              segments.map((seg, idx) => {
                const isSelected = selectedIndices.includes(idx);
                const isActive = activeSegmentIdx === idx;
                return (
                  <div
                    key={idx}
                    onClick={() => {
                      if (window.getSelection()?.toString().length) return;
                      handleSelectSegment(idx);
                    }}
                    className={`w-full text-left px-3 py-2 rounded border transition-colors flex flex-col gap-1 cursor-pointer select-text relative ${
                      isActive
                        ? 'bg-pink-600/20 border-pink-500 text-white' 
                        : isSelected
                        ? 'bg-zinc-800 border-zinc-600 text-zinc-200'
                        : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
                    }`}
                  >
                    <div className="flex justify-between items-center w-full">
                      <span className="text-[10px] font-mono text-zinc-500 pointer-events-none">[{seg.start.toFixed(2)}s - {seg.end.toFixed(2)}s]</span>
                      
                      <div className="flex items-center gap-2">
                        {isActive && (
                          <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                            <div className="flex items-center gap-1 bg-zinc-800 rounded px-1.5 py-0.5 border border-zinc-700">
                               <span className="text-[9px] text-zinc-400" title="Animation Duration">⏱️</span>
                               <input 
                                 type="number"
                                 step="0.1"
                                 value={Number((seg.end - seg.start).toFixed(2)).toString()}
                                 onChange={(e) => {
                                   const val = parseFloat(e.target.value);
                                   if (!isNaN(val) && val > 0) {
                                      handleTimeEdit(idx, 'end', seg.start + val);
                                   }
                                 }}
                                 className="w-10 bg-transparent text-[10px] text-white font-mono outline-none text-center"
                                 title="Set exact animation duration in seconds"
                               />
                               <span className="text-[9px] text-zinc-500 font-mono">s</span>
                            </div>
                            <button 
                              onClick={(e) => handleSplitSegment(e, idx)}
                              className="text-[9px] bg-zinc-700 hover:bg-zinc-600 text-zinc-300 px-1.5 py-0.5 rounded transition-colors"
                              title="Split this block at cursor"
                            >
                              ✂️ Split
                            </button>
                          </div>
                        )}
                        {seg.htmlCode && <span className="text-[8px] bg-emerald-500/20 text-emerald-400 px-1 rounded uppercase pointer-events-none">Code Added</span>}
                        <input 
                          type="checkbox" 
                          checked={isSelected}
                          onChange={(e) => handleToggleCheckbox(e, idx)}
                          onClick={(e) => e.stopPropagation()}
                          className="w-3 h-3 accent-pink-500 cursor-pointer"
                        />
                      </div>
                    </div>
                    {isActive ? (
                      <textarea 
                        ref={textAreaRef}
                        value={seg.phrase}
                        onChange={(e) => handlePhraseEdit(e, idx)}
                        onClick={(e) => e.stopPropagation()}
                        className="text-sm font-medium leading-tight bg-black/30 border border-pink-500/50 rounded p-1 w-full text-white resize-none outline-none focus:border-pink-400"
                        rows={2}
                      />
                    ) : (
                      <span className="text-sm font-medium leading-tight line-clamp-2 pointer-events-none">{seg.phrase}</span>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* ── CENTER PANE: Video + Preview Overlay ───────────────────────── */}
        <div className="flex-1 flex flex-col border-r border-zinc-800 bg-black relative">
          <div className="px-4 py-2 border-b border-zinc-800 bg-zinc-900/50 flex justify-between items-center absolute top-0 w-full z-10">
            <span className="text-[10px] font-bold text-zinc-500 tracking-wider uppercase">Live Preview Overlay</span>
          </div>
          
          <div className="flex-1 relative flex items-center justify-center p-8 mt-8">
             <div className="relative aspect-[9/16] h-full max-h-[800px] border border-zinc-800 bg-zinc-950 rounded-lg overflow-hidden shadow-2xl">
                {/* Base Video */}
                {videoPath ? (
                  <video 
                    ref={videoRef}
                    src={convertFileSrc(videoPath)}
                    className="absolute inset-0 w-full h-full object-cover"
                    controls={false}
                    onTimeUpdate={() => setVideoCurrentTime(videoRef.current?.currentTime || 0)}
                    onLoadedMetadata={() => setVideoDuration(videoRef.current?.duration || 1)}
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-zinc-700 text-xs font-medium">No Video</div>
                )}
                
                {/* Transparent Iframe Overlay */}
                {activeSegmentIdx !== null && (
                  <div className="absolute inset-0 z-10 pointer-events-none">
                    {(() => {
                      const activeSeg = segments[activeSegmentIdx];
                      const isVisible = videoCurrentTime >= activeSeg.start && videoCurrentTime <= activeSeg.end;
                      return (isVisible && iframeUrl) ? (
                        <iframe
                          src={iframeUrl}
                          className="w-full h-full border-none"
                          sandbox="allow-scripts allow-same-origin"
                          title="Overlay Preview"
                        />
                      ) : null;
                    })()}
                  </div>
                )}
             </div>
          </div>
          
          {/* Video Controls (Timeline & Scrubber) */}
          <div className="h-16 border-t border-zinc-800 bg-zinc-900 flex items-center px-6 gap-4 flex-shrink-0">
             <button onClick={() => videoRef.current?.play()} className="text-zinc-400 hover:text-white transition-colors" title="Play">
               <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd" /></svg>
             </button>
             <button onClick={() => videoRef.current?.pause()} className="text-zinc-400 hover:text-white transition-colors" title="Pause">
               <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" /></svg>
             </button>
             
             <span className="text-xs text-zinc-500 font-mono w-12 text-right">
               {videoCurrentTime.toFixed(1)}s
             </span>
             <input 
                type="range"
                min="0"
                max={videoDuration}
                step="0.01"
                value={videoCurrentTime}
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  if (videoRef.current) {
                    videoRef.current.currentTime = val;
                  }
                  setVideoCurrentTime(val);
                }}
                className="flex-1 accent-pink-500 cursor-pointer h-1.5 bg-zinc-800 appearance-none rounded-full outline-none hover:bg-zinc-700 transition-colors"
             />
             <span className="text-xs text-zinc-500 font-mono w-12">
               {videoDuration.toFixed(1)}s
             </span>
          </div>
        </div>

        {/* ── RIGHT PANE: Code Editor & AI Prompter ──────────────────────── */}
        <div className="w-[450px] bg-zinc-950 flex flex-col flex-shrink-0 min-w-0">
          
          {/* AI Prompter */}
          <div className="p-4 border-b border-zinc-800 bg-zinc-900 flex flex-col gap-2">
            <span className="text-[10px] font-bold text-pink-400 tracking-wider uppercase flex items-center gap-2">
               <span>🤖</span> AI Director
            </span>
            <textarea 
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              placeholder="e.g. 'Make the word slide in from the left glowing red, like a cyberpunk warning sign...'"
              className="w-full bg-zinc-950 border border-zinc-700 rounded p-2 text-sm text-zinc-200 outline-none focus:border-pink-500 resize-none h-20"
            />
            <button 
              onClick={handleGenerateAI}
              disabled={isGenerating || activeSegmentIdx === null}
              className="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isGenerating ? "Generating..." : "Generate Code with Groq"}
            </button>
          </div>

          {/* Editor Header */}
          <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-900/60 border-b border-zinc-800 flex-shrink-0">
            <span className="text-[10px] text-zinc-600 tracking-widest uppercase">index.html</span>
            <div className="flex gap-2">
               <button onClick={() => setEditorFontSize(s => Math.max(10, s - 1))} className="text-zinc-500 hover:text-white text-xs px-1">−</button>
               <span className="text-[10px] text-zinc-600">{editorFontSize}</span>
               <button onClick={() => setEditorFontSize(s => Math.min(20, s + 1))} className="text-zinc-500 hover:text-white text-xs px-1">+</button>
            </div>
          </div>

          {/* Code Editor */}
          <div className="flex-1 relative overflow-hidden flex">
            {/* Line Numbers */}
            <div
              className="select-none text-right pr-3 pt-3 text-zinc-700 overflow-hidden flex-shrink-0 bg-zinc-900 border-r border-zinc-800"
              style={{
                fontSize: editorFontSize,
                fontFamily: "'JetBrains Mono', monospace",
                lineHeight: '1.6',
                minWidth: '40px',
              }}
            >
              {Array.from({ length: (editorHtml.match(/\n/g) || []).length + 1 }, (_, i) => (
                <div key={i}>{i + 1}</div>
              ))}
            </div>

            {/* Textarea */}
            <textarea
              ref={textareaRef}
              value={editorHtml}
              onChange={e => handleEditorChange(e.target.value)}
              onKeyDown={handleKeyDown}
              spellCheck={false}
              className="flex-1 resize-none border-none outline-none bg-transparent text-zinc-200 leading-relaxed p-3 overflow-auto"
              style={{
                fontSize: editorFontSize,
                fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
                lineHeight: '1.6',
                caretColor: '#ec4899',
                tabSize: 2,
                whiteSpace: 'pre',
                overflowWrap: 'normal',
              }}
            />
          </div>
          
          {/* Terminal Console */}
          {terminalLines.length > 0 && (
            <div className="h-64 border-t border-zinc-800 bg-black flex flex-col flex-shrink-0">
               <div className="px-3 py-1.5 border-b border-zinc-800 bg-zinc-900 flex justify-between items-center">
                 <div className="flex items-center gap-2">
                   <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                   <span className="text-[10px] font-mono font-bold text-zinc-400">ENGINE TERMINAL</span>
                 </div>
                 <button onClick={() => setTerminalLines([])} className="text-[10px] text-zinc-500 hover:text-white">Clear</button>
               </div>
               <div className="flex-1 overflow-y-auto p-3 text-[10px] font-mono leading-relaxed tracking-tight">
                  {terminalLines.map((line, i) => (
                    <div key={i} className={`mb-1 ${line.includes('ERROR') || line.includes('❌') ? 'text-red-400 font-bold' : line.includes('✅') ? 'text-emerald-400 font-bold' : line.includes(']') ? 'text-purple-300' : 'text-zinc-500'}`}>
                      {line}
                    </div>
                  ))}
                  <div ref={consoleEndRef} />
               </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
