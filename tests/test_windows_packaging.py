import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class WindowsPackagingTests(unittest.TestCase):
    def test_signing_pipeline_files(self):
        required=[
            "packaging/windows/FairScope.spec","packaging/windows/FairScope.iss",
            "packaging/windows/build_windows.ps1","packaging/windows/verify_installer.ps1",
            "packaging/windows/test_installer.ps1","packaging/windows/version_info.txt",
            "packaging/windows/EULA.txt",".github/workflows/windows-signed-installer.yml",
        ]
        for relative in required:self.assertTrue((ROOT/relative).is_file(),relative)
    def test_pyinstaller_metadata_syntax(self):
        for relative in ("packaging/windows/FairScope.spec","packaging/windows/version_info.txt"):
            source=(ROOT/relative).read_text(encoding="utf-8")
            compile(source,relative,"exec")
    def test_version_and_signature_enforcement(self):
        build=(ROOT/"packaging/windows/build_windows.ps1").read_text(encoding="utf-8")
        installer=(ROOT/"packaging/windows/FairScope.iss").read_text(encoding="utf-8")
        version_info=(ROOT/"packaging/windows/version_info.txt").read_text(encoding="utf-8")
        workflow=(ROOT/".github/workflows/windows-signed-installer.yml").read_text(encoding="utf-8")
        self.assertIn("10.4.1",build);self.assertIn('MyAppVersion "10.4.1"',installer);self.assertIn("filevers=(10, 4, 1, 0)",version_info)
        self.assertIn("RequireSignature",build);self.assertIn("signtool",build.lower())
        self.assertIn("require_signature",workflow);self.assertIn("verify_installer.ps1",workflow)
        self.assertIn("publish_release",workflow);self.assertIn("gh release create",workflow)
    def test_no_private_key_material_committed(self):
        forbidden={".pfx",".p12",".pvk",".key"}
        found=[str(p) for p in ROOT.rglob("*") if p.is_file() and p.suffix.lower() in forbidden]
        self.assertEqual(found,[])

if __name__=="__main__":unittest.main()
