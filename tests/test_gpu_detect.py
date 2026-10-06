"""Exercise noc-gpu detection and planning against fixture `lspci -Dnn` output.

Never touches the real GPU stack: detection reads NOC_GPU_LSPCI_FILE, and the
install path only ever runs with --dry-run.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "bin/noc-gpu"

NV_3080TI = "0000:01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA102 [GeForce RTX 3080 Ti] [10de:2208] (rev a1)"
NV_3080TI_AUDIO = "0000:01:00.1 Audio device [0403]: NVIDIA Corporation GA102 High Definition Audio Controller [10de:1aef] (rev a1)"
NV_1080 = "0000:02:00.0 VGA compatible controller [0300]: NVIDIA Corporation GP104 [GeForce GTX 1080] [10de:1b80] (rev a1)"
NV_1660 = "0000:03:00.0 VGA compatible controller [0300]: NVIDIA Corporation TU116 [GeForce GTX 1660] [10de:2184] (rev a1)"
NV_GTX680 = "0000:04:00.0 VGA compatible controller [0300]: NVIDIA Corporation GK104 [GeForce GTX 680] [10de:1180] (rev a1)"
NV_BLACKWELL = "0000:05:00.0 VGA compatible controller [0300]: NVIDIA Corporation GB202 [GeForce RTX 5090] [10de:2b85] (rev a1)"
NV_UNKNOWN = "0000:06:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:9999] (rev a1)"
NV_A100 = "0000:07:00.0 3D controller [0302]: NVIDIA Corporation GA100 [A100 PCIe 40GB] [10de:20f1] (rev a1)"
AMD_7900 = "0000:0a:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 31 [Radeon RX 7900 XT/7900 XTX/7900M] [1002:744c] (rev c8)"
AMD_6600 = "0000:0b:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 23 [Radeon RX 6600/6600 XT/6600M] [1002:73ff] (rev c1)"
AMD_9070 = "0000:0c:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 48 [Radeon RX 9070/9070 XT/9070 GRE] [1002:7550] (rev c0)"
AMD_HALO = "0000:0d:00.0 Display controller [0380]: Advanced Micro Devices, Inc. [AMD/ATI] Strix Halo [Radeon Graphics / Radeon 8050S Graphics / Radeon 8060S Graphics] [1002:1586] (rev c1)"
AMD_CEZANNE = "0000:0e:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Cezanne [Radeon Vega Series / Radeon Vega Mobile Series] [1002:1638] (rev c8)"
AMD_VEGA64 = "0000:0f:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Vega 10 [Radeon RX Vega 56/64] [1002:687f] (rev c3)"
AMD_UNKNOWN = "0000:10:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Device [1002:7999] (rev c0)"
VM_QXL = "0000:00:02.0 VGA compatible controller [0300]: Red Hat, Inc. QXL paravirtual graphic card [1b36:0100] (rev 05)"
VM_VIRTIO = "0000:00:03.0 VGA compatible controller [0300]: Red Hat, Inc. Virtio 1.0 GPU [1af4:1050] (rev 01)"
INTEL_IGPU = "0000:00:02.0 VGA compatible controller [0300]: Intel Corporation UHD Graphics 630 [8086:3e92]"


def detect(*lines):
    with tempfile.TemporaryDirectory() as d:
        fixture = Path(d) / "lspci.txt"
        fixture.write_text("\n".join(lines) + "\n")
        out = subprocess.run(
            [str(SCRIPT), "detect", "--json"],
            env={**os.environ, "NOC_GPU_LSPCI_FILE": str(fixture)},
            capture_output=True, text=True, check=True,
        ).stdout
    return json.loads(out)


def bash_fn(expr, env=None, check=True):
    return subprocess.run(
        ["bash", "-c", f'source "{SCRIPT}"; {expr}'],
        capture_output=True, text=True, check=check, env={**os.environ, **(env or {})},
    )


class ClassificationTests(unittest.TestCase):
    def test_nvidia_generations(self):
        cases = [
            (NV_3080TI, "ampere", "modern"),
            (NV_1660, "turing", "modern"),
            (NV_BLACKWELL, "blackwell", "modern"),
            (NV_A100, "ampere", "modern"),
            (NV_1080, "pascal", "legacy"),
            (NV_GTX680, "kepler", "unsupported"),
            (NV_UNKNOWN, "unknown", "modern"),
        ]
        for line, family, tier in cases:
            with self.subTest(family=family):
                gpu = detect(line)["gpus"][0]
                self.assertEqual((gpu["vendor"], gpu["family"], gpu["tier"]), ("nvidia", family, tier))

    def test_amd_targets(self):
        cases = [
            (AMD_7900, "gfx1100", "rocm", None),
            (AMD_9070, "gfx1201", "rocm", None),
            (AMD_HALO, "gfx1151", "rocm", None),
            (AMD_6600, "gfx1032", "override", "10.3.0"),
            (AMD_CEZANNE, "gfx90c", "vulkan", None),
            (AMD_VEGA64, "gfx900", "vulkan", None),
        ]
        for line, gfx, tier, override in cases:
            with self.subTest(gfx=gfx):
                gpu = detect(line)["gpus"][0]
                self.assertEqual((gpu["vendor"], gpu["family"], gpu["tier"], gpu["hsa_override"]),
                                 ("amd", gfx, tier, override))

    def test_audio_functions_and_foreign_adapters_are_ignored(self):
        self.assertEqual(len(detect(NV_3080TI, NV_3080TI_AUDIO)["gpus"]), 1)
        for line in (VM_QXL, VM_VIRTIO, INTEL_IGPU):
            with self.subTest(line=line[:40]):
                result = detect(line)
                self.assertEqual(result["gpus"], [])
                self.assertEqual(result["plan"], {"nvidia": "none", "amd": "none", "amd_hsa_override": None})

    def test_empty_lspci_is_not_an_error(self):
        self.assertEqual(detect()["gpus"], [])


class PlanTests(unittest.TestCase):
    def test_hybrid_desktop_uses_cuda_and_leaves_the_apu_on_vulkan(self):
        plan = detect(AMD_CEZANNE, NV_3080TI)["plan"]
        self.assertEqual((plan["nvidia"], plan["amd"]), ("modern", "vulkan"))

    def test_oldest_supported_nvidia_card_decides(self):
        # one driver branch must drive both → Pascal pins the whole box to CUDA 12
        self.assertEqual(detect(NV_3080TI, NV_1080)["plan"]["nvidia"], "legacy")
        # an unsupported card next to a supported one does not drag it down
        self.assertEqual(detect(NV_GTX680, NV_3080TI)["plan"]["nvidia"], "modern")

    def test_native_rocm_card_wins_over_override_card(self):
        plan = detect(AMD_6600, AMD_7900)["plan"]
        self.assertEqual((plan["amd"], plan["amd_hsa_override"]), ("rocm", None))

    def test_override_is_reported_for_navi2x_only_boxes(self):
        plan = detect(AMD_6600)["plan"]
        self.assertEqual((plan["amd"], plan["amd_hsa_override"]), ("override", "10.3.0"))

    def test_cuda_series_selection(self):
        cases = [
            ("modern 595", "13"), ("modern 580", "13"), ("modern 570", "12"),
            ("modern 525", "12"), ("modern 470", "none"), ("modern ''", "13"),
            ("legacy 580", "12"), ("legacy ''", "12"), ("legacy 595", "12"),
            ("unsupported 580", "none"), ("none 580", "none"),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(bash_fn(f"pick_cuda_series {args}").stdout.strip(), expected)


class ReviewRegressionTests(unittest.TestCase):
    def test_unrecognised_amd_device_falls_back_to_vulkan(self):
        gpu = detect(AMD_UNKNOWN)["gpus"][0]
        self.assertEqual(gpu["tier"], "vulkan")
        self.assertEqual(detect(AMD_UNKNOWN)["plan"]["amd"], "vulkan")

    def test_unrecognised_amd_device_can_be_forced_onto_rocm(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = Path(d) / "l.txt"
            fixture.write_text(AMD_UNKNOWN + "\n")
            out = subprocess.run([str(SCRIPT), "detect", "--json"], capture_output=True, text=True, check=True,
                                 env={**os.environ, "NOC_GPU_LSPCI_FILE": str(fixture), "NOCTRAOS_GPU_FORCE_ROCM": "1"}).stdout
        self.assertEqual(json.loads(out)["plan"]["amd"], "rocm")

    def test_unrecognised_amd_never_plans_the_rocm_repo(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = Path(d) / "l.txt"
            fixture.write_text(AMD_UNKNOWN + "\n")
            out = subprocess.run([str(SCRIPT), "install", "--dry-run"], capture_output=True, text=True,
                                 env={**os.environ, "NOC_GPU_LSPCI_FILE": str(fixture)}).stdout
        self.assertNotIn("rocm.list", out)

    def test_rerun_keeps_the_recorded_rocm_release_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            lst = Path(d) / "rocm.list"
            lst.write_text("deb [arch=amd64 signed-by=/etc/apt/keyrings/rocm.gpg] https://repo.radeon.com/rocm/apt/6.4.1 noble main\n")
            # curl is broken on purpose: a remote lookup would fail the call
            result = bash_fn('curl() { return 7; }; resolve_rocm_version noble', env={"NOC_GPU_ROCM_LIST": str(lst)})
            self.assertEqual(result.stdout.strip(), "6.4.1")
            explicit = bash_fn('resolve_rocm_version noble', env={"NOC_GPU_ROCM_LIST": str(lst), "NOCTRAOS_ROCM_VERSION": "7.2.4"})
            self.assertEqual(explicit.stdout.strip(), "7.2.4")

    def test_failed_apt_pin_write_aborts_before_the_nvidia_repo_is_added(self):
        script = """
        write_root_file() { return 2; }
        sx() { echo "SX $*"; }
        pkg_installed() { return 1; }
        nvidia_repo_id() { echo ubuntu2404; }
        DRY_RUN=1
        setup_cuda_repo; echo "rc=$?"
        """
        out = bash_fn(script).stdout
        self.assertIn("rc=1", out)
        self.assertNotIn("SX dpkg", out)

    def test_apt_pin_is_written_before_the_repo_keyring_is_installed(self):
        script = """
        write_root_file() { echo "WRITE $1"; return 0; }
        sx() { echo "SX $*"; }
        pkg_installed() { return 1; }
        nvidia_repo_id() { echo ubuntu2404; }
        DRY_RUN=1
        setup_cuda_repo
        """
        lines = [l for l in bash_fn(script).stdout.splitlines() if l.startswith(("WRITE", "SX dpkg"))]
        self.assertEqual(lines[0], "WRITE /etc/apt/preferences.d/noctraos-cuda-toolkit-only")
        self.assertTrue(lines[1].startswith("SX dpkg"))

    def test_a_real_write_failure_is_reported_as_failure_not_unchanged(self):
        out = bash_fn('SUDO=""; DRY_RUN=0; echo x | write_apt_file /proc/nonexistent/f 644 2>/dev/null; echo "rc=$?"').stdout
        self.assertIn("rc=1", out)


class DryRunTests(unittest.TestCase):
    def run_dry(self, *lines, extra_env=None):
        with tempfile.TemporaryDirectory() as d:
            fixture = Path(d) / "lspci.txt"
            fixture.write_text("\n".join(lines) + "\n")
            return subprocess.run(
                [str(SCRIPT), "install", "--dry-run"],
                env={**os.environ, "NOC_GPU_LSPCI_FILE": str(fixture),
                     "NOCTRAOS_ROCM_VERSION": "7.2.4", **(extra_env or {})},
                capture_output=True, text=True,
            )

    def test_no_gpu_installs_nothing(self):
        result = self.run_dry(VM_QXL)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Nothing to install", result.stdout)
        self.assertNotIn("[dry-run]", result.stdout)

    def test_amd_dry_run_plans_rocm_repo_packages_and_groups(self):
        result = self.run_dry(AMD_7900)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        self.assertIn("rocm.list", out)
        self.assertIn("rocm-hip-sdk", out)
        self.assertIn("mesa-vulkan-drivers", out)
        self.assertIn("render", out)
        self.assertNotIn("HSA_OVERRIDE", out)

    def test_runtime_profile_skips_the_sdk(self):
        out = self.run_dry(AMD_7900, extra_env={"NOCTRAOS_GPU_PROFILE": "runtime"}).stdout
        self.assertIn("rocm-hip-runtime", out)
        self.assertNotIn("rocm-hip-sdk", out)

    def test_override_card_gets_an_ollama_dropin(self):
        out = self.run_dry(AMD_6600).stdout
        self.assertIn("ollama.service.d/noctraos-gpu.conf", out)

    def test_amd_apu_alone_never_touches_the_rocm_repo(self):
        out = self.run_dry(AMD_CEZANNE).stdout
        self.assertNotIn("rocm.list", out)
        self.assertIn("Vulkan", out)

    def test_vendor_filter(self):
        out = self.run_dry(AMD_7900, NV_1080, extra_env={"NOCTRAOS_GPU_VENDORS": "amd"}).stdout
        self.assertIn("rocm.list", out)
        self.assertNotIn("NVIDIA: legacy tier", out)

    def test_rejects_unknown_vendor(self):
        result = subprocess.run([str(SCRIPT), "install", "--dry-run", "--vendor", "intel"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)




def status_json(*lines):
    with tempfile.TemporaryDirectory() as d:
        fixture = Path(d) / "lspci.txt"
        fixture.write_text("\n".join(lines) + ("\n" if lines else ""))
        out = subprocess.run([str(SCRIPT), "status", "--json"], capture_output=True, text=True,
                             env={**os.environ, "NOC_GPU_LSPCI_FILE": str(fixture)}).stdout
    return json.loads(out)


class StatusJsonTests(unittest.TestCase):
    def test_no_gpu_is_a_state_not_ready(self):
        data = status_json()
        self.assertEqual(data["gpus"], [])
        self.assertFalse(data["ready"])
        self.assertEqual([r["status"] for r in data["rows"]], ["note"])
        self.assertIn("none detected", data["rows"][0]["text"])

    def test_shape_with_a_gpu(self):
        data = status_json(AMD_6600)
        self.assertEqual(set(data), {"gpus", "ready", "reboot_pending", "rows"})
        self.assertEqual(len(data["gpus"]), 1)
        self.assertIn("Navi 23", data["gpus"][0])
        self.assertTrue(data["rows"])
        for row in data["rows"]:
            self.assertEqual(set(row), {"status", "text"})
            self.assertIn(row["status"], {"ok", "fail", "note"})
            self.assertNotIn("\x1b", row["text"])         # no colour codes
        self.assertEqual(data["rows"][0]["status"], "ok")   # the "GPU: <name>" line

    def test_ready_means_every_check_passed(self):
        data = status_json(AMD_6600)
        self.assertEqual(data["ready"], all(r["status"] != "fail" for r in data["rows"]))


if __name__ == "__main__":
    unittest.main()
