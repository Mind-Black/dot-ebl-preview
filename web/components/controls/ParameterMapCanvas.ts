/**
 * 2D Parameter Map inspector canvases for Period Map, Angle Map, and Source Image.
 */

import { designStore } from '../../lib/store/designStore';

export class ParameterMapCanvas {
  public readonly container: HTMLElement;
  private canvas: HTMLCanvasElement;
  private legendContainer: HTMLElement;
  private downloadBtn: HTMLButtonElement;
  private mode: 'periods' | 'angles' | 'source';

  constructor(mode: 'periods' | 'angles' | 'source') {
    this.mode = mode;
    this.container = document.createElement('div');
    this.container.className = `parameter-map-panel map-${mode}`;

    const header = document.createElement('div');
    header.className = 'panel-header';

    const title = document.createElement('h3');
    title.className = 'panel-title';
    title.textContent =
      mode === 'periods'
        ? 'Grating Period Map'
        : mode === 'angles'
        ? 'Rotation Angle Map'
        : 'Source Image / Input Data';

    this.downloadBtn = document.createElement('button');
    this.downloadBtn.className = 'btn btn-xs btn-outline';
    this.downloadBtn.textContent = 'Download PNG';
    this.downloadBtn.onclick = () => this.downloadMapPng();

    header.append(title, this.downloadBtn);

    const canvasWrapper = document.createElement('div');
    canvasWrapper.className = 'canvas-wrapper';

    this.canvas = document.createElement('canvas');
    this.canvas.className = 'map-canvas';
    canvasWrapper.appendChild(this.canvas);

    this.legendContainer = document.createElement('div');
    this.legendContainer.className = 'map-legend';

    this.container.append(header, canvasWrapper, this.legendContainer);

    designStore.subscribe(() => {
      this.render();
    });
  }

  public render(): void {
    const design = designStore.getDesign();
    const source = designStore.getSource();
    const ctx = this.canvas.getContext('2d');
    if (!ctx) return;

    if (!design) {
      this.canvas.width = 1;
      this.canvas.height = 1;
      ctx.clearRect(0, 0, 1, 1);
      this.legendContainer.innerHTML = '<span class="text-muted">No design loaded</span>';
      return;
    }

    const { width, height, periodNm, angleDeg, active } = design;
    this.canvas.width = width;
    this.canvas.height = height;

    const imgData = ctx.createImageData(width, height);
    const rgba = imgData.data;

    if (this.mode === 'source') {
      if (source && source.data) {
        let src = 0;
        let dst = 0;
        const is16 = source.bitDepth === 16;
        for (let i = 0; i < width * height; i++) {
          const r = is16 ? source.data[src++] >> 8 : source.data[src++];
          const g = is16 ? source.data[src++] >> 8 : source.data[src++];
          const b = is16 ? source.data[src++] >> 8 : source.data[src++];
          rgba[dst++] = r;
          rgba[dst++] = g;
          rgba[dst++] = b;
          rgba[dst++] = 255;
        }
        this.legendContainer.innerHTML = `
          <span>Source: <strong>${source.filename}</strong> (${source.bitDepth}-bit RGB)</span>
        `;
      } else {
        // Procedural / NPZ: no source image
        ctx.fillStyle = '#181818';
        ctx.fillRect(0, 0, width, height);
        this.legendContainer.innerHTML = `
          <span class="text-muted">Procedural / NPZ physical design — no raw RGB image imported</span>
        `;
        return;
      }
    } else if (this.mode === 'periods') {
      // Find min and max active periods
      let minP = Infinity;
      let maxP = -Infinity;
      let hasActive = false;

      for (let i = 0; i < width * height; i++) {
        if (active[i]) {
          hasActive = true;
          const p = periodNm[i];
          if (p < minP) minP = p;
          if (p > maxP) maxP = p;
        }
      }

      if (!hasActive) {
        minP = 900;
        maxP = 1200;
      }

      const pRange = maxP > minP ? maxP - minP : 1;

      let dst = 0;
      for (let i = 0; i < width * height; i++) {
        if (!active[i]) {
          // Dark gray inactive
          rgba[dst++] = 24;
          rgba[dst++] = 24;
          rgba[dst++] = 24;
          rgba[dst++] = 255;
        } else {
          // Blue-to-Red spectrum ramp: level in [0, 1]
          const level = (periodNm[i] - minP) / pRange;
          const r = Math.round(255 * level);
          const g = Math.round(100 + 110 * (1 - Math.abs(2 * level - 1)));
          const b = Math.round(255 * (1 - level));

          rgba[dst++] = Math.min(255, Math.max(0, r));
          rgba[dst++] = Math.min(255, Math.max(0, g));
          rgba[dst++] = Math.min(255, Math.max(0, b));
          rgba[dst++] = 255;
        }
      }

      this.legendContainer.innerHTML = `
        <div class="legend-bar period-gradient"></div>
        <div class="legend-labels">
          <span>${minP} nm</span>
          <span>${Math.round((minP + maxP) / 2)} nm</span>
          <span>${maxP} nm</span>
        </div>
      `;
    } else {
      // Angles Map: -90° to +90° axial hue wheel or blue-to-red
      let minA = Infinity;
      let maxA = -Infinity;
      let hasActive = false;

      for (let i = 0; i < width * height; i++) {
        if (active[i]) {
          hasActive = true;
          const a = angleDeg[i];
          if (a < minA) minA = a;
          if (a > maxA) maxA = a;
        }
      }

      if (!hasActive) {
        minA = -90;
        maxA = 90;
      }
      const aRange = maxA > minA ? maxA - minA : 1;

      let dst = 0;
      for (let i = 0; i < width * height; i++) {
        if (!active[i]) {
          rgba[dst++] = 24;
          rgba[dst++] = 24;
          rgba[dst++] = 24;
          rgba[dst++] = 255;
        } else {
          const level = (angleDeg[i] - minA) / aRange;
          // Cyclic or blue-to-red ramp
          const hue = (2.0 / 3.0) * (1.0 - level);
          const [r, g, b] = this.hueToRgb(hue);
          rgba[dst++] = r;
          rgba[dst++] = g;
          rgba[dst++] = b;
          rgba[dst++] = 255;
        }
      }

      this.legendContainer.innerHTML = `
        <div class="legend-bar angle-gradient"></div>
        <div class="legend-labels">
          <span>${minA.toFixed(1)}°</span>
          <span>${((minA + maxA) / 2).toFixed(1)}°</span>
          <span>${maxA.toFixed(1)}°</span>
        </div>
      `;
    }

    ctx.putImageData(imgData, 0, 0);
  }

  private hueToRgb(h: number): [number, number, number] {
    const sector = Math.floor(h * 6);
    const fraction = h * 6 - sector;
    const q = 1 - fraction;
    let r = 0, g = 0, b = 0;
    switch (sector % 6) {
      case 0: r = 1; g = fraction; b = 0; break;
      case 1: r = q; g = 1; b = 0; break;
      case 2: r = 0; g = 1; b = fraction; break;
      case 3: r = 0; g = q; b = 1; break;
      case 4: r = fraction; g = 0; b = 1; break;
      case 5: r = 1; g = 0; b = q; break;
    }
    return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
  }

  public downloadMapPng(): void {
    const design = designStore.getDesign();
    if (!design) return;

    const dataUrl = this.canvas.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = `${this.mode}_map_${design.width}x${design.height}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
}
