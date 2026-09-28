import { useLocation } from 'react-router';
import { useTerminal } from '../context/TerminalContext';

/**
 * True while a terminal session fills the terminal page. The app shell hides
 * its header and the section's tab row then, so the conversation gets the
 * screen the way the engines' own web UIs give it.
 */
export function useTerminalFocus(): boolean {
  const { pathname } = useLocation();
  const { tabs, activeTabId } = useTerminal();
  return pathname === '/agent/terminal' && tabs.some(tab => tab.id === activeTabId);
}
