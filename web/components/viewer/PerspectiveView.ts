/**
 * 3D Perspective Surface View using Three.js.
 * Renders the physical hologram plane with optical diffraction texture,
 * synchronized observer/light orbital mechanics, and raycast cell picking.
 */

import * as THREE from 'three';
import {
  directionFromPosition,
  positionFromDirection,
} from '../../lib/optics/coordinates';
import {
  WebGlDiffractionRenderer,
  type RenderSceneParams,
} from '../../lib/optics/glRenderer';
import { designStore } from '../../lib/store/designStore';
import { sceneStore } from '../../lib/store/sceneStore';

export interface HoverCellInfo {
  row: number;
  col: number;
  xMm: number;
  yMm: number;
  periodNm: number;
  angleDeg: number;
  effectiveAngleDeg: number;
  active: boolean;
}

export class PerspectiveView {
  public readonly container: HTMLElement;
  private canvas: HTMLCanvasElement;
  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;

  private planeMesh: THREE.Mesh | null = null;
  private planeMaterial: THREE.MeshBasicMaterial | null = null;
  private opticalTexture: THREE.DataTexture | null = null;

  private diffractionRenderer: WebGlDiffractionRenderer;
  private offscreenCanvas: HTMLCanvasElement | OffscreenCanvas;

  private isDragging = false;
  private dragMode: 'camera' | 'light' = 'camera';
  private viewUp = new THREE.Vector3(0, 1, 0);
  private lastPointerX = 0;
  private lastPointerY = 0;

  private raycaster = new THREE.Raycaster();
  private mouse = new THREE.Vector2();

  private onHoverCallback?: (info: HoverCellInfo | null) => void;
  private animFrameId: number | null = null;
  private needsRender = true;
  private cleanups: (()=>void)[] = [];

  constructor(onHover?: (info: HoverCellInfo | null) => void) {
    this.onHoverCallback = onHover;

    this.container = document.createElement('div');
    this.container.className = 'perspective-viewport';

    this.canvas = document.createElement('canvas');
    this.canvas.className = 'perspective-canvas';
    this.container.appendChild(this.canvas);

    // Three.js renderer
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: false,
      preserveDrawingBuffer: true,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0e1117);

    // Camera tied to physical observer
    const camPos = sceneStore.getCameraPos();
    this.camera = new THREE.PerspectiveCamera(45, 1, 1, 5000);
    this.updateCameraTransform(camPos);

    // Offscreen optical diffraction generator
    if (typeof OffscreenCanvas !== 'undefined') {
      this.offscreenCanvas = new OffscreenCanvas(256, 256);
    } else {
      this.offscreenCanvas = document.createElement('canvas');
      this.offscreenCanvas.width = 256;
      this.offscreenCanvas.height = 256;
    }
    try { this.diffractionRenderer = new WebGlDiffractionRenderer(this.offscreenCanvas); } catch(e) { this.renderer.dispose(); throw e; }

    this.setupInteractions();
    this.setupSubscriptions();
    this.startRenderLoop();
  }

  private setupSubscriptions(): void {
    this.cleanups.push(designStore.subscribe(() => {
      this.updateMeshGeometry();
      this.needsRender = true;
    }));

    this.cleanups.push(sceneStore.subscribe(() => {
      const camPos = sceneStore.getCameraPos();
      this.updateCameraTransform(camPos);
      this.needsRender = true;
    }));

    // Resize observer
    const resizeObserver = new ResizeObserver(() => this.handleResize());
    resizeObserver.observe(this.container); this.cleanups.push(()=>resizeObserver.disconnect());
  }

  private updateCameraTransform(camPos: { x: number; y: number; z: number }): void {
    this.camera.position.set(camPos.x, camPos.y, camPos.z);

    // Trackball-style orientation: keep the previous up vector, projected perpendicular to the view
    // direction, so there is no pole singularity and the view may pass over the top (elevation > 90).
    const viewDir = new THREE.Vector3(camPos.x, camPos.y, camPos.z).normalize();
    const up = this.viewUp.clone().addScaledVector(viewDir, -this.viewUp.dot(viewDir));
    if (up.lengthSq() < 1e-8) {
      const dir = directionFromPosition(camPos);
      const azRad = (dir.azimuthDeg * Math.PI) / 180.0;
      const elRad = (dir.elevationDeg * Math.PI) / 180.0;
      up.set(-Math.sin(elRad) * Math.cos(azRad), -Math.sin(elRad) * Math.sin(azRad), Math.cos(elRad));
    }
    this.viewUp.copy(up.normalize());
    this.camera.up.copy(this.viewUp);
    this.camera.lookAt(0, 0, 0);
  }

  private handleResize(): void {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    if (width <= 0 || height <= 0) return;

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
    this.needsRender = true;
  }

  private updateMeshGeometry(): void {
    const design = designStore.getDesign();
    if (!design) {
      if (this.planeMesh) {
        this.scene.remove(this.planeMesh);
        this.planeMesh = null;
      }
      return;
    }

    const widthMm = (design.width * design.pitchNm) * 1e-6;
    const heightMm = (design.height * design.pitchNm) * 1e-6;

    if (this.planeMesh) {
      this.scene.remove(this.planeMesh);
      if (this.planeMesh.geometry) this.planeMesh.geometry.dispose();
      this.planeMesh = null;
    }

    const geometry = new THREE.PlaneGeometry(widthMm, heightMm);
    this.planeMaterial = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      side: THREE.DoubleSide,
    });
    this.planeMesh = new THREE.Mesh(geometry, this.planeMaterial);
    this.planeMesh.position.set(0, 0, 0);
    this.scene.add(this.planeMesh);

    // Initial texture allocation and view framing
    this.renderDiffractionTexture();
    this.fitView();
  }

  private renderDiffractionTexture(): void {
    const design = designStore.getDesign();
    if (!design) return;

    // For 3D perspective surface texture, always render at 1:1 design resolution
    // to prevent Three.js CanvasTexture quadrant-upload artifacts.
    const renderParams: RenderSceneParams = {
      ...sceneStore.getRenderParams(),
      downsampleFactor: 1.0,
    };

    // Render into the renderer's internal framebuffer and read pixels back into a
    // DataTexture (row 0 = bottom, matching plane UV origin). This avoids relying on
    // canvas-to-canvas texture copies, which can go stale.
    this.diffractionRenderer.render(design, renderParams);
    const pixels = this.diffractionRenderer.readPixelsRgba(design.width, design.height);

    if (
      !this.opticalTexture ||
      this.opticalTexture.image.width !== design.width ||
      this.opticalTexture.image.height !== design.height
    ) {
      if (this.opticalTexture) this.opticalTexture.dispose();
      this.opticalTexture = new THREE.DataTexture(
        pixels as Uint8Array<ArrayBuffer>,
        design.width,
        design.height,
        THREE.RGBAFormat,
        THREE.UnsignedByteType
      );
      this.opticalTexture.minFilter = THREE.NearestFilter;
      this.opticalTexture.magFilter = THREE.NearestFilter;
      this.opticalTexture.generateMipmaps = false;
      this.opticalTexture.colorSpace = THREE.SRGBColorSpace;
      this.opticalTexture.needsUpdate = true;
    } else {
      (this.opticalTexture.image.data as Uint8Array).set(pixels);
      this.opticalTexture.needsUpdate = true;
    }

    if (this.planeMaterial && this.planeMaterial.map !== this.opticalTexture) {
      this.planeMaterial.map = this.opticalTexture;
      this.planeMaterial.needsUpdate = true;
    }
  }

  private setupInteractions(): void {
    const canvas = this.canvas;

    canvas.addEventListener('contextmenu', (e) => e.preventDefault());

    canvas.addEventListener('pointerdown', (e) => {
      this.isDragging = true;
      this.lastPointerX = e.clientX;
      this.lastPointerY = e.clientY;

      // Right click or Shift+left = light orbit; Left click = camera orbit
      if (e.button === 2 || e.shiftKey) {
        this.dragMode = 'light';
      } else {
        this.dragMode = 'camera';
      }

      sceneStore.setIsInteracting(true);
      try {
        canvas.setPointerCapture(e.pointerId);
      } catch {
        // ignore in synthetic or touch environments
      }
    });

    canvas.addEventListener('pointermove', (e) => {
      if (this.isDragging) {
        const deltaX = e.clientX - this.lastPointerX;
        const deltaY = e.clientY - this.lastPointerY;
        this.lastPointerX = e.clientX;
        this.lastPointerY = e.clientY;

        const sensitivity = 0.5;

        if (this.dragMode === 'camera') {
          // Trackball orbit about the origin: yaw around the view-up axis, pitch around the view-right axis.
          const cam = sceneStore.getCameraPos();
          const p = new THREE.Vector3(cam.x, cam.y, cam.z);
          const u = this.viewUp.clone();
          const right = new THREE.Vector3().crossVectors(p.clone().negate().normalize(), u).normalize();
          const yaw = (-deltaX * sensitivity * Math.PI) / 180.0;
          const pitch = (deltaY * sensitivity * Math.PI) / 180.0;
          p.applyAxisAngle(u, yaw);
          right.applyAxisAngle(u, yaw);
          // Keep the camera in the top hemisphere (z > 0): shrink the pitch until it stays above the surface.
          const minZ = Math.sin((1.0 * Math.PI) / 180.0) * p.length();
          let scale = 1.0;
          let pitched = p.clone().applyAxisAngle(right, pitch);
          for (let i = 0; i < 8 && pitched.z < minZ; i++) {
            scale *= 0.5;
            pitched = p.clone().applyAxisAngle(right, pitch * scale);
          }
          if (pitched.z >= minZ) {
            p.copy(pitched);
            u.applyAxisAngle(right, pitch * scale);
          }
          if (p.z < minZ) p.z = minZ; // yaw never changes z, so this only guards the first frame
          this.viewUp.copy(u);
          sceneStore.setCameraPos({ x: p.x, y: p.y, z: p.z });
        } else {
          // Orbit primary light
          const light = sceneStore.getPrimaryLight();
          const dir = directionFromPosition(light.pos);
          let newAz = dir.azimuthDeg - deltaX * sensitivity;
          let newEl = dir.elevationDeg - deltaY * sensitivity;
          newEl = Math.max(1.0, Math.min(89.5, newEl));
          while (newAz < 0) newAz += 360;
          while (newAz >= 360) newAz -= 360;
          const newPos = positionFromDirection(newAz, newEl, dir.distanceMm);
          sceneStore.setPrimaryLight({ pos: newPos });
        }
      } else {
        // Raycast cell picking
        this.handlePointerHover(e);
      }
    });

    const endDrag = (e: PointerEvent) => {
      if (this.isDragging) {
        this.isDragging = false;
        sceneStore.setIsInteracting(false);
        try {
          canvas.releasePointerCapture(e.pointerId);
        } catch {
          // ignore
        }
        this.needsRender = true;
      }
    };

    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);

    canvas.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
        const zoomFactor = e.deltaY < 0 ? 0.9 : 1.1;

        if (e.shiftKey) {
          // Zoom primary light distance
          const light = sceneStore.getPrimaryLight();
          const dir = directionFromPosition(light.pos);
          const newDist = Math.max(10.0, Math.min(5000.0, dir.distanceMm * zoomFactor));
          const newPos = positionFromDirection(dir.azimuthDeg, dir.elevationDeg, newDist);
          sceneStore.setPrimaryLight({ pos: newPos });
        } else {
          // Zoom camera distance
          const cam = sceneStore.getCameraPos();
          const dir = directionFromPosition(cam);
          const newDist = Math.max(10.0, Math.min(5000.0, dir.distanceMm * zoomFactor));
          const newPos = positionFromDirection(dir.azimuthDeg, dir.elevationDeg, newDist);
          sceneStore.setCameraPos(newPos);
        }
      },
      { passive: false }
    );
  }

  private handlePointerHover(e: PointerEvent): void {
    if (!this.planeMesh || !this.onHoverCallback) return;

    const rect = this.canvas.getBoundingClientRect();
    this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObject(this.planeMesh);

    if (intersects.length > 0 && intersects[0].uv) {
      const uv = intersects[0].uv;
      const design = designStore.getDesign();
      if (!design) return;

      const col = Math.min(design.width - 1, Math.max(0, Math.floor(uv.x * design.width)));
      const row = Math.min(design.height - 1, Math.max(0, Math.floor((1.0 - uv.y) * design.height)));

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

  public fitView(): void {
    const design = designStore.getDesign();
    if (!design) return;

    const widthMm = (design.width * design.pitchNm) * 1e-6;
    const heightMm = (design.height * design.pitchNm) * 1e-6;
    const maxDim = Math.max(widthMm, heightMm);

    // Compute required FOV to frame design without changing observer distance
    const camPos = sceneStore.getCameraPos();
    const dist = Math.hypot(camPos.x, camPos.y, camPos.z);
    const requiredFov = 2.0 * Math.atan((maxDim * 0.75) / dist) * (180.0 / Math.PI);
    this.camera.fov = Math.max(0.05, Math.min(100, requiredFov));
    this.camera.updateProjectionMatrix();
    this.needsRender = true;
  }

  public captureSnapshot(): string {
    this.renderDiffractionTexture();
    this.renderer.render(this.scene, this.camera);
    return this.canvas.toDataURL('image/png');
  }

  private startRenderLoop(): void {
    const loop = () => {
      this.animFrameId = requestAnimationFrame(loop);

      if (this.needsRender || this.isDragging) {
        this.renderDiffractionTexture();
        this.renderer.render(this.scene, this.camera);
        if (!this.isDragging) {
          this.needsRender = false;
        }
      }
    };
    loop();
  }

  public dispose(): void {
    this.cleanups.forEach(f=>f());
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
    }
    this.diffractionRenderer.dispose();
    this.renderer.dispose();
  }
}
