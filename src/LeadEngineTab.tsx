import { useState, useEffect, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

interface Lead {
  title: string;
  url: string;
  upvotes: string | number;
  comments: string | number;
  subreddit: string;
  content?: string;
  aiScore?: number;
  aiContentIdea?: string;
  aiCommentIdea?: string;
  aiLeadQuality?: string;
  aiMatchedPillar?: string;
  aiEvidenceQuote?: string;
}

export default function LeadEngineTab() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [groqKey, setGroqKey] = useState(() => localStorage.getItem('groqKey') || '');
  const [subreddits, setSubreddits] = useState('SaaS, startups, Entrepreneur, smallbusiness, EntrepreneurRideAlong, indiehackers, nocode, webdev, SoftwareEngineering, AppIdeas, SideProject, marketing, digital_marketing, growmybusiness, agency, femalefounders, YouShouldKnow, microsaas, roastmystartup');
  const [searchQuery, setSearchQuery] = useState('video editing agency looking for founders struggling with content');

  const [engineState, setEngineState] = useState<'idle' | 'scraping' | 'analyzing'>('idle');
  const [analyzedCount, setAnalyzedCount] = useState(0);
  const [totalScraped, setTotalScraped] = useState(0);

  // New configuration states
  const [threadLimit, setThreadLimit] = useState(50);
  const [isComments, setIsComments] = useState(true);
  const [isContent, setIsContent] = useState(true);
  const [isMr2, setIsMr2] = useState(true);
  const [isPersonal, setIsPersonal] = useState(false);

  const [terminalLines, setTerminalLines] = useState<string[]>([]);
  const consoleEndRef = useRef<HTMLDivElement>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const copyForClaude = async (lead: Lead, index: number) => {
    const prompt = `I found this highly relevant Reddit thread. Please write a short-form video script based on this context and my proposed angle.

THREAD TITLE: ${lead.title}${lead.content ? `\n\nTHREAD CONTENT:\n${lead.content}` : ""}

MY PROPOSED ANGLE: ${lead.aiContentIdea}${lead.aiMatchedPillar ? `\n\nCONTENT PILLAR: ${lead.aiMatchedPillar}` : ""}

The script should be fast-paced, high-retention, and fit a 9:16 vertical format.`;
    
    try {
      await navigator.clipboard.writeText(prompt);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 2000);
    } catch (e) {
      console.error("Failed to copy", e);
    }
  };

  useEffect(() => {
    const unlistenPromise = listen<string>('engine-stdout', (event) => {
      const raw = event.payload ?? '';
      const incoming = raw.split('\n').filter((l) => l.trim().length > 0);
      if (incoming.length > 0) setTerminalLines((prev) => [...prev, ...incoming]);
    });
    return () => {
      unlistenPromise.then(unlisten => unlisten());
    };
  }, []);

  useEffect(() => {
    localStorage.setItem('groqKey', groqKey);
  }, [groqKey]);

  useEffect(() => {
    consoleEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [terminalLines]);

  const runLeadEngine = async () => {
    if (!groqKey || groqKey.trim() === '') {
      alert('Please enter a Groq API Key in Settings first!');
      return;
    }

    // Reset state
    setLeads([]);
    setTerminalLines([]);
    setAnalyzedCount(0);
    setTotalScraped(0);

    // Step 1: SCRAPE
    setEngineState('scraping');
    setTerminalLines(['🚀 Initializing Nexus Stealth Scraper...']);

    let scrapedLeads: Lead[] = [];
    try {
      await invoke('run_python_engine', {
        videoPath: 'dummy',
        processType: 'run_scraper',
        optionsJson: JSON.stringify({ 
          subreddits: subreddits, 
          query: searchQuery, 
          mode: isContent && !isComments ? 'content' : 'both' 
        })
      });

      const output = await invoke<string>('run_python_engine', {
        videoPath: 'dummy',
        processType: 'read_leads',
        optionsJson: '{}',
      });

      const match = output.match(/\[.*\]/s);
      if (match) {
        let allLeads = JSON.parse(match[0]);
        // Shuffle to get a mix of different subreddits if we hit the limit
        allLeads = allLeads.sort(() => Math.random() - 0.5);
        scrapedLeads = allLeads.slice(0, threadLimit);
        setTotalScraped(scrapedLeads.length);
      }
    } catch (e) {
      setTerminalLines(prev => [...prev, `[ERROR] Scraper Failed: ${e}`]);
      setEngineState('idle');
      return;
    }

    if (scrapedLeads.length === 0) {
      setTerminalLines(prev => [...prev, '[ERROR] No leads scraped. Check Subreddits.']);
      setEngineState('idle');
      return;
    }

    // Step 2: AI ANALYZE
    setEngineState('analyzing');
    setTerminalLines(prev => [...prev, `🧠 Engaging Llama 3 for deep analysis of ${scrapedLeads.length} threads...`]);

    const analyzedLeads: Lead[] = [];

    let systemPrompt = `[CONTEXT — WHO YOU'RE SCORING FOR]
Mr² Labs is a software/app development agency run by Mohamed Rashard, a self-taught developer and final-year Cardiff Metropolitan University student. The agency builds custom software, mobile apps, and MVPs for founders and small businesses, and also builds proprietary products. Mohamed also runs a separate personal creator brand focused on founder-relatable content — building in public, wearing every hat as a solo operator, and lessons from running an agency while studying.
${searchQuery && searchQuery.trim() !== '' ? `\n[ADDITIONAL CONTEXT FROM USER]\n${searchQuery}\n` : ''}
You are a world-class Lead Generation & Content Strategist for Mr² Labs and Mohamed Rashard.
You will be given a Reddit thread. Your job is to check if it GENUINELY qualifies as a high-intent client lead OR matches our content pillars based on the persona and context above.

[GENERAL RULES]
- Only output strict JSON, no markdown, no preamble.
- Do not infer intent that isn't clearly present in the text. If you have to guess, score it low.
- A thread about mindset, motivation, funding, marketing, or general business advice is NOT a lead unless it explicitly ties back to a build/dev pain point.
- Never force-fit a thread into a pillar to justify a high score. A low-relevance thread should score low, not be rationalized.

`;

    if (isComments) {
      systemPrompt += `[LEAD QUALIFICATION RULES]
Determine if the ORIGINAL POSTER is a genuine potential client — someone actively struggling with building, hiring for, or scoping a software/app/MVP project.
- Only flag high-intent signals: they need a developer, are frustrated with a current dev/agency, are unsure how to scope/price a build, or are stuck pre-launch on the technical side.
- Do NOT flag threads that merely mention startups, business, or tech in passing.

`;
    }

    if (isContent && isMr2) {
      systemPrompt += `[MR² LABS CONTENT PILLARS]
Check if it GENUINELY matches one of these 5 pillars — not just shares surface-level keywords:
1. Dev/Agency Trust Issues — burned by, ghosted by, or distrustful of a developer/agency
2. MVP & Build Cost Reality — discusses what an MVP/build actually costs, quotes, or scope creep
3. No-Code vs Custom Build Debates — weighs no-code tools against hiring a real developer
4. Post-Launch Struggles — built/launched something but struggling with users, growth, or product-market fit
5. Agency Red Flags / Vetting — describes red flags, vetting criteria, or bad experiences with an agency/freelancer

`;
    }

    if (isContent && isPersonal) {
      systemPrompt += `[MOHAMED RASHARD PERSONAL BRAND PILLARS]
Check if it GENUINELY matches one of these 5 pillars:
1. Solo Founder / Wearing Every Hat — doing everything themselves, burnout from solo-founding
2. Imposter Syndrome / Confidence — self-doubt about being capable/qualified as a founder
3. Time Management / Productivity Systems — how to find time to build, juggle tasks, or stay consistent
4. Student-Founder / Balancing School + Business — running a business while studying
5. Skill-Stacking / Self-Taught Journey — teaching themselves a skill (coding, design, etc.) without formal training

`;
    }

    systemPrompt += `OUTPUT FORMAT (Strict JSON):
{
  "score": integer (1-10),
  "is_lead": boolean,
  "match": boolean,
  "pillar": "exact pillar name from above or null",
  "evidence_quote": "short paraphrase (under 20 words) of the specific line that supports the score/match. If score is low or match is false, explain briefly why it doesn't fit",
  "content_idea": "one concrete video/post idea directly derived from this specific thread (or null)",
  "suggested_comment_angle": "1 sentence on how to genuinely help, based only on what they described (or null)"
}`;

    // Process in smaller batches or sequentially to avoid rate limits and show live updates
    for (let i = 0; i < scrapedLeads.length; i++) {
      const lead = scrapedLeads[i];
      try {
        const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${groqKey}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            model: 'llama-3.3-70b-versatile',
            messages: [
              { role: 'system', content: systemPrompt },
              { role: 'user', content: `Subreddit: r/${lead.subreddit}\nTitle: ${lead.title}\nContent: ${lead.content || 'No text body'}\nUpvotes: ${lead.upvotes}\nComments: ${lead.comments}` }
            ],
            response_format: { type: 'json_object' }
          })
        });

        const data = await response.json();
        
        if (data.error) {
          setTerminalLines(prev => [...prev, `[ERROR] Groq API Error: ${data.error.message.substring(0, 40)}... (Pausing 10s)`]);
          await new Promise(r => setTimeout(r, 10000));
          i--; // decrement i to retry this exact thread
          continue;
        }

        if (data.choices && data.choices[0]) {
          const rawContent = data.choices[0].message.content;
          const jsonMatch = rawContent.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            const aiContent = JSON.parse(jsonMatch[0]);
            const score = Number(aiContent.score) || 0;

            if (score >= 6) {
              setTerminalLines(prev => [...prev, `[SUCCESS] Score ${score}/10: ${lead.title.substring(0, 40)}...`]);
              const scoredLead = {
                ...lead,
                aiScore: score,
                aiContentIdea: aiContent.content_idea,
                aiCommentIdea: aiContent.suggested_comment_angle || aiContent.comment_idea,
                aiLeadQuality: aiContent.is_lead ? "High Intent Lead" : "Low Intent",
                aiMatchedPillar: aiContent.pillar || aiContent.matched_pillar,
                aiEvidenceQuote: aiContent.evidence_quote
              };
              analyzedLeads.push(scoredLead);
              // Update state so user sees them pop in live!
              setLeads([...analyzedLeads].sort((a, b) => (b.aiScore || 0) - (a.aiScore || 0)));
            } else {
              setTerminalLines(prev => [...prev, `[INFO] Discarded (Score ${score}): ${lead.title.substring(0, 30)}...`]);
            }
          } else {
             setTerminalLines(prev => [...prev, `[ERROR] AI returned invalid format for: ${lead.title.substring(0, 20)}...`]);
          }
        }
      } catch (e) {
        setTerminalLines(prev => [...prev, `[ERROR] Network Error on thread: ${lead.title.substring(0, 20)}...`]);
      }
      setAnalyzedCount(i + 1);
      // Wait 2 seconds to avoid Groq's 30 requests per minute free tier limit
      await new Promise(r => setTimeout(r, 2050));
    }

    setTerminalLines(prev => [...prev, `✅ Engine Complete. Found ${analyzedLeads.length} high-quality leads.`]);
    setEngineState('idle');
  };

  return (
    <div className="flex-1 p-6 md:p-10 flex flex-col overflow-y-auto w-full max-w-5xl mx-auto space-y-6">

      {/* HEADER SECTION */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b border-zinc-800 pb-6">
        <div>
          <h1 className="text-4xl font-black tracking-tight bg-gradient-to-r from-orange-400 to-rose-500 bg-clip-text text-transparent">
            Nexus Lead Engine
          </h1>
          <p className="text-zinc-400 text-sm mt-1 font-medium">Fully Automated Scraping & Llama 3 Intelligence</p>
        </div>
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="text-xs text-zinc-500 hover:text-orange-400 transition-colors flex items-center gap-1 font-mono"
        >
          {showSettings ? 'Hide Config' : '⚙️ Engine Config'}
        </button>
      </div>

      {/* CONFIGURATION */}
      {showSettings && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 grid grid-cols-1 md:grid-cols-2 gap-5 animate-in fade-in slide-in-from-top-2">
          
          <div className="col-span-1 md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4 bg-black/40 p-4 rounded-lg border border-zinc-800/50">
            <div>
              <label className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest block mb-3">AI Engine Goal</label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer group">
                  <input type="checkbox" checked={isComments} onChange={e => setIsComments(e.target.checked)} className="accent-orange-500 w-4 h-4 cursor-pointer" />
                  <span className="text-sm font-medium text-zinc-300 group-hover:text-white transition-colors">Find Leads (Comments)</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer group">
                  <input type="checkbox" checked={isContent} onChange={e => setIsContent(e.target.checked)} className="accent-rose-500 w-4 h-4 cursor-pointer" />
                  <span className="text-sm font-medium text-zinc-300 group-hover:text-white transition-colors">Ideate Content</span>
                </label>
              </div>
            </div>

            {isContent && (
              <div className="animate-in fade-in pl-0 md:pl-4 md:border-l border-zinc-800">
                <label className="text-[10px] text-rose-400 font-bold uppercase tracking-widest block mb-3">Content Pillars</label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer group">
                    <input type="checkbox" checked={isMr2} onChange={e => setIsMr2(e.target.checked)} className="accent-rose-500 w-4 h-4 cursor-pointer" />
                    <span className="text-sm font-medium text-zinc-300 group-hover:text-white transition-colors">Mr² Labs</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer group">
                    <input type="checkbox" checked={isPersonal} onChange={e => setIsPersonal(e.target.checked)} className="accent-rose-500 w-4 h-4 cursor-pointer" />
                    <span className="text-sm font-medium text-zinc-300 group-hover:text-white transition-colors">Personal Brand</span>
                  </label>
                </div>
              </div>
            )}
          </div>

          <div className="col-span-1 md:col-span-2">
            <label className="text-[10px] text-orange-400 font-bold uppercase tracking-widest block mb-1.5">Custom Niche / Context (Optional)</label>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="e.g. video editing agency looking for founders struggling with content"
              className="w-full bg-zinc-950 border border-zinc-700 text-white font-medium text-sm rounded-lg p-3 outline-none focus:border-orange-500 transition-all"
            />
          </div>
          
          <div className="col-span-1 md:col-span-2">
            <label className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest block mb-1.5">Subreddits</label>
            <textarea
              value={subreddits}
              onChange={(e) => setSubreddits(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 text-zinc-400 text-xs rounded-lg p-3 outline-none focus:border-zinc-600 min-h-[60px]"
            />
          </div>

          <div>
            <label className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest block mb-1.5">Thread Limit</label>
            <div className="flex gap-2 bg-zinc-950 p-1.5 rounded-lg border border-zinc-800">
               {[50, 100, 200, 500].map(limit => (
                 <button 
                   key={limit}
                   onClick={() => setThreadLimit(limit)}
                   className={`flex-1 text-xs py-1.5 rounded-md font-bold transition-all ${threadLimit === limit ? 'bg-orange-500/20 text-orange-400' : 'text-zinc-500 hover:text-zinc-300'}`}
                 >
                   {limit}
                 </button>
               ))}
            </div>
          </div>

          <div>
            <label className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest block mb-1.5">Groq API Key</label>
            <input
              type="password"
              value={groqKey}
              onChange={(e) => setGroqKey(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 text-zinc-500 text-sm rounded-lg p-2.5 outline-none focus:border-zinc-600"
            />
          </div>
        </div>
      )}

      {/* 1-CLICK MAGIC BUTTON */}
      <button
        onClick={runLeadEngine}
        disabled={engineState !== 'idle'}
        className={`w-full py-5 rounded-2xl font-black text-lg transition-all flex flex-col items-center justify-center gap-1
      ${engineState !== 'idle'
        ? 'bg-zinc-900 border border-zinc-800 text-zinc-500 cursor-not-allowed'
        : 'bg-gradient-to-r from-orange-600 to-rose-600 hover:from-orange-500 hover:to-rose-500 text-white shadow-[0_0_30px_rgba(234,88,12,0.3)] hover:shadow-[0_0_40px_rgba(234,88,12,0.5)] hover:scale-[1.01] border border-orange-500/50'
      }`}
      >
      {engineState === 'idle' && <span>🚀 AUTO-GENERATE LEADS</span>}
      {engineState === 'scraping' && (
        <span className="flex items-center gap-2 text-orange-400 animate-pulse">
          <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
          1. Scraping Subreddits...
        </span>
      )}
      {engineState === 'analyzing' && (
        <span className="flex items-center gap-2 text-rose-400">
          <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
          2. AI Scoring ({analyzedCount} / {totalScraped})
        </span>
      )}
    </button>

      {/* TERMINAL STATUS */}
  {
    terminalLines.length > 0 && (
      <div className="bg-black border border-zinc-800 rounded-xl overflow-hidden animate-in fade-in">
        <div className="px-4 py-1.5 border-b border-zinc-900 flex items-center gap-2 bg-zinc-950">
          <span className="text-[10px] text-zinc-500 font-mono tracking-widest">ENGINE LOGS</span>
        </div>
        <div className="p-3 max-h-24 overflow-y-auto">
          {terminalLines.map((line, i) => (
            <div key={i} className={`text-[11px] font-mono leading-relaxed ${line.startsWith('[ERROR]') ? 'text-red-400' : line.startsWith('[SUCCESS]') ? 'text-emerald-400' : 'text-zinc-400'}`}>
          {line}
        </div>
            ))}
        <div ref={consoleEndRef} />
      </div>
        </div >
      )
  }

  {/* RESULTS LIST */ }
  <div className="space-y-4 pt-2">
    {leads.length > 0 && <div className="text-sm font-bold text-zinc-400 px-1 border-b border-zinc-800 pb-2">Top AI-Verified Leads (Score 5+)</div>}

    {leads.map((lead, idx) => (
      <div key={idx} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 flex flex-col gap-4 relative overflow-hidden group shadow-lg hover:border-zinc-700 transition-colors">

        {/* Score Accent Banner */}
        <div className={`absolute top-0 left-0 w-1.5 h-full ${lead.aiScore! >= 8 ? 'bg-emerald-500 shadow-[0_0_20px_rgba(16,185,129,0.5)]' : 'bg-yellow-500'}`} />

        <div className="flex justify-between items-start gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] uppercase tracking-widest px-2 py-0.5 rounded bg-black text-zinc-400 font-bold border border-zinc-800">
                r/{lead.subreddit}
              </span>
              <span className="text-xs text-zinc-500 font-mono">
                ⬆️ {lead.upvotes} &nbsp; 💬 {lead.comments}
              </span>
            </div>
            <h3 className="text-lg font-bold text-zinc-100 leading-tight">
              {lead.title}
            </h3>
          </div>

          <div className="flex flex-col items-center gap-2">
            <div className={`shrink-0 w-12 h-12 rounded-full flex flex-col items-center justify-center border-2 bg-black/50 ${
              lead.aiScore! >= 8 ? 'border-emerald-500 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.2)]' : 'border-yellow-500 text-yellow-400'
            }`}>
              <span className="text-xl font-black leading-none">{lead.aiScore}</span>
            </div>
            <button onClick={() => window.open(lead.url, '_blank')} className="text-[10px] font-bold uppercase tracking-wider text-orange-500 hover:text-orange-400 whitespace-nowrap cursor-pointer">
              View Post ↗
            </button>
          </div>
        </div>

        {/* Thread Content Snippet */}
        {lead.content && lead.content.trim() !== "" && (
          <div className="mt-3 bg-zinc-950 rounded-lg p-3 border border-zinc-800/50">
            <p className="text-xs text-zinc-400 leading-relaxed font-mono whitespace-pre-wrap max-h-24 overflow-y-auto custom-scrollbar">
              {lead.content}
            </p>
          </div>
        )}

        {/* AI Insights - Clean grid */}
            <div className={`grid grid-cols-1 ${isContent && isComments ? 'lg:grid-cols-3' : 'lg:grid-cols-2'} gap-3 mt-1`}>
              
              <div className="bg-black/40 rounded-xl p-4 border border-zinc-800/50 flex flex-col gap-3">
                <span className="text-[10px] uppercase tracking-widest text-zinc-400 font-bold flex items-center gap-1.5 mb-1.5 border-b border-zinc-800 pb-2">
                  🧠 Evidence & Reasoning
                </span>
                <p className="text-xs text-zinc-300 leading-relaxed font-medium italic border-l-2 border-zinc-700 pl-3">
                  "{lead.aiEvidenceQuote}"
                </p>
                {isContent && lead.aiMatchedPillar && lead.aiMatchedPillar !== "None" && (
                  <div className="mt-auto pt-2">
                    <span className="inline-block text-[10px] uppercase tracking-widest px-2 py-1 rounded bg-rose-500/10 text-rose-400 font-bold border border-rose-500/20">
                      🎯 Pillar: {lead.aiMatchedPillar}
                    </span>
                  </div>
                )}
              </div>

              {isContent && (
                <div className="bg-black/40 rounded-xl p-4 border border-zinc-800/50">
                  <div className="flex justify-between items-center mb-1.5 border-b border-zinc-800 pb-2">
                    <span className="text-[10px] uppercase tracking-widest text-emerald-400 font-bold flex items-center gap-1.5">
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                      Content Idea
                    </span>
                    <button 
                      onClick={() => copyForClaude(lead, idx)}
                      className={`text-[9px] uppercase tracking-wider font-bold flex items-center gap-1 px-2 py-0.5 rounded transition-colors ${
                        copiedIndex === idx 
                          ? 'bg-emerald-500/20 text-emerald-400' 
                          : 'bg-zinc-800/50 text-zinc-400 hover:text-emerald-400 hover:bg-emerald-500/10'
                      }`}
                    >
                      {copiedIndex === idx ? (
                        <>
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                          Copied!
                        </>
                      ) : (
                        <>
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                          </svg>
                          Copy for Claude
                        </>
                      )}
                    </button>
                  </div>
                  <p className="text-xs text-zinc-300 leading-relaxed font-medium">{lead.aiContentIdea}</p>
                </div>
              )}
              
              {isComments && (
                <div className="bg-black/40 rounded-xl p-4 border border-zinc-800/50 flex flex-col gap-3">
                  <div>
                    <span className="text-[10px] uppercase tracking-widest text-sky-400 font-bold flex items-center gap-1.5 mb-1.5">
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
                      Comment Script
                    </span>
                    <p className="text-xs text-zinc-300 leading-relaxed font-medium">{lead.aiCommentIdea}</p>
                  </div>
                  <div className="mt-auto pt-3 border-t border-zinc-800/50">
                    <span className="text-[10px] uppercase tracking-widest text-orange-400 font-bold flex items-center gap-1.5 mb-1.5">
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                      Lead Quality
                    </span>
                    <p className="text-xs text-zinc-300 leading-relaxed font-medium">{lead.aiLeadQuality}</p>
                  </div>
                </div>
              )}
            </div>
          </div >
        ))
}
      </div >
    </div >
  );
}
