import { decodeDesign, computeParameterStats } from '../decoders';
import { loadRawImage } from '../io/imageLoader';
import { parseNpz } from '../io/npzParser';
import type { DesignModel, InterpretationFormat } from '../decoders/types';
import type { RgbaContinuousOptions } from '../decoders';
import type { RawImageSource } from '../decoders/types';
export interface DesignRequest {
    id: number;
    file?: File;
    source?: RawImageSource;
    format: InterpretationFormat;
    pitch: number;
    options: RgbaContinuousOptions;
}
let source: RawImageSource | null = null;
let physical: DesignModel | null = null;
self.onmessage = async ({ data: m }: {
    data: DesignRequest;
}) => {
    try {
        if (m.file) {
            physical = null;
            if (m.file.name.toLowerCase().endsWith('.npz')) {
                source = null;
                const design = physical = parseNpz(await m.file.arrayBuffer(), m.file.name);
                self.postMessage({ id: m.id, design, stats: computeParameterStats(design), physical: true });
                return;
            }
            source = (await loadRawImage(m.file, m.file.name)).source;
        }
        if (m.source)
            source = m.source;
        if (physical) {
            const design = { ...physical, pitchNm: m.pitch };
            self.postMessage({ id: m.id, design, stats: computeParameterStats(design), physical: true });
            return;
        }
        if (!source)
            throw Error('No image source');
        const design = decodeDesign(source, m.format, m.pitch, m.options);
        self.postMessage({ id: m.id, design, stats: computeParameterStats(design) });
    }
    catch (e) {
        self.postMessage({ id: m.id, error: String(e) });
    }
};
