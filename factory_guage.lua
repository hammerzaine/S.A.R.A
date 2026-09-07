-- factory_guage.lua
-- CC:Tweaked script — acts like Create Factory Gauge
--
-- ENVIRONMENT: What we know works:
--   - peripheral.find(side) — available
--   - term API — available (for monitor drawing)
--   - colors API — available
--   - io — available (stdin/stdout)
--   - No require() — everything is global or builtin
--   - No component/computer/shell globals
--
-- HOW IT WORKS:
--   1. Scans all 6 sides using peripheral.find
--   2. Looks for a written book in an item frame (clipboard)
--   3. Reads Frog Port names from the book (one per line)
--   4. Falls back to manual entry if no book found
--   5. User selects recipes, checks stock, triggers craft
--
-- CONTROLS:
--   Q / Esc     — quit
--   R           — rescan
--   1-9         — select recipe
--   C           — check stock
--   T           — trigger craft

print("factory_guage: starting...")

-- Detect environment
local has_peripheral_find = false
local has_term = false
local has_term_write = false
local has_term_clear = false
local has_term_setCursorPos = false
local has_term_getCursorPos = false
local has_term_isVisible = false
local has_term_scroll = false
local has_term_setTextColor = false
local has_term_setTextColor = false
local has_colors = false

if _G.peripheral and type(_G.peripheral) == "table" then
  if _G.peripheral.find and type(_G.peripheral.find) == "function" then
    has_peripheral_find = true
    print("[diag] peripheral.find: AVAILABLE")
  end
end

if _G.term and type(_G.term) == "table" then
  has_term = true
  print("[diag] term: AVAILABLE")
  if _G.term.write and type(_G.term.write) == "function" then
    has_term_write = true
  end
  if _G.term.clear and type(_G.term.clear) == "function" then
    has_term_clear = true
  end
  if _G.term.setCursorPos and type(_G.term.setCursorPos) == "function" then
    has_term_setCursorPos = true
  end
  if _G.term.getCursorPos and type(_G.term.getCursorPos) == "function" then
    has_term_getCursorPos = true
  end
  if _G.term.isVisible and type(_G.term.isVisible) == "function" then
    has_term_isVisible = true
  end
  if _G.term.scroll and type(_G.term.scroll) == "function" then
    has_term_scroll = true
  end
  if _G.term.setTextColor and type(_G.term.setTextColor) == "function" then
    has_term_setTextColor = true
  end
  if _G.term.read and type(_G.term.read) == "function" then
    has_term_read = true
  end
else
  print("[diag] term: ABSENT")
end

if _G.colors and type(_G.colors) == "table" then
  has_colors = true
  print("[diag] colors: AVAILABLE")
else
  print("[diag] colors: ABSENT")
end

-- Helper: write to term if available, else stdout.
-- In CC:T, term.write() does NOT auto-flush — we flush explicitly.
local function output(str)
  str = str or ""
  if has_term and has_term_write then
    _G.term.write(str)
    _G.term.flush()
  else
    io.stdout:write(str)
    io.stdout:flush()
  end
end

local function outputln(str)
  str = str or ""
  if has_term and has_term_write then
    _G.term.write(str .. "\n")
    _G.term.flush()
  else
    io.stdout:write(str .. "\n")
    io.stdout:flush()
  end
end

local pendingLines = {}

local function readln()
  -- Return the next line from a pending paste, if any.
  if #pendingLines > 0 then
    return table.remove(pendingLines, 1)
  end

  -- Otherwise build a line from character events.
  local t = {}
  io.stdout:flush()
  while true do
    local evt, data = os.pullEvent()
    if evt == "char" then
      local c = data
      if c == "\n" or c == "\r" then
        break
      elseif c == "\b" or c == "\127" then
        if #t > 0 then
          table.remove(t)
          io.stdout:write("\b \b")
          io.stdout:flush()
        end
      elseif type(c) == "string" and #c > 0 then
        t[#t + 1] = c
        io.stdout:write(c)
        io.stdout:flush()
      end
    elseif evt == "clipboard" then
      local text = data
      if text and #text > 0 then
        for line in string.gmatch(text, "[^\r\n]+") do
          line = string.match(line, "^%s*(.-)%s*$")
          if #line > 0 then
            pendingLines[#pendingLines + 1] = line
          end
        end
        if #pendingLines > 0 then
          return table.remove(pendingLines, 1)
        end
      end
    elseif evt == "key" then
      local key = data
      if key == keys.enter then
        break
      elseif key == keys.backspace then
        if #t > 0 then
          table.remove(t)
          io.stdout:write("\b \b")
          io.stdout:flush()
        end
      end
    end
  end
  io.stdout:write("\n")
  io.stdout:flush()
  return table.concat(t)
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
-- DETECTION
-- ---------------------------------------------------------------------------

local function detectPeripheralType(side)
  if not has_peripheral_find then
    return nil, nil
  end
  local ok, comp = pcall(function()
    return _G.peripheral.find(side)
  end)
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
        side = sideName,
        name = sideName,
        type = typ,
        comp = comp,
      }
    end
  end
end

-- ---------------------------------------------------------------------------
-- CLIPBOARD INPUT — paste handling
-- In CC:T, pasting fires "clipboard" events, not "char" events.
-- We collect pasted lines into a queue so readln() can consume one at a time.
-- ---------------------------------------------------------------------------
local pasteLineQueue = {}

local function drainPasteEvents()
  -- Pull all pending "clipboard" events and split into lines.
  while true do
    local evt = { os.pullEventRaw("clipboard") }
    if evt[1] ~= "clipboard" then
      -- Put the non-clipboard event back for the next listener.
      -- (In practice we won't get here because pullEventRaw blocks on "clipboard".)
      break
    end
    local text = evt[2]
    if text and #text > 0 then
      for line in string.gmatch(text, "[^\r\n]+") do
        line = string.match(line, "^%s*(.-)%s*$")
        if #line > 0 then
          pasteLineQueue[#pasteLineQueue + 1] = line
        end
      end
    end
  end
end

local function readSignText(p)
  local comp = p.comp
  if not comp then return nil end
  
  local text = nil
  local ok = pcall(function()
    if comp.getSignText then
      text = comp.getSignText()
    elseif comp.get then
      text = comp.get()
    end
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
  
  -- Get item from frame
  local item = nil
  local ok = pcall(function()
    if comp.getItem then
      item = comp.getItem()
    elseif comp.get then
      item = comp.get()
    end
  end)
  if not ok or not item then
    return nil
  end
  
  -- Check if it's a written book
  local id = item.id or item.name or item.displayName or ""
  if not string.find(string.lower(id or ""), "book") and
     not string.find(string.lower(id or ""), "written") then
    return nil
  end
  
  -- Get text
  local text = item.text or item.displayText or ""
  if #text == 0 and item.pages then
    text = table.concat(item.pages, "\n")
  end
  if #text == 0 then
    return nil
  end
  
  -- Parse lines
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
    
    -- Check sign
    if string.find(typ, "sign") then
      local signText = readSignText(p)
      if signText and #signText > 0 then
        clipboardSide = sideName
        return signText
      end
    end
    
    -- Check item frame with book
    if string.find(typ, "item_frame") then
      local bookLines = readBookFromFrame(p)
      if bookLines and #bookLines > 0 then
        clipboardSide = sideName
        return bookLines
      end
    end
    
    -- Check container with book
    if string.find(typ, "container") or string.find(typ, "chest") or
       string.find(typ, "barrel") or string.find(typ, "hopper") then
      -- Try to read first item as book
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
    outputln("Clipboard found on " .. (clipboardSide or "?"))
    outputln("Ports: " .. table.concat(clipboardEntries, ", "))
  else
    outputln("No clipboard found.")
    outputln("Enter Frog Port names, one per line. Press Enter on an empty line when done:")
    local entries = {}
    while true do
      output("> ")
      local line = readln()
      if not line or line == "" then break end
      local trimmed = string.match(line, "^%s*(.-)%s*$")
      if trimmed ~= "" then
        entries[#entries + 1] = trimmed
      end
    end
    if #entries > 0 then
      clipboardEntries = entries
      outputln("Loaded " .. #entries .. " port(s).")
    else
      clipboardEntries = { "smasher", "grinder", "smelter" }
      outputln("Using defaults: smasher, grinder, smelter")
    end
  end
end

-- ---------------------------------------------------------------------------
-- STOCK
-- ---------------------------------------------------------------------------

local function getStock(itemId)
  if stockCache[itemId] then
    return stockCache[itemId]
  end
  return 0
end

local function updateStockCache()
  for k in pairs(stockCache) do
    stockCache[k] = nil
  end
  
  -- Try to read stock from detected item services
  for _, p in pairs(detectedPeripherals) do
    local typ = p.type or ""
    if string.find(typ, "item_service") or string.find(typ, "item_storage") or
       string.find(typ, "item") then
      if p.comp then
        local items = nil
        local ok = pcall(function()
          if p.comp.getItems then
            items = p.comp.getItems()
          elseif p.comp.getAllItems then
            items = p.comp.getAllItems()
          elseif p.comp.get then
            items = { p.comp.get() }
          end
        end)
        if ok and items and type(items) == "table" and #items > 0 then
          for _, item in ipairs(items) do
            local id = item.id or item.name or ""
            local count = item.count or item.size or item.amount or 0
            if id ~= "" and count and count > 0 then
              if not stockCache[id] then
                stockCache[id] = 0
              end
              stockCache[id] = stockCache[id] + count
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
  if depth > 10 then
    return nil, "dependency too deep"
  end
  
  local current = getStock(itemId)
  local need = targetCount - current
  
  if need <= 0 then
    return {}, "in stock"
  end
  
  local queue = {}
  local entry = { action = "craft", item = itemId, count = need }
  table.insert(queue, 1, entry)
  
  local recipe = recipes[itemId]
  if recipe then
    for i, ingId in ipairs(recipe.ingredients) do
      local ingCount = recipe.ingredientCounts[i] or 1
      local totalNeeded = ingCount * need
      local subQueue, err = buildCraftQueue(ingId, totalNeeded, depth + 1)
      if err and err ~= "in stock" then
        return nil, err
      end
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
    if string.lower(name) == string.lower(portName) then
      return p
    end
  end
  for name, p in pairs(detectedPeripherals) do
    if string.find(string.lower(name), string.lower(portName)) then
      return p
    end
  end
  return nil
end

local function executeCraftToPort(itemId, count, portName)
  local p = findPort(portName)
  if not p then
    return false, "port not found: " .. tostring(portName)
  end
  
  local typ = p.type or ""
  if not string.find(typ, "item_service") and not string.find(typ, "item") then
    return false, "not an item service: " .. tostring(typ)
  end
  
  if not p.comp then
    return false, "no component object for port"
  end
  
  local pushed = false
  local pushMsg = ""
  
  local function tryPush(funcName)
    local ok, result = pcall(function()
      local fn = p.comp[funcName]
      if fn then
        return fn({ name = itemId, count = count })
      end
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
-- GUI
-- ---------------------------------------------------------------------------

local function clearScreen()
  if has_term and has_term_clear then
    _G.term.clear()
  else
    outputln("\27[2J\27[H")
  end
end

local function drawHeader(title)
  if not has_term then
    outputln(string.rep("=", 60))
    outputln(string.rep(" ", 20) .. title)
    outputln(string.rep("=", 60))
    return
  end
  
  local w = 60
  local titleLen = #title
  local pad = math.floor((w - titleLen) / 2)
  if pad < 0 then pad = 0 end
  
  if has_term_clear then _G.term.clear() end
  if has_term_setCursorPos then _G.term.setCursorPos(1, 1) end
  output(string.rep("=", w))
  outputln()
  output(string.rep(" ", pad) .. title .. string.rep(" ", w - pad - titleLen))
  outputln()
  output(string.rep("=", w))
  outputln()
end

local function countTable(t)
  if type(t) ~= "table" then return 0 end
  local c = 0
  for _ in pairs(t) do c = c + 1 end
  return c
end

local function showMainMenu()
  clearScreen()
  drawHeader("FACTORY GAUGE")
  
  outputln("Detected peripherals: " .. countTable(detectedPeripherals))
  
  local portNames = ""
  for i, name in ipairs(clipboardEntries) do
    if i > 1 then portNames = portNames .. ", " end
    portNames = portNames .. name
  end
  if portNames == "" then portNames = "(none)" end
  outputln("Frog Ports: " .. portNames)
  
  outputln("Controls: 1-9=recipe  C=stock  T=trigger  R=rescan  Q=quit")
  outputln("")
  
  outputln("DETECTED BLOCKS:")
  local idx = 0
  for sideName, p in pairs(detectedPeripherals) do
    idx = idx + 1
    local typeStr = p.type and (p.type:gsub("create:", "")) or "unknown"
    local mark = (idx == selectedRecipe) and ">" or " "
    outputln("  " .. mark .. "[" .. idx .. "] " .. sideName .. " - " .. typeStr)
  end
  
  outputln("")
  outputln("RECIPES:")
  local recipeList = {}
  for id in pairs(recipes) do
    recipeList[#recipeList + 1] = id
  end
  table.sort(recipeList)
  
  for i, id in ipairs(recipeList) do
    local r = recipes[id]
    local short = string.match(id, "^%w+:(.+)$") or id
    local target = r.sendTo or "?"
    if i <= 9 then
      outputln("  " .. i .. ". " .. short .. " -> " .. target .. " (keep " .. r.count .. ")")
    end
  end
  
  if #recipeList == 0 then
    outputln("  (no recipes defined)")
  end
  
  outputln("")
  outputln("Stock tracked: " .. countTable(stockCache) .. " item types")
end

local function showStockScreen()
  clearScreen()
  drawHeader("CURRENT STOCK")
  updateStockCache()
  
  local items = {}
  for id, count in pairs(stockCache) do
    if count > 0 then
      items[#items + 1] = { id = id, count = count }
    end
  end
  
  table.sort(items, function(a, b) return a.count > b.count end)
  
  local y = 4
  for i = 1, math.min(20, #items) do
    local item = items[i]
    local short = string.match(item.id, "^%w+:(.+)$") or item.id
    outputln(string.format("%2d. %-25s %6d", i, short, item.count))
  end
  
  if #items == 0 then
    outputln("  (no items in stock)")
  end
  
  outputln("")
  outputln("(press any key to return...)")
  readkey()
end

local function showCraftController()
  clearScreen()
  drawHeader("CRAFT CONTROLLER")
  
  local recipeList = {}
  for id in pairs(recipes) do
    recipeList[#recipeList + 1] = id
  end
  table.sort(recipeList)
  
  selectedRecipe = selectedRecipe or 1
  if selectedRecipe > #recipeList then
    selectedRecipe = 1
  end
  
  local recipeId = recipeList[selectedRecipe]
  if not recipeId then
    outputln("No recipe selected!")
    readkey()
    return
  end
  
  local r = recipes[recipeId]
  outputln("Recipe: " .. recipeId)
  outputln("Output: " .. r.count .. "x " .. r.output)
  outputln("Send to: " .. (r.sendTo or "unknown"))
  outputln("")
  outputln("INGREDIENTS:")
  
  for i, ingId in ipairs(r.ingredients) do
    local need = r.ingredientCounts[i] or 1
    local have = getStock(ingId)
    local short = string.match(ingId, "^%w+:(.+)$") or ingId
    local status = have >= need and "[OK] " or "[LOW] "
    outputln("  " .. status .. short .. ": " .. have .. "/" .. need)
  end
  
  outputln("")
  outputln("[1] Execute craft")
  outputln("[2] Show queue")
  outputln("[Q] Back")
  outputln("")
  output("Choice: ")
  local choice = readln()
  if not choice then return end
  
  local queue, err = buildCraftQueue(r.output, r.count)
  if err and err ~= "in stock" then
    outputln("Error: " .. err)
    readkey()
    return
  end
  
  if err == "in stock" then
    outputln(r.output .. " is already in stock")
    readkey()
    return
  end
  
  if choice == "2" then
    outputln("")
    outputln("CRAFT QUEUE:")
    for i, step in ipairs(queue) do
      local short = string.match(step.item, "^%w+:(.+)$") or step.item
      outputln("  " .. i .. ". " .. step.count .. "x " .. short)
    end
    readkey()
    return
  end
  
  -- Execute
  outputln("")
  outputln("EXECUTING...")
  for _, step in ipairs(queue) do
    local short = string.match(step.item, "^%w+:(.+)$") or step.item
    local ok, msg = executeCraftToPort(step.item, step.count, r.sendTo)
    local status = ok and "[OK] " or "[FAIL] "
    outputln("  " .. status .. short .. ": " .. msg)
  end
  
  updateStockCache()
  outputln("")
  outputln("Done.")
  readkey()
  selectedRecipe = nil
end

-- ---------------------------------------------------------------------------
-- MAIN LOOP
-- ---------------------------------------------------------------------------

local function main()
  loadClipboard()
  updateStockCache()
  
  local running = true
  
  while running do
    showMainMenu()
    
    local key = readkey()
    if not key then
      running = false
      break
    end
    
    if key == keys.q or key == keys.escape then
      running = false
    elseif key == keys.r then
      loadClipboard()
      updateStockCache()
    elseif key == keys.c then
      showStockScreen()
    elseif key == keys.t then
      if selectedRecipe then
        showCraftController()
      else
        outputln("Enter recipe number (1-" .. countTable(recipes) .. "):")
        output("> ")
        local n = readln()
        if n then
          local num = tonumber(n)
          if num and num >= 1 and num <= countTable(recipes) then
            selectedRecipe = num
            showCraftController()
          end
        end
      end
    elseif type(key) == "number" and key >= 48 and key <= 57 then
      -- Number keys 0-9 (ASCII codes). Convert to recipe index.
      local num = key - 48  -- '0'→0, '1'→1, ..., '9'→9
      if num >= 1 and num <= #recipeList then
        selectedRecipe = num
        showCraftController()
      else
        outputln("No recipe #" .. num)
        readkey()
      end
    else
      -- Unknown key, just wait for another
    end
  end
  
  outputln("\nShutting down.\n")
end

-- Run
main()