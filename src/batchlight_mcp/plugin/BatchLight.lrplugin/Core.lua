-- Every decision the bridge loop makes, with no Lightroom imports, so busted can
-- test it on plain Lua 5.1. Bridge.lua is the thin shell that performs the I/O.

local json = require 'dkjson'

local Core = {}

Core.FILE_CHECK_SECONDS = 2   -- how often to look for a new or changed bridge.json
Core.MAX_BACKOFF_SECONDS = 30
Core.CACHE_SIZE = 100         -- results kept so a repeated delivery never runs twice

function Core.decodeContract(text)
  local contract = json.decode(text)
  assert(type(contract) == 'table' and type(contract.protocol) == 'number', 'contract.json is invalid')
  assert(type(contract.actions) == 'table' and type(contract.poll_hold_seconds) == 'number', 'contract.json is invalid')
  return contract
end

-- Parse bridge.json. Returns the hub's details, or nil plus a reason.
function Core.parseDiscovery(text)
  if type(text) ~= 'string' or text == '' then return nil, 'missing' end
  local info = json.decode(text)
  if type(info) ~= 'table' then return nil, 'invalid' end
  if type(info.port) ~= 'number' or type(info.token) ~= 'string' or info.token == '' then
    return nil, 'invalid'
  end
  if info.test == true then return nil, 'test_hub' end  -- started by the test suite
  return {
    port = info.port,
    token = info.token,
    baseUrl = 'http://127.0.0.1:' .. string.format('%d', info.port),
  }
end

function Core.newState()
  return { discoveryText = nil, info = nil, connected = false, failures = 0, retryAt = 0 }
end

-- 1, 2, 4, 8, 16, then 30 seconds.
function Core.backoff(failures)
  if failures <= 0 then return 0 end
  local seconds = 2 ^ (failures - 1)
  if seconds > Core.MAX_BACKOFF_SECONDS then seconds = Core.MAX_BACKOFF_SECONDS end
  return seconds
end

-- What the loop should do next: { kind = 'wait', seconds = n } | { kind = 'hello' } | { kind = 'poll' }.
-- A changed discovery file always resets the backoff, so a new hub is found within FILE_CHECK_SECONDS.
function Core.nextStep(state, discoveryText, now)
  if discoveryText ~= state.discoveryText then
    state.discoveryText = discoveryText
    state.info = Core.parseDiscovery(discoveryText)
    state.connected = false
    state.failures = 0
    state.retryAt = 0
  end
  if not state.info then return { kind = 'wait', seconds = Core.FILE_CHECK_SECONDS } end
  if state.connected then return { kind = 'poll' } end
  if now < state.retryAt then
    return { kind = 'wait', seconds = math.min(Core.FILE_CHECK_SECONDS, state.retryAt - now) }
  end
  return { kind = 'hello' }
end

-- Map an HTTP status from LrHttp (nil on a network failure) to an outcome.
function Core.classify(status)
  if status == nil then return 'network' end
  if status == 200 then return 'ok' end
  if status == 204 then return 'idle' end
  if status == 409 then return 'stale' end
  if status == 428 then return 'hello_required' end
  return 'rejected'
end

local function fail(state, now)
  state.connected = false
  state.failures = state.failures + 1
  state.retryAt = now + Core.backoff(state.failures)
end

function Core.onHello(state, outcome, now)
  if outcome == 'ok' then
    state.connected = true
    state.failures = 0
  else
    fail(state, now)
  end
end

-- After a poll. 'stale' is handled by the shell first: it exits if this loop was superseded.
function Core.onPoll(state, outcome, now)
  if outcome == 'ok' or outcome == 'idle' then return end
  if outcome == 'stale' or outcome == 'hello_required' then
    state.connected = false  -- say hello again straight away
    return
  end
  fail(state, now)
end

-- One sentence for the BatchLight Status menu item. state is nil until the loop starts.
function Core.describe(state)
  if state == nil then return 'The bridge is starting. Try again in a few seconds.' end
  if state.connected then return 'Connected to the BatchLight server.' end
  if state.info == nil then
    if state.discoveryText ~= nil then
      return 'Found a bridge.json it cannot use. Waiting for the BatchLight server to write a new one.'
    end
    return 'Waiting for the BatchLight server. It starts with Claude Desktop or Claude Code.'
  end
  if state.failures > 0 then return 'The BatchLight server is not answering. Retrying.' end
  return 'Connecting to the BatchLight server.'
end

-- Returns true, or nil plus an error code from the contract.
function Core.validateCommand(command, actions)
  if type(command) ~= 'table' or type(command.id) ~= 'string' or type(command.action) ~= 'string' then
    return nil, 'bad_request'
  end
  if command.params ~= nil and type(command.params) ~= 'table' then return nil, 'bad_request' end
  if not actions[command.action] then return nil, 'unknown_action' end
  return true
end

-- Expiry only stops a command from starting. Without a clock, the hub's check stands.
function Core.isExpired(command, nowUnix)
  return type(command.expires_at) == 'number' and type(nowUnix) == 'number' and nowUnix > command.expires_at
end

function Core.newCache(size)
  return { size = size or Core.CACHE_SIZE, order = {}, byId = {} }
end

function Core.cacheGet(cache, id)
  return cache.byId[id]
end

function Core.cachePut(cache, id, reply)
  if cache.byId[id] == nil then cache.order[#cache.order + 1] = id end
  cache.byId[id] = reply
  while #cache.order > cache.size do
    local oldest = table.remove(cache.order, 1)
    cache.byId[oldest] = nil
  end
end

function Core.okReply(id, generation, result)
  return { id = id, generation = generation, ok = true, result = result }
end

function Core.errorReply(id, generation, code, params)
  return { id = id, generation = generation, ok = false, error = { code = code, params = params or {} } }
end

return Core
