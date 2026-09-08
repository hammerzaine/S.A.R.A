
-- factory_guage.lua
-- CC:Tweaked script — acts like Create Factory Gauge
--
-- ENVIRONMENT:
--   - peripheral.find(side) — available
--   - term API — available
--   - colors API — available
--   - io — available (stdin/stdout for text input)
--   - monitor — auto-detected at startup; menu renders on it if found
--
-- HOW IT WORKS:
--   1. Scans all 6 sides using peripheral.find
--   2. Auto-detects a monitor peripheral and renders the menu on it
--   3. Looks for a written book in an item frame (clipboard)
--   4. Reads Frog Port names from the book (one per line)
--   5. Falls back to manual entry via terminal if no book found
--   6. User selects recipes, checks stock, triggers craft
--
-- CONTROLS (keyboard goes through the COMPUTER, not the monitor):
--   W/Up        — navigate up
--   S/Down      — navigate down
--   Enter       — select highlighted recipe
--   1-9         — jump directly to recipe
--   T           — trigger craft for selected recipe
--   C           — check stock
--   R           — rescan peripherals
--   Q/Esc       — quit

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
local has_term_read     = has_term and hasFn(_G.term, "read")
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

-- Create the unified display target (monitor if found, otherwise term).
-- We also keep a direct reference to the computer's term for input prompts,
-- because monitors have no keyboard — all typing must happen in the
-- computer's terminal window.
local display = monitor or term

-- ---------------------------------------------------------------------------
-- OUTPUT HELPERS — work on monitor when available, term when not
-- ---------------------------------------------------------------------------

local function termFlush()
  if has_term_flush then _G.term.flush() end
end

-- Write to the monitor/term display (the big screen)
local function dispWrite(text)
    display.write(text)
end

-- Write a line, handling scrolling properly for monitor vs term.
-- Monitors have fixed size — don't scroll, just wrap or stop.
local function dispWriteLn(text)
    dispWrite(text)
    local _, y = display.getCursorPos()
    local _, h = display.getSize()
    if y >= h then
        -- At bottom of monitor — clear and restart.
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

-- Write a prompt to BOTH the monitor and the computer's terminal.
-- This ensures you can see where to type regardless of which screen
-- you're looking at.
local function prompt(text)
    dispWrite(text)
    if has_term and has_term_write then
        _G.term.write(text)
        termFlush()
    end
end

-- Clear the active display (monitor when available, term when not).
-- When a monitor is present, also clear the computer's term and write
-- a status line so the user knows the computer is driving the monitor.
local function dispClear()
  if onMonitor and monitor and hasFn(monitor, "clear") then
    monitor.clear()
  elseif has_term and has_term_clear then
    _G.term.clear()
  end
  -- Always ensure the computer's term shows something useful.
  -- Even when a monitor is driving the display, the user needs to see
  -- on the computer that it's active and what to do.
  if has_term and has_term_clear and has_term_write then
    _G.term.clear()
    _G.term.setCursorPos(1, 1)
    _G.term.setTextColor(colors.green)
    _G.term.write("Factory Gauge — monitor active")
    _G.term.setTextColor(colors.gray)
    _G.term.setCursorPos(1, 2)
    _G.term.write("Use THIS computer's keyboard to control")
    _G.term.setCursorPos(1, 3)
    _G.term.write("W/S: navigate  |  Enter: select  |  1-9: recipe")
    _G.term.setCursorPos(1, 4)
    _G.term.write("T: craft  |  C: stock  |  R: rescan  |  Q: quit")
    termFlush()
  end
end

-- Set cursor position on the active display.
local function dispSetCursorPos(x, y)
  if onMonitor and monitor and hasFn(monitor, "setCursorPos") then
    monitor.setCursorPos(x, y)
  elseif has_term and has_term_setCursorPos then
    _G.term.setCursorPos(x, y)
  end
end

-- Set text colour on the active display.
local function dispSetTextColor(c)
    local finalColor = c or colors.white
    if onMonitor and monitor and hasFn(monitor, "setTextColor") then
        monitor.setTextColor(finalColor)
    elseif has_term and has_term_setTextColor then
        _G.term.setTextColor(finalColor)
    end
end

-- Set background colour on the active display.
local function dispSetBackgroundColor(c)
  if onMonitor and monitor and hasFn(monitor, "setBackgroundColor") then
    monitor.setBackgroundColor(c)
  elseif has_term and hasFn(_G.term, "setBackgroundColor") then
    _G.term.setBackgroundColor(c)
  end
end

-- Get display size.
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
-- TEXT INPUT — always via terminal (io.read works reliably in CC:T GUI)
-- ---------------------------------------------------------------------------

local function readln()
  -- CC:T terminal GUI provides line input via io.read("*l").
  if has_io then
    local line = _G.io.read("*l")
    return line
  end
  -- Fallback: build line from key events.
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
-- RECIPES — edit this table
-- ---------------------------------------------------------------------------

local recipes = {
  ["minecraft:stick"] = {
    output = "minecraft:stick",
    count = 64,
    ingredients = { "minecraft:planks" },
    ingredientCounts = { 2 },
    sendTo = "smasher",
  },
  ["minecraft:crafting_table"] = {
    output = "minecraft:crafting_table",
    count = 1,
    ingredients = { "minecraft:planks" },
    ingredientCounts = { 4 },
    sendTo = "smasher",
  },
  ["minecraft:wooden_sword"] = {
    output = "minecraft:wooden_sword",
    count = 1,
    ingredients = { "minecraft:planks", "minecraft:stick" },
    ingredientCounts = { 1, 2 },
    sendTo = "smasher",
  },
}

-- ---------------------------------------------------------------------------
-- STATE
-- ---------------------------------------------------------------------------

local clipboardEntries = {}
local detectedPeripherals = {}
local stockCache = {}
local clipboardSide = nil
local selectedRecipe = nil

-- ---------------------------------------------------------------------------
-- PERIPHERAL DETECTION
-- ---------------------------------------------------------------------------

local function detectPeripheralType(side)
  if not has_peripheral_find then return nil, nil end
  local ok, comp = pcall(function() return _G.peripheral.find(side) end)
  if ok and comp and comp.type and comp.type ~= "none" then
    return comp.type, comp
  end
  return nil, nil
end

local function scanAllSides()
  detectedPeripherals = {}
  local sides_to_scan = { "left", "right", "front", "back", "top", "bottom" }
  for _, sideName in ipairs(sides_to_scan) do
    local typ, comp = detectPeripheralType(sideName)
    if typ then
      detectedPeripherals[sideName] = {
        side = sideName, name = sideName, type = typ, comp = comp,
      }
    end
  end
end

-- ---------------------------------------------------------------------------
-- CLIPBOARD — read Frog Port names from written book in item frame / sign
-- ---------------------------------------------------------------------------

local function readSignText(p)
  local comp = p.comp
  if not comp then return nil end
  local text = nil
  local ok = pcall(function()
    if comp.getSignText then text = comp.getSignText()
    elseif comp.get then text = comp.get() end
  end)
  if ok and text and type(text) == "string" and #text > 0 then
    local lines = {}
    for line in string.gmatch(text, "[^\r\n]+") do
      line = string.match(line, "^%s*(.-)%s*$")
      if line ~= "" and not string.match(line, "^%s*%-%-") then
        lines[#lines + 1] = line
      end
    end
    return #lines > 0 and lines or nil
  end
  return nil
end

local function readBookFromFrame(p)
  local comp = p.comp
  if not comp then return nil end
  local item = nil
  local ok = pcall(function()
    if comp.getItem then item = comp.getItem()
    elseif comp.get then item = comp.get() end
  end)
  if not ok or not item then return nil end
  local id = item.id or item.name or item.displayName or ""
  if not string.find(string.lower(id or ""), "book") and
     not string.find(string.lower(id or ""), "written") then
    return nil
  end
  local text = item.text or item.displayText or ""
  if #text == 0 and item.pages then text = table.concat(item.pages, "\n") end
  if #text == 0 then return nil end
  local lines = {}
  for line in string.gmatch(text, "[^\r\n]+") do
    line = string.match(line, "^%s*(.-)%s*$")
    if line ~= "" and not string.match(line, "^%s*%-%-") then
      lines[#lines + 1] = line
    end
  end
  return #lines > 0 and lines or nil
end

local function findClipboard()
  for sideName, p in pairs(detectedPeripherals) do
    local typ = p.type or ""
    if string.find(typ, "sign") then
      local signText = readSignText(p)
      if signText and #signText > 0 then
        clipboardSide = sideName
        return signText
      end
    end
    if string.find(typ, "item_frame") then
      local bookLines = readBookFromFrame(p)
      if bookLines and #bookLines > 0 then
        clipboardSide = sideName
        return bookLines
      end
    end
    if string.find(typ, "container") or string.find(typ, "chest") or
       string.find(typ, "barrel") or string.find(typ, "hopper") then
      local bookLines = readBookFromFrame(p)
      if bookLines and #bookLines > 0 then
        clipboardSide = sideName
        return bookLines
      end
    end
  end
  return nil
end

local function loadClipboard()
  clipboardEntries = {}
  clipboardSide = nil
  scanAllSides()
  local names = findClipboard()
  if names and #names > 0 then
    clipboardEntries = names
    dispWriteLn("Clipboard found on " .. (clipboardSide or "?"))
    dispWriteLn("Ports: " .. table.concat(clipboardEntries, ", "))
  else
    dispWriteLn("No clipboard found.")
    dispWriteLn("Enter Frog Port names, one per line.")
    dispWriteLn("Press Enter on an empty line when done:")
    local entries = {}
    while true do
      prompt("> ")
      local line = readln()
      if not line or line == "" then break end
      local trimmed = string.match(line, "^%s*(.-)%s*$")
      if trimmed ~= "" then entries[#entries + 1] = trimmed end
    end
    if #entries > 0 then
      clipboardEntries = entries
      dispWriteLn("Loaded " .. #entries .. " port(s).")
    else
      clipboardEntries = { "smasher", "grinder", "smelter" }
      dispWriteLn("Using defaults: smasher, grinder, smelter")
    end
  end
  sleep(2)
end

-- ---------------------------------------------------------------------------
-- STOCK
-- ---------------------------------------------------------------------------

local function getStock(itemId)
  if stockCache[itemId] then return stockCache[itemId] end
  return 0
end

local function updateStockCache()
  for k in pairs(stockCache) do stockCache[k] = nil end
  for _, p in pairs(detectedPeripherals) do
    local typ = p.type or ""
    if string.find(typ, "item_service") or string.find(typ, "item_storage") or
       string.find(typ, "item") then
      if p.comp then
        local items = nil
        local ok = pcall(function()
          if p.comp.getItems then items = p.comp.getItems()
          elseif p.comp.getAllItems then items = p.comp.getAllItems()
          elseif p.comp.get then items = { p.comp.get() } end
        end)
        if ok and items and type(items) == "table" and #items > 0 then
          for _, item in ipairs(items) do
            local id = item.id or item.name or ""
            local count = item.count or item.size or item.amount or 0
            if id ~= "" and count and count > 0 then
              stockCache[id] = (stockCache[id] or 0) + count
            end
          end
        end
      end
    end
  end
end

-- ---------------------------------------------------------------------------
-- CRAFTING QUEUE
-- ---------------------------------------------------------------------------

local function buildCraftQueue(itemId, targetCount, depth)
  depth = depth or 0
  if depth > 10 then return nil, "dependency too deep" end
  local current = getStock(itemId)
  local need = targetCount - current
  if need <= 0 then return {}, "in stock" end
  local queue = {}
  table.insert(queue, 1, { action = "craft", item = itemId, count = need })
  local recipe = recipes[itemId]
  if recipe then
    for i, ingId in ipairs(recipe.ingredients) do
      local ingCount = recipe.ingredientCounts[i] or 1
      local totalNeeded = ingCount * need
      local subQueue, err = buildCraftQueue(ingId, totalNeeded, depth + 1)
      if err and err ~= "in stock" then return nil, err end
      if subQueue then
        for j = #subQueue, 1, -1 do
          table.insert(queue, 1, subQueue[j])
        end
      end
    end
  else
    return nil, "missing recipe for " .. itemId
  end
  return queue, "ok"
end

-- ---------------------------------------------------------------------------
-- EXECUTION
-- ---------------------------------------------------------------------------

local function findPort(portName)
  if detectedPeripherals[portName] then
    return detectedPeripherals[portName]
  end
  for name, p in pairs(detectedPeripherals) do
    if string.lower(name) == string.lower(portName) then return p end
  end
  for name, p in pairs(detectedPeripherals) do
    if string.find(string.lower(name), string.lower(portName)) then return p end
  end
  return nil
end

local function executeCraftToPort(itemId, count, portName)
  local p = findPort(portName)
  if not p then return false, "port not found: " .. tostring(portName) end
  local typ = p.type or ""
  if not string.find(typ, "item_service") and not string.find(typ, "item") then
    return false, "not an item service: " .. tostring(typ)
  end
  if not p.comp then return false, "no component object for port" end
  local pushed = false
  local pushMsg = ""
  local function tryPush(funcName)
    local ok, result = pcall(function()
      local fn = p.comp[funcName]
      if fn then return fn({ name = itemId, count = count }) end
      return nil
    end)
    if ok and result ~= false and result ~= nil then
      pushed = true
      pushMsg = funcName
      return true
    end
    return false
  end
  if not tryPush("pushOut") then
    if not tryPush("offer") then
      if not tryPush("sell") then
        if not tryPush("add") then
          local items = nil
          pcall(function() items = p.comp.getItems() end)
          if items and #items > 0 then
            pushed = true
            pushMsg = "getItems (assumed)"
          end
        end
      end
    end
  end
  if pushed then
    return true, "deposited " .. count .. "x " .. itemId .. " to " .. portName .. " via " .. pushMsg
  end
  return false, "failed to deposit to " .. portName
end

-- ---------------------------------------------------------------------------
-- GUI — renders on monitor when available, falls back to terminal
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

local function countTable(t)
  if type(t) ~= "table" then return 0 end
  local c = 0
  for _ in pairs(t) do c = c + 1 end
  return c
end

local function drawMenuItem(x, y, selected, text)
  if selected then
    dispSetTextColor(colors.white)
    dispSetBackgroundColor(colors.blue)
  else
    dispSetTextColor(colors.gray)
    dispSetBackgroundColor(colors.black)
  end
  dispSetCursorPos(x, y)
  if selected then
    dispWrite("> " .. text .. " ")
  else
    dispWrite("  " .. text .. " ")
  end
end

local function drawMainMenu()
  local w, h = dispGetSize()
  drawHeader("FACTORY GAUGE")

  -- Status line
  dispSetTextColor(colors.white)
  dispSetBackgroundColor(colors.black)
  dispSetCursorPos(1, 3)
  dispWrite("Peripherals: " .. countTable(detectedPeripherals) .. "  |  ")

  -- Frog Ports
  local portNames = ""
  for i, name in ipairs(clipboardEntries) do
    if i > 1 then portNames = portNames .. ", " end
    portNames = portNames .. name
  end
  if portNames == "" then portNames = "(none)" end
  dispWrite("Frog Ports: " .. portNames)

  -- Controls hint (monitor: tell user to use computer keyboard)
  dispSetCursorPos(1, 4)
  dispSetTextColor(colors.darkGray)
  if onMonitor then
    dispWrite("Use COMPUTER keyboard: W/S=up/down  Enter=select  1-9=recipe  T=craft  C=stock  R=rescan  Q=quit")
  else
    dispWrite("W/S: up/down  |  Enter: select  |  1-9: recipe  |  T: craft  |  C: stock  |  R: rescan  |  Q: quit")
  end

  -- Detected blocks
  dispSetCursorPos(1, 6)
  dispSetTextColor(colors.white)
  dispWriteLn("DETECTED BLOCKS:")
  local idx = 0
  for sideName, p in pairs(detectedPeripherals) do
    idx = idx + 1
    local typeStr = p.type and (p.type:gsub("create:", "")) or "unknown"
    local mark = (idx == selectedRecipe) and ">" or " "
    dispSetCursorPos(2, 7 + idx - 1)
    dispWrite(mark .. "[" .. idx .. "] " .. sideName .. " - " .. typeStr)
  end

  -- Recipes
  local recipeList = {}
  for id in pairs(recipes) do recipeList[#recipeList + 1] = id end
  table.sort(recipeList)

  dispSetCursorPos(1, 7 + math.min(#detectedPeripherals, 5) + 1)
  dispSetTextColor(colors.white)
  dispWriteLn("RECIPES:")
  for i, id in ipairs(recipeList) do
    local r = recipes[id]
    local short = string.match(id, "^%w+:(.+)$") or id
    local target = r.sendTo or "?"
    local sel = (i == selectedRecipe)
    drawMenuItem(2, 8 + math.min(#detectedPeripherals, 5) + i,
                 sel, i .. ". " .. short .. " -> " .. target .. " (keep " .. r.count .. ")")
  end
  if #recipeList == 0 then
    dispSetCursorPos(2, 8 + math.min(#detectedPeripherals, 5) + 1)
    dispSetTextColor(colors.gray)
    dispWrite("(no recipes defined)")
  end

  -- Stock summary
  local stockY = 8 + math.min(#detectedPeripherals, 5) + math.max(#recipeList, 1) + 2
  dispSetCursorPos(1, stockY)
  dispSetTextColor(colors.darkGray)
  dispWrite("Stock tracked: " .. countTable(stockCache) .. " item types")
end

local function drawStockScreen()
  drawHeader("CURRENT STOCK")
  updateStockCache()
  local items = {}
  for id, count in pairs(stockCache) do
    if count > 0 then items[#items + 1] = { id = id, count = count } end
  end
  table.sort(items, function(a, b) return a.count > b.count end)
  dispSetCursorPos(1, 3)
  for i = 1, math.min(20, #items) do
    local item = items[i]
    local short = string.match(item.id, "^%w+:(.+)$") or item.id
    dispSetTextColor(i <= 5 and colors.white or colors.gray)
    dispWrite(string.format("%2d. %-25s %6d", i, short, item.count))
    dispWriteLn()
  end
  if #items == 0 then
    dispSetTextColor(colors.gray)
    dispWriteLn("  (no items in stock)")
  end
  dispSetCursorPos(1, math.min(22, 3 + #items + 2))
  dispSetTextColor(colors.darkGray)
  dispWriteLn("(press any key to return...)")
  readkey()
end

local function drawCraftController()
  local recipeList = {}
  for id in pairs(recipes) do recipeList[#recipeList + 1] = id end
  table.sort(recipeList)
  selectedRecipe = selectedRecipe or 1
  if selectedRecipe > #recipeList then selectedRecipe = 1 end
  local recipeId = recipeList[selectedRecipe]
  if not recipeId then
    dispWriteLn("No recipe selected!")
    readkey()
    return
  end
  local r = recipes[recipeId]
  drawHeader("CRAFT CONTROLLER")
  dispSetTextColor(colors.white)
  dispSetCursorPos(1, 3)
  dispWriteLn("Recipe: " .. recipeId)
  dispWriteLn("Output: " .. r.count .. "x " .. r.output)
  dispWriteLn("Send to: " .. (r.sendTo or "unknown"))
  dispWriteLn("")
  dispWriteLn("INGREDIENTS:")
  local y = 6
  for i, ingId in ipairs(r.ingredients) do
    local need = r.ingredientCounts[i] or 1
    local have = getStock(ingId)
    local short = string.match(ingId, "^%w+:(.+)$") or ingId
    local status = have >= need and "[OK] " or "[LOW] "
    dispSetTextColor(have >= need and colors.green or colors.red)
    dispSetCursorPos(2, y)
    dispWrite(status .. short .. ": " .. have .. "/" .. need)
    dispWriteLn()
    y = y + 1
  end
  y = y + 1
  dispWriteLn("")
  dispSetCursorPos(1, y)
  dispSetTextColor(colors.white)
  drawMenuItem(2, y, false, "[1] Execute craft")
  drawMenuItem(2, y + 1, false, "[2] Show queue")
  drawMenuItem(2, y + 2, false, "[Q] Back")
  dispWriteLn("")
  prompt("Choice: ")
  local choice = readln()
  if not choice then return end

  local queue, err = buildCraftQueue(r.output, r.count)
  if err and err ~= "in stock" then
    dispWriteLn("Error: " .. err)
    readkey()
    return
  end
  if err == "in stock" then
    dispWriteLn(r.output .. " is already in stock")
    readkey()
    return
  end
  if choice == "2" then
    dispWriteLn("")
    dispWriteLn("CRAFT QUEUE:")
    for i, step in ipairs(queue) do
      local short = string.match(step.item, "^%w+:(.+)$") or step.item
      dispWriteLn("  " .. i .. ". " .. step.count .. "x " .. short)
    end
    readkey()
    return
  end
  -- Execute
  dispWriteLn("")
  dispWriteLn("EXECUTING...")
  for _, step in ipairs(queue) do
    local short = string.match(step.item, "^%w+:(.+)$") or step.item
    local ok, msg = executeCraftToPort(step.item, step.count, r.sendTo)
    local status = ok and "[OK] " or "[FAIL] "
    dispSetTextColor(ok and colors.green or colors.red)
    dispWriteLn("  " .. status .. short .. ": " .. msg)
  end
  updateStockCache()
  dispWriteLn("")
  dispWriteLn("Done.")
  readkey()
  selectedRecipe = nil
end

-- ---------------------------------------------------------------------------
-- MAIN LOOP
-- ---------------------------------------------------------------------------

local function main()
  -- Initial scan and clipboard load
  scanAllSides()
  loadClipboard()
  updateStockCache()
  selectedRecipe = 1

  -- If we have a monitor, show instructions on the monitor.
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
    drawMainMenu()

    local key = readkey()
    if not key then
      running = false
      break
    end

    local recipeList = {}
    for id in pairs(recipes) do recipeList[#recipeList + 1] = id end
    table.sort(recipeList)

    if key == keys.q or key == keys.escape then
      -- QUIT
      running = false

    elseif key == keys.enter then
      -- ENTER selects the currently highlighted recipe
      if #recipeList > 0 and selectedRecipe >= 1 and selectedRecipe <= #recipeList then
        selectedRecipe = selectedRecipe
        drawCraftController()
      end

    elseif key == keys.r then
      -- RESCAN peripherals
      loadClipboard()
      updateStockCache()

    elseif key == keys.c then
      -- STOCK SCREEN
      drawStockScreen()

    elseif key == keys.t then
      -- TRIGGER CRAFT (opens craft controller for selected recipe)
      if selectedRecipe and #recipeList > 0 then
        drawCraftController()
      else
        dispWriteLn("Enter recipe number (1-" .. #recipeList .. "):")
        prompt("> ")
        local n = readln()
        if n then
          local num = tonumber(n)
          if num and num >= 1 and num <= #recipeList then
            selectedRecipe = num
            drawCraftController()
          end
        end
      end

    elseif key == keys.up or key == keys.w then
      -- NAVIGATE UP
      if #recipeList > 0 then
        selectedRecipe = selectedRecipe - 1
        if selectedRecipe < 1 then selectedRecipe = #recipeList end
      end

    elseif key == keys.down or key == keys.s then
      -- NAVIGATE DOWN
      if #recipeList > 0 then
        selectedRecipe = selectedRecipe + 1
        if selectedRecipe > #recipeList then selectedRecipe = 1 end
      end

    elseif type(key) == "number" and key >= 48 and key <= 57 then
      -- NUMBER KEY 0-9 — jump directly to recipe
      local num = key - 48
      if num >= 1 and num <= #recipeList then
        selectedRecipe = num
        drawCraftController()
      else
        dispWriteLn("No recipe #" .. num)
        sleep(1)
      end
    end
  end

  dispWriteLn("\nShutting down.\n")
end

-- Run
main()
