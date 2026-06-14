import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, beforeEach, expect, it, vi } from 'vitest';

import { UIActionResult } from '../../models/protocol';
import { ChatConnection } from '../../services/chat-connection';
import { Chat } from './chat';

describe('Chat', () => {
  let component: Chat;
  let fixture: ComponentFixture<Chat>;
  let connection: ChatConnection;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Chat],
    }).compileComponents();

    fixture = TestBed.createComponent(Chat);
    component = fixture.componentInstance;
    connection = TestBed.inject(ChatConnection);
    // Avoid opening a real WebSocket during tests; `connection.messages` and
    // `updatesFor` remain real so the rest of ChatConnection is exercised.
    vi.spyOn(connection, 'connect').mockImplementation(() => {});
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('tracks the thinking state from status messages', () => {
    connection.messages.next({ type: 'status', state: 'thinking' });
    expect(component.thinking()).toBe(true);

    connection.messages.next({ type: 'status', state: 'idle' });
    expect(component.thinking()).toBe(false);
  });

  it('appends chat items for assistant/tool/notice/error messages', () => {
    connection.messages.next({ type: 'assistant_message', text: 'Hallo!' });
    connection.messages.next({ type: 'tool_call', callId: 'c1', server: 'room-booking', tool: 'show_booking_form', args: {} });
    connection.messages.next({
      type: 'tool_result',
      callId: 'c1',
      server: 'room-booking',
      tool: 'show_booking_form',
      isError: false,
      summary: 'ok',
    });
    connection.messages.next({ type: 'notice', level: 'info', message: 'hi' });
    connection.messages.next({ type: 'error', message: 'oops' });

    expect(component.items().map((item) => item.kind)).toEqual([
      'assistant',
      'tool_call',
      'tool_result',
      'notice',
      'error',
    ]);
  });

  it('renders a ui_resource as a chat item and does not append one for ui_update', () => {
    connection.messages.next({
      type: 'ui_resource',
      callId: 'c1',
      server: 'room-booking',
      resource: { uri: 'ui://room-booking/booking-form', mimeType: 'text/html', text: '<p>hi</p>' },
      sandbox: { sandboxAttributes: 'allow-scripts allow-forms', csp: "default-src 'none';", trustLevel: 'trusted' },
    });
    expect(component.items()).toHaveLength(1);
    expect(component.items()[0]).toMatchObject({ kind: 'ui_resource', callId: 'c1' });

    connection.messages.next({ type: 'ui_update', callId: 'c1', data: { status: 'confirmed' } });
    expect(component.items()).toHaveLength(1);
  });

  it('send() appends a user item, forwards it to ChatConnection and clears the draft', () => {
    const sendSpy = vi.spyOn(connection, 'send');

    component.draft = 'Hallo';
    component.send();

    expect(component.items().at(-1)).toMatchObject({ kind: 'user', text: 'Hallo' });
    expect(sendSpy).toHaveBeenCalledWith({ type: 'user_message', text: 'Hallo' });
    expect(component.draft).toBe('');
  });

  it('onUiAction forwards a ui_action message with the given callId', () => {
    const sendSpy = vi.spyOn(connection, 'send');
    const action: UIActionResult = { type: 'notify', payload: { message: 'hi' } };

    component.onUiAction('c1', action);

    expect(sendSpy).toHaveBeenCalledWith({ type: 'ui_action', callId: 'c1', action });
  });
});
