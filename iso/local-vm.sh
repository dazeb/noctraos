#!/usr/bin/env bash
# local-vm.sh — a local KVM test VM for NoctraOS (UEFI, no root, no host changes).
#
#   iso/local-vm.sh start [iso|none]    boot the VM; with an ISO attached the disk boots first, so a
#                                       blank disk falls through to the installer and an installed
#                                       one boots the system. Creates the disk and UEFI vars if absent.
#   iso/local-vm.sh stop | status       (stop = hard power off; prefer `ssh 'sudo poweroff'` first)
#   iso/local-vm.sh shot out.png        console screenshot (1280x800)
#   iso/local-vm.sh click X Y [double]  absolute left click at pixel X,Y of that screenshot
#   iso/local-vm.sh key <qemu-key>...   e.g. key meta_l-spc ; key esc ; key n o c t r a o s ret
#   iso/local-vm.sh ssh '<command>'     run a command in the VM as noctraos (password: noctraos)
#   iso/local-vm.sh scp <file>...       copy files into the VM's /tmp
#
# Environment: VM_DIR (default ~/noctraos-vm; keep it on ext4, NOT NTFS), VM_DISK_SIZE (48G; the
# downloadable appliance uses 64G), VM_RAM (8192), VM_CPUS (6), VM_USER (noctraos), VM_PASSWORD
# (noctraos), VM_SSH_PORT (2222).
#
# Why these choices (each cost real debugging time):
#  - User-mode networking with an ssh port forward: nothing on the host changes.
#  - `-usb -device usb-tablet` plus a QMP socket: clicks are QMP `input-send-event` with ABSOLUTE axes
#    (0..32767). The HMP monitor's `mouse_move` is relative and a tablet ignores it.
#  - Keys go through the HMP monitor (`sendkey`); screenshots through `screendump`.
#  - Needs /dev/kvm access (an ACL for your seat user is enough), qemu-system-x86_64, OVMF, and
#    python3 with PIL or ffmpeg for `shot` (else it leaves the .ppm).
set -euo pipefail

VM_DIR="${VM_DIR:-$HOME/noctraos-vm}"
VM_USER="${VM_USER:-noctraos}"; VM_PASSWORD="${VM_PASSWORD:-noctraos}"; VM_SSH_PORT="${VM_SSH_PORT:-2222}"
DISK="$VM_DIR/disk.qcow2"; VARS="$VM_DIR/vars.fd"
MON="$VM_DIR/mon.sock"; QMP="$VM_DIR/qmp.sock"; PID="$VM_DIR/qemu.pid"
mkdir -p "$VM_DIR"

ssh_opts=(-p "$VM_SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
          -o PreferredAuthentications=password -o PubkeyAuthentication=no -o ConnectTimeout=8 -o LogLevel=ERROR)
askpass() {  # ssh asks for the password through a throwaway helper (no sshpass needed)
  printf '#!/bin/sh\necho %s\n' "$VM_PASSWORD" > "$VM_DIR/askpass.sh"; chmod 700 "$VM_DIR/askpass.sh"
  export SSH_ASKPASS="$VM_DIR/askpass.sh" SSH_ASKPASS_REQUIRE=force
}
monitor() {  # send HMP commands
  python3 - "$MON" "$@" <<'PY'
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); s.settimeout(2)
try: s.recv(4096)
except Exception: pass
for cmd in sys.argv[2:]:
    s.sendall((cmd + "\n").encode()); time.sleep(0.4)
    try: s.recv(65536)
    except Exception: pass
PY
}

case "${1:-status}" in
  start)
    ISO="${2:-none}"
    [ -f "$DISK" ] || qemu-img create -q -f qcow2 "$DISK" "${VM_DISK_SIZE:-48G}"
    [ -f "$VARS" ] || cp /usr/share/OVMF/OVMF_VARS_4M.fd "$VARS"
    # shellcheck disable=SC2054  # the commas are QEMU option syntax, not array separators
    args=(-enable-kvm -cpu host -smp "${VM_CPUS:-6}" -m "${VM_RAM:-8192}" -machine q35
      -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd
      -drive if=pflash,format=raw,file="$VARS"
      -drive file="$DISK",if=none,id=d0,format=qcow2,cache=writeback,discard=unmap
      -device virtio-blk-pci,drive=d0,bootindex=1
      -netdev user,id=n0,hostfwd=tcp:127.0.0.1:"$VM_SSH_PORT"-:22 -device virtio-net-pci,netdev=n0
      -vga std -display none -usb -device usb-tablet -device usb-kbd
      -monitor unix:"$MON",server,nowait -qmp unix:"$QMP",server,nowait
      -pidfile "$PID" -daemonize)
    # shellcheck disable=SC2054
    [ "$ISO" != none ] && args+=(-drive file="$ISO",media=cdrom,if=none,id=c0,readonly=on -device ide-cd,drive=c0,bootindex=2)
    qemu-system-x86_64 "${args[@]}"; echo "started (pid $(cat "$PID"))" ;;
  stop)   [ -f "$PID" ] && kill "$(cat "$PID")" 2>/dev/null || true; sleep 2; rm -f "$PID" "$MON" "$QMP"; echo stopped ;;
  status) [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null && echo "running (pid $(cat "$PID"))" || echo "not running" ;;
  shot)
    monitor "screendump $VM_DIR/shot.ppm"; sleep 1
    # ppm -> png: PIL if a python has it, else ffmpeg, else leave the .ppm
    for py in "${PYTHON_PIL:-python3}" /usr/bin/python3; do
      "$py" -c "from PIL import Image; Image.open('$VM_DIR/shot.ppm').save('$2')" 2>/dev/null && exit 0
    done
    command -v ffmpeg >/dev/null 2>&1 && ffmpeg -loglevel error -y -i "$VM_DIR/shot.ppm" "$2" && exit 0
    cp "$VM_DIR/shot.ppm" "${2%.png}.ppm"; echo "no PIL or ffmpeg: wrote ${2%.png}.ppm" >&2 ;;
  click)
    python3 - "$QMP" "$2" "$3" "${4:-}" <<'PY'
import json, socket, sys, time
sock, x, y, double = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
s = socket.socket(socket.AF_UNIX); s.connect(sock); f = s.makefile("rw"); f.readline()
def cmd(name, **a):
    f.write(json.dumps({"execute": name, "arguments": a} if a else {"execute": name}) + "\n"); f.flush(); f.readline()
ev = lambda t, **d: {"type": t, "data": d}
cmd("qmp_capabilities")
cmd("input-send-event", events=[ev("abs", axis="x", value=x * 32767 // 1280), ev("abs", axis="y", value=y * 32767 // 800)])
time.sleep(0.15)
for _ in range(2 if double else 1):
    cmd("input-send-event", events=[ev("btn", down=True, button="left")]); time.sleep(0.08)
    cmd("input-send-event", events=[ev("btn", down=False, button="left")]); time.sleep(0.12)
PY
    ;;
  key)  shift; cmds=(); for k in "$@"; do cmds+=("sendkey $k"); done; monitor "${cmds[@]}" ;;
  ssh)  shift; askpass; exec ssh "${ssh_opts[@]}" "$VM_USER@127.0.0.1" "$@" ;;
  scp)  shift; askpass; exec scp -q -P "$VM_SSH_PORT" "${ssh_opts[@]:2}" "$@" "$VM_USER@127.0.0.1:/tmp/" ;;
  *) sed -n '2,17p' "$0"; exit 1 ;;
esac
