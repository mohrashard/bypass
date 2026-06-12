import re

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Pattern to remove the Playwright stage_starting_hook
# Starts from # 16. HEADLESS CSS VISUAL HOOK ENGINE
# Ends before # 14. MAIN PIPELINE ORCHESTRATION (actually # ─────────────────────────────────────────────)
pattern = r"# 16\. HEADLESS CSS VISUAL HOOK ENGINE.*?def stage_starting_hook.*?(?=\n# ─────────────────────────────────────────────\n# 14\. MAIN PIPELINE ORCHESTRATION)"

# The new OpenCV V4 Engine code
new_engine_code = """# ─────────────────────────────────────────────────────────────────────────────
# 16. AI BODY-SCAN VISUAL HOOK ENGINE  — TikTok/AE Grade v4
#     "The subject arrives" — temporal reveal with staged energy build
# ─────────────────────────────────────────────────────────────────────────────
def stage_starting_hook(video_path: str, options: dict) -> str:
    import cv2
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    import os, subprocess

    hook_type = options.get("startingHook", "none")
    if hook_type == "none":
        return video_path

    print(f"[⚙️] TikTok/AE Hook Engine v4 — {hook_type}")
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    temp_vid   = os.path.join(base_dir, "_temp_hook.mp4")
    output_vid = os.path.splitext(video_path)[0] + "_hook.mp4"
    engine_dir = os.path.dirname(os.path.abspath(__file__))

    # ── MediaPipe ──────────────────────────────────────────────────────────
    model_path = os.path.join(engine_dir, "pretrained_models", "selfie_segmenter.tflite")
    if not os.path.exists(model_path):
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        import urllib.request
        urllib.request.urlretrieve(
            "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
            model_path)

    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    seg_options  = vision.ImageSegmenterOptions(
        base_options=base_options, output_confidence_masks=True)

    cap    = cv2.VideoCapture(video_path)
    fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    dur    = 1.5                          # 1.5 s gives room for real staging
    hook_frames = int(fps * dur)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_w  = cv2.VideoWriter(temp_vid, fourcc, fps, (width, height))

    # ══════════════════════════════════════════════════════════════════════
    #  EASING
    # ══════════════════════════════════════════════════════════════════════
    def ease_out_expo(t):
        return 1.0 - 2.0**(-10.0*t) if t > 0 else 0.0

    def ease_in_expo(t):
        return 2.0**(10.0*(t-1.0)) if t < 1 else 1.0

    def ease_out_elastic(t, amp=1.12, period=0.38):
        if t <= 0: return 0.0
        if t >= 1: return 1.0
        s = period/(2*np.pi)*np.arcsin(1.0/amp)
        return amp*(2.0**(-10.0*t))*np.sin((t-s)*(2*np.pi)/period)+1.0

    def ease_out_back(t, ov=1.70158):
        t -= 1
        return t*t*((ov+1)*t+ov)+1

    def ease_in_out_cubic(t):
        return 4*t**3 if t < 0.5 else 1-(-2*t+2)**3/2

    def smoothstep(t):
        return t*t*(3-2*t)

    # ══════════════════════════════════════════════════════════════════════
    #  CORE COMPOSITING
    # ══════════════════════════════════════════════════════════════════════
    def soft_mask_from_hard(m, radius=14):
        k = (radius*2+1)|1
        return cv2.GaussianBlur(m.astype(np.float32)/255.0, (k,k), radius/3.0)

    def comp(bg, fg, alpha):
        a  = alpha[:,:,np.newaxis]
        return np.clip(fg*a + bg*(1.0-a), 0, 255).astype(np.uint8)

    def add_layer(base, layer, alpha_scalar=1.0):
        return np.clip(base.astype(np.float32)
                       + layer.astype(np.float32)*alpha_scalar,
                       0, 255).astype(np.uint8)

    # ══════════════════════════════════════════════════════════════════════
    #  BACKGROUND FX
    # ══════════════════════════════════════════════════════════════════════
    def bg_dof_darken(bg, blur=20, exposure=0.45):
        k  = int(blur)*2+1
        b  = cv2.GaussianBlur(bg, (k|1, k|1), blur/3.0)
        lut = np.array([int(i*exposure) for i in range(256)], dtype=np.uint8)
        return cv2.LUT(b, lut)

    def bg_fog(bg, color_bgr, strength):
        fog = np.full_like(bg, color_bgr, dtype=np.float32)
        return np.clip(bg.astype(np.float32)*(1-strength)
                       + fog*strength, 0, 255).astype(np.uint8)

    # ══════════════════════════════════════════════════════════════════════
    #  REVEAL PRIMITIVES
    # ══════════════════════════════════════════════════════════════════════
    def scanline_wipe_mask(soft_mask, progress, line_glow_width=0.06):
        H, W = soft_mask.shape
        scan_y = int(progress * H)
        reveal = np.zeros((H, W), dtype=np.float32)
        if scan_y > 0: reveal[:scan_y, :] = 1.0
        reveal = reveal * soft_mask
        glow_h  = int(line_glow_width * H)
        glow_alpha = np.zeros((H, W), dtype=np.float32)
        y0, y1 = max(0, scan_y - glow_h), min(H, scan_y + glow_h)
        for y in range(y0, y1):
            alpha = (1.0 - abs(y - scan_y)/glow_h)**2
            glow_alpha[y, :] = alpha * soft_mask[y, :]
        return reveal, glow_alpha

    def energy_outline(hard_mask, color_bgr, intensity, blur_tight=8, blur_wide=35):
        dil_inner = cv2.dilate(hard_mask, np.ones((5,5), np.uint8),  iterations=2)
        dil_outer = cv2.dilate(hard_mask, np.ones((25,25), np.uint8), iterations=3)
        edge_inner = cv2.subtract(dil_inner, hard_mask)
        edge_outer = cv2.subtract(dil_outer, dil_inner)
        glow = np.zeros((*hard_mask.shape, 3), dtype=np.float32)
        for c_i, cv in enumerate(color_bgr):
            inner = cv2.GaussianBlur(edge_inner.astype(np.float32), (blur_tight|1,blur_tight|1), blur_tight/2) / 255.0
            outer = cv2.GaussianBlur(edge_outer.astype(np.float32), (blur_wide|1, blur_wide|1), blur_wide/2)  / 255.0
            glow[:,:,c_i] = (inner*1.4 + outer*0.6) * cv * intensity
        return np.clip(glow, 0, 255).astype(np.uint8)

    def ca_on_subject(sub, soft_mask, strength):
        if strength < 0.5: return sub
        s  = int(strength)
        b, g, r = cv2.split(sub)
        h, w = sub.shape[:2]
        r2 = cv2.warpAffine(r, np.float32([[1,0, s],[0,1, s]]), (w,h))
        b2 = cv2.warpAffine(b, np.float32([[1,0,-s],[0,1,-s]]), (w,h))
        ca = cv2.merge((b2, g, r2))
        a  = soft_mask[:,:,np.newaxis]
        return np.clip(ca*a + sub*(1-a), 0, 255).astype(np.uint8)

    def exposure_bloom(sub, soft_mask, ev, bloom_blur=30):
        boosted = np.clip(sub.astype(np.int32)+int(ev), 0, 255).astype(np.uint8)
        bloom   = cv2.GaussianBlur(boosted, (bloom_blur|1, bloom_blur|1), bloom_blur/3.0)
        blended = np.clip(sub.astype(np.float32) + bloom.astype(np.float32)*(ev/255.0)*0.5, 0, 255).astype(np.uint8)
        a = soft_mask[:,:,np.newaxis]
        return np.clip(blended*a + sub*(1-a), 0, 255).astype(np.uint8)

    def motion_blur(img, soft_mask, angle_deg, dist):
        if dist < 1: return img
        rad = np.deg2rad(angle_deg)
        dx, dy = int(np.cos(rad)*dist), int(np.sin(rad)*dist)
        ks = max(abs(dx),abs(dy),1)*2+1
        k  = np.zeros((ks,ks))
        c  = ks//2
        cv2.line(k,(c,c),(c+dx,c+dy),1,1)
        s = k.sum()
        if s > 0: k /= s
        blurred = cv2.filter2D(img, -1, k)
        a = soft_mask[:,:,np.newaxis]
        return np.clip(blurred*a + img*(1-a), 0, 255).astype(np.uint8)

    def zoom_blur(sub, soft_mask, cx, cy, zoom, steps=6):
        acc = sub.astype(np.float32)
        for i in range(1, steps+1):
            sc  = 1.0+zoom*(i/steps)
            M   = cv2.getRotationMatrix2D((cx,cy), 0, sc)
            acc += cv2.warpAffine(sub, M, (sub.shape[1],sub.shape[0])).astype(np.float32)
        r = np.clip(acc/(steps+1), 0, 255).astype(np.uint8)
        a = soft_mask[:,:,np.newaxis]
        return np.clip(r*a + sub*(1-a), 0, 255).astype(np.uint8)

    def film_lut(img, style):
        b,g,r = [ch.astype(np.float32) for ch in cv2.split(img)]
        if style == "teal_orange":
            r2 = np.clip(r*1.08+np.where(r<128,-6,20), 0,255)
            g2 = np.clip(g*0.96+np.where(g<128, 4,-5), 0,255)
            b2 = np.clip(b*1.06+np.where(b<128,14,-6), 0,255)
        elif style == "cold_chrome":
            r2 = np.clip(r*0.90+np.where(r<128,-12, 0), 0,255)
            g2 = np.clip(g*1.00+np.where(g<128, 10, 2), 0,255)
            b2 = np.clip(b*1.12+np.where(b<128, 20, 8), 0,255)
        elif style == "warm_bleach":
            r2 = np.clip(r*1.10+18, 0,255)
            g2 = np.clip(g*1.02+10, 0,255)
            b2 = np.clip(b*0.86+8,  0,255)
        else:
            r2,g2,b2 = r,g,b
        return cv2.merge([b2.astype(np.uint8),g2.astype(np.uint8),r2.astype(np.uint8)])

    class ParticleSystem:
        def __init__(self, outline_pixels, color_bgr, count=120):
            idxs = np.random.choice(len(outline_pixels), min(count, len(outline_pixels)), replace=False)
            pts  = outline_pixels[idxs]
            self.pos = pts.astype(np.float32)
            angles   = np.random.uniform(0, 2*np.pi, len(pts))
            speeds   = np.random.uniform(1, 6, len(pts))
            self.vel = np.stack([np.sin(angles)*speeds, np.cos(angles)*speeds], axis=1)
            self.life    = np.random.uniform(0.3, 1.0, len(pts))
            self.max_life= self.life.copy()
            self.color   = color_bgr
            self.sizes   = np.random.randint(1, 4, len(pts))

        def step(self, dt=1.0):
            self.pos += self.vel * dt
            self.vel *= 0.88
            self.vel[:,0] += 0.3 * dt
            self.life -= dt * 0.06

        def draw(self, canvas):
            for j in range(len(self.pos)):
                if self.life[j] <= 0: continue
                alpha = (self.life[j]/self.max_life[j])**0.5
                y,x   = int(self.pos[j,0]), int(self.pos[j,1])
                if 0<=y<canvas.shape[0] and 0<=x<canvas.shape[1]:
                    col = tuple(int(c*alpha) for c in self.color)
                    cv2.circle(canvas,(x,y),self.sizes[j]+2, tuple(c//3 for c in col),-1)
                    cv2.circle(canvas,(x,y),self.sizes[j],col,-1)

    try:
        with vision.ImageSegmenter.create_from_options(seg_options) as segmenter:
            ret, first_frame = cap.read()
            if not ret:
                cap.release(); out_w.release(); return video_path

            rgb    = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            res    = segmenter.segment(mp_img)

            if not res.confidence_masks:
                for _ in range(hook_frames): out_w.write(first_frame)
                cap.release(); out_w.release(); return video_path

            hard_mask = (np.squeeze(res.confidence_masks[0].numpy_view()) > 0.5).astype(np.uint8)*255
            soft_mask = soft_mask_from_hard(hard_mask, radius=14)

            ys,xs   = np.where(hard_mask>0)
            sub_top = int(ys.min()) if len(ys) else 0
            sub_bot = int(ys.max()) if len(ys) else height
            sub_cx  = int(xs.mean()) if len(xs) else width//2
            sub_cy  = int(ys.mean()) if len(ys) else height//2

            dil_outline     = cv2.dilate(hard_mask, np.ones((7,7),np.uint8), iterations=2)
            edge_px         = cv2.subtract(dil_outline, hard_mask)
            outline_coords  = np.column_stack(np.where(edge_px>0))

            bg_base    = bg_dof_darken(first_frame, blur=22, exposure=0.40)
            subject_lut = film_lut(first_frame, {
                "drop_in":"teal_orange","glitch":"cold_chrome","capcut_drop":"cold_chrome",
                "flash":"warm_bleach","flash_drop":"cold_chrome","impact":"teal_orange"
            }.get(hook_type,"teal_orange"))

            subject_clean = cv2.bitwise_and(subject_lut, subject_lut, mask=hard_mask)

            palettes = {
                "drop_in":    {"energy":(255,220,80),  "rim":(200,255,255), "particle":(255,200,60)},
                "capcut_drop":{"energy":(100,255,255), "rim":(200,255,255), "particle":(200,255,255)},
                "glitch":     {"energy":(255,50,200),  "rim":(255,80,255),  "particle":(200,255,255)},
                "flash":      {"energy":(255,255,255), "rim":(200,240,255), "particle":(255,240,200)},
                "flash_drop": {"energy":(255,240,0),   "rim":(255,220,0),   "particle":(200,255,255)},
                "impact":     {"energy":(30,100,255),  "rim":(50,150,255),  "particle":(100,180,255)},
            }
            pal = palettes.get(hook_type, palettes["flash"])

            particles = ParticleSystem(outline_coords, pal["particle"], count=150) if len(outline_coords)>0 else None
            base_noise = np.random.randint(0,40,(height+200,width+200,3),dtype=np.uint8)

            for i in range(hook_frames):
                t = i / max(hook_frames-1, 1)
                bg = bg_base.copy()

                particle_layer = np.zeros((height,width,3), dtype=np.uint8)
                if particles:
                    particles.step()
                    particles.draw(particle_layer)

                if hook_type == "capcut_drop":
                    # PHASE 1: FRAME 1 - The X-Ray Glitch (0% to 15%)
                    if t < 0.15:
                        noise_bg = cv2.add(bg, base_noise[:height, :width])
                        # X-Ray invert
                        inv = cv2.bitwise_not(subject_clean)
                        # Boost brightness/contrast
                        inv = cv2.convertScaleAbs(inv, alpha=1.5, beta=20)
                        xray_sub = cv2.bitwise_and(inv, inv, mask=hard_mask)
                        
                        # RGB Split simulation
                        ca_s = 30
                        b, g, r = cv2.split(xray_sub)
                        r2 = cv2.warpAffine(r, np.float32([[1,0,ca_s],[0,1,0]]), (width,height))
                        b2 = cv2.warpAffine(b, np.float32([[1,0,-ca_s],[0,1,0]]), (width,height))
                        split_sub = cv2.merge((b2, g, r2))
                        
                        # Apply to BG
                        final = comp(noise_bg, split_sub, soft_mask)
                        # Ambient flash
                        flash_layer = np.full_like(final, 255)
                        final = cv2.addWeighted(final, 0.7, flash_layer, 0.3, 0)
                        
                    # PHASE 2: FRAME 2 - The Vertical Echo Drop (15% to 50%)
                    elif t < 0.50:
                        drop_p = (t - 0.15) / 0.35
                        e = ease_out_expo(drop_p)
                        yOff = int((1 - e) * -800)
                        
                        # Main subject falling
                        M_sub = np.float32([[1,0,0],[0,1,yOff]])
                        sub_fall = cv2.warpAffine(subject_clean, M_sub, (width,height))
                        mroll = np.clip(np.roll(soft_mask, yOff, axis=0), 0, 1)
                        
                        # Echo Clones trailing behind
                        yOff1 = yOff - 100
                        M_c1 = np.float32([[1,0,0],[0,1,yOff1]])
                        c1_fall = cv2.warpAffine(subject_clean, M_c1, (width,height))
                        mroll1 = np.clip(np.roll(soft_mask, yOff1, axis=0), 0, 1)
                        c1_fall = cv2.GaussianBlur(c1_fall, (17,17), 8)
                        
                        yOff2 = yOff - 220
                        M_c2 = np.float32([[1,0,0],[0,1,yOff2]])
                        c2_fall = cv2.warpAffine(subject_clean, M_c2, (width,height))
                        mroll2 = np.clip(np.roll(soft_mask, yOff2, axis=0), 0, 1)
                        c2_fall = cv2.GaussianBlur(c2_fall, (31,31), 15)
                        
                        # Composite from back to front
                        final = bg.copy()
                        final = comp(final, c2_fall, mroll2 * 0.4)
                        final = comp(final, c1_fall, mroll1 * 0.7)
                        
                        # Sub fx brightness
                        sub_fx = cv2.convertScaleAbs(sub_fall, alpha=1.1, beta=0)
                        final = comp(final, sub_fx, mroll)
                        
                    # PHASE 3: FRAME 3 - The Hard Settle (50% to 100%)
                    else:
                        final = comp(bg, subject_clean, soft_mask)

                elif hook_type == "drop_in":
                    if t < 0.30:
                        ghost_alpha = smoothstep(t/0.30)*0.25
                        ghost = comp(bg, subject_clean, soft_mask*ghost_alpha)
                        out_e = energy_outline(hard_mask, pal["energy"], intensity=smoothstep(t/0.30)*1.2)
                        final = add_layer(ghost, out_e, 1.0)
                        final = add_layer(final, particle_layer, 0.8)
                    elif t < 0.70:
                        t2    = (t-0.30)/0.40
                        e     = ease_out_elastic(t2, amp=1.10, period=0.40)
                        offset= int((1.0-e)*(sub_top+height*0.35))
                        vel   = abs(e - ease_out_elastic(max(t2-0.04,0),1.10,0.40))
                        sub_fx= motion_blur(subject_clean, soft_mask, 90, int(vel*140))
                        M     = np.float32([[1,0,0],[0,1,-offset]])
                        sub_fx= cv2.warpAffine(sub_fx, M, (width,height))
                        mroll = np.clip(np.roll(soft_mask,-offset,axis=0),0,1)
                        rim_i = ease_out_expo(t2)*2.0
                        out_e = energy_outline(hard_mask, pal["energy"], intensity=(1.0-ease_out_expo(t2))*1.8)
                        final = comp(bg, sub_fx, mroll)
                        final = add_layer(final, out_e, 1.0)
                        final = add_layer(final, particle_layer, 0.9)
                    else:
                        t3    = (t-0.70)/0.30
                        out_e = energy_outline(hard_mask, pal["rim"], intensity=(1.0-ease_out_expo(t3))*1.0)
                        final = comp(bg, subject_clean, soft_mask)
                        final = add_layer(final, out_e, ease_out_expo(1.0-t3))
                        final = add_layer(final, particle_layer, 0.4*(1.0-t3))

                elif hook_type == "glitch":
                    is_hard = i in {1,2,5,7,10,13,17,20,24,28,32,35}
                    prog    = 1.0-ease_in_out_cubic(min(t/0.75,1.0))
                    if t < 0.25:
                        nx,ny = np.random.randint(0,200), np.random.randint(0,200)
                        noise_bg = cv2.add(bg, base_noise[ny:ny+height,nx:nx+width])
                        n_tears = np.random.randint(1,4)
                        for _ in range(n_tears):
                            ty = np.random.randint(0, height)
                            th = np.random.randint(2, int(height*0.06))
                            tx_shift = np.random.randint(20,120)*np.random.choice([-1,1])
                            band = noise_bg[ty:ty+th, :]
                            noise_bg[ty:ty+th,:] = cv2.warpAffine(band, np.float32([[1,0,tx_shift],[0,1,0]]), (width, band.shape[0]))
                        ghost_a = t/0.25 * 0.15
                        final   = comp(noise_bg, subject_clean, soft_mask*ghost_a)
                        final   = add_layer(final, particle_layer, 0.6)
                    elif t < 0.75:
                        t2 = (t-0.25)/0.50
                        ca_s   = prog*65
                        sub_fx = ca_on_subject(subject_clean, soft_mask, ca_s)
                        sx = int(prog*(80 if is_hard else 10)*np.random.choice([-1,1]))
                        sy = int(prog*(20 if is_hard else 3) *np.random.choice([-1,1]))
                        b_c,g_c,r_c = cv2.split(sub_fx)
                        h_,w_ = sub_fx.shape[:2]
                        sub_fx = cv2.merge((
                            cv2.warpAffine(b_c,np.float32([[1,0,-sx],[0,1,-sy]]),(w_,h_)),
                            g_c,
                            cv2.warpAffine(r_c,np.float32([[1,0,sx],[0,1,sy]]),(w_,h_))
                        ))
                        sub_fx = cv2.bitwise_and(sub_fx,sub_fx,mask=hard_mask)
                        wipe_p, wipe_glow = scanline_wipe_mask(soft_mask, t2)
                        sub_fx_rev = comp(bg, sub_fx, wipe_p)
                        scan_color = np.zeros((height,width,3),dtype=np.float32)
                        for c_i,cv_ in enumerate(pal["energy"]):
                            scan_color[:,:,c_i] = wipe_glow * cv_
                        sub_fx_rev = add_layer(sub_fx_rev, scan_color.astype(np.uint8), 1.2)
                        if is_hard and np.random.random()>0.5:
                            inv = cv2.bitwise_not(sub_fx)
                            sub_fx = cv2.bitwise_and(inv,inv,mask=hard_mask)
                            sub_fx_rev = comp(bg, sub_fx, wipe_p)
                        out_e = energy_outline(hard_mask, pal["energy"], intensity=prog*1.5)
                        final = add_layer(sub_fx_rev, out_e, 1.0)
                        nx,ny = np.random.randint(0,200),np.random.randint(0,200)
                        bg_n  = cv2.add(bg, base_noise[ny:ny+height,nx:nx+width])
                        final = np.where((wipe_p[:,:,np.newaxis]<0.1), bg_n, final).astype(np.uint8)
                        final = add_layer(final, particle_layer, 0.7)
                    else:
                        t3    = (t-0.75)/0.25
                        out_e = energy_outline(hard_mask, pal["energy"], intensity=(1.0-ease_out_expo(t3))*0.8)
                        final = comp(bg, subject_clean, soft_mask)
                        final = add_layer(final, out_e, 1.0-t3)

                elif hook_type == "flash":
                    if t < 0.08:
                        alpha_f = 1.0-ease_out_expo(t/0.08)
                        white   = np.ones_like(first_frame)*255
                        final   = cv2.addWeighted(white,alpha_f,bg,1-alpha_f,0)
                    elif t < 0.50:
                        t2    = (t-0.08)/0.42
                        decay = ease_out_expo(t2)
                        ev    = (1.0-decay)*240
                        ca_s  = (1.0-decay)*18
                        sub_fx = exposure_bloom(subject_clean, soft_mask, ev, bloom_blur=40)
                        sub_fx = ca_on_subject(sub_fx, soft_mask, ca_s)
                        opacity= smoothstep(t2)*1.0
                        out_e  = energy_outline(hard_mask, pal["energy"], intensity=(1.0-decay)*2.0)
                        final  = comp(bg, sub_fx, soft_mask*opacity)
                        final  = add_layer(final, out_e, 1.0)
                        final  = add_layer(final, particle_layer, (1.0-decay)*0.8)
                    else:
                        t3    = (t-0.50)/0.50
                        out_e = energy_outline(hard_mask, pal["rim"], intensity=(1.0-ease_out_expo(t3))*0.8)
                        final = comp(bg, subject_clean, soft_mask)
                        final = add_layer(final, out_e, 1.0-t3)

                elif hook_type == "flash_drop":
                    if t < 0.10:
                        alpha_f = 1.0-ease_out_expo(t/0.10)
                        white   = np.ones_like(first_frame)*255
                        final   = cv2.addWeighted(white,alpha_f,bg,1-alpha_f,0)
                    elif t < 0.65:
                        t2    = (t-0.10)/0.55
                        e     = ease_out_back(t2, ov=1.5)
                        off   = int((1.0-e)*height*0.22)
                        M_d   = np.float32([[1,0,0],[0,1,-off]])
                        decay = ease_out_expo(t2)
                        ev    = (1.0-decay)*200
                        ca_s  = (1.0-decay)*30
                        sub_fx = exposure_bloom(subject_clean, soft_mask, ev, bloom_blur=35)
                        sub_fx = ca_on_subject(sub_fx, soft_mask, ca_s)
                        vel    = abs(e-ease_out_back(max(t2-0.04,0),1.5))
                        sub_fx = motion_blur(sub_fx, soft_mask, 90, int(vel*100))
                        sub_fx = cv2.warpAffine(sub_fx, M_d, (width,height))
                        mroll  = np.clip(np.roll(soft_mask,-off,axis=0),0,1)
                        out_e  = energy_outline(hard_mask, pal["energy"], intensity=(1.0-decay)*2.2)
                        final  = comp(bg, sub_fx, mroll)
                        final  = add_layer(final, out_e, 1.0)
                        final  = add_layer(final, particle_layer, (1.0-decay))
                    else:
                        t3    = (t-0.65)/0.35
                        out_e = energy_outline(hard_mask, pal["rim"], intensity=(1.0-ease_out_expo(t3))*1.0)
                        final = comp(bg, subject_clean, soft_mask)
                        final = add_layer(final, out_e, 1.0-ease_out_expo(t3))
                        final = add_layer(final, particle_layer, 0.3*(1.0-t3))

                elif hook_type == "impact":
                    if t < 0.20:
                        zoom_s = (1.0-t/0.20)*0.15
                        zoomed_bg = np.zeros_like(bg)
                        acc    = bg.astype(np.float32)
                        steps  = 6
                        for s_i in range(1,steps+1):
                            sc = 1.0+zoom_s*(s_i/steps)
                            M  = cv2.getRotationMatrix2D((width//2,height//2),0,sc)
                            acc+=cv2.warpAffine(bg,M,(width,height)).astype(np.float32)
                        zoomed_bg = np.clip(acc/(steps+1),0,255).astype(np.uint8)
                        out_e = energy_outline(hard_mask, pal["energy"], intensity=t/0.20*0.6)
                        final = add_layer(zoomed_bg, out_e, 1.0)
                        final = add_layer(final, particle_layer, t/0.20*0.6)
                    elif t < 0.60:
                        t2    = (t-0.20)/0.40
                        decay = ease_out_expo(t2)
                        shake_a = (1.0-decay)*65
                        shx   = int(shake_a*np.random.uniform(-1,1))
                        shy   = int(shake_a*np.random.uniform(-1,1))
                        scale = 1.0+(1.0-decay)*0.28
                        M_hit = cv2.getRotationMatrix2D((sub_cx,sub_cy),0,scale)
                        M_hit[0,2]+=shx; M_hit[1,2]+=shy
                        sub_fx = cv2.warpAffine(subject_clean,M_hit,(width,height))
                        if t2<0.30:
                            sub_fx = zoom_blur(sub_fx,soft_mask, sub_cx,sub_cy,(1.0-t2/0.30)*0.12,steps=6)
                            sub_fx = ca_on_subject(sub_fx,soft_mask,(1.0-t2/0.30)*25)
                        out_e  = energy_outline(hard_mask, pal["energy"], intensity=(1.0-decay)*2.5)
                        final  = comp(bg, sub_fx, soft_mask)
                        final  = add_layer(final, out_e, 1.0)
                        final  = add_layer(final, particle_layer, (1.0-decay))
                    else:
                        t3    = (t-0.60)/0.40
                        out_e = energy_outline(hard_mask, pal["rim"], intensity=(1.0-ease_out_expo(t3))*1.0)
                        final = comp(bg, subject_clean, soft_mask)
                        final = add_layer(final, out_e, 1.0-ease_out_expo(t3))

                else:
                    final = first_frame.copy()

                out_w.write(np.clip(final,0,255).astype(np.uint8))

    except Exception:
        import traceback
        print(f"[❌] {traceback.format_exc()}")

    cap.release()
    out_w.release()

    if not os.path.exists(temp_vid) or os.path.getsize(temp_vid)<1000:
        print("[⚠️] Hook failed — skipping.")
        if os.path.exists(temp_vid): os.remove(temp_vid)
        return video_path

    # ── FFmpeg compose ─────────────────────────────────────────────────────
    sfx_map   = {"flash":"flash_sfx.MP3","flash_drop":"flash_sfx.MP3",
                 "drop_in":"impact_sfx.MP3","glitch":"glitch_sfx.MP3",
                 "impact":"impact_sfx.MP3","capcut_drop":"impact_sfx.MP3"}
    sfx_audio = os.path.join(engine_dir,"assets",sfx_map.get(hook_type,""))
    has_sfx   = os.path.exists(sfx_audio)

    fc = (f"[0:v]tpad=start_duration={dur}:start_mode=clone[v_main];"
          f"[v_main][1:v]overlay=eof_action=pass[v_out];"
          f"[0:a]adelay={int(dur*1000)}:all=1[main_a]")
    if has_sfx:
        fc  +=f";[2:a]volume=1.5[sfx];[main_a][sfx]amix=inputs=2:duration=longest:dropout_transition=2:normalize=0[a_final]"
        amap ="[a_final]"
    else:
        amap ="[main_a]"

    shared = ["-filter_complex",fc,"-map","[v_out]","-map",amap,
              "-c:a","aac","-b:a","192k",output_vid,"-y"]
    base_cmd = ["ffmpeg","-i",video_path,"-i",temp_vid]
    if has_sfx: base_cmd+=["-i",sfx_audio]

    try:
        subprocess.run(base_cmd+["-c:v","h264_nvenc","-preset","p6","-cq","18"]+shared,
                       check=True,capture_output=True)
    except subprocess.CalledProcessError:
        print("[⚠️] NVENC → CPU fallback")
        subprocess.run(base_cmd+["-c:v","libx264","-preset","fast","-crf","17"]+shared,
                       check=True,capture_output=True)

    if os.path.exists(temp_vid): os.remove(temp_vid)
    print(f"[✅] TikTok/AE Hook → {output_vid}")
    return output_vid
"""

new_content = re.sub(pattern, new_engine_code, content, flags=re.DOTALL)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("SUCCESS")
