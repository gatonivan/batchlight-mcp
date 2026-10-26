-- One function per contract action. Each takes the command's params and returns a
-- result table; Bridge.lua runs it inside LrTasks.pcall.

local LrApplication = import 'LrApplication'
local LrApplicationView = import 'LrApplicationView'

local Handlers = {}

function Handlers.ping(params)
  return { pong = true }
end

function Handlers.status(params)
  local catalog = LrApplication.activeCatalog()
  -- getTargetPhotos() returns the whole filmstrip when nothing is selected,
  -- so check for an active photo first.
  local selected = 0
  if catalog:getTargetPhoto() ~= nil then
    selected = #catalog:getTargetPhotos()
  end
  local okModule, module = pcall(LrApplicationView.getCurrentModuleName)
  return {
    lightroom_version = LrApplication.versionString(),
    module = okModule and module or 'unknown',
    selected_photos = selected,
  }
end

return Handlers
