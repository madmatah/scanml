/** Pairing: install the Android app, then pair it with this PC by QR code. */
import { api, links } from '../api.js';
import { icon } from '../components/icons.js';
import { errorState, loadingState } from '../components/states.js';
import { toast } from '../components/toast.js';
import { copyText } from '../lib/clipboard.js';
import { h, uniqueId } from '../lib/dom.js';
import { errorMessage, isAbort } from '../lib/errors.js';
import { quoted } from '../lib/format.js';
import { t, tNodes } from '../lib/i18n.js';

/** QR code image in a white frame (QR codes need a light quiet zone, even in dark mode). */
function qrCode(src, alt) {
  const image = h('img', { src, alt, width: 220, height: 220 });
  const frame = h('div', { class: 'qr-frame' }, image);
  image.addEventListener('error', () => {
    frame.replaceChildren(h('p', { class: 'qr-missing' }, t('QR code unavailable.')));
  });
  return frame;
}

/** Read-only value with a copy button (and an optional show/hide toggle for secrets). */
function copyField({ label, value, secret = false, copiedMessage }) {
  const id = uniqueId('copy-field');
  const input = h('input', {
    id, class: 'input input-mono', type: secret ? 'password' : 'text', value, readonly: true,
    autocomplete: 'off', spellcheck: 'false',
  });
  const copyButton = h('button', { type: 'button', class: 'btn', 'aria-label': t('Copy: {label}', { label }) },
    icon('copy'), h('span', { class: 'btn-label' }, t('Copy')));
  copyButton.addEventListener('click', async () => {
    const copied = await copyText(value);
    toast(copied ? copiedMessage : t('Could not copy: select the text by hand.'), {
      tone: copied ? 'success' : 'error',
    });
  });
  const controls = [input];
  if (secret) {
    const reveal = h('button', {
      type: 'button', class: 'btn btn-icon', 'aria-pressed': 'false', 'aria-label': t('Show token'),
    }, icon('eye'));
    reveal.addEventListener('click', () => {
      const visible = input.type === 'password';
      input.type = visible ? 'text' : 'password';
      reveal.setAttribute('aria-pressed', String(visible));
      reveal.setAttribute('aria-label', visible ? t('Hide token') : t('Show token'));
      reveal.replaceChildren(icon(visible ? 'eye-off' : 'eye'));
    });
    controls.push(reveal);
  }
  controls.push(copyButton);
  return h('div', { class: 'field' },
    h('label', { for: id }, label),
    h('div', { class: 'input-group' }, controls));
}

function installCard(pairing) {
  const body = pairing.apk_available
    ? [
      qrCode(links.apkQr, t('QR code of the Android app’s download link')),
      h('ol', { class: 'steps' },
        h('li', {}, tNodes('Scan this QR code with the phone’s camera to download {file}.', {
          file: h('strong', {}, 'scanmylib.apk'),
        })),
        h('li', {}, tNodes('Open the downloaded file. The first time, Android blocks the installation: tap {settings} '
          + 'and allow installing unknown apps ({unknownSources}) {thisBrowserOnly}, then go back and tap {install}.', {
          settings: h('strong', {}, t('Settings')),
          unknownSources: quoted(t('unknown sources')),
          thisBrowserOnly: h('strong', {}, t('for this browser only')),
          install: h('strong', {}, t('Install')),
        })),
        h('li', {}, t('Play Protect may report an unknown app: this is normal for an APK built on your PC.'))),
      h('div', { class: 'button-row' },
        h('a', { class: 'btn', href: links.apk, download: 'scanmylib.apk' }, icon('download'), t('Download the APK'))),
      h('p', { class: 'hint' },
        tNodes('Download address: {url}', { url: h('code', { class: 'path' }, pairing.apk_url) })),
    ]
    : [
      h('div', { class: 'notice' }, icon('alert'),
        h('p', {}, h('strong', {}, t('The APK is not available yet.')), ' ',
          tNodes('Build the Android app (the project’s {folder} folder), then reload this page.', {
            folder: h('code', {}, 'android/'),
          }))),
    ];
  return h('section', { class: 'card pairing-step', 'aria-labelledby': 'install-title' },
    h('h2', { id: 'install-title', class: 'card-title' },
      h('span', { class: 'step-number', 'aria-hidden': 'true' }, '1'), t('Install the Android app')),
    body);
}

/** The labels quoted here are those of the Android app's pairing screen. */
function pairCard(pairing) {
  return h('section', { class: 'card pairing-step', 'aria-labelledby': 'pair-title' },
    h('h2', { id: 'pair-title', class: 'card-title' },
      h('span', { class: 'step-number', 'aria-hidden': 'true' }, '2'), t('Pair the app with this PC')),
    qrCode(links.pairingQr, t('Pairing QR code: address of this PC and access token')),
    h('ol', { class: 'steps' },
      h('li', {}, tNodes('Open ScanMyLib on the phone: on the {screen} screen, tap {button}.', {
        screen: quoted(t('Pair with PC')),
        button: h('strong', {}, t('Scan the QR code')),
      })),
      h('li', {}, t('Point the phone at this QR code: the app saves the PC address and the access token.')),
      h('li', {}, t('The phone must be on the same Wi-Fi network as this PC (or connected through a VPN).'))),
    h('div', { class: 'notice notice-warn' }, icon('alert'),
      h('p', {}, t('This QR code and this token give access to your library: do not share them.'))),
    h('h3', { class: 'subsection-title' }, t('Manual entry')),
    h('p', { class: 'hint' }, t('Without a QR code reader, copy these two values into the app, then tap {button}.', {
      button: quoted(t('Test and pair')),
    })),
    copyField({ label: t('PC address'), value: pairing.url, copiedMessage: t('Address copied.') }),
    copyField({ label: t('Token'), value: pairing.token, secret: true, copiedMessage: t('Token copied.') }));
}

export function mountPairing(root, { signal, setTitle }) {
  setTitle(t('Pairing'));
  const content = h('div', { class: 'pairing-content' }, loadingState());
  root.replaceChildren(h('section', { class: 'view pairing' },
    h('header', { class: 'view-header' },
      h('div', { class: 'view-heading' },
        h('h1', { tabindex: '-1' }, t('Pair the phone')),
        h('p', { class: 'view-subtitle' }, t('Two steps: install the Android app, then pair it with this PC.')))),
    content));

  async function load() {
    content.replaceChildren(loadingState());
    try {
      const pairing = await api.pairing({ signal });
      content.replaceChildren(h('div', { class: 'pairing-grid' }, installCard(pairing), pairCard(pairing)));
    } catch (error) {
      if (isAbort(error)) return;
      content.replaceChildren(errorState({ message: errorMessage(error), onRetry: load }));
    }
  }
  load();
}
