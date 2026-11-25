# PyInstaller spec: FutbolDeCabeza.app (macOS arm64, CPU only, no PyCUDA).
# Use tools/packaging/mac/build.sh (it runs this spec and adds servidor.txt).
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", "..", ".."))
ICON = os.path.join(SPECPATH, "FutbolDeCabeza.icns")

analysis = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "fdc", "online", "panel.html"), "fdc/online")],
    excludes=["pycuda", "OpenGL", "tkinter"],
    runtime_hooks=[os.path.join(ROOT, "tools", "pyi_rth_stdout.py")],
)
# assets/ without the logo proposals and the iconset (design material only).
assets = Tree(os.path.join(ROOT, "assets"), prefix="assets",
              excludes=["propuestas", "mac", "__pycache__"])
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
          name="FutbolDeCabeza", console=False, target_arch="arm64")
coll = COLLECT(exe, analysis.binaries, analysis.datas, assets, name="FutbolDeCabeza")
app = BUNDLE(coll, name="FutbolDeCabeza.app",
             icon=ICON if os.path.exists(ICON) else None,
             bundle_identifier="ar.com.timecore.futbol",
             info_plist={"CFBundleDisplayName": "Futbol de Cabeza",
                         "NSHighResolutionCapable": True,
                         "LSMinimumSystemVersion": "11.0"})
