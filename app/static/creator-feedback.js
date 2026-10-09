(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const form = $('feedback-form'), button = $('feedback-submit');
  let busy = false, saved = false, attempt = null;
  const fields = ['device', 'task', 'outcome', 'confidence', 'notes'];
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || saved || !form.reportValidity()) return;
    const answers = Object.fromEntries(fields.map(id => [id, $(id).value.trim()]));
    const serialized = JSON.stringify(answers);
    if (!attempt || attempt.serialized !== serialized) attempt = {serialized, request_id: crypto.randomUUID()};
    busy = true; button.disabled = true; button.textContent = 'Saving feedback…';
    fields.forEach(id => { $(id).disabled = true; });
    $('feedback-recovery').hidden = true;
    $('status').classList.remove('error'); $('status').textContent = '';
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch('/api/creator-feedback', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'}, signal: controller.signal,
        body: JSON.stringify({...answers, request_id: attempt.request_id})});
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) $('feedback-recovery').hidden = false;
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Your feedback could not be saved. Please retry.');
      }
      if (!data.ok || !Number.isInteger(data.feedback_id)) throw new Error('We couldn’t confirm it saved. Please retry with the same answers.');
      saved = true; form.hidden = true; $('feedback-saved').hidden = false;
      $('status').textContent = `Feedback #${data.feedback_id} saved.`;
      fields.forEach(id => { $(id).value = ''; });
      attempt = null;
    } catch (error) {
      $('status').classList.add('error');
      $('status').textContent = error.name === 'AbortError' || error instanceof TypeError
        ? 'We couldn’t confirm it saved. Your answers are still here. Retry with the same answers to avoid a duplicate.' : error.message;
    } finally {
      clearTimeout(timeout); busy = false; button.disabled = false; button.textContent = 'Send feedback';
      fields.forEach(id => { $(id).disabled = false; });
      $('status').focus();
    }
  });
})();
