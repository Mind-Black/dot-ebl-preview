import type { DesignModel } from '../decoders/types';

export function fabricationSnapshot(design: DesignModel, orientationDeg: number): DesignModel {
    const snapshot = structuredClone(design);
    snapshot.angleDeg = Float64Array.from(design.angleDeg, angle => angle + orientationDeg);
    snapshot.artifactMetadata = { ...snapshot.artifactMetadata, appliedOrientationDeg: orientationDeg };
    return snapshot;
}
