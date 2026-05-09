from pathlib import Path


def test_release_workflow_publishes_multiarch_version_latest_and_sha_tags():
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "platforms: linux/amd64,linux/arm64" in workflow
    assert "short-sha=${GITHUB_SHA::7}" in workflow
    assert "${{ steps.image.outputs.name }}:latest" in workflow
    assert "${{ steps.image.outputs.name }}:${{ steps.version.outputs.version }}" in workflow
    assert "${{ steps.image.outputs.name }}:${{ steps.meta.outputs.short-sha }}" in workflow
