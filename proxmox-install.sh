#!/bin/bash
# NoctraOS on Proxmox VE: one command creates a ready-to-use VM.
#
#   bash <(curl -sSfL https://raw.githubusercontent.com/dazeb/noctraos/main/proxmox-install.sh)
#
# Two ways in, both UEFI (q35 + OVMF), both checked against the release SHA256SUMS:
#   image  the ready-made VM disk (qcow2), imported as-is. Signs in as noctraos / noctraos. Trial use.
#   iso    the installer ISO plus an empty disk: you run the normal installer and make your own account.
#
# Run as root on the Proxmox host. Unattended use: set NOCTRAOS_MODE (image|iso), NOCTRAOS_RAM (MB),
# NOCTRAOS_CORES, NOCTRAOS_DISK_GB (iso mode), NOCTRAOS_STORAGE (VM disks), NOCTRAOS_ISO_STORAGE
# (iso mode), NOCTRAOS_VMID, NOCTRAOS_NAME, NOCTRAOS_BRIDGE; they skip the matching question.
# NOCTRAOS_BASE_URL points at another copy of the release files (a local mirror, a test build);
# NOCTRAOS_SCRATCH_DIR is where the image is downloaded (default: the roomiest directory storage).
set -Eeuo pipefail

VERSION='0.3.0'
BASE_URL="${NOCTRAOS_BASE_URL:-https://dl.noctraos.dev/releases/v$VERSION}"
IMAGE_FILE="noctraos-$VERSION.qcow2"
ISO_FILE="noctraos-$VERSION-amd64.iso"

SCRATCH=''
VM_CREATED=''

# Runs on every exit, good or bad. VM_CREATED is cleared once the VM is fully configured, so a
# finished VM is never touched. Only files this script made are removed.
cleanup() {
    local status=$?
    if [[ -n $VM_CREATED ]]; then
        echo 'Removing incomplete VM...' >&2
        qm destroy "$VM_CREATED" --purge &> /dev/null || :
    fi
    if [[ -n $SCRATCH && -d $SCRATCH ]]; then
        cd / && rm -rf -- "$SCRATCH"
    fi
    return $status
}
trap cleanup EXIT
trap 'exit 130' INT TERM

die() { echo "ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die 'Run this as root on the Proxmox host.'
for tool in qm pvesm pvesh wget sha256sum; do
    command -v "$tool" > /dev/null || die "$tool not found. Is this a Proxmox VE host?"
done
PVE_MAJOR=$(pveversion 2> /dev/null | sed -n 's|^pve-manager/\([0-9]*\)\..*|\1|p')
if [[ ! $PVE_MAJOR =~ ^[0-9]+$ ]] || (( PVE_MAJOR < 8 )); then die 'Proxmox VE 8 or 9 is required.'; fi

# Ask with whiptail (on every Proxmox host) or dialog (same options), unless the answer came in through the environment. A refused question on a
# terminal is the user cancelling; without a terminal it means the variable should have been set.
TUI=$(command -v whiptail || command -v dialog || :)
cancelled() { if [[ -t 0 && -t 1 ]]; then exit 1; fi; die "No terminal to ask on; set $1 instead."; }
ask_menu() {  # ask_menu VAR title text height item desc [item desc ...]
    local var=$1 title=$2 text=$3 height=$4; shift 4
    [[ -n ${!var:-} ]] && return 0
    [[ -n $TUI ]] || die "Neither whiptail nor dialog found; set $var instead."
    local reply
    reply=$("$TUI" --title "$title" --menu "$text" "$height" 74 "$(( $# / 2 ))" "$@" 3>&1 1>&2 2>&3) || cancelled "$var"
    printf -v "$var" '%s' "$reply"
}
ask_text() {  # ask_text VAR title text default
    local var=$1 title=$2 text=$3 default=$4
    if [[ -z ${!var:-} ]]; then
        [[ -n $TUI ]] || die "Neither whiptail nor dialog found; set $var instead."
        local reply
        reply=$("$TUI" --title "$title" --inputbox "$text" 9 74 "$default" 3>&1 1>&2 2>&3) || cancelled "$var"
        printf -v "$var" '%s' "$reply"
    fi
}
ask_number() {  # ask_number VAR title text default
    ask_text "$@"
    [[ ${!1} =~ ^[1-9][0-9]*$ ]] || die "$1 must be a whole number, got '${!1}'."
}
storages() {  # storages <content type>: active storages that can hold it
    pvesm status --content "$1" 2> /dev/null | awk 'NR>1 && $3=="active" {print $1}'
}
pick_storage() {  # pick_storage VAR content title text
    local var=$1 content=$2 title=$3 text=$4 name options=()
    if [[ -n ${!var:-} ]]; then
        storages "$content" | grep -Fx "${!var}" > /dev/null || die "Storage '${!var}' is not active or cannot hold '$content'."
        return 0
    fi
    while read -r name; do options+=("$name" ''); done < <(storages "$content")
    (( ${#options[@]} )) || die "No active storage with the '$content' content type. Enable it under Datacenter > Storage."
    ask_menu "$var" "$title" "$text" 16 "${options[@]}"
}
download() {  # download URL FILE: resumable, so a dropped connection does not start over
    echo "Downloading ${1##*/}..."
    wget -c --progress=dot:giga "$1" -O "$2" || die "Download failed: $1"
}
verify() {  # verify FILE [NAME]: the release SHA256SUMS must list NAME (default: the file's name) and agree
    local file=$1 name=${2:-${1##*/}} want have
    wget -q "$BASE_URL/SHA256SUMS" -O "$SCRATCH_SUMS" || { echo "ERROR: Could not download $BASE_URL/SHA256SUMS" >&2; return 1; }
    want=$(awk -v n="$name" '$2 == n || $2 == "*" n {print $1; exit}' "$SCRATCH_SUMS")
    [[ -n $want ]] || { echo "ERROR: $name is not listed in SHA256SUMS." >&2; return 1; }
    echo 'Verifying SHA-256...'
    have=$(sha256sum "$file" | awk '{print $1}')
    if [[ $have != "$want" ]]; then
        echo "ERROR: SHA-256 mismatch for $name (expected $want, got $have). The file may be damaged." >&2
        return 1
    fi
    echo "OK: $name matches SHA256SUMS"
}

echo
echo "NoctraOS $VERSION for Proxmox VE"
echo

ask_menu NOCTRAOS_MODE 'NoctraOS' 'How do you want to install NoctraOS?' 14 \
    image 'Ready-made VM disk (recommended): signs in as noctraos / noctraos' \
    iso   'Installer ISO: run the installer and make your own account'
case $NOCTRAOS_MODE in image|iso) ;; *) die "NOCTRAOS_MODE must be 'image' or 'iso'." ;; esac

RAM=${NOCTRAOS_RAM:-}
ask_number RAM 'NoctraOS' 'RAM for the VM in MB (8192 recommended; AI models need room):' 8192
CORES=${NOCTRAOS_CORES:-}
ask_number CORES 'NoctraOS' 'CPU cores:' 4
STORAGE=${NOCTRAOS_STORAGE:-}
pick_storage STORAGE images 'NoctraOS' 'Storage for the VM disk (the disk is 64 GB, thin where the storage allows):'

if [[ $NOCTRAOS_MODE == iso ]]; then
    DISK_GB=${NOCTRAOS_DISK_GB:-}
    ask_number DISK_GB 'NoctraOS' 'Disk size in GB (at least 40):' 64
    (( DISK_GB >= 40 )) || die 'The disk needs at least 40 GB.'
    ISO_STORAGE=${NOCTRAOS_ISO_STORAGE:-}
    pick_storage ISO_STORAGE iso 'NoctraOS' 'Storage that keeps the installer ISO:'
else
    # The image is 17 GB and the host root disk is usually small, so it is downloaded
    # into the directory storage that has the most room, never into /tmp.
    SCRATCH_ROOT=${NOCTRAOS_SCRATCH_DIR:-}
    if [[ -z $SCRATCH_ROOT ]]; then
        # Free space is in KiB in column 6; directory storages also report their path.
        best=$(pvesm status 2> /dev/null | awk 'NR>1 && $2=="dir" && $3=="active" {print $6, $1}' | sort -rn | head -n1 | awk '{print $2}')
        [[ -n $best ]] || die 'No directory storage to download the image into. Set NOCTRAOS_SCRATCH_DIR to a directory with 20 GB free.'
        SCRATCH_ROOT=$(pvesh get "/storage/$best" --output-format json 2> /dev/null | sed -n 's|.*"path" *: *"\([^"]*\)".*|\1|p')
        [[ -n $SCRATCH_ROOT ]] || die "Could not find the path of storage '$best'. Set NOCTRAOS_SCRATCH_DIR."
    fi
    [[ -d $SCRATCH_ROOT ]] || die "Scratch directory '$SCRATCH_ROOT' does not exist."
    avail_kb=$(df -Pk "$SCRATCH_ROOT" | awk 'NR==2 {print $4}')
    (( avail_kb > 20 * 1024 * 1024 )) || die "$SCRATCH_ROOT has under 20 GB free; the image needs about 17 GB. Set NOCTRAOS_SCRATCH_DIR to another directory."
fi

# The VM id and name; the next free id unless asked otherwise.
VMID=${NOCTRAOS_VMID:-$(pvesh get /cluster/nextid)}
NAME=${NOCTRAOS_NAME:-noctraos}
BRIDGE=${NOCTRAOS_BRIDGE:-vmbr0}
[[ $VMID =~ ^[0-9]+$ ]] || die 'NOCTRAOS_VMID must be a number.'
if qm status "$VMID" &> /dev/null; then die "VM $VMID already exists."; fi

if [[ $NOCTRAOS_MODE == image ]]; then
    SCRATCH=$(mktemp -d -p "$SCRATCH_ROOT" noctraos-install.XXXXXX)
else
    SCRATCH=$(mktemp -d)   # only the small checksum file lands here
fi
SCRATCH_SUMS="$SCRATCH/SHA256SUMS"
cd "$SCRATCH"

# Everything is downloaded and verified before the VM exists, so a cancelled or failed run leaves nothing behind.
if [[ $NOCTRAOS_MODE == image ]]; then
    download "$BASE_URL/$IMAGE_FILE" "$IMAGE_FILE"
    verify "$IMAGE_FILE" || exit 1
else
    # Let Proxmox say where the volume lives: a storage may map its content types to custom folders.
    TARGET=$(pvesm path "$ISO_STORAGE:iso/$ISO_FILE") || die "Could not resolve $ISO_STORAGE:iso/$ISO_FILE; is '$ISO_STORAGE' a directory storage?"
    mkdir -p "${TARGET%/*}"
    # Reuse an ISO from an earlier run when it still matches the release checksum.
    if [[ -f $TARGET ]] && (wget -q "$BASE_URL/SHA256SUMS" -O "$SCRATCH_SUMS" && verify "$TARGET" "$ISO_FILE") &> /dev/null; then
        echo "OK: $ISO_FILE is already on $ISO_STORAGE and matches SHA256SUMS"
    else
        download "$BASE_URL/$ISO_FILE" "$TARGET.part"
        verify "$TARGET.part" "$ISO_FILE" || { rm -f "$TARGET.part"; exit 1; }
        mv -f "$TARGET.part" "$TARGET"
    fi
fi

echo
echo "Creating VM $VMID ($NAME)..."
# The cleanup marker is armed only once qm create has succeeded: if another operation took this id
# first, create fails and the trap must not destroy that other guest.
qm create "$VMID" --name "$NAME" --ostype l26 --machine q35 --bios ovmf \
    --cpu x86-64-v2-AES --cores "$CORES" --memory "$RAM" --balloon 0 \
    --scsihw virtio-scsi-single --net0 "virtio,bridge=$BRIDGE" --vga std > /dev/null
VM_CREATED=$VMID
qm set "$VMID" --efidisk0 "$STORAGE:1,efitype=4m,pre-enrolled-keys=0" > /dev/null

if [[ $NOCTRAOS_MODE == image ]]; then
    echo 'Importing the disk (a few minutes)...'
    qm importdisk "$VMID" "$IMAGE_FILE" "$STORAGE" > /dev/null
    DISK=$(qm config "$VMID" | awk '/^unused0:/ {print $2; exit}')
    [[ -n $DISK ]] || die 'The disk import produced no disk.'
    qm set "$VMID" --scsi0 "$DISK,discard=on,ssd=1" --boot order=scsi0 > /dev/null
else
    qm set "$VMID" --scsi0 "$STORAGE:$DISK_GB,discard=on,ssd=1" \
        --ide2 "$ISO_STORAGE:iso/$ISO_FILE,media=cdrom" --boot 'order=scsi0;ide2' > /dev/null
fi

qm set "$VMID" --description '<p><strong>NoctraOS</strong> - an AI-ready desktop for people moving from Windows.<br><a href="https://noctraos.dev/">noctraos.dev</a> &bull; <a href="https://github.com/dazeb/noctraos">GitHub</a></p>' > /dev/null

# The VM is complete: from here on, the exit trap leaves it alone.
VM_CREATED=''
qm start "$VMID"

echo
echo "VM $VMID is running. Open its Console in the Proxmox web UI."
if [[ $NOCTRAOS_MODE == image ]]; then
    echo 'The desktop signs in on its own; the account is noctraos / noctraos (trial use). The first start finishes setting up the AI tools, which can take a while.'
else
    echo 'Choose "Install NoctraOS". The VM keeps the ISO attached; after the install finishes, run: qm set '"$VMID"' --delete ide2'
fi
