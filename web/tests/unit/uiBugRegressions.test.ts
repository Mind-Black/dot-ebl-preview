import { afterEach, describe, expect, it, vi } from 'vitest';
import { DesignStore } from '@/lib/store/designStore';
import { createConcentricTestPattern } from '@/lib/presets/sampleDesigns';
import type { DesignModel, RawImageSource } from '@/lib/decoders/types';

function makeDesign(sourceIdentity = 'sample.png'): DesignModel {
  return {
    width: 1,
    height: 1,
    pitchNm: 20000,
    periodNm: new Uint32Array([1000]),
    angleDeg: new Float64Array([25]),
    active: new Uint8Array([1]),
    sourceIdentity,
  };
}

function makeSourcePreview(filename = 'sample.png'): RawImageSource {
  return {
    width: 2,
    height: 2,
    channels: 3,
    bitDepth: 8,
    data: new Uint8Array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]),
    filename,
  };
}

function stubWorkerQueue() {
  const workers: Array<{
    onmessage: ((ev: { data: any }) => void) | null;
    onerror: (() => void) | null;
    messages: any[];
    terminated: boolean;
    postMessage: (m: any) => void;
    terminate: () => void;
  }> = [];

  class WorkerMock {
    onmessage: ((ev: { data: any }) => void) | null = null;
    onerror: (() => void) | null = null;
    messages: any[] = [];
    terminated = false;
    constructor() {
      workers.push(this);
    }
    postMessage(m: any) {
      this.messages.push(m);
    }
    terminate() {
      this.terminated = true;
    }
  }

  vi.stubGlobal('Worker', WorkerMock);
  return workers;
}

describe('DesignStore UI/UX bug regressions', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('stores sourcePreview on image loadFile, preserves it on failed staged import, and clears it on NPZ or setPhysicalDesign', () => {
    const workers = stubWorkerQueue();
    const store = new DesignStore();

    // 1. Load an image file that returns sourcePreview
    const preview = makeSourcePreview('hls_test.png');
    store.loadFile({ name: 'hls_test.png' } as File, 'Holtida legacy HLS');
    workers[0].onmessage?.({
      data: {
        id: 1,
        design: makeDesign('hls_test.png'),
        stats: {},
        sourcePreview: preview,
      },
    });
    expect(store.getSource()).toBe(preview);

    // 2. Failed staged import preserves the prior sourcePreview
    store.loadFile({ name: 'broken.png' } as File, 'RGBA continuous');
    workers[1].onmessage?.({
      data: { id: 1, error: 'Corrupted PNG' },
    });
    expect(store.getSource()).toBe(preview);
    expect(store.hasImportError()).toBe(true);

    // 3. Loading an NPZ file clears sourcePreview
    store.loadFile({ name: 'design.npz' } as File, 'RGBA continuous');
    workers[2].onmessage?.({
      data: {
        id: 1,
        design: makeDesign('design.npz'),
        stats: {},
        physical: true,
      },
    });
    expect(store.getSource()).toBeNull();
    expect(store.getInterpretation()).toBe('NPZ design');

    // 4. Reload an image with sourcePreview, then call setPhysicalDesign() -> clears sourcePreview
    const preview2 = makeSourcePreview('second.png');
    store.loadFile({ name: 'second.png' } as File, 'RGBA continuous');
    workers[3].onmessage?.({
      data: {
        id: 1,
        design: makeDesign('second.png'),
        stats: {},
        sourcePreview: preview2,
      },
    });
    expect(store.getSource()).toBe(preview2);

    store.setPhysicalDesign(createConcentricTestPattern(8));
    expect(store.getSource()).toBeNull();
  });

  it('distinguishes import failures from RGBA bound validation errors via hasImportError and canRetryImport', () => {
    const workers = stubWorkerQueue();
    const store = new DesignStore();

    // Load a valid image design first
    store.loadFile({ name: 'valid.png' } as File, 'RGBA continuous');
    workers[0].onmessage?.({
      data: {
        id: 1,
        design: makeDesign('valid.png'),
        stats: {},
        sourcePreview: makeSourcePreview('valid.png'),
      },
    });
    expect(store.hasImportError()).toBe(false);
    expect(store.canRetryImport()).toBe(false);

    // Trigger RGBA bound validation error (min >= max)
    store.setRgbaOptions({ minPeriodNm: 1600, maxPeriodNm: 400 });
    expect(store.getError()).toBe('Minimum must be less than maximum');
    expect(store.hasImportError()).toBe(false);
    expect(store.canRetryImport()).toBe(false);

    // Clear RGBA validation error with valid bounds
    store.setRgbaOptions({ minPeriodNm: 400, maxPeriodNm: 1600 });
    expect(store.getError()).toBeNull();

    // Now trigger an actual staged import failure
    store.loadFile({ name: 'bad.png' } as File, 'RGBA continuous');
    workers[1].onmessage?.({
      data: { id: 1, error: 'Invalid PNG signature' },
    });
    expect(store.getError()).toContain('bad.png');
    expect(store.hasImportError()).toBe(true);
    expect(store.canRetryImport()).toBe(true);

    // Clear import error
    store.clearError();
    expect(store.getError()).toBeNull();
    expect(store.hasImportError()).toBe(false);
    expect(store.canRetryImport()).toBe(false);
  });

  it('clears a prior "Minimum must be less than maximum" error once valid bounds are provided, even when physical === true', () => {
    const store = new DesignStore();
    store.setPhysicalDesign(createConcentricTestPattern(8));

    store.setRgbaOptions({ minAngleDeg: 90, maxAngleDeg: -90 });
    expect(store.getError()).toBe('Minimum must be less than maximum');
    expect(store.hasImportError()).toBe(false);
    expect(store.canRetryImport()).toBe(false);

    let notified = 0;
    const unsubscribe = store.subscribe(() => {
      notified++;
    });

    store.setRgbaOptions({ minAngleDeg: -90, maxAngleDeg: 90 });
    expect(store.getError()).toBeNull();
    expect(store.getRgbaOptions().minAngleDeg).toBe(-90);
    expect(store.getRgbaOptions().maxAngleDeg).toBe(90);
    expect(notified).toBe(1);

    unsubscribe();
  });
});
