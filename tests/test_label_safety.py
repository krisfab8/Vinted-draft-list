from copy import deepcopy
from unittest.mock import patch
from app import extractor
from app.services import label_safety, listing_edits


def extracted(**changes):
    item=dict(brand='M&S',brand_confidence='high',item_type='wool blazer',colour='Brown',
              gender="women's",tagged_size='8',normalized_size='8',materials=['Wool','Polyester lining'],
              material_confidence='low',confidence=.65,low_confidence_fields=['tagged_size'],made_in=None)
    item.update(changes)
    return item


def run(item, reread):
    with patch.object(extractor,'_load_photos',return_value=([],{})), \
         patch.object(extractor,'_extract_claude',return_value=(deepcopy(item),{})), \
         patch.object(extractor,'_reread_material_photo',return_value=reread) as check, \
         patch.object(extractor,'VISION_PROVIDER','claude-haiku'), \
         patch('app.services.measurements.analyze',return_value=[]):
        result,_=extractor.extract('/tmp/no-paid-label-test')
        assert check.call_count == 1
        return result


def test_galvin_uncertain_synthetic_gets_one_grounded_blend_recheck():
    item=extracted(brand='Galvin Green',item_type='polo shirt',tagged_size='Large',normalized_size='Large',
                   materials=['100% Polyester'],material_confidence='medium',low_confidence_fields=['materials'])
    result=run(item,dict(materials=['97% Polyester','3% Elastane'],composition_label_text='97% POLYESTER 3% ELASTANE'))
    assert result['materials']==['97% Polyester','3% Elastane']
    assert result['material_confidence']=='high'
    assert result['tagged_size']=='Large'


def test_ms_unsupported_recheck_cannot_promote_guessed_facts():
    result=run(extracted(),dict(materials=['68% Wool','32% Polyamide']))
    assert result['materials']==[] and result['tagged_size'] is None and result['normalized_size'] is None
    assert result['size_reading_candidate']=='8'
    assert result['item_type']=='blazer'
    assert 'materials' in result['low_confidence_fields']


def test_ms_one_shared_recheck_recovers_printed_l_and_country():
    result=run(extracted(),dict(materials=['Shell: 70% Polyester','Shell: 30% Wool','Lining: 100% Polyester'],
        composition_label_text='SHELL 70% POLYESTER 30% WOOL\nLINING 100% POLYESTER',
        tagged_size='L',size_label_text='L',made_in='Cambodia',origin_label_text='Made in Cambodia'))
    assert result['tagged_size']==result['normalized_size']=='L'
    assert result['made_in']=='Cambodia' and result['material_confidence']=='high'
    assert 'tagged_size' not in result['low_confidence_fields']


def test_transposed_percentages_and_unquoted_size_are_rejected():
    assert not label_safety.composition_supported(['80% Wool','20% Polyester'],'20% Wool 80% Polyester')
    assert not label_safety.size_supported('8','L')
    assert not label_safety.size_supported('8','18')


def test_size_edit_retains_printed_l_updates_only_detail_and_preserves_prose():
    old=dict(tagged_size='L',normalized_size='L',description='My own opening.\n\n- Size: L\n- Material: wool\nMy notes.',manual_fields=['description'])
    new=listing_edits.apply(old,{'normalized_size':'18'})
    assert new['tagged_size']=='L'
    assert '- Size: 18 (equivalent); L (label)' in new['description']
    assert new['description'].startswith('My own opening.') and new['description'].endswith('My notes.')
    assert '- Material: wool' in new['description']


def test_edit_cannot_keep_an_uncertain_8_as_a_printed_label():
    old=dict(tagged_size='8',normalized_size='8',low_confidence_fields=['tagged_size'],description='Opening.\n\n- Size: 8')
    new=listing_edits.apply(old,{'normalized_size':'18'})
    assert new['tagged_size'] is None and '- Size: 18' in new['description']
    assert 'Size: 8' not in new['description']


def test_generated_copy_cannot_reintroduce_withheld_size_or_material():
    from app.services import copy_quality
    item=extracted()
    label_safety.suppress_uncertain(item)
    listing=dict(title='M&S Wool Blazer UK 8',description='Wool blazer. Size: 8',materials=[],tagged_size=None,normalized_size=None)
    result=copy_quality.apply(listing,item)
    assert 'UK 8' not in result['title'] and 'Size: 8' not in result['description']
    assert 'Wool' not in result['title'] and 'Wool' not in result['description']
