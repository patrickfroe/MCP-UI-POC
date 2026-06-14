import { Component } from '@angular/core';

import { Chat } from './components/chat/chat';

@Component({
  selector: 'app-root',
  imports: [Chat],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {}
