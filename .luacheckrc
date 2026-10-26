-- Lightroom Classic runs Lua 5.1. `import` and `_PLUGIN` are globals Lightroom provides.
std = 'lua51'
read_globals = { 'import', '_PLUGIN', 'MAC_ENV', 'WIN_ENV' }
unused_args = false
exclude_files = { 'src/batchlight_mcp/plugin/BatchLight.lrplugin/dkjson.lua', '.lua51/**', '.venv/**' }
files['tests/lua'] = { std = '+busted', globals = { 'import', 'table' } }
