/* Invitation secrets stay in memory; never analytics, storage, or request URLs. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const status = (message, error = false, id = 'status') => {
    $(id).textContent = message; $(id).classList.toggle('error', error);
  };
  async function api(path, body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(path, {method: body ? 'POST' : 'GET', credentials: 'same-origin',
        cache: 'no-store', headers: body ? {'Content-Type': 'application/json'} : {},
        body: body ? JSON.stringify(body) : undefined, signal: controller.signal});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check the form and try again.');
      return data;
    } catch (error) {
      if (error.name === 'AbortError' || error instanceof TypeError || error instanceof SyntaxError)
        throw new Error('Connection interrupted. Your request may have completed. Sign in if you were joining; refresh the list if you were managing invitations.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  const date = value => new Intl.DateTimeFormat(undefined, {dateStyle:'medium'}).format(new Date(value));
  async function join() {
    let token = new URLSearchParams(location.hash.slice(1)).get('invite') || '';
    history.replaceState(null, '', location.pathname);
    if (!/^[A-Za-z0-9_-]{43}$/.test(token)) {
      status('Open the complete private invitation link that Sabeel sent you.', true);
      $('recovery').hidden = false; return;
    }
    try {
      const info = await api('/auth/tester-invitations/check', {token});
      status('Your invitation is ready.');
      $('pilot-summary').textContent = `${info.pilot_days} days of creator access from the day you join. Up to ${info.daily_images} image and ${info.daily_text} writing requests daily, subject to shared preview capacity. Join by ${date(info.expires_at)}.`;
      $('pilot-details').hidden = $('join-form').hidden = false;
    } catch (error) { status(error.message, true); $('recovery').hidden = false; return; }
    $('join-form').addEventListener('submit', async event => {
      event.preventDefault();
      if ($('join-submit').disabled) return;
      if (new TextEncoder().encode($('password').value).length > 72) {
        status('Please use a password within 72 UTF-8 bytes (some characters use more than one byte).', true); return;
      }
      $('join-submit').disabled = true; $('join-submit').textContent = 'Creating your workspace…';
      status('Creating your private workspace…');
      try {
        const data = await api('/auth/tester-invitations/redeem', {token, name:$('name').value.trim(), email:$('email').value.trim(), password:$('password').value});
        token = ''; $('password').value = ''; $('join-form').hidden = $('pilot-details').hidden = $('recovery').hidden = true;
        status(`Welcome. Your workspace is ready, with access through ${date(data.access_expires_at)}.`);
        $('continue').hidden = false; $('continue').focus();
      } catch (error) { status(error.message, true); $('recovery').hidden = false; }
      finally { $('join-submit').disabled = false; $('join-submit').textContent = 'Create my workspace →'; }
    });
  }
  async function admin() {
    let issuedId = null;
    async function refresh() {
      $('refresh').disabled = true; status('Loading invitations…', false, 'list-status');
      try {
        const data = await api('/api/admin/tester-invitations');
        $('invitations').replaceChildren();
        for (const item of data.items) {
          const row = document.createElement('article'); row.className = 'invitation';
          const content = document.createElement('div');
          const heading = document.createElement('h3'); heading.textContent = item.email;
          const badge = document.createElement('span'); badge.className = 'badge'; badge.textContent = item.status;
          const details = document.createElement('p'); details.textContent = item.redeemed_at ? `Access through ${date(item.access_expires_at)}` : `Join by ${date(item.expires_at)} · ${item.pilot_days}-day pilot`;
          content.append(heading, details, badge); row.append(content);
          if (!['revoked', 'ended'].includes(item.status)) {
            const button = document.createElement('button'); button.className = 'secondary danger'; button.textContent = 'Revoke';
            button.setAttribute('aria-label', `Revoke access for ${item.email}`);
            button.addEventListener('click', async () => {
              if (button.disabled || !confirm(`Revoke ${item.email}? Access will end and scheduled work will stop. Saved work is retained; publishing already in progress may finish.`)) return;
              button.disabled = true; button.textContent = 'Revoking…';
              try {
                await api(`/api/admin/tester-invitations/${encodeURIComponent(item.id)}/revoke`, {});
                if (issuedId === item.id) { $('invite-link').value = ''; $('issued').hidden = true; }
                status('Access revoked. Saved work is retained.'); await refresh();
              } catch (error) { status(error.message, true); }
              finally { button.disabled = false; button.textContent = 'Revoke'; }
            }); row.append(button);
          }
          $('invitations').append(row);
        }
        status(data.items.length ? `${data.items.length} invitation${data.items.length === 1 ? '' : 's'}` : 'No invitations yet. Start with a small, personally invited group.', false, 'list-status');
      } catch (error) { status(error.message, true, 'list-status'); }
      finally { $('refresh').disabled = false; }
    }
    $('invite-form').addEventListener('submit', async event => {
      event.preventDefault(); if ($('invite-submit').disabled) return;
      $('invite-submit').disabled = true; status('Creating a private invitation…');
      $('issued').hidden = true; $('invite-link').value = '';
      try {
        const data = await api('/api/admin/tester-invitations', {email:$('email').value.trim(), invitation_days:Number($('invitation-days').value), pilot_days:Number($('pilot-days').value)});
        issuedId = data.invitation.id; $('invite-link').value = data.link; $('issued').hidden = false;
        status(`Invitation created for ${data.invitation.email}. No email was sent.`);
        await refresh(); $('invite-link').focus(); $('invite-link').select();
      } catch (error) { status(error.message, true); await refresh(); }
      finally { $('invite-submit').disabled = false; }
    });
    $('copy-link').addEventListener('click', async () => {
      try { await navigator.clipboard.writeText($('invite-link').value); status('Private link copied. Send it only to the invited creator.'); }
      catch { $('invite-link').focus(); $('invite-link').select(); status('Select and copy the link above.'); }
    });
    $('refresh').addEventListener('click', refresh);
    await refresh();
  }
  if (document.body.dataset.page === 'join') join();
  else if (document.body.dataset.page === 'admin') admin();
})();
