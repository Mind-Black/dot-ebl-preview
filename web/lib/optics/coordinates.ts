/**
 * Coordinate transformations and physical scene math.
 * World units are in millimeters (mm).
 */

export interface Point3D {
  x: number;
  y: number;
  z: number;
}

export interface DirectionalCoords {
  azimuthDeg: number;
  elevationDeg: number;
  distanceMm: number;
}

export function positionFromDirection(
  azimuthDeg: number,
  elevationDeg: number,
  distanceMm: number
): Point3D {
  if (
    !Number.isFinite(azimuthDeg) ||
    !Number.isFinite(elevationDeg) ||
    !Number.isFinite(distanceMm)
  ) {
    throw new Error('Direction and distance must be finite numbers.');
  }
  if (distanceMm <= 0) {
    throw new Error('Distance must be positive.');
  }
  if (elevationDeg < -90 || elevationDeg > 180) {
    throw new Error('Elevation must be between -90° and +90°.');
  }

  const azimuthRad = (azimuthDeg * Math.PI) / 180.0;
  const elevationRad = (elevationDeg * Math.PI) / 180.0;

  const horizontal = distanceMm * Math.cos(elevationRad);
  return {
    x: horizontal * Math.cos(azimuthRad),
    y: horizontal * Math.sin(azimuthRad),
    z: distanceMm * Math.sin(elevationRad),
  };
}

export function directionFromPosition(pos: Point3D): DirectionalCoords {
  const { x, y, z } = pos;
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
    throw new Error('Position coordinates must be finite numbers.');
  }
  const horizontal = Math.hypot(x, y);
  const distanceMm = Math.hypot(horizontal, z);
  if (distanceMm <= 0) {
    throw new Error('Position must be away from the origin.');
  }

  let azimuthDeg = (Math.atan2(y, x) * 180.0) / Math.PI;
  if (horizontal < 1e-6) {
    azimuthDeg = 270.0;
  }
  const elevationDeg = (Math.atan2(z, horizontal) * 180.0) / Math.PI;

  return {
    azimuthDeg,
    elevationDeg,
    distanceMm,
  };
}

export function cellCenterMm(
  row: number,
  col: number,
  width: number,
  height: number,
  pitchNm: number
): Point3D {
  const pitchMm = pitchNm * 1e-6;
  return {
    x: (col + 0.5 - width / 2.0) * pitchMm,
    y: -(row + 0.5 - height / 2.0) * pitchMm,
    z: 0.0,
  };
}
