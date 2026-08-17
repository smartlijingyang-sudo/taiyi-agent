"""Profile 加载和 patch 组合 — 完全对齐 dsh。

流程：
  1. 根据 profile 名加载 profiles/<name>/ 目录
  2. 读取 package.json 获取 bundles 列表
  3. 加载每个 bundle 的 cordis.patch.yml
  4. 加载 profile 自己的 cordis.patch.yml
  5. 按顺序组合所有 patches
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Profile:
    """一个 profile 的完整信息。"""
    name: str
    dir: Path
    bundles: list[str]
    patch_path: Path
    patches: list[dict]  # 来自 cordis.patch.yml


def load_profile(name: str, profile_name: str) -> Profile | None:
    """加载指定名称的 profile。

    Args:
        name: 应用名（"taiyi"）
        profile_name: profile 名称

    Returns:
        Profile 对象，如果不存在则返回 None
    """
    profiles_dir = Path(__file__).parent.parent.parent / "profiles"
    profile_dir = profiles_dir / profile_name

    if not profile_dir.exists():
        return None

    # 读取 package.json
    package_json = profile_dir / "package.json"
    if not package_json.exists():
        return None

    with open(package_json) as f:
        package_data = json.load(f)

    # 获取 bundles 列表
    taiyi_config = package_data.get(name, {})
    profile_config = taiyi_config.get("profile", {})
    bundles = profile_config.get("bundles", [])

    # 读取 cordis.patch.yml
    patch_path = profile_dir / "cordis.patch.yml"
    patches = []
    if patch_path.exists():
        with open(patch_path) as f:
            patches = yaml.safe_load(f) or []

    return Profile(
        name=profile_name,
        dir=profile_dir,
        bundles=bundles,
        patch_path=patch_path,
        patches=patches,
    )


def load_bundle_patches(bundle_name: str) -> list[dict]:
    """加载指定 bundle 的 cordis.patch.yml。

    Args:
        bundle_name: bundle 包名（如 "taiyi-bundle-base"）

    Returns:
        patch 列表
    """
    # bundle 包在 packages/bundle/<name>/cordis.patch.yml
    bundle_dir_name = bundle_name.replace("taiyi-bundle-", "")
    patch_file = Path(__file__).parent.parent.parent / "packages" / "bundle" / bundle_dir_name / "cordis.patch.yml"

    if not patch_file.exists():
        return []

    with open(patch_file) as f:
        return yaml.safe_load(f) or []


def compose_profile_patches(profile: Profile) -> list[dict]:
    """组合 profile 的所有 patches。

    顺序：
      1. 每个 bundle 的 cordis.patch.yml（按 bundles 列表顺序）
      2. profile 自己的 cordis.patch.yml

    Args:
        profile: Profile 对象

    Returns:
        组合后的 patch 列表
    """
    all_patches = []

    # 1. 加载每个 bundle 的 patches
    for bundle_name in profile.bundles:
        bundle_patches = load_bundle_patches(bundle_name)
        all_patches.extend(bundle_patches)

    # 2. 加载 profile 自己的 patches
    all_patches.extend(profile.patches)

    return all_patches
