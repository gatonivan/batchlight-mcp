-- Runs when Lightroom quits. Returning this table (and calling done) is what keeps
-- Lightroom from showing a "waiting for plug-in" dialog on every quit.

local LrPrefs = import 'LrPrefs'

return {
  LrShutdownFunction = function(doneFunction, progressFunction)
    local prefs = LrPrefs.prefsForPlugin()
    prefs.generation = (prefs.generation or 0) + 1
    doneFunction()
  end,
}
