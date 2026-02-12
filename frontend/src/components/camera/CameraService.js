export class CameraService {
  constructor(video, opts = {}) {
    if (!video) throw new Error("VIDEO_REQUIRED");

    this.video = video;
    this.stream = null;
    this.isActive = false;

    this.facingMode = opts.facingMode || "environment";

    /* ========= environment detection ========= */

    this.isIOS =
      /iPad|iPhone|iPod/.test(navigator.userAgent);

    this.isSafari =
      /^((?!chrome|android).)*safari/i.test(
        navigator.userAgent
      );

    /* ========= analysis engine ========= */

    this.analysisCanvas =
      document.createElement("canvas");

    this.analysisCtx =
      this.analysisCanvas.getContext("2d", {
        willReadFrequently: true
      });

    this.lastSharpness = null;

    /* ========= video setup ========= */

    video.setAttribute("playsinline", "");
    video.muted = true;
    video.autoplay = true;

    /* ========= recovery binding ========= */

    this._bindLifecycleRecovery();
  }

  /* =================================================
     BROWSER STABILITY LIFECYCLE
  ================================================= */

  _bindLifecycleRecovery() {
    const restart = () => {
      if (this.isActive) this.restart();
    };

    document.addEventListener(
      "visibilitychange",
      restart
    );

    window.addEventListener(
      "orientationchange",
      restart
    );
  }

  /* =================================================
     CAMERA START WITH FALLBACK
  ================================================= */

  async start() {
    if (!navigator.mediaDevices?.getUserMedia)
      throw new Error("UNSUPPORTED_BROWSER");

    const ladder = this._constraintLadder();

    let lastError;

    for (const constraints of ladder) {
      try {
        const stream =
          await navigator.mediaDevices.getUserMedia(
            constraints
          );

        this.stream = stream;
        this.video.srcObject = stream;

        await this._safePlay();

        stream
          .getVideoTracks()[0]
          .addEventListener("ended", () =>
            this.restart()
          );

        this.isActive = true;

        return;
      } catch (e) {
        lastError = e;
      }
    }

    throw lastError;
  }

  async _safePlay() {
    try {
      await this.video.play();
    } catch {
      // iOS retry loop
      await new Promise(r => setTimeout(r, 120));
      await this.video.play();
    }
  }

  _constraintLadder() {
    const presets = [
      { w: 1920, h: 1080 },
      { w: 1280, h: 720 },
      { w: 640, h: 480 }
    ];

    const ladder = presets.map(p => ({
      video: {
        width: { ideal: p.w },
        height: { ideal: p.h },
        facingMode: { ideal: this.facingMode }
      },
      audio: false
    }));

    ladder.push({ video: true, audio: false });

    return ladder;
  }

  /* =================================================
     STOP / RESTART
  ================================================= */

  stop() {
    if (!this.stream) return;

    this.stream
      .getTracks()
      .forEach(t => t.stop());

    this.video.srcObject = null;
    this.stream = null;
    this.isActive = false;
  }

  async restart() {
    this.stop();

    // iOS requires cooldown
    await new Promise(r =>
      setTimeout(r, this.isIOS ? 200 : 80)
    );

    await this.start();
  }

  /* =================================================
     READINESS
  ================================================= */

  ready() {
    return (
      this.isActive &&
      this.video.videoWidth > 0 &&
      this.video.readyState >= 2
    );
  }

  /* =================================================
     GUIDE ANALYSIS ENGINE
  ================================================= */

  analyze() {
    if (!this.ready())
      return {
        ok: false,
        reason: "NOT_READY"
      };

    const w = 160;
    const h = 120;

    this.analysisCanvas.width = w;
    this.analysisCanvas.height = h;

    this.analysisCtx.drawImage(
      this.video,
      0,
      0,
      w,
      h
    );

    const frame =
      this.analysisCtx.getImageData(
        0,
        0,
        w,
        h
      );

    const d = frame.data;

    let brightness = 0;
    let sharpness = 0;

    for (let i = 4; i < d.length; i += 4) {
      brightness +=
        0.2126 * d[i] +
        0.7152 * d[i + 1] +
        0.0722 * d[i + 2];

      sharpness += Math.abs(
        d[i] - d[i - 4]
      );
    }

    brightness /= d.length / 4;
    sharpness /= d.length / 4;

    const shaken =
      this.lastSharpness !== null &&
      Math.abs(
        sharpness - this.lastSharpness
      ) > 20;

    this.lastSharpness = sharpness;

    if (brightness < 60)
      return {
        ok: false,
        reason: "TOO_DARK"
      };

    if (sharpness < 15)
      return {
        ok: false,
        reason: "BLURRY"
      };

    if (shaken)
      return {
        ok: false,
        reason: "SHAKING"
      };

    return { ok: true };
  }

  /* =================================================
     SAFE CAPTURE
  ================================================= */

  async capture() {
    if (!this.ready())
      throw new Error("NOT_READY");

    const MAX = 1920;

    let w = this.video.videoWidth;
    let h = this.video.videoHeight;

    if (w > MAX) {
      const scale = MAX / w;
      w *= scale;
      h *= scale;
    }

    const canvas =
      document.createElement("canvas");

    canvas.width = w;
    canvas.height = h;

    const ctx =
      canvas.getContext("2d");

    ctx.drawImage(
      this.video,
      0,
      0,
      w,
      h
    );

    const blob =
      await new Promise((res, rej) =>
        canvas.toBlob(
          b => (b ? res(b) : rej()),
          "image/jpeg",
          0.95
        )
      );

    return new File(
      [blob],
      `capture_${Date.now()}.jpg`,
      { type: "image/jpeg" }
    );
  }
}