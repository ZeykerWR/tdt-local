// The settings dialog, described as data: what is shown for each setting, and the small pure helpers it needs.

export const TABS = [
  { id: 'ai', label: 'Asistente de IA' },
  { id: 'stt', label: 'Subtítulos y alertas' },
  { id: 'lists', label: 'Listas y guía' },
];

export const LANGUAGES = {
  es: 'Español', ca: 'Català', gl: 'Galego', eu: 'Euskara', en: 'English', fr: 'Français',
  pt: 'Português', de: 'Deutsch', it: 'Italiano', auto: 'Detectar automáticamente',
};

/**
 * Fields in the order they are shown. `type`: bool, number, text, url, path, select, json or secret.
 * `list` names a datalist the dialog fills (models offered by the endpoint, installed Whisper models).
 */
export const FIELDS = [
  { name: 'ai_enabled', tab: 'ai', type: 'bool', label: 'Activar el asistente de IA' },
  { name: 'llm_url', tab: 'ai', type: 'url', label: 'Dirección del servidor',
    hint: 'API compatible con OpenAI, terminada en /v1. Con llama.cpp: http://127.0.0.1:8080/v1', test: 'ai' },
  { name: 'llm_model', tab: 'ai', type: 'text', label: 'Modelo', list: 'llmModels',
    hint: 'Déjalo vacío para usar el que tenga cargado el servidor. «Probar conexión» muestra los disponibles.' },
  { name: 'llm_api_key', tab: 'ai', type: 'secret', label: 'Clave de API (opcional)',
    hint: 'Solo para servicios en línea. Se guarda en tu equipo, en settings.json, y no se vuelve a mostrar.' },
  { name: 'llm_temperature', tab: 'ai', type: 'number', step: 0.1, label: 'Temperatura',
    hint: '0 = respuestas más estables, 2 = más variadas.' },
  { name: 'llm_max_tokens', tab: 'ai', type: 'number', step: 1, label: 'Máximo de tokens por respuesta' },
  { name: 'llm_timeout', tab: 'ai', type: 'number', step: 1, label: 'Tiempo máximo de espera (segundos)' },
  { name: 'llm_disable_thinking', tab: 'ai', type: 'bool', label: 'Pedir al modelo que no «piense» antes de contestar',
    hint: 'Más rápido y evita respuestas cortadas. Desmárcalo si tu modelo no admite estas opciones.' },
  { name: 'llm_extra_params', tab: 'ai', type: 'json', label: 'Parámetros extra (JSON)',
    hint: 'Se añaden a cada petición, p. ej. {"top_p": 0.9, "top_k": 40}. No se puede cambiar «messages».' },

  { name: 'stt_enabled', tab: 'stt', type: 'bool', label: 'Activar subtítulos en directo y alertas por voz' },
  { name: 'whisper_lang', tab: 'stt', type: 'select', label: 'Idioma del audio', options: LANGUAGES },
  { name: 'whisper_model', tab: 'stt', type: 'path', label: 'Modelo (archivo ggml)', list: 'whisperModels',
    hint: 'Vacío = el primero de la carpeta de modelos. Abajo puedes descargar uno.' },
  { name: 'models_dir', tab: 'stt', type: 'path', label: 'Carpeta de modelos',
    hint: 'Vacío = la carpeta predeterminada (se indica abajo). Aquí se descargan los modelos.' },
  { name: 'whisper_bin', tab: 'stt', type: 'path', label: 'Programa whisper-server', test: 'stt',
    hint: 'Vacío = el que haya en el PATH.' },
  { name: 'whisper_url', tab: 'stt', type: 'url', label: 'Dirección del servidor Whisper' },
  { name: 'whisper_autostart', tab: 'stt', type: 'bool', label: 'Lanzar whisper-server automáticamente si no responde' },
  { name: 'whisper_threads', tab: 'stt', type: 'number', step: 1, label: 'Hilos de CPU' },
  { name: 'whisper_idle_minutes', tab: 'stt', type: 'number', step: 1,
    label: 'Apagar el servidor lanzado tras (minutos sin uso)' },

  { name: 'update_hours', tab: 'lists', type: 'number', step: 0.5, label: 'Actualizar las listas cada (horas)' },
  { name: 'auto_check', tab: 'lists', type: 'bool', label: 'Comprobar los streams de la tele tras cada actualización' },
  { name: 'epg_enabled', tab: 'lists', type: 'bool', label: 'Descargar la guía de programación' },
  { name: 'tv_source', tab: 'lists', type: 'url', label: 'Lista de televisión (TELEVISION.md)', advanced: true },
  { name: 'radio_source', tab: 'lists', type: 'url', label: 'Lista de radio (RADIO.md)', advanced: true },
  { name: 'epg_tv_source', tab: 'lists', type: 'url', label: 'Guía de la tele (XMLTV)', advanced: true },
  { name: 'epg_radio_source', tab: 'lists', type: 'url', label: 'Guía de la radio (XMLTV)', advanced: true },
];

export const fieldsOf = (tab) => FIELDS.filter((f) => f.tab === tab);

/**
 * The settings that differ from what the server sent: the only thing worth saving.
 * A secret is sent only if something was typed, or if the user chose to remove it (then as an empty string).
 * @param {Record<string, any>} original - `values` from `/api/settings`
 * @param {Record<string, any>} current - what the form holds
 * @param {{secret?: string, removeSecret?: boolean}} secret
 */
export function collectChanges(original, current, { secret = '', removeSecret = false } = {}) {
  const changes = {};
  for (const f of FIELDS) {
    if (f.type === 'secret') { // never part of `current`: the form does not read it back
      if (removeSecret) changes[f.name] = '';
      else if (secret) changes[f.name] = secret;
    } else if (f.name in current && current[f.name] !== original[f.name]) {
      changes[f.name] = current[f.name];
    }
  }
  return changes;
}

/** "574 MB", "1,1 GB" (Spanish decimal comma). */
export function formatBytes(n) {
  if (!n || n < 0) return '0 MB';
  const mb = n / 1024 / 1024;
  if (mb >= 1024) return (mb / 1024).toFixed(1).replace('.', ',') + ' GB';
  return Math.max(1, Math.round(mb)) + ' MB';
}

/** Percentage 0-100 of a download; 0 when the total is unknown. */
export const percent = (done, total) => (total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0);

/** Text for the state of a model download (`/api/whisper/download`). */
export function describeDownload(s) {
  if (!s || s.state === 'idle') return '';
  if (s.state === 'running') {
    const pct = s.total ? ' (' + percent(s.done, s.total) + ' %)' : '';
    return 'Descargando ' + s.file + ': ' + formatBytes(s.done) + (s.total ? ' de ' + formatBytes(s.total) : '') + pct;
  }
  if (s.state === 'done') {
    return s.file + ' descargado' + (s.verified ? ' y verificado (SHA-256).' : '; no se pudo verificar la huella.');
  }
  if (s.state === 'cancelled') return 'Descarga cancelada.';
  return 'Error al descargar: ' + (s.error || 'desconocido');
}

/**
 * The result of "Comprobar" (`/api/settings/test/stt`) as a checklist.
 * @returns {Array<{ok: boolean, text: string}>}
 */
export function describeDiagnosis(d) {
  const rows = [
    { ok: !!d.ffmpeg, text: d.ffmpeg ? 'ffmpeg encontrado' : 'No se encuentra ffmpeg: hace falta para extraer el audio' },
    { ok: d.binary.found, text: d.binary.found ? 'whisper-server: ' + d.binary.path : 'No se encuentra whisper-server en «' + d.binary.path + '»' },
    d.model.found
      ? { ok: true, text: 'Modelo: ' + d.model.path + ' (' + formatBytes(d.model.bytes) + ')' }
      : { ok: false, text: d.model.path ? 'No se encuentra el modelo «' + d.model.path + '»' : 'Todavía no hay ningún modelo: descarga uno' },
    { ok: d.server_up || d.can_launch, text: d.server_up ? 'Hay un servidor Whisper respondiendo' : d.can_launch ? 'No hay servidor en marcha, pero se puede lanzar uno' : 'No hay servidor en marcha y no se puede lanzar uno' },
  ];
  return rows;
}
