import "Turbine";
import "Turbine.Gameplay";
import "Turbine.UI";
import "Turbine.UI.Lotro";
import "LotroZh.ItemEnglish.Lookup";

local lookup = LotroZhItemEnglishLookup;
-- Native UI/Shell registries must not be relied on to retain Lua wrappers.
-- Keep every control and the command alive until this apartment is unloaded.
LotroZhItemEnglishState = { controls = {} };
local state = LotroZhItemEnglishState;
local function retain(control)
    table.insert(state.controls, control);
    return control;
end
state.window = retain(Turbine.UI.Lotro.Window());
local window = state.window;
window:SetSize(570, 360);
window:SetPosition(150, 160);
window:SetText("English item name");

local function label(text, x, y, width, height)
    local control = retain(Turbine.UI.Label());
    control:SetParent(window); control:SetPosition(x,y); control:SetSize(width,height);
    control:SetText(text); control:SetFont(Turbine.UI.Lotro.Font.Verdana16);
    return control;
end
label("Drop an item here, or enter its Chinese name:",20,48,530,30);
local slot = retain(Turbine.UI.Lotro.Quickslot());
slot:SetParent(window); slot:SetPosition(22,85); slot:SetSize(40,40);
slot:SetAllowDrop(true); slot:SetUseOnRightClick(false);
-- The shortcut is cleared synchronously after reading the name. It never
-- remains here as an item button that could be activated by a later click.
local name = retain(Turbine.UI.Lotro.TextBox());
name:SetParent(window); name:SetPosition(75,88); name:SetSize(365,28);
name:SetFont(Turbine.UI.Lotro.Font.Verdana16);
local search = retain(Turbine.UI.Lotro.Button());
search:SetParent(window); search:SetPosition(450,88); search:SetSize(95,28); search:SetText("Find");
local status = label("Select English text, Ctrl+A / Ctrl+C; paste into Auction House.",20,135,530,40);
local output = retain(Turbine.UI.Lotro.TextBox());
output:SetParent(window); output:SetPosition(22,183); output:SetSize(525,38);
output:SetFont(Turbine.UI.Lotro.Font.Verdana18);
output:SetMultiline(false);
local previous = retain(Turbine.UI.Lotro.Button());
previous:SetParent(window); previous:SetPosition(22,238); previous:SetSize(105,28); previous:SetText("Prev");
local next = retain(Turbine.UI.Lotro.Button());
next:SetParent(window); next:SetPosition(140,238); next:SetSize(105,28); next:SetText("Next");
local count = label("",265,238,280,28);
label("Name lookup only. No chat messages are sent and no item is used.",20,285,530,32);
local matches, index = {}, 1;
local function show()
    output:SetText(matches[index] or "");
    count:SetText(#matches > 0 and (tostring(index).." / "..tostring(#matches)) or "0 / 0");
end
local function find()
    local state;
    matches, state = lookup.Find(name:GetText()); index = 1;
    if state == "ambiguous" then
        status:SetText("Multiple English names: check Prev / Next before copying.");
    elseif state == "load_error" then
        status:SetText("Dictionary load failed. Use /zhenitem debug; retry Find.");
        Turbine.Shell.WriteLine("[Item English 0.1.4] " .. lookup.Diagnostics());
    elseif state == "missing" or state == "empty" then
        status:SetText("No exact match. Check the name, or use /zhenitem debug.");
    else
        status:SetText("Click English text: Ctrl+A / Ctrl+C. Auction House: Ctrl+V.");
    end
    show();
end
search.Click = find;
previous.Click = function() if #matches > 0 then index = (index - 2) % #matches + 1; show(); end end;
next.Click = function() if #matches > 0 then index = index % #matches + 1; show(); end end;
local handlingDrop = false;
slot.ShortcutChanged = function()
    if handlingDrop then return; end
    -- Clearing a shortcut may deliver a later empty event; retain the result.
    local shortcut = slot:GetShortcut();
    if shortcut == nil or shortcut:GetType() ~= Turbine.UI.Lotro.ShortcutType.Item then return; end
    handlingDrop = true;
    local ok, itemName = pcall(function()
        local item = shortcut:GetItem();
        if item == nil then return nil; end
        return item:GetName();
    end);
    slot:SetShortcut(Turbine.UI.Lotro.Shortcut());
    handlingDrop = false;
    if ok and itemName then name:SetText(itemName); find();
    else output:SetText(""); status:SetText("Could not read item. Enter its name above."); end
end;
function state.Show()
    window:SetPosition(100,120);
    window:SetOpacity(1);
    window:SetZOrder(100);
    window:SetVisible(true);
    Turbine.Shell.WriteLine("[Item English 0.1.4] window visible=" .. tostring(window:IsVisible()) .. "; position=100,120; /zhenitem hide");
end
state.command = Turbine.ShellCommand();
local command = state.command;
function command:Execute(_, args)
    if args == "hide" then window:SetVisible(false);
    elseif args == "debug" then Turbine.Shell.WriteLine("[Item English 0.1.4] " .. lookup.Diagnostics());
    else state.Show(); end
end
function command:GetHelp() return "/zhenitem [hide|reset|debug] - English item name lookup"; end
Turbine.Shell.AddCommand("zhenitem", command);
state.Show();
Turbine.Shell.WriteLine("Item English lookup ready. /zhenitem");
