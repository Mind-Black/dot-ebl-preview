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

  private minPeriodInput: HTMLInputElement;

  private maxPeriodInput: HTMLInputElement;

  private minAngleInput: HTMLInputElement;

  private maxAngleInput: HTMLInputElement;

  private filterCheckbox: HTMLInputElement;

  private roundAnglesCheckbox: HTMLInputElement;

  private roundPeriodCheckbox: HTMLInputElement;

  private pitchControl: SliderControl;

  private orientationControl: SliderControl;

  private qualityContainer: HTMLElement;

  private errorBanner: HTMLElement;

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
    const identity = document.createElement('p'); identity.setAttribute('role','status'); this.element.append(identity);
    const recovery = document.createElement('div'); this.element.append(recovery);
    for (const [label,action] of [['Retry',()=>designStore.retryImport()],['Choose another file',()=>this.fileInput.click()],['Continue with retained design',()=>designStore.clearError()]] as const) { const b=document.createElement('button'); b.className='btn'; b.textContent=label; b.onclick=action; recovery.append(b); }
    designStore.subscribe(()=>{ identity.textContent = designStore.getPendingFilename() ? `Importing ${designStore.getPendingFilename()}…` : `${designStore.getDesign()?.sourceIdentity ?? 'No design loaded'} · ${designStore.getInterpretation()}`; recovery.hidden=!designStore.getError(); }); recovery.hidden=true;



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

    uploadBtn.className = 'btn btn-primary w-full';

    uploadBtn.innerHTML = `

      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2">

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



    const minPeriodGroup = document.createElement('div');

    const minPeriodLabel = document.createElement('label');

    minPeriodLabel.className = 'text-xs text-muted block mb-1';

    minPeriodLabel.textContent = 'Min Period (nm)';

    this.minPeriodInput = document.createElement('input');

    this.minPeriodInput.type = 'number';

    this.minPeriodInput.className = 'form-input form-input-sm w-full';

    this.minPeriodInput.value = '400';

    this.minPeriodInput.step = '10';

    this.minPeriodInput.onchange = () => {

      const val = parseFloat(this.minPeriodInput.value);

      if (Number.isFinite(val) && val > 0) {

        designStore.setRgbaOptions({ minPeriodNm: val });

      }

    };

    minPeriodGroup.append(minPeriodLabel, this.minPeriodInput);



    const maxPeriodGroup = document.createElement('div');

    const maxPeriodLabel = document.createElement('label');

    maxPeriodLabel.className = 'text-xs text-muted block mb-1';

    maxPeriodLabel.textContent = 'Max Period (nm)';

    this.maxPeriodInput = document.createElement('input');

    this.maxPeriodInput.type = 'number';

    this.maxPeriodInput.className = 'form-input form-input-sm w-full';

    this.maxPeriodInput.value = '1600';

    this.maxPeriodInput.step = '10';

    this.maxPeriodInput.onchange = () => {

      const val = parseFloat(this.maxPeriodInput.value);

      if (Number.isFinite(val) && val > 0) {

        designStore.setRgbaOptions({ maxPeriodNm: val });

      }

    };

    maxPeriodGroup.append(maxPeriodLabel, this.maxPeriodInput);

    periodRow.append(minPeriodGroup, maxPeriodGroup);

    this.rgbaPanel.appendChild(periodRow);



    const angleRow = document.createElement('div');

    angleRow.className = 'grid grid-cols-2 gap-2 mb-2';



    const minAngleGroup = document.createElement('div');

    const minAngleLabel = document.createElement('label');

    minAngleLabel.className = 'text-xs text-muted block mb-1';

    minAngleLabel.textContent = 'Min Angle (°)';

    this.minAngleInput = document.createElement('input');

    this.minAngleInput.type = 'number';

    this.minAngleInput.className = 'form-input form-input-sm w-full';

    this.minAngleInput.value = '-90';

    this.minAngleInput.step = '1';

    this.minAngleInput.onchange = () => {

      const val = parseFloat(this.minAngleInput.value);

      if (Number.isFinite(val)) {

        designStore.setRgbaOptions({ minAngleDeg: val });

      }

    };

    minAngleGroup.append(minAngleLabel, this.minAngleInput);



    const maxAngleGroup = document.createElement('div');

    const maxAngleLabel = document.createElement('label');

    maxAngleLabel.className = 'text-xs text-muted block mb-1';

    maxAngleLabel.textContent = 'Max Angle (°)';

    this.maxAngleInput = document.createElement('input');

    this.maxAngleInput.type = 'number';

    this.maxAngleInput.className = 'form-input form-input-sm w-full';

    this.maxAngleInput.value = '90';

    this.maxAngleInput.step = '1';

    this.maxAngleInput.onchange = () => {

      const val = parseFloat(this.maxAngleInput.value);

      if (Number.isFinite(val)) {

        designStore.setRgbaOptions({ maxAngleDeg: val });

      }

    };

    maxAngleGroup.append(maxAngleLabel, this.maxAngleInput);

    angleRow.append(minAngleGroup, maxAngleGroup);

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



    for(const [input,key,min,max] of [[this.minPeriodInput,'minPeriodNm',200,2000],[this.maxPeriodInput,'maxPeriodNm',200,2000],[this.minAngleInput,'minAngleDeg',-180,180],[this.maxAngleInput,'maxAngleDeg',-180,180]] as const){

      const control=createSliderControl({label:input.parentElement?.querySelector('label')?.textContent||key,min,max,step:key.includes('Period')?10:1,initialVal:Number(input.value),decimals:0,onChange:v=>{input.value=String(v);designStore.setRgbaOptions({[key]:v});}});this.optionControls.set(key,control);input.parentElement!.replaceChildren(control.container);input.hidden=true;

    }

    for(const [key,label,min,max,step,initialVal] of [['filterDiameter','Filter diameter',1,9,2,3],['filterSigmaSpace','Spatial sigma',10,200,5,100],['filterSigmaColorPeriod','Period sigma',10,100,1,50],['filterSigmaColorAngle','Angle sigma',2,45,1,10]] as const){const control=createSliderControl({label,min,max,step,initialVal,onChange:v=>designStore.setRgbaOptions({[key]:v})});this.optionControls.set(key,control);this.rgbaPanel.append(control.container);}

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

      btn.className = `btn btn-sm ${lvl.id === sceneStore.getQuality() ? 'btn-active' : ''}`;

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

      btn.classList.toggle('btn-active', order[idx] === q);

    });

  }



  private setupSubscriptions(): void {

    designStore.subscribe(() => {

      const err = designStore.getError();

      if (err) {

        this.errorBanner.textContent = err;

        this.errorBanner.classList.remove('hidden');

      } else {

        this.errorBanner.textContent = '';

        this.errorBanner.classList.add('hidden');

      }



      const interp = designStore.getInterpretation();

      this.formatSelect.value = interp;
      this.formatSelect.disabled = interp === 'NPZ design' || !!designStore.getPendingFilename();
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

      if (document.activeElement !== this.minPeriodInput) {

        this.minPeriodInput.value = String(opts.minPeriodNm ?? 400);

      }

      if (document.activeElement !== this.maxPeriodInput) {

        this.maxPeriodInput.value = String(opts.maxPeriodNm ?? 1600);

      }

      if (document.activeElement !== this.minAngleInput) {

        this.minAngleInput.value = String(opts.minAngleDeg ?? -90);

      }

      if (document.activeElement !== this.maxAngleInput) {

        this.maxAngleInput.value = String(opts.maxAngleDeg ?? 90);

      }

      this.filterCheckbox.checked = opts.applyFilter ?? true;

      this.roundAnglesCheckbox.checked = opts.roundIntegerAngles ?? false;

      this.roundPeriodCheckbox.checked = opts.roundPeriod50Nm ?? false;

    });



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
