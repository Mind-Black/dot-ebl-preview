import type { DesignRequest } from './designWorker';
import { decodeDesign, computeParameterStats, type RgbaContinuousOptions } from '../decoders';
import type { DesignModel, InterpretationFormat, ParameterStats, RawImageSource } from '../decoders/types';
export interface RgbaOptions extends RgbaContinuousOptions {
}
export type DesignListener = () => void;
export class DesignStore {
    private importError: string | null = null;
    private importing: Worker | null = null;
    private failedFile: File | null = null;
    private failedFormat: InterpretationFormat = 'RGBA continuous';
    private pendingFilename: string | null = null;
    getPendingFilename() { return this.pendingFilename; }
    canExport() { return !!this.design && !this.getIsProcessing() && !this.getError(); }
    retryImport() { if (this.failedFile) this.loadFile(this.failedFile, this.failedFormat); }
    private sourceRevision = 0;
    getSourceRevision() { return this.sourceRevision; }
    private resetWorker() { this.sourceRevision++; this.id++; this.pending = null; this.worker?.terminate(); this.worker = null; this.running = false; }
    private design: DesignModel | null = null;
    private source: RawImageSource | null = null;
    private format: InterpretationFormat = 'RGBA continuous';
    private pitch = 20000;
    private stats: ParameterStats | null = null;
    private error: string | null = null;
    private options: RgbaOptions = { minPeriodNm: 400, maxPeriodNm: 1600, minAngleDeg: -90, maxAngleDeg: 90, applyFilter: true };
    private listeners = new Set<DesignListener>();
    private worker: Worker | null = null;
    private id = 0;
    private running = false;
    private pending: DesignRequest | null = null;
    private physical = true;
    subscribe(f: DesignListener) { this.listeners.add(f); return () => this.listeners.delete(f); }
    private notify() { this.listeners.forEach(f => f()); }
    getDesign() { return this.design; }
    getSource() { return this.source; }
    getInterpretation() { return this.format; }
    getPitchNm() { return this.pitch; }
    getStats() { return this.stats; }
    getError() { return this.error ?? this.importError; }
    getIsProcessing() { return !!this.importing || this.running || !!this.pending; }
    getRgbaOptions() { return { ...this.options }; }
    clearError() { this.importError = null; this.error = null; this.notify(); }
    private submit(extra: Partial<DesignRequest> = {}) {
        if(this.importing) return;
        const m = { id: ++this.id, format: this.format, pitch: this.pitch, options: { ...this.options }, ...extra };
        this.error = null;
        if (typeof Worker === 'undefined' && this.source) {
            try {
                this.design = decodeDesign(this.source, this.format, this.pitch, this.options);
                this.stats = computeParameterStats(this.design);
            }
            catch (e) {
                this.error = String(e);
            }
            this.notify();
            return;
        }
        if (!this.worker) {
            const revision = this.sourceRevision;
            this.worker = new Worker(new URL('./designWorker.ts', import.meta.url), { type: 'module' });
            this.worker.onmessage = ({ data: r }) => { if (revision !== this.sourceRevision) return; this.running = false; if (!r.error || r.id === this.id) {
                if (r.error)
                    this.error = r.error;
                else {
                    this.design = r.design;
                    this.stats = r.stats;
                    if (r.physical) {
                        this.physical = true;
                        this.format = 'NPZ design';
                        if (this.pending) this.pending.format = 'NPZ design';
                        if (r.id === this.id) this.pitch = r.design.pitchNm;
                        else { this.design = { ...r.design, pitchNm: this.pitch }; this.stats = computeParameterStats(this.design!); }
                    }
                }
            } if (this.pending) {
                const next = this.pending;
                this.pending = null;
                this.running = true;
                this.worker!.postMessage(next);
            } this.notify(); };
            this.worker.onerror = () => { if (revision !== this.sourceRevision) return; this.error = 'Design worker failed; upload again to retry'; this.running = false; this.pending = null; this.worker?.terminate(); this.worker = null; this.notify(); };
        }
        if (this.running) {
            this.pending = { ...this.pending, ...m };
        }
        else {
            this.running = true;
            this.worker.postMessage(m);
        }
        this.notify();
    }
    loadFile(file: File, format: InterpretationFormat = 'RGBA continuous') {
        this.importing?.terminate();
        const candidate = new Worker(new URL('./designWorker.ts', import.meta.url), { type: 'module' });
        this.importing = candidate; this.pendingFilename = file.name; this.error = null; this.importError = null;
        this.failedFile = file; this.failedFormat = format;
        const fail = (reason: string) => {
            if (this.importing !== candidate) return;
            candidate.terminate(); this.importing = null; this.pendingFilename = null;
            this.importError = `Could not import ${file.name}: ${reason}. ${this.design ? 'Retained design: ' + this.design.sourceIdentity : 'No design is loaded'}. Retry or choose another file.`;
            this.notify();
        };
        candidate.onerror = () => fail('Design worker failed');
        candidate.onmessage = ({data:r}) => {
            if (this.importing !== candidate) return;
            if (r.error) { fail(r.error); return; }
            this.resetWorker(); this.importing = null; this.pendingFilename = null;
            this.worker = candidate; this.design = r.design; this.stats = r.stats;
            this.physical = !!r.physical; this.format = r.physical ? 'NPZ design' : format;
            this.pitch = r.design.pitchNm; this.source = null; this.error = null;
            this.failedFile = null; this.importError = null;
            const committedRevision=this.sourceRevision;
            candidate.onmessage = ({data:next}) => {
                if(this.worker!==candidate || committedRevision!==this.sourceRevision || next.id > this.id) return;
                this.running = false;
                if (next.error) this.error = next.error;
                else { this.design = next.design; this.stats = next.stats; }
                if (this.pending) { const pending = this.pending; this.pending = null; this.running = true; candidate.postMessage(pending); }
                this.notify();
            };
            candidate.onerror = () => { this.running = false; this.pending = null; this.error = 'Design worker failed; upload again to retry'; this.notify(); };
            this.notify();
        };
        candidate.postMessage({id:1,file,format,pitch:this.pitch,options:{...this.options}});
        this.notify();
    }
    loadSource(source: RawImageSource, format: InterpretationFormat, pitchNm?: number) { this.resetWorker(); this.source = source; this.physical = false; this.format = format; if (pitchNm)
        this.pitch = pitchNm; this.submit({ source }); }
    setRgbaOptions(o: Partial<RgbaOptions>) { if(this.importing)return; const next = { ...this.options, ...o }; if ((next.minPeriodNm ?? 400) >= (next.maxPeriodNm ?? 1600) || (next.minAngleDeg ?? -90) >= (next.maxAngleDeg ?? 90)) {
        this.error = 'Minimum must be less than maximum';
        this.notify();
        return;
    } this.options = next; if (!this.physical)
        this.submit();
    else
        this.notify(); }
    setInterpretation(f: InterpretationFormat) { if(this.importing)return; if (this.physical)
        return; this.format = f; this.submit(); }
    setPitchNm(n: number) { if(this.importing)return; if (!Number.isFinite(n) || n <= 0)
        return; this.pitch = Math.round(n); if (!this.physical || this.running)
        this.submit();
    else if (this.design) {
        this.design = { ...this.design, pitchNm: this.pitch };
        this.stats = computeParameterStats(this.design);
        this.notify();
    } }
    setPhysicalDesign(d: DesignModel) { this.importError = null; this.importing?.terminate(); this.importing = null; this.pendingFilename = null; this.resetWorker(); this.physical = true; this.source = null; this.design = d; this.pitch = d.pitchNm; this.stats = computeParameterStats(d); this.error = null; this.format = 'NPZ design'; this.notify(); }
}
export const designStore = new DesignStore();
