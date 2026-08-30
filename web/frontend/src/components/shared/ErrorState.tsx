import React from 'react';
import { AlertCircle } from 'lucide-react';
import { useT } from '../../i18n/context';
import Button from './Button';

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

/**
 * Consistent error display with optional retry button.
 * Retry triggers a callback instead of page reload.
 */
const ErrorState: React.FC<ErrorStateProps> = ({ message, onRetry }) => {
  const t = useT();
  return (
  <div className="animate-fade-rise flex flex-col items-center justify-center h-96 gap-4">
    <div className="flex items-center gap-3 text-red-500">
      <AlertCircle className="w-6 h-6" />
      <span className="text-sm font-medium">{message}</span>
    </div>
    {onRetry && <Button onClick={onRetry}>{t('common.retry')}</Button>}
  </div>
  );
};

export default ErrorState;
