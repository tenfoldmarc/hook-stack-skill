#!/usr/bin/env python3
"""Edit every ad in <project>/plan.json: hook + body, dead air cut, 1080x1920, burned-in captions, on-screen hook text,
loudness levelled. Run with the skill's own Python (<skill>/.venv).

  build_ads.py <project_dir> [--only H01,H02] [--no-verify] [--keep-going]

Needs <project_dir>/work/clips.json (scan.py transcribe) and <project_dir>/plan.json (format: references/plan.md).
Writes:
  ads/<id>.mp4             the finished ad (H.264 + AAC, 30 fps, faststart: ready for Meta)
  ads/<id>-thumb.jpg       its cover (first frame of the hook with the hook text), used as the ad thumbnail
  ads/manifest.json        what launch reads: id, file, thumb, duration, hook text
  work/qa_sheet.jpg        one frame of every hook + body frames with captions, to look at before showing anyone
Each segment (a hook, the body) is cut and normalised once and reused, so 12 ads with one body cost one body render.
Verify (on by default) re-transcribes the start of every finished ad and flags a clipped or missing word at the
start of the hook or at the hook-to-body join.
"""
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

W, H, FPS, SR = 1080, 1920, 30, 48000
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(SKILL, 'fonts', 'InterTight-Variable.ttf')     # one variable font, weight set per use


def font(size, weight):
    from PIL import ImageFont
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name(weight)
    except (OSError, ValueError):
        f.set_variation_by_axes([{'Black': 900, 'ExtraBold': 800, 'Bold': 700}.get(weight, 700)])
    return f

DEFAULTS = {
    'max_gap': 0.35,          # pauses longer than this inside a segment get cut
    'silence_db': -35,        # what counts as quiet (raise to -30 in a noisy room, lower to -40 in a dead-quiet one)
    'pad_after': 0.10,        # kept after the last word before a cut
    'pad_before': 0.07,       # kept before the next word after a cut
    'captions': True,
    'caption_case': 'upper',  # upper | as_spoken
    'caption_size': 82,
    'caption_y': 1130,        # centre line of the captions (Meta keeps the bottom ~35% for its own UI)
    'caption_max_words': 3,
    'caption_max_chars': 18,
    'caption_color': '#FFFFFF',
    'caption_accent': '#FFD60A',  # the word being said
    'hook_text_y': 300,       # top of the on-screen hook text (Meta keeps the top ~14% clear)
    'hook_text_size': 64,
    'hook_text_seconds': None,  # None = for as long as the hook is spoken, at least 3 s
    'fixes': {},              # caption word fixes, e.g. {"cloud": "Claude"}
}


def run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        tail = '\n'.join(r.stderr.strip().splitlines()[-12:])
        raise SystemExit(f'ffmpeg failed while {what}:\n{tail}')
    return r


def q(t):
    """snap a time to the frame grid"""
    return round(round(t * FPS) / FPS, 4)


# ------------------------------------------------------------------ segments
def silences(path, start, end, db, min_d):
    """quiet stretches in [start, end] of a clip, measured on the audio itself (the transcript's word times run
    into the pauses, so they cannot be trusted to find dead air)"""
    r = subprocess.run(['ffmpeg', '-v', 'info', '-hide_banner', '-nostats', '-ss', f'{start:.3f}', '-t', f'{end - start:.3f}',
                        '-i', path, '-vn', '-af', f'silencedetect=n={db}dB:d={min_d}', '-f', 'null', '-'],
                       capture_output=True, text=True)
    out, cur = [], None
    for line in r.stderr.splitlines():
        m = re.search(r'silence_start: (-?[\d.]+)', line)
        if m:
            cur = max(0.0, float(m.group(1)))
        m = re.search(r'silence_end: ([\d.]+)', line)
        if m and cur is not None:
            out.append((start + cur, start + float(m.group(1))))
            cur = None
    if cur is not None:
        out.append((start + cur, end))
    return out


def seg_pieces(clip, seg, o):
    start, end = float(seg['start']), float(seg['end'])
    end = min(end, clip['duration'])
    words = [dict(w) for w in clip['words'] if w['s'] < end - 0.05 and w['e'] > start + 0.05]
    pieces = []
    if seg.get('tighten', True):
        quiet = silences(clip['path'], start, end, o['silence_db'], min(o['max_gap'], 0.25))
        cur = start
        for s0, s1 in quiet:
            if s0 <= start + 0.02:                       # dead air before the first word
                cur = max(cur, s1 - o['pad_before'])
            elif s1 >= end - 0.02:                       # dead air after the last word
                end = min(end, s0 + o['pad_after'])
            elif s1 - s0 > o['max_gap']:
                pieces.append([cur, s0 + o['pad_after']])
                cur = s1 - o['pad_before']
        pieces.append([cur, end])
    else:
        pieces = [[start, end]]
    for c in seg.get('cut', []):              # extra cuts the plan asks for: [from, to] in clip time
        out = []
        for s, e in pieces:
            if c[1] <= s or c[0] >= e:
                out.append([s, e])
                continue
            if c[0] > s:
                out.append([s, c[0]])
            if c[1] < e:
                out.append([c[1], e])
        pieces = out
    pieces = [p for p in pieces if p[1] - p[0] >= 0.1]
    # frame-exact lengths, so audio and picture stay locked across every join
    out, t = [], 0.0
    for s, e in pieces:
        n = max(3, round((e - s) * FPS))
        out.append({'s': s, 'n': n, 'off': t})
        t += n / FPS
    # source words on the new timeline (only used to check the cut: silence holds no words, so a word whose
    # transcript time lands in a removed pause belongs to the next kept piece)
    mapped = []
    for w in words:
        p = next((p for p in out if w['s'] < p['s'] + p['n'] / FPS), None)
        if p is None:
            continue
        ns = p['off'] + max(0.0, w['s'] - p['s'])
        mapped.append({'w': w['w'], 's': round(ns, 3), 'e': round(ns + max(0.05, w['e'] - w['s']), 3)})
    return out, mapped, t


def seg_key(clip, seg, o):
    raw = json.dumps([clip['path'], clip.get('mtime'), seg['start'], seg['end'], seg.get('tighten', True),
                      seg.get('cut', []), o['max_gap'], o['pad_after'], o['pad_before'], o['silence_db'], 4], sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def video_chain(clip):
    chain = []
    if clip.get('hdr'):
        # no tone-mapping filter in many ffmpeg builds: convert the colours and keep the HLG curve as SDR gamma
        chain.append('colorspace=all=bt709:iprimaries=bt2020:ispace=bt2020ncl:itrc=bt709:irange=tv:format=yuv420p')
    chain += [f'scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos', f'crop={W}:{H}', 'setsar=1',
              'format=yuv420p']
    return ','.join(chain)


def render_segment(clip, pieces, out_path):
    cmd = ['ffmpeg', '-y', '-v', 'error']
    fl = []
    for i, p in enumerate(pieces):
        dur = p['n'] / FPS
        cmd += ['-ss', f'{p["s"]:.4f}', '-t', f'{dur + 0.25:.4f}', '-i', clip['path']]
        ns = round(dur * SR)
        fl.append(f'[{i}:v]setpts=PTS-STARTPTS,fps={FPS},{video_chain(clip)},tpad=stop_mode=clone:stop_duration=0.3,'
                  f'trim=end_frame={p["n"]},setpts=PTS-STARTPTS[v{i}]')
        fl.append(f'[{i}:a]asetpts=PTS-STARTPTS,aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo,apad,'
                  f'atrim=end_sample={ns},asetpts=PTS-STARTPTS,afade=t=in:d=0.012,'
                  f'afade=t=out:st={max(dur - 0.012, 0):.4f}:d=0.012[a{i}]')
    ins = ''.join(f'[v{i}][a{i}]' for i in range(len(pieces)))
    fl.append(f'{ins}concat=n={len(pieces)}:v=1:a=1[v][a]')
    cmd += ['-filter_complex', ';'.join(fl), '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'veryfast',
            '-crf', '14', '-pix_fmt', 'yuv420p', '-r', str(FPS), '-c:a', 'pcm_s16le', '-ar', str(SR), out_path + '.tmp.mov']
    run(cmd, f'cutting {os.path.basename(clip["path"])}')
    os.replace(out_path + '.tmp.mov', out_path)


# ------------------------------------------------------------------ captions + hook text (Pillow layers)
def hex_rgba(h, a=255):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def apply_fixes(word, fixes):
    core = re.sub(r"^[^\w']+|[^\w']+$", '', word)
    for k, v in fixes.items():
        if core.lower() == k.lower():
            return word.replace(core, v)
    return word


def caption_groups(words, o):
    groups, cur = [], []
    for w in words:
        if cur:
            text_len = len(' '.join(x['w'] for x in cur + [w]))
            if (len(cur) >= o['caption_max_words'] or w['s'] - cur[-1]['e'] > 0.35 or text_len > o['caption_max_chars']
                    or re.search(r'[.!?,;:]$', cur[-1]['w'])):
                groups.append(cur)
                cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def shown(word, o):
    t = re.sub(r'[.,;:]+$', '', word)
    return t.upper() if o['caption_case'] == 'upper' else t


class Painter:
    def __init__(self, o, cache_dir):
        self.o, self.cache = o, cache_dir
        self.fc = font(o['caption_size'], 'Black')
        self.fh = font(o['hook_text_size'], 'ExtraBold')
        self.box_layers = {}
        os.makedirs(cache_dir, exist_ok=True)

    def hook_layer(self, text):
        from PIL import Image, ImageDraw
        if text in self.box_layers:
            return self.box_layers[text]
        img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        maxw, words, lines, cur = 860, text.split(), [], ''
        for w in words:
            t = (cur + ' ' + w).strip()
            if d.textlength(t, font=self.fh) <= maxw or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) == 2:                           # balance two lines so one word is not left alone
            best = min(range(1, len(words)), key=lambda k: max(d.textlength(' '.join(words[:k]), font=self.fh),
                                                               d.textlength(' '.join(words[k:]), font=self.fh)))
            lines = [' '.join(words[:best]), ' '.join(words[best:])]
        asc, desc = self.fh.getmetrics()
        lh, padx, pady = asc + desc, 26, 12
        y = self.o['hook_text_y']
        for ln in lines:
            tw = d.textlength(ln, font=self.fh)
            x0 = (W - tw) / 2 - padx
            d.rounded_rectangle([x0, y, x0 + tw + 2 * padx, y + lh + 2 * pady], radius=18, fill=(255, 255, 255, 255))
            d.text(((W - tw) / 2, y + pady), ln, font=self.fh, fill=(0, 0, 0, 255))
            y += lh + 2 * pady - 6        # lines touch, like Instagram's own text boxes
        self.box_layers[text] = img
        return img

    def caption(self, img, group, active, o):
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        toks = [shown(w['w'], o) for w in group]
        space = d.textlength(' ', font=self.fc)
        widths = [d.textlength(t, font=self.fc) for t in toks]
        lines = [list(range(len(toks)))]
        if sum(widths) + space * (len(toks) - 1) > 940 and len(toks) > 1:
            cut = max(1, len(toks) // 2)
            lines = [list(range(cut)), list(range(cut, len(toks)))]
        asc, desc = self.fc.getmetrics()
        lh = asc + desc
        y = o['caption_y'] - (lh * len(lines)) / 2
        for ln in lines:
            tw = sum(widths[i] for i in ln) + space * (len(ln) - 1)
            x = (W - tw) / 2
            for i in ln:
                col = hex_rgba(o['caption_accent'] if i == active else o['caption_color'])
                d.text((x + 4, y + 6), toks[i], font=self.fc, fill=(0, 0, 0, 120), stroke_width=10, stroke_fill=(0, 0, 0, 120))
                d.text((x, y), toks[i], font=self.fc, fill=col, stroke_width=10, stroke_fill=(0, 0, 0, 255))
                x += widths[i] + space
            y += lh

    def state(self, hook_text, group, active):
        from PIL import Image
        key = hashlib.sha1(json.dumps(['layer-v2', hook_text, [w['w'] for w in group] if group else None, active,
                                       {k: self.o[k] for k in sorted(self.o) if k.startswith(('caption', 'hook_text'))}],
                                      default=str).encode()).hexdigest()[:16]
        path = os.path.join(self.cache, key + '.png')
        if not os.path.isfile(path):
            img = self.hook_layer(hook_text).copy() if hook_text else Image.new('RGBA', (W, H), (0, 0, 0, 0))
            if group:
                self.caption(img, group, active, self.o)
            img.save(path, compress_level=1)
        return path


def overlay_list(words, total, hook_text, box_end, o, painter, list_path):
    groups = caption_groups(words, o) if o['captions'] else []
    spans = []                                    # (start, end, group, active)
    for gi, g in enumerate(groups):
        g_end = min(groups[gi + 1][0]['s'] if gi + 1 < len(groups) else total, g[-1]['e'] + 0.5)
        for k, w in enumerate(g):
            s = w['s'] if k else g[0]['s']
            e = g[k + 1]['s'] if k + 1 < len(g) else g_end
            spans.append((q(s), q(e), g, k))
    cuts = {0.0, q(total), q(box_end)} | {s for s, _, _, _ in spans} | {e for _, e, _, _ in spans}
    cuts = sorted(c for c in cuts if 0 <= c <= q(total))
    items = [] if len(cuts) > 1 else [[painter.state('', None, None), total]]
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 0.5 / FPS:
            continue
        mid = (a + b) / 2
        hit = next(((g, k) for s, e, g, k in spans if s <= mid < e), (None, None))
        box = hook_text if (hook_text and mid < box_end) else ''
        img = painter.state(box, hit[0], hit[1])
        if items and items[-1][0] == img:
            items[-1][1] += b - a
        else:
            items.append([img, b - a])
    def quoted(p):                                    # ffconcat quoting: a ' inside the path becomes '\''
        return "'" + p.replace("'", "'\\''") + "'"
    with open(list_path, 'w', encoding='utf-8') as f:
        f.write('ffconcat version 1.0\n')
        for img, dur in items:
            f.write(f"file {quoted(img)}\nduration {dur:.4f}\n")
        f.write(f"file {quoted(items[-1][0])}\n")
    return len(items)


# ------------------------------------------------------------------ verify
def norm_words(text):
    return [re.sub(r"[^a-z0-9']", '', w.lower()) for w in text.split() if re.sub(r"[^a-z0-9']", '', w.lower())]


_MODEL = {}


def seg_words(path, cfg, vocab=''):
    cache = path + '.words.json'
    name = cfg.get('whisper_model', 'small.en')
    if os.path.isfile(cache):
        with open(cache, encoding='utf-8') as f:
            d = json.load(f)
        if d.get('model') == name:
            return d['words']
    from faster_whisper import WhisperModel
    if name not in _MODEL:
        _MODEL[name] = WhisperModel(name, device='cpu', compute_type='int8')
    segs, _ = _MODEL[name].transcribe(path, language=cfg.get('language', 'en') or None, word_timestamps=True,
                                      vad_filter=False, condition_on_previous_text=False,
                                      initial_prompt=vocab or None, beam_size=5)
    words = [{'w': w.word.strip(), 's': round(w.start, 3), 'e': round(w.end, 3)}
             for s in segs for w in (s.words or []) if w.word.strip()]
    with open(cache, 'w', encoding='utf-8') as f:
        json.dump({'model': name, 'words': words}, f)
    return words


def _norm(w):
    return re.sub(r"[^a-z0-9']", '', w.lower())


def compare(planned, heard_words):
    """Lines up what the plan expected (the full-clip transcript in the kept range) with what the cut actually says.
    Returns (caption words, problems). Captions keep the full-clip wording (more context, fewer misheard words) on
    the cut's own timing; words only the cut has (a restart left in, a half word at a join) are kept as heard.
    Problems: extra words heard (a restart such as "then check, then check", a half word) and planned words not
    heard (a clipped word). Same-length wording differences are the transcriber, not the edit, and are not flagged."""
    P = [w for w in planned if _norm(w['w'])]
    Hh = [w for w in heard_words if _norm(w['w'])]
    sm = difflib.SequenceMatcher(None, [_norm(w['w']) for w in P], [_norm(w['w']) for w in Hh], autojunk=False)
    caps, problems = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        a = ' '.join(_norm(w['w']) for w in P[i1:i2])
        b = ' '.join(_norm(w['w']) for w in Hh[j1:j2])
        if tag == 'equal' or (tag == 'replace' and (i2 - i1 == j2 - j1 or same_sound(a, b))):
            if i2 - i1 == j2 - j1:
                caps += [{'w': P[i1 + k]['w'], 's': Hh[j1 + k]['s'], 'e': Hh[j1 + k]['e']} for k in range(i2 - i1)]
            else:                                  # "gotta" vs "got to": one span, spread the plan's words over it
                s, e, n = Hh[j1]['s'], Hh[j2 - 1]['e'], i2 - i1
                caps += [{'w': P[i1 + k]['w'], 's': round(s + (e - s) * k / n, 3), 'e': round(s + (e - s) * (k + 1) / n, 3)}
                         for k in range(n)]
            continue
        caps += Hh[j1:j2]
        if b:
            problems.append(f'heard "{b}" that the plan did not have')
        if a:
            problems.append(f'planned "{a}" but it is not heard')
    return caps, problems


SOUNDS_SAME = [{'gotta', 'got to', 'got a'}, {'wanna', 'want to'}, {'gonna', 'going to'}, {'ok', 'okay'},
               {'kinda', 'kind of'}, {"cause", "because"}, {'alright', 'all right'}]


def same_sound(a, b):
    if a.replace(' ', '') == b.replace(' ', '') and a:
        return True
    for g in SOUNDS_SAME:
        if a in g and b in g:
            return True
    return bool(a and b and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8)


# ------------------------------------------------------------------ QA sheet
def qa_sheet(project, ads, out_path):
    from PIL import Image, ImageDraw
    tw, th = 216, 384
    frames = []
    tmp = os.path.join(project, 'work', 'qa_frames')
    os.makedirs(tmp, exist_ok=True)
    for ad in ads:
        p = os.path.join(tmp, f'{ad["id"]}_hook.jpg')
        run(['ffmpeg', '-y', '-v', 'error', '-ss', '0.6', '-i', ad['file'], '-frames:v', '1', '-q:v', '3', p], 'grabbing a QA frame')
        frames.append((ad['id'] + ' hook', p))
    first = ads[0]
    body_len = first['duration'] - first['hook_dur']
    for k in range(4):
        t = first['hook_dur'] + body_len * (k + 0.5) / 4
        p = os.path.join(tmp, f'body_{k}.jpg')
        run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{t:.2f}', '-i', first['file'], '-frames:v', '1', '-q:v', '3', p],
            'grabbing a QA frame')
        frames.append((f'body {t:.1f}s', p))
    cols = 6
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * tw, rows * (th + 30)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    label_font = font(20, 'Bold')
    for i, (label, p) in enumerate(frames):
        im = Image.open(p).convert('RGB').resize((tw, th))
        x, y = (i % cols) * tw, (i // cols) * (th + 30)
        sheet.paste(im, (x, y + 30))
        d.text((x + 8, y + 4), label, font=label_font, fill=(255, 255, 255))
    sheet.save(out_path, quality=88)
    shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ main
def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__.strip())
        return
    project = os.path.abspath(os.path.expanduser(args[0]))
    only = None
    if '--only' in args:
        only = set(args[args.index('--only') + 1].split(','))
    cfg = {}
    if os.path.isfile(os.path.join(SKILL, 'config.json')):
        with open(os.path.join(SKILL, 'config.json'), encoding='utf-8') as f:
            cfg = json.load(f)
    with open(os.path.join(project, 'plan.json'), encoding='utf-8') as f:
        plan = json.load(f)
    with open(os.path.join(project, 'work', 'clips.json'), encoding='utf-8') as f:
        clips = {c['id']: c for c in json.load(f)['clips']}
    o = dict(DEFAULTS)
    o.update({k: v for k, v in cfg.get('style', {}).items() if k in DEFAULTS})
    o.update({k: v for k, v in plan.get('style', {}).items() if k in DEFAULTS})
    o['fixes'] = {**cfg.get('fixes', {}), **plan.get('fixes', {})}

    seg_dir = os.path.join(project, 'work', 'segments')
    ads_dir = os.path.join(project, 'ads')
    os.makedirs(seg_dir, exist_ok=True)
    os.makedirs(ads_dir, exist_ok=True)
    painter = Painter(o, os.path.join(project, 'work', 'layers'))

    seg_cache = {}

    def segment(seg):
        clip = clips.get(seg['clip'])
        if not clip:
            raise SystemExit(f'plan uses clip {seg["clip"]} but clips.json has {", ".join(clips)}')
        key = seg_key(clip, seg, o)
        if key in seg_cache:
            return seg_cache[key]
        pieces, planned, dur = seg_pieces(clip, seg, o)
        path = os.path.join(seg_dir, key + '.mov')
        if not os.path.isfile(path):
            t0 = time.time()
            render_segment(clip, pieces, path)
            print(f'  cut {seg["clip"]} {seg["start"]:.2f}-{seg["end"]:.2f}: {len(pieces)} piece(s), {dur:.2f}s '
                  f'({time.time() - t0:.0f}s)', flush=True)
        # captions come from a transcript of the cut itself: exactly what is heard, at the times it is heard
        heard = seg_words(path, cfg, vocab=cfg.get('vocab', ''))
        words, problems = compare(planned, heard)
        for w in words:
            w['w'] = apply_fixes(w['w'], o['fixes'])
        def src_time(t):                          # a time in the cut back to the time in the original clip
            for p in pieces:
                if t < p['off'] + p['n'] / FPS:
                    return p['s'] + (t - p['off'])
            return pieces[-1]['s'] + pieces[-1]['n'] / FPS
        kept = {'clip': seg['clip'], 'kept': [(round(p['s'], 2), round(p['s'] + p['n'] / FPS, 2)) for p in pieces],
                'problems': problems, 'planned': ' '.join(w['w'] for w in planned),
                'heard': ' '.join(f'{w["w"]}[{src_time(w["s"]):.2f}]' for w in heard)}
        seg_cache[key] = (path, words, dur, kept)
        return seg_cache[key]

    bodies = plan.get('bodies', {})
    made = []
    manifest_path = os.path.join(ads_dir, 'manifest.json')
    old = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding='utf-8') as f:
            old = {a['id']: a for a in json.load(f).get('ads', [])}
    for ad in plan['ads']:
        if only and ad['id'] not in only:
            if ad['id'] in old:
                made.append(old[ad['id']])
            continue
        t0 = time.time()
        hp, hw, hd, hk = segment(ad['hook'])
        body = ad['body'] if isinstance(ad['body'], (dict, list)) else bodies[ad['body']]
        parts = [segment(s) for s in (body if isinstance(body, list) else [body])]   # a body can span several clips
        words, t = list(hw), hd
        for _, pw, pd, _ in parts:
            words += [{'w': w['w'], 's': round(w['s'] + t, 3), 'e': round(w['e'] + t, 3)} for w in pw]
            t += pd
        total = t
        hook_text = (ad.get('hook_text') or '').strip()
        box_end = o['hook_text_seconds'] if o['hook_text_seconds'] else max(hd, 3.0)
        box_end = min(box_end, total)
        lst = os.path.join(project, 'work', f'overlay_{ad["id"]}.txt')
        overlay_list(words, total, hook_text, box_end, o, painter, lst)
        out = os.path.join(ads_dir, f'{ad["id"]}.mp4')
        n = 1 + len(parts)
        ins = ''.join(f'[{i}:v][{i}:a]' for i in range(n))
        fl = (f'{ins}concat=n={n}:v=1:a=1[cv][ca];[{n}:v]fps={FPS},format=rgba[ov];'
              f'[cv][ov]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[vo];'
              f'[ca]loudnorm=I=-14:TP=-1.5:LRA=11,aresample={SR}[ao]')
        inputs = ['-i', hp]
        for pp, _, _, _ in parts:
            inputs += ['-i', pp]
        run(['ffmpeg', '-y', '-v', 'error', *inputs, '-f', 'concat', '-safe', '0', '-i', lst,
             '-filter_complex', fl, '-map', '[vo]', '-map', '[ao]', '-t', f'{total:.4f}', '-c:v', 'libx264',
             '-preset', 'medium', '-crf', '19', '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-r', str(FPS),
             '-c:a', 'aac', '-b:a', '192k', '-ar', str(SR), '-movflags', '+faststart', out + '.tmp.mp4'],
            f'rendering {ad["id"]}')
        os.replace(out + '.tmp.mp4', out)
        thumb = os.path.join(ads_dir, f'{ad["id"]}-thumb.jpg')
        run(['ffmpeg', '-y', '-v', 'error', '-ss', '0.4', '-i', out, '-frames:v', '1', '-q:v', '2', thumb], 'making the thumbnail')
        made.append({'id': ad['id'], 'name': ad.get('name', ad['id']), 'file': out, 'thumb': thumb,
                     'duration': round(total, 3), 'hook_dur': round(hd, 3), 'hook_text': hook_text,
                     'hook_said': ' '.join(w['w'] for w in hw), 'hook_src': hk, 'body_src': [p[3] for p in parts],
                     'words': words})
        print(f'{ad["id"]}: {total:.1f}s (hook {hd:.1f}s + body {total - hd:.1f}s) in {time.time() - t0:.0f}s  {out}', flush=True)

    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump({'ads': made, 'made': time.strftime('%Y-%m-%d %H:%M')}, f, indent=1)
    if made:
        qa = os.path.join(project, 'work', 'qa_sheet.jpg')
        qa_sheet(project, made, qa)
        print(f'QA sheet: {qa}')
    long = [a['id'] for a in made if a['duration'] > 60]
    if long:
        print(f'note: {", ".join(long)} run over 60 s; short ads usually hold attention better')
    print('word check (each cut re-transcribed and compared with the plan):')
    seen = set()
    for a in made:
        for label, src in [('hook', a['hook_src'])] + [('body', b) for b in a['body_src']]:
            k = (src['clip'], tuple(map(tuple, src['kept'])))
            if label == 'body' and k in seen:
                continue
            seen.add(k)
            who = f'{a["id"]} hook' if label == 'hook' else f'body ({src["clip"]} from {src["kept"][0][0]:.2f})'
            if not src.get('problems'):
                print(f'  {who}: ok')
                continue
            print(f'  {who}: CHECK  ' + '; '.join(src['problems']))
            print(f'      heard (times in the original clip): {src["heard"]}\n      kept from {src["clip"]}: '
                  + ', '.join(f'{s:.2f}-{e:.2f}' for s, e in src['kept']))
    print(f'manifest: {manifest_path}')


if __name__ == '__main__':
    main()
