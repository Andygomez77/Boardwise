"""python -m tests.test_updater — chequea la comparación de versiones sin tocar la red."""
import io
import json
from unittest import mock

from boardwise import updater


def release(tag, asset=updater.ASSET):
    body = json.dumps({"tag_name": tag, "assets": [{"name": asset, "url": "https://api/asset/1"}]}).encode()
    return mock.patch.object(updater, "_open", return_value=io.BytesIO(body))


with mock.patch.object(updater, "current_version", return_value=5):
    with release("v6"):
        assert updater.check() == (6, "https://api/asset/1")
    with release("v5"):
        assert updater.check() is None
    with release("v4"):
        assert updater.check() is None
    with release("v6", asset="otro.zip"):
        assert updater.check() is None  # release sin el zip de esta plataforma
print("ok")
