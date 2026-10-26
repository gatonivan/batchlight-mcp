-- File > Plug-in Extras > BatchLight Status. Declaring this menu item is also what
-- makes Lightroom honour LrForceInitPlugin (see Info.lua).

local LrDialogs = import 'LrDialogs'
local LrTasks = import 'LrTasks'

local Bridge = require 'Bridge'

LrTasks.startAsyncTask(function()
  LrDialogs.message('BatchLight', Bridge.describe(), 'info')
end)
