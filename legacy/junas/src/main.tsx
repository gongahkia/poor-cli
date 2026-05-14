import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './app/globals.css';
import { getRuntimeMode } from '@/lib/runtime';

if (typeof document !== 'undefined') {
  document.documentElement.setAttribute('data-runtime-mode', getRuntimeMode());
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
