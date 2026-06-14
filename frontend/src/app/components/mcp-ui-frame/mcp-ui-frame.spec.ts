import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { UIActionResult } from '../../models/protocol';
import { McpUiFrame } from './mcp-ui-frame';

const SANDBOX = {
  sandboxAttributes: 'allow-scripts allow-forms',
  csp: "default-src 'none'; script-src 'unsafe-inline';",
  trustLevel: 'untrusted' as const,
};

/** Roughly mirrors the structure of mcp-server-example's booking form. */
const BOOKING_FORM_HTML = `<!DOCTYPE html>
<html lang="de">
  <head>
    <meta charset="utf-8" />
    <style>body { margin: 0; }</style>
  </head>
  <body>
    <form id="booking-form"><button type="submit">Raum buchen</button></form>
  </body>
</html>`;

async function createFixture(resource: { uri: string; mimeType: string; text: string }) {
  const fixture: ComponentFixture<McpUiFrame> = TestBed.createComponent(McpUiFrame);
  fixture.componentRef.setInput('resource', resource);
  fixture.componentRef.setInput('sandbox', SANDBOX);
  await fixture.whenStable();
  return fixture;
}

function getIframe(fixture: ComponentFixture<McpUiFrame>): HTMLIFrameElement {
  return fixture.nativeElement.querySelector('iframe');
}

describe('McpUiFrame', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [McpUiFrame],
    }).compileComponents();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should create', async () => {
    const fixture = await createFixture({ uri: 'ui://test/resource', mimeType: 'text/html', text: '<p>hello</p>' });
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('wraps a fragment without <head> in a CSP meta tag and bootstrap script', async () => {
    const fixture = await createFixture({ uri: 'ui://test/resource', mimeType: 'text/html', text: '<p>hello</p>' });
    const srcdoc = getIframe(fixture).srcdoc;
    expect(srcdoc).toContain('Content-Security-Policy');
    expect(srcdoc).toContain(SANDBOX.csp);
    expect(srcdoc).toContain('<p>hello</p>');
    expect(srcdoc).toContain('mcp-ui-update');
  });

  it('injects the CSP tag and bootstrap script as the first children of an existing <head>', async () => {
    const fixture = await createFixture({ uri: 'ui://room-booking/booking-form', mimeType: 'text/html;profile=mcp-app', text: BOOKING_FORM_HTML });
    const srcdoc = getIframe(fixture).srcdoc;

    const headStart = srcdoc.indexOf('<head');
    const cspIndex = srcdoc.indexOf('Content-Security-Policy');
    const bootstrapIndex = srcdoc.indexOf('ResizeObserver');
    const charsetIndex = srcdoc.indexOf('charset="utf-8"');

    expect(headStart).toBeGreaterThanOrEqual(0);
    expect(cspIndex).toBeGreaterThan(headStart);
    expect(cspIndex).toBeLessThan(charsetIndex);
    expect(bootstrapIndex).toBeGreaterThan(cspIndex);
    expect(bootstrapIndex).toBeLessThan(charsetIndex);
    expect(srcdoc).toContain('<form id="booking-form">');
  });

  it('applies the backend-computed sandbox attribute to the iframe', async () => {
    const fixture = await createFixture({ uri: 'ui://test/resource', mimeType: 'text/html', text: '<p>hello</p>' });
    expect(getIframe(fixture).getAttribute('sandbox')).toBe('allow-scripts allow-forms');
  });

  it('emits a UIActionResult for a recognized message from its own iframe', async () => {
    const fixture = await createFixture({ uri: 'ui://test/resource', mimeType: 'text/html', text: '<p>hello</p>' });
    const iframe = getIframe(fixture);

    const received: UIActionResult[] = [];
    fixture.componentInstance.action.subscribe((action) => received.push(action));

    const action: UIActionResult = {
      type: 'tool',
      payload: { toolName: 'book_room', params: { room_id: 'room-a' } },
    };
    window.dispatchEvent(new MessageEvent('message', { data: action, source: iframe.contentWindow as Window }));

    expect(received).toEqual([action]);
  });

  it('ignores messages that are not from its own iframe', async () => {
    const fixture = await createFixture({ uri: 'ui://test/resource', mimeType: 'text/html', text: '<p>hello</p>' });

    const received: UIActionResult[] = [];
    fixture.componentInstance.action.subscribe((action) => received.push(action));

    const otherFrame = document.createElement('iframe');
    document.body.appendChild(otherFrame);

    const action: UIActionResult = { type: 'notify', payload: { message: 'hi' } };
    window.dispatchEvent(new MessageEvent('message', { data: action, source: otherFrame.contentWindow as Window }));

    expect(received).toEqual([]);
    otherFrame.remove();
  });

  it('drops messages from its own iframe that do not match the UIActionResult schema', async () => {
    const fixture = await createFixture({ uri: 'ui://test/resource', mimeType: 'text/html', text: '<p>hello</p>' });
    const iframe = getIframe(fixture);

    const received: UIActionResult[] = [];
    fixture.componentInstance.action.subscribe((action) => received.push(action));
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    window.dispatchEvent(
      new MessageEvent('message', { data: { type: 'tool', payload: { wrong: true } }, source: iframe.contentWindow as Window }),
    );

    expect(received).toEqual([]);
    expect(warn).toHaveBeenCalled();
  });

  it('resizes the iframe on a ui-size-changed message from its own iframe', async () => {
    const fixture = await createFixture({ uri: 'ui://test/resource', mimeType: 'text/html', text: '<p>hello</p>' });
    const iframe = getIframe(fixture);

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'ui-size-changed', payload: { height: 400 } },
        source: iframe.contentWindow as Window,
      }),
    );
    fixture.detectChanges();

    expect(fixture.componentInstance.heightPx()).toBe(400);
    expect(iframe.style.height).toBe('400px');
  });

  it('forwards ui_update data into the iframe via postMessage', async () => {
    const updates = new Subject<Record<string, unknown>>();
    const fixture: ComponentFixture<McpUiFrame> = TestBed.createComponent(McpUiFrame);
    fixture.componentRef.setInput('resource', { uri: 'ui://test/resource', mimeType: 'text/html', text: '<p>hello</p>' });
    fixture.componentRef.setInput('sandbox', SANDBOX);
    fixture.componentRef.setInput('updates', updates);
    await fixture.whenStable();

    const iframe = getIframe(fixture);
    const postMessage = vi.spyOn(iframe.contentWindow!, 'postMessage');

    updates.next({ status: 'confirmed', roomName: 'Raum A' });

    expect(postMessage).toHaveBeenCalledWith({ type: 'ui-update', payload: { status: 'confirmed', roomName: 'Raum A' } }, '*');
  });
});
