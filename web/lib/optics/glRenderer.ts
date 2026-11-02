/**
 * High-performance WebGL2 offscreen / onscreen diffraction renderer.
 * Manages RGBA32F data textures, spectral tables, multi-light uniforms, and framebuffer targets.
 */

import { OPTICS_VERTEX_SHADER, OPTICS_FRAGMENT_SHADER } from './shaders';
import { getSpectralConfig, type QualityLevel, type SpectralConfig } from './tables';
import type { DesignModel } from '../decoders/types';
import type { Point3D } from './coordinates';

export interface LightSettings {
  pos: Point3D;
  sourceRadiusMm: number;
  intensity: number;
}

export interface RenderSceneParams {
  cameraPos: Point3D;
  apertureRadiusMm: number;
  orientationDeg: number;
  lights: LightSettings[];
  quality: QualityLevel;
  downsampleFactor?: number; // 1.0 for full quality, 0.5 during active drag
}

export class WebGlDiffractionRenderer {
  public readonly gl: WebGL2RenderingContext;
  private program: WebGLProgram;
  private vao: WebGLVertexArrayObject;
  private designTexture: WebGLTexture;
  private spectrumTexture: WebGLTexture;
  private colorTexture: WebGLTexture | null = null;
  private framebuffer: WebGLFramebuffer | null = null;

  private uniformLocations: Record<string, WebGLUniformLocation | null> = {};

  private currentDesign: DesignModel | null = null;
  private currentTargetWidth = 0;
  private currentTargetHeight = 0;
  private currentQuality: QualityLevel = 'balanced';

  constructor(canvasOrGl?: HTMLCanvasElement | OffscreenCanvas | WebGL2RenderingContext) {
    if (canvasOrGl instanceof WebGL2RenderingContext) {
      this.gl = canvasOrGl;
    } else {
      const canvas = canvasOrGl || (typeof OffscreenCanvas !== 'undefined' ? new OffscreenCanvas(16, 16) : document.createElement('canvas'));
      const gl = canvas.getContext('webgl2', {
        alpha: false,
        antialias: false,
        depth: false,
        stencil: false,
        premultipliedAlpha: false,
        preserveDrawingBuffer: true,
      });
      if (!gl) {
        throw new Error('WebGL2 is not supported in this browser. Please use a WebGL2-compatible browser.');
      }
      this.gl = gl;
    }

    const gl = this.gl;

    // Check float texture support
    const extColorBufferFloat = gl.getExtension('EXT_color_buffer_float');
    // Note: RGBA32F texture sampling is native in WebGL2; EXT_color_buffer_float is only needed if rendering TO float textures.
    if (!extColorBufferFloat) {
      // Still fully functional because we render to standard RGBA8 color targets!
    }

    // Compile shaders
    this.program = this.createProgram(OPTICS_VERTEX_SHADER, OPTICS_FRAGMENT_SHADER);
    this.vao = gl.createVertexArray()!;

    // Create textures
    this.designTexture = gl.createTexture()!;
    this.spectrumTexture = gl.createTexture()!;
    this.framebuffer = gl.createFramebuffer()!;
    this.colorTexture = gl.createTexture()!;

    this.cacheUniformLocations();
    this.uploadSpectrum(this.currentQuality);
  }

  private createShader(type: number, source: string): WebGLShader {
    const gl = this.gl;
    const shader = gl.createShader(type)!;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const info = gl.getShaderInfoLog(shader);
      gl.deleteShader(shader);
      throw new Error(`Shader compilation failed: ${info}`);
    }
    return shader;
  }

  private createProgram(vsSource: string, fsSource: string): WebGLProgram {
    const gl = this.gl;
    const vs = this.createShader(gl.VERTEX_SHADER, vsSource);
    const fs = this.createShader(gl.FRAGMENT_SHADER, fsSource);
    const prog = gl.createProgram()!;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      const info = gl.getProgramInfoLog(prog);
      gl.deleteProgram(prog);
      throw new Error(`Program linking failed: ${info}`);
    }
    return prog;
  }

  private cacheUniformLocations(): void {
    const gl = this.gl;
    const names = [
      'u_design',
      'u_spectrum',
      'u_size',
      'u_target_size',
      'u_pitch_mm',
      'u_orientation_deg',
      'u_num_lights',
      'u_camera_pos',
      'u_aperture_mm',
      'u_light_y',
      'u_white_xy',
      'u_num_bands',
      'u_start_wavelength_nm',
      'u_wavelength_step_nm',
    ];
    for (const name of names) {
      this.uniformLocations[name] = gl.getUniformLocation(this.program, name);
    }
    for (let i = 0; i < 8; i++) {
      this.uniformLocations[`u_light_pos_${i}`] = gl.getUniformLocation(this.program, `u_light_pos[${i}]`);
      this.uniformLocations[`u_source_size_mm_${i}`] = gl.getUniformLocation(this.program, `u_source_size_mm[${i}]`);
      this.uniformLocations[`u_light_intensity_${i}`] = gl.getUniformLocation(this.program, `u_light_intensity[${i}]`);
    }
  }

  public uploadSpectrum(quality: QualityLevel): void {
    const gl = this.gl;
    const config: SpectralConfig = getSpectralConfig(quality);
    this.currentQuality = quality;

    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.spectrumTexture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      gl.RGBA32F,
      config.numBands,
      1,
      0,
      gl.RGBA,
      gl.FLOAT,
      config.premultipliedXyz
    );
  }

  public uploadDesign(design: DesignModel): void {
    const gl = this.gl;
    const { width, height, periodNm, angleDeg, active, fallbackIntensity } = design;

    if (design === this.currentDesign) {
      return;
    }

    const totalCells = width * height;
    const packed = new Float32Array(totalCells * 4);

    for (let i = 0; i < totalCells; i++) {
      packed[i * 4 + 0] = periodNm[i];
      packed[i * 4 + 1] = angleDeg[i];
      packed[i * 4 + 2] = active[i];
      packed[i * 4 + 3] = fallbackIntensity ? fallbackIntensity[i] : 0.0;
    }

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.designTexture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      gl.RGBA32F,
      width,
      height,
      0,
      gl.RGBA,
      gl.FLOAT,
      packed
    );

    this.currentDesign = design;
  }

  public render(
    design: DesignModel,
    params: RenderSceneParams,
    targetCanvas?: HTMLCanvasElement | OffscreenCanvas
  ): void {
    const gl = this.gl;
    this.uploadDesign(design);

    if (params.quality !== this.currentQuality) {
      this.uploadSpectrum(params.quality);
    }
    const specConfig = getSpectralConfig(params.quality);

    const downsample = params.downsampleFactor || 1.0;
    const targetW = Math.max(1, Math.round(design.width * downsample));
    const targetH = Math.max(1, Math.round(design.height * downsample));

    if (targetCanvas) {
      if (targetCanvas.width !== targetW || targetCanvas.height !== targetH) {
        targetCanvas.width = targetW;
        targetCanvas.height = targetH;
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, targetW, targetH);
    } else {
      if (this.currentTargetWidth !== targetW || this.currentTargetHeight !== targetH) {
        gl.bindTexture(gl.TEXTURE_2D, this.colorTexture);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texImage2D(
          gl.TEXTURE_2D,
          0,
          gl.RGBA8,
          targetW,
          targetH,
          0,
          gl.RGBA,
          gl.UNSIGNED_BYTE,
          null
        );

        gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
        gl.framebufferTexture2D(
          gl.FRAMEBUFFER,
          gl.COLOR_ATTACHMENT0,
          gl.TEXTURE_2D,
          this.colorTexture,
          0
        );

        const status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
        if (status !== gl.FRAMEBUFFER_COMPLETE) {
          throw new Error(`Framebuffer incomplete: status ${status}`);
        }

        this.currentTargetWidth = targetW;
        this.currentTargetHeight = targetH;
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
      gl.viewport(0, 0, targetW, targetH);
    }

    gl.useProgram(this.program);
    gl.bindVertexArray(this.vao);

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.designTexture);
    gl.uniform1i(this.uniformLocations['u_design'], 0);

    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.spectrumTexture);
    gl.uniform1i(this.uniformLocations['u_spectrum'], 1);

    gl.uniform2i(this.uniformLocations['u_size'], design.width, design.height);
    gl.uniform2i(this.uniformLocations['u_target_size'], targetW, targetH);
    gl.uniform1f(this.uniformLocations['u_pitch_mm'], design.pitchNm * 1e-6);
    gl.uniform1f(this.uniformLocations['u_orientation_deg'], params.orientationDeg);

    gl.uniform3f(
      this.uniformLocations['u_camera_pos'],
      params.cameraPos.x,
      params.cameraPos.y,
      params.cameraPos.z
    );
    gl.uniform1f(this.uniformLocations['u_aperture_mm'], params.apertureRadiusMm);

    // Spectrum config uniforms
    gl.uniform1f(this.uniformLocations['u_light_y'], specConfig.lightY);
    gl.uniform2f(this.uniformLocations['u_white_xy'], specConfig.whiteXy[0], specConfig.whiteXy[1]);
    gl.uniform1i(this.uniformLocations['u_num_bands'], specConfig.numBands);
    gl.uniform1f(this.uniformLocations['u_start_wavelength_nm'], 380.0);
    gl.uniform1f(this.uniformLocations['u_wavelength_step_nm'], specConfig.wavelengthStepNm);

    // Light uniforms
    const numLights = Math.min(8, params.lights.length);
    gl.uniform1i(this.uniformLocations['u_num_lights'], numLights);

    for (let i = 0; i < numLights; i++) {
      const l = params.lights[i];
      gl.uniform3f(this.uniformLocations[`u_light_pos_${i}`], l.pos.x, l.pos.y, l.pos.z);
      gl.uniform1f(this.uniformLocations[`u_source_size_mm_${i}`], l.sourceRadiusMm);
      gl.uniform1f(this.uniformLocations[`u_light_intensity_${i}`], l.intensity);
    }

    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.flush();
  }

  public readPixelsRgba(width = this.currentTargetWidth, height = this.currentTargetHeight): Uint8Array {
    const gl = this.gl;
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
    const pixels = new Uint8Array(width * height * 4);
    gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    return pixels;
  }

  public getOutputTexture(): WebGLTexture | null {
    return this.colorTexture;
  }

  public dispose(): void {
    const gl = this.gl;
    if (this.program) gl.deleteProgram(this.program);
    if (this.vao) gl.deleteVertexArray(this.vao);
    if (this.designTexture) gl.deleteTexture(this.designTexture);
    if (this.spectrumTexture) gl.deleteTexture(this.spectrumTexture);
    if (this.colorTexture) gl.deleteTexture(this.colorTexture);
    if (this.framebuffer) gl.deleteFramebuffer(this.framebuffer);
  }
}
