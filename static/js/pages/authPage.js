const ASCII_PASSWORD = /^[A-Za-z0-9!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]+$/;
const SPECIAL = /[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/;

export function initAuthPage() {
  document.querySelectorAll('[data-password-wrap]').forEach(initPasswordToggle);
  const password = document.querySelector('input[name="password"][data-password-policy]');
  if (!password) return;

  const repeat = document.querySelector('input[name="password2"]');
  const form = password.form;

  const update = () => {
    const value = password.value || '';
    const checks = {
      length: value.length >= 8,
      latin: value.length > 0 && ASCII_PASSWORD.test(value),
      upper: /[A-Z]/.test(value),
      lower: /[a-z]/.test(value),
      digit: /\d/.test(value),
      special: SPECIAL.test(value),
    };
    document.querySelectorAll('[data-password-check]').forEach((item) => {
      const ok = Boolean(checks[item.dataset.passwordCheck]);
      item.classList.toggle('is-ok', ok);
      item.classList.toggle('is-bad', value.length > 0 && !ok);
    });

    const valid = Object.values(checks).every(Boolean);
    password.setCustomValidity(value && !valid ? 'Пароль не соответствует требованиям.' : '');
    if (repeat) {
      repeat.setCustomValidity(repeat.value && repeat.value !== value ? 'Пароли не совпадают.' : '');
    }
    return valid;
  };

  password.addEventListener('input', update);
  repeat?.addEventListener('input', update);
  form?.addEventListener('submit', (event) => {
    update();
    if (!form.checkValidity()) {
      event.preventDefault();
      form.reportValidity();
    }
  });
  update();
}

function initPasswordToggle(wrapper) {
  const input = wrapper.querySelector('input[type="password"], input[data-password-input]');
  const button = wrapper.querySelector('[data-password-toggle]');
  if (!input || !button) return;

  button.addEventListener('click', () => {
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    button.textContent = showing ? 'Показать' : 'Скрыть';
    button.setAttribute('aria-pressed', String(!showing));
    input.focus({ preventScroll: true });
    try { input.setSelectionRange(input.value.length, input.value.length); } catch (_) {}
  });
}

document.addEventListener('DOMContentLoaded', initAuthPage);
