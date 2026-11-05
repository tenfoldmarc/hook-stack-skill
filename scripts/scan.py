#!/usr/bin/env python3
"""Find the clips and transcribe them with word timings. Run with the skill's own Python (<skill>/.venv).

  scan.py list [--dir ~/Downloads] [--limit 25]
      newest video files in a folder (default: Downloads), with time, length and size, so you can spot the batch
      that was just AirDropped (they land within a few minutes of each other)

  scan.py transcribe <project_dir> <clip> [<clip> ...] [--model small.en] [--language en] [--vocab "Brand, Product"]
      probes every clip (size, fps, HDR, rotation) and transcribes it with word timestamps.
      Writes <project_dir>/work/clips.json and prints one block per clip: id, length, speech start/end, longest
      pause and the words with their times, which is what the plan is written from.

Clips are read where they are (nothing is copied or changed). Clip ids are c01, c02 ... in the order given.
"""
import json
import os
import subprocess
import sys
import time

VIDEO_EXT = ('.mp4', '.mov', '.m4v', '.MP4', '.MOV', '.M4V')
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    p = os.path.join(SKILL, 'config.json')
    if os.path.isfile(p):
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    return {}


def opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            v = args[i + 1]
            del args[i:i + 2]
            return v
    return default


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', path],
                         capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f'ffprobe could not read {path}: {out.stderr.strip()[-200:]}')
    d = json.loads(out.stdout)
    v = next((s for s in d['streams'] if s.get('codec_type') == 'video'), None)
    a = next((s for s in d['streams'] if s.get('codec_type') == 'audio'), None)
    if not v:
        raise SystemExit(f'{path} has no video stream')
    rot = 0
    for sd in v.get('side_data_list', []) or []:
        if 'rotation' in sd:
            rot = int(float(sd['rotation']))
    rot = rot or int(float(v.get('tags', {}).get('rotate', 0) or 0))
    w, h = int(v['width']), int(v['height'])
    if abs(rot) in (90, 270):
        w, h = h, w
    num, den = (v.get('avg_frame_rate') or v.get('r_frame_rate') or '30/1').split('/')
    fps = float(num) / float(den) if float(den) else 30.0
    trc = v.get('color_transfer', '') or ''
    return {
        'width': w, 'height': h, 'fps': round(fps, 3), 'rotation': rot,
        'duration': round(float(d['format'].get('duration') or v.get('duration') or 0), 3),
        'hdr': trc in ('arib-std-b67', 'smpte2084'), 'color_transfer': trc,
        'pix_fmt': v.get('pix_fmt', ''), 'has_audio': a is not None, 'codec': v.get('codec_name', ''),
    }


def cmd_list(args):
    folder = os.path.expanduser(opt(args, '--dir', '~/Downloads'))
    limit = int(opt(args, '--limit', '25'))
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(VIDEO_EXT) and not f.startswith('.')]
    files.sort(key=os.path.getmtime, reverse=True)
    if not files:
        print(f'no video files in {folder}')
        return
    print(f'newest videos in {folder}:')
    prev = None
    for p in files[:limit]:
        mt = os.path.getmtime(p)
        try:
            dur = probe(p)['duration']
        except SystemExit:
            dur = 0
        gap = '' if prev is None else f'  (+{(prev - mt) / 60:.0f} min gap)' if prev - mt > 600 else ''
        print(f'  {time.strftime("%b %d %H:%M", time.localtime(mt))}  {dur:6.1f}s  '
              f'{os.path.getsize(p) / 1e6:7.1f} MB  {p}{gap}')
        prev = mt


def cmd_transcribe(args):
    if len(args) < 2:
        raise SystemExit('usage: scan.py transcribe <project_dir> <clip> [<clip> ...]')
    cfg = load_config()
    model_name = opt(args, '--model', cfg.get('whisper_model', 'small.en'))
    language = opt(args, '--language', cfg.get('language', 'en'))
    vocab = opt(args, '--vocab', cfg.get('vocab', ''))
    project, clips = os.path.abspath(os.path.expanduser(args[0])), [os.path.abspath(os.path.expanduser(c)) for c in args[1:]]
    for c in clips:
        if not os.path.isfile(c):
            raise SystemExit(f'not a file: {c}')
    os.makedirs(os.path.join(project, 'work'), exist_ok=True)
    out_path = os.path.join(project, 'work', 'clips.json')
    old = {}
    if os.path.isfile(out_path):
        with open(out_path, encoding='utf-8') as f:
            for c in json.load(f).get('clips', []):
                old[(c['path'], c.get('mtime'), c.get('model'))] = c

    from faster_whisper import WhisperModel
    model = None
    result = []
    for i, path in enumerate(clips, 1):
        cid = f'c{i:02d}'
        mtime = round(os.path.getmtime(path), 1)
        hit = old.get((path, mtime, model_name))
        if hit:
            hit['id'] = cid
            result.append(hit)
            continue
        info = probe(path)
        if not info['has_audio']:
            raise SystemExit(f'{path} has no audio track; hook-stack needs the spoken audio')
        if model is None:
            print(f'loading speech model {model_name} (first time downloads it once) ...', flush=True)
            model = WhisperModel(model_name, device='cpu', compute_type='int8')
        t0 = time.time()
        segs, _ = model.transcribe(path, language=language or None, word_timestamps=True, vad_filter=False,
                                   condition_on_previous_text=False, initial_prompt=vocab or None, beam_size=5)
        words = []
        for s in segs:
            for w in s.words or []:
                txt = w.word.strip()
                if txt:
                    words.append({'w': txt, 's': round(w.start, 3), 'e': round(w.end, 3), 'p': round(w.probability, 2)})
        print(f'  {cid} transcribed in {time.time() - t0:.0f}s', flush=True)
        result.append(dict(id=cid, path=path, mtime=mtime, model=model_name, **info, words=words,
                           text=' '.join(w['w'] for w in words)))
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'clips': result, 'made': time.strftime('%Y-%m-%d %H:%M')}, f, indent=1)

    for c in result:
        ws = c['words']
        pauses = [(round(b['s'] - a['e'], 2), a['e']) for a, b in zip(ws, ws[1:])]
        longest = max(pauses) if pauses else (0, 0)
        print(f'\n== {c["id"]}  {os.path.basename(c["path"])}  {c["duration"]:.1f}s  {c["width"]}x{c["height"]} '
              f'{c["fps"]:g}fps{"  HDR" if c["hdr"] else ""}')
        if not ws:
            print('   (no speech found)')
            continue
        print(f'   speech {ws[0]["s"]:.2f} to {ws[-1]["e"]:.2f}   longest pause {longest[0]:.2f}s at {longest[1]:.2f}')
        line = '   '
        for w in ws:
            tok = f'{w["w"]}[{w["s"]:.2f}]' + ('?' if w['p'] < 0.5 else '')
            if len(line) + len(tok) > 118:
                print(line)
                line = '   '
            line += tok + ' '
        print(line)
    print(f'\nwrote {out_path}')


def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__.strip())
        return
    cmd, rest = args[0], args[1:]
    if cmd == 'list':
        cmd_list(rest)
    elif cmd == 'transcribe':
        cmd_transcribe(rest)
    else:
        raise SystemExit(f'unknown command {cmd}; use list or transcribe')


if __name__ == '__main__':
    main()
