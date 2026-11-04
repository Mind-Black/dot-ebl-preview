import { describe, expect, it } from 'vitest';
import { directionFromPosition, positionFromDirection } from '@/lib/optics/coordinates';
import { sceneStore } from '@/lib/store/sceneStore';

describe('Secondary Fill Light and Multi-Illumination', () => {
  it('initializes secondary light at 55° elevation with visible default intensity', () => {
    const sec = sceneStore.getSecondaryLight();
    const dir = directionFromPosition(sec.pos);
    const normalizedAz = ((dir.azimuthDeg % 360) + 360) % 360;

    // Elevation must be 55° (standard oblique) rather than 35° so visible spectrum diffraction occurs
    expect(dir.elevationDeg).toBeCloseTo(55.0, 1);
    expect(normalizedAz).toBeCloseTo(0.0, 1);
    expect(sec.intensity).toBeGreaterThanOrEqual(0.8);
    expect(sec.sourceRadiusMm).toBeGreaterThanOrEqual(20.0);
  });

  it('toggles secondary light in render params', () => {
    sceneStore.setSecondaryLightEnabled(false);
    expect(sceneStore.getRenderParams().lights.length).toBe(1);

    sceneStore.setSecondaryLightEnabled(true);
    const params = sceneStore.getRenderParams();
    expect(params.lights.length).toBe(2);
    expect(params.lights[0].intensity).toBe(1.0);
    expect(params.lights[1].intensity).toBe(0.8);

    // Reset back to default
    sceneStore.setSecondaryLightEnabled(false);
  });

  it('keeps secondary fill light stationary when primary azimuth is swept', () => {
    sceneStore.setSecondaryLightEnabled(true);

    const initialSecPos = sceneStore.getSecondaryLight().pos;
    const initialSecDir = directionFromPosition(initialSecPos);

    // Simulate primary light sweep step
    const initialPrimaryPos = sceneStore.getPrimaryLight().pos;
    const initialPrimaryDir = directionFromPosition(initialPrimaryPos);

    const sweptPrimaryPos = positionFromDirection(
      (initialPrimaryDir.azimuthDeg + 45.0) % 360.0,
      initialPrimaryDir.elevationDeg,
      initialPrimaryDir.distanceMm
    );
    sceneStore.setPrimaryLight({ pos: sweptPrimaryPos });

    // Primary has moved
    const updatedPrimaryDir = directionFromPosition(sceneStore.getPrimaryLight().pos);
    const normPrimaryAz = ((updatedPrimaryDir.azimuthDeg % 360) + 360) % 360;
    const normExpectedAz = ((((initialPrimaryDir.azimuthDeg + 45.0) % 360) + 360) % 360);
    expect(normPrimaryAz).toBeCloseTo(normExpectedAz, 1);

    // Secondary fill light remains perfectly stationary
    const currentSecPos = sceneStore.getSecondaryLight().pos;
    const currentSecDir = directionFromPosition(currentSecPos);
    expect(currentSecDir.azimuthDeg).toBeCloseTo(initialSecDir.azimuthDeg, 1);
    expect(currentSecDir.elevationDeg).toBeCloseTo(initialSecDir.elevationDeg, 1);
    expect(currentSecDir.distanceMm).toBeCloseTo(initialSecDir.distanceMm, 1);

    // Clean up
    sceneStore.setSecondaryLightEnabled(false);
    sceneStore.setPrimaryLight({ pos: initialPrimaryPos });
  });

  it('supports diffraction order mode toggle (both vs single)', () => {
    expect(sceneStore.getDiffractionOrders()).toBe('both');
    expect(sceneStore.getRenderParams().diffractionOrders).toBe('both');

    sceneStore.setDiffractionOrders('single');
    expect(sceneStore.getDiffractionOrders()).toBe('single');
    expect(sceneStore.getRenderParams().diffractionOrders).toBe('single');

    // Reset back to both
    sceneStore.setDiffractionOrders('both');
  });
});
