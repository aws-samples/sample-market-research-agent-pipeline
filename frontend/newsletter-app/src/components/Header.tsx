import React from 'react';
import { formatFolderName } from '../services/s3Service';

interface HeaderProps {
  topic: string;
  lastUpdated?: string;
  runDate?: string;
  onCreateProject?: () => void;
  customer?: string;
}

const Header: React.FC<HeaderProps> = ({ topic, lastUpdated, runDate, onCreateProject, customer }) => {
  const formattedTopic = formatFolderName(topic);

  return (
    <header className="sticky top-0 z-30 bg-gradient-to-r from-primary-700 to-primary-900 text-white shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between">
          <div>
            <div className="flex items-center space-x-3">
              <div className="bg-white/20 rounded-lg p-2">
                <svg
                  className="w-8 h-8"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z"
                  />
                </svg>
              </div>
              <div>
                <h1 className="text-3xl md:text-4xl font-bold tracking-tight">
                  {formattedTopic}
                </h1>
                <p className="text-primary-100 mt-1 text-sm md:text-base">
                  Market Research Intelligence
                </p>
              </div>
            </div>
          </div>
          <div className="mt-4 md:mt-0 flex items-center justify-end gap-3 sm:gap-4 w-full md:w-auto">
            <div className="flex flex-col items-end justify-center">
              {customer && (
                <div className="text-sm text-primary-200 whitespace-nowrap">
                  <span className="hidden sm:inline">Customer: </span>
                  <span className="text-white font-medium capitalize">{customer}</span>
                </div>
              )}
              {(lastUpdated || runDate) && (
                <div className="text-sm text-primary-200 whitespace-nowrap">
                  <span className="hidden sm:inline">Ingestion Period: </span>
                  {lastUpdated
                    ? (() => {
                      const d = new Date(lastUpdated);
                      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                      return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
                    })()
                    : ''}
                  {lastUpdated && runDate ? ' – ' : ''}
                  {runDate ?? ''}
                </div>
              )}
            </div>

            <button
              onClick={onCreateProject}
              className="bg-white/10 hover:bg-white/20 transition-colors rounded-lg px-4 py-2 flex items-center space-x-2 shrink-0 ml-auto md:ml-0"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              <span className="text-sm font-medium">Generate</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
