import type { DesignModel } from '../decoders/types';
import { roundHalfAwayFromZero as round } from '../decoders/rgbaContinuous';
export const sanitize = (s: string) => s.replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 32) || 'unnamed';
export interface Options {
    topName: string;
    layer: number;
    dose: number;
    centerOrigin: boolean;
}
export function excess64Encode(n: number): Uint8Array {
    const b = new Uint8Array(8);
    if (n === 0)
        return b;
    if (!Number.isFinite(n))
        throw Error('Non-finite GDS real');
    let m = Math.abs(n), e = 0;
    while (m >= 1) {
        m /= 16;
        e++;
    }
    while (m < 1 / 16) {
        m *= 16;
        e--;
    }
    if (e + 64 < 0 || e + 64 > 127)
        throw Error('GDS real overflow');
    b[0] = (e + 64) | (n < 0 ? 128 : 0);
    for (let k = 1; k < 8; k++) {
        m *= 256;
        b[k] = Math.floor(m);
        m -= b[k];
    }
    return b;
}
export function dfToDatatype(d: number) { if (!Number.isFinite(d) || d < 0 || d > 17797.5)
    throw Error('Dose must be 0–17797.5'); return d <= 30 ? round(d * 1000) : round(30000 + 2 * (round(d * 2) / 2 - 30)); }
export function chords(pitch: number, period: number) {
    const paths: number[][] = [];
    let skipped = 0;
    const r = pitch / 2, start = -r + period / 2;
    for (let k = Math.ceil((-r - start) / period); k <= Math.floor((r - start) / period); k++) {
        const y = start + k * period;
        if (Math.abs(y) > r)
            continue;
        const diff = r * r - y * y;
        if (diff < -1e-7)
            continue;
        const x = round(Math.sqrt(Math.max(0, diff)));
        if (!x) {
            skipped++;
            continue;
        }
        paths.push([-x, round(y), x, round(y)]);
    }
    return { paths, skipped };
}
export function plan(d: DesignModel, o: Options) {
    const n = d.width * d.height;
    if (!Number.isSafeInteger(n) || !Number.isInteger(d.width) || !Number.isInteger(d.height) || d.width <= 0 || d.height <= 0 || !Number.isSafeInteger(d.pitchNm) || d.pitchNm <= 0)
        throw Error('Invalid grid');
    if ([d.periodNm, d.angleDeg, d.active].some(a => a.length !== n))
        throw Error('Array length mismatch');
    if (!Number.isInteger(o.layer) || o.layer < 0 || o.layer > 63)
        throw Error('Layer must be 0–63');
    dfToDatatype(o.dose);
    const counts = new Map<number, number>();
    let activeCells = 0;
    const offset = [o.centerOrigin ? round(d.width * d.pitchNm / 2) : 0, o.centerOrigin ? round(-d.height * d.pitchNm / 2) : 0];
    for (let i = 0; i < n; i++) {
        if (!Number.isFinite(d.angleDeg[i]))
            throw Error('Non-finite angle');
        if (d.active[i] !== 0 && d.active[i] !== 1)
            throw Error('Invalid mask');
        if (d.active[i]) {
            if (!d.periodNm[i])
                throw Error('Active period must be positive');
            activeCells++;
            counts.set(d.periodNm[i], (counts.get(d.periodNm[i]) || 0) + 1);
        }
    }
    const cells = [...counts.keys()].sort((a, b) => a - b).map(period => ({ period, ...chords(d.pitchNm, period) }));
    if (cells.some(c => sanitize(o.topName) === `P_${c.period}`))
        throw Error('Top name collides with period structure');
    const check = (v: number) => { if (!Number.isSafeInteger(v) || v < -2147483648 || v > 2147483647)
        throw Error('Coordinate exceeds signed 32-bit range'); };
    for (const c of cells)
        for (const xy of c.paths)
            xy.forEach(check);
    for (let i = 0; i < n; i++)
        if (d.active[i]) {
            check(round((i % d.width + .5) * d.pitchNm) - offset[0]);
            check(round(-(Math.floor(i / d.width) + .5) * d.pitchNm) - offset[1]);
        }
    return { cells, offset, totalCells: n, activeCells, uniquePeriodsCount: cells.length, totalStripes: cells.reduce((s, c) => s + c.paths.length, 0), skippedDegenerateStripes: cells.reduce((s, c) => s + c.skipped, 0), placedStripes: cells.reduce((s, c) => s + c.paths.length * counts.get(c.period)!, 0), placedSkipped: cells.reduce((s, c) => s + c.skipped * counts.get(c.period)!, 0), widthMm: d.width * d.pitchNm / 1e6, heightMm: d.height * d.pitchNm / 1e6 };
}
export type Plan = ReturnType<typeof plan>;
export function writeGds(d: DesignModel, o: Options, p: Plan, date = new Date(), progress = (value: number) => { void value; }) {
    const chunks: Uint8Array[] = [];
    let buf = new Uint8Array(65536), used = 0;
    const put = (v: number) => { if (used === buf.length) {
        chunks.push(buf);
        buf = new Uint8Array(65536);
        used = 0;
    } buf[used++] = v; };
    const rec = (r: number, t: number, data: number[] | string = []) => {
        const size = typeof data === 'string' ? data.length : data.length * (t === 5 ? 8 : t === 3 ? 4 : 2);
        const len = 4 + size + (size % 2);
        if (len > 65534)
            throw Error('Record too large');
        put(len >> 8);
        put(len);
        put(r);
        put(t);
        if (typeof data === 'string') {
            for (const ch of data)
                put(ch.charCodeAt(0));
        }
        else
            for (const v of data) {
                if (t === 5) {
                    for (const b of excess64Encode(v))
                        put(b);
                }
                else {
                    const bytes = t === 3 ? 4 : 2;
                    for (let j = bytes - 1; j >= 0; j--)
                        put(v >>> (j * 8));
                }
            }
        if (size % 2)
            put(0);
    };
    const ts = [date.getFullYear(), date.getMonth() + 1, date.getDate(), date.getHours(), date.getMinutes(), date.getSeconds()];
    const times = [...ts, ...ts];
    rec(0, 2, [3]);
    rec(1, 2, times);
    rec(2, 6, sanitize(sanitize(o.topName) + '_LIB'));
    rec(3, 5, [1e-3, 1e-9]);
    for (const c of p.cells) {
        rec(5, 2, times);
        rec(6, 6, `P_${c.period}`);
        for (const xy of c.paths) {
            rec(9, 0);
            rec(13, 2, [o.layer]);
            rec(14, 2, [dfToDatatype(o.dose)]);
            rec(15, 3, [0]);
            rec(16, 3, xy);
            rec(17, 0);
        }
        rec(7, 0);
    }
    rec(5, 2, times);
    rec(6, 6, sanitize(o.topName));
    for (let i = 0; i < p.totalCells; i++) {
        if (d.active[i]) {
            rec(10, 0);
            rec(18, 6, `P_${d.periodNm[i]}`);
            if (d.angleDeg[i] !== 0) {
                rec(26, 1, [0]);
                rec(27, 5, [1]);
                rec(28, 5, [d.angleDeg[i]]);
            }
            rec(16, 3, [round((i % d.width + .5) * d.pitchNm) - p.offset[0], round(-(Math.floor(i / d.width) + .5) * d.pitchNm) - p.offset[1]]);
            rec(17, 0);
        }
        if (i % 16384 === 0)
            progress(i / p.totalCells);
    }
    rec(7, 0);
    rec(4, 0);
    chunks.push(buf.slice(0, used));
    progress(1);
    return new Blob(chunks as BlobPart[]);
}
