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
local has_term_setBackgroundColor = has_term and hasFn(_G.term, "setBackgroundColor")
local has_term_flush    = has_term and hasFn(_G.term, "flush")
local has_term_setTextScale = has_term and hasFn(_G.term, "setTextScale")
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
  if has_term_flush then pcall(function() _G.term.flush() end) end
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

local function prompt(text)
    dispWrite(text)
    if has_term and has_term_write then
        pcall(function() _G.term.write(text) end)
        termFlush()
    end
end

local function dispClear()
  if onMonitor and monitor and hasFn(monitor, "clear") then
    pcall(function() monitor.clear() end)
  elseif has_term and has_term_clear then
    pcall(function() _G.term.clear() end)
  end
  if has_term and has_term_clear and has_term_write then
    pcall(function() _G.term.clear() end)
    pcall(function() _G.term.setCursorPos(1, 1) end)
    dispSetTextColor(colors.green)
    pcall(function() _G.term.write("Factory Gauge — monitor active") end)
    dispSetTextColor(colors.gray)
    pcall(function() _G.term.setCursorPos(1, 2) end)
    pcall(function() _G.term.write("Use THIS computer's keyboard to control") end)
    pcall(function() _G.term.setCursorPos(1, 3) end)
    pcall(function() _G.term.write("W/S: navigate  |  Enter: select  |  Q: back/quit") end)
    termFlush()
  end
end

local function dispSetCursorPos(x, y)
  if onMonitor and monitor and hasFn(monitor, "setCursorPos") then
    pcall(function() monitor.setCursorPos(x, y) end)
  elseif has_term and has_term_setCursorPos then
    pcall(function() _G.term.setCursorPos(x, y) end)
  end
end

local function dispSetTextColor(c)
    local finalColor = c
    if not finalColor and has_colors then
        finalColor = colors.white
    elseif not finalColor then
        finalColor = 1  -- default white (CC:T color ID fallback)
    end
    if onMonitor and monitor and hasFn(monitor, "setTextColor") then
        pcall(function() monitor.setTextColor(finalColor) end)
    elseif has_term and has_term_setTextColor then
        pcall(function() _G.term.setTextColor(finalColor) end)
    end
end

local function dispSetBackgroundColor(c)
    if not c and has_colors then
        c = colors.black
    elseif not c then
        c = 0  -- default black
    end
    if onMonitor and monitor and hasFn(monitor, "setBackgroundColor") then
        pcall(function() monitor.setBackgroundColor(c) end)
    elseif has_term and has_term_setBackgroundColor then
        pcall(function() _G.term.setBackgroundColor(c) end)
    end
end

-- Set text scale on monitor (1 = default, 0.5 = smaller, 2 = larger).
local function dispSetTextScale(scale)
  if onMonitor and monitor and hasFn(monitor, "setTextScale") then
    pcall(function() monitor.setTextScale(scale) end)
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
-- ---------------------------------------------------------------------------
-- TERM-DIRECT OUTPUT (for computer-term-only rendering, e.g. main menu when
-- a monitor is also attached). These bypass the disp* routing and write
-- directly to _G.term so the computer screen and the monitor can show
-- different content simultaneously.
-- ---------------------------------------------------------------------------

local function termWrite(text)
  if has_term and has_term_write then
    pcall(function() _G.term.write(text) end)
  end
end

local function termWriteLn(text)
  termWrite(text)
  if has_term and has_term_getCursorPos then
    local ok, y = pcall(function() return _G.term.getCursorPos() end)
    if ok then
      local ok2, h = pcall(function() return _G.term.getSize() end)
      if ok2 and y and h and y >= h then
        pcall(function() _G.term.scroll(1) end)
        pcall(function() _G.term.setCursorPos(1, h) end)
      else
        pcall(function() _G.term.setCursorPos(1, y + 1) end)
      end
    end
  end
end

local function termClear()
  if has_term and has_term_clear then
    pcall(function() _G.term.clear() end)
  end
end

local function termSetCursorPos(x, y)
  if has_term and has_term_setCursorPos then
    pcall(function() _G.term.setCursorPos(x, y) end)
  end
end

local function termSetTextColor(c)
  if has_term and has_term_setTextColor and c then
    pcall(function() _G.term.setTextColor(c) end)
  end
end

local function termSetBackgroundColor(c)
  if has_term and has_term_setBackgroundColor and c then
    pcall(function() _G.term.setBackgroundColor(c) end)
  end
end

local function termSetTextScale(scale)
  if has_term and has_term_setTextScale then
    pcall(function() _G.term.setTextScale(scale) end)
  end
end

local function termGetSize()
  if has_term and has_term_getCursorPos then
    local ok, w, h = pcall(function() return _G.term.getSize() end)
    if ok then return w, h end
  end
  return 51, 19
end

-- INPUT
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- INPUT — with screen echo
-- ---------------------------------------------------------------------------

-- Read a line of text from the keyboard, echoing characters to the display
-- as they are typed (like a normal terminal prompt). Backspace removes the
-- last character and erases it from screen. Enter finishes the line.
--
-- On a monitor, echoing uses the monitor display. The computer's term always
-- gets a mirror so the user sees what they type even when looking at the
-- computer GUI.
--
-- Returns the typed line (string), or nil if the user entered nothing.
local function readlnWithEcho(promptText)
  -- Write the prompt first.
  dispWrite(promptText)
  if has_term and has_term_write then
    pcall(function() _G.term.write(promptText) end)
    termFlush()
  end

  local t = {}
  local echoX, echoY = 1, 1
  if onMonitor and monitor and hasFn(monitor, "getCursorPos") then
    echoX, echoY = monitor.getCursorPos()
  elseif has_term and has_term_getCursorPos then
    echoX, echoY = _G.term.getCursorPos()
  end

  -- Echo helpers: write a character (or erase it) on both displays.
  local function echoChar(ch)
    if ch then
      dispWrite(ch)
      if has_term and has_term_write then
        pcall(function() _G.term.write(ch) end)
        termFlush()
      end
    else
      -- Erase the last character on screen: back up one column, write a space, back up again.
      local curX, curY = 1, 1
      if onMonitor and monitor and hasFn(monitor, "getCursorPos") then
        curX, curY = monitor.getCursorPos()
      elseif has_term and has_term_getCursorPos then
        curX, curY = _G.term.getCursorPos()
      end
      local eraseX = curX - 1
      if eraseX < 1 then eraseX = 1 end
      dispSetCursorPos(eraseX, curY)
      dispWrite(" ")
      if has_term and has_term_write then
        pcall(function() _G.term.setCursorPos(eraseX, curY) end)
        pcall(function() _G.term.write(" ") end)
        termFlush()
      end
      dispSetCursorPos(eraseX, curY)
    end
  end

  while true do
    local evt, data = os.pullEvent()
    if evt == "char" then
      local c = data
      if c == "\n" or c == "\r" then
        -- Finalise: move to a new line on both displays.
        dispWriteLn("")
        if has_term and has_term_write then
          pcall(function() _G.term.write("\n") end)
          termFlush()
        end
        break
      elseif c == "\b" or c == "\127" then
        if #t > 0 then
          table.remove(t)
          echoChar(nil)  -- erase last char from screen
        end
      elseif type(c) == "string" and #c > 0 then
        t[#t + 1] = c
        echoChar(c)
      end
    elseif evt == "key" then
      local key = data
      if key == keys.enter then
        dispWriteLn("")
        if has_term and has_term_write then
          pcall(function() _G.term.write("\n") end)
          termFlush()
        end
        break
      elseif key == keys.backspace then
        if #t > 0 then
          table.remove(t)
          echoChar(nil)
        end
      end
    end
  end

  local line = table.concat(t)
  if line == "" then return nil end
  return line
end

-- ---------------------------------------------------------------------------
-- readkey() — normalises every event to a lowercase string label
-- ---------------------------------------------------------------------------
--
-- CC:T fires keys two ways:
--   1. "char" events with a single-character string (e.g. "w", "a", "r").
--   2. "key" / "key_down" / "key_up" events with a numeric key code from the
--      keys table (e.g. keys.enter, keys.up, keys.escape).
--
-- We build a reverse map (number → lowercase label) from the keys table that
-- actually exists on this build, so every handler only ever sees a string
-- label. Letter keys that aren't in the keys table are handled by the "char"
-- path directly.
--
-- Returns:
--   - a lowercase string label (e.g. "w", "a", "up", "enter", "escape")
--   - nil  (os.pullEvent returned nil — no more events; caller should stop)

local KEY_LABEL = {}

do
  local keysTbl = _G.keys
  if type(keysTbl) == "table" then
    for k, v in pairs(keysTbl) do
      if type(k) == "string" and type(v) == "number" then
        KEY_LABEL[v] = string.lower(k)
      end
    end
  end
end

local function readkey()
  while true do
    local evt, data = os.pullEvent()
    if evt == "char" then
      if type(data) == "string" and #data == 1 then
        return string.lower(data)
      end
    elseif evt == "key" or evt == "key_down" or evt == "key_up" then
      if type(data) == "number" then
        local label = KEY_LABEL[data]
        if label then
          return label
        end
        -- Unknown numeric key code — ignore (could be a modifier or
        -- an unrecognised key on this CC:T build).
      elseif type(data) == "string" and #data == 1 then
        -- Some builds pass a single-char string where we'd expect a number.
        return string.lower(data)
      end
    elseif evt == nil then
      -- No more events.
      return nil
    end
    -- Any other event type (timer, etc.): ignore and loop.
  end
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
local factoryGauges = {}

local dashboardTimer = nil
local dashboardNeedsRefresh = false
local productionFn = nil
local productionFnPath = nil
local stockReadMethod = nil
local stockReadMethodPath = nil
local currentDashboardItemColor = nil  -- cached color per gauge line for blinking

-- ---------------------------------------------------------------------------
-- FACTORY GAUGE DATA MODEL
-- ---------------------------------------------------------------------------
--
-- factoryGauges[] is an array of:
--   { name = string, frogPort = string, qty = number (1..100),
--     mode = "stack" | "item", inactive = boolean }
--
-- "Needed" for a gauge = qty, interpreted as stacks if mode=="stack" else items.
-- "Stock" is read from stockCache keyed by the gauge's item name (normalised).

local function gaugeDisplayName(g)
  return g.name
end

local function gaugeItemName(g)
  -- Use the gauge name as the stock item key. CC:T stock integrations may use
  -- namespaced ids ("create:copper_ingot") or plain names ("copper_ingot").
  -- We try the gauge name first, then a few variations.
  return g.name
end

local function stockForGauge(g)
  local key = gaugeItemName(g)
  if stockCache[key] then
    return stockCache[key]
  end
  -- Try common namespace prefixes.
  for _, ns in ipairs({ "minecraft:", "create:", "forge:", "" }) do
    local k = ns .. key
    if stockCache[k] then
      return stockCache[k]
    end
    -- Also try without any namespace but the raw id may be numeric-ish.
  end
  -- Try to match by stripping any namespace off keys in stockCache.
  for ck, cv in pairs(stockCache) do
    local bare = string.match(ck, "^%w+:(.+)$")
    if bare and bare == key then
      return cv
    end
  end
  return 0
end

local function neededCount(g)
  -- qty is in stacks or items depending on mode. Multiply by a per-unit factor
  -- so the gauge's "needed" matches what the stock ticker reports as a count.
  -- If mode=="stack", treat qty as stacks (each stack = 64 items). Otherwise
  -- qty is already the item count.
  if g.mode == "stack" then
    return g.qty * 64
  else
    return g.qty
  end
end

local function gaugeWorking(g)
  return not g.inactive
end

local function gaugeForIndex(idx)
  if idx < 1 or idx > #factoryGauges then
    return nil
  end
  return factoryGauges[idx]
end

local function sortedGauges()
  local sorted = {}
  for _, g in ipairs(factoryGauges) do
    sorted[#sorted + 1] = g
  end
  table.sort(sorted, function(a, b) return a.name < b.name end)
  return sorted
end

local function findGaugeByName(name)
  for _, g in ipairs(factoryGauges) do
    if g.name == name then
      return g
    end
  end
  return nil
end

local function countWorkingGauges()
  local n = 0
  for _, g in ipairs(factoryGauges) do
    if gaugeWorking(g) then
      n = n + 1
    end
  end
  return n
end

local function countTotalNeeded()
  local total = 0
  for _, g in ipairs(factoryGauges) do
    if gaugeWorking(g) then
      total = total + neededCount(g)
    end
  end
  return total
end

local function countTotalStock()
  -- Sum stock for all items referenced by working gauges.
  local seen = {}
  local total = 0
  for _, g in ipairs(factoryGauges) do
    if gaugeWorking(g) then
      local key = gaugeItemName(g)
      if not seen[key] then
        seen[key] = true
        total = total + stockForGauge(g)
      end
    end
  end
  return total
end

local function scanAllSides()
  detectedPeripherals = {}
  stockTicker = nil
  stockTickerSide = nil
  stockCache = {}
  if not has_peripheral_find then return end

  local diagLines = {}

  -- 1. Scan all sides, wrapping each one to get its type
  local sides_to_scan = { "left", "right", "front", "back", "top", "bottom" }
  for _, sideName in ipairs(sides_to_scan) do
    local ok, comp = pcall(function() return _G.peripheral.wrap(sideName) end)
    if ok and comp then
      local typ = type(comp)
      if typ == "table" then
        local compType = "unknown"
        if hasFn(comp, "getType") then
          compType = comp.getType()
        elseif hasFn(comp, "type") then
          compType = comp.type
        elseif hasFn(comp, "getName") then
          compType = comp.getName()
        end
        local methods = {}
        for k, v in pairs(comp) do
          if type(k) == "string" and type(v) == "function" then
            methods[#methods + 1] = k
          elseif type(k) == "string" and type(v) == "table" then
            local nestedMethods = {}
            for nk, nv in pairs(v) do
              if type(nk) == "string" and type(nv) == "function" then
                nestedMethods[#nestedMethods + 1] = nk
              end
            end
            if #nestedMethods > 0 then
              methods[#methods + 1] = k .. "." .. table.concat(nestedMethods, ",")
            end
          end
        end
        detectedPeripherals[sideName] = {
          side = sideName, name = sideName, type = compType, comp = comp, methods = methods,
        }
        local methodsStr = table.concat(methods, ",")
        diagLines[#diagLines + 1] = "side " .. sideName ..
          ": type=" .. compType .. " methods=" .. methodsStr
      else
        diagLines[#diagLines + 1] = "side " .. sideName .. ": not a table (type=" .. typ .. ")"
      end
    else
      diagLines[#diagLines + 1] = "side " .. sideName .. ": no peripheral"
    end
  end

  -- 2. Search for stock ticker by type name
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
      for sideName, p in pairs(detectedPeripherals) do
        if p.comp == comp then
          stockTickerSide = sideName
          break
        end
      end
      if not stockTickerSide then
        for _, sideName in ipairs(sides_to_scan) do
          local w = _G.peripheral.wrap(sideName)
          if w == comp then
            stockTickerSide = sideName
            break
          end
        end
      end
      diagLines[#diagLines + 1] = "STOCK TICKER: DETECTED as '" .. tickerName ..
        "' on side " .. (stockTickerSide or "unknown")
      break
    end
  end

  -- 2b. Direct peripheral.stock property check
  if not stockTicker and _G.peripheral and _G.peripheral.stock then
    local stockProp = _G.peripheral.stock
    if type(stockProp) == "table" then
      stockTicker = stockProp
      stockTickerSide = "indirect"
      diagLines[#diagLines + 1] = "STOCK TICKER: DETECTED via peripheral.stock (direct property)"
    elseif type(stockProp) == "string" then
      local ok, comp = pcall(function() return _G.peripheral.find(stockProp) end)
      if ok and comp then
        stockTicker = comp
        stockTickerSide = "indirect"
        diagLines[#diagLines + 1] = "STOCK TICKER: DETECTED via peripheral.stock type name ('" .. stockProp .. "')"
      end
    end
  end

  -- Deep side-by-side search: enumerate every key on every side's component and
  -- look for ANY function whose name contains stock/item/list/ticker/detail/filter/request.
  -- Uses a recursive search so deeply-nested methods (like requestFiltered.getStockItemDetail.list)
  -- are found regardless of depth.
  if not stockTicker then
    print("[diag] Starting deep side-by-side stock scan...")
    for _, sideName in ipairs(sides_to_scan) do
      local comp = nil
      local ok = pcall(function()
        comp = _G.peripheral.wrap(sideName)
      end)
      if not ok or not comp then
        if _G.peripheral and type(_G.peripheral) == "table" then
          local sideProp = _G.peripheral[sideName]
          if type(sideProp) == "table" then
            comp = sideProp
          end
        end
      end
      if comp and type(comp) == "table" then
        print("[diag] Deep scanning side " .. sideName .. "...")
        -- Recursive search for stock-related functions at any depth
        local function deepSearch(tbl, path, depth)
          if depth > 5 then return false end
          for k, v in pairs(tbl) do
            if type(k) == "string" then
              local lower = string.lower(k)
              if lower:find("stock") or lower:find("item") or
                 lower:find("list") or lower:find("ticker") or
                 lower:find("detail") or lower:find("filter") or
                 lower:find("request") then
                if type(v) == "function" then
                  stockTicker = comp
                  stockTickerSide = sideName
                  diagLines[#diagLines + 1] = "STOCK TICKER: FOUND on side " .. sideName ..
                    " via '" .. path .. "." .. k .. "' (function)"
                  print("[diag] FOUND on " .. sideName .. ": " .. path .. "." .. k)
                  return true
                elseif type(v) == "table" then
                  diagLines[#diagLines + 1] = "diag: deep scan '" .. path .. "." .. k .. "' is a table"
                  print("[diag] deep: " .. path .. "." .. k .. " is a table")
                  if deepSearch(v, path .. "." .. k, depth + 1) then
                    return true
                  end
                end
              end
            elseif type(k) == "string" and type(v) == "table" then
              if deepSearch(v, path .. "." .. k, depth + 1) then
                return true
              end
            end
          end
          return false
        end
        if deepSearch(comp, "component", 1) then
          break
        end
      else
        print("[diag] side " .. sideName .. " not accessible")
      end
    end
    if not stockTicker then
      print("[diag] Deep scan complete — stock ticker not found on any side")
    end
  end

  if not stockTicker then
    diagLines[#diagLines + 1] = "STOCK TICKER: NOT FOUND — tried type names, peripheral.stock, and side-by-side scan"
  end

  -- Probe the stock ticker for a production-request method and a stock-reading
  -- method. We log the candidates but do not call them during startup scan.
  -- probeProductionMethods is also called from readStockFromTicker after the
  -- first successful stock read, so the methods get re-confirmed once we know
  -- the ticker speaks.
  if stockTicker then
    local prodCandidates = {}
    local prodAppend = function(path, fn)
      table.insert(prodCandidates, { path = path, fn = fn })
    end
    for k, v in pairs(stockTicker) do
      if type(k) == "string" and type(v) == "function" then
        local lower = string.lower(k)
        if lower:find("request") or lower:find("create") or lower:find("make") or
           lower:find("produce") or lower:find("craft") or lower:find("build") or
           lower:find("manufacture") then
          prodAppend(k, v)
        end
      elseif type(k) == "string" and type(v) == "table" then
        for nk, nv in pairs(v) do
          if type(nk) == "string" and type(nv) == "function" then
            local lower = string.lower(nk)
            if lower:find("request") or lower:find("create") or lower:find("make") or
               lower:find("produce") or lower:find("craft") or lower:find("build") or
               lower:find("manufacture") then
              prodAppend(k .. "." .. nk, nv)
            end
          elseif type(nk) == "string" and type(nv) == "table" then
            for nnk, nvn in pairs(nv) do
              if type(nnk) == "string" and type(nvn) == "function" then
                local lower = string.lower(nnk)
                if lower:find("request") or lower:find("create") or lower:find("make") or
                   lower:find("produce") or lower:find("craft") or lower:find("build") then
                  prodAppend(k .. "." .. nk .. "." .. nnk, nvn)
                end
              end
            end
          end
        end
      end
    end
    if #prodCandidates > 0 then
      local bestPath = prodCandidates[1].path
      local bestFn = prodCandidates[1].fn
      for _, c in ipairs(prodCandidates) do
        -- Prefer ones whose path contains "request" or "create".
        local lower = string.lower(c.path)
        if lower:find("request") or lower:find("create") then
          bestPath = c.path
          bestFn = c.fn
          break
        end
      end
      productionFn = bestFn
      productionFnPath = bestPath
      diagLines[#diagLines + 1] = "PRODUCTION METHOD: candidate '" .. bestPath .. "' (will probe on first stock read)"
    else
      diagLines[#diagLines + 1] = "PRODUCTION METHOD: none found — stock ticker may not support request-creation"
    end

    -- Also note the strongest stock-reading candidate path for diagnostics.
    local stockCandidates = {}
    for k, v in pairs(stockTicker) do
      if type(k) == "string" and type(v) == "function" then
        local lower = string.lower(k)
        if lower:find("stock") or lower:find("item") or lower:find("list") or lower:find("level") then
          table.insert(stockCandidates, k)
        end
      elseif type(k) == "string" and type(v) == "table" then
        for nk, nv in pairs(v) do
          if type(nk) == "string" and type(nv) == "function" then
            local lower = string.lower(nk)
            if lower:find("stock") or lower:find("item") or lower:find("list") or lower:find("level") then
              table.insert(stockCandidates, k .. "." .. nk)
            end
          end
        end
      end
    end
    if #stockCandidates > 0 then
      stockReadMethodPath = stockCandidates[1]
      for _, p in ipairs(stockCandidates) do
        local lower = string.lower(p)
        if lower:find("stock") then
          stockReadMethodPath = p
          break
        end
      end
      diagLines[#diagLines + 1] = "STOCK READ METHOD: candidate '" .. stockReadMethodPath .. "'"
    end
  end

  -- Print diagnostics to the display and WAIT for keypress
  if #diagLines > 0 then
    if onMonitor and monitor and hasFn(monitor, "clear") then
      pcall(function() monitor.clear() end)
    elseif has_term and has_term_clear then
      pcall(function() _G.term.clear() end)
    end

    dispSetTextScale(0.5)

    local w, h = dispGetSize()
    local y = 1

    dispSetTextColor(colors.yellow)
    dispSetCursorPos(1, y)
    dispWrite("=== PERIPHERAL SCAN ===")
    y = y + 1

    dispSetTextColor(colors.white)
    for _, line in ipairs(diagLines) do
      if y > h then break end
      if string.find(line, "STOCK TICKER") then
        dispSetTextColor(colors.green)
        dispSetCursorPos(1, y)
        dispWrite(">> " .. line)
        dispSetTextColor(colors.white)
      else
        dispSetCursorPos(1, y)
        dispWrite(line)
      end
      y = y + 1
    end

    -- If we found a stock ticker, show its callable methods on the MONITOR
    if stockTicker and y + 2 <= h then
      y = y + 2
      dispSetTextColor(colors.darkGray)
      dispSetCursorPos(1, y)
      dispWrite("Ticker callable methods:")
      y = y + 1
      for k, v in pairs(stockTicker) do
        if type(k) == "string" and type(v) == "function" then
          if string.find(k, "stock", 1, true) or string.find(k, "Stock", 1, true) or
             string.find(k, "item", 1, true) or string.find(k, "Item", 1, true) or
             string.find(k, "list", 1, true) or string.find(k, "List", 1, true) or
             string.find(k, "request", 1, true) or string.find(k, "filter", 1, true) then
            if y > h then break end
            dispSetCursorPos(2, y)
            dispWrite(k .. " (fn)")
            y = y + 1
          end
        elseif type(k) == "string" and type(v) == "table" then
          for nk, nv in pairs(v) do
            if type(nk) == "string" and type(nv) == "function" then
              if y > h then break end
              dispSetCursorPos(2, y)
              dispWrite(k .. "." .. nk .. " (fn)")
              y = y + 1
            end
          end
        end
      end
    end

    if y <= h then
      y = y + 1
      dispSetTextColor(colors.gray)
      dispSetCursorPos(1, y)
      dispWrite("Press any key to continue...")
    end

    -- Mirror to computer's term
    if has_term and has_term_write then
      pcall(function() _G.term.clear() end)
      pcall(function() _G.term.setCursorPos(1, 1) end)
      for i, line in ipairs(diagLines) do
        if i > h then break end
        pcall(function() _G.term.setCursorPos(1, i + 1) end)
        if string.find(line, "STOCK TICKER") then
          dispSetTextColor(colors.green)
          pcall(function() _G.term.write(">> " .. line) end)
          dispSetTextColor(colors.white)
        else
          pcall(function() _G.term.write(line) end)
        end
      end
      local tY = #diagLines + 2
      if stockTicker then
        tY = #diagLines + 2
        pcall(function() _G.term.setCursorPos(1, tY) end)
        dispSetTextColor(colors.gray)
        pcall(function() _G.term.write("Ticker callable methods:") end)
        tY = tY + 1
        for k, v in pairs(stockTicker) do
          if type(k) == "string" and type(v) == "function" then
            if string.find(k, "stock", 1, true) or string.find(k, "Stock", 1, true) or
               string.find(k, "item", 1, true) or string.find(k, "Item", 1, true) or
               string.find(k, "list", 1, true) or string.find(k, "List", 1, true) or
               string.find(k, "request", 1, true) or string.find(k, "filter", 1, true) then
              pcall(function() _G.term.setCursorPos(2, tY) end)
              pcall(function() _G.term.write(k .. " (fn) end)")
              tY = tY + 1
            end
          elseif type(k) == "string" and type(v) == "table" then
            for nk, nv in pairs(v) do
              if type(nk) == "string" and type(nv) == "function" then
                pcall(function() _G.term.setCursorPos(2, tY) end)
                pcall(function() _G.term.write(k .. "." .. nk .. " (fn) end)")
                tY = tY + 1
              end
            end
          end
        end
      end
      local promptY = math.max(tY + 1, #diagLines + 2)
      if promptY < h then
        pcall(function() _G.term.setCursorPos(1, promptY + 1) end)
        dispSetTextColor(colors.gray)
        pcall(function() _G.term.write("Press any key to continue...") end)
        if has_term_flush then pcall(function() _G.term.flush() end) end
      end
    end

    local evt = os.pullEventRaw("key")
  end
end

-- ---------------------------------------------------------------------------
-- READ STOCK FROM TICKER — comprehensive probing
-- ---------------------------------------------------------------------------

local function readStockFromTicker()
  stockCache = {}
  if not stockTicker then return end

  -- Debug helper: prints to computer's term
  local function debugPrint(label, result)
    local desc
    if type(result) == "table" then
      local keys = {}
      local count = 0
      for k, v in pairs(result) do
        count = count + 1
        if count <= 5 then
          if type(v) == "table" then
            local subkeys = {}
            local subc = 0
            for sk, sv in pairs(v) do
              subc = subc + 1
              if subc <= 3 then subkeys[#subkeys + 1] = sk end
            end
            keys[#keys + 1] = k .. "={ " .. table.concat(subkeys, ",") .. " }"
          else
            keys[#keys + 1] = k .. "=" .. tostring(v)
          end
        end
      end
      if count > 5 then keys[#keys + 1] = "...(" .. count .. " keys)" end
      desc = "table{ " .. table.concat(keys, ", ") .. " }"
    elseif type(result) == "string" then
      desc = "string: " .. result
    elseif type(result) == "number" then
      desc = "number: " .. result
    else
      desc = "type=" .. type(result)
    end
    print("[stock-debug] " .. label .. ": " .. desc)
  end

  -- Probe function: try calling a function, report result
  local function tryCall(fn, label, ...)
    if type(fn) ~= "function" then
      print("[stock-probe] " .. label .. " (not a function)")
      return false, nil
    end
    local ok, result = pcall(fn, ...)
    if not ok then
      print("[stock-probe] " .. label .. " FAILED: " .. tostring(result))
      return false, nil
    end
    print("[stock-probe] " .. label .. " OK — type: " .. type(result))
    if type(result) == "table" then
      local keys = {}
      local kcount = 0
      for k, v in pairs(result) do
        kcount = kcount + 1
        if kcount <= 8 then
          local vdesc
          if type(v) == "table" then
            local sub = {}
            local sc = 0
            for sk, sv in pairs(v) do
              sc = sc + 1; if sc <= 3 then sub[#sub + 1] = sk end
            end
            vdesc = "{" .. table.concat(sub, ",") .. "}"
          elseif type(v) == "string" then
            vdesc = "\"" .. v .. "\""
          else
            vdesc = tostring(v)
          end
          keys[#keys + 1] = k .. "=" .. vdesc
        end
      end
      if kcount > 8 then keys[#keys + 1] = "...(" .. kcount .. " keys)" end
      print("[stock-probe]   keys: " .. table.concat(keys, ", "))
    end
    return true, result
  end

  local function addItem(id, count)
    if id ~= "" and count and count > 0 then
      stockCache[id] = (stockCache[id] or 0) + count
      print("[stock-probe]   added: " .. id .. " = " .. count .. " (total: " .. stockCache[id] .. ")")
    end
  end

  -- First: enumerate all callable methods for debugging
  print("[stock-probe] === STOCK TICKER PROBE ===")
  print("[stock-probe] type of stockTicker: " .. type(stockTicker))

  -- Enumerate all functions on the ticker (top-level + nested)
  local seen = {}
  local function listFuncs(tbl, prefix)
    if type(tbl) ~= "table" or seen[tbl] then return end
    seen[tbl] = true
    for k, v in pairs(tbl) do
      local full = prefix and (prefix .. "." .. k) or k
      if type(v) == "function" then
        print("[stock-probe] fn: " .. full)
      elseif type(v) == "table" then
        print("[stock-probe] tbl: " .. full)
        listFuncs(v, full)
      end
    end
  end
  listFuncs(stockTicker, nil)

  -- Collect candidate functions
  local candidates = {}
  for k, v in pairs(stockTicker) do
    if type(k) == "string" and type(v) == "function" then
      if string.lower(k):find("stock") or string.lower(k):find("item") or string.lower(k):find("list") then
        table.insert(candidates, { path = k, fn = v })
      end
    elseif type(k) == "string" and type(v) == "table" then
      local lower = string.lower(k)
      if lower:find("stock") or lower:find("request") or lower:find("filter") or lower:find("item") then
        for nk, nv in pairs(v) do
          if type(nk) == "string" and type(nv) == "function" then
            table.insert(candidates, { path = k .. "." .. nk, fn = nv })
          elseif type(nk) == "string" and type(nv) == "table" then
            for nnk, nvn in pairs(nv) do
              if type(nnk) == "string" and type(nvn) == "function" then
                table.insert(candidates, { path = k .. "." .. nk .. "." .. nnk, fn = nvn })
              end
            end
          end
        end
      end
    end
  end
  -- Also check .stock sub-table
  if stockTicker.stock and type(stockTicker.stock) == "table" then
    for k, v in pairs(stockTicker.stock) do
      if type(k) == "string" and type(v) == "function" then
        table.insert(candidates, { path = "stock." .. k, fn = v })
      elseif type(k) == "string" and type(v) == "table" then
        for nk, nv in pairs(v) do
          if type(nk) == "string" and type(nv) == "function" then
            table.insert(candidates, { path = "stock." .. k .. "." .. nk, fn = nv })
          elseif type(nk) == "string" and type(nv) == "table" then
            for nnk, nvn in pairs(nv) do
              if type(nnk) == "string" and type(nvn) == "function" then
                table.insert(candidates, { path = "stock." .. k .. "." .. nk .. "." .. nnk, fn = nvn })
              end
            end
          end
        end
      end
    end
  end
  -- Also check .requestFiltered sub-table
  if stockTicker.requestFiltered and type(stockTicker.requestFiltered) == "table" then
    for k, v in pairs(stockTicker.requestFiltered) do
      if type(k) == "string" and type(v) == "function" then
        table.insert(candidates, { path = "requestFiltered." .. k, fn = v })
      elseif type(k) == "string" and type(v) == "table" then
        for nk, nv in pairs(v) do
          if type(nk) == "string" and type(nv) == "function" then
            table.insert(candidates, { path = "requestFiltered." .. k .. "." .. nk, fn = nv })
          elseif type(nk) == "string" and type(nv) == "table" then
            for nnk, nvn in pairs(nv) do
              if type(nnk) == "string" and type(nvn) == "function" then
                table.insert(candidates, { path = "requestFiltered." .. k .. "." .. nk .. "." .. nnk, fn = nvn })
              end
            end
          end
        end
      end
    end
  end

  print("[stock-probe] candidates:")
  for _, c in ipairs(candidates) do
    print("[stock-probe]   " .. c.path)
    local ok, result = tryCall(c.fn, c.path)
    if ok and result and type(result) == "table" then
      -- Try to extract items
      if result.items and type(result.items) == "table" then
        for _, item in ipairs(result.items) do
          local id = item.id or item.name or item.displayName or item[1] or ""
          local count = item.count or item.size or item.amount or item[2] or 0
          addItem(id, count)
        end
        if next(stockCache) then
          print("[stock-probe] extracted items, done.")
          return
        end
      elseif result[1] and type(result[1]) == "table" then
        for _, item in ipairs(result) do
          local id = item.id or item.name or item.displayName or item[1] or ""
          local count = item.count or item.size or item.amount or item[2] or 0
          addItem(id, count)
        end
        if next(stockCache) then
          print("[stock-probe] extracted items, done.")
          return
        end
      elseif result.id or result.name then
        local id = result.id or result.name or result.displayName or ""
        local count = result.count or result.size or result.amount or 1
        addItem(id, count)
        if next(stockCache) then
          print("[stock-probe] extracted item, done.")
          return
        end
      else
        -- key-value?
        for name, count in pairs(result) do
          if type(count) == "number" and count > 0 then
            addItem(name, count)
          end
        end
        if next(stockCache) then
          print("[stock-probe] extracted items via key-value, done.")
          return
        end
      end
    end
  end

  -- Try flat methods on stockTicker itself
  for _, fnName in ipairs({ "getStock", "getStockLevels", "getStockItems", "getItems", "getItem", "getAllItems" }) do
    if stockTicker[fnName] and type(stockTicker[fnName]) == "function" then
      local ok, result = tryCall(stockTicker[fnName], fnName .. "()")
      if ok and result and type(result) == "table" then
        if result.items and type(result.items) == "table" then
          for _, item in ipairs(result.items) do
            local id = item.id or item.name or item.displayName or item[1] or ""
            local count = item.count or item.size or item.amount or item[2] or 0
            addItem(id, count)
          end
          if next(stockCache) then
            print("[stock-probe] extracted from " .. fnName .. "() items, done.")
            return
          end
        elseif result[1] and type(result[1]) == "table" then
          for _, item in ipairs(result) do
            local id = item.id or item.name or item.displayName or item[1] or ""
            local count = item.count or item.size or item.amount or item[2] or 0
            addItem(id, count)
          end
          if next(stockCache) then
            print("[stock-probe] extracted from " .. fnName .. "() array, done.")
            return
          end
        elseif result.id or result.name then
          local id = result.id or result.name or result.displayName or ""
          local count = result.count or result.size or result.amount or 1
          addItem(id, count)
          if next(stockCache) then
            print("[stock-probe] extracted from " .. fnName .. "() single, done.")
            return
          end
        else
          for name, count in pairs(result) do
            if type(count) == "number" and count > 0 then
              addItem(name, count)
            end
          end
          if next(stockCache) then
            print("[stock-probe] extracted from " .. fnName .. "() key-value, done.")
            return
          end
        end
      end
    end
  end

  if not next(stockCache) then
    print("[stock-probe] ERROR: no stock data extracted from any method")
  else
    print("[stock-probe] stockCache:")
    for id, count in pairs(stockCache) do
      print("[stock-probe]   " .. id .. ": " .. count)
    end
  end
end

-- ---------------------------------------------------------------------------
-- MENU RENDERING
-- ---------------------------------------------------------------------------

local function drawHeader(title)
  local w, h = termGetSize()
  termClear()
  termSetTextScale(1.0)
  termSetBackgroundColor(colors.black)
  termSetTextColor(colors.yellow)
  local titleLen = #title
  local pad = math.floor((w - titleLen) / 2)
  if pad < 0 then pad = 0 end
  termSetCursorPos(1, 1)
  termWrite(string.rep("=", w))
  termWriteLn()
  termSetCursorPos(1, 2)
  termWrite(string.rep(" ", pad) .. title .. string.rep(" ", w - pad - titleLen))
  termWriteLn()
  termWrite(string.rep("=", w))
  termWriteLn()
end

local dashboardBlinkPhase = 0
local lastDashboardDrawY = 0

-- PRODUCTION REQUEST — talk to the stock ticker
-- ---------------------------------------------------------------------------
--
-- requestProductionForGauges(gauges) asks the stock ticker to produce enough
-- of each item to cover the shortfall on every working gauge. The ticker's API
-- varies by mod; we try the production method we discovered during scanning,
-- passing item name + count. If the method has a different signature we log a
-- diagnostic and move on.

local function requestProductionForGauges(gauges)
  if not productionFn or type(productionFn) ~= "function" then
    return
  end
  for _, g in ipairs(gauges) do
    if gaugeWorking(g) then
      local stock = stockForGauge(g)
      local needed = neededCount(g)
      local shortfall = needed - stock
      if shortfall > 0 then
        local itemName = gaugeItemName(g)
        local ok, err = pcall(productionFn, itemName, shortfall)
        if not ok then
          print("[prod] requestProduction failed for " .. itemName .. " (" .. shortfall .. "): " .. tostring(err))
        else
          print("[prod] requested " .. shortfall .. " of " .. itemName .. " for gauge '" .. g.name .. "'")
        end
      end
    end
  end
end
local function drawDashboard(w, startY)
  local h = 19  -- default; will be corrected below
  local _, realH = dispGetSize()
  if realH and realH > 0 then h = realH end

  local y = startY
  dispSetTextColor(colors.white)
  dispSetBackgroundColor(colors.black)
  dispSetCursorPos(1, y)
  dispWrite("WORKING GAUGES (monitor)")
  y = y + 1

  local gauges = sortedGauges()
  local anyWorking = false
  local maxLines = h - y - 3  -- leave room for total + hint + bottom bar

  -- First pass: working gauges
  for _, g in ipairs(gauges) do
    if gaugeWorking(g) then
      anyWorking = true
      if y >= h - 2 then break end  -- leave room for total + hint
      local stock = stockForGauge(g)
      local needed = neededCount(g)
      local shortName = g.name
      if #shortName > w - 20 then
        shortName = string.sub(shortName, 1, w - 20)
      end
      local lineText = string.format("%s: %d / %d", shortName, stock, needed)
      local displayText = lineText .. string.rep(" ", math.max(1, w - #lineText))

      if stock >= needed then
        dispSetTextColor(colors.green)
      elseif stock > 0 then
        dispSetTextColor(colors.yellow)
      else
        dispSetTextColor(colors.red)
      end
      dispSetBackgroundColor(colors.black)
      dispSetCursorPos(2, y)
      dispWrite(displayText)
      y = y + 1
    end
  end

  -- Total line
  if y < h - 1 then
    local totalStock = countTotalStock()
    local totalNeeded = countTotalNeeded()
    local totalText = string.format("TOTAL: %d / %d", totalStock, totalNeeded)
    local totalDisplay = totalText .. string.rep(" ", math.max(1, w - #totalText))
    if totalStock >= totalNeeded then
      dispSetTextColor(colors.green)
    elseif totalStock > 0 then
      dispSetTextColor(colors.yellow)
    else
      dispSetTextColor(colors.red)
    end
    dispSetBackgroundColor(colors.black)
    dispSetCursorPos(2, y)
    dispWrite(totalDisplay)
    y = y + 1
  end

  -- Production status / shortfall hint
  if y < h then
    local shortfall = 0
    for _, g in ipairs(gauges) do
      if gaugeWorking(g) then
        local s = stockForGauge(g)
        local n = neededCount(g)
        if s < n then
          shortfall = shortfall + (n - s)
        end
      end
    end
    if shortfall > 0 then
      dispSetTextColor(colors.red)
      dispSetCursorPos(2, y)
      local hint = "SHORTFALL: " .. shortfall .. " — requesting production..."
      if #hint > w - 2 then hint = string.sub(hint, 1, w - 2) end
      dispWrite(hint .. string.rep(" ", math.max(1, w - #hint)))
      y = y + 1
      -- Trigger production request for all shortfalls
      requestProductionForGauges(gauges)
    else
      if anyWorking then
        dispSetTextColor(colors.green)
        dispSetCursorPos(2, y)
        local okTxt = "All gauges covered — no shortfall"
        if #okTxt > w - 2 then okTxt = string.sub(okTxt, 1, w - 2) end
        dispWrite(okTxt .. string.rep(" ", math.max(1, w - #okTxt)))
        y = y + 1
      end
    end
  end

  -- Inactive gauges at the bottom
  local inactiveY = h - 1
  if y < inactiveY then
    y = inactiveY
  end
  dispSetTextColor(colors.gray)
  dispSetBackgroundColor(colors.black)
  dispSetCursorPos(2, y)
  local inactiveList = {}
  for _, g in ipairs(gauges) do
    if not gaugeWorking(g) then
      inactiveList[#inactiveList + 1] = g.name
    end
  end
  if #inactiveList > 0 then
    local txt = "Inactive: " .. table.concat(inactiveList, ", ")
    if #txt > w - 2 then txt = string.sub(txt, 1, w - 2) end
    dispWrite(txt)
  end

  lastDashboardDrawY = y
end

local function countVisibleDashboardLines()
  -- Approximate: header(1) + gauges(up to ~8) + total(1) + hint(1) + inactive(1)
  local gauges = sortedGauges()
  local workingCount = 0
  for _, g in ipairs(gauges) do
    if gaugeWorking(g) then
      workingCount = workingCount + 1
    end
  end
  return 1 + math.min(workingCount, 8) + (workingCount > 0 and 1 or 0) + 1 + 1
end

local function drawMainMenu()
  -- Render the main menu on the computer term (always), and if a monitor is
  -- attached also render the live factory gauge dashboard on the monitor.
  -- This keeps the menu and the gauge list visible at the same time.

  -- --- Computer term: menu + stock overview ---
  local tw, th = termGetSize()
  termClear()
  drawHeader("FACTORY GAUGE")

  local items = {
    { text = "Create factory gauge" },
    { text = "Working gauges" },
    { text = "Frog Port" },
    { text = "Settings" },
  }

  local ty = 4
  for i, item in ipairs(items) do
    local isSelected = (i == selectedIndex)
    if isSelected then
      termSetTextColor(colors.white)
    else
      termSetTextColor(colors.gray)
    end
    termSetCursorPos(2, ty)
    if isSelected then
      termWrite("> " .. item.text .. string.rep(" ", tw - 4 - #item.text))
    else
      termWrite("  " .. item.text .. string.rep(" ", tw - 4 - #item.text))
    end
    ty = ty + 1
  end

  -- Stock overview on the computer term
  ty = ty + 1
  termSetTextColor(colors.white)
  termSetCursorPos(1, ty)
  termWrite("STOCK:")
  ty = ty + 1
  if next(stockCache) then
    local itemList = {}
    for id, count in pairs(stockCache) do
      table.insert(itemList, { id = id, count = count })
    end
    table.sort(itemList, function(a, b) return a.count > b.count end)
    local show = math.min(#itemList, 6)
    for i = 1, show do
      local short = string.match(itemList[i].id, "^%w+:(.+)$") or itemList[i].id
      termSetCursorPos(2, ty)
      termWrite(i .. ". " .. short .. ": " .. itemList[i].count)
      ty = ty + 1
    end
    if #itemList > show then
      termSetCursorPos(2, ty)
      termWrite("... and " .. (#itemList - show) .. " more")
      ty = ty + 1
    end
  else
    termSetCursorPos(2, ty)
    termSetTextColor(colors.gray)
    termWrite("  (no stock data -- check stock ticker connection)")
    ty = ty + 1
  end

  -- Usage hint at the bottom of the computer term
  termSetCursorPos(1, ty + 1)
  termSetTextColor(colors.darkGray)
  termSetBackgroundColor(colors.black)
  termWrite("W/S: navigate  |  Enter: select  |  Q: quit")
  termFlush()

  -- --- Monitor: live factory gauge dashboard ---
  if onMonitor and monitor then
    local mw, mh = dispGetSize()
    dispClear()
    dispSetTextScale(1.0)
    dispSetBackgroundColor(colors.black)
    dispSetTextColor(colors.yellow)
    local titleLen = #"FACTORY GAUGE (monitor)"
    local pad = math.floor((mw - titleLen) / 2)
    if pad < 0 then pad = 0 end
    dispSetCursorPos(1, 1)
    dispWrite(string.rep("=", mw))
    dispWriteLn()
    dispSetCursorPos(1, 2)
    dispWrite(string.rep(" ", pad) .. "FACTORY GAUGE (monitor)" .. string.rep(" ", mw - pad - titleLen))
    dispWriteLn()
    dispWrite(string.rep("=", mw))
    dispWriteLn()
    drawDashboard(mw, 4)
  end
end


-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- FROG PORT MANAGEMENT
-- ---------------------------------------------------------------------------

local function addFrogPort()
  termClear()
  drawHeader("ADD FROG PORT")
  termSetTextColor(colors.white)
  termSetCursorPos(1, 3)
  termWriteLn("Enter the name of the new Frog Port:")
  termWriteLn("")

  local name = readlnWithEcho("> ")
  if name and name ~= "" then
    name = string.match(name, "^%s*(.-)%s*$")
    if name ~= "" then
      frogPorts[#frogPorts + 1] = name
      termWriteLn("")
      termWriteLn("Added: " .. name)
    else
      termWriteLn("")
      termWriteLn("(empty name — not added)")
    end
  else
    termWriteLn("")
    termWriteLn("(cancelled)")
  end
  termWriteLn("")
  termWriteLn("(press any key to continue...)")
  readkey()
end

local function removeFrogPort()
  if #frogPorts == 0 then
    termClear()
    drawHeader("REMOVE FROG PORT")
    termSetTextColor(colors.gray)
    termSetCursorPos(1, 3)
    termWriteLn("No Frog Ports to remove.")
    termWriteLn("")
    termWriteLn("(press any key to continue...)")
    readkey()
    return
  end

  -- Show the numbered list
  termClear()
  drawHeader("REMOVE FROG PORT")
  termSetTextColor(colors.white)
  termSetCursorPos(1, 3)
  termWriteLn("Select a Frog Port to remove:")
  termWriteLn("")

  for i, name in ipairs(frogPorts) do
    termSetCursorPos(2, 4 + i - 1)
    termSetTextColor(colors.gray)
    termWrite(i .. ". " .. name)
  end

  local bottomY = 4 + #frogPorts + 1
  termSetCursorPos(1, bottomY)
  termSetTextColor(colors.darkGray)
  termWriteLn("")
  termWriteLn("(type the number of the port to remove)")

  local input = readlnWithEcho("> ")
  if input then
    local num = tonumber(input)
    if num and num >= 1 and num <= #frogPorts then
      local removed = table.remove(frogPorts, num)
      termWriteLn("")
      termWriteLn("Removed: " .. removed)
    else
      termWriteLn("")
      termWriteLn("Invalid number — enter a number from 1 to " .. #frogPorts)
    end
  else
    termWriteLn("")
    termWriteLn("(cancelled)")
  end
  termWriteLn("")
  termWriteLn("(press any key to continue...)")
  readkey()
end

local function showFrogPortList()
  if #frogPorts == 0 then
    termClear()
    drawHeader("FROG PORTS")
    termSetTextColor(colors.gray)
    termSetCursorPos(1, 3)
    termWriteLn("No Frog Ports configured.")
    termWriteLn("")
    termWriteLn("(press any key to continue...)")
    readkey()
    return
  end

  local listNeedsRedraw = true

  while true do
    if listNeedsRedraw then
      termClear()
      drawHeader("FROG PORTS")

      local listY = 3
      for i, name in ipairs(frogPorts) do
        local isSelected = (i == selectedIndex)
        if isSelected then
          termSetTextColor(colors.white)
          termSetBackgroundColor(colors.blue)
        else
          termSetTextColor(colors.gray)
          termSetBackgroundColor(colors.black)
        end
        termSetCursorPos(2, listY)
        if isSelected then
          termWrite("> " .. i .. ". " .. name .. " ")
        else
          termWrite("  " .. i .. ". " .. name .. " ")
        end
        listY = listY + 1
      end

      local bottomY = listY + 1
      termSetCursorPos(1, bottomY)
      termSetTextColor(colors.darkGray)
      termSetBackgroundColor(colors.black)
      termWriteLn("")
      termSetCursorPos(2, bottomY + 1)
      termWrite("A. Add Frog Port")
      termSetCursorPos(2, bottomY + 2)
      termWrite("R. Remove Frog Port")
      termSetCursorPos(2, bottomY + 3)
      termWrite("B. Back")

      listNeedsRedraw = false
    end

    -- readkey() returns a lowercase string label; compare only against strings.
    local key = readkey()
    if not key then break end

    local isUp    = (key == "w" or key == "up")
    local isDown  = (key == "s" or key == "down")
    local isEsc   = (key == "q" or key == "escape")
    local isEnter = (key == "enter")
    local isA     = (key == "a")
    local isR     = (key == "r")
    local isB     = (key == "b")

    if isEsc or isB or isEnter then
      break

    elseif isUp then
      if selectedIndex > 1 then
        selectedIndex = selectedIndex - 1
      else
        selectedIndex = #frogPorts
      end
      listNeedsRedraw = true

    elseif isDown then
      if selectedIndex < #frogPorts then
        selectedIndex = selectedIndex + 1
      else
        selectedIndex = 1
      end
      listNeedsRedraw = true

    elseif isA then
      addFrogPort()
      -- After adding, clamp selectedIndex to the new list size.
      if selectedIndex > #frogPorts then
        selectedIndex = #frogPorts
      end
      listNeedsRedraw = true

    elseif isR then
      removeFrogPort()
      -- After removing, clamp selectedIndex.
      if #frogPorts > 0 and selectedIndex > #frogPorts then
        selectedIndex = #frogPorts
      elseif #frogPorts == 0 then
        -- List empty — exit the modal.
        break
      end
      listNeedsRedraw = true
    end
    -- Any other key is ignored and we loop again.
  end
end

-- ---------------------------------------------------------------------------
-- SETTINGS SCREEN
-- ---------------------------------------------------------------------------

local function showSettings()
  termClear()
  drawHeader("SETTINGS")

  termSetTextColor(colors.white)
  termSetCursorPos(1, 3)
  termWriteLn("SETTINGS")
  termWriteLn("")
  termSetTextColor(colors.gray)
  termSetCursorPos(1, 5)
  termWriteLn("  Auto-scan peripherals:  Enabled")
  termSetCursorPos(1, 6)
  termWriteLn("  Default Frog Ports:     " .. (#frogPorts > 0 and table.concat(frogPorts, ", ") or "none"))
  termSetCursorPos(1, 7)
  termWriteLn("  Monitor auto-detect:    " .. (onMonitor and "Enabled" or "Disabled"))
  termSetCursorPos(1, 8)
  termWriteLn("  Stock ticker:           " .. (stockTicker and "Connected" or "Not found"))
  termSetCursorPos(1, 9)
  if next(stockCache) then
    termSetTextColor(colors.white)
    termWriteLn("  Items in stock:         " .. countTable(stockCache))
  else
    termSetTextColor(colors.gray)
    termWriteLn("  Items in stock:         0")
  end
  termSetCursorPos(1, 11)
  termSetTextColor(colors.darkGray)
  termWriteLn("")
  termWriteLn("(press any key to return...)")
  readkey()
end

-- ---------------------------------------------------------------------------
-- CREATE FACTORY GAUGE SCREEN
-- ---------------------------------------------------------------------------
-- showCreateFactoryGauge() renders the create-gauge form. On the computer term
-- the user types a name, selects a frog port by number, enters a quantity (1-100
-- via readlnWithEcho), and chooses stack or item mode. On the monitor we show
-- the same form but read input via readlnWithEcho (keyboard still goes through
-- the computer). After creating, the gauge is added to factoryGauges and the
-- stock ticker is refreshed.

local function showCreateFactoryGauge()
  local w, h = termGetSize()
  termClear()
  drawHeader("CREATE FACTORY GAUGE")

  local y = 3
  termSetTextColor(colors.white)
  termSetCursorPos(1, y)
  termWrite("Name this factory gauge:")
  y = y + 1
  local name = readlnWithEcho("> ")

  if not name or name == "" then
    y = y + 1
    termSetTextColor(colors.gray)
    termSetCursorPos(1, y)
    termWriteLn("(cancelled)")
    y = y + 2
    termSetTextColor(colors.darkGray)
    termWriteLn("(press any key to return...)")
    readkey()
    return
  end
  name = string.match(name, "^%s*(.-)%s*$")
  if name == "" then
    y = y + 1
    termSetTextColor(colors.gray)
    termSetCursorPos(1, y)
    termWriteLn("(empty name — cancelled)")
    y = y + 2
    termSetTextColor(colors.darkGray)
    termWriteLn("(press any key to return...)")
    readkey()
    return
  end
  -- Reject duplicates
  if findGaugeByName(name) then
    y = y + 1
    termSetTextColor(colors.red)
    termSetCursorPos(1, y)
    termWriteLn("A gauge with that name already exists.")
    y = y + 2
    termSetTextColor(colors.darkGray)
    termWriteLn("(press any key to return...)")
    readkey()
    return
  end

  -- Frog port selection
  y = y + 1
  termSetTextColor(colors.white)
  termSetCursorPos(1, y)
  termWrite("Assign to Frog Port:")
  y = y + 1
  if #frogPorts == 0 then
    termSetTextColor(colors.gray)
    termSetCursorPos(2, y)
    termWriteLn("(no frog ports configured — go to Frog Port menu)")
    y = y + 1
    termSetTextColor(colors.white)
    termSetCursorPos(1, y)
    termWrite("Using default (no port):")
    y = y + 1
  else
    for i, portName in ipairs(frogPorts) do
      termSetCursorPos(2, y)
      termWrite(i .. ". " .. portName)
      y = y + 1
    end
  end

  local portChoice = readlnWithEcho("> ")
  local chosenPort = ""
  if portChoice and #frogPorts > 0 then
    local num = tonumber(portChoice)
    if num and num >= 1 and num <= #frogPorts then
      chosenPort = frogPorts[num]
    else
      -- If they typed something that isn't a valid number, just leave it blank.
      termSetTextColor(colors.gray)
      termSetCursorPos(1, y)
      termWriteLn("(invalid selection — no port assigned)")
      y = y + 1
    end
  end

  -- Quantity (1-100)
  y = y + 1
  termSetTextColor(colors.white)
  termSetCursorPos(1, y)
  termWrite("Quantity needed (1-100):")
  y = y + 1
  local qtyChoice = readlnWithEcho("> ")
  local qty = tonumber(qtyChoice)
  if not qty or qty < 1 or qty > 100 then
    qty = 10
    termSetTextColor(colors.gray)
    termSetCursorPos(1, y)
    termWriteLn("(invalid — defaulting to 10)")
    y = y + 1
  end

  -- Mode: stack or item
  y = y + 1
  termSetTextColor(colors.white)
  termSetCursorPos(1, y)
  termWrite("Mode: 1 = stack  2 = item")
  y = y + 1
  local modeChoice = readlnWithEcho("> ")
  local mode = "stack"
  local modeNum = tonumber(modeChoice)
  if modeNum == 2 then
    mode = "item"
  elseif modeNum ~= 1 and modeNum ~= nil then
    termSetTextColor(colors.gray)
    termSetCursorPos(1, y)
    termWriteLn("(invalid — defaulting to stack)")
    y = y + 1
  end

  -- Build the gauge record
  local gauge = {
    name = name,
    frogPort = chosenPort,
    qty = qty,
    mode = mode,
    inactive = false,
  }
  factoryGauges[#factoryGauges + 1] = gauge

  -- Confirm
  y = y + 1
  termSetTextColor(colors.green)
  termSetCursorPos(1, y)
  termWriteLn("Created: " .. gaugeDisplayName(gauge))
  termSetTextColor(colors.gray)
  termSetCursorPos(1, y + 1)
  if chosenPort ~= "" then
    termWriteLn("  Frog Port: " .. chosenPort)
  else
    termWriteLn("  Frog Port: (none)")
  end
  termWriteLn("  Qty: " .. qty .. " (" .. mode .. ")")
  y = y + 3
  termSetTextColor(colors.darkGray)
  termWriteLn("(press any key to return...)")
  readkey()
end

-- ---------------------------------------------------------------------------
-- SHOW WORKING GAUGES LIST
-- ---------------------------------------------------------------------------
--
-- showWorkingGaugesList() shows every gauge in factoryGauges sorted alphabetically.
-- Selecting one by number opens the gauge editor (showGaugeEditor) where you can
-- change qty, mode, inactive status, or delete the gauge. Press B to go back.

local function showWorkingGaugesList()
  local w, h = termGetSize()
  if #factoryGauges == 0 then
    termClear()
    drawHeader("WORKING GAUGES")
    termSetTextColor(colors.gray)
    termSetCursorPos(1, 3)
    termWriteLn("No factory gauges created yet.")
    termWriteLn("")
    termSetCursorPos(1, 5)
    termWriteLn("Go to 'Create factory gauge' to add one.")
    termWriteLn("")
    termSetTextColor(colors.darkGray)
    termWriteLn("(press any key to return...)")
    readkey()
    return
  end

  local sorted = sortedGauges()
  local selectedIdx = 1
  local needsRedraw = true

  while true do
    if needsRedraw then
      termClear()
      drawHeader("WORKING GAUGES")
      local y = 3
      for i, g in ipairs(sorted) do
        local isSel = (i == selectedIdx)
        if isSel then
          termSetTextColor(colors.white)
          termSetBackgroundColor(colors.blue)
        else
          termSetTextColor(colors.gray)
          termSetBackgroundColor(colors.black)
        end
        termSetCursorPos(2, y)
        local status = gaugeWorking(g) and "ON " or "OFF"
        local txt = string.format("%d. %s [%s] %s", i, g.name, status,
                                   g.frogPort ~= "" and ("-> " .. g.frogPort) or "")
        local padded = txt .. string.rep(" ", math.max(1, w - 4 - #txt))
        if isSel then
          termWrite("> " .. padded)
        else
          termWrite("  " .. padded)
        end
        y = y + 1
      end
      termSetTextColor(colors.darkGray)
      termSetBackgroundColor(colors.black)
      termSetCursorPos(1, y + 1)
      termWrite("W/S: navigate  |  Enter: edit  |  B: back")
      needsRedraw = false
    end

    -- Use readkey() for sub-screen input (monitor + term).
    local key = readkey()
    if not key then break end

    local isUp    = (key == "w" or key == "up")
    local isDown  = (key == "s" or key == "down")
    local isEsc   = (key == "q" or key == "escape")
    local isEnter = (key == "enter")
    local isB     = (key == "b")

    if isEsc or isB then
      break
    elseif isEnter then
      local g = sorted[selectedIdx]
      if g then
        showGaugeEditor(g)
        -- After editing, the gauge may have been deleted; re-sort.
        sorted = sortedGauges()
        if #sorted == 0 then
          break
        end
        -- Clamp selectedIdx
        if selectedIdx > #sorted then
          selectedIdx = #sorted
        end
        needsRedraw = true
      end
    elseif isUp then
      if selectedIdx > 1 then
        selectedIdx = selectedIdx - 1
      else
        selectedIdx = #sorted
      end
      needsRedraw = true
    elseif isDown then
      if selectedIdx < #sorted then
        selectedIdx = selectedIdx + 1
      else
        selectedIdx = 1
      end
      needsRedraw = true
    end
  end
end

-- ---------------------------------------------------------------------------
-- GAUGE EDITOR
-- ---------------------------------------------------------------------------
--
-- showGaugeEditor(g) lets the user edit one gauge: qty (1-100), mode
-- (stack/item), inactive toggle, or delete. Changes are applied immediately
-- to the gauge record. Press B to return to the list.

local function showGaugeEditor(g)
  local w, h = termGetSize()
  while true do
    termClear()
    drawHeader("EDIT: " .. g.name)

    local y = 3
    termSetTextColor(colors.white)
    termSetCursorPos(1, y)
    termWrite("Name: " .. g.name)
    y = y + 1

    local statusText = gaugeWorking(g) and "ACTIVE" or "INACTIVE"
    local statusColor = gaugeWorking(g) and colors.green or colors.yellow
    termSetTextColor(statusColor)
    termSetCursorPos(1, y)
    termWrite("Status: " .. statusText)
    y = y + 1

    if g.frogPort ~= "" then
      termSetCursorPos(1, y)
      termWrite("Frog Port: " .. g.frogPort)
      y = y + 1
    else
      termSetCursorPos(1, y)
      termWrite("Frog Port: (none)")
      y = y + 1
    end

    local neededTxt = (g.mode == "stack" and (g.qty .. " stacks = " .. (g.qty * 64) .. " items"))
                      or (g.qty .. " items")
    termSetCursorPos(1, y)
    termWrite("Needed: " .. g.qty .. " " .. g.mode .. "s  (" .. neededTxt .. ")")
    y = y + 1

    local stock = stockForGauge(g)
    termSetCursorPos(1, y)
    if stock >= neededCount(g) then
      termSetTextColor(colors.green)
    elseif stock > 0 then
      termSetTextColor(colors.yellow)
    else
      termSetTextColor(colors.red)
    end
    termWrite("On stock: " .. stock)
    y = y + 2

    termSetTextColor(colors.darkGray)
    termWriteLn("")
    termSetCursorPos(1, y)
    termWrite("1. Edit quantity")
    y = y + 1
    termWrite("2. Toggle stack/item mode")
    y = y + 1
    termWrite("3. Toggle active/inactive")
    y = y + 1
    termWrite("4. Delete this gauge")
    y = y + 2
    termSetTextColor(colors.darkGray)
    termWriteLn("(press any key to return...)")

    local key = readkey()
    if not key then break end

    if key == "1" then
      local qtyChoice = readlnWithEcho("New qty (1-100): ")
      local nq = tonumber(qtyChoice)
      if nq and nq >= 1 and nq <= 100 then
        g.qty = nq
      else
        termSetTextColor(colors.gray)
        termWriteLn("(invalid — unchanged)")
        readkey()
      end
    elseif key == "2" then
      g.mode = (g.mode == "stack" and "item" or "stack")
    elseif key == "3" then
      g.inactive = not g.inactive
    elseif key == "4" then
      -- Delete
      for i, og in ipairs(factoryGauges) do
        if og == g then
          table.remove(factoryGauges, i)
          break
        end
      end
      termClear()
      drawHeader("GAUGE DELETED")
      termSetTextColor(colors.gray)
      termSetCursorPos(1, 3)
      termWriteLn("Gauge deleted: " .. g.name)
      termWriteLn("")
      termSetTextColor(colors.darkGray)
      termWriteLn("(press any key to return...)")
      readkey()
      return
    else
      -- Any other key = return
      break
    end
  end
end

local function countTable(t)
  if type(t) ~= "table" then return 0 end
  local c = 0
  for _ in pairs(t) do c = c + 1 end
  return c
end

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

  -- Read initial stock from ticker — results go to computer's term via print()
  readStockFromTicker()

  if onMonitor then
    dispClear()
    dispSetCursorPos(1, 1)
    dispSetTextColor(colors.green)
    dispWrite("Monitor ready. Keyboard input goes through the")
    dispWriteLn("computer — use the computer's keyboard.")
    sleep(2)
  end

  -- Start the auto-refresh timer for the monitor dashboard. Fires every 3s;
  -- drawMainMenu() checks dashboardNeedsRefresh and re-renders the dashboard
  -- when it is set. Sub-screens cancel the timer so they don't fight the
  -- display. When we return to main we restart it.
  if onMonitor and monitor then
    dashboardTimer = os.startTimer(3)
  end

  local running = true
  while running do
    if currentScreen == "main" then
      drawMainMenu()
      dashboardNeedsRefresh = false

      -- Poll for events: timer fires -> re-draw dashboard; key/char -> handle nav.
      if dashboardTimer then os.cancelTimer(dashboardTimer) end
      dashboardTimer = os.startTimer(3)
      while true do
        local evt, data = os.pullEvent()
        if evt == "timer" then
          dashboardNeedsRefresh = true
          -- Re-draw immediately and restart the timer for the next refresh.
          drawMainMenu()
          if dashboardTimer then os.cancelTimer(dashboardTimer) end
          dashboardTimer = os.startTimer(3)
        elseif evt == "char" or evt == "key" or evt == "key_down" or evt == "key_up" then
          local key
          if evt == "char" then
            key = type(data) == "string" and #data == 1 and string.lower(data) or nil
          elseif evt == "key" or evt == "key_down" or evt == "key_up" then
            key = KEY_LABEL[data] or data
          else
            key = nil
          end
          if not key then
            -- Unrecognised event (e.g. a modifier) — keep waiting.
          else
            local isUp    = (key == "w" or key == "up")
            local isDown  = (key == "s" or key == "down")
            local isEsc   = (key == "q" or key == "escape")
            local isEnter = (key == "enter")
            local isA     = (key == "a")
            local isR     = (key == "r")
            local isB     = (key == "b")

            if isEsc then
              running = false
              break
            elseif isEnter then
              if selectedIndex == 1 then
                currentScreen = "create"
              elseif selectedIndex == 2 then
                currentScreen = "workinggauges"
              elseif selectedIndex == 3 then
                currentScreen = "frogport"
              elseif selectedIndex == 4 then
                currentScreen = "settings"
              end
              break
            elseif isUp then
              if selectedIndex > 1 then
                selectedIndex = selectedIndex - 1
              else
                selectedIndex = 4
              end
              -- Re-draw with new selection, then keep waiting.
              drawMainMenu()
              if dashboardTimer then os.cancelTimer(dashboardTimer) end
              dashboardTimer = os.startTimer(3)
            elseif isDown then
              if selectedIndex < 4 then
                selectedIndex = selectedIndex + 1
              else
                selectedIndex = 1
              end
              drawMainMenu()
              if dashboardTimer then os.cancelTimer(dashboardTimer) end
              dashboardTimer = os.startTimer(3)
            end
            -- Any other key (a, r, b) is ignored on the main menu.
          end
        elseif evt == nil then
          running = false
          break
        end
        -- Any other event type (mouse, etc.): ignore.
      end

    elseif currentScreen == "create" then
      showCreateFactoryGauge()
      currentScreen = "main"
      selectedIndex = 1
      readStockFromTicker()

    elseif currentScreen == "workinggauges" then
      showWorkingGaugesList()
      currentScreen = "main"
      selectedIndex = 2
      readStockFromTicker()

    elseif currentScreen == "frogport" then
      showFrogPortList()
      currentScreen = "main"
      selectedIndex = 3
      readStockFromTicker()

    elseif currentScreen == "settings" then
      showSettings()
      currentScreen = "main"
      selectedIndex = 4
      readStockFromTicker()
    end
  end

  dispWriteLn("\nShutting down.\n")
end

-- Run
main()
