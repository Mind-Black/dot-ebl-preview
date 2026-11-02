import { zipSync, strToU8 } from 'fflate';
import type { DesignModel } from '../decoders/types';
import { sanitize, type Options, type Plan } from './engine';
export async function sha(bytes: Uint8Array) { return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes as BufferSource))].map(v => v.toString(16).padStart(2, '0')).join(''); }
function npy(data: Uint8Array, descr: string, shape: number[]) {
    let h = `{'descr': '${descr}', 'fortran_order': False, 'shape': (${shape.join(', ')}${shape.length === 1 ? ',' : ''}), }`;
    h += ' '.repeat((64 - (10 + h.length + 1) % 64) % 64) + '\n';
    const out = new Uint8Array(10 + h.length + data.length);
    out.set([147, 78, 85, 77, 80, 89, 1, 0]);
    new DataView(out.buffer).setUint16(8, h.length, true);
    out.set(strToU8(h), 10);
    out.set(data, 10 + h.length);
    return out;
}
export function writeNpz(d: DesignModel) {
    const shape = [d.height, d.width], entries: Record<string, Uint8Array> = {};
    const add = (key: string, a: ArrayBufferView, descr: string, s = shape) => { entries[key + '.npy'] = npy(new Uint8Array(a.buffer, a.byteOffset, a.byteLength), descr, s); };
    add('period_nm', d.periodNm, '<u4');
    add('angle_deg', d.angleDeg, '<f8');
    add('active', d.active, '|b1');
    if (d.appearanceRgb)
        add('appearance_rgb', d.appearanceRgb, '<f4', [...shape, 3]);
    if (d.fallbackIntensity)
        add('fallback_intensity', d.fallbackIntensity, '<f4');
    for (const [k, v] of Object.entries(d.regionMasks || {}))
        add('mask_' + k, v, '|b1');
    const meta = JSON.stringify({ ...d.artifactMetadata, shape, pitch_nm: d.pitchNm, layer: d.layer ?? 1, dose: d.dose ?? 1, exposure_mode: 'single_pixel_line', source_identity: d.sourceIdentity, region_mask_keys: Object.keys(d.regionMasks || {}), has_appearance: !!d.appearanceRgb, has_fallback: !!d.fallbackIntensity, operations: d.artifactMetadata?.operations ?? [] });
    const codes = Array.from(meta, c => c.codePointAt(0)!);
    const unicode = new Uint32Array(codes);
    entries['metadata_json.npy'] = npy(new Uint8Array(unicode.buffer), `<U${codes.length}`, [1]);
    return zipSync(entries);
}
export function matrices(d: DesignModel) { const rows = (angle: boolean) => { const out: string[] = []; for (let r = 0; r < d.height; r++) {
    const row: string[] = [];
    for (let c = 0; c < d.width; c++) {
        const i = r * d.width + c;
        row.push((d.active[i] ? (angle ? d.angleDeg[i] : d.periodNm[i] / 1000) : (angle ? -1000 : 0)).toFixed(6));
    }
    out.push(row.join(' '));
} return strToU8(out.join('\n') + '\n'); }; return { 'angles.txt': rows(true), 'gratings.txt': rows(false) }; }
function evenRound(n: number) { const f = Math.floor(n), r = n - f; return r === .5 ? (f % 2 === 0 ? f : f + 1) : Math.round(n); }
export async function designHash(d: DesignModel) {
    const parts: Uint8Array[] = [strToU8(`shape:(${d.height}, ${d.width})pitch_nm:${d.pitchNm}mode:single_pixel_linelayer:${d.layer ?? 1}dose:${(d.dose ?? 1).toFixed(6)}`), d.active, new Uint8Array(d.periodNm.buffer, d.periodNm.byteOffset, d.periodNm.byteLength)];
    const angles = Float64Array.from(d.angleDeg, n => { const v = evenRound(n * 1e6) / 1e6; return v === 0 && n < 0 ? -0 : v; });
    parts.push(new Uint8Array(angles.buffer));
    if (d.fallbackIntensity) {
        const f = Float32Array.from(d.fallbackIntensity, n => Math.fround(evenRound(Math.fround(n * 1e4)) / 1e4));
        parts.push(new Uint8Array(f.buffer));
    }
    const bytes = new Uint8Array(parts.reduce((s, p) => s + p.length, 0));
    let offset = 0;
    for (const p of parts) {
        bytes.set(p, offset);
        offset += p.length;
    }
    return sha(bytes);
}
export async function bundle(d: DesignModel, o: Options, p: Plan, gds: Blob) {
    const files: Record<string, Uint8Array> = { ...matrices(d), [sanitize(o.topName) + '.gds']: new Uint8Array(await gds.arrayBuffer()), 'design.npz': writeNpz({ ...d, layer: o.layer, dose: o.dose }) };
    const hashes: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(files))
        hashes[k] = { size_bytes: v.length, sha256: await sha(v) };
    const exportFingerprint = await sha(strToU8(JSON.stringify({ options: o, files: hashes })));
    const design_hash = await designHash({ ...d, layer: o.layer, dose: o.dose });
    const plan_hash = await sha(strToU8(design_hash + o.topName + `stripes:${p.totalStripes}:skipped:${p.skippedDegenerateStripes}`));
    const manifest = { design_hash, plan_hash, version: '1.0', timestamp: new Date().toISOString(), layout_name: sanitize(o.topName), total_cells: p.totalCells, active_cells: p.activeCells, total_stripes: p.totalStripes, skipped_degenerate_stripes: p.skippedDegenerateStripes, unique_periods_count: p.uniquePeriodsCount, files: hashes, status: 'COMPLETED', web: { version: 1, offset_nm: p.offset, grid_extents_nm: [-p.offset[0], d.width * d.pitchNm - p.offset[0], -d.height * d.pitchNm - p.offset[1], -p.offset[1]], placed_stripes: p.placedStripes, placed_skipped: p.placedSkipped, export_fingerprint: exportFingerprint } };
    files['manifest.json'] = strToU8(JSON.stringify(manifest, null, 2));
    return new Blob([zipSync(files) as BlobPart]);
}
