from datetime import datetime

import pytest

from app import create_app
from backend.extensions import db
from backend.models import Procurement, User


@pytest.fixture
def app(monkeypatch, tmp_path):
    app = create_app('test')
    # Тесты не должны зависеть от Ollama/FAISS и не должны писать в реальную папку instance.
    monkeypatch.setattr('backend.blueprints.admin._quick_models', lambda: {'candidate_search': {'ok': False}, 'llm': {'ok': False}})
    monkeypatch.setattr('backend.blueprints.admin.SPEED_HISTORY_FILE', tmp_path / 'api_speed_tests.json')
    monkeypatch.setattr('backend.blueprints.admin._probe_candidate_search', lambda: {'ok': True, 'latency_ms': 1})
    monkeypatch.setattr('backend.blueprints.admin._probe_llm', lambda: {'ok': True, 'latency_ms': 1})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def make_user(*, email='customer@test.local', role='customer', inn='7800000000', name='ООО «Старое»', password='Password1!'):
    user = User(email=email, full_name='Иван Петров', account_role=role, organization_inn=inn, organization_name=name)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user.id


def login(client, user_id):
    user = db.session.get(User, user_id)
    with client.session_transaction() as session:
        session['user_id'] = user.id
        session['user_email'] = user.email


def make_request(owner, number='REQ-SET-1'):
    p = Procurement(
        procurement_number=number, title='Поставка оборудования', region='Санкт-Петербург',
        delivery_region='Санкт-Петербург', initial_price=1000, customer_inn=owner,
        source_system='USER', status='matching', updated_at=datetime.utcnow(),
    )
    db.session.add(p)
    db.session.commit()
    return p.procurement_number


# --- Настройки ----------------------------------------------------------------

def test_settings_requires_login(client):
    response = client.get('/settings/', follow_redirects=False)
    assert response.status_code in {302, 303}
    assert '/auth/login' in response.headers['Location']


def test_settings_page_renders_for_customer_and_admin(client):
    uid = make_user()
    login(client, uid)
    html = client.get('/settings/').get_data(as_text=True)
    assert 'form-profile' in html and 'form-organization' in html and 'form-password' in html
    admin_id = make_user(email='admin@test.local', role='admin', inn='7800000099')
    login(client, admin_id)
    assert client.get('/settings/').status_code == 200


def test_profile_update_changes_name_and_email_and_keeps_session(client):
    uid = make_user()
    login(client, uid)
    response = client.post('/settings/api/profile', json={'full_name': 'Пётр  Сидоров', 'email': 'NEW@Test.Local'})
    assert response.status_code == 200
    user = db.session.get(User, uid)
    assert user.full_name == 'Пётр Сидоров'
    assert user.email == 'new@test.local'
    # После смены e-mail пользователь остаётся авторизованным.
    assert client.get('/settings/').status_code == 200


def test_profile_rejects_invalid_and_duplicate_email(client):
    uid = make_user()
    make_user(email='busy@test.local', inn='7811111111')
    login(client, uid)
    assert client.post('/settings/api/profile', json={'full_name': 'Иван', 'email': 'not-an-email'}).status_code == 400
    duplicate = client.post('/settings/api/profile', json={'full_name': 'Иван', 'email': 'busy@test.local'})
    assert duplicate.status_code == 400
    assert duplicate.get_json()['error']['field'] == 'email'
    assert client.post('/settings/api/profile', json={'full_name': 'И', 'email': 'ok@test.local'}).status_code == 400


def test_organization_update_moves_requests_to_new_inn(client):
    uid = make_user(inn='7800000000')
    number = make_request('7800000000')
    login(client, uid)
    response = client.post('/settings/api/organization', json={'organization_inn': '78-12345678 ', 'organization_name': 'ООО «Новое»'})
    assert response.status_code == 200
    assert response.get_json()['migrated_requests'] == 1
    user = db.session.get(User, uid)
    assert user.organization_inn == '7812345678' and user.organization_name == 'ООО «Новое»'
    assert Procurement.query.filter_by(procurement_number=number).one().customer_inn == '7812345678'


def test_organization_update_keeps_requests_for_colleagues(client):
    uid = make_user(inn='7800000000')
    make_user(email='colleague@test.local', inn='7800000000')
    number = make_request('7800000000')
    login(client, uid)
    response = client.post('/settings/api/organization', json={'organization_inn': '7812345678', 'organization_name': 'ООО «Новое»'})
    assert response.status_code == 200
    assert response.get_json()['migrated_requests'] == 0
    assert Procurement.query.filter_by(procurement_number=number).one().customer_inn == '7800000000'


def test_organization_rejects_bad_inn(client):
    uid = make_user()
    login(client, uid)
    response = client.post('/settings/api/organization', json={'organization_inn': '12345', 'organization_name': 'ООО'})
    assert response.status_code == 400
    assert response.get_json()['error']['field'] == 'organization_inn'


def test_password_change_validates_and_applies(client):
    uid = make_user()
    login(client, uid)
    wrong = client.post('/settings/api/password', json={'current_password': 'nope', 'new_password': 'Newpass1!', 'new_password2': 'Newpass1!'})
    assert wrong.status_code == 400 and wrong.get_json()['error']['field'] == 'current_password'
    weak = client.post('/settings/api/password', json={'current_password': 'Password1!', 'new_password': 'weak', 'new_password2': 'weak'})
    assert weak.status_code == 400
    mismatch = client.post('/settings/api/password', json={'current_password': 'Password1!', 'new_password': 'Newpass1!', 'new_password2': 'Other1!x'})
    assert mismatch.status_code == 400
    ok = client.post('/settings/api/password', json={'current_password': 'Password1!', 'new_password': 'Newpass1!', 'new_password2': 'Newpass1!'})
    assert ok.status_code == 200
    user = db.session.get(User, uid)
    assert user.check_password('Newpass1!') and not user.check_password('Password1!')
    assert client.get('/settings/').status_code == 200  # сессия сохранена


def test_demo_seed_does_not_overwrite_changed_admin_account(app):
    from backend.services.demo_users import ADMIN_EMAIL, ensure_admin_user
    ensure_admin_user()
    admin = User.query.filter_by(email=ADMIN_EMAIL).one()
    admin.full_name = 'Главный админ'
    admin.set_password('Changed1!x')
    db.session.commit()
    assert ensure_admin_user() == 0
    admin = User.query.filter_by(email=ADMIN_EMAIL).one()
    assert admin.full_name == 'Главный админ' and admin.check_password('Changed1!x')
    assert admin.account_role == 'admin' and admin.is_active


# --- Тесты API (скорость) --------------------------------------------------------

def test_api_tests_page_is_admin_only(client):
    customer = make_user()
    login(client, customer)
    assert client.get('/admin/api-tests', follow_redirects=False).status_code in {302, 303}
    admin = make_user(email='admin@test.local', role='admin', inn='7800000099')
    login(client, admin)
    html = client.get('/admin/api-tests').get_data(as_text=True)
    assert 'Тесты АПИ' in html and 'apitest-run' in html


def test_speed_test_requires_admin(client):
    customer = make_user()
    login(client, customer)
    assert client.post('/admin/api/speed-test', json={}).status_code == 403


def test_speed_test_reports_timings_and_keeps_history(client):
    admin = make_user(email='admin@test.local', role='admin', inn='7800000099')
    login(client, admin)
    response = client.post('/admin/api/speed-test', json={'runs': 2, 'include_ai': True})
    assert response.status_code == 200
    data = response.get_json()
    ids = {r['id'] for r in data['results']}
    assert {'db-ping', 'suppliers-list', 'analytics-regions', 'admin-status', 'ai-faiss', 'ai-qwen'} <= ids
    db_ping = next(r for r in data['results'] if r['id'] == 'db-ping')
    assert db_ping['ok'] and db_ping['runs'] == 2
    assert db_ping['min_ms'] <= db_ping['avg_ms'] <= db_ping['max_ms']
    assert data['summary']['checks'] == len(data['results'])
    assert data['total_ms'] >= 0

    history = client.get('/admin/api/speed-test/history').get_json()
    assert history['latest']['summary']['checks'] == data['summary']['checks']
    assert len(history['history']) == 1


def test_speed_test_skips_ai_by_default_and_clamps_runs(client):
    admin = make_user(email='admin@test.local', role='admin', inn='7800000099')
    login(client, admin)
    data = client.post('/admin/api/speed-test', json={'runs': 999}).get_json()
    assert data['runs'] == 10
    assert not any(r['id'].startswith('ai-') for r in data['results'])
