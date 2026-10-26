-- The state folder shared with the Python server: bridge.json and plugin.log live here.
-- Must match default_state_dir() in bridge/discovery.py.

local LrPathUtils = import 'LrPathUtils'

local Paths = {}

local APP_DIR = 'batchlight-mcp'

function Paths.stateDir()
  if MAC_ENV then
    local home = LrPathUtils.getStandardFilePath('home')
    return LrPathUtils.child(LrPathUtils.child(LrPathUtils.child(home, 'Library'), 'Application Support'), APP_DIR)
  end
  local appData = os.getenv('APPDATA')
  if appData == nil or appData == '' then
    local ok, path = pcall(LrPathUtils.getStandardFilePath, 'appData')
    appData = ok and path or nil
  end
  return appData and LrPathUtils.child(appData, APP_DIR) or nil
end

return Paths
