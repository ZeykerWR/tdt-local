// YouTube links from the lists -> the official embedded player (no proxy, nothing is bypassed).

const CHANNEL_LIVE = /^https?:\/\/(?:www\.)?youtube\.com\/channel\/(UC[\w-]{22})\/live/i;
const VIDEO = [
  /^https?:\/\/(?:www\.|m\.)?youtube\.com\/(?:live|embed)\/([\w-]{11})/i,
  /^https?:\/\/youtu\.be\/([\w-]{11})/i,
  /^https?:\/\/(?:www\.|m\.)?youtube\.com\/watch\?(?:[^#]*&)?v=([\w-]{11})/i,
];

/** Embed URL for a YouTube link, or `null` if `url` is not one. */
export function ytEmbed(url) {
  const channel = CHANNEL_LIVE.exec(url);
  if (channel) return 'https://www.youtube-nocookie.com/embed/live_stream?channel=' + channel[1];
  for (const re of VIDEO) {
    const m = re.exec(url);
    if (m) return 'https://www.youtube-nocookie.com/embed/' + m[1];
  }
  return null;
}
