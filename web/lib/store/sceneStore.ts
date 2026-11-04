/**
 * Optical scene, illumination parameters, quality toggle, and viewport interaction state.
 */

import type { Point3D } from '../optics/coordinates';
import type { LightSettings, RenderSceneParams } from '../optics/glRenderer';
import type { QualityLevel } from '../optics/tables';

export type SceneListener = () => void;

class SceneStore {
  private cameraPos: Point3D = { x: 0.0, y: 0.0, z: 300.0 };
  private apertureRadiusMm = 2.0;
  private orientationDeg = 0.0;
  private quality: QualityLevel = 'balanced';
  private diffractionOrders: 'both' | 'single' = 'both';

  private primaryLight: LightSettings = {
    pos: {
      x: 0.0,
      y: 400.0 * Math.sin((35.0 * Math.PI) / 180.0), // ~229.430573 mm (elevation 55°, zenith 35°)
      z: 400.0 * Math.cos((35.0 * Math.PI) / 180.0), // ~327.660818 mm
    },
    sourceRadiusMm: 20.0,
    intensity: 1.0,
  };

  private secondaryLightEnabled = false;
  private secondaryLight: LightSettings = {
    pos: {
      x: 400.0 * Math.cos((55.0 * Math.PI) / 180.0), // ~229.430574 mm (azimuth 0° East, elevation 55°)
      y: 0.0,
      z: 400.0 * Math.sin((55.0 * Math.PI) / 180.0), // ~327.660818 mm
    },
    sourceRadiusMm: 20.0,
    intensity: 0.8,
  };

  private isInteracting = false;
  private activeTab: 'periods' | 'angles' | 'source' | 'analytics' = 'periods';

  private listeners: Set<SceneListener> = new Set();

  public subscribe(listener: SceneListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }

  public getCameraPos(): Point3D {
    return { ...this.cameraPos };
  }

  public setCameraPos(pos: Point3D): void {
    this.cameraPos = { ...pos };
    this.notify();
  }

  public getApertureRadiusMm(): number {
    return this.apertureRadiusMm;
  }

  public setApertureRadiusMm(radius: number): void {
    if (radius < 0 || !Number.isFinite(radius)) return;
    this.apertureRadiusMm = radius;
    this.notify();
  }

  public getOrientationDeg(): number {
    return this.orientationDeg;
  }

  public setOrientationDeg(deg: number): void {
    if (!Number.isFinite(deg)) return;
    this.orientationDeg = deg;
    this.notify();
  }

  public getQuality(): QualityLevel {
    return this.quality;
  }

  public setQuality(quality: QualityLevel): void {
    if (this.quality === quality) return;
    this.quality = quality;
    this.notify();
  }

  public getPrimaryLight(): LightSettings {
    return { ...this.primaryLight, pos: { ...this.primaryLight.pos } };
  }

  public setPrimaryLight(light: Partial<LightSettings>): void {
    if (light.pos) this.primaryLight.pos = { ...light.pos };
    if (light.sourceRadiusMm !== undefined && light.sourceRadiusMm >= 0) {
      this.primaryLight.sourceRadiusMm = light.sourceRadiusMm;
    }
    if (light.intensity !== undefined && light.intensity >= 0) {
      this.primaryLight.intensity = light.intensity;
    }
    this.notify();
  }

  public isSecondaryLightEnabled(): boolean {
    return this.secondaryLightEnabled;
  }

  public setSecondaryLightEnabled(enabled: boolean): void {
    this.secondaryLightEnabled = enabled;
    this.notify();
  }

  public getSecondaryLight(): LightSettings {
    return { ...this.secondaryLight, pos: { ...this.secondaryLight.pos } };
  }

  public setSecondaryLight(light: Partial<LightSettings>): void {
    if (light.pos) this.secondaryLight.pos = { ...light.pos };
    if (light.sourceRadiusMm !== undefined && light.sourceRadiusMm >= 0) {
      this.secondaryLight.sourceRadiusMm = light.sourceRadiusMm;
    }
    if (light.intensity !== undefined && light.intensity >= 0) {
      this.secondaryLight.intensity = light.intensity;
    }
    this.notify();
  }

  public getIsInteracting(): boolean {
    return this.isInteracting;
  }

  public setIsInteracting(interacting: boolean): void {
    if (this.isInteracting === interacting) return;
    this.isInteracting = interacting;
    this.notify();
  }

  public getActiveTab(): 'periods' | 'angles' | 'source' | 'analytics' {
    return this.activeTab;
  }

  public getDiffractionOrders(): 'both' | 'single' {
    return this.diffractionOrders;
  }

  public setDiffractionOrders(orders: 'both' | 'single'): void {
    if (this.diffractionOrders === orders) return;
    this.diffractionOrders = orders;
    this.notify();
  }

  public setActiveTab(tab: 'periods' | 'angles' | 'source' | 'analytics'): void {
    this.activeTab = tab;
    this.notify();
  }

  public getRenderParams(): RenderSceneParams {
    const lights: LightSettings[] = [this.getPrimaryLight()];
    if (this.secondaryLightEnabled) {
      lights.push(this.getSecondaryLight());
    }
    return {
      cameraPos: this.getCameraPos(),
      apertureRadiusMm: this.apertureRadiusMm,
      orientationDeg: this.orientationDeg,
      lights,
      quality: this.quality,
      downsampleFactor: this.isInteracting ? 0.5 : 1.0,
      diffractionOrders: this.diffractionOrders,
    };
  }
}

export const sceneStore = new SceneStore();
