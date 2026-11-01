"""The parts of the installer build that can be checked without PyInstaller, Inno Setup, hdiutil or dpkg."""

import importlib.util
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tdtlocal import __version__
from tdtlocal.config import PROJECT_DIR
from tdtlocal.net import create_ssl_context

PACKAGING = PROJECT_DIR / "packaging"


def load_build():
    spec = importlib.util.spec_from_file_location("tdt_build", PACKAGING / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load_build()


class BuildHelperTests(unittest.TestCase):
    def test_version_matches_the_package(self):
        self.assertEqual(build.read_version(), __version__)

    def test_artifact_names(self):
        with mock.patch.object(build.platform, "machine", return_value="AMD64"):
            self.assertEqual(build.machine(), "x64")
            self.assertEqual(
                build.artifact_name("1.2.3", "windows-x64-setup", "exe"), "tdt-local-1.2.3-windows-x64-setup.exe"
            )
            self.assertEqual(build.artifact_name("1.2.3", "", "deb"), "tdt-local_1.2.3_amd64.deb")
        with mock.patch.object(build.platform, "machine", return_value="aarch64"):
            self.assertEqual(build.machine(), "arm64")
            self.assertEqual(build.artifact_name("1.2.3", "", "deb"), "tdt-local_1.2.3_arm64.deb")

    def test_deb_control_is_well_formed(self):
        text = build.deb_control("1.2.3", "amd64", 4096)
        fields = dict(line.split(": ", 1) for line in text.splitlines() if line and not line.startswith(" "))
        self.assertEqual(fields["Package"], "tdt-local")
        self.assertEqual(fields["Version"], "1.2.3")
        self.assertEqual(fields["Architecture"], "amd64")
        self.assertEqual(fields["Installed-Size"], "4096")
        self.assertIn("<", fields["Maintainer"])
        self.assertTrue(text.endswith("\n"))
        self.assertIn("Homepage: https://github.com/cibernicola/tdt-local\n", text)
        with mock.patch.object(build, "HOMEPAGE", "https://example.org/x"):
            self.assertIn("Homepage: https://example.org/x\n", build.deb_control("1.2.3", "amd64", 1))

    def test_desktop_entry(self):
        text = build.desktop_entry("/usr/bin/tdt-local", "tdt-local")
        self.assertTrue(text.startswith("[Desktop Entry]\n"))
        for line in (
            "Type=Application",
            "Exec=/usr/bin/tdt-local",
            "Icon=tdt-local",
            "Terminal=false",
            "Name=TDT local",
        ):
            self.assertIn(line + "\n", text)

    def test_debian_copyright_names_the_licence(self):
        text = build.deb_copyright()
        self.assertIn("License: Apache-2.0", text)
        self.assertIn("Upstream-Name: TDT local", text)

    def test_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f"
            path.write_bytes(b"abc")
            self.assertEqual(build.sha256(path), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_install_scripts_are_valid_posix_sh(self):
        for script in (build.INSTALL_SH, build.UNINSTALL_SH):
            self.assertTrue(script.startswith("#!/bin/sh\n"))
        self.assertIn("set -e", build.INSTALL_SH)

    def test_every_platform_has_a_builder(self):
        self.assertEqual(set(build.BUILDERS), {"win32", "darwin", "linux"})

    def test_deb_depends_on_what_electron_loads(self):
        text = build.deb_control("1.2.3", "amd64", 1)
        depends = next(line for line in text.splitlines() if line.startswith("Depends: "))
        for needle in ("libc6 (>= 2.35)", "libgtk-3-0 | libgtk-3-0t64", "libnss3", "libasound2 | libasound2t64"):
            self.assertIn(needle, depends)

    def test_the_user_install_chooses_the_sandbox_at_launch(self):
        self.assertIn("chrome-sandbox", build.INSTALL_SH)
        self.assertIn("unshare --user true", build.INSTALL_SH)
        self.assertIn("--no-sandbox", build.INSTALL_SH)  # only as a fallback, decided when it starts

    def test_electron_app_needs_node_and_node_is_named_in_the_docstring(self):
        self.assertIn("Node 20", build.__doc__)
        self.assertTrue(callable(build.electron_app))


class PackagingFilesTests(unittest.TestCase):
    def test_icons_are_valid_images(self):
        icons = PACKAGING / "icons"
        png = (icons / "icon-256.png").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(int.from_bytes(png[16:20], "big"), 256)
        ico = (icons / "icon.ico").read_bytes()
        self.assertEqual(ico[:4], b"\x00\x00\x01\x00")
        self.assertEqual(int.from_bytes(ico[4:6], "little"), 6)
        icns = (icons / "icon.icns").read_bytes()
        self.assertEqual(icns[:4], b"icns")
        self.assertEqual(int.from_bytes(icns[4:8], "big"), len(icns))

    def test_windows_script_is_ascii_and_references_the_build_defines(self):
        script = (PACKAGING / "windows" / "installer.iss").read_bytes()
        script.decode("ascii")  # Inno Setup reads it as ANSI
        text = script.decode()
        for define in ("AppVersion", "SourceDir", "RepoDir", "OutputDir", "OutputName"):
            self.assertIn(define, text)
        self.assertIn("PrivilegesRequired=lowest", text)  # no administrator needed

    def test_windows_installer_cleans_the_libraries_of_the_earlier_app(self):
        text = (PACKAGING / "windows" / "installer.iss").read_text(encoding="ascii")
        self.assertIn("[InstallDelete]", text)
        self.assertIn(r'Name: "{app}\_internal"', text)
        self.assertIn(
            '#define AppExe "tdt-local.exe"', text
        )  # the Electron app keeps the name, so the shortcuts survive

    def test_server_spec_has_a_console_and_bundles_the_static_files(self):
        spec = (PACKAGING / "tdt-local-server.spec").read_text(encoding="utf-8")
        for needle in ("tdtlocal/static", "TDT_PYTHON_LICENSE", "console=True", 'packaging" / "server.py'):
            self.assertIn(needle, spec)
        self.assertIn("utf-8", (PACKAGING / "server.py").read_text(encoding="utf-8"))

    def test_release_workflow_runs_the_smoke_test_and_has_node(self):
        workflow = (PROJECT_DIR / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        for needle in ("actions/setup-node", "packaging/smoke.py", "xvfb-run", "test -u /opt/tdt-local/chrome-sandbox"):
            self.assertIn(needle, workflow)

    def test_smoke_finds_the_program_in_the_packaged_folder(self):
        spec = importlib.util.spec_from_file_location("tdt_smoke", PACKAGING / "smoke.py")
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(smoke.sys, "platform", "win32"):
                self.assertEqual(smoke.executable(Path(tmp)), Path(tmp) / "tdt-local.exe")
            with mock.patch.object(smoke.sys, "platform", "linux"):
                self.assertEqual(smoke.executable(Path(tmp)), Path(tmp) / "tdt-local")

    def test_spec_bundles_static_files_and_the_licences(self):
        spec = (PACKAGING / "tdt-local.spec").read_text(encoding="utf-8")
        for needle in ("tdtlocal/static", '"LICENSE"', '"NOTICE"', "TDT_PYTHON_LICENSE", '"licenses"', "console=False"):
            self.assertIn(needle, spec)

    def test_launcher_and_gui_script_point_at_the_desktop_entry(self):
        self.assertIn("tdtlocal.desktop", (PACKAGING / "launcher.py").read_text(encoding="utf-8"))
        self.assertIn("tdtlocal.desktop:main", (PROJECT_DIR / "pyproject.toml").read_text(encoding="utf-8"))


class SslContextTests(unittest.TestCase):
    empty = ssl.DefaultVerifyPaths(None, None, "X", "", "X", "")

    def test_uses_a_system_bundle_when_openssl_has_no_default(self):
        with tempfile.NamedTemporaryFile(suffix=".pem") as bundle:
            context = mock.MagicMock(spec=ssl.SSLContext)
            with (
                mock.patch("tdtlocal.net.sys.platform", "linux"),
                mock.patch("tdtlocal.net.ssl.get_default_verify_paths", return_value=self.empty),
                mock.patch("tdtlocal.net.ssl.create_default_context", return_value=context),
            ):
                self.assertIs(create_ssl_context((bundle.name,)), context)
            context.load_verify_locations.assert_called_once_with(cafile=bundle.name)

    def test_falls_back_to_certifi_and_tolerates_its_absence(self):
        context = mock.MagicMock(spec=ssl.SSLContext)
        fake_certifi = mock.MagicMock()
        fake_certifi.where.return_value = "/certifi/cacert.pem"
        with (
            mock.patch("tdtlocal.net.sys.platform", "darwin"),
            mock.patch("tdtlocal.net.ssl.get_default_verify_paths", return_value=self.empty),
            mock.patch("tdtlocal.net.ssl.create_default_context", return_value=context),
            mock.patch.dict("sys.modules", {"certifi": fake_certifi}),
        ):
            create_ssl_context(("/nope",))
            context.load_verify_locations.assert_called_once_with(cafile="/certifi/cacert.pem")
        context.reset_mock()
        with (
            mock.patch("tdtlocal.net.sys.platform", "darwin"),
            mock.patch("tdtlocal.net.ssl.get_default_verify_paths", return_value=self.empty),
            mock.patch("tdtlocal.net.ssl.create_default_context", return_value=context),
            mock.patch.dict("sys.modules", {"certifi": None}),
        ):
            self.assertIs(create_ssl_context(("/nope",)), context)
        context.load_verify_locations.assert_not_called()

    def test_default_context_is_left_alone_when_it_works(self):
        context = create_ssl_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)


if __name__ == "__main__":
    unittest.main()
