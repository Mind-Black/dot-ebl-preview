/**
 * Physical parameter analytics, histograms, and distinct value distribution tables.
 */

import { designStore } from '../../lib/store/designStore';

export class StatsPanel {
  public readonly container: HTMLElement;

  constructor() {
    this.container = document.createElement('div');
    this.container.className = 'stats-panel-container';

    designStore.subscribe(() => {
      this.render();
    });
    this.render();
  }

  public render(): void {
    const stats = designStore.getStats();
    const design = designStore.getDesign();

    if (!design || !stats) {
      this.container.innerHTML = `
        <div class="empty-state">
          <p class="text-muted">No design loaded. Load an image or preset to inspect parameter analytics.</p>
        </div>
      `;
      return;
    }

    const fillPercent = (stats.fillFactor * 100).toFixed(1);

    this.container.innerHTML = `
      <div class="stats-overview-grid">
        <div class="stat-card">
          <div class="stat-label">Grid Shape</div>
          <div class="stat-value">${design.width} × ${design.height}</div>
          <div class="stat-sub">${stats.totalCells.toLocaleString()} cells</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Physical Dimensions</div>
          <div class="stat-value">${stats.widthMm.toFixed(2)} × ${stats.heightMm.toFixed(2)} mm</div>
          <div class="stat-sub">Pitch: ${(design.pitchNm / 1000).toFixed(1)} µm</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Active Cells</div>
          <div class="stat-value">${stats.activeCells.toLocaleString()}</div>
          <div class="stat-sub">${fillPercent}% fill factor</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Period Range</div>
          <div class="stat-value">${stats.minPeriodNm} – ${stats.maxPeriodNm} nm</div>
          <div class="stat-sub">${stats.uniquePeriods.length} unique periods</div>
        </div>
      </div>

      <div class="stats-tables-grid mt-4">
        <div class="table-card">
          <h4 class="card-subtitle">Active Grating Periods</h4>
          <div class="table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Period (nm)</th>
                  <th>Cell Count</th>
                  <th>Distribution</th>
                </tr>
              </thead>
              <tbody>
                ${stats.uniquePeriods
                  .map((p) => {
                    const pct = ((p.count / stats.activeCells) * 100).toFixed(1);
                    return `
                      <tr>
                        <td><strong>${p.periodNm} nm</strong></td>
                        <td>${p.count.toLocaleString()}</td>
                        <td>
                          <div class="distribution-bar-wrapper">
                            <div class="bar-fill" style="width: ${pct}%"></div>
                            <span class="pct-label">${pct}%</span>
                          </div>
                        </td>
                      </tr>
                    `;
                  })
                  .join('')}
              </tbody>
            </table>
          </div>
        </div>

        <div class="table-card">
          <h4 class="card-subtitle">Active Grating Angles</h4>
          <div class="table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Angle (°)</th>
                  <th>Cell Count</th>
                  <th>Distribution</th>
                </tr>
              </thead>
              <tbody>
                ${stats.uniqueAngles
                  .slice(0, 50)
                  .map((a) => {
                    const pct = ((a.count / stats.activeCells) * 100).toFixed(1);
                    return `
                      <tr>
                        <td><strong>${a.angleDeg.toFixed(2)}°</strong></td>
                        <td>${a.count.toLocaleString()}</td>
                        <td>
                          <div class="distribution-bar-wrapper">
                            <div class="bar-fill angle-bar" style="width: ${pct}%"></div>
                            <span class="pct-label">${pct}%</span>
                          </div>
                        </td>
                      </tr>
                    `;
                  })
                  .join('')}
                ${
                  stats.uniqueAngles.length > 50
                    ? `<tr><td colspan="3" class="text-muted text-center">+ ${stats.uniqueAngles.length - 50} more angles (see CSV export)</td></tr>`
                    : ''
                }
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }
}
