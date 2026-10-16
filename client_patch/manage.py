"""Install/restore fully validated archives with hashes and atomic file swaps.

The build helper cannot write outside the workspace. This separate entry point
only copies finished files to the exact four paths recorded for this computer.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PATCH = Path(__file__).resolve().parent
ALLOWED = {"client_local_English.dat", "client_surface.dat", "client_surface_aux_1.datx", "client_surface_aux_2.datx"}
GAME_PROCESSES = {"lotroclient.exe", "lotroclient64.exe", "lotrolauncher.exe", "turbineinvoker.exe"}


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def game_processes():
    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("pid", wintypes.DWORD), ("heap", ctypes.c_size_t),
                    ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("parent", wintypes.DWORD), ("priority", wintypes.LONG),
                    ("flags", wintypes.DWORD), ("name", wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    found = []
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        valid = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        if not valid:
            raise ctypes.WinError(ctypes.get_last_error())
        while valid:
            if entry.name.casefold() in GAME_PROCESSES:
                found.append(entry.name)
            valid = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(snapshot)
    return found


def require_closed():
    running = game_processes()
    if running:
        raise RuntimeError("请先退出游戏和启动器，再重试：" + ", ".join(running))


def load_plan():
    plan = json.loads((PATCH / "package/install-plan.json").read_text(encoding="utf-8"))
    if not plan.get("all_workspace_checks_passed") or {a["name"] for a in plan["archives"]} != ALLOWED:
        raise ValueError("安装计划尚未通过完整副本校验")
    for archive in plan["archives"]:
        name = archive["name"]
        if Path(archive["backup"]).resolve() != (PATCH / "backups" / (name + ".original")).resolve():
            raise ValueError("备份路径不属于本补丁")
        if Path(archive["candidate"]).resolve() != (PATCH / "work" / name).resolve():
            raise ValueError("候选路径不属于本补丁")
        if "previous_candidate" in archive:
            if Path(archive["previous_candidate"]).resolve() != (PATCH / "work/previous" / name).resolve():
                raise ValueError("上版候选路径不属于本补丁")
    return plan


def write_receipt(state, plan):
    receipt = {"state": state, "updated_at": datetime.now(timezone.utc).isoformat(),
               "task": plan["task"], "install_directory": plan["install_directory"],
               "game_rendering_verified": False,
               "archives": [{k: a[k] for k in ("name", "original_sha256", "patched_sha256")} for a in plan["archives"]]}
    path = PATCH / "installed-receipt.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def transition(plan, restoring=False):
    policy_path = PATCH / "deployment-policy.json"
    if not restoring and policy_path.exists():
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        if not policy.get("deployment_enabled", False):
            raise ValueError("暂不部署：" + policy.get("reason", "本地汉化制作期间已禁用安装"))
    require_closed()
    install = Path(plan["install_directory"]).resolve()
    desired_key = "original_sha256" if restoring else "patched_sha256"
    print("校验备份、候选和当前游戏文件；操作完成前请不要启动游戏。", flush=True)
    actions = []
    for archive in plan["archives"]:
        name = archive["name"]
        backup = Path(archive["backup"]).resolve()
        candidate = Path(archive["candidate"]).resolve()
        target = install / name
        if file_hash(backup) != archive["original_sha256"]:
            raise ValueError("原始备份校验失败，停止：" + name)
        source = backup if restoring else candidate
        expected = archive[desired_key]
        if file_hash(source) != expected:
            raise ValueError("安装/还原来源校验失败，停止：" + name)
        current = file_hash(target)
        known = {archive["original_sha256"]: backup, archive["patched_sha256"]: candidate}
        if archive.get("previous_sha256") and archive.get("previous_candidate"):
            previous = Path(archive["previous_candidate"]).resolve()
            if file_hash(previous) != archive["previous_sha256"]:
                raise ValueError("上版回滚副本校验失败，停止：" + name)
            known[archive["previous_sha256"]] = previous
        if current not in known:
            raise ValueError("游戏文件与备份/本补丁均不匹配，可能已经更新；为避免覆盖新版本，已停止：" + name)
        if current == expected:
            print("无需更改：" + name, flush=True)
            continue
        actions.append({"archive": archive, "target": target, "source": source,
                        "expected": expected, "before": current, "before_source": known[current]})
    staged, changed = [], []
    try:
        # All staging copies finish before replacing the first game file.
        for action in actions:
            stage = action["target"].with_name(action["target"].name + ".lotrozh-" + uuid.uuid4().hex + ".tmp")
            staged.append(stage)
            print("准备替换：" + action["target"].name, flush=True)
            shutil.copyfile(action["source"], stage)
            if file_hash(stage) != action["expected"]:
                raise ValueError("安装暂存文件校验失败")
            action["stage"] = stage
        require_closed()
        for action in actions:
            require_closed()
            if file_hash(action["target"]) != action["before"]:
                raise ValueError("准备期间游戏文件变化，停止替换")
            os.replace(action["stage"], action["target"])
            changed.append(action)
            if file_hash(action["target"]) != action["expected"]:
                raise ValueError("替换后的文件校验失败")
            print("已校验：" + action["target"].name, flush=True)
        write_receipt("restored" if restoring else "installed-for-testing", plan)
        print("已还原原始资源包。" if restoring else "验证补丁安装完成；真实游戏显示仍待测试。", flush=True)
    except Exception:
        # Restore exactly the state present before this invocation. A prior
        # partial install can contain both original and patched archives.
        rollback_errors = []
        for action in reversed(changed):
            previous = action["before_source"]
            rollback = action["target"].with_name(action["target"].name + ".lotrozh-rollback.tmp")
            try:
                shutil.copyfile(previous, rollback)
                if file_hash(rollback) != action["before"]:
                    raise ValueError("回滚暂存校验失败")
                os.replace(rollback, action["target"])
                print("已回滚：" + action["target"].name, flush=True)
            except Exception as exc:
                rollback_errors.append(str(exc))
        if rollback_errors:
            raise RuntimeError("自动回滚未完全成功；请保持游戏关闭并使用备份恢复：" + "; ".join(rollback_errors))
        raise
    finally:
        for stage in staged:
            stage.unlink(missing_ok=True)


def install_font_test(directory):
    destination = Path(directory).resolve()
    source = PATCH / "font_test"
    files = [Path("LotroZhTest/LotroZhFontTest.plugin"), Path("LotroZhTest/Main.lua"),
             Path("LotroZhTest/Diagnostic.lua")]
    for relative in files:
        target = destination / relative
        if target.exists() and file_hash(target) != file_hash(source / relative):
            raise ValueError("已有同名插件内容不同，未覆盖：" + str(target))
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    print("已安装字体测试插件；进入游戏后输入 /plugins load LotroZhFontTest。", flush=True)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("install", "restore", "status"))
    parser.add_argument("--plugins-dir")
    args = parser.parse_args()
    plan = load_plan()
    if args.command == "status":
        receipt = PATCH / "installed-receipt.json"
        print(receipt.read_text(encoding="utf-8") if receipt.exists() else "尚未安装验证补丁。")
        print("游戏/启动器进程：" + ", ".join(game_processes()))
        return
    transition(plan, restoring=args.command == "restore")
    if args.command == "install" and args.plugins_dir:
        install_font_test(args.plugins_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("停止：" + str(error), file=sys.stderr)
        sys.exit(1)
