-- The bridge loop: find the hub through bridge.json, say hello, then long-poll for
-- commands. Decisions live in Core.lua; this file only does the I/O.

local LrApplication = import 'LrApplication'
local LrDate = import 'LrDate'
local LrFileUtils = import 'LrFileUtils'
local LrHttp = import 'LrHttp'
local LrPathUtils = import 'LrPathUtils'
local LrPrefs = import 'LrPrefs'
local LrTasks = import 'LrTasks'

local json = require 'dkjson'
local Core = require 'Core'
local Handlers = require 'Handlers'
local Log = require 'Log'
local Paths = require 'Paths'

local Bridge = {}

local contract = Core.decodeContract(LrFileUtils.readFile(LrPathUtils.child(_PLUGIN.path, 'contract.json')))

local current  -- the running loop's state, read by the Status menu item

function Bridge.describe()
  return Core.describe(current)
end

local function pluginVersion()
  local ok, info = pcall(require, 'Info')
  if ok and type(info) == 'table' and type(info.VERSION) == 'table' and info.VERSION.display then
    return info.VERSION.display
  end
  return 'unknown'
end

local function discoveryPath()
  return LrPathUtils.child(Paths.stateDir(), 'bridge.json')
end

local function readDiscovery(path)
  if not LrFileUtils.exists(path) then return nil end
  return LrFileUtils.readFile(path)
end

local function headers(token, withJson)
  local list = { { field = 'Authorization', value = 'Bearer ' .. token } }
  if withJson then list[#list + 1] = { field = 'Content-Type', value = 'application/json' } end
  return list
end

local function post(info, path, payload, timeout)
  local _, responseHeaders = LrHttp.post(
    info.baseUrl .. path, json.encode(payload), headers(info.token, true), 'POST', timeout)
  return responseHeaders and responseHeaders.status
end

local function unixNow()
  if os and os.time then return os.time() end
  return nil
end

local function handle(info, cache, generation, body)
  local command = json.decode(body)
  local valid, code = Core.validateCommand(command, contract.actions)
  local reply
  if not valid then
    if type(command) ~= 'table' or type(command.id) ~= 'string' then
      Log.warn('dropping a command without an id')
      return
    end
    reply = Core.errorReply(command.id, generation, code, { action = tostring(command.action) })
  else
    reply = Core.cacheGet(cache, command.id)
    if reply == nil then
      if Core.isExpired(command, unixNow()) then
        reply = Core.errorReply(command.id, generation, 'expired', { action = command.action })
      else
        local ok, result = LrTasks.pcall(Handlers[command.action], command.params or {})
        if ok then
          reply = Core.okReply(command.id, generation, result)
        else
          Log.error('%s failed: %s', command.action, tostring(result))
          reply = Core.errorReply(command.id, generation, 'handler_failed', { action = command.action })
        end
      end
      Core.cachePut(cache, command.id, reply)
    end
  end
  -- If this post fails, the caller times out and a retry is answered from the cache.
  post(info, '/result', reply, 30)
end

function Bridge.run(generation)
  local prefs = LrPrefs.prefsForPlugin()
  local path = discoveryPath()
  local state = Core.newState()
  current = state
  local cache = Core.newCache()
  local hello = {
    generation = generation,
    protocol = contract.protocol,
    plugin_version = pluginVersion(),
    lightroom_version = LrApplication.versionString(),
  }
  Log.info('bridge loop %d started; looking for %s', generation, path)

  while prefs.generation == generation do
    local step = Core.nextStep(state, readDiscovery(path), LrDate.currentTime())
    if step.kind == 'wait' then
      LrTasks.sleep(step.seconds)
    elseif step.kind == 'hello' then
      local outcome = Core.classify(post(state.info, '/hello', hello, 10))
      Core.onHello(state, outcome, LrDate.currentTime())
      Log.info('hello to port %d: %s', state.info.port, outcome)
    else
      local url = state.info.baseUrl .. '/poll?generation=' .. string.format('%d', generation)
      local body, responseHeaders = LrHttp.get(url, headers(state.info.token, false), contract.poll_hold_seconds + 10)
      local outcome = Core.classify(responseHeaders and responseHeaders.status)
      if outcome == 'ok' then
        handle(state.info, cache, generation, body)
      elseif outcome == 'stale' and prefs.generation ~= generation then
        break
      else
        Core.onPoll(state, outcome, LrDate.currentTime())
        if outcome ~= 'idle' then Log.info('poll: %s', outcome) end
      end
    end
  end
  Log.info('bridge loop %d stopped (superseded by a reload or shutdown)', generation)
end

return Bridge
