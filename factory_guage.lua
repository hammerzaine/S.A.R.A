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

local function prompt(text)
    dispWrite(text)
    if has_term and has_term_write then
        _G.term.write(text)
        termFlush()
    end
end

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

-- Set text scale on monitor (1 = default, 0.5 = smaller, 2 = larger).
local function dispSetTextScale(scale)
  if onMonitor and monitor and hasFn(monitor, "setTextScale") then
    monitor.setTextScale(scale)
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

  -- 2c. Direct side-by-side search: wrap every side and check for stock methods
  if not stockTicker then
    for _, sideName in ipairs(sides_to_scan) do
      local ok, comp = pcall(function() return _G.peripheral.wrap(sideName) end)
      if not ok or not comp or type(comp) ~= "table" then
        if _G.peripheral and type(_G.peripheral) == "table" then
          local sideProp = _G.peripheral[sideName]
          if type(sideProp) == "table" then
            comp = sideProp
          end
        end
      end
      if comp and type(comp) == "table" then
        if comp.stock and type(comp.stock) == "table" and
           comp.stock.getItemDetail and type(comp.stock.getItemDetail) == "function" then
          stockTicker = comp
          stockTickerSide = sideName
          diagLines[#diagLines + 1] = "STOCK TICKER: FOUND on side " .. sideName ..
            " via comp.stock.getItemDetail"
          break
        end
        if comp.requestFiltered and type(comp.requestFiltered) == "table" and
           comp.requestFiltered.getStockItemDetail and type(comp.requestFiltered.getStockItemDetail) == "table" and
           comp.requestFiltered.getStockItemDetail.list and type(comp.requestFiltered.getStockItemDetail.list) == "function" then
          stockTicker = comp
          stockTickerSide = sideName
          diagLines[#diagLines + 1] = "STOCK TICKER: FOUND on side " .. sideName ..
            " via comp.requestFiltered.getStockItemDetail.list"
          break
        end
      end
    end
  end

  if not stockTicker then
    diagLines[#diagLines + 1] = "STOCK TICKER: NOT FOUND — tried type names, peripheral.stock, and side-by-side scan"
  end

  -- Print diagnostics to the display and WAIT for keypress
  if #diagLines > 0 then
    if onMonitor and monitor and hasFn(monitor, "clear") then
      monitor.clear()
    elseif has_term and has_term_clear then
      _G.term.clear()
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
      _G.term.clear()
      _G.term.setCursorPos(1, 1)
      for i, line in ipairs(diagLines) do
        if i > h then break end
        _G.term.setCursorPos(1, i + 1)
        if string.find(line, "STOCK TICKER") then
          _G.term.setTextColor(colors.green)
          _G.term.write(">> " .. line)
          _G.term.setTextColor(colors.white)
        else
          _G.term.write(line)
        end
      end
      local tY = #diagLines + 2
      if stockTicker then
        tY = #diagLines + 2
        _G.term.setCursorPos(1, tY)
        _G.term.setTextColor(colors.gray)
        _G.term.write("Ticker callable methods:")
        tY = tY + 1
        for k, v in pairs(stockTicker) do
          if type(k) == "string" and type(v) == "function" then
            if string.find(k, "stock", 1, true) or string.find(k, "Stock", 1, true) or
               string.find(k, "item", 1, true) or string.find(k, "Item", 1, true) or
               string.find(k, "list", 1, true) or string.find(k, "List", 1, true) or
               string.find(k, "request", 1, true) or string.find(k, "filter", 1, true) then
              _G.term.setCursorPos(2, tY)
              _G.term.write(k .. " (fn)")
              tY = tY + 1
            end
          elseif type(k) == "string" and type(v) == "table" then
            for nk, nv in pairs(v) do
              if type(nk) == "string" and type(nv) == "function" then
                _G.term.setCursorPos(2, tY)
                _G.term.write(k .. "." .. nk .. " (fn)")
                tY = tY + 1
              end
            end
          end
        end
      end
      local promptY = math.max(tY + 1, #diagLines + 2)
      if promptY < h then
        _G.term.setCursorPos(1, promptY + 1)
        _G.term.setTextColor(colors.gray)
        _G.term.write("Press any key to continue...")
        if has_term_flush then _G.term.flush() end
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
  local w, h = dispGetSize()
  dispClear()
  dispSetTextScale(1.0)
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

  -- Stock overview
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
