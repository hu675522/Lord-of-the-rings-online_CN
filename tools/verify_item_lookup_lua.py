"""Compile exported Lua with the local game Lua 5.1 runtime, then mock UI events.

Never launches the game or installs the plugin. The DLL is read from the local
game and is not copied or included with the generated package.
"""
import ctypes
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from localization.item_lookup.build_lookup import lua_string
from localization.item_lookup.layout import validate_layout


def main(out=None):
    out=Path(out).resolve() if out else ROOT/'localization/item_lookup/generated'
    if not out.is_relative_to(ROOT):raise ValueError('Export must be inside workspace')
    config=json.loads((ROOT/'data/original-archives.json').read_text(encoding='utf-8'))
    library=Path(config['game_directory'])/'x64/lua51.dll'
    lua=ctypes.CDLL(str(library))
    lua.luaL_newstate.restype=ctypes.c_void_p
    lua.luaL_openlibs.argtypes=[ctypes.c_void_p]
    lua.luaL_loadbuffer.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_size_t,ctypes.c_char_p]
    lua.luaL_loadbuffer.restype=ctypes.c_int
    lua.lua_pcall.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int]
    lua.lua_tolstring.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p]
    lua.lua_tolstring.restype=ctypes.c_char_p
    lua.lua_settop.argtypes=[ctypes.c_void_p,ctypes.c_int]
    lua.lua_close.argtypes=[ctypes.c_void_p]
    state=lua.luaL_newstate();lua.luaL_openlibs(state)
    def run(source,name,execute=True):
        raw=source.encode('utf-8')
        status=lua.luaL_loadbuffer(state,raw,len(raw),name.encode('utf-8'))
        if not status and execute:status=lua.lua_pcall(state,0,0,0)
        if status:raise ValueError(lua.lua_tolstring(state,-1,None).decode('utf-8'))
        lua.lua_settop(state,0)
    layout=validate_layout(out)
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'));count=0
    try:
        for record in manifest['records']:
            p=out/record['file'];raw=p.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('Exported file hash mismatch')
            if '/Data/' in record['file'] and not raw.isascii():raise ValueError('Dictionary source must be ASCII')
            if p.suffix=='.lua':run(raw.decode('utf-8'),p.name,execute=False);count+=1
        setup='''
            controls = setmetatable({}, {__mode='v'});
            commands = setmetatable({}, {__mode='v'}); local cached = {};
            function import(name)
                if name:match('^Turbine') then return end
                if IMPORT_FAULT==name then error('simulated dictionary load failure') end
                if cached[name] then return end
                local file = PLUGIN_ROOT .. '/' .. name:gsub('%.','/') .. '.lua';
                local chunk = loadfile(file); if not chunk then error('Missing plugin file') end
                if NAMESPACE_ENV and name:find('%.Data%.') then setfenv(chunk,setmetatable({}, {__index=_G})) end
                chunk();
                cached[name] = true;
            end
            local function control(kind)
                local c = {kind=kind, text='', shortcut=nil}; table.insert(controls,c);
                local setters={'Parent','Size','Position','Font','AllowDrop','UseOnRightClick','Multiline','Opacity','ZOrder'};
                for _,key in ipairs(setters) do c['Set'..key] = function(self,...) self[key]={...} end end
                function c:SetText(t) self.text=t end
                function c:GetText() return self.text end
                function c:SetVisible(v) self.visible=v end
                function c:IsVisible() return self.visible==true end
                function c:GetShortcut() return self.shortcut end
                function c:SetShortcut(value) self.shortcut=value; if self.ShortcutChanged then self.ShortcutChanged() end end
                return c;
            end
            Turbine = {Gameplay={}, UI={Lotro={Font={Verdana16=1,Verdana18=2},ShortcutType={Item=2}}},Shell={}};
            function Turbine.UI.Label() return control('Label') end
            function Turbine.UI.Lotro.Window() return control('Window') end
            function Turbine.UI.Lotro.Quickslot() return control('Quickslot') end
            function Turbine.UI.Lotro.TextBox() return control('TextBox') end
            function Turbine.UI.Lotro.Button() return control('Button') end
            function Turbine.UI.Lotro.Shortcut() return {GetType=function()return 0 end} end
            function Turbine.ShellCommand() return {} end
            function Turbine.Shell.AddCommand(name,command) commands[name]=command end
            function Turbine.Shell.WriteLine() end
            if PRELOAD_SHARD then import('LotroZh.ItemEnglish.Data.Shard_E993') end
            import(ENTRY_MODULE);
            local expectedControls=#controls;
            collectgarbage('collect'); collectgarbage('collect');
            assert(commands.zhenitem, 'Command lost after garbage collection');
            local alive=0;local win;
            for _,c in pairs(controls) do alive=alive+1;if c.kind=='Window' then win=c end end
            assert(alive==expectedControls and win, 'UI controls lost after garbage collection');
            assert(win:IsVisible(), 'Window not visible after load/collection');
            commands.zhenitem:Execute('zhenitem','hide');assert(not win:IsVisible());
            collectgarbage('collect');
            commands.zhenitem:Execute('zhenitem','');assert(win:IsVisible());
            assert(win.Position[1]==100 and win.Position[2]==120 and win.Opacity[1]==1);
            commands.zhenitem:Execute('zhenitem','reset');assert(win:IsVisible());
            local lookup=LotroZhItemEnglishLookup;
            if not PRELOAD_SHARD then
                IMPORT_FAULT='LotroZh.ItemEnglish.Data.Shard_E993';
                local a,s,d=lookup.Find('银碎片的堆积');assert(#a==0 and s=='load_error' and d.error:find('simulated'));
                IMPORT_FAULT=nil;
            end
            local screenshot,screenshotStatus=lookup.Find('银碎片的堆积');
            assert(#screenshot==1 and screenshot[1]=='Massive Pile of Silver Scraps' and screenshotStatus=='exact');
            assert(lookup.Normalize(string.char(239,187,191)..'银碎片的堆积'..string.char(194,160))=='银碎片的堆积');
            local invisible=lookup.Find('银碎片'..string.char(226,128,139)..'的堆积');assert(invisible[1]=='Massive Pile of Silver Scraps');
            local english,englishStatus=lookup.Find('Mûmak Token');assert(english[1]=='Mûmak Token' and englishStatus=='already_english');
            assert(lookup.Normalize('[3 银片大片]')=='银片大片');
            assert(lookup.Normalize('银片大片[ps]')=='银片大片');
            local options,status=lookup.Find('银片大片');assert(#options==2 and status=='ambiguous');
            local option,status=lookup.Find('银渣大堆');assert(#option==1 and option[1]=='Huge Pile of Silver Scraps');
            local missing,status=lookup.Find('此物品不存在于测试词表');assert(#missing==0 and status=='missing');
            local boxes={};local slot;
            for _,c in ipairs(controls) do if c.kind=='TextBox' then table.insert(boxes,c) end;if c.kind=='Quickslot' then slot=c end end
            local item={GetName=function() return '银碎片的堆积' end};
            slot.shortcut={GetType=function() return 2 end,GetItem=function() return item end};
            slot.ShortcutChanged();
            assert(boxes[2]:GetText()=='Massive Pile of Silver Scraps');
            assert(slot.shortcut:GetType()==0); -- no usable item remains in the slot
            slot.ShortcutChanged(); -- delayed empty event after clearing the drop
            assert(boxes[2]:GetText()=='Massive Pile of Silver Scraps');
            slot.shortcut=nil; slot.ShortcutChanged();
            assert(boxes[2]:GetText()=='Massive Pile of Silver Scraps');
            boxes[1]:SetText('银片大片');
            for _,c in ipairs(controls) do if c.text=='Find' then c.Click() end end
            assert(boxes[2]:GetText()=='Huge Pile of Silver Scraps');
            for _,c in ipairs(controls) do if c.text=='Next' then c.Click() end end
            assert(boxes[2]:GetText()=='Massive Pile of Silver Scraps');
        '''
        for mode in ('normal','preloaded','scoped'):
            prefix=('LotroZhItemEnglishState=nil;LotroZhItemEnglishLookup=nil;LotroZhItemEnglishShards=nil;IMPORT_FAULT=nil;'
                    +'PRELOAD_SHARD='+('true' if mode=='preloaded' else 'false')+';'
                    +'NAMESPACE_ENV='+('true' if mode=='scoped' else 'false')+';')
            run(prefix+'PLUGIN_ROOT='+lua_string((out/'Plugins').as_posix())+';\nENTRY_MODULE='+lua_string(layout['entry_module'])+';\n'+setup,'integration-'+mode)
    finally:lua.lua_close(state)
    report={'lua_runtime':'local game Lua 5.1 x64','compiled_lua_files':count,
        'all_exported_file_hashes_verified':True,'drag_drop_and_copy_field_mock_verified':True,
        'plural_to_singular_and_ambiguity_verified':True,'empty_shortcut_after_drop':True,
        'delayed_empty_event_retains_result':True,
        'discovery_layout_verified':True,'descriptor':layout['descriptor'],
        'entry_loaded_from_descriptor':True,'version':layout['version'],
        'weak_registry_gc_retains_window_controls_and_command':True,
        'hide_reopen_reset_after_gc_verified':True,
        'screenshot_item_exact_match_verified':True,'cached_shard_registry_verified':True,
        'shard_load_error_and_retry_verified':True,'module_scope_registry_verified':True,
        'utf8_whitespace_and_accented_english_verified':True,'dictionary_ascii_source_verified':True,
        'game_tested':False,'installed':False}
    (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',type=Path)
    main(parser.parse_args().export)
