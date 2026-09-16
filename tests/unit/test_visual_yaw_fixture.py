import pytest
from PIL import Image, ImageDraw

from uavlab.training.visual_yaw_fixture import visible_bearing


def test_visible_targets_require_image_and_instruction():
    image = Image.new("RGB", (224, 224), (126, 173, 211))
    d = ImageDraw.Draw(image)
    d.rectangle((30, 30, 45, 60), fill=(220, 35, 35))
    d.rectangle((180, 30, 195, 60), fill=(35, 45, 220))
    assert visible_bearing(image, "red", 112, 112)[0] < 0
    assert visible_bearing(image, "blue", 112, 112)[0] > 0
    flipped = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    assert visible_bearing(flipped, "red", 112, 112)[0] > 0
    assert visible_bearing(flipped, "blue", 112, 112)[0] < 0


@pytest.mark.parametrize("kind", ["missing", "sky", "clipped", "tiny", "down_only"])
def test_teacher_rejects_invisible_or_ambiguous_support(kind):
    image = Image.new("RGB", (224, 224), (126, 173, 211) if kind == "sky" else (80, 80, 80))
    d = ImageDraw.Draw(image)
    if kind == "clipped":
        d.rectangle((0, 25, 10, 50), fill=(220, 35, 35))
    if kind == "tiny":
        d.rectangle((20, 25, 21, 26), fill=(220, 35, 35))
    if kind == "down_only":
        d.rectangle((20, 150, 50, 180), fill=(220, 35, 35))
    with pytest.raises(ValueError):
        visible_bearing(image, "blue" if kind == "sky" else "red", 112, 112)
