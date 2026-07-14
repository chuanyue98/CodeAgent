import React from 'react';

/**
 * Consistent loading spinner.
 */
const LoadingState: React.FC<{ height?: string }> = ({ height = 'h-96' }) => (
  <div className={`flex items-center justify-center ${height}`}>
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
  </div>
);

export default LoadingState;
