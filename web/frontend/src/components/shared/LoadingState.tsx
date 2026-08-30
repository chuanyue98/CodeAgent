import React from 'react';

/**
 * Consistent loading spinner. `message` renders below the spinner for
 * contexts that want to explain what is loading.
 */
const LoadingState: React.FC<{ height?: string; message?: string }> = ({
  height = 'h-96',
  message,
}) => (
  <div className={`animate-fade-in flex flex-col items-center justify-center gap-2 ${height}`}>
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    {message && <p className="text-xs text-muted-foreground">{message}</p>}
  </div>
);

export default LoadingState;
