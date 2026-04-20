"""
print_watcher.py — Wait for Canon TR7000 to appear on the network, then print.

Usage:
    C:\G\python.exe f:\executedcode\❤Music\tools\print_watcher.py [--docx <path>]

- Scans 10.0.0.1-254 for a device with port 9100 open (Canon RAW print port)
- Once found, updates the Windows printer port to the real IP
- Sends the print job (or re-sends if a path is provided)
- Polls the print queue until the job clears
- Shows a Windows toast notification on completion
"""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


PRINTER_NAME = "Canon TR7000 series"
PORT_NAME = "c6BFB6E00000"
SUBNET = "10.0.0"
SCAN_TIMEOUT = 0.5      # seconds per host TCP connect attempt
POLL_INTERVAL = 5       # seconds between network scans
JOB_POLL_INTERVAL = 3   # seconds between queue checks
MAX_WAIT_MINUTES = 30


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


CANON_PORTS = [80, 9100, 8611]  # web UI, RAW print, Canon proprietary


def tcp_ping(ip: str, ports: list[int] = CANON_PORTS, timeout: float = SCAN_TIMEOUT) -> bool:
    for port in ports:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def mdns_lookup() -> str | None:
    """Try to resolve Canon printer via mDNS/Bonjour using dns-sd or ping."""
    names = ["Canon-TR7000-series", "CANONTR7000", "Canon-TR7000",
             "CanonTR7000series", "Canon_TR7000_series"]
    for name in names:
        try:
            ip = socket.gethostbyname(f"{name}.local")
            return ip
        except OSError:
            pass
        try:
            ip = socket.gethostbyname(name)
            return ip
        except OSError:
            pass
    return None


def scan_subnet(subnet: str = SUBNET) -> str | None:
    """Return the first Canon-likely IP on the subnet, or None."""
    # Try mDNS first — fastest if Bonjour is active
    ip = mdns_lookup()
    if ip:
        log(f"mDNS resolved printer to {ip}")
        return ip

    hosts = [f"{subnet}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=60) as ex:
        futures = {ex.submit(tcp_ping, h): h for h in hosts}
        for fut in as_completed(futures):
            if fut.result():
                return futures[fut]
    return None


def update_printer_port(ip: str) -> bool:
    """Update the Windows TCP/IP printer port to the discovered IP."""
    ps = (
        f'$port = Get-PrinterPort -Name "{PORT_NAME}" -ErrorAction SilentlyContinue; '
        f'if ($port) {{ Set-PrinterPort -Name "{PORT_NAME}" -PrinterHostAddress "{ip}"; '
        f'Write-Host "Port updated to {ip}" }} '
        f'else {{ Add-PrinterPort -Name "{PORT_NAME}" -PrinterHostAddress "{ip}" -PortNumber 9100; '
        f'Write-Host "Port created for {ip}" }}'
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True
    )
    log(result.stdout.strip() or result.stderr.strip())
    return result.returncode == 0


def get_queue_jobs() -> list[str]:
    """Return list of job names currently in the Canon print queue."""
    ps = (
        f'Get-PrintJob -PrinterName "{PRINTER_NAME}" -ErrorAction SilentlyContinue '
        f'| Select-Object -ExpandProperty JobStatus'
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True
    )
    return [l.strip() for l in result.stdout.splitlines() if l.strip()]


def send_print_job(docx_path: Path) -> None:
    subprocess.Popen(
        ["powershell", "-NoProfile", "-Command",
         f'Start-Process -FilePath "{docx_path}" -Verb Print'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    log(f"Print job sent: {docx_path.name}")


def toast(title: str, msg: str) -> None:
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        "$n.Visible = $true; "
        f'$n.ShowBalloonTip(5000, "{title}", "{msg}", '
        "[System.Windows.Forms.ToolTipIcon]::Info); "
        "Start-Sleep -Seconds 6; $n.Dispose()"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", type=str, default=None,
                        help="Path to DOCX to print once printer is online")
    args = parser.parse_args()

    docx_path: Path | None = None
    if args.docx:
        docx_path = Path(args.docx)
        if not docx_path.exists():
            sys.exit(f"File not found: {docx_path}")

    log(f"Watching for Canon TR7000 on {SUBNET}.1-254 (port 9100)...")
    log("Turn the printer on. This script will handle the rest.")

    deadline = time.time() + MAX_WAIT_MINUTES * 60
    printer_ip: str | None = None

    while time.time() < deadline:
        printer_ip = scan_subnet()
        if printer_ip:
            log(f"Printer found at {printer_ip}!")
            break
        log(f"Not found yet — retrying in {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)
    else:
        sys.exit(f"Printer not found after {MAX_WAIT_MINUTES} minutes. Giving up.")

    # Fix the port
    update_printer_port(printer_ip)
    time.sleep(2)  # Let Windows settle

    # Send job (or rely on spooled job to drain now that port is fixed)
    if docx_path:
        send_print_job(docx_path)
    else:
        log("Relying on already-spooled job to drain now that port is live...")
        # Resume any paused jobs
        ps_resume = (
            f'Get-PrintJob -PrinterName "{PRINTER_NAME}" -ErrorAction SilentlyContinue '
            f'| Resume-PrintJob -ErrorAction SilentlyContinue'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_resume],
                       capture_output=True)

    # Wait for queue to clear
    log("Waiting for print job to complete...")
    time.sleep(4)
    for _ in range(60):
        jobs = get_queue_jobs()
        if not jobs:
            log("Print queue empty — job complete!")
            toast("Print Complete", "Canon TR7000: job finished.")
            break
        log(f"Queue status: {jobs}")
        time.sleep(JOB_POLL_INTERVAL)
    else:
        log("Timed out waiting for queue to clear — check printer manually.")
        toast("Print Watcher", "Queue did not clear in time. Check printer.")


if __name__ == "__main__":
    main()
