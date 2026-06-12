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

    def computed_blend(data):
        from .blend import group_blend
        names = data.get("profiles") or [data.get("a"), data.get("b")]
        profs = [Profile.load(ppath(n)) for n in names if n]
        if len(profs) < 2:
            raise ValueError("pick at least two profiles")
        limit = int(data.get("limit", 30))
        if len(profs) == 2:
            return blend_profiles(profs[0], profs[1], limit=limit)
        return group_blend(profs, limit=limit)

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
        try:
            r = computed_blend(request.get_json(force=True))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if hasattr(r, "users"):                       # pairwise
            return jsonify({"mode": "pair", "people": list(r.users), "score": r.score,
                            "bars": r.breakdown, "shared_artists": r.shared_artists,
                            "pairwise": None, "playlist": r.playlist})
        return jsonify({"mode": "group", "people": r.members, "score": r.score,
                        "bars": r.cohesion, "shared_artists": r.shared_by_all,
                        "pairwise": r.pairwise, "playlist": r.playlist})

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

    @app.post("/api/transfer")
    def transfer():
        data = request.get_json(force=True)
        src, dst = data.get("src"), data.get("dst")
        playlist = (data.get("playlist") or "").strip()
        client_id = (data.get("client_id") or "").strip()
        if not playlist:
            return jsonify({"error": "a source playlist is required"}), 400
        if src == dst:
            return jsonify({"error": "pick two different services"}), 400
        if not client_id:
            return jsonify({"error": "a Spotify client ID is required"}), 400
        from .playlist import apple_to_spotify, spotify_to_apple
        try:
            if src == "spotify" and dst == "apple":
                info = spotify_to_apple(client_id, playlist, new_name=data.get("name") or None)
            elif src == "apple" and dst == "spotify":
                from .apple import default_library_path
                xml = (data.get("xml") or "").strip() or default_library_path()
                if not xml:
                    return jsonify({"error": "no Apple Music library XML found"}), 400
                info = apple_to_spotify(xml, playlist, client_id,
                                        new_name=data.get("name") or None,
                                        public=bool(data.get("public")))
            else:
                return jsonify({"error": "only spotify↔apple transfers are supported"}), 400
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
  .chk { display:inline-block; background:#222834; border:1px solid var(--line);
       border-radius:99px; padding:5px 13px; margin:4px 6px 0 0; font-size:13px; cursor:pointer; }
  .chk input { width:auto; margin-right:7px; vertical-align:middle; }
  .pw { color:var(--mut); font-size:13px; margin:6px 0; }
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
    <label>Pick two or more profiles (3+ makes a group blend)</label>
    <div id="checklist"></div>
    <div style="max-width:160px"><label>Playlist size</label>
      <input id="limit" type="number" value="30"></div>
    <button class="green" onclick="runBlend()">Blend</button>
    <div id="blend-msg" class="err"></div>
  </div>

  <div class="card" id="result" style="display:none">
    <h2>3 · Your blend</h2>
    <div class="score"><span id="score">0</span><small>/100</small></div>
    <div class="bars" id="bars"></div>
    <div id="pairwise"></div>
    <div style="margin-top:10px"><span class="muted" id="shared-label">Shared artists:</span>
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

  <div class="card">
    <h2>Transfer a playlist (Spotify ↔ Apple)</h2>
    <div class="row">
      <div><label>From</label><select id="t-from"><option value="spotify">Spotify</option><option value="apple">Apple Music</option></select></div>
      <div><label>To</label><select id="t-to"><option value="apple">Apple Music</option><option value="spotify">Spotify</option></select></div>
    </div>
    <label>Source playlist — its name (Spotify also accepts a link or ID)</label>
    <input id="t-playlist" placeholder="My Mix">
    <label>New name (optional)</label>
    <input id="t-name" placeholder="leave blank for a default">
    <button class="purple" onclick="transfer()">Transfer</button>
    <div class="muted">uses the Spotify client ID above</div>
    <div id="t-msg" class="err"></div>
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
  const checked = new Set(selectedNames());
  $("checklist").innerHTML = s.profiles.length
    ? s.profiles.map(p=>`<label class="chk"><input type="checkbox" value="${p.name}" ${checked.has(p.name)?"checked":""}> ${p.name} <span class="muted">${p.source}</span></label>`).join("")
    : '<span class="muted">add a profile above first</span>';
  if (s.apple_library) $("apple-xml").placeholder = "auto-detected: " + s.apple_library;
  if (localStorage.getItem("cid")) $("spotify-cid").placeholder = "client ID saved ✓";
}
function selectedNames(){ return [...document.querySelectorAll('#checklist input:checked')].map(c=>c.value); }

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

function blendBody(){ return {profiles:selectedNames(), limit:+$("limit").value}; }

async function runBlend() {
  $("blend-msg").textContent="";
  if (selectedNames().length < 2){ $("blend-msg").textContent="pick at least two profiles"; return; }
  try {
    const r = await api("/api/blend", blendBody());
    $("result").style.display="block";
    $("score").textContent = r.score;
    const b = r.bars;
    $("bars").innerHTML = r.mode==="group"
      ? `artists ${b.artists.toFixed(2)} · genres ${b.genres.toFixed(2)} (mean of pairs)`
      : `artists ${b.artists.toFixed(2)} · genres ${b.genres.toFixed(2)} · tracks ${b.tracks.toFixed(2)}`;
    $("pairwise").innerHTML = r.pairwise
      ? Object.entries(r.pairwise).sort((a,c)=>c[1]-a[1]).map(([k,v])=>`<div class="pw">${v} · ${k}</div>`).join("")
      : "";
    $("shared-label").textContent = r.mode==="group" ? "Liked by everyone:" : "Shared artists:";
    $("shared").innerHTML = (r.shared_artists.slice(0,12).map(a=>`<span>${a}</span>`).join("")) || '<span class="muted">—</span>';
    $("playlist").innerHTML = r.playlist.map(t=>{
       let tag;
       if (t.origin==="shared"||t.origin==="all") tag='<span class="tag heart">'+(t.origin==="all"?"all ♥":"both ♥")+'</span>';
       else if (t.members && t.members>1) tag=`<span class="tag">${t.members} share</span>`;
       else tag=`<span class="tag">→ ${t.origin}</span>`;
       return `<li>${tag}<span>${t.artist} — ${t.title}</span></li>`;
    }).join("");
    $("pl-name").value = $("pl-name").value || `blend: ${r.people.join(" × ")}`;
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

async function transfer() {
  $("t-msg").className=""; $("t-msg").textContent="transferring… (Spotify may open a login tab)";
  try {
    const info = await api("/api/transfer", {src:$("t-from").value, dst:$("t-to").value,
      playlist:$("t-playlist").value, name:$("t-name").value, client_id:clientId()});
    $("t-msg").className="ok";
    $("t-msg").innerHTML = info.url
      ? `transferred ${info.source_tracks} tracks — <a href="${info.url}" target="_blank">open in Spotify</a> (${info.added} added, ${info.missed.length} not found)`
      : `created “${info.playlist}” in Apple Music from ${info.source_tracks} tracks`;
    loadState();
  } catch(e){ $("t-msg").className="err"; $("t-msg").textContent = e.message; }
}

loadState();
</script>
</body>
</html>
"""
