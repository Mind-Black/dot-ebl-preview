import { importDesign } from '../importDesign';
/**
 * Welcome landing view featuring a prominent drag-and-drop upload zone
 * and one-click procedural sample preset cards.
 */

import { SAMPLE_PRESETS } from '../../lib/presets/sampleDesigns';
import { designStore } from '../../lib/store/designStore';



export class WelcomeView {
  public readonly element: HTMLElement;
  private onReadyCallback: () => void;
  private fileInput: HTMLInputElement;

  constructor(onReady: () => void) {
    this.onReadyCallback = onReady;

    this.element = document.createElement('div');
    this.element.className = 'welcome-container';

    this.element.innerHTML = `
      <div class="welcome-hero">
        <div class="hero-badge">Dot-Matrix EBL Preview Platform</div>
        <h1 class="hero-title">Interactive Diffraction Optics & Physical Parameter Inspector</h1>
        <p class="hero-subtitle">
          Inspect micro-grating periods, orientations, and qualitative diffraction optical behavior directly in the browser.
          Upload design images, inspect parameter distributions, or explore test benchmarks below.
        </p>
      </div>

      <div class="welcome-actions-grid">
        <div class="upload-dropzone" id="welcome-dropzone">
          <svg class="dropzone-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          <div class="dropzone-title">Drop Design Image or .npz Archive</div>
          <div class="dropzone-desc">Supports RGB8 / RGB16 PNGs, Python design.npz, BMP, JPEG, WebP</div>
          <button class="btn btn-primary mt-3" id="welcome-browse-btn">Browse Local Files</button>
        </div>

        <div class="presets-container">
          <div class="presets-header">
            <h3>Or Explore a Physical Benchmark</h3>
            <span class="text-muted">Instant procedural designs</span>
          </div>
          <div class="presets-grid" id="welcome-presets-grid"></div>
        </div>
      </div>
    `;

    // Hidden file input
    this.fileInput = document.createElement('input');
    this.fileInput.type = 'file';
    this.fileInput.accept = '.png,.bmp,.jpg,.jpeg,.webp,.npz';
    this.fileInput.className = 'hidden';
    this.element.appendChild(this.fileInput);

    this.setupEvents();
    this.renderPresets();
  }

  private renderPresets(): void {
    const grid = this.element.querySelector('#welcome-presets-grid');
    if (!grid) return;

    for (const preset of SAMPLE_PRESETS) {
      const card = document.createElement('button');
      card.className = 'preset-card';
      card.innerHTML = `
        <div class="preset-card-title">${preset.title}</div>
        <div class="preset-card-desc">${preset.description}</div>
        <div class="preset-card-action">Load Preset &rarr;</div>
      `;
      card.onclick = () => {
        designStore.setPhysicalDesign(preset.generator());
        this.onReadyCallback();
      };
      grid.appendChild(card);
    }
  }

  private setupEvents(): void {
    const dropzone = this.element.querySelector('#welcome-dropzone') as HTMLElement;
    const browseBtn = this.element.querySelector('#welcome-browse-btn') as HTMLButtonElement;

    browseBtn.onclick = () => this.fileInput.click();

    this.fileInput.onchange = (e) => {
      const files = (e.target as HTMLInputElement).files;
      if (files && files.length > 0) {
        this.handleFile(files[0]);
      }
    };

    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('drag-over');
    });

    dropzone.addEventListener('dragleave', () => {
      dropzone.classList.remove('drag-over');
    });

    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('drag-over');
      if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
        this.handleFile(e.dataTransfer.files[0]);
      }
    });
  }

  private async handleFile(file: File): Promise<void> {
    importDesign(file, this.onReadyCallback);
    this.fileInput.value = "";
  }
}
