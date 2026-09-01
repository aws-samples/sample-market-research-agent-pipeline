import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { S3NewsItem } from '../types/newsletter.types';
import PromptInput from './PromptInput';
import { askAgentToRegenerate, generateInsightsImplications, AgentResponse } from '../services/agentService';
import { getAWSConfig } from '../services/authService';
import { refreshNewsItem, formatTimestampToIst } from '../services/s3Service';
import Toast from './Toast';

interface NewsItemCardProps {
  item: S3NewsItem;
  onRefresh: (s3Key: string) => Promise<void>;
}

const NewsItemCard: React.FC<NewsItemCardProps> = ({ item, onRefresh }) => {
  const [agentResponses, setAgentResponses] = useState<{
    insights?: AgentResponse;
    implications?: AgentResponse;
  }>({});
  const [regeneratingSection, setRegeneratingSection] = useState<'insights' | 'implications' | 'all' | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);

  // Close modal on Escape key
  const handleEscKey = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') setIsDetailOpen(false);
  }, []);

  useEffect(() => {
    if (isDetailOpen) {
      document.addEventListener('keydown', handleEscKey);
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.removeEventListener('keydown', handleEscKey);
      document.body.style.overflow = '';
    };
  }, [isDetailOpen, handleEscKey]);

  const pollUntilUpdated = (section: 'insights' | 'implications' | 'all', oldDate: string) => {
    setRegeneratingSection(section);
    let attempts = 0;
    const maxAttempts = 25;

    const intervalId = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts) {
        clearInterval(intervalId);
        setRegeneratingSection(null);
        setToast({ message: 'Regeneration timed out', type: 'error' });
        return;
      }

      try {
        const freshItem = await refreshNewsItem(item.s3Key);
        // Compare string values robustly, safely defaulting to empty
        const currentDate = freshItem?.last_updated || '';
        if (freshItem && currentDate !== oldDate) {
          clearInterval(intervalId);
          setRegeneratingSection(null);
          setToast({ message: 'Regeneration completed successfully!', type: 'success' });
          await onRefresh(item.s3Key); // Push latest to global state
        }
      } catch (err) {
        console.error('Error during polling:', err);
      }
    }, 5000);
  };

  // Construct full S3 URI from the item's s3Key
  const getS3Uri = (): string => {
    const config = getAWSConfig();
    return `s3://${config.s3Bucket}/${item.s3Key}`;
  };

  // Find the oldest published date if available
  const oldestPublishedDate = useMemo(() => {
    if (!item.published_date || item.published_date.length === 0) return null;

    const validDates = item.published_date
      .filter((d): d is string => !!d)
      .map(d => new Date(d))
      .filter(d => !isNaN(d.getTime()));

    if (validDates.length === 0) return null;

    return new Date(Math.min(...validDates.map(d => d.getTime())));
  }, [item.published_date]);

  // Handler for prompt submissions - calls the regenerate API
  const handlePromptSubmit = async (
    prompt: string,
    section: 'insights' | 'implications',
    s3Uri: string
  ) => {
    console.log('Sending regenerate request to agent:', {
      s3_uri: s3Uri,
      field: section,
      user_instruction: prompt,
    });

    try {
      const response = await askAgentToRegenerate(s3Uri, section, prompt);

      // Store the response for the specific section
      setAgentResponses((prev) => ({
        ...prev,
        [section]: response,
      }));

      if (response.success) {
        console.log('Agent regenerate response received:', response.response);
        setToast({ message: 'Regeneration request submitted successfully', type: 'success' });
        // Start polling immediately with current last_updated timestamp
        pollUntilUpdated(section, item.last_updated || '');
      } else {
        console.error('Agent error:', response.error);
        setToast({ message: response.error || 'Regeneration failed', type: 'error' });
      }

      return response;
    } catch (error) {
      console.error('Failed to invoke agent:', error);
      throw error;
    }
  };


  const s3Uri = getS3Uri();

  const handleGenerateAll = async () => {
    console.log('Sending generate insights/implications request to agent:', {
      s3_uri: s3Uri,
    });
    setRegeneratingSection('all');
    try {
      const response = await generateInsightsImplications(s3Uri);
      if (response.success) {
        setToast({ message: 'Generation request submitted successfully', type: 'success' });
        pollUntilUpdated('all', item.last_updated || '');
      } else {
        setRegeneratingSection(null);
        setToast({ message: response.error || 'Generation failed', type: 'error' });
      }
    } catch (error) {
      setRegeneratingSection(null);
      console.error('Failed to invoke agent:', error);
      setToast({ message: 'Generation failed due to error', type: 'error' });
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm hover:shadow-xl ring-1 ring-gray-900/5 transition-all duration-300 flex flex-col h-full overflow-hidden group relative">
      {/* Expand Button — top-right corner */}
      <button
        onClick={() => setIsDetailOpen(true)}
        className="absolute top-4 right-4 z-10 p-1.5 rounded-lg bg-gray-50 hover:bg-indigo-50 border border-gray-200 hover:border-indigo-200 text-gray-400 hover:text-indigo-600 transition-all duration-200 opacity-0 group-hover:opacity-100"
        title="Expand article"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
      </button>

      {/* Card Header & Content */}
      <div className="p-6 sm:p-8 flex-1 flex flex-col">
        {/* Initially Published Date */}
        {oldestPublishedDate && (
          <div className="mb-3 flex items-center text-xs text-gray-500">
            <span className="flex items-center bg-white px-2.5 py-1 rounded-md border border-gray-200 shadow-sm leading-none">
              <svg className="w-3.5 h-3.5 mr-1.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              Initially Published: {oldestPublishedDate.toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' })}
            </span>
          </div>
        )}

        {/* Title */}
        <h3
          className="text-xl font-bold tracking-tight text-gray-900 mb-4 group-hover:text-indigo-600 transition-colors duration-200 line-clamp-2 min-h-[3.5rem] cursor-pointer hover:underline decoration-indigo-300 underline-offset-4"
          title={item.title}
          onClick={() => setIsDetailOpen(true)}
        >
          {item.title}
        </h3>

        {/* Keywords */}
        <div className="mb-5 overflow-y-auto" style={{ height: '8rem' }}>
          <div className="flex flex-wrap items-start gap-2">
            {item.keywords.map((keyword, index) => (
              <span
                key={index}
                className="inline-flex items-center rounded-full bg-indigo-50/80 px-2.5 py-0.5 text-xs font-semibold text-indigo-700 ring-1 ring-inset ring-indigo-700/10"
              >
                {keyword}
              </span>
            ))}
          </div>
        </div>

        {/* Summary */}
        <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center">
          <svg className="w-4 h-4 mr-1.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          Summary
        </h4>
        <div className="prose prose-sm prose-slate max-w-none mb-6 h-32 overflow-y-auto pr-2">
          <p className="text-slate-600 leading-relaxed text-[15px] m-0">{item.summary}</p>
        </div>

        {/* Generate Insights Button - Always visible unless no_record_found */}
        {!item.no_record_found && (
          <div className="mb-4 flex justify-end">
            <button
              onClick={handleGenerateAll}
              disabled={
                regeneratingSection === 'all' ||
                (!!item.insights && item.insights.trim() !== '' && !!item.implications && item.implications.trim() !== '')
              }
              className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-white transition-colors duration-200 bg-indigo-600 border border-transparent rounded-lg shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-indigo-600"
            >
              {regeneratingSection === 'all' ? (
                <>
                  <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                  </svg>
                  Generating...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  Generate Insights & Implications
                </>
              )}
            </button>
          </div>
        )}

        {/* Insights and Implications (Aligned to bottom of content area) */}
        <div className="mt-auto">
          {(item.insights || item.implications) && (
            <div className="space-y-4 pt-5 border-t border-gray-100/80">
              {/* Insights */}
              {item.insights && (
                <div className="bg-amber-50/40 rounded-xl p-5 border border-amber-100/60 relative overflow-hidden">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-bold text-amber-900 flex items-center">
                      <svg className="w-4 h-4 mr-2 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                      </svg>
                      Key Insights
                    </h4>
                    {regeneratingSection === 'insights' && (
                      <div className="flex items-center text-xs text-amber-600 font-medium animate-pulse">
                        <svg className="animate-spin -ml-1 mr-1.5 h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                        </svg>
                        Regenerating...
                      </div>
                    )}
                  </div>
                  <div className="relative h-32 overflow-y-auto pr-2">
                    {regeneratingSection === 'insights' && <div className="absolute inset-0 bg-white/40 backdrop-blur-[1px] z-10 rounded"></div>}
                    <div className={`text-sm text-slate-700 leading-relaxed m-0 whitespace-pre-line ${regeneratingSection === 'insights' ? 'opacity-40' : ''}`}>
                      {item.insights}
                    </div>
                  </div>
                  <div className="mt-4 pt-4 border-t border-amber-200/40">
                    <PromptInput
                      section="insights"
                      s3Uri={s3Uri}
                      onSubmit={handlePromptSubmit}
                      agentResponse={agentResponses.insights}
                    />
                  </div>
                </div>
              )}

              {/* Implications */}
              {item.implications && (
                <div className="bg-blue-50/40 rounded-xl p-5 border border-blue-100/60 relative overflow-hidden">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-bold text-blue-900 flex items-center">
                      <svg className="w-4 h-4 mr-2 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                      </svg>
                      Implications
                    </h4>
                    {regeneratingSection === 'implications' && (
                      <div className="flex items-center text-xs text-blue-600 font-medium animate-pulse">
                        <svg className="animate-spin -ml-1 mr-1.5 h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                        </svg>
                        Regenerating...
                      </div>
                    )}
                  </div>
                  <div className="relative h-32 overflow-y-auto pr-2">
                    {regeneratingSection === 'implications' && <div className="absolute inset-0 bg-white/40 backdrop-blur-[1px] z-10 rounded"></div>}
                    <div className={`text-sm text-slate-700 leading-relaxed m-0 whitespace-pre-line ${regeneratingSection === 'implications' ? 'opacity-40' : ''}`}>
                      {item.implications}
                    </div>
                  </div>
                  <div className="mt-4 pt-4 border-t border-blue-200/40">
                    <PromptInput
                      section="implications"
                      s3Uri={s3Uri}
                      onSubmit={handlePromptSubmit}
                      agentResponse={agentResponses.implications}
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Footer / Citations */}
      {(item.citation || item.last_updated) && (
        <div className="bg-gray-50/50 border-t border-gray-100 px-6 sm:px-8 py-5">
          {item.last_updated && (
            <div className="flex items-center flex-wrap gap-2 text-xs text-gray-500 mb-4">
              <span className="flex items-center bg-white px-2.5 py-1 rounded-md border border-gray-200 shadow-sm leading-none">
                <svg className="w-3.5 h-3.5 mr-1.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Record Last Updated: {formatTimestampToIst(item.last_updated)}
              </span>
            </div>
          )}

          {item.citation && (() => {
            const citations = Array.isArray(item.citation) ? item.citation : [item.citation];
            const publishedDates = item.published_date || [];

            return (
              <div>
                <h5 className="text-xs font-semibold text-gray-900 mb-2.5 uppercase tracking-wider flex items-center">
                  <svg className="w-3.5 h-3.5 mr-1.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                  </svg>
                  Sources
                </h5>
                <ul className="space-y-2">
                  {citations.map((url, index) => {
                    let displayName = url;
                    try {
                      displayName = new URL(url).hostname.replace('www.', '');
                    } catch (e) { }

                    return (
                      <li key={index} className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-1 sm:gap-4 text-xs pb-2 border-b border-gray-100 last:border-0 last:pb-0">
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-indigo-600 hover:text-indigo-800 font-medium truncate flex-1 block max-w-full hover:underline transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded-sm w-full"
                          title={url}
                        >
                          {displayName}
                        </a>
                        {publishedDates[index] && (
                          <span className="text-gray-500 whitespace-nowrap shrink-0 sm:mt-0 mt-0.5">
                            {new Date(publishedDates[index]!).toLocaleDateString('en-US', {
                              year: 'numeric',
                              month: 'short',
                              day: 'numeric',
                            })}
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })()}
        </div>
      )}
      {/* Detail Modal */}
      {isDetailOpen && (
        <div
          className="fixed inset-0 z-[200] flex items-start justify-center bg-slate-900/50 backdrop-blur-sm overflow-y-auto py-8 px-4"
          onClick={(e) => { if (e.target === e.currentTarget) setIsDetailOpen(false); }}
        >
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl my-auto ring-1 ring-gray-900/10 animate-[fadeInUp_0.25s_ease-out]">
            {/* Modal Header */}
            <div className="bg-white rounded-t-2xl border-b border-gray-100 px-8 py-5 flex items-start justify-between gap-4">
              <h2 className="text-xl font-bold text-gray-900 leading-snug">{item.title}</h2>
              <button
                onClick={() => setIsDetailOpen(false)}
                className="shrink-0 p-1.5 rounded-lg hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-600"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Body */}
            <div className="px-8 py-6 space-y-6">
              {/* Published Date & Keywords */}
              <div className="flex flex-wrap items-center gap-2">
                {oldestPublishedDate && (
                  <span className="inline-flex items-center bg-white px-2.5 py-1 rounded-md border border-gray-200 shadow-sm text-xs text-gray-500">
                    <svg className="w-3.5 h-3.5 mr-1.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    Initially Published: {oldestPublishedDate.toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' })}
                  </span>
                )}
                {item.last_updated && (
                  <span className="inline-flex items-center bg-white px-2.5 py-1 rounded-md border border-gray-200 shadow-sm text-xs text-gray-500">
                    <svg className="w-3.5 h-3.5 mr-1.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    Record Last Updated: {formatTimestampToIst(item.last_updated)}
                  </span>
                )}
              </div>

              {/* Keywords */}
              <div className="flex flex-wrap gap-2">
                {item.keywords.map((keyword, index) => (
                  <span
                    key={index}
                    className="inline-flex items-center rounded-full bg-indigo-50/80 px-3 py-1 text-xs font-semibold text-indigo-700 ring-1 ring-inset ring-indigo-700/10"
                  >
                    {keyword}
                  </span>
                ))}
              </div>

              {/* Summary */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center">
                  <svg className="w-4 h-4 mr-1.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Summary
                </h4>
                <p className="text-slate-600 leading-relaxed text-[15px]">{item.summary}</p>
              </div>

              {/* Insights */}
              {item.insights && (
                <div className="bg-amber-50/40 rounded-xl p-5 border border-amber-100/60">
                  <h4 className="text-sm font-bold text-amber-900 mb-3 flex items-center">
                    <svg className="w-4 h-4 mr-2 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                    Key Insights
                  </h4>
                  <div className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{item.insights}</div>
                </div>
              )}

              {/* Implications */}
              {item.implications && (
                <div className="bg-blue-50/40 rounded-xl p-5 border border-blue-100/60">
                  <h4 className="text-sm font-bold text-blue-900 mb-3 flex items-center">
                    <svg className="w-4 h-4 mr-2 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                    </svg>
                    Implications
                  </h4>
                  <div className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{item.implications}</div>
                </div>
              )}

              {/* Sources */}
              {item.citation && (() => {
                const citations = Array.isArray(item.citation) ? item.citation : [item.citation];
                const publishedDates = item.published_date || [];
                return (
                  <div className="border-t border-gray-100 pt-5">
                    <h5 className="text-xs font-semibold text-gray-900 mb-3 uppercase tracking-wider flex items-center">
                      <svg className="w-3.5 h-3.5 mr-1.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                      </svg>
                      Sources
                    </h5>
                    <ul className="space-y-2">
                      {citations.map((url, index) => {
                        let displayName = url;
                        try { displayName = new URL(url).hostname.replace('www.', ''); } catch (e) { }
                        return (
                          <li key={index} className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-1 sm:gap-4 text-sm pb-2 border-b border-gray-100 last:border-0 last:pb-0">
                            <a href={url} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:text-indigo-800 font-medium hover:underline transition-colors break-all">
                              {displayName}
                            </a>
                            {publishedDates[index] && (
                              <span className="text-gray-500 whitespace-nowrap shrink-0 text-xs">
                                {new Date(publishedDates[index]!).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                              </span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
      )}

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  );
};

export default NewsItemCard;
