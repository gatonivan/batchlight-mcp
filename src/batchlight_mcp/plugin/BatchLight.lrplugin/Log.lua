-- Local log only. Raw error text, which can include file paths, goes here and never
-- to the AI. Written two ways: Lightroom's own logger, and plugin.log next to
-- bridge.json, which is easy to find (~/Library/Application Support/batchlight-mcp).

local LrLogger = import 'LrLogger'
local LrPathUtils = import 'LrPathUtils'
local LrFileUtils = import 'LrFileUtils'

local Paths = require 'Paths'

local logger = LrLogger('BatchLight')
logger:enable('logfile')

local MAX_BYTES = 1024 * 1024

local logPath
do
  local ok, dir = pcall(Paths.stateDir)
  if ok and dir then
    pcall(LrFileUtils.createAllDirectories, dir)
    logPath = LrPathUtils.child(dir, 'plugin.log')
  end
end

local function append(level, text)
  if not logPath then return end
  pcall(function()
    local size = LrFileUtils.fileAttributes(logPath)
    local mode = (size and size.fileSize and size.fileSize > MAX_BYTES) and 'w' or 'a'
    local f = io.open(logPath, mode)
    if f then
      f:write(os.date('%Y-%m-%d %H:%M:%S'), ' ', level, ' ', text, '\n')
      f:close()
    end
  end)
end

local Log = {}

function Log.info(fmt, ...)
  local text = string.format(fmt, ...)
  logger:info(text)
  append('INFO', text)
end

function Log.warn(fmt, ...)
  local text = string.format(fmt, ...)
  logger:warn(text)
  append('WARN', text)
end

function Log.error(fmt, ...)
  local text = string.format(fmt, ...)
  logger:error(text)
  append('ERROR', text)
end

return Log
