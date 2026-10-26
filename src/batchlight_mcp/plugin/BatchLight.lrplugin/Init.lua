-- Runs when Lightroom starts (LrForceInitPlugin, which needs the menu item in Info.lua)
-- and on every Reload in Plug-in Manager.

local LrFunctionContext = import 'LrFunctionContext'
local LrPrefs = import 'LrPrefs'
local LrTasks = import 'LrTasks'

local Log = require 'Log'

-- Each load gets a new generation. An older loop still running after a Reload sees
-- the change and exits, so there is never more than one loop.
local prefs = LrPrefs.prefsForPlugin()
prefs.generation = (prefs.generation or 0) + 1
local generation = prefs.generation
Log.info('init: generation %d, plugin folder %s', generation, tostring(_PLUGIN and _PLUGIN.path))

local loaded, Bridge = pcall(require, 'Bridge')
if not loaded then
  Log.error('init: could not load Bridge.lua: %s', tostring(Bridge))
  error(Bridge)  -- also surfaces in Plug-in Manager
end

LrFunctionContext.postAsyncTaskWithContext('BatchLight bridge', function(context)
  while prefs.generation == generation do
    local ok, err = LrTasks.pcall(Bridge.run, generation)
    if ok then break end
    Log.error('bridge loop crashed: %s; restarting in 5 s', tostring(err))
    LrTasks.sleep(5)
  end
end)
