"""taiyi-bundle-web-app — web-app bundle。

挂载 host + api + web。base 内的 plugin 已经在 base bundle 中 mount，
这里只追加 web 相关的 rows。
"""
from __future__ import annotations


def get_plugin_paths() -> list[tuple[str, dict]]:
    return [
        ("taiyi_host_webserver.plugin:setup", {"host": "127.0.0.1", "port": 3080}),
        ("taiyi_api.plugin:setup", {}),
        ("taiyi_web.plugin:setup", {}),
    ]