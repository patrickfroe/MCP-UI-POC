import {
  AfterViewInit,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  ViewChild,
  signal,
} from '@angular/core';
import { Observable, Subscription } from 'rxjs';

import { ResourcePayload, SandboxPolicy, UIActionResult, parseUIActionResult } from '../../models/protocol';

const MIN_HEIGHT_PX = 140;
const MAX_HEIGHT_PX = 720;

/**
 * Injected into every rendered ui_resource document. Mirrors
 * docs/konzept-mcp-apps.md 6.3:
 *  - reports document-size changes to the host (`ui-size-changed`) so the
 *    iframe can be resized without `allow-same-origin`,
 *  - re-dispatches host -> iframe `ui-update` postMessages as a
 *    `mcp-ui-update` CustomEvent on `document`, so resources only need a
 *    plain `addEventListener` (see mcp-server-example's templates.py).
 */
const BOOTSTRAP_SCRIPT = `
(function () {
  function reportSize() {
    var height = document.documentElement.scrollHeight;
    window.parent.postMessage({ type: 'ui-size-changed', payload: { height: height } }, '*');
  }

  window.addEventListener('message', function (event) {
    var data = event.data;
    if (data && data.type === 'ui-update') {
      document.dispatchEvent(new CustomEvent('mcp-ui-update', { detail: data.payload }));
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    reportSize();
    if (window.ResizeObserver) {
      new ResizeObserver(reportSize).observe(document.body);
    }
  });

  window.addEventListener('load', reportSize);
})();
`;

/**
 * Renders a `ui_resource` (rawHtml) in a sandboxed iframe and mediates the
 * `UIActionResult` postMessage protocol (docs/konzept-mcp-apps.md 6/7).
 *
 * Security-critical invariants:
 *  - `sandbox` and `csp` are applied exactly as received from the backend
 *    (never widened here).
 *  - incoming `message` events are only accepted if `event.source` is
 *    *this* iframe's `contentWindow` (opaque-origin iframes report
 *    `event.origin === "null"`, so a string check would be meaningless).
 *  - `event.data` is validated against the strict `UIActionResult` schema;
 *    anything else is dropped and logged.
 */
@Component({
  selector: 'app-mcp-ui-frame',
  imports: [],
  templateUrl: './mcp-ui-frame.html',
  styleUrl: './mcp-ui-frame.css',
})
export class McpUiFrame implements AfterViewInit, OnChanges, OnDestroy {
  @Input({ required: true }) resource!: ResourcePayload;
  @Input({ required: true }) sandbox!: SandboxPolicy;
  @Input() updates: Observable<Record<string, unknown>> | null = null;

  @Output() action = new EventEmitter<UIActionResult>();

  @ViewChild('frame', { static: true }) frameRef!: ElementRef<HTMLIFrameElement>;

  readonly heightPx = signal(MIN_HEIGHT_PX);

  private updatesSub?: Subscription;
  private readonly onMessage = (event: MessageEvent) => this.handleMessage(event);

  ngAfterViewInit(): void {
    window.addEventListener('message', this.onMessage);
    this.renderDocument();

    this.updatesSub = this.updates?.subscribe((data) => this.pushUpdate(data));
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['resource'] && !changes['resource'].firstChange) {
      this.renderDocument();
    }
  }

  ngOnDestroy(): void {
    window.removeEventListener('message', this.onMessage);
    this.updatesSub?.unsubscribe();
  }

  private renderDocument(): void {
    const iframe = this.frameRef.nativeElement;
    // Angular refuses to bind `sandbox` from a template expression (NG0910),
    // since a maliciously-constructed value could widen the sandbox. The
    // template therefore ships the most restrictive `sandbox=""` and this
    // (backend-computed, never-widened) value is applied via direct DOM
    // access instead.
    iframe.setAttribute('sandbox', this.sandbox.sandboxAttributes);
    iframe.srcdoc = this.buildDocument();
  }

  /**
   * Wraps the raw HTML from the `ui_resource` with the backend-computed CSP
   * `<meta>` tag and the bootstrap script. The CSP tag is inserted as the
   * *first* element of `<head>` so it applies to everything that follows.
   */
  private buildDocument(): string {
    const html = this.decodeContent();
    const cspContent = this.sandbox.csp.replace(/"/g, '&quot;');
    const cspTag = `<meta http-equiv="Content-Security-Policy" content="${cspContent}">`;
    const bootstrapTag = `<script>${BOOTSTRAP_SCRIPT}</script>`;

    if (/<head[^>]*>/i.test(html)) {
      return html
        .replace(/<head([^>]*)>/i, `<head$1>${cspTag}${bootstrapTag}`);
    }

    return `<!DOCTYPE html><html><head>${cspTag}${bootstrapTag}</head><body>${html}</body></html>`;
  }

  private decodeContent(): string {
    if (this.resource.text != null) {
      return this.resource.text;
    }
    if (this.resource.blob != null) {
      return atob(this.resource.blob);
    }
    return '';
  }

  private handleMessage(event: MessageEvent): void {
    if (event.source !== this.frameRef.nativeElement.contentWindow) {
      return;
    }

    const data = event.data as Record<string, unknown> | null;
    if (data && data['type'] === 'ui-size-changed') {
      this.applySize(data['payload']);
      return;
    }

    const action = parseUIActionResult(data);
    if (action) {
      this.action.emit(action);
    } else {
      console.warn('Ignoring message from ui_resource iframe (does not match UIActionResult)', event.data);
    }
  }

  private applySize(payload: unknown): void {
    const height = (payload as { height?: unknown } | undefined)?.height;
    if (typeof height !== 'number' || !Number.isFinite(height)) {
      return;
    }
    this.heightPx.set(Math.min(Math.max(height, MIN_HEIGHT_PX), MAX_HEIGHT_PX));
  }

  /** Forward a backend `ui_update` into the iframe (see 6.3, step 4). */
  private pushUpdate(data: Record<string, unknown>): void {
    this.frameRef.nativeElement.contentWindow?.postMessage({ type: 'ui-update', payload: data }, '*');
  }
}
