import { TestBed } from '@angular/core/testing';
import { describe, beforeEach, expect, it, vi } from 'vitest';

import { ChatConnection } from './chat-connection';

describe('ChatConnection', () => {
  let service: ChatConnection;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(ChatConnection);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('updatesFor returns the same ReplaySubject for the same callId', () => {
    expect(service.updatesFor('call-1')).toBe(service.updatesFor('call-1'));
  });

  it('updatesFor replays the most recent value to late subscribers', () => {
    service.updatesFor('call-1').next({ status: 'confirmed' });

    const received: Record<string, unknown>[] = [];
    service.updatesFor('call-1').subscribe((value) => received.push(value));

    expect(received).toEqual([{ status: 'confirmed' }]);
  });

  it('send warns and does not throw before connect() has been called', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    expect(() => service.send({ type: 'user_message', text: 'hi' })).not.toThrow();
    expect(warn).toHaveBeenCalled();
  });
});
