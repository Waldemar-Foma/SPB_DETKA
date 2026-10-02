import { toast } from '../components/toast.js';

const $ = (selector, root = document) => root.querySelector(selector);

export function initSettingsPage() {
  document.querySelectorAll('.settings-form').forEach((form) => {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      submitForm(form);
    });
    // Очищаем сообщение об ошибке, как только пользователь начал исправлять поле.
    form.addEventListener('input', (event) => {
      const name = event.target?.name;
      if (name) setFieldError(form, name, '');
    });
  });
}

async function submitForm(form) {
  const button = $('button[type="submit"]', form);
  const payload = Object.fromEntries(new FormData(form).entries());
  clearErrors(form);

  if (form.id === 'form-password' && payload.new_password !== payload.new_password2) {
    setFieldError(form, 'new_password2', 'Новые пароли не совпадают.');
    return;
  }

  button.disabled = true;
  try {
    const response = await fetch(form.dataset.endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = body?.error || {};
      if (error.field) setFieldError(form, error.field, error.message);
      toast(error.message || `Ошибка сохранения (HTTP ${response.status})`, 'error');
      return;
    }
    toast(body.message || 'Сохранено', 'success');
    if (body.profile) applyProfile(body.profile);
    if (form.id === 'form-password') form.reset();
  } catch (error) {
    toast('Не удалось сохранить: ' + error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

function applyProfile(profile) {
  const set = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
  set('settings-name', profile.full_name);
  set('settings-email', profile.email);
  set('settings-initials', profile.initials);
  document.querySelectorAll('[name="organization_inn"]').forEach((el) => { el.value = profile.organization_inn; });
}

function setFieldError(form, name, message) {
  const holder = form.querySelector(`[data-error-for="${name}"]`);
  const input = form.querySelector(`[name="${name}"]`);
  if (holder) holder.textContent = message || '';
  if (input) input.classList.toggle('is-invalid', Boolean(message));
}

function clearErrors(form) {
  form.querySelectorAll('[data-error-for]').forEach((el) => { el.textContent = ''; });
  form.querySelectorAll('.is-invalid').forEach((el) => el.classList.remove('is-invalid'));
}
