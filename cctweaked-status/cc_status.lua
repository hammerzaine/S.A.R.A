-- cc_status.lua  —  CCTweaked status reporter
-- Drop this on a CC:T computer (pastebin/forge or `edit cc_status`). It pushes
-- a status JSON blob to the S.A.R.A status backend every REPORT_MS.
--
-- CONFIG — point these at your backend:
local BACKEND = "http://192.168.2.176:8011/api/status"
local NAME    = "ReactorCtrl"   -- unique per computer
local LABEL   = "Reactor Controller"
local REPORT_MS = 15000

-- Optional: GPS coords (needs a GPS setup in the world)
local hasGPS, x, y, z = pcall(gps.locate)

local function fuel()
  if turtle then return turtle.getFuelLevel() end
  return nil
end

local function collect()
  local st = {
    name  = NAME,
    id    = os.getComputerID(),
    type  = turtle and "turtle" or "computer",
    label = LABEL,
    online = true,
    state  = "running",
    fuel   = fuel(),
    position = hasGPS and {x=x,y=y,z=z} or nil,
    data = {
      uptime = os.clock and math.floor(os.clock()) or nil,
      -- add your own live metrics here, e.g. read peripherals:
      -- reactor = peripheral.call("top","getHeat") or nil,
    },
  }
  return st
end

local function post(payload)
  local ok, err = pcall(function()
    local h = http.post(BACKEND, textutils.serializeJSON(payload),
                        { ["Content-Type"] = "application/json" })
    if h then h.close() end
  end)
  if not ok then
    print("status POST failed: " .. tostring(err))
  end
end

print("CCTweaked status reporter starting -> " .. BACKEND)
while true do
  local ok, st = pcall(collect)
  if ok then post(st) end
  sleep(REPORT_MS / 1000)
end
