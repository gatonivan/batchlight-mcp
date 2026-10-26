-- Loaded by busted before the specs (see .busted).

package.path = 'src/batchlight_mcp/plugin/BatchLight.lrplugin/?.lua;' .. package.path

-- Lightroom's Lua 5.1 has no table.unpack, but Penlight (loaded by busted) adds one.
-- Remove it so plugin code that relies on it fails here instead of in Lightroom.
table.unpack = nil

-- Lightroom's `import` returns SDK namespaces. Specs get recording stubs instead.
_G.import = function(name)
  return setmetatable({}, {
    __index = function(_, key)
      error(('Lightroom API %s.%s used outside Lightroom'):format(name, tostring(key)), 2)
    end,
  })
end
