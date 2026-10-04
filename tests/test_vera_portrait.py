from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from band_mgmt import generate_band_mgmt_panel as panel
from utils import vera_portrait as vera


def test_get_daily_portrait_uses_shared_cascade_with_mode_prompts(
    monkeypatch, tmp_path: Path
) -> None:
    generated = tmp_path / "provider-result.png"
    generated.write_bytes(b"image")
    calls: dict[str, object] = {}

    class FakeCascade:
        def generate(
            self,
            prompt: str,
            *,
            output_dir: Path,
            negative_prompt: str,
        ) -> SimpleNamespace:
            calls["prompt"] = prompt
            calls["output_dir"] = output_dir
            calls["negative_prompt"] = negative_prompt
            return SimpleNamespace(path=generated)

    def build_cascade(persona_svg: Path) -> FakeCascade:
        calls["persona_svg"] = persona_svg
        return FakeCascade()

    shared_module = SimpleNamespace(portrait_image_cascade=build_cascade)
    monkeypatch.setattr(
        vera, "_load_workspace_cascade", lambda: shared_module, raising=False
    )
    monkeypatch.setattr(vera, "_IMAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(vera, "_build_prompt", lambda mode: (f"positive:{mode}", "negative"))

    portrait = vera.get_daily_portrait(mode="pre_show")

    assert calls.get("prompt") == "positive:pre_show"
    assert calls.get("negative_prompt") == "negative"
    assert calls.get("output_dir") == tmp_path
    assert isinstance(calls.get("persona_svg"), Path)
    assert portrait == vera._today_cache_path("pre_show")
    assert portrait.is_file()
    tag = vera.get_portrait_img_tag(max_width=42, mode="pre_show")
    assert "src=\"data:image/png;base64,aW1hZ2U=\"" in tag
    assert 'alt="Vera — Band Manager · Pre-Show"' in tag
    assert "width:42px" in tag


def test_svg_fallback_cache_is_reused_per_mode(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    class FailingCascade:
        def generate(
            self,
            prompt: str,
            *,
            output_dir: Path,
            negative_prompt: str | None,
        ) -> None:
            calls.append(prompt)
            raise RuntimeError("offline")

    shared_module = SimpleNamespace(
        portrait_image_cascade=lambda persona_svg: FailingCascade()
    )
    monkeypatch.setattr(vera, "_load_workspace_cascade", lambda: shared_module)
    monkeypatch.setattr(vera, "_IMAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(vera, "_build_prompt", lambda mode: (mode, None))

    rehearsal_first = vera.get_daily_portrait("rehearsal")
    rehearsal_again = vera.get_daily_portrait("rehearsal")
    pre_show = vera.get_daily_portrait("pre_show")

    assert rehearsal_first == rehearsal_again
    assert rehearsal_first != pre_show
    assert rehearsal_first.suffix == ".svg"
    assert pre_show.suffix == ".svg"
    assert calls == ["rehearsal", "pre_show"]


def test_pruning_keeps_other_modes_and_caps_only_generated_mode(
    monkeypatch, tmp_path: Path
) -> None:
    for mode in ("rehearsal", "pre_show", "show_night"):
        for days_ago in range(1, 5):
            cache_path = tmp_path / (
                f"vera_portrait_{(vera.date.today() - timedelta(days=days_ago)).isoformat()}_{mode}.png"
            )
            cache_path.write_bytes(b"cached")

    generated = tmp_path / "provider-result.png"
    generated.write_bytes(b"image")

    class SuccessfulCascade:
        def generate(self, prompt: str, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(path=generated)

    shared_module = SimpleNamespace(
        portrait_image_cascade=lambda persona_svg: SuccessfulCascade()
    )
    monkeypatch.setattr(vera, "_load_workspace_cascade", lambda: shared_module)
    monkeypatch.setattr(vera, "_IMAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(vera, "_build_prompt", lambda mode: (mode, None))

    vera.get_daily_portrait("show_night")

    files_by_mode = {
        mode: list(tmp_path.glob(f"vera_portrait_*_{mode}.png"))
        for mode in ("rehearsal", "pre_show", "show_night")
    }
    assert len(files_by_mode["rehearsal"]) == 4
    assert len(files_by_mode["pre_show"]) == 4
    assert len(files_by_mode["show_night"]) == vera._MAX_CACHED_PORTRAITS


def test_band_management_panel_embeds_offline_svg_portrait(
    monkeypatch, tmp_path: Path
) -> None:
    class OfflineCascade:
        def generate(self, prompt: str, **kwargs: object) -> None:
            raise RuntimeError("offline")

    shared_module = SimpleNamespace(
        portrait_image_cascade=lambda persona_svg: OfflineCascade()
    )
    monkeypatch.setattr(vera, "_load_workspace_cascade", lambda: shared_module)
    monkeypatch.setattr(vera, "_IMAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(vera, "_build_prompt", lambda mode: (mode, None))
    monkeypatch.setattr(
        panel,
        "_get_vera_tag",
        lambda: vera.get_portrait_img_tag(max_width=160, mode="show_night"),
    )

    html = panel.generate({"exported_at": "offline-test", "bands": []}, [])

    assert "data:image/svg+xml;base64," in html
    assert 'alt="Vera — Band Manager · Show Night"' in html
    assert "bm-vera-portrait" in html