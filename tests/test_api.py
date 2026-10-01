from datetime import datetime, timedelta

import pytest

from app import create_app
from backend.extensions import db
from backend.models import Procurement, Supplier, User, SupplierReview


@pytest.fixture
def app(monkeypatch):
    app = create_app('test')
    # Tests must not depend on local AI processes.
    monkeypatch.setattr('backend.blueprints.procurement.warm_similarity_cache', lambda *_a, **_k: None)
    monkeypatch.setattr('backend.services.semantic.embedding', lambda *_a, **_k: None)
    monkeypatch.setattr('backend.blueprints.procurement.search_procurement', lambda *_a, **_k: {
        'ok': False, 'engine': 'all-minilm+faiss', 'model': 'all-minilm', 'items': [], 'reason': 'disabled in test'
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def seed(app):
    with app.app_context():
        customer = User(
            email='customer@test.local', full_name='Тест Заказчик', account_role='customer',
            organization_inn='7800000000', organization_name='Тестовый заказчик'
        )
        customer.set_password('password123')
        suppliers = [
            Supplier(
                inn='7800000001', name='МедТех Петербург', company_type='Поставщик',
                region='Санкт-Петербург', okpd2_codes='32.50.50.190',
                specialization='медицинское оборудование аппаратура', participation_count=20,
                wins_count=8, unique_won_okpd2=2, lat=59.94, lon=30.31,
                phone='+7 812 000-00-01', email='info@medtech.test', website='https://medtech.test'
            ),
            Supplier(
                inn='7700000001', name='МедСнаб Москва', company_type='Поставщик',
                region='Москва', okpd2_codes='32.50.50.190', specialization='медицинское оборудование',
                participation_count=12, wins_count=4, unique_won_okpd2=3, lat=55.75, lon=37.62,
                phone='+7 495 000-00-01', email='info@medsnab.test', website='https://medsnab.test'
            ),
            Supplier(
                inn='6600000001', name='Завод МедПрибор', company_type='Поставщик',
                region='Свердловская область', okpd2_codes='32.50.50.190', specialization='медицинские приборы',
                participation_count=15, wins_count=6, unique_won_okpd2=2, is_gisp_manufacturer=True,
                lat=56.84, lon=60.61, phone='+7 343 000-00-01', email='info@factory.test', website='https://factory.test'
            ),
        ]
        db.session.add_all([customer, *suppliers])
        db.session.commit()
        return customer.id


def login_as(client, user_id):
    with client.session_transaction() as session:
        session['user_id'] = user_id


def create_user_request(app, *, owner='7800000000', number='REQ-TEST-1', updated_at=None):
    with app.app_context():
        p = Procurement(
            procurement_number=number, title='Поставка медицинского оборудования',
            subject='Нужно медицинское оборудование для учреждения',
            okpd2_code='32.50.50.190', okpd2_name='Медицинское оборудование',
            region='Санкт-Петербург', delivery_region='Санкт-Петербург', initial_price=1_000_000,
            keywords='медицинское оборудование', customer_inn=owner,
            procurement_kind='goods', source_system='USER', status='matching',
            updated_at=updated_at or datetime.utcnow(),
        )
        db.session.add(p)
        db.session.commit()
        return p.procurement_number


def test_private_pages_require_login(client):
    for path in ['/contracts/', '/contracts/new', '/dashboard/?procurement=X', '/security/', '/admin/']:
        response = client.get(path, follow_redirects=False)
        assert response.status_code in {302, 303}, path
        assert '/auth/login' in response.headers.get('Location', ''), path


def test_registration_always_creates_customer(client, app):
    response = client.post('/auth/register', data={
        'full_name': 'Иван Петров', 'email': 'ivan@test.local', 'organization_inn': '7812345678',
        'organization_name': 'ООО Тест', 'password': 'password123', 'password2': 'password123',
        'account_role': 'supplier',  # malicious/obsolete field must be ignored
    }, follow_redirects=False)
    assert response.status_code in {302, 303}
    with app.app_context():
        user = User.query.filter_by(email='ivan@test.local').one()
        assert user.account_role == 'customer'


def test_new_customer_dashboard_starts_empty(client, app):
    uid = seed(app); login_as(client, uid)
    response = client.get('/contracts/')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'У вас пока нет заявок' in html
    assert 'Создать заявку' in html


def test_customer_can_create_manual_request(client, app):
    uid = seed(app); login_as(client, uid)
    response = client.post('/contracts/new', data={
        'mode': 'manual', 'title': 'Поставка медицинского оборудования',
        'description': 'Нужно поставить медицинское оборудование в Санкт-Петербург к декабрю.',
        'initial_price': '1500000', 'delivery_region': 'Санкт-Петербург', 'okpd2': '32.50.50.190',
    }, follow_redirects=False)
    assert response.status_code in {302, 303}
    assert '/dashboard/' in response.headers['Location']
    with app.app_context():
        p = Procurement.query.filter_by(source_system='USER', customer_inn='7800000000').one()
        assert p.status == 'matching'
        assert p.input_mode == 'manual'


def test_top5_is_not_hard_limited_to_spb(client, app):
    uid = seed(app); number = create_user_request(app); login_as(client, uid)
    response = client.get(f'/api/v1/procurement/{number}/suppliers')
    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload['items']) <= 5
    regions = {x['region'] for x in payload['items']}
    assert 'Москва' in regions or 'Свердловская область' in regions
    assert payload['meta']['full_pool'] == 3


def test_company_type_filter_recalculates_top(client, app):
    uid = seed(app); number = create_user_request(app); login_as(client, uid)
    response = client.get(f'/api/v1/procurement/{number}/suppliers?company_types=Производитель')
    assert response.status_code == 200
    items = response.get_json()['items']
    assert items
    assert all(x['company_type'] == 'Производитель' for x in items)


def test_selection_reveals_contacts_on_request_page(client, app):
    uid = seed(app); number = create_user_request(app); login_as(client, uid)
    response = client.post(f'/api/v1/procurement/{number}/select', json={'supplier_inn': '7800000001'})
    assert response.status_code == 200
    data = response.get_json()
    assert data['details_url'] == f'/contracts/{number}'
    detail = client.get(data['details_url'])
    html = detail.get_data(as_text=True)
    assert 'МедТех Петербург' in html
    assert '+7 812 000-00-01' in html
    assert 'info@medtech.test' in html


def test_customer_cannot_select_for_foreign_request(client, app):
    uid = seed(app); number = create_user_request(app, owner='7811111111'); login_as(client, uid)
    response = client.post(f'/api/v1/procurement/{number}/select', json={'supplier_inn': '7800000001'})
    assert response.status_code == 403


def test_review_only_after_completed_order(client, app):
    uid = seed(app); number = create_user_request(app); login_as(client, uid)
    client.post(f'/api/v1/procurement/{number}/select', json={'supplier_inn': '7800000001'})
    before = client.post(f'/contracts/{number}/review', data={'rating': '5'}, follow_redirects=False)
    assert before.status_code in {302, 303}
    with app.app_context():
        assert SupplierReview.query.count() == 0
    client.post(f'/contracts/{number}/complete', follow_redirects=False)
    client.post(f'/contracts/{number}/review', data={
        'rating': '5', 'quality_rating': '5', 'deadlines_rating': '4',
        'communication_rating': '5', 'comment': 'Всё выполнено вовремя.'
    }, follow_redirects=False)
    with app.app_context():
        assert SupplierReview.query.count() == 1


def test_request_is_auto_archived_after_one_year_without_touch(client, app):
    uid = seed(app)
    number = create_user_request(app, updated_at=datetime.utcnow() - timedelta(days=366))
    login_as(client, uid)
    client.get('/contracts/')
    with app.app_context():
        p = Procurement.query.filter_by(procurement_number=number).one()
        assert p.status == 'archived'
        assert p.archived_at is not None


def test_reports_are_removed(client, app):
    uid = seed(app); login_as(client, uid)
    assert client.get('/reports/').status_code == 404


def test_security_page_shows_reviews_from_completed_orders(client, app):
    uid = seed(app)
    number = create_user_request(app)
    login_as(client, uid)
    client.post(f'/api/v1/procurement/{number}/select', json={'supplier_inn': '7800000001'})
    client.post(f'/contracts/{number}/complete', follow_redirects=False)
    client.post(f'/contracts/{number}/review', data={
        'rating': '4', 'quality_rating': '5', 'deadlines_rating': '3',
        'communication_rating': '4', 'comment': 'Хороший исполнитель, сроки пришлось уточнить.'
    }, follow_redirects=False)

    response = client.get('/security/?inn=7800000001')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'Отзывы заказчиков' in html
    assert 'Хороший исполнитель, сроки пришлось уточнить.' in html
    assert '4/5' in html
    assert 'Тестовый заказчик' in html


def test_matching_is_locked_after_supplier_selected(client, app):
    uid = seed(app); number = create_user_request(app); login_as(client, uid)
    first = client.post(f'/api/v1/procurement/{number}/select', json={'supplier_inn': '7800000001'})
    assert first.status_code == 200

    dashboard = client.get(f'/dashboard/?procurement={number}', follow_redirects=False)
    assert dashboard.status_code in {302, 303}
    assert f'/contracts/{number}' in dashboard.headers.get('Location', '')

    feed = client.get(f'/api/v1/procurement/{number}/suppliers')
    assert feed.status_code == 409
    assert feed.get_json()['error']['code'] == 'matching_closed'

    second = client.post(f'/api/v1/procurement/{number}/select', json={'supplier_inn': '7700000001'})
    assert second.status_code == 409
    assert second.get_json()['error']['code'] == 'selection_locked'
    with app.app_context():
        p = Procurement.query.filter_by(procurement_number=number).one()
        assert p.selected_supplier_inn == '7800000001'


def test_matching_stays_locked_after_completion_and_delete(client, app):
    uid = seed(app); number = create_user_request(app); login_as(client, uid)
    client.post(f'/api/v1/procurement/{number}/select', json={'supplier_inn': '7800000001'})
    client.post(f'/contracts/{number}/complete', follow_redirects=False)
    assert client.get(f'/api/v1/procurement/{number}/suppliers').status_code == 409

    client.post(f'/contracts/{number}/delete', follow_redirects=False)
    assert client.get(f'/api/v1/procurement/{number}/suppliers').status_code == 410
    dash = client.get(f'/dashboard/?procurement={number}', follow_redirects=False)
    assert dash.status_code in {302, 303}
    assert '/contracts/' in dash.headers.get('Location', '')
