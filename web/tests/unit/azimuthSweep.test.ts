import { describe, it, expect } from 'vitest';
import { positionFromDirection, directionFromPosition } from '../../lib/optics/coordinates';

describe('Illumination Azimuth Sweep Kinematics', () => {
  it('advances azimuth proportionally to delta time and wraps cleanly at 360 degrees', () => {
    const sweepSpeed = 36.0; // deg per second
    let currentAz = 350.0;
    const dt = 0.5; // half second = +18 deg

    currentAz = (currentAz + sweepSpeed * dt) % 360.0;
    expect(currentAz).toBeCloseTo(8.0, 4);

    // Negative handling if stepping backward
    let negAz = -5.0 % 360.0;
    if (negAz < 0) negAz += 360.0;
    expect(negAz).toBe(355.0);
  });

  it('preserves elevation angle and distance during azimuth orbit', () => {
    const elevation = 55.0;
    const distance = 400.0;

    for (const az of [0, 45, 90, 135, 180, 225, 270, 315, 359.5]) {
      const pos = positionFromDirection(az, elevation, distance);
      const dir = directionFromPosition(pos);

      // Verify elevation is invariant
      expect(dir.elevationDeg).toBeCloseTo(elevation, 2);
      // Verify distance is invariant
      expect(dir.distanceMm).toBeCloseTo(distance, 2);
      // Verify reconstructed azimuth matches
      const reconstructedAz = ((dir.azimuthDeg % 360) + 360) % 360;
      expect(reconstructedAz).toBeCloseTo(az, 2);
    }
  });

  it('produces smooth continuous orbital vectors without singularities', () => {
    const elevation = 45.0;
    const distance = 300.0;
    let prevPos = positionFromDirection(0, elevation, distance);

    for (let az = 1; az <= 360; az += 1) {
      const pos = positionFromDirection(az % 360, elevation, distance);
      const stepDist = Math.hypot(pos.x - prevPos.x, pos.y - prevPos.y, pos.z - prevPos.z);
      // Distance per 1 degree step on a circle of radius R * cos(45) ~ 212 mm
      // 2 * pi * 212 / 360 ~ 3.7 mm per degree
      expect(stepDist).toBeGreaterThan(2.0);
      expect(stepDist).toBeLessThan(6.0);
      prevPos = pos;
    }
  });
});
