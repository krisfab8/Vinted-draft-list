from app.listing_writer import finalize_listing
from app.services import description_layout


def test_generated_tailoring_details_have_dual_sizes_before_keywords():
    item = dict(brand='Boggi', item_type='wool blazer', tagged_size='54', normalized_size='44R',
                materials=['100% New Zealand Merino Wool'], fabric_mill='Loro Piana',
                fabric_line='Zelander Dream', made_in='Italy', cut='Regular fit',
                gender="men's", colour='Blue', condition_summary='Good used condition',
                brand_confidence='high', material_confidence='high', tag_keywords_confidence='high')
    listing = dict(item, title='Boggi Milano Blue Mens 44R Merino Wool Blazer', price_gbp=85,
                   category='Men > Suits > Blazers', description='Boggi blue blazer.\n- Size: 44R\n'
                   '- Material: Wrong\nKeywords: Boggi Size 54.')
    result = finalize_listing(listing, item)
    desc = result['description']
    assert result['tagged_size'] == '54' and result['normalized_size'] == '44R'
    assert desc.count('- Size:') == 1 and '- Size: UK 44R / EU 54 (label)' in desc
    labels = ['- Size:', '- Made in:', '- Fabric mill:', '- Fabric line:', '- Fit:', '- Material:']
    assert [desc.index(x) for x in labels] == sorted(desc.index(x) for x in labels)
    assert desc.index('- Size:') < desc.index('Keywords:')
    assert 'Wrong' not in desc and '- Good used condition' in desc


def test_unknown_size_and_unconfirmed_conversion_stay_unknown():
    listing = dict(item_type='trousers', description='Toast cords.\n- Size: M\nKeywords: Toast.')
    description_layout.apply(listing)
    assert '- Size:' not in listing['description']
    listing.update(tagged_size='M', normalized_size='M')
    description_layout.apply(listing)
    assert '- Size: M' in listing['description'] and 'EU' not in listing['description']
    assert description_layout.size_text(dict(item_type='dress', tagged_size='38', normalized_size='10')) == '10 (equivalent); 38 (label)'


def test_formatting_preserves_measurements_flaws_and_is_repeatable():
    listing = dict(item_type='blazer', tagged_size='54', normalized_size='44R',
                   description='Blue blazer.\n- Small mark on cuff.\n\n'
                   'Measurements (seller confirmed):\n- Back length: approx. 72 cm\n\nKeywords: Boggi.')
    description_layout.apply(listing)
    first = listing['description']
    description_layout.apply(listing)
    assert first == listing['description']
    assert '- Small mark on cuff.' in first and '- Back length: approx. 72 cm' in first
