import type { DesignModel } from '../decoders/types';
import type { Options, Plan } from './engine';
import { plan, writeGds } from './engine';
import { bundle } from './bundle';
export type FabricationRequest = {
    id: number;
    type: 'VALIDATE';
    design: DesignModel;
    options: Options;
} | {
    id: number;
    type: 'GDS' | 'ZIP';
};
export type FabricationResponse = {
    id: number;
    type: 'VALIDATED';
    metrics: Omit<Plan, 'cells'>;
} | {
    id: number;
    type: 'PROGRESS';
    percent: number;
} | {
    id: number;
    type: 'COMPLETE';
    blob: Blob;
    kind: 'GDS' | 'ZIP';
} | {
    id: number;
    type: 'ERROR';
    message: string;
};
let d: DesignModel, o: Options, p: Plan, gds: Blob | undefined;
self.onmessage = async ({ data: m }: {
    data: FabricationRequest;
}) => { try {
    if (m.type === 'VALIDATE') {
        d = m.design;
        o = m.options;
        p = plan(d, o);
        const { cells, ...metrics } = p;
        self.postMessage({ id: m.id, type: 'VALIDATED', metrics });
        return;
    }
    if (!p)
        throw Error('Validate first');
    if (!gds)
        gds = writeGds(d, o, p, new Date(), percent => self.postMessage({ id: m.id, type: 'PROGRESS', percent }));
    const blob = m.type === 'ZIP' ? await bundle(d, o, p, gds) : gds;
    self.postMessage({ id: m.id, type: 'COMPLETE', blob, kind: m.type });
}
catch (e) {
    self.postMessage({ id: m.id, type: 'ERROR', message: String(e) });
} };
