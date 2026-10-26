return {
  LrSdkVersion = 15.0,
  LrSdkMinimumVersion = 15.0,
  LrToolkitIdentifier = 'io.github.gatonivan.batchlight',
  LrPluginName = 'BatchLight',
  LrInitPlugin = 'Init.lua',
  LrForceInitPlugin = true,
  -- LrC 15.6 only checks LrForceInitPlugin while building a plug-in's menu items
  -- (AgSdkMenus.lua). Without a menu item, Init.lua never runs and the bridge never starts.
  LrExportMenuItems = { { title = 'BatchLight Status...', file = 'StatusMenu.lua' } },
  LrShutdownPlugin = 'Shutdown.lua',
  LrShutdownApp = 'ShutdownApp.lua',
  -- Keep in step with pyproject.toml; a test checks they match.
  VERSION = { major = 0, minor = 1, revision = 0, build = 0, display = '0.1.0' },
}
