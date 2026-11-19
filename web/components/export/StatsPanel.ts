/**
 * Physical parameter analytics, histograms, and distinct value distribution tables.
 */

import { designStore } from '../../lib/store/designStore';

export class StatsPanel {
  public readonly container: HTMLElement;
  private lastDesign: unknown = Symbol('init');
  private lastStats: unknown = Symbol('init');

  constructor() {
    this.container = document.createElement('div');
    this.container.className = 'stats-panel-container';

    designStore.subscribe(() => {
      this.render();
    });
    this.render();
  }

  public render(): void {
    if (this.container.classList.contains('hidden')) return;

    const stats = designStore.getStats();
    const design = designStore.getDesign();
    if (design === this.lastDesign && stats === this.lastStats) return;
    this.lastDesign = design;
    this.lastStats = stats;

    if (!design || !stats) {
      this.container.innerHTML = `
        <div class="empty-state">
          <p class="text-muted">No design loaded. Load an image or preset to inspect parameter analytics.</p>
        </div>
      `;
      return;
    }

    const fillPercent = (stats.fillFactor * 100).toFixed(1);
    const periodRangeText = stats.activeCells > 0 ? `${stats.minPeriodNm} – ${stats.maxPeriodNm} nm` : '—';

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
          <div class="stat-value">${periodRangeText}</div>
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
                  <th scope="col">Period (nm)</th>
                  <th scope="col">Cell Count</th>
                  <th scope="col">Distribution</th>
                </tr>
              </thead>
              <tbody>
                ${
                  stats.activeCells === 0 || stats.uniquePeriods.length === 0
                    ? `<tr><td colspan="3" class="text-muted text-center">No active cells</td></tr>`
                    : `${stats.uniquePeriods
                        .slice(0, 50)
                        .map((p) => {
                          const pct = stats.activeCells > 0 ? ((p.count / stats.activeCells) * 100).toFixed(1) : '0.0';
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
                        .join('')}${
                        stats.uniquePeriods.length > 50
                          ? `<tr><td colspan="3" class="text-muted text-center">+ ${stats.uniquePeriods.length - 50} more periods (see CSV export)</td></tr>`
                          : ''
                      }`
                }
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
                  <th scope="col">Angle (°)</th>
                  <th scope="col">Cell Count</th>
                  <th scope="col">Distribution</th>
                </tr>
              </thead>
              <tbody>
                ${
                  stats.activeCells === 0 || stats.uniqueAngles.length === 0
                    ? `<tr><td colspan="3" class="text-muted text-center">No active cells</td></tr>`
                    : `${stats.uniqueAngles
                        .slice(0, 50)
                        .map((a) => {
                          const pct = stats.activeCells > 0 ? ((a.count / stats.activeCells) * 100).toFixed(1) : '0.0';
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
                        .join('')}${
                        stats.uniqueAngles.length > 50
                          ? `<tr><td colspan="3" class="text-muted text-center">+ ${stats.uniqueAngles.length - 50} more angles (see CSV export)</td></tr>`
                          : ''
                      }`
                }
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }
}
