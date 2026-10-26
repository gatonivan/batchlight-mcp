# BatchLight: agent instructions

BatchLight is an MCP server (Python) plus a Lightroom Classic plugin (Lua 5.1) that lets AI assistants read and edit photos, locally and privacy-first.

**The plan of record is [docs/PLAN.md](docs/PLAN.md).** Read it before substantive work. Its decisions table and plan review log override anything a tutorial, snippet or older note says.

**Status:** M1 in progress. The bridge, plugin loop, `lightroom_status` and `probe` exist and are tested against a fake plugin; the real-Lightroom check is next.

## Commands
| What | Command |
|---|---|
| Set up the Python environment | `uv sync` |
| Run the server (stdio) | `uv run batchlight-mcp` |
| Python tests | `uv run pytest` |
| Talk to the plugin directly | `uv run batchlight-mcp probe status` (or `ping`, `hub-status`) |
| Lua tests | `.lua51/bin/busted` (config in `.busted`) |
| Lua 5.1 syntax check | `.lua51/bin/luac -p <file.lua>` |
| Lua lint | `.lua51/bin/luacheck .` (config in `.luacheckrc`) |

`.lua51/` is gitignored. To rebuild it, run `uvx hererocks .lua51 --lua 5.1 --luarocks latest`, then `.lua51/bin/luarocks install busted` and `.lua51/bin/luarocks install luacheck`.

## Rules
1. **stdout belongs to MCP.**
   - Server code never prints or writes to stdout; logs go to stderr.
   - A test spawns the server and checks that every stdout line is valid JSON-RPC.
2. **One privacy gate.**
   - Everything that reaches the AI goes through `policy.py`: tool results, errors, progress and log notifications, resources and prompts.
   - Every returned field carries a data class, and untagged fields are dropped.
   - Error messages are built from contract error codes, never from raw Lua error text, which contains file paths.
   - File names, full paths, GPS, people and keywords are **off** by default.
3. **No telemetry, ever.**
   - No analytics, crash reports or update checks.
   - The server and plugin talk only over `127.0.0.1`.
   - Don't add a dependency that phones home (e.g. MediaPipe; PLAN.md D20).
4. **Non-destructive.**
   - Edits go only through develop settings, and never write XMP into original files.
   - Every write is read back and recorded in the edit journal.
5. **Lightroom's Lua is 5.1.**
   - No `goto`, `table.unpack`, `print` or `package` library.
   - Run `luac -p` and luacheck before committing Lua.
6. **Tests never touch the real Lightroom.**
   - Tests use a temporary state folder (`BATCHLIGHT_STATE_DIR`).
   - Test hubs are marked so the real plugin refuses them.
7. **Real-Lightroom testing uses a throwaway catalog with non-client photos only.** Previews from dev builds go to the model provider.
8. **Adobe's material stays out of the repo.**
   - The Lightroom Classic SDK docs live in `docs/vendor/`, which is gitignored.
   - Adobe's built-in preset files may be read for their format, but never copied.
9. **Commits** use conventional commits, with an imperative subject under 72 characters. **No AI attribution anywhere:** no `Co-Authored-By` trailers or "Generated with" lines in commits, PRs, code or docs.

## Bridge contract
The Python–Lua bridge contract is `src/batchlight_mcp/plugin/BatchLight.lrplugin/contract.json`. It sits inside the plugin folder so both sides read the same file at runtime. It holds the messages, actions, error codes, protocol version and example messages. Link to it; never restate it here or in code comments.

## New capability checklist
1. Add the action and its error codes to `contract.json`, with an example message.
2. Write a Lua handler with the right read or write access. Keep its logic in a pure module that busted can test.
3. Add one MCP tool. Develop-parameter arguments come from `develop_params.json`, never hand-written ranges.
4. Add a test against the fake plugin, including at least one failure path.
5. Add a `probe` command to try it against a real Lightroom.
