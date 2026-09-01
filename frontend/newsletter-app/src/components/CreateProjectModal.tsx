import React, { useState, useMemo, useRef, useEffect } from 'react';
import { fetchDomainsConfig } from '../services/s3Service';

interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (projectData: ProjectFormData) => void;
}

export interface ProjectFormData {
  enrichmentFile: File | null;
  research_topic: string;
  customer: string;
  kitsKips: string;
  type: string;
  fromDate?: string;
  frequency?: string;
  dayOfWeek?: string;
  dayOfMonth?: string;
  time?: string;
}

const CreateProjectModal: React.FC<CreateProjectModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [formData, setFormData] = useState<ProjectFormData>({
    enrichmentFile: null,
    research_topic: '',
    customer: '',
    kitsKips: '',
    type: '',
  });

  const [executionType, setExecutionType] = useState<'on-demand' | 'scheduler'>('on-demand');
  const [fromDate, setFromDate] = useState<string>('');
  const [frequency, setFrequency] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [dayOfWeek, setDayOfWeek] = useState<string>('1');
  const [dayOfMonth, setDayOfMonth] = useState<string>('');
  const [time, setTime] = useState<string>('');
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [domainsList, setDomainsList] = useState<string[]>([]);
  const [isLoadingDomains, setIsLoadingDomains] = useState(false);

  useEffect(() => {
    if (isOpen) {
      let isMounted = true;
      const loadDomains = async () => {
        setIsLoadingDomains(true);
        try {
          const domains = await fetchDomainsConfig();
          if (isMounted) setDomainsList(domains);
        } catch (error) {
          console.error('Failed to fetch domains', error);
        } finally {
          if (isMounted) setIsLoadingDomains(false);
        }
      };
      loadDomains();
      return () => { isMounted = false; };
    }
  }, [isOpen]);

  const isSubmitDisabled = useMemo(() => {
    const hasRequiredFields = formData.research_topic.trim() !== '' && formData.customer.trim() !== '' && formData.enrichmentFile !== null;
    const hasDateForOnDemand = executionType === 'on-demand' ? fromDate !== '' : true;
    const hasTimeForScheduler = executionType === 'scheduler' ? time !== '' : true;
    return !hasRequiredFields || !hasDateForOnDemand || !hasTimeForScheduler;
  }, [formData.research_topic, formData.customer, formData.enrichmentFile, executionType, fromDate, time]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const submissionData: ProjectFormData = {
      ...formData,
      type: executionType,
      fromDate: executionType === 'on-demand' ? fromDate : undefined,
      frequency: executionType === 'scheduler' ? frequency : undefined,
      dayOfWeek: executionType === 'scheduler' && frequency === 'weekly' ? dayOfWeek : undefined,
      dayOfMonth: executionType === 'scheduler' && frequency === 'monthly' ? dayOfMonth : undefined,
      time: executionType === 'scheduler' ? time : undefined,
    };

    onSubmit(submissionData);
    setFormData({ enrichmentFile: null, research_topic: '', customer: '', kitsKips: '', type: '' });
    setExecutionType('on-demand');
    setFromDate('');
    setFrequency('daily');
    setDayOfWeek('1');
    setDayOfMonth('');
    setTime('');
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const processFile = (file: File | null) => {
    if (file) {
      const isTextExtension = file.name.toLowerCase().endsWith('.txt');
      const isTextMimeType = file.type === 'text/plain';
      const hasNoExtension = !file.name.includes('.');

      if (!isTextExtension && !isTextMimeType && !hasNoExtension) {
        alert('Please select a valid .txt file or a plain text file without an extension');
        return;
      }
    }
    setFormData({ ...formData, enrichmentFile: file });
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    processFile(file);
    if (e.target.value) e.target.value = ''; // reset so we can re-select if needed
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0] || null;
    processFile(file);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 pt-10 sm:pt-14 font-sans text-slate-800">
      {/* Blurred overlay backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-md transition-opacity duration-300"
        onClick={onClose}
        role="button"
        tabIndex={-1}
        aria-label="Close modal"
      />

      {/* Modal Container */}
      <div className="relative bg-white rounded-3xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.3)] w-full max-w-3xl flex flex-col overflow-hidden max-h-[92vh] ring-1 ring-slate-900/5 transform transition-all scale-100 opacity-100">

        {/* Subtle top decoration line */}
        <div className="h-1.5 w-full bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500"></div>

        {/* Header */}
        <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between shrink-0 bg-white/90 backdrop-blur-sm relative z-10">
          <div className="flex items-center space-x-4">
            <div className="p-2.5 bg-indigo-50 text-indigo-600 rounded-xl shadow-sm border border-indigo-100">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
            <div>
              <h2 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-slate-800 to-slate-600">
                Generate News Letter
              </h2>
              <p className="text-sm text-slate-500 font-medium mt-0.5">Define your project details and execution strategy</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-all duration-200"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content Body */}
        <form onSubmit={handleSubmit} className="flex flex-col flex-1 overflow-hidden relative">

          {/* Subtle background gradient blob for aesthetics */}
          <div className="absolute -top-40 -right-40 w-96 h-96 bg-purple-100 rounded-full mix-blend-multiply filter blur-3xl opacity-50 pointer-events-none" />
          <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-indigo-100 rounded-full mix-blend-multiply filter blur-3xl opacity-50 pointer-events-none" />

          <div className="p-8 space-y-8 overflow-y-auto flex-1 relative z-10 custom-scrollbar">

            {/* Project Details Section */}
            <section className="space-y-5">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400">Project Details</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

                {/* Research Topic */}
                <div className="relative group">
                  <label htmlFor="research_topic" className="block text-sm font-semibold text-slate-700 mb-1.5 transition-colors group-focus-within:text-indigo-600">
                    Research Topic <span className="text-rose-500">*</span>
                  </label>
                  <input
                    id="research_topic"
                    type="text"
                    name="research_topic"
                    value={formData.research_topic}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-3 bg-slate-50/50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all duration-200 shadow-sm placeholder-slate-400 text-slate-700"
                    placeholder="e.g., obesity, diabetes"
                  />
                </div>

                {/* Client Account */}
                <div className="relative group">
                  <label htmlFor="customer" className="block text-sm font-semibold text-slate-700 mb-1.5 transition-colors group-focus-within:text-indigo-600">
                    Client Account <span className="text-rose-500">*</span>
                  </label>
                  <input
                    id="customer"
                    type="text"
                    name="customer"
                    value={formData.customer}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-3 bg-slate-50/50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all duration-200 shadow-sm placeholder-slate-400 text-slate-700"
                    placeholder="Enter customer name"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

                {/* Enrichment File (Drag & Drop) */}
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                    Enrichment Keywords <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="file"
                    id="file-upload"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  <div
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className={`flex items-center justify-between w-full h-[50px] px-4 py-3 bg-slate-50/50 border rounded-xl cursor-pointer transition-all duration-200 shadow-sm group ${isDragging
                      ? 'border-indigo-500 bg-indigo-50 ring-2 ring-indigo-500/20'
                      : 'border-slate-200 hover:bg-white hover:border-indigo-400'
                      }`}
                  >
                    <span className={`text-sm font-semibold truncate flex-1 pr-3 ${formData.enrichmentFile ? 'text-slate-800' : 'text-slate-400'}`}>
                      {formData.enrichmentFile ? formData.enrichmentFile.name : 'Click or drag text file to upload'}
                    </span>
                    <div className={`shrink-0 p-1.5 rounded-lg transition-colors ${formData.enrichmentFile || isDragging ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-200 text-slate-500 group-hover:bg-indigo-50 group-hover:text-indigo-500'}`}>
                      {formData.enrichmentFile ? (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                      )}
                    </div>
                  </div>
                </div>

                {/* KITs & KIQs */}
                <div className="relative group">
                  <label htmlFor="kitsKips" className="block text-sm font-semibold text-slate-700 mb-1.5 transition-colors group-focus-within:text-indigo-600">
                    KITs & KIQs <span className="text-slate-400 font-normal ml-1">(Optional)</span>
                  </label>
                  <input
                    id="kitsKips"
                    type="text"
                    name="kitsKips"
                    value={formData.kitsKips}
                    onChange={handleChange}
                    className="w-full px-4 py-3 bg-slate-50/50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all duration-200 shadow-sm placeholder-slate-400 text-slate-700"
                    placeholder="Enter specific tracking keywords"
                  />
                </div>

                {/* Enrichment Keyword Format Helper */}
                <div className="col-span-1 md:col-span-2 -mt-2 p-4 bg-slate-50/80 rounded-xl border border-slate-200/60 shadow-inner group">
                  <div className="flex items-center gap-2 mb-2">
                    <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <p className="text-sm font-bold text-slate-700">Required .txt format</p>
                  </div>
                  <p className="text-xs text-slate-500 mb-2 leading-snug">
                    Please upload a text file containing your mesh terms formatted exactly like this example:
                  </p>
                  <pre className="bg-slate-800 text-emerald-300 text-xs font-mono p-2.5 rounded-lg overflow-x-auto shadow-sm ring-1 ring-slate-900/10 transition-all group-hover:ring-indigo-500/30">
                    {`[
    "Mesh Term 1",
    "Mesh Term 2"
]`}
                  </pre>
                </div>

                {/* Domains List Viewer */}
                <div className="col-span-1 md:col-span-2 p-4 bg-white rounded-xl border border-slate-200/60 shadow-sm group">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>
                      <p className="text-sm font-bold text-slate-700">Tracked Domains ({domainsList.length})</p>
                    </div>
                  </div>
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 h-32 overflow-y-auto">
                    {isLoadingDomains ? (
                      <div className="flex h-full items-center justify-center text-slate-400 text-sm">
                        <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                        Loading domains config...
                      </div>
                    ) : domainsList.length > 0 ? (
                      <ul className="space-y-1.5">
                        {domainsList.map((domain, idx) => (
                          <li key={idx} className="flex items-start text-xs text-slate-600">
                            <span className="text-slate-400 mr-2 mt-0.5">•</span>
                            <span className="break-all">{domain}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="flex h-full items-center justify-center text-slate-400 text-xs">
                        No domains found. Ensure VITE_DOMAINS_CONFIG_BUCKET is fully configured.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </section>

            <hr className="border-slate-100" />

            {/* Execution Strategy Section */}
            <section className="space-y-7">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400">Execution Strategy</h3>

              <div className="flex flex-col gap-4">
                <label className="block text-sm font-semibold text-slate-700 mb-1">
                  Timeline <span className="text-rose-500">*</span>
                </label>

                {/* Segmented Control for Execution Type */}
                <div className="inline-flex p-1.5 bg-slate-100/80 rounded-xl shadow-inner w-full sm:w-[400px]">
                  <button
                    type="button"
                    onClick={() => setExecutionType('on-demand')}
                    className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 text-sm font-semibold rounded-lg transition-all duration-300 ${executionType === 'on-demand'
                      ? 'bg-white text-indigo-700 shadow-[0_2px_8px_rgba(0,0,0,0.08)] scale-100'
                      : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'
                      }`}
                  >
                    <svg className={`w-4 h-4 ${executionType === 'on-demand' ? 'text-indigo-600' : 'text-slate-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                    On-Demand
                  </button>
                  <button
                    type="button"
                    onClick={() => setExecutionType('scheduler')}
                    className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 text-sm font-semibold rounded-lg transition-all duration-300 ${executionType === 'scheduler'
                      ? 'bg-white text-indigo-700 shadow-[0_2px_8px_rgba(0,0,0,0.08)] scale-100'
                      : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'
                      }`}
                  >
                    <svg className={`w-4 h-4 ${executionType === 'scheduler' ? 'text-indigo-600' : 'text-slate-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                    Scheduler
                  </button>
                </div>
              </div>

              {/* Dynamic Strategy Fields */}
              <div className="bg-slate-50/80 p-7 rounded-2xl border border-slate-100 transition-all duration-300 shadow-sm relative overflow-hidden">
                {/* Decorative subtle stripe inside the box */}
                <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-indigo-400 to-purple-400 rounded-l-2xl"></div>

                {executionType === 'on-demand' && (
                  <div className="animate-in fade-in slide-in-from-top-2 duration-300 pl-3">
                    <label htmlFor="fromDate" className="block text-sm font-semibold text-slate-700 mb-2">
                      Fetch News From Date <span className="text-rose-500">*</span>
                    </label>
                    <input
                      id="fromDate"
                      type="date"
                      value={fromDate}
                      onChange={(e) => setFromDate(e.target.value)}
                      required
                      className="w-full sm:w-[300px] px-4 py-3 bg-white border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors shadow-sm text-slate-700"
                    />
                  </div>
                )}

                {executionType === 'scheduler' && (
                  <div className="animate-in fade-in slide-in-from-top-2 duration-300 space-y-6 pl-3">
                    <div>
                      <label className="block text-sm font-semibold text-slate-700 mb-3">
                        Schedule Frequency
                      </label>
                      <div className="flex flex-wrap gap-3">
                        {['daily', 'weekly', 'monthly'].map((freq) => (
                          <button
                            key={freq}
                            type="button"
                            onClick={() => setFrequency(freq as any)}
                            className={`px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 border ${frequency === freq
                              ? 'bg-indigo-600 border-indigo-600 text-white shadow-md shadow-indigo-600/20 translate-y-[-1px]'
                              : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/30'
                              }`}
                          >
                            {freq.charAt(0).toUpperCase() + freq.slice(1)}
                          </button>
                        ))}
                      </div>
                    </div>

                    {frequency === 'weekly' && (
                      <div className="animate-in fade-in zoom-in-95 duration-200">
                        <label className="block text-sm font-semibold text-slate-700 mb-2">
                          Day of Week
                        </label>
                        <select
                          value={dayOfWeek}
                          onChange={(e) => setDayOfWeek(e.target.value)}
                          className="w-full sm:w-[300px] px-4 py-3 bg-white border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 shadow-sm text-slate-700"
                        >
                          <option value="1">Sunday</option>
                          <option value="2">Monday</option>
                          <option value="3">Tuesday</option>
                          <option value="4">Wednesday</option>
                          <option value="5">Thursday</option>
                          <option value="6">Friday</option>
                          <option value="7">Saturday</option>
                        </select>
                      </div>
                    )}

                    {frequency === 'monthly' && (
                      <div className="animate-in fade-in zoom-in-95 duration-200">
                        <label className="block text-sm font-semibold text-slate-700 mb-2">
                          Day of Month
                        </label>
                        <input
                          type="text"
                          value={dayOfMonth}
                          onChange={(e) => {
                            const val = e.target.value;
                            if (val === '' || (/^[1-9]\d*$/.test(val) && parseInt(val) >= 1 && parseInt(val) <= 30)) {
                              setDayOfMonth(val);
                            }
                          }}
                          className="w-full sm:w-[300px] px-4 py-3 bg-white border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 shadow-sm text-slate-700"
                          placeholder="Enter day (1-30)"
                        />
                      </div>
                    )}

                    <div className="animate-in fade-in zoom-in-95 duration-200 pt-2">
                      <label className="block text-sm font-semibold text-slate-700 mb-2">
                        Time of Day <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="time"
                        value={time}
                        onChange={(e) => setTime(e.target.value)}
                        required
                        className="w-full sm:w-[300px] px-4 py-3 bg-white border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 shadow-sm text-slate-700"
                      />
                    </div>
                  </div>
                )}
              </div>
            </section>
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-end gap-3 px-8 py-5 border-t border-slate-100 bg-slate-50/50 shrink-0 relative z-10">
            <button
              type="button"
              onClick={onClose}
              className="px-6 py-2.5 text-sm font-semibold text-slate-600 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 hover:text-slate-800 transition-all duration-200 shadow-sm focus:ring-2 focus:ring-slate-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitDisabled}
              className={`px-8 py-2.5 text-sm font-semibold rounded-xl flex items-center gap-2 transition-all duration-300 shadow-sm ${isSubmitDisabled
                ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                : 'bg-indigo-600 text-white hover:bg-indigo-700 hover:shadow-lg hover:shadow-indigo-600/30 hover:-translate-y-0.5 focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2'
                }`}
            >
              Generate Project
              <svg className="w-4 h-4 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" /></svg>
            </button>
          </div>
        </form>
      </div>

      {/* Basic style tag for simple in-file animation utilities if not natively in their tailwind config */}
      <style>{`
        .animate-in { animation: animateIn 0.3s ease-out forwards; }
        @keyframes animateIn {
          from { opacity: 0; transform: translateY(10px) scale(0.98); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        .custom-scrollbar::-webkit-scrollbar { width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
      `}</style>
    </div>
  );
};

export default CreateProjectModal;

