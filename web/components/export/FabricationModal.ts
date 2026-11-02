import type { FabricationResponse } from '../../lib/raith/fabricationWorker';
import type { DesignModel } from '../../lib/decoders/types';
import { sanitize, type Options } from '../../lib/raith/engine';
export function openFabrication(d: DesignModel, o: Options) {
    const focus = document.activeElement as HTMLElement | null;
    const dialog = document.createElement('dialog');
    dialog.className = 'fabrication-dialog';
    const title = document.createElement('h2');
    title.id='fabrication-title'; dialog.setAttribute('aria-labelledby',title.id);
    title.textContent = 'EBL fabrication — reviewed snapshot';
    const status = document.createElement('pre');
    status.textContent = 'Validating geometry…';
    status.setAttribute('role','status');
    const progress = document.createElement('progress');
    progress.max = 1; progress.setAttribute('aria-label','Fabrication progress');
    let worker = new Worker(new URL('../../lib/raith/fabricationWorker.ts', import.meta.url), { type: 'module' });
    let id = 1;
    let closed = false;
    const buttons: HTMLButtonElement[] = [];
    const action = (label: string, fn: () => void) => { const b = document.createElement('button'); b.className = 'btn btn-primary'; b.textContent = label; b.onclick = fn; dialog.append(b); return b; };
    dialog.append(title, status, progress);
    for (const kind of ['GDS', 'ZIP'] as const) {
        const b = action('Generate ' + kind, () => { status.textContent='Generating '+kind+'…'; progress.removeAttribute('value'); buttons.forEach(b => b.disabled = true); worker.postMessage({ id: ++id, type: kind }); });
        b.disabled = true;
        buttons.push(b);
    }
    action('Close / Cancel', () => { closed=true; worker.terminate(); dialog.close(); });
    dialog.oncancel = () => {closed=true; worker.terminate();};
    dialog.onclose = () => { closed = true; worker.terminate(); dialog.remove(); focus?.focus(); };
    worker.onmessage = ({ data: r }: {
        data: FabricationResponse;
    }) => { if (closed || r.id !== id)
        return; if (r.type === 'VALIDATED') {
        progress.value=1;
        const m = r.metrics;
        status.textContent = `Pitch: ${d.pitchNm} nm\nApplied orientation: ${d.artifactMetadata?.appliedOrientationDeg ?? 0}°\nGrid cells: ${m.totalCells}\nActive cells: ${m.activeCells}\nUnique periods: ${m.uniquePeriodsCount}\nStored paths: ${m.totalStripes}\nPlaced exposures: ${m.placedStripes}\nSkipped stored / placed: ${m.skippedDegenerateStripes} / ${m.placedSkipped}\nGrid extents: ${m.widthMm} × ${m.heightMm} mm\nLayer: ${o.layer}; dose: ${o.dose}\nOrigin offset (nm): ${m.offset.join(', ')}\nSoftware validated; hardware qualification separate.`;
        buttons.forEach(b => b.disabled = false);
    }
    else if (r.type === 'PROGRESS') {
        progress.value = r.percent;
    }
    else if (r.type === 'ERROR') {
        status.textContent = 'Failed: '+r.message; progress.value=0;
    }
    else {
        status.textContent='Completed '+r.kind+' download'; progress.value=1; buttons.forEach(b => b.disabled = false);
        const a = document.createElement('a');
        const url = URL.createObjectURL(r.blob);
        a.href = url;
        a.download = sanitize(o.topName) + (r.kind === 'ZIP' ? '_bundle.zip' : '.gds');
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    } };
    worker.onerror = () => { status.textContent = 'Fabrication worker failed. Use Retry to revalidate this snapshot.'; progress.value=0; buttons.forEach(b=>b.disabled=true); };
    action('Retry', () => { worker.terminate(); worker = new Worker(new URL('../../lib/raith/fabricationWorker.ts', import.meta.url), {type:'module'}); worker.onmessage=handleMessage; worker.onerror=handleError; status.textContent='Validating geometry…'; progress.removeAttribute('value'); buttons.forEach(b=>b.disabled=true); worker.postMessage({id:++id,type:'VALIDATE',design:structuredClone(d),options:o}); });
    const handleMessage=worker.onmessage; const handleError=worker.onerror;
    document.body.append(dialog);
    dialog.showModal();
    const snapshot = structuredClone(d);
    worker.postMessage({ id, type: 'VALIDATE', design: snapshot, options: o }, [snapshot.periodNm.buffer, snapshot.angleDeg.buffer, snapshot.active.buffer]);
}
