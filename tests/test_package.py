from pathlib import Path

from veyra.extensions.package import inspect_package
from veyra.extensions.repository import RemoteExtension


def test_native_package_classification() -> None:
    extension = RemoteExtension(
        id="demo", name="Demo", version="1", url="https://example.test/demo.zip", package_type="veyra"
    )
    result = inspect_package(Path("demo.zip"), extension)
    assert result.package_type == "veyra"
    assert result.cs3 is None
