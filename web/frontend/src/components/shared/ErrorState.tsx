import React from 'react';
import { AlertCircle } from 'lucide-react';

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

/**
 * Consistent error display with optional retry button.
 * Retry triggers a callback instead of page reload.
 */
const ErrorState: React.FC<ErrorStateProps> = ({ message, onRetry }) => (
  <div className="animate-fade-rise flex flex-col items-center justify-center h-96 gap-4">
    <div className="flex items-center gap-3 text-red-500">
      <AlertCircle className="w-6 h-6" />
      <span className="text-sm font-medium">{message}</span>
    </div>
    {onRetry && (
      <button
        onClick={onRetry}
        className="px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/90 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_12px_20px_-8px_hsl(192_82%_31%/0.4)] text-sm font-medium"
      >
        重试
      </button>
    )}
  </div>
);

export default ErrorState;
