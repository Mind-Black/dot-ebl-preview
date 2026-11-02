/**
 * Reusable linked range slider + numeric input component for real-time parameter control.
 */

export interface SliderControlOptions {
  label: string;
  min: number;
  max: number;
  step: number;
  initialVal: number;
  unit?: string;
  helpText?: string;
  decimals?: number;
  numberMin?: number;
  numberMax?: number;
  onChange: (val: number) => void;
  onInteractingChange?: (isInteracting: boolean) => void;
}

export interface SliderControl {
  container: HTMLElement;
  slider: HTMLInputElement;
  numInput: HTMLInputElement;
  valueBadge: HTMLElement;
  getValue(): number;
  setValue(val: number): void;
}

let controlId = 0;
export function createSliderControl(options: SliderControlOptions): SliderControl {
  const decimals = options.decimals ?? 1;
  const unit = options.unit ?? '';
  const id = `parameter-${++controlId}`;
  const numMin = options.numberMin ?? options.min;
  const numMax = options.numberMax ?? options.max;

  const container = document.createElement('div');
  container.className = 'form-group slider-control-group';

  const labelRow = document.createElement('label');
  labelRow.className = 'form-label';

  const labelTitle = document.createElement('span');
  labelTitle.textContent = options.label;

  const valueBadge = document.createElement('span');
  valueBadge.className = 'value-badge';
  valueBadge.textContent = `${options.initialVal.toFixed(decimals)}${unit}`;

  labelRow.append(labelTitle, valueBadge);

  const row = document.createElement('div');
  row.className = 'flex items-center gap-2';

  const slider = document.createElement('input');
  slider.type = 'range';
  slider.min = options.min.toString();
  slider.max = options.max.toString();
  slider.step = options.step.toString();
  slider.value = options.initialVal.toString();
  slider.className = 'form-range flex-1';

  const numInput = document.createElement('input');
  numInput.type = 'number';
  numInput.min = numMin.toString();
  numInput.max = numMax.toString();
  numInput.step = options.step.toString();
  numInput.value = options.initialVal.toFixed(decimals);
  numInput.className = 'form-input form-input-sm w-20 text-right font-mono';

  let currentVal = options.initialVal;


  const updateFromVal = (val: number, source: 'slider' | 'number' | 'external') => {
    if (!Number.isFinite(val)) return;
    currentVal = val;
    valueBadge.textContent = `${val.toFixed(decimals)}${unit}`;

    if (source !== 'slider') {
      const clampedForSlider = Math.max(options.min, Math.min(options.max, val));
      slider.value = clampedForSlider.toString();
    }
    if (source !== 'number') {
      numInput.value = val.toFixed(decimals);
    }

    if (source !== 'external') {
      options.onChange(val);
    }
  };

  slider.oninput = () => {
    const val = parseFloat(slider.value);
    updateFromVal(val, 'slider');
  };

  slider.addEventListener('pointerdown', () => {
    options.onInteractingChange?.(true);
  });
  slider.addEventListener('pointerup', () => {
    options.onInteractingChange?.(false);
  });
  slider.addEventListener('pointercancel', () => {
    options.onInteractingChange?.(false);
  });

  numInput.oninput = () => {
    const val = parseFloat(numInput.value);
    if (Number.isFinite(val)) {
      updateFromVal(val, 'number');
    }
  };

  numInput.onchange = () => {
    const val = parseFloat(numInput.value);
    if (Number.isFinite(val)) {
      updateFromVal(val, 'number');
    }
  };

  slider.id = `${id}-range`; numInput.id = `${id}-number`;
  labelRow.htmlFor = slider.id;
  slider.setAttribute('aria-label', `${options.label} ${unit} slider`);
  numInput.setAttribute('aria-label', `${options.label} ${unit} numeric value`);
  row.append(slider, numInput);
  container.append(labelRow, row);
  if(options.helpText){const help=document.createElement('p');help.id=`${id}-help`;help.className='text-muted text-xs';help.textContent=options.helpText;container.append(help);slider.setAttribute('aria-describedby',help.id);numInput.setAttribute('aria-describedby',help.id);}


  return {
    container,
    slider,
    numInput,
    valueBadge,
    getValue: () => currentVal,
    setValue: (val: number) => {
      updateFromVal(val, 'external');
    },
  };
}
