import io
from unittest.mock import patch

import pytest
from PIL import Image

from app.web import app
from app.services.photo_prepare import normalize


def photo(fmt='JPEG', size=(100, 80)):
    output = io.BytesIO()
    Image.new('RGB', size, 'navy').save(output, fmt)
    return output.getvalue()


@pytest.mark.parametrize('fmt', ['JPEG', 'PNG', 'WEBP', 'HEIF'])
def test_real_route_converts_supported_bytes_without_ai(fmt):
    with patch('app.services.pipeline.run_pipeline', side_effect=AssertionError('AI started')):
        response = app.test_client().post('/prepare-photo', data={
            'photo': (io.BytesIO(photo(fmt)), 'camera.bin')})
    assert response.status_code == 200
    assert response.mimetype == 'image/jpeg'
    result = Image.open(io.BytesIO(response.data))
    assert result.format == 'JPEG' and result.size == (100, 80)
    assert not result.getexif()


def test_exif_orientation_and_large_camera_photo():
    source = Image.new('RGB', (3000, 2000), 'navy')
    exif = source.getexif()
    exif[274] = 6
    stream = io.BytesIO()
    source.save(stream, 'JPEG', exif=exif)
    result = Image.open(io.BytesIO(normalize(stream.getvalue())))
    assert result.height > result.width
    assert max(result.size) == 2048
    assert not result.getexif()


@pytest.mark.parametrize('data', [b'', b'not an image', b'\xff\xd8broken jpeg'])
def test_invalid_photo_is_actionable_before_ai(data):
    with patch('app.services.pipeline.run_pipeline', side_effect=AssertionError('AI started')):
        response = app.test_client().post('/prepare-photo', data={
            'photo': (io.BytesIO(data), 'photo.jpg')})
    assert response.status_code == 422
    assert 'photo' in response.json['error'].lower()
    assert 'Traceback' not in response.json['error']


def test_oversized_image_rejected_before_decode(monkeypatch):
    from app.services import photo_prepare
    monkeypatch.setattr(photo_prepare, 'MAX_PIXELS', 100)
    response = app.test_client().post('/prepare-photo', data={
        'photo': (io.BytesIO(photo()), 'large.jpg')})
    assert response.status_code == 422
    assert 'resolution' in response.json['error']


def test_missing_photo():
    assert app.test_client().post('/prepare-photo').status_code == 400
