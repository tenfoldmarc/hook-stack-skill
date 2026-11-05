#!/usr/bin/env python3
"""First-run setup and quick health check for the hook-stack skill. Standard library only: any python3 runs it.

  python3 scripts/setup_skill.py            set up or repair (safe to run again: it only fixes what is missing)
  python3 scripts/setup_skill.py --check    look only, change nothing (exit code 0 = ready)

What it does:
  1. checks the tools the skill calls: ffmpeg + ffprobe
  2. makes the skill's own Python environment, <skill>/.venv, from requirements.txt (exact, tested versions) with a
     Python between 3.11 and 3.14, and proves it works: every version matches and a real audio decode runs through
     faster-whisper and PyAV
  3. checks the bundled caption fonts
Meta is not checked here: launching goes through the Meta Ads connector, which Claude checks at the first launch.
Options: --python <path> use this Python for the venv
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

PY_MIN, PY_MAX = (3, 11), (3, 14)
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV = os.path.join(SKILL, '.venv')
REQ = os.path.join(SKILL, 'requirements.txt')
FONTS = os.path.join(SKILL, 'fonts')
WIN = os.name == 'nt'
MAC = sys.platform == 'darwin'
INTEL_MAC = MAC and platform.machine() == 'x86_64'
OS = 'win' if WIN else 'mac' if MAC else 'linux'

FIX = {
    'ffmpeg': {'mac': 'brew install ffmpeg', 'win': 'winget install --id Gyan.FFmpeg -e',
               'linux': 'sudo apt install ffmpeg   (or your distribution\'s package manager)'},
    'python': {'mac': 'brew install python@3.12   (or the installer from https://www.python.org/downloads/)',
               'win': 'winget install --id Python.Python.3.12 -e   (or https://www.python.org/downloads/)',
               'linux': 'sudo apt install python3.12 python3.12-venv   (or any Python 3.11 to 3.14 with venv)'},
}
BREW = ('Homebrew is not installed. Open Terminal and paste this one line, then press Enter (it asks for your Mac '
        'password): /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')

VERIFY = r'''
import importlib.metadata as md, json, os, sys, tempfile, wave
out = {"wrong": [], "error": None, "versions": {}}
try:
    from packaging.requirements import Requirement
    for line in open(sys.argv[1], encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        r = Requirement(line)
        if r.marker is not None and not r.marker.evaluate():
            continue
        want = next(iter(r.specifier)).version
        try:
            have = md.version(r.name)
        except md.PackageNotFoundError:
            have = None
        if have != want:
            out["wrong"].append("%s %s (wants %s)" % (r.name, have or "missing", want))
    import numpy, PIL, av, ctranslate2, onnxruntime, faster_whisper
    from faster_whisper.audio import decode_audio
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "silence.wav")
        with wave.open(p, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\x00\x00" * 16000)
        n = len(decode_audio(p, sampling_rate=16000))
    if n != 16000:
        out["error"] = "the audio decode test returned %d samples instead of 16000" % n
    out["versions"] = {k: md.version(k) for k in ("faster-whisper", "av", "numpy", "Pillow", "onnxruntime")}
except Exception as e:
    out["error"] = "%s: %s" % (type(e).__name__, e)
print(json.dumps(out))
'''


def venv_python():
    return os.path.join(VENV, 'Scripts', 'python.exe') if WIN else os.path.join(VENV, 'bin', 'python')


def run(cmd, timeout=None, env=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def say(status, what, detail=''):
    print(f'  {status:<9} {what}' + (f': {detail}' if detail else ''))


# ------------------------------------------------------------------ tools
def check_ffmpeg(fixes):
    ok = True
    for name in ('ffmpeg', 'ffprobe'):
        path = shutil.which(name)
        if not path:
            say('MISSING', name)
            ok = False
            continue
        code, out = run([path, '-version'], 30)
        m = re.search(r'version\s+(\S+)', out)
        say('ok', name, f'{m.group(1) if m else "?"} ({path})')
    if not ok:
        if MAC and not shutil.which('brew'):
            fixes.append(BREW)
        fixes.append('ffmpeg: ' + FIX['ffmpeg'][OS])
    return ok


# ------------------------------------------------------------------ python + venv
def py_info(cmd):
    code, out = run(cmd + ['-c', 'import sys,sysconfig;print("%d.%d.%d" % sys.version_info[:3], '
                                 'int(bool(sysconfig.get_config_var("Py_GIL_DISABLED"))))'], 60)
    m = re.search(r'(\d+)\.(\d+)\.(\d+) (\d)', out)
    return (tuple(int(x) for x in m.groups()[:3]), m.group(4) == '1') if code == 0 and m else (None, False)


def usable(version, free_threaded):
    if not version or free_threaded:
        return False
    if not (PY_MIN <= version[:2] <= PY_MAX):
        return False
    return not (INTEL_MAC and version[:2] >= (3, 14))       # no onnxruntime build for Intel Macs on 3.14


def pick_python(forced):
    if forced:
        cands = [[forced]]
    elif WIN:
        cands = [['py', '-3.12'], ['py', '-3.13'], ['py', '-3.11'], ['py', '-3.14'], ['python']]
    else:
        cands = [[n] for n in ('python3.12', 'python3.13', 'python3.11', 'python3.14', 'python3', 'python') if shutil.which(n)]
    cands.append([sys.executable])
    seen = []
    for c in cands:
        v, ft = py_info(c)
        if v:
            seen.append('.'.join(map(str, v)))
        if usable(v, ft):
            return c, v
    return None, seen


def check_venv(check_only, forced_python, fixes):
    vp = venv_python()
    ok_python = False
    if os.path.isfile(vp):
        v, ft = py_info([vp])
        ok_python = usable(v, ft)
        if not ok_python and not check_only:
            old = VENV + '-old-' + time.strftime('%Y%m%d-%H%M%S')
            os.rename(VENV, old)                         # never deleted: moved aside, safe to remove by hand
            say('note', '.venv did not work', f'moved aside to {old} (delete it whenever you like) and made again')
    if not ok_python:
        if check_only:
            if os.path.isfile(vp):
                say('FAILED', 'the skill\'s Python environment (.venv)', 'its Python is broken or not 3.11 to 3.14; '
                    'run this script without --check to rebuild it')
                fixes.append('Python environment: run this script without --check')
            else:
                say('MISSING', 'the skill\'s Python environment (.venv)', 'run this script without --check to make it')
            return False
        cmd, v = pick_python(forced_python)
        if not cmd:
            found = f' (found: {", ".join(v)})' if v else ''
            say('MISSING', f'Python {PY_MIN[0]}.{PY_MIN[1]} to {PY_MAX[0]}.{PY_MAX[1]}{found}')
            if MAC and not shutil.which('brew'):
                fixes.append(BREW)
            fixes.append('Python: ' + FIX['python'][OS])
            return False
        print(f'  making .venv with Python {".".join(map(str, v))} ...')
        code, out = run(cmd + ['-m', 'venv', VENV], 600)
        if code:
            say('FAILED', 'could not make .venv', out.strip()[-300:])
            if 'ensurepip' in out:
                fixes.append(f'Python venv support: sudo apt install python{v[0]}.{v[1]}-venv, then run setup again')
            return False
    result = verify()
    if (result.get('wrong') or result.get('error')) and not check_only:
        print('  installing the tested Python packages into .venv (first time: about 1 to 3 minutes) ...')
        code = subprocess.call([vp, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '-q', '-r', REQ])
        if code:
            say('FAILED', 'pip install -r requirements.txt', 'see the error above')
            fixes.append('Python packages: read the pip error above; check your internet connection and run setup again')
            return False
        result = verify()
    v, _ = py_info([vp])
    if result.get('wrong'):
        say('MISSING' if check_only else 'FAILED', 'Python packages not at the tested versions', '; '.join(result['wrong'][:6]))
        if check_only:
            fixes.append('Python packages: run this script without --check')
        return False
    if result.get('error'):
        say('FAILED', 'Python packages do not work', result['error'])
        fixes.append('Python packages: run this script again; if it repeats, move .venv to the Trash and run it again')
        return False
    vs = result.get('versions', {})
    say('ok', f'Python {".".join(map(str, v))} environment', f'{vp}')
    say('ok', 'packages', f'faster-whisper {vs.get("faster-whisper")}, PyAV {vs.get("av")}, numpy {vs.get("numpy")}, '
        f'Pillow {vs.get("Pillow")}; audio decode works')
    return True


def verify():
    vp = venv_python()
    if not os.path.isfile(vp):
        return {'error': 'no .venv'}
    code, out = run([vp, '-I', '-c', VERIFY, REQ], 600)
    try:
        return json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {'error': (out.strip()[-300:] or 'the check did not run')}


# ------------------------------------------------------------------ fonts
def check_fonts(fixes):
    need = ('InterTight-Variable.ttf',)
    miss = [f for f in need if not os.path.isfile(os.path.join(FONTS, f))]
    if miss:
        say('MISSING', 'caption fonts', ', '.join(miss))
        fixes.append('fonts: the skill folder is incomplete; reinstall the skill from GitHub')
        return False
    say('ok', 'caption fonts', FONTS)
    return True


def main():
    args = sys.argv[1:]
    if '-h' in args or '--help' in args:
        print(__doc__.strip())
        return 0
    check_only = '--check' in args
    forced = args[args.index('--python') + 1] if '--python' in args and args.index('--python') + 1 < len(args) else None
    print(f'hook-stack {"check" if check_only else "setup"} ({SKILL})')
    fixes = []
    ff = check_ffmpeg(fixes)
    py = check_venv(check_only, forced, fixes)
    fo = check_fonts(fixes)
    say('note', 'Meta', 'launching goes through the Meta Ads connector; Claude checks it at the first launch')
    ready = ff and py and fo
    print('READY' if ready else 'NOT READY')
    if ready:
        print(f'skill python: {venv_python()}')
    for f in fixes:
        print('  fix: ' + f)
    return 0 if ready else 1


if __name__ == '__main__':
    sys.exit(main())
