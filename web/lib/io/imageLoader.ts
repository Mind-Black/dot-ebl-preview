/**
 * Image loader handling raw PNG bit-depth extraction as well as standard
 * raster web formats (BMP, JPEG, WebP) for legacy appearance interpretations.
 */

import { parsePng } from './pngParser';
import type { RawImageSource } from '../decoders/types';

export async function loadRawImage(
  file: File | Blob,
  filename = 'image.png'
): Promise<{ source: RawImageSource; isJpeg: boolean }> {
  const arrayBuffer = await file.arrayBuffer();
  const bytes = new Uint8Array(arrayBuffer);

  const isPng =
    bytes.length >= 8 &&
    bytes[0] === 0x89 &&
    bytes[1] === 0x50 &&
    bytes[2] === 0x4e &&
    bytes[3] === 0x47;

  const isJpeg =
    bytes.length >= 3 &&
    bytes[0] === 0xff &&
    bytes[1] === 0xd8 &&
    bytes[2] === 0xff;

  if (isPng) {
    const source = parsePng(bytes, filename);
    return { source, isJpeg: false };
  }

  // Fallback for BMP, JPEG, WebP via browser decoding
  if (typeof createImageBitmap !== 'undefined') {
    const bitmap = await createImageBitmap(new Blob([bytes]));
    const width = bitmap.width;
    const height = bitmap.height;

    // Use OffscreenCanvas if available, otherwise DOM canvas
    let ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D | null = null;
    if (typeof OffscreenCanvas !== 'undefined') {
      const canvas = new OffscreenCanvas(width, height);
      ctx = canvas.getContext('2d');
      if (ctx) ctx.drawImage(bitmap, 0, 0);
    } else if (typeof document !== 'undefined') {
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      ctx = canvas.getContext('2d');
      if (ctx) ctx.drawImage(bitmap, 0, 0);
    }

    if (!ctx) {
      throw new Error('Canvas context could not be created to decode raster image.');
    }

    const imgData = ctx.getImageData(0, 0, width, height);
    bitmap.close();
    const rgba = imgData.data;

    let hasAlpha = false;
    if (!isJpeg) {
      for (let src = 3; src < rgba.length; src += 4) {
        if (rgba[src] < 255) {
          hasAlpha = true;
          break;
        }
      }
    }

    if (hasAlpha) {
      const rgbaData = new Uint8Array(rgba.length);
      rgbaData.set(rgba);
      return {
        source: {
          width,
          height,
          channels: 4,
          bitDepth: 8,
          data: rgbaData,
          formatHint: 'raster',
          filename,
        },
        isJpeg: false,
      };
    }

    const rgbData = new Uint8Array(width * height * 3);
    let dst = 0;
    for (let src = 0; src < rgba.length; src += 4) {
      rgbData[dst++] = rgba[src];
      rgbData[dst++] = rgba[src + 1];
      rgbData[dst++] = rgba[src + 2];
    }

    return {
      source: {
        width,
        height,
        channels: 3,
        bitDepth: 8,
        data: rgbData,
        formatHint: isJpeg ? 'jpeg' : 'raster',
        filename,
      },
      isJpeg,
    };
  }

  throw new Error('Unsupported image format or runtime environment.');
}
