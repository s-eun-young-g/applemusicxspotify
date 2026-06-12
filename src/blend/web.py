"""Local web GUI — `blend serve` opens a webpage so nobody has to touch the CLI.

Crucially this is a *local* server, not a hosted one: it runs on your machine, so
it can read your Apple Music library directly and do Spotify's loopback OAuth, and
there's no shared 5-user cap and no server holding anyone's tokens. The browser is
just a friendlier front end over the exact same tested engine (profile / blend /
playlist). Flask is an optional extra (`pip install 'blend[web]'`) so the core CLI
stays dependency-free.
"""

from __future__ import annotations

import os
import threading
import webbrowser

from .blend import blend as blend_profiles
from .profile import Profile


def create_app(profiles_dir: str = "."):
    try:
        from flask import Flask, Response, jsonify, request
    except ImportError as exc:  # pragma: no cover - exercised via CLI message
        raise RuntimeError(
            "the web GUI needs Flask — install it with:  pip install 'blend[web]'"
        ) from exc

    app = Flask(__name__)
    app.config["PROFILES_DIR"] = os.path.abspath(profiles_dir)

    def pdir() -> str:
        return app.config["PROFILES_DIR"]

    def ppath(name: str) -> str:
        return os.path.join(pdir(), f"{os.path.basename(name)}.json")

    def load_two(data):
        return Profile.load(ppath(data["a"])), Profile.load(ppath(data["b"]))

    def computed_blend(data):
        a, b = load_two(data)
        return blend_profiles(a, b, limit=int(data.get("limit", 30)))

    @app.get("/")
    def index():
        return Response(_INDEX_HTML, mimetype="text/html")

    @app.get("/api/state")
    def state():
        from .apple import default_library_path
        profiles = []
        for fn in sorted(os.listdir(pdir())):
            if not fn.endswith(".json"):
                continue
            try:
                p = Profile.load(os.path.join(pdir(), fn))
            except Exception:
                continue
            profiles.append({"name": fn[:-5], "source": p.source, "user": p.user,
                             "tracks": len(p.tracks), "artists": len(p.artists)})
        return jsonify({"profiles": profiles,
                        "apple_library": default_library_path()})

    @app.post("/api/profile/apple")
    def profile_apple():
        data = request.get_json(force=True)
        user = (data.get("user") or "").strip()
        if not user:
            return jsonify({"error": "a profile name is required"}), 400
        from .apple import default_library_path, read_library
        path = (data.get("xml") or "").strip() or default_library_path()
        if not path or not os.path.exists(path):
            return jsonify({"error": "no Apple Music library XML found — export one "
                                     "(Music ▸ File ▸ Library ▸ Export Library…) "
                                     "and give its path"}), 400
        p = read_library(path, user)
        p.save(ppath(user))
        return jsonify({"name": user, "source": "apple",
                        "tracks": len(p.tracks), "artists": len(p.artists)})

    @app.post("/api/profile/spotify")
    def profile_spotify():
        data = request.get_json(force=True)
        user = (data.get("user") or "").strip()
        client_id = (data.get("client_id") or "").strip()
        if not user or not client_id:
            return jsonify({"error": "a profile name and Spotify client ID are required"}), 400
        from .spotify import read_spotify
        try:
            p = read_spotify(client_id, user)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400
        p.save(ppath(user))
        return jsonify({"name": user, "source": "spotify",
                        "tracks": len(p.tracks), "artists": len(p.artists)})

    @app.post("/api/blend")
    def do_blend():
        r = computed_blend(request.get_json(force=True))
        return jsonify({"users": r.users, "score": r.score, "breakdown": r.breakdown,
                        "shared_artists": r.shared_artists,
                        "shared_tracks": r.shared_tracks, "playlist": r.playlist})

    @app.post("/api/export/spotify")
    def export_spotify():
        data = request.get_json(force=True)
        client_id = (data.get("client_id") or "").strip()
        if not client_id:
            return jsonify({"error": "a Spotify client ID is required to export"}), 400
        r = computed_blend(data)
        from .playlist import spotify_export
        try:
            info = spotify_export(r, client_id, name=data.get("name"),
                                  public=bool(data.get("public")))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(info)

    @app.post("/api/export/apple")
    def export_apple():
        data = request.get_json(force=True)
        r = computed_blend(data)
        from .playlist import apple_export
        try:
            info = apple_export(r, name=data.get("name"))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(info)

    return app


def serve(host: str = "127.0.0.1", port: int = 8000,
          profiles_dir: str = ".", open_browser: bool = True) -> None:
    app = create_app(profiles_dir)
    url = f"http://{host}:{port}/"
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print(f"blend: web GUI at {url}  (Ctrl-C to stop)")
    app.run(host=host, port=port, threaded=True)


# ---------------------------------------------------------------------------
# Single-page front end (vanilla; no build step).
# ---------------------------------------------------------------------------

_INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>blend</title>
<style>
  :root { --bg:#0f1115; --card:#171a21; --line:#262b36; --fg:#e8eaed; --mut:#9aa3b2;
          --accent:#1db954; --accent2:#8a6cff; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .wrap { max-width:880px; margin:0 auto; padding:28px 20px 80px; }
  h1 { font-size:26px; margin:0 0 2px; }
  h1 .x { color:var(--accent2); }
  .sub { color:var(--mut); margin:0 0 24px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px;
          padding:18px 20px; margin-bottom:18px; }
  h2 { font-size:15px; text-transform:uppercase; letter-spacing:.06em; color:var(--mut);
       margin:0 0 14px; }
  label { display:block; font-size:13px; color:var(--mut); margin:8px 0 4px; }
  input, select { width:100%; padding:9px 11px; background:#0e1015; color:var(--fg);
       border:1px solid var(--line); border-radius:9px; font-size:14px; }
  .row { display:flex; gap:12px; flex-wrap:wrap; }
  .row > div { flex:1; min-width:140px; }
  button { cursor:pointer; border:0; border-radius:9px; padding:10px 16px; font-size:14px;
       font-weight:600; color:#fff; background:#2a3140; margin-top:12px; }
  button.green { background:var(--accent); color:#04210f; }
  button.purple{ background:var(--accent2); }
  button:disabled { opacity:.5; cursor:default; }
  .plist { margin:0; padding:0; list-style:none; }
  .plist li { display:flex; align-items:center; gap:10px; padding:7px 0;
       border-top:1px solid var(--line); }
  .tag { font-size:11px; padding:2px 8px; border-radius:99px; white-space:nowrap;
       background:#2a3140; color:var(--mut); }
  .tag.heart { background:#3a2030; color:#ff86b0; }
  .score { font-size:54px; font-weight:800; line-height:1; }
  .score small { font-size:18px; color:var(--mut); font-weight:500; }
  .bars { display:flex; gap:14px; margin:12px 0 4px; color:var(--mut); font-size:13px; }
  .chips span { display:inline-block; background:#222834; border:1px solid var(--line);
       border-radius:99px; padding:3px 10px; margin:3px 4px 0 0; font-size:13px; }
  .err { color:#ff8a8a; font-size:13px; margin-top:8px; min-height:18px; }
  .ok  { color:var(--accent); font-size:13px; margin-top:8px; }
  .muted { color:var(--mut); font-size:13px; }
  .plus { font-size:12px; color:var(--accent); text-decoration:none; }
  a { color:var(--accent); }
</style>
</head>
<body>
<div class="wrap">
  <h1>blend <span class="x">×</span></h1>
  <p class="sub">Apple Music × Spotify — a blend for the pairs Spotify won't do.</p>

  <div class="card">
    <h2>1 · Profiles</h2>
    <div id="profiles" class="muted">loading…</div>
    <div class="row" style="margin-top:16px">
      <div>
        <label>Add from Apple Music (this Mac)</label>
        <input id="apple-user" placeholder="name, e.g. sofia">
        <input id="apple-xml" placeholder="Library.xml path (blank = auto-detect)" style="margin-top:8px">
        <button class="green" onclick="addApple()">Read Apple library</button>
      </div>
      <div>
        <label>Add from Spotify (opens browser to log in)</label>
        <input id="spotify-user" placeholder="name, e.g. alex">
        <input id="spotify-cid" placeholder="your Spotify client ID" style="margin-top:8px">
        <button class="purple" onclick="addSpotify()">Connect Spotify</button>
      </div>
    </div>
    <div id="add-msg" class="err"></div>
  </div>

  <div class="card">
    <h2>2 · Blend</h2>
    <div class="row">
      <div><label>Profile A</label><select id="sel-a"></select></div>
      <div><label>Profile B</label><select id="sel-b"></select></div>
      <div style="max-width:120px"><label>Playlist size</label><input id="limit" type="number" value="30"></div>
    </div>
    <button class="green" onclick="runBlend()">Blend</button>
    <div id="blend-msg" class="err"></div>
  </div>

  <div class="card" id="result" style="display:none">
    <h2>3 · Your blend</h2>
    <div class="score"><span id="score">0</span><small>/100</small></div>
    <div class="bars" id="bars"></div>
    <div style="margin-top:10px"><span class="muted">Shared artists:</span>
      <div class="chips" id="shared"></div></div>
    <ul class="plist" id="playlist"></ul>

    <h2 style="margin-top:22px">4 · Make it a playlist</h2>
    <label>Playlist name</label>
    <input id="pl-name" placeholder="Our Blend">
    <div class="row">
      <div>
        <button class="green" onclick="exportSpotify()">Create on Spotify</button>
        <div class="muted">uses the client ID above</div>
      </div>
      <div>
        <button onclick="exportApple()">Create in Apple Music</button>
        <div class="muted">adds songs already in your library</div>
      </div>
    </div>
    <div id="export-msg" class="err"></div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
async function api(path, body) {
  const r = await fetch(path, body ? {method:"POST", headers:{"Content-Type":"application/json"},
                                      body: JSON.stringify(body)} : {});
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || "request failed");
  return data;
}
function clientId(){ const c=$("spotify-cid").value.trim(); if(c) localStorage.setItem("cid",c);
  return c || localStorage.getItem("cid") || ""; }

async function loadState() {
  const s = await api("/api/state");
  $("profiles").innerHTML = s.profiles.length
    ? s.profiles.map(p=>`<span class="chips"><span>${p.name} · ${p.source} · ${p.tracks} tracks</span></span>`).join("")
    : '<span class="muted">none yet — add one below</span>';
  for (const sel of [$("sel-a"), $("sel-b")]) {
    const cur = sel.value;
    sel.innerHTML = s.profiles.map(p=>`<option value="${p.name}">${p.name} (${p.source})</option>`).join("");
    if (cur) sel.value = cur;
  }
  if (s.profiles.length>1 && !$("sel-b").value) $("sel-b").selectedIndex=1;
  if (s.apple_library) $("apple-xml").placeholder = "auto-detected: " + s.apple_library;
  if (localStorage.getItem("cid")) $("spotify-cid").placeholder = "client ID saved ✓";
}

async function addApple() {
  $("add-msg").textContent = "reading library…";
  try { const p = await api("/api/profile/apple", {user:$("apple-user").value, xml:$("apple-xml").value});
        $("add-msg").className="ok"; $("add-msg").textContent = `added ${p.name}: ${p.tracks} tracks`; await loadState(); }
  catch(e){ $("add-msg").className="err"; $("add-msg").textContent = e.message; }
}
async function addSpotify() {
  $("add-msg").className=""; $("add-msg").textContent = "opening Spotify login in your browser…";
  try { const p = await api("/api/profile/spotify", {user:$("spotify-user").value, client_id:clientId()});
        $("add-msg").className="ok"; $("add-msg").textContent = `added ${p.name}: ${p.tracks} tracks`; await loadState(); }
  catch(e){ $("add-msg").className="err"; $("add-msg").textContent = e.message; }
}

function blendBody(){ return {a:$("sel-a").value, b:$("sel-b").value, limit:+$("limit").value}; }

async function runBlend() {
  $("blend-msg").textContent="";
  if ($("sel-a").value===$("sel-b").value){ $("blend-msg").textContent="pick two different profiles"; return; }
  try {
    const r = await api("/api/blend", blendBody());
    $("result").style.display="block";
    $("score").textContent = r.score;
    $("bars").innerHTML = `artists ${r.breakdown.artists.toFixed(2)} · genres ${r.breakdown.genres.toFixed(2)} · tracks ${r.breakdown.tracks.toFixed(2)}`;
    $("shared").innerHTML = (r.shared_artists.slice(0,12).map(a=>`<span>${a}</span>`).join("")) || '<span class="muted">—</span>';
    $("playlist").innerHTML = r.playlist.map(t=>{
       const heart = t.origin==="shared";
       const tag = heart ? '<span class="tag heart">both ♥</span>' : `<span class="tag">→ ${t.origin}</span>`;
       return `<li>${tag}<span>${t.artist} — ${t.title}</span></li>`;
    }).join("");
    $("pl-name").value = $("pl-name").value || `blend: ${r.users[0]} × ${r.users[1]}`;
    $("result").scrollIntoView({behavior:"smooth"});
  } catch(e){ $("blend-msg").textContent = e.message; }
}

async function exportSpotify() {
  $("export-msg").className=""; $("export-msg").textContent="creating on Spotify…";
  try { const info = await api("/api/export/spotify", {...blendBody(), name:$("pl-name").value, client_id:clientId()});
        $("export-msg").className="ok";
        $("export-msg").innerHTML = `created (${info.added} added, ${info.missed.length} not found) — <a href="${info.url}" target="_blank">open in Spotify</a>`; }
  catch(e){ $("export-msg").className="err"; $("export-msg").textContent=e.message; }
}
async function exportApple() {
  $("export-msg").className=""; $("export-msg").textContent="creating in Apple Music…";
  try { const info = await api("/api/export/apple", {...blendBody(), name:$("pl-name").value});
        $("export-msg").className="ok"; $("export-msg").textContent = `created “${info.playlist}” (${info.attempted} tracks attempted)`; }
  catch(e){ $("export-msg").className="err"; $("export-msg").textContent=e.message; }
}

loadState();
</script>
</body>
</html>
"""
