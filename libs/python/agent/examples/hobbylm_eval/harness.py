"""Text-only, sequential HobbyLM evaluation against an explicitly owned Linux guest.

No desktop is created by this program. Attach to cua-spacesd in an owned headless
Sway guest, with xwayland disabled. Provision /tmp/hobbylm-eval-owned.json with
{"owner": "<ownership-id>", "environment": "owned-linux-sway-v1"} there.
Requires guest python3 + python3-gi/AT-SPI, swaymsg, mate-calc, mousepad,
thunar, orage, parole, xfce4-notes, gsettings and pactl.
Unavailable capabilities are reported as unsupported, never successful.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import resource
import selectors
import shlex
import subprocess
import sys
import threading
import time
from typing import Any
from urllib.parse import urlsplit

TASKS_PATH = Path(__file__).with_name("tasks.json")
ENVIRONMENT = "owned-linux-sway-v1"
APPS = {"Calculator": "mate-calc", "Notes": "mousepad", "Calendar": "orage",
        "Finder": "thunar", "Music": "parole", "Reminders": "xfce4-notes"}
KEYS = {"VOLUME_UP", "VOLUME_DOWN", "MUTE", "BRIGHTNESS_UP", "BRIGHTNESS_DOWN"}

# This constant script is the only guest shell program. Model text is JSON data,
# never interpolated source. All subprocess calls use bounded argv, not a shell.
GUEST = r'''
import base64, datetime, hashlib, json, os, pathlib, re, shutil, signal, subprocess, sys, time
p = json.loads(base64.b64decode(sys.argv[1]))
root = pathlib.Path('/tmp/hobbylm-eval')
marker = json.loads(pathlib.Path('/tmp/hobbylm-eval-owned.json').read_text())
if marker != {'owner':p['owner'], 'environment':'owned-linux-sway-v1'}:
    raise RuntimeError('Owned sandbox marker does not match')
if not os.environ.get('WAYLAND_DISPLAY') or not os.environ.get('SWAYSOCK') or os.environ.get('DISPLAY'):
    raise RuntimeError('Requires private headless Sway sockets, with no X11 display')
apps = {'Calculator':'mate-calc','Notes':'mousepad','Calendar':'orage','Finder':'thunar',
        'Music':'parole','Reminders':'xfce4-notes'}
allowed = set(apps.values()) | {'swaymsg','pactl','gsettings','grim'}
def run(argv, check=False):
    if not argv or argv[0] not in allowed:
        raise ValueError('Executable outside fixed allowlist')
    r = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    if check and r.returncode:
        raise RuntimeError(r.stderr[:2000])
    return r.stdout.strip() if r.returncode == 0 else None
outputs = json.loads(run(['swaymsg','-r','-t','get_outputs'],True))
if not outputs or any(not o['name'].startswith('HEADLESS-') for o in outputs):
    raise RuntimeError('Only owned HEADLESS Sway outputs are allowed')
def process_identity(pid):
    try:
        executable = pathlib.Path('/proc/%s/exe' % pid)
        info = executable.stat()
        stat = pathlib.Path('/proc/%s/stat' % pid).read_text().rsplit(')',1)[1].split()
        return {'pid':int(pid), 'start_ticks':int(stat[19]),
                'executable':str(executable.resolve(strict=True)),
                'executable_dev':info.st_dev, 'executable_ino':info.st_ino}
    except (OSError, ValueError, IndexError):
        return None
def windows():
    tree = json.loads(run(['swaymsg','-r','-t','get_tree'],True))
    found = []
    def visit(node):
        if node.get('app_id') and node.get('pid'):
            identity = process_identity(node['pid'])
            binary = pathlib.Path(identity['executable']).name if identity else ''
            found.append({'id':node['id'],'title':node.get('name',''),
                          'focused':node.get('focused',False),'binary':binary,
                          'identity':identity,
                          'app':next((k for k,v in apps.items() if v == binary),None)})
        for child in node.get('nodes',[]) + node.get('floating_nodes',[]): visit(child)
    visit(tree)
    return found
root.mkdir(mode=0o700, exist_ok=True)
if root.is_symlink():
    raise RuntimeError('Owned root cannot be a symlink')
pidfile = root / 'processes.json'
def processes():
    return json.loads(pidfile.read_text()) if pidfile.exists() else []
def alive(row):
    identity = process_identity(row['pid'])
    return identity is not None and all(row.get(k) == value for k,value in identity.items())
def stop_owned(row):
    try:
        fd = os.pidfd_open(row['pid'])
    except ProcessLookupError:
        return
    try:
        if alive(row):
            signal.pidfd_send_signal(fd, signal.SIGTERM)
    finally:
        os.close(fd)
def spawn(name, extra=()):
    executable = apps[name]
    if not shutil.which(executable):
        raise RuntimeError('Unavailable app: ' + executable)
    rows = processes()
    proc = subprocess.Popen([executable, *extra], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    identity = process_identity(proc.pid)
    if identity is None:
        raise RuntimeError('Launched app exited before ownership could be recorded')
    rows.append(dict(identity, app=name))
    pidfile.write_text(json.dumps(rows))
timer_code = "import pathlib,sys,time; time.sleep(int(sys.argv[1])); pathlib.Path('/tmp/hobbylm-eval/timer-expired').touch()"
def timer_state():
    try:
        pid = int((root/'timer.pid').read_text())
        argv = pathlib.Path('/proc/%s/cmdline' % pid).read_bytes().split(b'\0')
        if len(argv) < 4 or argv[1:3] != [b'-c',timer_code.encode()]: return None
        seconds = int(argv[3])
        stat = pathlib.Path('/proc/%s/stat' % pid).read_text().rsplit(')',1)[1].split()
        start = int(stat[19]) / os.sysconf('SC_CLK_TCK')
        uptime = float(pathlib.Path('/proc/uptime').read_text().split()[0])
        return {'pid':pid,'duration_seconds':seconds,'remaining_seconds':max(0,seconds-uptime+start),
                'running':stat[0] != 'Z','start_ticks':int(stat[19])}
    except (OSError,ValueError,IndexError):
        return None
def theme():
    if not shutil.which('gsettings'):
        return None
    value = run(['gsettings','get','org.gnome.desktop.interface','gtk-theme'])
    return None if value is None else 'dark' in value.lower()
def set_theme(dark):
    run(['gsettings','set','org.gnome.desktop.interface','gtk-theme',
         'Adwaita-dark' if dark else 'Adwaita'], True)
    run(['gsettings','set','org.gnome.desktop.interface','color-scheme',
         'prefer-dark' if dark else 'default'])
def focused_calculator(expected=None):
    front = next((row for row in windows() if row['focused']), None)
    if not front or front['app'] != 'Calculator' or not front['identity']:
        raise ValueError('The owned Calculator process is not foreground')
    identity = front['identity']
    if expected is not None and identity != expected:
        raise ValueError('Calculator focus changed during TYPE')
    if not any(row.get('app') == 'Calculator' and alive(row) and
               all(row.get(k) == value for k,value in identity.items()) for row in processes()):
        raise ValueError('Calculator process ownership is not verified')
    return identity
def calculator_accessible(identity):
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi
    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app.get_process_id() == identity['pid']:
            return app
    raise RuntimeError('Owned Calculator accessibility application is unavailable')
def ax_calculator():
    # Only the live editbar is an oracle, never history or unrelated labels.
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi
    try:
        identity = focused_calculator()
    except ValueError:
        return []
    texts = []
    def visit(node, depth=0):
        if depth > 12:
            return
        if node.get_role_name() == 'editbar':
            text = node.get_text_iface()
            content = Atspi.Text.get_text(text, 0, text.get_character_count())
            if content.strip(): texts.append(content.strip())
        for i in range(min(node.get_child_count(), 200)):
            child = node.get_child_at_index(i)
            if child: visit(child, depth + 1)
    visit(calculator_accessible(identity))
    return texts
def snapshot():
    caps = {k:bool(shutil.which(v)) for k,v in apps.items()}
    for tool in ('swaymsg','pactl','gsettings'):
        caps[tool] = bool(shutil.which(tool))
    try:
        values = ax_calculator()
        caps['atspi'] = True
    except Exception:
        values = []
        caps['atspi'] = False
    live_windows = windows()
    title = next((row['title'] for row in live_windows if row['focused']),None)
    focused = next((row for row in live_windows if row['focused']), None)
    owned = processes()
    front_owned = bool(focused and focused['identity'] and any(
        row.get('app') == focused['app'] and alive(row) and
        all(row.get(k) == value for k,value in focused['identity'].items()) for row in owned))
    volume = run(['pactl','get-sink-volume','@DEFAULT_SINK@']) if caps['pactl'] else None
    mute = run(['pactl','get-sink-mute','@DEFAULT_SINK@']) if caps['pactl'] else None
    match = re.search(r'(\d+)%', volume or '')
    timer = timer_state()
    calendar = root / 'calendar.ics'
    answer = root / 'Desktop' / 'answer.txt'
    return {'capabilities':caps, 'front_title':title,
            'front_identity':focused['identity'] if focused else None,
            'front_app':focused['app'] if focused else None, 'front_owned':front_owned,
            'apps':sorted(set(r['app'] for r in live_windows if r['app'])),
            'calculator_text':values, 'volume':int(match[1]) if match else None,
            'muted':None if mute is None else 'yes' in mute,
            'dark':theme(), 'brightness':None, 'timer':timer,
            'calendar':calendar.read_text() if calendar.exists() else '',
            'contacts':(root/'contact.vcf').read_text() if (root/'contact.vcf').exists() else '',
            'answer':answer.read_text() if answer.exists() else '',
            'screenshots':sorted(f.name for f in root.glob('capture-*.png')),
            'question':(root/'Desktop'/'question.txt').read_text() if (root/'Desktop'/'question.txt').exists() else ''}
mode = p['mode']
if mode == 'snapshot':
    result = snapshot()
elif mode == 'fingerprint':
    result = {'os_release':pathlib.Path('/etc/os-release').read_text(),
              'architecture':os.uname().machine,
              'sway':json.loads(run(['swaymsg','-r','-t','get_version'],True)),
              'outputs':[{k:o.get(k) for k in ('name','rect','scale','transform')} for o in outputs],
              'app_binaries':{k:hashlib.sha256(pathlib.Path(shutil.which(v)).read_bytes()).hexdigest()
                              if shutil.which(v) else None for k,v in apps.items()}}
elif mode == 'reset':
    for row in processes():
        stop_owned(row)
    pidfile.write_text('[]')
    active_timer = timer_state()
    if active_timer and active_timer['running']:
        try: os.kill(active_timer['pid'],signal.SIGTERM)
        except ProcessLookupError: pass
    for name in ('calendar.ics', 'Desktop/answer.txt', 'Desktop/question.txt', 'timer.pid', 'timer-expired'):
        path = root / name
        if path.is_symlink(): raise RuntimeError('Refusing symlink fixture')
        path.unlink(missing_ok=True)
    for path in root.glob('capture-*.png'):
        path.unlink()
    for folder in ('Desktop','Downloads','Documents'):
        (root/folder).mkdir(exist_ok=True)
    if shutil.which('pactl'):
        run(['pactl','set-sink-volume','@DEFAULT_SINK@','50%'])
        run(['pactl','set-sink-mute','@DEFAULT_SINK@','0'])
    if shutil.which('gsettings') and theme() is not None: set_theme(p.get('dark',False))
    # Timer process is scoped by its exact fixed cmdline, not an external service.
    (root/'contact.vcf').write_text('BEGIN:VCARD\nVERSION:3.0\nFN:Eval Contact\nEMAIL:eval-contact@example.invalid\nEND:VCARD\n')
    if p.get('question'):
        (root/'Desktop'/'question.txt').write_text(p['question'])
    result = {'reset':True}
elif mode == 'type':
    text = p['text']
    if not isinstance(text,str) or not re.fullmatch(r'[0-9. +*/=\-]{1,128}',text):
        raise ValueError('TYPE is restricted to calculator keys')
    identity = focused_calculator(p['identity'])
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi
    buttons = {}
    def visit_buttons(node, depth=0):
        if depth > 14:
            return
        if node.get_role_name() == 'push button':
            buttons[node.get_name()] = node
        for i in range(min(node.get_child_count(),200)):
            child = node.get_child_at_index(i)
            if child: visit_buttons(child,depth+1)
    visit_buttons(calculator_accessible(identity))
    names = {'+':'add','-':'subtract','*':'multiply','/':'divide',
             '=':'result','.':'numeric_point'}
    for char in text:
        if char == ' ': continue
        focused_calculator(identity)
        button = buttons.get(names.get(char,char))
        if button is None or not Atspi.Action.do_action(button,0):
            raise RuntimeError('Owned Calculator accessible button failed')
        time.sleep(.05)
    result = {'typed':text,'execution_backend':'native Calculator accessibility buttons'}
elif mode == 'open':
    spawn(p['app'])
    result = {'opened':p['app']}
elif mode == 'folder':
    if p['folder'] not in ('Desktop','Downloads','Documents'): raise ValueError('Invalid folder')
    spawn('Finder', [str(root/p['folder'])])
    result = {'opened':p['folder']}
elif mode == 'key':
    key = p['key']
    if key not in ('VOLUME_DOWN','VOLUME_UP','MUTE'): raise ValueError('Unsupported key')
    if key == 'MUTE': run(['pactl','set-sink-mute','@DEFAULT_SINK@','1'], True)
    else: run(['pactl','set-sink-volume','@DEFAULT_SINK@','5%-' if key == 'VOLUME_DOWN' else '5%+'],True)
    result = {'key':key}
elif mode == 'dark':
    set_theme(p['enabled'])
    result = {'dark':p['enabled']}
elif mode == 'timer':
    minutes = p['minutes']
    if type(minutes) is not int or not 1 <= minutes <= 120: raise ValueError('Invalid timer')
    existing = timer_state()
    if existing and existing['running']: os.kill(existing['pid'],signal.SIGTERM)
    proc = subprocess.Popen([sys.executable,'-c',timer_code,str(minutes*60)],
                            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,start_new_session=True)
    (root/'timer.pid').write_text(str(proc.pid))
    result = {'timer_minutes':minutes}
elif mode == 'event':
    event = p['event']
    fixture = p['confirmation']
    if fixture != dict(event, confirmed=True, local_only=True):
        raise ValueError('Event does not match explicit confirmation fixture')
    title, day, clock, person = (event[k] for k in ('title','day','time','person'))
    if person == 'Eval Contact':
        contact = (root/'contact.vcf').read_text()
        if 'FN:Eval Contact\n' not in contact: raise ValueError('Owned contact missing')
        match = re.search(r'^EMAIL:([^\r\n]+)$',contact,re.M)
        if not match: raise ValueError('Owned contact has no email')
        person = match[1]
    if person not in ('none','eval-contact@example.invalid'): raise ValueError('Not a synthetic contact')
    if not re.fullmatch(r'[A-Za-z0-9 _-]{1,80}',title): raise ValueError('Unsafe event title')
    dt = datetime.datetime.strptime(day + ' ' + clock,'%Y-%m-%d %H:%M UTC')
    uid = hashlib.sha256(json.dumps(event,sort_keys=True).encode()).hexdigest()[:24]
    # A genuine local RFC5545 calendar, deliberately no METHOD/ATTENDEE or send call.
    content = '\r\n'.join(['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//CUA//Owned Eval//EN',
        'BEGIN:VEVENT','UID:'+uid+'@example.invalid','DTSTAMP:20300101T000000Z',
        'DTSTART:'+dt.strftime('%Y%m%dT%H%M%SZ'),'SUMMARY:'+title,
        'X-EVAL-CONTACT:'+person,'END:VEVENT','END:VCALENDAR',''])
    (root/'calendar.ics').write_text(content)
    result = {'saved_local_calendar':'/tmp/hobbylm-eval/calendar.ics','invitation_sent':False}
elif mode == 'capture':
    shot = subprocess.run(['grim','-o',outputs[0]['name'],'-'],capture_output=True,timeout=10,check=True)
    result = {'png':base64.b64encode(shot.stdout).decode()}
elif mode == 'save_screenshot':
    data = base64.b64decode(p['png'],validate=True)
    if not data.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('Not PNG')
    digest = hashlib.sha256(data).hexdigest()
    (root/('capture-'+digest+'.png')).write_bytes(data)
    result = {'sha256':digest}
else:
    raise ValueError('Unknown guest operation')
print(json.dumps(result,sort_keys=True))
'''


def validate_endpoint(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("A cua-spacesd HTTP(S) URL is required")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Endpoint must not embed credentials, query or fragment")
    return url


def event_fields(argument: str) -> dict[str, str]:
    fields = [v.strip() for v in argument.split("|")]
    if len(fields) != 4:
        raise ValueError("EVENT requires title | ISO day | HH:MM UTC | person")
    return dict(zip(("title", "day", "time", "person"), fields))


def action_command(name: str, argument: str, confirmation: dict | None = None) -> dict:
    """Validate model data before any guest request; no arbitrary commands exist."""
    if name == "OPEN" and argument in APPS:
        return {"mode": "open", "app": argument}
    if name == "FOLDER" and argument in {"Desktop", "Downloads", "Documents"}:
        return {"mode": "folder", "folder": argument}
    if name == "TYPE" and re.fullmatch(r"[0-9. +*/=\-]{1,80}", argument):
        return {"mode": "type", "text": argument}
    if name == "KEY" and argument in KEYS:
        if argument.startswith("BRIGHTNESS"):
            raise NotImplementedError("Headless display has no physical backlight")
        return {"mode": "key", "key": argument}
    if name == "DARK_MODE" and argument in {"ON", "OFF"}:
        return {"mode": "dark", "enabled": argument == "ON"}
    if name == "TIMER" and re.fullmatch(r"[0-9]{1,3}", argument) and 1 <= int(argument) <= 120:
        return {"mode": "timer", "minutes": int(argument)}
    if name == "EVENT":
        event = event_fields(argument)
        if confirmation != dict(event, confirmed=True, local_only=True):
            raise ValueError("EVENT lacks matching explicit local-only confirmation")
        return {"mode": "event", "event": event, "confirmation": confirmation}
    if name in {"SCREENSHOT", "DONE", "UNKNOWN"} and not argument:
        return {"mode": name.lower()}
    raise ValueError("Action outside the frozen ten-action allowlist")


class OwnedLinuxBackend:
    """Existing cua Sandbox HTTP transport; never touches a host desktop."""

    def __init__(self, sandbox: Any, owner: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", owner):
            raise ValueError("Ownership id must be 8-80 alphanumeric/underscore/hyphen characters")
        self.sandbox, self.owner = sandbox, owner
        self.confirmation: dict | None = None

    async def guest(self, **payload: Any) -> dict:
        encoded = base64.b64encode(json.dumps(dict(payload, owner=self.owner)).encode()).decode()
        result = await self.sandbox.shell.run(shlex.join(["python3", "-c", GUEST, encoded]), timeout=30)
        if not result.success:
            raise RuntimeError("Guest operation failed: " + result.stderr[:3000])
        return json.loads(result.stdout)

    async def reset(self, task: dict) -> None:
        self.confirmation = task.get("confirmation")
        await self.guest(mode="reset", dark=task.get("initial", {}).get("dark", False),
                         question=task.get("question", ""))
        await asyncio.sleep(0.3)

    async def snapshot(self) -> dict:
        return await self.guest(mode="snapshot")

    async def observe(self) -> str:
        return semantic_state(await self.snapshot())

    async def screenshot(self) -> bytes:
        try:
            data = await self.sandbox.screenshot()
        except Exception:
            # Older spacesd images lack wlroots capture; grim is scoped to the
            # explicitly verified guest HEADLESS output, never the host display.
            data = base64.b64decode((await self.guest(mode="capture"))["png"], validate=True)
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("Sandbox screenshot is not PNG")
        return data

    async def action(self, raw: str) -> dict:
        from cua_agent.loops.hobbylm import parse_action
        action = parse_action(raw)
        command = action_command(action.name, action.argument, self.confirmation)
        mode = command["mode"]
        if mode == "type":
            snapshot = await self.snapshot()
            if not snapshot.get("front_owned") or snapshot.get("front_app") != "Calculator":
                raise ValueError("TYPE requires the verified owned Calculator process to be foreground")
            focused_identity = snapshot["front_identity"]
            current = await self.snapshot()
            if (not current.get("front_owned") or current.get("front_app") != "Calculator"
                    or current.get("front_identity") != focused_identity):
                raise ValueError("Calculator focus changed during TYPE")
            # spacesd 0.6's native keyboard route requires X11. Use the actual
            # owned application's accessible buttons, never Python arithmetic.
            result = await self.guest(**command, identity=focused_identity)
        elif mode == "screenshot":
            result = await self.guest(mode="save_screenshot",
                                      png=base64.b64encode(await self.screenshot()).decode())
        elif mode in {"done", "unknown"}:
            result = {"terminal": mode}
        else:
            result = await self.guest(**command)
        await asyncio.sleep(0.3)
        return result


def semantic_state(snapshot: dict) -> str:
    """Only independently observed text goes to every runtime, never PNG bytes."""
    return "\n".join([
        "Calculator: " + ("open, display shows " + (
            snapshot["calculator_text"][0] if snapshot["calculator_text"] else "(empty)")
            if "Calculator" in snapshot["apps"] else "not open"),
        "Front app: " + str(snapshot.get("front_app") or snapshot["front_title"]),
        f"Brightness: unsupported (headless)  Volume: {snapshot['volume']}%" +
        (" (muted)" if snapshot["muted"] else ""),
        "Dark mode: " + ("unknown" if snapshot["dark"] is None else "on" if snapshot["dark"] else "off"),
        "Open apps: " + ", ".join(snapshot["apps"]),
        "Timer (actual owned countdown process): " + str(snapshot["timer"]),
        "Owned local calendar: " + snapshot["calendar"],
        "Owned contact names: " + ", ".join(re.findall(r"^FN:(.+)$", snapshot.get("contacts", ""), re.M)),
        "Saved screenshots: " + str(len(snapshot["screenshots"])),
        "Owned benchmark question: " + snapshot["question"],
        "Owned benchmark answer: " + snapshot["answer"],
    ])


def unsupported_reason(task: dict, before: dict) -> str | None:
    if task.get("unsupported"):
        return task["unsupported"]
    kind = task["oracle"]["kind"]
    caps = before["capabilities"]
    needed = {"calculator": ["Calculator", "atspi", "swaymsg"], "folder": ["Finder", "swaymsg"],
              "volume": ["pactl"], "volume_exact": ["pactl"], "mute": ["pactl"], "dark": ["gsettings"],
              "app": [task["oracle"].get("value", "")]}.get(kind, [])
    missing = [name for name in needed if not caps.get(name)]
    if missing:
        return "Missing guest capabilities: " + ", ".join(missing)
    if kind in {"volume", "volume_exact", "mute"} and before["volume"] is None:
        return "Guest PulseAudio/PipeWire sink unavailable"
    if kind == "dark" and before["dark"] is None:
        return "Guest GTK theme property unavailable"
    return None


def oracle(task: dict, before: dict, after: dict, terminal: str | None) -> bool:
    """Final-state checks never accept an action result or model success claim."""
    target = task["oracle"]
    kind = target["kind"]
    if kind == "calculator":
        return target["value"] in [s.replace(",", "").strip() for s in after["calculator_text"]]
    if kind == "volume":
        return before["volume"] is not None and after["volume"] is not None and (
            after["volume"] - before["volume"]) * target["direction"] > 0
    if kind == "volume_exact":
        return after["volume"] == target["value"] and before["volume"] != target["value"]
    if kind == "mute":
        return after["muted"] is True and before["muted"] is False
    if kind == "dark":
        return after["dark"] is target["value"] and before["dark"] is not target["value"]
    if kind == "folder":
        return "Finder" in after["apps"] and target["value"] in (after["front_title"] or "")
    if kind == "app":
        return target["value"] in after["apps"] and target["value"] not in before["apps"]
    if kind == "timer":
        timer = after["timer"]
        return (timer is not None and timer["running"] and timer["remaining_seconds"] > 0
                and timer["duration_seconds"] == target["minutes"] * 60)
    if kind == "screenshot":
        return bool(set(after["screenshots"]) - set(before["screenshots"]))
    if kind == "event":
        text = after["calendar"]
        stamp = target["day"].replace("-", "") + "T" + target["time"].replace(":", "") + "00Z"
        if target.get("contact_name"):
            contact = after.get("contacts", "")
            if ("FN:" + target["contact_name"] + "\n" not in contact or
                    "EMAIL:" + target["person"] + "\n" not in contact):
                return False
        return (text != before["calendar"] and "SUMMARY:" + target["title"] + "\n" in text
                and "DTSTART:" + stamp + "\n" in text and "ATTENDEE" not in text
                and "METHOD:" not in text and "X-EVAL-CONTACT:" + target["person"] + "\n" in text)
    if kind == "answer_file":
        return after["answer"].strip().lower() == target["value"].lower()
    if kind == "refusal":
        return terminal == "UNKNOWN" and before == after
    return False


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    return ordered[lower] + (ordered[math.ceil(index)] - ordered[lower]) * (index - lower)


class SubprocessRuntime:
    """Keep one real model loaded in its dependency-isolated Python interpreter."""
    def __init__(self, python: str, args: argparse.Namespace):
        executable = Path(python).absolute()
        # venv executables normally symlink to /usr/bin/python; retain the venv
        # argv path while verifying its containing directory is in the cache.
        if not executable.parent.resolve().is_relative_to("/workspace/cache") or not executable.is_file():
            raise ValueError("--runtime-python must be an existing interpreter under /workspace/cache")
        argv = [str(executable), str(Path(__file__).with_name("runtime.py")),
                "--runtime", "hobby" if args.runtime == "hobbylm" else "local",
                "--base", args.base, "--adapter", args.adapter, "--device", args.device]
        if args.model:
            argv.extend(["--model", args.model])
        self.log = (args.output/"runtime.stderr.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log, bufsize=0)
        self.seed = 1729
        self.memory: dict = {}
        self.hardware: dict = {}
        try:
            ready = self._receive()
            if ready != {"ready": True}:
                raise RuntimeError("Runtime worker did not emit the readiness contract")
        except Exception:
            self.close()
            raise

    def _receive(self) -> dict:
        # Unbuffered byte reads avoid a TextIO buffer masking a ready JSONL line.
        deadline = time.monotonic() + 1800
        line = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while len(line) <= 1024 * 1024:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError("Local runtime worker exceeded 1800 seconds")
                char = os.read(self.process.stdout.fileno(), 1)
                if not char:
                    raise RuntimeError("Local runtime worker exited; inspect runtime.stderr.log")
                if char == b"\n":
                    return json.loads(line)
                line.extend(char)
        raise RuntimeError("Local runtime worker exceeded the JSONL response bound")

    def complete(self, system: str, user: str, max_new: int = 64) -> dict:
        payload = {"system":system, "user":user, "max_new":max_new, "seed":self.seed}
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        self.process.stdin.flush()
        reply = self._receive()
        for key in ("raw", "seconds", "prompt_tokens", "output_tokens"):
            if key not in reply:
                raise RuntimeError("Incomplete real runtime completion")
        for key, value in reply.get("memory", {}).items():
            if value is not None:
                self.memory[key] = max(self.memory.get(key, 0), value)
        self.hardware.update(reply.get("hardware", {}))
        if reply.get("dtype"):
            self.hardware["dtype"] = reply["dtype"]
        return reply

    def close(self):
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.process.stdout:
            self.process.stdout.close()
        self.log.close()


class MemorySampler:
    """Sample this evaluator/model process only; never claim guest/board totals."""
    def __init__(self, pid: int | None = None):
        self.pid = pid or os.getpid()
        self.peak_rss_bytes = 0
        self.peak_hwm_bytes = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self):
        while not self.stop.is_set():
            try:
                for line in Path(f"/proc/{self.pid}/status").read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        self.peak_rss_bytes = max(self.peak_rss_bytes, int(line.split()[1]) * 1024)
                    elif line.startswith("VmHWM:"):
                        self.peak_hwm_bytes = max(self.peak_hwm_bytes, int(line.split()[1]) * 1024)
            except OSError:
                pass
            self.stop.wait(0.05)

    def __enter__(self):
        self.thread.start()
        torch = sys.modules.get("torch")
        if torch is not None and torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join()

    def result(self) -> dict:
        torch = sys.modules.get("torch")
        cuda = torch is not None and torch.cuda.is_available()
        return {"process_peak_rss_bytes_sampled": self.peak_rss_bytes,
                "target_lifetime_peak_rss_bytes": self.peak_hwm_bytes,
                "harness_lifetime_maxrss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated() if cuda else None,
                "cuda_peak_reserved_bytes": torch.cuda.max_memory_reserved() if cuda else None,
                "scope": "sampled target process RSS; allocator VRAM excludes driver/context; no guest or board total",
                "rss_pid": self.pid}


def summarize(rows: list[dict]) -> dict:
    latencies = [step["generation_seconds"] for row in rows for step in row["steps"]
                 if "generation_seconds" in step]
    step_wall = [step["wall_seconds"] for row in rows for step in row["steps"] if "wall_seconds" in step]
    means = sum(latencies) / len(latencies) if latencies else None
    refusals = [row for row in rows if row["oracle_kind"] == "refusal" and row["status"] != "unsupported"]
    supported = [row for row in rows if row["status"] != "unsupported"]
    post_attempted = sum(row.get("task", "").startswith("post-") and bool(row["steps"]) for row in rows)
    return {"tasks": len(rows), "supported": len(supported), "unsupported": len(rows)-len(supported),
            "passed": sum(row["status"] == "passed" for row in rows),
            "post_tasks_attempted":post_attempted, "post_13_attempt_requirement_met":post_attempted >= 13,
            "existing_benchmark_tasks_attempted":sum(row.get("task", "").startswith("cua-") and bool(row["steps"]) for row in rows),
            "success_rate_supported": sum(row["status"] == "passed" for row in rows)/len(supported) if supported else None,
            "success_rate_all": sum(row["status"] == "passed" for row in rows)/len(rows) if rows else None,
            "correct_refusals": sum(row["status"] == "passed" for row in refusals),
            "refusal_tasks": len(refusals),
            "correct_refusal_rate": sum(row["status"] == "passed" for row in refusals)/len(refusals) if refusals else None,
            "incorrect_refusals": sum(row.get("terminal") == "UNKNOWN" and row["oracle_kind"] != "refusal"
                                      and row["status"] != "unsupported" for row in rows),
            "generation_count": len(latencies), "generation_seconds_mean": means,
            "generation_seconds_p50": percentile(latencies, .5), "generation_seconds_p95": percentile(latencies, .95),
            "step_wall_seconds_p50": percentile(step_wall, .5), "step_wall_seconds_p95": percentile(step_wall, .95),
            "task_wall_seconds": sum(row["wall_seconds"] for row in rows),
            "published_reference_comparison": {
                "mlx_replay_median_seconds": .262, "mlx_replay_mean_seconds": .455,
                "mlx_replay_p90_seconds": .724, "mlx_live_mean_seconds": .806,
                "p50_ratio_to_mlx_replay_median": percentile(latencies,.5)/.262 if latencies else None,
                "mean_ratio_to_mlx_live_mean": means/.806 if means is not None else None,
                "caveat": "Published MLX timings are context only, not same-device or same-environment baselines."}}


def hardware_metadata(device: str, remote: bool = False) -> dict:
    cpu = platform.processor()
    try:
        cpu = next((line.split(":",1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")),cpu)
    except OSError:
        pass
    torch = sys.modules.get("torch")
    gpu = (torch.cuda.get_device_name(torch.cuda.current_device())
           if not remote and device.startswith("cuda") and torch is not None and torch.cuda.is_available() else None)
    return {"local_cpu_model":cpu or None, "platform":platform.platform(),
            "gpu_name":gpu, "provider_hardware":"unknown" if remote else "local"}


def compare_reports(current: dict, reference: dict) -> dict:
    """Fail closed rather than silently mix action spaces/modalities/environments."""
    keys = ("seed", "environment", "tasks_sha256", "input_modality", "action_space",
            "max_steps", "max_new_tokens", "guest_fingerprint", "initial_states",
            "task_capabilities", "supported_tasks")
    mismatches = [key for key in keys if key not in current or key not in reference
                  or current[key] != reference[key]]
    if not current.get("initial_states") or any(value is None for value in current.get("initial_states", {}).values()):
        mismatches.append("missing_initial_state_evidence")
    if mismatches:
        return {"valid": False, "mismatched_fields": mismatches,
                "reason": "Not a controlled same-state/seed/environment text-only comparison"}
    a, b = current["generation_seconds_mean"], reference["generation_seconds_mean"]
    return {"valid": True, "reference_runtime": reference["runtime"],
            "generation_mean_ratio": a/b if a is not None and b else None}


async def run_task(backend: OwnedLinuxBackend, runtime: Any, task: dict, directory: Path,
                   max_steps: int, max_new: int, seed: int | None = None) -> dict:
    from cua_agent.loops.hobbylm import SYSTEM_V2, format_user, parse_action
    directory.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    row = {"task": task["id"], "oracle_kind": task["oracle"]["kind"], "steps": [], "terminal": None, "seed":seed}
    trace = directory / "trace.jsonl"
    def emit(record):
        with trace.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    try:
        await backend.reset(task)
        before = await backend.snapshot()
        row["initial_state_sha256"] = hashlib.sha256(
            semantic_state(before).encode()).hexdigest()
        row["initial_capabilities"] = before["capabilities"]
        (directory / "initial.png").write_bytes(await backend.screenshot())
        emit({"type":"initial", "snapshot":before, "task":task, "seed":seed, "environment":ENVIRONMENT})
        reason = unsupported_reason(task, before)
        if reason:
            row.update(status="unsupported", reason=reason)
        else:
            last_action = result = None
            for index in range(max_steps):
                step_started = time.perf_counter()
                state = await backend.observe()
                user = format_user(task["request"], state, last_action, result)
                step = {"type":"step", "index":index, "system":SYSTEM_V2, "user":user}
                try:
                    reply = runtime.complete(SYSTEM_V2, user, max_new=max_new)
                    step.update(raw=reply["raw"], generation_seconds=reply["seconds"],
                                prompt_tokens=reply["prompt_tokens"], output_tokens=reply["output_tokens"])
                    action = parse_action(reply["raw"])
                    result_dict = await backend.action(reply["raw"])
                    step["result"] = result_dict
                    last_action, result = str(action), json.dumps(result_dict, sort_keys=True)
                    if action.name in {"DONE", "UNKNOWN"}:
                        row["terminal"] = action.name
                except Exception as error:
                    step["error"] = f"{type(error).__name__}: {error}"
                    result = step["error"]
                    last_action = step.get("raw")
                    if "raw" not in step:
                        row.update(status="error", error=step["error"])
                # Capture after EVERY attempted action, including refused/invalid ones.
                step["snapshot"] = await backend.snapshot()
                filename = f"step-{index:03d}.png"
                (directory / filename).write_bytes(await backend.screenshot())
                step["screenshot"] = filename
                step["wall_seconds"] = time.perf_counter() - step_started
                row["steps"].append(step)
                emit(step)
                if row["terminal"] or row.get("status") == "error":
                    break
            after = await backend.snapshot()
            if row.get("status") != "error":
                row["status"] = "passed" if oracle(task, before, after, row["terminal"]) else "failed"
            row["final_snapshot"] = after
        (directory / "final.png").write_bytes(await backend.screenshot())
    except Exception as error:
        row.update(status="error", error=f"{type(error).__name__}: {error}")
    row["wall_seconds"] = time.perf_counter() - started
    emit({"type":"final", **row})
    (directory / "result.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")
    return row


def load_tasks(path: Path = TASKS_PATH) -> tuple[dict, str]:
    data = path.read_bytes()
    suite = json.loads(data)
    ids = [task["id"] for task in suite["tasks"]]
    if len(ids) != len(set(ids)) or suite["environment"] != ENVIRONMENT:
        raise ValueError("Invalid frozen task suite")
    return suite, hashlib.sha256(data).hexdigest()


async def run(args: argparse.Namespace) -> dict:
    # Import native/model dependencies only for actual execution, not stdlib tests.
    from cua_sandbox import Sandbox
    suite, digest = load_tasks()
    random.seed(suite["seed"])
    if args.output.exists():
        raise ValueError("Output must be a new directory (never overwrite an eval)")
    args.output.mkdir(parents=True)
    # Local models use the cache-only runtime; the explicit codex variant uses
    # the parent's approved subscription CLI, never an invented baseline.
    load_started = time.perf_counter()
    if args.runtime == "codex":
        from codex_runtime import CodexRuntime
        runtime = CodexRuntime(max_calls=6 * len(suite["tasks"]))
    elif args.runtime_python:
        runtime = SubprocessRuntime(args.runtime_python, args)
    else:
        from runtime import HobbyRuntime, SmallLocalRuntime
        runtime = (HobbyRuntime(args.base, args.adapter, device=args.device) if args.runtime == "hobbylm"
                   else SmallLocalRuntime(args.model, device=args.device))
    load_seconds = time.perf_counter() - load_started
    torch = sys.modules.get("torch")
    if torch is not None:
        torch.manual_seed(suite["seed"])
    try:
        sandbox = await Sandbox.connect(url=validate_endpoint(args.endpoint),
                                        token=os.environ.get(args.token_env), telemetry_enabled=False)
    except Exception:
        if isinstance(runtime, SubprocessRuntime):
            runtime.close()
        raise
    rows = []
    try:
        backend = OwnedLinuxBackend(sandbox, args.ownership_id)
        guest_fingerprint = await backend.guest(mode="fingerprint")
        with MemorySampler(runtime.process.pid if isinstance(runtime, SubprocessRuntime) else None) as memory:
            for index, task in enumerate(suite["tasks"]):
                task_seed = suite["seed"] + index
                random.seed(task_seed)
                if isinstance(runtime, SubprocessRuntime):
                    runtime.seed = task_seed
                if torch is not None:
                    torch.manual_seed(task_seed)
                row = await run_task(backend, runtime, task, args.output/task["id"],
                                     args.max_steps, args.max_new, seed=task_seed)
                rows.append(row)
        summary = {"schema_version":1, "runtime":args.runtime, "device":args.device,
                   "source_revision":os.environ.get("HOBBY_SOURCE_SHA"),
                   "source_files_sha256":{
                       name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                       for name in ("harness.py","runtime.py","codex_runtime.py","artifact_manifest.json")
                   },
                   "seed":suite["seed"], "environment":suite["environment"], "tasks_sha256":digest,
                   "model_load_seconds":load_seconds, "model_paths":{"base":args.base,"adapter":args.adapter,"model":args.model},
                   "input_modality":"identical semantic text only; screenshots are artifacts, never model inputs",
                   "action_space":"OPEN TYPE KEY DARK_MODE FOLDER TIMER SCREENSHOT EVENT DONE UNKNOWN",
                   "max_steps":args.max_steps,"max_new_tokens":args.max_new,
                   "timing_regime":("codex_cli_startup_plus_network_not_model_only" if args.runtime == "codex"
                                    else "local_complete_wall_including_decode_not_model_load"),
                   "seed_caveat":("Provider does not expose seeded decoding" if args.runtime == "codex" else None),
                   "guest_fingerprint":guest_fingerprint,
                   "initial_states":{row["task"]:row.get("initial_state_sha256") for row in rows},
                   "task_capabilities":{row["task"]:row.get("initial_capabilities") for row in rows},
                   "supported_tasks":[row["task"] for row in rows if row["status"] != "unsupported"],
                   "memory":memory.result(), **summarize(rows)}
        summary["hardware"] = hardware_metadata(args.device, remote=args.runtime == "codex")
        if args.runtime == "codex":
            summary["memory"]["remote_model_ram_vram"] = "not measurable from subscription CLI"
            summary["memory"]["scope"] = "local harness only; remote provider model memory is unmeasured"
        if isinstance(runtime, SubprocessRuntime):
            summary["memory"].update(runtime.memory)
            summary["runtime_python"] = args.runtime_python
            summary["hardware"].update(runtime.hardware)
        if args.compare_to:
            summary["controlled_comparison"] = compare_reports(
                summary, json.loads(args.compare_to.read_text()))
        (args.output/"summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        return summary
    finally:
        await sandbox.disconnect()
        if isinstance(runtime, SubprocessRuntime):
            runtime.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="Existing owned guest cua-spacesd URL; no host desktop")
    parser.add_argument("--token-env", default="HOBBYLM_EVAL_TOKEN", help="Environment variable holding guest API token (never recorded)")
    parser.add_argument("--ownership-id", required=True, help="Must match guest ownership marker")
    parser.add_argument("--runtime", choices=("hobbylm", "small-local", "codex"), required=True)
    parser.add_argument("--base", default="/workspace/cache/hobbylm-cua/models/hobbylm-1B-instruct")
    parser.add_argument("--adapter", default="/workspace/cache/hobbylm-cua/models/hobbylm-1B-computer-use")
    parser.add_argument("--model", help="Cached transformers small instruct model for small-local")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--runtime-python", help="Persistent model worker Python under /workspace/cache; avoids SDK/model dependency collision")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--compare-to", type=Path, help="Prior real summary.json; compare only identical state/seed/environment")
    parser.add_argument("--max-steps", type=int, choices=range(1, 7), default=6)
    parser.add_argument("--max-new", type=int, choices=range(1, 65), default=64)
    args = parser.parse_args()
    if args.runtime == "small-local" and not args.model:
        parser.error("--model is required for small-local; no fake baseline exists")
    print(json.dumps(asyncio.run(run(args)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
