/**
 * Web Application Entry Point.
 * Coordinates landing WelcomeView and Dual-Viewport Workbench UI.
 */

import { DualViewport } from './components/viewer/DualViewport';
import { ParameterMapCanvas } from './components/controls/ParameterMapCanvas';
import { DesignControls } from './components/controls/DesignControls';
import { SceneControls } from './components/controls/SceneControls';
import { StatsPanel } from './components/export/StatsPanel';
import { ExportControls } from './components/export/ExportControls';
import { WelcomeView } from './components/welcome/WelcomeView';
import { WebGlDiffractionRenderer } from './lib/optics/glRenderer';
import { designStore } from './lib/store/designStore';
import { sceneStore } from './lib/store/sceneStore';

class DotEblApp {
  private root: HTMLElement;
  private welcomeView: WelcomeView;
  private dualViewport: DualViewport;
  private designControls: DesignControls;
  private sceneControls: SceneControls;
  private statsPanel: StatsPanel;
  private exportControls: ExportControls;

  private periodMapCanvas: ParameterMapCanvas;
  private angleMapCanvas: ParameterMapCanvas;
  private sourceMapCanvas: ParameterMapCanvas;

  private workbenchElement: HTMLElement;
  public isWelcomeState = true;

  constructor() {
    const root = document.getElementById('app-root');
    if (!root) throw new Error('Missing #app-root element in DOM.');
    this.root = root;

    // 1. Initialize components
    this.dualViewport = new DualViewport();
    this.designControls = new DesignControls();
    this.sceneControls = new SceneControls();
    this.statsPanel = new StatsPanel();
    this.exportControls = new ExportControls(this.dualViewport);

    this.periodMapCanvas = new ParameterMapCanvas('periods');
    this.angleMapCanvas = new ParameterMapCanvas('angles');
    this.sourceMapCanvas = new ParameterMapCanvas('source');

    // 2. Build workbench layout
    this.workbenchElement = document.createElement('div');
    this.workbenchElement.className = 'workbench-container hidden';

    const sidebar = document.createElement('aside');
    sidebar.className = 'workbench-sidebar';

    // 2D Inspector tab navigation
    const tabsNav = document.createElement('nav');
    tabsNav.className = 'sidebar-tabs'; tabsNav.setAttribute('role','tablist'); tabsNav.setAttribute('aria-label','Inspector');

    const tabButtons: { id: 'periods' | 'angles' | 'source' | 'analytics'; label: string }[] = [
      { id: 'periods', label: 'Period Map' },
      { id: 'angles', label: 'Angle Map' },
      { id: 'source', label: 'Source Image' },
      { id: 'analytics', label: 'Analytics' },
    ];

    const tabPanelsWrapper = document.createElement('div');
    tabPanelsWrapper.className = 'inspector-panels mb-4';

    const updateActiveTab = (tabId: 'periods' | 'angles' | 'source' | 'analytics') => {
      sceneStore.setActiveTab(tabId);
      tabButtons.forEach((t) => {
        const btn = tabsNav.querySelector(`[data-tab="${t.id}"]`);
        btn?.classList.toggle('active', t.id === tabId); btn?.setAttribute('aria-selected', String(t.id === tabId)); btn?.setAttribute('tabindex', t.id === tabId ? '0' : '-1');
      });

      this.periodMapCanvas.container.classList.toggle('hidden', tabId !== 'periods');
      this.angleMapCanvas.container.classList.toggle('hidden', tabId !== 'angles');
      this.sourceMapCanvas.container.classList.toggle('hidden', tabId !== 'source');
      this.statsPanel.container.classList.toggle('hidden', tabId !== 'analytics');

      if (tabId === 'periods') this.periodMapCanvas.render();
      if (tabId === 'angles') this.angleMapCanvas.render();
      if (tabId === 'source') this.sourceMapCanvas.render();
      if (tabId === 'analytics') this.statsPanel.render();
    };

    for (const t of tabButtons) {
      const btn = document.createElement('button');
      btn.className = `sidebar-tab-btn ${t.id === 'periods' ? 'active' : ''}`;
      btn.textContent = t.label;
      btn.dataset.tab = t.id;
      btn.id = `tab-${t.id}`; btn.setAttribute('role','tab'); btn.setAttribute('aria-controls',`panel-${t.id}`);
      btn.setAttribute('aria-selected',String(t.id==='periods')); btn.tabIndex=t.id==='periods'?0:-1;
      btn.onkeydown = e => { const i=tabButtons.indexOf(t); const next=e.key==='Home'?0:e.key==='End'?3:e.key==='ArrowRight'?(i+1)%4:e.key==='ArrowLeft'?(i+3)%4:-1; if(next<0)return; e.preventDefault(); updateActiveTab(tabButtons[next].id); (tabsNav.children[next] as HTMLElement).focus(); };
      btn.onclick = () => updateActiveTab(t.id);
      tabsNav.appendChild(btn);
    }

    tabPanelsWrapper.append(
      this.periodMapCanvas.container,
      this.angleMapCanvas.container,
      this.sourceMapCanvas.container,
      this.statsPanel.container
    );
    Array.from(tabPanelsWrapper.children).forEach((panel,i)=>{panel.id=`panel-${tabButtons[i].id}`; panel.setAttribute('role','tabpanel'); panel.setAttribute('aria-labelledby',`tab-${tabButtons[i].id}`);});
    // Initial hidden state for inactive tabs
    this.angleMapCanvas.container.classList.add('hidden');
    this.sourceMapCanvas.container.classList.add('hidden');
    this.statsPanel.container.classList.add('hidden');

    const sidebarContent = document.createElement('div');
    sidebarContent.className = 'sidebar-content';
    sidebarContent.append(
      tabsNav,
      tabPanelsWrapper,
      this.designControls.element,
      this.sceneControls.element,
      this.exportControls.element
    );

    sidebar.appendChild(sidebarContent);
    this.workbenchElement.append(this.dualViewport.element, sidebar);

    // 3. Welcome View
    this.welcomeView = new WelcomeView(() => {
      this.showWorkbench();
    });

    this.root.append(this.welcomeView.element, this.workbenchElement);

    // Header actions
    const headerWelcomeBtn = document.getElementById('header-welcome-btn');
    if (headerWelcomeBtn) {
      headerWelcomeBtn.onclick = () => {
        this.showWelcome();
      };
    }
  }

  public showWorkbench(): void {
    this.isWelcomeState = false;
    this.welcomeView.element.classList.add('hidden');
    this.workbenchElement.classList.remove('hidden');
    const heading=this.designControls.element.querySelector('h2')!; heading.tabIndex=-1; heading.focus();
    if (this.dualViewport.getViewMode() !== 'flat') {
      this.dualViewport.perspectiveView?.fitView();
    }
    this.dualViewport.flatView.resetFit();
  }

  public showWelcome(): void {
    this.isWelcomeState = true;
    this.workbenchElement.classList.add('hidden');
    this.welcomeView.element.classList.remove('hidden');
    const heading=this.welcomeView.element.querySelector('h1')!; heading.tabIndex=-1; heading.focus();
  }
}

// Start application
window.addEventListener('DOMContentLoaded', () => {
  const app = new DotEblApp();
  (window as unknown as Record<string, unknown>).__DOT_EBL_APP__ = app;
  (window as unknown as Record<string, unknown>).__DOT_EBL_MODULES__ = {
    designStore,
    sceneStore,
    WebGlDiffractionRenderer,
  };
});
