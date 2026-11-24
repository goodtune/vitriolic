from PIL import Image

from harness.contact import sheet


def test_sheet_tiles_images_with_labels(tmp_path):
    files = []
    for i in range(5):
        p = tmp_path / f"page{i}-1440.png"
        Image.new("RGB", (1440, 900 + i * 300), (200, 220, 240)).save(p)
        files.append(p)
    out = tmp_path / "contact-1440.png"
    sheet(files, out, columns=4, tile_width=360)
    img = Image.open(out)
    assert img.width == 4 * 360 + 5 * 16  # four tiles, 16 px gutters
    assert img.height > 2 * 225  # two rows
