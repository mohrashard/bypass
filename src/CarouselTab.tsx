import { useState, useEffect } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { invoke, convertFileSrc } from '@tauri-apps/api/core';

interface Element {
  id: string;
  type: 'text' | 'image';
  content: string;
  font?: string;
  size?: number;
  color?: string;
  bg_color?: string;
  bg_padding?: number;
  bg_radius?: number;
  stroke_color?: string;
  stroke_width?: number;
  shadow_color?: string;
  shadow_blur?: number;
  shadow_x?: number;
  shadow_y?: number;
  x: number;
  y: number;
}

interface SlideContext {
  id: string;
  elements: Element[];
}

interface CarouselConfig {
  slides: SlideContext[];
  theme_bg: string;
  ratio: string;
  show_swipe: boolean;
  show_dots: boolean;
  ui_color: string;
}

const FONTS = ["Mate", "Proxima Nova", "Cursive", "Gemunu Libre"];

export default function CarouselTab() {
  const [config, setConfig] = useState<CarouselConfig>({
    slides: [
      {
        id: 'slide-1',
        elements: [
          { id: 'el-1', type: 'text', content: 'How to get 10 customers with $0', font: 'Mate', size: 40, color: '#F8FAFC', x: 50, y: 50, bg_color: 'transparent', bg_padding: 15, bg_radius: 0, stroke_color: 'transparent', stroke_width: 0, shadow_color: 'transparent', shadow_blur: 0, shadow_x: 0, shadow_y: 0 }
        ]
      }
    ],
    theme_bg: '#0F172A',
    ratio: '1:1',
    show_swipe: true,
    show_dots: true,
    ui_color: '#3B82F6',
  });
  
  const [activeSlideIdx, setActiveSlideIdx] = useState(0);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRendering, setIsRendering] = useState(false);

  useEffect(() => {
    const fetchPreview = async () => {
      setIsLoading(true);
      try {
        // Send the full config with preview_idx so the backend knows the total slides
        // to render pagination dots correctly.
        const previewConfig = { ...config, preview_idx: activeSlideIdx };
        
        const out = await invoke<string>('run_carousel_engine', {
          action: 'preview',
          optionsJson: JSON.stringify(previewConfig),
        });
        
        const match = out.match(/\[PREVIEW_READY\] (.*)/);
        if (match && match[1]) {
          const pPath = match[1].trim();
          setPreviewUrl(convertFileSrc(pPath) + "?t=" + Date.now());
        } else {
          console.error("Failed to parse preview path:", out);
        }
      } catch (err) {
        console.error('Failed to fetch preview', err);
      } finally {
        setIsLoading(false);
      }
    };

    const timer = setTimeout(fetchPreview, 400);
    return () => clearTimeout(timer);
  }, [config, activeSlideIdx]);

  const handleAddSlide = () => {
    setConfig(prev => ({
      ...prev,
      slides: [...prev.slides, { id: `slide-${Date.now()}`, elements: [] }]
    }));
    setActiveSlideIdx(config.slides.length);
  };

  const handleRemoveSlide = (idx: number) => {
    if (config.slides.length <= 1) return;
    setConfig(prev => ({
      ...prev,
      slides: prev.slides.filter((_, i) => i !== idx)
    }));
    setActiveSlideIdx(0);
  };

  const handleAddTextElement = () => {
    const newSlides = config.slides.map((slide, i) => i === activeSlideIdx ? {
      ...slide,
      elements: [...slide.elements, {
        id: `el-${Date.now()}`, type: 'text' as const, content: 'New Text', font: 'Proxima Nova', size: 30, color: '#F8FAFC', x: 50, y: 50,
        bg_color: 'transparent', bg_padding: 15, bg_radius: 0,
        stroke_color: 'transparent', stroke_width: 0,
        shadow_color: 'transparent', shadow_blur: 0, shadow_x: 0, shadow_y: 0
      }]
    } : slide);
    setConfig({ ...config, slides: newSlides });
  };

  const handleAddImageElement = async () => {
    const selected = await open({
      multiple: false,
      filters: [{ name: 'Image', extensions: ['jpg', 'jpeg', 'png', 'webp'] }],
    }).catch(() => null);
    
    if (selected && typeof selected === 'string') {
      const newSlides = config.slides.map((slide, i) => i === activeSlideIdx ? {
        ...slide,
        elements: [...slide.elements, {
          id: `el-${Date.now()}`, type: 'image' as const, content: selected, x: 50, y: 50, size: 50
        }]
      } : slide);
      setConfig({ ...config, slides: newSlides });
    }
  };

  const handleUpdateElement = (elId: string, updates: Partial<Element>) => {
    const newSlides = config.slides.map((slide, i) => i === activeSlideIdx ? {
      ...slide,
      elements: slide.elements.map(e => e.id === elId ? { ...e, ...updates } : e)
    } : slide);
    setConfig({ ...config, slides: newSlides });
  };

  const handleRemoveElement = (elId: string) => {
    const newSlides = config.slides.map((slide, i) => i === activeSlideIdx ? {
      ...slide,
      elements: slide.elements.filter(e => e.id !== elId)
    } : slide);
    setConfig({ ...config, slides: newSlides });
  };

  const applyPreset = (elId: string, presetName: string) => {
    let updates: Partial<Element> = {};
    if (presetName === 'default') {
       updates = { color: '#F8FAFC', bg_color: 'transparent', stroke_color: 'transparent', stroke_width: 0, shadow_color: 'transparent', shadow_blur: 0, shadow_x: 0, shadow_y: 0 };
    } else if (presetName === 'minimalist') {
       updates = { color: '#F8FAFC', bg_color: 'transparent', stroke_color: 'transparent', stroke_width: 0, shadow_color: '#000000', shadow_blur: 10, shadow_x: 0, shadow_y: 4 };
    } else if (presetName === 'electric-glow') {
       updates = { color: '#00FFFF', bg_color: 'transparent', stroke_color: 'transparent', stroke_width: 0, shadow_color: '#00FFFF', shadow_blur: 20, shadow_x: 0, shadow_y: 0 };
    } else if (presetName === 'hormozi-bold') {
       updates = { color: '#FFDE59', bg_color: 'transparent', stroke_color: '#000000', stroke_width: 3, shadow_color: '#000000', shadow_blur: 0, shadow_x: 6, shadow_y: 6 };
    } else if (presetName === 'glassmorphism') {
       updates = { color: '#FFFFFF', bg_color: 'rgba(255,255,255,0.1)', bg_padding: 20, bg_radius: 12, stroke_color: 'transparent', stroke_width: 0, shadow_color: 'transparent' };
    } else if (presetName === 'black-box') {
       updates = { color: '#FFFFFF', bg_color: '#000000', bg_padding: 15, bg_radius: 8, stroke_color: 'transparent', stroke_width: 0, shadow_color: 'transparent' };
    }
    handleUpdateElement(elId, updates);
  };


  const handleRenderFinal = async () => {
    setIsRendering(true);
    try {
      const out = await invoke<string>('run_carousel_engine', {
        action: 'render',
        optionsJson: JSON.stringify(config),
      });

      const match = out.match(/\[RENDER_READY\] (.*)/);
      if (match && match[1]) {
        const pPath = match[1].trim();
        const a = document.createElement('a');
        a.href = convertFileSrc(pPath);
        a.download = `nexus_carousel_${Date.now()}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        alert(`Rendered successfully to:\n${pPath}`);
      } else {
        alert('Failed to render PDF. Console output:\n' + out);
      }
    } catch (err) {
      alert('Error rendering final carousel: ' + err);
    } finally {
      setIsRendering(false);
    }
  };

  const getAspectRatioClass = () => {
    if (config.ratio === '1:1') return 'aspect-square max-w-[500px]';
    if (config.ratio === '4:5') return 'aspect-[4/5] max-w-[400px]';
    if (config.ratio === '16:9') return 'aspect-video max-w-[600px]';
    return 'aspect-square max-w-[500px]';
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 w-full overflow-hidden bg-zinc-950 font-sans text-white">
      <div className="flex items-center gap-4 px-4 py-3 border-b border-zinc-800 bg-zinc-900 flex-shrink-0">
        <span className="text-xs font-bold tracking-[0.2em] text-blue-400 uppercase flex items-center gap-2">
          <span className="text-lg">🖼️</span> Nexus Carousels Engine
        </span>
        <div className="flex-1" />
        <button 
          onClick={handleRenderFinal}
          disabled={isRendering}
          className="text-xs px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white font-bold tracking-wide transition-colors flex items-center gap-2 shadow-[0_0_12px_rgba(37,99,235,0.3)] disabled:opacity-50"
        >
          {isRendering ? "Rendering PDF..." : "Render Final PDF"}
        </button>
      </div>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left Pane - Configuration */}
        <div className="w-[450px] border-r border-zinc-800 bg-zinc-950 flex flex-col flex-shrink-0">
          
          <div className="flex flex-col p-4 border-b border-zinc-800 gap-4">
            <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider">Global Settings</h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-zinc-400 block mb-1">Aspect Ratio</label>
                <select value={config.ratio} onChange={e => setConfig({...config, ratio: e.target.value})} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 text-sm outline-none">
                  <option value="1:1">1:1 (Square)</option>
                  <option value="4:5">4:5 (Portrait)</option>
                  <option value="16:9">16:9 (Landscape)</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-zinc-400 block mb-1">BG Color</label>
                <input type="color" value={config.theme_bg} onChange={e => setConfig({...config, theme_bg: e.target.value})} className="w-full h-8 cursor-pointer rounded border border-zinc-700 bg-zinc-900" />
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-3 bg-zinc-900 p-2 rounded border border-zinc-800">
               <label className="flex items-center gap-2 text-xs text-zinc-300">
                 <input type="checkbox" checked={config.show_swipe} onChange={e => setConfig({...config, show_swipe: e.target.checked})} className="accent-blue-500" />
                 Show Swipe Icon (›)
               </label>
               <label className="flex items-center gap-2 text-xs text-zinc-300">
                 <input type="checkbox" checked={config.show_dots} onChange={e => setConfig({...config, show_dots: e.target.checked})} className="accent-blue-500" />
                 Show Pagination Dots
               </label>
               <div className="col-span-2 flex items-center gap-2 mt-1">
                 <label className="text-xs text-zinc-400">Retention UI Color:</label>
                 <input type="color" value={config.ui_color} onChange={e => setConfig({...config, ui_color: e.target.value})} className="h-6 w-12 cursor-pointer rounded border border-zinc-700 bg-zinc-900" />
               </div>
            </div>
          </div>

          {/* Slide Navigation */}
          <div className="flex gap-2 p-3 bg-zinc-900 border-b border-zinc-800 overflow-x-auto items-center flex-shrink-0">
            {config.slides.map((slide, idx) => (
              <div 
                key={slide.id} 
                onClick={() => setActiveSlideIdx(idx)}
                className={`relative px-3 py-1.5 rounded text-xs font-bold cursor-pointer transition-colors border ${activeSlideIdx === idx ? 'bg-blue-600/20 text-blue-400 border-blue-500' : 'bg-zinc-800 text-zinc-400 border-zinc-700 hover:bg-zinc-700'}`}
              >
                Slide {idx + 1}
                {config.slides.length > 1 && activeSlideIdx === idx && (
                  <span onClick={(e) => { e.stopPropagation(); handleRemoveSlide(idx); }} className="absolute -top-1.5 -right-1.5 bg-red-500 text-white w-4 h-4 rounded-full flex items-center justify-center text-[10px] hover:bg-red-400 shadow-lg">✕</span>
                )}
              </div>
            ))}
            <button onClick={handleAddSlide} className="px-3 py-1.5 rounded text-xs font-bold bg-emerald-600/20 text-emerald-400 border border-emerald-500 hover:bg-emerald-600/30 transition-colors shrink-0">
              + New Slide
            </button>
          </div>

          {/* Active Slide Editor */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
             <div className="flex justify-between items-center">
               <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider">Slide Elements</h3>
               <div className="flex gap-2">
                 <button onClick={handleAddTextElement} className="text-[10px] bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 px-2 py-1 rounded text-zinc-300">+ Text</button>
                 <button onClick={handleAddImageElement} className="text-[10px] bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 px-2 py-1 rounded text-zinc-300">+ Image</button>
               </div>
             </div>

             {config.slides[activeSlideIdx].elements.length === 0 && (
               <div className="text-zinc-600 text-xs text-center py-4">No elements on this slide.</div>
             )}

             {config.slides[activeSlideIdx].elements.map((el, i) => (
               <div key={el.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 space-y-3 relative group">
                  <button onClick={() => handleRemoveElement(el.id)} className="absolute top-2 right-2 text-zinc-500 hover:text-red-400 text-xs hidden group-hover:block">✕</button>
                  <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">[{el.type}] Element {i + 1}</span>
                  
                  {el.type === 'text' ? (
                    <>
                      <textarea 
                        value={el.content}
                        onChange={e => handleUpdateElement(el.id, { content: e.target.value })}
                        className="w-full bg-black/50 border border-zinc-700 rounded p-2 text-sm text-white resize-none outline-none focus:border-blue-500"
                        rows={2}
                      />
                      <div className="grid grid-cols-2 gap-2 mt-2">
                        <select value={el.font} onChange={e => handleUpdateElement(el.id, { font: e.target.value })} className="w-full bg-zinc-950 border border-zinc-700 text-xs rounded p-1 outline-none">
                          {FONTS.map(f => <option key={f} value={f}>{f}</option>)}
                        </select>
                        <select value="custom" onChange={e => applyPreset(el.id, e.target.value)} className="w-full bg-zinc-950 border border-pink-700/50 text-xs rounded p-1 outline-none text-pink-300 font-bold">
                          <option value="custom">Load Preset...</option>
                          <option value="default">Default Clean</option>
                          <option value="minimalist">Minimalist Shadow</option>
                          <option value="electric-glow">Electric Glow</option>
                          <option value="hormozi-bold">🔥 Secret Sauce (Retainer)</option>
                          <option value="glassmorphism">Glass Block</option>
                          <option value="black-box">High-Contrast Box</option>
                        </select>
                        <div className="flex gap-2 col-span-2">
                          <input type="number" value={el.size} onChange={e => handleUpdateElement(el.id, { size: parseInt(e.target.value) })} className="w-16 bg-zinc-950 border border-zinc-700 text-xs rounded p-1 outline-none text-center" title="Font Size" />
                          <input type="color" value={el.color} onChange={e => handleUpdateElement(el.id, { color: e.target.value })} className="flex-1 h-6 cursor-pointer rounded border border-zinc-700 bg-zinc-900" title="Text Color" />
                        </div>
                      </div>

                      <div className="space-y-2 mt-3 p-3 bg-black/40 border border-zinc-800 rounded-lg">
                        <div className="flex justify-between items-center">
                          <span className="text-[9px] font-bold text-zinc-500 uppercase">Background Box</span>
                          <div className="flex gap-1">
                            <input type="color" value={el.bg_color === 'transparent' ? '#000000' : el.bg_color} onChange={e => handleUpdateElement(el.id, { bg_color: e.target.value })} className="h-5 w-6 cursor-pointer bg-zinc-900 border-none" title="BG Color" />
                            <button onClick={() => handleUpdateElement(el.id, { bg_color: 'transparent' })} className="text-[9px] px-1.5 bg-red-900/50 hover:bg-red-800 text-red-200 rounded">Clear</button>
                            <input type="number" value={el.bg_padding || 0} onChange={e => handleUpdateElement(el.id, { bg_padding: parseInt(e.target.value) })} className="w-10 bg-zinc-950 text-[10px] text-center border border-zinc-700 rounded" title="Padding (px)" />
                            <input type="number" value={el.bg_radius || 0} onChange={e => handleUpdateElement(el.id, { bg_radius: parseInt(e.target.value) })} className="w-10 bg-zinc-950 text-[10px] text-center border border-zinc-700 rounded" title="Border Radius (px)" />
                          </div>
                        </div>

                        <div className="flex justify-between items-center">
                          <span className="text-[9px] font-bold text-zinc-500 uppercase">Stroke / Outline</span>
                          <div className="flex gap-1">
                            <input type="color" value={el.stroke_color === 'transparent' ? '#000000' : el.stroke_color} onChange={e => handleUpdateElement(el.id, { stroke_color: e.target.value })} className="h-5 w-6 cursor-pointer bg-zinc-900 border-none" title="Stroke Color" />
                            <button onClick={() => handleUpdateElement(el.id, { stroke_color: 'transparent' })} className="text-[9px] px-1.5 bg-red-900/50 hover:bg-red-800 text-red-200 rounded">Clear</button>
                            <input type="number" value={el.stroke_width || 0} onChange={e => handleUpdateElement(el.id, { stroke_width: parseInt(e.target.value) })} className="w-10 bg-zinc-950 text-[10px] text-center border border-zinc-700 rounded" title="Stroke Width (px)" />
                          </div>
                        </div>

                        <div className="flex justify-between items-center">
                          <span className="text-[9px] font-bold text-zinc-500 uppercase">Drop Shadow</span>
                          <div className="flex gap-1">
                            <input type="color" value={el.shadow_color === 'transparent' ? '#000000' : el.shadow_color} onChange={e => handleUpdateElement(el.id, { shadow_color: e.target.value })} className="h-5 w-6 cursor-pointer bg-zinc-900 border-none" title="Shadow Color" />
                            <button onClick={() => handleUpdateElement(el.id, { shadow_color: 'transparent' })} className="text-[9px] px-1.5 bg-red-900/50 hover:bg-red-800 text-red-200 rounded">Clear</button>
                            <input type="number" value={el.shadow_blur || 0} onChange={e => handleUpdateElement(el.id, { shadow_blur: parseInt(e.target.value) })} className="w-8 bg-zinc-950 text-[10px] text-center border border-zinc-700 rounded" title="Blur" />
                            <input type="number" value={el.shadow_x || 0} onChange={e => handleUpdateElement(el.id, { shadow_x: parseInt(e.target.value) })} className="w-8 bg-zinc-950 text-[10px] text-center border border-zinc-700 rounded" title="Offset X" />
                            <input type="number" value={el.shadow_y || 0} onChange={e => handleUpdateElement(el.id, { shadow_y: parseInt(e.target.value) })} className="w-8 bg-zinc-950 text-[10px] text-center border border-zinc-700 rounded" title="Offset Y" />
                          </div>
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-4 mt-2">
                         <div className="flex items-center gap-2">
                           <span className="text-[10px] text-zinc-500">X:</span>
                           <input type="range" min="0" max="100" value={el.x} onChange={e => handleUpdateElement(el.id, { x: parseInt(e.target.value) })} className="flex-1 accent-emerald-500 h-1 bg-zinc-800 rounded-full appearance-none" />
                         </div>
                         <div className="flex items-center gap-2">
                           <span className="text-[10px] text-zinc-500">Y:</span>
                           <input type="range" min="0" max="100" value={el.y} onChange={e => handleUpdateElement(el.id, { y: parseInt(e.target.value) })} className="flex-1 accent-emerald-500 h-1 bg-zinc-800 rounded-full appearance-none" />
                         </div>
                      </div>
                    </>
                  ) : (
                    <div className="bg-black/50 border border-zinc-700 rounded p-2 text-[10px] text-zinc-400 truncate">
                      {el.content}
                      <div className="mt-2 text-emerald-400 font-bold">Full Frame Background</div>
                    </div>
                  )}
               </div>
             ))}
          </div>

        </div>

        {/* Right Pane - Live Preview */}
        <div className="flex-1 bg-black relative flex flex-col items-center justify-center p-8 border-l border-zinc-800">
           <div className="absolute top-4 left-4 flex items-center gap-2">
             <span className="text-[10px] font-bold text-zinc-500 tracking-wider uppercase">Live Preview (Slide {activeSlideIdx + 1})</span>
             {isLoading && <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>}
           </div>

           <div className={`w-full ${getAspectRatioClass()} rounded-xl overflow-hidden border border-zinc-800 bg-zinc-900 shadow-2xl relative flex items-center justify-center transition-all duration-300`}>
             {previewUrl ? (
               <img src={previewUrl} alt="Slide Preview" className="w-full h-full object-contain" />
             ) : (
               <div className="text-zinc-600 text-sm flex items-center gap-2">
                 <span className="animate-spin">⚙️</span> Rendering Preview...
               </div>
             )}
           </div>
           <div className="mt-6 text-zinc-500 text-xs italic">
             Use the X/Y sliders to position your elements anywhere on the slide.
           </div>
        </div>

      </div>
    </div>
  );
}
