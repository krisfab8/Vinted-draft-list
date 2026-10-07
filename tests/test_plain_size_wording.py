"""Listing copy reads like a person wrote it: no bracketed notes, sizes spelled out in the title."""
import pytest

from app.services import description_layout
from app.services.premium_features import ensure_title_size, retitle_size


def test_label_word_and_letter_are_one_size():
    assert description_layout.size_text(dict(tagged_size='Large', normalized_size='L')) == 'L / Large'


def test_logo_detail_has_no_quotes_or_brackets():
    item = dict(description='Polo.', garment_text=[
        {'text': 'DUNBARNIE LINKS', 'location': 'chest embroidery', 'confidence': 'high'}])
    description_layout.apply(item)
    assert '- Logo / print: DUNBARNIE LINKS, chest embroidery' in item['description']
    assert '(' not in item['description'] and '“' not in item['description']


@pytest.mark.parametrize('title, size, expected', [
    ('Galvin Green Polo Shirt Mens Navy L', 'L', 'Galvin Green Polo Shirt Mens Navy Size Large'),
    ('Peter Millar Polo Mens S Blue', 'S', 'Peter Millar Polo Mens Size Small Blue'),
    ('Polo Shirt Mens Size M', 'M', 'Polo Shirt Mens Size Medium'),
    ('Polo Shirt Mens XL', 'XL', 'Polo Shirt Mens Size Extra Large'),
    ('Polo Shirt Mens Large', 'L', 'Polo Shirt Mens Size Large'),
    ('Dunbarnie Links Polo Mens', 'L', 'Dunbarnie Links Polo Mens Size Large'),
    ('Levi 501 Jeans W32 L30', 'W32 L30', 'Levi 501 Jeans W32 L30'),
    ('Boggi Blazer 44R', '44R', 'Boggi Blazer 44R'),
])
def test_title_spells_letter_sizes(title, size, expected):
    listing = dict(title=title, normalized_size=size)
    ensure_title_size(listing)
    assert listing['title'] == expected
    ensure_title_size(listing)  # running again changes nothing
    assert listing['title'] == expected


def test_title_left_alone_when_too_long():
    title = 'x' * 115 + ' L'
    listing = dict(title=title, normalized_size='L')
    ensure_title_size(listing)
    assert listing['title'] == title


def test_size_edit_swaps_spelled_size_in_title():
    listing = dict(title='Galvin Green Links Polo Mens Size Large Navy', normalized_size='M')
    retitle_size(listing, 'L')
    assert listing['title'] == 'Galvin Green Links Polo Mens Size Medium Navy'
