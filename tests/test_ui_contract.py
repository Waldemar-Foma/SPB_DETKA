from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def test_no_site_letter_logo_in_auth_or_shell():
    for rel in ['templates/auth/login.html', 'templates/auth/register.html', 'templates/_sidebar.html', 'templates/_header.html']:
        text = read(rel)
        assert '>К<' not in text
        assert 'auth-brand' not in text
        assert 'app-sidebar__logo' not in text


def test_header_restores_map_and_list_only_on_matching_dashboard():
    header = read('templates/_header.html')
    assert 'data-view="map"' in header
    assert 'data-view="list"' in header
    assert 'data-view="widgets"' not in header
    assert 'Карта' in header and 'Список' in header


def test_map_widgets_are_draggable_in_map_mode():
    js = read('static/js/utils/dragWidgets.js')
    assert "dataset.view !== 'map'" in js
    assert "pointerdown" in js and "pointermove" in js
    assert 'localStorage.setItem' in js


def test_main_nav_has_requests_and_security_but_no_reports_or_supplier_cabinet():
    sidebar = read('templates/_sidebar.html')
    assert "contracts.page" in sidebar
    assert "security.page" in sidebar
    assert 'reports.' not in sidebar
    assert 'cabinet.' not in sidebar
    assert 'suppliers_page.' not in sidebar


def test_request_creation_offers_spec_or_manual():
    html = read('templates/pages/request_new.html')
    assert 'Загрузить ТЗ' in html
    assert 'Описать самостоятельно' in html
    assert 'mode=\'spec\'' in html or "mode='spec'" in html
    assert 'mode=\'manual\'' in html or "mode='manual'" in html


def test_dashboard_has_type_filter_and_top5():
    html = read('templates/pages/dashboard.html')
    for text in ['Производители', 'Дистрибьюторы / оптовики', 'Поставщики', 'Исполнители / подрядчики', 'Топ-5 компаний']:
        assert text in html


def test_theme_is_applied_before_stylesheets_on_main_app():
    html = read('templates/base.html')
    assert html.index("const key = 'procurement-theme'") < html.index('<link rel="stylesheet"')


def test_dark_map_tiles_are_not_dimmed():
    css = read('static/css/components/map-view.css') + read('static/css/components/map.css')
    assert 'brightness(.75)' not in css
    assert 'brightness(.55)' not in css
    assert 'invert(1)' not in css
    assert 'filter: none !important' in css or 'filter:none !important' in css


def test_reports_blueprint_is_not_registered():
    app = read('app.py')
    assert 'reports_bp' not in app
    assert 'backend.blueprints.reports' not in app


def test_only_customer_and_admin_account_roles_exist():
    user = read('backend/models/user.py')
    assert '"customer": "Заказчик"' in user
    assert '"admin": "Администратор"' in user
    for old in ['"supplier":', '"manufacturer":', '"distributor":', '"contractor":']:
        assert old not in user


def test_selection_redirects_to_request_with_contacts():
    drawer = read('static/js/components/drawer.js')
    api = read('backend/blueprints/procurement.py')
    assert 'window.location.replace(result.details_url)' in drawer
    assert 'details_url' in api
    assert 'contacts_locked' in read('backend/blueprints/suppliers.py')


def test_request_context_card_is_draggable_too():
    html = read('templates/pages/dashboard.html')
    js = read('static/js/utils/dragWidgets.js')
    assert 'data-widget="request-context"' in html
    assert 'dash-context__drag-handle' in html
    assert ".dash-context[data-widget]" in js
    assert "procurement-widget-positions-v3" in js


def test_security_page_contains_internal_reviews_section():
    html = read('templates/pages/security.html')
    assert 'Отзывы заказчиков' in html
    assert 'reviews_summary' in html
    assert 'review.comment' in html

def test_supplied_faiss_model_is_integrated_as_first_stage():
    service = read('backend/services/candidate_retrieval.py')
    route = read('backend/blueprints/procurement.py')
    compose = read('docker-compose.yml')
    assert 'suppliers.index' in service
    assert 'all-minilm' in service
    assert 'search_procurement(procurement, top_k=120)' in route
    assert 'all-minilm' in compose
    assert 'faiss-cpu==1.8.0' in read('requirements.txt')


def test_faiss_artifact_map_contains_2000_rows():
    import csv
    path = ROOT / 'ml_artifacts' / 'supplier_index_map.csv'
    with path.open('r', encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2000
    assert rows[0]['faiss_row'] == '0'
    assert rows[-1]['faiss_row'] == '1999'



def test_matching_page_is_locked_after_selection_in_ui_and_backend():
    dashboard = read('backend/blueprints/dashboard.py')
    procurement = read('backend/blueprints/procurement.py')
    detail = read('templates/pages/request_detail.html')
    js = read('static/js/pages/dashboardPage.js')
    assert 'procurement.selected_supplier_inn or procurement.status != "matching"' in dashboard
    assert 'selection_locked' in procurement
    assert 'matching_closed' in procurement
    assert "procurement.status == 'matching' and not procurement.selected_supplier_inn" in detail
    assert 'event.persisted' in js and 'window.location.reload()' in js


def test_ai_explanation_marks_qwen_and_rejects_foreign_scripts():
    service = read('backend/services/explanation.py')
    drawer = read('static/js/components/drawer.js')
    assert '3–5 предложений' in service
    assert '_contains_forbidden_script' in service
    assert 'qwen2.5:3b' in service
    assert 'Объяснение сформировано локальной Qwen' in drawer
    assert 'Показано объяснение по рассчитанным метрикам' in drawer
