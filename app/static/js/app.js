const output = document.getElementById('output');
const connectionBadge = document.getElementById('connectionBadge');
const playerSelect = document.getElementById('playerSelect');
const deviceSummary = document.getElementById('deviceSummary');
const vlcInstalledBadge = document.getElementById('vlcInstalledBadge');
const vlcRunningBadge = document.getElementById('vlcRunningBadge');
const pcInfo = document.getElementById('pcInfo');
const dailyView = document.getElementById('dailyView');
const settingsView = document.getElementById('settingsView');
const dailyTabButton = document.getElementById('dailyTabButton');
const settingsTabButton = document.getElementById('settingsTabButton');
const discoverResults = document.getElementById('discoverResults');
const nowImage = document.getElementById('nowImage');
const nowTitle = document.getElementById('nowTitle');
const nowArtist = document.getElementById('nowArtist');
const nowAlbum = document.getElementById('nowAlbum');
const nowMeta = document.getElementById('nowMeta');
const audioFormatPanel = document.getElementById('audioFormatPanel');
const speakerPanel = document.getElementById('speakerPanel');
const liveBadge = document.getElementById('liveBadge');
const liveDot = document.getElementById('liveDot');
const liveText = document.getElementById('liveText');
const liveToggleButton = document.getElementById('liveToggleButton');
const liveIntervalSelect = document.getElementById('liveInterval');
const sourceBrowser = document.getElementById('sourceBrowser');
const browserPath = document.getElementById('browserPath');
const queueModeSelect = document.getElementById('queueMode');
const sourceSearchInput = document.getElementById('sourceSearch');
let liveTimer = null;
let liveEnabled = document.body.dataset.liveEnabled !== 'false';
let liveIntervalSeconds = Number(document.body.dataset.liveInterval || 5);
let statusRefreshInFlight = false;
let lastStatusData = null;
let browseStack = [];
let currentBrowse = {sid: '', cid: '', title: 'Quellen'};
let currentBrowseItems = [];

function selectedPlayerId() {
  return playerSelect ? (playerSelect.value || playerSelect.dataset.selected || '') : '';
}

function setBadge(element, text, state = 'idle') {
  if (!element) return;
  element.textContent = text;
  element.dataset.state = state;
}

function setConnectionBadge(text, state = 'idle') {
  setBadge(connectionBadge, text, state);
}

function escapeText(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  }[char]));
}

function line(label, value) {
  if (value === undefined || value === null || value === '') return '';
  return `<div class="result-line"><span>${escapeText(label)}</span><strong>${escapeText(value)}</strong></div>`;
}

function showMessage(title, message = '', state = 'idle', details = []) {
  const detailRows = details.filter(Boolean).join('');
  output.innerHTML = `
    <div class="result-message" data-state="${state}">
      <strong>${escapeText(title)}</strong>
      ${message ? `<span>${escapeText(message)}</span>` : ''}
    </div>
    ${detailRows ? `<div class="result-details">${detailRows}</div>` : ''}
  `;
}

function formatTime(date = new Date()) {
  return date.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
}

function setLiveUi(state = 'idle', text = '') {
  const running = liveEnabled && state !== 'bad';
  setBadge(liveBadge, liveEnabled ? 'Live aktiv' : 'Live aus', liveEnabled ? (state === 'loading' ? 'warn' : 'good') : 'idle');
  if (liveToggleButton) liveToggleButton.textContent = liveEnabled ? 'Live aus' : 'Live an';
  if (liveDot) {
    liveDot.dataset.state = running ? 'good' : (state === 'bad' ? 'bad' : 'idle');
  }
  if (liveText) {
    liveText.textContent = text || (liveEnabled
      ? `Aktualisiert alle ${liveIntervalSeconds} Sekunden.`
      : 'Automatische Aktualisierung ist pausiert.');
  }
  if (liveIntervalSelect) liveIntervalSelect.value = String(liveIntervalSeconds);
}

function describeResult(data, fallbackTitle = 'Fertig') {
  if (!data || typeof data !== 'object') {
    showMessage(fallbackTitle, String(data || ''), 'idle');
    return;
  }

  const ok = data.ok !== false;
  const state = ok ? 'good' : 'bad';
  const title = ok ? fallbackTitle : (data.error || 'Aktion fehlgeschlagen');
  const message = data.message || data.hint || data.response || '';
  const details = [
    line('Player', data.player),
    line('URL', data.url),
    line('IP', data.ip),
    line('Port', data.port || data.rc_port),
    line('Befehl', data.command),
    line('Main Player', data.main_player_id),
    line('Gelöste Gruppen', data.ungrouped_count !== undefined ? data.ungrouped_count : ''),
    line('Gestoppte Räume', data.stopped_count !== undefined ? data.stopped_count : ''),
    line('Geprüfte Räume', data.checked_count !== undefined ? data.checked_count : ''),
    line('Weiter aktiv', data.still_playing_count ? data.still_playing_count : ''),
    line('Gemutete Räume', data.muted_count ? data.muted_count : ''),
    line('Mute-Fehler', data.mute_failed_count ? data.mute_failed_count : ''),
    line('AVR-Zonen aus', data.zones_off_count !== undefined ? data.zones_off_count : ''),
    line('Fehler Räume', data.failed_count ? data.failed_count : ''),
    line('Prozess', data.pid ? `PID ${data.pid}` : ''),
    line('Pfad', data.path),
  ];
  showMessage(title, message, state, details);
}

function clearOutput() {
  showMessage('Ausgabe geleert', 'Bereit für den nächsten Befehl.');
}

async function switchTab(tab, persist = true) {
  const activeTab = tab === 'settings' ? 'settings' : 'daily';
  document.body.dataset.activeTab = activeTab;
  if (dailyView) dailyView.hidden = activeTab !== 'daily';
  if (settingsView) settingsView.hidden = activeTab !== 'settings';
  if (dailyTabButton) dailyTabButton.classList.toggle('active', activeTab === 'daily');
  if (settingsTabButton) settingsTabButton.classList.toggle('active', activeTab === 'settings');
  if (persist) {
    await saveUiSettings({active_tab: activeTab}, false);
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {cache: 'no-store', ...options});
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function post(url, body = null, title = 'Befehl ausgeführt') {
  try {
    showMessage('Sende Befehl', 'Einen Moment bitte.');
    const data = await requestJson(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: body ? JSON.stringify(body) : null
    });
    describeResult(data, title);
    window.setTimeout(() => refreshStatus({silent: true}), 900);
    return data;
  } catch (err) {
    showMessage('Fehler', err.message, 'bad');
    return null;
  }
}

async function saveUiSettings(partial, announce = true) {
  try {
    await requestJson('/api/ui/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(partial)
    });
    if (announce) showMessage('Einstellung gespeichert', 'Die Alltagsansicht merkt sich deine Auswahl.', 'good');
  } catch (err) {
    showMessage('Einstellung nicht gespeichert', err.message, 'bad');
  }
}

async function refreshStatus(options = {}) {
  const silent = Boolean(options.silent);
  if (statusRefreshInFlight) return lastStatusData;
  statusRefreshInFlight = true;
  try {
    if (!silent) setConnectionBadge('Prüfe...', 'idle');
    if (silent && !lastStatusData) setLiveUi('loading', 'Live-Ansicht startet...');
    const pid = selectedPlayerId();
    const params = new URLSearchParams({_ts: String(Date.now())});
    if (pid) params.set('pid', pid);
    const data = await requestJson(`/api/status?${params}`);
    lastStatusData = data;
    updatePlayers(data.players);
    updateConnectionBadge(data);
    updateDeviceSummary(data);
    updateNowPlaying(data);
    updateAvrDetails(data.avr_status);
    setLiveUi('good', `Zuletzt aktualisiert um ${formatTime()}.`);
    if (!silent) showStatus(data);
    return data;
  } catch (err) {
    setConnectionBadge('Fehler', 'bad');
    setLiveUi('bad', `Live-Abfrage fehlgeschlagen: ${err.message}`);
    if (!silent) showMessage('Statusfehler', err.message, 'bad');
    return null;
  } finally {
    statusRefreshInFlight = false;
  }
}

function startLiveMode(persist = true) {
  liveEnabled = true;
  if (liveTimer) window.clearInterval(liveTimer);
  setLiveUi('loading', 'Live-Ansicht startet...');
  refreshStatus({silent: true});
  liveTimer = window.setInterval(() => refreshStatus({silent: true}), liveIntervalSeconds * 1000);
  if (persist) saveUiSettings({live_enabled: true, live_interval_seconds: liveIntervalSeconds}, false);
}

function stopLiveMode(persist = true) {
  liveEnabled = false;
  if (liveTimer) {
    window.clearInterval(liveTimer);
    liveTimer = null;
  }
  setLiveUi('idle');
  if (persist) saveUiSettings({live_enabled: false, live_interval_seconds: liveIntervalSeconds}, false);
}

function toggleLiveMode() {
  if (liveEnabled) {
    stopLiveMode();
  } else {
    startLiveMode();
  }
}

async function setLiveInterval() {
  liveIntervalSeconds = Number(liveIntervalSelect?.value || liveIntervalSeconds || 5);
  await saveUiSettings({live_interval_seconds: liveIntervalSeconds, live_enabled: liveEnabled}, false);
  if (liveEnabled) startLiveMode(false);
  setLiveUi('good', `Live-Intervall auf ${liveIntervalSeconds} Sekunden gesetzt.`);
}

function updateConnectionBadge(data) {
  const ports = data && data.ports ? data.ports : {};
  const heosOk = Boolean(ports.heos && ports.heos.ok);
  const avrOk = Boolean(ports.avr && ports.avr.ok);
  if (heosOk && avrOk) {
    setConnectionBadge('Verbunden', 'good');
  } else if (heosOk || avrOk) {
    setConnectionBadge('Teilweise erreichbar', 'warn');
  } else {
    setConnectionBadge('Nicht erreichbar', 'bad');
  }
}

function updateDeviceSummary(data) {
  if (!deviceSummary) return;
  const ports = data.ports || {};
  const playerCount = data.players && Array.isArray(data.players.payload) ? data.players.payload.length : 0;
  const media = data.now_playing && data.now_playing.payload ? data.now_playing.payload : {};
  const nowPlaying = media.song || media.station || media.album || '';
  deviceSummary.innerHTML = [
    summaryItem('HEOS', ports.heos && ports.heos.ok ? 'erreichbar' : 'nicht erreichbar', ports.heos && ports.heos.ok ? 'good' : 'bad'),
    summaryItem('AVR', ports.avr && ports.avr.ok ? 'erreichbar' : 'nicht erreichbar', ports.avr && ports.avr.ok ? 'good' : 'bad'),
    summaryItem('Player', playerCount ? `${playerCount} gefunden` : 'keiner gefunden', playerCount ? 'good' : 'warn'),
    summaryItem('Jetzt', nowPlaying || 'keine Wiedergabe', nowPlaying ? 'good' : 'warn')
  ].join('');
}

function summaryItem(label, value, state) {
  return `<div class="summary-item" data-state="${state}"><span>${escapeText(label)}</span><strong>${escapeText(value)}</strong></div>`;
}

function showStatus(data) {
  const ports = data.ports || {};
  const players = data.players && Array.isArray(data.players.payload) ? data.players.payload : [];
  const media = data.now_playing && data.now_playing.payload ? data.now_playing.payload : {};
  const avr = data.avr_status || {};
  const details = [
    line('HEOS', ports.heos && ports.heos.ok ? `Port ${ports.heos.port} erreichbar` : ports.heos && ports.heos.message),
    line('AVR', ports.avr && ports.avr.ok ? `Port ${ports.avr.port} erreichbar` : ports.avr && ports.avr.message),
    line('Player', players.length ? players.map((player) => player.name || player.pid).join(', ') : 'Keine HEOS-Player gemeldet'),
    line('Titel', media.song || media.station),
    line('Artist', media.artist),
    line('Album', media.album),
    line('Audio', [avr.sound_mode, avr.sample_rate, avr.input_format].filter(Boolean).join(' · ')),
    line('Lautsprecher', avr.speakers && avr.speakers.length ? avr.speakers.map((speaker) => speaker.name).join(', ') : ''),
  ];
  const ok = Boolean(ports.heos && ports.heos.ok) || Boolean(ports.avr && ports.avr.ok);
  showMessage(ok ? 'Status aktualisiert' : 'Denon nicht erreichbar', ok ? 'Die Verbindung wurde geprüft.' : 'IP, Netzwerk und Denon-Netzwerksteuerung prüfen.', ok ? 'good' : 'bad', details);
}

function updateNowPlaying(data) {
  const media = data.now_playing && data.now_playing.payload ? data.now_playing.payload : {};
  const title = media.song || media.station || media.album || 'Keine Wiedergabe';
  const artist = media.artist || media.type || 'Keine weiteren Titelinformationen gemeldet.';
  const playFields = data.play_state && data.play_state.message_fields ? data.play_state.message_fields : {};
  const volumeFields = data.heos_volume && data.heos_volume.message_fields ? data.heos_volume.message_fields : {};
  const state = data.play_state && data.play_state.payload ? data.play_state.payload.state : playFields.state;
  const volume = data.heos_volume && data.heos_volume.payload ? data.heos_volume.payload.level : volumeFields.level;
  const updated = formatTime();
  if (nowTitle) nowTitle.textContent = title;
  if (nowArtist) nowArtist.textContent = artist;
  if (nowAlbum) nowAlbum.textContent = media.album || '';
  if (nowMeta) {
    nowMeta.textContent = [
      state ? `Status: ${state}` : '',
      volume !== '' ? `HEOS: ${volume}` : '',
      `Live: ${updated}`
    ].filter(Boolean).join(' · ');
  }
  if (nowImage) {
    if (media.image_url) {
      nowImage.src = media.image_url;
      nowImage.hidden = false;
    } else {
      nowImage.hidden = true;
      nowImage.removeAttribute('src');
    }
  }
}

function updateAvrDetails(avr) {
  const status = avr && avr.ok !== false ? avr : {};
  const volume = status.volume || decodeAvrVolumeFromLines(status.raw_lines);
  if (audioFormatPanel) {
    audioFormatPanel.innerHTML = [
      infoItem('Eingang', status.input || 'nicht gemeldet'),
      infoItem('Signal', status.input_format || status.input_signal || 'nicht gemeldet'),
      infoItem('Sampling', status.sample_rate || 'nicht gemeldet'),
      infoItem('Soundmodus', status.sound_mode || 'nicht gemeldet'),
      infoItem('Lautstärke', volume || 'nicht gemeldet'),
      infoItem('Mute', status.mute || 'nicht gemeldet'),
    ].join('');
  }
  if (speakerPanel) {
    const speakers = Array.isArray(status.speakers) ? status.speakers : [];
    speakerPanel.innerHTML = speakers.length
      ? speakers.map((speaker) => `<div class="speaker-pill"><strong>${escapeText(speaker.name)}</strong><span>${escapeText(speaker.trim)}</span></div>`).join('')
      : '<span class="muted">Keine Lautsprecherkanäle gemeldet.</span>';
  }
}

function infoItem(label, value) {
  return `<div><span>${escapeText(label)}</span><strong>${escapeText(value)}</strong></div>`;
}

function decodeAvrVolumeFromLines(lines) {
  if (!Array.isArray(lines)) return '';
  const line = [...lines].reverse().find((item) => /^MV\d+$/.test(item));
  if (!line) return '';
  const raw = line.slice(2);
  const value = Number(raw) / (raw.length === 3 ? 10 : 1);
  if (!Number.isFinite(value)) return '';
  const db = value - 80;
  return raw.length === 3 ? `${db.toFixed(1)} dB` : `${db.toFixed(0)} dB`;
}

function updatePlayers(playersResponse) {
  if (!playerSelect) return;
  const currentValue = playerSelect.value || playerSelect.dataset.selected || '';
  playerSelect.innerHTML = '<option value="">Automatisch wählen</option>';
  const players = playersResponse && Array.isArray(playersResponse.payload) ? playersResponse.payload : [];
  for (const player of players) {
    const option = document.createElement('option');
    option.value = player.pid || '';
    option.textContent = [player.name, player.model, player.ip].filter(Boolean).join(' - ') || `Player ${player.pid}`;
    playerSelect.appendChild(option);
  }
  if ([...playerSelect.options].some((option) => option.value === currentValue)) {
    playerSelect.value = currentValue;
  }
  playerSelect.dataset.selected = playerSelect.value;
}

if (playerSelect) {
  playerSelect.addEventListener('change', () => {
    playerSelect.dataset.selected = selectedPlayerId();
    saveUiSettings({selected_player_id: selectedPlayerId()});
  });
}

async function saveSettings() {
  const body = {
    denon_ip: document.getElementById('denonIp').value.trim(),
    heos_port: Number(document.getElementById('heosPort').value || 1255),
    avr_port: Number(document.getElementById('avrPort').value || 23),
    socket_timeout_seconds: Number(document.getElementById('socketTimeout').value || 3)
  };
  await post('/api/settings', body, 'Verbindung gespeichert');
  document.getElementById('currentIp').innerText = body.denon_ip || 'nicht gesetzt';
  await refreshStatus();
}

function setInput(source) {
  post('/api/avr/input', {source}, 'Eingang geschaltet');
}

function powerOnMainRoom() {
  post('/api/avr/power_on', {
    pid: selectedPlayerId(),
    stop_other_rooms: true,
    mute_fallback: true,
    stop_avr_zones: true
  }, 'Hauptraum eingeschaltet');
}

function heosTransport(action) {
  post(`/api/heos/${action}`, {pid: selectedPlayerId()}, 'HEOS-Befehl gesendet');
}

function setHeosVolume() {
  const level = Number(document.getElementById('heosVolume').value || 40);
  post('/api/heos/volume', {level, pid: selectedPlayerId()}, 'HEOS-Lautstärke gesetzt');
}

function setVolume() {
  post('/api/avr/volume', {volume: Number(document.getElementById('volume').value)}, 'Lautstärke gesetzt');
}

function playUrl() {
  const url = document.getElementById('streamUrl').value.trim();
  if (!url) {
    showMessage('Stream-URL fehlt', 'Bitte zuerst eine URL eintragen.', 'warn');
    return;
  }
  post('/api/heos/play_url', {url, pid: selectedPlayerId()}, 'Stream an HEOS gesendet');
}

async function playHeosInput() {
  const input = document.getElementById('heosInput').value;
  await saveUiSettings({default_heos_input: input}, false);
  await post('/api/heos/input', {input, pid: selectedPlayerId()}, 'HEOS-Eingang gestartet');
}

async function playPreset() {
  const preset = Number(document.getElementById('favoritePreset').value || 1);
  await saveUiSettings({favorite_preset: preset}, false);
  await post('/api/heos/preset', {preset, pid: selectedPlayerId()}, 'HEOS-Favorit gestartet');
}

function quickPreset(preset) {
  document.getElementById('favoritePreset').value = preset;
  playPreset();
}

async function loadHeosSources() {
  try {
    showMessage('Lade Dienste', 'HEOS-Musikquellen werden abgefragt.');
    const data = await requestJson('/api/heos/sources');
    browseStack = [];
    currentBrowse = {sid: '', cid: '', title: 'Quellen'};
    renderBrowseItems(data, 'Quellen', 'sources');
    showSourceList(data, 'Dienste geladen');
  } catch (err) {
    showMessage('Dienste nicht geladen', err.message, 'bad');
  }
}

async function loadHeosPlaylists() {
  try {
    showMessage('Lade Playlists', 'HEOS-Playlists werden abgefragt.');
    const data = await requestJson('/api/heos/playlists');
    showSourceList(data, 'Playlists geladen');
  } catch (err) {
    showMessage('Playlists nicht geladen', err.message, 'bad');
  }
}

function showSourceList(data, title) {
  if (!data || data.ok === false) {
    describeResult(data, title);
    return;
  }
  const items = Array.isArray(data.payload) ? data.payload.slice(0, 12) : [];
  const details = items.map((item) => {
    const label = item.name || item.type || item.sid || item.cid || 'Eintrag';
    const value = [item.type, item.sid ? `SID ${item.sid}` : '', item.cid ? `CID ${item.cid}` : ''].filter(Boolean).join(' · ');
    return line(label, value || 'verfügbar');
  });
  showMessage(title, items.length ? `${items.length} Einträge angezeigt.` : 'Keine Einträge gemeldet.', items.length ? 'good' : 'warn', details);
}

function setBrowserPath(text) {
  if (browserPath) browserPath.textContent = text;
}

function renderBrowseItems(data, title, mode = 'browse') {
  if (!sourceBrowser) return;
  if (!data || data.ok === false) {
    sourceBrowser.innerHTML = '<span class="muted">Keine Einträge verfügbar.</span>';
    setBrowserPath(title);
    return;
  }
  const items = Array.isArray(data.payload) ? data.payload : [];
  currentBrowseItems = items;
  setBrowserPath(title);
  if (!items.length) {
    sourceBrowser.innerHTML = '<span class="muted">Keine Einträge gemeldet.</span>';
    return;
  }
  sourceBrowser.innerHTML = items.map((item, index) => browseItemHtml(item, index, mode)).join('');
}

function browseItemHtml(item, index, mode) {
  const name = item.name || item.song || item.station || item.album || item.type || `Eintrag ${index + 1}`;
  const meta = [
    item.type,
    item.sid ? `SID ${item.sid}` : '',
    item.cid ? `CID ${item.cid}` : '',
    item.mid ? `MID ${item.mid}` : '',
    item.playable ? `playable ${item.playable}` : '',
    item.container ? `container ${item.container}` : ''
  ].filter(Boolean).join(' · ');
  const canOpen = mode === 'sources' ? item.sid : item.container === 'yes' && item.cid;
  const canPlay = item.playable === 'yes' || item.mid || item.type === 'station' || item.type === 'song';
  return `
    <div class="browser-item">
      <div class="browser-copy">
        <strong>${escapeText(name)}</strong>
        <span>${escapeText(meta || 'verfügbar')}</span>
      </div>
      <div class="browser-actions">
        ${canOpen ? `<button class="small secondary" onclick="openBrowseItem(${index}, '${escapeText(mode)}')">Öffnen</button>` : ''}
        ${canPlay ? `<button class="small" onclick="playBrowseItem(${index})">Play</button>` : ''}
        ${canPlay ? `<button class="small secondary" onclick="queueBrowseItem(${index})">Queue</button>` : ''}
      </div>
    </div>
  `;
}

function browseItemByIndex(index) {
  const item = currentBrowseItems[Number(index)];
  if (!item) showMessage('Eintrag nicht gefunden', 'Bitte die Quelle neu laden.', 'warn');
  return item || null;
}

async function openBrowseItem(index, mode) {
  const item = browseItemByIndex(index);
  if (!item) return;
  const next = mode === 'sources'
    ? {sid: String(item.sid || ''), cid: '', title: item.name || `Quelle ${item.sid}`}
    : {sid: currentBrowse.sid, cid: String(item.cid || ''), title: item.name || item.album || item.type || 'Container'};
  if (!next.sid) {
    showMessage('Quelle fehlt', 'Der Eintrag enthält keine SID.', 'warn');
    return;
  }
  browseStack.push({...currentBrowse});
  currentBrowse = next;
  await browseCurrent();
}

async function browseCurrent() {
  if (!currentBrowse.sid) {
    await loadHeosSources();
    return;
  }
  try {
    showMessage('Lade Quelle', currentBrowse.title || currentBrowse.sid);
    const data = await requestJson('/api/heos/browse', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({sid: currentBrowse.sid, cid: currentBrowse.cid, range: '0,49'})
    });
    renderBrowseItems(data, currentBrowse.title || `SID ${currentBrowse.sid}`);
    showSourceList(data, 'Quelle geladen');
  } catch (err) {
    showMessage('Quelle nicht geladen', err.message, 'bad');
  }
}

async function browseBack() {
  if (!browseStack.length) {
    await loadHeosSources();
    return;
  }
  currentBrowse = browseStack.pop();
  if (!currentBrowse.sid) {
    await loadHeosSources();
  } else {
    await browseCurrent();
  }
}

async function playBrowseItem(index) {
  const item = browseItemByIndex(index);
  if (!item) return;
  const sid = item.sid || currentBrowse.sid;
  const cid = item.cid || currentBrowse.cid || '';
  const mid = item.mid || '';
  const name = item.name || item.station || item.song || '';
  if (!sid || !mid) {
    showMessage('Nicht spielbar', 'Der Eintrag enthält keine SID oder MID.', 'warn');
    return;
  }
  await post('/api/heos/station', {sid, cid, mid, name, pid: selectedPlayerId()}, 'HEOS-Eintrag gestartet');
}

async function queueBrowseItem(index) {
  const item = browseItemByIndex(index);
  if (!item) return;
  const sid = item.sid || currentBrowse.sid;
  const cid = item.cid || currentBrowse.cid || '';
  const mid = item.mid || '';
  const aid = Number(queueModeSelect?.value || 1);
  if (!sid || (!cid && !mid)) {
    showMessage('Queue nicht möglich', 'Der Eintrag enthält keine SID, CID oder MID.', 'warn');
    return;
  }
  await post('/api/heos/queue', {sid, cid, mid, aid, pid: selectedPlayerId()}, 'Queue aktualisiert');
}

async function searchCurrentSource() {
  const search = sourceSearchInput?.value.trim() || '';
  if (!currentBrowse.sid) {
    showMessage('Keine Quelle ausgewählt', 'Bitte zuerst eine HEOS-Quelle öffnen.', 'warn');
    return;
  }
  if (!search) {
    showMessage('Suchbegriff fehlt', 'Bitte einen Suchbegriff eintragen.', 'warn');
    return;
  }
  try {
    showMessage('Suche läuft', search);
    const criteria = await requestJson('/api/heos/search_criteria', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({sid: currentBrowse.sid})
    });
    const criteriaItems = Array.isArray(criteria.payload) ? criteria.payload : [];
    const firstCriteria = criteriaItems[0] || {};
    const scid = firstCriteria.scid || firstCriteria.id || firstCriteria.name || '';
    const data = await requestJson('/api/heos/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({sid: currentBrowse.sid, search, scid, range: '0,49'})
    });
    browseStack.push({...currentBrowse});
    currentBrowse = {...currentBrowse, title: `Suche: ${search}`};
    renderBrowseItems(data, currentBrowse.title);
    showSourceList(data, 'Suche abgeschlossen');
  } catch (err) {
    showMessage('Suche fehlgeschlagen', err.message, 'bad');
  }
}

async function discoverAvr() {
  if (!discoverResults) return;
  discoverResults.innerHTML = '<span class="muted">Suche im lokalen Netz...</span>';
  showMessage('AVR-Suche läuft', 'Das lokale Netzwerk wird nach HEOS/AVR-Ports durchsucht.');
  try {
    const data = await requestJson('/api/discover');
    renderDiscoverResults(data);
    const best = data.devices && data.devices[0];
    if (best && best.score >= 80) {
      showMessage('AVR-Kandidat gefunden', `${best.ip} sieht nach Denon/HEOS aus.`, 'good', [
        line('Offene Ports', best.open_ports.join(', ')),
        line('Netz', (data.networks || []).join(', '))
      ]);
    } else {
      showMessage('Kein HEOS-Kandidat gefunden', 'Prüfe Strom, Netzwerksteuerung und ob PC und AVR im gleichen WLAN/LAN sind.', 'warn');
    }
  } catch (err) {
    discoverResults.innerHTML = '<span class="muted">Suche fehlgeschlagen.</span>';
    showMessage('AVR-Suche fehlgeschlagen', err.message, 'bad');
  }
}

function renderDiscoverResults(data) {
  const devices = (data.devices || []).slice(0, 10);
  if (!devices.length) {
    discoverResults.innerHTML = '<span class="muted">Keine Kandidaten gefunden.</span>';
    return;
  }
  discoverResults.innerHTML = devices.map((device) => `
    <div class="discover-item">
      <div>
        <strong>${escapeText(device.ip)}</strong>
        <span>${escapeText(device.kind)} · Ports ${escapeText(device.open_ports.join(', '))}</span>
      </div>
      <button onclick="applyDiscoveredIp('${escapeText(device.ip)}')">Übernehmen</button>
    </div>
  `).join('');
}

async function applyDiscoveredIp(ip) {
  const data = await post('/api/discover/apply', {ip}, 'Denon-IP übernommen');
  if (!data || data.ok === false) return;
  document.getElementById('denonIp').value = ip;
  document.getElementById('currentIp').innerText = ip;
  await refreshStatus();
}

async function refreshBridgeStatus() {
  try {
    const data = await requestJson('/api/audio_bridge/status');
    updateBridgeUi(data);
    showBridgeStatus(data);
  } catch (err) {
    showMessage('Bridge-Statusfehler', err.message, 'bad');
  }
}

function updateBridgeUi(data) {
  const vlc = data.vlc || {};
  if (data.vlc_path) document.getElementById('vlcPath').value = data.vlc_path;
  if (vlc.rc_port) document.getElementById('vlcRcPort').value = vlc.rc_port;
  setBadge(vlcInstalledBadge, vlc.installed ? 'VLC gefunden' : 'VLC fehlt', vlc.installed ? 'good' : 'warn');
  setBadge(vlcRunningBadge, vlc.running ? `VLC läuft ${vlc.pid || ''}` : 'VLC gestoppt', vlc.running ? 'good' : 'idle');
  if (pcInfo) pcInfo.textContent = `${data.pc_name || 'PC'} · ${data.pc_ip || '127.0.0.1'}`;
}

function showBridgeStatus(data) {
  const vlc = data.vlc || {};
  const details = [
    line('VLC', vlc.installed ? 'installiert' : 'nicht gefunden'),
    line('Status', vlc.running ? 'läuft' : 'gestoppt'),
    line('RC-Port', vlc.rc_port),
    line('Letzte URL', vlc.last_url),
    line('Pfad', vlc.vlc_path),
  ];
  showMessage('Bridge geprüft', vlc.running ? 'VLC kann lokal gesteuert werden.' : 'Starte einen Stream, um VLC mit Steuerung zu öffnen.', vlc.installed ? 'good' : 'warn', details);
}

async function saveBridgeSettings() {
  const optionalValue = (id) => document.getElementById(id)?.value.trim() || '';
  const body = {
    mode: document.getElementById('bridgeMode')?.value || 'manual',
    vlc_path: optionalValue('vlcPath'),
    default_stream_url: optionalValue('pcStreamUrl'),
    vlc_rc_port: Number(document.getElementById('vlcRcPort')?.value || 4212),
    vlc_volume: Number(document.getElementById('vlcVolume')?.value || 160),
    airplay_tool_path: optionalValue('airplayToolPath'),
    dlna_tool_path: optionalValue('dlnaToolPath')
  };
  await post('/api/audio_bridge/settings', body, 'Bridge gespeichert');
  await refreshBridgeStatus();
}

async function openPcStream() {
  const url = document.getElementById('pcStreamUrl').value.trim();
  if (!url) {
    showMessage('Stream-URL fehlt', 'VLC braucht eine Netzwerk-Stream-URL oder Datei-URL.', 'warn');
    return;
  }
  const data = await post('/api/audio_bridge/vlc/open_stream', {url}, 'VLC gestartet');
  if (data) await refreshBridgeStatus();
}

async function vlcCommand(command) {
  const data = await post('/api/audio_bridge/vlc/command', {command}, 'VLC-Befehl gesendet');
  if (data) await refreshBridgeStatus();
}

async function setVlcVolume() {
  const value = Number(document.getElementById('vlcVolume').value || 160);
  const data = await post('/api/audio_bridge/vlc/command', {command: 'volume', value}, 'VLC-Lautstärke gesetzt');
  if (data) await saveBridgeSettings();
}

async function stopVlc() {
  const data = await post('/api/audio_bridge/vlc/stop', null, 'VLC beendet');
  if (data) await refreshBridgeStatus();
}

function showBridgeHelp() {
  showMessage(
    'PC Audio Bridge Setup',
    'VLC wird mit einer lokalen Steuer-Schnittstelle gestartet. Für AirPlay oder DLNA brauchst du weiterhin ein separates Receiver-Tool.',
    'idle',
    [
      line('VLC', 'https://www.videolan.org/vlc/'),
      line('RC-Schnittstelle', 'nur lokal auf 127.0.0.1'),
      line('Hinweis', 'Normaler AVR-Ton wird nicht automatisch als HEOS-Stream an Windows gesendet.')
    ]
  );
}

Object.assign(window, {
  applyDiscoveredIp,
  clearOutput,
  discoverAvr,
  heosTransport,
  loadHeosPlaylists,
  loadHeosSources,
  openPcStream,
  openBrowseItem,
  powerOnMainRoom,
  playHeosInput,
  playBrowseItem,
  playPreset,
  playUrl,
  browseBack,
  queueBrowseItem,
  post,
  quickPreset,
  refreshBridgeStatus,
  refreshStatus,
  saveBridgeSettings,
  saveSettings,
  searchCurrentSource,
  setLiveInterval,
  setHeosVolume,
  setInput,
  setVlcVolume,
  setVolume,
  showBridgeHelp,
  stopVlc,
  switchTab,
  toggleLiveMode,
  vlcCommand,
});

switchTab(document.body.dataset.activeTab, false);
refreshBridgeStatus();
if (liveEnabled) {
  startLiveMode(false);
} else {
  setLiveUi('idle');
  refreshStatus();
}
