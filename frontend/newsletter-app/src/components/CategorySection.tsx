import React, { useState } from 'react';
import { S3NewsItem, Category } from '../types/newsletter.types';
import NewsItemCard from './NewsItemCard';

interface CategorySectionProps {
  category: Category;
  items: S3NewsItem[];
  onRefresh: (s3Key: string) => Promise<void>;
  isProjectEmpty?: boolean;
  isScheduled?: boolean;
}

const categoryConfig = {
  competitive_landscape: {
    title: 'Competitive Landscape',
    description: 'Competitor moves, product launches, and strategic positioning',
    icon: (
      <svg
        className="w-6 h-6"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
        />
      </svg>
    ),
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-500',
    textColor: 'text-blue-800',
    badgeColor: 'bg-blue-600',
  },
  deals_and_partnerships: {
    title: 'Deals & Partnerships',
    description: 'M&A activity, licensing deals, and strategic alliances',
    icon: (
      <svg
        className="w-6 h-6"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
        />
      </svg>
    ),
    bgColor: 'bg-emerald-50',
    borderColor: 'border-emerald-500',
    textColor: 'text-emerald-800',
    badgeColor: 'bg-emerald-600',
  },
};

const CategorySection: React.FC<CategorySectionProps> = ({ category, items, onRefresh, isProjectEmpty, isScheduled }) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const config = categoryConfig[category];

  return (
    <section className="mb-8">
      {/* Section Header */}
      <div
        className={`${config.bgColor} border-l-4 ${config.borderColor} rounded-r-lg p-4 cursor-pointer transition-all hover:shadow-md`}
        onClick={() => setIsExpanded(!isExpanded)}
        onKeyDown={(e) => e.key === 'Enter' && setIsExpanded(!isExpanded)}
        role="button"
        tabIndex={0}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className={`${config.textColor}`}>{config.icon}</div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className={`text-xl font-bold ${config.textColor}`}>
                  {config.title}
                </h2>
                <span
                  className={`${config.badgeColor} text-white text-xs font-semibold px-2.5 py-0.5 rounded-full`}
                >
                  {items.length}
                </span>
              </div>
              <p className="text-sm text-gray-600 mt-0.5">{config.description}</p>
            </div>
          </div>
          <button className="p-2 hover:bg-white/50 rounded-full transition-colors">
            <svg
              className={`w-5 h-5 ${config.textColor} transform transition-transform ${isExpanded ? 'rotate-180' : ''
                }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Section Content */}
      {isExpanded && (
        <div className="mt-4 space-y-4">
          {items.length === 0 ? (
            <div className="bg-gray-50 rounded-lg p-8 text-center">
              <svg
                className="w-12 h-12 mx-auto text-gray-400 mb-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
                />
              </svg>
              {isProjectEmpty ? (
                <>
                  <h3 className="text-lg font-medium text-gray-900 mb-1">
                    {isScheduled ? 'Project is scheduled Successfully' : 'Project is running'}
                  </h3>
                  <p className="text-gray-500 max-w-sm mx-auto">
                    News items will appear here once ready.
                  </p>
                </>
              ) : (
                <p className="text-gray-500">No {config.title.toLowerCase()} news items available</p>
              )}
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
              {items.map((item) => (
                <NewsItemCard key={item.s3Key} item={item} onRefresh={onRefresh} />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
};

export default CategorySection;
