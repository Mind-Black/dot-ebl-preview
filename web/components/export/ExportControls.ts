import { sceneStore } from '../../lib/store/sceneStore';
import { fabricationSnapshot } from '../../lib/raith/snapshot';
import { openFabrication } from './FabricationModal';

/**

 * Export controls for PNG captures, parameter maps, CSV, and JSON data.

 */



import { designStore } from '../../lib/store/designStore';

import type { DualViewport } from '../viewer/DualViewport';



export class ExportControls {

  public readonly element: HTMLElement;

  private dualViewport: DualViewport;



  constructor(dualViewport: DualViewport) {

    this.dualViewport = dualViewport;



    this.element = document.createElement('section');

    this.element.className = 'controls-section export-controls';



    const title = document.createElement('h2');

    title.className = 'section-title';

    title.textContent = 'Exports & Data Artifacts';

    this.element.appendChild(title);



    const btnGrid = document.createElement('div');

    btnGrid.className = 'grid grid-cols-2 gap-2';



    // 1. Full-resolution flat optical preview PNG

    const btnFlatOptical = document.createElement('button');

    btnFlatOptical.className = 'btn btn-outline btn-sm';

    btnFlatOptical.textContent = 'Optical Preview PNG (1:1)';

    btnFlatOptical.onclick = () => this.exportFlatOptical();



    // 2. Perspective Viewport Capture PNG

    const btnPerspective = document.createElement('button');

    btnPerspective.className = 'btn btn-outline btn-sm';

    btnPerspective.textContent = 'Perspective Capture PNG';

    btnPerspective.onclick = () => this.exportPerspective();



    // 3. Distribution CSV

    const btnCsv = document.createElement('button');

    btnCsv.className = 'btn btn-outline btn-sm';

    btnCsv.textContent = 'Parameter Distribution (CSV)';

    btnCsv.onclick = () => this.exportCsv();



    // 4. Distribution JSON

    const btnJson = document.createElement('button');

    btnJson.className = 'btn btn-outline btn-sm';

    btnJson.textContent = 'Parameter Metadata (JSON)';

    btnJson.onclick = () => this.exportJson();



    const capabilityNotice=document.createElement('p'); capabilityNotice.className='text-muted text-xs'; this.element.append(capabilityNotice);
    const updateEligibility=()=>{capabilityNotice.textContent = !this.dualViewport.flatView.available ? 'Optical captures are unavailable. Use Retry preview above; parameter data and fabrication exports remain available.' : !this.dualViewport.perspectiveView ? 'Perspective capture is unavailable because its renderer could not initialize.' : ''; for(const b of [btnFlatOptical,btnPerspective,btnCsv,btnJson]) b.disabled=!designStore.canExport();btnFlatOptical.disabled ||= !this.dualViewport.flatView.available;btnPerspective.disabled ||= !this.dualViewport.perspectiveView;};
    designStore.subscribe(updateEligibility); this.element.addEventListener('pointerover',updateEligibility); this.element.addEventListener('focusin',updateEligibility); updateEligibility();
    btnGrid.append(btnFlatOptical, btnPerspective, btnCsv, btnJson);

    this.element.appendChild(btnGrid);

    const section=document.createElement('details');const summary=document.createElement('summary');summary.textContent='EBL Lithography Fabrication';section.append(summary);

    const field=(label:string,value:string,type='number')=>{const l=document.createElement('label');l.textContent=label;const i=document.createElement('input');i.type=type;i.value=value;i.className='form-input';l.append(i);section.append(l);return i;};

    const layer=field('GDS layer','1');layer.min='0';layer.max='63';const dose=field('Dose factor','1');dose.min='0';dose.max='17797.5';dose.step='0.001';const name=field('Top structure name','HOLOGRAM','text');name.maxLength=32;const center=field('Center full grid at (0, 0)','','checkbox');

    const exportButton=document.createElement('button');exportButton.className='btn btn-primary w-full';exportButton.textContent='Export EBL Layout (.gds)';section.append(exportButton);

    let previous:object|null=null;designStore.subscribe(()=>{const d=designStore.getDesign();exportButton.disabled=!d||designStore.getIsProcessing()||!!designStore.getError();if(d&&d!==previous){if(d.layer!==undefined)layer.value=String(d.layer);if(d.dose!==undefined)dose.value=String(d.dose);previous=d;}});

    exportButton.disabled=!designStore.getDesign();exportButton.onclick=()=>{const d=designStore.getDesign();if(d&&!designStore.getIsProcessing()&&!designStore.getError())openFabrication(fabricationSnapshot(d, sceneStore.getOrientationDeg()),{topName:name.value,layer:Number(layer.value),dose:Number(dose.value),centerOrigin:center.checked});};this.element.append(section);



  }



  private downloadDataUrl(dataUrl: string, filename: string): void {

    const a = document.createElement('a');

    a.href = dataUrl;

    a.download = filename;

    document.body.appendChild(a);

    a.click();

    document.body.removeChild(a);

  }



  private downloadBlob(blob: Blob, filename: string): void {

    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');

    a.href = url;

    a.download = filename;

    document.body.appendChild(a);

    a.click();

    document.body.removeChild(a);

    URL.revokeObjectURL(url);

  }



  public exportFlatOptical(): void {

    const design = designStore.getDesign();

    if (!designStore.canExport() || !design) return;

    const dataUrl = this.dualViewport.flatView.captureSnapshot();

    if (dataUrl) {

      this.downloadDataUrl(dataUrl, `optical_preview_${design.width}x${design.height}.png`);

    }

  }



  public exportPerspective(): void {

    const design = designStore.getDesign();

    if (!designStore.canExport() || !design) return;

    const dataUrl = this.dualViewport.perspectiveView?.captureSnapshot();

    if (dataUrl) {

      this.downloadDataUrl(dataUrl, `perspective_capture_${design.width}x${design.height}.png`);

    }

  }



  public exportCsv(): void {

    const stats = designStore.getStats();

    const design = designStore.getDesign();

    if (!designStore.canExport() || !design || !stats) return;



    let csv = 'parameter_type,value,unit,cell_count,percentage\n';

    for (const p of stats.uniquePeriods) {

      const pct = ((p.count / stats.activeCells) * 100).toFixed(2);

      csv += `grating_period,${p.periodNm},nm,${p.count},${pct}%\n`;

    }

    for (const a of stats.uniqueAngles) {

      const pct = ((a.count / stats.activeCells) * 100).toFixed(2);

      csv += `grating_angle,${a.angleDeg.toFixed(2)},deg,${a.count},${pct}%\n`;

    }



    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });

    this.downloadBlob(blob, `parameter_distribution_${design.width}x${design.height}.csv`);

  }



  public exportJson(): void {

    const stats = designStore.getStats();

    const design = designStore.getDesign();

    if (!designStore.canExport() || !design || !stats) return;



    const data = {

      source_identity: design.sourceIdentity,

      grid_shape: [design.height, design.width],

      pitch_nm: design.pitchNm,

      physical_extent_mm: [stats.heightMm, stats.widthMm],

      total_cells: stats.totalCells,

      active_cells: stats.activeCells,

      fill_factor: stats.fillFactor,

      period_distribution: stats.uniquePeriods,

      angle_distribution: stats.uniqueAngles,

    };



    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });

    this.downloadBlob(blob, `design_metadata_${design.width}x${design.height}.json`);

  }

}
