import { describe, expect, it } from 'vitest';
import { createConcentricTestPattern } from '@/lib/presets/sampleDesigns';
import { designStore } from '@/lib/store/designStore';
import { sceneStore } from '@/lib/store/sceneStore';

describe('Design and Scene State Stores', () => {
  it('updates design and computes parameter statistics correctly', () => {
    const design = createConcentricTestPattern(32);
    designStore.setPhysicalDesign(design);

    expect(designStore.getDesign()).toBe(design);
    const stats = designStore.getStats();
    expect(stats).not.toBeNull();
    if (!stats) return;

    expect(stats.totalCells).toBe(32 * 32);
    expect(stats.activeCells).toBeGreaterThan(0);
    expect(stats.fillFactor).toBeGreaterThan(0);
    expect(stats.fillFactor).toBeLessThanOrEqual(1.0);
    expect(stats.widthMm).toBeCloseTo(32 * 0.02, 4);
    expect(stats.heightMm).toBeCloseTo(32 * 0.02, 4);
    expect(stats.uniquePeriods.length).toBeGreaterThan(0);
  });

  it('updates holopixel pitch and synchronizes physical dimensions', () => {
    const design = createConcentricTestPattern(16);
    designStore.setPhysicalDesign(design);

    designStore.setPitchNm(60000); // 60 µm
    expect(designStore.getPitchNm()).toBe(60000);
    expect(designStore.getDesign()?.pitchNm).toBe(60000);

    const stats = designStore.getStats();
    expect(stats?.widthMm).toBeCloseTo(16 * 0.06, 4);
  });

  it('retains the previous valid design when a failed decoding occurs', () => {
    const initialDesign = createConcentricTestPattern(16);
    designStore.setPhysicalDesign(initialDesign);

    // Try loading corrupted raw source
    const corruptSource = {
      width: 2,
      height: 2,
      channels: 3,
      bitDepth: 8 as const,
      data: new Uint8Array([200, 0, 255, 200, 0, 255, 200, 0, 255, 200, 0, 255]), // R index beyond period LUT
      filename: 'corrupted.png',
    };

    designStore.loadSource(corruptSource, 'RGB8 indexed');
    expect(designStore.getError()).toMatch(/exceeds period LUT size/);
    // Previous design retained!
    expect(designStore.getDesign()).toBe(initialDesign);
  });

  it('manages scene illumination, camera coordinates, and quality toggle', () => {
    sceneStore.setCameraPos({ x: 10, y: 20, z: 250 });
    expect(sceneStore.getCameraPos()).toEqual({ x: 10, y: 20, z: 250 });

    sceneStore.setQuality('high');
    expect(sceneStore.getQuality()).toBe('high');

    sceneStore.setSecondaryLightEnabled(true);
    expect(sceneStore.isSecondaryLightEnabled()).toBe(true);
    const renderParams = sceneStore.getRenderParams();
    expect(renderParams.lights.length).toBe(2);

    sceneStore.setSecondaryLightEnabled(false);
    expect(sceneStore.getRenderParams().lights.length).toBe(1);

    sceneStore.setIsInteracting(true);
    expect(sceneStore.getRenderParams().downsampleFactor).toBe(0.5);

    sceneStore.setIsInteracting(false);
    expect(sceneStore.getRenderParams().downsampleFactor).toBe(1.0);

    sceneStore.setOrientationDeg(45.5);
    expect(sceneStore.getOrientationDeg()).toBe(45.5);
    expect(sceneStore.getRenderParams().orientationDeg).toBe(45.5);

    sceneStore.setApertureRadiusMm(4.5);
    expect(sceneStore.getApertureRadiusMm()).toBe(4.5);
    expect(sceneStore.getRenderParams().apertureRadiusMm).toBe(4.5);

    sceneStore.setPrimaryLight({ sourceRadiusMm: 35.0, intensity: 2.5 });
    expect(sceneStore.getPrimaryLight().sourceRadiusMm).toBe(35.0);
    expect(sceneStore.getPrimaryLight().intensity).toBe(2.5);
  });
});
