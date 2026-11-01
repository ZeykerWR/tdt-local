// A link that opens the "Añadir canal" dialog already filled in (tools/capturar-directo.js makes them).
// Everything is in the fragment (#...), which the browser never sends to any server.

const MAX_URL = 4096;
const HEADERS = ['', 'atres'];

/**
 * What a `#add=<url>&name=…&kind=tv|radio&hdr=atres` fragment asks for, or `null` if it is not one or its
 * link is not http(s). It only fills the form in: nothing is added until the user presses the button.
 * @param {string} hash - `location.hash`
 * @returns {{url: string, name: string, kind: 'tv'|'radio', hdr: string} | null}
 */
export function parseAddLink(hash) {
  const params = new URLSearchParams(String(hash || '').replace(/^#/, ''));
  const url = (params.get('add') || '').trim();
  if (!url || url.length > MAX_URL || !/^https?:\/\/\S+$/.test(url)) return null;
  const hdr = params.get('hdr') || '';
  return {
    url,
    name: (params.get('name') || '').trim().slice(0, 80),
    kind: params.get('kind') === 'radio' ? 'radio' : 'tv',
    hdr: HEADERS.includes(hdr) ? hdr : '',
  };
}
