/**
 * CIE 1931 standard observer, D65 illuminant, and bulk nickel reflectance tables.
 * Ported from dot_ebl_preview.optics.tables.
 */

// 77 CIE 1931 2-degree observer samples (380 to 760 nm in 5 nm increments)
export const S2XYZ_77: [number, number, number][] = [
  [0.0014, 0.0, 0.0065],
  [0.0022, 0.0001, 0.0105],
  [0.0042, 0.0001, 0.0201],
  [0.0076, 0.0002, 0.0362],
  [0.0143, 0.0004, 0.0679],
  [0.0232, 0.0006, 0.1102],
  [0.0435, 0.0012, 0.2074],
  [0.0776, 0.0022, 0.3713],
  [0.1344, 0.004, 0.6456],
  [0.2148, 0.0073, 1.0391],
  [0.2839, 0.0116, 1.3856],
  [0.3285, 0.0168, 1.623],
  [0.3483, 0.023, 1.7471],
  [0.3481, 0.0298, 1.7826],
  [0.3362, 0.038, 1.7721],
  [0.3187, 0.048, 1.7441],
  [0.2908, 0.06, 1.6692],
  [0.2511, 0.0739, 1.5281],
  [0.1954, 0.091, 1.2876],
  [0.1421, 0.1126, 1.0419],
  [0.0956, 0.139, 0.813],
  [0.058, 0.1693, 0.6162],
  [0.032, 0.208, 0.4652],
  [0.0147, 0.2586, 0.3533],
  [0.0049, 0.323, 0.272],
  [0.0024, 0.4073, 0.2123],
  [0.0093, 0.503, 0.1582],
  [0.0291, 0.6082, 0.1117],
  [0.0633, 0.71, 0.0782],
  [0.1096, 0.7932, 0.0573],
  [0.1655, 0.862, 0.0422],
  [0.2257, 0.9149, 0.0298],
  [0.2904, 0.954, 0.0203],
  [0.3597, 0.9803, 0.0134],
  [0.4334, 0.995, 0.0087],
  [0.5121, 1.0, 0.0057],
  [0.5945, 0.995, 0.0039],
  [0.6784, 0.9786, 0.0027],
  [0.7621, 0.952, 0.0021],
  [0.8425, 0.9154, 0.0018],
  [0.9163, 0.87, 0.0017],
  [0.9786, 0.8163, 0.0014],
  [1.0263, 0.757, 0.0011],
  [1.0567, 0.6949, 0.001],
  [1.0622, 0.631, 0.0008],
  [1.0456, 0.5668, 0.0006],
  [1.0026, 0.503, 0.0003],
  [0.9384, 0.4412, 0.0002],
  [0.8544, 0.381, 0.0002],
  [0.7514, 0.321, 0.0001],
  [0.6424, 0.265, 0.0],
  [0.5419, 0.217, 0.0],
  [0.4479, 0.175, 0.0],
  [0.3608, 0.1382, 0.0],
  [0.2835, 0.107, 0.0],
  [0.2187, 0.0816, 0.0],
  [0.1649, 0.061, 0.0],
  [0.1212, 0.0446, 0.0],
  [0.0874, 0.032, 0.0],
  [0.0636, 0.0232, 0.0],
  [0.0468, 0.017, 0.0],
  [0.0329, 0.0119, 0.0],
  [0.0227, 0.0082, 0.0],
  [0.0158, 0.0057, 0.0],
  [0.0114, 0.0041, 0.0],
  [0.0081, 0.0029, 0.0],
  [0.0058, 0.0021, 0.0],
  [0.0041, 0.0015, 0.0],
  [0.0029, 0.001, 0.0],
  [0.002, 0.0007, 0.0],
  [0.0014, 0.0005, 0.0],
  [0.001, 0.0004, 0.0],
  [0.0007, 0.0002, 0.0],
  [0.0005, 0.0001, 0.0],
  [0.0003, 0.0001, 0.0],
  [0.0002, 0.0001, 0.0],
  [0.0002, 0.0, 0.0],
];

// CIE Standard Illuminant D65 relative spectral power distribution
export const STD_ILLUM_D65_77: number[] = [
  49.98, 52.31, 54.65, 68.7, 82.75, 87.12, 91.49, 92.46, 93.43, 90.06,
  86.68, 95.77, 104.86, 110.94, 117.01, 117.41, 117.81, 116.34, 114.86, 115.39,
  115.92, 112.37, 108.81, 109.08, 109.35, 108.58, 107.8, 106.3, 104.79, 106.24,
  107.69, 106.05, 104.41, 104.23, 104.05, 102.02, 100.0, 98.17, 96.33, 96.06,
  95.79, 92.24, 88.69, 89.35, 90.01, 89.8, 89.6, 88.65, 87.7, 85.49,
  83.29, 83.49, 83.7, 81.86, 80.03, 80.12, 80.21, 81.25, 82.28, 80.28,
  78.28, 74.0, 69.72, 70.67, 71.61, 72.98, 74.35, 67.98, 61.6, 65.74,
  69.89, 72.49, 75.09, 69.34, 63.59, 55.01, 46.52,
];

// Bulk nickel reflectance spectral table
export const REFL_NI_77: number[] = [
  0.458696774, 0.464232258, 0.4696, 0.4748, 0.48, 0.485625, 0.49125, 0.496637097, 0.501548387, 0.506459677,
  0.511529032, 0.516767742, 0.522006451, 0.527220968, 0.532403226, 0.537585484, 0.542629032, 0.546875, 0.551120968, 0.555366935,
  0.559903226, 0.564620968, 0.56933871, 0.574056452, 0.577903226, 0.581532258, 0.58516129, 0.588790322, 0.592225806, 0.595564516,
  0.598903226, 0.602241935, 0.605532258, 0.608592742, 0.611653226, 0.614713709, 0.617774193, 0.62071129, 0.623319355, 0.625927419,
  0.628535484, 0.631143549, 0.633751613, 0.636298387, 0.63883871, 0.641379032, 0.643919355, 0.646459677, 0.649, 0.650532258,
  0.652064516, 0.653596774, 0.655129032, 0.65666129, 0.658193548, 0.659718548, 0.661235484, 0.662752419, 0.664269355, 0.66578629,
  0.667303226, 0.668820161, 0.670191935, 0.671055645, 0.671919355, 0.672783064, 0.673646774, 0.674510484, 0.675374194, 0.676237903,
  0.677025806, 0.677245161, 0.677464516, 0.677683871, 0.677903226, 0.678122581, 0.678341935,
];

export interface SpectralConfig {
  numBands: number;
  wavelengthStepNm: number;
  wavelengthsNm: Float32Array;
  premultipliedXyz: Float32Array; // [numBands * 4] formatted for RGBA32F texture
  lightXyz: [number, number, number];
  lightY: number;
  whiteXy: [number, number];
}

function buildSpectralConfig(stepIndices: number[]): SpectralConfig {
  const numBands = stepIndices.length;
  const wavelengthsNm = new Float32Array(numBands);
  const premultipliedXyz = new Float32Array(numBands * 4); // RGBA for WebGL texture packing

  let sumX = 0;
  let sumY = 0;
  let sumZ = 0;

  for (let b = 0; b < numBands; b++) {
    const origIdx = stepIndices[b];
    const wl = 380.0 + origIdx * 5.0;
    wavelengthsNm[b] = wl;

    const s = S2XYZ_77[origIdx];
    const illum = STD_ILLUM_D65_77[origIdx];
    const refl = REFL_NI_77[origIdx];

    const px = s[0] * illum * refl;
    const py = s[1] * illum * refl;
    const pz = s[2] * illum * refl;

    premultipliedXyz[b * 4 + 0] = px;
    premultipliedXyz[b * 4 + 1] = py;
    premultipliedXyz[b * 4 + 2] = pz;
    premultipliedXyz[b * 4 + 3] = 1.0;

    sumX += px;
    sumY += py;
    sumZ += pz;
  }

  const totalSum = sumX + sumY + sumZ;
  const whiteXy: [number, number] = totalSum > 1e-9 ? [sumX / totalSum, sumY / totalSum] : [0.3127, 0.329];

  return {
    numBands,
    wavelengthStepNm: (wavelengthsNm[numBands - 1] - wavelengthsNm[0]) / (numBands - 1),
    wavelengthsNm,
    premultipliedXyz,
    lightXyz: [sumX, sumY, sumZ],
    lightY: sumY,
    whiteXy,
  };
}

// 1. High Quality: 77 spectral bands (5 nm intervals)
export const SPECTRAL_HIGH: SpectralConfig = buildSpectralConfig(
  Array.from({ length: 77 }, (_, i) => i)
);

// 2. Balanced Quality: 39 spectral bands (10 nm intervals)
export const SPECTRAL_BALANCED: SpectralConfig = buildSpectralConfig(
  Array.from({ length: 39 }, (_, i) => i * 2)
);

// 3. Performance Quality: 20 spectral bands / 19 intervals (20 nm intervals from 380 to 760 nm)
export const SPECTRAL_PERFORMANCE: SpectralConfig = buildSpectralConfig(
  Array.from({ length: 20 }, (_, i) => i * 4)
);

export type QualityLevel = 'high' | 'balanced' | 'performance';

export function getSpectralConfig(quality: QualityLevel): SpectralConfig {
  switch (quality) {
    case 'high':
      return SPECTRAL_HIGH;
    case 'balanced':
      return SPECTRAL_BALANCED;
    case 'performance':
      return SPECTRAL_PERFORMANCE;
  }
}
