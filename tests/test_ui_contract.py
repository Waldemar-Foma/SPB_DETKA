from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def test_site_logo_is_used_in_sidebar_auth_and_favicon():
    # Буквенная заглушка («К»/«сп») убрана, вместо неё настоящий логотип из static/img.
    for rel in ['templates/auth/login.html', 'templates/auth/register.html', 'templates/_sidebar.html', 'templates/_header.html']:
        text = read(rel)
        assert '>К<' not in text
        assert 'auth-brand' not in text
        assert 'app-sidebar__logo' not in text
    for rel in ['templates/auth/login.html', 'templates/auth/register.html', 'templates/_sidebar.html']:
        assert 'img/logo.svg' in read(rel), rel
    assert 'app-sidebar__brand' in read('templates/_sidebar.html')
    assert 'rel="icon"' in read('templates/base.html')
    for name in ['logo.svg', 'logo-square.svg', 'favicon.png']:
        assert (ROOT / 'static' / 'img' / name).exists(), name


def test_view_switcher_styles_are_restored():
    css = read('static/css/components/header.css')
    assert '.view-switcher' in css
    assert '.view-tab.is-active' in css
    assert 'var(--color-accent)' in css[css.index('.view-tab.is-active'):]


def test_dashboard_list_is_relevance_table():
    html = read('templates/pages/dashboard.html')
    js = read('static/js/pages/dashboardPage.js')
    for text in ['Релевантные исполнители', 'class="shortlist"', 'Индекс релевантности', 'Объём контрактов', 'id="list-search"']:
        assert text in html, text
    assert 'renderShortlist' in js and 'shortlistTable.js' in js
    assert 'contracts_sum_mln' in read('backend/blueprints/procurement.py')


def test_admin_has_api_tests_section_with_speed_results():
    sidebar = read('templates/_sidebar.html')
    page = read('templates/pages/admin_api_tests.html')
    js = read('static/js/pages/apiTestsPage.js')
    py = read('backend/blueprints/admin.py')
    assert 'admin.api_tests_page' in sidebar
    assert 'Тесты АПИ' in page and 'Запустить тест' in page
    assert 'avg_ms' in js and 'min_ms' in js and 'max_ms' in js
    assert '"/api-tests"' in py and '"/api/speed-test"' in py
    assert "dataset.page === 'admin-api-tests'" in read('static/js/main.js')


def test_settings_page_lets_user_change_profile_organization_and_password():
    html = read('templates/pages/settings.html')
    for name in ['full_name', 'email', 'organization_name', 'organization_inn', 'current_password', 'new_password']:
        assert f'name="{name}"' in html, name
    assert 'settings.page' in read('templates/_sidebar.html')
    assert "settings_bp" in read('app.py')
    assert "dataset.page === 'settings'" in read('static/js/main.js')


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



def test_supplier_can_be_changed_until_order_is_completed():
    dashboard = read('backend/blueprints/dashboard.py')
    procurement = read('backend/blueprints/procurement.py')
    detail = read('templates/pages/request_detail.html')
    drawer = read('static/js/components/drawer.js')
    js = read('static/js/pages/dashboardPage.js')
    assert 'procurement.status not in {"matching", "selected"}' in dashboard
    assert 'procurement.status not in {"matching", "selected"}' in procurement
    assert 'Изменить исполнителя' in detail
    assert 'Выбрать вместо текущего' in drawer
    assert "['matching', 'selected'].includes" in js
    assert 'event.persisted' in js and 'window.location.reload()' in js


def test_admin_page_javascript_is_initialized():
    main = read('static/js/main.js')
    assert "./pages/adminPage.js" in main
    assert "dataset.page === 'admin'" in main
    assert 'initAdminPage()' in main


def test_local_and_internet_launchers_and_caddy_are_present():
    assert (ROOT / 'START_LOCAL.bat').exists()
    assert (ROOT / 'START_INTERNET.bat').exists()
    assert (ROOT / 'Caddyfile').exists()
    assert (ROOT / 'docker-compose.internet.yml').exists()
    caddy = read('Caddyfile')
    internet = read('docker-compose.internet.yml')
    assert 'neva-hub.space' in caddy
    assert 'reverse_proxy app:5000' in caddy
    assert '18443:443' in internet


def test_ai_explanation_marks_qwen_and_rejects_foreign_scripts():
    service = read('backend/services/explanation.py')
    drawer = read('static/js/components/drawer.js')
    assert '3–5 предложений' in service
    assert '_contains_forbidden_script' in service
    assert 'qwen2.5:3b' in service
    assert 'Объяснение сформировано локальной Qwen' in drawer
    assert 'Показано объяснение по рассчитанным метрикам' in drawer


def test_auth_password_visibility_and_policy_ui_present():
    register = read('templates/auth/register.html')
    login = read('templates/auth/login.html')
    js = read('static/js/pages/authPage.js')
    assert 'data-password-toggle' in register
    assert 'data-password-toggle' in login
    assert 'data-password-policy' in register
    assert 'Только латиница' in register
    assert 'ASCII_PASSWORD' in js and 'SPECIAL' in js


def test_admin_does_not_show_e5_and_has_clear_component_states():
    html = read('templates/pages/admin.html')
    js = read('static/js/pages/adminPage.js')
    py = read('backend/blueprints/admin.py')
    assert 'Final semantic / E5' not in html
    assert 'health-embeddings' not in html
    assert 'health-embeddings' not in js
    assert 'candidate_search' in py and 'llm' in py
    assert 'Доступно' in js and 'Недоступно' in js


def test_gisp_parser_uses_official_source_and_fast_mirror_fallback():
    worker = read('scripts/gisp_worker.py')
    enrich = read('scripts/enrich_gisp.py')
    assert 'portfolio.gisp.gov.ru' in worker
    assert 'gisp.gov.ru' in worker
    assert 'Скачать только действующие' in worker
    assert '_discover_links' in worker and '_click_download' in worker
    assert 'tovarminpro.online' in worker
    assert '_download_from_mirror' in worker
    assert 'официальный сайт блокирует автоматический доступ (403)' in worker
    assert 'partial-mirror' in worker
    assert 'if not partial_mirror' in enrich
    assert '_read_registry' in enrich
    assert 'строка заголовка' in enrich



def test_supplier_details_load_before_qwen_explanation():
    api = read('backend/blueprints/suppliers.py')
    drawer = read('static/js/components/drawer.js')
    client = read('static/js/api/suppliers.js')
    assert '"status": "pending"' in api
    assert 'def explanation_for' in api
    assert 'getSupplierExplanation' in client
    assert 'Qwen формирует объяснение' in drawer
    assert 'hydrateExplanation' in drawer


def test_company_enrichment_parser_is_integrated():
    parser = read('scripts/sync_company_enrichment.py')
    admin = read('backend/blueprints/admin.py')
    html = read('templates/pages/admin.html')
    compose = read('docker-compose.yml')
    assert 'YANDEX_TEST_DATA_URL' in parser
    assert 'DADATA_TOKEN' in parser
    assert 'build_history_profiles' in parser
    assert 'apply_to_database' in parser
    assert '/api/enrichment/start' in admin
    assert 'Синхронизировать данные' in html
    assert 'DADATA_TOKEN' in compose


def test_gisp_has_403_cooldown_and_faster_mirror_defaults():
    worker = read('scripts/gisp_worker.py')
    assert 'OFFICIAL_BLOCK_CACHE' in worker
    assert '_official_block_active' in worker
    assert 'GISP_MIRROR_WORKERS' in worker and '"10"' in worker
    assert 'GISP_MIRROR_TIMEOUT' in worker and '"8"' in worker

def test_admin_health_rows_are_horizontal():
    css = read('static/css/pages/operations.css')
    assert '.ops-health-grid { display: grid; grid-template-columns: 1fr;' in css
    assert '.ops-health > div { display: flex; align-items: center;' in css
    assert 'white-space: nowrap' in css
