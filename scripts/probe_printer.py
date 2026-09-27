#!/usr/bin/env python3
"""Read-only macOS Epson baseline probe; no print jobs or configuration changes.

Uses only Python's standard library. Raw device IDs, preference values, passwords,
and tokens are never written. Bonjour is observed through a PTY to avoid buffering.
"""
import argparse
import concurrent.futures
import datetime
import ipaddress
import json
import os
from pathlib import Path
import plistlib
import pty
import re
import select
import shutil
import signal
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request

SERVICES = ("_ipp._tcp", "_ipps._tcp", "_printer._tcp", "_pdl-datastream._tcp")
EPSON = re.compile(r"epson|\bL(?:805[08]?|18050|18058)\b", re.I)
MODELS = re.compile(r"\b(?:L\d{3,5}|ET-\d{3,5}|XP-\d{3,5}|WF-\d{3,5})\b", re.I)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def models(text):
    return sorted(set(m.upper() for m in MODELS.findall(text)))


def local_target(uri):
    try:
        host = urllib.parse.urlsplit(uri).hostname or ""
    except ValueError:
        return False
    try:
        address = ipaddress.ip_address(host)
        return address.is_private or address.is_link_local or address.is_loopback
    except ValueError:
        return host.rstrip(".").lower().endswith(".local")


def safe_endpoint(uri):
    """Reject credential-bearing URLs; never return their original representation."""
    try:
        parts = urllib.parse.urlsplit(uri)
        if parts.username is not None or parts.password is not None:
            return None, "credential_endpoint_skipped"
        if not parts.hostname or parts.scheme not in ("ipp", "ipps", "http", "https"):
            return None, "invalid_endpoint_skipped"
        host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
        netloc = f"{host}:{parts.port}" if parts.port else host
        return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path or "/", "", "")), "ok"
    except ValueError:
        return None, "invalid_endpoint_skipped"


def run(argv, timeout=8, observe=False):
    """Return metadata and transient raw text. Observation expiry is not failure."""
    meta = {"tool": argv[0], "arguments": argv[1:], "timeout_seconds": timeout}
    executable = shutil.which(argv[0])
    if not executable:
        return dict(meta, status="tool_missing", returncode=None), ""
    started = time.monotonic()
    proc = None
    master = slave = None
    raw = b""
    environment = dict(os.environ, LC_ALL="C", LANG="C")
    try:
        if observe:
            master, slave = pty.openpty()
            proc = subprocess.Popen([executable] + argv[1:], stdout=slave,
                                    stderr=slave, stdin=subprocess.DEVNULL,
                                    start_new_session=True, env=environment)
            os.close(slave)
            slave = None
            deadline = started + timeout
            while time.monotonic() < deadline:
                if select.select([master], [], [], min(.2, max(0, deadline-time.monotonic())))[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    raw += chunk
                if proc.poll() is not None:
                    break
            expired = proc.poll() is None
            if expired:
                os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=2)
            status = "observation_window_elapsed" if expired else ("ok" if proc.returncode == 0 else "tool_failed")
        else:
            proc = subprocess.Popen([executable] + argv[1:], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                    start_new_session=True, env=environment)
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                raw = stdout + (b"\n" + stderr if stderr else b"")
                status = "ok" if proc.returncode == 0 else "tool_failed"
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                stdout, stderr = proc.communicate(timeout=2)
                raw = stdout + stderr
                status = "timed_out"
        meta.update(status=status, returncode=proc.returncode,
                    elapsed_seconds=round(time.monotonic()-started, 3))
    except (OSError, subprocess.SubprocessError) as exc:
        meta.update(status="tool_failed", returncode=proc.poll() if proc else None,
                    error_type=type(exc).__name__)
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
    finally:
        for fd in (master, slave):
            if fd is not None:
                os.close(fd)
    return meta, raw.decode("utf-8", "replace")


def read_plist(path):
    try:
        return plistlib.loads(path.read_bytes()), "ok"
    except FileNotFoundError:
        return None, "not_found"
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None, "read_failed"


def remote_info():
    app = Path("/Applications/Epson Software/Epson Remote Print Utility.app")
    info, status = read_plist(app / "Contents/Info.plist")
    result = {"installed": app.exists(), "info_status": status}
    if info:
        result["version"] = info.get("CFBundleShortVersionString")
    pref = Path.home()/"Library/Preferences/com.epson.ijprinter.RemotePrintUtility.plist"
    data, status = read_plist(pref)
    result["user_preferences_status"] = status
    # Only identify model strings and existence of registration-like top-level fields.
    result["registration_status"] = "not_verifiable_from_preferences"
    if isinstance(data, dict):
        values = [v for v in data.values() if isinstance(v, str)]
        result["model_mentions"] = models(" ".join(values))
        result["ui_preferences_only"] = all(str(k).startswith("NS") for k in data)
    result["note"] = "应用已安装不代表已建立本地队列；用户界面偏好不能证明设备在线。"
    return result


def queue_info():
    meta, raw = run(["lpstat", "-p", "-d", "-v"])
    queue_names = re.findall(r"^printer\s+(\S+)\s", raw, re.M)
    endpoints = dict(re.findall(r"^device for ([^:]+):\s*(\S+)", raw, re.M))
    entries = []
    targets = []
    for index, name in enumerate(dict.fromkeys(queue_names), 1):
        entry = {"alias": f"queue-{index}", "epson": bool(EPSON.search(name))}
        uri = endpoints.get(name, "")
        try:
            entry["transport"] = urllib.parse.urlsplit(uri).scheme
        except ValueError:
            entry["transport"] = "invalid_uri"
        opt_meta, options = run(["lpoptions", "-p", name, "-l"])
        opt_meta["arguments"] = ["-p", entry["alias"], "-l"]
        entry["lpoptions"] = opt_meta
        entry["option_keys"] = [line.split("/", 1)[0].split(":", 1)[0]
                                for line in options.splitlines() if ":" in line][:150]
        ppd = Path("/etc/cups/ppd")/(name + ".ppd")
        try:
            text = ppd.read_text(errors="replace")
            entry["ppd_status"] = "ok"
            name_lines = " ".join(re.findall(r'^\*(?:NickName|ModelName|Manufacturer):.*$', text, re.M))
            entry["epson"] = entry["epson"] or bool(EPSON.search(name_lines))
            entry["models"] = models(name_lines)
            entry["ppd_filter_declarations"] = re.findall(r'^\*cupsFilter2?:\s*"([^\"]+)"', text, re.M)
            entry["tray_related_options_present"] = bool(re.search(r"PVC|Disc|CD/DVD|ManuCDR|DiskTray", text, re.I))
        except FileNotFoundError:
            entry["ppd_status"] = "not_found"
        except OSError:
            entry["ppd_status"] = "read_failed"
        if entry["epson"] and entry["transport"] in ("ipp", "ipps"):
            targets.append(uri)
        entries.append(entry)
    recognized = bool(queue_names or re.search(r"(?:no system default destination|system default destination:|No destinations)", raw, re.I))
    collection = meta["status"] if meta["status"] != "ok" else ("ok" if recognized else "parse_failed")
    return {"command": meta, "collection_status": collection, "queues": entries,
            "queue_count": len(entries) if collection == "ok" else None,
            "epson_queue_count": sum(x["epson"] for x in entries) if collection == "ok" else None}, targets


def usb_info():
    sp_meta, raw = run(["system_profiler", "SPUSBDataType", "-json"], timeout=12)
    found = []
    nodes = 0
    sp_meta["parse_status"] = "not_parsed"
    try:
        data = json.loads(raw) if sp_meta["status"] == "ok" else None
        def visit(value):
            nonlocal nodes
            if isinstance(value, dict):
                nodes += 1
                description = " ".join(str(value.get(k, "")) for k in ("_name", "manufacturer", "vendor_id"))
                if EPSON.search(description) or "0x04b8" in description.lower():
                    found.append({"models": models(description), "epson_vendor": True})
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        if isinstance(data, dict) and isinstance(data.get("SPUSBDataType"), list):
            sp_meta["parse_status"] = "ok"
            visit(data.get("SPUSBDataType", []))
        elif sp_meta["status"] == "ok":
            sp_meta["parse_status"] = "parse_failed"
    except (ValueError, TypeError):
        sp_meta["parse_status"] = "parse_failed"
    io_meta, io = run(["ioreg", "-p", "IOUSB", "-l", "-w", "0"])
    io_meta["parse_status"] = ("ok" if "+-o" in io else "parse_failed") if io_meta["status"] == "ok" else "not_parsed"
    # No raw ioreg text or unrelated hardware identifiers are retained.
    relevant = [line for line in io.splitlines() if EPSON.search(line) or re.search(r'"idVendor"\s*=\s*1208\b', line)]
    sp_valid = sp_meta["status"] == "ok" and sp_meta["parse_status"] == "ok"
    io_valid = io_meta["status"] == "ok" and io_meta["parse_status"] == "ok"
    return {"system_profiler": sp_meta, "enumerated_nodes": nodes if sp_valid else None,
            "epson_devices": found, "ioreg": io_meta,
            "collection_status": "ok" if sp_valid and io_valid else "partial_or_failed",
            "target_record_count": len(found)+len(relevant) if sp_valid and io_valid else None,
            "ioreg_epsontarget_mentions": len(relevant) if io_valid else None, "ioreg_models": models(" ".join(relevant)),
            "coverage_note": "SPUSBDataType为空时以ioreg补查；两者未发现也只代表本次系统枚举未见目标。"}


def browse(service):
    meta, raw = run(["dns-sd", "-B", service, "local."], timeout=7, observe=True)
    instances = []
    for line in raw.splitlines():
        match = re.search(r"\bAdd\s+\S+\s+\d+\s+\S+\s+\S+\s+(.+)$", line)
        if match:
            name = match.group(1).strip()
            if name not in instances:
                instances.append(name)
    epson = [name for name in instances if EPSON.search(name)]
    tool_ok = meta["status"] in ("ok", "observation_window_elapsed")
    # macOS emits the Timestamp table heading only after the first result.
    # A valid startup line with no Add rows is a successful empty observation.
    add_rows = [line for line in raw.splitlines() if re.search(r"\bAdd\s+", line)]
    parsed = (f"Browsing for {service}.local." in raw and
              all(re.search(r"\bAdd\s+\S+\s+\d+\s+\S+\s+\S+\s+(.+)$", line) for line in add_rows))
    collection = ("ok" if parsed else "parse_failed") if tool_ok else meta["status"]
    record = {"service": service, "command": meta, "collection_status": collection,
              "discovered_instance_count": len(instances) if collection == "ok" else None,
              "epson_instance_count": len(epson) if collection == "ok" else None, "epson_models": models(" ".join(epson))}
    targets = []
    resolutions = []
    for index, name in enumerate(epson[:5] if collection == "ok" else [], 1):
        resolution, text = run(["dns-sd", "-L", name, service, "local."], timeout=5, observe=True)
        resolution["arguments"] = ["-L", f"epson-service-{index}", service, "local."]
        match = re.search(r"can be reached at\s+([^\s:]+):(\d+)", text)
        resolution["endpoint_resolved"] = bool(match)
        if match and service in ("_ipp._tcp", "_ipps._tcp"):
            host, port = match.groups()
            rp_match = re.search(r"(?:^|\s)rp=([^\s]+)", text)
            resource = rp_match.group(1).strip('"') if rp_match else "ipp/print"
            scheme = "ipps" if service == "_ipps._tcp" else "ipp"
            targets.append(f"{scheme}://{host}:{port}/{resource.lstrip('/')}")
        elif match:
            # Read the identified printer's HTTP information page, never its
            # LPD/9100 print port. A failed GET is reported, without port scanning.
            targets.append(f"http://{match.group(1)}/")
        resolutions.append(resolution)
    record["resolutions"] = resolutions
    return record, targets


def ipp_attributes(uri):
    """Only IPP operation 0x000B (Get-Printer-Attributes), never Print-Job."""
    uri, policy = safe_endpoint(uri)
    if policy != "ok":
        return {"operation": "Get-Printer-Attributes", "operation_id": 11, "status": policy, "request_sent": False}
    def attribute(tag, name, value):
        name, value = name.encode(), value.encode()
        return bytes([tag])+struct.pack(">H", len(name))+name+struct.pack(">H", len(value))+value
    payload = b"\x02\x00\x00\x0b\x00\x00\x00\x01\x01"
    payload += attribute(0x47, "attributes-charset", "utf-8")
    payload += attribute(0x48, "attributes-natural-language", "en")
    payload += attribute(0x45, "printer-uri", uri)
    requested = ("printer-make-and-model", "printer-state", "operations-supported", "document-format-supported")
    for index, value in enumerate(requested):
        payload += attribute(0x44, "requested-attributes" if index == 0 else "", value)
    payload += b"\x03"
    endpoint = urllib.parse.urlsplit(uri)
    scheme = "https" if endpoint.scheme == "ipps" else "http"
    host = f"[{endpoint.hostname}]" if ":" in endpoint.hostname else endpoint.hostname
    netloc = f"{host}:{endpoint.port or 631}"
    url = urllib.parse.urlunsplit((scheme, netloc, endpoint.path, "", ""))
    result = {"operation": "Get-Printer-Attributes", "operation_id": 11,
              "endpoint_scheme": endpoint.scheme, "timeout_seconds": 6, "request_sent": False}
    try:
        request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/ipp"}, method="POST")
        # Do not forward local printer metadata through environment-configured proxies.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        result["request_sent"] = True
        with opener.open(request, timeout=6) as response:
            data = response.read(262144)
            result["http_status"] = response.status
        if len(data) < 8:
            return dict(result, status="invalid_ipp_response")
        status = struct.unpack(">H", data[2:4])[0]
        result.update(ipp_status_code=status, status="ok" if status < 0x100 else "ipp_error")
        # Whitelist four capability fields; never retain serial/UUID/device ID values.
        offset, name, attrs = 8, "", {}
        while offset < len(data):
            tag = data[offset]; offset += 1
            if tag == 3:
                break
            if tag <= 15:
                continue
            n = struct.unpack(">H", data[offset:offset+2])[0]; offset += 2
            if n:
                name = data[offset:offset+n].decode("utf-8", "replace")
            offset += n
            n = struct.unpack(">H", data[offset:offset+2])[0]; offset += 2
            value = data[offset:offset+n]; offset += n
            if name not in requested:
                continue
            if name == "printer-make-and-model":
                parsed = {"epson": bool(EPSON.search(value.decode(errors="replace"))), "models": models(value.decode(errors="replace"))}
            elif tag in (0x21, 0x23) and len(value) == 4:
                parsed = struct.unpack(">i", value)[0]
            else:
                parsed = value.decode("utf-8", "replace")[:120]
            attrs.setdefault(name, []).append(parsed)
        result["attributes"] = attrs
    except Exception as exc:
        timed_out = isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout))
        result.update(status="timed_out" if timed_out else "request_failed", error_type=type(exc).__name__)
    return result


def http_info(uri):
    result = {"operation": "HTTP GET device information", "timeout_seconds": 6, "request_sent": False}
    uri, policy = safe_endpoint(uri)
    if policy != "ok":
        return dict(result, status=policy)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        result["request_sent"] = True
        with opener.open(urllib.request.Request(uri, method="GET"), timeout=6) as response:
            data = response.read(262144).decode("utf-8", "replace")
            result.update(status="ok", http_status=response.status,
                          epson_mention=bool(EPSON.search(data)), models=models(data))
    except Exception as exc:
        timed_out = isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout))
        result.update(status="timed_out" if timed_out else "request_failed", error_type=type(exc).__name__)
    return result


def installed_tools():
    names = ("lpstat", "lpoptions", "cupsfilter", "cupstestppd", "gs", "escputil", "gutenprint-version", "ijsgutenprint.5.3", "ijsgutenprint.5.2", "dns-sd", "system_profiler", "ioreg")
    paths = [Path("/Library/Printers/EPSON/InkjetPrinter2/Filter/rastertoescpII.app/Contents/MacOS/rastertoescpII"),
             Path("/Library/Printers/EPSON/InkjetPrinter2/Backend/epsonremote.app/Contents/MacOS/epsonremote")]
    support = Path("/Library/Printers/EPSON/InkjetPrinter2/SupportPrinters")
    return {"executables": {name: shutil.which(name) for name in names},
            "epson_binaries": [{"path": str(p), "exists": p.is_file()} for p in paths],
            "installed_l8050_family_data": [p.name for p in support.glob("*L805*.data")] if support.exists() else [],
            "gutenprint_paths": [str(p) for base in (Path("/Library/Printers"), Path("/usr/local/lib"), Path("/opt/homebrew/lib")) if base.exists() for p in base.glob("*gutenprint*")]}


def platform_info():
    result = {}
    for key, argv, pattern in (("macos_version", ["sw_vers", "-productVersion"], r"\d+(?:\.\d+)+"),
                               ("architecture", ["uname", "-m"], r"arm64|x86_64|i386")):
        meta, text = run(argv)
        value = text.strip()
        valid = meta["status"] == "ok" and re.fullmatch(pattern, value)
        result[key] = {"value": value if valid else None, "command": meta}
    return result


def observation_summary(result):
    q, usb, discovery = result["queues"], result["usb"], result["bonjour"]
    queue_line = (f"本地打印队列：{q['queue_count']} 个；Epson 队列 {q['epson_queue_count']} 个。"
                  if q["collection_status"] == "ok" else "本地打印队列：未知／检查失败；不能判为未发现。")
    usb_line = (f"USB：Epson 相关记录 {usb['target_record_count']} 条；system_profiler 枚举节点 {usb['enumerated_nodes']} 个。"
                if usb["collection_status"] == "ok" else "USB：未知／部分检查失败；详见各工具状态，不能判为未发现。")
    known = all(b["collection_status"] == "ok" for b in discovery)
    count = sum(b["epson_instance_count"] for b in discovery) if known else None
    durations = "、".join(f"{b['service']} {b['command'].get('elapsed_seconds', '未知')} 秒" for b in discovery)
    outcome = f"发现 Epson 服务 {count} 项" if known else "总数未知／部分检查失败，不能判为未发现"
    return [queue_line, usb_line, f"Bonjour：{outcome}；实际观察时长：{durations}。"], count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = {"schema_version": 1, "timestamp": datetime.datetime.now().astimezone().isoformat(),
              "scope": "read_only_baseline", "raw_identifiers_saved": False}
    result["platform"] = platform_info()
    result["queues"], targets = queue_info()
    result["remote_utility"] = remote_info()
    result["installed_tools"] = installed_tools()
    result["usb"] = usb_info()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        discoveries = list(executor.map(browse, SERVICES))
    result["bonjour"] = [r for r, _ in discoveries]
    for _, discovered in discoveries:
        targets.extend(discovered)
    result["network_checks"] = []
    for index, uri in enumerate((uri for uri in dict.fromkeys(targets) if local_target(uri)), 1):
        check = ipp_attributes(uri) if urllib.parse.urlsplit(uri).scheme in ("ipp", "ipps") else http_info(uri)
        check["endpoint_alias"] = f"epson-endpoint-{index}"
        result["network_checks"].append(check)
    result["network_note"] = "只查询已识别Epson的私有IP或.local端点；不访问远程云端、不扫描子网。Bonjour按服务名称识别Epson，改名的设备可能漏检。"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "diagnostics.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    os.chmod(output, 0o600)
    summaries, bonjour_count = observation_summary(result)
    usb_count = result["usb"]["target_record_count"]
    request_count = sum(bool(check.get("request_sent")) for check in result["network_checks"])
    lines = ["# L8058 第一步：本机连接基线", "", f"检查时间：{result['timestamp']}", "",
             f"- macOS：{result['platform']['macos_version']['value'] or '未知'}；架构：{result['platform']['architecture']['value'] or '未知'}。",
             *["- "+line for line in summaries],
             f"- Epson Remote Print Utility：{'已安装' if result['remote_utility']['installed'] else '未发现'}，版本 {result['remote_utility'].get('version', '未知')}。",
             "- Remote 用户偏好仅作最小读取；未从界面偏好确认设备登记或在线状态。",
             f"- 向已识别 Epson 端点发起的只读 IPP/HTTP 查询：{request_count} 次。", "",
             "## 工具与结果状态", "", "| 检查 | 状态 | 退出码 |", "|---|---|---|"]
    records = [("sw_vers", result["platform"]["macos_version"]["command"]), ("uname -m", result["platform"]["architecture"]["command"]), ("lpstat", result["queues"]["command"]), ("USB system_profiler", result["usb"]["system_profiler"]), ("USB ioreg", result["usb"]["ioreg"])]
    records += [(b["service"], b["command"]) for b in result["bonjour"]]
    for title, record in records:
        display_status = record["status"] + (" / "+record["parse_status"] if record.get("parse_status") not in (None, "ok") else "")
        lines.append(f"| {title} | {display_status} | {record.get('returncode')} |")
    lines += ["", "Bonjour 是持续观察命令，observation_window_elapsed 表示正常观察窗口结束；脚本随后终止观察进程，退出码可能为 -15。timed_out 表示其他命令超时，tool_missing/tool_failed 表示工具缺失或失败，均不能当作未发现设备。", "",
              "## 已有输出工具", ""]
    for name, path in result["installed_tools"]["executables"].items():
        lines.append(f"- {name}：{'已发现' if path else '未发现'}。")
    for binary in result["installed_tools"]["epson_binaries"]:
        lines.append(f"- 系统 Epson {Path(binary['path']).name}：{'已发现' if binary['exists'] else '未发现'}。")
    lines.append(f"- 系统 L8050/L8058 型号数据：{'已发现' if result['installed_tools']['installed_l8050_family_data'] else '未发现'}。")
    lines += ["", "## 结论边界", "", "本次未创建或修改队列、驱动、系统配置，未提交打印任务，也未执行已安装的 Epson 打印后端。USB/Bonjour 未发现目标只能说明本次本机检测未见，不能证明设备不存在、关机或不可打印。Remote 登记与本地托盘打印能力须分别确认。研究目录中的解包驱动不是已安装系统驱动，也不证明 Gutenprint 兼容。", "", "详细退出码、检测覆盖和脱敏结果见 diagnostics.json；端点使用本地匿名编号，未保存原始地址或设备标识。"]
    (args.output_dir / "检查结果.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({"output_dir": str(args.output_dir), "epson_queues": result["queues"]["epson_queue_count"], "usb_target_records": usb_count, "bonjour_target_services": bonjour_count, "read_only_device_queries": request_count}, ensure_ascii=False))


if __name__ == "__main__":
    main()
