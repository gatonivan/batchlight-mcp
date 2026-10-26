local Core = require 'Core'

local function readFile(path)
  local f = assert(io.open(path, 'r'))
  local text = f:read('*a')
  f:close()
  return text
end

describe('Handlers', function()
  it('has a handler for every contract action, and nothing else', function()
    local Handlers = require 'Handlers'
    local contract = Core.decodeContract(readFile('src/batchlight_mcp/plugin/BatchLight.lrplugin/contract.json'))
    for action in pairs(contract.actions) do
      assert.is_function(Handlers[action], 'missing handler for ' .. action)
    end
    for name in pairs(Handlers) do
      assert.is_not_nil(contract.actions[name], name .. ' is not in contract.json')
    end
  end)
end)
