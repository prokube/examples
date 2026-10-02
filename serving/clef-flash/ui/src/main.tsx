import { createRoot } from 'react-dom/client';

import { App } from './App';
import './styles.css';

await import(/* @vite-ignore */ new URL('config.js', document.baseURI).href);

const root = document.getElementById('root');
if (root === null) throw new Error('Application root is missing');

const policy = window.__CLEF_POLICY__;
const configured = policy === 'heuristic' || policy === 'clef';

createRoot(root).render(
  <App initialMode={configured ? policy : 'heuristic'} policyLocked={configured} />,
);
