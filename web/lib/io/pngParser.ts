/**
 * Raw PNG parser preserving exact 8-bit and 16-bit RGB channel samples
 * without browser canvas color management, alpha premultiplication, or gamut conversion.
 */

import { unzlibSync } from 'fflate';
import type { RawImageSource } from '../decoders/types';

export function parsePng(buffer: ArrayBuffer | Uint8Array, filename = 'design.png'): RawImageSource {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);

  // 1. Validate PNG signature: \x89PNG\r\n\x1a\n
  const PNG_SIG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (bytes.length < 8) {
    throw new Error('File is too short to be a valid PNG image.');
  }
  for (let i = 0; i < 8; i++) {
    if (bytes[i] !== PNG_SIG[i]) {
      throw new Error('Invalid PNG signature. Please upload a valid PNG file.');
    }
  }

  let offset = 8;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  let compressionMethod = 0;
  let filterMethod = 0;
  let interlaceMethod = 0;

  const idatChunks: Uint8Array[] = [];

  while (offset + 8 <= bytes.length) {
    const chunkLength = view.getUint32(offset, false);
    offset += 4;
    const chunkType = String.fromCharCode(
      bytes[offset],
      bytes[offset + 1],
      bytes[offset + 2],
      bytes[offset + 3]
    );
    offset += 4;

    if (offset + chunkLength + 4 > bytes.length) {
      throw new Error(`Corrupted PNG: chunk '${chunkType}' extends beyond end of file.`);
    }

    const chunkData = bytes.subarray(offset, offset + chunkLength);
    offset += chunkLength + 4; // skip chunk data + 4 bytes CRC

    if (chunkType === 'IHDR') {
      if (chunkLength < 13) {
        throw new Error('Corrupted IHDR chunk in PNG.');
      }
      const ihdrView = new DataView(chunkData.buffer, chunkData.byteOffset, chunkData.byteLength);
      width = ihdrView.getUint32(0, false);
      height = ihdrView.getUint32(4, false);
      bitDepth = ihdrView.getUint8(8);
      colorType = ihdrView.getUint8(9);
      compressionMethod = ihdrView.getUint8(10);
      filterMethod = ihdrView.getUint8(11);
      interlaceMethod = ihdrView.getUint8(12);
    } else if (chunkType === 'IDAT') {
      idatChunks.push(chunkData);
    } else if (chunkType === 'acTL') {
      throw new Error('Animated PNG (APNG) is not supported for numeric parameter profiles.');
    } else if (chunkType === 'IEND') {
      break;
    }
  }

  // 2. Validate format constraints
  if (width <= 0 || height <= 0) {
    throw new Error(`Invalid PNG dimensions: ${width}x${height}.`);
  }
  // Cell count safety check (e.g. max 4096 x 4096)
  if (width > 4096 || height > 4096) {
    throw new Error(`Design dimensions ${width}x${height} exceed safe cell limit (max 4096 per axis).`);
  }

  if (colorType === 3) {
    throw new Error('Palette/Indexed-color PNG is not supported. Use truecolor RGB or RGBA PNG.');
  }
  if (colorType === 0) {
    throw new Error('Grayscale PNG is not supported for parameter profiles. Use truecolor RGB or RGBA PNG.');
  }
  if (colorType === 4) {
    throw new Error('Grayscale + Alpha PNG is not supported. Use truecolor RGB or RGBA PNG.');
  }
  if (colorType !== 2 && colorType !== 6) {
    throw new Error(`Unsupported PNG color type ${colorType}. Only Truecolor RGB (type 2) and RGBA (type 6) are supported.`);
  }

  if (bitDepth !== 8 && bitDepth !== 16) {
    throw new Error(`Unsupported PNG bit depth: ${bitDepth}-bit. Expected 8-bit or 16-bit RGB/RGBA.`);
  }
  if (compressionMethod !== 0 || filterMethod !== 0) {
    throw new Error('Unsupported PNG compression or filter method.');
  }
  if (interlaceMethod !== 0) {
    throw new Error('Adam7 interlaced PNG is not supported for raw parameter profiles. Please re-export as non-interlaced.');
  }

  // 3. Concatenate IDAT chunks and decompress zlib stream
  let totalIdatLength = 0;
  for (const c of idatChunks) totalIdatLength += c.length;
  const combinedIdat = new Uint8Array(totalIdatLength);
  let idatOffset = 0;
  for (const c of idatChunks) {
    combinedIdat.set(c, idatOffset);
    idatOffset += c.length;
  }

  let raw: Uint8Array;
  try {
    raw = unzlibSync(combinedIdat);
  } catch (err) {
    throw new Error(`Failed to decompress PNG image data: ${err instanceof Error ? err.message : String(err)}`);
  }

  // 4. Un-filter scanlines
  const channels = colorType === 6 ? 4 : 3;
  const bpp = bitDepth === 16 ? channels * 2 : channels;
  const stride = 1 + width * bpp;

  if (raw.length !== height * stride) {
    throw new Error(`Decompressed PNG byte size (${raw.length}) does not match expected scanline size (${height * stride}).`);
  }

  const prevRow = new Uint8Array(width * bpp);
  const curRow = new Uint8Array(width * bpp);

  if (bitDepth === 8) {
    const outData = new Uint8Array(width * height * channels);
    let outOffset = 0;

    for (let r = 0; r < height; r++) {
      const rowSlice = raw.subarray(r * stride, (r + 1) * stride);
      const filterType = rowSlice[0];
      const sliceData = rowSlice.subarray(1);

      switch (filterType) {
        case 0: // None
          curRow.set(sliceData);
          break;
        case 1: // Sub
          for (let i = 0; i < sliceData.length; i++) {
            const left = i >= bpp ? curRow[i - bpp] : 0;
            curRow[i] = (sliceData[i] + left) & 0xff;
          }
          break;
        case 2: // Up
          for (let i = 0; i < sliceData.length; i++) {
            curRow[i] = (sliceData[i] + prevRow[i]) & 0xff;
          }
          break;
        case 3: // Average
          for (let i = 0; i < sliceData.length; i++) {
            const left = i >= bpp ? curRow[i - bpp] : 0;
            const up = prevRow[i];
            curRow[i] = (sliceData[i] + ((left + up) >> 1)) & 0xff;
          }
          break;
        case 4: // Paeth
          for (let i = 0; i < sliceData.length; i++) {
            const a = i >= bpp ? curRow[i - bpp] : 0;
            const b = prevRow[i];
            const c = i >= bpp ? prevRow[i - bpp] : 0;
            const p = a + b - c;
            const pa = Math.abs(p - a);
            const pb = Math.abs(p - b);
            const pc = Math.abs(p - c);
            const pr = pa <= pb && pa <= pc ? a : (pb <= pc ? b : c);
            curRow[i] = (sliceData[i] + pr) & 0xff;
          }
          break;
        default:
          throw new Error(`Unsupported PNG filter type: ${filterType}`);
      }

      outData.set(curRow, outOffset);
      outOffset += curRow.length;
      prevRow.set(curRow);
    }

    return {
      width,
      height,
      channels,
      bitDepth: 8,
      data: outData,
      filename,
    };
  } else {
    // 16-bit RGB/RGBA: big-endian 2 bytes per channel sample
    const outData = new Uint16Array(width * height * channels);
    let sampleIdx = 0;

    for (let r = 0; r < height; r++) {
      const rowSlice = raw.subarray(r * stride, (r + 1) * stride);
      const filterType = rowSlice[0];
      const sliceData = rowSlice.subarray(1);

      switch (filterType) {
        case 0: // None
          curRow.set(sliceData);
          break;
        case 1: // Sub
          for (let i = 0; i < sliceData.length; i++) {
            const left = i >= bpp ? curRow[i - bpp] : 0;
            curRow[i] = (sliceData[i] + left) & 0xff;
          }
          break;
        case 2: // Up
          for (let i = 0; i < sliceData.length; i++) {
            curRow[i] = (sliceData[i] + prevRow[i]) & 0xff;
          }
          break;
        case 3: // Average
          for (let i = 0; i < sliceData.length; i++) {
            const left = i >= bpp ? curRow[i - bpp] : 0;
            const up = prevRow[i];
            curRow[i] = (sliceData[i] + ((left + up) >> 1)) & 0xff;
          }
          break;
        case 4: // Paeth
          for (let i = 0; i < sliceData.length; i++) {
            const a = i >= bpp ? curRow[i - bpp] : 0;
            const b = prevRow[i];
            const c = i >= bpp ? prevRow[i - bpp] : 0;
            const p = a + b - c;
            const pa = Math.abs(p - a);
            const pb = Math.abs(p - b);
            const pc = Math.abs(p - c);
            const pr = pa <= pb && pa <= pc ? a : (pb <= pc ? b : c);
            curRow[i] = (sliceData[i] + pr) & 0xff;
          }
          break;
        default:
          throw new Error(`Unsupported PNG filter type: ${filterType}`);
      }

      for (let i = 0; i < curRow.length; i += 2) {
        outData[sampleIdx++] = (curRow[i] << 8) | curRow[i + 1];
      }
      prevRow.set(curRow);
    }

    return {
      width,
      height,
      channels,
      bitDepth: 16,
      data: outData,
      filename,
    };
  }
}
