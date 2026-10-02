from scripts import gisp_worker as gw


class FakeResponse:
    def __init__(self, status_code=200, text=''):
        self.status_code = status_code
        self.text = text


def test_partial_xlsx_is_valid():
    payload = gw._make_partial_xlsx([('7414003633', 'ПАО «ТЕСТ»')])
    assert gw._looks_like_xlsx(payload)


def test_mirror_exact_inn_detected(monkeypatch):
    html = '''
    <html><body>
      <div>Производитель: ПАО «ТЕСТ»</div>
      <div>Включён: 01.09.2026 Срок: 01.09.2029 ОКПД2: 24.10.31 ИНН: 7414003633</div>
    </body></html>
    '''
    monkeypatch.setattr(gw.requests, 'get', lambda *a, **k: FakeResponse(200, html))
    inn, manufacturer, name, detail = gw._mirror_check_inn('7414003633')
    assert inn == '7414003633'
    assert manufacturer is True
    assert 'ТЕСТ' in name
    assert detail == 'ok'


def test_mirror_missing_inn_is_not_manufacturer(monkeypatch):
    monkeypatch.setattr(gw.requests, 'get', lambda *a, **k: FakeResponse(200, '<html><body>Ничего не найдено</body></html>'))
    _, manufacturer, name, detail = gw._mirror_check_inn('7812345678')
    assert manufacturer is False
    assert name == ''
    assert detail == 'ok'
