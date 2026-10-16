_G.LotroZhItemEnglishLookup = {};
local api = _G.LotroZhItemEnglishLookup;
-- Retain every imported shard in an explicit global registry. No temporary
-- global, and no permanent empty entry when import fails or is already cached.
_G.LotroZhItemEnglishShards = _G.LotroZhItemEnglishShards or {};
local registry = _G.LotroZhItemEnglishShards;
api.available_shards = nil; -- Filled by the offline exporter.

function api.Normalize(text)
    text = (text or ""):gsub("<[^>]*>", "");
    text = text:gsub("\239\187\191", ""):gsub("\226\128\139", "");
    text = text:gsub("\194\160", " "):gsub("\227\128\128", " ");
    text = text:gsub("%[[A-Za-z!0-9]+%]$", "");
    if text:match("^%s*%[.*%]%s*$") then
        text = text:gsub("^%s*%[", ""):gsub("%]%s*$", "");
        text = text:gsub("^%d+%s+", "");
    end
    text = text:match("^%s*(.-)%s*$"):gsub("%s+", " ");
    return text;
end

local function containsHan(text)
    for a,b,c in text:gmatch("([\224-\239])([\128-\191])([\128-\191])") do
        local code = (a:byte()-224)*4096 + (b:byte()-128)*64 + c:byte()-128;
        if code >= 0x3400 and code <= 0x9fff then return true; end
    end
    return false;
end

function api.Diagnostics()
    local d = api.last or {};
    local bytes = {};
    for i=1,math.min(#(d.name or ""),90) do bytes[#bytes+1]=string.format("%02X",d.name:byte(i)); end
    return "result="..tostring(d.result).."; shard="..tostring(d.shard).."; UTF8="..table.concat(bytes," ").."; error="..tostring(d.error);
end

function api.Find(text)
    local name = api.Normalize(text);
    local detail={ name=name };
    api.last=detail;
    local function finish(options,result,err)
        detail.result=result;detail.error=err;
        return options,result,detail;
    end
    if name == "" then return finish({},"empty"); end
    if not containsHan(name) then return finish({ name },"already_english"); end
    local first, second = name:byte(1), name:byte(2);
    local shard = string.format("%02X%02X", first or 0, second or 0);
    detail.shard=shard;
    if api.available_shards and not api.available_shards[shard] then return finish({},"missing"); end
    if registry[shard] == nil then
        local ok,err = pcall(function() import("LotroZh.ItemEnglish.Data.Shard_" .. shard); end);
        if not ok then return finish({},"load_error",tostring(err)); end
        if type(registry[shard]) ~= "table" then return finish({},"load_error","Import returned without registering shard"); end
    end
    local matches = registry[shard][name];
    if matches then return finish(matches,#matches > 1 and "ambiguous" or "exact"); end
    return finish({},"missing");
end
