(() => {
  const grid = document.getElementById('account-grid');
  const status = document.getElementById('status');
  const button = document.getElementById('continue-btn');
  let accounts = [], inputs = [], selected = new Set(), saving = false;
  function message(text, error = false) { status.textContent = text; status.classList.toggle('error', error); }
  function updateButton() { button.disabled = saving || selected.size === 0; inputs.forEach(input => { input.disabled = saving; }); }
  async function request(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url, {...options, signal: controller.signal});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Connection expired. Please start again.');
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('This is taking too long. Check your workspace before starting again.');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  async function initialize() {
    try {
      const [available, connected] = await Promise.all([request('/accounts/available'), request('/accounts/connected')]);
      if (!Array.isArray(available) || !Array.isArray(connected)) throw new Error('Account discovery could not be loaded. Start again.');
      accounts = available;
      grid.replaceChildren();
      accounts.forEach(account => {
        const label = document.createElement('label'); label.className = 'account';
        const input = document.createElement('input'); input.type = 'checkbox'; input.value = account.ig_user_id; inputs.push(input);
        const name = document.createElement('span'); name.textContent = account.username ? '@' + account.username : account.name;
        const detail = document.createElement('small'); detail.textContent = connected.includes(account.ig_user_id) ? 'Already connected · select to refresh access' : 'Available to connect';
        name.appendChild(detail); label.append(input, name); grid.appendChild(label);
        input.addEventListener('change', () => { input.checked ? selected.add(account.ig_user_id) : selected.delete(account.ig_user_id); updateButton(); message(selected.size ? `${selected.size} account${selected.size === 1 ? '' : 's'} selected.` : 'Choose at least one account to continue.'); });
      });
      message(accounts.length ? 'Choose at least one account to continue.' : 'No eligible accounts were returned. Check your Facebook Page connection and permissions, then start again.');
    } catch (error) { message(error.message || 'Could not load accounts. Please start again.', true); }
  }
  button.addEventListener('click', async () => {
    if (saving || !selected.size) return;
    saving = true; updateButton(); button.textContent = 'Connecting…'; message('Saving your connection…');
    try {
      const payload = accounts.filter(account => selected.has(account.ig_user_id)).map(account => ({ig_user_id: account.ig_user_id, page_id: account.fb_page_id}));
      const result = await request('/accounts/select', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
      if (!result.ok) throw new Error('Connection was not saved. Please start again.');
      message('Accounts connected. Opening your workspace…'); window.location.assign('/app');
    } catch (error) { message(error.message || 'Connection failed. Please start again.', true); }
    finally { saving = false; updateButton(); button.textContent = 'Connect selected accounts'; }
  });
  updateButton();
  initialize();
})();
