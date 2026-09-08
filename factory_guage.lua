
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

local display = monitor or term

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
-- When a monitor is active, the computer term shows a status panel.
local function dispClear()
  if onMonitor and monitor and hasFn(monitor, "clear") then
    monitor.clear()
  elseif has_term and has_term_clear then
    _G.term.clear()
  end
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

local frogPorts = {}
local selectedIndex = 1
local currentScreen = "main"
local detectedPeripherals = {}
local stockTicker = nil
local stockTickerSide = nil
local stockCache = {}

local function scanAllSides()
  detectedPeripherals = {}
  stockTicker = nil
  stockTickerSide = nil
  stockCache = {}
  if not has_peripheral_find then return end

  -- 1. Scan all sides, wrapping each one to get its type
  local sides_to_scan = { "left", "right", "front", "back", "top", "bottom" }
  for _, sideName in ipairs(sides_to_scan) do
    local ok, comp = pcall(function() return _G.peripheral.wrap(sideName) end)
    if ok and comp then
      local typ = type(comp)
      if typ == "table" then
        -- Try to get type via component.getType() or check known fields
        local compType = "unknown"
        if hasFn(comp, "getType") then
          compType = comp.getType()
        elseif hasFn(comp, "type") then
          compType = comp.type
        elseif hasFn(comp, "getName") then
          compType = comp.getName()
        end
        -- Also check by looking at what methods it has
        local methods = {}
        for k, v in pairs(comp) do
          if type(k) == "string" and type(v) == "function" then
            methods[#methods + 1] = k
          end
        end
        detectedPeripherals[sideName] = {
          side = sideName,
          name = sideName,
          type = compType,
          comp = comp,
          methods = methods,
        }
        print("[diag] side " .. sideName .. ": type=" .. compType .. " methods=" .. table.concat(methods, ","))
      end
    end
  end

  -- 2. Search for stock ticker by type name across ALL sides
  local tickerNames = {
    "stock_ticker", "stockticker", "tickertape", "stock_display",
    "create:stock_ticker", "create:stockticker", "item_display",
    "stock", "ticker", "create:ticker", "create:stock_ticker",
    "create:stockticker", "stocktickers", "ticker_minecolonies",
    "minecolonies:ticker", "stockpanel", "itembar", "bar",
  }
  for _, tickerName in ipairs(tickerNames) do
    local ok, comp = pcall(function() return _G.peripheral.find(tickerName) end)
    if ok and comp then
      stockTicker = comp
      -- Figure out which side it's on
      for sideName, p in pairs(detectedPeripherals) do
        if p.comp == comp then
          stockTickerSide = sideName
          break
        end
      end
      if not stockTickerSide then
        -- Fallback: wrap each side and compare
        for _, sideName in ipairs(sides_to_scan) do
          local w = _G.peripheral.wrap(sideName)
          if w == comp then
            stockTickerSide = sideName
            break
          end
        end
      end
      print("[diag] stock ticker: DETECTED as '" .. tickerName .. "' on side " .. (stockTickerSide or "unknown"))
      break
    end
  end

  if not stockTicker then
    print("[diag] stock ticker: NOT FOUND — trying all sides individually")
    -- 3. Brute force: check every side for anything that looks like a stock ticker
    for _, sideName in ipairs(sides_to_scan) do
      local comp = detectedPeripherals[sideName] and detectedPeripherals[sideName].comp
      if comp and type(comp) == "table" then
        -- Check if it has stock-related methods
        for _, method in ipairs({ "getStock", "getItems", "getStockItems", "getTickers", "getTicker" }) do
          if comp[method] then
            stockTicker = comp
            stockTickerSide = sideName
            print("[diag] stock ticker: FOUND on side " .. sideName .. " via method '" .. method .. "'")
            break
          end
        end
      end
      if stockTicker then break end
    end
  end

  if not stockTicker then
    print("[diag] stock ticker: NOT FOUND — check what side it's on and what type it registers as")
  end
end

-- Read stock levels from the ticker peripheral.
-- Tries multiple API call patterns since the exact interface varies.
local function readStockFromTicker()
  stockCache = {}
  if not stockTicker then return end

  local function tryGetItems()
    -- Pattern 1: getItems() returns { {name=id, count=n} }
    if stockTicker.getItems then
      local ok, items = pcall(stockTicker.getItems)
      if ok and items and type(items) == "table" then
        for _, item in ipairs(items) do
          local id = item.id or item.name or item.displayName or ""
          local count = item.count or item.size or item.amount or 0
          if id ~= "" and count and count > 0 then
            stockCache[id] = (stockCache[id] or 0) + count
          end
        end
        if next(stockCache) then return true end
      end
    end
    -- Pattern 2: getAllItems() 
    if stockTicker.getAllItems then
      local ok, items = pcall(stockTicker.getAllItems)
      if ok and items and type(items) == "table" then
        for _, item in ipairs(items) do
          local id = item.id or item.name or item.displayName or ""
          local count = item.count or item.size or item.amount or 0
          if id ~= "" and count and count > 0 then
            stockCache[id] = (stockCache[id] or 0) + count
          end
        end
        if next(stockCache) then return true end
      end
    end
    -- Pattern 3: getStock() or getStockLevels()
    for _, fnName in ipairs({ "getStock", "getStockLevels", "getStockItems" }) do
      if stockTicker[fnName] then
        local ok, result = pcall(stockTicker[fnName])
        if ok and result and type(result) == "table" then
          -- Could be { itemName = count } or { {name, count} }
          if result[1] and type(result[1]) == "table" then
            -- Array of items
            for _, item in ipairs(result) do
              local id = item.id or item.name or item[1] or ""
              local count = item.count or item[2] or item.amount or 0
              if id ~= "" and count and count > 0 then
                stockCache[id] = (stockCache[id] or 0) + count
              end
            end
          else
            -- Key-value table: name -> count
            for name, count in pairs(result) do
              if type(count) == "number" and count > 0 then
                stockCache[name] = (stockCache[name] or 0) + count
              end
            end
          end
          if next(stockCache) then return true end
        end
      end
    end
    -- Pattern 4: get() returns a single item or stock overview
    if stockTicker.get then
      local ok, result = pcall(stockTicker.get)
      if ok and result then
        if type(result) == "table" then
          if result.count and result.name then
            stockCache[result.name] = result.count
          elseif result[1] then
            for _, item in ipairs(result) do
              local id = item.id or item.name or ""
              local count = item.count or item.size or 0
              if id ~= "" and count and count > 0 then
                stockCache[id] = (stockCache[id] or 0) + count
              end
            end
          end
          if next(stockCache) then return true end
        end
      end
    end
    return false
  end

  if not tryGetItems() then
    -- Fallback: try to read as a monitor (some stock tickers are monitor peripherals)
    if stockTicker.setTextColor and stockTicker.write then
      -- It's a monitor-like peripheral; can't read stock from it directly
      print("[diag] stock ticker: appears to be a display-only peripheral")
    end
  end
end

-- ---------------------------------------------------------------------------
-- MENU RENDERING (defined BEFORE screen functions that call them)
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

  local items = {
    { text = "Create factory gauge" },
    { text = "Frog Port" },
    { text = "Settings" },
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

  -- Stock overview (read from ticker if available)
  y = y + 1
  dispSetTextColor(colors.white)
  dispSetBackgroundColor(colors.black)
  dispSetCursorPos(1, y)
  dispWrite("STOCK:")
  y = y + 1
  if next(stockCache) then
    local itemList = {}
    for id, count in pairs(stockCache) do
      table.insert(itemList, { id = id, count = count })
    end
    table.sort(itemList, function(a, b) return a.count > b.count end)
    local show = math.min(#itemList, 6)
    for i = 1, show do
      local short = string.match(itemList[i].id, "^%w+:(.+)$") or itemList[i].id
      dispSetCursorPos(2, y)
      dispWrite(i .. ". " .. short .. ": " .. itemList[i].count)
      y = y + 1
    end
    if #itemList > show then
      dispSetCursorPos(2, y)
      dispWrite("... and " .. (#itemList - show) .. " more")
      y = y + 1
    end
  else
    dispSetCursorPos(2, y)
    dispSetTextColor(colors.gray)
    dispWrite("  (no stock data — check stock ticker connection)")
    y = y + 1
  end

  local bottomY = y + 1
  dispSetCursorPos(1, bottomY)
  dispSetTextColor(colors.darkGray)
  dispSetBackgroundColor(colors.black)
  dispWrite("W/S: navigate  |  Enter: select  |  Q: quit")
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

  dispClear()
  drawHeader("REMOVE FROG PORT")
  dispSetTextColor(colors.white)
  dispSetCursorPos(1, 3)
  dispWriteLn("Select a Frog Port to remove:")
  dispWriteLn("")

  for i, name in ipairs(frogPorts) do
    dispSetCursorPos(2, 4 + i - 1)
    dispSetTextColor(colors.gray)
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

  local running = true
  while running do
    local key = readkey()
    if not key then break end

    if key == keys.q or key == keys.escape then
      running = false
    elseif key == keys.enter then
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
      if lower == "a" then
        addFrogPort()
        showFrogPortList()
        return
      elseif lower == "r" then
        removeFrogPort()
        showFrogPortList()
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
  dispSetCursorPos(1, 8)
  dispWriteLn("  Stock ticker:           " .. (stockTicker and "Connected" or "Not found"))
  dispSetCursorPos(1, 9)
  if next(stockCache) then
    dispSetTextColor(colors.white)
    dispWriteLn("  Items in stock:         " .. countTable(stockCache))
  else
    dispSetTextColor(colors.gray)
    dispWriteLn("  Items in stock:         0")
  end
  dispSetCursorPos(1, 11)
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
-- MAIN LOOP
-- ---------------------------------------------------------------------------

local function main()
  scanAllSides()

  -- Load frog ports from sign text if available, else defaults
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
    frogPorts = { "smasher", "grinder", "smelter" }
  end

  selectedIndex = 1
  currentScreen = "main"

  -- Read initial stock from ticker
  readStockFromTicker()

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
          selectedIndex = 3
        end
      elseif key == keys.down or key == keys.s then
        if selectedIndex < 3 then
          selectedIndex = selectedIndex + 1
        else
          selectedIndex = 1
        end
      end

    elseif currentScreen == "create" then
      showCreateFactoryGauge()
      currentScreen = "main"
      selectedIndex = 1
      readStockFromTicker()

    elseif currentScreen == "frogport" then
      showFrogPortList()
      currentScreen = "main"
      selectedIndex = 2
      readStockFromTicker()

    elseif currentScreen == "settings" then
      showSettings()
      currentScreen = "main"
      selectedIndex = 3
      readStockFromTicker()
    end
  end

  dispWriteLn("\nShutting down.\n")
end

-- Run
main()
