
-- factory_guage.lua
-- CC:Tweaked script — simplified menu-driven factory gauge
--
-- CONTROLS (keyboard goes through the COMPUTER, not the monitor):
--   W/Up        — navigate up
--   S/Down      — navigate down
--   Enter       — select highlighted item
--   Q/Esc       — back / quit

print("factory_guage: starting...")

-- ---------------------------------------------------------------------------
-- ENVIRONMENT DETECTION
-- ---------------------------------------------------------------------------

local function hasFn(tbl, name)
  return tbl and type(tbl[name]) == "function"
end

local has_peripheral_find = _G.peripheral and hasFn(_G.peripheral, "find")
local has_term = _G.term and type(_G.term) == "table"
local has_term_write    = has_term and hasFn(_G.term, "write")
local has_term_clear    = has_term and hasFn(_G.term, "clear")
local has_term_setCursorPos = has_term and hasFn(_G.term, "setCursorPos")
local has_term_getCursorPos = has_term and hasFn(_G.term, "getCursorPos")
local has_term_setTextColor = has_term and hasFn(_G.term, "setTextColor")
local has_term_flush    = has_term and hasFn(_G.term, "flush")
local has_colors        = _G.colors and type(_G.colors) == "table"
local has_io            = _G.io and type(_G.io.read) == "function"

if has_peripheral_find then print("[diag] peripheral.find: AVAILABLE") end
if has_term then print("[diag] term: AVAILABLE") end
if has_colors then print("[diag] colors: AVAILABLE") end
if has_io then print("[diag] io.read: AVAILABLE") end

-- ---------------------------------------------------------------------------
-- MONITOR AUTO-DETECTION
-- ---------------------------------------------------------------------------

local monitor = nil
local onMonitor = false

if has_peripheral_find then
  monitor = _G.peripheral.find("monitor")
  if monitor then
    onMonitor = true
    print("[diag] monitor: DETECTED")
  else
    print("[diag] monitor: NOT FOUND — using terminal")
  end
else
  print("[diag] monitor: peripheral.find unavailable")
end

-- Unified display: monitor if found, otherwise computer's term.
-- We also keep termDisplay for writing prompts to the computer's terminal
-- (monitors have no keyboard — all input goes through the computer).
local display = monitor or term
local termDisplay = term

-- ---------------------------------------------------------------------------
-- OUTPUT HELPERS
-- ---------------------------------------------------------------------------

local function termFlush()
  if has_term_flush then _G.term.flush() end
end

local function dispWrite(text)
    display.write(text)
end

local function dispWriteLn(text)
    dispWrite(text)
    local _, y = display.getCursorPos()
    local _, h = display.getSize()
    if y >= h then
        if onMonitor then
            display.setCursorPos(1, h)
            display.write(string.rep(" ", 51))
            display.setCursorPos(1, h)
        else
            display.scroll(1)
            display.setCursorPos(1, h)
        end
    else
        display.setCursorPos(1, y + 1)
    end
end

-- Write to both the monitor and the computer's terminal.
local function prompt(text)
    dispWrite(text)
    if has_term and has_term_write then
        _G.term.write(text)
        termFlush()
    end
end

-- Clear both the monitor (if present) and the computer's term.
-- When a monitor is active, the computer term shows a status panel so
-- the user knows where to type.
local function dispClear()
  if onMonitor and monitor and hasFn(monitor, "clear") then
    monitor.clear()
  elseif has_term and has_term_clear then
    _G.term.clear()
  end
  -- Always show something on the computer's terminal.
  if has_term and has_term_clear and has_term_write then
    _G.term.clear()
    _G.term.setCursorPos(1, 1)
    _G.term.setTextColor(colors.green)
    _G.term.write("Factory Gauge — monitor active")
    _G.term.setTextColor(colors.gray)
    _G.term.setCursorPos(1, 2)
    _G.term.write("Use THIS computer's keyboard to control")
    _G.term.setCursorPos(1, 3)
    _G.term.write("W/S: navigate  |  Enter: select  |  Q: back/quit")
    termFlush()
  end
end

local function dispSetCursorPos(x, y)
  if onMonitor and monitor and hasFn(monitor, "setCursorPos") then
    monitor.setCursorPos(x, y)
  elseif has_term and has_term_setCursorPos then
    _G.term.setCursorPos(x, y)
  end
end

local function dispSetTextColor(c)
    local finalColor = c or colors.white
    if onMonitor and monitor and hasFn(monitor, "setTextColor") then
        monitor.setTextColor(finalColor)
    elseif has_term and has_term_setTextColor then
        _G.term.setTextColor(finalColor)
    end
end

local function dispSetBackgroundColor(c)
  if onMonitor and monitor and hasFn(monitor, "setBackgroundColor") then
    monitor.setBackgroundColor(c)
  elseif has_term and hasFn(_G.term, "setBackgroundColor") then
    _G.term.setBackgroundColor(c)
  end
end

local function dispGetSize()
  if onMonitor and monitor and hasFn(monitor, "getSize") then
    return monitor.getSize()
  elseif has_term and has_term_getCursorPos then
    local ok, w, h = pcall(function() return _G.term.getSize() end)
    if ok then return w, h end
    return 51, 19
  end
  return 51, 19
end

-- ---------------------------------------------------------------------------
-- INPUT
-- ---------------------------------------------------------------------------

local function readln()
  if has_io then
    local line = _G.io.read("*l")
    return line
  end
  local t = {}
  while true do
    local evt, data = os.pullEvent()
    if evt == "char" then
      local c = data
      if c == "\n" or c == "\r" then
        break
      elseif c == "\b" or c == "\127" then
        if #t > 0 then table.remove(t) end
      elseif type(c) == "string" and #c > 0 then
        t[#t + 1] = c
      end
    elseif evt == "key" then
      local key = data
      if key == keys.enter then
        break
      elseif key == keys.backspace then
        if #t > 0 then table.remove(t) end
      end
    end
  end
  local line = table.concat(t)
  if line == "" then return nil end
  return line
end

local function readkey()
  local evt, key = os.pullEvent("key")
  return key
end

-- ---------------------------------------------------------------------------
-- STATE
-- ---------------------------------------------------------------------------

local frogPorts = {}        -- list of frog port names
local selectedIndex = 1     -- currently highlighted menu item
local currentScreen = "main" -- "main" | "frogport" | "settings"

-- ---------------------------------------------------------------------------
-- PERIPHERAL SCAN (for detecting frog ports and other blocks)
-- ---------------------------------------------------------------------------

local detectedPeripherals = {}

local function scanAllSides()
  detectedPeripherals = {}
  if not has_peripheral_find then return end
  local sides_to_scan = { "left", "right", "front", "back", "top", "bottom" }
  for _, sideName in ipairs(sides_to_scan) do
    local ok, comp = pcall(function() return _G.peripheral.find(sideName) end)
    if ok and comp and comp.type and comp.type ~= "none" then
      detectedPeripherals[sideName] = {
        side = sideName,
        name = sideName,
        type = comp.type,
        comp = comp,
      }
    end
  end
end

-- ---------------------------------------------------------------------------
-- FROG PORT MANAGEMENT
-- ---------------------------------------------------------------------------

local function addFrogPort()
  dispClear()
  drawHeader("ADD FROG PORT")
  dispSetTextColor(colors.white)
  dispSetCursorPos(1, 3)
  dispWriteLn("Enter the name of the new Frog Port:")
  dispWriteLn("")
  prompt("> ")
  local name = readln()
  if name and name ~= "" then
    -- Trim whitespace
    name = string.match(name, "^%s*(.-)%s*$")
    if name ~= "" then
      frogPorts[#frogPorts + 1] = name
      dispWriteLn("")
      dispWriteLn("Added: " .. name)
    end
  end
  dispWriteLn("")
  dispWriteLn("(press any key to continue...)")
  readkey()
end

local function removeFrogPort()
  if #frogPorts == 0 then
    dispClear()
    drawHeader("REMOVE FROG PORT")
    dispSetTextColor(colors.gray)
    dispSetCursorPos(1, 3)
    dispWriteLn("No Frog Ports to remove.")
    dispWriteLn("")
    dispWriteLn("(press any key to continue...)")
    readkey()
    return
  end

  -- Show list with numbers
  dispClear()
  drawHeader("REMOVE FROG PORT")
  dispSetTextColor(colors.white)
  dispSetCursorPos(1, 3)
  dispWriteLn("Select a Frog Port to remove:")
  dispWriteLn("")

  for i, name in ipairs(frogPorts) do
    dispSetCursorPos(2, 4 + i - 1)
    dispSetTextColor(i == selectedIndex and colors.white or colors.gray)
    dispWrite(i .. ". " .. name)
  end

  local bottomY = 4 + #frogPorts + 1
  dispSetCursorPos(1, bottomY)
  dispSetTextColor(colors.darkGray)
  dispWriteLn("(type the number of the port to remove)")
  prompt("> ")
  local input = readln()
  if input then
    local num = tonumber(input)
    if num and num >= 1 and num <= #frogPorts then
      local removed = table.remove(frogPorts, num)
      dispWriteLn("")
      dispWriteLn("Removed: " .. removed)
    else
      dispWriteLn("")
      dispWriteLn("Invalid number.")
    end
  end
  dispWriteLn("")
  dispWriteLn("(press any key to continue...)")
  readkey()
end

local function showFrogPortList()
  if #frogPorts == 0 then
    dispClear()
    drawHeader("FROG PORTS")
    dispSetTextColor(colors.gray)
    dispSetCursorPos(1, 3)
    dispWriteLn("No Frog Ports configured.")
    dispWriteLn("")
    dispWriteLn("(press any key to continue...)")
    readkey()
    return
  end

  dispClear()
  drawHeader("FROG PORTS")

  -- List ports with numbers, highlight selected
  local listY = 3
  for i, name in ipairs(frogPorts) do
    local isSelected = (i == selectedIndex)
    if isSelected then
      dispSetTextColor(colors.white)
      dispSetBackgroundColor(colors.blue)
    else
      dispSetTextColor(colors.gray)
      dispSetBackgroundColor(colors.black)
    end
    dispSetCursorPos(2, listY)
    if isSelected then
      dispWrite("> " .. i .. ". " .. name .. " ")
    else
      dispWrite("  " .. i .. ". " .. name .. " ")
    end
    listY = listY + 1
  end

  -- Bottom options
  local bottomY = listY + 1
  dispSetCursorPos(1, bottomY)
  dispSetTextColor(colors.darkGray)
  dispSetBackgroundColor(colors.black)
  dispWriteLn("")
  dispSetCursorPos(2, bottomY + 1)
  dispWrite("A. Add Frog Port")
  dispSetCursorPos(2, bottomY + 2)
  dispWrite("R. Remove Frog Port")
  dispSetCursorPos(2, bottomY + 3)
  dispWrite("B. Back")

  -- Handle keyboard in this sub-screen
  local running = true
  while running do
    local key = readkey()
    if not key then break end

    if key == keys.q or key == keys.escape then
      running = false
    elseif key == keys.enter then
      -- Enter on a port number does nothing special here;
      -- use A/R to add/remove, B to go back
      running = false
    elseif key == keys.up or key == keys.w then
      if selectedIndex > 1 then
        selectedIndex = selectedIndex - 1
      else
        selectedIndex = #frogPorts
      end
    elseif key == keys.down or key == keys.s then
      if selectedIndex < #frogPorts then
        selectedIndex = selectedIndex + 1
      else
        selectedIndex = 1
      end
    elseif type(key) == "string" then
      local lower = string.lower(key)
      if lower == "a" or lower == "a" then
        addFrogPort()
        showFrogPortList()  -- refresh the list
        return
      elseif lower == "r" then
        removeFrogPort()
        showFrogPortList()  -- refresh the list
        return
      elseif lower == "b" then
        running = false
      end
    end
  end
end

-- ---------------------------------------------------------------------------
-- SETTINGS SCREEN
-- ---------------------------------------------------------------------------

local function showSettings()
  dispClear()
  drawHeader("SETTINGS")

  dispSetTextColor(colors.white)
  dispSetCursorPos(1, 3)
  dispWriteLn("SETTINGS")
  dispWriteLn("")
  dispSetTextColor(colors.gray)
  dispSetCursorPos(1, 5)
  dispWriteLn("  Auto-scan peripherals:  Enabled")
  dispSetCursorPos(1, 6)
  dispWriteLn("  Default Frog Ports:     " .. (#frogPorts > 0 and table.concat(frogPorts, ", ") or "none"))
  dispSetCursorPos(1, 7)
  dispWriteLn("  Monitor auto-detect:    " .. (onMonitor and "Enabled" or "Disabled"))
  dispSetCursorPos(1, 9)
  dispSetTextColor(colors.darkGray)
  dispWriteLn("")
  dispWriteLn("(press any key to return...)")
  readkey()
end

-- ---------------------------------------------------------------------------
-- CREATE FACTORY GAUGE SCREEN
-- ---------------------------------------------------------------------------

local function showCreateFactoryGauge()
  dispClear()
  drawHeader("CREATE FACTORY GAUGE")

  dispSetTextColor(colors.white)
  dispSetCursorPos(1, 3)
  dispWriteLn("CREATE FACTORY GAUGE")
  dispWriteLn("")
  dispSetTextColor(colors.gray)
  dispSetCursorPos(1, 5)
  dispWriteLn("This would trigger the factory gauge")
  dispSetCursorPos(1, 6)
  dispWriteLn("creation process using the configured")
  dispSetCursorPos(1, 7)
  dispWriteLn("Frog Ports.")
  dispWriteLn("")
  dispSetCursorPos(1, 9)
  dispWriteLn("Frog Ports available:")
  if #frogPorts > 0 then
    for i, name in ipairs(frogPorts) do
      dispSetCursorPos(2, 10 + i - 1)
      dispWrite(i .. ". " .. name)
    end
  else
    dispSetCursorPos(2, 10)
    dispWriteLn("(none configured — go to Frog Port menu)")
  end

  local bottomY = 10 + math.max(#frogPorts, 1) + 1
  dispSetCursorPos(1, bottomY)
  dispSetTextColor(colors.darkGray)
  dispWriteLn("")
  dispWriteLn("(press any key to return...)")
  readkey()
end

-- ---------------------------------------------------------------------------
-- MENU RENDERING
-- ---------------------------------------------------------------------------

local function drawHeader(title)
  local w, h = dispGetSize()
  dispClear()
  dispSetBackgroundColor(colors.black)
  dispSetTextColor(colors.yellow)
  local titleLen = #title
  local pad = math.floor((w - titleLen) / 2)
  if pad < 0 then pad = 0 end
  dispSetCursorPos(1, 1)
  dispWrite(string.rep("=", w))
  dispWriteLn()
  dispSetCursorPos(1, 2)
  dispWrite(string.rep(" ", pad) .. title .. string.rep(" ", w - pad - titleLen))
  dispWriteLn()
  dispWrite(string.rep("=", w))
  dispWriteLn()
end

local function drawMainMenu()
  local w, h = dispGetSize()
  drawHeader("FACTORY GAUGE")

  -- Menu items
  local items = {
    { text = "Create factory gauge", action = "create" },
    { text = "Frog Port", action = "frogport" },
    { text = "Settings", action = "settings" },
  }

  local y = 4
  for i, item in ipairs(items) do
    local isSelected = (i == selectedIndex)
    if isSelected then
      dispSetTextColor(colors.white)
      dispSetBackgroundColor(colors.blue)
    else
      dispSetTextColor(colors.gray)
      dispSetBackgroundColor(colors.black)
    end
    dispSetCursorPos(2, y)
    if isSelected then
      dispWrite("> " .. item.text .. string.rep(" ", w - 4 - #item.text))
    else
      dispWrite("  " .. item.text .. string.rep(" ", w - 4 - #item.text))
    end
    y = y + 1
  end

  -- Bottom hint
  local bottomY = y + 1
  dispSetCursorPos(1, bottomY)
  dispSetTextColor(colors.darkGray)
  dispSetBackgroundColor(colors.black)
  dispWrite("W/S: navigate  |  Enter: select  |  Q: quit")
end

-- ---------------------------------------------------------------------------
-- MAIN LOOP
-- ---------------------------------------------------------------------------

local function main()
  scanAllSides()

  -- Try to load frog ports from clipboard (book/sign) first
  local clipboardNames = {}
  for sideName, p in pairs(detectedPeripherals) do
    local typ = p.type or ""
    if string.find(typ, "sign") then
      local comp = p.comp
      if comp and hasFn(comp, "getSignText") then
        local text = comp.getSignText()
        if text then
          for line in string.gmatch(text, "[^\r\n]+") do
            line = string.match(line, "^%s*(.-)%s*$")
            if line ~= "" then clipboardNames[#clipboardNames + 1] = line end
          end
        end
      end
    end
  end

  if #clipboardNames > 0 then
    frogPorts = clipboardNames
  else
    -- Default ports
    frogPorts = { "smasher", "grinder", "smelter" }
  end

  selectedIndex = 1
  currentScreen = "main"

  -- Brief startup message
  if onMonitor then
    dispClear()
    dispSetCursorPos(1, 1)
    dispSetTextColor(colors.green)
    dispWrite("Monitor ready. Keyboard input goes through the")
    dispWriteLn("computer — use the computer's keyboard.")
    sleep(2)
  end

  local running = true
  while running do
    if currentScreen == "main" then
      drawMainMenu()

      local key = readkey()
      if not key then break end

      if key == keys.q or key == keys.escape then
        running = false

      elseif key == keys.enter then
        if selectedIndex == 1 then
          currentScreen = "create"
        elseif selectedIndex == 2 then
          currentScreen = "frogport"
        elseif selectedIndex == 3 then
          currentScreen = "settings"
        end

      elseif key == keys.up or key == keys.w then
        if selectedIndex > 1 then
          selectedIndex = selectedIndex - 1
        else
          selectedIndex = #({ "Create factory gauge", "Frog Port", "Settings" })
        end

      elseif key == keys.down or key == keys.s then
        local max = 3
        if selectedIndex < max then
          selectedIndex = selectedIndex + 1
        else
          selectedIndex = 1
        end
      end

    elseif currentScreen == "create" then
      showCreateFactoryGauge()
      currentScreen = "main"
      selectedIndex = 1

    elseif currentScreen == "frogport" then
      showFrogPortList()
      currentScreen = "main"
      selectedIndex = 2  -- Keep selection on Frog Port

    elseif currentScreen == "settings" then
      showSettings()
      currentScreen = "main"
      selectedIndex = 3  -- Keep selection on Settings
    end
  end

  dispWriteLn("\nShutting down.\n")
end

-- Run
main()
