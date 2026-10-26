-- Runs when the plugin is disabled, removed or reloaded: retire the running loop.

local LrPrefs = import 'LrPrefs'

local prefs = LrPrefs.prefsForPlugin()
prefs.generation = (prefs.generation or 0) + 1
