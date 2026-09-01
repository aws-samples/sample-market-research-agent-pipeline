export interface NewsItem {
  title: string;
  keywords: string[];
  summary: string;
  insights?: string;
  implications?: string;
  citation: string | string[]; // Source URL for this news item
  published_date?: (string | null)[]; // Published dates corresponding to citations
  date?: string;
  news_from_date?: string;
  last_updated?: string;
  customer?: string;
  no_record_found?: boolean;
}

// Category type - Competitive Landscape or Deals & Partnerships
export type Category = 'competitive_landscape' | 'deals_and_partnerships';

// S3 object representing a news item with metadata
export interface S3NewsItem extends NewsItem {
  research_topic: string;
  category: Category;
  date: string;
  s3Key: string;
}

// Grouped news data by category
export interface CategoryNewsData {
  competitive_landscape: S3NewsItem[];
  deals_and_partnerships: S3NewsItem[];
}

// Sidebar tree item — supports collapsible scheduled folders
export interface SidebarItem {
  name: string;            // raw S3 folder name (used as key for data fetching)
  displayName: string;     // human-readable formatted name
  isScheduled: boolean;    // true → collapsible parent
  children?: SidebarItem[]; // sub-run folders (only for scheduled parents)
}

// Intelligence Brief data structure
export interface IntelligenceBriefData {
  research_topic: string;
  lastUpdated: string;
  categories: CategoryNewsData;
}

// Loading and error states
export interface DataState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

// Configuration for AWS services
export interface AWSConfig {
  region: string;
  identityPoolId: string;
  s3Bucket: string;
  enrichmentKeywordsBucket: string;
  domainsConfigBucket: string;
}
