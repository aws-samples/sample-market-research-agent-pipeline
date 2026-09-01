import React, { useState, useEffect, useRef } from 'react';
import { getCurrentUser, signOut } from './services/authService';
import Login from './components/Login';
import Header from './components/Header';
import CategorySection from './components/CategorySection';
import LoadingSpinner from './components/LoadingSpinner';
import CreateProjectModal, { ProjectFormData } from './components/CreateProjectModal';
import Toast from './components/Toast';
import { fetchBriefData, listTopics, refreshNewsItem, uploadFileToS3, buildSidebarTree, extractRunDateFromTopic } from './services/s3Service';
import { createProject } from './services/agentService';
import { CategoryNewsData, SidebarItem } from './types/newsletter.types';
import { getAWSConfig } from './services/authService';

// Build the API payload from form data, handling on-demand and scheduler types
const buildProjectPayload = (projectData: ProjectFormData, config: any, s3Key: string) => {
  const payload: any = {
    research_topic: projectData.research_topic.split(',').map(s => s.trim()),
    enrichment_bucket: projectData.enrichmentFile ? config.enrichmentKeywordsBucket : '',
    enrichment_key: s3Key,
    customer: projectData.customer,
    category: projectData.kitsKips ? projectData.kitsKips.split(',').map(s => s.trim()) : [],
    type: projectData.type,
  };

  // On-demand: add from_date (convert from YYYY-MM-DD to M/D/YYYY)
  if (projectData.type === 'on-demand' && projectData.fromDate) {
    const [year, month, day] = projectData.fromDate.split('-');
    payload.from_date = `${parseInt(month)}/${parseInt(day)}/${year}`;
  }

  // Scheduler: add frequency, day selection, and time
  if (projectData.type === 'scheduler' && projectData.frequency) {
    payload.frequency = projectData.frequency;
    if (projectData.time) payload.time = projectData.time;
    if (projectData.frequency === 'weekly' && projectData.dayOfWeek) payload.day_of_week = projectData.dayOfWeek;
    if (projectData.frequency === 'monthly' && projectData.dayOfMonth) payload.day_of_month = projectData.dayOfMonth;
  }

  return payload;
};

const App: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [selectedTopic, setSelectedTopic] = useState<string>('');
  const [sidebarItems, setSidebarItems] = useState<SidebarItem[]>([]);
  const [expandedSchedules, setExpandedSchedules] = useState<Set<string>>(new Set());
  const [isScheduledExpanded, setIsScheduledExpanded] = useState<boolean>(true);
  const [categoryData, setCategoryData] = useState<CategoryNewsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [customerName, setCustomerName] = useState<string>('');
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [isGeneratingProject, setIsGeneratingProject] = useState<boolean>(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState<number>(256);
  const [isResizing, setIsResizing] = useState<boolean>(false);
  // Track whether we're waiting for a newly created on-demand folder's data to load
  const pendingOnDemandNav = useRef<boolean>(false);

  // Helper to load and build sidebar tree
  const reloadSidebarTree = async () => {
    const topFolders = await listTopics();
    const tree = await buildSidebarTree(topFolders);
    setSidebarItems(tree);
    return tree;
  };

  useEffect(() => {
    if (!isResizing) {
      document.body.style.cursor = '';
      return;
    }

    document.body.style.cursor = 'col-resize';
    const handleMouseMove = (e: MouseEvent) => {
      // Limit sidebar width between 200px and 800px
      setSidebarWidth(Math.max(200, Math.min(800, e.clientX)));
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
    };
  }, [isResizing]);

  const startResizing = (e: React.MouseEvent) => {
    setIsResizing(true);
    e.preventDefault();
  };

  // Check authentication on mount
  useEffect(() => {
    getCurrentUser()
      .then(() => setIsAuthenticated(true))
      .catch(() => setIsAuthenticated(false))
      .finally(() => setCheckingAuth(false));
  }, []);

  // Toggle expand/collapse for a scheduled parent
  const toggleSchedule = (name: string) => {
    setExpandedSchedules((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  // Load available topics on mount (after auth)
  useEffect(() => {
    if (!isAuthenticated) return;

    const loadTopics = async () => {
      try {
        const tree = await reloadSidebarTree();

        // Auto-select the first selectable item
        if (tree.length > 0) {
          const first = tree[0];
          if (first.isScheduled && first.children && first.children.length > 0) {
            setExpandedSchedules(new Set([first.name]));
            setSelectedTopic(first.children[0].name);
          } else {
            setSelectedTopic(first.name);
          }
        } else {
          setLoading(false);
        }

      } catch (err) {
        console.error('Failed to load topics:', err);
        setError('Failed to load available topics. Please check your AWS configuration.');
        setLoading(false);
      }
    };

    loadTopics();
  }, [isAuthenticated]);

  // Load intelligence brief data when topic changes
  useEffect(() => {
    if (!selectedTopic || !isAuthenticated) return;

    const loadBriefData = async () => {
      setLoading(true);
      setError(null);

      try {
        const data = await fetchBriefData(selectedTopic);
        setCategoryData(data);

        const allItems = [...data.competitive_landscape, ...data.deals_and_partnerships];
        if (allItems.length > 0) {
          setLastUpdated(allItems[0].news_from_date || '');
          setCustomerName(allItems[0].customer || '');
        } else {
          setLastUpdated('');
          setCustomerName('');
        }
      } catch (err) {
        console.error('Failed to load intelligence brief data:', err);
        setError('Failed to load intelligence brief data. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    loadBriefData();
  }, [selectedTopic, isAuthenticated]);

  // When loading finishes after a pending on-demand navigation, dismiss the overlay
  useEffect(() => {
    if (!loading && pendingOnDemandNav.current) {
      pendingOnDemandNav.current = false;
      setIsGeneratingProject(false);
    }
  }, [loading]);


  const handleRefreshItem = async (s3Key: string) => {
    const refreshedItem = await refreshNewsItem(s3Key);
    if (!refreshedItem || !categoryData) return;

    setCategoryData({
      competitive_landscape: categoryData.competitive_landscape.map(item =>
        item.s3Key === s3Key ? refreshedItem : item
      ),
      deals_and_partnerships: categoryData.deals_and_partnerships.map(item =>
        item.s3Key === s3Key ? refreshedItem : item
      ),
    });
  };

  const handleCreateProject = async (projectData: ProjectFormData) => {
    try {
      const config = getAWSConfig();
      let s3Key = '';

      if (projectData.enrichmentFile) {
        s3Key = await uploadFileToS3(
          projectData.enrichmentFile,
          projectData.research_topic,
          config.enrichmentKeywordsBucket
        );
      }

      const payload = buildProjectPayload(projectData, config, s3Key);

      setIsModalOpen(false);
      setIsGeneratingProject(true);

      const response = await createProject(payload);

      if (response.success) {
        setToast({ message: 'Project creation started! Waiting for project folder...', type: 'success' });

        const prefix = response.response?.prefix;

        if (prefix) {
          // Poll S3 listTopics to check if the prefix has been created
          const maxAttempts = 40; // max 2 minutes (40 * 3s)
          let attempts = 0;

          const pollInterval = setInterval(async () => {
            attempts++;
            try {
              const currentFolders = await listTopics();
              // Check if the exact prefix (top-level folder) exists
              if (currentFolders.includes(prefix)) {
                clearInterval(pollInterval);
                setToast({ message: 'Project folder created successfully!', type: 'success' });

                // Refresh sidebar
                await reloadSidebarTree();

                // For on-demand, keep the overlay alive while the data loads
                if (!prefix.includes('_scheduled_')) {
                  pendingOnDemandNav.current = true;
                  // isGeneratingProject stays true; dismissed once loading flips false
                }

                // Auto-navigate to the new folder
                if (prefix.includes('_scheduled_')) {
                  setExpandedSchedules(prev => new Set(prev).add(prefix));
                  setIsGeneratingProject(false);
                }
                setSelectedTopic(prefix);
              } else if (attempts >= maxAttempts) {
                clearInterval(pollInterval);
                setIsGeneratingProject(false);
                setToast({ message: 'Project is taking longer than expected. Please refresh later.', type: 'error' });
                await reloadSidebarTree();
              }
            } catch (err) {
              console.error('Error polling topics:', err);
            }
          }, 3000); // Check every 3 seconds
        } else {
          // Fallback if no prefix is returned
          setIsGeneratingProject(false);
          await reloadSidebarTree();
        }

      } else {
        setIsGeneratingProject(false);
        setToast({ message: `Failed to create project: ${response.error}`, type: 'error' });
      }

    } catch (error) {
      setIsGeneratingProject(false);
      console.error('Failed to create project:', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setToast({ message: `Failed to create project: ${errorMessage}`, type: 'error' });
    }
  };

  const handleLogout = async () => {
    try {
      await signOut();
      setIsAuthenticated(false);
    } catch (error) {
      console.error('Failed to log out:', error);
    }
  };

  // Show loading while checking authentication
  if (checkingAuth) {
    return <LoadingSpinner message="Loading..." />;
  }

  // Show login if not authenticated
  if (!isAuthenticated) {
    return <Login onLoginSuccess={() => setIsAuthenticated(true)} />;
  }

  // Show loading state
  if (loading && !categoryData) {
    return <LoadingSpinner message="Loading market research intelligence..." />;
  }

  // Show error state
  if (error && !categoryData) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 p-4">
        <div className="bg-white rounded-xl shadow-lg p-8 max-w-md text-center">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">Unable to Load Intelligence Brief</h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <button onClick={() => window.location.reload()} className="bg-primary-600 hover:bg-primary-700 text-white font-medium px-6 py-2 rounded-lg transition-colors">
            Try Again
          </button>
        </div>
      </div>
    );
  }

  // Renders the child run items for a scheduled parent
  const renderScheduledChildren = (item: SidebarItem) => {
    if (!expandedSchedules.has(item.name) || !item.children) return null;

    return (
      <div className="ml-5 mt-1 space-y-0.5 border-l-2 border-indigo-50 pl-2">
        {item.children.map((child) => (
          <button
            key={child.name}
            onClick={() => setSelectedTopic(child.name)}
            className={`w-full text-left px-3 py-1.5 rounded-lg text-xs font-medium transition-colors truncate ${selectedTopic === child.name ? 'bg-primary-100 text-primary-800' : 'text-gray-600 hover:bg-gray-100'
              }`}
            title={child.displayName}
          >
            {child.displayName}
          </button>
        ))}
        {item.children.length === 0 && (
          <p className="text-xs text-gray-400 px-3 py-1">No runs yet</p>
        )}
      </div>
    );
  };

  // Renders a single scheduled parent item with its toggle and children
  const renderScheduleParentItem = (item: SidebarItem) => (
    <div key={item.name}>
      <button
        onClick={() => toggleSchedule(item.name)}
        className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100 transition-colors"
      >
        <span className="flex items-center gap-2 truncate">
          <svg className="w-4 h-4 flex-shrink-0 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <span className="truncate" title={item.displayName}>{item.displayName}</span>
        </span>
        <svg
          className={`w-4 h-4 flex-shrink-0 text-gray-400 transition-transform duration-200 ${expandedSchedules.has(item.name) ? 'rotate-90' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </button>
      {renderScheduledChildren(item)}
    </div>
  );

  // Helper to render the sidebar nav items (shared between no-data and main views)
  const renderSidebarNav = () => {
    const regularItems = sidebarItems.filter(item => !item.isScheduled);
    const scheduledItems = sidebarItems.filter(item => item.isScheduled);

    return (
      <nav className="space-y-1">
        {regularItems.map((item) => (
          <button
            key={item.name}
            onClick={() => setSelectedTopic(item.name)}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-colors ${selectedTopic === item.name ? 'bg-primary-100 text-primary-800' : 'text-gray-700 hover:bg-gray-100'
              }`}
          >
            {item.displayName}
          </button>
        ))}

        {scheduledItems.length > 0 && (
          <div className="mt-4">
            <button
              onClick={() => setIsScheduledExpanded(!isScheduledExpanded)}
              className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-semibold text-gray-900 hover:bg-gray-100 transition-colors"
            >
              <span className="flex items-center gap-2">
                <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Scheduled
              </span>
              <svg
                className={`w-4 h-4 text-gray-500 transition-transform duration-200 ${isScheduledExpanded ? 'rotate-90' : ''}`}
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>

            {isScheduledExpanded && (
              <div className="ml-1 mt-1 space-y-1 border-l-2 border-gray-100 pl-2">
                {scheduledItems.map(renderScheduleParentItem)}
              </div>
            )}
          </div>
        )}
      </nav>
    );
  };

  // Show no data state
  if (sidebarItems.length === 0 && !loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex">
        <aside style={{ width: `${sidebarWidth}px` }} className="bg-white border-r border-gray-200 fixed h-full flex flex-col z-20">
          <div className="p-4 flex-1 overflow-y-auto">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Projects</h2>
            <p className="text-sm text-gray-400">No intelligence briefs available</p>
          </div>
          <div className="p-4 border-t border-gray-200 flex-shrink-0">
            <button
              onClick={handleLogout}
              className="w-full flex items-center px-3 py-2 text-sm font-medium text-gray-700 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
              Log out
            </button>
          </div>
          <div
            className="absolute top-0 right-0 w-1.5 h-full cursor-col-resize hover:bg-indigo-300 opacity-0 hover:opacity-100 transition-opacity z-10"
            onMouseDown={startResizing}
          />
        </aside>

        <div style={{ marginLeft: `${sidebarWidth}px` }} className="flex-1 flex flex-col items-center justify-center">
          <div className="bg-white rounded-xl shadow-lg p-8 max-w-md text-center">
            <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">No Data Available</h2>
            <p className="text-gray-600 mb-4">No intelligence brief has been generated yet.</p>
            <button
              onClick={() => setIsModalOpen(true)}
              className="bg-primary-600 hover:bg-primary-700 text-white font-medium px-6 py-2 rounded-lg transition-colors"
            >
              Create Project
            </button>
          </div>
        </div>

        <CreateProjectModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onSubmit={handleCreateProject} />
        {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      </div>
    );
  }

  // Main intelligence brief app
  return (
    <div className="min-h-screen bg-gray-50 flex">
      <aside style={{ width: `${sidebarWidth}px` }} className="bg-white border-r border-gray-200 fixed h-full flex flex-col z-20">
        <div className="p-4 flex-1 overflow-y-auto">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Projects</h2>
          {renderSidebarNav()}
        </div>
        <div className="p-4 border-t border-gray-200 flex-shrink-0">
          <button
            onClick={handleLogout}
            className="w-full flex items-center px-3 py-2 text-sm font-medium text-gray-700 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Log out
          </button>
        </div>
        <div
          className="absolute top-0 right-0 w-1.5 h-full cursor-col-resize hover:bg-indigo-300 opacity-0 hover:opacity-100 transition-opacity z-10"
          onMouseDown={startResizing}
        />
      </aside>

      <div style={{ marginLeft: `${sidebarWidth}px` }} className="flex-1 flex flex-col min-h-screen">
        <Header topic={selectedTopic} lastUpdated={lastUpdated} runDate={extractRunDateFromTopic(selectedTopic)} onCreateProject={() => setIsModalOpen(true)} customer={customerName} />

        <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
            </div>
          ) : categoryData ? (
            <>
              <CategorySection
                category="competitive_landscape"
                items={categoryData.competitive_landscape}
                onRefresh={handleRefreshItem}
                isProjectEmpty={categoryData.competitive_landscape.length === 0 && categoryData.deals_and_partnerships.length === 0}
                isScheduled={selectedTopic.includes('_scheduled_')}
              />
              <CategorySection
                category="deals_and_partnerships"
                items={categoryData.deals_and_partnerships}
                onRefresh={handleRefreshItem}
                isProjectEmpty={categoryData.competitive_landscape.length === 0 && categoryData.deals_and_partnerships.length === 0}
                isScheduled={selectedTopic.includes('_scheduled_')}
              />
            </>
          ) : null}
        </main>

        <footer className="bg-gray-800 text-white py-6">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <p className="text-sm text-gray-400">Market Research Intelligence • Powered by AI Orchestrator Agent</p>
          </div>
        </footer>
      </div>

      <CreateProjectModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onSubmit={handleCreateProject} />
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}

      {/* Full-screen Loading Overlay for Project Generation */}
      {
        isGeneratingProject && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/40 backdrop-blur-sm transition-opacity duration-300">
            <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-sm w-full text-center flex flex-col items-center">
              <div className="w-16 h-16 relative flex items-center justify-center mb-6">
                <div className="absolute inset-0 rounded-full border-4 border-slate-100"></div>
                <div className="absolute inset-0 rounded-full border-4 border-indigo-600 border-t-transparent animate-spin"></div>
                <svg className="w-6 h-6 text-indigo-600 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h2 className="text-xl font-bold text-slate-800 mb-2">Generating Project</h2>
              <p className="text-slate-500 text-sm">Please wait while the system creates your project...</p>
            </div>
          </div>
        )
      }
    </div >
  );
};

export default App;
