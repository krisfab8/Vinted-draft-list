import json
from urllib.parse import urlparse, parse_qs
import pytest
from app.services.premium_features import ensure_title, confirmed_terms
from app.services.ebay_comps import search_links, _relevant, sold_comparison_summary


def boggi():
    return dict(brand='Boggi', item_type='blazer', title='Boggi Blue Blazer Mens 44R', normalized_size='44R', colour='Blue',
                fabric_mill='Loro Piana', fabric_mill_confidence='high', material_confidence='high',
                materials=['100% Merino Wool'], tag_keywords=['Full Canvas'], tag_keywords_confidence='high')


def test_required_terms_survive_long_title_and_are_idempotent():
    item=boggi();item['title']='Boggi '+ 'Vintage Beautiful Regular Fit Blue '*5
    ensure_title(item);assert len(item['title'])<=120
    for term in ['Boggi','Loro Piana cloth','Merino Wool','Full Canvas','44R']:assert term in item['title']
    first=item['title'];ensure_title(item);assert item['title']==first


def test_confirmed_grade_cashmere_and_uncertainty():
    item=dict(title='Brora Jumper M', brand='Brora', item_type='jumper', materials=['100% Cashmere'], material_confidence='high',
              tag_keywords=['Super 100\'s'], tag_keywords_confidence='high')
    ensure_title(item);assert 'Cashmere' in item['title'];assert 'Super 100s' in item['title']
    item['material_confidence']='low';item['tag_keywords_confidence']='low';assert confirmed_terms(item)==[]
    item['fabric_mill']='Loro Piana';item['low_confidence_fields']=['fabric_mill'];assert confirmed_terms(item)==[]


def test_sold_query_preserves_premium_and_opens_size():
    item=boggi();links=search_links(item);query=parse_qs(urlparse(links['sold']).query)['_nkw'][0]
    assert 'Boggi' in query and 'Loro Piana' in query and 'Merino Wool' in query
    assert '44R' not in query and 'Blue' not in query
    assert _relevant({'title':'Boggi Loro Piana Merino Wool Full Canvas blazer 42R Grey'},item)
    assert not _relevant({'title':'Boggi Wool blazer 44R Blue'},item)
    assert not _relevant({'title':'Loro Piana Merino Wool Full Canvas blazer 44R Blue'},item)


def test_average_other_sizes_and_rejects_wrong_premium_or_brand():
    text='\n'.join(['Boggi Loro Piana Merino Wool Full Canvas blazer 44R Blue | 80',
                    'Boggi Loro Piana Merino Wool Full Canvas blazer 42R Grey | 90',
                    'Boggi Loro Piana Merino Wool Full Canvas blazer 40R Black | 100',
                    'Boggi wool blazer | 20','Loro Piana merino wool full canvas blazer | 300'])
    result=sold_comparison_summary(boggi(),text)
    assert result['sample_count']==3 and result['excluded_count']==2
    assert result['mean_sold_gbp']==90 and result['median_sold_gbp']==90
    assert result['source']=='seller_entered_sold_comparisons'
    result=sold_comparison_summary(boggi(),'Boggi Loro Piana Merino Wool Full Canvas blazer | 80\n'*3)
    assert result['sample_count']==1 and result['mean_sold_gbp'] is None


@pytest.mark.parametrize('text',['title | nan','title | -5','missing separator',None,'x'*20001])
def test_invalid_sale_input_rejected(text):
    with pytest.raises(ValueError):sold_comparison_summary(boggi(),text)


def test_route_keeps_price_and_title(tmp_path,monkeypatch):
    from app import web
    monkeypatch.setattr(web,'ITEMS_DIR',tmp_path)
    folder=tmp_path/'upload_12345678';folder.mkdir();listing=boggi();listing['price_gbp']=123;listing['title']='My edited title'
    (folder/'listing.json').write_text(json.dumps(listing))
    text='\n'.join(f'Boggi Loro Piana Merino Wool Full Canvas blazer {size} | {price}' for size,price in [('44R',80),('42R',90),('40R',100)])
    response=web.app.test_client().post('/api/listing/upload_12345678/sold-comparisons',json={'text':text})
    assert response.status_code==200
    saved=json.loads((folder/'listing.json').read_text())
    assert saved['price_gbp']==123 and saved['title']=='My edited title'
    assert saved['ebay_sold_comparisons']['mean_sold_gbp']==90


def test_writer_finalization_enforces_premium_title():
    from app.listing_writer import finalize_listing
    item=boggi()
    item.update(tagged_size='54', description='Boggi blazer.', category='Men > Suits > Blazers', price_gbp=72)
    generated=dict(item);generated['title']='Boggi blazer 44R'
    result=finalize_listing(generated,item,{})
    assert 'Loro Piana cloth' in result['title'] and 'Merino Wool' in result['title']
    assert result['price_gbp']==72 and result['tagged_size']=='54'


def test_cashmere_blend_stays_distinct_from_pure_cashmere():
    item=dict(brand='Brora', item_type='jumper', title='Brora jumper M', materials=['10% Cashmere','90% Wool'], material_confidence='high')
    ensure_title(item);assert 'Cashmere Blend' in item['title']
    assert not _relevant({'title':'Brora 100% cashmere jumper'},item)
