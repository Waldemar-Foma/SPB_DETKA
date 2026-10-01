from backend.services.geography import logistics_score
from backend.services.role_classifier import classify_role, is_large_distributor, procurement_kind


class Procurement:
    title = 'Поставка свежих пирожков'
    subject = 'Готовые пирожки с ежедневной доставкой'
    okpd2_name = 'Продукты питания'
    keywords = 'пирожки питание свежие'
    okpd2_code = '10.71.11'
    procurement_kind = 'goods'
    delivery_region = 'Санкт-Петербург'
    region = 'Санкт-Петербург'


class Supplier:
    is_gisp_manufacturer = False
    primary_okved = ''
    company_type = 'Поставщик'
    wins_count = 30
    unique_won_okpd2 = 12
    region = 'Иркутская область'


def test_perishable_long_distance_is_penalized():
    geo = logistics_score(Procurement(), Supplier())
    assert geo['profile'] == 'perishable'
    assert geo['score'] < 45
    assert 'невыгод' in geo['note'] or 'стоимость доставки' in geo['note']


def test_large_distributor_is_classification_not_user_role():
    assert is_large_distributor(Supplier()) is True
    assert classify_role(Supplier(), Procurement()) == 'Дистрибьютор / Оптовик'


def test_procurement_kind_understands_services():
    class P:
        title='Оказание услуг по ремонту оборудования'
        okpd2_name='Услуги по ремонту'
        keywords='ремонт обслуживание'
        okpd2_code='33.12.1'
        procurement_kind=None
    assert procurement_kind(P()) in {'services', 'works'}
