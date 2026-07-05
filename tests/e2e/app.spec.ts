import { expect, test } from "@playwright/test";
import path from "node:path";

test("stop live capture ends microphone input but keeps processing captured audio", async ({
  page
}) => {
  await page.addInitScript(() => {
    class FakeAnalyserNode {
      fftSize = 256;
      frequencyBinCount = 32;

      getByteFrequencyData(buffer: Uint8Array) {
        buffer.fill(96);
      }
    }

    class FakeAudioContext {
      createMediaStreamSource() {
        return {
          connect() {}
        };
      }

      createAnalyser() {
        return new FakeAnalyserNode();
      }

      close() {
        return Promise.resolve();
      }
    }

    class FakeMediaRecorder {
      static isTypeSupported() {
        return true;
      }

      stream: unknown;
      mimeType: string;
      state = "inactive";
      ondataavailable: ((event: BlobEvent) => void) | null = null;
      onstop: (() => void) | null = null;
      chunkTimer: number | null = null;

      constructor(stream: unknown, options?: { mimeType?: string }) {
        this.stream = stream;
        this.mimeType = options?.mimeType ?? "audio/webm";
      }

      start() {
        this.state = "recording";
        this.chunkTimer = window.setTimeout(() => {
          if (this.state !== "recording") {
            return;
          }
          this.ondataavailable?.(
            new BlobEvent("dataavailable", {
              data: new Blob(["live-audio"], { type: this.mimeType })
            })
          );
        }, 150);
      }

      stop() {
        if (this.state === "inactive") {
          return;
        }
        this.state = "inactive";
        if (this.chunkTimer !== null) {
          window.clearTimeout(this.chunkTimer);
          this.chunkTimer = null;
        }
        this.onstop?.();
      }
    }

    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      writable: true,
      value: FakeAudioContext
    });

    Object.defineProperty(window, "MediaRecorder", {
      configurable: true,
      writable: true,
      value: FakeMediaRecorder
    });

    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: async () => ({
          getTracks: () => [
            {
              stop() {}
            }
          ]
        })
      }
    });
  });

  let createdSessionId = "live-session-1";

  await page.route("**/api/dashboard", async (route) => {
    await route.fulfill({
      json: {
        sessions: [],
        vocabulary: [],
        parameters: []
      }
    });
  });

  await page.route("**/api/sessions", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }

    await route.fulfill({
      json: {
        id: createdSessionId,
        source: "live",
        status: "ready",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        raw_transcript: "",
        corrected_transcript: "",
        avg_confidence: 0,
        duration_seconds: 0,
        processing_ms: 0,
        chunk_count: 0,
        language: null
      }
    });
  });

  await page.route("**/api/sessions/*/chunks", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 5000));
    await route.fulfill({
      json: {
        session: {
          id: createdSessionId,
          source: "live",
          status: "ready",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          raw_transcript: "This captured live result should finish rendering.",
          corrected_transcript: "This captured live result should finish rendering.",
          avg_confidence: 0.91,
          duration_seconds: 4,
          processing_ms: 5000,
          chunk_count: 1,
          language: "en"
        },
        raw_transcript: "This captured live result should finish rendering.",
        corrected_transcript: "This captured live result should finish rendering.",
        avg_confidence: 0.91,
        duration_seconds: 4,
        processing_ms: 5000,
        chunk_count: 1,
        words: []
      }
    });
  });

  await page.goto("/");

  await page.getByRole("button", { name: /Start live capture/i }).click();
  await expect(page.getByText(/Processing audio locally/i)).toBeVisible({ timeout: 10000 });

  const stopButton = page.getByRole("button", { name: /Stop live capture/i });
  await expect(stopButton).toBeEnabled();
  await stopButton.click();

  await expect(
    page.getByText(/Processing the captured audio that is already queued/i)
  ).toBeVisible();

  await expect(page.getByText(/Processing audio locally/i)).toBeVisible({ timeout: 2000 });
  await expect(stopButton).toBeDisabled();

  await expect(page.getByTestId("corrected-transcript")).toContainText(
    /captured live result should finish rendering/i,
    { timeout: 8000 }
  );
});

test("uploads audio, produces corrected text, and manages vocabulary", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      name: /High-fidelity correction for partial, noisy, and broken speech/i
    })
  ).toBeVisible();

  const sampleAudio = path.resolve("tests/assets/sample_partial_speech.wav");
  await page.locator('input[type="file"]').setInputFiles(sampleAudio);

  const correctedTranscript = page.getByTestId("corrected-transcript");
  await expect(correctedTranscript).not.toContainText("Corrected output will appear here", {
    timeout: 600000
  });
  await expect(correctedTranscript).toContainText(/clear and complete transcript/i, {
    timeout: 600000
  });

  await page.getByPlaceholder("Add preferred words, product names, people").fill("Kushumanjali");
  await page.getByPlaceholder("Optional pronunciation hint").fill("koo-shoo-man-ja-lee");
  await page.getByRole("button", { name: /Add term/i }).click();

  await expect(page.getByText("Kushumanjali", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Delete Kushumanjali/i }).click();
  await expect(page.getByText("Kushumanjali", { exact: true })).toHaveCount(0);

  await expect(page.locator(".session-row").first()).toBeVisible();
});

