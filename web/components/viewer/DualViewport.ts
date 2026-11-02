/**
 * Dual-Viewport container housing the 3D Perspective Surface View and Flat 2D Reference View.
 */

import { FlatView } from './FlatView';
import { PerspectiveView, type HoverCellInfo } from './PerspectiveView';
import { sceneStore } from '../../lib/store/sceneStore';

export class DualViewport {
  public readonly element: HTMLElement;
  public readonly perspectiveView: PerspectiveView | null;
  public readonly flatView: FlatView;

  private viewMode: 'perspective' | 'flat' | 'split' = 'flat';
  private hoverPill: HTMLElement;
  private qualityBadge: HTMLElement;

  constructor() {
    this.element = document.createElement('section');
    this.element.className = 'dual-viewport-hero';

    // Toolbar Header
    const toolbar = document.createElement('div');
    toolbar.className = 'viewport-toolbar';

    const tabGroup = document.createElement('div');
    tabGroup.className = 'btn-group';

    const btnPerspective = document.createElement('button');
    btnPerspective.className = 'btn btn-sm';
    btnPerspective.textContent = '3D Perspective';
    btnPerspective.disabled = true;
    btnPerspective.title = '3D Perspective view is disabled for now';

    const btnFlat = document.createElement('button');
    btnFlat.className = 'btn btn-sm btn-active';
    btnFlat.textContent = 'Flat 2D Reference';

    const btnSplit = document.createElement('button');
    btnSplit.className = 'btn btn-sm';
    btnSplit.textContent = 'Side-by-Side';
    btnSplit.disabled = true;
    btnSplit.title = 'Side-by-Side view is disabled for now';

    tabGroup.append(btnPerspective, btnFlat, btnSplit);

    const fitBtn = document.createElement('button');
    fitBtn.className = 'btn btn-sm btn-outline';
    fitBtn.textContent = 'Fit View';
    fitBtn.onclick = () => {
      if (this.viewMode === 'perspective' || this.viewMode === 'split') {
        this.perspectiveView?.fitView();
      }
      if (this.viewMode === 'flat' || this.viewMode === 'split') {
        this.flatView.resetFit();
      }
    };

    this.qualityBadge = document.createElement('span');
    this.qualityBadge.className = 'badge badge-quality';
    this.updateQualityBadge();

    toolbar.append(tabGroup, fitBtn, this.qualityBadge);

    // Viewports container
    const viewportsWrapper = document.createElement('div');
    viewportsWrapper.className = 'viewports-wrapper mode-flat';

    const onHover = (info: HoverCellInfo | null) => this.updateHoverPill(info);
    try { this.perspectiveView = new PerspectiveView(onHover); } catch { this.perspectiveView = null; }
    this.flatView = new FlatView(onHover);

    if(this.perspectiveView) viewportsWrapper.append(this.perspectiveView.container);
    viewportsWrapper.append(this.flatView.container);

    // Footer overlay with hover info and controls hint
    const footer = document.createElement('div');
    footer.className = 'viewport-footer';

    this.hoverPill = document.createElement('div');
    this.hoverPill.className = 'hover-probe-pill';
    this.hoverPill.textContent = 'Hover over surface to inspect cell parameters';

    const hints = document.createElement('div');
    hints.className = 'interaction-hints';

    const updateHints = (mode: 'perspective' | 'flat' | 'split') => {
      if (mode === 'flat') {
        hints.innerHTML = `
          <span><kbd>Left-drag</kbd> Pan View</span>
          <span><kbd>Wheel</kbd> Zoom</span>
        `;
      } else {
        hints.innerHTML = `
          <span><kbd>Left-drag</kbd> Orbit Camera</span>
          <span><kbd>Right-drag</kbd> Orbit Light</span>
          <span><kbd>Wheel</kbd> Distance</span>
        `;
      }
    };
    updateHints('flat');

    footer.append(this.hoverPill, hints);

    this.element.append(toolbar, viewportsWrapper, footer);

    // Switch view modes
    const setMode = (mode: 'perspective' | 'flat' | 'split') => {
      // Perspective and side-by-side views are disabled for now
      if ((mode as string) !== 'flat') {
        return;
      }
      this.viewMode = mode;
      btnPerspective.classList.toggle('btn-active', false);
      btnFlat.classList.toggle('btn-active', true);
      btnSplit.classList.toggle('btn-active', false);

      viewportsWrapper.className = `viewports-wrapper mode-${mode}`;
      updateHints(mode);
      this.flatView.resetFit();
    };

    btnPerspective.onclick = () => setMode('perspective');
    btnFlat.onclick = () => setMode('flat');
    btnSplit.onclick = () => setMode('split');

    sceneStore.subscribe(() => {
      this.updateQualityBadge();
    });
  }

  public getViewMode(): 'perspective' | 'flat' | 'split' {
    return this.viewMode;
  }

  private updateQualityBadge(): void {
    const q = sceneStore.getQuality();
    const interacting = sceneStore.getIsInteracting();
    let text = q === 'high' ? 'High (77 bands)' : q === 'balanced' ? 'Balanced (39 bands)' : 'Performance (19 bands)';
    if (interacting) {
      text += ' [Interacting]';
    }
    this.qualityBadge.textContent = text;
  }

  private updateHoverPill(info: HoverCellInfo | null): void {
    if (!info) {
      this.hoverPill.textContent = 'Hover over surface to inspect cell parameters';
      this.hoverPill.classList.remove('has-data');
      return;
    }

    this.hoverPill.classList.add('has-data');
    if (!info.active) {
      this.hoverPill.innerHTML = `
        <strong>Cell (${info.row}, ${info.col})</strong>:
        <span>x=${info.xMm.toFixed(3)} mm, y=${info.yMm.toFixed(3)} mm</span> |
        <span class="text-muted">Inactive (no grating)</span>
      `;
    } else {
      this.hoverPill.innerHTML = `
        <strong>Cell (${info.row}, ${info.col})</strong>:
        <span>x=${info.xMm.toFixed(3)} mm, y=${info.yMm.toFixed(3)} mm</span> |
        <span>Period: <strong>${info.periodNm} nm</strong></span> |
        <span>Stored: <strong>${info.angleDeg.toFixed(2)}°</strong></span> |
        <span>Effective: <strong>${info.effectiveAngleDeg.toFixed(2)}°</strong></span>
      `;
    }
  }

  public dispose(): void {
    this.perspectiveView?.dispose();
    this.flatView.dispose();
  }
}
