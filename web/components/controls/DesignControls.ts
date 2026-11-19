import { importDesign } from '../importDesign';
/**

 * Design controls: file upload, interpretation selection, pitch, global orientation, and quality toggle.

 * Features real-time linked range sliders for holopixel pitch and grating orientation.

 */



import type { InterpretationFormat } from '../../lib/decoders/types';





import { SAMPLE_PRESETS, createShowcaseHologram } from '../../lib/presets/sampleDesigns';

import { designStore } from '../../lib/store/designStore';

import { sceneStore } from '../../lib/store/sceneStore';

import type { QualityLevel } from '../../lib/optics/tables';

import { createSliderControl, type SliderControl } from './sliderControl';



export class DesignControls {

  public readonly element: HTMLElement;

  private optionControls = new Map<string, SliderControl>();

  private formatSelect: HTMLSelectElement;

  private rgbaPanel: HTMLElement;

  private filterCheckbox: HTMLInputElement;

  private roundAnglesCheckbox: HTMLInputElement;

  private roundPeriodCheckbox: HTMLInputElement;

  private pitchControl: SliderControl;

  private orientationControl: SliderControl;

  private qualityContainer: HTMLElement;

  private errorBanner: HTMLElement;

  private identityStatus: HTMLParagraphElement;

  private recoveryGroup: HTMLDivElement;

  private retryBtn: HTMLButtonElement;

  private chooseAnotherBtn: HTMLButtonElement;

  private continueBtn: HTMLButtonElement;

  private fileInput: HTMLInputElement;



  constructor() {

    this.element = document.createElement('section');

    this.element.className = 'controls-section design-controls';



    // Title

    const title = document.createElement('h2');

    title.className = 'section-title';

    title.textContent = 'Design & Ingestion';

    this.element.appendChild(title);



    // Error banner

    this.errorBanner = document.createElement('div');

    this.errorBanner.setAttribute('role', 'alert');
    this.errorBanner.className = 'alert alert-danger hidden';

    this.element.appendChild(this.errorBanner);
    this.identityStatus = document.createElement('p');
    this.identityStatus.className = 'design-identity-status';
    this.identityStatus.setAttribute('role', 'status');
    this.identityStatus.textContent = `${designStore.getDesign()?.sourceIdentity ?? 'No design loaded'} · ${designStore.getInterpretation()}`;
    this.element.append(this.identityStatus);

    this.recoveryGroup = document.createElement('div');
    this.recoveryGroup.className = 'import-recovery-actions';
    this.recoveryGroup.hidden = true;
    const makeRecoveryBtn = (label: string, action: () => void) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-outline btn-xs';
      b.textContent = label;
      b.onclick = action;
      this.recoveryGroup.append(b);
      return b;
    };
    this.retryBtn = makeRecoveryBtn('Retry', () => designStore.retryImport());
    this.chooseAnotherBtn = makeRecoveryBtn('Choose another file', () => this.fileInput.click());
    this.continueBtn = makeRecoveryBtn('Continue with retained design', () => designStore.clearError());
    this.element.append(this.recoveryGroup);



    // File Drop Zone / Upload Button

    const uploadGroup = document.createElement('div');

    uploadGroup.className = 'form-group file-upload-group';



    this.fileInput = document.createElement('input');

    this.fileInput.type = 'file';

    this.fileInput.accept = '.png,.bmp,.jpg,.jpeg,.webp,.npz';

    this.fileInput.className = 'hidden-file-input';

    this.fileInput.onchange = (e) => {

      const target = e.target as HTMLInputElement;

      if (target.files && target.files.length > 0) {

        this.handleFileUpload(target.files[0]);

      }

    };



    const uploadBtn = document.createElement('button');

    uploadBtn.type = 'button';

    uploadBtn.className = 'btn btn-primary w-full';

    uploadBtn.innerHTML = `

      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2" aria-hidden="true">

        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>

        <polyline points="17 8 12 3 7 8"/>

        <line x1="12" y1="3" x2="12" y2="15"/>

      </svg>

      Upload Design (.png, .npz, web images)

    `;

    uploadBtn.onclick = () => this.fileInput.click();



    uploadGroup.append(this.fileInput, uploadBtn);

    this.element.appendChild(uploadGroup);



    // Interpretation format dropdown

    const formatGroup = document.createElement('div');

    formatGroup.className = 'form-group';

    const formatLabel = document.createElement('label');

    formatLabel.className = 'form-label';

    formatLabel.textContent = 'Parameter Interpretation Profile';



    this.formatSelect = document.createElement('select');

    this.formatSelect.className = 'form-select';

    const formats: InterpretationFormat[] = [

      'RGBA continuous',

      'RGB8 indexed',

      'RGB16 fixed',

      'Holtida legacy HLS',

      'Learning Shaders HLS',

      'Unity HSV',

      'NPZ design',

    ];

    for (const f of formats) {

      const opt = document.createElement('option');

      opt.value = f;

      opt.textContent = f;

      this.formatSelect.appendChild(opt);

    }

    this.formatSelect.value = designStore.getInterpretation();

    this.formatSelect.onchange = () => {

      designStore.setInterpretation(this.formatSelect.value as InterpretationFormat);

    };



    this.formatSelect.id = 'interpretation-profile'; formatLabel.htmlFor = this.formatSelect.id;
    formatGroup.append(formatLabel, this.formatSelect);

    this.element.appendChild(formatGroup);



    // Dedicated RGBA Interpretation Panel

    this.rgbaPanel = document.createElement('div');

    this.rgbaPanel.className = 'form-group rgba-interpretation-panel';

    this.rgbaPanel.style.padding = '10px';

    this.rgbaPanel.style.border = '1px solid var(--border-color, #333)';

    this.rgbaPanel.style.borderRadius = '6px';

    this.rgbaPanel.style.marginBottom = '12px';



    const rgbaTitle = document.createElement('div');

    rgbaTitle.className = 'form-label';

    rgbaTitle.style.fontWeight = 'bold';

    rgbaTitle.style.marginBottom = '8px';

    rgbaTitle.textContent = 'RGBA Interpretation';

    this.rgbaPanel.appendChild(rgbaTitle);



    const periodRow = document.createElement('div');
    periodRow.className = 'grid grid-cols-2 gap-2 mb-2';
    for (const [label, key, min, max, initialVal] of [
      ['Min Period (nm)', 'minPeriodNm', 200, 2000, 400],
      ['Max Period (nm)', 'maxPeriodNm', 200, 2000, 1600],
    ] as const) {
      const control = createSliderControl({
        label,
        min,
        max,
        step: 10,
        initialVal,
        decimals: 0,
        onChange: (v) => designStore.setRgbaOptions({ [key]: v }),
      });
      this.optionControls.set(key, control);
      periodRow.append(control.container);
    }
    this.rgbaPanel.appendChild(periodRow);

    const angleRow = document.createElement('div');
    angleRow.className = 'grid grid-cols-2 gap-2 mb-2';
    for (const [label, key, min, max, initialVal] of [
      ['Min Angle (°)', 'minAngleDeg', -180, 180, -90],
      ['Max Angle (°)', 'maxAngleDeg', -180, 180, 90],
    ] as const) {
      const control = createSliderControl({
        label,
        min,
        max,
        step: 1,
        initialVal,
        decimals: 0,
        onChange: (v) => designStore.setRgbaOptions({ [key]: v }),
      });
      this.optionControls.set(key, control);
      angleRow.append(control.container);
    }
    this.rgbaPanel.appendChild(angleRow);



    const filterRow = document.createElement('div');

    filterRow.className = 'flex items-center gap-2 mt-2';

    this.filterCheckbox = document.createElement('input');

    this.filterCheckbox.type = 'checkbox';

    this.filterCheckbox.id = 'rgba-smooth-gradients-toggle';

    this.filterCheckbox.checked = true;

    this.filterCheckbox.onchange = () => {

      designStore.setRgbaOptions({ applyFilter: this.filterCheckbox.checked });

    };

    const filterLabel = document.createElement('label');

    filterLabel.htmlFor = 'rgba-smooth-gradients-toggle';

    filterLabel.className = 'text-sm cursor-pointer select-none';

    filterLabel.textContent = 'Smooth Gradients';

    filterRow.append(this.filterCheckbox, filterLabel);

    this.rgbaPanel.appendChild(filterRow);



    const roundRow = document.createElement('div');

    roundRow.className = 'flex items-center gap-2 mt-2';

    this.roundAnglesCheckbox = document.createElement('input');

    this.roundAnglesCheckbox.type = 'checkbox';

    this.roundAnglesCheckbox.id = 'rgba-round-angles-toggle';

    this.roundAnglesCheckbox.checked = false;

    this.roundAnglesCheckbox.onchange = () => {

      designStore.setRgbaOptions({ roundIntegerAngles: this.roundAnglesCheckbox.checked });

    };

    const roundLabel = document.createElement('label');

    roundLabel.htmlFor = 'rgba-round-angles-toggle';

    roundLabel.className = 'text-sm cursor-pointer select-none';

    roundLabel.textContent = 'Round to Integer Angles';

    roundRow.append(this.roundAnglesCheckbox, roundLabel);

    this.rgbaPanel.appendChild(roundRow);



    const roundPeriodRow = document.createElement('div');

    roundPeriodRow.className = 'flex items-center gap-2 mt-2';

    this.roundPeriodCheckbox = document.createElement('input');

    this.roundPeriodCheckbox.type = 'checkbox';

    this.roundPeriodCheckbox.id = 'rgba-round-period-toggle';

    this.roundPeriodCheckbox.checked = false;

    this.roundPeriodCheckbox.onchange = () => {

      designStore.setRgbaOptions({ roundPeriod50Nm: this.roundPeriodCheckbox.checked });

    };

    const roundPeriodLabel = document.createElement('label');

    roundPeriodLabel.htmlFor = 'rgba-round-period-toggle';

    roundPeriodLabel.className = 'text-sm cursor-pointer select-none';

    roundPeriodLabel.textContent = 'Round Period to 50 nm';

    roundPeriodRow.append(this.roundPeriodCheckbox, roundPeriodLabel);

    this.rgbaPanel.appendChild(roundPeriodRow);



    for (const [key, label, min, max, step, initialVal, decimals] of [
      ['filterDiameter', 'Filter diameter', 1, 9, 2, 3, 0],
      ['filterSigmaSpace', 'Spatial sigma', 10, 200, 5, 100, 1],
      ['filterSigmaColorPeriod', 'Period sigma', 10, 100, 1, 50, 1],
      ['filterSigmaColorAngle', 'Angle sigma', 2, 45, 1, 10, 1],
    ] as const) {
      const control = createSliderControl({
        label,
        min,
        max,
        step,
        initialVal,
        decimals,
        onChange: (v) => {
          if (key === 'filterDiameter') {
            const odd = Math.min(9, Math.max(1, Math.round((v - 1) / 2) * 2 + 1));
            if (odd !== v) control.setValue(odd);
            designStore.setRgbaOptions({ filterDiameter: odd });
          } else {
            designStore.setRgbaOptions({ [key]: v });
          }
        },
      });
      this.optionControls.set(key, control);
      this.rgbaPanel.append(control.container);
    }

    this.element.appendChild(this.rgbaPanel);

    if (designStore.getInterpretation() !== 'RGBA continuous') {

      this.rgbaPanel.classList.add('hidden');

    }



    // Pitch Control (µm) with Real-Time Range Slider

    this.pitchControl = createSliderControl({

      label: 'Holopixel Lattice Pitch',

      min: 1,

      max: 100,

      numberMin: 1,

      numberMax: 1000,

      step: 1,

      initialVal: designStore.getPitchNm() / 1000.0,

      unit: ' µm',

      decimals: 0,

      onChange: (um) => {

        if (Number.isFinite(um) && um > 0) {

          designStore.setPitchNm(Math.round(um * 1000.0));

        }

      },

    });

    this.element.appendChild(this.pitchControl.container);



    // Global Grating Orientation Control (-180° to +180°) with Real-Time Slider

    this.orientationControl = createSliderControl({

      label: 'Grating Orientation',

      min: -180,

      max: 180,

      step: 0.5,

      initialVal: sceneStore.getOrientationDeg(),

      unit: '°',

      decimals: 1,

      onChange: (deg) => {

        sceneStore.setOrientationDeg(deg);

      },

      onInteractingChange: (interacting) => {

        sceneStore.setIsInteracting(interacting);

      },

    });

    this.element.appendChild(this.orientationControl.container);



    // Quality Toggle: High / Balanced / Performance

    const qualityGroup = document.createElement('div');

    qualityGroup.className = 'form-group';

    const qualityLabel = document.createElement('label');

    qualityLabel.className = 'form-label';

    qualityLabel.textContent = 'Optical Diffraction Quality';



    this.qualityContainer = document.createElement('div');

    this.qualityContainer.className = 'btn-group w-full';



    const levels: { id: QualityLevel; name: string; desc: string }[] = [

      { id: 'high', name: 'High', desc: '77 bands (5 nm)' },

      { id: 'balanced', name: 'Balanced', desc: '39 bands (10 nm)' },

      { id: 'performance', name: 'Fast', desc: '19 bands (20 nm)' },

    ];



    for (const lvl of levels) {

      const btn = document.createElement('button');

      btn.type = 'button';

      const isActive = lvl.id === sceneStore.getQuality();

      btn.className = `btn btn-sm ${isActive ? 'btn-active' : ''}`;

      btn.setAttribute('aria-pressed', String(isActive));

      btn.textContent = lvl.name;

      btn.title = lvl.desc;

      btn.onclick = () => {

        sceneStore.setQuality(lvl.id);

        this.updateQualityButtons();

      };

      this.qualityContainer.appendChild(btn);

    }



    qualityGroup.append(qualityLabel, this.qualityContainer);

    this.element.appendChild(qualityGroup);



    // Sample design quick loader buttons

    const sampleGroup = document.createElement('div');

    sampleGroup.className = 'form-group mt-3';

    const sampleLabel = document.createElement('label');

    sampleLabel.className = 'form-label text-muted';

    sampleLabel.textContent = 'Load Sample Physical Design';



    const sampleRow = document.createElement('div');

    sampleRow.className = 'grid grid-cols-2 gap-2';

    const showcaseBtn = document.createElement('button');
    showcaseBtn.type = 'button';
    showcaseBtn.className = 'btn btn-xs btn-outline btn-showcase-select';
    showcaseBtn.style.gridColumn = '1 / -1';
    showcaseBtn.textContent = '✨ Default Showcase (256×256)';
    showcaseBtn.onclick = () => {
      const design = createShowcaseHologram(256);
      designStore.setPhysicalDesign(design);
    };
    sampleRow.appendChild(showcaseBtn);



    for (const preset of SAMPLE_PRESETS) {

      const btn = document.createElement('button');

      btn.type = 'button';

      btn.className = 'btn btn-xs btn-outline';

      btn.textContent = preset.title;

      btn.onclick = () => {

        const design = preset.generator();

        designStore.setPhysicalDesign(design);

      };

      sampleRow.appendChild(btn);

    }



    sampleGroup.append(sampleLabel, sampleRow);

    this.element.appendChild(sampleGroup);



    this.setupSubscriptions();

  }



  private updateQualityButtons(): void {

    const q = sceneStore.getQuality();

    const buttons = this.qualityContainer.querySelectorAll('button');

    const order: QualityLevel[] = ['high', 'balanced', 'performance'];

    buttons.forEach((btn, idx) => {

      const active = order[idx] === q;

      btn.classList.toggle('btn-active', active);

      btn.setAttribute('aria-pressed', String(active));

    });

  }



  private setupSubscriptions(): void {

    const syncDesignState = () => {

      const err = designStore.getError();

      const design = designStore.getDesign();

      const pending = designStore.getPendingFilename();

      this.identityStatus.textContent = pending
        ? `Importing ${pending}…`
        : `${design?.sourceIdentity ?? 'No design loaded'} · ${designStore.getInterpretation()}`;

      this.recoveryGroup.hidden = !err;
      this.retryBtn.hidden = !designStore.canRetryImport();
      this.chooseAnotherBtn.hidden = !err;
      this.continueBtn.hidden = !err || !design;

      if (err) {

        this.errorBanner.textContent = err;

        this.errorBanner.classList.remove('hidden');

      } else {

        this.errorBanner.textContent = '';

        this.errorBanner.classList.add('hidden');

      }



      const interp = designStore.getInterpretation();

      this.formatSelect.value = interp;
      this.formatSelect.disabled = interp === 'NPZ design' || !!pending;
      Array.from(this.formatSelect.options).forEach(o=>o.disabled=o.value==='NPZ design');

      this.pitchControl.setValue(designStore.getPitchNm() / 1000.0);



      if (interp === 'RGBA continuous') {

        this.rgbaPanel.classList.remove('hidden');

      } else {

        this.rgbaPanel.classList.add('hidden');

      }



      const opts = designStore.getRgbaOptions();
      const defaults = {minPeriodNm:400,maxPeriodNm:1600,minAngleDeg:-90,maxAngleDeg:90,filterDiameter:3,filterSigmaSpace:100,filterSigmaColorPeriod:50,filterSigmaColorAngle:10};
      for (const [key,control] of this.optionControls) control.setValue(Number(opts[key as keyof typeof opts] ?? defaults[key as keyof typeof defaults]));

      const filterEnabled = opts.applyFilter ?? true;
      for (const key of ['filterDiameter', 'filterSigmaSpace', 'filterSigmaColorPeriod', 'filterSigmaColorAngle']) {
        this.optionControls.get(key)?.setDisabled(!filterEnabled);
      }

      this.filterCheckbox.checked = filterEnabled;

      this.roundAnglesCheckbox.checked = opts.roundIntegerAngles ?? false;

      this.roundPeriodCheckbox.checked = opts.roundPeriod50Nm ?? false;

    };

    designStore.subscribe(syncDesignState);
    syncDesignState();



    sceneStore.subscribe(() => {

      this.updateQualityButtons();

      this.orientationControl.setValue(sceneStore.getOrientationDeg());

    });

  }



  public async handleFileUpload(file: File): Promise<void> {

    importDesign(file);
    this.fileInput.value = "";

  }

}
