(() => {
  const byId = name => document.getElementById(`usage-${name}`);
  const {t, locale} = window.MhkI18n;
  const format = Intl.NumberFormat(locale);
  const date = new Intl.DateTimeFormat(locale, {month: 'short', day: 'numeric', timeZone: 'UTC'});
  const timestamp = new Intl.DateTimeFormat(locale, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short'});
  const number = value => value == null ? '—' : format.format(value);
  const dateLabel = value => date.format(new Date(`${value}T00:00:00Z`));
  const refreshButton = byId('refresh');
  const period = byId('period');
  let snapshot;
  let updating = false;

  const text = (name, value) => { byId(name).textContent = value; };
  const make = (tag, value) => {
    const element = document.createElement(tag);
    element.textContent = value;
    return element;
  };

  function status(state, label) {
    const element = byId('status');
    element.dataset.state = state;
    if (element.textContent !== t(label)) element.textContent = t(label);
  }

  function renderHistory() {
    const selected = Number(period.value);
    const days = snapshot.days.slice(-selected - 1, -1);
    const observed = days.filter(day => day.calls !== null);
    for (const [key, name] of [['calls', 'period-calls'], ['ok', 'outcome-ok'], ['failed', 'outcome-failed'], ['unconfirmed', 'outcome-unconfirmed']]) {
      text(name, number(observed.length ? observed.reduce((sum, day) => sum + day[key], 0) : null));
    }

    const peak = Math.max(1, ...observed.map(day => day.calls));
    byId('chart').replaceChildren(...days.map(day => {
      const bar = document.createElement('span');
      bar.title = `${dateLabel(day.date)} · ${number(day.calls)}`;
      if (day.calls === null) bar.dataset.missing = '';
      if (day.calls === 0) bar.dataset.zero = '';
      bar.style.setProperty('--usage-height', `${100 * (day.calls ?? 0) / peak}%`);
      return bar;
    }));
    byId('chart-dates').replaceChildren(...[days[0], days[Math.floor(days.length / 2)], days.at(-1)].map(day => make('span', dateLabel(day.date))));
    byId('table').replaceChildren(...days.map(day => {
      const row = document.createElement('tr');
      const heading = make('th', dateLabel(day.date));
      heading.scope = 'row';
      row.append(heading, make('td', number(day.calls)), make('td', number(day.ok)));
      return row;
    }));

    const tools = snapshot.topTools[selected];
    byId('ranking').replaceChildren(...tools.map(tool => {
      const item = document.createElement('li');
      item.append(make('code', tool.name), make('span', number(tool.calls)));
      return item;
    }));
    byId('no-tools').hidden = tools.length > 0 || !observed.length;
  }

  function render() {
    const today = snapshot.days.at(-1);
    text('today-calls', number(today.calls));
    text('today-ok', number(today.ok));
    text('today-mcp', number(today.mcpRequests));
    text('updated', t('usageAsOf', {time: timestamp.format(new Date(snapshot.asOf))}));
    byId('today').hidden = byId('history').hidden = byId('updated').hidden = false;
    renderHistory();
  }

  async function refresh() {
    if (updating) return;
    updating = true;
    refreshButton.disabled = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);
    try {
      const response = await fetch('/api/v1/usage', {signal: controller.signal});
      if (!response.ok) throw new Error('No usage snapshot');
      const next = await response.json();
      if (next.version !== 1 || !Array.isArray(next.days) || next.days.length !== 31 ||
          !Array.isArray(next.topTools?.[7]) || !Array.isArray(next.topTools?.[30]) || !Number.isFinite(Date.parse(next.asOf))) {
        throw new Error('Invalid usage snapshot');
      }
      const previous = snapshot;
      snapshot = next;
      try { render(); }
      catch (error) { snapshot = previous; if (previous) render(); throw error; }
      status('live', 'usageLive');
    } catch {
      status(snapshot ? 'stale' : 'unavailable', snapshot ? 'usageStale' : 'usageUnavailable');
    } finally {
      clearTimeout(timeout);
      updating = false;
      refreshButton.disabled = false;
    }
  }

  period.addEventListener('change', () => { if (snapshot) renderHistory(); });
  refreshButton.addEventListener('click', refresh);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  setInterval(() => { if (!document.hidden) refresh(); }, 30_000);
  refresh();
})();
