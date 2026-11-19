import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { before, describe, it } from 'node:test';

interface PngHeader {
  readonly widthPixels: number;
  readonly heightPixels: number;
  readonly bitDepth: number;
  readonly colorType: number;
  readonly chunkTypes: readonly string[];
}

interface PictureSize {
  readonly widthPixels: number;
  readonly heightPixels: number;
}

interface PictureColor {
  readonly colorType: number;
  readonly colorTypeName: string;
  readonly reason: string;
}

interface ManifestIcon {
  readonly src: string;
  readonly sizes: string;
  readonly type: string;
  readonly purpose: string;
}

interface Picture {
  readonly file: string;
  readonly href: string;
  readonly declaredSize: PictureSize;
  readonly color: PictureColor;
}

const WEB = new URL('./', import.meta.url);
const ICONS = new URL('static/icons/', WEB);

const PNG_SIGNATURE = Uint8Array.of(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a);
// The chunks of the image itself, those that .claude/skills/pull-request/scripts/pr_screenshots.py keeps.
const IMAGE_CHUNKS = new Set(['IHDR', 'PLTE', 'IDAT', 'IEND', 'tRNS', 'gAMA', 'cHRM', 'sRGB', 'sBIT', 'bKGD', 'pHYs']);
const MASKED_COLOR: PictureColor = {
  colorType: 2,
  colorTypeName: 'RGB',
  reason: 'a platform masks it, and a mask shows no transparency',
};
const UNMASKED_COLOR: PictureColor = {
  colorType: 6,
  colorTypeName: 'RGBA',
  reason: 'it shows on its own, and its rounded tile needs transparency',
};
const BITS_PER_CHANNEL = 8;

const readPngHeader = (bytes: Uint8Array): PngHeader => {
  if (!PNG_SIGNATURE.every((byte, index) => bytes[index] === byte)) {
    throw new Error('not a PNG: wrong signature');
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const chunkTypes = [];
  let offset = PNG_SIGNATURE.length;
  while (offset < bytes.length) {
    if (offset + 8 > bytes.length) {
      throw new Error('truncated chunk header');
    }
    const length = view.getUint32(offset);
    const type = String.fromCharCode(...bytes.subarray(offset + 4, offset + 8));
    if (offset + 12 + length > bytes.length) {
      throw new Error(`truncated ${type} chunk`);
    }
    chunkTypes.push(type);
    offset += 12 + length;
  }
  if (chunkTypes[0] !== 'IHDR') {
    throw new Error('the first chunk is not IHDR');
  }
  return {
    widthPixels: view.getUint32(16),
    heightPixels: view.getUint32(20),
    bitDepth: view.getUint8(24),
    colorType: view.getUint8(25),
    chunkTypes,
  };
};

const readMark = (source: string): string => {
  const mark = source.match(/<g id="mark">[\s\S]*?<\/g>/)?.[0];
  if (mark === undefined) {
    throw new Error('no <g id="mark"> group');
  }
  return mark.replace(/\s+/g, ' ');
};

const readSizes = (sizes: string): PictureSize => {
  const [widthPixels = Number.NaN, heightPixels = Number.NaN] = sizes.split('x').map(Number);
  return { widthPixels, heightPixels };
};

const readAttribute = (tag: string, name: string): string => {
  const attribute = tag.match(new RegExp(`\\s${name}="([^"]*)"`))?.[1];
  if (attribute === undefined) {
    throw new Error(`no ${name} in ${tag}`);
  }
  return attribute;
};

const readText = (field: string, value: unknown): string => {
  if (typeof value !== 'string') {
    throw new Error(`the manifest's ${field} is not a text`);
  }
  return value;
};

const readManifestIcons = (manifest: unknown): ManifestIcon[] => {
  const icons = typeof manifest === 'object' && manifest !== null ? Reflect.get(manifest, 'icons') : undefined;
  if (!Array.isArray(icons)) {
    throw new Error('the manifest lists no icons');
  }
  return icons.map((icon: unknown) => ({
    src: readText('src', Reflect.get(Object(icon), 'src')),
    sizes: readText('sizes', Reflect.get(Object(icon), 'sizes')),
    type: readText('type', Reflect.get(Object(icon), 'type')),
    purpose: readText('purpose', Reflect.get(Object(icon), 'purpose')),
  }));
};

const readAppleTouchLink = (page: string): string => {
  const link = page.match(/<link\s[^>]*rel="apple-touch-icon"[^>]*>/)?.[0];
  if (link === undefined) {
    throw new Error('no apple-touch-icon link in the template of the entry page');
  }
  return link;
};

const DRAWINGS = readdirSync(ICONS).filter((file) => file.endsWith('.svg'));

const MANIFEST_ICONS = readManifestIcons(JSON.parse(readFileSync(new URL('static/manifest.webmanifest', WEB), 'utf8')));
const APPLE_TOUCH_LINK = readAppleTouchLink(readFileSync(new URL('src/index.html', WEB), 'utf8'));

const PICTURES: readonly Picture[] = [
  ...MANIFEST_ICONS.filter((icon) => icon.type === 'image/png').map((icon) => ({
    href: icon.src,
    declaredSize: readSizes(icon.sizes),
    color: icon.purpose.split(' ').includes('maskable') ? MASKED_COLOR : UNMASKED_COLOR,
  })),
  {
    href: readAttribute(APPLE_TOUCH_LINK, 'href'),
    declaredSize: readSizes(readAttribute(APPLE_TOUCH_LINK, 'sizes')),
    color: MASKED_COLOR,
  },
].map((picture) => ({ ...picture, file: picture.href.split('/').at(-1) ?? '' }));

describe('The brand icons', () => {
  describe('When the page and the manifest list their icons', () => {
    const servedDrawings = ['icon.svg', 'favicon.svg'];
    const servedPictures = ['icon-192.png', 'icon-512.png', 'icon-maskable-512.png', 'apple-touch-icon.png'];

    it('should find every drawing the page serves, so that none escapes its checks', () => {
      assert.deepEqual(
        servedDrawings.filter((file) => !DRAWINGS.includes(file)),
        [],
      );
    });

    it("should find the manifest's pictures and the apple-touch icon, so that none escapes its checks", () => {
      const pictureFiles = PICTURES.map((picture) => picture.file);
      assert.deepEqual(
        servedPictures.filter((file) => !pictureFiles.includes(file)),
        [],
      );
    });
  });

  describe('The mark of favicon.svg', () => {
    let tabMark: string;
    let iconMark: string;
    before(() => {
      tabMark = readMark(readFileSync(new URL('favicon.svg', ICONS), 'utf8'));
      iconMark = readMark(readFileSync(new URL('icon.svg', ICONS), 'utf8'));
    });

    it('should be the mark of icon.svg, so that the tab, the page and the installed app show one drawing', () => {
      assert.equal(tabMark, iconMark);
      assert.ok(tabMark.split('<path').length - 1 > 0);
    });
  });

  for (const file of DRAWINGS) {
    describe(`The ${file} drawing`, () => {
      let source: string;
      before(() => {
        source = readFileSync(new URL(file, ICONS), 'utf8');
      });

      it('should paint with attributes only, never a style, since the Content Security Policy that comes with it refuses inline style', () => {
        assert.doesNotMatch(source, /<style\b|\sstyle\s*=/i);
      });
    });
  }

  for (const { file, href, declaredSize, color } of PICTURES) {
    describe(`The ${file} picture`, () => {
      let header: PngHeader;
      before(() => {
        header = readPngHeader(readFileSync(new URL(href.replace(/^\//, ''), WEB)));
      });

      it('should be as large as the page or the manifest declares it', () => {
        assert.deepEqual({ widthPixels: header.widthPixels, heightPixels: header.heightPixels }, declaredSize);
      });

      it(`should be ${color.colorTypeName}, since ${color.reason}`, () => {
        assert.equal(header.colorType, color.colorType);
      });

      it('should store 8 bits per channel, since more would weigh twice as much for nothing a screen shows', () => {
        assert.equal(header.bitDepth, BITS_PER_CHANNEL);
      });

      it('should hold only the chunks of the image, so that no text, time or color profile of the machine that drew it is published', () => {
        assert.deepEqual(
          header.chunkTypes.filter((type) => !IMAGE_CHUNKS.has(type)),
          [],
        );
      });
    });
  }
});
