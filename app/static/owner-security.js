(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let busy = false;
  function show(next) {
    for (const id of ['sign-in','enroll','verification','recovery','manage']) $(id).hidden = id !== next;
    $('intro').textContent = next === 'verification' ? 'One more step to confirm it’s you.' :
      next === 'enroll' ? 'Add a second layer of protection for your owner account.' :
      next === 'manage' ? 'Your account controls and recovery options.' : 'Private access for the Sabeel owner.';
  }
  function note(message) { $('message').textContent = message; $('message').hidden = !message; }
  async function api(path, body) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
    try {
      const res = await fetch('/auth/owner-security' + path, {
        method:body === undefined ? 'GET' : 'POST', credentials:'same-origin', cache:'no-store',
        headers:{'Accept':'application/json', ...(body === undefined ? {} : {'Content-Type':'application/json'})},
        ...(body === undefined ? {} : {body:JSON.stringify(body)}), signal:controller.signal
      });
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 401) show('sign-in');
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Verification could not be completed.');
      }
      return data;
    } finally { clearTimeout(timer); }
  }
  async function action(fn) {
    if (busy) return; busy = true; note('');
    document.querySelectorAll('button').forEach(b => b.disabled = true);
    try { await fn(); }
    catch (e) { note(e.name === 'AbortError' || e instanceof TypeError ?
      'The result could not be confirmed. Refresh this page before trying again.' : e.message); }
    finally {
      $('code').value = ''; $('replacement-code').value = '';
      busy = false; document.querySelectorAll('button').forEach(b => b.disabled = false);
      $('finish').disabled = !$('saved').checked;
    }
  }
  function recovery(codes) {
    $('qr').removeAttribute('src'); $('setup-key').textContent = ''; $('code').value = '';
    $('codes').replaceChildren();
    for (const code of codes) { const li = document.createElement('li'); li.textContent = code; $('codes').appendChild(li); }
    $('saved').checked = false; show('recovery');
  }
  $('start').addEventListener('click', () => action(async () => {
    const data = await api('/enroll', {});
    $('qr').src = data.qr; $('setup-key').textContent = data.setup_key;
    $('setup').hidden = false; $('start').hidden = true; $('verification').hidden = false;
    $('code-help').textContent = 'Enter a six-digit code from the authenticator you just added.';
    $('code').focus();
  }));
  $('verification').addEventListener('submit', e => {
    e.preventDefault(); const code = $('code').value.trim();
    action(async () => {
      const data = await api('/verify', {code}); $('code').value = '';
      if (data.recovery_codes) recovery(data.recovery_codes);
      else window.location.assign('/admin');
    });
  });
  $('reauth').addEventListener('click', () => action(async () => {
    await api('/reauth', {}); show('verification'); $('code').focus();
  }));
  $('replace-codes').addEventListener('submit', e => {
    e.preventDefault(); const code = $('replacement-code').value.trim();
    action(async () => { const data = await api('/recovery', {code}); $('replacement-code').value = ''; recovery(data.recovery_codes); });
  });
  $('revoke').addEventListener('click', () => action(async () => {
    await api('/revoke-sessions', {}); note('Other sessions are signed out. This device remains signed in.');
  }));
  $('saved').addEventListener('change', () => { $('finish').disabled = !$('saved').checked; });
  $('finish').addEventListener('click', () => { if ($('saved').checked) window.location.assign('/admin'); });
  window.addEventListener('pagehide', () => {
    $('codes').replaceChildren(); $('setup-key').textContent = ''; $('qr').removeAttribute('src');
    $('code').value = ''; $('replacement-code').value = '';
  });
  window.addEventListener('pageshow', e => { if (e.persisted) window.location.reload(); });
  action(async () => {
    const data = await api('/status');
    show(data.mode === 'verify' ? 'verification' : data.mode === 'sign_in' ? 'sign-in' : data.mode);
    if (data.mode === 'manage') $('remaining').textContent = `${data.recovery_remaining} recovery codes remaining.`;
  });
})();
