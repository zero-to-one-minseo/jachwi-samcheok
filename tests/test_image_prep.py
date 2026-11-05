import io
import struct
import unittest
import zlib
from unittest import mock

from PIL import Image

from lib import image_prep, settings
from lib.image_prep import image_tokens, prepare_image, prepare_pdf, prepare_upload, target_size


def jpeg_bytes(width, height, color=(200, 30, 30), *, orientation=None, comment=None):
    image = Image.new("RGB", (width, height), color)
    kwargs = {"quality": 95}
    if orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = orientation
        exif[0x010F] = "SecretCam"
        kwargs["exif"] = exif.tobytes()
    if comment is not None:
        kwargs["comment"] = comment
    out = io.BytesIO()
    image.save(out, format="JPEG", **kwargs)
    return out.getvalue()


def png_header_only(width, height):
    """IHDR만 있는 PNG. Image.open은 머리 정보만 읽으니 큰 크기를 메모리 없이 흉내 낸다."""

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


def open_result(data):
    return Image.open(io.BytesIO(data))


class SizeRuleTest(unittest.TestCase):
    def test_four_by_three_matches_tech_note(self):
        self.assertEqual(target_size(4032, 3024), (2212, 1659))
        self.assertEqual(image_tokens(2212, 1659), 4740)

    def test_square_fits_token_limit(self):
        w, h = target_size(4000, 4000)
        self.assertLessEqual(image_tokens(w, h), settings.IMAGE_MAX_TOKENS)
        self.assertEqual((w, h), (1932, 1932))
        self.assertGreater(image_tokens(w + 28, h + 28), settings.IMAGE_MAX_TOKENS)

    def test_many_ratios_stay_within_both_limits(self):
        for w, h in [(4032, 3024), (3024, 4032), (1920, 1080), (6000, 4000), (2480, 3508), (5000, 4000), (9000, 300)]:
            with self.subTest(size=(w, h)):
                tw, th = target_size(w, h)
                self.assertLessEqual(max(tw, th), settings.IMAGE_MAX_LONG_SIDE)
                self.assertLessEqual(image_tokens(tw, th), settings.IMAGE_MAX_TOKENS)

    def test_small_image_is_not_enlarged(self):
        self.assertEqual(target_size(800, 600), (800, 600))

    def test_48mp_phone_photo_passes_pixel_cap(self):
        self.assertLessEqual(8064 * 6048, settings.IMAGE_MAX_PIXELS)


class PrepareImageTest(unittest.TestCase):
    def test_rotated_exif_is_applied_and_removed(self):
        data = jpeg_bytes(400, 300, orientation=6, comment=b"secret-comment")
        result = prepare_image(data)
        self.assertTrue(result.ok)
        self.assertEqual(result.kind, "image")
        self.assertEqual(result.media_type, "image/jpeg")
        self.assertEqual((result.width, result.height), (300, 400))
        out = open_result(result.data)
        self.assertEqual(out.format, "JPEG")
        self.assertEqual(out.size, (300, 400))
        self.assertEqual(len(out.getexif()), 0)
        self.assertNotIn("comment", out.info)
        self.assertNotIn(b"SecretCam", result.data)
        self.assertNotIn(b"secret-comment", result.data)

    def test_rgba_png_gets_white_background(self):
        image = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
        image.paste((0, 0, 255, 255), (0, 0, 50, 80))
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        result = prepare_image(buf.getvalue())
        self.assertTrue(result.ok)
        out = open_result(result.data).convert("RGB")
        self.assertEqual(out.mode, "RGB")
        r, g, b = out.getpixel((90, 40))
        self.assertGreater(min(r, g, b), 245)
        r, g, b = out.getpixel((10, 40))
        self.assertGreater(b, 200)
        self.assertLess(r, 40)

    def test_palette_with_transparency(self):
        image = Image.new("P", (40, 40), 0)
        image.putpalette([0, 0, 0] * 256)
        image.info["transparency"] = 0
        buf = io.BytesIO()
        image.save(buf, format="PNG", transparency=0)
        result = prepare_image(buf.getvalue())
        self.assertTrue(result.ok)
        self.assertGreater(min(open_result(result.data).getpixel((20, 20))), 245)

    def test_grayscale_and_cmyk_become_rgb(self):
        for mode, color in (("L", 128), ("CMYK", (0, 0, 0, 0))):
            with self.subTest(mode=mode):
                buf = io.BytesIO()
                Image.new(mode, (50, 50), color).save(buf, format="JPEG")
                result = prepare_image(buf.getvalue())
                self.assertTrue(result.ok)
                self.assertEqual(open_result(result.data).mode, "RGB")

    def test_large_photo_is_shrunk_within_limits(self):
        result = prepare_image(jpeg_bytes(4032, 3024))
        self.assertTrue(result.ok)
        self.assertLessEqual(max(result.width, result.height), settings.IMAGE_MAX_LONG_SIDE)
        self.assertLessEqual(image_tokens(result.width, result.height), settings.IMAGE_MAX_TOKENS)
        self.assertGreaterEqual(max(result.width, result.height), 2200)

    def test_square_photo_is_shrunk_under_token_limit(self):
        result = prepare_image(jpeg_bytes(3000, 3000))
        self.assertTrue(result.ok)
        self.assertLessEqual(image_tokens(result.width, result.height), settings.IMAGE_MAX_TOKENS)
        self.assertEqual(open_result(result.data).size, (result.width, result.height))

    def test_too_many_pixels(self):
        result = prepare_image(png_header_only(9000, 7000))
        self.assertFalse(result.ok)
        self.assertEqual(result.error_kind, "너무 큼")
        self.assertEqual(result.message, image_prep.MSG_TOO_BIG_IMAGE)

    def test_decompression_bomb_is_caught(self):
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 100):
            result = prepare_image(jpeg_bytes(100, 100))
        self.assertEqual(result.error_kind, "너무 큼")

    def test_broken_and_unsupported(self):
        self.assertEqual(prepare_image(b"not an image").error_kind, "열 수 없음")
        self.assertEqual(prepare_image(png_header_only(100, 100)).error_kind, "열 수 없음")
        gif = io.BytesIO()
        Image.new("RGB", (10, 10)).save(gif, format="GIF")
        self.assertEqual(prepare_image(gif.getvalue()).error_kind, "지원 안 함")
        heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
        self.assertEqual(prepare_image(heic).error_kind, "지원 안 함")
        self.assertEqual(prepare_upload(heic, "IMG_1.HEIC").error_kind, "지원 안 함")
        self.assertIn("HEIC", prepare_upload(heic, "photo.jpg").message)


class PrepareUploadTest(unittest.TestCase):
    def test_pdf_passthrough(self):
        pdf = b"%PDF-1.7\n" + b"0" * 100
        result = prepare_upload(pdf, "contract.pdf")
        self.assertTrue(result.ok)
        self.assertEqual(result.kind, "pdf")
        self.assertEqual(result.media_type, "application/pdf")
        self.assertIs(result.data, pdf)

    def test_pdf_size_cap(self):
        with mock.patch.object(settings, "PDF_MAX_MB", 0.0001):
            result = prepare_pdf(b"%PDF-1.7\n" + b"0" * 1000)
        self.assertEqual(result.error_kind, "너무 큼")
        self.assertEqual(prepare_pdf(b"not pdf").error_kind, "열 수 없음")

    def test_upload_size_cap_and_extension(self):
        with mock.patch.object(settings, "UPLOAD_MAX_MB", 0.0001):
            self.assertEqual(prepare_upload(jpeg_bytes(50, 50), "a.jpg").error_kind, "너무 큼")
        self.assertEqual(prepare_upload(b"GIF89a....", "a.gif").error_kind, "지원 안 함")
        self.assertTrue(prepare_upload(jpeg_bytes(50, 50), "a.JPG").ok)
        self.assertTrue(prepare_upload(jpeg_bytes(50, 50), None).ok)

    def test_messages_are_polite_korean(self):
        for message in (
            image_prep.MSG_TOO_BIG_IMAGE,
            image_prep.MSG_TOO_BIG_PDF,
            image_prep.MSG_CANNOT_OPEN,
            image_prep.MSG_HEIC,
            image_prep.MSG_UNSUPPORTED,
        ):
            self.assertTrue(message.endswith("요."), message)


if __name__ == "__main__":
    unittest.main()
