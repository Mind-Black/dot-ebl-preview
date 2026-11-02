/**
 * Client-side Python .npz design archive parser.
 * Unpacks design.npz files exported by Python dot-ebl-preview without external Python backends.
 */

import { unzipSync } from 'fflate';
import type { DesignModel } from '../decoders/types';

interface NpyHeader {
  descr: string;
  fortranOrder: boolean;
  shape: number[];
  dataOffset: number;
}

export function parseNpyHeader(bytes: Uint8Array): NpyHeader {
  if (bytes.length < 10) {
    throw new Error('NPY buffer too short.');
  }

  // Check magic \x93NUMPY
  const magic = [0x93, 0x4e, 0x55, 0x4d, 0x50, 0x59];
  for (let i = 0; i < 6; i++) {
    if (bytes[i] !== magic[i]) {
      throw new Error('Invalid NPY magic number.');
    }
  }

  const major = bytes[6];
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

  let headerLength = 0;
  let headerOffset = 10;
  if (major === 1) {
    headerLength = view.getUint16(8, true);
    headerOffset = 10;
  } else if (major >= 2) {
    headerLength = view.getUint32(8, true);
    headerOffset = 12;
  } else {
    throw new Error(`Unsupported NPY version: ${major}.${bytes[7]}`);
  }

  const headerStr = new TextDecoder('latin1').decode(
    bytes.subarray(headerOffset, headerOffset + headerLength)
  );

  // Parse header dict with regex
  const descrMatch = headerStr.match(/'descr':\s*'([^']+)'/);
  const fortranMatch = headerStr.match(/'fortran_order':\s*(True|False)/i);
  const shapeMatch = headerStr.match(/'shape':\s*\(([^)]*)\)/);

  if (!descrMatch || !fortranMatch || !shapeMatch) {
    throw new Error(`Failed to parse NPY header dictionary: ${headerStr}`);
  }

  const descr = descrMatch[1];
  const fortranOrder = fortranMatch[1].toLowerCase() === 'true';

  const shapeParts = shapeMatch[1]
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  const shape = shapeParts.map((s) => parseInt(s, 10));

  return {
    descr,
    fortranOrder,
    shape,
    dataOffset: headerOffset + headerLength,
  };
}

export function parseNpz(buffer: ArrayBuffer | Uint8Array, filename = 'design.npz'): DesignModel {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);

  let unzipped: Record<string, Uint8Array>;
  try {
    unzipped = unzipSync(bytes);
  } catch (err) {
    throw new Error(`Invalid NPZ archive. Could not unzip: ${err instanceof Error ? err.message : String(err)}`);
  }

  // Find files in archive
  function findEntry(baseName: string): Uint8Array | null {
    if (unzipped[baseName]) return unzipped[baseName];
    if (unzipped[`${baseName}.npy`]) return unzipped[`${baseName}.npy`];
    for (const key of Object.keys(unzipped)) {
      if (key === baseName || key === `${baseName}.npy` || key.endsWith(`/${baseName}.npy`)) {
        return unzipped[key];
      }
    }
    return null;
  }

  const periodEntry = findEntry('period_nm');
  const angleEntry = findEntry('angle_deg');
  const activeEntry = findEntry('active');

  if (!periodEntry || !angleEntry || !activeEntry) {
    throw new Error('Malformed design.npz: missing required arrays (period_nm, angle_deg, active).');
  }

  const periodHeader = parseNpyHeader(periodEntry);
  const angleHeader = parseNpyHeader(angleEntry);
  const activeHeader = parseNpyHeader(activeEntry);

  if (periodHeader.shape.length !== 2) {
    throw new Error(`Expected 2D period_nm array, got shape (${periodHeader.shape.join(', ')}).`);
  }
  const [height, width] = periodHeader.shape;
  if (width <= 0 || height <= 0) {
    throw new Error(`Invalid design dimensions in NPZ: ${width}x${height}.`);
  }

  if (angleHeader.shape[0] !== height || angleHeader.shape[1] !== width) {
    throw new Error(`Shape mismatch: period_nm is (${height}, ${width}) but angle_deg is (${angleHeader.shape.join(', ')}).`);
  }
  if (activeHeader.shape[0] !== height || activeHeader.shape[1] !== width) {
    throw new Error(`Shape mismatch: period_nm is (${height}, ${width}) but active is (${activeHeader.shape.join(', ')}).`);
  }

  for(const h of [periodHeader,angleHeader,activeHeader]) {
    if(h.fortranOrder || h.descr.startsWith('>')) throw Error('Unsupported NPY byte order or Fortran order');
  }
  if(!['<u4','=u4'].includes(periodHeader.descr) || !['<f8','<f4','=f8','=f4'].includes(angleHeader.descr) || !['|b1','|u1'].includes(activeHeader.descr)) throw Error('Unsupported array dtype');
  const totalCells = width * height;
  if(activeEntry.length-activeHeader.dataOffset!==totalCells)throw Error('Invalid activity array size');

  // Unpack period_nm (uint32)
  const periodDataView = new DataView(
    periodEntry.buffer,
    periodEntry.byteOffset + periodHeader.dataOffset,
    periodEntry.byteLength - periodHeader.dataOffset
  );
  const periodNm = new Uint32Array(totalCells);
  for (let i = 0; i < totalCells; i++) {
    periodNm[i] = periodDataView.getUint32(i * 4, true);
  }

  // Unpack angle_deg (float64 or float32)
  const angleDataView = new DataView(
    angleEntry.buffer,
    angleEntry.byteOffset + angleHeader.dataOffset,
    angleEntry.byteLength - angleHeader.dataOffset
  );
  const angleDeg = new Float64Array(totalCells);
  const isAngleFloat32 = angleHeader.descr.includes('f4');
  for (let i = 0; i < totalCells; i++) {
    angleDeg[i] = isAngleFloat32
      ? angleDataView.getFloat32(i * 4, true)
      : angleDataView.getFloat64(i * 8, true);
  }

  // Unpack active (bool / uint8)
  const activeRaw = activeEntry.subarray(activeHeader.dataOffset, activeHeader.dataOffset + totalCells);
  const active = new Uint8Array(totalCells);
  for (let i = 0; i < totalCells; i++) {
    active[i] = activeRaw[i] ? 1 : 0;
  }

  let pitchNm = 20000;
  let sourceIdentity = `npz:${filename}`;
  let metadata: Record<string, any> = {};
  const metadataEntry = findEntry('metadata_json');
  if (metadataEntry) {
    const h = parseNpyHeader(metadataEntry);
    const raw = metadataEntry.subarray(h.dataOffset);
    let str = '';
    if (h.descr.includes('U')) {
      const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
      for(let i=0;i+4<=raw.length;i+=4){const code=view.getUint32(i,!h.descr.startsWith('>'));if(code)str+=String.fromCodePoint(code);}
    } else if(h.descr.includes('S')) str=new TextDecoder().decode(raw).replace(/\0+$/, '');
    else throw Error('Unsupported metadata encoding');
    metadata=JSON.parse(str);
    pitchNm=metadata.pitch_nm;
    sourceIdentity=metadata.source_identity || sourceIdentity;
  }
  const regionMasks: Record<string, Uint8Array> = {};
  for(const key of metadata.region_mask_keys || []) {
    const entry=findEntry(`mask_${key}`); if(!entry)throw Error('Missing region mask');
    const h=parseNpyHeader(entry); regionMasks[key]=entry.slice(h.dataOffset);
  }
  // Unpack optional appearance_rgb (float32 HxWx3)
  let appearanceRgb: Float32Array | undefined;
  const appearanceEntry = findEntry('appearance_rgb');
  if (appearanceEntry) {
    try {
      const appHeader = parseNpyHeader(appearanceEntry);
      if (appHeader.shape.length === 3 && appHeader.shape[0] === height && appHeader.shape[1] === width && appHeader.shape[2] === 3) {
        const appView = new DataView(
          appearanceEntry.buffer,
          appearanceEntry.byteOffset + appHeader.dataOffset,
          totalCells * 3 * 4
        );
        appearanceRgb = new Float32Array(totalCells * 3);
        for (let i = 0; i < totalCells * 3; i++) {
          appearanceRgb[i] = appView.getFloat32(i * 4, true);
        }
      }
    } catch {
      throw new Error('Malformed optional NPZ array');
    }
  }

  // Unpack optional fallback_intensity (float32 HxW)
  let fallbackIntensity: Float32Array | undefined;
  const fallbackEntry = findEntry('fallback_intensity');
  if (fallbackEntry) {
    try {
      const fbHeader = parseNpyHeader(fallbackEntry);
      if (fbHeader.shape.length === 2 && fbHeader.shape[0] === height && fbHeader.shape[1] === width) {
        const fbView = new DataView(
          fallbackEntry.buffer,
          fallbackEntry.byteOffset + fbHeader.dataOffset,
          totalCells * 4
        );
        fallbackIntensity = new Float32Array(totalCells);
        for (let i = 0; i < totalCells; i++) {
          fallbackIntensity[i] = fbView.getFloat32(i * 4, true);
        }
      }
    } catch {
      throw new Error('Malformed optional NPZ array');
    }
  }

  if(!Number.isSafeInteger(pitchNm)||pitchNm<=0)throw Error('Invalid NPZ pitch');
  if(!Number.isInteger(metadata.layer??1)||(metadata.layer??1)<0||(metadata.layer??1)>63||!Number.isFinite(metadata.dose??1)||(metadata.dose??1)<0||(metadata.dose??1)>17797.5)throw Error('Invalid fabrication metadata');
  if(metadata.exposure_mode && metadata.exposure_mode!=='single_pixel_line')throw Error('Unsupported exposure mode');
  for(let i=0;i<totalCells;i++)if(!Number.isFinite(angleDeg[i])||(active[i]&&!periodNm[i]))throw Error('Invalid physical parameters');
  return {
    width,
    height,
    pitchNm,
    periodNm,
    angleDeg,
    active,
    appearanceRgb,
    fallbackIntensity,
    sourceIdentity,
    layer: metadata.layer ?? 1, dose: metadata.dose ?? 1, artifactMetadata: metadata, regionMasks,
  };
}
