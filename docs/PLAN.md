# Lightroom Classic MCP — Plan

> Status: **reviewed**, BIG CHANGE plan review completed 2026-10-26 (see *Plan review log*) · Started 2026-10-24 · Updated 2026-10-26
> §1–2 are product (what and why). §3 is discovery (what's verified). §4–8 are engineering (how).
> Open questions are collected at the end. Edit this file directly; it is the source of truth.

---

## 1. Product

### What it is
An MCP server that lets AI assistants read and edit photos in **Adobe Lightroom Classic**. It targets Claude Desktop first, then Claude Code, Codex and Cursor, and it runs entirely on the user's computer.

It is meant to be more than a generic slider mover: a **domain-aware editing assistant**, starting with two genres at opposite ends of editing, **weddings & engagements** and **interior design**.

### Who it's for
- **Primary user:** a working photographer who shoots weddings, engagements and interiors. They keep Claude Desktop open in a narrow window beside Lightroom and type or dictate requests: *"Soften their faces naturally, warm the background a touch, and mute the neon greens."* / *"Fix the verticals and pull the yellow lamp cast out of the ceiling."*
- **Secondary:** other Lightroom Classic users who download it.
- **Builder:** the developer, running Claude Code or Codex in a terminal next to Lightroom to build and test.

### The two genres
| | Weddings & engagements | Interior design |
|---|---|---|
| What good looks like | Organic flattery, emotion | Geometric precision, color accuracy |
| Hard lighting | Church tungsten, midday sun, golden hour | Warm lamps fighting cool window light |
| Repetitive manual work | Person masks to soften skin; background masks for separation; 15–30 heal clicks per close-up | Upright for verticals; balancing windows against dark corners; neutralizing wall casts; removing outlets and cords |
| Color work | Skin oranges and reds, foliage greens, color grading | Walls that are actually white, wood that stays warm |

### Workflow pillars
| # | Done by hand today | What the MCP does | Feasibility |
|---|---|---|---|
| P1 | **Skin softening:** people mask → facial + body skin, lower Texture/Clarity, lift shadows | Apply an **adaptive skin preset** by UUID, scaled by preset amount: Adobe's built-in *Smooth Facial Skin* (D23) or a preset this package ships. No setup by the photographer | ⚠️ No script call can create a skin mask directly (D10), but presets can carry one (D11, D23). Applies to everyone in the frame. Verify on LrC in M1/M4 |
| P2 | **Background separation:** background mask, −0.2 to −0.4 EV, lower highlights, warm or cool it | Background or subject AI mask with subtle tonal separation | ✅ `background` and `subject` masks work from a plugin (LrC 12+), one photo at a time in Develop |
| P3 | **Blemish and distraction removal:** zoom to 200%, 15–30 heal clicks | v1: nothing (the AI can only point out spots for the photographer to click). Later: native heal spots | ❌ for v1. No API creates heal spots, and the XMP route rewrites originals (D12, D13). Spike in M6 |
| P4 | **Color:** white balance, HSL and color grading by eye | Color analysis computed on the machine (numbers) plus the AI's own vision → exact HSL, grading and calibration values | ✅ the analysis is plain Python; parameter names verified (D16) |
| P5 | **Consistency across a set:** sync settings across 30 shots | `sync_look` from a hero photo to the selection | ⚠️ Global settings copy cleanly; AI masks must be recomputed per photo (`updateAISettings`). Verify in M4 |
| P6 | **Personal taste:** lives in the photographer's head | Style profiles extracted from favorite past edits, exposed as an MCP resource | ✅ plain JSON data |

### Decisions already made
| Decision | Choice | Why |
|---|---|---|
| Target app | Lightroom **Classic** only | Lightroom (cloud, formerly "CC") has no plugin SDK. Its only route is Adobe's cloud API, which needs OAuth and goes through Adobe's servers. |
| What the AI sees by default | Develop settings, photo references (`#3 · 14:32:07`), camera EXIF, previews | Enough for the AI to make good edits. File names are off by default because renamed files often carry client names (plan review, 2026-10-26). |
| Off by default | File names, GPS, people/face names, full file paths | Highest sensitivity. Users opt in through config. |
| Previews | On by default, ≤1024 px, sent only when a tool runs, never saved by the server; README covers client consent | Edit quality depends on the AI seeing the result. The client-consent question is the photographer's to answer, so it's documented. |
| Genre workflows | **Recipe engine:** one `apply_recipe(name, intensity)` tool runs multi-step JSON recipes | One call per logical action (principle 6), and taste stays editable data (principle 8). New genres and personal looks need no code. |
| Primary platform | macOS, verified on the photographer's **own** Mac (a clean machine) | Windows stays supported in CI, but nobody is testing it by hand yet. |
| Package name | Brand **BatchLight**; package and command **`batchlight-mcp`** (import `batchlight_mcp`; registry `io.github.gatonivan/batchlight-mcp`) | The owner's pick (2026-10-26). On 2026-10-26 it was free on PyPI, there was no `batchlight-mcp` repo on GitHub, and no released software used the name. PyPI treats `BatchLight_MCP` and `batchlight-mcp` as the same name, so the lowercase form is used everywhere. Rejected: `darkroom-mcp` (a Darkroom photo app exists, and so does a GitHub repo with that name) and `safelight-mcp` (Safelight is an open-source RAW editor). |
| Public identity | Ivan Gaton · contact `ivan@de-nos.com` (package metadata, SECURITY.md); M0 replaces the Gmail address now in `pyproject.toml` | One dev address everywhere, and the personal Gmail stays out of public metadata (Q13, 2026-10-26). Each published PyPI release keeps its metadata **forever**. |
| Commit email | `ivan@de-nos.com`, set in this repo's git config only (the global config stays as it is) | Owner's choice (2026-10-26). Git history is permanent once pushed, so this address is public for good. GitHub links commits to the account only if the address is added there. |
| Lightroom Classic versions | Target the current release (the photographer runs the latest). `LrSdkVersion = 15.0`; the minimum supported version is the oldest one actually tested | Every masking and preset route needs 13.3+, which the photographer clears. `lightroom_status` reports the exact version in M1. |
| Skin masks | **Fully automated**, no hand-made presets (Q11) | Adobe's built-in adaptive portrait presets, or presets we author and ship, carry the skin mask (D23). |
| Dev test data | A throwaway catalog with **non-client photos** only | Dev builds are buggy and every preview goes to the model provider (§7). |
| Several servers at once | Hub + relay + takeover (§5) | Claude Desktop, Claude Code and the probe all work at the same time, and it survives a crashed or leftover process. |
| Build vs fork | Build our own, in Python | The privacy layer and recipe engine are core design, not add-ons. Read Automaat's issues for lessons; copy nothing without MIT attribution. |
| Keywords, titles, captions | **Off** by default (opt-in) | Person keywords are keywords (D22), and client names end up there too. Keyword search still matches on the machine. |
| Lua unit tests | Standard **Lua 5.1** + busted + luacheck in `.lua51/` (dev-only, never shipped). This replaced LuaJIT in the plan review on 2026-10-26 | Plugin logic can be tested in seconds without reloading Lightroom, on the same language version Lightroom runs. Install commands get confirmed before they run. |
| Face detection library | **Not MediaPipe**; OpenCV + YuNet if P3 ever ships | MediaPipe sends usage metrics to Google (D20), which breaks principle 1. |
| AI attribution | None anywhere (code, docs, commits, PRs) | Owner's rule. |

### Principles
1. **Local only, no telemetry, ever.** The server and plugin talk only over `127.0.0.1`. There are no analytics, crash reports or update checks. (The Premiere MCP shipped with telemetry on by default.)
2. **The user decides what the AI sees.** The only data that leaves the machine is what tools return to the model provider. One privacy policy, enforced in one place, decides what that is.
3. **Non-destructive and reversible.** Edits go only through develop settings, so originals are never touched. Every edit is a named history step, batch edits take a snapshot first, and the server can revert its own edits.
4. **Never trust a silent success.** Every write is read back, and tools report the values Lightroom actually holds. (The Premiere MCP's `apply_lut` failed without reporting an error.)
5. **Errors tell the model what to do next.** Not "Error 500" but *"No photo is selected. Ask the user to select one in Lightroom, then call `get_selected_photos`."* (The Resolve MCP never said why it couldn't connect.)
6. **Tools follow workflows, not SDK calls.** If one logical action takes four SDK calls, it's one tool. Granular wrappers waste context and make models fail midway.
7. **Protect the context window.** Every list takes a `limit` (default 25, max 200), returns summary fields only (id, reference, rating, capture time; the file name only if `share_filenames` is on) and reports how many more exist. Full metadata is returned only on request. A catalog can hold 100,000 photos.
8. **Taste is data, not code.** Genre recipes and the photographer's style live in JSON, not as numbers hard-coded in tool functions.

### Non-goals for v1
- Lightroom (cloud) support.
- Deleting, moving or renaming photos or files, and removing photos from the catalog.
- Export, publish and print, apart from the temporary renders tools need internally.
- Cloud generative fill or inpainting, which would send full-resolution client images off the machine.

---

## 2. User experience

### Privacy policy (what tool results may contain)
| Data | Example | Default | Config key |
|---|---|---|---|
| Develop settings | Exposure +0.70 | **on** (always) | — |
| Photo reference, capture time | `#3 · 14:32:07` (position in the request plus capture time) | **on** (always) | — |
| File name | `Smith-Wedding_0412.NEF` (renamed files often carry client names) | **off** | `share_filenames` |
| Color statistics (computed locally) | "4.2% of pixels clipped; walls +18 toward yellow" | **on** (always) | — |
| Camera EXIF | Sony A7 IV, 35 mm, ISO 400, 1/250, f/2.8 | **on** | `share_exif` |
| Preview images | JPEG of the edited photo, ≤1024 px, never saved | **on** | `share_previews` |
| Full file path | `/Users/<name>/Pictures/…` | **off** | `share_paths` |
| GPS location | 40.71, −74.00 | **off** | `share_location` |
| People / face names | "Maria" | **off** | `share_people` |
| Keywords, title, caption | "client: Acme" | **off** (person keywords follow `share_people`) | `share_keywords` |

> **Client images.** This work means previews show clients' faces and clients' homes, and previews go to the model provider (Anthropic for Claude, OpenAI for Codex). Two things to check that this codebase can't control: the photographer's client contract, and the data settings of the AI account they use (whether chats may be used for training). The README will say this plainly.

Local face detection for blemishes (P3) runs only on the machine and never leaves it. Its results (spot coordinates) are not sent to the AI unless a tool returns them.

### Install (target experience)
1. `uvx batchlight-mcp install-plugin`, which copies the Lightroom plugin to a permanent folder and prints the Plug-in Manager steps. A zip on GitHub Releases is the manual fallback.
2. Add the server to the AI client. There's one snippet per client in the README, including the macOS fix of using an absolute `uvx` path in Claude Desktop.
3. Ask *"check my Lightroom connection"*. `lightroom_status` reports what works and the exact fix for anything that doesn't.
There's no manual preset step. Skin recipes use Adobe's built-in adaptive portrait presets, or presets that `install-plugin` copies into Lightroom's presets folder (D23).

### Tool catalog (draft; domain tools depend on §3 verification)
**Core (v1):**
- `lightroom_status`: versions, connection state, selection count, and fixes.
- `get_selected_photos(limit)`: summary fields, plus EXIF if allowed.
- `get_develop_settings(photo_ids, groups)`: grouped (tone, presence, color, HSL, grading, detail, geometry).
  - **Bounded by default:** only values that differ from Lightroom's defaults; masks and retouch data summarized (count and names) unless asked for; at most 25 photos per call.
- `inspect_photo(photo_id, include_image=true)`: a preview (if allowed) **plus** color statistics computed locally (luminance, clipping, the cast in bright neutrals such as walls or dresses, and channel balance). The AI gets objective numbers alongside its own vision.
  - **Stats cache:** the statistics are cached in memory, keyed by photo plus a hash of its develop settings. Pixels are never cached.
  - `include_image=false` skips rendering when cached stats exist.
  - The image is never skipped on the server's own initiative. A new conversation shares the same server process and may never have seen the photo.
- `apply_develop_settings(photo_ids, settings, mode=absolute|relative)`: read back, one named history step.
- `create_snapshot(name)` (automatic before batches) · `revert_mcp_edit(edit_id)`. Revert restores only values that still hold what BatchLight wrote. Anything the photographer changed since is kept and reported as a conflict (§5, *Edit journal*).

**Domain (v1.x, once verified):**
- `apply_recipe(name, intensity, photo_ids)`: runs a JSON recipe, a list of steps.
  - **Intensity (0–2).** Each value in a recipe declares how intensity applies to it:
    - `delta`: relative values are multiplied;
    - `lerp`: absolute targets move from the photo's current value toward the target;
    - `none`: enums and on/off settings, e.g. Upright mode, are never scaled.

    Preset amounts scale like `delta`. Values are clamped after scaling, and the reply says when that happens.
  - **Failure.** If a step fails, the recipe stops. It reports what ran, per photo and per step, and names the pre-batch snapshot to restore.
  - **Step types.** There are three:
  - `preset`: an adaptive preset by UUID (Adobe's built-in, ours, or the photographer's own), at an amount from 0 to 200. This is how skin masks get in (D11, D23), and it also works on batches, because it doesn't need the Develop module.
  - `settings`: global values, absolute or relative.
  - `mask`: a subject, sky or background AI mask with local values. It runs only on the photo **already open in Develop**, and the plugin checks before and after each masking call that the active photo hasn't changed. A recipe with a `mask` step is refused for batches with an actionable error; batches get masks only through `preset` steps.

  Recipes ship in `recipes/` (`wedding/skin-natural`, `wedding/background-separation`, `interior/verticals-and-windows`, …), and users can add their own.
- `list_recipes()`: names, descriptions and genres, so the AI can choose.
- `list_presets(filter)`: preset names plus UUIDs (bounded by `limit`), so recipes and the AI can refer to the photographer's presets.
- Building blocks, each also callable directly:
- `mask_and_adjust(target=subject|sky|background, adjustments)`: one call bundles go-to-masking, create mask, retry until the values stick, and read back. It works on the photo open in Develop only, with the same active-photo guard. If the photographer switches photos midway, it stops and names the step to undo. `people` is **not** offered (D10); skin goes through a preset.
- `set_color_mix(hsl, grading, calibration)`: grouped arguments, not 30 flat parameters.
- `straighten(mode)`: Upright modes for interiors.
- `apply_preset(name)`: including adaptive presets (the facial-skin mask route).
- `sync_look(from_photo, to=selection, groups)`.
- **Every batch tool is chunked:** `apply_develop_settings`, `apply_recipe` and `sync_look`.
  - Each call stops after about 40 s or N photos, whichever comes first, and returns *done / remaining / `continue_token`*.
  - The AI calls again with the token to carry on, and progress is reported per photo.
  - Resuming is safe because commands are retry-safe (§5).
  - One shared chunking helper implements this; no tool rolls its own.
- Style profiles: `save_style_profile(name, from=selection)` plus the resource `lightroom://styles/{name}`.
- MCP prompts: `wedding-portrait`, `interior-room`.

**Later (v2):** blemish detection → heal spots (P3), and distraction removal for interiors.

---

## 3. Discovery: claims from the two pasted guides
Neither guide's code runs as written. Every claim is tracked here so nothing ships on an unverified claim.
✅ verified · ❌ refuted · ⚠️ partly · ⏳ being researched.

| # | Claim | Status | Evidence / correction |
|---|---|---|---|
| D1 | `from mcp.server.fastmcp import FastMCP, Image` | ❌ | Removed in installed `mcp` 2.3.0 (`mcp/server/fastmcp.py` raises on import). Use `from mcp.server import MCPServer`. |
| D2 | Printing to stderr is enough to keep stdout clean | ⚠️ | An unflushed `print()` reaches stdout when the interpreter exits (tested). Run unbuffered and add a test that every stdout line is valid JSON-RPC. |
| D3 | The bridge needs `aiohttp` | ❌ | Not installed and not needed. An asyncio TCP server inside the server's `lifespan` works alongside stdio (tested). |
| D4 | Tools return `[Image(...), "text"]` | ⚠️ | Return `list[TextContent \| Image]`. Use `format="jpeg"`, since `"jpg"` produces an invalid MIME type. Prefer `data=` over `path=` (path reads block the event loop). |
| D5 | Docstring `Args:` describe parameters to the AI | ❌ | v2 copies the docstring as-is. Parameter descriptions and ranges must use `Annotated[..., Field(ge=, le=, description=)]`, which does reach the schema (tested). |
| D6 | `LrDevelopController.setValue` inside `withWriteAccessDo` | ❌ | Not required by the docs, and reference plugins (Adobe's sample, MIDI2LR) don't do it. It needlessly holds the exclusive catalog lock. Make edits with `photo:applyDevelopSettings` inside a short write gate, and use `LrDevelopController` only for live Develop work (masking). |
| D7 | `requestJpegThumbnail` reflects the latest edits | ⚠️ | It returns the cached preview unless none exists at that size, so it can be stale right after an edit, and a stale image makes the AI over-correct. Verified renders need `LrExportSession` (slower; measure in M1). |
| D8 | Polling with `LrHttp` every 100 ms | ❌ | That wakes Lightroom's shared UI thread constantly. Use long-polling instead: the server holds each request for up to 25 s, the plugin re-polls immediately, and it backs off to 30 s while the server is down. |
| D9 | `LrSdkVersion = 13.0` is current | ❌ | Lightroom Classic is at 15.6 (Sep 2026), so use `LrSdkVersion = 15.0`. Set the minimum to the oldest version we actually test (the photographer runs the latest). |
| D10 | `createNewMask("aiSelection", "people")` plus `local_*` sliders | ⚠️ | `createNewMask` is real (SDK 11+; `background`/`objects`/`people` since 12.0), but **`people` stops at Lightroom's person/part picker and creates nothing**, and no argument selects facial or body skin. Subject, sky and background work. The local names are **`local_Exposure` and `local_Shadows`** (no `2012`); `local_Texture` and `local_Clarity` are right. Masks need the Develop module and act on the active photo only. There's no "mask finished" signal, so retry and read back with `getValue`. |
| D11 | An adaptive preset computes facial/body skin masks via `applyDevelopPreset` | ⚠️ | Works with caveats: `applyDevelopPreset(preset, nil, amount 0–200)`, then `photo:updateAISettings()` in a **second** write gate (LrC 13.3+), then poll until the mask's digest appears. It applies to **all** people in the frame. Find presets by UUID, since names aren't unique. |
| D12 | No SDK call places heal spots | ✅ | Confirmed. The SDK 14.1 Remove-tool API only edits spots that already exist. |
| D13 | Injecting XMP `RetouchAreas`, which Lightroom then reloads | ❌ | There is no documented way to make Lightroom re-read XMP. JPEG, TIFF and DNG keep XMP *inside the original file*, so this rewrites originals (principle 3), and reading it back can wipe catalog-only edits. Writing `RetouchInfo` through `applyDevelopSettings` is unproven: spike it on a virtual copy before anything depends on it. |
| D14 | `catalog:addPhoto(path, photo, 'above')` stacks a derivative | ⚠️ | Real (needs a write gate), but stacking **silently fails** unless the new file is in the same folder as the original. |
| D15 | `PerspectiveUpright = 4` is Vertical | ✅ | 0 Off · 1 Auto · 2 Full · 3 Level · 4 Vertical · 5 Guided. Guided can't be automated, because it needs lines the user draws. |
| D16 | Color grading parameter names (`SplitToning*`, `ColorGradeMidtoneSat`) | ⚠️ | Both spellings are real, for different wheels. Shadows and highlights use `SplitToning{Shadow,Highlight}{Hue,Saturation}`; midtone and global use `ColorGrade{Midtone,Global}{Hue,Sat,Lum}` (note "Sat"). The full list goes in `docs/develop-params.md`. |
| D17 | Preview written to a fixed path in the temp dir | ❌ | A predictable, shared path. Export to a private temp folder (owner-only permissions, one per process), read the file, delete it immediately, and send the bytes over the bridge. |
| D21 | The preview JPEG can be sent to the AI as-is | ❌ | Lightroom embeds EXIF, and GPS unless told not to. Strip metadata in the export settings **and** re-encode in Python with Pillow, dropping all metadata, before anything reaches the AI. |
| D22 | Face names are separate from keywords | ❌ | Named faces become **person keywords**, so sharing keywords would leak people names even with `share_people` off. |
| D18 | Timed-out commands are simply abandoned | ❌ | They stay queued and run later. A stale "apply" would fire the next time Lightroom opens. Commands need an expiry. |
| D19 | Bundle the Adobe SDK docs in `docs/` | ❌ | Adobe's terms treat the docs as part of the SDK and restrict redistributing them. Keep `docs/vendor/` gitignored; the README links to Adobe's download. |
| D23 | *(found locally, not from the guides)* Adobe ships adaptive presets that already carry skin masks | ✅ in Lightroom 9.6 · ⏳ in LrC | The cloud app on the dev Mac has `Settings/Premium/Adaptive - Portrait/` with 12 presets. One is **Adaptive - Smooth Facial Skin** (UUID `798869B7B7234F0EBF221B90067B07FF`: facial-skin mask, Texture −0.2, Clarity −0.1), and *Polished Portrait* adds a body-skin mask. A people-part mask is `crs:What="Mask/Image"` with `MaskSubType="3"` and `MaskSubCategoryID` set to 2 facial skin · 3 iris/pupil · 4 body skin · 5 hair · 6 lips · 7 facial hair · 8 sclera · 9 eyebrows · 11 clothes · 12 teeth. **Verify in M1** that LrC ships the same files and UUIDs, and that `applyDevelopPreset` plus `updateAISettings` computes them. Our own presets reuse the structure with our own values and UUIDs; Adobe's files are read for format only and never copied into the repo. |
| D20 | MediaPipe for face landmarks | ❌ | Python 3.13 wheels exist (Apache-2.0), but **Google's privacy notice says MediaPipe Tasks send usage metrics to Google**, with no documented opt-out. Excluded. Use OpenCV + the YuNet face detector (Apache-2.0 / MIT) instead. |

---

## 4. Developer workflow
- **Prerequisite: Lightroom Classic on the dev Mac.** Check first that the Adobe subscription includes it: the Photography plan does, the Lightroom-only (1 TB) plan doesn't. The Apps tab of the Creative Cloud app shows what's included.
- **`AGENTS.md` at the repo root is the single source of agent instructions.** Codex reads it directly. `CLAUDE.md` just contains `@AGENTS.md`, so the two never drift. It holds:
  - a link to the bridge contract (`contract.json`), not a copy of it;
  - the "new capability checklist":
    1. the action and its error codes in `contract.json`, with an example message;
    2. a Lua handler with the right read/write access;
    3. one MCP tool, whose develop-parameter arguments come from the catalog;
    4. a test against the fake plugin;
    5. a probe command;
  - the privacy-policy rules;
  - the no-stdout rule;
  - the no-AI-attribution rule.
- **SDK reference stays on this machine.** Adobe's Lightroom Classic SDK (Programmer's Guide plus API reference) goes in `docs/vendor/lrc-sdk/`, which is gitignored. Our own `docs/develop-params.md` *is* committed. It's **generated** from `develop_params.json`, and CI fails if the committed copy is stale.
- **Bridge probe:** `uv run batchlight-mcp probe <action> '{json}'` sends a raw command to the plugin, bypassing MCP, so a new Lua handler can be checked before any MCP client is reloaded. It reuses the server's own relay client rather than being a separate script, so it can't drift. It also works while an MCP client is connected (see §5, "More than one server running").

---

## 5. Architecture

### Components
```
Claude Desktop / Claude Code / Codex
        │  stdio · JSON-RPC (MCP)
        ▼
MCP server (Python)
  ├─ tools ──► privacy policy ──► result        (the policy is the only exit to the AI)
  ├─ color analysis (Pillow, local)
  └─ bridge hub: HTTP on 127.0.0.1:<random port>, token required
        ▲  the plugin long-polls GET /poll and answers with POST /result
        │
Lightroom Classic plugin (Lua)
  └─ one worker task ──► SDK (applyDevelopSettings · getDevelopSettings · export · LrDevelopController)
```

### Why the server hosts the connection, not the plugin
The alternative, the plugin listening with `LrSocket`, has documented failures in the plugins that use it:
- `reconnect()` hangs Lightroom (MIDI2LR).
- `onConnected` doesn't fire on macOS in Lightroom Classic 15.5 (Automaat).
- Ports stay bound after *Reload*.
- Several MCPs reuse MIDI2LR's fixed ports and collide with it.

Long-polling with `LrHttp` avoids all of these; lightroom-py and LrGeniusAI switched to it for the same reasons.

### Bridge protocol (v1)
- **Discovery file:** `~/Library/Application Support/batchlight-mcp/bridge.json` (macOS) or `%APPDATA%\batchlight-mcp\bridge.json` (Windows), owner-only permissions. It holds `{port, token, pid, protocol, server_version}`. The OS assigns the port, so it can't collide with anything. The plugin re-reads the file whenever a request fails.
- **Auth:**
  - Each hub generates a fresh random token. Requests send it as `Authorization: Bearer …`, and it is compared in constant time.
  - Requests with an `Origin` header (browsers) are rejected.
  - Requests whose `Host` isn't `127.0.0.1:<port>` are rejected (DNS rebinding).
  - JSON only, with an explicit 8 MB body-size cap. A result over the cap is a command error with a fix ("ask for fewer photos or groups"); the plugin never treats it as "server down".

  This mirrors the protections the MCP SDK uses on its own HTTP transport.
- **Envelope:** `{id, action, params, expires_at, protocol}`.
- **Retry-safe commands:**
  - `expires_at` only stops a command from *starting*. A command the plugin already started always reports its result (fixes D18).
  - The `id` is an idempotency key. The plugin caches the last ~100 results by id and answers a repeat delivery from that cache instead of running the command again.
  - A result that arrives after the tool call gave up is still written to the edit journal and mentioned in that server's next reply.
  - A write that times out never claims it failed. The error says *"it may have been applied; call `get_develop_settings` before retrying."*
  - MCP cancellation is passed on to commands that haven't started yet.
- **Endpoints:**
  - `GET /poll`: held for up to 25 s.
  - `POST /result`
  - `POST /hello`: plugin and Lightroom versions, for `lightroom_status` and the version-mismatch warning.
  - `POST /submit`: the relay (next section).
- **Large payloads:** previews travel as base64 inside the JSON, about 150–300 KB at 1024 px.
- **One contract file.** `contract.json` holds:
  - the message formats;
  - the action names;
  - the error codes, with safe message templates;
  - the protocol version;
  - example messages.

  `protocol.py`, `Protocol.lua` and the FakePlugin are each tested against the same examples (pytest and busted both load it). AGENTS.md links to it.
- **Request checks.** The Host, Origin, token and body-size checks are our own small middleware, with tests. We don't reuse `mcp.server.transport_security`, because a maintainer's TODO in that module (mcp 2.3.0) questions whether it should exist at all.

### Edit journal
- **The hub owns it.** The journal is a JSONL file in the state folder, next to `bridge.json`. Only the lock holder writes it, so there's exactly one writer, and a new hub after a handover carries on with the same file.
- **Keyed by catalog.** Entries are keyed by a catalog identifier the plugin reports in `/hello`, so a revert can never hit a photo in a different catalog.
- **What an entry records:** the edit id, catalog, photo, history-step name, and each value's before and after.
- **How revert works:** it restores only the values that still hold BatchLight's "after". Values the photographer changed since are kept and reported as conflicts. Masks added by presets are reverted by restoring the earlier `MaskGroupBasedCorrections`; verify that in M3.

### More than one server running (decided: hub + relay + takeover)
Each AI client starts its own server process: Claude Desktop, Claude Code, the dev probe, and sometimes a leftover process from a restart. Only one can host the bridge. Recommended design:
- Whoever holds an **exclusive OS file lock** (`bridge.lock`) is the hub. The OS releases the lock if that process dies.
- Every other instance, including the probe, **relays** its commands through the hub's `/submit`.
- If the hub disappears, the next instance to notice takes the lock and becomes the hub. The plugin finds the new hub through the discovery file.

**Handover, specified (plan review, 2026-10-26):**
- **Fast shutdown.** uvicorn runs inside our own lifecycle:
  - its signal capture is turned off;
  - its graceful shutdown times out after about 1 s;
  - held `/poll` requests return straight away with "hub closing".

  On shutdown the hub first deletes `bridge.json` and then releases `bridge.lock`, so no relay reads a stale port.
- **Atomic discovery.** A new hub writes `bridge.json` to a temp file and renames it into place, so a reader never sees half a file.
- **Quick reconnect.** While disconnected, the plugin re-reads `bridge.json` about once a second for the first minute, then backs off to 30 s.
- **Stale plugin loops.** Every poll carries the plugin's generation token. The hub rejects polls from an older generation with 409, so a loop left over from a Reload exits instead of swallowing a command.
- **Versions.** Relays and the hub exchange protocol versions on their first request. A mismatch is an actionable error ("restart Claude Desktop to update"), never a silent misread.
- **In-flight relays.** If the hub dies with a relay's command in flight, the relay gets a "hub changed" error. Retry-safe ids (above) make it safe to resend.

### Plugin
- **Lifecycle:**
  - `LrForceInitPlugin`, so the bridge starts with Lightroom.
  - One worker started with `postAsyncTaskWithContext` (a plain `startAsyncTask` from init was seen being cancelled).
  - **Fast lane.** Read-only status actions (ping, hello, status) are answered directly in the poll loop and never queued behind a running batch, so "is it connected?" never looks like "it's broken."
  - A **run flag plus a generation token stored in plugin prefs**. After a *Reload*, the old loop sees it's been superseded and exits. Without this, reloads leave duplicate loops running.
  - `LrShutdownApp` returns `{LrShutdownFunction = …}` and calls `done()` (Automaat got this wrong and showed a dialog on every quit).
- **Errors:** every handler runs inside `LrTasks.pcall`, because plain `pcall` breaks on calls that yield. A handler failure becomes an actionable error, never a crash.
- **Edits:**
  - `applyDevelopSettings` runs inside `withWriteAccessDo` with `timeoutParams`, and the lock is held only for the write itself.
  - Lookups happen outside the lock. (Automaat held it for 45 s on a 123k-photo catalog.)
  - Large batches are written in chunks (see *Every batch tool is chunked*, §2).
- **Catalog reads in bulk.**
  - Metadata for many photos comes from one `catalog:batchGetRawMetadata` / `batchGetFormattedMetadata` call, never one call per photo per field.
  - The preset UUID index is built once per command, not once per recipe step.
  - Values are read back after the commit, never inside it, where the old values are still visible.
- **Parameters: `develop_params.json` is the only source** (plan review, 2026-10-26).
  - Each entry holds the name, range, step size, group, description and the processing versions that support it.
  - Tool argument schemas (`Field` limits and descriptions) and `docs/develop-params.md` are generated from it.
  - Lua holds no ranges. Python validates and clamps; Lightroom's own clamping shows up in the read-back.
  - `LrDevelopController.getRange` is used only by `probe verify-params`, which checks the JSON against a real Lightroom (M1, and after every Lightroom update).
- **Read-back rule:**
  - A value counts as applied if Lightroom holds it to within the parameter's step size.
  - Replies show *requested → clamped → what Lightroom holds*.
  - A slider the photo's processing version doesn't support is rejected before anything is sent.
- **Lua environment:** Lua 5.1, with no `print` and no `package` library. Plugin files load with `require`, and JSON uses `dkjson` (MIT; rxi/json.lua drops nulls).

### Previews
- **Default: export with `LrExportSession` into a private temp folder.**
  - 1024 px long edge, sRGB, JPEG quality ~80.
  - Location, face and EXIF metadata removed.
  - Not re-imported into the catalog.
  - The file is read, then deleted.
- **Python re-encodes** the JPEG with Pillow, stripping all metadata, and computes the color statistics from the same pixels.
- **Fallback:** `requestJpegThumbnail` is faster but may be stale, so when it's used the result is labelled *"may not show the latest edit"*.
- **Check in M1:** measure export latency on the photographer's Mac, and revisit if it's too slow.

### How the privacy policy is enforced
- **`policy.py` covers every way out, not just tool results.** One wrapper applies it to:
  - tool results;
  - error messages;
  - progress and log notifications;
  - resources (style profiles);
  - prompts.

  Nothing is registered with `MCPServer` except through that wrapper.
- **Deny by default.** Every field a tool returns carries a data class: filename, exif, location, people, keywords, path or preview. A field with no class is dropped, and a test fails on it. The policy drops every class that isn't enabled. Person keywords always count as `people` (D22).
- **Errors come from codes.** The plugin returns an error code plus safe parameters, and Python builds the message the AI sees. Raw Lua error text, which includes file paths and so the macOS username, goes only to the local stderr log.
- **Who filters:** the server process that *submitted* the command applies its own client's policy. The hub never filters for a relay, because each client can configure different sharing.
- The plugin also collects only the fields it was asked for, so less data moves in the first place.
- **Config:** env vars in each client's MCP config block (`BATCHLIGHT_SHARE_LOCATION=1` …). They map 1:1 to `.mcpb` `user_config` later.

### Known traps
- **uvicorn logs to stdout by default** (its access log goes to `sys.stdout`). Run it with `access_log=False, log_config=None`; the stdout test (§7) catches regressions.
- **uvicorn takes over SIGINT and SIGTERM, and by default waits forever for open connections when shutting down** (`Server.capture_signals` and `timeout_graceful_shutdown=None` in uvicorn 0.54). Long-polls would hold the lock open, so see *Handover* above.
- **Tools that touch the bridge must be `async def`,** because sync tools run on a worker thread.
- **Keep blocking work off the hub's event loop.** Pillow decoding, re-encoding and statistics, plus journal file writes, run in `anyio.to_thread`. Otherwise they stall held polls and relay requests.
- **Configure logging before constructing `MCPServer`,** because the SDK calls `basicConfig` itself.
- **Use `ToolError` for messages the AI should see.** Any other exception reaches the AI as just "Error executing tool X".

## 6. Code structure
```
<repo root>/                        git root (moved up from mcp-server/)
├── AGENTS.md · CLAUDE.md (@AGENTS.md) · README.md · LICENSE · SECURITY.md · CHANGELOG.md · THIRD_PARTY_NOTICES
├── pyproject.toml · uv.lock
├── docs/            PLAN.md · develop-params.md · vendor/ (gitignored SDK)
├── src/batchlight_mcp/
│   ├── __main__.py      CLI: serve (default) · probe · install-plugin
│   ├── server.py        MCPServer, lifespan, tool registration
│   ├── tools/           status · photos · develop · inspect · recipes
│   ├── bridge/          hub (HTTP) · relay · protocol (envelope, expiry, idempotency) · discovery (file + lock) · journal
│   ├── contract.json    bridge contract: messages, actions, error codes, examples (also read by the Lua tests)
│   ├── policy.py        privacy filter
│   ├── analysis.py      color statistics (Pillow only)
│   ├── params.py        develop-parameter catalog: validate, clamp, map
│   ├── data/            develop_params.json · recipes/**/*.json · presets/*.xmp (our own adaptive presets)
│   └── plugin/BatchLight.lrplugin/
│         Info.lua · Init.lua · Shutdown.lua · ShutdownApp.lua
│         Bridge.lua (poll loop) · Handlers.lua · Protocol.lua (pure) · dkjson.lua
└── tests/           python/ · lua/ (busted, pure modules only)
```
- **The plugin lives inside the Python package** so it ships in the wheel for `install-plugin`. During development, Plug-in Manager points straight at this folder, so a Lua edit plus *Reload* takes effect immediately.
- **`starlette` + `uvicorn` host the bridge**, so there's no hand-written HTTP parsing. Both are already installed with `mcp`; they become explicit dependencies because we import them directly.
- **No numpy.** Pillow is enough for histograms and channel means, which keeps `uvx` installs light.

## 7. Testing
**Unit tests (Python):**
- Protocol: expiry, late results, token comparison.
- Discovery: the lock, takeover, file permissions.
- Policy: every data class on and off; person keywords stay hidden while `share_people` is off.
- **Planted-marker test (privacy):**
  - One unique marker string is planted in every sensitive field of the fake catalog: paths containing a username, GPS, person keywords, titles and captions, client-style file names, and raw Lua error text.
  - Every tool, resource, prompt and failure path then runs with default settings, and the marker must never appear in any result, structured result, error, notification or resource.
  - Every preview is decoded and must carry no metadata segments (APP1, APP13, COM).
  - A registration test checks that every registered tool, resource and prompt goes through the policy wrapper, so new ones are covered automatically.
- Params: names, clamping, process versions, and the step-size read-back rule. The generated tool schemas and `develop-params.md` match the JSON.
- Contract: `protocol.py` round-trips every example message in `contract.json`, and every error code has a message template.
- Journal: revert with no conflicts, with some (the photographer's changed values are kept), and across a catalog switch (refused).
- Analysis: synthetic images with a known clipping percentage or cast.
- Recipes:
  - every shipped recipe passes schema validation;
  - `delta`, `lerp` and `none` scale correctly at intensities 0, 0.5, 1 and 2, with clamping reported;
  - a step failing midway stops the recipe and reports per photo and per step.

**Test isolation (they must never reach the real Lightroom):**
- The SDK's in-process `Client(server)` runs the server's real lifespan (`mcp/client/client.py:118`), so tests would otherwise take the real lock and write the real `bridge.json`.
- **Separate state folder.** The state folder is configurable with `BATCHLIGHT_STATE_DIR`. An autouse fixture in the root `conftest.py` points it, along with HOME and APPDATA, at a temp folder for every test.
- **Test hubs are refused.** Hubs started by tests write `"test": true` into `bridge.json`, and the real plugin refuses to poll them.
- **Fail fast.** The suite aborts if it ever resolves the real state folder.

**Integration tests (no Lightroom needed):**
- A `FakePlugin` long-polls the real hub and runs handlers against an in-memory fake catalog.
- **The fake is realistic, not forgiving.** It has switches for:
  - rounding values to the parameter's step;
  - delayed AI-mask completion;
  - catalog write-lock timeouts;
  - stale thumbnails;
  - "not in the Develop module" errors;
  - the active photo changing mid-mask.

  M1's `probe --record` calibrates these against real behavior.
- Every tool runs end to end through `Client(server)`, in both protocol modes ("auto" and "legacy").
- On a fake clock:
  - a command cancelled midway;
  - one command delivered twice (answered from the cache, applied once);
  - an old and a new plugin loop polling at once (the old one gets 409);
  - quit → the lock is released and `bridge.json` removed within 2 s;
  - an oversized result (a command error, not "server down");
  - a relay and hub on different protocol versions;
  - a chunked batch resumed with its `continue_token`, including after a hub handover;
  - `lightroom_status` answering while a long batch is running (the fast lane);
  - the stats cache missing after any develop-settings change.
- Failure paths:
  - the plugin isn't connected;
  - the plugin drops out mid-command;
  - a command expires;
  - a result arrives late;
  - the token is wrong;
  - a request carries an `Origin` header;
  - the body is oversized;
  - a second instance relays through the hub;
  - the hub dies and another instance takes over.

**Stdout test:** spawn the real server as a subprocess, then initialize, list tools and call a tool. Every stdout line must be valid JSON-RPC.

**Lua:**
- **Pure cores, thin shells.** Every decision the plugin makes lives in pure modules: the poll-loop backoff schedule, generation checks, expiry, the retry cache, error-code mapping and parameter mapping. busted tests them against the `contract.json` examples, with the `Lr*` imports stubbed. `Bridge.lua` and `Handlers.lua` stay thin shells around `LrHttp` and the catalog calls.
- **Runs on real Lua 5.1, not LuaJIT** (plan review, 2026-10-26). LuaJIT accepts `goto`, newer string escapes and the `bit`/`jit` libraries, all of which Lightroom's Lua 5.1 rejects.
  - The test environment is standard Lua 5.1, built with `hererocks` into `.lua51/` at the repo root (gitignored), with busted and luacheck installed there.
  - CI and a pre-commit check run `luac -p` (Lua 5.1) and `luacheck --std lua51` on every plugin file.
- **Fidelity trap:** busted loads Penlight, which adds `table.unpack` even on Lua 5.1. The spec helper removes Lua 5.2+ additions before loading plugin modules, and a test proves they're gone.

**Real-Lightroom self-test:** `probe selftest` runs apply → read back → export → revert on a dedicated photo in the throwaway catalog, and refuses to run in any other catalog. It replaces most of the manual checklist below. `probe --record` (M1) captures real exchanges, scrubbed of metadata and with no previews saved, to calibrate the fake.

**Test data (manual and dev testing):**
- Use a **throwaway catalog** (e.g. `~/Pictures/batchlight-dev/`), never the photographer's working catalog.
- Fill it with **non-client photos only**: your own shots, or freely licensed samples. During M1–M4 the code is unfinished and every preview it takes goes to the model provider.
- Cover the cases the tools care about: a portrait with one face and one with several (skin masks), an interior with verticals and mixed light, and RAW, DNG, JPEG and TIFF files (D13 says JPEG/TIFF/DNG carry XMP inside the original).
- Before the first test on the photographer's real catalog (M5), back that catalog up.

**Manual checklist on a real Lightroom, every release (what `probe selftest` can't cover):**
- install from a clean state;
- *Reload* leaves no duplicate loops;
- quitting shows no shutdown dialog;
- two AI clients at once, including quitting the hub's client mid-command;
- no deadlock alongside another plugin;
- clicking another photo during a mask step stops it cleanly.

**CI:** macOS, Windows and Linux on Python 3.13, plus a stdio smoke test of the built wheel.

## 8. Distribution
- **PyPI** through GitHub Actions trusted publishing (OIDC, no stored tokens). Users run `uvx batchlight-mcp@X.Y.Z`.
- **The plugin ships inside the wheel**, with an `install-plugin` command, so server and plugin versions move together and the server warns on a mismatch. A zip on GitHub Releases is the fallback.
- **MCP Registry** listing as `io.github.gatonivan/batchlight-mcp`, using the `mcp-name` marker in the README.
- **MIT license**, plus `THIRD_PARTY_NOTICES` for the bundled Lua JSON library.
- `README` (per-client snippets, security model, troubleshooting, uninstall), `SECURITY.md` and `CHANGELOG.md`.
- **CI** on macOS, Windows and Linux with Python 3.13, including a stdio smoke test on the built wheel.
- **Later:** a one-click `.mcpb` bundle for Claude Desktop (uv type) and Adobe Exchange. There's no in-plugin update check, because principle 1 rules it out; `lightroom_status` compares the plugin and server versions locally instead.

## 9. Milestones
| # | Milestone | Done when |
|---|---|---|
| M0 | **Repo hygiene:**<br>• move the git root up from `mcp-server/`<br>• rename the package to `batchlight-mcp`<br>• set the repo-local git `user.email` to `ivan@de-nos.com`<br>• replace the Gmail address in `pyproject.toml`<br>• remove the stdout `print`<br>• add LICENSE (MIT) and AGENTS.md / CLAUDE.md<br>• gitignore `docs/vendor/` and `.lua51/` | The repo is ready to push and the first commit is clean, with no AI attribution |
| M1 | **"It connects"** (the original goal): hub + plugin long-poll + `lightroom_status` + `probe ping` | Claude reports the Lightroom version and selection count. Also measured: the long-poll's effect on Lightroom's UI, export-preview latency, Reload supersession, and Claude Desktop's tool-call timeout (it sets the chunk budget). Also built: `probe verify-params` and `probe --record`. Also checked: LrC ships the D23 presets with the same UUIDs |
| M2 | Read tools + privacy policy + color analysis | `inspect_photo` returns a stripped preview plus color statistics; the policy tests pass |
| M3 | Write tools with read-back, named history steps, snapshot and revert journal | Edit-and-verify works on a real photo, and revert restores it exactly |
| M4 | Recipe engine + domain building blocks (presets, masks, HSL, Upright, sync, style profiles) | Skin preset route (D11, D23) and background masks proven on a real Lightroom, with Adobe's built-in preset and with our own shipped one. That includes whether preset *amount* scales mask values, and whether Lightroom sees newly installed preset files without a restart. First wedding and interior recipes tried by the photographer |
| M5 | Packaging: `install-plugin` (plugin + our presets), README, CI, PyPI, MCP Registry | A clean install on the photographer's Mac from a published version |
| M6 | v2: blemish pipeline | A spike shows `RetouchInfo` writes work on a **virtual copy**; detection with OpenCV + YuNet. If the spike fails, the AI only points out spots |

## 10. Prior art
| Project | Stack | Notes |
|---|---|---|
| Automaat/lightroom-mcp | Node/TS · two LrSocket ports | The most mature: ~50 tools, ~156★, MIT. Read its issues before M1; most of the traps in §5 come from them. |
| drshy-org/lightroom-py | Python · LrHttp long-poll | 15 tools, v0.6. The closest to this bridge design. |
| Symphon-y, 4xiomdev, varunkumar | various | Small; some have no license. |

What would be different here:
- a privacy policy layer;
- domain recipes stored as data;
- every edit read back and verified;
- previews honestly labelled when they might be stale;
- a correct reload and shutdown lifecycle;
- no port collisions.

Decision: build our own (see *Decisions already made*).

---

## Plan review log (2026-10-26, BIG CHANGE mode)
An independent reviewer read the plan, and its SDK and uvicorn claims were checked against the installed packages. All 16 issues were decided, each with the recommended option, and the changes are folded into the sections above.

| # | Section | Issue | Decision |
|---|---|---|---|
| 1 | Architecture | Late or duplicate edits applied twice | Retry-safe ids, plugin result cache, late results journaled (§5) |
| 2 | Architecture | Masks act on whatever photo is active | Photo open in Develop only, plus an active-photo guard; batches use preset masks (§2) |
| 3 | Architecture | Hub handover unspecified; uvicorn blocks shutdown | Handover specified: 1 s shutdown, atomic discovery, stale-loop 409, version check (§5) |
| 4 | Architecture | Channels bypass the privacy filter; file names leak | Every channel filtered, deny by default, errors from codes, `share_filenames` off (§2, §5) |
| 5 | Code quality | Parameter knowledge in four places | `develop_params.json` is the only source; step-size read-back rule (§5) |
| 6 | Code quality | Bridge contract written four times | `contract.json` with shared examples; our own request checks (§5) |
| 7 | Code quality | Intensity breaks absolute values and enums | Per-value `delta` / `lerp` / `none`; stop and report on failure (§2) |
| 8 | Code quality | Revert journal has no owner | Hub-owned JSONL keyed by catalog; conflict-aware revert (§5) |
| 9 | Tests | Tests can reach the real Lightroom | Temp state folder, test hubs refused, fail fast (§7) |
| 10 | Tests | Lua untested; fake too forgiving | Pure Lua cores, realistic fake, `probe selftest`, `probe --record` (§7) |
| 11 | Tests | LuaJIT isn't Lua 5.1 | Standard Lua 5.1 in `.lua51/`, plus `luac -p` and luacheck (§7) |
| 12 | Tests | No proof every channel is filtered | Planted-marker test plus a registration test (§7) |
| 13 | Performance | Long batches outrun client timeouts | Chunks with `continue_token`, plus a fast lane for status (§2, §5) |
| 14 | Performance | `get_develop_settings` unbounded | Non-default values only, groups, max 25, 8 MB cap (§2, §5) |
| 15 | Performance | Full export on every inspect | Stats cache (never pixels), `include_image` (§2) |
| 16 | Performance | N+1 catalog reads; event-loop stalls | Batch reads, preset index once, thread offload (§5) |

## Open questions
- ~~Q1 keywords · Q2 previews · Q3 genre tools · Q4 commit email · Q5 machine · Q8 several servers · Q9 build vs fork · Q10 Lua tests~~: resolved 2026-10-24, see *Decisions already made*.
- ~~Q6 package name · Q7 photographer's LrC version · Q11 hand-made presets · Q12 name check · Q13 public contact~~: resolved 2026-10-26 (`batchlight-mcp` · the latest · no, automate it · checked · `ivan@de-nos.com`), see *Decisions already made*.
