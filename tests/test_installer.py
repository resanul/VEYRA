from pathlib import Path

from veyra.extensions.installer import ExtensionInstaller
from veyra.extensions.repository import RemoteExtension


def test_target_path_and_installed(tmp_path: Path) -> None:
    installer = ExtensionInstaller(tmp_path)
    extension = RemoteExtension(
        id="demo",
        name="Demo",
        version="1",
        url="https://example.test/demo.bin",
    )
    target = installer.target_path(extension)
    assert target == tmp_path / "demo" / "extension.bin"
    assert not installer.is_installed(extension)
