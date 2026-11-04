/**
 * Flat 2D Optical Reference View.
 * Renders the full 2D diffraction color preview with aspect-correct framing,
 * pixel-accurate zoom/pan, cell inspection crosshairs, and export capture.
 */

import type { HoverCellInfo } from './PerspectiveView';
import { WebGlDiffractionRenderer } from '../../lib/optics/glRenderer';
import { designStore } from '../../lib/store/designStore';
import { sceneStore } from '../../lib/store/sceneStore';
import { directionFromPosition } from '../../lib/optics/coordinates';

export class FlatView {
  public readonly container: HTMLElement;
  private canvas: HTMLCanvasElement;
  private offscreenCanvas: HTMLCanvasElement;
  private diffractionRenderer: WebGlDiffractionRenderer | null = null;
  public get available() { return !!this.diffractionRenderer; }
  private selected = {row:0,col:0};
  private selectionOutput = document.createElement('output');
  private rowInput = document.createElement('input');
  private colInput = document.createElement('input');
  private selectedRevision = -1;
  private cleanups: (()=>void)[] = [];
  private selectCell(row: number, col: number) {
    const d=designStore.getDesign(); if(!d)return;
    this.selected={row:Math.max(0,Math.min(d.height-1,row)),col:Math.max(0,Math.min(d.width-1,col))};
    this.rowInput.max=String(d.height-1); this.colInput.max=String(d.width-1);
    this.rowInput.value=String(this.selected.row); this.colInput.value=String(this.selected.col);
    const i=this.selected.row*d.width+this.selected.col;
    this.selectionOutput.textContent=`Cell (${this.selected.row}, ${this.selected.col}): ${d.active[i]?'Active':'Inactive'}; x=${((this.selected.col+.5-d.width/2)*d.pitchNm*1e-6).toFixed(3)} mm; y=${(-(this.selected.row+.5-d.height/2)*d.pitchNm*1e-6).toFixed(3)} mm; Period ${d.periodNm[i]} nm; Stored ${d.angleDeg[i].toFixed(2)}°; Effective ${(d.angleDeg[i]+sceneStore.getOrientationDeg()).toFixed(2)}°`;
    this.requestRender();
  }

  private scale = 1.0;
  private panX = 0;
  private panY = 0;
  private isPanning = false;
  private lastPointerX = 0;
  private lastPointerY = 0;

  private rafId: number | null = null;
  private onHoverCallback?: (info: HoverCellInfo | null) => void;

  constructor(onHover?: (info: HoverCellInfo | null) => void) {
    this.onHoverCallback = onHover;

    this.container = document.createElement('div');
    this.container.className = 'flat-viewport';

    this.canvas = document.createElement('canvas');
    this.canvas.className = 'flat-canvas';
    this.container.appendChild(this.canvas);

    this.offscreenCanvas = document.createElement('canvas');
    const recovery=document.createElement('div'); recovery.className='preview-recovery'; recovery.setAttribute('role','status');
    const retry=document.createElement('button'); retry.className='btn'; retry.textContent='Retry preview';
    const initialize=()=>{try {this.diffractionRenderer=new WebGlDiffractionRenderer(this.offscreenCanvas); recovery.hidden=true; this.requestRender();} catch { recovery.hidden=false; }};
    recovery.append('Optical preview requires WebGL. Enable browser hardware acceleration or try a compatible browser. Parameter inspection and data exports remain available. ',retry);
    retry.onclick=initialize; this.container.append(recovery); initialize();
    const probe=document.createElement('div'); probe.className='cell-selection';
    for(const [name,input] of [['Row (zero-based)',this.rowInput],['Column (zero-based)',this.colInput]] as const){const label=document.createElement('label');label.textContent=name;input.type='number';input.min='0';input.value='0';label.append(input);probe.append(label);input.onchange=()=>this.selectCell(Number(this.rowInput.value)||0,Number(this.colInput.value)||0);}
    this.selectionOutput.setAttribute('aria-live','polite'); probe.append(this.selectionOutput); this.container.append(probe);
    this.canvas.tabIndex=0; this.canvas.setAttribute('aria-label','Optical preview. Arrow keys select cells');
    this.canvas.onkeydown=e=>{const delta:Record<string,[number,number]>={ArrowUp:[-1,0],ArrowDown:[1,0],ArrowLeft:[0,-1],ArrowRight:[0,1]}; if(delta[e.key]){e.preventDefault();this.selectCell(this.selected.row+delta[e.key][0],this.selected.col+delta[e.key][1]);}};
    let downX=0,downY=0;
    this.canvas.addEventListener('pointerdown',e=>{downX=e.clientX;downY=e.clientY;});
    this.canvas.addEventListener('pointerup',e=>{if(Math.hypot(e.clientX-downX,e.clientY-downY)>5)return; const rect=this.canvas.getBoundingClientRect();this.selectCell(Math.floor((e.clientY-rect.top-this.panY)/this.scale),Math.floor((e.clientX-rect.left-this.panX)/this.scale));});

    this.setupInteractions();
    this.setupSubscriptions();
  }

  private setupSubscriptions(): void {
    let revision = -1;
    let lastDesign = designStore.getDesign();
    this.cleanups.push(designStore.subscribe(() => {
      if (designStore.getDesign() !== lastDesign && revision !== designStore.getSourceRevision()) {
        revision = designStore.getSourceRevision();
        this.resetFit();
      }
      if (designStore.getDesign() !== lastDesign) {
        const revision=designStore.getSourceRevision();
        if(revision!==this.selectedRevision){this.selected={row:0,col:0};this.selectedRevision=revision;}
        this.selectCell(this.selected.row,this.selected.col);
      }
      lastDesign = designStore.getDesign();
      this.requestRender();
    }));

    this.cleanups.push(sceneStore.subscribe(() => {
      this.selectCell(this.selected.row,this.selected.col);
      this.requestRender();
    }));

    const resizeObserver = new ResizeObserver(() => {
      this.handleResize();
    });
    resizeObserver.observe(this.container);
    this.cleanups.push(()=>resizeObserver.disconnect());
  }

  public requestRender(): void {
    if (this.rafId !== null) return;
    this.rafId = requestAnimationFrame(() => {
      this.rafId = null;
      this.render();
    });
  }

  private handleResize(): void {
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    if (width <= 0 || height <= 0) return;

    this.canvas.width = width * Math.min(window.devicePixelRatio, 2);
    this.canvas.height = height * Math.min(window.devicePixelRatio, 2);
    this.render();
  }

  public resetFit(): void {
    const design = designStore.getDesign();
    if (!design) return;

    const contW = this.canvas.clientWidth || 400;
    const contH = this.canvas.clientHeight || 400;

    const scaleX = (contW * 0.9) / design.width;
    const scaleY = (contH * 0.9) / design.height;
    this.scale = Math.min(scaleX, scaleY);
    this.panX = (contW - design.width * this.scale) / 2;
    this.panY = (contH - design.height * this.scale) / 2;
    this.requestRender();
  }

  public render(): void {
    if (this.container.offsetParent === null && this.canvas.clientWidth === 0) {
      return;
    }

    const design = designStore.getDesign();
    if (!design) {
      const ctx = this.canvas.getContext('2d');
      if (ctx) ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      return;
    }

    // 1. Render diffraction optical colors to offscreen buffer
    const rawParams = sceneStore.getRenderParams();
    const camDist = Math.hypot(rawParams.cameraPos.x, rawParams.cameraPos.y, rawParams.cameraPos.z) || 300.0;
    const params = {
      ...rawParams,
      cameraPos: { x: 0.0, y: 0.0, z: camDist },
    };
    if (!this.diffractionRenderer) return;
    this.diffractionRenderer.render(design, params, this.offscreenCanvas);

    // 2. Draw offscreen buffer to visible canvas with pan and zoom
    const ctx = this.canvas.getContext('2d');
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio, 2);
    const contW = this.canvas.clientWidth;
    const contH = this.canvas.clientHeight;

    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#0e1117';
    ctx.fillRect(0, 0, contW, contH);

    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(
      this.offscreenCanvas,
      this.panX,
      this.panY,
      design.width * this.scale,
      design.height * this.scale
    );

    // Subtle outline around design boundaries
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
    ctx.lineWidth = 1;
    ctx.strokeRect(
      this.panX - 0.5,
      this.panY - 0.5,
      design.width * this.scale + 1,
      design.height * this.scale + 1
    );

    ctx.strokeStyle='#67e8f9'; ctx.lineWidth=2;
    ctx.strokeRect(this.panX+this.selected.col*this.scale,this.panY+this.selected.row*this.scale,this.scale,this.scale);
    this.renderLightIndicators(ctx, design);
    ctx.restore();
  }

  
  private renderLightIndicators(ctx: CanvasRenderingContext2D, design: import('../../lib/decoders/types').DesignModel): void {
    const cx = this.panX + design.width * this.scale * 0.5;
    const cy = this.panY + design.height * this.scale * 0.5;
    const orbitRadius = Math.max(design.width, design.height) * this.scale * 0.5 + 16;
    if (orbitRadius < 25) return;

    ctx.save();
    // Faint orbit ring guide
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 5]);
    ctx.beginPath();
    ctx.arc(cx, cy, orbitRadius, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);

    // Cardinal tick marks
    const cardinals = [
      { label: 'E', az: 0 },
      { label: 'N', az: 90 },
      { label: 'W', az: 180 },
      { label: 'S', az: 270 },
    ];
    ctx.font = '9px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
    for (const card of cardinals) {
      const rad = (card.az * Math.PI) / 180.0;
      const tx = cx + (orbitRadius - 10) * Math.cos(rad);
      const ty = cy - (orbitRadius - 10) * Math.sin(rad);
      ctx.fillText(card.label, tx, ty);
    }

    // Helper to draw a light badge
    const drawBadge = (azDeg: number, label: string, color: string, glowColor: string) => {
      const rad = (azDeg * Math.PI) / 180.0;
      const bx = cx + orbitRadius * Math.cos(rad);
      const by = cy - orbitRadius * Math.sin(rad);

      const innerX = cx + (orbitRadius - 8) * Math.cos(rad);
      const innerY = cy - (orbitRadius - 8) * Math.sin(rad);
      ctx.strokeStyle = glowColor;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(bx, by);
      ctx.lineTo(innerX, innerY);
      ctx.stroke();

      ctx.fillStyle = glowColor;
      ctx.beginPath();
      ctx.arc(bx, by, 11, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(bx, by, 9, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#0e1117';
      ctx.font = 'bold 9px sans-serif';
      ctx.fillText(label, bx, by + 0.5);
    };

    // Primary Light (L1 - Cyan)
    const pLight = sceneStore.getPrimaryLight();
    const pDir = directionFromPosition(pLight.pos);
    drawBadge(pDir.azimuthDeg, 'L1', '#38bdf8', 'rgba(56, 189, 248, 0.25)');

    // Secondary Fill Light (L2 - Amber, if enabled)
    if (sceneStore.isSecondaryLightEnabled()) {
      const sLight = sceneStore.getSecondaryLight();
      const sDir = directionFromPosition(sLight.pos);
      drawBadge(sDir.azimuthDeg, 'L2', '#fbbf24', 'rgba(251, 191, 36, 0.25)');
    }

    ctx.restore();
  }

  private setupInteractions(): void {
    const canvas = this.canvas;

    canvas.addEventListener('contextmenu', (e) => e.preventDefault());

    canvas.addEventListener('pointerdown', (e) => {
      this.isPanning = true;
      this.lastPointerX = e.clientX;
      this.lastPointerY = e.clientY;
      canvas.setPointerCapture(e.pointerId);
    });

    canvas.addEventListener('pointermove', (e) => {
      if (this.isPanning) {
        const deltaX = e.clientX - this.lastPointerX;
        const deltaY = e.clientY - this.lastPointerY;
        this.lastPointerX = e.clientX;
        this.lastPointerY = e.clientY;

        this.panX += deltaX;
        this.panY += deltaY;
        this.render();
      } else {
        this.handlePointerHover(e);
      }
    });

    const endPan = (e: PointerEvent) => {
      if (this.isPanning) {
        this.isPanning = false;
        try {
          canvas.releasePointerCapture(e.pointerId);
        } catch {
          // ignore
        }
      }
    };

    canvas.addEventListener('pointerup', endPan);
    canvas.addEventListener('pointercancel', endPan);

    canvas.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
        const design = designStore.getDesign();
        if (!design) return;

        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const zoomFactor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
        const newScale = Math.max(0.1, Math.min(100.0, this.scale * zoomFactor));

        // Zoom centered around mouse pointer
        this.panX = mouseX - (mouseX - this.panX) * (newScale / this.scale);
        this.panY = mouseY - (mouseY - this.panY) * (newScale / this.scale);
        this.scale = newScale;

        this.render();
      },
      { passive: false }
    );
  }

  private handlePointerHover(e: PointerEvent): void {
    if (!this.onHoverCallback) return;
    const design = designStore.getDesign();
    if (!design) {
      this.onHoverCallback(null);
      return;
    }

    const rect = this.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const col = Math.floor((mouseX - this.panX) / this.scale);
    const row = Math.floor((mouseY - this.panY) / this.scale);

    if (col >= 0 && col < design.width && row >= 0 && row < design.height) {
      const idx = row * design.width + col;
      const pitchMm = design.pitchNm * 1e-6;
      const xMm = (col + 0.5 - design.width / 2.0) * pitchMm;
      const yMm = -(row + 0.5 - design.height / 2.0) * pitchMm;

      const orientation = sceneStore.getOrientationDeg();

      this.onHoverCallback({
        row,
        col,
        xMm,
        yMm,
        periodNm: design.periodNm[idx],
        angleDeg: design.angleDeg[idx],
        effectiveAngleDeg: design.angleDeg[idx] + orientation,
        active: Boolean(design.active[idx]),
      });
    } else {
      this.onHoverCallback(null);
    }
  }

  public captureSnapshot(): string {
    const design = designStore.getDesign();
    if (!design || !this.available) return '';

    // Render exact 1:1 design resolution to export canvas
    const exportCanvas = document.createElement('canvas');
    exportCanvas.width = design.width;
    exportCanvas.height = design.height;

    const renderer = new WebGlDiffractionRenderer(exportCanvas);
    const rawParams = sceneStore.getRenderParams();
    const camDist = Math.hypot(rawParams.cameraPos.x, rawParams.cameraPos.y, rawParams.cameraPos.z) || 300.0;
    const params = {
      ...rawParams,
      cameraPos: { x: 0.0, y: 0.0, z: camDist },
      quality: 'high' as const, // Always export at High 77-band quality
      downsampleFactor: 1.0,
    };
    renderer.render(design, params, exportCanvas);
    const dataUrl = exportCanvas.toDataURL('image/png');
    renderer.dispose();
    return dataUrl;
  }

  public dispose(): void {
    this.cleanups.forEach(f=>f());
    if(this.rafId!==null) cancelAnimationFrame(this.rafId);
    this.diffractionRenderer?.dispose();
  }
}
