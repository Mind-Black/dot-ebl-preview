/**
 * Scene controls: primary/secondary light sources and physical observer (camera) settings.
 */

import { directionFromPosition, positionFromDirection } from '../../lib/optics/coordinates';
import { sceneStore } from '../../lib/store/sceneStore';
import { createSliderControl, type SliderControl } from './sliderControl';

export class SceneControls {
  public readonly element: HTMLElement;
  private primaryAzControl: SliderControl;
  private primaryElControl: SliderControl;
  private primaryDistControl: SliderControl;
  private primaryRadiusControl: SliderControl;
  private primaryIntensityControl: SliderControl;
  private sweepBtn: HTMLButtonElement;
  private isSweeping = false;
  private btnBothOrders!: HTMLButtonElement;
  private btnSingleOrder!: HTMLButtonElement;
  private sweepRafId: number | null = null;
  private lastSweepTime = 0;
  private sweepSpeedDegPerSec = 36.0;

  private secLightCheck: HTMLInputElement;
  private secLightFields: HTMLElement;
  private secAzControl: SliderControl;
  private secElControl: SliderControl;
  private secDistControl: SliderControl;
  private secRadiusControl: SliderControl;
  private secIntensityControl: SliderControl;
  private camAzControl: SliderControl;
  private camElControl: SliderControl;
  private camDistControl: SliderControl;
  private camApertureControl: SliderControl;
  private isDraggingSlider = false;

  constructor() {
    this.element = document.createElement('section');
    this.element.className = 'controls-section scene-controls';

    const title = document.createElement('h2');
    title.className = 'section-title';
    title.textContent = 'Illumination & Observer';
    this.element.appendChild(title);

    const onInteractingChange = (interacting: boolean): void => {
      this.isDraggingSlider = interacting;
      sceneStore.setIsInteracting(interacting);
    };

    // Primary light
    const primaryGroup = document.createElement('div');
    primaryGroup.className = 'control-subgroup';

    const primaryHeader = document.createElement('h3');
    primaryHeader.className = 'subgroup-title';
    primaryHeader.textContent = 'Primary Light Source';
    primaryGroup.appendChild(primaryHeader);

    const presetRow = document.createElement('div');
    presetRow.className = 'btn-group w-full mb-3';

    const presets = [
      { name: 'Overhead', az: 90, el: 89.9, dist: 400 },
      { name: 'Standard Oblique', az: 90, el: 55, dist: 400 },
      { name: '45° Oblique', az: 90, el: 45, dist: 400 },
      { name: 'Grazing', az: 90, el: 15, dist: 400 },
    ];
    for (const preset of presets) {
      const btn = document.createElement('button');
      btn.className = 'btn btn-xs btn-outline';
      btn.textContent = preset.name;
      btn.onclick = () => {
        const pos = positionFromDirection(preset.az, preset.el, preset.dist);
        sceneStore.setPrimaryLight({ pos });
      };
      presetRow.appendChild(btn);
    }
    primaryGroup.appendChild(presetRow);

    // Auto-Sweep Azimuth Toggle
    const sweepRow = document.createElement('div');
    sweepRow.className = 'sweep-control-row mb-3';

    this.sweepBtn = document.createElement('button');
    this.sweepBtn.className = 'btn btn-xs btn-outline btn-sweep-toggle w-full';
    this.sweepBtn.id = 'btn-sweep-azimuth';
    this.sweepBtn.setAttribute('aria-label', 'Toggle auto sweep azimuth');
    this.sweepBtn.innerHTML = `
      <svg class="sweep-icon mr-1" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="5 3 19 12 5 21 5 3"/>
      </svg>
      <span>Auto Sweep Azimuth</span>
    `;
    this.sweepBtn.onclick = () => this.toggleSweep();
    sweepRow.appendChild(this.sweepBtn);
    primaryGroup.appendChild(sweepRow);

    this.primaryAzControl = createSliderControl({
      label: 'Light Azimuth',
      min: 0,
      max: 360,
      step: 0.5,
      initialVal: 90,
      unit: '°',
      decimals: 1,
      onChange: () => this.updatePrimarySpherical(),
      onInteractingChange,
    });

    this.primaryElControl = createSliderControl({
      label: 'Light Elevation',
      min: 1,
      max: 89,
      step: 0.5,
      initialVal: 55,
      unit: '°',
      decimals: 1,
      onChange: () => this.updatePrimarySpherical(),
      onInteractingChange,
    });

    this.primaryDistControl = createSliderControl({
      label: 'Light Distance',
      min: 10,
      max: 2000,
      numberMax: 5000,
      step: 5,
      initialVal: 400,
      unit: ' mm',
      decimals: 0,
      onChange: () => this.updatePrimarySpherical(),
      onInteractingChange,
    });

    this.primaryRadiusControl = createSliderControl({
      label: 'Source Radius',
      min: 0,
      max: 100,
      step: 1,
      initialVal: 20,
      unit: ' mm',
      decimals: 1,
      onChange: (v) => sceneStore.setPrimaryLight({ sourceRadiusMm: v }),
      onInteractingChange,
    });

    this.primaryIntensityControl = createSliderControl({
      label: 'Light Intensity',
      min: 0,
      max: 5,
      numberMax: 10,
      step: 0.05,
      initialVal: 1.0,
      unit: '',
      decimals: 2,
      onChange: (v) => sceneStore.setPrimaryLight({ intensity: v }),
      onInteractingChange,
    });

    primaryGroup.append(
      this.primaryAzControl.container,
      this.primaryElControl.container,
      this.primaryDistControl.container,
      this.primaryRadiusControl.container,
      this.primaryIntensityControl.container
    );
    this.element.appendChild(primaryGroup);

    // Secondary light
    const secGroup = document.createElement('div');
    secGroup.className = 'control-subgroup';

    const secHeader = document.createElement('label');
    secHeader.className = 'checkbox-label';

    this.secLightCheck = document.createElement('input');
    this.secLightCheck.type = 'checkbox';
    this.secLightCheck.checked = sceneStore.isSecondaryLightEnabled();
    const handleSecLightToggle = () => {
      sceneStore.setSecondaryLightEnabled(this.secLightCheck.checked);
      this.secLightFields.classList.toggle('hidden', !this.secLightCheck.checked);
    };
    this.secLightCheck.onchange = handleSecLightToggle;
    this.secLightCheck.oninput = handleSecLightToggle;

    const secTitle = document.createElement('span');
    secTitle.className = 'subgroup-title';
    secTitle.textContent = 'Secondary Fill Light';

    secHeader.append(this.secLightCheck, secTitle);
    secGroup.appendChild(secHeader);

    this.secLightFields = document.createElement('div');
    this.secLightFields.className = `mt-2 ${this.secLightCheck.checked ? '' : 'hidden'}`;

    this.secAzControl = createSliderControl({
      label: 'Fill Light Azimuth',
      min: 0,
      max: 360,
      step: 0.5,
      initialVal: 0,
      unit: '°',
      decimals: 1,
      onChange: () => this.updateSecondarySpherical(),
      onInteractingChange,
    });

    this.secElControl = createSliderControl({
      label: 'Fill Light Elevation',
      min: 1,
      max: 89,
      step: 0.5,
      initialVal: 55,
      unit: '°',
      decimals: 1,
      onChange: () => this.updateSecondarySpherical(),
      onInteractingChange,
    });

    this.secDistControl = createSliderControl({
      label: 'Fill Light Distance',
      min: 10,
      max: 2000,
      numberMax: 5000,
      step: 5,
      initialVal: 400,
      unit: ' mm',
      decimals: 0,
      onChange: () => this.updateSecondarySpherical(),
      onInteractingChange,
    });

    this.secRadiusControl = createSliderControl({
      label: 'Fill Source Radius',
      min: 0,
      max: 100,
      step: 1,
      initialVal: 20,
      unit: ' mm',
      decimals: 1,
      onChange: (v) => sceneStore.setSecondaryLight({ sourceRadiusMm: v }),
      onInteractingChange,
    });

    this.secIntensityControl = createSliderControl({
      label: 'Fill Intensity',
      min: 0,
      max: 5,
      numberMax: 10,
      step: 0.05,
      initialVal: 0.8,
      unit: '',
      decimals: 2,
      onChange: (v) => sceneStore.setSecondaryLight({ intensity: v }),
      onInteractingChange,
    });

    
    const secPresetsRow = document.createElement('div');
    secPresetsRow.className = 'btn-group w-full mb-3';
    const secPresets = [
      { label: '0° East (Orthogonal)', az: 0 },
      { label: '45° Cross', az: 45 },
      { label: '270° South', az: 270 },
      { label: '180° West', az: 180 },
    ];
    for (const p of secPresets) {
      const btn = document.createElement('button');
      btn.className = 'btn btn-xs btn-outline';
      btn.textContent = p.label;
      btn.onclick = () => {
        this.secAzControl.setValue(p.az);
        this.updateSecondarySpherical();
      };
      secPresetsRow.appendChild(btn);
    }

    this.secLightFields.append(
      secPresetsRow,
      this.secAzControl.container,
      this.secElControl.container,
      this.secDistControl.container,
      this.secRadiusControl.container,
      this.secIntensityControl.container
    );
    secGroup.appendChild(this.secLightFields);
    this.element.appendChild(secGroup);

    
    // Diffraction Orders Mode (Physical ±1 vs Single +1)
    const orderGroup = document.createElement('div');
    orderGroup.className = 'control-subgroup';

    const orderHeader = document.createElement('h3');
    orderHeader.className = 'subgroup-title';
    orderHeader.textContent = 'Diffraction Orders (Micro-Gratings)';
    orderGroup.appendChild(orderHeader);

    const orderHint = document.createElement('p');
    orderHint.className = 'text-xs text-muted mb-2';
    orderHint.textContent = 'Physical symmetric gratings emit twin conjugate orders (±1). Use "+1 Order Only" to isolate a single highlight per light.';
    orderGroup.appendChild(orderHint);

    const orderBtnGroup = document.createElement('div');
    orderBtnGroup.className = 'btn-group w-full';

    this.btnBothOrders = document.createElement('button');
    this.btnBothOrders.className = 'btn btn-xs btn-active';
    this.btnBothOrders.textContent = 'Physical (±1 Orders)';
    this.btnBothOrders.onclick = () => {
      sceneStore.setDiffractionOrders('both');
      this.btnBothOrders.className = 'btn btn-xs btn-active';
      this.btnSingleOrder.className = 'btn btn-xs btn-outline';
    };

    this.btnSingleOrder = document.createElement('button');
    this.btnSingleOrder.className = 'btn btn-xs btn-outline';
    this.btnSingleOrder.textContent = 'Single (+1 Order Only)';
    this.btnSingleOrder.onclick = () => {
      sceneStore.setDiffractionOrders('single');
      this.btnSingleOrder.className = 'btn btn-xs btn-active';
      this.btnBothOrders.className = 'btn btn-xs btn-outline';
    };

    orderBtnGroup.append(this.btnBothOrders, this.btnSingleOrder);
    orderGroup.appendChild(orderBtnGroup);
    this.element.appendChild(orderGroup);

    // Physical observer
    const obsGroup = document.createElement('div');
    obsGroup.className = 'control-subgroup';

    const obsHeader = document.createElement('h3');
    obsHeader.className = 'subgroup-title';
    obsHeader.textContent = 'Physical Observer';
    obsGroup.appendChild(obsHeader);

    const camPresetRow = document.createElement('div');
    camPresetRow.className = 'btn-group w-full mb-3';

    const btnTop = document.createElement('button');
    btnTop.className = 'btn btn-xs btn-outline';
    btnTop.textContent = 'Top-Down View';
    btnTop.onclick = () => {
      const dist = Math.hypot(...Object.values(sceneStore.getCameraPos()));
      sceneStore.setCameraPos({ x: 0, y: 0.1, z: dist });
    };

    const btnOblique = document.createElement('button');
    btnOblique.className = 'btn btn-xs btn-outline';
    btnOblique.textContent = '45° Oblique View';
    btnOblique.onclick = () => {
      const dist = Math.hypot(...Object.values(sceneStore.getCameraPos())) || 300;
      const pos = positionFromDirection(270, 45, dist);
      sceneStore.setCameraPos(pos);
    };

    const btnReset = document.createElement('button');
    btnReset.className = 'btn btn-xs btn-outline';
    btnReset.textContent = 'Reset (0, 0, 300)';
    btnReset.onclick = () => {
      sceneStore.setCameraPos({ x: 0, y: 0, z: 300 });
    };

    camPresetRow.append(btnTop, btnOblique, btnReset);
    obsGroup.appendChild(camPresetRow);

    this.camAzControl = createSliderControl({
      label: 'Camera Azimuth',
      min: 0,
      max: 360,
      step: 0.5,
      initialVal: 270,
      unit: '°',
      decimals: 1,
      onChange: () => this.updateCameraSpherical(),
      onInteractingChange,
    });

    this.camElControl = createSliderControl({
      label: 'Camera Elevation',
      min: 1,
      max: 179,
      step: 0.5,
      initialVal: 90,
      unit: '°',
      decimals: 1,
      onChange: () => this.updateCameraSpherical(),
      onInteractingChange,
    });

    this.camDistControl = createSliderControl({
      label: 'Camera Distance',
      min: 10,
      max: 2000,
      numberMax: 5000,
      step: 5,
      initialVal: 300,
      unit: ' mm',
      decimals: 0,
      onChange: () => this.updateCameraSpherical(),
      onInteractingChange,
    });

    this.camApertureControl = createSliderControl({
      label: 'Observer Aperture Radius',
      min: 0.1,
      max: 30,
      numberMax: 50,
      step: 0.1,
      initialVal: 2.0,
      unit: ' mm',
      decimals: 2,
      onChange: (v) => sceneStore.setApertureRadiusMm(v),
      onInteractingChange,
    });

    obsGroup.append(
      this.camAzControl.container,
      this.camElControl.container,
      this.camDistControl.container,
      this.camApertureControl.container
    );
    this.element.appendChild(obsGroup);

    this.setupSubscriptions();
    this.syncFromStore();
  }

  public isAzimuthSweeping(): boolean {
    return this.isSweeping;
  }

  public toggleSweep(): void {
    if (this.isSweeping) {
      this.stopSweep();
    } else {
      this.startSweep();
    }
  }

  public startSweep(): void {
    if (this.isSweeping) return;
    this.isSweeping = true;
    this.sweepBtn.classList.add('btn-active');
    this.sweepBtn.innerHTML = `
      <svg class="sweep-icon mr-1" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="6" y="4" width="4" height="16"/>
        <rect x="14" y="4" width="4" height="16"/>
      </svg>
      <span>Pause Sweep</span>
    `;
    this.lastSweepTime = performance.now();

    const sweepStep = (timestamp: number) => {
      if (!this.isSweeping) return;
      const dt = Math.min((timestamp - this.lastSweepTime) / 1000.0, 0.1);
      this.lastSweepTime = timestamp;

      if (!this.isDraggingSlider) {
        const currentAz = this.primaryAzControl.getValue();
        let nextAz = (currentAz + this.sweepSpeedDegPerSec * dt) % 360.0;
        if (nextAz < 0) nextAz += 360.0;

        this.primaryAzControl.setValue(nextAz);

        const currentEl = Math.max(1, Math.min(89, this.primaryElControl.getValue()));
        const currentDist = Math.max(1, this.primaryDistControl.getValue());
        const pos = positionFromDirection(nextAz, currentEl, currentDist);
        sceneStore.setPrimaryLight({ pos });
      }

      this.sweepRafId = requestAnimationFrame(sweepStep);
    };

    this.sweepRafId = requestAnimationFrame(sweepStep);
  }

  public stopSweep(): void {
    this.isSweeping = false;
    if (this.sweepRafId !== null) {
      cancelAnimationFrame(this.sweepRafId);
      this.sweepRafId = null;
    }
    this.sweepBtn.classList.remove('btn-active');
    this.sweepBtn.innerHTML = `
      <svg class="sweep-icon mr-1" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="5 3 19 12 5 21 5 3"/>
      </svg>
      <span>Auto Sweep Azimuth</span>
    `;
  }

  private updatePrimarySpherical(): void {
    const az = this.primaryAzControl.getValue();
    const el = Math.max(1, Math.min(89, this.primaryElControl.getValue()));
    const dist = Math.max(1, this.primaryDistControl.getValue());
    const pos = positionFromDirection(az, el, dist);
    sceneStore.setPrimaryLight({ pos });
  }

  private updateSecondarySpherical(): void {
    const az = this.secAzControl.getValue();
    const el = Math.max(1, Math.min(89, this.secElControl.getValue()));
    const dist = Math.max(1, this.secDistControl.getValue());
    const pos = positionFromDirection(az, el, dist);
    sceneStore.setSecondaryLight({ pos });
  }

  private updateCameraSpherical(): void {
    const az = this.camAzControl.getValue();
    const el = Math.max(0.5, Math.min(179, this.camElControl.getValue()));
    const dist = Math.max(10, this.camDistControl.getValue());
    const pos = positionFromDirection(az, el, dist);
    sceneStore.setCameraPos(pos);
  }

  private syncFromStore(): void {
    const primary = sceneStore.getPrimaryLight();
    const pDir = directionFromPosition(primary.pos);
    const pAz = ((pDir.azimuthDeg % 360) + 360) % 360;
    this.primaryAzControl.setValue(pAz);
    this.primaryElControl.setValue(pDir.elevationDeg);
    this.primaryDistControl.setValue(pDir.distanceMm);
    this.primaryRadiusControl.setValue(primary.sourceRadiusMm);
    this.primaryIntensityControl.setValue(primary.intensity);

    const sec = sceneStore.getSecondaryLight();
    const sDir = directionFromPosition(sec.pos);
    const sAz = ((sDir.azimuthDeg % 360) + 360) % 360;
    this.secAzControl.setValue(sAz);
    this.secElControl.setValue(sDir.elevationDeg);
    this.secDistControl.setValue(sDir.distanceMm);
    this.secRadiusControl.setValue(sec.sourceRadiusMm);
    this.secIntensityControl.setValue(sec.intensity);
    this.secLightCheck.checked = sceneStore.isSecondaryLightEnabled();
    this.secLightFields.classList.toggle('hidden', !this.secLightCheck.checked);

    const cam = sceneStore.getCameraPos();
    const camDir = directionFromPosition(cam);
    const sliderEl = this.camElControl.getValue();
    const sliderPos = positionFromDirection(
      this.camAzControl.getValue(),
      Math.min(179, Math.max(0.5, sliderEl)),
      Math.max(10, this.camDistControl.getValue())
    );
    const sliderMatches =
      sliderEl > 90 &&
      Math.hypot(sliderPos.x - cam.x, sliderPos.y - cam.y, sliderPos.z - cam.z) < 1e-3;
    if (!sliderMatches) {
      const cAz = ((camDir.azimuthDeg % 360) + 360) % 360;
      this.camAzControl.setValue(cAz);
      this.camElControl.setValue(camDir.elevationDeg);
      this.camDistControl.setValue(camDir.distanceMm);
    }
    this.camApertureControl.setValue(sceneStore.getApertureRadiusMm());
    if (this.btnBothOrders && this.btnSingleOrder) {
      const orders = sceneStore.getDiffractionOrders();
      this.btnBothOrders.className = `btn btn-xs ${orders === 'both' ? 'btn-active' : 'btn-outline'}`;
      this.btnSingleOrder.className = `btn btn-xs ${orders === 'single' ? 'btn-active' : 'btn-outline'}`;
    }
  }

  private setupSubscriptions(): void {
    sceneStore.subscribe(() => {
      if (!this.isDraggingSlider) {
        this.syncFromStore();
      }
    });
  }
}
