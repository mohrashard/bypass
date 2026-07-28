# NEXUS ENGINE — Animation Code Rules
# Paste this entire prompt before your animation request in any AI tool.
# (ChatGPT, Claude, Gemini, Grok, Copilot — all work)
# ─────────────────────────────────────────────────────────────────────────────

You are generating an HTML animation file for the **Nexus Engine** — a headless
Chromium renderer that captures animations frame-by-frame and encodes them to a
high-quality MP4. The engine controls the animation clock directly, so the output
must follow strict rules or the render will be broken or blank.

---

## ✅ REQUIRED RULES — Follow all of these exactly

### 1. Single self-contained HTML file
Output ONE complete `.html` file. All CSS and JS must be inline (inside `<style>`
and `<script>` tags). No external file references, no `src="./file.js"` paths.

### 2. External CDN libraries are ALLOWED
You may load libraries from CDN. Always use a pinned version URL. Recommended:
- GSAP:    `<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>`
- Tone.js: `<script src="https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.js"></script>`
- Anime.js:`<script src="https://cdnjs.cloudflare.com/ajax/libs/animejs/3.2.2/anime.min.js"></script>`
- Three.js:`<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>`
- Google Fonts via `<link>` in `<head>` — always allowed.
- p5.js, Lottie, Pixi.js — all fine via cdnjs or unpkg.

### 3. Body MUST use 100vw / 100vh — NEVER hardcode pixel dimensions
The engine sets the Chromium viewport to the chosen resolution (e.g. 1920×1080
for 16:9, or 1080×1920 for 9:16, or 1080×1080 for 1:1). The HTML must fill
the viewport exactly.

```css
/* ✅ CORRECT */
body {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  margin: 0;
  padding: 0;
}

/* ❌ WRONG — never do this */
body {
  width: 1920px;
  height: 1080px;
}
```

### 4. All sizes must be relative units — vw, vh, vmin, vmax, %, em, rem
Never use raw pixel values for layout, font sizes, or element sizes.
Pixels are only acceptable for border widths (e.g. `border: 1px solid`),
box-shadow blur, and border-radius on small decorative elements.

```css
/* ✅ CORRECT — scales to any aspect ratio */
.title    { font-size: 6vw; }
.card     { width: 60vw; height: 40vh; padding: 3vw; }
.logo     { width: 8vmin; height: 8vmin; }

/* ❌ WRONG */
.title    { font-size: 96px; }
.card     { width: 800px; }
```

### 5. Use requestAnimationFrame (rAF) for ALL animation timing
The Nexus Engine overrides `requestAnimationFrame`, `Date.now()`, and
`performance.now()` to scrub animations frame-by-frame without waiting real time.
Animations that rely on `setTimeout` or `setInterval` for their motion will
appear frozen. Use `rAF` loops or a library (GSAP, anime.js) which internally
uses `rAF`.

```js
// ✅ CORRECT — rAF-driven animation
let start = null;
function animate(ts) {
  if (!start) start = ts;
  const progress = (ts - start) / 1000; // seconds
  element.style.opacity = Math.min(progress / 0.5, 1);
  if (progress < 5) requestAnimationFrame(animate);
}
requestAnimationFrame(animate);

// ✅ CORRECT — GSAP (uses rAF internally)
gsap.fromTo('.card', { opacity: 0, y: 80 }, { opacity: 1, y: 0, duration: 0.6 });

// ❌ WRONG — setTimeout/setInterval won't animate
setTimeout(() => { el.style.opacity = 1; }, 500);
```

### 6. CSS @keyframes are fully supported
Pure CSS animations work perfectly. The engine fires rAF which drives the
browser's animation timeline.

```css
/* ✅ CORRECT */
.box {
  animation: slideIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
@keyframes slideIn {
  from { opacity: 0; transform: translateY(5vh); }
  to   { opacity: 1; transform: translateY(0); }
}
```

### 7. Canvas and WebGL are supported
Three.js, p5.js, raw Canvas 2D, and WebGL all work — as long as their render
loop uses `requestAnimationFrame`.

```js
// ✅ CORRECT — Three.js render loop
function animate() {
  requestAnimationFrame(animate);
  mesh.rotation.y += 0.01;
  renderer.render(scene, camera);
}
animate();
```

### 8. Canvas must be sized with JS, not CSS pixels
```js
// ✅ CORRECT
canvas.width  = window.innerWidth;   // equals the render width (e.g. 1920)
canvas.height = window.innerHeight;  // equals the render height (e.g. 1080)
```

### 9. No user interaction or input elements
The render is automated — no buttons, sliders, or click handlers needed.
The animation should start automatically on page load and run for its full
duration without any user action.

### 10. Transparent backgrounds: use `background: transparent` not `rgba(0,0,0,0)`
If you want a transparent background for compositing, set:
```css
html, body { background: transparent; }
```
And in Three.js: `renderer.setClearColor(0x000000, 0)` + `alpha: true`.

---

## 🎨 ASPECT RATIO GUIDE
The AI will tell you which aspect ratio they are targeting. Design accordingly:

| Ratio | Viewport at render   | Typical use         | Key layout tip                        |
|-------|----------------------|---------------------|---------------------------------------|
| 16:9  | 1920 × 1080 px       | YouTube, landscape  | Wide horizontal layouts, side-by-side |
| 9:16  | 1080 × 1920 px       | TikTok, Reels, Shorts | Tall vertical layouts, top-to-bottom flow |
| 1:1   | 1080 × 1080 px       | Instagram feed, X   | Centered, symmetrical, radial layouts |

Since you are using `vw`/`vh` as required, the same HTML will render correctly
at all three resolutions — design for the intended ratio but don't break others.

---

## 🎨 AESTHETIC PROFILES & COLOR RULES

You must design using one of the following premium aesthetic profiles. Choose the one that best fits the vibe of the animation request. NEVER use plain, unstyled HTML elements.

### AESTHETIC 1: High-Dopamine Dark Mode (The "Hacker/Tech" Vibe)
To lock a viewer's eyes onto motion graphics on mobile OLED screens. Bright neon elements glowing against a deep obsidian background force the viewer's pupils to dilate.
* **Background:** Deep Space Obsidian (`#06080E`) with subtle radial Deep Violet (`#7C3AED`) glows.
* **Text (70%):** Crisp Off-White (`#F8FAFC`)
* **Accent 1 (Focus):** Electric Cyan (`#00F0FF`)
* **Accent 2 (Success):** Terminal Green (`#00FF66`)
* **Accent 3 (Warning):** Flame Amber (`#FF4500`)
* **The "OLED Glow" Trick:** Add a subtle neon drop-shadow to active nodes or key text: `box-shadow: 0px 0px 20px rgba(0, 240, 255, 0.35);`

### AESTHETIC 2: Cinematic Light Mode & Chromatic Aberration (The "Blueprint" Vibe)
A clean, ultra-premium light mode featuring fine grids, deep metallic shadows, and RGB-split text. Perfect for "strong hook" or "secret recipe" style typography.
* **Background:** Clean White (`#FFFFFF`) or off-white (`#F8FAFC`).
* **The Grid (CRITICAL):** Add a very fine, light-gray grid to the background to make it look like a technical blueprint.
```css
  background-image: 
    linear-gradient(to right, rgba(0,0,0,0.05) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(0,0,0,0.05) 1px, transparent 1px);
  background-size: 4vw 4vw; /* Scale to viewport */
```
* **Text Colors:** Deep Charcoal/Black (`#111111`) for main text.
* **Chromatic Aberration (RGB Split) Effect:** Apply this CSS text-shadow to key hook text to create a digital/glitchy lens effect:
```css
  .chromatic-text {
    /* Red shifted left, Cyan/Blue shifted right */
    text-shadow: -3px 0px 0px rgba(255,0,0,0.8), 3px 0px 0px rgba(0,255,255,0.8);
  }
```
* **3D & Metallic Accents:** Use deep `drop-shadow` or CSS gradients (e.g., silver/chrome gradients) to make text or icons look metallic and 3-dimensional.

### AESTHETIC 3: Neon Glassmorphism (The "Pro vs Noob" Vibe)
For comparison cards, pricing tiers, or "upgrade" animations.
* **Background:** Rich gradients (e.g., dark gold/amber to black, or deep blue to black).
* **Glass Cards:** Create translucent cards with frosted glass effects.
```css
  .glass-card {
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(15px);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 3vw;
  }
```
* **Vibrant Neon Glow:** If a card is the "Pro" or "Active" state, give it an intense color (like Yellow/Gold `#FFD700` or Electric Cyan) and a massive, soft box-shadow glow (e.g., `box-shadow: 0 0 50px rgba(255, 215, 0, 0.3);`).

### The 70 / 20 / 10 Rule for Text & Animations

When coding motion graphics apply colors using this ratio:
* **70% Neutral Base:** (White in dark mode, Black in light mode)
* **20% Primary Accent:** (e.g., Electric Cyan, Chrome, or Bright Gold)
* **10% Secondary/Alert Accent:** (e.g., Terminal Green, Orange, or Red/Blue Chromatic)

*Rule for Text:* In a 6-word overlay, 4–5 words should be the neutral base, and 1–2 key impact words should be heavily styled (glowing, chromatic, or metallic).

---

## 🧠 VIEWER PSYCHOLOGY & VISUAL HOOKS

To biologically lock the viewer's attention, the visual pacing and content must hit their dopamine receptors perfectly.

### 1. ABSOLUTELY NO EMOJIS (Use SVG Icons) 🚨
* **Never use text-based emojis (`🔥`, `🚀`, `💡`, etc.).** They look incredibly cheap and instantly signal low-effort content, breaking the premium IDE/SaaS aesthetic.
* **ONLY use crisp, line-art SVG icons.** You may use inline SVGs (like Lucide, Feather, or Heroicons) or draw simple geometric vector shapes via code.
* Icons must be colored using the **High-Dopamine Accent Palette** (Electric Cyan, Terminal Green, or Flame Amber) and feature a subtle drop-shadow glow.

### 2. Extreme Minimalism (Do Not Overload with Text)
* Viewers will swipe away in 200ms if they see a wall of text.
* **Keep text brutally short.** Use 3–5 word punchy hooks per frame. 
* Replace paragraphs with **high-impact visual representations** (charts, progress bars, architecture diagrams, glowing data nodes flowing through wires). Let the graphics do the explaining, while the text only serves as a bold headline.

### 3. The Dopamine Spike (Motion & Easing)
* The human brain is biologically attracted to high-contrast, snappy motion.
* Ensure key metrics, success states, or critical nodes visually "snap" into place with a subtle overshoot (using spring physics or `power3.out`). Fast, intentional movements followed by a smooth deceleration hold attention far better than slow, continuous linear drifts.

---

## 🎬 AFTER EFFECTS LEVEL MOTION GRAPHICS (The Secret Sauce)

To achieve professional, "After Effects" tier motion graphics in CSS/JS, you must implement the following advanced techniques:

### 1. Complex Staggering & Text Splitting
Never animate an entire sentence as a single block. Break text down into words or characters and stagger them.
* **Write a custom JS splitter function:** Since premium plugins like `GSAP SplitText` are not available, you MUST write a quick JS function to wrap every letter or word in a `<span>` so they can be animated individually.
* **Use GSAP Stagger:** `gsap.from(".word", { y: "5vh", opacity: 0, stagger: 0.05, ease: "back.out(1.7)" })` creates that cascading AE feel.

### 2. Null Objects (Wrapper Divs)
Never try to apply multiple complex transforms (like spinning, scaling, and moving) on a single DOM element. It breaks.
* **Use Parent Wrappers (Nulls):** Create a `.wrapper` div to control the X/Y position, and rotate/scale the child `.element` inside it. This perfectly mimics AE's Null Object parenting.

### 3. Track Mattes (CSS clip-path)
To recreate AE's "Track Matte" or "Alpha Matte" reveals (where text emerges from an invisible line):
* Use `clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%);` on a parent container or use `overflow: hidden;`.
* Animate the child element moving up from `transform: translateY(100%)`. As it moves into the container, it visually "wipes" into existence.

### 4. Advanced AE Easing Curves
Linear or default eases look like a PowerPoint presentation.
* **For Snappy Pops:** Use `ease: "back.out(1.7)"` or `ease: "elastic.out(1, 0.75)"`
* **For Cinematic Slides:** Use `ease: "expo.inOut"` or `ease: "power4.inOut"`
* **For Camera Pushes:** Use `ease: "none"` (Linear) over a long duration (e.g., 5 seconds) to create a continuous, uninterrupted 2.5D camera zoom.

### 5. Faux Motion Blur, Glows & Chromatic Aberration
* **Motion Blur:** Simulate it during fast swipes by briefly scaling the element along the axis of movement (e.g., `scaleX: 1.5` during a horizontal swipe, returning to `1` when stopped).
* **Intense Glows:** Use layered `box-shadow` or `filter: drop-shadow()` to create a deep cinematic glow (e.g., `drop-shadow(0 0 10px #00F0FF) drop-shadow(0 0 30px #00F0FF)`).
* **Chromatic Aberration (RGB Split):** Instead of a standard shadow, use `-3px 0 0 red, 3px 0 0 cyan` on text or icons during fast impacts, or as a constant style for a "digital glitch" aesthetic.

### 6. Dynamic Ambient Backgrounds & Camera Drift
A perfectly static background or dead-still camera feels cheap and lifeless.
* **Cinematic Vignette:** Always place a full-screen overlay with `pointer-events: none` and a radial gradient that darkens the edges. This forces focus to the center.
* **Slow Camera Drift:** Even when an element is "resting", apply a very slow, continuous GSAP animation (e.g., scale from `1` to `1.05` over 10 seconds) so the screen is never perfectly still.
* **Ambient Glow Blobs:** Place 2-3 massive, heavily blurred divs (`filter: blur(15vh); opacity: 0.15; background: #7C3AED;`) in the far background and slowly drift their X/Y positions to create volumetric lighting.
* **Cyber Grids & Data Lines:** Use CSS `linear-gradient` or HTML5 `<canvas>` to draw a perspective grid or subtle falling particles that drift continuously.

---

## 📱 9:16 VERTICAL CANVAS RULES (TikTok, Shorts, Reels)

🚨 **CRITICAL DEAD ZONE WARNING** 🚨
**DO NOT place ANY text, code, or animations at the very top or very bottom of the screen!** Over 35% of the frame is hidden by the app UI.
* **Top 15% is covered** (Search bar, Following tabs)
* **Bottom 25% is covered** (Username, Captions, Audio track)
* **Right 15% is covered** (Like, Comment, Share buttons)
**ALL elements MUST sit in the middle of the screen!**

### 1. The TikTok Safe Zone Grid (Use `vw` / `vh`)

Since you must use relative units, here are the strict layout boundaries:
* **Top Clearance:** Start content at least `15vh` down from the top.
* **Bottom Clearance:** End content by `75vh` down (leave bottom `25vh` completely empty).
* **Right Clearance:** Leave the right `15vw` empty.
* **Left Clearance:** Leave `5vw` empty.
* **Max Width:** Keep content within `80vw`.
* **Optimal Alignment:** Center-Left (`padding-left: 5vw`). Never fully center long text because the right side will hit the buttons.

### 2. Typography & Scaling 🚨 (DO NOT MAKE TEXT OR ANIMATIONS TINY!) 🚨

AI generators often make text and visuals way too small. Mobile users need MASSIVE, readable elements.
* **Approved Fonts:** `Inter`, `Plus Jakarta Sans`, `Outfit` (Weight 800/900). For Code: `JetBrains Mono` (Bold 700).
* **MASSIVE Font Sizes:**
  * **Frame 1 Hook / Main Title:** `7vw` to `9vw` | Black (900) | 3–4 words max
  * **Main Body / Explainer Text:** `5vw` to `6vw` | ExtraBold (800)
  * **Code Snippets & Terminal Text:** `2.5vw` to `3vw` | Medium (600)
  * **Badges / Small Text:** `2vw` to `2.5vw` | Bold (700)
* **Line Heights:** Set `line-height: 1.1`. Do not use desktop standard `1.4`.
* **ANIMATION SIZE:** Your main visual (dashboard, code window, architecture diagram) must be BIG. It should take up at least `70vw` to `80vw` in width. Do NOT generate tiny diagrams in the middle of a massive black void.

### 3. Motion & Animation Placement Rules

* **The "Pop & Overshoot" Entry:** Fast, spring-based motion curves instead of slow linear fades.
  * **Duration:** `120ms` to `180ms` total.
  * `Frame 0ms`: Scale `80%` | Opacity `0`
  * `Frame 100ms`: Scale `105%` | Opacity `1` (Overshoot)
  * `Frame 150ms`: Scale `100%` | Opacity `1` (Settles)
  * **Easing:** `cubic-bezier(0.16, 1, 0.3, 1)`
* **Vertical Placement by Content Type:**
  * **Hooks & High-Impact Text (0:00 – 0:03):** Upper-Middle Third (`Y: 20vh` to `35vh` from top).
  * **Diagrams, Dashboards & Motion Cards (0:03 – End):** Dead Center (`Y: 40vh` to `60vh`). Max width `80vw`.
  * **Code Windows & Terminals:** 4:3 or 16:10 vertical aspect ratio. Apply `2vw` border-radius and a heavy backdrop blur or glow.

### 4. CSS / Layout Reference Container

Wrap your main video layer in a safe zone container:
```css
.tiktok-safe-canvas {
  width: 100vw;
  height: 100vh;
  box-sizing: border-box;
  
  /* Critical Safe Zone Padding */
  padding-top: 15vh;
  padding-bottom: 25vh;
  padding-left: 5vw;
  padding-right: 15vw;
  
  display: flex;
  flex-direction: column;
  justify-content: center; /* Keeps everything vertically safe */
  align-items: flex-start; /* Left-align for best visual balance */
}
```

---

## 🎵 AUDIO & SOUND EFFECTS (SFX)

The Nexus Engine features a concurrent two-pass audio extractor. It will automatically record any audio generated by your HTML and perfectly mux it into the final MP4.

### 1. How to Generate Sound
You must use **Tone.js** for all synthesized sound effects. It is highly recommended over raw Web Audio API for its simplicity and built-in synths (FM, Membrane, Noise).
- You can also use **Base64 Audio** via `<audio src="data:audio/mp3;base64,...">` if embedding actual sound files.
*(Do not link external audio files, as network latency will break synchronization).*

### 2. Synchronization (CRITICAL)
Do **NOT** use `setTimeout` or `setInterval` to trigger audio. Because the engine manipulates the `requestAnimationFrame` timeline for video rendering, `setTimeout` will fall completely out of sync.
**ALWAYS trigger audio via GSAP callbacks (`onStart`, `onComplete`, `call()`) or inside your `requestAnimationFrame` loop.**

```javascript
// ✅ CORRECT: Tone.js synth triggered by GSAP animation timeline
const synth = new Tone.MembraneSynth().toDestination();

gsap.to('.card', { 
  y: 0, 
  duration: 0.5, 
  onStart: () => {
    // Perfectly synced impact sound!
    synth.triggerAttackRelease("C2", "8n");
  }
});
```

### 3. Autoplay & Interaction
The engine runs with `--autoplay-policy=no-user-gesture-required`. You do NOT need a user click to start the `AudioContext` or play `<audio>` tags. Audio can trigger immediately on load or via your animation timeline.

---

## 🚀 PERFORMANCE TIPS (the engine renders faster when you follow these)

- Prefer CSS `transform` and `opacity` for animation — they are GPU composited.
  Avoid animating `width`, `height`, `top`, `left`, `margin` — they cause reflow.
- For particle systems or generative art, use `<canvas>` not DOM elements.
- Limit DOM nodes — hundreds of individually animated `<div>` elements are slow.
- Avoid `backdrop-filter: blur()` on large areas — very expensive per frame.
- GSAP is the fastest JS animation library for this engine. Use it when possible.

---

## 📋 MINIMAL VALID TEMPLATE

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;900&display=swap" rel="stylesheet">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.js"></script>
  <style>
    *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      width: 100vw; height: 100vh;
      overflow: hidden;
      background: #06080E;
      font-family: 'Inter', sans-serif;
      display: flex; align-items: center; justify-content: center;
    }
    .title {
      font-size: 6vw;
      font-weight: 900;
      color: #ffffff;
      opacity: 0;
    }
  </style>
</head>
<body>
  <h1 class="title">YOUR ANIMATION</h1>
  <script>
    gsap.to('.title', { opacity: 1, y: 0, duration: 0.8, ease: 'power3.out' });
  </script>
</body>
</html>
```

---

## ❌ COMMON MISTAKES THAT BREAK THE RENDER

| Mistake | Why it breaks | Fix |
|---|---|---|
| `body { width: 1920px }` | Doesn't scale to 9:16 or 1:1 | Use `100vw / 100vh` |
| `font-size: 96px` | Too big on 1080px wide, too small on 4K | Use `6vw` |
| `setTimeout(() => animate(), 500)` | Engine's clock override doesn't fire `setTimeout` | Use GSAP or rAF |
| External local files `src="./anim.js"` | Headless Chrome can't resolve relative paths | Inline everything or use CDN |
| `canvas.width = 1920` hardcoded | Wrong on 9:16 renders | Use `window.innerWidth` |
| `position: fixed` with px offsets | Doesn't adapt to viewport | Use `vh`/`vw` offsets |
| Waiting for click/keypress to start | Render is automated, no input happens | Auto-start on `DOMContentLoaded` or `window.onload` |

---

## MY ANIMATION REQUEST

[← PASTE YOUR ANIMATION DESCRIPTION BELOW THIS LINE →]
